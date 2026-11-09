"""Build observation-based intervals and independently compare every selected source interval."""
import argparse
import csv
import hashlib
import heapq
import json
import shutil
import subprocess
import tempfile
import threading
import time
from collections import Counter, defaultdict
from contextlib import ExitStack
from datetime import datetime, timezone
from itertools import zip_longest
from pathlib import Path

import preflight_retailrocket_item_state_observations as staging

previous=staging.previous
FILES=previous.FILES
COLUMNS=previous.COLUMNS
SOURCE_FIELDS=previous.TABLE_FIELDS
SOURCE_SCHEMA=[('timestamp','BIGINT'),('itemid','BIGINT'),('property','VARCHAR'),('value','VARCHAR'),('source_file','VARCHAR')]
FIELDS=['itemid','property','value','observed_from_ms','observed_to_ms','source_file']
MAX_MS=253402300799999
CHUNK_ROWS=50000
CONTRACT_SHA='fd0918667f1e3b42648fd6e0e5be018a564cbd68b18ba62103e7d3bff3bfe060'
CHECK_MARKER='-- CHECKS: if rr_core.item_state_intervals already exists, run only the query below.'
PARAMETER_SQL="""SELECT 2291853::BIGINT AS expected_rows,788214::BIGINT AS expected_category_rows,
        1503639::BIGINT AS expected_available_rows,253402300799999::BIGINT AS max_supported_ms"""
CHECKS=['source_rows','source_schema_mismatch','source_contract_violations','interval_rows','interval_schema_mismatch',
        'categoryid_rows','available_rows','missing_required_rows','invalid_start_rows','invalid_end_rows',
        'invalid_value_rows','unknown_source_file_rows','candidate_key_surplus','source_only_rows','interval_only_rows',
        'endpoint_mismatch_rows','open_end_group_errors','open_end_position_errors','finite_link_count_difference',
        'interval_pair_count_difference','item_property_pairs','finite_intervals','open_intervals','unchanged_next_value_links']
PRIVATE_ROWS='SELECT '+','.join(FIELDS)+' FROM rr_core.item_state_intervals;'
PRIVATE_SOURCE='SELECT '+','.join(SOURCE_FIELDS)+' FROM rr_stg.item_state_observations;'
PRIVATE_STREAM="""SELECT itemid,property,value,observed_from_ms,
    COALESCE(CAST(observed_to_ms AS VARCHAR),'__OPEN__'),source_file
    FROM rr_core.item_state_intervals ORDER BY itemid,property,observed_from_ms;"""


def source_counts(rows):
    return dict(rows=len(rows),categoryid=sum(row[2]=='categoryid' for row in rows),
                available=sum(row[2]=='available' for row in rows))


def adjusted(sql,rows,override=None):
    expected={**source_counts(rows),**(override or {})}
    replacement=(f"SELECT {expected['rows']}::BIGINT AS expected_rows,"
                 f"{expected['categoryid']}::BIGINT AS expected_category_rows,"
                 f"{expected['available']}::BIGINT AS expected_available_rows,{MAX_MS}::BIGINT AS max_supported_ms")
    assert sql.count(PARAMETER_SQL)==2
    return sql.replace(PARAMETER_SQL,replacement)


def ordered_source(row):
    return (int(row[1]),row[2],int(row[0]),row[3],row[4])


def blank_interval_stats():
    return dict(rows=0,item_property_pairs=0,finite_intervals=0,open_intervals=0,unchanged_next_value_links=0)


def expected_intervals(records,stats):
    prior=None
    for row in records:
        if prior is None:
            stats['item_property_pairs']+=1
        else:
            same=prior[:2]==row[:2]
            if same:
                assert prior[2]<row[2],'Private source candidate key is not unique or ordered; values withheld'
                end=row[2]
                stats['finite_intervals']+=1
                stats['unchanged_next_value_links']+=prior[3]==row[3]
            else:
                assert prior[:2]<row[:2],'Private history ordering differs; values withheld'
                end=None
                stats['open_intervals']+=1
                stats['item_property_pairs']+=1
            stats['rows']+=1
            yield (prior[0],prior[1],prior[3],prior[2],end,prior[4])
        prior=row
    if prior is not None:
        stats['rows']+=1;stats['open_intervals']+=1
        yield (prior[0],prior[1],prior[3],prior[2],None,prior[4])


def make_report(actual,expected):
    return [dict(check_order=i,check_name=name,actual=value,expected=target,
                 status='BLOCKED' if value is None else 'INFO' if target is None else 'PASS' if value==target else 'FAIL')
            for i,(name,value,target) in enumerate(zip(CHECKS,actual,expected),1)]


def healthy_report(population,interval_stats):
    assert interval_stats['rows']==population['rows']
    assert interval_stats['open_intervals']==interval_stats['item_property_pairs']
    assert interval_stats['finite_intervals']+interval_stats['open_intervals']==population['rows']
    controls=[population['rows'],0,0,population['rows'],0,population['categoryid'],population['available']]+[0]*13
    observed=[interval_stats[name] for name in CHECKS[20:]]
    return make_report(controls+observed,controls+[None]*4)


def report_reference(source,intervals):
    # Tiny synthetic fixtures only; no real records are collected into counters or dictionaries.
    population=source_counts(source)
    reference_stats=blank_interval_stats()
    expected=list(expected_intervals(sorted(ordered_source(row) for row in source),reference_stats))
    projected_source=Counter((row[1],row[2],row[3],row[0],row[4]) for row in source)
    projected_target=Counter((row[0],row[1],row[2],row[3],row[5]) for row in intervals)
    groups=defaultdict(list)
    keys=defaultdict(list)
    for row in intervals:
        groups[row[:2]].append(row)
        keys[(row[0],row[1],row[3])].append(row)
    endpoint_errors=0
    for row in expected:
        matches=keys.get((row[0],row[1],row[3]),[])
        endpoint_errors+=sum(row[4]!=match[4] for match in matches) if matches else row[4] is not None
    finite=sum(row[4] is not None for row in intervals)
    opens=len(intervals)-finite
    group_errors=sum(sum(row[4] is None for row in rows)!=1 for rows in groups.values())
    position_errors=sum(row[4] is None and row[3]!=max(item[3] for item in groups[row[:2]]) for row in intervals)
    unchanged=0
    for rows in groups.values():
        ordered=sorted(rows,key=lambda row:row[3])
        unchanged+=sum(left[2]==right[2] for left,right in zip(ordered,ordered[1:]))
    actual=[len(source),0,0,len(intervals),0,sum(row[1]=='categoryid' for row in intervals),sum(row[1]=='available' for row in intervals),
            sum(any(row[i] is None or row[i]=='' for i in [0,1,2,3,5]) for row in intervals),
            sum(row[3] is None or not 0<=row[3]<=MAX_MS for row in intervals),
            sum(row[4] is not None and not (0<=row[4]<=MAX_MS and row[4]>row[3]) for row in intervals),
            sum(not staging.valid_value(row[1],row[2]) for row in intervals),sum(row[5] not in FILES for row in intervals),
            len(intervals)-len(keys),sum((projected_source-projected_target).values()),sum((projected_target-projected_source).values()),
            endpoint_errors,group_errors,position_errors,finite-(len(intervals)-len(groups)),len(groups)-reference_stats['item_property_pairs']]
    targets=[population['rows'],0,0,population['rows'],0,population['categoryid'],population['available']]+[0]*13
    actual+= [len(groups),finite,opens,unchanged] if actual==targets else [None]*4
    return make_report(actual,targets+[None]*4)


def setup(rows,schema=SOURCE_SCHEMA):
    query='CREATE SCHEMA rr_stg; CREATE TABLE rr_stg.item_state_observations ('+','.join(name+' '+kind for name,kind in schema)+');\n'
    if rows:
        def literal(value):
            return 'NULL' if value is None else "'"+str(value).replace("'","''")+"'"
        ordered=[]
        for row in rows:
            logical=dict(zip(SOURCE_FIELDS,row))
            ordered.append('('+','.join(literal(logical[name]) for name,_ in schema)+')')
        query+='INSERT INTO rr_stg.item_state_observations VALUES '+','.join(ordered)+';\n'
    return query


def sorted_source_chunks(source_dir,folder,chunk_rows=CHUNK_ROWS):
    paths,chunk=[],[]
    stats=dict(raw_rows=0,raw_parts={name:0 for name in FILES},rows=0,selected_parts={name:0 for name in FILES},
               categoryid=0,available=0,other_rows=0)
    def flush():
        chunk.sort()
        path=folder/f'interval-source-{len(paths):04d}.csv'
        with path.open('w',encoding='utf-8',newline='') as output:
            csv.writer(output).writerows(chunk)
        paths.append(path);chunk.clear()
    for name in FILES:
        with (source_dir/name).open('r',encoding='utf-8',newline='') as stream:
            reader=csv.reader(stream,strict=True)
            assert next(reader)==previous.RAW_FIELDS
            for row in reader:
                assert len(row)==4,'Private source record width differs'
                stats['raw_rows']+=1;stats['raw_parts'][name]+=1
                if row[2] not in staging.NAMES:
                    stats['other_rows']+=1;continue
                record=tuple(row)+(name,)
                assert staging.valid_named(record) and int(row[0])<=MAX_MS,'Private source interval input invalid; record withheld'
                stats['rows']+=1;stats['selected_parts'][name]+=1;stats[row[2]]+=1
                chunk.append(ordered_source(record))
                if len(chunk)==chunk_rows:
                    flush()
    if chunk:
        flush()
    assert stats['rows']>0 and stats['raw_rows']==stats['rows']+stats['other_rows']
    return paths,stats


def merged_source(paths):
    def numeric(reader):
        for row in reader:
            assert len(row)==5
            yield (int(row[0]),row[1],int(row[2]),row[3],row[4])
    with ExitStack() as stack:
        streams=[numeric(csv.reader(stack.enter_context(path.open('r',encoding='utf-8',newline='')),strict=True)) for path in paths]
        yield from heapq.merge(*streams)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--duckdb',required=True)
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--fixtures-only',action='store_true')
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    script_path='sql/67_build_retailrocket_item_state_intervals.sql'
    validator_path='validation/preflight_retailrocket_item_state_intervals.py'
    method_path='docs/RETAILROCKET_ITEM_STATE_INTERVALS_VALIDATION.md'
    output=root/'data/retailrocket_item_state_intervals_preflight.json'
    assert args.output.resolve()==output.resolve()
    dependencies=[script_path,validator_path,'sql/56_import_retailrocket_properties.sql','sql/65_stage_retailrocket_item_state_observations.sql',
                  'validation/preflight_retailrocket_properties_import.py','validation/preflight_retailrocket_item_state_observations.py',
                  'data/retailrocket_source_audit.json','data/retailrocket_item_state_observations_preflight.json',
                  'data/retailrocket_item_state_observations_learner_acceptance.json','data/retailrocket_item_state_time_preflight.json',
                  'data/retailrocket_item_state_time_learner_acceptance.json','docs/RETAILROCKET_ITEM_STATE_TIME_VALIDATION.md']
    hashes={path:previous.sha256(root/path) for path in dependencies}
    contract=(root/method_path).read_bytes().split(b'\n## Executed results\n',1)[0]
    assert hashlib.sha256(contract).hexdigest()==CONTRACT_SHA
    sql=(root/script_path).read_text(encoding='utf-8')
    assert sql.count(CHECK_MARKER)==1 and 'CREATE TABLE rr_core.item_state_intervals AS' in sql
    assert 'OR REPLACE' not in sql and 'CREATE TABLE IF NOT EXISTS' not in sql
    create,checks=sql.split(CHECK_MARKER,1)
    raw_sql=(root/'sql/56_import_retailrocket_properties.sql').read_text(encoding='utf-8').split('-- CHECKS:',1)[0]
    stage_sql=(root/'sql/65_stage_retailrocket_item_state_observations.sql').read_text(encoding='utf-8').split(staging.CHECK_MARKER,1)[0]
    assert raw_sql.count('read_csv(')==2 and 'EXCEPT ALL' not in raw_sql+stage_sql
    old_stage=json.loads((root/'data/retailrocket_item_state_observations_preflight.json').read_text(encoding='utf-8'))
    old_time=json.loads((root/'data/retailrocket_item_state_time_preflight.json').read_text(encoding='utf-8'))
    assert old_stage['script_sha256']==hashes['sql/65_stage_retailrocket_item_state_observations.sql']
    for path,code in [('sql/56_import_retailrocket_properties.sql',raw_sql),('sql/65_stage_retailrocket_item_state_observations.sql',stage_sql)]:
        assert hashlib.sha256(code.encode()).hexdigest()==old_time['reconstruction_prefix_sha256'][path]
    for label,evidence in [('item_state_observations',old_stage),('item_state_time',old_time)]:
        acceptance=json.loads((root/f'data/retailrocket_{label}_learner_acceptance.json').read_text(encoding='utf-8'))
        assert acceptance['acceptance_status']=='accepted' and acceptance['report_sha256']==evidence['report_sha256']
    assert old_time['supported_epoch_ms_max']==MAX_MS and old_time['checks_passed']==12
    audit=json.loads((root/'data/retailrocket_source_audit.json').read_text(encoding='utf-8'))
    assert audit['all_checks_passed']
    for name in FILES:
        assert audit['files'][name]['sha256']==previous.SOURCE_HASHES[name]
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
        assert size<=5*1024**3
        sizes.append(size)

    def execute(folder,database,query,allow_error=False,readonly=False):
        started=time.perf_counter()
        run=subprocess.run([args.duckdb,str(database),'-bail','-json']+(['-readonly'] if readonly else []),
                           input=settings(folder,database)+query,text=True,encoding='utf-8',capture_output=True,timeout=120)
        if not allow_error:
            assert run.returncode==0,'Private interval execution failed; row-bearing diagnostics withheld'
        observe(folder)
        return run,round(time.perf_counter()-started,3)

    def compare_stream(folder,database,chunks):
        started,timed_out=time.perf_counter(),threading.Event()
        process=subprocess.Popen([args.duckdb,str(database),'-bail','-readonly','-csv','-noheader'],stdin=subprocess.PIPE,
                                 stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,encoding='utf-8')
        def expire():
            timed_out.set();process.kill()
        timer=threading.Timer(120,expire);timer.start()
        stats=blank_interval_stats();sentinel=object();count=0
        try:
            process.stdin.write(settings(folder,database)+PRIVATE_STREAM);process.stdin.close()
            for observed,expected in zip_longest(csv.reader(process.stdout,strict=True),expected_intervals(merged_source(chunks),stats),fillvalue=sentinel):
                assert observed is not sentinel and expected is not sentinel,'Private interval row count differs'
                assert len(observed)==6,'Private interval stream width differs'
                actual=(int(observed[0]),observed[1],observed[2],int(observed[3]),None if observed[4]=='__OPEN__' else int(observed[4]),observed[5])
                assert actual==expected,'Private six-field interval differs; values withheld'
                count+=1
            assert process.wait(timeout=120)==0 and not timed_out.is_set(),'Private interval stream failed or timed out'
        finally:
            timer.cancel()
            if process.poll() is None:
                process.kill();process.wait()
            process.stdout.close()
        assert count==stats['rows']
        observe(folder)
        return stats,round(time.perf_counter()-started,3)

    cases=[]
    p1,p2=FILES
    fixture=[(10,2,'categoryid','7',p1),(1,10,'available','0',p1),(9,2,'categoryid','001',p2),
             (1,2,'categoryid','001',p2),(2,2,'available','1',p1),(11,2,'available','1',p2),
             (3,10,'categoryid','8',p2),(0,11,'available','0',p1)]
    with tempfile.TemporaryDirectory(prefix='rr-interval-fixture-',dir=tmp_root) as temporary:
        folder,database=Path(temporary),Path(temporary)/'fixture.duckdb'
        parts=[[tuple(str(value) for value in row[:4]) for row in fixture if row[4]==name] for name in FILES]
        parts[0].append(('0','20','999','opaque'))
        previous.write_fixture(folder,parts)
        chunks,fixture_source_stats=sorted_source_chunks(folder,folder,chunk_rows=2)
        assert len(chunks)==4 and fixture_source_stats['raw_rows']==9 and fixture_source_stats['other_rows']==1
        query=adjusted(sql,fixture)
        run,_=execute(folder,database,setup(fixture)+query+PRIVATE_ROWS)
        report,rows=previous.json_outputs(run.stdout)
        intervals=[tuple(row[field] for field in FIELDS) for row in rows]
        assert report==report_reference(fixture,intervals)
        assert [row['status'] for row in report]==['PASS']*20+['INFO']*4
        compared,_=compare_stream(folder,database,chunks)
        assert compared==dict(rows=8,item_property_pairs=5,finite_intervals=3,open_intervals=5,unchanged_next_value_links=2)
        probes="""WITH probes(label,instant) AS (VALUES ('before',0),('first',1),('between',5),('next',9),('last',10),('later',99))
            SELECT p.label,i.observed_from_ms FROM probes p LEFT JOIN rr_core.item_state_intervals i
            ON i.itemid=2 AND i.property='categoryid' AND p.instant>=i.observed_from_ms
            AND (p.instant<i.observed_to_ms OR i.observed_to_ms IS NULL) ORDER BY p.instant;"""
        run,_=execute(folder,database,probes,readonly=True)
        assert json.loads(run.stdout)==[dict(label=label,observed_from_ms=start) for label,start in
                                      [('before',None),('first',1),('between',1),('next',9),('last',10),('later',10)]]
        cases.append(dict(case='numeric_cross_chunk_order_original_values_equal_links_open_tail_and_half_open_synthetic_probes',passed=True,
                          raw_fixture_rows=9,selected_fixture_rows=8,comparison_chunks=4))
        adjusted_checks=query.split(CHECK_MARKER,1)[1]
        for label,mutation in [('nonadjacent_end',"UPDATE rr_core.item_state_intervals SET observed_to_ms=10 WHERE itemid=2 AND property='categoryid' AND observed_from_ms=1;"),
                               ('provenance',"UPDATE rr_core.item_state_intervals SET observed_to_ms=9,source_file='item_properties_part1.csv' WHERE itemid=2 AND property='categoryid' AND observed_from_ms=1;")]:
            run,_=execute(folder,database,mutation+adjusted_checks+PRIVATE_ROWS)
            report,rows=previous.json_outputs(run.stdout)
            changed=[tuple(row[field] for field in FIELDS) for row in rows]
            assert report==report_reference(fixture,changed),label
            assert all(row['status']=='BLOCKED' and row['actual'] is None for row in report[20:]),label
            required='endpoint_mismatch_rows' if label=='nonadjacent_end' else 'source_only_rows'
            assert next(row for row in report if row['check_name']==required)['status']=='FAIL',label
        sentinel=Counter(changed)
        rejected,_=execute(folder,database,query.split(CHECK_MARKER,1)[0],allow_error=True)
        assert rejected.returncode!=0
        run,_=execute(folder,database,PRIVATE_ROWS,readonly=True)
        assert Counter(tuple(row[field] for field in FIELDS) for row in json.loads(run.stdout))==sentinel
        cases.append(dict(case='nonadjacent_endpoint_and_same_count_provenance_mutations_block_info_existing_target_preserved',passed=True))
    assert not folder.exists()

    base=(1,1,'categoryid','7',p1)
    invalid=[('empty',[],None),('wrong_count',[base],{'rows':2}),('missing_key',[(1,None,'categoryid','7',p1)],None),
             ('negative_item',[(1,-1,'categoryid','7',p1)],None),('negative_time',[(-1,1,'categoryid','7',p1)],None),
             ('unsupported_time',[(MAX_MS+1,1,'categoryid','7',p1)],None),('invalid_availability',[(1,1,'available','2',p1)],None),
             ('invalid_category',[(1,1,'categoryid','bad',p1)],None),('unknown_provenance',[(1,1,'categoryid','7','unknown.csv')],None),
             ('duplicate_key',[base,(1,1,'categoryid','7',p2)],None),('conflicting_key',[base,(1,1,'categoryid','8',p2)],None)]
    with tempfile.TemporaryDirectory(prefix='rr-interval-invalid-',dir=tmp_root) as temporary:
        folder=Path(temporary)
        for label,rows,override in invalid:
            database=folder/(label+'.duckdb')
            rejected,_=execute(folder,database,setup(rows)+adjusted(sql,rows,override),allow_error=True)
            assert rejected.returncode!=0 and 'SQL67 observation interval contract failed' in rejected.stderr,label
            run,_=execute(folder,database,"SELECT COUNT(*) AS targets FROM information_schema.tables WHERE table_schema='rr_core' AND table_name='item_state_intervals';"+PRIVATE_SOURCE,readonly=True)
            target,source=previous.json_outputs(run.stdout)
            assert target==[{'targets':0}] and Counter(tuple(row[field] for field in SOURCE_FIELDS) for row in source)==Counter(rows),label
        for label,schema,rows in [('wrong_type',[('timestamp','VARCHAR')]+SOURCE_SCHEMA[1:],[('1',1,'categoryid','7',p1)]),
                                 ('wrong_order',[SOURCE_SCHEMA[1],SOURCE_SCHEMA[0],*SOURCE_SCHEMA[2:]],[base])]:
            database=folder/(label+'.duckdb')
            rejected,_=execute(folder,database,setup(rows,schema)+adjusted(sql,rows),allow_error=True)
            assert rejected.returncode!=0 and 'SQL67 observation interval contract failed' in rejected.stderr,label
            run,_=execute(folder,database,"SELECT COUNT(*) AS targets FROM information_schema.tables WHERE table_schema='rr_core' AND table_name='item_state_intervals';"+PRIVATE_SOURCE,readonly=True)
            target,source=previous.json_outputs(run.stdout)
            assert target==[{'targets':0}] and Counter(tuple(row[field] for field in SOURCE_FIELDS) for row in source)==Counter(rows),label
        cases.append(dict(case='invalid_source_counts_identity_time_value_provenance_keys_and_schema_rejected_atomically',passed=True,
                          expected_rejection=True,subcases=[case[0] for case in invalid]+['wrong_type','wrong_order']))
    assert not folder.exists()
    print(json.dumps({'fixture_families_passed':len(cases),'rejection_subcases':len(invalid)+2}),flush=True)
    if args.fixtures_only:
        return

    before={name:previous.snapshot(previous.SOURCE_DIR/name) for name in FILES}
    assert all(before[name]['sha256']==previous.SOURCE_HASHES[name] and before[name]['size_bytes']==previous.SOURCE_BYTES[name] for name in FILES)
    historical={str(path.relative_to(root)):previous.sha256(path) for path in (root/'data').glob('*preflight.json') if path.resolve()!=output.resolve()}
    with tempfile.TemporaryDirectory(prefix='rr-interval-real-',dir=tmp_root) as temporary:
        folder,database=Path(temporary),Path(temporary)/'preflight.duckdb'
        started=time.perf_counter()
        chunks,source_stats=sorted_source_chunks(previous.SOURCE_DIR,folder)
        sort_seconds=round(time.perf_counter()-started,3)
        assert source_stats['raw_rows']==20275902 and source_stats['raw_parts']==previous.SOURCE_ROWS
        population={name:source_stats[name] for name in ['rows','categoryid','available']}
        assert population==dict(rows=2291853,categoryid=788214,available=1503639)
        assert source_stats['selected_parts']==old_stage['independent_python_source_counts']['selected_parts']
        assert source_stats['other_rows']==17984049
        chunk_count,chunk_bytes=len(chunks),sum(path.stat().st_size for path in chunks)
        _,raw_seconds=execute(folder,database,raw_sql)
        _,stage_seconds=execute(folder,database,stage_sql)
        run,interval_seconds=execute(folder,database,sql)
        report=json.loads(run.stdout)
        assert [row['status'] for row in report]==['PASS']*20+['INFO']*4
        database_before=previous.sha256(database)
        interval_stats,stream_seconds=compare_stream(folder,database,chunks)
        assert interval_stats['rows']==source_stats['rows']
        assert report==healthy_report(population,interval_stats)
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
        reconstruction_basis='Frozen SQL56 raw import and SQL65 typed creation prefixes only; no prior full comparison checks. One SQL67 construction/report and one read-only interval comparison stream.',
        table='rr_core.item_state_intervals',interval_fields=FIELDS,interval_types=['BIGINT','VARCHAR','VARCHAR','BIGINT','BIGINT','VARCHAR'],
        nullable_fields=['observed_to_ms'],raw_rows=20275902,selected_rows=2291853,opaque_complement_rows=17984049,
        real_raw_reconstruction_executions=1,real_staging_reconstruction_executions=1,real_interval_script_executions=1,real_private_comparison_stream_executions=1,
        report_rows=24,report_columns=5,output_columns=COLUMNS,checks_passed=20,info_rows=4,fail_rows=0,blocked_rows=0,
        results=report,report_sha256=previous.report_hash(report),report_fingerprint_contract='SHA-256 of ordered compact JSON arrays in output-column order, each followed by LF; actual/expected are integer counts or JSON null.',
        independent_python_source_counts=source_stats,independent_python_interval_counts=interval_stats,
        independent_python_numeric_sort_and_lookahead=True,independent_python_report_matched=True,
        independent_stream_rows_compared=interval_stats['rows'],independent_stream_fields_compared=6,independent_full_six_field_interval_stream_matched=True,
        original_value_spellings_and_provenance_preserved=True,consecutive_equal_value_rows_retained=True,half_open_boundary_assignment_fixture_verified=True,
        open_endpoint_marker='__OPEN__',open_endpoint_meaning='No later observation recorded for this item/property; actual next boundary and freshness are unknown.',
        private_database_sha256_before_readonly_stream=database_before,private_database_sha256_after_readonly_stream=database_after,private_stream_database_bytes_unchanged=True,
        fixture_case_count=len(cases),fixture_cases=cases,rejection_subcase_count=len(invalid)+2,
        invalid_creation_destination_absence_verified=True,existing_destination_sentinel_preserved=True,
        nonadjacent_endpoint_mutation_detected=True,same_count_provenance_mutation_detected=True,info_requires_all_controls_pass_verified=True,
        preflight_settings=dict(threads=2,memory_limit='1GB',max_temp_directory_size='2GB',timeout_seconds_per_cli_phase=120,
                                python_sort_chunk_rows=CHUNK_ROWS,private_directory_budget_bytes=5*1024**3),
        private_selected_source_comparison_chunks=chunk_count,private_selected_source_comparison_chunk_bytes=chunk_bytes,
        private_comparison_spool_scope='Only selected source tuples with numeric item/time sorting were spooled; original property values and source_file retained. All chunks removed with their owning private directory.',
        workspace_free_bytes_before=free_before,workspace_free_bytes_after=shutil.disk_usage(tmp_root).free,
        private_database_bytes_before_cleanup=database_bytes,largest_private_directory_bytes_observed_after_phase=max(sizes),
        temporary_databases_and_spills_removed=True,private_selected_source_comparison_spools_removed=True,
        learner_database_opened=False,other_source_csvs_read=False,historical_comparison_or_analysis_suites_rerun=False,
        historical_preflight_files_unchanged=len(historical),source_records_or_identifiers_uploaded_or_logged=False,
        elapsed_python_scan_select_sort_seconds=sort_seconds,elapsed_raw_reconstruction_seconds=raw_seconds,
        elapsed_staging_reconstruction_seconds=stage_seconds,elapsed_interval_and_checks_seconds=interval_seconds,elapsed_private_stream_seconds=stream_seconds,
        timing_scope='Four CLI phases: raw prefix, typed prefix, SQL67 construction/checks and read-only interval stream. Independent two-source numeric selection/sort timed separately; hashing/fixtures excluded; not a performance benchmark.',
        scope='Assistant observation-interval model passed; learner SQL67 pending. All original selected observations remain. [from,to) is an assignment convention, NULL tail is unknown next boundary, not unlimited freshness or known business validity. No real event join, backward fill, global cutoff, state collapse, reference repair, inventory, conversion or causal outcome.')
    output.write_text(json.dumps(evidence,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps({'report_rows':24,'checks_passed':20,'info_rows':4,'interval_rows_compared':interval_stats['rows'],
                      'interval_and_checks_seconds':interval_seconds,'report_sha256':evidence['report_sha256']}),flush=True)


if __name__=='__main__':
    main()
