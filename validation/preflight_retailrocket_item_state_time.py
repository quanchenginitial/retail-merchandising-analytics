"""Read-only named-property time audit with independent selected-source UTC arithmetic."""
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
from pathlib import Path

import preflight_retailrocket_event_time as reference
import preflight_retailrocket_item_state_observations as staging

previous=staging.previous
FILES=previous.FILES
COLUMNS=previous.COLUMNS
MAX_MS=reference.MAX_MS
FORMAT=reference.FORMAT
utc=reference.utc
recover=reference.recover
blank_stats=reference.blank_stats
accumulate=reference.accumulate
date_fingerprint=reference.date_fingerprint
CONTRACT_SHA='19cfe93e4e12226be16c057190d1b1b9c3cc54c8c0be49b0db74fc1dca4f6c98'
SCHEMA=[('timestamp','BIGINT'),('itemid','BIGINT'),('property','VARCHAR'),('value','VARCHAR'),('source_file','VARCHAR')]
CHECKS=['observation_rows','schema_mismatch','missing_timestamp_rows','negative_timestamp_rows',
        'unsupported_epoch_ms_rows','converted_rows','conversion_null_rows','roundtrip_error_rows',
        'date_partition_error_rows','daily_rows_difference','categoryid_rows','available_rows',
        'min_timestamp_ms','max_timestamp_ms','first_utc_timestamp','last_utc_timestamp',
        'distinct_utc_dates','first_date_observation_rows','last_date_observation_rows','subsecond_observation_rows']
PARAMETER_SQL="""SELECT 2291853::BIGINT AS expected_rows,788214::BIGINT AS expected_category_rows,
        1503639::BIGINT AS expected_available_rows,253402300799999::BIGINT AS max_supported_ms"""
PRIVATE_STREAM="""SELECT timestamp,
    strftime(make_timestamp_ms(timestamp),'%Y-%m-%dT%H:%M:%S.%fZ'),
    CAST(CAST(make_timestamp_ms(timestamp) AS DATE) AS VARCHAR),
    epoch_ms(make_timestamp_ms(timestamp)) FROM rr_stg.item_state_observations;"""


def counts(records):
    return dict(rows=len(records),categoryid=sum(prop=='categoryid' for _,prop in records),
                available=sum(prop=='available' for _,prop in records))


def adjusted(sql,expected):
    assert sql.count(PARAMETER_SQL)==1
    replacement=(f"SELECT {expected['rows']}::BIGINT AS expected_rows,"
                 f"{expected['categoryid']}::BIGINT AS expected_category_rows,"
                 f"{expected['available']}::BIGINT AS expected_available_rows,{MAX_MS}::BIGINT AS max_supported_ms")
    return sql.replace(PARAMETER_SQL,replacement)


def make_report(actual,expected):
    actual=[str(value) if value is not None else None for value in actual]
    expected=[str(value) if value is not None else None for value in expected]
    return [dict(check_order=i,check_name=name,actual=value,expected=target,
                 status='BLOCKED' if value is None else 'INFO' if target is None else 'PASS' if value==target else 'FAIL')
            for i,(name,value,target) in enumerate(zip(CHECKS,actual,expected),1)]


def info_values(stats):
    first,last=utc(stats['min_ms']),utc(stats['max_ms'])
    return [stats['min_ms'],stats['max_ms'],first.strftime(FORMAT),last.strftime(FORMAT),
            len(stats['dates']),stats['dates'][first.date().isoformat()],
            stats['dates'][last.date().isoformat()],stats['subsecond_rows']]


def report_reference(records,expected,schema=SCHEMA):
    def parsed(value):
        try:
            result=int(value)
            return result if -9223372036854775808<=result<=9223372036854775807 else None
        except (ValueError,TypeError):
            return None
    values=[row[0] for row in records]
    nums=[parsed(value) for value in values]
    mismatches=sum(left!=right for left,right in zip(schema,SCHEMA))+abs(len(schema)-len(SCHEMA))
    missing=sum(value is None for value in values)
    negative=sum(value is not None and value<0 for value in nums)
    unsupported=sum(original is not None and (value is None or value>MAX_MS) for original,value in zip(values,nums))
    population=counts(records)
    admitted=(mismatches==0 and population==expected and len(values)>0 and missing==negative==unsupported==0)
    actual=[len(values),mismatches,missing,negative,unsupported]+[None]*5+[population['categoryid'],population['available']]+[None]*8
    targets=[expected['rows'],0,0,0,0,expected['rows'],0,0,0,0,expected['categoryid'],expected['available']]+[None]*8
    if admitted:
        stats=reference.fold(nums)
        actual[5:10]=[len(values),0,0,0,sum(stats['dates'].values())-len(values)]
        if actual[:12]==targets[:12]:
            actual[12:]=info_values(stats)
    return make_report(actual,targets)


def report_from_stats(stats,population,expected):
    assert stats['rows']==population['rows'] and population==expected
    controls=[stats['rows'],0,0,0,0,stats['rows'],0,0,0,sum(stats['dates'].values())-stats['rows'],
              population['categoryid'],population['available']]
    targets=[expected['rows'],0,0,0,0,expected['rows'],0,0,0,0,expected['categoryid'],expected['available']]
    assert controls==targets
    return make_report(controls+info_values(stats),targets+[None]*8)


def setup(records,schema=SCHEMA):
    query='CREATE SCHEMA rr_stg; CREATE TABLE rr_stg.item_state_observations ('+','.join(name+' '+kind for name,kind in schema)+');\n'
    rows=[]
    for index,(value,prop) in enumerate(records):
        logical=dict(timestamp=value,itemid=index+1,property=prop,value='1',source_file=FILES[index%2])
        def literal(value):
            return 'NULL' if value is None else "'"+str(value).replace("'","''")+"'"
        rows.append('('+','.join(literal(logical[name]) for name,_ in schema)+')')
    if rows:
        query+='INSERT INTO rr_stg.item_state_observations VALUES '+','.join(rows)+';'
    return query


def fold_csv(source_dir):
    stats=blank_stats()
    population=dict(rows=0,categoryid=0,available=0)
    raw_parts={name:0 for name in FILES}
    selected_parts={name:0 for name in FILES}
    for name in FILES:
        with (source_dir/name).open('r',encoding='utf-8',newline='') as stream:
            reader=csv.reader(stream,strict=True)
            assert next(reader)==previous.RAW_FIELDS
            for row in reader:
                assert len(row)==4,'Private source record width differs'
                raw_parts[name]+=1
                if row[2] not in staging.NAMES:
                    continue
                assert staging.canonical_key(row[0]),'Private selected timestamp invalid; record withheld'
                accumulate(stats,int(row[0]))
                population['rows']+=1;population[row[2]]+=1;selected_parts[name]+=1
    assert raw_parts==previous.SOURCE_ROWS
    assert stats['rows']==population['rows']==sum(selected_parts.values())
    return stats,population,raw_parts,selected_parts


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--duckdb',required=True)
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--fixtures-only',action='store_true')
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    script_path='sql/66_audit_retailrocket_item_state_time.sql'
    validator_path='validation/preflight_retailrocket_item_state_time.py'
    method_path='docs/RETAILROCKET_ITEM_STATE_TIME_VALIDATION.md'
    output=root/'data/retailrocket_item_state_time_preflight.json'
    assert args.output.resolve()==output.resolve()
    dependencies=[script_path,validator_path,'sql/56_import_retailrocket_properties.sql','sql/65_stage_retailrocket_item_state_observations.sql',
                  'validation/preflight_retailrocket_properties_import.py','validation/preflight_retailrocket_item_state_observations.py',
                  'validation/preflight_retailrocket_event_time.py','validation/preflight_retailrocket_events_staging.py',
                  'validation/preflight_retailrocket_events_import.py','data/retailrocket_source_audit.json',
                  'data/retailrocket_item_state_observations_preflight.json','data/retailrocket_item_state_observations_learner_acceptance.json',
                  'docs/RETAILROCKET_ITEM_STATE_OBSERVATIONS_VALIDATION.md']
    hashes={path:previous.sha256(root/path) for path in dependencies}
    contract=(root/method_path).read_bytes().split(b'\n## Executed results\n',1)[0]
    assert hashlib.sha256(contract).hexdigest()==CONTRACT_SHA
    sql=(root/script_path).read_text(encoding='utf-8')
    cleaned=re.sub(r'--[^\n]*','',sql)
    assert cleaned.lstrip().startswith('WITH ') and not re.search(r'\b(CREATE|INSERT|UPDATE|DELETE|DROP|ALTER|COPY|ATTACH|DETACH|SET)\b',cleaned,re.I)
    raw_sql=(root/'sql/56_import_retailrocket_properties.sql').read_text(encoding='utf-8').split('-- CHECKS:',1)[0]
    stage_sql=(root/'sql/65_stage_retailrocket_item_state_observations.sql').read_text(encoding='utf-8').split(staging.CHECK_MARKER,1)[0]
    assert raw_sql.count('read_csv(')==2 and 'EXCEPT ALL' not in raw_sql+stage_sql
    stage_evidence=json.loads((root/'data/retailrocket_item_state_observations_preflight.json').read_text(encoding='utf-8'))
    assert stage_evidence['checks_passed']==20 and stage_evidence['script_sha256']==hashes['sql/65_stage_retailrocket_item_state_observations.sql']
    assert hashlib.sha256(raw_sql.encode()).hexdigest()==stage_evidence['reconstruction_prefix_sha256']['sql/56_import_retailrocket_properties.sql']
    accepted=json.loads((root/'data/retailrocket_item_state_observations_learner_acceptance.json').read_text(encoding='utf-8'))
    assert accepted['acceptance_status']=='accepted' and accepted['report_sha256']==stage_evidence['report_sha256']
    audit=json.loads((root/'data/retailrocket_source_audit.json').read_text(encoding='utf-8'))
    assert audit['all_checks_passed']
    for name in FILES:
        assert audit['files'][name]['sha256']==previous.SOURCE_HASHES[name]
    expected=dict(rows=2291853,categoryid=788214,available=1503639)
    tmp_root=root/'tmp';tmp_root.mkdir(exist_ok=True)
    free_before=shutil.disk_usage(tmp_root).free
    assert free_before>=6*1024**3
    sizes=[]

    def settings(folder,database,zone='UTC'):
        assert folder.resolve().is_relative_to(tmp_root.resolve()) and Path(database).resolve().is_relative_to(folder.resolve())
        assert zone in ('UTC','Australia/Sydney')
        spill=(folder/'spill').as_posix().replace("'","''")
        return f"SET threads=2; SET memory_limit='1GB'; SET max_temp_directory_size='2GB'; SET temp_directory='{spill}'; SET TimeZone='{zone}';\n"

    def observe(folder):
        size=sum(path.stat().st_size for path in folder.rglob('*') if path.is_file())
        assert size<=5*1024**3
        sizes.append(size)

    def execute(folder,database,query,readonly=False,zone='UTC'):
        started=time.perf_counter()
        command=[args.duckdb,str(database),'-bail','-json']+(['-readonly'] if readonly else [])
        run=subprocess.run(command,input=settings(folder,database,zone)+query,text=True,encoding='utf-8',capture_output=True,timeout=120)
        assert run.returncode==0,'Private observation-time execution failed; row-bearing diagnostics withheld'
        observe(folder)
        return run,round(time.perf_counter()-started,3)

    def stream(folder,database,zone='UTC'):
        started,timed_out=time.perf_counter(),threading.Event()
        process=subprocess.Popen([args.duckdb,str(database),'-bail','-readonly','-csv','-noheader'],
                                 stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,encoding='utf-8')
        def expire():
            timed_out.set();process.kill()
        timer=threading.Timer(120,expire);timer.start()
        stats=blank_stats()
        try:
            process.stdin.write(settings(folder,database,zone)+PRIVATE_STREAM);process.stdin.close()
            for row in csv.reader(process.stdout,strict=True):
                assert len(row)==4,'Private timestamp stream width differs'
                ms=int(row[0]);dt=utc(ms)
                assert row[1]==dt.strftime(FORMAT) and row[2]==dt.date().isoformat(),'Private UTC interpretation differs; values withheld'
                assert int(row[3])==recover(dt)==ms,'Private integer roundtrip differs; values withheld'
                accumulate(stats,ms,dt)
            assert process.wait(timeout=120)==0 and not timed_out.is_set(),'Private time stream failed or timed out'
        finally:
            timer.cancel()
            if process.poll() is None:
                process.kill();process.wait()
            process.stdout.close()
        observe(folder)
        return stats,round(time.perf_counter()-started,3)

    cases=[]
    boundary_values=[0,1,999,1000,86399999,86400000,86400001,1456704000123,MAX_MS,1]
    boundary=[(ms,staging.NAMES[index%2]) for index,ms in enumerate(boundary_values)]
    assert utc(1456704000123).strftime(FORMAT)=='2016-02-29T00:00:00.123000Z'
    assert utc(MAX_MS).strftime(FORMAT)=='9999-12-31T23:59:59.999000Z'
    with tempfile.TemporaryDirectory(prefix='rr-state-time-fixture-',dir=tmp_root) as temporary:
        folder,database=Path(temporary),Path(temporary)/'boundary.duckdb'
        execute(folder,database,setup(boundary))
        initial_hash=previous.sha256(database)
        boundary_stats=reference.fold(boundary_values)
        assert boundary_stats['dates']=={'1970-01-01':6,'1970-01-02':2,'2016-02-29':1,'9999-12-31':1}
        params=counts(boundary)
        for zone in ['UTC','Australia/Sydney']:
            run,_=execute(folder,database,adjusted(sql,params),readonly=True,zone=zone)
            assert json.loads(run.stdout)==report_reference(boundary,params)
            streamed,_=stream(folder,database,zone=zone)
            assert streamed==boundary_stats
        assert previous.sha256(database)==initial_hash
        cases.append(dict(case='exact_fraction_midnight_leap_day_duplicates_shared_upper_bound_two_zone_invariance',passed=True,
                          fixture_occurrences=10,session_timezones=['UTC','Australia/Sydney']))
        for label,override in [('wrong_category_count',{'categoryid':6}),('wrong_available_count',{'available':6}),
                               ('same_total_wrong_property_mix',{'categoryid':4,'available':6})]:
            changed={**params,**override}
            run,_=execute(folder,database,adjusted(sql,changed),readonly=True)
            observed=json.loads(run.stdout)
            assert observed==report_reference(boundary,changed),label
            assert any(row['status']=='FAIL' for row in observed[10:12]),label
            assert all(row['actual'] is None and row['status']=='BLOCKED' for row in observed[5:10]+observed[12:]),label
        assert previous.sha256(database)==initial_hash
        cases.append(dict(case='wrong_property_counts_block_conversion_and_all_info_even_with_matching_total',passed=True,
                          subcases=['wrong_category_count','wrong_available_count','same_total_wrong_property_mix']))
    assert not folder.exists()

    invalid=[('empty',[],SCHEMA,None),('wrong_count',[(0,'categoryid')],SCHEMA,2),
             ('null',[(None,'categoryid')],SCHEMA,None),('negative',[(-1,'categoryid')],SCHEMA,None),
             ('beyond_shared_range',[(MAX_MS+1,'available')],SCHEMA,None),
             ('bigint_overflow_for_timestamp',[(9223372036854775807,'categoryid')],SCHEMA,None),
             ('wrong_type_numeric',[('0','available')],[('timestamp','VARCHAR')]+SCHEMA[1:],None),
             ('wrong_type_unparsed',[('bad','categoryid')],[('timestamp','VARCHAR')]+SCHEMA[1:],None),
             ('wrong_order',[(0,'categoryid')],[SCHEMA[1],SCHEMA[0],*SCHEMA[2:]],None)]
    with tempfile.TemporaryDirectory(prefix='rr-state-time-invalid-',dir=tmp_root) as temporary:
        folder=Path(temporary)
        for label,records,schema,row_override in invalid:
            database=folder/(label+'.duckdb')
            execute(folder,database,setup(records,schema))
            original_hash=previous.sha256(database)
            params=counts(records)
            if row_override is not None:
                params['rows']=row_override
            run,_=execute(folder,database,adjusted(sql,params),readonly=True)
            observed=json.loads(run.stdout)
            assert observed==report_reference(records,params,schema),label
            assert all(row['actual'] is None and row['status']=='BLOCKED' for row in observed[5:10]+observed[12:]),label
            assert previous.sha256(database)==original_hash,label
        cases.append(dict(case='invalid_prerequisites_block_every_derived_metric_without_unsafe_conversion',passed=True,
                          subcases=[case[0] for case in invalid]))
    assert not folder.exists()
    print(json.dumps({'fixture_families_passed':len(cases),'prerequisite_subcases':len(invalid),'changed_control_subcases':3}),flush=True)
    if args.fixtures_only:
        return

    before={name:previous.snapshot(previous.SOURCE_DIR/name) for name in FILES}
    assert all(before[name]['sha256']==previous.SOURCE_HASHES[name] and before[name]['size_bytes']==previous.SOURCE_BYTES[name] for name in FILES)
    historical={str(path.relative_to(root)):previous.sha256(path) for path in (root/'data').glob('*preflight.json') if path.resolve()!=output.resolve()}
    start=time.perf_counter()
    source_stats,population,raw_parts,selected_parts=fold_csv(previous.SOURCE_DIR)
    fold_seconds=round(time.perf_counter()-start,3)
    assert selected_parts==stage_evidence['independent_python_source_counts']['selected_parts']
    expected_report=report_from_stats(source_stats,population,expected)
    with tempfile.TemporaryDirectory(prefix='rr-state-time-real-',dir=tmp_root) as temporary:
        folder,database=Path(temporary),Path(temporary)/'preflight.duckdb'
        _,raw_reconstruction_seconds=execute(folder,database,raw_sql)
        _,stage_reconstruction_seconds=execute(folder,database,stage_sql)
        database_before=previous.sha256(database)
        run,audit_seconds=execute(folder,database,sql,readonly=True)
        report=json.loads(run.stdout)
        assert report==expected_report
        assert [row['status'] for row in report]==['PASS']*12+['INFO']*8
        stream_stats,stream_seconds=stream(folder,database)
        assert stream_stats==source_stats
        database_after=previous.sha256(database)
        assert database_before==database_after
        database_bytes=database.stat().st_size
    assert not folder.exists()
    after={name:previous.snapshot(previous.SOURCE_DIR/name) for name in FILES}
    assert before==after
    assert all(previous.sha256(root/path)==digest for path,digest in hashes.items())
    assert all(previous.sha256(root/path)==digest for path,digest in historical.items())
    assert (root/method_path).read_bytes().startswith(contract)
    evidence=dict(
        checked_at_utc=datetime.now(timezone.utc).isoformat(),executor='assistant',
        engine=subprocess.check_output([args.duckdb,'-version'],text=True).strip(),
        script=script_path,script_sha256=hashes[script_path],validator=validator_path,validator_sha256=hashes[validator_path],
        code_and_dependency_sha256=hashes,method_contract=method_path,method_contract_prefix_bytes=len(contract),method_contract_prefix_sha256=CONTRACT_SHA,
        source_files=FILES,source_before=before,source_after=after,source_hashes_and_metadata_unchanged=True,
        reconstruction_prefix_sha256={'sql/56_import_retailrocket_properties.sql':hashlib.sha256(raw_sql.encode()).hexdigest(),
                                      'sql/65_stage_retailrocket_item_state_observations.sql':hashlib.sha256(stage_sql.encode()).hexdigest()},
        reconstruction_basis='Only frozen SQL56 import and SQL65 creation prefixes; no prior full checks. Separate read-only SQL66 report and per-occurrence stream.',
        source_table='rr_stg.item_state_observations',query_read_only=True,real_audit_script_executions=1,real_private_stream_executions=1,
        real_raw_reconstruction_executions=1,real_staging_reconstruction_executions=1,
        report_rows=20,report_columns=5,output_columns=COLUMNS,actual_expected_types='VARCHAR or NULL; check_order integer',
        checks_passed=12,info_rows=8,fail_rows=0,blocked_rows=0,results=report,report_sha256=previous.report_hash(report),
        report_fingerprint_contract='SHA-256 of ordered compact JSON arrays in output-column order, each followed by LF. actual/expected are strings or JSON null.',
        independent_source_raw_parts=raw_parts,independent_source_selected_parts=selected_parts,independent_source_property_counts=population,
        independent_python_integer_datetime_reference=True,independent_python_source_fold_matched=True,
        independent_python_report_matched=True,independent_stream_occurrences_compared=stream_stats['rows'],independent_stream_fields_compared=4,
        independent_stream_all_occurrences_matched=True,independent_source_and_stream_date_partitions_matched=True,
        utc_date_partition_sha256=date_fingerprint(source_stats),utc_date_partition_fingerprint_contract='Ordered compact JSON [YYYY-MM-DD, occurrence_count] arrays followed by LF.',
        private_database_sha256_before_readonly=database_before,private_database_sha256_after_readonly=database_after,private_database_bytes_unchanged=True,
        supported_epoch_ms_min=0,supported_epoch_ms_max=MAX_MS,time_interpretation='UTC convention applied to timezone-naive TIMESTAMP; not evidence of business local timezone or a precisely timed state change.',
        fixture_case_count=len(cases),fixture_cases=cases,invalid_prerequisite_subcase_count=len(invalid),changed_control_subcase_count=3,
        blocked_dependencies_verified=True,info_requires_all_controls_pass_verified=True,session_timezone_invariance_verified=True,
        preflight_settings=dict(threads=2,memory_limit='1GB',max_temp_directory_size='2GB',timeout_seconds_per_cli_phase=120),
        workspace_free_bytes_before=free_before,workspace_free_bytes_after=shutil.disk_usage(tmp_root).free,
        private_database_bytes_before_cleanup=database_bytes,largest_private_directory_bytes_observed_after_phase=max(sizes),temporary_databases_and_spills_removed=True,
        learner_database_opened=False,other_source_csvs_read=False,historical_comparison_or_analysis_suites_rerun=False,historical_preflight_files_unchanged=len(historical),
        source_records_or_identifiers_exported_or_logged=False,private_per_observation_comparison_files_created=False,
        elapsed_python_source_fold_seconds=fold_seconds,elapsed_raw_reconstruction_seconds=raw_reconstruction_seconds,
        elapsed_staging_reconstruction_seconds=stage_reconstruction_seconds,elapsed_readonly_audit_seconds=audit_seconds,elapsed_private_stream_seconds=stream_seconds,
        timing_scope='Two prefix reconstruction CLI phases, one read-only SQL66 report and one read-only per-occurrence stream; independent selected-source fold timed separately. Hashing/fixtures excluded; not a performance benchmark.',
        scope='Assistant named-observation timestamp audit passed; learner SQL66 pending. No table mutation, deduplication, local-business timezone inference, effective validity interval, exact change time, latest state, event-time property join, conversion rate or inventory/monetary metric. Global selected-history date coverage is not per-item/per-property coverage or proof of complete collection days.')
    output.write_text(json.dumps(evidence,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps({'report_rows':20,'checks_passed':12,'info_rows':8,'occurrences_compared':stream_stats['rows'],
                      'readonly_audit_seconds':audit_seconds,'report_sha256':evidence['report_sha256']}),flush=True)


if __name__=='__main__':
    main()
