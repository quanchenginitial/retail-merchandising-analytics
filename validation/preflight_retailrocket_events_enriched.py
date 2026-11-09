"""Build and verify a persistent 17-field event fact against independent bounded CSV matching."""
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
from datetime import datetime, timezone, timedelta
from contextlib import contextmanager
from itertools import zip_longest
from pathlib import Path

import preflight_retailrocket_event_property_coverage as coverage
import preflight_retailrocket_event_time as event_time

histories=coverage.histories
events=coverage.events
previous=coverage.previous
FILES=coverage.FILES
COLUMNS=coverage.COLUMNS
MAX_MS=coverage.MAX_MS
CHUNK_ROWS=coverage.CHUNK_ROWS
HISTORY_CAP=coverage.HISTORY_CAP
CONTRACT_SHA='4ef7c43f3a4b8069c4cccb846fc159b54d65cf7a6766deda1da2cf3ca04ff689'
ORIGINAL_CONTRACT_SHA='429c848a03ae1e3f1c965e6af8741c22582683b1bcd6f2f761ea2fb18676c644'
CHECK_MARKER='-- CHECKS: if rr_mart.events_enriched already exists, run only the query below.'
CHECKS=coverage.CHECKS[:12]+['fact_rows','fact_schema_mismatch','invalid_fact_rows','fact_duplicate_surplus',
    'expected_only_rows','fact_only_rows','timestamp_roundtrip_errors','utc_date_errors']+coverage.CHECKS[20:]
EVENT_SCHEMA=coverage.EVENT_SCHEMA
INTERVAL_SCHEMA=coverage.INTERVAL_SCHEMA
PRIVATE_SELECT=coverage.PRIVATE_SELECT.replace('available_coverage\n    FROM classified',
    "available_coverage,strftime(event_timestamp_utc,'%Y-%m-%dT%H:%M:%S.%fZ'),CAST(event_date_utc AS VARCHAR)\n    FROM rr_mart.events_enriched")
assert 'FROM rr_mart.events_enriched' in PRIVATE_SELECT

def adjusted(sql,event_rows,interval_rows,override=None):
    parts=sql.split(CHECK_MARKER)
    assert len(parts) in (1,2)
    return CHECK_MARKER.join(coverage.adjusted(part,event_rows,interval_rows,override) for part in parts)

def expected_matches(event_paths,property_paths,stats,interval_stats,history_cap=HISTORY_CAP):
    for row in coverage.expected_matches(event_paths,property_paths,stats,interval_stats,history_cap):
        dt=event_time.utc(row[0])
        assert event_time.recover(dt)==row[0]
        yield row+(dt.strftime(event_time.FORMAT),dt.date().isoformat())

def parse_wide(row):
    assert len(row)==17,'Private fact stream width differs'
    return coverage.parse_wide(row[:15])+tuple(row[15:])

def healthy_report(source_counts,interval_stats,match_stats):
    old=coverage.healthy_report(source_counts,interval_stats,match_stats)
    count=match_stats['event_rows']
    actual=[row['actual'] for row in old[:12]]+[count,0,0,match_stats['event_duplicate_surplus'],0,0,0,0]+[row['actual'] for row in old[20:]]
    expected=actual[:20]+[None]*8
    return [dict(check_order=i,check_name=n,actual=a,expected=e,status='INFO' if e is None else 'PASS')
            for i,(n,a,e) in enumerate(zip(CHECKS,actual,expected),1)]

blank_match_stats=coverage.blank_match_stats
event_chunks=coverage.event_chunks
setup=coverage.setup


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--duckdb',required=True)
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--fixtures-only',action='store_true')
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    script_path='sql/69_build_retailrocket_events_enriched.sql'
    validator_path='validation/preflight_retailrocket_events_enriched.py'
    method_path='docs/RETAILROCKET_EVENTS_ENRICHED_VALIDATION.md'
    output=root/'data/retailrocket_events_enriched_preflight.json'
    assert args.output.resolve()==output.resolve()
    dependencies=[script_path,validator_path,'sql/56_import_retailrocket_properties.sql','sql/65_stage_retailrocket_item_state_observations.sql',
                  'sql/67_build_retailrocket_item_state_intervals.sql','sql/54_import_retailrocket_events.sql','sql/63_stage_retailrocket_events.sql',
                  'validation/preflight_retailrocket_item_state_intervals.py','validation/preflight_retailrocket_item_state_observations.py',
                  'validation/preflight_retailrocket_properties_import.py','validation/preflight_retailrocket_events_staging.py',
                  'validation/preflight_retailrocket_events_import.py','data/retailrocket_source_audit.json',
                  'data/retailrocket_item_state_intervals_preflight.json','data/retailrocket_item_state_intervals_learner_acceptance.json',
                  'docs/RETAILROCKET_ITEM_STATE_INTERVALS_VALIDATION.md','data/retailrocket_events_staging_preflight.json',
                  'data/retailrocket_events_staging_learner_acceptance.json','data/retailrocket_event_time_preflight.json','validation/preflight_retailrocket_event_time.py',
                  'sql/68_audit_retailrocket_event_property_coverage.sql','validation/preflight_retailrocket_event_property_coverage.py',
                  'data/retailrocket_event_property_coverage_preflight.json','data/retailrocket_event_property_coverage_learner_acceptance.json',
                  'docs/RETAILROCKET_EVENT_PROPERTY_COVERAGE_VALIDATION.md']
    hashes={path:previous.sha256(root/path) for path in dependencies}
    contract=(root/method_path).read_bytes().split(b'\n## Executed results\n',1)[0]
    assert hashlib.sha256(contract).hexdigest()==CONTRACT_SHA
    assert hashlib.sha256(contract[:10590]).hexdigest()==ORIGINAL_CONTRACT_SHA
    sql=(root/script_path).read_text(encoding='utf-8')
    cleaned=re.sub(r'--[^\n]*','',sql)
    assert sql.count(CHECK_MARKER)==1 and sql.count('ASOF LEFT JOIN')==4
    creation,checks=sql.split(CHECK_MARKER)
    assert 'CREATE TABLE rr_mart.events_enriched AS' in creation
    assert not re.search(r'\b(REPLACE|DROP|INSERT|UPDATE|DELETE|ATTACH|DETACH|SET)\b',cleaned,re.I)
    assert not re.search(r'\b(CREATE|ALTER|COPY)\b',re.sub(r'--[^\n]*','',checks),re.I)
    old_coverage=json.loads((root/'data/retailrocket_event_property_coverage_preflight.json').read_text(encoding='utf-8'))
    accepted_coverage=json.loads((root/'data/retailrocket_event_property_coverage_learner_acceptance.json').read_text(encoding='utf-8'))
    assert accepted_coverage['acceptance_status'].startswith('accepted') and accepted_coverage['report_sha256']==old_coverage['report_sha256']
    assert old_coverage['script_sha256']==hashes['sql/68_audit_retailrocket_event_property_coverage.sql']
    assert old_coverage['validator_sha256']==hashes['validation/preflight_retailrocket_event_property_coverage.py']
    prefixes={
        'sql/56_import_retailrocket_properties.sql':(root/'sql/56_import_retailrocket_properties.sql').read_text(encoding='utf-8').split('-- CHECKS:',1)[0],
        'sql/65_stage_retailrocket_item_state_observations.sql':(root/'sql/65_stage_retailrocket_item_state_observations.sql').read_text(encoding='utf-8').split(histories.staging.CHECK_MARKER,1)[0],
        'sql/67_build_retailrocket_item_state_intervals.sql':(root/'sql/67_build_retailrocket_item_state_intervals.sql').read_text(encoding='utf-8').split(histories.CHECK_MARKER,1)[0],
        'sql/54_import_retailrocket_events.sql':(root/'sql/54_import_retailrocket_events.sql').read_text(encoding='utf-8').split('-- CHECKS:',1)[0],
        'sql/63_stage_retailrocket_events.sql':(root/'sql/63_stage_retailrocket_events.sql').read_text(encoding='utf-8').split(events.CHECK_MARKER,1)[0]}
    old_intervals=json.loads((root/'data/retailrocket_item_state_intervals_preflight.json').read_text(encoding='utf-8'))
    old_events=json.loads((root/'data/retailrocket_events_staging_preflight.json').read_text(encoding='utf-8'))
    old_event_time=json.loads((root/'data/retailrocket_event_time_preflight.json').read_text(encoding='utf-8'))
    assert old_intervals['script_sha256']==hashes['sql/67_build_retailrocket_item_state_intervals.sql']
    assert old_events['script_sha256']==hashes['sql/63_stage_retailrocket_events.sql']
    for old in [old_intervals,old_event_time]:
        for path,digest in old['reconstruction_prefix_sha256'].items():
            assert hashlib.sha256(prefixes[path].encode()).hexdigest()==digest
    for label,old in [('item_state_intervals',old_intervals),('events_staging',old_events)]:
        accepted=json.loads((root/f'data/retailrocket_{label}_learner_acceptance.json').read_text(encoding='utf-8'))
        assert accepted['acceptance_status']=='accepted' and accepted['report_sha256']==old['report_sha256']
    assert all('EXCEPT ALL' not in text for text in prefixes.values())
    audit=json.loads((root/'data/retailrocket_source_audit.json').read_text(encoding='utf-8'))
    assert audit['all_checks_passed']
    source_paths={name:previous.SOURCE_DIR/name for name in previous.FILES}
    source_paths['events.csv']=Path(events.previous.SOURCE)
    source_hashes={**previous.SOURCE_HASHES,'events.csv':events.previous.SOURCE_SHA}
    for name in FILES:
        assert audit['files'][name]['sha256']==source_hashes[name]
    tmp_root=root/'tmp';tmp_root.mkdir(exist_ok=True)
    free_before=shutil.disk_usage(tmp_root).free
    assert free_before>=8*1024**3
    sizes=[]

    def settings(folder,database,enlarged=False):
        assert folder.resolve().is_relative_to(tmp_root.resolve()) and Path(database).resolve().is_relative_to(folder.resolve())
        spill=(folder/'spill').as_posix().replace("'","''")
        memory,spill_cap=('2GB','4GB') if enlarged else ('1GB','2GB')
        return f"SET threads=2; SET memory_limit='{memory}'; SET max_temp_directory_size='{spill_cap}'; SET temp_directory='{spill}';\n"

    def observe(folder):
        size=sum(path.stat().st_size for path in folder.rglob('*') if path.is_file())
        assert size<=7*1024**3
        sizes.append(size)

    def execute(folder,database,query,readonly=False,enlarged=False):
        started=time.perf_counter()
        run=subprocess.run([args.duckdb,str(database),'-bail','-json']+(['-readonly'] if readonly else []),
                           input=settings(folder,database,enlarged)+query,text=True,encoding='utf-8',capture_output=True,timeout=120)
        if run.returncode!=0:
            diagnostic=run.stderr.lower()
            category=next((name for name,patterns in [
                ('out_of_memory',['out of memory','failed to allocate','could not allocate']),
                ('disk_or_spill',['no space left','max_temp_directory_size','failed to offload']),
                ('parser',['parser error']),('binder',['binder error']),('invalid_input',['invalid input error']),
                ('io',['io error'])] if any(pattern in diagnostic for pattern in patterns)),'unclassified_cli_error')
            print(json.dumps({'failure_category':category,'creation_complete_marker_reached':'SQL69_CREATION_COMPLETE' in run.stdout,
                              'returncode':run.returncode,'row_diagnostics_withheld':True}),flush=True)
            raise AssertionError('Private CLI phase failed: '+category+'; row-bearing diagnostics withheld')
        observe(folder)
        return run,round(time.perf_counter()-started,3)

    def compare_stream(folder,database,query,event_paths,property_paths):
        started,timed_out=time.perf_counter(),threading.Event()
        private_query=PRIVATE_SELECT
        process=subprocess.Popen([args.duckdb,str(database),'-bail','-readonly','-csv','-noheader'],stdin=subprocess.PIPE,
                                 stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,encoding='utf-8')
        def expire():
            timed_out.set();process.kill()
        timer=threading.Timer(120,expire);timer.start()
        match_stats=blank_match_stats();interval_stats=histories.blank_interval_stats();sentinel=object();count=0
        try:
            process.stdin.write(settings(folder,database)+private_query);process.stdin.close()
            expected=expected_matches(event_paths,property_paths,match_stats,interval_stats)
            for observed,wanted in zip_longest(csv.reader(process.stdout,strict=True),expected,fillvalue=sentinel):
                assert observed is not sentinel and wanted is not sentinel,'Private coverage occurrence count differs'
                assert parse_wide(observed)==wanted,'Private 17-field persisted fact occurrence differs; values withheld'
                count+=1
            assert process.wait(timeout=120)==0 and not timed_out.is_set(),'Private coverage stream failed or timed out'
        finally:
            timer.cancel()
            if process.poll() is None:
                process.kill();process.wait()
            process.stdout.close()
        assert count==match_stats['event_rows']
        observe(folder)
        return match_stats,interval_stats,round(time.perf_counter()-started,3)

    p1,p2=previous.FILES
    fixture_properties=[(1,2,'categoryid','001',p1),(5,2,'categoryid','7',p2),(3,2,'available','1',p1),
                        (7,2,'available','0',p2),(2,10,'categoryid','999999',p1),(0,20,'available','1',p2)]
    fixture_events=[(0,1,'view',2,None),(1,1,'view',2,None),(3,2,'addtocart',2,None),(5,3,'transaction',2,0),
                    (7,4,'view',2,None),(10,5,'view',2,None),(1,6,'view',10,None),(2,6,'view',10,None),
                    (2,6,'view',10,None),(9,7,'view',99,None),(0,8,'view',20,None),(86400001,9,'view',2,None)]
    fixture_interval_stats=histories.blank_interval_stats()
    fixture_intervals=list(histories.expected_intervals(sorted(histories.ordered_source(row) for row in fixture_properties),fixture_interval_stats))
    cases=[]
    with tempfile.TemporaryDirectory(prefix='rr-enriched-fixture-',dir=tmp_root) as temporary:
        folder,database=Path(temporary),Path(temporary)/'fixture.duckdb'
        parts=[[tuple(str(value) for value in row[:4]) for row in fixture_properties if row[4]==name] for name in previous.FILES]
        parts[0].append(('0','100','999','opaque'))
        previous.write_fixture(folder,parts)
        with (folder/'events.csv').open('w',encoding='utf-8',newline='') as stream:
            writer=csv.writer(stream);writer.writerow(events.FIELDS);writer.writerows(reversed(fixture_events))
        property_paths,property_counts=histories.sorted_source_chunks(folder,folder,chunk_rows=2)
        event_paths,event_counts=event_chunks(folder/'events.csv',folder,chunk_rows=2)
        assert len(property_paths)==3 and len(event_paths)==6
        expected_stats=blank_match_stats();expected_interval_stats=histories.blank_interval_stats()
        expected_rows=list(expected_matches(event_paths,property_paths,expected_stats,expected_interval_stats))
        assert len(expected_rows)==12 and expected_stats['event_duplicate_surplus']==1
        assert expected_stats['maximum_current_event_item_history_rows']==4
        assert next(row for row in expected_rows if row[0]==86400001)[15:]==('1970-01-02T00:00:00.001000Z','1970-01-02')
        assert next(row for row in expected_rows if row[0]==0)[15:]==('1970-01-01T00:00:00.000000Z','1970-01-01')
        assert expected_stats['categoryid_matched_rows']==8 and expected_stats['categoryid_before_first_rows']==2 and expected_stats['categoryid_no_history_rows']==2
        assert expected_stats['available_matched_rows']==6 and expected_stats['available_before_first_rows']==2 and expected_stats['available_no_history_rows']==4
        query=adjusted(sql,fixture_events,fixture_intervals)
        run,_=execute(folder,database,setup(fixture_events,fixture_intervals)+query)
        report=json.loads(run.stdout)
        source_counts=dict(event_rows=12,categoryid=3,available=3)
        assert report==healthy_report(source_counts,expected_interval_stats,expected_stats)
        before_db=previous.sha256(database)
        compared,compared_intervals,_=compare_stream(folder,database,query,event_paths,property_paths)
        assert compared==expected_stats and compared_intervals==expected_interval_stats
        rerun,_=execute(folder,database,query.split(CHECK_MARKER)[1],readonly=True)
        assert json.loads(rerun.stdout)==report and previous.sha256(database)==before_db
        cases.append(dict(case='persisted_17_fields_numeric_chunks_coverage_boundaries_duplicates_null_transactions_UTC_milliseconds_and_midnight',passed=True,
                          fixture_events=12,fixture_intervals=6,event_chunks=6,property_chunks=3))
        # Failure must leave an existing target and its full content intact.
        failed=subprocess.run([args.duckdb,str(database),'-bail','-json'],input=settings(folder,database)+query.split(CHECK_MARKER)[0],
            text=True,encoding='utf-8',capture_output=True,timeout=120)
        assert failed.returncode!=0 and 'already exists' in failed.stderr.lower()
        assert previous.sha256(database)==before_db
        cases.append(dict(case='existing_target_creation_rejected_without_change',passed=True))
        mutations=[
            ('original_event',"UPDATE rr_mart.events_enriched SET visitorid=visitorid+100 WHERE timestamp=86400001;",'expected_only_rows'),
            ('property_provenance',"UPDATE rr_mart.events_enriched SET categoryid_source_file='item_properties_part1.csv' WHERE timestamp=86400001;",'expected_only_rows'),
            ('coverage',"UPDATE rr_mart.events_enriched SET categoryid_coverage='BEFORE_FIRST' WHERE timestamp=86400001;",'invalid_fact_rows'),
            ('utc_timestamp',"UPDATE rr_mart.events_enriched SET event_timestamp_utc=event_timestamp_utc+INTERVAL 1 MILLISECOND WHERE timestamp=86400001;",'timestamp_roundtrip_errors'),
            ('utc_date',"UPDATE rr_mart.events_enriched SET event_date_utc=event_date_utc+1 WHERE timestamp=86400001;",'utc_date_errors'),
            ('fact_schema',"ALTER TABLE rr_mart.events_enriched ALTER COLUMN event_timestamp_utc TYPE VARCHAR;",'fact_schema_mismatch')]
        for label,mutation,failed_check in mutations:
            run,_=execute(folder,database,'BEGIN TRANSACTION;'+mutation+query.split(CHECK_MARKER)[1]+'ROLLBACK;')
            mutated=json.loads(run.stdout)
            assert next(row for row in mutated if row['check_name']==failed_check)['status']=='FAIL',label
            assert all(row['actual'] is None and row['status']=='BLOCKED' for row in mutated[20:]),label
            if label!='fact_schema':
                assert all(next(row for row in mutated if row['check_name']==name)['actual']>0 for name in ['expected_only_rows','fact_only_rows']),label
        cases.append(dict(case='same_count_fact_content_UTC_and_schema_mutations_detected_INFO_blocked',passed=True,subcases=[case[0] for case in mutations]))
    assert not folder.exists()

    def replace_interval(index,field,value):
        changed=list(fixture_intervals)
        row=list(changed[index]);row[field]=value;changed[index]=tuple(row)
        return changed
    cat_first=next(index for index,row in enumerate(fixture_intervals) if row[:2]==(2,'categoryid') and row[3]==1)
    cat_last=next(index for index,row in enumerate(fixture_intervals) if row[:2]==(2,'categoryid') and row[3]==5)
    invalid=[
        ('empty_events',[],fixture_intervals,None,EVENT_SCHEMA,INTERVAL_SCHEMA),
        ('empty_intervals',fixture_events,[],None,EVENT_SCHEMA,INTERVAL_SCHEMA),
        ('wrong_event_count',fixture_events,fixture_intervals,{'events':13},EVENT_SCHEMA,INTERVAL_SCHEMA),
        ('wrong_duplicate_count',fixture_events,fixture_intervals,{'duplicates':0},EVENT_SCHEMA,INTERVAL_SCHEMA),
        ('null_event_time',[(None,*fixture_events[0][1:])]+fixture_events[1:],fixture_intervals,None,EVENT_SCHEMA,INTERVAL_SCHEMA),
        ('negative_event_item',[(0,1,'view',-1,None)]+fixture_events[1:],fixture_intervals,None,EVENT_SCHEMA,INTERVAL_SCHEMA),
        ('wrong_event_type',[(str(row[0]),*row[1:]) for row in fixture_events],fixture_intervals,None,[('timestamp','VARCHAR')]+EVENT_SCHEMA[1:],INTERVAL_SCHEMA),
        ('wrong_interval_order',fixture_events,fixture_intervals,None,EVENT_SCHEMA,[INTERVAL_SCHEMA[1],INTERVAL_SCHEMA[0],*INTERVAL_SCHEMA[2:]]),
        ('duplicate_interval_key',fixture_events,fixture_intervals+[fixture_intervals[cat_first]],None,EVENT_SCHEMA,INTERVAL_SCHEMA),
        ('overlapping_chain',fixture_events,replace_interval(cat_first,4,6),None,EVENT_SCHEMA,INTERVAL_SCHEMA),
        ('gapped_chain',fixture_events,replace_interval(cat_first,4,4),None,EVENT_SCHEMA,INTERVAL_SCHEMA),
        ('closed_final_tail',fixture_events,replace_interval(cat_last,4,10),None,EVENT_SCHEMA,INTERVAL_SCHEMA),
        ('invalid_interval_value',fixture_events,replace_interval(cat_first,2,'bad'),None,EVENT_SCHEMA,INTERVAL_SCHEMA),
        ('unknown_provenance',fixture_events,replace_interval(cat_first,5,'unknown.csv'),None,EVENT_SCHEMA,INTERVAL_SCHEMA)]
    with tempfile.TemporaryDirectory(prefix='rr-enriched-invalid-',dir=tmp_root) as temporary:
        folder=Path(temporary)
        for label,erows,irows,override,eschema,ischema in invalid:
            database=folder/(label+'.duckdb')
            execute(folder,database,setup(erows,irows,eschema,ischema))
            creation_query=adjusted(creation,erows,irows,override)
            failed=subprocess.run([args.duckdb,str(database),'-bail','-json'],input=settings(folder,database)+creation_query,
                text=True,encoding='utf-8',capture_output=True,timeout=120)
            assert failed.returncode!=0 and 'SQL69 source contract failed' in failed.stderr,label
            run,_=execute(folder,database,"SELECT COUNT(*) AS tables FROM information_schema.tables WHERE table_schema='rr_mart' AND table_name='events_enriched';",readonly=True)
            assert json.loads(run.stdout)==[{'tables':0}],label
            # A diagnostic target permits checks-only verification without granting source admission.
            execute(folder,database,"CREATE TABLE rr_mart.events_enriched AS SELECT * FROM ("+
                "SELECT NULL::BIGINT AS timestamp,NULL::BIGINT AS visitorid,NULL::VARCHAR AS event,NULL::BIGINT AS itemid,NULL::BIGINT AS transactionid,"+
                ",".join("NULL::"+kind+" AS "+prop+suffix for prop in ['categoryid','available'] for suffix,kind in [('_value','VARCHAR'),('_from_ms','BIGINT'),('_to_ms','BIGINT'),('_source_file','VARCHAR'),('_coverage','VARCHAR')])+
                ",NULL::TIMESTAMP AS event_timestamp_utc,NULL::DATE AS event_date_utc) WHERE false;")
            before_db=previous.sha256(database)
            run,_=execute(folder,database,adjusted(checks,erows,irows,override),readonly=True)
            blocked=json.loads(run.stdout)
            assert next(row for row in blocked if row['check_name']=='source_contract_violations')['actual']==1,label
            assert all(row['actual'] is None and row['status']=='BLOCKED' for row in blocked[12:]),label
            assert previous.sha256(database)==before_db,label
        cases.append(dict(case='invalid_input_creation_atomic_and_checks_only_dependencies_blocked',passed=True,subcases=[case[0] for case in invalid]))
    assert not folder.exists()
    print(json.dumps({'fixture_families_passed':len(cases),'invalid_prerequisite_subcases':len(invalid),'fact_mutation_subcases':len(mutations)}),flush=True)
    if args.fixtures_only:
        return

    before={name:previous.snapshot(path) for name,path in source_paths.items()}
    assert all(before[name]['sha256']==source_hashes[name] for name in FILES)
    assert sum(before[name]['size_bytes'] for name in FILES)==987483569
    historical={str(path.relative_to(root)):previous.sha256(path) for path in (root/'data').glob('*preflight.json') if path.resolve()!=output.resolve()}
    assert len(historical)==67
    print(json.dumps({'phase':'fresh source hashes checked','historical_preflights':len(historical)}),flush=True)
    @contextmanager
    def recovery_workspace():
        owned=Path(tempfile.mkdtemp(prefix='rr-enriched-real-',dir=tmp_root))
        assert owned.resolve().is_relative_to(tmp_root.resolve())
        try:
            yield str(owned)
        except BaseException:
            print(json.dumps({'recovery_private_directory_retained_for_targeted_review':str(owned),
                              'cleanup_required_before_recovery_ends':True}),flush=True)
            raise
        else:
            assert owned.resolve().is_relative_to(tmp_root.resolve())
            shutil.rmtree(owned)
    with recovery_workspace() as temporary:
        folder,database=Path(temporary),Path(temporary)/'preflight.duckdb'
        started=time.perf_counter()
        property_paths,property_counts=histories.sorted_source_chunks(previous.SOURCE_DIR,folder)
        property_sort_seconds=round(time.perf_counter()-started,3)
        assert property_counts['raw_rows']==20275902 and property_counts['raw_parts']==previous.SOURCE_ROWS
        assert property_counts['rows']==2291853 and property_counts['categoryid']==788214 and property_counts['available']==1503639
        started=time.perf_counter()
        event_paths,event_counts=event_chunks(source_paths['events.csv'],folder)
        event_sort_seconds=round(time.perf_counter()-started,3)
        assert event_counts==dict(event_rows=2756101,view_rows=2664312,addtocart_rows=69332,transaction_rows=22457,null_transaction_rows=2733644)
        property_chunk_bytes=sum(path.stat().st_size for path in property_paths)
        event_chunk_bytes=sum(path.stat().st_size for path in event_paths)
        print(json.dumps({'phase':'independent property and event source sorting complete'}),flush=True)
        prop_code='\n'.join(prefixes[path] for path in ['sql/56_import_retailrocket_properties.sql','sql/65_stage_retailrocket_item_state_observations.sql','sql/67_build_retailrocket_item_state_intervals.sql'])
        event_code='\n'.join(prefixes[path] for path in ['sql/54_import_retailrocket_events.sql','sql/63_stage_retailrocket_events.sql'])
        _,property_reconstruction_seconds=execute(folder,database,prop_code)
        _,event_reconstruction_seconds=execute(folder,database,event_code)
        print(json.dumps({'phase':'source prefixes reconstructed'}),flush=True)
        build_query=creation+"SELECT 'SQL69_CREATION_COMPLETE' AS private_phase;\n"+checks
        run,audit_seconds=execute(folder,database,build_query,enlarged=True)
        database_before=previous.sha256(database)
        outputs=previous.json_outputs(run.stdout)
        assert len(outputs)==2 and outputs[0]==[{'private_phase':'SQL69_CREATION_COMPLETE'}]
        report=outputs[1]
        assert [row['status'] for row in report]==['PASS']*20+['INFO']*8
        print(json.dumps({'phase':'SQL69 create and checks passed'}),flush=True)
        match_stats,interval_stats,stream_seconds=compare_stream(folder,database,sql,event_paths,property_paths)
        assert match_stats['event_rows']==2756101 and match_stats['event_duplicate_surplus']==460
        assert match_stats['maximum_current_event_item_history_rows']<=HISTORY_CAP
        assert interval_stats==old_intervals['independent_python_interval_counts']
        source_counts=dict(event_rows=event_counts['event_rows'],categoryid=property_counts['categoryid'],available=property_counts['available'])
        assert report==healthy_report(source_counts,interval_stats,match_stats)
        database_after=previous.sha256(database)
        assert database_before==database_after
        database_bytes=database.stat().st_size
    assert not folder.exists()
    after={name:previous.snapshot(path) for name,path in source_paths.items()}
    assert before==after
    assert all(previous.sha256(root/path)==digest for path,digest in hashes.items())
    assert all(previous.sha256(root/path)==digest for path,digest in historical.items())
    assert (root/method_path).read_bytes().startswith(contract)
    evidence=dict(
        checked_at_utc=datetime.now(timezone.utc).isoformat(),executor='assistant',
        engine=subprocess.check_output([args.duckdb,'-version'],text=True).strip(),
        script=script_path,script_sha256=hashes[script_path],validator=validator_path,validator_sha256=hashes[validator_path],
        code_and_dependency_sha256=hashes,method_contract=method_path,method_contract_prefix_bytes=len(contract),method_contract_prefix_sha256=CONTRACT_SHA,
        original_method_contract_prefix_bytes=10590,original_method_contract_prefix_sha256=ORIGINAL_CONTRACT_SHA,
        source_files=FILES,source_before=before,source_after=after,source_hashes_and_metadata_unchanged=True,
        reconstruction_prefix_sha256={path:hashlib.sha256(code.encode()).hexdigest() for path,code in prefixes.items()},
        reconstruction_basis='Only SQL56/65/67 property/interval creation prefixes and SQL54/63 event creation prefixes, in two reconstruction phases; no prior full checks.',
        source_tables=['rr_stg.events','rr_core.item_state_intervals'],target_table='rr_mart.events_enriched',target_columns=17,checks_query_read_only=True,private_stream_read_only=True,
        real_source_attempts=2,real_source_successful_attempts=1,
        real_property_reconstruction_executions=2,real_event_reconstruction_executions=2,real_build_and_check_script_executions=2,real_private_stream_executions=1,
        initial_failed_attempt=dict(phase='SQL69 create/check',failure_category='unknown_nonzero_cli_exit',timeout=False,
                                   property_reconstruction_completed=True,event_reconstruction_completed=True,private_directory_cleanup_verified=True,
                                   memory_limit='1GB',max_temp_directory_size='2GB',report_or_evidence_issued=False),
        successful_recovery_creation_marker_reached=True,safe_error_category_reporting=True,
        report_rows=28,report_columns=5,output_columns=COLUMNS,checks_passed=20,info_rows=8,fail_rows=0,blocked_rows=0,
        results=report,report_sha256=previous.report_hash(report),report_fingerprint_contract='SHA-256 of ordered compact JSON arrays in output-column order, each followed by LF; actual/expected are integer counts or JSON null.',
        independent_python_property_source_counts=property_counts,independent_python_event_source_counts=event_counts,
        independent_python_interval_counts=interval_stats,independent_python_match_counts=match_stats,
        independent_python_numeric_external_sort=True,independent_python_current_item_binary_search=True,independent_python_report_matched=True,
        independent_stream_occurrences_compared=match_stats['event_rows'],independent_stream_fields_compared=17,
        independent_stream_all_occurrences_matched=True,independent_original_event_fields_and_duplicates_preserved=True,
        independent_original_property_values_and_provenance_preserved=True,independent_UTC_timestamp_and_date_matched=True,all_source_property_intervals_reconciled=True,
        coverage_partitions_reconciled=True,open_tail_counts_are_matched_subsets=True,no_backward_fill_verified=True,
        maximum_current_event_item_history_rows_observed=match_stats['maximum_current_event_item_history_rows'],current_item_history_budget_rows=HISTORY_CAP,
        history_buffer_cap_inherited_from_accepted_SQL68=True,null_marker='__NULL__',
        private_database_sha256_before_readonly=database_before,private_database_sha256_after_readonly=database_after,private_database_bytes_unchanged=True,
        fixture_case_count=len(cases),fixture_cases=cases,invalid_prerequisite_subcase_count=len(invalid),
        atomic_invalid_input_noncreation_verified=True,existing_target_preserved_verified=True,fact_mutation_subcase_count=len(mutations),
        blocked_dependencies_verified=True,info_requires_all_controls_pass_verified=True,overlap_gap_and_invalid_tail_admission_blocked=True,
        preflight_settings=dict(threads=2,memory_limit='1GB',max_temp_directory_size='2GB',timeout_seconds_per_cli_phase=120,
                                python_sort_chunk_rows=CHUNK_ROWS,current_item_history_rows=HISTORY_CAP,private_directory_budget_bytes=7*1024**3,free_space_admission_bytes=8*1024**3,
                                build_check_memory_limit='2GB',build_check_max_temp_directory_size='4GB'),
        private_property_comparison_chunks=len(property_paths),private_property_comparison_chunk_bytes=property_chunk_bytes,
        private_event_comparison_chunks=len(event_paths),private_event_comparison_chunk_bytes=event_chunk_bytes,
        private_comparison_spool_scope='Selected property source tuples and every event occurrence were sorted privately; no normalized 5.5-million-row join export was created. All chunks removed with their owning private directory.',
        workspace_free_bytes_before=free_before,workspace_free_bytes_after=shutil.disk_usage(tmp_root).free,
        private_database_bytes_before_cleanup=database_bytes,largest_private_directory_bytes_observed_after_phase=max(sizes),
        temporary_databases_and_spills_removed=True,private_source_comparison_spools_removed=True,
        learner_database_opened=False,category_csv_read=False,historical_comparison_or_analysis_suites_rerun=False,
        historical_preflight_files_unchanged=len(historical),source_records_or_identifiers_uploaded_or_logged=False,
        elapsed_python_property_scan_select_sort_seconds=property_sort_seconds,elapsed_python_event_scan_sort_seconds=event_sort_seconds,
        elapsed_property_reconstruction_seconds=property_reconstruction_seconds,elapsed_event_reconstruction_seconds=event_reconstruction_seconds,
        elapsed_build_and_check_seconds=audit_seconds,elapsed_private_stream_seconds=stream_seconds,
        timing_scope='Successful recovery only, excluding the earlier unknown failed attempt. Four CLI phases: property prefix chain, event prefix chain, SQL69 creation and checks, and read-only 17-field persisted fact stream. Independent source sorting timed separately; hashing/fixtures excluded; not a performance benchmark.',
        scope='Assistant enriched-event materialization preflight passed; learner SQL69 pending. Each original event occurrence retained. MATCHED means greatest recorded start at/before event with interval compliance, not confirmed business truth or freshness. NO_HISTORY and BEFORE_FIRST retained without backfill. Open-tail matches are subsets, not a fourth class. Persistent 17-column fact verified, with UTC timestamp/date. No category reference repair, expiry age, inventory, conversion or causal claim.')
    output.write_text(json.dumps(evidence,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps({'report_rows':28,'checks_passed':20,'info_rows':8,'event_occurrences_compared':match_stats['event_rows'],
                      'build_and_check_seconds':audit_seconds,'report_sha256':evidence['report_sha256']}),flush=True)


if __name__=='__main__':
    main()
