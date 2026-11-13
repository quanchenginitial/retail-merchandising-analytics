"""Validate binary association formulas and a nested threshold profile using a bounded private copy."""
import argparse
import csv
import hashlib
import json
import math
import re
import shutil
import statistics
import subprocess
import tempfile
import threading
import time
from collections import Counter
from datetime import datetime, timezone
from fractions import Fraction
from itertools import zip_longest
from pathlib import Path

import preflight_retailrocket_basket_pair_counts as counts

model=counts.model
staging=counts.staging
source_reference=counts.source_reference
KEYS=counts.KEYS
CONTRACT_SHA='3f825703a4ef994189cd071c1f877fc43576ff3ae618b757fa9a376ac4dd4ea1'
OUTPUT=['min_pair_baskets','retained_pairs','retained_pair_pct','retained_pair_occurrences','median_support_pct',
        'median_directional_confidence_pct','median_lift','max_lift','check_status']
METRICS=['item_a','item_b','n_ab','n_a','n_b','n_baskets','support','confidence_a_to_b','confidence_b_to_a','lift']
THRESHOLDS=[1,2,3,5,10]
ABS_TOL=REL_TOL=1e-12
DISPLAY_TOL=0.5e-6+1e-12


def metric_reference(rows):
    stats,pairs=counts.pair_reference(rows);marginals=Counter(row[2] for row in rows);n=stats['baskets'];metrics=[]
    assert sum(marginals.values())==stats['memberships']
    for a,b,ab in pairs:
        na,nb=marginals[a],marginals[b]
        support,cab,cba,lift=Fraction(ab,n),Fraction(ab,na),Fraction(ab,nb),Fraction(n*ab,na*nb)
        assert support*n==cab*na==cba*nb==ab and lift*na*nb==n*ab
        assert 0<ab<=min(na,nb)<=n and 0<support<=1 and 0<cab<=1 and 0<cba<=1 and lift>0
        metrics.append((a,b,ab,na,nb,n,support,cab,cba,lift))
    return stats,metrics


def reference_profile(stats,metrics):
    report=[]
    for threshold in THRESHOLDS:
        kept=[row for row in metrics if row[2]>=threshold]
        values=[threshold,len(kept),Fraction(100*len(kept),len(metrics)) if metrics else None,sum(row[2] for row in kept),
            100*statistics.median(row[6] for row in kept) if kept else None,
            100*statistics.median([value for row in kept for value in row[7:9]]) if kept else None,
            statistics.median(row[9] for row in kept) if kept else None,max((row[9] for row in kept),default=None),'PASS']
        report.append(dict(zip(OUTPUT,values)))
    return report


def compare_profile(observed,expected):
    assert len(observed)==len(expected)==5
    for actual,wanted in zip(observed,expected):
        assert list(actual)==OUTPUT
        for key in OUTPUT:
            if key in ['min_pair_baskets','retained_pairs','retained_pair_occurrences','check_status'] or wanted[key] is None:
                assert actual[key]==wanted[key],'Private report count/status/NULL mismatch; values withheld'
            else:
                assert math.isfinite(actual[key]) and abs(actual[key]-float(wanted[key]))<=DISPLAY_TOL,'Private display value mismatch; values withheld'
                assert abs(actual[key]*1e6-round(actual[key]*1e6))<=1e-5,'Report exceeds six decimal display places'


def adjusted(sql,stats,override=None):
    query=counts.adjusted(sql,stats)
    values={name:stats[key] for name,key in [('expected_pair_occurrences','pair_occurrences'),('expected_distinct_pairs','distinct_pairs'),
        ('expected_pairs_seen_once','pairs_seen_once'),('expected_pairs_seen_2plus','pairs_seen_2plus'),('expected_max_pair_baskets','max_baskets_per_pair')]}
    values.update(override or {})
    for name,value in values.items():
        query,n=re.subn(r'\b[0-9]+::BIGINT AS '+name+r'\b',f'{value if value is not None else "NULL"}::BIGINT AS {name}',query);assert n==1
    return query


def metric_stream_sql(sql):
    assert sql.count('), metric_health AS (')==1
    return sql.split('), metric_health AS (',1)[0]+')\nSELECT '+','.join(METRICS)+' FROM pair_metrics ORDER BY item_a,item_b;'


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--duckdb',required=True)
    parser.add_argument('--output',required=True);parser.add_argument('--fixtures-only',action='store_true');args=parser.parse_args()
    root=Path(__file__).resolve().parents[1];output=(root/args.output).resolve()
    script_path='sql/81_analyze_retailrocket_basket_association_metrics.sql'
    validator_path='validation/preflight_retailrocket_basket_association_metrics.py';method_path='docs/RETAILROCKET_BASKET_ASSOCIATION_METRICS_VALIDATION.md'
    assert output==(root/'data/retailrocket_basket_association_metrics_preflight.json').resolve()
    old=json.loads((root/'data/retailrocket_basket_pair_counts_preflight.json').read_text(encoding='utf-8'))
    accepted=json.loads((root/'data/retailrocket_basket_pair_counts_learner_acceptance.json').read_text(encoding='utf-8'))
    assert accepted['acceptance_status']=='accepted' and accepted['report_sha256']==old['report_sha256']
    deps=list(old['code_and_dependency_sha256'])+[script_path,validator_path,'data/retailrocket_basket_pair_counts_preflight.json',
        'data/retailrocket_basket_pair_counts_learner_acceptance.json','docs/RETAILROCKET_BASKET_PAIR_COUNTS_VALIDATION.md']
    hashes={name:source_reference.sha256(root/name) for name in deps}
    assert all(hashes[name]==digest for name,digest in old['code_and_dependency_sha256'].items())
    contract=(root/method_path).read_bytes().split(b'\n## Executed results\n',1)[0]
    assert hashlib.sha256(contract).hexdigest()==CONTRACT_SHA
    sql=(root/script_path).read_text(encoding='utf-8');clean=re.sub(r'--[^\n]*','',sql)
    assert clean.lstrip().startswith('WITH ') and not re.search(r'\b(CREATE|INSERT|UPDATE|DELETE|DROP|ALTER|COPY|SET|ATTACH|DETACH)\b',clean,re.I)
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

    cases=[]
    baskets=[(1,10,[2,10]),(2,10,[2,10]),(3,30,[2]),(4,40,[2,20]),(5,50,[10])]
    rows=sorted((visitor,transaction,item,100,100,1) for visitor,transaction,items in baskets for item in items)
    stats,metrics=metric_reference(rows)
    assert metrics==[(2,10,2,4,3,5,Fraction(2,5),Fraction(1,2),Fraction(2,3),Fraction(5,6)),
        (2,20,1,4,1,5,Fraction(1,5),Fraction(1,4),Fraction(1),Fraction(5,4))]
    expected=reference_profile(stats,metrics)
    assert expected[0]['median_support_pct']==30 and expected[0]['median_directional_confidence_pct']==Fraction(175,3)
    assert expected[0]['median_lift']==Fraction(25,24)
    with tempfile.TemporaryDirectory(prefix='rr-association-fixture-',dir=tmp_root) as temporary:
        folder,database=Path(temporary),Path(temporary)/'fixture.duckdb';load_memberships(folder,database,rows)
        execute(folder,database,'ALTER TABLE rr_mart.transaction_basket_items ADD COLUMN unqueried_fixture VARCHAR;')
        query=adjusted(sql,stats);before_db=source_reference.sha256(database)
        report,_=execute(folder,database,query,readonly=True);compare_profile(report,expected)
        proof,_=compare_metrics(folder,database,metric_stream_sql(query),iter(metrics))
        assert proof['rows']==2 and source_reference.sha256(database)==before_db
        assert all(row['retained_pairs']==row['retained_pair_occurrences']==0 and row['median_lift'] is None
            and row['median_support_pct'] is None and row['median_directional_confidence_pct'] is None and row['max_lift'] is None for row in report[2:])
        ignored,_=execute(folder,database,'BEGIN;UPDATE rr_mart.transaction_basket_items SET source_event_rows=source_event_rows+1000;'+query+'ROLLBACK;')
        assert ignored==report
        cases.append(dict(case='asymmetric_all_basket_marginals_unweighted_medians_lift_below_and_above_one_empty_thresholds_ignored_occurrences',passed=True,
            candidate_baskets=5,metric_rows=2,full_metric_fields_compared=10))
        for label,mutation in [('duplicate_key','INSERT INTO rr_mart.transaction_basket_items SELECT * FROM rr_mart.transaction_basket_items LIMIT 1;'),
            ('empty_input','DELETE FROM rr_mart.transaction_basket_items;')]:
            blocked,_=execute(folder,database,'BEGIN;'+mutation+query+'ROLLBACK;')
            assert [row['min_pair_baskets'] for row in blocked]==THRESHOLDS
            assert all(row['check_status']=='BLOCKED' and all(row[key] is None for key in OUTPUT[1:-1]) for row in blocked),label
        failed,_=execute(folder,database,adjusted(sql,stats,{'expected_distinct_pairs':3}),readonly=True)
        assert all(row['check_status']=='FAIL' and all(row[key] is None for key in OUTPUT[1:-1]) for row in failed)
        cases.append(dict(case='invalid_duplicate_or_empty_admission_BLOCKED_post_admission_wrong_pair_control_FAIL',passed=True,subcases=3))
    assert not folder.exists()
    print(json.dumps({'fixture_families_passed':len(cases),'invalid_control_subcases':3}),flush=True)
    if args.fixtures_only:return

    before={'events.csv':staging.snapshot(source)}
    assert all(before['events.csv'][key]==source_audit['source_before']['events.csv'][key]==source_audit['source_after']['events.csv'][key]
        for key in ['size_bytes','modified_time_ns','sha256'])
    historical={str(p.relative_to(root)):source_reference.sha256(p) for p in (root/'data').glob('*preflight.json') if p.resolve()!=output.resolve()}
    assert len(historical)==79
    started=time.perf_counter();rows,source_counts=counts.scan_source(source);source_seconds=round(time.perf_counter()-started,3)
    assert source_counts==old['independent_python_source_counts'] and len(rows)==22323
    input_hash=counts.canonical_hash(rows);assert input_hash==old['accepted_SQL79_membership_sha256']
    started=time.perf_counter();stats,metrics=metric_reference(rows);expected=reference_profile(stats,metrics)
    reference_seconds=round(time.perf_counter()-started,3);assert stats==old['independent_python_pair_counts']
    print(json.dumps({'phase':'single canonical parse and accepted membership fingerprint matched'}),flush=True)
    with tempfile.TemporaryDirectory(prefix='rr-association-real-',dir=tmp_root) as temporary:
        folder,database=Path(temporary),Path(temporary)/'preflight.duckdb'
        readback_hash,load_seconds,csv_bytes=load_memberships(folder,database,rows);assert readback_hash==input_hash
        database_before=source_reference.sha256(database)
        report,query_seconds=execute(folder,database,sql,readonly=True);compare_profile(report,expected)
        assert Counter(row['check_status'] for row in report)==Counter(PASS=5)
        proof,stream_seconds=compare_metrics(folder,database,stream_sql,iter(metrics))
        assert proof['rows']==stats['distinct_pairs']==9688
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
        accepted_original_five_field_proof_reused=True,original_five_field_occurrence_comparison_rerun=False,original_event_external_sort_rerun=False,
        SQL54_rerun=False,SQL63_rerun=False,SQL79_rerun=False,SQL80_rerun=False,stored_membership_timestamps_and_counts_in_query_readset=False,
        property_files_read=False,category_csv_read=False,UTC_fields_read=False,property_history_reconstructed=False,category_hierarchy_reverified=False,
        learner_database_opened=False,query_read_only=True,private_metric_stream_read_only=True,
        real_source_attempts=1,real_event_csv_parse_passes=1,real_cli_phases=3,real_private_input_load_executions=1,real_analysis_script_executions=1,real_private_metric_stream_executions=1,
        report_rows=5,report_columns=9,output_columns=OUTPUT,checks_passed=5,fail_rows=0,blocked_rows=0,results=report,
        report_sha256=counts.canonical_hash([[row[key] for key in OUTPUT] for row in report]),
        report_fingerprint_contract='SHA-256 of actual returned compact JSON arrays in output-column order followed by LF. Rounded displays are independently compared within stated absolute tolerance, not asserted mathematically exact.',
        independent_python_source_counts=source_counts,independent_python_pair_counts=stats,independent_python_profile_matched_with_display_tolerance=True,
        profile_integer_fields_compared_exactly=True,profile_display_absolute_tolerance=DISPLAY_TOL,profile_display_decimal_places=6,
        independent_metric_rows_compared=proof['rows'],independent_metric_fields_compared=10,private_metric_columns=METRICS,
        independent_metric_integer_fields_compared_exactly=6,independent_metric_float_fields_compared_with_tolerance=4,
        independent_metric_stream_sha256=proof['sha256'],independent_metrics_all_matched=True,
        metric_absolute_tolerance=ABS_TOL,metric_relative_tolerance=REL_TOL,observed_max_metric_absolute_error=proof['max_absolute_error'],
        independent_fraction_identities_checked=True,metric_stream_sql_sha256=hashlib.sha256(stream_sql.encode()).hexdigest(),
        candidate_basket_key=['visitorid','transactionid'],unordered_numeric_pair_verified=True,singleton_baskets_retained_in_population_and_marginals=True,
        support_denominator=17672,retained_pair_pct_denominator=9688,thresholds=THRESHOLDS,threshold_rows_nested=True,threshold_rows_additive=False,
        distribution_weighting='Equal unordered-pair weight for support/lift; equal weight for both confidence directions of each retained pair; no basket-frequency weights.',
        source_event_rows_used_as_pair_weight=False,association_metrics_calculated=True,thresholds_selected_as_optimal=False,
        candidate_baskets_are_verified_orders=False,recommendation_or_causal_effect_estimated=False,
        retained_transaction_occurrences=source_counts['transaction'],transaction_occurrence_cap=counts.TRANSACTION_CAP,pair_occurrence_cap=counts.PAIR_CAP,distinct_pair_key_cap=counts.PAIR_CAP,
        private_database_sha256_before_readonly=database_before,private_database_sha256_after_readonly=database_after,private_database_bytes_unchanged=True,
        fixture_case_count=len(cases),fixture_cases=cases,invalid_control_fixture_subcases=3,
        invalid_admission_blocks_all_measured_fields_verified=True,post_admission_control_failure_masks_fields_verified=True,
        additional_unqueried_columns_allowed_verified=True,unqueried_source_event_rows_ignored_verified=True,empty_threshold_counts_zero_metrics_NULL_verified=True,
        preflight_settings=dict(threads=2,memory_limit='1GB',max_temp_directory_size='2GB',timeout_seconds_per_cli_phase=120,
            transaction_occurrence_cap=counts.TRANSACTION_CAP,pair_occurrence_cap=counts.PAIR_CAP,distinct_pair_key_cap=counts.PAIR_CAP,
            minimum_free_bytes=8*1024**3,private_directory_budget_bytes=7*1024**3),
        private_input_csv_bytes=csv_bytes,private_database_bytes_before_cleanup=database_bytes,
        largest_private_directory_bytes_observed_after_phase=max(sizes),workspace_free_bytes_before=free_before,workspace_free_bytes_after=shutil.disk_usage(tmp_root).free,
        temporary_databases_and_spills_removed=True,private_membership_csv_removed=True,historical_preflight_files_unchanged=len(historical),
        historical_comparison_or_analysis_suites_rerun=False,source_records_or_identifiers_uploaded_or_logged=False,raw_pair_list_published=False,
        elapsed_python_source_scan_reconstruction_seconds=source_seconds,elapsed_python_metric_reference_seconds=reference_seconds,
        elapsed_private_input_load_readback_seconds=load_seconds,elapsed_readonly_profile_seconds=query_seconds,elapsed_private_metric_stream_seconds=stream_seconds,
        timing_scope='One canonical CSV parse and bounded membership/rational-metric reference, plus small private load/readback and two read-only CLI phases. Hash scans also read source bytes. No old SQL runs or full event sort.',
        scope='Assistant SQL81 preparation passed; learner execution pending. Nested binary association-metric distributions over all candidate baskets, without public pair identities, recommendation effects, quantity or revenue claims.')
    output.write_text(json.dumps(evidence,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps({'report_rows':5,'checks_passed':5,'metric_rows_compared':proof['rows'],'metric_fields':10,'report_sha256':evidence['report_sha256']}),flush=True)


if __name__=='__main__':main()
