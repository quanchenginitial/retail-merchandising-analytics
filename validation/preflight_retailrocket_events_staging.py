"""Validate typed events with private bounded exact sorted-tuple comparisons."""
import argparse
import csv
import hashlib
import heapq
import json
import re
import shutil
import subprocess
import tempfile
import threading
import time
from collections import Counter
from contextlib import ExitStack
from datetime import datetime, timezone
from itertools import zip_longest
from pathlib import Path

import preflight_retailrocket_events_import as previous

FIELDS = previous.FIELDS
COLUMNS = previous.COLUMNS
CHECK_MARKER = '-- CHECKS: if rr_stg.events already exists, run only the query below.'
CONTRACT_SHA = '1eff15c9b102fa2196065f3065d61459e69efe110a0e021d2f4dc14f157641ed'
COUNT_SQL = ('SELECT 2756101::BIGINT AS expected_rows,2664312::BIGINT AS expected_views,\n'
             '        69332::BIGINT AS expected_carts,22457::BIGINT AS expected_transactions,\n'
             '        2733644::BIGINT AS expected_null_ids,460::BIGINT AS expected_duplicate_surplus')
CHECKS = ['staging_rows', 'column_count', 'schema_mismatch_count', 'missing_required_rows',
          'negative_numeric_rows', 'unexpected_event_rows', 'event_id_mismatch_rows',
          'view_rows', 'addtocart_rows', 'transaction_rows', 'null_transactionid_rows',
          'duplicate_surplus_rows', 'raw_rows', 'raw_value_violations', 'raw_schema_mismatch',
          'raw_duplicate_surplus', 'raw_only_rows', 'staging_only_rows',
          'raw_null_transactionid_rows', 'source_contract_violations']
EXPECTED = [2756101,5,0,0,0,0,0,2664312,69332,22457,2733644,460,2756101,0,0,460,0,0,2733644,0]
LIMIT = 9223372036854775807
CHUNK_ROWS = 50000
READ_ROWS = ('SELECT timestamp,visitorid,event,itemid,transactionid FROM rr_raw.events; '
             'SELECT timestamp,visitorid,event,itemid,transactionid FROM rr_stg.events;')


def canonical(value):
    return (isinstance(value, str) and re.fullmatch('[0-9]+', value) is not None
            and len(value) <= 19 and int(value) <= LIMIT and str(int(value)) == value)


def valid_row(row):
    return (all(canonical(row[i]) for i in [0,1,3])
            and (row[4] is None or canonical(row[4]))
            and row[2] in ('view','addtocart','transaction')
            and ((row[2]=='transaction') == (row[4] is not None)))


def typed(row):
    return tuple(int(value) if i != 2 and value is not None else value for i,value in enumerate(row))


def text_tuple(row):
    return tuple(str(value) if value is not None else None for value in row)


def json_outputs(text):
    decoder, results = json.JSONDecoder(), []
    while text.strip():
        text = text.lstrip()
        value, end = decoder.raw_decode(text)
        results.append(value)
        text = text[end:]
    return results


def tuples(records):
    return [tuple(row[field] for field in FIELDS) for row in records]


def counts(rows):
    events = Counter(row[2] for row in rows)
    return [len(rows),events['view'],events['addtocart'],events['transaction'],
            sum(row[4] is None for row in rows),len(rows)-len(set(rows))]


def adjusted(sql, rows, override=None):
    values = counts(rows)
    if override:
        for index, value in override.items():
            values[index] = value
    names = ['expected_rows','expected_views','expected_carts','expected_transactions','expected_null_ids','expected_duplicate_surplus']
    replacement = 'SELECT '+','.join(f'{v}::BIGINT AS {n}' for n,v in zip(names,values))
    assert sql.count(COUNT_SQL)==2
    return sql.replace(COUNT_SQL,replacement)


def report_reference(raw, staged):
    n, views, carts, transactions, nulls, duplicates = counts(raw)
    sn, sv, sc, st, sz, sd = counts(staged)
    r, s = Counter(raw), Counter(text_tuple(row) for row in staged)
    violation = sum(not valid_row(row) for row in raw)
    actual = [sn,5,0,sum(any(row[i] is None for i in [0,1,2,3]) or row[2]=='' for row in staged),
              sum(any(row[i] is not None and row[i]<0 for i in [0,1,3,4]) for row in staged),
              sum(row[2] not in ('view','addtocart','transaction') for row in staged),
              sum((row[2]=='transaction' and row[4] is None)
                  or (row[2] is not None and row[2]!='transaction' and row[4] is not None) for row in staged),
              sv,sc,st,sz,sd,n,violation,0,duplicates,sum((r-s).values()),sum((s-r).values()),nulls,
              int(n==0 or violation!=0)]
    expected = [n,5,0,0,0,0,0,views,carts,transactions,nulls,duplicates,n,0,0,duplicates,0,0,nulls,0]
    return make_report(actual,expected)


def make_report(actual, expected):
    return [dict(check_order=i,check_name=name,actual=value,expected=target,
                 status='PASS' if value==target else 'FAIL')
            for i,(name,value,target) in enumerate(zip(CHECKS,actual,expected),1)]


def setup(rows, schema=None):
    schema = schema or ','.join(field+' VARCHAR' for field in FIELDS)
    query = 'CREATE SCHEMA rr_raw; CREATE TABLE rr_raw.events ('+schema+');\n'
    if rows:
        literal = lambda value: 'NULL' if value is None else "'"+str(value).replace("'","''")+"'"
        query += 'INSERT INTO rr_raw.events VALUES '+','.join('('+','.join(map(literal,row))+')' for row in rows)+';\n'
    return query


def snapshot(path):
    stat = path.stat()
    return dict(size_bytes=stat.st_size,modified_time_ns=stat.st_mtime_ns,sha256=previous.sha256(path))


def sorted_source_chunks(source, folder, chunk_rows=CHUNK_ROWS):
    paths, chunk, events, total, nulls = [], [], Counter(), 0, 0
    def flush():
        chunk.sort()
        path = folder/f'comparison-{len(paths):04d}.csv'
        with path.open('w',encoding='utf-8',newline='') as output:
            csv.writer(output).writerows(chunk)
        paths.append(path)
        chunk.clear()
    with source.open('r',encoding='utf-8',newline='') as stream:
        reader = csv.reader(stream,strict=True)
        assert next(reader)==FIELDS,'Source header differs'
        for row in reader:
            assert len(row)==5,'Private source record width differs'
            logical = tuple([*row[:4],row[4] or None])
            assert valid_row(logical),'Private source fails canonical typing contract; record withheld'
            chunk.append(tuple(row))
            total += 1
            events[row[2]] += 1
            nulls += row[4]==''
            if len(chunk)==chunk_rows:
                flush()
        if chunk:
            flush()
    assert total>0
    return paths,dict(rows=total,event_counts=dict(events),null_ids=nulls)


def merged_source(paths):
    with ExitStack() as stack:
        streams = [stack.enter_context(path.open('r',encoding='utf-8',newline='')) for path in paths]
        readers = [map(tuple,csv.reader(stream,strict=True)) for stream in streams]
        yield from heapq.merge(*readers)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--duckdb',required=True)
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--fixtures-only',action='store_true')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    script_path = 'sql/63_stage_retailrocket_events.sql'
    validator_path = 'validation/preflight_retailrocket_events_staging.py'
    method_path = 'docs/RETAILROCKET_EVENTS_STAGING_VALIDATION.md'
    output = root/'data/retailrocket_events_staging_preflight.json'
    assert args.output.resolve()==output.resolve()
    dependencies = [script_path,validator_path,'sql/54_import_retailrocket_events.sql',
                    'validation/preflight_retailrocket_events_import.py','data/retailrocket_source_audit.json',
                    'data/retailrocket_independent_checks.json','data/retailrocket_events_import_preflight.json',
                    'data/retailrocket_events_import_learner_acceptance.json']
    hashes = {p:previous.sha256(root/p) for p in dependencies}
    contract = (root/method_path).read_bytes().split(b'\n## Executed results\n',1)[0]
    assert hashlib.sha256(contract).hexdigest()==CONTRACT_SHA
    sql = (root/script_path).read_text(encoding='utf-8')
    assert 'CREATE TABLE rr_stg.events AS' in sql and 'OR REPLACE' not in sql and 'CREATE TABLE IF NOT EXISTS' not in sql
    assert sql.count(CHECK_MARKER)==1 and sql.count('EXCEPT ALL')==2
    raw_sql = (root/'sql/54_import_retailrocket_events.sql').read_text(encoding='utf-8').split('-- CHECKS:',1)[0]
    assert raw_sql.count('read_csv(')==1 and 'EXCEPT ALL' not in raw_sql
    prior = json.loads((root/'data/retailrocket_events_import_preflight.json').read_text(encoding='utf-8'))
    accepted = json.loads((root/'data/retailrocket_events_import_learner_acceptance.json').read_text(encoding='utf-8'))
    assert prior['script_sha256']==hashes['sql/54_import_retailrocket_events.sql'] and prior['checks_passed']==18
    assert accepted['script_sha256']==prior['script_sha256'] and accepted['rows_with_pass_status']==18
    audit = json.loads((root/'data/retailrocket_source_audit.json').read_text(encoding='utf-8'))
    assert audit['all_checks_passed'] and audit['files']['events.csv']['sha256']==previous.SOURCE_SHA
    tmp_root = root/'tmp'
    tmp_root.mkdir(exist_ok=True)
    free_before = shutil.disk_usage(tmp_root).free
    assert free_before>=6*1024**3
    sizes = []

    def settings(folder, database):
        assert folder.resolve().is_relative_to(tmp_root.resolve())
        assert Path(database).resolve().is_relative_to(folder.resolve())
        spill = (folder/'spill').as_posix().replace("'","''")
        return f"SET threads=2; SET memory_limit='1GB'; SET max_temp_directory_size='2GB'; SET temp_directory='{spill}';\n"

    def observe_size(folder):
        size = sum(p.stat().st_size for p in folder.rglob('*') if p.is_file())
        assert size<=5*1024**3,'Private directory budget exceeded'
        sizes.append(size)
        return size

    def execute(folder, database, query, allow_error=False):
        started = time.perf_counter()
        run = subprocess.run([args.duckdb,str(database),'-bail','-json'],input=settings(folder,database)+query,
                             text=True,encoding='utf-8',capture_output=True,timeout=120)
        if not allow_error:
            assert run.returncode==0,'Private event staging execution failed; row-bearing diagnostics withheld'
        observe_size(folder)
        return run,round(time.perf_counter()-started,3)

    def compare_stream(folder, database, table, chunks):
        assert table in ('rr_raw.events','rr_stg.events')
        expressions = [f'CAST({field} AS VARCHAR)' if field!='transactionid' else "COALESCE(CAST(transactionid AS VARCHAR),'')" for field in FIELDS]
        query = 'SELECT '+','.join(expressions)+' FROM '+table+' ORDER BY 1,2,3,4,5;'
        started, timed_out = time.perf_counter(), threading.Event()
        process = subprocess.Popen([args.duckdb,str(database),'-bail','-csv','-noheader'],
                                   stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
                                   text=True,encoding='utf-8')
        def expire():
            timed_out.set()
            process.kill()
        timer = threading.Timer(120,expire)
        timer.start()
        rows, duplicates, last, sentinel = 0,0,None,object()
        try:
            process.stdin.write(settings(folder,database)+query)
            process.stdin.close()
            actual = csv.reader(process.stdout,strict=True)
            for observed, expected in zip_longest(actual,merged_source(chunks),fillvalue=sentinel):
                assert observed is not sentinel and expected is not sentinel,'Private comparison row count differs'
                assert tuple(observed)==expected,'Private full five-field tuple comparison differs; values withheld'
                duplicates += expected==last
                last, rows = expected, rows+1
            assert process.wait(timeout=120)==0 and not timed_out.is_set(),'Private streaming comparison failed or timed out'
        finally:
            timer.cancel()
            if process.poll() is None:
                process.kill()
                process.wait()
            process.stdout.close()
        observe_size(folder)
        return dict(rows=rows,fields=5,duplicate_surplus=duplicates,matched=True,elapsed_seconds=round(time.perf_counter()-started,3))

    cases = []
    fixture_rows = [('1','1','view','10',None),('1','1','view','10',None),
                    ('2','2','addtocart','20',None),('3','2','transaction','20','9'),
                    ('0','0','view','0',None),(str(LIMIT),str(LIMIT),'transaction',str(LIMIT),str(LIMIT)),
                    ('10','10','view','2',None)]
    with tempfile.TemporaryDirectory(prefix='rr-event-stage-fixture-',dir=tmp_root) as temporary:
        folder,database = Path(temporary),Path(temporary)/'fixture.duckdb'
        query = adjusted(sql,fixture_rows)
        run,_ = execute(folder,database,setup(fixture_rows)+query+'\n'+READ_ROWS)
        report,raw,staged = json_outputs(run.stdout)
        expected_stage = [typed(row) for row in fixture_rows]
        assert Counter(tuples(raw))==Counter(fixture_rows) and Counter(tuples(staged))==Counter(expected_stage)
        assert report==report_reference(fixture_rows,expected_stage) and all(r['status']=='PASS' for r in report)
        fixture_csv = folder/'synthetic.csv'
        with fixture_csv.open('w',encoding='utf-8',newline='') as stream:
            writer = csv.writer(stream)
            writer.writerow(FIELDS)
            writer.writerows(fixture_rows)
        fixture_chunks,fixture_counts = sorted_source_chunks(fixture_csv,folder,chunk_rows=2)
        assert len(fixture_chunks)==4
        assert [row[0] for row in merged_source(fixture_chunks)]==['0','1','1','10','2','3',str(LIMIT)]
        for table in ['rr_raw.events','rr_stg.events']:
            compared = compare_stream(folder,database,table,fixture_chunks)
            assert compared['rows']==7 and compared['duplicate_surplus']==1 and compared['matched']
        cases.append(dict(case='canonical_zero_max_bigint_null_duplicates_and_chunked_text_sort_streams_full_report',passed=True))

        changed = [tuple([*row[:3],999,row[4]]) if row[0]==2 else row for row in expected_stage]
        run,_ = execute(folder,database,'UPDATE rr_stg.events SET itemid=999 WHERE timestamp=2;\n'+query.split(CHECK_MARKER,1)[1]+'\n'+READ_ROWS)
        report,raw,staged = json_outputs(run.stdout)
        assert Counter(tuples(staged))==Counter(changed) and report==report_reference(fixture_rows,changed)
        assert report[0]['status']=='PASS' and report[11]['status']=='PASS'
        assert report[16]['actual']==report[17]['actual']==1
        run,_ = execute(folder,database,'DELETE FROM rr_stg.events WHERE rowid=(SELECT MIN(rowid) FROM rr_stg.events WHERE timestamp=1);\n'+query.split(CHECK_MARKER,1)[1]+'\n'+READ_ROWS)
        changed.remove(typed(fixture_rows[0]))
        report,raw,staged = json_outputs(run.stdout)
        assert Counter(tuples(staged))==Counter(changed) and report==report_reference(fixture_rows,changed)
        assert report[11]['actual']==0 and report[11]['expected']==1 and report[16]['actual']==2 and report[17]['actual']==1
        rejected,_ = execute(folder,database,query,allow_error=True)
        assert rejected.returncode!=0 and 'already exists' in rejected.stderr
        run,_ = execute(folder,database,READ_ROWS)
        raw,staged = json_outputs(run.stdout)
        assert Counter(tuples(raw))==Counter(fixture_rows) and Counter(tuples(staged))==Counter(changed)
        cases.append(dict(case='same_count_tuple_change_duplicate_loss_detected_existing_sentinel_preserved',passed=True))
    assert not folder.exists()

    base = ('1','1','view','1',None)
    def changed_field(index,value):
        row = list(base)
        row[index] = value
        return [tuple(row)]
    invalid = [('empty',[],None),('wrong_count',[base],{0:2}),
               ('isolated_leading_zero',changed_field(1,'01'),None),
               ('numeric_alias_pair',[base,('2','01','view','1',None)],None),
               ('whitespace',changed_field(0,' 1'),None),('plus_sign',changed_field(3,'+1'),None),
               ('decimal',changed_field(3,'1.0'),None),('non_ascii_digits',changed_field(3,'１'),None),
               ('overflow',changed_field(0,str(LIMIT+1)),None),('missing_required',changed_field(0,None),None),
               ('empty_required',changed_field(1,''),None),('empty_transaction_id',[('1','1','transaction','1','')],None),
               ('transaction_without_id',[('1','1','transaction','1',None)],None),
               ('nontransaction_with_id',changed_field(4,'9'),None),('unexpected_event',changed_field(2,'purchase'),None),
               ('negative',changed_field(3,'-1'),None),('wrong_event_counts',[base],{1:0,2:1}),
               ('wrong_duplicate_count',[base],{5:1}),('wrong_null_count',[base],{4:0})]
    with tempfile.TemporaryDirectory(prefix='rr-event-stage-reject-',dir=tmp_root) as temporary:
        folder = Path(temporary)
        for label,rows,override in invalid:
            database = folder/(label+'.duckdb')
            rejected,_ = execute(folder,database,setup(rows)+adjusted(sql,rows,override),allow_error=True)
            assert rejected.returncode!=0 and 'SQL63 raw event contract failed' in rejected.stderr,label
            run,_ = execute(folder,database,"SELECT COUNT(*) AS targets FROM information_schema.tables WHERE table_schema='rr_stg' AND table_name='events'; SELECT timestamp,visitorid,event,itemid,transactionid FROM rr_raw.events;")
            target,raw = json_outputs(run.stdout)
            assert target==[{'targets':0}] and Counter(tuples(raw))==Counter(rows),label
        for label,schema,physical in [
            ('wrong_type','timestamp BIGINT,visitorid VARCHAR,event VARCHAR,itemid VARCHAR,transactionid VARCHAR',[base]),
            ('wrong_order','visitorid VARCHAR,timestamp VARCHAR,event VARCHAR,itemid VARCHAR,transactionid VARCHAR',[('2','1','view','3',None)]),
        ]:
            logical = [(1,'1','view','1',None)] if label=='wrong_type' else [('1','2','view','3',None)]
            database = folder/(label+'.duckdb')
            rejected,_ = execute(folder,database,setup(physical,schema)+adjusted(sql,[text_tuple(r) for r in logical]),allow_error=True)
            assert rejected.returncode!=0 and 'SQL63 raw event contract failed' in rejected.stderr,label
            run,_ = execute(folder,database,"SELECT COUNT(*) AS targets FROM information_schema.tables WHERE table_schema='rr_stg' AND table_name='events'; SELECT timestamp,visitorid,event,itemid,transactionid FROM rr_raw.events;")
            target,raw = json_outputs(run.stdout)
            assert target==[{'targets':0}] and Counter(tuples(raw))==Counter(logical),label
        cases.append(dict(case='invalid_canonical_values_empty_counts_and_populated_schema_rejected_atomically',
                          subcases=[x[0] for x in invalid]+['wrong_type','wrong_order'],passed=True,expected_rejection=True))
    assert not folder.exists()
    print(json.dumps({'focused_cases_passed':len(cases),'rejection_subcases':len(invalid)+2}),flush=True)
    if args.fixtures_only:
        return

    source = Path(previous.SOURCE)
    before = snapshot(source)
    assert before['sha256']==previous.SOURCE_SHA and before['size_bytes']==94237913
    historical = {str(p.relative_to(root)):previous.sha256(p) for p in (root/'data').glob('*preflight.json') if p.resolve()!=output.resolve()}
    with tempfile.TemporaryDirectory(prefix='rr-event-stage-real-',dir=tmp_root) as temporary:
        folder,database = Path(temporary),Path(temporary)/'preflight.duckdb'
        started = time.perf_counter()
        chunks,source_counts = sorted_source_chunks(source,folder)
        source_sort_seconds = round(time.perf_counter()-started,3)
        assert source_counts==dict(rows=2756101,event_counts={'view':2664312,'addtocart':69332,'transaction':22457},null_ids=2733644)
        chunk_count,chunk_bytes = len(chunks),sum(p.stat().st_size for p in chunks)
        run,elapsed = execute(folder,database,raw_sql+'\n'+sql)
        report = json.loads(run.stdout)
        assert report==make_report(EXPECTED,EXPECTED)
        raw_compare = compare_stream(folder,database,'rr_raw.events',chunks)
        stage_compare = compare_stream(folder,database,'rr_stg.events',chunks)
        assert raw_compare['rows']==stage_compare['rows']==source_counts['rows']
        assert raw_compare['duplicate_surplus']==stage_compare['duplicate_surplus']==460
        independent = [source_counts['rows'],5,0,0,0,0,0,source_counts['event_counts']['view'],
                       source_counts['event_counts']['addtocart'],source_counts['event_counts']['transaction'],
                       source_counts['null_ids'],stage_compare['duplicate_surplus'],source_counts['rows'],0,0,
                       raw_compare['duplicate_surplus'],0,0,source_counts['null_ids'],0]
        assert report==make_report(independent,EXPECTED)
        database_bytes = database.stat().st_size
    assert not folder.exists()
    after = snapshot(source)
    assert before==after
    assert all(previous.sha256(root/p)==h for p,h in hashes.items())
    assert all(previous.sha256(root/p)==h for p,h in historical.items())
    assert (root/method_path).read_bytes().startswith(contract)
    evidence = dict(
        checked_at_utc=datetime.now(timezone.utc).isoformat(),executor='assistant',
        engine=subprocess.check_output([args.duckdb,'-version'],text=True).strip(),
        script=script_path,script_sha256=hashes[script_path],validator=validator_path,validator_sha256=hashes[validator_path],
        code_and_dependency_sha256=hashes,method_contract=method_path,method_contract_prefix_bytes=len(contract),method_contract_prefix_sha256=CONTRACT_SHA,
        source_files=['events.csv'],source_before={'events.csv':before},source_after={'events.csv':after},source_hashes_and_metadata_unchanged=True,
        reconstruction_prefix_sha256={'sql/54_import_retailrocket_events.sql':hashlib.sha256(raw_sql.encode()).hexdigest()},
        reconstruction_basis='Only frozen SQL54 import prefix; no previous full audit suites or learner database.',
        table='rr_stg.events',staging_fields=FIELDS,staging_types=['BIGINT','BIGINT','VARCHAR','BIGINT','BIGINT'],
        real_staging_script_executions=1,real_private_comparison_stream_executions=2,
        report_rows=20,report_columns=5,output_columns=COLUMNS,checks_passed=20,fail_rows=0,results=report,report_sha256=previous.report_hash(report),
        report_fingerprint_contract='SHA-256 of ordered compact JSON arrays in output-column order, each followed by LF; count fields are integers.',
        independent_python_source_counts=source_counts,independent_python_canonical_spelling_validated=True,
        independent_python_report_matched=True,independent_raw_stream=raw_compare,independent_staging_stream=stage_compare,
        independent_full_five_field_multiset_matched=True,independent_raw_input_unchanged=True,
        fixture_case_count=len(cases),fixture_cases=cases,rejection_subcase_count=len(invalid)+2,
        invalid_creation_destination_absence_verified=True,existing_destination_sentinel_preserved=True,
        same_count_changed_tuple_detected=True,lost_duplicate_occurrence_detected=True,
        preflight_settings=dict(threads=2,memory_limit='1GB',max_temp_directory_size='2GB',timeout_seconds_per_cli_phase=120,python_sort_chunk_rows=CHUNK_ROWS),
        private_source_comparison_chunks=chunk_count,private_source_comparison_chunk_bytes=chunk_bytes,
        private_comparison_spool_scope='Complete real source tuples were written only to private temporary sorted chunks, streamed against private raw/staged tables and removed with their owning directory. No identifiers enter public artifacts or logs.',
        workspace_free_bytes_before=free_before,workspace_free_bytes_after=shutil.disk_usage(tmp_root).free,
        private_database_bytes_before_cleanup=database_bytes,largest_private_directory_bytes_observed_after_phase=max(sizes),
        temporary_databases_and_spills_removed=True,private_source_comparison_spools_removed=True,
        learner_database_opened=False,other_source_csvs_read=False,historical_comparison_or_analysis_suites_rerun=False,
        historical_preflight_files_unchanged=len(historical),source_records_or_identifiers_uploaded_or_logged=False,
        elapsed_source_sort_seconds=source_sort_seconds,elapsed_import_stage_and_checks_seconds=elapsed,
        timing_scope='One real import/staging/check CLI phase and two private sorted comparison streams; source sorting and each stream recorded separately. Hashing/Python fixtures excluded; not a performance benchmark.',
        scope='Assistant typed-event staging passed; learner SQL63 pending. All original observations and NULL/duplicate multiplicities retained. No UTC/date derivation, deduplication decision, declared event PK, session/order/person definitions, historical property association, conversion or monetary metrics.')
    output.write_text(json.dumps(evidence,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps({'report_rows':20,'checks_passed':20,'source_rows_compared':source_counts['rows'],
                      'focused_cases_passed':len(cases),'elapsed_import_stage_checks_seconds':elapsed,'report_sha256':evidence['report_sha256']}),flush=True)


if __name__=='__main__':
    main()
