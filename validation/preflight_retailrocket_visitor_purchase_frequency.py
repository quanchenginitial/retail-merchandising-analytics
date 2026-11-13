"""Validate observed transaction-visitor frequency from complete composite basket keys."""
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
from itertools import zip_longest
from pathlib import Path

import preflight_retailrocket_pair_month_coverage as previous

counts=previous.counts
model=previous.model
staging=previous.staging
source_reference=previous.source_reference
READSET=['visitorid','transactionid','itemid']
DISPLAY_TOL=previous.DISPLAY_TOL
CONTRACT_SHA='d97211d2c9684c014ee483b98459e01c44adc5707e7bc047f30b530a6c8b5727'
OUTPUT=['frequency_band','visitor_ids','visitor_share_pct','candidate_baskets','basket_share_pct','max_baskets_per_visitor','check_status']
FREQUENCY_FIELDS=['visitorid','basket_count']
BANDS=['F_1','F_2','F_3_4','F_5_PLUS','TOTAL']
FREQUENCY_CAP=100000


def frequency_reference(rows):
    assert len({row[:3] for row in rows})==len(rows)
    basket_items=Counter(row[:2] for row in rows)
    frequencies=Counter(visitor for visitor,transaction in basket_items)
    assert len(frequencies)<=FREQUENCY_CAP
    stream=sorted(frequencies.items());values=list(frequencies.values())
    stats=dict(memberships=len(rows),baskets=len(basket_items),single_baskets=sum(value==1 for value in basket_items.values()),
        multi_baskets=sum(value>1 for value in basket_items.values()),max_items=max(basket_items.values(),default=None),
        visitor_ids=len(frequencies),frequency_basket_sum=sum(values),max_baskets_per_visitor=max(values,default=None))
    assert sum(values)==stats['baskets']
    groups=[[value for value in values if value==1],[value for value in values if value==2],
        [value for value in values if 3<=value<=4],[value for value in values if value>=5],values]
    report=[dict(zip(OUTPUT,[band,len(group),Fraction(100*len(group),len(values)),sum(group),
        Fraction(100*sum(group),stats['baskets']),max(group,default=None),'PASS'])) for band,group in zip(BANDS,groups)]
    assert sum(row['visitor_ids'] for row in report[:4])==report[4]['visitor_ids']
    assert sum(row['candidate_baskets'] for row in report[:4])==report[4]['candidate_baskets']
    return stats,stream,report


def compare_report(observed,expected):
    assert len(observed)==len(expected)==5
    for actual,wanted in zip(observed,expected):
        assert list(actual)==OUTPUT
        for key in OUTPUT:
            if key in ['visitor_share_pct','basket_share_pct']:
                assert math.isfinite(actual[key]) and abs(actual[key]-float(wanted[key]))<=DISPLAY_TOL,'Private frequency share differs; values withheld'
                assert abs(actual[key]*1e6-round(actual[key]*1e6))<=1e-5
            else:assert actual[key]==wanted[key],'Private frequency label/count/status differs; values withheld'


def adjusted(sql,stats):
    query=counts.adjusted(sql,stats)
    query,n=re.subn(r'\b[0-9]+::BIGINT AS expected_visitor_ids\b',f"{stats['visitor_ids']}::BIGINT AS expected_visitor_ids",query)
    assert n==1
    return query


def frequency_stream_sql(sql):
    assert sql.count('), frequency_health AS (')==1
    return sql.split('), frequency_health AS (',1)[0]+')\nSELECT '+','.join(FREQUENCY_FIELDS)+' FROM visitor_frequency ORDER BY visitorid;'


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--duckdb',required=True)
    parser.add_argument('--output',required=True);parser.add_argument('--fixtures-only',action='store_true');args=parser.parse_args()
    root=Path(__file__).resolve().parents[1];output=(root/args.output).resolve()
    script_path='sql/85_analyze_retailrocket_visitor_purchase_frequency.sql'
    validator_path='validation/preflight_retailrocket_visitor_purchase_frequency.py';method_path='docs/RETAILROCKET_VISITOR_PURCHASE_FREQUENCY_VALIDATION.md'
    assert output==(root/'data/retailrocket_visitor_purchase_frequency_preflight.json').resolve()
    old=json.loads((root/'data/retailrocket_pair_month_coverage_preflight.json').read_text(encoding='utf-8'))
    accepted=json.loads((root/'data/retailrocket_pair_month_coverage_learner_acceptance.json').read_text(encoding='utf-8'))
    assert accepted['acceptance_status']=='accepted' and accepted['report_sha256']==old['report_sha256']
    overview_path='data/retailrocket_event_overview_preflight.json';overview_acceptance_path='data/retailrocket_event_overview_learner_acceptance.json'
    overview=json.loads((root/overview_path).read_text(encoding='utf-8'))
    overview_accepted=json.loads((root/overview_acceptance_path).read_text(encoding='utf-8'))
    assert overview_accepted['acceptance_status']=='accepted' and overview_accepted['script']=='sql/70_analyze_retailrocket_event_overview.sql'
    assert overview_accepted['report_sha256']==overview['report_sha256'] and overview_accepted['assistant_preflight_sha256']==source_reference.sha256(root/overview_path)
    assert [row['distinct_visitor_ids'] for row in overview['results'] if row['event_type']=='transaction']==[11719]
    assert [row['distinct_visitor_ids'] for row in overview_accepted['results'] if row['event_type']=='transaction']==[11719]
    deps=list(old['code_and_dependency_sha256'])+[script_path,validator_path,'data/retailrocket_pair_month_coverage_preflight.json',
        'data/retailrocket_pair_month_coverage_learner_acceptance.json','docs/RETAILROCKET_PAIR_MONTH_COVERAGE_VALIDATION.md',overview_path,overview_acceptance_path]
    hashes={name:source_reference.sha256(root/name) for name in deps}
    assert all(hashes[name]==digest for name,digest in old['code_and_dependency_sha256'].items())
    contract=(root/method_path).read_bytes().split(b'\n## Executed results\n',1)[0]
    assert hashlib.sha256(contract).hexdigest()==CONTRACT_SHA
    sql=(root/script_path).read_text(encoding='utf-8');clean=re.sub(r'--[^\n]*','',sql)
    assert clean.lstrip().startswith('WITH ') and not re.search(r'\b(CREATE|INSERT|UPDATE|DELETE|DROP|ALTER|COPY|SET|ATTACH|DETACH|LIMIT)\b',clean,re.I)
    assert all(name not in clean for name in ['first_timestamp_ms','last_timestamp_ms','source_event_rows','rr_stg','rr_core','categoryid','available','pair_counts','selected_pairs'])
    stream_sql=frequency_stream_sql(sql)
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
    def compare_frequencies(folder,database,query,expected):
        started=time.perf_counter();expired=threading.Event();count=0;sentinel=object();digest=hashlib.sha256()
        process=subprocess.Popen([args.duckdb,str(database),'-bail','-readonly','-csv','-noheader'],stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,encoding='utf-8')
        def expire():expired.set();process.kill()
        timer=threading.Timer(120,expire);timer.start()
        try:
            process.stdin.write(settings(folder,database)+query);process.stdin.close()
            for observed,wanted in zip_longest(csv.reader(process.stdout,strict=True),expected,fillvalue=sentinel):
                assert observed is not sentinel and wanted is not sentinel,'Private frequency row count differs'
                assert len(observed)==2 and count<FREQUENCY_CAP
                actual=tuple(int(value) for value in observed)
                assert actual==wanted,'Private frequency tuple differs; identifiers withheld'
                digest.update((json.dumps(actual,separators=(',',':'))+'\n').encode());count+=1
            assert process.wait(timeout=120)==0 and not expired.is_set()
        finally:
            timer.cancel()
            if process.poll() is None:process.kill();process.wait()
            process.stdout.close()
        observe(folder)
        return dict(rows=count,fields=2,sha256=digest.hexdigest()),round(time.perf_counter()-started,3)

    rows=[];cases=[]
    for visitor in range(1,6):
        for transaction in range(1,visitor+1):
            rows.extend([(visitor,transaction,10+visitor,100,100,7),(visitor,transaction,100+transaction,100,100,7)])
    rows.append((3,1,999,100,100,7));rows.sort()
    stats,frequencies,expected=frequency_reference(rows)
    assert frequencies==[(1,1),(2,2),(3,3),(4,4),(5,5)] and stats['memberships']==31 and stats['baskets']==15
    assert [row['visitor_ids'] for row in expected]==[1,1,2,1,5] and [row['candidate_baskets'] for row in expected]==[1,2,7,5,15]
    with tempfile.TemporaryDirectory(prefix='rr-visitor-frequency-fixture-',dir=tmp_root) as temporary:
        folder,database=Path(temporary),Path(temporary)/'fixture.duckdb';load_memberships(folder,database,rows)
        query=adjusted(sql,stats);before_db=source_reference.sha256(database)
        report,_=execute(folder,database,query,readonly=True);compare_report(report,expected)
        proof,_=compare_frequencies(folder,database,frequency_stream_sql(query),iter(frequencies))
        assert proof['rows']==5 and source_reference.sha256(database)==before_db
        blocked,_=execute(folder,database,'BEGIN;UPDATE rr_mart.transaction_basket_items SET visitorid=NULL WHERE visitorid=1;'+query+'ROLLBACK;')
        assert [row['frequency_band'] for row in blocked]==BANDS and all(row['check_status']=='BLOCKED' and all(row[key] is None for key in OUTPUT[1:-1]) for row in blocked)
        assert query.count("(3,'F_3_4',3::BIGINT,4::BIGINT)")==1
        wrong=query.replace("(3,'F_3_4',3::BIGINT,4::BIGINT)","(3,'F_3_4',3::BIGINT,5::BIGINT)")
        failed,_=execute(folder,database,wrong,readonly=True)
        assert [row['frequency_band'] for row in failed]==BANDS and all(row['check_status']=='FAIL' and all(row[key] is None for key in OUTPUT[1:-1]) for row in failed)
        cases.append(dict(case='frequency_boundaries_1_2_3_4_5_multi_item_baskets_shared_transaction_ids_NULL_key_BLOCKED_overlapping_band_FAIL',passed=True,
            memberships=31,candidate_baskets=15,visitor_ids=5,complete_frequency_fields=2,invalid_control_subcases=2))
    assert not folder.exists()
    with tempfile.TemporaryDirectory(prefix='rr-visitor-frequency-zero-',dir=tmp_root) as temporary:
        folder,database=Path(temporary),Path(temporary)/'fixture.duckdb';single_rows=[(7,1,10,100,100,1),(7,2,20,100,100,1)]
        single_stats,single_frequencies,single_expected=frequency_reference(single_rows);load_memberships(folder,database,single_rows)
        query=adjusted(sql,single_stats);report,_=execute(folder,database,query,readonly=True);compare_report(report,single_expected)
        proof,_=compare_frequencies(folder,database,frequency_stream_sql(query),iter(single_frequencies));assert proof['rows']==1
        assert all(report[index]['visitor_ids']==report[index]['candidate_baskets']==0 and report[index]['max_baskets_per_visitor'] is None for index in [0,2,3])
        cases.append(dict(case='zero_bands_visible_zero_shares_NULL_maximum_TOTAL_correct',passed=True,empty_bands=3))
    assert not folder.exists()
    print(json.dumps({'fixture_families_passed':len(cases),'invalid_control_subcases':2}),flush=True)
    if args.fixtures_only:return

    before={'events.csv':staging.snapshot(source)}
    assert all(before['events.csv'][key]==source_audit['source_before']['events.csv'][key]==source_audit['source_after']['events.csv'][key]
        for key in ['size_bytes','modified_time_ns','sha256'])
    historical={str(p.relative_to(root)):source_reference.sha256(p) for p in (root/'data').glob('*preflight.json') if p.resolve()!=output.resolve()}
    assert len(historical)==83
    started=time.perf_counter();rows,source_counts=counts.scan_source(source);source_seconds=round(time.perf_counter()-started,3)
    assert source_counts==old['independent_python_source_counts'] and len(rows)==22323
    input_hash=counts.canonical_hash(rows);assert input_hash==old['accepted_SQL79_membership_sha256']
    started=time.perf_counter();stats,frequencies,expected=frequency_reference(rows);reference_seconds=round(time.perf_counter()-started,3)
    assert [stats[name] for name in ['memberships','baskets','single_baskets','multi_baskets','max_items','visitor_ids']]==[22323,17672,15029,2643,31,11719]
    print(json.dumps({'phase':'single canonical parse and accepted membership fingerprint matched'}),flush=True)
    with tempfile.TemporaryDirectory(prefix='rr-visitor-frequency-real-',dir=tmp_root) as temporary:
        folder,database=Path(temporary),Path(temporary)/'preflight.duckdb'
        readback_hash,load_seconds,csv_bytes=load_memberships(folder,database,rows);assert readback_hash==input_hash
        database_before=source_reference.sha256(database)
        report,query_seconds=execute(folder,database,sql,readonly=True);compare_report(report,expected)
        assert Counter(row['check_status'] for row in report)==Counter(PASS=5)
        proof,stream_seconds=compare_frequencies(folder,database,stream_sql,iter(frequencies))
        assert proof['rows']==11719 and proof['sha256']==counts.canonical_hash(frequencies)
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
        source_table='rr_mart.transaction_basket_items',readset_fields=READSET,required_readset_columns=3,
        private_input_fields=model.FIELDS,private_input_rows=len(rows),private_input_columns=6,
        reconstructed_membership_sha256=input_hash,accepted_SQL79_membership_sha256=old['accepted_SQL79_membership_sha256'],
        accepted_SQL79_membership_fingerprint_matched=True,private_input_readback_sha256=readback_hash,private_input_readback_matched=True,
        accepted_original_five_field_proof_reused=True,accepted_SQL70_transaction_visitor_count_control_verified=True,
        expected_transaction_visitor_ids=11719,transaction_visitor_count_provenance=[overview_path,overview_acceptance_path],
        transaction_visitor_count_source_script='sql/70_analyze_retailrocket_event_overview.sql',
        original_five_field_occurrence_comparison_rerun=False,original_event_external_sort_rerun=False,
        SQL54_rerun=False,SQL63_rerun=False,SQL70_rerun=False,SQL79_rerun=False,SQL80_rerun=False,SQL81_rerun=False,SQL82_rerun=False,SQL83_rerun=False,SQL84_rerun=False,
        pair_selection_recomputed=False,metric_formula_stream_recompared=False,visitor_concentration_stream_recompared=False,month_cell_stream_recompared=False,
        stored_timestamps_and_source_count_in_query_readset=False,property_files_read=False,category_csv_read=False,enriched_fact_read=False,
        learner_database_opened=False,query_read_only=True,private_visitor_frequency_stream_read_only=True,
        real_source_attempts=1,real_event_csv_parse_passes=1,real_cli_phases=3,real_private_input_load_executions=1,real_analysis_script_executions=1,real_private_visitor_frequency_stream_executions=1,
        report_rows=5,report_columns=7,output_columns=OUTPUT,checks_passed=5,fail_rows=0,blocked_rows=0,results=report,
        report_sha256=counts.canonical_hash([[row[key] for key in OUTPUT] for row in report]),
        report_fingerprint_contract='SHA-256 of actual returned compact JSON arrays in output-column order followed by LF; fixed band order and NULL maxima retained. Rounded percentages compared within stated tolerance.',
        independent_python_source_counts=source_counts,independent_python_frequency_counts=stats,independent_python_report_matched_with_display_tolerance=True,
        band_labels_integer_counts_maxima_NULLs_and_status_compared_exactly=True,report_display_absolute_tolerance=DISPLAY_TOL,report_display_decimal_places=6,
        independent_visitor_frequency_rows_compared=proof['rows'],independent_visitor_frequency_fields_compared=2,private_visitor_frequency_columns=FREQUENCY_FIELDS,
        independent_visitor_frequencies_all_integer_fields_exact=True,independent_visitor_frequency_stream_sha256=proof['sha256'],independent_visitor_frequencies_all_matched=True,
        visitor_frequency_stream_sql_sha256=hashlib.sha256(stream_sql.encode()).hexdigest(),candidate_basket_key=['visitorid','transactionid'],
        unique_composite_baskets_counted_once=True,multi_item_memberships_do_not_inflate_frequency=True,
        frequency_bands=BANDS,band_ranges_disjoint_exhaustive=True,band_visitor_counts_sum=11719,band_basket_counts_sum=17672,
        visitor_share_denominator=11719,basket_share_denominator=17672,population='Transaction-recorded visitor IDs with at least one candidate basket only.',
        all_event_visitors_in_denominator=False,F_zero_nontransaction_visitors_included=False,selected_pair_funnel_category_restriction_applied=False,
        recency_computed=False,combined_RF_scores_or_segments_completed=False,band_cutoffs_optimized=False,
        verified_people_orders_or_lifetime_loyalty_claimed=False,finite_observation_window_and_unequal_visitor_exposure_acknowledged=True,
        retained_transaction_occurrences=source_counts['transaction'],transaction_occurrence_cap=counts.TRANSACTION_CAP,visitor_frequency_row_cap=FREQUENCY_CAP,
        private_database_sha256_before_readonly=database_before,private_database_sha256_after_readonly=database_after,private_database_bytes_unchanged=True,
        fixture_case_count=len(cases),fixture_cases=cases,invalid_control_fixture_subcases=2,
        band_boundaries_and_composite_key_fixture_verified=True,zero_bands_NULL_maxima_fixture_verified=True,
        invalid_key_BLOCKED_verified=True,overlapping_band_partition_FAIL_verified=True,
        preflight_settings=dict(threads=2,memory_limit='1GB',max_temp_directory_size='2GB',timeout_seconds_per_cli_phase=120,
            transaction_occurrence_cap=counts.TRANSACTION_CAP,visitor_frequency_row_cap=FREQUENCY_CAP,
            minimum_free_bytes=8*1024**3,private_directory_budget_bytes=7*1024**3),
        private_input_csv_bytes=csv_bytes,private_database_bytes_before_cleanup=database_bytes,
        largest_private_directory_bytes_observed_after_phase=max(sizes),workspace_free_bytes_before=free_before,workspace_free_bytes_after=shutil.disk_usage(tmp_root).free,
        temporary_databases_and_spills_removed=True,private_membership_csv_removed=True,historical_preflight_files_unchanged=len(historical),
        historical_comparison_or_analysis_suites_rerun=False,source_records_or_identifiers_uploaded_or_logged=False,raw_visitor_identifiers_published=False,
        elapsed_python_source_scan_reconstruction_seconds=source_seconds,elapsed_python_frequency_reference_seconds=reference_seconds,
        elapsed_private_input_load_readback_seconds=load_seconds,elapsed_readonly_frequency_report_seconds=query_seconds,elapsed_private_visitor_frequency_stream_seconds=stream_seconds,
        timing_scope='One canonical parse and unique-composite-basket Counter; small private load/readback plus frequency report and complete two-integer frequency stream. Hash reads separate; no pair/month/recency machinery run.',
        scope='Assistant SQL85 preparation passed; learner execution pending. Frequency-only descriptive baseline for transaction-recorded IDs, excluding non-purchasers and without recency, optimized RF segments or loyalty claims.')
    output.write_text(json.dumps(evidence,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps({'report_rows':5,'checks_passed':5,'visitor_frequency_rows_compared':proof['rows'],
        'visitor_frequency_fields':2,'report_sha256':evidence['report_sha256']}),flush=True)


if __name__=='__main__':main()
