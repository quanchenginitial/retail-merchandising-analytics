"""Validate per-case visitor-ID concentration with an exact selected group comparison."""
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

import preflight_retailrocket_basket_pair_cases as cases_reference

counts=cases_reference.counts
model=cases_reference.model
staging=cases_reference.staging
source_reference=cases_reference.source_reference
KEYS=cases_reference.KEYS
DISPLAY_TOL=cases_reference.DISPLAY_TOL
CONTRACT_SHA='360fed85d5889b51e4dfbff841de05e96e5376ad3a7fd66cf6dacb50d139cd94'
OUTPUT=['case_label','n_ab','distinct_visitor_ids','repeat_visitor_ids','max_baskets_one_visitor',
        'top_visitor_share_pct','repeat_visitor_basket_share_pct','check_status']
GROUP_FIELDS=['case_rank','item_a','item_b','visitorid','pair_baskets']
SELECTED_GROUP_CAP=110


def visitor_reference(rows):
    stats,selected=cases_reference.selected_reference(rows)
    pair_ranks={(row[0],row[1]):rank for rank,row in enumerate(selected,1)};counter=Counter()
    for basket,members in groupby(rows,key=lambda row:row[:2]):
        items=[row[2] for row in members];assert items==sorted(set(items))
        for pair in combinations(items,2):
            if pair in pair_ranks:
                key=(pair_ranks[pair],pair[0],pair[1],basket[0])
                if key not in counter:assert len(counter)<SELECTED_GROUP_CAP,'Private selected visitor-group cap exceeded'
                counter[key]+=1
    groups=[key+(count,) for key,count in sorted(counter.items())]
    expected=[]
    for rank,pair in enumerate(selected,1):
        contributors=[row[4] for row in groups if row[0]==rank]
        assert contributors and sum(contributors)==pair[2]
        repeated=[value for value in contributors if value>=2]
        expected.append(dict(zip(OUTPUT,[f'PAIR_{rank:02d}',pair[2],len(contributors),len(repeated),max(contributors),
            Fraction(100*max(contributors),pair[2]),Fraction(100*sum(repeated),pair[2]),'PASS'])))
    assert sum(row[4] for row in groups)==sum(row[2] for row in selected)
    return stats,selected,groups,expected


def compare_report(observed,expected):
    assert len(observed)==len(expected)
    for actual,wanted in zip(observed,expected):
        assert list(actual)==OUTPUT
        for key in OUTPUT:
            if key in ['top_visitor_share_pct','repeat_visitor_basket_share_pct']:
                assert math.isfinite(actual[key]) and abs(actual[key]-float(wanted[key]))<=DISPLAY_TOL,'Private concentration display differs; values withheld'
                assert abs(actual[key]*1e6-round(actual[key]*1e6))<=1e-5
            else:assert actual[key]==wanted[key],'Private concentration label/count/status differs; values withheld'


def group_stream_sql(sql):
    assert sql.count('), visitor_summaries AS MATERIALIZED (')==1
    return sql.split('), visitor_summaries AS MATERIALIZED (',1)[0]+')\nSELECT '+','.join(GROUP_FIELDS)+' FROM selected_visitor_groups ORDER BY case_rank,visitorid;'


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--duckdb',required=True)
    parser.add_argument('--output',required=True);parser.add_argument('--fixtures-only',action='store_true');args=parser.parse_args()
    root=Path(__file__).resolve().parents[1];output=(root/args.output).resolve()
    script_path='sql/83_analyze_retailrocket_pair_visitor_concentration.sql'
    validator_path='validation/preflight_retailrocket_pair_visitor_concentration.py';method_path='docs/RETAILROCKET_PAIR_VISITOR_CONCENTRATION_VALIDATION.md'
    assert output==(root/'data/retailrocket_pair_visitor_concentration_preflight.json').resolve()
    old=json.loads((root/'data/retailrocket_basket_pair_cases_preflight.json').read_text(encoding='utf-8'))
    accepted=json.loads((root/'data/retailrocket_basket_pair_cases_learner_acceptance.json').read_text(encoding='utf-8'))
    assert accepted['acceptance_status']=='accepted' and accepted['report_sha256']==old['report_sha256']
    deps=list(old['code_and_dependency_sha256'])+[script_path,validator_path,'data/retailrocket_basket_pair_cases_preflight.json',
        'data/retailrocket_basket_pair_cases_learner_acceptance.json','docs/RETAILROCKET_BASKET_PAIR_CASES_VALIDATION.md']
    hashes={name:source_reference.sha256(root/name) for name in deps}
    assert all(hashes[name]==digest for name,digest in old['code_and_dependency_sha256'].items())
    contract=(root/method_path).read_bytes().split(b'\n## Executed results\n',1)[0]
    assert hashlib.sha256(contract).hexdigest()==CONTRACT_SHA
    sql=(root/script_path).read_text(encoding='utf-8');clean=re.sub(r'--[^\n]*','',sql)
    assert clean.lstrip().startswith('WITH ') and not re.search(r'\b(CREATE|INSERT|UPDATE|DELETE|DROP|ALTER|COPY|SET|ATTACH|DETACH|LIMIT)\b',clean,re.I)
    assert all(name not in clean for name in ['first_timestamp_ms','last_timestamp_ms','source_event_rows','rr_stg','rr_core','categoryid','available'])
    stream_sql=group_stream_sql(sql)
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
    def compare_groups(folder,database,query,expected):
        started=time.perf_counter();expired=threading.Event();count=0;sentinel=object();digest=hashlib.sha256()
        process=subprocess.Popen([args.duckdb,str(database),'-bail','-readonly','-csv','-noheader'],stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,encoding='utf-8')
        def expire():expired.set();process.kill()
        timer=threading.Timer(120,expire);timer.start()
        try:
            process.stdin.write(settings(folder,database)+query);process.stdin.close()
            for observed,wanted in zip_longest(csv.reader(process.stdout,strict=True),expected,fillvalue=sentinel):
                assert observed is not sentinel and wanted is not sentinel,'Private visitor-group row count differs'
                assert len(observed)==5 and count<SELECTED_GROUP_CAP
                actual=tuple(int(value) for value in observed)
                assert actual==wanted,'Private visitor-group integer tuple differs; values withheld'
                digest.update((json.dumps(actual,separators=(',',':'))+'\n').encode());count+=1
            assert process.wait(timeout=120)==0 and not expired.is_set()
        finally:
            timer.cancel()
            if process.poll() is None:process.kill();process.wait()
            process.stdout.close()
        observe(folder)
        return dict(rows=count,fields=5,sha256=digest.hexdigest()),round(time.perf_counter()-started,3)

    fixture_baskets=[(1,10,(2,10)),(1,11,(2,10)),(1,12,(2,10)),(2,10,(2,10)),(3,10,(2,10)),
        (4,10,(3,20)),(4,11,(3,20)),(5,10,(3,20)),(5,11,(3,20)),(6,10,(3,20))]
    rows=sorted((visitor,transaction,item,100,100,1) for visitor,transaction,items in fixture_baskets for item in items)
    stats,selected,groups,expected=visitor_reference(rows);cases=[]
    assert len(selected)==2 and len(groups)==6 and stats['baskets']==10
    assert [row['n_ab'] for row in expected]==[5,5] and [row['repeat_visitor_ids'] for row in expected]==[1,2]
    assert [row['top_visitor_share_pct'] for row in expected]==[60,40]
    assert [row['repeat_visitor_basket_share_pct'] for row in expected]==[60,80]
    with tempfile.TemporaryDirectory(prefix='rr-pair-visitor-fixture-',dir=tmp_root) as temporary:
        folder,database=Path(temporary),Path(temporary)/'fixture.duckdb';load_memberships(folder,database,rows)
        query=cases_reference.adjusted(sql,stats,selected);before_db=source_reference.sha256(database)
        report,_=execute(folder,database,query,readonly=True);compare_report(report,expected)
        proof,_=compare_groups(folder,database,group_stream_sql(query),iter(groups))
        assert proof['rows']==6 and source_reference.sha256(database)==before_db
        cases.append(dict(case='patterns_3_1_1_and_2_2_1_full_repeat_numerator_tied_maximum_shared_transaction_ids_across_visitors',passed=True,
            candidate_baskets=10,selected_pairs=2,selected_pair_visitor_groups=6,complete_group_fields=5))
        blocked,_=execute(folder,database,'BEGIN;DELETE FROM rr_mart.transaction_basket_items;'+query+'ROLLBACK;')
        assert len(blocked)==2 and [row['case_label'] for row in blocked]==[row['case_label'] for row in report]
        assert all(row['check_status']=='BLOCKED' and all(row[key] is None for key in OUTPUT[1:-1]) for row in blocked)
        assert query.count('COUNT(*)::BIGINT AS pair_baskets')==1
        wrong=query.replace('COUNT(*)::BIGINT AS pair_baskets','(COUNT(*)+1)::BIGINT AS pair_baskets')
        failed,_=execute(folder,database,wrong,readonly=True)
        assert len(failed)==2 and all(row['check_status']=='FAIL' and all(row[key] is None for key in OUTPUT[1:-1]) for row in failed)
        cases.append(dict(case='empty_source_preserves_labels_BLOCKED_multiplied_visitor_group_counts_FAIL_masks_values',passed=True,subcases=2))
    assert not folder.exists()
    print(json.dumps({'fixture_families_passed':len(cases),'invalid_control_subcases':2}),flush=True)
    if args.fixtures_only:return

    before={'events.csv':staging.snapshot(source)}
    assert all(before['events.csv'][key]==source_audit['source_before']['events.csv'][key]==source_audit['source_after']['events.csv'][key]
        for key in ['size_bytes','modified_time_ns','sha256'])
    historical={str(p.relative_to(root)):source_reference.sha256(p) for p in (root/'data').glob('*preflight.json') if p.resolve()!=output.resolve()}
    assert len(historical)==81
    started=time.perf_counter();rows,source_counts=counts.scan_source(source);source_seconds=round(time.perf_counter()-started,3)
    assert source_counts==old['independent_python_source_counts'] and len(rows)==22323
    input_hash=counts.canonical_hash(rows);assert input_hash==old['accepted_SQL79_membership_sha256']
    started=time.perf_counter();stats,selected,groups,expected=visitor_reference(rows);reference_seconds=round(time.perf_counter()-started,3)
    assert stats==old['independent_python_pair_counts'] and len(selected)==12 and sum(row[2] for row in selected)==110
    assert [(row['case_label'],row['n_ab']) for row in expected]==[(row['case_label'],row['n_ab']) for row in old['results']]
    assert len(groups)<=SELECTED_GROUP_CAP and sum(row[4] for row in groups)==110
    print(json.dumps({'phase':'single canonical parse and accepted membership fingerprint matched'}),flush=True)
    with tempfile.TemporaryDirectory(prefix='rr-pair-visitor-real-',dir=tmp_root) as temporary:
        folder,database=Path(temporary),Path(temporary)/'preflight.duckdb'
        readback_hash,load_seconds,csv_bytes=load_memberships(folder,database,rows);assert readback_hash==input_hash
        database_before=source_reference.sha256(database)
        report,query_seconds=execute(folder,database,sql,readonly=True);compare_report(report,expected)
        assert Counter(row['check_status'] for row in report)==Counter(PASS=12)
        proof,stream_seconds=compare_groups(folder,database,stream_sql,iter(groups))
        assert proof['rows']==len(groups) and proof['sha256']==counts.canonical_hash(groups)
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
        source_table='rr_mart.transaction_basket_items',readset_fields=KEYS,required_readset_columns=3,
        private_input_fields=model.FIELDS,private_input_rows=len(rows),private_input_columns=6,
        reconstructed_membership_sha256=input_hash,accepted_SQL79_membership_sha256=old['accepted_SQL79_membership_sha256'],
        accepted_SQL79_membership_fingerprint_matched=True,private_input_readback_sha256=readback_hash,private_input_readback_matched=True,
        accepted_original_five_field_proof_reused=True,accepted_SQL81_full_metric_proof_reused=True,accepted_SQL82_case_selection_proof_reused=True,
        full_9688_SQL_metric_stream_recompared=False,selected_metric_formula_stream_recompared=False,
        original_five_field_occurrence_comparison_rerun=False,original_event_external_sort_rerun=False,
        SQL54_rerun=False,SQL63_rerun=False,SQL79_rerun=False,SQL80_rerun=False,SQL81_rerun=False,SQL82_rerun=False,
        stored_membership_timestamps_and_counts_in_query_readset=False,
        property_files_read=False,category_csv_read=False,UTC_fields_read=False,property_history_reconstructed=False,category_hierarchy_reverified=False,
        learner_database_opened=False,query_read_only=True,private_selected_visitor_group_stream_read_only=True,
        real_source_attempts=1,real_event_csv_parse_passes=1,real_cli_phases=3,real_private_input_load_executions=1,real_analysis_script_executions=1,real_private_selected_visitor_group_stream_executions=1,
        report_rows=12,report_columns=8,output_columns=OUTPUT,checks_passed=12,fail_rows=0,blocked_rows=0,results=report,
        report_sha256=counts.canonical_hash([[row[key] for key in OUTPUT] for row in report]),
        report_fingerprint_contract='SHA-256 of actual returned compact JSON arrays in output-column order followed by LF, preserving frozen case order. Rounded percentages compared within stated tolerance.',
        independent_python_source_counts=source_counts,independent_python_pair_counts=stats,independent_python_report_matched_with_display_tolerance=True,
        case_labels_counts_status_and_order_compared_exactly=True,report_display_absolute_tolerance=DISPLAY_TOL,report_display_decimal_places=6,
        independent_selected_visitor_group_rows_compared=proof['rows'],independent_selected_visitor_group_fields_compared=5,
        private_selected_visitor_group_columns=GROUP_FIELDS,independent_selected_visitor_groups_all_integer_fields_exact=True,
        independent_selected_visitor_group_stream_sha256=proof['sha256'],independent_selected_visitor_groups_all_matched=True,
        selected_visitor_group_stream_sql_sha256=hashlib.sha256(stream_sql.encode()).hexdigest(),
        candidate_basket_key=['visitorid','transactionid'],frozen_SQL82_case_order_and_n_ab_verified=True,
        selected_pairs=len(selected),selected_pair_occurrences=sum(row[2] for row in selected),selected_visitor_group_cap=SELECTED_GROUP_CAP,
        selected_visitor_group_basket_counts_sum=sum(row[4] for row in groups),per_case_visitor_baskets_reconcile_to_n_ab=True,
        percentage_denominator='Each case n_ab; never 110.',repeat_visitor_definition='At least two paired baskets for the same visitor ID within the case.',
        repeat_share_numerator='All paired baskets contributed by repeat IDs, not only surplus baskets beyond the first.',
        top_visitor_identity_selected=False,high_concentration_treated_as_failure=False,visitor_ids_are_verified_people=False,
        independence_or_causal_significance_estimated=False,persistent_private_identifier_mapping_created=False,
        source_event_rows_used_as_pair_weight=False,candidate_baskets_are_verified_orders=False,
        retained_transaction_occurrences=source_counts['transaction'],transaction_occurrence_cap=counts.TRANSACTION_CAP,pair_occurrence_cap=counts.PAIR_CAP,distinct_pair_key_cap=counts.PAIR_CAP,
        private_database_sha256_before_readonly=database_before,private_database_sha256_after_readonly=database_after,private_database_bytes_unchanged=True,
        fixture_case_count=len(cases),fixture_cases=cases,invalid_control_fixture_subcases=2,
        invalid_admission_preserves_case_labels_and_masks_fields_verified=True,multiplied_visitor_group_counts_fail_verified=True,
        repeat_numerator_and_tied_maximum_fixture_verified=True,shared_transaction_ids_under_distinct_visitors_fixture_verified=True,
        preflight_settings=dict(threads=2,memory_limit='1GB',max_temp_directory_size='2GB',timeout_seconds_per_cli_phase=120,
            transaction_occurrence_cap=counts.TRANSACTION_CAP,pair_occurrence_cap=counts.PAIR_CAP,distinct_pair_key_cap=counts.PAIR_CAP,
            selected_visitor_group_cap=SELECTED_GROUP_CAP,minimum_free_bytes=8*1024**3,private_directory_budget_bytes=7*1024**3),
        private_input_csv_bytes=csv_bytes,private_database_bytes_before_cleanup=database_bytes,
        largest_private_directory_bytes_observed_after_phase=max(sizes),workspace_free_bytes_before=free_before,workspace_free_bytes_after=shutil.disk_usage(tmp_root).free,
        temporary_databases_and_spills_removed=True,private_membership_csv_removed=True,historical_preflight_files_unchanged=len(historical),
        historical_comparison_or_analysis_suites_rerun=False,source_records_or_identifiers_uploaded_or_logged=False,raw_pair_or_visitor_identifiers_published=False,
        elapsed_python_source_scan_reconstruction_seconds=source_seconds,elapsed_python_visitor_reference_seconds=reference_seconds,
        elapsed_private_input_load_readback_seconds=load_seconds,elapsed_readonly_concentration_report_seconds=query_seconds,elapsed_private_selected_visitor_group_stream_seconds=stream_seconds,
        timing_scope='One canonical parse and bounded private group reference; small private load/readback plus read-only case report and selected visitor-group stream. Source hash reads are separate; no old SQL or metric streams rerun.',
        scope='Assistant SQL83 preparation passed; learner execution pending. Descriptive visitor-ID concentration for twelve frozen exploratory cases, without verified-person, independent-observation or causal claims.')
    output.write_text(json.dumps(evidence,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps({'report_rows':12,'checks_passed':12,'selected_visitor_group_rows_compared':proof['rows'],
        'selected_visitor_group_fields':5,'report_sha256':evidence['report_sha256']}),flush=True)


if __name__=='__main__':main()
