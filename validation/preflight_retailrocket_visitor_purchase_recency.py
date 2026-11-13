"""Validate integer elapsed recency at a frozen global endpoint, separately from frequency."""
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

import preflight_retailrocket_visitor_purchase_frequency as previous

counts=previous.counts
model=previous.model
staging=previous.staging
source_reference=previous.source_reference
READSET=['visitorid','transactionid','itemid','last_timestamp_ms']
DISPLAY_TOL=previous.DISPLAY_TOL
CONTRACT_SHA='338d01de50fe7c66ef27c4abc4d1b9ced7b194e6abac83d2ff4a0c3593940149'
REFERENCE_MS=1442545187788
REFERENCE_UTC='2015-09-18T02:59:47.788000Z'
SOURCE_MIN_MS=1430622004384
DAY_MS=86400000
BOUNDARIES=[7*DAY_MS,30*DAY_MS,60*DAY_MS]
OUTPUT=['recency_band','visitor_ids','visitor_share_pct','min_recency_days','median_recency_days','max_recency_days','check_status']
RECENCY_FIELDS=['visitorid','last_transaction_ms','recency_ms']
BANDS=['R_LT_7D','R_7_TO_LT_30D','R_30_TO_LT_60D','R_GE_60D','TOTAL']
RECENCY_CAP=100000


def exact_median(values):
    ordered=sorted(values);n=len(ordered)
    if not n:return None
    return Fraction(ordered[n//2]) if n%2 else Fraction(ordered[n//2-1]+ordered[n//2],2)


def recency_reference(rows):
    assert len({row[:3] for row in rows})==len(rows)
    basket_items=Counter(row[:2] for row in rows);latest={}
    for row in rows:
        assert isinstance(row[4],int) and SOURCE_MIN_MS<=row[4]<=REFERENCE_MS
        latest[row[0]]=max(latest.get(row[0],SOURCE_MIN_MS),row[4])
    assert len(latest)<=RECENCY_CAP
    stream=[(visitor,stamp,REFERENCE_MS-stamp) for visitor,stamp in sorted(latest.items())]
    values=[row[2] for row in stream]
    assert all(0<=value<=REFERENCE_MS-SOURCE_MIN_MS for value in values)
    stats=dict(memberships=len(rows),baskets=len(basket_items),single_baskets=sum(value==1 for value in basket_items.values()),
        multi_baskets=sum(value>1 for value in basket_items.values()),max_items=max(basket_items.values(),default=None),visitor_ids=len(latest))
    groups=[[value for value in values if value<BOUNDARIES[0]],[value for value in values if BOUNDARIES[0]<=value<BOUNDARIES[1]],
        [value for value in values if BOUNDARIES[1]<=value<BOUNDARIES[2]],[value for value in values if value>=BOUNDARIES[2]],values]
    report=[dict(zip(OUTPUT,[band,len(group),Fraction(100*len(group),len(values)),
        Fraction(min(group),DAY_MS) if group else None,exact_median(group)/DAY_MS if group else None,
        Fraction(max(group),DAY_MS) if group else None,'PASS'])) for band,group in zip(BANDS,groups)]
    assert sum(row['visitor_ids'] for row in report[:4])==len(latest)
    return stats,stream,report


def compare_report(observed,expected):
    assert len(observed)==len(expected)==5
    for actual,wanted in zip(observed,expected):
        assert list(actual)==OUTPUT
        for key in OUTPUT:
            if key in ['recency_band','visitor_ids','check_status'] or wanted[key] is None:
                assert actual[key]==wanted[key],'Private recency label/count/NULL/status differs; values withheld'
            else:
                assert math.isfinite(actual[key]) and abs(actual[key]-float(wanted[key]))<=DISPLAY_TOL,'Private recency display differs; values withheld'
                assert abs(actual[key]*1e6-round(actual[key]*1e6))<=1e-5


def adjusted(sql,stats):
    query=counts.adjusted(sql,stats)
    query,n=re.subn(r'\b[0-9]+::BIGINT AS expected_visitor_ids\b',f"{stats['visitor_ids']}::BIGINT AS expected_visitor_ids",query);assert n==1
    return query


def recency_stream_sql(sql):
    assert sql.count('), recency_health AS (')==1
    return sql.split('), recency_health AS (',1)[0]+')\nSELECT '+','.join(RECENCY_FIELDS)+' FROM visitor_recency ORDER BY visitorid;'


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--duckdb',required=True)
    parser.add_argument('--output',required=True);parser.add_argument('--fixtures-only',action='store_true');args=parser.parse_args()
    root=Path(__file__).resolve().parents[1];output=(root/args.output).resolve()
    script_path='sql/86_analyze_retailrocket_visitor_purchase_recency.sql'
    validator_path='validation/preflight_retailrocket_visitor_purchase_recency.py';method_path='docs/RETAILROCKET_VISITOR_PURCHASE_RECENCY_VALIDATION.md'
    assert output==(root/'data/retailrocket_visitor_purchase_recency_preflight.json').resolve()
    old=json.loads((root/'data/retailrocket_visitor_purchase_frequency_preflight.json').read_text(encoding='utf-8'))
    accepted=json.loads((root/'data/retailrocket_visitor_purchase_frequency_learner_acceptance.json').read_text(encoding='utf-8'))
    assert accepted['acceptance_status']=='accepted' and accepted['report_sha256']==old['report_sha256']
    time_path='data/retailrocket_event_time_preflight.json';time_acceptance_path='data/retailrocket_event_time_learner_acceptance.json'
    time_proof=json.loads((root/time_path).read_text(encoding='utf-8'));time_accepted=json.loads((root/time_acceptance_path).read_text(encoding='utf-8'))
    assert time_accepted['acceptance_status']=='accepted' and time_accepted['script']=='sql/64_audit_retailrocket_event_time.sql'
    assert time_accepted['report_sha256']==time_proof['report_sha256'] and time_accepted['assistant_preflight_sha256']==source_reference.sha256(root/time_path)
    for proof in [time_proof,time_accepted]:
        time_values={row['check_name']:row['actual'] for row in proof['results']}
        assert int(time_values['max_timestamp_ms'])==REFERENCE_MS and int(time_values['min_timestamp_ms'])==SOURCE_MIN_MS
        assert time_values['last_utc_timestamp']==REFERENCE_UTC
    overview_path='data/retailrocket_event_overview_preflight.json';overview_acceptance_path='data/retailrocket_event_overview_learner_acceptance.json'
    overview=json.loads((root/overview_path).read_text(encoding='utf-8'));overview_accepted=json.loads((root/overview_acceptance_path).read_text(encoding='utf-8'))
    assert overview_accepted['acceptance_status']=='accepted' and overview_accepted['report_sha256']==overview['report_sha256']
    assert overview_accepted['assistant_preflight_sha256']==source_reference.sha256(root/overview_path)
    for proof in [overview,overview_accepted]:
        assert [row['last_event_utc'] for row in proof['results'] if row['event_type']=='TOTAL']==[REFERENCE_UTC]
        assert [row['distinct_visitor_ids'] for row in proof['results'] if row['event_type']=='transaction']==[11719]
    transaction_end=next(row['last_event_utc'] for row in overview['results'] if row['event_type']=='transaction');assert transaction_end<REFERENCE_UTC
    deps=list(old['code_and_dependency_sha256'])+[script_path,validator_path,'data/retailrocket_visitor_purchase_frequency_preflight.json',
        'data/retailrocket_visitor_purchase_frequency_learner_acceptance.json','docs/RETAILROCKET_VISITOR_PURCHASE_FREQUENCY_VALIDATION.md',time_path,time_acceptance_path,overview_path,overview_acceptance_path]
    hashes={name:source_reference.sha256(root/name) for name in deps}
    assert all(hashes[name]==digest for name,digest in old['code_and_dependency_sha256'].items())
    contract=(root/method_path).read_bytes().split(b'\n## Executed results\n',1)[0]
    assert hashlib.sha256(contract).hexdigest()==CONTRACT_SHA
    sql=(root/script_path).read_text(encoding='utf-8');clean=re.sub(r'--[^\n]*','',sql)
    assert clean.lstrip().startswith('WITH ') and not re.search(r'\b(CREATE|INSERT|UPDATE|DELETE|DROP|ALTER|COPY|SET|ATTACH|DETACH|LIMIT|CURRENT_DATE|CURRENT_TIMESTAMP|NOW)\b',clean,re.I)
    assert 'last_timestamp_ms' in clean and all(name not in clean for name in ['first_timestamp_ms','source_event_rows','rr_stg','rr_core','categoryid','available','visitor_frequency','pair_counts','selected_pairs'])
    stream_sql=recency_stream_sql(sql)
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
    def compare_recencies(folder,database,query,expected):
        started=time.perf_counter();expired=threading.Event();count=0;sentinel=object();digest=hashlib.sha256()
        process=subprocess.Popen([args.duckdb,str(database),'-bail','-readonly','-csv','-noheader'],stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,encoding='utf-8')
        def expire():expired.set();process.kill()
        timer=threading.Timer(120,expire);timer.start()
        try:
            process.stdin.write(settings(folder,database)+query);process.stdin.close()
            for observed,wanted in zip_longest(csv.reader(process.stdout,strict=True),expected,fillvalue=sentinel):
                assert observed is not sentinel and wanted is not sentinel,'Private recency row count differs'
                assert len(observed)==3 and count<RECENCY_CAP
                actual=tuple(int(value) for value in observed)
                assert actual==wanted,'Private recency tuple differs; identifiers withheld'
                digest.update((json.dumps(actual,separators=(',',':'))+'\n').encode());count+=1
            assert process.wait(timeout=120)==0 and not expired.is_set()
        finally:
            timer.cancel()
            if process.poll() is None:process.kill();process.wait()
            process.stdout.close()
        observe(folder)
        return dict(rows=count,fields=3,sha256=digest.hexdigest()),round(time.perf_counter()-started,3)

    elapsed=[0,BOUNDARIES[0]-1,BOUNDARIES[0],BOUNDARIES[0]+1,BOUNDARIES[1]-1,
        BOUNDARIES[1],BOUNDARIES[1]+1,BOUNDARIES[2]-1,BOUNDARIES[2],BOUNDARIES[2]+1]
    rows=[];cases=[]
    for visitor,delta in enumerate(elapsed,1):
        stamp=REFERENCE_MS-(BOUNDARIES[0]+1 if visitor==2 else delta)
        rows.append((visitor,1,100+visitor,stamp-1000,stamp,2))
    rows.append((2,1,999,REFERENCE_MS-BOUNDARIES[1],REFERENCE_MS-elapsed[1],2));rows.sort()
    stats,recencies,expected=recency_reference(rows)
    assert [row[2] for row in recencies]==elapsed and [row['visitor_ids'] for row in expected]==[2,3,3,2,10]
    assert expected[0]['median_recency_days']==Fraction(BOUNDARIES[0]-1,2*DAY_MS)
    assert expected[1]['median_recency_days']==Fraction(BOUNDARIES[0]+1,DAY_MS)
    assert expected[4]['median_recency_days']==Fraction(2*BOUNDARIES[1]-1,2*DAY_MS)
    with tempfile.TemporaryDirectory(prefix='rr-visitor-recency-fixture-',dir=tmp_root) as temporary:
        folder,database=Path(temporary),Path(temporary)/'fixture.duckdb';load_memberships(folder,database,rows)
        query=adjusted(sql,stats);before_db=source_reference.sha256(database)
        report,_=execute(folder,database,query,readonly=True);compare_report(report,expected)
        proof,_=compare_recencies(folder,database,recency_stream_sql(query),iter(recencies))
        assert proof['rows']==10 and source_reference.sha256(database)==before_db
        mutations=[('NULL','UPDATE rr_mart.transaction_basket_items SET last_timestamp_ms=NULL WHERE visitorid=1;'),
            ('future',f'UPDATE rr_mart.transaction_basket_items SET last_timestamp_ms={REFERENCE_MS+1} WHERE visitorid=1;'),
            ('wrong_type','ALTER TABLE rr_mart.transaction_basket_items ALTER COLUMN last_timestamp_ms TYPE VARCHAR;')]
        for label,mutation in mutations:
            blocked,_=execute(folder,database,'BEGIN;'+mutation+query+'ROLLBACK;')
            assert [row['recency_band'] for row in blocked]==BANDS
            assert all(row['check_status']=='BLOCKED' and all(row[key] is None for key in OUTPUT[1:-1]) for row in blocked),label
        assert query.count("(1,'R_LT_7D',0::BIGINT,604800000::BIGINT)")==1
        wrong=query.replace("(1,'R_LT_7D',0::BIGINT,604800000::BIGINT)","(1,'R_LT_7D',0::BIGINT,604800001::BIGINT)")
        failed,_=execute(folder,database,wrong,readonly=True)
        assert [row['recency_band'] for row in failed]==BANDS and all(row['check_status']=='FAIL' and all(row[key] is None for key in OUTPUT[1:-1]) for row in failed)
        cases.append(dict(case='exact_7_30_60_days_plus_minus_1ms_all_member_MAX_last_timestamp_odd_even_and_TOTAL_medians_invalid_time_BLOCKED_overlap_FAIL',passed=True,
            memberships=11,candidate_baskets=10,visitor_ids=10,complete_recency_fields=3,invalid_control_subcases=4))
    assert not folder.exists()
    with tempfile.TemporaryDirectory(prefix='rr-visitor-recency-zero-',dir=tmp_root) as temporary:
        folder,database=Path(temporary),Path(temporary)/'fixture.duckdb';stamp=REFERENCE_MS-10*DAY_MS
        single_rows=[(7,1,10,stamp-1000,stamp,1)];single_stats,single_recencies,single_expected=recency_reference(single_rows)
        load_memberships(folder,database,single_rows);query=adjusted(sql,single_stats)
        report,_=execute(folder,database,query,readonly=True);compare_report(report,single_expected)
        proof,_=compare_recencies(folder,database,recency_stream_sql(query),iter(single_recencies));assert proof['rows']==1
        assert all(report[index]['visitor_ids']==0 and all(report[index][key] is None for key in ['min_recency_days','median_recency_days','max_recency_days']) for index in [0,2,3])
        cases.append(dict(case='zero_bands_visible_zero_share_three_NULL_stats_TOTAL_direct',passed=True,empty_bands=3))
    assert not folder.exists()
    print(json.dumps({'fixture_families_passed':len(cases),'invalid_control_subcases':4}),flush=True)
    if args.fixtures_only:return

    before={'events.csv':staging.snapshot(source)}
    assert all(before['events.csv'][key]==source_audit['source_before']['events.csv'][key]==source_audit['source_after']['events.csv'][key]
        for key in ['size_bytes','modified_time_ns','sha256'])
    historical={str(p.relative_to(root)):source_reference.sha256(p) for p in (root/'data').glob('*preflight.json') if p.resolve()!=output.resolve()}
    assert len(historical)==84
    started=time.perf_counter();rows,source_counts=counts.scan_source(source);source_seconds=round(time.perf_counter()-started,3)
    assert source_counts==old['independent_python_source_counts'] and len(rows)==22323
    input_hash=counts.canonical_hash(rows);assert input_hash==old['accepted_SQL79_membership_sha256']
    started=time.perf_counter();stats,recencies,expected=recency_reference(rows);reference_seconds=round(time.perf_counter()-started,3)
    assert [stats[name] for name in ['memberships','baskets','single_baskets','multi_baskets','max_items','visitor_ids']]==[22323,17672,15029,2643,31,11719]
    print(json.dumps({'phase':'single canonical parse and accepted membership fingerprint matched'}),flush=True)
    with tempfile.TemporaryDirectory(prefix='rr-visitor-recency-real-',dir=tmp_root) as temporary:
        folder,database=Path(temporary),Path(temporary)/'preflight.duckdb'
        readback_hash,load_seconds,csv_bytes=load_memberships(folder,database,rows);assert readback_hash==input_hash
        database_before=source_reference.sha256(database)
        report,query_seconds=execute(folder,database,sql,readonly=True);compare_report(report,expected)
        assert Counter(row['check_status'] for row in report)==Counter(PASS=5)
        proof,stream_seconds=compare_recencies(folder,database,stream_sql,iter(recencies))
        assert proof['rows']==11719 and proof['sha256']==counts.canonical_hash(recencies)
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
        accepted_original_five_field_proof_reused=True,accepted_SQL64_SQL70_endpoint_provenance_verified=True,
        endpoint_provenance=[time_path,time_acceptance_path,overview_path,overview_acceptance_path],
        reference_endpoint_ms=REFERENCE_MS,reference_endpoint_utc=REFERENCE_UTC,source_lower_timestamp_ms=SOURCE_MIN_MS,
        reference_endpoint_scope='Frozen global observed event endpoint, not a confirmed collection cutoff.',reference_is_today=False,reference_is_latest_transaction_timestamp=False,
        earlier_transaction_endpoint_utc_from_accepted_SQL70=transaction_end,
        original_five_field_occurrence_comparison_rerun=False,original_event_external_sort_rerun=False,
        SQL54_rerun=False,SQL63_rerun=False,SQL64_rerun=False,SQL70_rerun=False,SQL79_rerun=False,SQL80_rerun=False,SQL81_rerun=False,SQL82_rerun=False,SQL83_rerun=False,SQL84_rerun=False,SQL85_rerun=False,
        old_frequency_pair_visitor_concentration_or_month_streams_recompared=False,
        stored_last_timestamp_ms_in_query_readset=True,stored_first_timestamp_and_source_count_in_query_readset=False,
        property_files_read=False,category_csv_read=False,enriched_fact_read=False,learner_database_opened=False,query_read_only=True,private_visitor_recency_stream_read_only=True,
        real_source_attempts=1,real_event_csv_parse_passes=1,real_cli_phases=3,real_private_input_load_executions=1,real_analysis_script_executions=1,real_private_visitor_recency_stream_executions=1,
        report_rows=5,report_columns=7,output_columns=OUTPUT,checks_passed=5,fail_rows=0,blocked_rows=0,results=report,
        report_sha256=counts.canonical_hash([[row[key] for key in OUTPUT] for row in report]),
        report_fingerprint_contract='SHA-256 of actual returned compact JSON arrays in output-column order followed by LF; fixed bands and NULLs preserved. Rounded shares/day stats compared within stated tolerance.',
        independent_python_source_counts=source_counts,independent_python_recency_scope_counts=stats,independent_python_report_matched_with_display_tolerance=True,
        band_labels_counts_NULLs_and_status_compared_exactly=True,report_display_absolute_tolerance=DISPLAY_TOL,report_display_decimal_places=6,
        independent_visitor_recency_rows_compared=proof['rows'],independent_visitor_recency_fields_compared=3,private_visitor_recency_columns=RECENCY_FIELDS,
        independent_visitor_recencies_all_integer_fields_exact=True,independent_visitor_recency_stream_sha256=proof['sha256'],independent_visitor_recencies_all_matched=True,
        visitor_recency_stream_sql_sha256=hashlib.sha256(stream_sql.encode()).hexdigest(),candidate_basket_key=['visitorid','transactionid'],
        last_transaction_MAX_across_all_memberships=True,integer_elapsed_ms_before_day_display_and_classification=True,
        recency_day_ms=DAY_MS,raw_ms_boundaries=BOUNDARIES,recency_bands=BANDS,band_intervals_half_open=True,
        band_visitor_counts_sum=11719,visitor_share_denominator=11719,even_medians_use_exact_central_mean=True,TOTAL_median_direct_over_all_visitors=True,
        population='Transaction-recorded visitor IDs only; not all event visitors or non-purchasers.',all_event_visitors_in_denominator=False,nontransaction_visitors_included=False,
        frequency_recomputed=False,combined_RF_scores_or_segments_completed=False,monetary_analysis_performed=False,band_cutoffs_optimized=False,
        churn_retention_loyalty_or_verified_people_orders_claimed=False,finite_window_and_unequal_visitor_exposure_acknowledged=True,
        retained_transaction_occurrences=source_counts['transaction'],transaction_occurrence_cap=counts.TRANSACTION_CAP,visitor_recency_row_cap=RECENCY_CAP,
        private_database_sha256_before_readonly=database_before,private_database_sha256_after_readonly=database_after,private_database_bytes_unchanged=True,
        fixture_case_count=len(cases),fixture_cases=cases,invalid_control_fixture_subcases=4,
        exact_boundary_plus_minus_1ms_fixture_verified=True,all_member_last_MAX_and_first_time_distinction_verified=True,
        odd_even_and_TOTAL_median_fixture_verified=True,zero_bands_three_NULL_stats_fixture_verified=True,
        invalid_timestamp_BLOCKED_verified=True,overlapping_ms_band_partition_FAIL_verified=True,
        preflight_settings=dict(threads=2,memory_limit='1GB',max_temp_directory_size='2GB',timeout_seconds_per_cli_phase=120,
            transaction_occurrence_cap=counts.TRANSACTION_CAP,visitor_recency_row_cap=RECENCY_CAP,
            minimum_free_bytes=8*1024**3,private_directory_budget_bytes=7*1024**3),
        private_input_csv_bytes=csv_bytes,private_database_bytes_before_cleanup=database_bytes,
        largest_private_directory_bytes_observed_after_phase=max(sizes),workspace_free_bytes_before=free_before,workspace_free_bytes_after=shutil.disk_usage(tmp_root).free,
        temporary_databases_and_spills_removed=True,private_membership_csv_removed=True,historical_preflight_files_unchanged=len(historical),
        historical_comparison_or_analysis_suites_rerun=False,source_records_or_identifiers_uploaded_or_logged=False,raw_visitor_identifiers_published=False,
        elapsed_python_source_scan_reconstruction_seconds=source_seconds,elapsed_python_recency_reference_seconds=reference_seconds,
        elapsed_private_input_load_readback_seconds=load_seconds,elapsed_readonly_recency_report_seconds=query_seconds,elapsed_private_visitor_recency_stream_seconds=stream_seconds,
        timing_scope='One canonical parse and per-visitor last-timestamp MAX; small private load/readback, R report and complete integer R stream. Hash reads separate; no F/pair/month proof reruns.',
        scope='Assistant SQL86 preparation passed; learner execution pending. R-only elapsed-time baseline at the frozen global observed endpoint for transaction-recorded IDs; not churn, retention, monetary analysis or completed RF segmentation.')
    output.write_text(json.dumps(evidence,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps({'report_rows':5,'checks_passed':5,'visitor_recency_rows_compared':proof['rows'],
        'visitor_recency_fields':3,'report_sha256':evidence['report_sha256']}),flush=True)


if __name__=='__main__':main()
