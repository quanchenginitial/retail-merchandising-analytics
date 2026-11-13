"""Check all exploratory pair cases and their selected keyed metrics without rerunning full metric proofs."""
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
from itertools import zip_longest
from pathlib import Path

import preflight_retailrocket_basket_association_metrics as association

counts=association.counts
model=association.model
staging=association.staging
source_reference=association.source_reference
KEYS=association.KEYS
METRICS=association.METRICS
ABS_TOL=REL_TOL=1e-12
DISPLAY_TOL=association.DISPLAY_TOL
CONTRACT_SHA='04726b98a1b9c16751148a842b3ec1208336cb282d3371da4ed032b065b0d28f'
OUTPUT=['case_label','n_ab','n_a','n_b','support_pct','confidence_a_to_b_pct','confidence_b_to_a_pct','lift','check_status']
MIN_PAIR_BASKETS=5


def selected_reference(rows):
    stats,metrics=association.metric_reference(rows)
    selected=sorted((row for row in metrics if row[2]>=MIN_PAIR_BASKETS),key=lambda row:(-row[2],row[3]*row[4],row[0],row[1]))
    assert selected==sorted((row for row in metrics if row[2]>=MIN_PAIR_BASKETS),key=lambda row:(-row[2],-row[9],row[0],row[1]))
    return stats,selected


def reference_cases(selected):
    return [dict(zip(OUTPUT,[f'PAIR_{rank:02d}',row[2],row[3],row[4],row[6]*100,row[7]*100,row[8]*100,row[9],'PASS']))
        for rank,row in enumerate(selected,1)]


def compare_cases(observed,expected):
    assert len(observed)==len(expected)
    for actual,wanted in zip(observed,expected):
        assert list(actual)==OUTPUT
        for key in OUTPUT:
            if key in ['case_label','n_ab','n_a','n_b','check_status']:
                assert actual[key]==wanted[key],'Private case identity/count/status differs; values withheld'
            else:
                assert math.isfinite(actual[key]) and abs(actual[key]-float(wanted[key]))<=DISPLAY_TOL,'Private case display differs; values withheld'
                assert abs(actual[key]*1e6-round(actual[key]*1e6))<=1e-5


def adjusted(sql,stats,selected,override=None):
    query=association.adjusted(sql,stats)
    values={'expected_selected_pairs':len(selected),'expected_selected_pair_occurrences':sum(row[2] for row in selected)}
    values.update(override or {})
    for name,value in values.items():
        query,n=re.subn(r'\b[0-9]+::BIGINT AS '+name+r'\b',f'{value}::BIGINT AS {name}',query);assert n==1
    return query


def metric_stream_sql(sql):
    assert sql.count('), selected_health AS (')==1
    return sql.split('), selected_health AS (',1)[0]+')\nSELECT '+','.join(METRICS)+' FROM selected_pairs ORDER BY case_rank;'


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--duckdb',required=True)
    parser.add_argument('--output',required=True);parser.add_argument('--fixtures-only',action='store_true');args=parser.parse_args()
    root=Path(__file__).resolve().parents[1];output=(root/args.output).resolve()
    script_path='sql/82_analyze_retailrocket_basket_pair_cases.sql'
    validator_path='validation/preflight_retailrocket_basket_pair_cases.py';method_path='docs/RETAILROCKET_BASKET_PAIR_CASES_VALIDATION.md'
    assert output==(root/'data/retailrocket_basket_pair_cases_preflight.json').resolve()
    old=json.loads((root/'data/retailrocket_basket_association_metrics_preflight.json').read_text(encoding='utf-8'))
    accepted=json.loads((root/'data/retailrocket_basket_association_metrics_learner_acceptance.json').read_text(encoding='utf-8'))
    assert accepted['acceptance_status']=='accepted' and accepted['report_sha256']==old['report_sha256']
    deps=list(old['code_and_dependency_sha256'])+[script_path,validator_path,'data/retailrocket_basket_association_metrics_preflight.json',
        'data/retailrocket_basket_association_metrics_learner_acceptance.json','docs/RETAILROCKET_BASKET_ASSOCIATION_METRICS_VALIDATION.md']
    hashes={name:source_reference.sha256(root/name) for name in deps}
    assert all(hashes[name]==digest for name,digest in old['code_and_dependency_sha256'].items())
    contract=(root/method_path).read_bytes().split(b'\n## Executed results\n',1)[0]
    assert hashlib.sha256(contract).hexdigest()==CONTRACT_SHA
    sql=(root/script_path).read_text(encoding='utf-8');clean=re.sub(r'--[^\n]*','',sql)
    assert clean.lstrip().startswith('WITH ') and not re.search(r'\b(CREATE|INSERT|UPDATE|DELETE|DROP|ALTER|COPY|SET|ATTACH|DETACH|LIMIT)\b',clean,re.I)
    assert all(name not in clean for name in ['first_timestamp_ms','last_timestamp_ms','source_event_rows','rr_stg','rr_core','categoryid','available'])
    stream_sql=metric_stream_sql(sql)
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
    def compare_metrics(folder,database,query,expected):
        started=time.perf_counter();expired=threading.Event();count=0;sentinel=object();digest=hashlib.sha256();max_absolute=0.0
        process=subprocess.Popen([args.duckdb,str(database),'-bail','-readonly','-csv','-noheader'],stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,encoding='utf-8')
        def expire():expired.set();process.kill()
        timer=threading.Timer(120,expire);timer.start()
        try:
            process.stdin.write(settings(folder,database)+query);process.stdin.close()
            for observed,wanted in zip_longest(csv.reader(process.stdout,strict=True),expected,fillvalue=sentinel):
                assert observed is not sentinel and wanted is not sentinel,'Private metric row count differs'
                assert len(observed)==10
                actual=tuple(int(value) for value in observed[:6])+tuple(float(value) for value in observed[6:])
                assert actual[:6]==wanted[:6],'Private metric integer fields differ; values withheld'
                for value,fraction in zip(actual[6:],wanted[6:]):
                    assert math.isfinite(value) and math.isclose(value,float(fraction),rel_tol=REL_TOL,abs_tol=ABS_TOL),'Private metric formula differs; values withheld'
                    max_absolute=max(max_absolute,abs(value-float(fraction)))
                digest.update((json.dumps(actual,separators=(',',':'))+'\n').encode());count+=1
            assert process.wait(timeout=120)==0 and not expired.is_set()
        finally:
            timer.cancel()
            if process.poll() is None:process.kill();process.wait()
            process.stdout.close()
        observe(folder)
        return dict(rows=count,fields=10,sha256=digest.hexdigest(),max_absolute_error=max_absolute),round(time.perf_counter()-started,3)

    cases=[];rows=[];transaction=0
    for item_a in range(2,17):
        item_b=item_a+100
        for occurrence in range(5):
            transaction+=1
            rows.extend([(1,transaction,item_a,100,100,1),(1,transaction,item_b,100,100,1)])
    for occurrence in range(4):
        transaction+=1;rows.extend([(1,transaction,50,100,100,1),(1,transaction,150,100,100,1)])
    transaction+=1;rows.append((1,transaction,2,100,100,1));rows.sort()
    stats,selected=selected_reference(rows);expected=reference_cases(selected)
    assert stats['baskets']==80 and len(selected)==15 and sum(row[2] for row in selected)==75
    assert [row[0] for row in selected]==list(range(3,17))+[2]
    assert all(row[2]==5 for row in selected) and all(row[9]==16 for row in selected[:-1])
    with tempfile.TemporaryDirectory(prefix='rr-pair-case-fixture-',dir=tmp_root) as temporary:
        folder,database=Path(temporary),Path(temporary)/'fixture.duckdb';load_memberships(folder,database,rows)
        query=adjusted(sql,stats,selected);before_db=source_reference.sha256(database)
        report,_=execute(folder,database,query,readonly=True);compare_cases(report,expected)
        proof,_=compare_metrics(folder,database,metric_stream_sql(query),iter(selected))
        assert proof['rows']==15 and source_reference.sha256(database)==before_db
        assert report[0]['case_label']=='PAIR_01' and report[-1]['case_label']=='PAIR_15'
        assert report[-1]['n_a']==6 and report[-1]['n_b']==5
        cases.append(dict(case='fifteen_qualifying_pairs_no_LIMIT_threshold_boundary_exact_lift_and_numeric_ties_singleton_marginal',passed=True,
            candidate_baskets=80,selected_pairs=15,selected_pair_occurrences=75,complete_selected_metric_fields=10))
        blocked,_=execute(folder,database,'BEGIN;DELETE FROM rr_mart.transaction_basket_items;'+query+'ROLLBACK;')
        assert len(blocked)==15 and [row['case_label'] for row in blocked]==[row['case_label'] for row in report]
        assert all(row['check_status']=='BLOCKED' and all(row[key] is None for key in OUTPUT[1:-1]) for row in blocked)
        failed,_=execute(folder,database,adjusted(sql,stats,selected,{'expected_selected_pair_occurrences':76}),readonly=True)
        assert len(failed)==15 and all(row['check_status']=='FAIL' and all(row[key] is None for key in OUTPUT[1:-1]) for row in failed)
        cases.append(dict(case='empty_source_preserves_case_labels_BLOCKED_wrong_selection_control_FAIL_masks_values',passed=True,subcases=2))
    assert not folder.exists()
    print(json.dumps({'fixture_families_passed':len(cases),'invalid_control_subcases':2}),flush=True)
    if args.fixtures_only:return

    before={'events.csv':staging.snapshot(source)}
    assert all(before['events.csv'][key]==source_audit['source_before']['events.csv'][key]==source_audit['source_after']['events.csv'][key]
        for key in ['size_bytes','modified_time_ns','sha256'])
    historical={str(p.relative_to(root)):source_reference.sha256(p) for p in (root/'data').glob('*preflight.json') if p.resolve()!=output.resolve()}
    assert len(historical)==80
    started=time.perf_counter();rows,source_counts=counts.scan_source(source);source_seconds=round(time.perf_counter()-started,3)
    assert source_counts==old['independent_python_source_counts'] and len(rows)==22323
    input_hash=counts.canonical_hash(rows);assert input_hash==old['accepted_SQL79_membership_sha256']
    started=time.perf_counter();stats,selected=selected_reference(rows);expected=reference_cases(selected)
    reference_seconds=round(time.perf_counter()-started,3);assert stats==old['independent_python_pair_counts']
    assert len(selected)==12 and sum(row[2] for row in selected)==110
    print(json.dumps({'phase':'single canonical parse and accepted six-field membership fingerprint matched'}),flush=True)
    with tempfile.TemporaryDirectory(prefix='rr-pair-case-real-',dir=tmp_root) as temporary:
        folder,database=Path(temporary),Path(temporary)/'preflight.duckdb'
        readback_hash,load_seconds,csv_bytes=load_memberships(folder,database,rows);assert readback_hash==input_hash
        database_before=source_reference.sha256(database)
        report,query_seconds=execute(folder,database,sql,readonly=True);compare_cases(report,expected)
        assert Counter(row['check_status'] for row in report)==Counter(PASS=12)
        proof,stream_seconds=compare_metrics(folder,database,stream_sql,iter(selected));assert proof['rows']==12
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
        accepted_original_five_field_proof_reused=True,accepted_SQL81_full_metric_proof_reused=True,
        full_9688_SQL_metric_stream_recompared=False,original_five_field_occurrence_comparison_rerun=False,original_event_external_sort_rerun=False,
        SQL54_rerun=False,SQL63_rerun=False,SQL79_rerun=False,SQL80_rerun=False,SQL81_rerun=False,stored_membership_timestamps_and_counts_in_query_readset=False,
        property_files_read=False,category_csv_read=False,UTC_fields_read=False,property_history_reconstructed=False,category_hierarchy_reverified=False,
        learner_database_opened=False,query_read_only=True,private_selected_metric_stream_read_only=True,
        real_source_attempts=1,real_event_csv_parse_passes=1,real_cli_phases=3,real_private_input_load_executions=1,real_analysis_script_executions=1,real_private_selected_metric_stream_executions=1,
        report_rows=12,report_columns=9,output_columns=OUTPUT,checks_passed=12,fail_rows=0,blocked_rows=0,results=report,
        report_sha256=counts.canonical_hash([[row[key] for key in OUTPUT] for row in report]),
        report_fingerprint_contract='SHA-256 of actual returned compact JSON arrays in output-column order followed by LF; case order preserved. Rounded displays are compared within stated tolerance.',
        independent_python_source_counts=source_counts,independent_python_pair_counts=stats,independent_python_cases_matched_with_display_tolerance=True,
        case_labels_counts_status_and_order_compared_exactly=True,report_display_absolute_tolerance=DISPLAY_TOL,report_display_decimal_places=6,
        independent_selected_metric_rows_compared=proof['rows'],independent_selected_metric_fields_compared=10,private_selected_metric_columns=METRICS,
        independent_selected_metric_integer_fields_compared_exactly=6,independent_selected_metric_float_fields_compared_with_tolerance=4,
        independent_selected_metric_stream_sha256=proof['sha256'],independent_selected_metrics_all_matched=True,
        metric_absolute_tolerance=ABS_TOL,metric_relative_tolerance=REL_TOL,observed_max_selected_metric_absolute_error=proof['max_absolute_error'],
        selected_metric_stream_sql_sha256=hashlib.sha256(stream_sql.encode()).hexdigest(),
        candidate_basket_key=['visitorid','transactionid'],unordered_numeric_pair_verified=True,singleton_baskets_retained_in_population_and_marginals=True,
        support_denominator=17672,min_pair_baskets=MIN_PAIR_BASKETS,selected_pairs=len(selected),selected_pair_occurrences=sum(row[2] for row in selected),
        selection_includes_all_qualifying_pairs=True,LIMIT_used=False,selection_threshold_optimality_claimed=False,
        exact_sort_order=['n_ab DESC','n_a*n_b ASC','item_a ASC','item_b ASC'],integer_product_sort_equals_unrounded_lift_sort_verified=True,
        case_label_scope='PAIR_%02d minimum-width labels reconstructible for this accepted snapshot and query; not global item aliases or an anonymization guarantee.',
        persistent_private_identifier_mapping_created=False,source_event_rows_used_as_pair_weight=False,candidate_baskets_are_verified_orders=False,
        recommendation_or_causal_effect_estimated=False,retained_transaction_occurrences=source_counts['transaction'],
        transaction_occurrence_cap=counts.TRANSACTION_CAP,pair_occurrence_cap=counts.PAIR_CAP,distinct_pair_key_cap=counts.PAIR_CAP,
        private_database_sha256_before_readonly=database_before,private_database_sha256_after_readonly=database_after,private_database_bytes_unchanged=True,
        fixture_case_count=len(cases),fixture_cases=cases,invalid_control_fixture_subcases=2,
        invalid_admission_preserves_case_labels_and_masks_fields_verified=True,post_selection_control_failure_masks_fields_verified=True,
        more_than_twelve_qualifying_fixture_pairs_all_returned=True,threshold_boundary_and_tie_order_verified=True,
        preflight_settings=dict(threads=2,memory_limit='1GB',max_temp_directory_size='2GB',timeout_seconds_per_cli_phase=120,
            transaction_occurrence_cap=counts.TRANSACTION_CAP,pair_occurrence_cap=counts.PAIR_CAP,distinct_pair_key_cap=counts.PAIR_CAP,
            minimum_free_bytes=8*1024**3,private_directory_budget_bytes=7*1024**3),
        private_input_csv_bytes=csv_bytes,private_database_bytes_before_cleanup=database_bytes,
        largest_private_directory_bytes_observed_after_phase=max(sizes),workspace_free_bytes_before=free_before,workspace_free_bytes_after=shutil.disk_usage(tmp_root).free,
        temporary_databases_and_spills_removed=True,private_membership_csv_removed=True,historical_preflight_files_unchanged=len(historical),
        historical_comparison_or_analysis_suites_rerun=False,source_records_or_identifiers_uploaded_or_logged=False,raw_pair_identifiers_published=False,
        elapsed_python_source_scan_reconstruction_seconds=source_seconds,elapsed_python_metric_reference_selection_seconds=reference_seconds,
        elapsed_private_input_load_readback_seconds=load_seconds,elapsed_readonly_case_report_seconds=query_seconds,elapsed_private_selected_metric_stream_seconds=stream_seconds,
        timing_scope='One canonical CSV parse and bounded independent rational selection, plus private input load/readback and two read-only phases. Source hash reads are separate; no full SQL metric stream repeated.',
        scope='Assistant SQL82 preparation passed; learner execution pending. All pairs observed in at least five candidate baskets, with snapshot case labels and no public raw item IDs, optimized threshold or recommendation-effect claim.')
    output.write_text(json.dumps(evidence,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps({'report_rows':12,'checks_passed':12,'selected_metric_rows_compared':proof['rows'],'selected_metric_fields':10,'report_sha256':evidence['report_sha256']}),flush=True)


if __name__=='__main__':main()
