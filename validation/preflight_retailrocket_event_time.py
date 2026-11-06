"""Read-only event-time audit, checked per occurrence with integer Python UTC arithmetic."""
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
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

import preflight_retailrocket_events_staging as staging

previous=staging.previous
COLUMNS=previous.COLUMNS
CONTRACT_SHA='75e3f3d48f9d3b295ff7543c6234c1a16cfc6906c03129fa04559eb25f3e39a3'
MAX_MS=253402300799999
DAY_MS=86400000
EPOCH=datetime(1970,1,1,tzinfo=timezone.utc)
FORMAT='%Y-%m-%dT%H:%M:%S.%fZ'
SCHEMA=[('timestamp','BIGINT'),('visitorid','BIGINT'),('event','VARCHAR'),('itemid','BIGINT'),('transactionid','BIGINT')]
CHECKS=['event_rows','schema_mismatch','missing_timestamp_rows','negative_timestamp_rows',
        'unsupported_epoch_ms_rows','converted_rows','conversion_null_rows','roundtrip_error_rows',
        'date_partition_error_rows','min_timestamp_ms','max_timestamp_ms','first_utc_timestamp',
        'last_utc_timestamp','distinct_utc_dates','daily_rows_difference','first_date_event_rows',
        'last_date_event_rows','subsecond_event_rows']
PARAMETER_SQL="""SELECT 2756101::BIGINT AS expected_rows,
        1430622004384::BIGINT AS expected_min_ms,1442545187788::BIGINT AS expected_max_ms,
        '2015-05-03T03:00:04.384000Z'::VARCHAR AS expected_first_utc,
        '2015-09-18T02:59:47.788000Z'::VARCHAR AS expected_last_utc,
        139::BIGINT AS expected_dates,253402300799999::BIGINT AS max_supported_ms"""
PRIVATE_STREAM="""SELECT timestamp,
    strftime(make_timestamp_ms(timestamp),'%Y-%m-%dT%H:%M:%S.%fZ'),
    CAST(CAST(make_timestamp_ms(timestamp) AS DATE) AS VARCHAR),
    epoch_ms(make_timestamp_ms(timestamp)) FROM rr_stg.events;"""


def utc(ms):
    assert isinstance(ms,int) and 0<=ms<=MAX_MS
    return EPOCH+timedelta(milliseconds=ms)


def recover(dt):
    difference=dt-EPOCH
    assert difference.microseconds%1000==0
    return difference.days*DAY_MS+difference.seconds*1000+difference.microseconds//1000


def blank_stats():
    return dict(rows=0,min_ms=None,max_ms=None,dates=Counter(),subsecond_rows=0)


def accumulate(stats,ms,dt=None):
    dt=dt or utc(ms)
    assert recover(dt)==ms
    day_start=(dt.date()-EPOCH.date()).days*DAY_MS
    assert day_start==(ms//DAY_MS)*DAY_MS and day_start<=ms<day_start+DAY_MS
    stats['rows']+=1
    stats['min_ms']=ms if stats['min_ms'] is None else min(ms,stats['min_ms'])
    stats['max_ms']=ms if stats['max_ms'] is None else max(ms,stats['max_ms'])
    stats['dates'][dt.date().isoformat()]+=1
    stats['subsecond_rows']+=ms%1000!=0


def fold(values):
    stats=blank_stats()
    for ms in values:
        accumulate(stats,ms)
    return stats


def expectations(stats):
    return dict(rows=stats['rows'],min_ms=stats['min_ms'],max_ms=stats['max_ms'],
                first_utc=utc(stats['min_ms']).strftime(FORMAT),last_utc=utc(stats['max_ms']).strftime(FORMAT),
                dates=len(stats['dates']))


def adjusted(sql,expected):
    assert sql.count(PARAMETER_SQL)==1
    replacement=(f"SELECT {expected['rows']}::BIGINT AS expected_rows,"
                 f"{expected['min_ms']}::BIGINT AS expected_min_ms,{expected['max_ms']}::BIGINT AS expected_max_ms,"
                 f"'{expected['first_utc']}'::VARCHAR AS expected_first_utc,'{expected['last_utc']}'::VARCHAR AS expected_last_utc,"
                 f"{expected['dates']}::BIGINT AS expected_dates,{MAX_MS}::BIGINT AS max_supported_ms")
    return sql.replace(PARAMETER_SQL,replacement)


def report_reference(values,expected,schema=SCHEMA):
    def parsed(value):
        try:
            result=int(value)
            return result if -9223372036854775808<=result<=9223372036854775807 else None
        except (ValueError,TypeError):
            return None
    nums=[parsed(value) for value in values]
    mismatches=sum(left!=right for left,right in zip(schema,SCHEMA))+abs(len(schema)-len(SCHEMA))
    missing=sum(value is None for value in values)
    negative=sum(value is not None and value<0 for value in nums)
    unsupported=sum(original is not None and (value is None or value>MAX_MS) for original,value in zip(values,nums))
    admitted=(mismatches==0 and len(values)==expected['rows'] and len(values)>0 and missing==negative==unsupported==0)
    actual=[len(values),mismatches,missing,negative,unsupported]+[None]*13
    targets=[expected['rows'],0,0,0,0,expected['rows'],0,0,0,expected['min_ms'],expected['max_ms'],
             expected['first_utc'],expected['last_utc'],expected['dates'],0,None,None,None]
    if admitted:
        stats=fold(nums)
        actual[5:15]=[len(values),0,0,0,stats['min_ms'],stats['max_ms'],
                      utc(stats['min_ms']).strftime(FORMAT),utc(stats['max_ms']).strftime(FORMAT),
                      len(stats['dates']),sum(stats['dates'].values())-len(values)]
        if actual[:15]==targets[:15]:
            actual[15:]=[stats['dates'][utc(stats['min_ms']).date().isoformat()],
                         stats['dates'][utc(stats['max_ms']).date().isoformat()],stats['subsecond_rows']]
    return make_report(actual,targets)


def report_from_stats(stats,expected):
    first,last=utc(stats['min_ms']),utc(stats['max_ms'])
    actual=[stats['rows'],0,0,0,0,stats['rows'],0,0,0,stats['min_ms'],stats['max_ms'],
            first.strftime(FORMAT),last.strftime(FORMAT),len(stats['dates']),sum(stats['dates'].values())-stats['rows'],
            stats['dates'][first.date().isoformat()],stats['dates'][last.date().isoformat()],stats['subsecond_rows']]
    targets=[expected['rows'],0,0,0,0,expected['rows'],0,0,0,expected['min_ms'],expected['max_ms'],
             expected['first_utc'],expected['last_utc'],expected['dates'],0,None,None,None]
    assert actual[:15]==targets[:15]
    return make_report(actual,targets)


def make_report(actual,expected):
    actual=[str(value) if value is not None else None for value in actual]
    expected=[str(value) if value is not None else None for value in expected]
    return [dict(check_order=i,check_name=name,actual=value,expected=target,
                 status='BLOCKED' if value is None else 'INFO' if target is None else 'PASS' if value==target else 'FAIL')
            for i,(name,value,target) in enumerate(zip(CHECKS,actual,expected),1)]


def setup(values,schema=SCHEMA):
    query='CREATE SCHEMA rr_stg; CREATE TABLE rr_stg.events ('+','.join(name+' '+kind for name,kind in schema)+');\n'
    rows=[]
    for value in values:
        logical=dict(timestamp=value,visitorid=1,event='view',itemid=1,transactionid=None)
        def literal(value):
            return 'NULL' if value is None else "'"+str(value).replace("'","''")+"'"
        rows.append('('+','.join(literal(logical[name]) for name,_ in schema)+')')
    if rows:
        query+='INSERT INTO rr_stg.events VALUES '+','.join(rows)+';'
    return query


def fold_csv(source):
    stats=blank_stats()
    with source.open('r',encoding='utf-8',newline='') as stream:
        reader=csv.reader(stream,strict=True)
        assert next(reader)==previous.FIELDS
        for row in reader:
            assert len(row)==5 and staging.canonical(row[0]),'Private source timestamp invalid; record withheld'
            accumulate(stats,int(row[0]))
    return stats


def date_fingerprint(stats):
    payload=''.join(json.dumps([date,count],separators=(',',':'))+'\n' for date,count in sorted(stats['dates'].items()))
    return hashlib.sha256(payload.encode()).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--duckdb',required=True)
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--fixtures-only',action='store_true')
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    script_path='sql/64_audit_retailrocket_event_time.sql'
    validator_path='validation/preflight_retailrocket_event_time.py'
    method_path='docs/RETAILROCKET_EVENT_TIME_VALIDATION.md'
    output=root/'data/retailrocket_event_time_preflight.json'
    assert args.output.resolve()==output.resolve()
    dependencies=[script_path,validator_path,'sql/54_import_retailrocket_events.sql','sql/63_stage_retailrocket_events.sql',
                  'validation/preflight_retailrocket_events_import.py','validation/preflight_retailrocket_events_staging.py',
                  'data/retailrocket_source_audit.json','data/retailrocket_independent_checks.json',
                  'data/retailrocket_events_staging_preflight.json','data/retailrocket_events_staging_learner_acceptance.json',
                  'docs/RETAILROCKET_EVENTS_STAGING_VALIDATION.md']
    hashes={path:previous.sha256(root/path) for path in dependencies}
    assert hashes['data/retailrocket_events_staging_learner_acceptance.json']=='e6bcad9ecdf019cd8ce5a9ff21527eeecac002dd43f9c52ea9a1479e11dd07cb'
    assert hashes['docs/RETAILROCKET_EVENTS_STAGING_VALIDATION.md']=='df3b0594345adf6f682941828496c95fc81e70ee4088108596d0a578a818070a'
    contract=(root/method_path).read_bytes().split(b'\n## Executed results\n',1)[0]
    assert hashlib.sha256(contract).hexdigest()==CONTRACT_SHA
    sql=(root/script_path).read_text(encoding='utf-8')
    cleaned=re.sub(r'--[^\n]*','',sql)
    assert cleaned.lstrip().startswith('WITH ') and not re.search(r'\b(CREATE|INSERT|UPDATE|DELETE|DROP|ALTER|COPY|ATTACH|DETACH|SET)\b',cleaned,re.I)
    raw_sql=(root/'sql/54_import_retailrocket_events.sql').read_text(encoding='utf-8').split('-- CHECKS:',1)[0]
    stage_sql=(root/'sql/63_stage_retailrocket_events.sql').read_text(encoding='utf-8').split(staging.CHECK_MARKER,1)[0]
    assert raw_sql.count('read_csv(')==1 and 'EXCEPT ALL' not in raw_sql+stage_sql
    stage_evidence=json.loads((root/'data/retailrocket_events_staging_preflight.json').read_text(encoding='utf-8'))
    assert stage_evidence['checks_passed']==20 and stage_evidence['script_sha256']==hashes['sql/63_stage_retailrocket_events.sql']
    prior=json.loads((root/'data/retailrocket_independent_checks.json').read_text(encoding='utf-8'))
    prior_time=prior['events']
    assert [prior_time[k] for k in ['rows','min_timestamp_ms','max_timestamp_ms','distinct_utc_dates']]==[2756101,1430622004384,1442545187788,139]
    expected=dict(rows=2756101,min_ms=1430622004384,max_ms=1442545187788,
                  first_utc='2015-05-03T03:00:04.384000Z',last_utc='2015-09-18T02:59:47.788000Z',dates=139)
    assert utc(expected['min_ms']).strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]==prior_time['min_timestamp_utc']
    assert utc(expected['max_ms']).strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]==prior_time['max_timestamp_utc']
    tmp_root=root/'tmp'
    tmp_root.mkdir(exist_ok=True)
    free_before=shutil.disk_usage(tmp_root).free
    assert free_before>=4*1024**3
    sizes=[]

    def settings(folder,database,zone='UTC'):
        assert folder.resolve().is_relative_to(tmp_root.resolve()) and Path(database).resolve().is_relative_to(folder.resolve())
        assert zone in ('UTC','Australia/Sydney')
        spill=(folder/'spill').as_posix().replace("'","''")
        return f"SET threads=2; SET memory_limit='1GB'; SET max_temp_directory_size='2GB'; SET temp_directory='{spill}'; SET TimeZone='{zone}';\n"

    def observe(folder):
        size=sum(path.stat().st_size for path in folder.rglob('*') if path.is_file())
        assert size<=3*1024**3
        sizes.append(size)

    def execute(folder,database,query,readonly=False,zone='UTC'):
        started=time.perf_counter()
        command=[args.duckdb,str(database),'-bail','-json']+(['-readonly'] if readonly else [])
        run=subprocess.run(command,input=settings(folder,database,zone)+query,text=True,encoding='utf-8',capture_output=True,timeout=120)
        assert run.returncode==0,'Private event-time execution failed; row-bearing diagnostics withheld'
        observe(folder)
        return run,round(time.perf_counter()-started,3)

    def stream(folder,database,zone='UTC'):
        started,timed_out=time.perf_counter(),threading.Event()
        process=subprocess.Popen([args.duckdb,str(database),'-bail','-readonly','-csv','-noheader'],
                                 stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,encoding='utf-8')
        def expire():
            timed_out.set()
            process.kill()
        timer=threading.Timer(120,expire)
        timer.start()
        stats=blank_stats()
        try:
            process.stdin.write(settings(folder,database,zone)+PRIVATE_STREAM)
            process.stdin.close()
            for row in csv.reader(process.stdout,strict=True):
                assert len(row)==4,'Private timestamp stream width differs'
                ms=int(row[0]); dt=utc(ms)
                assert row[1]==dt.strftime(FORMAT) and row[2]==dt.date().isoformat(),'Private UTC interpretation differs; values withheld'
                assert int(row[3])==recover(dt)==ms,'Private integer roundtrip differs; values withheld'
                accumulate(stats,ms,dt)
            assert process.wait(timeout=120)==0 and not timed_out.is_set(),'Private time stream failed or timed out'
        finally:
            timer.cancel()
            if process.poll() is None:
                process.kill(); process.wait()
            process.stdout.close()
        observe(folder)
        return stats,round(time.perf_counter()-started,3)

    cases=[]
    boundary=[0,1,999,1000,86399999,86400000,86400001,1456704000123,MAX_MS,1]
    assert utc(1456704000123).strftime(FORMAT)=='2016-02-29T00:00:00.123000Z'
    assert utc(MAX_MS).strftime(FORMAT)=='9999-12-31T23:59:59.999000Z'
    with tempfile.TemporaryDirectory(prefix='rr-time-fixture-',dir=tmp_root) as temporary:
        folder,database=Path(temporary),Path(temporary)/'boundary.duckdb'
        execute(folder,database,setup(boundary))
        initial_hash=previous.sha256(database)
        boundary_stats=fold(boundary)
        assert boundary_stats['dates']=={'1970-01-01':6,'1970-01-02':2,'2016-02-29':1,'9999-12-31':1}
        params=expectations(boundary_stats)
        query=adjusted(sql,params)
        for zone in ['UTC','Australia/Sydney']:
            run,_=execute(folder,database,query,readonly=True,zone=zone)
            assert json.loads(run.stdout)==report_reference(boundary,params)
            streamed,_=stream(folder,database,zone=zone)
            assert streamed==boundary_stats
        assert previous.sha256(database)==initial_hash
        cases.append(dict(case='exact_fraction_midnight_leap_day_duplicates_shared_upper_bound_two_zone_invariance',passed=True,
                          fixture_occurrences=10,session_timezones=['UTC','Australia/Sydney']))

        for label,override in [('changed_minimum',{'min_ms':1}),('changed_maximum',{'max_ms':MAX_MS-1}),('changed_date_count',{'dates':5})]:
            changed={**params,**override}
            run,_=execute(folder,database,adjusted(sql,changed),readonly=True)
            observed=json.loads(run.stdout)
            assert observed==report_reference(boundary,changed)
            assert sum(row['status']=='FAIL' for row in observed)==1
            assert all(row['actual'] is None and row['status']=='BLOCKED' for row in observed[15:])
        assert previous.sha256(database)==initial_hash
        cases.append(dict(case='frozen_bounds_or_date_count_mismatch_blocks_all_info_despite_valid_conversion',passed=True,
                          subcases=['changed_minimum','changed_maximum','changed_date_count']))
    assert not folder.exists()

    invalid=[('empty',[],SCHEMA,None),('wrong_count',[0],SCHEMA,2),('null',[None],SCHEMA,None),
             ('negative',[-1],SCHEMA,None),('beyond_shared_range',[MAX_MS+1],SCHEMA,None),
             ('bigint_overflow_for_timestamp',[9223372036854775807],SCHEMA,None),
             ('wrong_type_numeric',['0'],[('timestamp','VARCHAR')]+SCHEMA[1:],None),
             ('wrong_type_unparsed',['bad'],[('timestamp','VARCHAR')]+SCHEMA[1:],None),
             ('wrong_order',[0],[SCHEMA[1],SCHEMA[0],*SCHEMA[2:]],None)]
    with tempfile.TemporaryDirectory(prefix='rr-time-invalid-',dir=tmp_root) as temporary:
        folder=Path(temporary)
        for label,values,schema,row_override in invalid:
            database=folder/(label+'.duckdb')
            execute(folder,database,setup(values,schema))
            original_hash=previous.sha256(database)
            params=expectations(fold([0])); params['rows']=len(values) if row_override is None else row_override
            run,_=execute(folder,database,adjusted(sql,params),readonly=True)
            observed=json.loads(run.stdout)
            assert observed==report_reference(values,params,schema),label
            assert all(row['actual'] is None and row['status']=='BLOCKED' for row in observed[5:]),label
            assert previous.sha256(database)==original_hash,label
        cases.append(dict(case='invalid_prerequisites_block_every_derived_metric_without_unsafe_conversion',passed=True,
                          subcases=[case[0] for case in invalid]))
    assert not folder.exists()
    print(json.dumps({'fixture_families_passed':len(cases),'prerequisite_subcases':len(invalid),'changed_control_subcases':3}),flush=True)
    if args.fixtures_only:
        return

    source=Path(previous.SOURCE)
    before=staging.snapshot(source)
    assert before['sha256']==previous.SOURCE_SHA and before['size_bytes']==94237913
    historical={str(path.relative_to(root)):previous.sha256(path) for path in (root/'data').glob('*preflight.json') if path.resolve()!=output.resolve()}
    start=time.perf_counter(); source_stats=fold_csv(source); fold_seconds=round(time.perf_counter()-start,3)
    expected_report=report_from_stats(source_stats,expected)
    with tempfile.TemporaryDirectory(prefix='rr-time-real-',dir=tmp_root) as temporary:
        folder,database=Path(temporary),Path(temporary)/'preflight.duckdb'
        _,reconstruction_seconds=execute(folder,database,raw_sql+'\n'+stage_sql)
        database_before=previous.sha256(database)
        run,audit_seconds=execute(folder,database,sql,readonly=True)
        report=json.loads(run.stdout)
        assert report==expected_report
        assert [row['status'] for row in report]==['PASS']*15+['INFO']*3
        stream_stats,stream_seconds=stream(folder,database)
        assert stream_stats==source_stats
        database_after=previous.sha256(database)
        assert database_before==database_after
        database_bytes=database.stat().st_size
    assert not folder.exists()
    after=staging.snapshot(source)
    assert before==after
    assert all(previous.sha256(root/path)==digest for path,digest in hashes.items())
    assert all(previous.sha256(root/path)==digest for path,digest in historical.items())
    assert (root/method_path).read_bytes().startswith(contract)
    evidence=dict(
        checked_at_utc=datetime.now(timezone.utc).isoformat(),executor='assistant',
        engine=subprocess.check_output([args.duckdb,'-version'],text=True).strip(),
        script=script_path,script_sha256=hashes[script_path],validator=validator_path,validator_sha256=hashes[validator_path],
        code_and_dependency_sha256=hashes,method_contract=method_path,method_contract_prefix_bytes=len(contract),method_contract_prefix_sha256=CONTRACT_SHA,
        source_files=['events.csv'],source_before={'events.csv':before},source_after={'events.csv':after},source_hashes_and_metadata_unchanged=True,
        reconstruction_prefix_sha256={'sql/54_import_retailrocket_events.sql':hashlib.sha256(raw_sql.encode()).hexdigest(),
                                      'sql/63_stage_retailrocket_events.sql':hashlib.sha256(stage_sql.encode()).hexdigest()},
        reconstruction_basis='Only frozen SQL54 import and SQL63 creation prefixes; no prior full checks. One separate read-only report and one read-only per-occurrence stream.',
        source_table='rr_stg.events',query_read_only=True,real_audit_script_executions=1,real_private_stream_executions=1,
        report_rows=18,report_columns=5,output_columns=COLUMNS,actual_expected_types='VARCHAR or NULL; check_order integer',
        checks_passed=15,info_rows=3,fail_rows=0,blocked_rows=0,results=report,report_sha256=previous.report_hash(report),
        report_fingerprint_contract='SHA-256 of ordered compact JSON arrays in output-column order, each followed by LF. actual/expected are strings or JSON null.',
        independent_python_integer_datetime_reference=True,independent_python_source_fold_matched=True,
        independent_python_report_matched=True,independent_stream_occurrences_compared=stream_stats['rows'],independent_stream_fields_compared=4,
        independent_stream_all_occurrences_matched=True,independent_source_and_stream_date_partitions_matched=True,
        utc_date_partition_sha256=date_fingerprint(source_stats),utc_date_partition_fingerprint_contract='Ordered compact JSON [YYYY-MM-DD, occurrence_count] arrays followed by LF.',
        private_database_sha256_before_readonly=database_before,private_database_sha256_after_readonly=database_after,private_database_bytes_unchanged=True,
        supported_epoch_ms_min=0,supported_epoch_ms_max=MAX_MS,time_interpretation='UTC convention applied to timezone-naive TIMESTAMP; not evidence of business local timezone.',
        fixture_case_count=len(cases),fixture_cases=cases,invalid_prerequisite_subcase_count=len(invalid),changed_control_subcase_count=3,
        blocked_dependencies_verified=True,info_requires_all_controls_pass_verified=True,session_timezone_invariance_verified=True,
        preflight_settings=dict(threads=2,memory_limit='1GB',max_temp_directory_size='2GB',timeout_seconds_per_cli_phase=120),
        workspace_free_bytes_before=free_before,workspace_free_bytes_after=shutil.disk_usage(tmp_root).free,
        private_database_bytes_before_cleanup=database_bytes,largest_private_directory_bytes_observed_after_phase=max(sizes),temporary_databases_and_spills_removed=True,
        learner_database_opened=False,other_source_csvs_read=False,historical_comparison_or_analysis_suites_rerun=False,historical_preflight_files_unchanged=len(historical),
        source_records_or_identifiers_exported_or_logged=False,private_per_event_comparison_files_created=False,
        elapsed_python_source_fold_seconds=fold_seconds,elapsed_reconstruction_seconds=reconstruction_seconds,
        elapsed_readonly_audit_seconds=audit_seconds,elapsed_private_stream_seconds=stream_seconds,
        timing_scope='One reconstruction CLI, one read-only SQL64 report and one read-only per-occurrence stream; independent source fold timed separately. Hashing/fixtures excluded; not a performance benchmark.',
        scope='Assistant timestamp audit passed; learner SQL64 pending. No table mutation, deduplication, local-business timezone inference, session/order/person definitions, event-time property join, conversion rate or monetary metric. Observed endpoint dates are not assumed complete collection days.')
    output.write_text(json.dumps(evidence,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps({'report_rows':18,'checks_passed':15,'info_rows':3,'occurrences_compared':stream_stats['rows'],
                      'readonly_audit_seconds':audit_seconds,'report_sha256':evidence['report_sha256']}),flush=True)


if __name__=='__main__':
    main()
