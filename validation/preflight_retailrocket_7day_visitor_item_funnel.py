"""Validate first-view-anchored seven-day pair progression with complete potential follow-up."""
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
from datetime import datetime, timezone, timedelta
from decimal import Decimal, ROUND_HALF_UP
from itertools import zip_longest
from pathlib import Path

import preflight_retailrocket_events_staging as staging
previous=staging.previous
CONTRACT_SHA='dced516c84c1e0f0191a1e8271369fac276ceb68685ba11b6f5a055ac1bb685e'
CHUNK_ROWS=50000
MAX_MS=253402300799999
WINDOW_MS=604800000
OBSERVATION_END_MS=1442545187788
LABELS=['VIEWED_ALL','EXCLUDED_INCOMPLETE_7D','ELIGIBLE_VIEW_7D','VIEW_THEN_CART_7D','VIEW_CART_TRANSACTION_7D']
FIELDS=staging.FIELDS
OUTPUT=['stage','visitor_item_pairs','share_of_eligible_pairs_pct','step_rate_pct','check_status']
PARAMETERS='''SELECT 2756101::BIGINT AS expected_rows,2664312::BIGINT AS expected_views,
        69332::BIGINT AS expected_carts,22457::BIGINT AS expected_transactions,
        460::BIGINT AS expected_duplicate_surplus,253402300799999::BIGINT AS max_supported_ms,
        604800000::BIGINT AS window_ms,1442545187788::BIGINT AS expected_observation_end_ms'''
PROJECTION="""CREATE SCHEMA rr_mart;
CREATE TABLE rr_mart.events_enriched AS SELECT timestamp,visitorid,event,itemid,transactionid FROM rr_stg.events;"""
STREAM="""SELECT timestamp,visitorid,event,itemid,COALESCE(CAST(transactionid AS VARCHAR),'__NULL__')
FROM rr_mart.events_enriched ORDER BY visitorid,itemid,timestamp,event,transactionid NULLS FIRST;"""

def key(row):
    return (row[1],row[3],row[0],row[2],-1 if row[4] is None else row[4])

def source_chunks(path,folder,chunk_rows=CHUNK_ROWS):
    paths,chunk=[],[]
    counts=dict(rows=0,view=0,addtocart=0,transaction=0,null_transaction_ids=0,observation_end_ms=None)
    def flush():
        chunk.sort(key=key)
        output=folder/f'pair-funnel-{len(paths):04d}.csv'
        with output.open('w',encoding='utf-8',newline='') as stream:
            csv.writer(stream).writerows(chunk)
        paths.append(output);chunk.clear()
    with path.open('r',encoding='utf-8',newline='') as stream:
        reader=csv.reader(stream,strict=True)
        assert next(reader)==staging.FIELDS
        for raw in reader:
            assert len(raw)==5
            logical=tuple(None if i==4 and value=='' else value for i,value in enumerate(raw))
            assert staging.valid_row(logical),'Private event source rules failed; values withheld'
            row=staging.typed(logical)
            assert row[0]<=MAX_MS
            counts['rows']+=1;counts[row[2]]+=1;counts['null_transaction_ids']+=row[4] is None
            counts['observation_end_ms']=row[0] if counts['observation_end_ms'] is None else max(counts['observation_end_ms'],row[0])
            chunk.append(row)
            if len(chunk)==chunk_rows:
                flush()
    if chunk:
        flush()
    assert counts['rows']>0
    return paths,counts

def merged_events(paths):
    def typed(reader):
        for row in reader:
            assert len(row)==5
            yield (int(row[0]),int(row[1]),row[2],int(row[3]),None if row[4]=='' else int(row[4]))
    with ExitStack() as stack:
        streams=[typed(csv.reader(stack.enter_context(path.open('r',encoding='utf-8',newline='')),strict=True)) for path in paths]
        yield from heapq.merge(*streams,key=key)

def utc_text(milliseconds):
    return (datetime(1970,1,1,tzinfo=timezone.utc)+timedelta(milliseconds=milliseconds)).strftime('%Y-%m-%dT%H:%M:%S.%fZ')

def blank_stats():
    return dict(rows=0,duplicate_surplus=0,observed_pairs=0,pairs_without_view=0,
                viewed_all_pairs=0,excluded_incomplete_pairs=0,eligible_viewed_pairs=0,
                view_then_cart_pairs=0,view_cart_transaction_pairs=0,
                maximum_simultaneous_pair_states=0,observed_max_timestamp_ms=None)

def expected_stream(paths,stats,observation_end_ms):
    prior=None;current_pair=None;first_view=None;deadline=None;eligible=False;first_cart=None;first_transaction=None
    def close_pair():
        stats['observed_pairs']+=1
        stats['pairs_without_view']+=first_view is None
        if first_view is not None:
            stats['viewed_all_pairs']+=1
            stats['excluded_incomplete_pairs']+=not eligible
            stats['eligible_viewed_pairs']+=eligible
        stats['view_then_cart_pairs']+=first_cart is not None
        stats['view_cart_transaction_pairs']+=first_transaction is not None
        assert first_cart is None or (eligible and first_view<first_cart<=deadline)
        assert first_transaction is None or (first_cart is not None and first_cart<first_transaction<=deadline)
    for row in merged_events(paths):
        pair=(row[1],row[3])
        if pair!=current_pair:
            if current_pair is not None:
                close_pair()
            current_pair=pair;first_view=None;deadline=None;eligible=False;first_cart=None;first_transaction=None
            stats['maximum_simultaneous_pair_states']=1
        timestamp,event=row[0],row[2]
        if event=='view' and first_view is None:
            first_view=timestamp;deadline=timestamp+WINDOW_MS;eligible=deadline<=observation_end_ms
        elif eligible and event=='addtocart' and first_view<timestamp<=deadline and first_cart is None:
            first_cart=timestamp
        elif eligible and event=='transaction' and first_cart is not None and first_cart<timestamp<=deadline and first_transaction is None:
            first_transaction=timestamp
        stats['rows']+=1;stats['duplicate_surplus']+=row==prior;prior=row
        stats['observed_max_timestamp_ms']=timestamp if stats['observed_max_timestamp_ms'] is None else max(stats['observed_max_timestamp_ms'],timestamp)
        yield row
    if current_pair is not None:
        close_pair()
    assert stats['observed_pairs']==stats['pairs_without_view']+stats['viewed_all_pairs']
    assert stats['viewed_all_pairs']==stats['excluded_incomplete_pairs']+stats['eligible_viewed_pairs']
    assert stats['observed_max_timestamp_ms']==observation_end_ms

def percent(numerator,denominator):
    if denominator is None or denominator==0:
        return None
    return format((Decimal(numerator)*100/Decimal(denominator)).quantize(Decimal('0.0001'),rounding=ROUND_HALF_UP),'.4f')

def reference_report(stats):
    counts=[stats['viewed_all_pairs'],stats['excluded_incomplete_pairs'],stats['eligible_viewed_pairs'],stats['view_then_cart_pairs'],stats['view_cart_transaction_pairs']]
    assert counts[0]==counts[1]+counts[2] and counts[2]>=counts[3]>=counts[4]>=0
    return [dict(zip(OUTPUT,[label,count,None if i<2 else percent(count,counts[2]),None if i<3 else percent(count,counts[i-1]),'PASS']))
            for i,(label,count) in enumerate(zip(LABELS,counts))]

def report_hash(report):
    return hashlib.sha256(''.join(json.dumps([row[name] for name in OUTPUT],ensure_ascii=False,separators=(',',':'))+'\n' for row in report).encode()).hexdigest()

def adjusted(sql,rows,override=None):
    counts=Counter(row[2] for row in rows)
    values=dict(expected_rows=len(rows),expected_views=counts['view'],expected_carts=counts['addtocart'],
                expected_transactions=counts['transaction'],expected_duplicate_surplus=len(rows)-len(set(rows)),max_supported_ms=MAX_MS,
                window_ms=WINDOW_MS,expected_observation_end_ms=max(row[0] for row in rows))
    values.update(override or {})
    assert sql.count(PARAMETERS)==1
    return sql.replace(PARAMETERS,'SELECT '+','.join(f'{value}::BIGINT AS {name}' for name,value in values.items()))

def fixture_setup(rows):
    query='CREATE SCHEMA rr_stg; CREATE TABLE rr_stg.events(timestamp BIGINT,visitorid BIGINT,event VARCHAR,itemid BIGINT,transactionid BIGINT);\n'
    def literal(value):
        return 'NULL' if value is None else "'"+str(value).replace("'","''")+"'"
    if rows:
        query+='INSERT INTO rr_stg.events VALUES '+','.join('('+','.join(literal(value) for value in row)+')' for row in rows)+';\n'
    return query+PROJECTION

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--duckdb',required=True)
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--fixtures-only',action='store_true')
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    script_path='sql/72_analyze_retailrocket_7day_visitor_item_funnel.sql'
    validator_path='validation/preflight_retailrocket_7day_visitor_item_funnel.py'
    method_path='docs/RETAILROCKET_7DAY_VISITOR_ITEM_FUNNEL_VALIDATION.md'
    output=root/'data/retailrocket_7day_visitor_item_funnel_preflight.json'
    assert args.output.resolve()==output.resolve()
    dependencies=[script_path,validator_path,'sql/54_import_retailrocket_events.sql','sql/63_stage_retailrocket_events.sql',
                  'sql/69_build_retailrocket_events_enriched.sql','validation/preflight_retailrocket_events_import.py',
                  'validation/preflight_retailrocket_events_staging.py',
                  'data/retailrocket_source_audit.json','data/retailrocket_event_time_preflight.json',
                  'sql/70_analyze_retailrocket_event_overview.sql','data/retailrocket_event_overview_preflight.json',
                  'data/retailrocket_event_overview_learner_acceptance.json','docs/RETAILROCKET_EVENT_OVERVIEW_VALIDATION.md',
                  'data/retailrocket_events_enriched_preflight.json','data/retailrocket_events_enriched_learner_acceptance.json',
                  'docs/RETAILROCKET_EVENTS_ENRICHED_VALIDATION.md','sql/71_analyze_retailrocket_visitor_item_funnel.sql',
                  'data/retailrocket_visitor_item_funnel_preflight.json','data/retailrocket_visitor_item_funnel_learner_acceptance.json',
                  'docs/RETAILROCKET_VISITOR_ITEM_FUNNEL_VALIDATION.md']
    hashes={name:previous.sha256(root/name) for name in dependencies}
    contract=(root/method_path).read_bytes().split(b'\n## Executed results\n',1)[0]
    assert hashlib.sha256(contract).hexdigest()==CONTRACT_SHA
    old=json.loads((root/'data/retailrocket_events_enriched_preflight.json').read_text(encoding='utf-8'))
    accepted=json.loads((root/'data/retailrocket_events_enriched_learner_acceptance.json').read_text(encoding='utf-8'))
    assert accepted['acceptance_status'].startswith('accepted') and accepted['report_sha256']==old['report_sha256']
    assert old['script_sha256']==hashes['sql/69_build_retailrocket_events_enriched.sql']
    overview=json.loads((root/'data/retailrocket_event_overview_preflight.json').read_text(encoding='utf-8'))
    accepted_overview=json.loads((root/'data/retailrocket_event_overview_learner_acceptance.json').read_text(encoding='utf-8'))
    assert accepted_overview['acceptance_status'].startswith('accepted') and accepted_overview['report_sha256']==overview['report_sha256']
    assert overview['script_sha256']==hashes['sql/70_analyze_retailrocket_event_overview.sql']
    prior_funnel=json.loads((root/'data/retailrocket_visitor_item_funnel_preflight.json').read_text(encoding='utf-8'))
    accepted_funnel=json.loads((root/'data/retailrocket_visitor_item_funnel_learner_acceptance.json').read_text(encoding='utf-8'))
    assert accepted_funnel['acceptance_status'].startswith('accepted') and accepted_funnel['report_sha256']==prior_funnel['report_sha256']
    assert prior_funnel['script_sha256']==hashes['sql/71_analyze_retailrocket_visitor_item_funnel.sql']
    sql=(root/script_path).read_text(encoding='utf-8')
    clean=re.sub(r'--[^\n]*','',sql)
    assert clean.lstrip().startswith('WITH ') and not re.search(r'\b(CREATE|INSERT|UPDATE|DELETE|DROP|ALTER|COPY|ATTACH|DETACH|SET)\b',clean,re.I)
    assert all(name not in clean for name in ['categoryid_value','available_value','event_timestamp_utc','event_date_utc','rr_core','rr_stg'])
    prefixes={
        'sql/54_import_retailrocket_events.sql':(root/'sql/54_import_retailrocket_events.sql').read_text(encoding='utf-8').split('-- CHECKS:',1)[0],
        'sql/63_stage_retailrocket_events.sql':(root/'sql/63_stage_retailrocket_events.sql').read_text(encoding='utf-8').split(staging.CHECK_MARKER,1)[0]}
    old_time=json.loads((root/'data/retailrocket_event_time_preflight.json').read_text(encoding='utf-8'))
    assert int(next(row for row in old_time['results'] if row['check_name']=='max_timestamp_ms')['actual'])==OBSERVATION_END_MS
    assert next(row for row in overview['results'] if row['event_type']=='TOTAL')['last_event_utc']==utc_text(OBSERVATION_END_MS)
    assert all(hashlib.sha256(code.encode()).hexdigest()==old_time['reconstruction_prefix_sha256'][name] for name,code in prefixes.items())
    assert all('EXCEPT ALL' not in code for code in prefixes.values())
    audit=json.loads((root/'data/retailrocket_source_audit.json').read_text(encoding='utf-8'))
    source=Path(previous.SOURCE)
    assert audit['files']['events.csv']['sha256']==previous.SOURCE_SHA
    tmp_root=root/'tmp';tmp_root.mkdir(exist_ok=True)
    free_before=shutil.disk_usage(tmp_root).free
    assert free_before>=6*1024**3
    sizes=[]
    def settings(folder,database):
        assert folder.resolve().is_relative_to(tmp_root.resolve()) and Path(database).resolve().is_relative_to(folder.resolve())
        spill=(folder/'spill').as_posix().replace("'","''")
        return f"SET threads=2; SET memory_limit='1GB'; SET max_temp_directory_size='2GB'; SET temp_directory='{spill}';\n"
    def observe(folder):
        size=sum(path.stat().st_size for path in folder.rglob('*') if path.is_file())
        assert size<=5*1024**3;sizes.append(size)
    def execute(folder,database,query,readonly=False):
        started=time.perf_counter()
        run=subprocess.run([args.duckdb,str(database),'-bail','-json']+(['-readonly'] if readonly else []),
                           input=settings(folder,database)+query,text=True,encoding='utf-8',capture_output=True,timeout=120)
        if run.returncode!=0:
            diagnostic=run.stderr.lower()
            category=next((name for name,patterns in [('out_of_memory',['out of memory','failed to allocate']),('disk_or_spill',['no space left','max_temp_directory_size']),
                ('parser',['parser error']),('binder',['binder error']),('invalid_input',['invalid input error'])] if any(pattern in diagnostic for pattern in patterns)),'unclassified_cli_error')
            raise AssertionError('Private pair-funnel CLI failure: '+category+'; row-bearing details withheld')
        observe(folder)
        return json.loads(run.stdout) if run.stdout.strip() else None,round(time.perf_counter()-started,3)
    def compare_stream(folder,database,paths,observation_end_ms):
        started=time.perf_counter();expired=threading.Event();stats=blank_stats();count=0;sentinel=object()
        process=subprocess.Popen([args.duckdb,str(database),'-bail','-readonly','-csv','-noheader'],stdin=subprocess.PIPE,
                                 stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,encoding='utf-8')
        def expire():
            expired.set();process.kill()
        timer=threading.Timer(120,expire);timer.start()
        try:
            process.stdin.write(settings(folder,database)+STREAM);process.stdin.close()
            for observed,wanted in zip_longest(csv.reader(process.stdout,strict=True),expected_stream(paths,stats,observation_end_ms),fillvalue=sentinel):
                assert observed is not sentinel and wanted is not sentinel,'Private five-field occurrence count differs'
                assert len(observed)==5
                actual=(int(observed[0]),int(observed[1]),observed[2],int(observed[3]),None if observed[4]=='__NULL__' else int(observed[4]))
                assert actual==wanted,'Private five-field occurrence differs; values withheld'
                count+=1
            assert process.wait(timeout=120)==0 and not expired.is_set()
        finally:
            timer.cancel()
            if process.poll() is None:
                process.kill();process.wait()
            process.stdout.close()
        assert count==stats['rows'];observe(folder)
        return stats,round(time.perf_counter()-started,3)

    w=WINDOW_MS
    fixture_rows=[
        (0,2,'view',2,None),(0,2,'view',2,None),(w-1,2,'addtocart',2,None),(w,2,'transaction',2,0),
        (0,2,'view',10,None),(w,2,'addtocart',10,None),(w+1,2,'transaction',10,1),
        (w,10,'view',2,None),(2*w-1,10,'addtocart',2,None),(2*w,10,'transaction',2,2),
        (w+1,10,'view',10,None),(w+2,10,'addtocart',10,None),(w+3,10,'transaction',10,3),
        (0,20,'view',2,None),(w+1,20,'addtocart',2,None),(w+2,20,'transaction',2,4),
        (0,20,'view',10,None),(0,20,'addtocart',10,None),(1,20,'transaction',10,5),
        (0,30,'view',2,None),(w-2,30,'addtocart',2,None),(w-2,30,'transaction',2,6),
        (0,30,'addtocart',10,None),(1,30,'transaction',10,7),(1,30,'view',10,None),(2,30,'addtocart',10,None),(3,30,'transaction',10,8),
        (2*w,40,'addtocart',2,None)]
    cases=[]
    def fixture_source(folder,rows):
        with (folder/'events.csv').open('w',encoding='utf-8',newline='') as stream:
            writer=csv.writer(stream);writer.writerow(staging.FIELDS);writer.writerows(reversed(rows))
        return source_chunks(folder/'events.csv',folder,chunk_rows=3)
    with tempfile.TemporaryDirectory(prefix='rr-7day-fixture-',dir=tmp_root) as temporary:
        folder,database=Path(temporary),Path(temporary)/'fixture.duckdb'
        paths,counts=fixture_source(folder,fixture_rows)
        execute(folder,database,fixture_setup(fixture_rows)+"ALTER TABLE rr_mart.events_enriched ADD COLUMN unqueried_fixture VARCHAR;")
        before_db=previous.sha256(database)
        report,_=execute(folder,database,adjusted(sql,fixture_rows),readonly=True)
        stats,_=compare_stream(folder,database,paths,counts['observation_end_ms'])
        assert report==reference_report(stats) and [row['check_status'] for row in report]==['PASS']*5
        assert previous.sha256(database)==before_db
        assert counts['observation_end_ms']==2*w and max(row[0] for row in fixture_rows if row[2]=='view')==w+1
        assert [row['visitor_item_pairs'] for row in report]==[8,1,7,5,3]
        assert [row['share_of_eligible_pairs_pct'] for row in report]==[None,None,'100.0000','71.4286','42.8571']
        assert [row['step_rate_pct'] for row in report]==[None,None,None,'71.4286','60.0000']
        assert stats['observed_pairs']==9 and stats['pairs_without_view']==1 and stats['duplicate_surplus']==1
        assert stats['maximum_simultaneous_pair_states']==1 and len(paths)==10
        cases.append(dict(case='inclusive_deadline_eligibility_plus_one_ms_incomplete_success_exclusion_no_cart_clock_reset_all_event_endpoint_ties',passed=True,
                          events=28,chunks=10,expected_stage_counts=[8,1,7,5,3],extra_unqueried_column_allowed=True))
        mutations=[
            ('empty_readset','DELETE FROM rr_mart.events_enriched;'),
            ('negative_identifier','UPDATE rr_mart.events_enriched SET visitorid=-1 WHERE visitorid=30;'),
            ('invalid_event',"UPDATE rr_mart.events_enriched SET event='other' WHERE visitorid=30 AND event='view';"),
            ('invalid_transaction_null',"UPDATE rr_mart.events_enriched SET transactionid=NULL WHERE event='transaction';"),
            ('negative_timestamp','UPDATE rr_mart.events_enriched SET timestamp=-1 WHERE visitorid=30;'),
            ('unsupported_timestamp',f'UPDATE rr_mart.events_enriched SET timestamp={MAX_MS+1} WHERE visitorid=30;'),
            ('missing_timestamp','UPDATE rr_mart.events_enriched SET timestamp=NULL WHERE visitorid=30;'),
            ('required_field_type','ALTER TABLE rr_mart.events_enriched ALTER COLUMN timestamp TYPE VARCHAR;')]
        for label,mutation in mutations:
            blocked,_=execute(folder,database,'BEGIN;'+mutation+adjusted(sql,fixture_rows)+'ROLLBACK;')
            assert [row['stage'] for row in blocked]==LABELS,label
            assert all(row['check_status']=='BLOCKED' and all(row[name] is None for name in OUTPUT[1:-1]) for row in blocked),label
        for name,value in [('expected_rows',29),('expected_duplicate_surplus',0),('expected_observation_end_ms',2*w+1)]:
            blocked,_=execute(folder,database,adjusted(sql,fixture_rows,{name:value}),readonly=True)
            assert all(row['check_status']=='BLOCKED' and all(row[field] is None for field in OUTPUT[1:-1]) for row in blocked)
        failed=subprocess.run([args.duckdb,str(database),'-bail','-json'],input=settings(folder,database)+'BEGIN;ALTER TABLE rr_mart.events_enriched DROP COLUMN visitorid;'+adjusted(sql,fixture_rows),
            text=True,encoding='utf-8',capture_output=True,timeout=120)
        assert failed.returncode!=0 and 'binder error' in failed.stderr.lower()
        cases.append(dict(case='invalid_admission_including_wrong_endpoint_blocks_all_metrics_and_missing_required_field_binds_fail',passed=True,
                          subcases=[row[0] for row in mutations]+['wrong_row_count','wrong_duplicate_count','wrong_expected_endpoint','missing_required_column']))
    assert not folder.exists()
    zero_cases=[('eligible_but_no_qualifying_cart',[(0,1,'view',1,None),(0,1,'addtocart',1,None),(1,1,'transaction',1,0),(w,2,'addtocart',2,None)],[1,0,1,0,0]),
                ('zero_eligible_despite_observed_chain',[(1,1,'view',1,None),(2,1,'addtocart',1,None),(3,1,'transaction',1,0),(w,2,'addtocart',2,None)],[1,1,0,0,0])]
    with tempfile.TemporaryDirectory(prefix='rr-7day-zero-',dir=tmp_root) as temporary:
        parent=Path(temporary)
        for label,rows,wanted_counts in zero_cases:
            folder=parent/label;folder.mkdir();database=folder/'fixture.duckdb'
            paths,counts=fixture_source(folder,rows)
            execute(folder,database,fixture_setup(rows))
            before_db=previous.sha256(database)
            report,_=execute(folder,database,adjusted(sql,rows),readonly=True)
            stats,_=compare_stream(folder,database,paths,counts['observation_end_ms'])
            assert report==reference_report(stats) and [row['visitor_item_pairs'] for row in report]==wanted_counts
            assert previous.sha256(database)==before_db
            if label=='zero_eligible_despite_observed_chain':
                assert all(row['share_of_eligible_pairs_pct'] is None and row['step_rate_pct'] is None for row in report)
            else:
                assert [row['step_rate_pct'] for row in report]==[None,None,None,'0.0000',None]
        cases.append(dict(case='zero_eligible_and_zero_cart_denominators_remain_NULL_where_undefined',passed=True,
                          subcases=[row[0] for row in zero_cases]))
    assert not parent.exists()
    print(json.dumps({'fixture_families_passed':len(cases),'invalid_subcases':12,'zero_denominator_subcases':2}),flush=True)
    if args.fixtures_only:
        return

    before={'events.csv':staging.snapshot(source)}
    assert before['events.csv']['sha256']==previous.SOURCE_SHA and before['events.csv']['size_bytes']==94237913
    historical={str(path.relative_to(root)):previous.sha256(path) for path in (root/'data').glob('*preflight.json') if path.resolve()!=output.resolve()}
    assert len(historical)==70
    with tempfile.TemporaryDirectory(prefix='rr-7day-real-',dir=tmp_root) as temporary:
        folder,database=Path(temporary),Path(temporary)/'preflight.duckdb'
        started=time.perf_counter();paths,source_counts=source_chunks(source,folder);sort_seconds=round(time.perf_counter()-started,3)
        assert source_counts==dict(rows=2756101,view=2664312,addtocart=69332,transaction=22457,null_transaction_ids=2733644,observation_end_ms=OBSERVATION_END_MS)
        chunk_bytes=sum(path.stat().st_size for path in paths)
        print(json.dumps({'phase':'event-only source sorting complete'}),flush=True)
        reconstruction='\n'.join(prefixes.values())+'\n'+PROJECTION
        _,reconstruction_seconds=execute(folder,database,reconstruction)
        database_before=previous.sha256(database)
        report,query_seconds=execute(folder,database,sql,readonly=True)
        assert [row['check_status'] for row in report]==['PASS']*5 and all(list(row)==OUTPUT for row in report)
        print(json.dumps({'phase':'SQL72 five-row seven-day funnel passed'}),flush=True)
        stats,stream_seconds=compare_stream(folder,database,paths,source_counts['observation_end_ms'])
        assert report==reference_report(stats) and stats['rows']==2756101 and stats['duplicate_surplus']==460
        database_after=previous.sha256(database);assert database_before==database_after
        database_bytes=database.stat().st_size
        aggregate_counts=dict(stats)
    assert not folder.exists()
    after={'events.csv':staging.snapshot(source)}
    assert before==after and all(previous.sha256(root/name)==digest for name,digest in hashes.items())
    assert all(previous.sha256(root/name)==digest for name,digest in historical.items())
    assert (root/method_path).read_bytes().startswith(contract)
    evidence=dict(checked_at_utc=datetime.now(timezone.utc).isoformat(),executor='assistant',
        engine=subprocess.check_output([args.duckdb,'-version'],text=True).strip(),
        script=script_path,script_sha256=hashes[script_path],validator=validator_path,validator_sha256=hashes[validator_path],
        code_and_dependency_sha256=hashes,method_contract=method_path,method_contract_prefix_bytes=len(contract),method_contract_prefix_sha256=CONTRACT_SHA,
        source_files=['events.csv'],source_before=before,source_after=after,source_hashes_and_metadata_unchanged=True,
        reconstruction_prefix_sha256={name:hashlib.sha256(code.encode()).hexdigest() for name,code in prefixes.items()},
        private_readset_projection_sql=PROJECTION,private_readset_projection_sha256=hashlib.sha256(PROJECTION.encode()).hexdigest(),
        projection_scope='Disposable original-five-column stand-in for SQL72 readset only; accepted SQL69 remains the evidence for the seventeen-column production fact. UTC and property fields are not reverified.',
        source_table='rr_mart.events_enriched',readset_fields=FIELDS,required_readset_columns=5,full17_not_reverified=True,
        property_files_read=False,category_csv_read=False,SQL69_rerun=False,SQL70_rerun=False,SQL71_rerun=False,UTC_fields_read=False,learner_database_opened=False,
        query_read_only=True,private_stream_read_only=True,real_source_attempts=1,real_reconstruction_executions=1,real_analysis_script_executions=1,real_private_stream_executions=1,
        report_rows=5,report_columns=5,output_columns=OUTPUT,checks_passed=5,fail_rows=0,blocked_rows=0,
        results=report,report_sha256=report_hash(report),report_fingerprint_contract='SHA-256 of compact JSON arrays in output-column order followed by LF; DECIMAL percentages are four-place JSON strings, integer counts remain integers, NULL rates remain JSON null.',
        independent_python_source_counts=source_counts,independent_python_aggregate_counts=aggregate_counts,
        independent_python_report_matched=True,independent_python_Decimal_rates_matched=True,independent_one_pair_streaming_state=True,strict_timestamp_order_verified=True,shared_first_view_deadline_verified=True,incomplete_followup_excluded_before_outcomes=True,
        window_ms=WINDOW_MS,observation_end_ms=source_counts['observation_end_ms'],observation_end_utc=utc_text(source_counts['observation_end_ms']),
        eligibility_cutoff_ms=source_counts['observation_end_ms']-WINDOW_MS,eligibility_cutoff_utc=utc_text(source_counts['observation_end_ms']-WINDOW_MS),
        actual_endpoint_matches_frozen_accepted_endpoint=True,cohort_partition_reconciled=True,
        independent_stream_occurrences_compared=stats['rows'],independent_stream_fields_compared=5,independent_stream_all_occurrences_matched=True,
        independent_original_event_fields_and_duplicates_preserved=True,
        maximum_simultaneous_pair_states=stats['maximum_simultaneous_pair_states'],
        private_database_sha256_before_readonly=database_before,private_database_sha256_after_readonly=database_after,private_database_bytes_unchanged=True,
        fixture_case_count=len(cases),fixture_cases=cases,invalid_fixture_subcase_count=12,zero_denominator_fixture_subcase_count=2,
        invalid_admission_blocks_all_metrics_verified=True,additional_unqueried_columns_allowed_verified=True,zero_denominator_NULLs_verified=True,
        preflight_settings=dict(threads=2,memory_limit='1GB',max_temp_directory_size='2GB',timeout_seconds_per_cli_phase=120,
                                python_sort_chunk_rows=CHUNK_ROWS,simultaneous_pair_state_budget=1,private_directory_budget_bytes=5*1024**3),
        private_event_comparison_chunks=len(paths),private_event_comparison_chunk_bytes=chunk_bytes,
        private_database_bytes_before_cleanup=database_bytes,largest_private_directory_bytes_observed_after_phase=max(sizes),
        workspace_free_bytes_before=free_before,workspace_free_bytes_after=shutil.disk_usage(tmp_root).free,
        temporary_databases_and_spills_removed=True,private_source_comparison_spools_removed=True,
        historical_preflight_files_unchanged=len(historical),historical_comparison_or_analysis_suites_rerun=False,
        source_records_or_identifiers_uploaded_or_logged=False,
        elapsed_python_event_scan_sort_seconds=sort_seconds,elapsed_reconstruction_seconds=reconstruction_seconds,
        elapsed_readonly_funnel_seconds=query_seconds,elapsed_private_stream_seconds=stream_seconds,
        timing_scope='Three CLI phases: event prefixes plus disposable five-field projection; read-only seven-day pair funnel; read-only five-field stream. Source sorting timed separately; hashing and fixtures excluded.',
        scope='Assistant SQL72 seven-day pair-funnel preflight passed; learner SQL72 pending. Fixed seven elapsed days from earliest observed view, complete potential follow-up cohort, both later stages share the inclusive view deadline and strict stage ordering. Global log end does not prove continuous capture; first observed is not first-ever. Seven days is chosen, not optimized. Not a person/session/order or causal conversion claim. Only original-five-field readset verified; UTC/property fields not reverified.')
    output.write_text(json.dumps(evidence,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps({'report_rows':5,'checks_passed':5,'occurrences_compared':stats['rows'],'fields_compared':5,'report_sha256':evidence['report_sha256']}),flush=True)

if __name__=='__main__':
    main()
