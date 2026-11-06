"""Type only named property observations; compare exact selected source multisets."""
import argparse
import csv
import heapq
import json
import re
import shutil
import subprocess
import tempfile
import threading
import time
import hashlib
from collections import Counter
from contextlib import ExitStack
from datetime import datetime, timezone
from itertools import zip_longest
from pathlib import Path

import preflight_retailrocket_properties_import as previous

FIELDS=previous.TABLE_FIELDS
FILES=previous.FILES
NAMES=('categoryid','available')
COLUMNS=previous.COLUMNS
LIMIT=9223372036854775807
CHUNK_ROWS=50000
CHECK_MARKER='-- CHECKS: if rr_stg.item_state_observations already exists, run only the query below.'
CONTRACT_SHA='b83200620a8734c1da2e8b0948886bd937e5007591afaad7109709fa345c4836'
COUNT_SQL="""SELECT 20275902::BIGINT AS expected_raw_rows,10999999::BIGINT AS expected_part1,
        9275903::BIGINT AS expected_part2,2291853::BIGINT AS expected_selected_rows,
        788214::BIGINT AS expected_category_rows,1503639::BIGINT AS expected_available_rows,
        17984049::BIGINT AS expected_other_rows"""
CHECKS=['raw_rows','raw_part1_rows','raw_part2_rows','raw_schema_mismatch','raw_unknown_source_rows',
        'staging_rows','staging_schema_mismatch','categoryid_rows','available_rows','other_property_rows',
        'missing_required_rows','negative_numeric_rows','value_rule_violations','unexpected_property_rows',
        'unknown_source_file_rows','candidate_key_surplus','raw_key_value_violations','raw_only_rows',
        'staging_only_rows','source_contract_violations','selected_part1_rows','selected_part2_rows']
TARGETS=[20275902,10999999,9275903,0,0,2291853,0,788214,1503639,17984049]+[0]*10+[None,None]
PRIVATE_ROWS=('SELECT timestamp,itemid,property,value,source_file FROM rr_raw.item_properties; '
              'SELECT timestamp,itemid,property,value,source_file FROM rr_stg.item_state_observations;')


def numeric_value(value):
    if not isinstance(value,str) or re.fullmatch('[0-9]+',value) is None:
        return False
    significant=value.lstrip('0') or '0'
    return len(significant)<=19 and int(significant)<=LIMIT


def canonical_key(value):
    return numeric_value(value) and value==(value.lstrip('0') or '0')


def valid_value(property_name,value):
    return (property_name=='categoryid' and numeric_value(value)) or (property_name=='available' and value in ('0','1'))


def valid_named(row):
    return canonical_key(row[0]) and canonical_key(row[1]) and valid_value(row[2],row[3])


def as_text(row):
    return tuple(None if value is None else str(value) for value in row)


def as_typed(row):
    return (int(row[0]),int(row[1]),*row[2:])


def tuples(records):
    return [tuple(row[field] for field in FIELDS) for row in records]


def subset(rows):
    return [row for row in rows if row[2] in NAMES]


def parameter_values(rows):
    selected=subset(rows)
    return [len(rows),sum(row[4]==FILES[0] for row in rows),sum(row[4]==FILES[1] for row in rows),
            len(selected),sum(row[2]=='categoryid' for row in selected),sum(row[2]=='available' for row in selected),
            len(rows)-len(selected)]


def adjusted(sql,rows,override=None):
    values=parameter_values(rows)
    if override:
        for index,value in override.items():
            values[index]=value
    names=['expected_raw_rows','expected_part1','expected_part2','expected_selected_rows',
           'expected_category_rows','expected_available_rows','expected_other_rows']
    assert sql.count(COUNT_SQL)==2
    return sql.replace(COUNT_SQL,'SELECT '+','.join(f'{value}::BIGINT AS {name}' for name,value in zip(names,values)))


def report_reference(raw,staged):
    n,p1,p2,selected_count,category_count,available_count,other=parameter_values(raw)
    selected=subset(raw)
    source_counter,stage_counter=Counter(selected),Counter(as_text(row) for row in staged)
    raw_unknown=sum(row[4] not in FILES for row in raw)
    invalid=sum(not valid_named(row) for row in selected)
    raw_key_surplus=len(selected)-len({row[:3] for row in selected})
    valid=n>0 and selected_count>0 and raw_unknown==invalid==raw_key_surplus==0
    actual=[n,p1,p2,0,raw_unknown,len(staged),0,sum(row[2]=='categoryid' for row in staged),
            sum(row[2]=='available' for row in staged),other,
            sum(any(value is None or value=='' for value in row) for row in staged),
            sum(any(value is not None and value<0 for value in row[:2]) for row in staged),
            sum(not valid_value(row[2],row[3]) for row in staged),sum(row[2] not in NAMES for row in staged),
            sum(row[4] not in FILES for row in staged),len(staged)-len({row[:3] for row in staged}),invalid,
            sum((source_counter-stage_counter).values()),sum((stage_counter-source_counter).values()),int(not valid)]
    expected=[n,p1,p2,0,0,selected_count,0,category_count,available_count,other]+[0]*10
    actual += [sum(row[4]==name for row in staged) for name in FILES] if actual==expected else [None,None]
    return make_report(actual,expected+[None,None])


def make_report(actual,expected):
    return [dict(check_order=i,check_name=name,actual=value,expected=target,
                 status='BLOCKED' if value is None else 'INFO' if target is None else 'PASS' if value==target else 'FAIL')
            for i,(name,value,target) in enumerate(zip(CHECKS,actual,expected),1)]


def setup(rows,schema=None):
    schema=schema or [(name,'VARCHAR') for name in FIELDS]
    query='CREATE SCHEMA rr_raw; CREATE TABLE rr_raw.item_properties ('+','.join(name+' '+kind for name,kind in schema)+');\n'
    if rows:
        def literal(value):
            return 'NULL' if value is None else "'"+str(value).replace("'","''")+"'"
        ordered=[]
        for row in rows:
            logical=dict(zip(FIELDS,row))
            ordered.append('('+','.join(literal(logical[name]) for name,_ in schema)+')')
        query+='INSERT INTO rr_raw.item_properties VALUES '+','.join(ordered)+';\n'
    return query


def sorted_source_chunks(source_dir,folder,chunk_rows=CHUNK_ROWS):
    paths,chunk=[],[]
    stats=dict(raw_rows=0,raw_parts={name:0 for name in FILES},selected_rows=0,
               selected_parts={name:0 for name in FILES},categoryid_rows=0,available_rows=0,other_rows=0)
    def flush():
        chunk.sort()
        path=folder/f'selected-comparison-{len(paths):04d}.csv'
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
                if row[2] not in NAMES:
                    stats['other_rows']+=1
                    continue
                record=tuple(row)+(name,)
                assert valid_named(record),'Private named source violates typing/value contract; record withheld'
                stats['selected_rows']+=1;stats['selected_parts'][name]+=1
                stats[row[2]+'_rows']+=1
                chunk.append(record)
                if len(chunk)==chunk_rows:
                    flush()
    if chunk:
        flush()
    assert stats['selected_rows']>0 and stats['raw_rows']==stats['selected_rows']+stats['other_rows']
    return paths,stats


def merged_source(paths):
    with ExitStack() as stack:
        readers=[map(tuple,csv.reader(stack.enter_context(path.open('r',encoding='utf-8',newline='')),strict=True)) for path in paths]
        yield from heapq.merge(*readers)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--duckdb',required=True)
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--fixtures-only',action='store_true')
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    script_path='sql/65_stage_retailrocket_item_state_observations.sql'
    validator_path='validation/preflight_retailrocket_item_state_observations.py'
    method_path='docs/RETAILROCKET_ITEM_STATE_OBSERVATIONS_VALIDATION.md'
    output=root/'data/retailrocket_item_state_observations_preflight.json'
    assert args.output.resolve()==output.resolve()
    dependencies=[script_path,validator_path,'sql/56_import_retailrocket_properties.sql',
                  'validation/preflight_retailrocket_properties_import.py','data/retailrocket_source_audit.json',
                  'data/retailrocket_properties_import_preflight.json','data/retailrocket_properties_import_learner_acceptance.json',
                  'data/retailrocket_property_keys_preflight.json','data/retailrocket_property_keys_learner_acceptance.json',
                  'data/retailrocket_named_properties_preflight.json','data/retailrocket_named_properties_learner_acceptance.json',
                  'data/retailrocket_unmatched_categories_preflight.json']
    hashes={path:previous.sha256(root/path) for path in dependencies}
    contract=(root/method_path).read_bytes().split(b'\n## Executed results\n',1)[0]
    assert hashlib.sha256(contract).hexdigest()==CONTRACT_SHA
    sql=(root/script_path).read_text(encoding='utf-8')
    assert 'CREATE TABLE rr_stg.item_state_observations AS' in sql and 'OR REPLACE' not in sql and 'CREATE TABLE IF NOT EXISTS' not in sql
    assert sql.count(CHECK_MARKER)==1 and sql.count('EXCEPT ALL')==2
    raw_sql=(root/'sql/56_import_retailrocket_properties.sql').read_text(encoding='utf-8').split('-- CHECKS:',1)[0]
    assert raw_sql.count('read_csv(')==2 and 'EXCEPT ALL' not in raw_sql
    old=json.loads((root/'data/retailrocket_properties_import_preflight.json').read_text(encoding='utf-8'))
    assert old['script_sha256']==hashes['sql/56_import_retailrocket_properties.sql'] and old['checks_passed']==14
    named=json.loads((root/'data/retailrocket_named_properties_preflight.json').read_text(encoding='utf-8'))
    named_values={row['check_name']:row['actual'] for row in named['results']}
    assert [named_values[name] for name in ['categoryid_rows','available_rows','other_property_rows','category_unmatched_exact_rows']]==[788214,1503639,17984049,167]
    keys=json.loads((root/'data/retailrocket_property_keys_preflight.json').read_text(encoding='utf-8'))
    key_values={row['check_name']:row['actual'] for row in keys['results']}
    assert key_values['raw_rows']==20275902 and key_values['candidate_keys']==20275902
    audit=json.loads((root/'data/retailrocket_source_audit.json').read_text(encoding='utf-8'))
    assert audit['all_checks_passed']
    for name in FILES:
        assert audit['files'][name]['sha256']==previous.SOURCE_HASHES[name]
    tmp_root=root/'tmp';tmp_root.mkdir(exist_ok=True)
    free_before=shutil.disk_usage(tmp_root).free
    assert free_before>=6*1024**3
    memory_before=previous.memory_availability()
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
            assert run.returncode==0,'Private named-property execution failed; row-bearing diagnostics withheld'
        observe(folder)
        return run,round(time.perf_counter()-started,3)

    def compare_stream(folder,database,table,chunks):
        assert table in ('rr_raw.item_properties','rr_stg.item_state_observations')
        projection=','.join(f'CAST({field} AS VARCHAR)' for field in FIELDS)
        selection=" WHERE property IN ('categoryid','available')" if table=='rr_raw.item_properties' else ''
        query='SELECT '+projection+' FROM '+table+selection+' ORDER BY 1,2,3,4,5;'
        started,timed_out=time.perf_counter(),threading.Event()
        process=subprocess.Popen([args.duckdb,str(database),'-bail','-readonly','-csv','-noheader'],stdin=subprocess.PIPE,
                                 stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,encoding='utf-8')
        def expire():
            timed_out.set();process.kill()
        timer=threading.Timer(120,expire);timer.start()
        rows,key_surplus,last_key,sentinel=0,0,None,object()
        part_counts={name:0 for name in FILES}
        try:
            process.stdin.write(settings(folder,database)+query);process.stdin.close()
            actual=csv.reader(process.stdout,strict=True)
            for observed,expected in zip_longest(actual,merged_source(chunks),fillvalue=sentinel):
                assert observed is not sentinel and expected is not sentinel,'Private selected row count differs'
                assert tuple(observed)==expected,'Private selected five-field tuple differs; values withheld'
                key=expected[:3]
                key_surplus+=key==last_key
                last_key=key;rows+=1;part_counts[expected[4]]+=1
            assert process.wait(timeout=120)==0 and not timed_out.is_set(),'Private selected stream failed or timed out'
        finally:
            timer.cancel()
            if process.poll() is None:
                process.kill();process.wait()
            process.stdout.close()
        observe(folder)
        return dict(rows=rows,fields=5,candidate_key_surplus=key_surplus,selected_parts=part_counts,
                    matched=True,elapsed_seconds=round(time.perf_counter()-started,3))

    cases=[]
    p1,p2=FILES
    long_category='0'*24+'7'
    fixture=[('1','1','categoryid','001',p1),('10','1','available','0',p1),
             ('2','1','available','1',p2),('3','2','categoryid','999999',p2),
             ('0','0','categoryid',long_category,p1),(str(LIMIT),str(LIMIT),'available','1',p2),
             ('opaque_time','opaque_item','42',' n1 ',p1),('x','y',None,'opaque',p2)]
    with tempfile.TemporaryDirectory(prefix='rr-state-fixture-',dir=tmp_root) as temporary:
        folder,database=Path(temporary),Path(temporary)/'fixture.duckdb'
        query=adjusted(sql,fixture)
        run,_=execute(folder,database,setup(fixture)+query+'\n'+PRIVATE_ROWS)
        report,raw,staged=previous.json_outputs(run.stdout)
        expected_stage=[as_typed(row) for row in subset(fixture)]
        assert Counter(tuples(raw))==Counter(fixture) and Counter(tuples(staged))==Counter(expected_stage)
        assert report==report_reference(fixture,expected_stage)
        assert [row['status'] for row in report]==['PASS']*20+['INFO']*2
        for name in FILES:
            with (folder/name).open('w',encoding='utf-8',newline='') as output_stream:
                writer=csv.writer(output_stream);writer.writerow(previous.RAW_FIELDS)
                writer.writerows(row[:4] for row in fixture if row[4]==name)
        chunks,fixture_stats=sorted_source_chunks(folder,folder,chunk_rows=2)
        assert len(chunks)==3 and fixture_stats['selected_rows']==6 and fixture_stats['other_rows']==2
        assert [row[0] for row in merged_source(chunks)]==['0','1','10','2','3',str(LIMIT)]
        for table in ['rr_raw.item_properties','rr_stg.item_state_observations']:
            compared=compare_stream(folder,database,table,chunks)
            assert compared['rows']==6 and compared['candidate_key_surplus']==0 and compared['selected_parts']=={p1:3,p2:3}
        cases.append(dict(case='exact_named_subset_value_spellings_unknown_reference_opaque_complement_and_chunked_streams',
                          passed=True,raw_fixture_rows=8,selected_fixture_rows=6))

        changed=[tuple([*row[:3],'1',row[4]]) if row[0]==1 else row for row in expected_stage]
        run,_=execute(folder,database,"UPDATE rr_stg.item_state_observations SET value='1' WHERE timestamp=1;\n"+query.split(CHECK_MARKER,1)[1]+'\n'+PRIVATE_ROWS)
        report,raw,staged=previous.json_outputs(run.stdout)
        assert Counter(tuples(staged))==Counter(changed) and report==report_reference(fixture,changed)
        assert report[5]['status']=='PASS' and report[12]['status']=='PASS'
        assert report[17]['actual']==report[18]['actual']==1 and all(row['status']=='BLOCKED' for row in report[20:])
        changed=[tuple([*row[:4],p2]) if row[0]==1 else row for row in expected_stage]
        run,_=execute(folder,database,"UPDATE rr_stg.item_state_observations SET value='001',source_file='item_properties_part2.csv' WHERE timestamp=1;\n"+query.split(CHECK_MARKER,1)[1]+'\n'+PRIVATE_ROWS)
        report,raw,staged=previous.json_outputs(run.stdout)
        assert Counter(tuples(staged))==Counter(changed) and report==report_reference(fixture,changed)
        assert report[5]['status']=='PASS' and report[14]['status']=='PASS'
        assert report[17]['actual']==report[18]['actual']==1 and all(row['status']=='BLOCKED' for row in report[20:])
        rejected,_=execute(folder,database,query,allow_error=True)
        assert rejected.returncode!=0 and 'already exists' in rejected.stderr
        run,_=execute(folder,database,PRIVATE_ROWS,readonly=True)
        raw,staged=previous.json_outputs(run.stdout)
        assert Counter(tuples(raw))==Counter(fixture) and Counter(tuples(staged))==Counter(changed)
        cases.append(dict(case='same_count_value_and_provenance_changes_detected_info_blocked_existing_sentinel_preserved',passed=True))
    assert not folder.exists()

    base=('1','1','categoryid','7',p1)
    def changed_field(index,value):
        row=list(base);row[index]=value
        return [tuple(row)]
    invalid=[('empty',[],None),('no_selected',[('x','y','42','opaque',p1)],None),
             ('isolated_leading_zero',changed_field(0,'01'),None),
             ('numeric_key_alias',[base,('1','01','categoryid','7',p2)],None),
             ('missing_timestamp',changed_field(0,None),None),('empty_item',changed_field(1,''),None),
             ('whitespace_key',changed_field(0,' 1'),None),('overflow_key',changed_field(1,str(LIMIT+1)),None),
             ('negative_key',changed_field(1,'-1'),None),('invalid_availability',[('1','1','available','2',p1)],None),
             ('invalid_category_value',changed_field(3,'n7'),None),('overflow_category_value',changed_field(3,str(LIMIT+1)),None),
             ('missing_value',changed_field(3,None),None),('unknown_provenance',changed_field(4,'unknown.csv'),None),
             ('duplicate_key_across_parts',[base,(*base[:4],p2)],None),
             ('conflicting_key_across_parts',[base,('1','1','categoryid','8',p2)],None),
             ('wrong_raw_count',[base],{0:2}),('wrong_selected_count',[base],{3:2})]
    with tempfile.TemporaryDirectory(prefix='rr-state-reject-',dir=tmp_root) as temporary:
        folder=Path(temporary)
        for label,rows,override in invalid:
            database=folder/(label+'.duckdb')
            rejected,_=execute(folder,database,setup(rows)+adjusted(sql,rows,override),allow_error=True)
            assert rejected.returncode!=0 and 'SQL65 named property contract failed' in rejected.stderr,label
            run,_=execute(folder,database,"SELECT COUNT(*) AS targets FROM information_schema.tables WHERE table_schema='rr_stg' AND table_name='item_state_observations'; SELECT timestamp,itemid,property,value,source_file FROM rr_raw.item_properties;",readonly=True)
            target,raw=previous.json_outputs(run.stdout)
            assert target==[{'targets':0}] and Counter(tuples(raw))==Counter(rows),label
        for label,schema,rows in [
            ('wrong_type',[('timestamp','BIGINT')]+[(name,'VARCHAR') for name in FIELDS[1:]],[(1,'1','categoryid','7',p1)]),
            ('wrong_order',[('itemid','VARCHAR'),('timestamp','VARCHAR')]+[(name,'VARCHAR') for name in FIELDS[2:]],[base])]:
            database=folder/(label+'.duckdb')
            rejected,_=execute(folder,database,setup(rows,schema)+adjusted(sql,rows),allow_error=True)
            assert rejected.returncode!=0 and 'SQL65 named property contract failed' in rejected.stderr,label
            run,_=execute(folder,database,"SELECT COUNT(*) AS targets FROM information_schema.tables WHERE table_schema='rr_stg' AND table_name='item_state_observations'; SELECT timestamp,itemid,property,value,source_file FROM rr_raw.item_properties;",readonly=True)
            target,raw=previous.json_outputs(run.stdout)
            assert target==[{'targets':0}] and Counter(tuples(raw))==Counter(rows),label
        cases.append(dict(case='invalid_selected_keys_values_counts_provenance_and_cross_part_candidate_keys_rejected_atomically',
                          passed=True,expected_rejection=True,subcases=[case[0] for case in invalid]+['wrong_type','wrong_order']))
    assert not folder.exists()
    print(json.dumps({'fixture_families_passed':len(cases),'rejection_subcases':len(invalid)+2}),flush=True)
    if args.fixtures_only:
        return

    before={name:previous.snapshot(previous.SOURCE_DIR/name) for name in FILES}
    assert all(before[name]['sha256']==previous.SOURCE_HASHES[name] and before[name]['size_bytes']==previous.SOURCE_BYTES[name] for name in FILES)
    historical={str(path.relative_to(root)):previous.sha256(path) for path in (root/'data').glob('*preflight.json') if path.resolve()!=output.resolve()}
    with tempfile.TemporaryDirectory(prefix='rr-state-real-',dir=tmp_root) as temporary:
        folder,database=Path(temporary),Path(temporary)/'preflight.duckdb'
        started=time.perf_counter()
        chunks,source_stats=sorted_source_chunks(previous.SOURCE_DIR,folder)
        sort_seconds=round(time.perf_counter()-started,3)
        assert source_stats['raw_rows']==20275902 and source_stats['raw_parts']==previous.SOURCE_ROWS
        assert source_stats['selected_rows']==2291853 and source_stats['categoryid_rows']==788214 and source_stats['available_rows']==1503639
        assert source_stats['other_rows']==17984049
        chunk_count,chunk_bytes=len(chunks),sum(path.stat().st_size for path in chunks)
        _,reconstruction_seconds=execute(folder,database,raw_sql)
        run,stage_seconds=execute(folder,database,sql)
        report=json.loads(run.stdout)
        assert [row['status'] for row in report]==['PASS']*20+['INFO']*2
        raw_compare=compare_stream(folder,database,'rr_raw.item_properties',chunks)
        stage_compare=compare_stream(folder,database,'rr_stg.item_state_observations',chunks)
        for compared in [raw_compare,stage_compare]:
            assert compared['rows']==source_stats['selected_rows'] and compared['candidate_key_surplus']==0
            assert compared['selected_parts']==source_stats['selected_parts']
        independent=[source_stats['raw_rows'],source_stats['raw_parts'][p1],source_stats['raw_parts'][p2],0,0,
                     source_stats['selected_rows'],0,source_stats['categoryid_rows'],source_stats['available_rows'],
                     source_stats['other_rows'],0,0,0,0,0,stage_compare['candidate_key_surplus'],0,0,0,0,
                     source_stats['selected_parts'][p1],source_stats['selected_parts'][p2]]
        assert report==make_report(independent,TARGETS)
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
        reconstruction_prefix_sha256={'sql/56_import_retailrocket_properties.sql':hashlib.sha256(raw_sql.encode()).hexdigest()},
        reconstruction_basis='Full raw SQL56 import prefix only. No old import/key/named/reference audit queries rerun. SQL65 selects only categoryid and available.',
        table='rr_stg.item_state_observations',staging_fields=FIELDS,staging_types=['BIGINT','BIGINT','VARCHAR','VARCHAR','VARCHAR'],
        raw_rows=20275902,selected_rows=2291853,opaque_complement_rows=17984049,
        real_staging_script_executions=1,real_reconstruction_executions=1,real_private_comparison_stream_executions=2,
        report_rows=22,report_columns=5,output_columns=COLUMNS,checks_passed=20,info_rows=2,fail_rows=0,blocked_rows=0,
        results=report,report_sha256=previous.report_hash(report),
        report_fingerprint_contract='SHA-256 of ordered compact JSON arrays in output-column order, each followed by LF; actual/expected are integer counts or JSON null.',
        independent_python_source_counts=source_stats,independent_python_selected_key_and_value_rules_matched=True,
        independent_python_report_matched=True,independent_raw_stream=raw_compare,independent_staging_stream=stage_compare,
        independent_full_selected_five_field_multiset_matched=True,independent_selected_raw_input_unchanged=True,
        independent_candidate_key_surplus_verified_zero=True,
        prior_unmatched_category_records=167,unmatched_category_count_recomputed=False,
        unknown_reference_preservation_basis='Complete selected five-field tuple equality preserves the previously observed unmatched cohort. No category reference is read or joined, and no new unmatched count is claimed.',
        fixture_case_count=len(cases),fixture_cases=cases,rejection_subcase_count=len(invalid)+2,
        invalid_creation_destination_absence_verified=True,existing_destination_sentinel_preserved=True,
        same_count_value_mutation_detected=True,same_count_provenance_mutation_detected=True,info_requires_all_controls_pass_verified=True,
        preflight_settings=dict(threads=2,memory_limit='1GB',max_temp_directory_size='2GB',timeout_seconds_per_cli_phase=120,
                                python_sort_chunk_rows=CHUNK_ROWS,private_directory_budget_bytes=5*1024**3),
        private_selected_source_comparison_chunks=chunk_count,private_selected_source_comparison_chunk_bytes=chunk_bytes,
        private_comparison_spool_scope='Only selected categoryid/available five-field source tuples were written to private sorted chunks; opaque observations were counted but never spooled. All chunks removed with their owning private directory.',
        memory_availability_before=memory_before,workspace_free_bytes_before=free_before,workspace_free_bytes_after=shutil.disk_usage(tmp_root).free,
        private_database_bytes_before_cleanup=database_bytes,largest_private_directory_bytes_observed_after_phase=max(sizes),
        temporary_databases_and_spills_removed=True,private_selected_source_comparison_spools_removed=True,
        learner_database_opened=False,other_source_csvs_read=False,historical_comparison_or_analysis_suites_rerun=False,
        historical_preflight_files_unchanged=len(historical),source_records_or_identifiers_uploaded_or_logged=False,
        elapsed_python_scan_select_sort_seconds=sort_seconds,elapsed_full_raw_reconstruction_seconds=reconstruction_seconds,
        elapsed_staging_and_checks_seconds=stage_seconds,
        timing_scope='One full raw prefix reconstruction, one SQL65 staging/check phase and two selected read-only streams. Python two-source scan/selection/sort and stream timings recorded separately; hashing/fixtures excluded, not a performance benchmark.',
        scope='Assistant named item-state observations passed; learner SQL65 pending. Only 2,291,853 selected records typed. All other properties stay raw/opaque. Exact value/provenance and unknown references retained; no intervals, latest-state selection, as-of/event join, deduplication, identity repair, exact inventory, conversion or monetary claim.')
    output.write_text(json.dumps(evidence,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps({'report_rows':22,'checks_passed':20,'info_rows':2,'selected_rows_compared':source_stats['selected_rows'],
                      'stage_and_checks_seconds':stage_seconds,'report_sha256':evidence['report_sha256']}),flush=True)


if __name__=='__main__':
    main()
