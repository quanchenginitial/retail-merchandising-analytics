"""Check whole-basket UTC month anchoring and the complete selected-case month scaffold."""
import argparse
import csv
import hashlib
import json
import math
import re
import shutil
import subprocess
import tempfile
import threading
import time
from collections import Counter
from datetime import datetime, timezone
from fractions import Fraction
from itertools import combinations,groupby,zip_longest
from pathlib import Path

import preflight_retailrocket_pair_visitor_concentration as previous

cases_reference=previous.cases_reference
counts=previous.counts
model=previous.model
staging=previous.staging
source_reference=previous.source_reference
utc_reference=model.events.utc_reference
READSET=['visitorid','transactionid','itemid','first_timestamp_ms']
DISPLAY_TOL=previous.DISPLAY_TOL
CONTRACT_SHA='183d6844786826de601c5fd5cc86ee23e4870bf256adcb484cf7bfc1a7ebf1f9'
SOURCE_MIN_MS=1430622004384
SOURCE_MAX_MS=1442545187788
OUTPUT=['case_label','n_ab','may_baskets','jun_baskets','jul_baskets','aug_baskets','sep_baskets','top_month_share_pct','check_status']
MONTH_FIELDS=['case_rank','month_number','pair_baskets']
MONTHS=[5,6,7,8,9]
MONTH_CELL_CAP=60


def month_reference(rows):
    stats,selected=cases_reference.selected_reference(rows)
    pair_ranks={(row[0],row[1]):rank for rank,row in enumerate(selected,1)};counter=Counter();anchored=0
    for basket,members in groupby(rows,key=lambda row:row[:2]):
        all_members=list(members);items=[row[2] for row in all_members];assert items==sorted(set(items))
        assert all(isinstance(row[3],int) and SOURCE_MIN_MS<=row[3]<=SOURCE_MAX_MS for row in all_members)
        anchor=min(row[3] for row in all_members);date=utc_reference.utc(anchor)
        assert date.year==2015 and date.month in MONTHS and utc_reference.recover(date)==anchor;anchored+=1
        for pair in combinations(items,2):
            if pair in pair_ranks:counter[(pair_ranks[pair],date.month)]+=1
    cells=[(rank,month,counter[(rank,month)]) for rank in range(1,len(selected)+1) for month in MONTHS]
    assert len(cells)<=MONTH_CELL_CAP and anchored==stats['baskets']
    expected=[]
    for rank,pair in enumerate(selected,1):
        values=[counter[(rank,month)] for month in MONTHS];assert sum(values)==pair[2]
        expected.append(dict(zip(OUTPUT,[f'PAIR_{rank:02d}',pair[2]]+values+[Fraction(100*max(values),pair[2]),'PASS'])))
    assert sum(row[2] for row in cells)==sum(row[2] for row in selected)
    return stats,selected,cells,expected,anchored


def compare_report(observed,expected):
    assert len(observed)==len(expected)
    for actual,wanted in zip(observed,expected):
        assert list(actual)==OUTPUT
        for key in OUTPUT:
            if key=='top_month_share_pct':
                assert math.isfinite(actual[key]) and abs(actual[key]-float(wanted[key]))<=DISPLAY_TOL,'Private month share differs; values withheld'
                assert abs(actual[key]*1e6-round(actual[key]*1e6))<=1e-5
            else:assert actual[key]==wanted[key],'Private month label/count/status differs; values withheld'


def month_stream_sql(sql):
    assert sql.count('), monthly_case_summary AS MATERIALIZED (')==1
    return sql.split('), monthly_case_summary AS MATERIALIZED (',1)[0]+')\nSELECT '+','.join(MONTH_FIELDS)+' FROM case_month_counts ORDER BY case_rank,month_number;'


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--duckdb',required=True)
    parser.add_argument('--output',required=True);parser.add_argument('--fixtures-only',action='store_true');args=parser.parse_args()
    root=Path(__file__).resolve().parents[1];output=(root/args.output).resolve()
    script_path='sql/84_analyze_retailrocket_pair_month_coverage.sql'
    validator_path='validation/preflight_retailrocket_pair_month_coverage.py';method_path='docs/RETAILROCKET_PAIR_MONTH_COVERAGE_VALIDATION.md'
    assert output==(root/'data/retailrocket_pair_month_coverage_preflight.json').resolve()
    old=json.loads((root/'data/retailrocket_pair_visitor_concentration_preflight.json').read_text(encoding='utf-8'))
    accepted=json.loads((root/'data/retailrocket_pair_visitor_concentration_learner_acceptance.json').read_text(encoding='utf-8'))
    assert accepted['acceptance_status']=='accepted' and accepted['report_sha256']==old['report_sha256']
    deps=list(old['code_and_dependency_sha256'])+[script_path,validator_path,'data/retailrocket_pair_visitor_concentration_preflight.json',
        'data/retailrocket_pair_visitor_concentration_learner_acceptance.json','docs/RETAILROCKET_PAIR_VISITOR_CONCENTRATION_VALIDATION.md']
    hashes={name:source_reference.sha256(root/name) for name in deps}
    assert all(hashes[name]==digest for name,digest in old['code_and_dependency_sha256'].items())
    contract=(root/method_path).read_bytes().split(b'\n## Executed results\n',1)[0]
    assert hashlib.sha256(contract).hexdigest()==CONTRACT_SHA
    sql=(root/script_path).read_text(encoding='utf-8');clean=re.sub(r'--[^\n]*','',sql)
    assert clean.lstrip().startswith('WITH ') and not re.search(r'\b(CREATE|INSERT|UPDATE|DELETE|DROP|ALTER|COPY|SET|ATTACH|DETACH|LIMIT)\b',clean,re.I)
    assert 'first_timestamp_ms' in clean and all(name not in clean for name in ['last_timestamp_ms','source_event_rows','rr_stg','rr_core','categoryid','available'])
    stream_sql=month_stream_sql(sql)
    source=Path(source_reference.SOURCE);source_audit=json.loads((root/'data/retailrocket_source_audit.json').read_text(encoding='utf-8'))
    tmp_root=root/'tmp';tmp_root.mkdir(exist_ok=True);free_before=shutil.disk_usage(tmp_root).free
    assert free_before>=8*1024**3;sizes=[]
    def settings(folder,database):
        assert folder.resolve().is_relative_to(tmp_root.resolve()) and Path(database).resolve().is_relative_to(folder.resolve())
        spill=(folder/'spill').as_posix().replace("'","''")
        return f"SET threads=2;SET memory_limit='1GB';SET max_temp_directory_size='2GB';SET temp_directory='{spill}';\n"
    def observe(folder):
        size=sum(p.stat().st_size for p in folder.rglob('*') if p.is_file());assert size<=7*1024**3;sizes.append(size)
    def execute(folder,database,query,readonly=False):
        started=time.perf_counter();run=subprocess.run([args.duckdb,str(database),'-bail','-json']+(['-readonly'] if readonly else []),
            input=settings(folder,database)+query,text=True,encoding='utf-8',capture_output=True,timeout=120)
        if run.returncode:
            diagnostic=run.stderr.lower()
            category=next((name for name,patterns in [('out_of_memory',['out of memory','failed to allocate']),('disk_or_spill',['no space left','max_temp_directory_size']),
                ('parser',['parser error']),('binder',['binder error']),('invalid_input',['invalid input error'])]
                if any(pattern in diagnostic for pattern in patterns)),'unclassified_cli_error')
            raise AssertionError('Private association CLI failure: '+category+'; row-bearing details withheld')
        observe(folder)
        return json.loads(run.stdout) if run.stdout.strip() else None,round(time.perf_counter()-started,3)
    def load_memberships(folder,database,rows):
        path=folder/'memberships.csv'
        with path.open('w',encoding='utf-8',newline='') as stream:
            writer=csv.writer(stream);writer.writerow(model.FIELDS);writer.writerows(rows)
        columns=','.join("'"+name+"':'BIGINT'" for name in model.FIELDS)
        query="CREATE SCHEMA rr_mart;CREATE TABLE rr_mart.transaction_basket_items AS SELECT * FROM read_csv('"+path.as_posix().replace("'","''")+"',header=true,columns={"+columns+"});\n"+model.MEMBERSHIP_STREAM
        observed,seconds=execute(folder,database,query)
        actual=[tuple(row[name] for name in model.FIELDS) for row in observed]
        assert actual==rows,'Private membership input readback differs; values withheld'
        return counts.canonical_hash(actual),seconds,path.stat().st_size
    def compare_months(folder,database,query,expected):
        started=time.perf_counter();expired=threading.Event();count=0;sentinel=object();digest=hashlib.sha256()
        process=subprocess.Popen([args.duckdb,str(database),'-bail','-readonly','-csv','-noheader'],stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,encoding='utf-8')
        def expire():expired.set();process.kill()
        timer=threading.Timer(120,expire);timer.start()
        try:
            process.stdin.write(settings(folder,database)+query);process.stdin.close()
            for observed,wanted in zip_longest(csv.reader(process.stdout,strict=True),expected,fillvalue=sentinel):
                assert observed is not sentinel and wanted is not sentinel,'Private month scaffold count differs'
                assert len(observed)==3 and count<MONTH_CELL_CAP
                actual=tuple(int(value) for value in observed)
                assert actual==wanted,'Private month cell differs; values withheld'
                digest.update((json.dumps(actual,separators=(',',':'))+'\n').encode());count+=1
            assert process.wait(timeout=120)==0 and not expired.is_set()
        finally:
            timer.cancel()
            if process.poll() is None:process.kill();process.wait()
            process.stdout.close()
        observe(folder)
        return dict(rows=count,fields=3,sha256=digest.hexdigest()),round(time.perf_counter()-started,3)

    june=utc_reference.recover(datetime(2015,6,1,tzinfo=timezone.utc))
    july=utc_reference.recover(datetime(2015,7,1,tzinfo=timezone.utc))
    september=utc_reference.recover(datetime(2015,9,1,tzinfo=timezone.utc))
    fixture_times=[june,june,july-1,july,september]
    rows=sorted([(1,index,item,stamp,stamp,1) for index,stamp in enumerate(fixture_times,1) for item in [2,10]]+[(1,1,99,june-1,june-1,1)])
    stats,selected,cells,expected,anchored=month_reference(rows);cases=[]
    assert len(selected)==1 and anchored==5 and cells==[(1,5,1),(1,6,2),(1,7,1),(1,8,0),(1,9,1)]
    assert expected[0]['top_month_share_pct']==40
    with tempfile.TemporaryDirectory(prefix='rr-pair-month-fixture-',dir=tmp_root) as temporary:
        folder,database=Path(temporary),Path(temporary)/'fixture.duckdb';load_memberships(folder,database,rows)
        query=cases_reference.adjusted(sql,stats,selected);before_db=source_reference.sha256(database)
        report,_=execute(folder,database,query,readonly=True);compare_report(report,expected)
        proof,_=compare_months(folder,database,month_stream_sql(query),iter(cells))
        assert proof['rows']==5 and source_reference.sha256(database)==before_db
        cases.append(dict(case='earlier_third_item_anchors_whole_basket_before_UTC_boundary_integer_ms_and_zero_month_scaffold',passed=True,
            candidate_baskets=5,selected_pairs=1,month_cells=5,zero_month_cells=1,complete_month_fields=3))
        mutations=[('NULL','UPDATE rr_mart.transaction_basket_items SET first_timestamp_ms=NULL WHERE itemid=99;'),
            ('out_of_bound',f'UPDATE rr_mart.transaction_basket_items SET first_timestamp_ms={SOURCE_MAX_MS+1} WHERE itemid=99;'),
            ('wrong_type','ALTER TABLE rr_mart.transaction_basket_items ALTER COLUMN first_timestamp_ms TYPE VARCHAR;')]
        for label,mutation in mutations:
            blocked,_=execute(folder,database,'BEGIN;'+mutation+query+'ROLLBACK;')
            assert len(blocked)==1 and blocked[0]['case_label']=='PAIR_01'
            assert all(row['check_status']=='BLOCKED' and all(row[key] is None for key in OUTPUT[1:-1]) for row in blocked),label
        assert query.count('COUNT(*)::BIGINT AS pair_baskets')==1
        wrong=query.replace('COUNT(*)::BIGINT AS pair_baskets','(COUNT(*)+1)::BIGINT AS pair_baskets')
        failed,_=execute(folder,database,wrong,readonly=True)
        assert len(failed)==1 and failed[0]['check_status']=='FAIL' and all(failed[0][key] is None for key in OUTPUT[1:-1])
        cases.append(dict(case='NULL_out_of_bound_wrong_timestamp_type_BLOCKED_inflated_month_counts_FAIL',passed=True,subcases=4))
    assert not folder.exists()
    print(json.dumps({'fixture_families_passed':len(cases),'invalid_control_subcases':4}),flush=True)
    if args.fixtures_only:return

    before={'events.csv':staging.snapshot(source)}
    assert all(before['events.csv'][key]==source_audit['source_before']['events.csv'][key]==source_audit['source_after']['events.csv'][key]
        for key in ['size_bytes','modified_time_ns','sha256'])
    historical={str(p.relative_to(root)):source_reference.sha256(p) for p in (root/'data').glob('*preflight.json') if p.resolve()!=output.resolve()}
    assert len(historical)==82
    started=time.perf_counter();rows,source_counts=counts.scan_source(source);source_seconds=round(time.perf_counter()-started,3)
    assert source_counts==old['independent_python_source_counts'] and len(rows)==22323
    input_hash=counts.canonical_hash(rows);assert input_hash==old['accepted_SQL79_membership_sha256']
    started=time.perf_counter();stats,selected,cells,expected,anchored=month_reference(rows);reference_seconds=round(time.perf_counter()-started,3)
    assert stats==old['independent_python_pair_counts'] and len(selected)==12 and sum(row[2] for row in selected)==110 and anchored==17672
    assert [(row['case_label'],row['n_ab']) for row in expected]==[(row['case_label'],row['n_ab']) for row in old['results']]
    assert len(cells)==60 and sum(row[2] for row in cells)==110
    print(json.dumps({'phase':'single canonical parse and accepted membership fingerprint matched'}),flush=True)
    with tempfile.TemporaryDirectory(prefix='rr-pair-month-real-',dir=tmp_root) as temporary:
        folder,database=Path(temporary),Path(temporary)/'preflight.duckdb'
        readback_hash,load_seconds,csv_bytes=load_memberships(folder,database,rows);assert readback_hash==input_hash
        database_before=source_reference.sha256(database)
        report,query_seconds=execute(folder,database,sql,readonly=True);compare_report(report,expected)
        assert Counter(row['check_status'] for row in report)==Counter(PASS=12)
        proof,stream_seconds=compare_months(folder,database,stream_sql,iter(cells))
        assert proof['rows']==60 and proof['sha256']==counts.canonical_hash(cells)
        database_after=source_reference.sha256(database);assert database_before==database_after;database_bytes=database.stat().st_size
    assert not folder.exists()
    after={'events.csv':staging.snapshot(source)}
    assert before==after and all(source_reference.sha256(root/name)==digest for name,digest in hashes.items())
    assert all(source_reference.sha256(root/name)==digest for name,digest in historical.items())
    assert (root/method_path).read_bytes().startswith(contract)
    evidence=dict(checked_at_utc=datetime.now(timezone.utc).isoformat(),executor='assistant',engine=subprocess.check_output([args.duckdb,'-version'],text=True).strip(),
        script=script_path,script_sha256=hashes[script_path],validator=validator_path,validator_sha256=hashes[validator_path],code_and_dependency_sha256=hashes,
        method_contract=method_path,method_contract_prefix_bytes=len(contract),method_contract_prefix_sha256=CONTRACT_SHA,
        source_files=['events.csv'],source_before=before,source_after=after,source_hashes_and_metadata_unchanged=True,
        source_table='rr_mart.transaction_basket_items',readset_fields=READSET,required_readset_columns=4,
        private_input_fields=model.FIELDS,private_input_rows=len(rows),private_input_columns=6,
        reconstructed_membership_sha256=input_hash,accepted_SQL79_membership_sha256=old['accepted_SQL79_membership_sha256'],
        accepted_SQL79_membership_fingerprint_matched=True,private_input_readback_sha256=readback_hash,private_input_readback_matched=True,
        accepted_original_five_field_proof_reused=True,accepted_SQL81_full_metric_proof_reused=True,accepted_SQL82_case_selection_proof_reused=True,accepted_SQL83_contributor_proof_reused=True,
        full_9688_SQL_metric_stream_recompared=False,selected_metric_formula_stream_recompared=False,selected_visitor_group_stream_recompared=False,
        original_five_field_occurrence_comparison_rerun=False,original_event_external_sort_rerun=False,
        SQL54_rerun=False,SQL63_rerun=False,SQL79_rerun=False,SQL80_rerun=False,SQL81_rerun=False,SQL82_rerun=False,SQL83_rerun=False,
        stored_first_timestamp_ms_in_query_readset=True,stored_last_timestamp_and_source_count_in_query_readset=False,
        property_files_read=False,category_csv_read=False,stored_UTC_fields_read=False,UTC_months_derived_from_first_timestamp_ms=True,
        property_history_reconstructed=False,category_hierarchy_reverified=False,learner_database_opened=False,query_read_only=True,private_month_cell_stream_read_only=True,
        real_source_attempts=1,real_event_csv_parse_passes=1,real_cli_phases=3,real_private_input_load_executions=1,real_analysis_script_executions=1,real_private_month_cell_stream_executions=1,
        report_rows=12,report_columns=9,output_columns=OUTPUT,checks_passed=12,fail_rows=0,blocked_rows=0,results=report,
        report_sha256=counts.canonical_hash([[row[key] for key in OUTPUT] for row in report]),
        report_fingerprint_contract='SHA-256 of actual returned compact JSON arrays in output-column order followed by LF, preserving frozen case order. Rounded top-month percentages compared within stated tolerance.',
        independent_python_source_counts=source_counts,independent_python_pair_counts=stats,independent_python_report_matched_with_display_tolerance=True,
        case_labels_month_counts_status_and_order_compared_exactly=True,report_display_absolute_tolerance=DISPLAY_TOL,report_display_decimal_places=6,
        independent_month_cell_rows_compared=proof['rows'],independent_month_cell_fields_compared=3,private_month_cell_columns=MONTH_FIELDS,
        independent_month_cells_all_integer_fields_exact=True,independent_month_cell_stream_sha256=proof['sha256'],independent_month_cells_all_matched=True,
        month_cell_stream_sql_sha256=hashlib.sha256(stream_sql.encode()).hexdigest(),candidate_basket_key=['visitorid','transactionid'],
        frozen_SQL82_case_order_and_n_ab_verified=True,selected_pairs=len(selected),selected_pair_occurrences=sum(row[2] for row in selected),
        months=MONTHS,month_cell_cap=MONTH_CELL_CAP,explicit_zero_month_cells=sum(row[2]==0 for row in cells),month_cell_counts_sum=sum(row[2] for row in cells),
        all_basket_anchors_reconstructed=anchored,whole_basket_MIN_before_pair_selection_verified=True,
        source_timestamp_bounds_ms=[SOURCE_MIN_MS,SOURCE_MAX_MS],anchor_year=2015,all_anchors_in_accepted_month_partition=True,
        UTC_conversion='Integer make_timestamp_ms to timezone-naive TIMESTAMP under UTC convention; independent integer Python UTC arithmetic.',
        percentage_denominator='Each case n_ab; never 110.',per_case_month_counts_reconcile_to_n_ab=True,tied_maximum_month_identity_selected=False,
        independent_temporal_validation_performed=False,monthly_rates_lift_or_growth_estimated=False,partial_unequal_month_exposure_acknowledged=True,
        basket_anchor_is_verified_order_time=False,persistent_private_identifier_mapping_created=False,source_event_rows_used_as_pair_weight=False,
        retained_transaction_occurrences=source_counts['transaction'],transaction_occurrence_cap=counts.TRANSACTION_CAP,pair_occurrence_cap=counts.PAIR_CAP,distinct_pair_key_cap=counts.PAIR_CAP,
        private_database_sha256_before_readonly=database_before,private_database_sha256_after_readonly=database_after,private_database_bytes_unchanged=True,
        fixture_case_count=len(cases),fixture_cases=cases,invalid_control_fixture_subcases=4,
        third_item_earlier_month_anchor_fixture_verified=True,integer_UTC_month_boundary_fixture_verified=True,zero_month_scaffold_fixture_verified=True,
        NULL_out_of_bound_wrong_timestamp_type_BLOCKED_verified=True,inflated_month_count_FAIL_verified=True,
        preflight_settings=dict(threads=2,memory_limit='1GB',max_temp_directory_size='2GB',timeout_seconds_per_cli_phase=120,
            transaction_occurrence_cap=counts.TRANSACTION_CAP,pair_occurrence_cap=counts.PAIR_CAP,distinct_pair_key_cap=counts.PAIR_CAP,
            month_cell_cap=MONTH_CELL_CAP,minimum_free_bytes=8*1024**3,private_directory_budget_bytes=7*1024**3),
        private_input_csv_bytes=csv_bytes,private_database_bytes_before_cleanup=database_bytes,
        largest_private_directory_bytes_observed_after_phase=max(sizes),workspace_free_bytes_before=free_before,workspace_free_bytes_after=shutil.disk_usage(tmp_root).free,
        temporary_databases_and_spills_removed=True,private_membership_csv_removed=True,historical_preflight_files_unchanged=len(historical),
        historical_comparison_or_analysis_suites_rerun=False,source_records_or_identifiers_uploaded_or_logged=False,raw_pair_or_visitor_identifiers_published=False,
        elapsed_python_source_scan_reconstruction_seconds=source_seconds,elapsed_python_month_reference_seconds=reference_seconds,
        elapsed_private_input_load_readback_seconds=load_seconds,elapsed_readonly_month_report_seconds=query_seconds,elapsed_private_month_cell_stream_seconds=stream_seconds,
        timing_scope='One canonical parse and bounded whole-basket UTC-month reference; small private load/readback plus read-only report and60-cell scaffold stream. Source hash reads separate; no old proof streams rerun.',
        scope='Assistant SQL84 preparation passed; learner execution pending. Descriptive month coverage of full-snapshot-selected cases with unequal partial months, not temporal validation, growth or verified order timing.')
    output.write_text(json.dumps(evidence,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps({'report_rows':12,'checks_passed':12,'month_cell_rows_compared':proof['rows'],
        'month_cell_fields':3,'report_sha256':evidence['report_sha256']}),flush=True)


if __name__=='__main__':main()
