"""Validate transaction-group diagnostics using only the original five event fields."""
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
from collections import Counter, defaultdict
from datetime import datetime, timezone
from itertools import zip_longest
from pathlib import Path

import preflight_retailrocket_event_overview as event_reference

staging=event_reference.staging
source_reference=staging.previous
CONTRACT_SHA='9076cbdb7f345602552be4c30408d59c122c5cd1840ba48d1fbe29889d32d788'
CHUNK_ROWS=50000
TRANSACTION_CAP=100000
FIELDS=staging.FIELDS
OUTPUT=['check_order','check_name','actual','expected','status']
CHECKS=['source_event_rows','required_schema_mismatch','invalid_event_rows','source_duplicate_surplus',
        'transaction_event_rows','distinct_transaction_ids','visitor_transaction_pairs','transaction_ids_multiple_visitors',
        'transaction_ids_multiple_timestamps','visitor_transaction_pairs_multiple_timestamps','transaction_exact_duplicate_surplus',
        'distinct_basket_item_pairs','repeated_basket_item_pairs','repeat_basket_item_surplus_rows','nonexact_repeat_surplus_rows',
        'single_item_baskets','multi_item_baskets','max_distinct_items_per_basket','basket_partition_difference',
        'transaction_row_reconciliation_difference','basket_item_reconciliation_difference']
PARAMETERS=event_reference.PARAMETERS
STREAM='''SELECT timestamp,visitorid,event,itemid,COALESCE(CAST(transactionid AS VARCHAR),'__NULL__')
FROM rr_stg.events ORDER BY timestamp,visitorid,event,itemid,transactionid NULLS FIRST;'''


def blank_stats():
    return dict(rows=0,duplicate_surplus=0,view=0,addtocart=0,transaction=0,null_transaction_ids=0,transaction_tuples=[])


def expected_stream(paths,stats,transaction_cap=TRANSACTION_CAP):
    prior=None
    for row in event_reference.merged_events(paths):
        stats['rows']+=1;stats[row[2]]+=1;stats['null_transaction_ids']+=row[4] is None
        stats['duplicate_surplus']+=row==prior;prior=row
        if row[2]=='transaction':
            assert len(stats['transaction_tuples'])<transaction_cap,'Private transaction retention cap exceeded; no filtering'
            stats['transaction_tuples'].append(row)
        yield row


def diagnostics(transactions):
    assert len(transactions)<=TRANSACTION_CAP
    id_visitors=defaultdict(set);id_times=defaultdict(set);basket_times=defaultdict(set);basket_items=defaultdict(set)
    basket_rows=Counter();item_rows=Counter()
    for timestamp,visitor,event,item,transaction in transactions:
        assert event=='transaction' and transaction is not None
        id_visitors[transaction].add(visitor);id_times[transaction].add(timestamp)
        basket=(visitor,transaction)
        basket_times[basket].add(timestamp);basket_items[basket].add(item)
        basket_rows[basket]+=1;item_rows[(*basket,item)]+=1
    rows=len(transactions);distinct_tuples=len(set(transactions));memberships=len(item_rows)
    sizes=[len(items) for items in basket_items.values()]
    single=sum(size==1 for size in sizes);multi=sum(size>1 for size in sizes)
    return dict(distinct_transaction_ids=len(id_visitors),visitor_transaction_pairs=len(basket_rows),
        transaction_ids_multiple_visitors=sum(len(values)>1 for values in id_visitors.values()),
        transaction_ids_multiple_timestamps=sum(len(values)>1 for values in id_times.values()),
        visitor_transaction_pairs_multiple_timestamps=sum(len(values)>1 for values in basket_times.values()),
        transaction_exact_duplicate_surplus=rows-distinct_tuples,distinct_basket_item_pairs=memberships,
        repeated_basket_item_pairs=sum(value>1 for value in item_rows.values()),repeat_basket_item_surplus_rows=rows-memberships,
        nonexact_repeat_surplus_rows=distinct_tuples-memberships,single_item_baskets=single,multi_item_baskets=multi,
        max_distinct_items_per_basket=max(sizes,default=None),basket_partition_difference=single+multi-len(basket_rows),
        transaction_row_reconciliation_difference=sum(basket_rows.values())-rows,
        basket_item_reconciliation_difference=sum(sizes)-memberships)


def reference_report(stats):
    values=dict(source_event_rows=stats['rows'],required_schema_mismatch=0,invalid_event_rows=0,
                source_duplicate_surplus=stats['duplicate_surplus'],transaction_event_rows=stats['transaction'])
    values.update(diagnostics(stats['transaction_tuples']))
    expected={CHECKS[0]:stats['rows'],CHECKS[1]:0,CHECKS[2]:0,CHECKS[3]:stats['duplicate_surplus'],CHECKS[4]:stats['transaction'],
              CHECKS[18]:0,CHECKS[19]:0,CHECKS[20]:0}
    return [dict(zip(OUTPUT,[i,name,values[name],expected.get(name),'PASS' if name in expected else 'INFO']))
            for i,name in enumerate(CHECKS,1)]


def report_hash(report):
    return hashlib.sha256(''.join(json.dumps([row[name] for name in OUTPUT],separators=(',',':'))+'\n' for row in report).encode()).hexdigest()


def adjusted(sql,rows,override=None):
    counts=Counter(row[2] for row in rows)
    parameters=dict(expected_rows=len(rows),expected_views=counts['view'],expected_carts=counts['addtocart'],
        expected_transactions=counts['transaction'],expected_duplicate_surplus=len(rows)-len(set(rows)),max_supported_ms=event_reference.utc_reference.MAX_MS)
    parameters.update(override or {})
    assert sql.count(PARAMETERS)==1
    return sql.replace(PARAMETERS,'SELECT '+','.join(f'{value}::BIGINT AS {name}' for name,value in parameters.items()))


def fixture_setup(rows):
    query='CREATE SCHEMA rr_stg; CREATE TABLE rr_stg.events(timestamp BIGINT,visitorid BIGINT,event VARCHAR,itemid BIGINT,transactionid BIGINT);\n'
    def literal(value):
        return 'NULL' if value is None else "'"+str(value).replace("'","''")+"'"
    if rows:query+='INSERT INTO rr_stg.events VALUES '+','.join('('+','.join(literal(value) for value in row)+')' for row in rows)+';\n'
    return query


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--duckdb',required=True);parser.add_argument('--output',required=True)
    parser.add_argument('--fixtures-only',action='store_true');args=parser.parse_args()
    root=Path(__file__).resolve().parents[1];output=(root/args.output).resolve()
    script_path='sql/78_audit_retailrocket_transaction_basket_grain.sql'
    validator_path='validation/preflight_retailrocket_transaction_basket_grain.py'
    method_path='docs/RETAILROCKET_TRANSACTION_BASKET_GRAIN_VALIDATION.md'
    assert output==(root/'data/retailrocket_transaction_basket_grain_preflight.json').resolve()
    dependencies=[script_path,validator_path,'sql/54_import_retailrocket_events.sql','sql/63_stage_retailrocket_events.sql',
        'validation/preflight_retailrocket_events_import.py','validation/preflight_retailrocket_events_staging.py',
        'validation/preflight_retailrocket_event_time.py','validation/preflight_retailrocket_event_overview.py',
        'data/retailrocket_source_audit.json','data/retailrocket_event_time_preflight.json',
        'data/retailrocket_events_staging_preflight.json','data/retailrocket_events_staging_learner_acceptance.json',
        'docs/RETAILROCKET_EVENTS_STAGING_VALIDATION.md']
    hashes={name:source_reference.sha256(root/name) for name in dependencies}
    contract=(root/method_path).read_bytes().split(b'\n## Executed results\n',1)[0]
    assert hashlib.sha256(contract).hexdigest()==CONTRACT_SHA
    accepted=json.loads((root/'data/retailrocket_events_staging_learner_acceptance.json').read_text(encoding='utf-8'))
    old=json.loads((root/'data/retailrocket_events_staging_preflight.json').read_text(encoding='utf-8'))
    assert accepted['acceptance_status']=='accepted' and accepted['report_sha256']==old['report_sha256']
    assert old['script_sha256']==hashes['sql/63_stage_retailrocket_events.sql']
    sql=(root/script_path).read_text(encoding='utf-8');clean=re.sub(r'--[^\n]*','',sql)
    assert clean.lstrip().startswith('WITH ') and not re.search(r'\b(CREATE|INSERT|UPDATE|DELETE|DROP|ALTER|COPY|ATTACH|DETACH|SET)\b',clean,re.I)
    assert all(name not in clean for name in ['categoryid','available','event_timestamp_utc','event_date_utc','rr_mart','rr_core'])
    prefixes={
        'sql/54_import_retailrocket_events.sql':(root/'sql/54_import_retailrocket_events.sql').read_text(encoding='utf-8').split('-- CHECKS:',1)[0],
        'sql/63_stage_retailrocket_events.sql':(root/'sql/63_stage_retailrocket_events.sql').read_text(encoding='utf-8').split(staging.CHECK_MARKER,1)[0]}
    time_evidence=json.loads((root/'data/retailrocket_event_time_preflight.json').read_text(encoding='utf-8'))
    assert all(hashlib.sha256(code.encode()).hexdigest()==time_evidence['reconstruction_prefix_sha256'][name] for name,code in prefixes.items())
    assert all('EXCEPT ALL' not in code for code in prefixes.values())
    audit=json.loads((root/'data/retailrocket_source_audit.json').read_text(encoding='utf-8'))
    source=Path(source_reference.SOURCE)
    assert audit['files']['events.csv']['sha256']==source_reference.SOURCE_SHA
    tmp_root=root/'tmp';tmp_root.mkdir(exist_ok=True);free_before=shutil.disk_usage(tmp_root).free
    assert free_before>=8*1024**3;sizes=[]
    def settings(folder,database):
        assert folder.resolve().is_relative_to(tmp_root.resolve()) and Path(database).resolve().is_relative_to(folder.resolve())
        spill=(folder/'spill').as_posix().replace("'","''")
        return f"SET threads=2;SET memory_limit='1GB';SET max_temp_directory_size='2GB';SET temp_directory='{spill}';\n"
    def observe(folder):
        size=sum(path.stat().st_size for path in folder.rglob('*') if path.is_file());assert size<=7*1024**3;sizes.append(size)
    def execute(folder,database,query,readonly=False):
        started=time.perf_counter()
        run=subprocess.run([args.duckdb,str(database),'-bail','-json']+(['-readonly'] if readonly else []),
            input=settings(folder,database)+query,text=True,encoding='utf-8',capture_output=True,timeout=120)
        if run.returncode:
            diagnostic=run.stderr.lower()
            category=next((name for name,patterns in [('out_of_memory',['out of memory','failed to allocate']),('disk_or_spill',['no space left','max_temp_directory_size']),
                ('parser',['parser error']),('binder',['binder error']),('invalid_input',['invalid input error'])] if any(pattern in diagnostic for pattern in patterns)),'unclassified_cli_error')
            raise AssertionError('Private basket-grain CLI failure: '+category+'; row-bearing details withheld')
        observe(folder)
        return json.loads(run.stdout) if run.stdout.strip() else None,round(time.perf_counter()-started,3)
    def compare_stream(folder,database,paths):
        started=time.perf_counter();expired=threading.Event();stats=blank_stats();count=0;sentinel=object()
        process=subprocess.Popen([args.duckdb,str(database),'-bail','-readonly','-csv','-noheader'],stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,encoding='utf-8')
        def expire():expired.set();process.kill()
        timer=threading.Timer(120,expire);timer.start()
        try:
            process.stdin.write(settings(folder,database)+STREAM);process.stdin.close()
            for observed,wanted in zip_longest(csv.reader(process.stdout,strict=True),expected_stream(paths,stats),fillvalue=sentinel):
                assert observed is not sentinel and wanted is not sentinel,'Private five-field occurrence count differs'
                assert len(observed)==5
                actual=(int(observed[0]),int(observed[1]),observed[2],int(observed[3]),None if observed[4]=='__NULL__' else int(observed[4]))
                assert actual==wanted,'Private five-field occurrence differs; values withheld';count+=1
            report=reference_report(stats)
            assert process.wait(timeout=120)==0 and not expired.is_set()
        finally:
            timer.cancel()
            if process.poll() is None:process.kill();process.wait()
            process.stdout.close()
        assert count==stats['rows'];observe(folder)
        return stats,report,round(time.perf_counter()-started,3)

    fixture_rows=[(0,1,'view',1,None),(1,1,'addtocart',1,None),
        (100,1,'transaction',1,10),(100,1,'transaction',1,10),(101,1,'transaction',1,10),(102,1,'transaction',2,10),
        (103,2,'transaction',3,10),(200,1,'transaction',4,20),(200,1,'transaction',5,20),(300,3,'transaction',6,30)]
    cases=[]
    with tempfile.TemporaryDirectory(prefix='rr-basket-grain-fixture-',dir=tmp_root) as temporary:
        folder,database=Path(temporary),Path(temporary)/'fixture.duckdb'
        with (folder/'events.csv').open('w',encoding='utf-8',newline='') as stream:
            writer=csv.writer(stream);writer.writerow(FIELDS);writer.writerows(reversed(fixture_rows))
        paths,counts=event_reference.source_chunks(folder/'events.csv',folder,chunk_rows=2)
        execute(folder,database,fixture_setup(fixture_rows)+'ALTER TABLE rr_stg.events ADD COLUMN unqueried_fixture VARCHAR;')
        before_db=source_reference.sha256(database);query=adjusted(sql,fixture_rows)
        report,_=execute(folder,database,query,readonly=True)
        stats,expected,_=compare_stream(folder,database,paths)
        assert report==expected,'Synthetic report differs from independent counts'
        assert source_reference.sha256(database)==before_db
        values={row['check_name']:row['actual'] for row in report}
        assert [values[name] for name in CHECKS[5:18]]==[3,4,1,1,1,1,6,1,2,1,2,2,2]
        assert Counter(row['status'] for row in report)==Counter(PASS=8,INFO=13)
        assert stats['rows']==10 and stats['duplicate_surplus']==1 and len(stats['transaction_tuples'])==8
        cases.append(dict(case='cross_visitor_identifier_multiple_timestamps_exact_and_nonexact_repeats_single_multi_groups',passed=True,
                          source_rows=10,transaction_rows=8,expected_info_values=[3,4,1,1,1,1,6,1,2,1,2,2,2],complete_readset_fields=5))
        cases.append(dict(case='additional_unqueried_column_allowed_without_wider_schema_claim',passed=True))
        mutations=[('negative_identifier','UPDATE rr_stg.events SET visitorid=-1 WHERE timestamp=0;'),
            ('unknown_event',"UPDATE rr_stg.events SET event='other' WHERE timestamp=0;"),
            ('missing_transaction_id',"UPDATE rr_stg.events SET transactionid=NULL WHERE event='transaction';"),
            ('nontransaction_id',"UPDATE rr_stg.events SET transactionid=0 WHERE event='view';"),
            ('wrong_required_type','ALTER TABLE rr_stg.events ALTER COLUMN timestamp TYPE VARCHAR;')]
        for label,mutation in mutations:
            blocked,_=execute(folder,database,'BEGIN;'+mutation+query+'ROLLBACK;')
            assert [row['check_name'] for row in blocked]==CHECKS
            assert all(row['actual'] is None and row['status']=='BLOCKED' for row in blocked),label
            assert [row['expected'] for row in blocked]==[row['expected'] for row in report]
        for parameter,value in [('expected_rows',11),('expected_duplicate_surplus',0)]:
            blocked,_=execute(folder,database,adjusted(sql,fixture_rows,{parameter:value}),readonly=True)
            assert all(row['actual'] is None and row['status']=='BLOCKED' for row in blocked)
        cases.append(dict(case='invalid_values_types_or_expected_counts_block_all_actuals_keep_static_expectations',passed=True,subcases=7))
        try:
            for _ in expected_stream(paths,blank_stats(),transaction_cap=7):pass
        except AssertionError as error:assert 'retention cap' in str(error)
        else:raise AssertionError('Transaction retention cap was not enforced')
        cases.append(dict(case='transaction_retention_cap_aborts_without_sampling',passed=True))
    assert not folder.exists()
    with tempfile.TemporaryDirectory(prefix='rr-basket-grain-empty-',dir=tmp_root) as temporary:
        folder,database=Path(temporary),Path(temporary)/'fixture.duckdb';rows=[(0,1,'view',2,None),(1,1,'addtocart',2,None)]
        with (folder/'events.csv').open('w',encoding='utf-8',newline='') as stream:
            writer=csv.writer(stream);writer.writerow(FIELDS);writer.writerows(rows)
        paths,_=event_reference.source_chunks(folder/'events.csv',folder,chunk_rows=1)
        execute(folder,database,fixture_setup(rows));report,_=execute(folder,database,adjusted(sql,rows),readonly=True)
        stats,expected,_=compare_stream(folder,database,paths);assert report==expected
        assert report[17]['actual'] is None and all(row['actual']==0 for row in report[5:17]+report[18:])
        assert Counter(row['status'] for row in report)==Counter(PASS=8,INFO=13)
        cases.append(dict(case='valid_source_without_transactions_keeps_zero_counts_and_NULL_maximum',passed=True))
    assert not folder.exists()
    print(json.dumps({'fixture_families_passed':len(cases),'invalid_admission_subcases':7}),flush=True)
    if args.fixtures_only:return

    before={'events.csv':staging.snapshot(source)}
    assert before['events.csv']['sha256']==source_reference.SOURCE_SHA and before['events.csv']['size_bytes']==94237913
    historical={str(path.relative_to(root)):source_reference.sha256(path) for path in (root/'data').glob('*preflight.json') if path.resolve()!=output.resolve()}
    assert len(historical)==76
    with tempfile.TemporaryDirectory(prefix='rr-basket-grain-real-',dir=tmp_root) as temporary:
        folder,database=Path(temporary),Path(temporary)/'preflight.duckdb'
        started=time.perf_counter();paths,source_counts=event_reference.source_chunks(source,folder,chunk_rows=CHUNK_ROWS);sort_seconds=round(time.perf_counter()-started,3)
        assert source_counts==dict(rows=2756101,view=2664312,addtocart=69332,transaction=22457,null_transaction_ids=2733644)
        chunk_bytes=sum(path.stat().st_size for path in paths)
        print(json.dumps({'phase':'event-only source sorting complete'}),flush=True)
        _,build_seconds=execute(folder,database,'\n'.join(prefixes.values()))
        database_before=source_reference.sha256(database)
        report,query_seconds=execute(folder,database,sql,readonly=True)
        assert Counter(row['status'] for row in report)==Counter(PASS=8,INFO=13) and all(list(row)==OUTPUT for row in report)
        print(json.dumps({'phase':'SQL78 report passed','PASS':8,'INFO':13}),flush=True)
        stats,expected,stream_seconds=compare_stream(folder,database,paths)
        assert report==expected and stats['rows']==2756101 and stats['duplicate_surplus']==460
        assert len(stats['transaction_tuples'])==22457
        aggregate_counts={key:value for key,value in stats.items() if key!='transaction_tuples'}
        measured=diagnostics(stats['transaction_tuples'])
        database_after=source_reference.sha256(database);assert database_before==database_after
        database_bytes=database.stat().st_size
    assert not folder.exists()
    after={'events.csv':staging.snapshot(source)}
    assert before==after and all(source_reference.sha256(root/name)==digest for name,digest in hashes.items())
    assert all(source_reference.sha256(root/name)==digest for name,digest in historical.items())
    assert (root/method_path).read_bytes().startswith(contract)
    evidence=dict(checked_at_utc=datetime.now(timezone.utc).isoformat(),executor='assistant',
        engine=subprocess.check_output([args.duckdb,'-version'],text=True).strip(),
        script=script_path,script_sha256=hashes[script_path],validator=validator_path,validator_sha256=hashes[validator_path],
        code_and_dependency_sha256=hashes,method_contract=method_path,method_contract_prefix_bytes=len(contract),method_contract_prefix_sha256=CONTRACT_SHA,
        source_files=['events.csv'],source_before=before,source_after=after,source_hashes_and_metadata_unchanged=True,
        reconstruction_prefix_sha256={name:hashlib.sha256(code.encode()).hexdigest() for name,code in prefixes.items()},
        projection_scope='Original five-field rr_stg.events only; no enriched fact, property history, category reference or stored UTC projection.',
        source_table='rr_stg.events',readset_fields=FIELDS,required_readset_columns=5,
        property_files_read=False,category_csv_read=False,UTC_fields_read=False,full17_not_reverified=True,
        property_history_reconstructed=False,category_hierarchy_reverified=False,learner_database_opened=False,
        query_read_only=True,private_stream_read_only=True,real_source_attempts=1,real_cli_phases=3,
        real_reconstruction_executions=1,real_analysis_script_executions=1,real_private_stream_executions=1,
        report_rows=21,report_columns=5,output_columns=OUTPUT,checks_passed=8,info_rows=13,fail_rows=0,blocked_rows=0,
        results=report,report_sha256=report_hash(report),
        report_fingerprint_contract='SHA-256 of compact JSON arrays in output-column order followed by LF; counts are integers, missing expectations and undefined maximum are null.',
        independent_python_source_counts=source_counts,independent_python_aggregate_counts=aggregate_counts,
        independent_python_transaction_diagnostics=measured,independent_python_report_matched=True,
        independent_stream_occurrences_compared=stats['rows'],independent_stream_fields_compared=5,independent_stream_all_occurrences_matched=True,
        independent_original_event_fields_and_duplicates_preserved=True,candidate_basket_key=['visitorid','transactionid'],
        candidate_key_is_diagnostic_not_verified_business_order=True,source_duplicate_rows_deleted=False,
        repeated_item_records_treated_as_quantities=False,association_metrics_calculated=False,
        retained_transaction_occurrences=stats['transaction'],transaction_occurrence_retention_cap=TRANSACTION_CAP,
        private_database_sha256_before_readonly=database_before,private_database_sha256_after_readonly=database_after,private_database_bytes_unchanged=True,
        fixture_case_count=len(cases),fixture_cases=cases,invalid_admission_fixture_subcases=7,
        invalid_admission_blocks_all_actuals_verified=True,static_expectations_preserved_on_blocked_verified=True,
        additional_unqueried_columns_allowed_verified=True,empty_transaction_maximum_NULL_verified=True,
        preflight_settings=dict(threads=2,memory_limit='1GB',max_temp_directory_size='2GB',timeout_seconds_per_cli_phase=120,
            python_sort_chunk_rows=CHUNK_ROWS,transaction_occurrence_retention_cap=TRANSACTION_CAP,
            minimum_free_bytes=8*1024**3,private_directory_budget_bytes=7*1024**3),
        private_event_comparison_chunks=len(paths),private_event_comparison_chunk_bytes=chunk_bytes,
        private_database_bytes_before_cleanup=database_bytes,largest_private_directory_bytes_observed_after_phase=max(sizes),
        workspace_free_bytes_before=free_before,workspace_free_bytes_after=shutil.disk_usage(tmp_root).free,
        temporary_databases_and_spills_removed=True,private_source_comparison_spools_removed=True,
        historical_preflight_files_unchanged=len(historical),historical_comparison_or_analysis_suites_rerun=False,
        source_records_or_identifiers_uploaded_or_logged=False,
        elapsed_python_event_scan_sort_seconds=sort_seconds,elapsed_reconstruction_seconds=build_seconds,
        elapsed_readonly_basket_grain_seconds=query_seconds,elapsed_private_stream_seconds=stream_seconds,
        timing_scope='Three CLI phases: frozen event import/staging creation prefixes, read-only SQL78, read-only complete five-field stream and independent transaction diagnostics. Source sorting timed separately; hashing and fixtures excluded.',
        scope='Assistant SQL78 preparation passed; learner execution pending. Candidate transaction/basket grain diagnostics only; INFO is measurement rather than data failure. No verified business order semantics, automatic deduplication, quantity, monetary or association-effect claim.')
    output.write_text(json.dumps(evidence,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps({'report_rows':21,'checks_passed':8,'info_rows':13,'occurrences_compared':stats['rows'],
                      'fields_compared':5,'report_sha256':evidence['report_sha256']}),flush=True)


if __name__=='__main__':main()
