"""Validate a descriptive R x F matrix with a new exact per-visitor reference."""
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
from collections import Counter, defaultdict
from datetime import datetime, timezone
from fractions import Fraction
from itertools import zip_longest
from pathlib import Path

import preflight_retailrocket_visitor_purchase_recency as previous

counts=previous.counts
model=previous.model
staging=previous.staging
source_reference=previous.source_reference
READSET=['visitorid','transactionid','itemid','last_timestamp_ms']
DISPLAY_TOL=previous.DISPLAY_TOL
CONTRACT_SHA='383cdaf6ed6e0555445eff9e65a53db334933022de4b8500c8ab0293d0f7f350'
REFERENCE_MS=1442545187788
REFERENCE_UTC='2015-09-18T02:59:47.788000Z'
SOURCE_MIN_MS=1430622004384
DAY_MS=86400000
BOUNDARIES=[7*DAY_MS,30*DAY_MS,60*DAY_MS]
OUTPUT=['recency_band','frequency_band','visitor_ids','visitor_share_pct','candidate_baskets','basket_share_pct','check_status']
RF_FIELDS=['visitorid','basket_count','last_transaction_ms','recency_ms','recency_band','frequency_band']
R_BANDS=['R_LT_7D','R_7_TO_LT_30D','R_30_TO_LT_60D','R_GE_60D']
F_BANDS=['F_1','F_2','F_3_4','F_5_PLUS']
LABELS=[(r,f) for r in R_BANDS for f in F_BANDS]+[('TOTAL','TOTAL')]
RF_CAP=100000


def rf_reference(rows):
    assert len({row[:3] for row in rows})==len(rows)
    basket_items=Counter(row[:2] for row in rows);visitor_baskets=defaultdict(set);latest={}
    for row in rows:
        assert isinstance(row[4],int) and SOURCE_MIN_MS<=row[4]<=REFERENCE_MS
        visitor_baskets[row[0]].add(row[:2])
        latest[row[0]]=max(latest.get(row[0],SOURCE_MIN_MS),row[4])
    assert 0<len(latest)<=RF_CAP
    stream=[]
    for visitor in sorted(latest):
        frequency=len(visitor_baskets[visitor]);stamp=latest[visitor];recency=REFERENCE_MS-stamp
        r_label=R_BANDS[sum(recency>=boundary for boundary in BOUNDARIES)]
        f_label='F_1' if frequency==1 else 'F_2' if frequency==2 else 'F_3_4' if frequency<=4 else 'F_5_PLUS'
        stream.append((visitor,frequency,stamp,recency,r_label,f_label))
    stats=dict(memberships=len(rows),baskets=len(basket_items),single_baskets=sum(value==1 for value in basket_items.values()),
        multi_baskets=sum(value>1 for value in basket_items.values()),max_items=max(basket_items.values(),default=None),visitor_ids=len(latest))
    cells={labels:[0,0] for labels in LABELS[:-1]};direct_r={label:[0,0] for label in R_BANDS};direct_f={label:[0,0] for label in F_BANDS}
    for visitor,frequency,stamp,recency,r_label,f_label in stream:
        assert 0<=recency<=REFERENCE_MS-SOURCE_MIN_MS and stamp+recency==REFERENCE_MS
        for target in [cells[(r_label,f_label)],direct_r[r_label],direct_f[f_label]]:
            target[0]+=1;target[1]+=frequency
    cells[('TOTAL','TOTAL')]=[len(stream),sum(row[1] for row in stream)]
    assert cells[('TOTAL','TOTAL')]==[stats['visitor_ids'],stats['baskets']]
    report=[dict(zip(OUTPUT,[r,f,cells[(r,f)][0],Fraction(100*cells[(r,f)][0],stats['visitor_ids']),
        cells[(r,f)][1],Fraction(100*cells[(r,f)][1],stats['baskets']),'PASS'])) for r,f in LABELS]
    matrix_r={label:[sum(cells[(label,f)][index] for f in F_BANDS) for index in [0,1]] for label in R_BANDS}
    matrix_f={label:[sum(cells[(r,label)][index] for r in R_BANDS) for index in [0,1]] for label in F_BANDS}
    assert matrix_r==direct_r and matrix_f==direct_f
    assert [sum(value[index] for key,value in cells.items() if key!=('TOTAL','TOTAL')) for index in [0,1]]==[stats['visitor_ids'],stats['baskets']]
    return stats,stream,report,dict(R=direct_r,F=direct_f)


def compare_report(observed,expected):
    assert len(observed)==len(expected)==17
    for actual,wanted in zip(observed,expected):
        assert list(actual)==OUTPUT
        for key in OUTPUT:
            if key not in ['visitor_share_pct','basket_share_pct']:
                assert actual[key]==wanted[key],'Private RF label/count/status differs; values withheld'
            else:
                assert math.isfinite(actual[key]) and abs(actual[key]-float(wanted[key]))<=DISPLAY_TOL,'Private RF display differs; values withheld'
                assert abs(actual[key]*1e6-round(actual[key]*1e6))<=1e-5


def adjusted(sql,stats):
    query=counts.adjusted(sql,stats)
    query,n=re.subn(r'\b[0-9]+::BIGINT AS expected_visitor_ids\b',f"{stats['visitor_ids']}::BIGINT AS expected_visitor_ids",query);assert n==1
    return query


def rf_stream_sql(sql):
    assert sql.count('), rf_health AS (')==1
    return sql.split('), rf_health AS (',1)[0]+')\nSELECT '+','.join(RF_FIELDS)+' FROM visitor_rf ORDER BY visitorid;'


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--duckdb',required=True)
    parser.add_argument('--output',required=True);parser.add_argument('--fixtures-only',action='store_true');args=parser.parse_args()
    root=Path(__file__).resolve().parents[1];output=(root/args.output).resolve()
    script_path='sql/87_analyze_retailrocket_visitor_rf_segments.sql'
    validator_path='validation/preflight_retailrocket_visitor_rf_segments.py';method_path='docs/RETAILROCKET_VISITOR_RF_SEGMENTS_VALIDATION.md'
    assert output==(root/'data/retailrocket_visitor_rf_segments_preflight.json').resolve()
    old_path='data/retailrocket_visitor_purchase_recency_preflight.json';accepted_path='data/retailrocket_visitor_purchase_recency_learner_acceptance.json'
    old=json.loads((root/old_path).read_text(encoding='utf-8'));accepted=json.loads((root/accepted_path).read_text(encoding='utf-8'))
    assert accepted['acceptance_status']=='accepted' and accepted['script']=='sql/86_analyze_retailrocket_visitor_purchase_recency.sql'
    assert accepted['report_sha256']==old['report_sha256'] and accepted['assistant_preflight_sha256']==source_reference.sha256(root/old_path)
    assert old['reference_endpoint_ms']==REFERENCE_MS and old['reference_endpoint_utc']==REFERENCE_UTC
    assert old['source_lower_timestamp_ms']==SOURCE_MIN_MS and old['accepted_SQL64_SQL70_endpoint_provenance_verified']
    frequency_path='data/retailrocket_visitor_purchase_frequency_preflight.json'
    frequency_accepted_path='data/retailrocket_visitor_purchase_frequency_learner_acceptance.json'
    frequency=json.loads((root/frequency_path).read_text(encoding='utf-8'));frequency_accepted=json.loads((root/frequency_accepted_path).read_text(encoding='utf-8'))
    assert frequency_accepted['acceptance_status']=='accepted' and frequency_accepted['script']=='sql/85_analyze_retailrocket_visitor_purchase_frequency.sql'
    assert frequency_accepted['report_sha256']==frequency['report_sha256'] and frequency_accepted['assistant_preflight_sha256']==source_reference.sha256(root/frequency_path)
    for proof in [old,accepted]:assert next(row['visitor_ids'] for row in proof['results'] if row['recency_band']=='TOTAL')==11719
    for proof in [frequency,frequency_accepted]:
        total=next(row for row in proof['results'] if row['frequency_band']=='TOTAL');assert [total['visitor_ids'],total['candidate_baskets']]==[11719,17672]
    deps=list(old['code_and_dependency_sha256'])+[script_path,validator_path,old_path,accepted_path,
        'docs/RETAILROCKET_VISITOR_PURCHASE_RECENCY_VALIDATION.md',frequency_path,frequency_accepted_path]
    hashes={name:source_reference.sha256(root/name) for name in deps}
    assert all(hashes[name]==digest for name,digest in old['code_and_dependency_sha256'].items())
    assert hashes[accepted_path]=='030532186f48942a67dc1047518477f23d3675d499858d81c9f5acd247830270'
    assert hashes['docs/RETAILROCKET_VISITOR_PURCHASE_RECENCY_VALIDATION.md']=='8fd95a47fba2083cfa3be82cf5120aeefe20c4f12a38c177edd5cb3ed92da520'
    contract=(root/method_path).read_bytes().split(b'\n## Executed results\n',1)[0]
    assert hashlib.sha256(contract).hexdigest()==CONTRACT_SHA
    sql=(root/script_path).read_text(encoding='utf-8');clean=re.sub(r'--[^\n]*','',sql)
    assert clean.lstrip().startswith('WITH ') and not re.search(r'\b(CREATE|INSERT|UPDATE|DELETE|DROP|ALTER|COPY|SET|ATTACH|DETACH|LIMIT|CURRENT_DATE|CURRENT_TIMESTAMP|NOW)\b',clean,re.I)
    assert 'last_timestamp_ms' in clean and all(name not in clean for name in ['first_timestamp_ms','source_event_rows','rr_stg','rr_core','categoryid','available','pair_counts','selected_pairs'])
    stream_sql=rf_stream_sql(sql)
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
    def compare_rf(folder,database,query,expected):
        started=time.perf_counter();expired=threading.Event();count=0;sentinel=object();digest=hashlib.sha256()
        process=subprocess.Popen([args.duckdb,str(database),'-bail','-readonly','-csv','-noheader'],stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,encoding='utf-8')
        def expire():expired.set();process.kill()
        timer=threading.Timer(120,expire);timer.start()
        try:
            process.stdin.write(settings(folder,database)+query);process.stdin.close()
            for observed,wanted in zip_longest(csv.reader(process.stdout,strict=True),expected,fillvalue=sentinel):
                assert observed is not sentinel and wanted is not sentinel,'Private RF row count differs'
                assert len(observed)==6 and count<RF_CAP
                actual=tuple(int(value) for value in observed[:4])+tuple(observed[4:])
                assert actual==wanted,'Private RF tuple differs; identifiers withheld'
                digest.update((json.dumps(actual,separators=(',',':'))+'\n').encode());count+=1
            assert process.wait(timeout=120)==0 and not expired.is_set()
        finally:
            timer.cancel()
            if process.poll() is None:process.kill();process.wait()
            process.stdout.close()
        observe(folder)
        return dict(rows=count,fields=6,sha256=digest.hexdigest()),round(time.perf_counter()-started,3)

    elapsed=[0,BOUNDARIES[0]-1,BOUNDARIES[0],BOUNDARIES[0]+1,BOUNDARIES[1]-1,
        BOUNDARIES[1],BOUNDARIES[1]+1,BOUNDARIES[2]-1,BOUNDARIES[2],BOUNDARIES[2]+1]
    frequencies=[1,2,3,4,5,1,2,3,4,5];rows=[];cases=[]
    for visitor,(delta,number) in enumerate(zip(elapsed,frequencies),1):
        base=REFERENCE_MS-(BOUNDARIES[0]+1 if visitor==2 else delta)
        for basket in range(1,number+1):
            stamp=base-(basket-1)*1000;rows.append((visitor,basket,100+visitor,stamp-1000,stamp,7))
    rows.append((2,1,999,REFERENCE_MS-BOUNDARIES[1],REFERENCE_MS-elapsed[1],7));rows.sort()
    stats,records,expected,marginals=rf_reference(rows)
    assert [row[1] for row in records]==frequencies and [row[3] for row in records]==elapsed
    assert [stats[name] for name in ['memberships','baskets','single_baskets','multi_baskets','max_items','visitor_ids']]==[31,30,29,1,2,10]
    assert [value[0] for value in marginals['R'].values()]==[2,3,3,2]
    assert marginals['F']==dict(F_1=[2,2],F_2=[2,4],F_3_4=[4,14],F_5_PLUS=[2,10])
    zero_cells=sum(row['visitor_ids']==0 for row in expected[:-1]);assert zero_cells==7
    with tempfile.TemporaryDirectory(prefix='rr-visitor-rf-fixture-',dir=tmp_root) as temporary:
        folder,database=Path(temporary),Path(temporary)/'fixture.duckdb';load_memberships(folder,database,rows)
        query=adjusted(sql,stats);before_db=source_reference.sha256(database)
        report,_=execute(folder,database,query,readonly=True);compare_report(report,expected)
        proof,_=compare_rf(folder,database,rf_stream_sql(query),iter(records))
        assert proof['rows']==10 and source_reference.sha256(database)==before_db
        assert all(row['candidate_baskets']==row['visitor_share_pct']==row['basket_share_pct']==0 for row in report[:-1] if row['visitor_ids']==0)
        mutations=[('NULL','UPDATE rr_mart.transaction_basket_items SET last_timestamp_ms=NULL WHERE visitorid=1;'),
            ('future',f'UPDATE rr_mart.transaction_basket_items SET last_timestamp_ms={REFERENCE_MS+1} WHERE visitorid=1;'),
            ('wrong_type','ALTER TABLE rr_mart.transaction_basket_items ALTER COLUMN last_timestamp_ms TYPE VARCHAR;')]
        for label,mutation in mutations:
            blocked,_=execute(folder,database,'BEGIN;'+mutation+query+'ROLLBACK;')
            assert [(row['recency_band'],row['frequency_band']) for row in blocked]==LABELS
            assert all(row['check_status']=='BLOCKED' and all(row[key] is None for key in OUTPUT[2:-1]) for row in blocked),label
        overlaps=[("(1,'R_LT_7D',0::BIGINT,604800000::BIGINT)","(1,'R_LT_7D',0::BIGINT,604800001::BIGINT)"),
            ("(1,'F_1',1::BIGINT,1::BIGINT)","(1,'F_1',1::BIGINT,2::BIGINT)")]
        for original,replacement in overlaps:
            assert query.count(original)==1
            failed,_=execute(folder,database,query.replace(original,replacement),readonly=True)
            assert [(row['recency_band'],row['frequency_band']) for row in failed]==LABELS
            assert all(row['check_status']=='FAIL' and all(row[key] is None for key in OUTPUT[2:-1]) for row in failed)
        cases.append(dict(case='RF_boundaries_full_composite_baskets_all_member_MAX_dense_zero_cells_NULL_future_type_BLOCKED_R_and_F_overlap_FAIL',passed=True,
            memberships=31,candidate_baskets=30,visitor_ids=10,private_RF_fields=6,empty_cells=zero_cells,invalid_control_subcases=5))
    assert not folder.exists()
    print(json.dumps({'fixture_families_passed':len(cases),'invalid_control_subcases':5}),flush=True)
    if args.fixtures_only:return

    before={'events.csv':staging.snapshot(source)}
    assert all(before['events.csv'][key]==source_audit['source_before']['events.csv'][key]==source_audit['source_after']['events.csv'][key]
        for key in ['size_bytes','modified_time_ns','sha256'])
    historical={str(p.relative_to(root)):source_reference.sha256(p) for p in (root/'data').glob('*preflight.json') if p.resolve()!=output.resolve()}
    assert len(historical)==85
    started=time.perf_counter();rows,source_counts=counts.scan_source(source);source_seconds=round(time.perf_counter()-started,3)
    assert source_counts==old['independent_python_source_counts'] and len(rows)==22323
    input_hash=counts.canonical_hash(rows);assert input_hash==old['accepted_SQL79_membership_sha256']
    started=time.perf_counter();stats,records,expected,marginals=rf_reference(rows);reference_seconds=round(time.perf_counter()-started,3)
    assert [stats[name] for name in ['memberships','baskets','single_baskets','multi_baskets','max_items','visitor_ids']]==[22323,17672,15029,2643,31,11719]
    for proof in [frequency,frequency_accepted]:
        assert marginals['F']=={row['frequency_band']:[row['visitor_ids'],row['candidate_baskets']] for row in proof['results'] if row['frequency_band']!='TOTAL'}
    for proof in [old,accepted]:
        assert {label:value[0] for label,value in marginals['R'].items()}=={row['recency_band']:row['visitor_ids'] for row in proof['results'] if row['recency_band']!='TOTAL'}
    print(json.dumps({'phase':'single canonical parse, accepted memberships and accepted R/F aggregate marginals matched'}),flush=True)
    with tempfile.TemporaryDirectory(prefix='rr-visitor-rf-real-',dir=tmp_root) as temporary:
        folder,database=Path(temporary),Path(temporary)/'preflight.duckdb'
        readback_hash,load_seconds,csv_bytes=load_memberships(folder,database,rows);assert readback_hash==input_hash
        database_before=source_reference.sha256(database)
        report,query_seconds=execute(folder,database,sql,readonly=True);compare_report(report,expected)
        assert Counter(row['check_status'] for row in report)==Counter(PASS=17)
        proof,stream_seconds=compare_rf(folder,database,stream_sql,iter(records))
        assert proof['rows']==11719 and proof['sha256']==counts.canonical_hash(records)
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
        accepted_original_five_field_proof_reused=True,accepted_SQL86_fixed_endpoint_provenance_reused=True,
        accepted_SQL64_SQL70_endpoint_provenance_reused=True,reference_endpoint_ms=REFERENCE_MS,reference_endpoint_utc=REFERENCE_UTC,source_lower_timestamp_ms=SOURCE_MIN_MS,
        reference_endpoint_scope='Frozen global observed event endpoint, not a confirmed collection cutoff.',reference_is_today=False,reference_is_latest_transaction_timestamp=False,
        original_five_field_occurrence_comparison_rerun=False,original_event_external_sort_rerun=False,
        SQL54_rerun=False,SQL63_rerun=False,SQL64_rerun=False,SQL70_rerun=False,SQL79_rerun=False,SQL80_rerun=False,SQL81_rerun=False,SQL82_rerun=False,SQL83_rerun=False,SQL84_rerun=False,SQL85_rerun=False,SQL86_rerun=False,
        old_frequency_recency_pair_visitor_concentration_or_month_streams_recompared=False,
        stored_last_timestamp_ms_in_query_readset=True,stored_first_timestamp_and_source_count_in_query_readset=False,
        property_files_read=False,category_csv_read=False,enriched_fact_read=False,learner_database_opened=False,query_read_only=True,private_visitor_RF_stream_read_only=True,
        real_source_attempts=1,real_event_csv_parse_passes=1,real_cli_phases=3,real_private_input_load_executions=1,real_analysis_script_executions=1,real_private_visitor_RF_stream_executions=1,
        report_rows=17,report_columns=7,output_columns=OUTPUT,checks_passed=17,fail_rows=0,blocked_rows=0,results=report,
        report_sha256=counts.canonical_hash([[row[key] for key in OUTPUT] for row in report]),
        report_fingerprint_contract='SHA-256 of actual returned compact JSON arrays in output-column order followed by LF; dense R-major/F-minor cells and TOTAL preserved. Rounded shares use stated tolerance.',
        independent_python_source_counts=source_counts,independent_python_RF_scope_counts=stats,independent_python_report_matched_with_display_tolerance=True,
        band_labels_counts_and_status_compared_exactly=True,report_display_absolute_tolerance=DISPLAY_TOL,report_display_decimal_places=6,
        independent_visitor_RF_rows_compared=proof['rows'],independent_visitor_RF_fields_compared=6,private_visitor_RF_columns=RF_FIELDS,
        independent_visitor_RF_four_integer_fields_two_labels_exact=True,independent_visitor_RF_stream_sha256=proof['sha256'],independent_visitor_RF_all_matched=True,
        visitor_RF_stream_sql_sha256=hashlib.sha256(stream_sql.encode()).hexdigest(),candidate_basket_key=['visitorid','transactionid'],
        full_composite_basket_keys_counted_once=True,last_transaction_MAX_across_all_memberships=True,integer_elapsed_ms_before_classification=True,
        recency_day_ms=DAY_MS,raw_ms_boundaries=BOUNDARIES,recency_bands=R_BANDS,frequency_bands=F_BANDS,recency_band_intervals_half_open=True,
        dense_cells=16,dense_order='R major, F minor; then TOTAL/TOTAL',empty_cells=sum(row['visitor_ids']==0 for row in report[:-1]),
        matrix_visitor_sum=11719,matrix_candidate_basket_sum=17672,visitor_share_denominator=11719,basket_share_denominator=17672,
        cell_baskets_sum_full_window_visitor_frequency=True,cell_baskets_restricted_to_recency_interval=False,
        per_visitor_exactly_one_cell_verified=True,direct_new_R_and_F_marginals_matched_matrix=True,
        accepted_SQL85_frequency_marginal_counts_and_baskets_matched=True,accepted_SQL86_recency_marginal_counts_matched=True,
        prior_R_basket_marginals_claimed=False,prior_aggregate_artifacts_compared_without_query_rerun=True,
        population='Transaction-recorded visitor IDs only; not all event visitors or non-purchasers.',all_event_visitors_in_denominator=False,nontransaction_visitors_included=False,
        descriptive_RF_cross_tabulation_prepared=True,validated_RF_customer_value_or_response_segments_completed=False,
        monetary_analysis_performed=False,RFM_claimed=False,band_cutoffs_optimized=False,churn_retention_loyalty_or_verified_people_orders_claimed=False,
        finite_window_and_unequal_visitor_exposure_acknowledged=True,
        retained_transaction_occurrences=source_counts['transaction'],transaction_occurrence_cap=counts.TRANSACTION_CAP,visitor_RF_row_cap=RF_CAP,
        private_database_sha256_before_readonly=database_before,private_database_sha256_after_readonly=database_after,private_database_bytes_unchanged=True,
        fixture_case_count=len(cases),fixture_cases=cases,invalid_control_fixture_subcases=5,
        exact_recency_boundary_plus_minus_1ms_fixture_verified=True,frequency_1_2_3_4_5_boundaries_verified=True,
        all_member_last_MAX_and_composite_basket_grain_verified=True,dense_zero_cells_verified=True,
        invalid_timestamp_BLOCKED_verified=True,overlapping_R_and_F_partitions_FAIL_verified=True,
        preflight_settings=dict(threads=2,memory_limit='1GB',max_temp_directory_size='2GB',timeout_seconds_per_cli_phase=120,
            transaction_occurrence_cap=counts.TRANSACTION_CAP,visitor_RF_row_cap=RF_CAP,
            minimum_free_bytes=8*1024**3,private_directory_budget_bytes=7*1024**3),
        private_input_csv_bytes=csv_bytes,private_database_bytes_before_cleanup=database_bytes,
        largest_private_directory_bytes_observed_after_phase=max(sizes),workspace_free_bytes_before=free_before,workspace_free_bytes_after=shutil.disk_usage(tmp_root).free,
        temporary_databases_and_spills_removed=True,private_membership_csv_removed=True,historical_preflight_files_unchanged=len(historical),
        historical_comparison_or_analysis_suites_rerun=False,source_records_or_identifiers_uploaded_or_logged=False,raw_visitor_identifiers_published=False,
        elapsed_python_source_scan_reconstruction_seconds=source_seconds,elapsed_python_RF_reference_seconds=reference_seconds,
        elapsed_private_input_load_readback_seconds=load_seconds,elapsed_readonly_RF_report_seconds=query_seconds,elapsed_private_visitor_RF_stream_seconds=stream_seconds,
        timing_scope='One canonical parse and new set/MAX RF reference; small private load/readback, matrix report and complete exact RF stream. Hash reads separate; old result streams not repeated.',
        scope='Assistant SQL87 preparation passed; learner execution pending. Descriptive RF cross-tabulation at the frozen global observed endpoint for transaction-recorded IDs; not churn, monetary RFM, lifetime value or validated customer-response segmentation.')
    output.write_text(json.dumps(evidence,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps({'report_rows':17,'checks_passed':17,'visitor_RF_rows_compared':proof['rows'],
        'visitor_RF_fields':6,'report_sha256':evidence['report_sha256']}),flush=True)


if __name__=='__main__':main()
