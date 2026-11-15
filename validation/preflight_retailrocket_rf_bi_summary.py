"""Validate one-time materialization of an additive sixteen-cell R/F BI summary."""
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

import preflight_retailrocket_rf_basket_concentration as previous

counts=previous.counts
model=previous.model
staging=previous.staging
source_reference=previous.source_reference
READSET=['visitorid','transactionid','itemid','last_timestamp_ms']
CONTRACT_SHA='ddc3ba182a31aa544ddfe9f344240eefa380ea26fc31df94231274afdbf18451'
REFERENCE_MS=1442545187788
REFERENCE_UTC='2015-09-18T02:59:47.788000Z'
SOURCE_MIN_MS=1430622004384
DAY_MS=86400000
BOUNDARIES=[7*DAY_MS,30*DAY_MS,60*DAY_MS]
OUTPUT=['check_order','check_name','actual','expected','status']
TABLE_FIELDS=['reference_timestamp_ms','recency_order','recency_band','frequency_order','frequency_band','visitor_ids','candidate_baskets']
TABLE_TYPES=['BIGINT','BIGINT','VARCHAR','BIGINT','VARCHAR','BIGINT','BIGINT']
R_BANDS=['R_LT_7D','R_7_TO_LT_30D','R_30_TO_LT_60D','R_GE_60D']
F_BANDS=['F_1','F_2','F_3_4','F_5_PLUS']
VISITOR_CAP=100000
MARKER='-- CHECKS: if the target already exists, run only the read-only query below.\n'
TABLE_QUERY='SELECT '+','.join(TABLE_FIELDS)+' FROM rr_bi.rf_segment_summary ORDER BY reference_timestamp_ms,recency_order,frequency_order;'
CHECKS=['summary_rows','column_count','schema_mismatch','distinct_rf_keys','missing_required_rows','negative_count_rows',
 'invalid_band_order_rows','reference_mismatch_rows','distinct_recency_orders','distinct_frequency_orders','visitor_ids_total',
 'candidate_baskets_total','total_label_rows','duplicate_key_surplus','source_membership_rows','source_contract_violations',
 'source_rf_contract_violations','expected_only_rows','summary_only_rows','cell_count_inconsistency_rows']


def summary_reference(rows):
    assert len({row[:3] for row in rows})==len(rows)
    basket_items=Counter(row[:2] for row in rows);visitor_baskets=defaultdict(set);latest={}
    for row in rows:
        assert isinstance(row[4],int) and SOURCE_MIN_MS<=row[4]<=REFERENCE_MS
        visitor_baskets[row[0]].add(row[:2]);latest[row[0]]=max(latest.get(row[0],SOURCE_MIN_MS),row[4])
    assert 0<len(latest)<=VISITOR_CAP
    rf=[];cells={(r,f):[0,0] for r in R_BANDS for f in F_BANDS}
    for visitor in sorted(latest):
        frequency=len(visitor_baskets[visitor]);stamp=latest[visitor];recency=REFERENCE_MS-stamp
        r_label=R_BANDS[sum(recency>=boundary for boundary in BOUNDARIES)]
        f_label='F_1' if frequency==1 else 'F_2' if frequency==2 else 'F_3_4' if frequency<=4 else 'F_5_PLUS'
        assert 0<=recency<=REFERENCE_MS-SOURCE_MIN_MS and recency+stamp==REFERENCE_MS
        rf.append((visitor,frequency,stamp,recency,r_label,f_label))
        cells[(r_label,f_label)][0]+=1;cells[(r_label,f_label)][1]+=frequency
    stats=dict(memberships=len(rows),baskets=len(basket_items),single_baskets=sum(value==1 for value in basket_items.values()),
        multi_baskets=sum(value>1 for value in basket_items.values()),max_items=max(basket_items.values(),default=None),visitor_ids=len(latest))
    table=[(REFERENCE_MS,ri,r,fi,f,*cells[(r,f)]) for ri,r in enumerate(R_BANDS,1) for fi,f in enumerate(F_BANDS,1)]
    assert len(table)==16 and sum(row[5] for row in table)==stats['visitor_ids'] and sum(row[6] for row in table)==stats['baskets']
    values=[16,7,0,16,0,0,0,0,4,4,stats['visitor_ids'],stats['baskets'],0,0,stats['memberships'],0,0,0,0,0]
    audit=[dict(zip(OUTPUT,[i,name,str(value),str(value),'PASS'])) for i,(name,value) in enumerate(zip(CHECKS,values),1)]
    return stats,table,audit,counts.canonical_hash(rf)


def adjusted(sql,stats):
    for name,key in [('expected_memberships','memberships'),('expected_baskets','baskets'),('expected_single_baskets','single_baskets'),
        ('expected_multi_baskets','multi_baskets'),('expected_max_items','max_items'),('expected_visitor_ids','visitor_ids')]:
        sql,n=re.subn(r'\b[0-9]+::BIGINT AS '+name+r'\b',f'{stats[key]}::BIGINT AS {name}',sql);assert n==2
    return sql


def compare_audit(observed,expected):
    assert len(observed)==len(expected)==20
    assert all(list(row)==OUTPUT for row in observed)
    assert observed==expected,'Private BI summary audit differs; details withheld'


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--duckdb',required=True)
    parser.add_argument('--output',required=True);args=parser.parse_args()
    root=Path(__file__).resolve().parents[1];output=(root/args.output).resolve()
    script_path='sql/89_build_retailrocket_rf_bi_summary.sql'
    validator_path='validation/preflight_retailrocket_rf_bi_summary.py';method_path='docs/RETAILROCKET_RF_BI_SUMMARY_VALIDATION.md'
    assert output==(root/'data/retailrocket_rf_bi_summary_preflight.json').resolve()
    old_path='data/retailrocket_rf_basket_concentration_preflight.json';accepted_path='data/retailrocket_rf_basket_concentration_learner_acceptance.json'
    old=json.loads((root/old_path).read_text(encoding='utf-8'));accepted=json.loads((root/accepted_path).read_text(encoding='utf-8'))
    assert accepted['acceptance_status']=='accepted' and accepted['script']=='sql/88_analyze_retailrocket_rf_basket_concentration.sql'
    assert accepted['report_sha256']==old['report_sha256'] and accepted['assistant_preflight_sha256']==source_reference.sha256(root/old_path)
    assert old['reference_endpoint_ms']==REFERENCE_MS and old['reference_endpoint_utc']==REFERENCE_UTC
    assert old['source_lower_timestamp_ms']==SOURCE_MIN_MS and old['accepted_fixed_endpoint_provenance_reused']
    rf_path='data/retailrocket_visitor_rf_segments_preflight.json';rf_accept_path='data/retailrocket_visitor_rf_segments_learner_acceptance.json'
    rf_proof=json.loads((root/rf_path).read_text(encoding='utf-8'));rf_accepted=json.loads((root/rf_accept_path).read_text(encoding='utf-8'))
    assert rf_accepted['acceptance_status']=='accepted' and rf_accepted['report_sha256']==rf_proof['report_sha256']
    assert rf_accepted['assistant_preflight_sha256']==source_reference.sha256(root/rf_path)
    assert rf_proof['independent_visitor_RF_stream_sha256']==old['accepted_SQL87_RF_fingerprint']
    deps=list(old['code_and_dependency_sha256'])+[script_path,validator_path,old_path,accepted_path,
        'docs/RETAILROCKET_RF_BASKET_CONCENTRATION_VALIDATION.md',rf_path,rf_accept_path]
    hashes={name:source_reference.sha256(root/name) for name in deps}
    assert all(hashes[name]==digest for name,digest in old['code_and_dependency_sha256'].items())
    assert hashes[accepted_path]=='8b27edf9c89c6dab780fd907198f62da720e8466d9d63dea29ea499f23a59ac7'
    assert hashes['docs/RETAILROCKET_RF_BASKET_CONCENTRATION_VALIDATION.md']=='846dccda763c166dbdbeadb92713e10ed029f7a04e298400fe747536562459aa'
    contract=(root/method_path).read_bytes().split(b'\n## Executed results\n',1)[0]
    assert hashlib.sha256(contract).hexdigest()==CONTRACT_SHA
    sql=(root/script_path).read_text(encoding='utf-8');assert sql.count(MARKER)==1
    build_sql,audit_sql=sql.split(MARKER);clean=re.sub(r'--[^\n]*','',sql)
    assert len(re.findall(r'\bCREATE SCHEMA IF NOT EXISTS rr_bi;',clean))==1
    assert len(re.findall(r'\bCREATE TABLE rr_bi.rf_segment_summary AS',clean))==1
    assert not re.search(r'\b(OR REPLACE|DROP|DELETE|UPDATE|INSERT|COPY|ALTER|ATTACH|DETACH|CURRENT_DATE|CURRENT_TIMESTAMP|NOW)\b',clean,re.I)
    assert audit_sql.lstrip().startswith('WITH ') and 'last_timestamp_ms' in clean
    assert all(name not in clean for name in ['first_timestamp_ms','source_event_rows','rr_stg','rr_core','categoryid','available','ROW_NUMBER','top1_','top5_','share_pct'])
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
    def read_summary(folder,database,expected):
        observed,seconds=execute(folder,database,TABLE_QUERY,readonly=True)
        assert len(observed)==16 and all(list(row)==TABLE_FIELDS for row in observed)
        actual=[]
        for row in observed:
            record=tuple(row[name] for name in TABLE_FIELDS)
            assert all(type(record[index]) is int for index in [0,1,3,5,6]) and all(type(record[index]) is str for index in [2,4])
            actual.append(record)
        assert actual==expected,'Private materialized BI table differs; rows withheld'
        return counts.canonical_hash(actual),seconds
    def expect_failure(folder,database,query,marker):
        run=subprocess.run([args.duckdb,str(database),'-bail','-json'],input=settings(folder,database)+query,
            text=True,encoding='utf-8',capture_output=True,timeout=120)
        assert run.returncode!=0 and marker in run.stderr.lower(),'Expected guarded build failure not observed; diagnostic withheld'
        observe(folder)
    def target_absent(folder,database):
        result,_=execute(folder,database,"SELECT COUNT(*) AS target_tables FROM information_schema.tables WHERE table_catalog=current_database() AND table_schema='rr_bi' AND table_name='rf_segment_summary';",readonly=True)
        assert result==[{'target_tables':0}],'Rejected build left a target'

    rows=[]
    for visitor,(days,frequency) in enumerate([(3,1),(15,2),(45,3),(90,5)],1):
        for basket in range(1,frequency+1):
            stamp=REFERENCE_MS-days*DAY_MS-(basket-1)*1000;rows.append((visitor,basket,100+visitor,stamp-1000,stamp,7))
    rows.append((1,1,999,REFERENCE_MS-4*DAY_MS,REFERENCE_MS-3*DAY_MS,7));rows.sort()
    stats,table,expected,rf_hash=summary_reference(rows)
    assert [stats[name] for name in ['memberships','baskets','single_baskets','multi_baskets','max_items','visitor_ids']]==[12,11,10,1,2,4]
    assert len(table)==16 and sum(row[5]==0 for row in table)==12
    query=adjusted(sql,stats);fixture_build,fixture_audit=query.split(MARKER);cases=[]
    with tempfile.TemporaryDirectory(prefix='rr-rf-bi-fixture-',dir=tmp_root) as temporary:
        folder,database=Path(temporary),Path(temporary)/'fixture.duckdb';load_memberships(folder,database,rows)
        report,_=execute(folder,database,query);compare_audit(report,expected)
        built_hash=source_reference.sha256(database);table_hash,_=read_summary(folder,database,table)
        assert source_reference.sha256(database)==built_hash
        expect_failure(folder,database,query,'already exists')
        after_refusal,_=read_summary(folder,database,table);assert after_refusal==table_hash
        assert source_reference.sha256(database)==built_hash,'Rejected existing-target build changed private database bytes'
        corrupted,_=execute(folder,database,'BEGIN;UPDATE rr_bi.rf_segment_summary SET visitor_ids=visitor_ids+1,candidate_baskets=candidate_baskets+1 WHERE recency_order=1 AND frequency_order=1;'+fixture_audit+'ROLLBACK;')
        assert len(corrupted)==20 and {row['check_name'] for row in corrupted if row['status']=='FAIL'}=={
            'visitor_ids_total','candidate_baskets_total','expected_only_rows','summary_only_rows'}
        type_error,_=execute(folder,database,'BEGIN;ALTER TABLE rr_bi.rf_segment_summary ALTER COLUMN visitor_ids TYPE VARCHAR;'+fixture_audit+'ROLLBACK;')
        assert len(type_error)==20 and {row['check_name'] for row in type_error if row['status']=='FAIL'}=={'schema_mismatch'}
        invalid_db=folder/'invalid.duckdb';load_memberships(folder,invalid_db,rows)
        execute(folder,invalid_db,'UPDATE rr_mart.transaction_basket_items SET last_timestamp_ms=NULL WHERE visitorid=1;')
        expect_failure(folder,invalid_db,query,'sql89 source/rf contract failed');target_absent(folder,invalid_db)
        execute(folder,invalid_db,'DELETE FROM rr_mart.transaction_basket_items;')
        expect_failure(folder,invalid_db,query,'sql89 source/rf contract failed');target_absent(folder,invalid_db)
        cases.append(dict(case='typed_dense_creation_no_TOTAL_existing_target_refusal_invalid_nonempty_empty_rejection_count_and_type_audits',passed=True,
            memberships=12,candidate_baskets=11,visitor_ids=4,target_rows=16,target_columns=7,empty_cells=12,build_safety_and_audit_subcases=5))
    assert not folder.exists()
    print(json.dumps({'fixture_families_passed':len(cases),'build_safety_and_audit_subcases':5}),flush=True)

    before={'events.csv':staging.snapshot(source)}
    assert all(before['events.csv'][key]==source_audit['source_before']['events.csv'][key]==source_audit['source_after']['events.csv'][key]
        for key in ['size_bytes','modified_time_ns','sha256'])
    historical={str(p.relative_to(root)):source_reference.sha256(p) for p in (root/'data').glob('*preflight.json') if p.resolve()!=output.resolve()}
    assert len(historical)==87
    started=time.perf_counter();rows,source_counts=counts.scan_source(source);source_seconds=round(time.perf_counter()-started,3)
    assert source_counts==old['independent_python_source_counts'] and len(rows)==22323
    input_hash=counts.canonical_hash(rows);assert input_hash==old['accepted_SQL79_membership_sha256']
    started=time.perf_counter();stats,table,expected,rf_hash=summary_reference(rows);reference_seconds=round(time.perf_counter()-started,3)
    assert [stats[name] for name in ['memberships','baskets','single_baskets','multi_baskets','max_items','visitor_ids']]==[22323,17672,15029,2643,31,11719]
    assert rf_hash==old['accepted_SQL87_RF_fingerprint']
    for proof in [rf_proof,rf_accepted]:
        assert [(row[2],row[4],row[5],row[6]) for row in table]==[
            (row['recency_band'],row['frequency_band'],row['visitor_ids'],row['candidate_baskets']) for row in proof['results'][:-1]]
    print(json.dumps({'phase':'single canonical parse, accepted memberships and RF fingerprint/cell counts matched'}),flush=True)
    with tempfile.TemporaryDirectory(prefix='rr-rf-bi-real-',dir=tmp_root) as temporary:
        folder,database=Path(temporary),Path(temporary)/'preflight.duckdb'
        readback_hash,load_seconds,csv_bytes=load_memberships(folder,database,rows);assert readback_hash==input_hash
        database_before_build=source_reference.sha256(database)
        report,build_seconds=execute(folder,database,sql);compare_audit(report,expected)
        assert Counter(row['status'] for row in report)==Counter(PASS=20)
        database_after_build=source_reference.sha256(database);assert database_before_build!=database_after_build
        table_hash,table_seconds=read_summary(folder,database,table);assert table_hash==counts.canonical_hash(table)
        database_after_read=source_reference.sha256(database);assert database_after_build==database_after_read;database_bytes=database.stat().st_size
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
        accepted_original_five_field_proof_reused=True,accepted_SQL87_RF_fingerprint=rf_hash,accepted_SQL87_RF_fingerprint_matched=True,
        accepted_SQL87_sixteen_cell_counts_matched=True,accepted_fixed_endpoint_provenance_reused=True,
        reference_endpoint_ms=REFERENCE_MS,reference_endpoint_utc=REFERENCE_UTC,source_lower_timestamp_ms=SOURCE_MIN_MS,
        target_table='rr_bi.rf_segment_summary',target_rows=16,target_columns=7,target_column_names=TABLE_FIELDS,target_column_types=TABLE_TYPES,
        target_key=['reference_timestamp_ms','recency_order','frequency_order'],target_dense_cells=16,target_TOTAL_rows=0,
        target_visitor_ids_sum=11719,target_candidate_baskets_sum=17672,target_empty_cells=sum(row[5]==0 for row in table),
        target_contains_percentages=False,target_contains_top_k=False,target_contains_original_identifiers=False,
        full_observation_window_additive_counts=True,multiple_snapshot_people_additivity_claimed=False,
        build_once_no_replace=True,invalid_input_error_guard_including_empty=True,
        original_five_field_occurrence_comparison_rerun=False,original_event_external_sort_rerun=False,
        SQL54_rerun=False,SQL63_rerun=False,SQL64_rerun=False,SQL70_rerun=False,SQL79_rerun=False,SQL80_rerun=False,SQL81_rerun=False,SQL82_rerun=False,SQL83_rerun=False,SQL84_rerun=False,SQL85_rerun=False,SQL86_rerun=False,SQL87_rerun=False,SQL88_rerun=False,
        old_frequency_recency_RF_ranked_pair_or_month_streams_recompared=False,previous_RF_boundary_or_concentration_fixtures_rerun=False,
        property_files_read=False,category_csv_read=False,enriched_fact_read=False,learner_database_opened=False,
        query_read_only=False,build_intentionally_creates_private_target=True,final_table_readback_read_only=True,
        integrated_fixture_and_real_run_count=2,successful_integrated_fixture_and_real_run_count=1,
        preliminary_fixture_attempts=1,preliminary_fixture_failure='Audit binder ambiguity in reference_timestamp_ms; corrected by qualifying summary column.',
        preliminary_failure_before_source_parse=True,synthetic_empty_schema_binder_diagnostic_only=True,
        real_source_attempts=1,real_event_csv_parse_passes=1,real_cli_phases=3,
        real_private_input_load_executions=1,real_build_and_audit_executions=1,real_private_target_readback_executions=1,
        report_rows=20,report_columns=5,output_columns=OUTPUT,checks_passed=20,fail_rows=0,blocked_rows=0,results=report,
        report_sha256=counts.canonical_hash([[row[key] for key in OUTPUT] for row in report]),
        report_fingerprint_contract='Returned audit compact JSON arrays in output-column order followed by LF; actual/expected are canonical integer strings.',
        independent_python_source_counts=source_counts,independent_python_BI_scope_counts=stats,independent_python_audit_matched_exactly=True,
        independent_target_rows_compared=16,independent_target_fields_compared=7,independent_target_five_integer_fields_two_labels_exact=True,
        independent_target_all_matched=True,independent_target_sha256=table_hash,target_readback_sql_sha256=hashlib.sha256(TABLE_QUERY.encode()).hexdigest(),
        aggregate_target_rows=[dict(zip(TABLE_FIELDS,row)) for row in table],
        private_database_sha256_before_build=database_before_build,private_database_sha256_after_build=database_after_build,
        private_database_sha256_after_readonly=database_after_read,private_database_changed_by_build=True,
        private_database_bytes_unchanged_during_final_readonly=True,
        fixture_case_count=len(cases),fixture_cases=cases,build_safety_and_audit_fixture_subcases=5,
        typed_dense_sixteen_cells_no_TOTAL_verified=True,existing_target_rejected_and_unchanged_verified=True,
        invalid_nonempty_input_rejected_target_absent_verified=True,invalid_empty_input_rejected_target_absent_verified=True,
        corrupted_count_audit_FAIL_verified=True,wrong_target_count_type_schema_FAIL_verified=True,
        retained_transaction_occurrences=source_counts['transaction'],transaction_occurrence_cap=counts.TRANSACTION_CAP,visitor_reference_cap=VISITOR_CAP,
        preflight_settings=dict(threads=2,memory_limit='1GB',max_temp_directory_size='2GB',timeout_seconds_per_cli_phase=120,
            transaction_occurrence_cap=counts.TRANSACTION_CAP,visitor_reference_cap=VISITOR_CAP,
            minimum_free_bytes=8*1024**3,private_directory_budget_bytes=7*1024**3),
        private_input_csv_bytes=csv_bytes,private_database_bytes_before_cleanup=database_bytes,
        largest_private_directory_bytes_observed_after_phase=max(sizes),workspace_free_bytes_before=free_before,workspace_free_bytes_after=shutil.disk_usage(tmp_root).free,
        temporary_databases_and_spills_removed=True,private_membership_csv_removed=True,historical_preflight_files_unchanged=len(historical),
        historical_comparison_or_analysis_suites_rerun=False,source_records_or_identifiers_uploaded_or_logged=False,raw_visitor_identifiers_published=False,
        elapsed_python_source_scan_reconstruction_seconds=source_seconds,elapsed_python_summary_reference_seconds=reference_seconds,
        elapsed_private_input_load_readback_seconds=load_seconds,elapsed_build_and_audit_seconds=build_seconds,elapsed_private_target_readback_seconds=table_seconds,
        timing_scope='One new build/audit fixture family then one canonical parse and independent cell aggregate; input load, build/audit and read-only new table proof. No old result streams repeated.',
        power_bi_model_completed=False,power_bi_dashboard_completed=False,
        scope='Assistant SQL89 preparation passed; learner build pending. Additive aggregate RF table for later BI work, not a completed Power BI model or dashboard.')
    output.write_text(json.dumps(evidence,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps({'report_rows':20,'checks_passed':20,'target_rows_compared':16,'target_fields':7,'report_sha256':evidence['report_sha256']}),flush=True)


if __name__=='__main__':main()
