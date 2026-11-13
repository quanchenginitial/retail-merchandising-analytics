"""Build candidate basket-item memberships and independently verify all source and membership tuples."""
import argparse
import csv
import hashlib
import json
import re
import shutil
import subprocess
import tempfile
import threading
import time
from datetime import datetime, timezone
from itertools import zip_longest
from pathlib import Path

import preflight_retailrocket_transaction_basket_grain as grain

events=grain.event_reference
staging=grain.staging
source_reference=grain.source_reference
CONTRACT_SHA='b5b50226a110b37ab801dc20f8fccfc355c8df11629ac6425fc8401e2067d8dd'
CHECK_MARKER='-- CHECKS: if rr_mart.transaction_basket_items already exists, run only the query below.'
FIELDS=['visitorid','transactionid','itemid','first_timestamp_ms','last_timestamp_ms','source_event_rows']
OUTPUT=['check_order','check_name','actual','expected','status']
CHECKS=['source_event_rows','source_schema_mismatch','source_invalid_event_rows','source_duplicate_surplus','source_transaction_rows',
        'source_contract_violations','membership_rows','column_count','schema_mismatch','missing_or_invalid_rows','duplicate_key_surplus',
        'candidate_baskets','source_event_rows_sum','repeated_memberships','repeat_surplus_rows','single_item_baskets',
        'multi_item_baskets','max_distinct_items_per_basket','source_only_memberships','table_only_memberships','basket_partition_difference']
SOURCE_FINGERPRINT='''SELECT COUNT(*) AS rows,BIT_XOR(hash(timestamp,visitorid,event,itemid,transactionid)) AS xor64,
    SUM(CAST(hash(timestamp,visitorid,event,itemid,transactionid) AS HUGEINT)) AS sum128 FROM rr_stg.events;'''
MEMBERSHIP_STREAM='''SELECT visitorid,transactionid,itemid,first_timestamp_ms,last_timestamp_ms,source_event_rows
FROM rr_mart.transaction_basket_items ORDER BY visitorid,transactionid,itemid;'''


def memberships(transactions):
    assert len(transactions)<=grain.TRANSACTION_CAP
    grouped={}
    for timestamp,visitor,event,item,transaction in transactions:
        assert event=='transaction' and transaction is not None
        key=(visitor,transaction,item)
        if key not in grouped:grouped[key]=[timestamp,timestamp,0]
        value=grouped[key];value[0]=min(value[0],timestamp);value[1]=max(value[1],timestamp);value[2]+=1
    return [key+tuple(value) for key,value in sorted(grouped.items())]


def parameters(rows):
    stats=grain.blank_stats()
    stats.update(rows=len(rows),duplicate_surplus=len(rows)-len(set(rows)),transaction_tuples=[row for row in rows if row[2]=='transaction'])
    for row in rows:stats[row[2]]+=1
    d=grain.diagnostics(stats['transaction_tuples'])
    return dict(expected_rows=stats['rows'],expected_views=stats['view'],expected_carts=stats['addtocart'],
        expected_transactions=stats['transaction'],expected_duplicate_surplus=stats['duplicate_surplus'],
        max_supported_ms=events.utc_reference.MAX_MS,expected_memberships=d['distinct_basket_item_pairs'],
        expected_baskets=d['visitor_transaction_pairs'],expected_repeated_memberships=d['repeated_basket_item_pairs'],
        expected_repeat_surplus=d['repeat_basket_item_surplus_rows'],expected_single_baskets=d['single_item_baskets'],
        expected_multi_baskets=d['multi_item_baskets'],expected_max_items=d['max_distinct_items_per_basket'] or 0)


def adjusted(sql,rows,override=None):
    values=parameters(rows);values.update(override or {})
    for name,value in values.items():
        sql,n=re.subn(r'\b[0-9]+::BIGINT AS '+name+r'\b',f'{value}::BIGINT AS {name}',sql)
        assert n in (1,2),(name,n)
    return sql


def reference_report(stats,rows):
    d=grain.diagnostics(stats['transaction_tuples'])
    assert sum(row[5] for row in rows)==stats['transaction']
    values=[stats['rows'],0,0,stats['duplicate_surplus'],stats['transaction'],0,len(rows),6,0,0,0,
        d['visitor_transaction_pairs'],stats['transaction'],d['repeated_basket_item_pairs'],d['repeat_basket_item_surplus_rows'],
        d['single_item_baskets'],d['multi_item_baskets'],d['max_distinct_items_per_basket'],0,0,0]
    return [dict(zip(OUTPUT,[i,name,value,value,'PASS'])) for i,(name,value) in enumerate(zip(CHECKS,values),1)]


def report_hash(report):
    return hashlib.sha256(''.join(json.dumps([row[name] for name in OUTPUT],separators=(',',':'))+'\n' for row in report).encode()).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--duckdb',required=True)
    parser.add_argument('--output',required=True);parser.add_argument('--fixtures-only',action='store_true');args=parser.parse_args()
    root=Path(__file__).resolve().parents[1];output=(root/args.output).resolve()
    script_path='sql/79_build_retailrocket_transaction_basket_items.sql'
    validator_path='validation/preflight_retailrocket_transaction_basket_items.py'
    method_path='docs/RETAILROCKET_TRANSACTION_BASKET_ITEMS_VALIDATION.md'
    assert output==(root/'data/retailrocket_transaction_basket_items_preflight.json').resolve()
    old=json.loads((root/'data/retailrocket_transaction_basket_grain_preflight.json').read_text(encoding='utf-8'))
    accepted=json.loads((root/'data/retailrocket_transaction_basket_grain_learner_acceptance.json').read_text(encoding='utf-8'))
    assert accepted['acceptance_status']=='accepted' and accepted['report_sha256']==old['report_sha256']
    deps=list(old['code_and_dependency_sha256'])+[script_path,validator_path,'data/retailrocket_transaction_basket_grain_preflight.json',
        'data/retailrocket_transaction_basket_grain_learner_acceptance.json','docs/RETAILROCKET_TRANSACTION_BASKET_GRAIN_VALIDATION.md']
    hashes={name:source_reference.sha256(root/name) for name in deps}
    assert all(hashes[name]==digest for name,digest in old['code_and_dependency_sha256'].items())
    contract=(root/method_path).read_bytes().split(b'\n## Executed results\n',1)[0]
    assert hashlib.sha256(contract).hexdigest()==CONTRACT_SHA
    sql=(root/script_path).read_text(encoding='utf-8');creation,audit=sql.split(CHECK_MARKER,1)
    assert 'CREATE TABLE rr_mart.transaction_basket_items AS' in creation
    assert not re.search(r'\b(UPDATE|DELETE|DROP|REPLACE|ATTACH|DETACH)\b',re.sub(r'--[^\n]*','',sql),re.I)
    assert all(name not in sql for name in ['categoryid','available','event_timestamp_utc','event_date_utc','rr_core'])
    clean_audit=re.sub(r'--[^\n]*','',audit)
    assert clean_audit.lstrip().startswith('WITH ') and not re.search(r'\b(CREATE|INSERT|UPDATE|DELETE|DROP|ALTER|COPY|SET)\b',clean_audit,re.I)
    prefixes={
        'sql/54_import_retailrocket_events.sql':(root/'sql/54_import_retailrocket_events.sql').read_text(encoding='utf-8').split('-- CHECKS:',1)[0],
        'sql/63_stage_retailrocket_events.sql':(root/'sql/63_stage_retailrocket_events.sql').read_text(encoding='utf-8').split(staging.CHECK_MARKER,1)[0]}
    assert all(hashlib.sha256(code.encode()).hexdigest()==old['reconstruction_prefix_sha256'][name] for name,code in prefixes.items())
    assert all('EXCEPT ALL' not in code for code in prefixes.values())
    source=Path(source_reference.SOURCE)
    source_audit=json.loads((root/'data/retailrocket_source_audit.json').read_text(encoding='utf-8'))
    tmp_root=root/'tmp';tmp_root.mkdir(exist_ok=True);free_before=shutil.disk_usage(tmp_root).free
    assert free_before>=8*1024**3;sizes=[]
    def settings(folder,database):
        assert folder.resolve().is_relative_to(tmp_root.resolve()) and Path(database).resolve().is_relative_to(folder.resolve())
        spill=(folder/'spill').as_posix().replace("'","''")
        return f"SET threads=2;SET memory_limit='1GB';SET max_temp_directory_size='2GB';SET temp_directory='{spill}';\n"
    def observe(folder):
        size=sum(p.stat().st_size for p in folder.rglob('*') if p.is_file());assert size<=7*1024**3;sizes.append(size)
    def execute(folder,database,query,readonly=False):
        started=time.perf_counter()
        run=subprocess.run([args.duckdb,str(database),'-bail','-json']+(['-readonly'] if readonly else []),
            input=settings(folder,database)+query,text=True,encoding='utf-8',capture_output=True,timeout=120)
        if run.returncode:
            diagnostic=run.stderr.lower()
            category=next((name for name,patterns in [('out_of_memory',['out of memory','failed to allocate']),('disk_or_spill',['no space left','max_temp_directory_size']),
                ('parser',['parser error']),('binder',['binder error']),('invalid_input',['invalid input error']),('catalog',['catalog error'])]
                if any(pattern in diagnostic for pattern in patterns)),'unclassified_cli_error')
            raise AssertionError('Private basket-item CLI failure: '+category+'; row-bearing details withheld')
        observe(folder)
        return staging.json_outputs(run.stdout),round(time.perf_counter()-started,3)
    def compare_stream(folder,database,query,wanted,fields):
        started=time.perf_counter();expired=threading.Event();count=0;sentinel=object();fingerprint=hashlib.sha256()
        process=subprocess.Popen([args.duckdb,str(database),'-bail','-readonly','-csv','-noheader'],stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,encoding='utf-8')
        def expire():expired.set();process.kill()
        timer=threading.Timer(120,expire);timer.start()
        try:
            process.stdin.write(settings(folder,database)+query);process.stdin.close()
            for observed,expected in zip_longest(csv.reader(process.stdout,strict=True),wanted,fillvalue=sentinel):
                assert observed is not sentinel and expected is not sentinel,'Private complete occurrence count differs'
                assert len(observed)==fields
                actual=tuple(None if fields==5 and i==4 and value=='__NULL__' else value if fields==5 and i==2 else int(value)
                             for i,value in enumerate(observed))
                assert actual==expected,'Private complete tuple comparison differs; values withheld'
                fingerprint.update((json.dumps(actual,separators=(',',':'))+'\n').encode());count+=1
            assert process.wait(timeout=120)==0 and not expired.is_set()
        finally:
            timer.cancel()
            if process.poll() is None:process.kill();process.wait()
            process.stdout.close()
        observe(folder)
        return dict(rows=count,fields=fields,sha256=fingerprint.hexdigest()),round(time.perf_counter()-started,3)
    def source_fixture(folder,rows):
        with (folder/'events.csv').open('w',encoding='utf-8',newline='') as stream:
            writer=csv.writer(stream);writer.writerow(staging.FIELDS);writer.writerows(reversed(rows))
        return events.source_chunks(folder/'events.csv',folder,chunk_rows=2)[0]
    def table_presence(folder,database):
        result,_=execute(folder,database,"SELECT COUNT(*) AS n FROM information_schema.tables WHERE table_schema='rr_mart' AND table_name='transaction_basket_items';",readonly=True)
        return result[0][0]['n']

    fixture_rows=[(0,1,'view',1,None),(1,1,'addtocart',1,None),
        (100,1,'transaction',1,10),(100,1,'transaction',1,10),(101,1,'transaction',1,10),(102,1,'transaction',2,10),
        (103,2,'transaction',3,10),(200,1,'transaction',4,20),(200,1,'transaction',5,20),(300,3,'transaction',6,30)]
    cases=[]
    with tempfile.TemporaryDirectory(prefix='rr-basket-items-fixture-',dir=tmp_root) as temporary:
        folder,database=Path(temporary),Path(temporary)/'fixture.duckdb';paths=source_fixture(folder,fixture_rows)
        before_outputs,_=execute(folder,database,grain.fixture_setup(fixture_rows)+'ALTER TABLE rr_stg.events ADD COLUMN unqueried_fixture VARCHAR;'+SOURCE_FINGERPRINT)
        result,_=execute(folder,database,adjusted(sql,fixture_rows)+'\n'+SOURCE_FINGERPRINT)
        assert result[1]==before_outputs[0]
        stats=grain.blank_stats();source_proof,_=compare_stream(folder,database,grain.STREAM,grain.expected_stream(paths,stats),5)
        expected=memberships(stats['transaction_tuples']);table_proof,_=compare_stream(folder,database,MEMBERSHIP_STREAM,iter(expected),6)
        assert result[0]==reference_report(stats,expected) and all(row['status']=='PASS' for row in result[0])
        assert expected[0]==(1,10,1,100,101,3) and expected[1]==(1,10,2,102,102,1)
        assert source_proof['rows']==10 and table_proof['rows']==6
        cases.append(dict(case='six_field_item_specific_bounds_exact_and_nonexact_repeats_cross_visitor_keys_extra_source_column',passed=True,
            source_rows=10,transaction_occurrences=8,membership_rows=6,source_fields=5,membership_fields=6))
        try:execute(folder,database,adjusted(sql,fixture_rows))
        except AssertionError as error:assert 'catalog' in str(error)
        else:raise AssertionError('Existing destination was overwritten')
        after_outputs,_=execute(folder,database,SOURCE_FINGERPRINT,readonly=True)
        after_table,_=compare_stream(folder,database,MEMBERSHIP_STREAM,iter(expected),6)
        assert after_outputs==before_outputs and after_table==table_proof
        cases.append(dict(case='existing_destination_fails_preserving_source_and_complete_membership_tuples',passed=True))
        for column in ['source_event_rows','first_timestamp_ms','last_timestamp_ms']:
            query=f'BEGIN;UPDATE rr_mart.transaction_basket_items SET {column}={column}+1 WHERE visitorid=1 AND transactionid=10 AND itemid=1;'+adjusted(audit,fixture_rows)+'ROLLBACK;'
            corrupted,_=execute(folder,database,query);found={row['check_name']:row for row in corrupted[0]}
            assert found['source_only_memberships']['actual']==found['table_only_memberships']['actual']==1
            assert found['source_only_memberships']['status']==found['table_only_memberships']['status']=='FAIL'
            if column=='source_event_rows':assert found['source_event_rows_sum']['status']=='FAIL'
        cases.append(dict(case='audit_detects_changed_occurrence_count_first_and_last_item_bounds',passed=True,subcases=3))
    assert not folder.exists()
    with tempfile.TemporaryDirectory(prefix='rr-basket-items-invalid-',dir=tmp_root) as temporary:
        parent=Path(temporary)
        invalid_cases=[('empty_source','DELETE FROM rr_stg.events;',{}),('no_transaction_source',"DELETE FROM rr_stg.events WHERE event='transaction';",{}),
            ('negative_source_id','UPDATE rr_stg.events SET visitorid=-1 WHERE timestamp=0;',{}),
            ('wrong_required_type','ALTER TABLE rr_stg.events ALTER COLUMN timestamp TYPE VARCHAR;',{}),
            ('wrong_expected_memberships','',{'expected_memberships':7})]
        for name,mutation,overrides in invalid_cases:
            folder=parent/name;folder.mkdir();database=folder/'fixture.duckdb'
            setup,_=execute(folder,database,grain.fixture_setup(fixture_rows)+mutation+SOURCE_FINGERPRINT)
            try:execute(folder,database,adjusted(creation,fixture_rows,overrides))
            except AssertionError as error:assert 'invalid_input' in str(error),name
            else:raise AssertionError('Invalid source created destination: '+name)
            assert table_presence(folder,database)==0,name
            post,_=execute(folder,database,SOURCE_FINGERPRINT,readonly=True);assert post==setup
        cases.append(dict(case='empty_no_transaction_invalid_fields_types_or_controls_leave_no_destination',passed=True,subcases=5))
    assert not parent.exists()
    with tempfile.TemporaryDirectory(prefix='rr-basket-items-empty-',dir=tmp_root) as temporary:
        folder,database=Path(temporary),Path(temporary)/'fixture.duckdb';rows=[(0,1,'view',2,None),(1,1,'addtocart',2,None)]
        paths=source_fixture(folder,rows);execute(folder,database,grain.fixture_setup(rows))
        result,_=execute(folder,database,adjusted(sql,rows));stats=grain.blank_stats()
        compare_stream(folder,database,grain.STREAM,grain.expected_stream(paths,stats),5)
        table_proof,_=compare_stream(folder,database,MEMBERSHIP_STREAM,iter(memberships(stats['transaction_tuples'])),6)
        assert table_proof['rows']==0 and result[0]==reference_report(stats,[])
        assert result[0][17]['actual'] is None and all(row['status']=='PASS' for row in result[0])
        cases.append(dict(case='valid_nonempty_source_with_zero_transactions_creates_empty_six_field_table',passed=True))
    assert not folder.exists()
    print(json.dumps({'fixture_families_passed':len(cases),'invalid_creation_subcases':5,'audit_corruption_subcases':3}),flush=True)
    if args.fixtures_only:return

    before={'events.csv':staging.snapshot(source)}
    assert all(before['events.csv'][key]==source_audit['source_before']['events.csv'][key]==source_audit['source_after']['events.csv'][key]
               for key in ['size_bytes','modified_time_ns','sha256'])
    historical={str(p.relative_to(root)):source_reference.sha256(p) for p in (root/'data').glob('*preflight.json') if p.resolve()!=output.resolve()}
    assert len(historical)==77
    with tempfile.TemporaryDirectory(prefix='rr-basket-items-real-',dir=tmp_root) as temporary:
        folder,database=Path(temporary),Path(temporary)/'preflight.duckdb'
        started=time.perf_counter();paths,source_counts=events.source_chunks(source,folder,chunk_rows=grain.CHUNK_ROWS);sort_seconds=round(time.perf_counter()-started,3)
        assert source_counts==old['independent_python_source_counts'];chunk_bytes=sum(p.stat().st_size for p in paths)
        print(json.dumps({'phase':'event-only source sorting complete'}),flush=True)
        built,source_build_seconds=execute(folder,database,'\n'.join(prefixes.values())+'\n'+SOURCE_FINGERPRINT)
        built_result,membership_build_seconds=execute(folder,database,sql+'\n'+SOURCE_FINGERPRINT)
        report=built_result[0];source_before_build=built[0][0];source_after_build=built_result[1][0]
        assert source_before_build==source_after_build
        assert len(report)==21 and all(list(row)==OUTPUT and row['status']=='PASS' for row in report)
        print(json.dumps({'phase':'SQL79 guarded creation and twenty-one checks passed'}),flush=True)
        database_before=source_reference.sha256(database)
        stats=grain.blank_stats();source_proof,source_stream_seconds=compare_stream(folder,database,grain.STREAM,grain.expected_stream(paths,stats),5)
        expected=memberships(stats['transaction_tuples'])
        membership_proof,membership_stream_seconds=compare_stream(folder,database,MEMBERSHIP_STREAM,iter(expected),6)
        assert report==reference_report(stats,expected)
        assert source_proof['rows']==2756101 and source_proof['fields']==5 and membership_proof['rows']==22323 and membership_proof['fields']==6
        assert stats['duplicate_surplus']==460 and len(stats['transaction_tuples'])==22457
        diagnostics=grain.diagnostics(stats['transaction_tuples']);assert diagnostics==old['independent_python_transaction_diagnostics']
        database_after=source_reference.sha256(database);assert database_before==database_after
        database_bytes=database.stat().st_size;aggregate_counts={k:v for k,v in stats.items() if k!='transaction_tuples'}
    assert not folder.exists()
    after={'events.csv':staging.snapshot(source)}
    assert before==after and all(source_reference.sha256(root/name)==digest for name,digest in hashes.items())
    assert all(source_reference.sha256(root/name)==digest for name,digest in historical.items())
    assert (root/method_path).read_bytes().startswith(contract)
    evidence=dict(checked_at_utc=datetime.now(timezone.utc).isoformat(),executor='assistant',engine=subprocess.check_output([args.duckdb,'-version'],text=True).strip(),
        script=script_path,script_sha256=hashes[script_path],validator=validator_path,validator_sha256=hashes[validator_path],code_and_dependency_sha256=hashes,
        method_contract=method_path,method_contract_prefix_bytes=len(contract),method_contract_prefix_sha256=CONTRACT_SHA,
        source_files=['events.csv'],source_before=before,source_after=after,source_hashes_and_metadata_unchanged=True,
        reconstruction_prefix_sha256={name:hashlib.sha256(code.encode()).hexdigest() for name,code in prefixes.items()},
        source_table='rr_stg.events',source_readset_fields=staging.FIELDS,source_readset_columns=5,
        destination_table='rr_mart.transaction_basket_items',destination_fields=FIELDS,destination_columns=6,destination_types=['BIGINT']*6,
        source_logical_fingerprint_before_build=source_before_build,source_logical_fingerprint_after_build=source_after_build,
        source_fingerprint_definition='COUNT plus BIT_XOR and SUM of DuckDB hash(original five fields), with complete independent after-build source occurrence comparison; aggregate fingerprints alone are not exact identity proof.',
        source_logical_fingerprint_unchanged=True,source_complete_after_build_csv_comparison_passed=True,
        property_files_read=False,category_csv_read=False,UTC_fields_read=False,full17_not_reverified=True,property_history_reconstructed=False,category_hierarchy_reverified=False,
        learner_database_opened=False,source_events_modified=False,destination_uses_plain_guarded_create=True,destination_existing_data_overwritten=False,
        atomic_invalid_creation_verified=True,invalid_empty_source_creates_no_table_verified=True,invalid_no_transaction_source_creates_no_table_verified=True,
        existing_destination_preserved_verified=True,valid_empty_transaction_fixture_verified=True,additional_unqueried_source_columns_allowed_verified=True,
        audit_count_and_first_last_bounds_corruption_detected=True,audit_only_query_read_only=True,private_streams_read_only=True,
        real_source_attempts=1,real_cli_phases=4,real_source_reconstruction_executions=1,real_membership_build_and_audit_executions=1,
        real_source_stream_executions=1,real_membership_stream_executions=1,
        report_rows=21,report_columns=5,output_columns=OUTPUT,checks_passed=21,info_rows=0,fail_rows=0,results=report,report_sha256=report_hash(report),
        report_fingerprint_contract='SHA-256 of compact JSON arrays in output-column order followed by LF; counts are integers and undefined synthetic maximum is null.',
        independent_python_source_counts=source_counts,independent_python_aggregate_counts=aggregate_counts,independent_python_transaction_diagnostics=diagnostics,
        independent_python_report_matched=True,independent_source_occurrences_compared=source_proof['rows'],independent_source_fields_compared=5,
        independent_membership_rows_compared=membership_proof['rows'],independent_membership_fields_compared=6,
        independent_source_stream_sha256=source_proof['sha256'],independent_membership_stream_sha256=membership_proof['sha256'],
        independent_source_and_membership_all_occurrences_matched=True,independent_original_event_fields_and_duplicates_preserved=True,
        membership_key=['visitorid','transactionid','itemid'],candidate_basket_key=['visitorid','transactionid'],
        item_specific_first_last_and_occurrence_count_verified=True,source_event_rows_sum=22457,membership_rows=22323,candidate_baskets=17672,
        candidate_key_is_diagnostic_not_verified_business_order=True,repeated_item_records_treated_as_quantities=False,association_metrics_calculated=False,
        retained_transaction_occurrences=22457,transaction_occurrence_retention_cap=grain.TRANSACTION_CAP,membership_aggregate_keys_retained=len(expected),
        private_database_sha256_before_readonly=database_before,private_database_sha256_after_readonly=database_after,private_database_bytes_unchanged=True,
        fixture_case_count=len(cases),fixture_cases=cases,invalid_creation_fixture_subcases=5,audit_corruption_fixture_subcases=3,
        preflight_settings=dict(threads=2,memory_limit='1GB',max_temp_directory_size='2GB',timeout_seconds_per_cli_phase=120,
            python_sort_chunk_rows=grain.CHUNK_ROWS,transaction_occurrence_retention_cap=grain.TRANSACTION_CAP,membership_key_cap=grain.TRANSACTION_CAP,
            minimum_free_bytes=8*1024**3,private_directory_budget_bytes=7*1024**3),
        private_event_comparison_chunks=len(paths),private_event_comparison_chunk_bytes=chunk_bytes,private_database_bytes_before_cleanup=database_bytes,
        largest_private_directory_bytes_observed_after_phase=max(sizes),workspace_free_bytes_before=free_before,workspace_free_bytes_after=shutil.disk_usage(tmp_root).free,
        temporary_databases_and_spills_removed=True,private_source_comparison_spools_removed=True,historical_preflight_files_unchanged=len(historical),
        historical_comparison_or_analysis_suites_rerun=False,source_records_or_identifiers_uploaded_or_logged=False,
        elapsed_python_event_scan_sort_seconds=sort_seconds,elapsed_source_reconstruction_seconds=source_build_seconds,
        elapsed_membership_build_and_audit_seconds=membership_build_seconds,elapsed_source_stream_seconds=source_stream_seconds,
        elapsed_membership_stream_seconds=membership_stream_seconds,
        timing_scope='Four bounded CLI phases: frozen source creation, SQL79 membership creation/audit, read-only full source stream, read-only full membership stream. Source sorting timed separately; hashing/fixtures excluded.',
        scope='Assistant SQL79 preparation passed; learner execution pending. One candidate basket-item membership retains original source occurrence counts and item-specific time bounds. Source events are unchanged; no quantities, verified order semantics, monetary metrics or associations are inferred.')
    output.write_text(json.dumps(evidence,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps({'report_rows':21,'checks_passed':21,'source_occurrences_compared':2756101,'source_fields':5,
                      'membership_rows_compared':22323,'membership_fields':6,'report_sha256':evidence['report_sha256']}),flush=True)


if __name__=='__main__':main()
