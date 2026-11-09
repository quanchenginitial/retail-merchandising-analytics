"""Audit temporal coverage with bounded independent source matching of every event occurrence."""
import argparse
import bisect
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

import preflight_retailrocket_item_state_intervals as histories
import preflight_retailrocket_events_staging as events

previous=histories.previous
FILES=previous.FILES+['events.csv']
COLUMNS=previous.COLUMNS
MAX_MS=histories.MAX_MS
CHUNK_ROWS=50000
HISTORY_CAP=50000
CONTRACT_SHA='8cb849837dafdaa7f403afd653d42413062e471f80464fddadc0be170295bd30'
REPORT_MARKER='-- REPORT: the validator reuses the guarded prefix above for its private occurrence stream.'
PARAMETER_SQL="""SELECT 2756101::BIGINT AS expected_event_rows,460::BIGINT AS expected_duplicate_surplus,
        2291853::BIGINT AS expected_interval_rows,788214::BIGINT AS expected_category_rows,
        1503639::BIGINT AS expected_available_rows,253402300799999::BIGINT AS max_supported_ms"""
EVENT_SCHEMA=[('timestamp','BIGINT'),('visitorid','BIGINT'),('event','VARCHAR'),('itemid','BIGINT'),('transactionid','BIGINT')]
INTERVAL_SCHEMA=list(zip(histories.FIELDS,['BIGINT','VARCHAR','VARCHAR','BIGINT','BIGINT','VARCHAR']))
CHECKS=['event_rows','event_schema_mismatch','invalid_event_rows','event_duplicate_surplus','interval_rows',
        'interval_schema_mismatch','invalid_interval_rows','interval_candidate_key_surplus','interval_chain_errors',
        'categoryid_interval_rows','available_interval_rows','source_contract_violations','categoryid_joined_rows',
        'available_joined_rows','categoryid_future_match_rows','available_future_match_rows','categoryid_boundary_error_rows',
        'available_boundary_error_rows','categoryid_coverage_partition_difference','available_coverage_partition_difference',
        'categoryid_matched_rows','categoryid_before_first_rows','categoryid_no_history_rows','categoryid_open_tail_match_rows',
        'available_matched_rows','available_before_first_rows','available_no_history_rows','available_open_tail_match_rows']
PRIVATE_SELECT="""SELECT timestamp,visitorid,event,itemid,COALESCE(CAST(transactionid AS VARCHAR),'__NULL__'),
    COALESCE(categoryid_value,'__NULL__'),COALESCE(CAST(categoryid_from_ms AS VARCHAR),'__NULL__'),
    COALESCE(CAST(categoryid_to_ms AS VARCHAR),'__NULL__'),COALESCE(categoryid_source_file,'__NULL__'),categoryid_coverage,
    COALESCE(available_value,'__NULL__'),COALESCE(CAST(available_from_ms AS VARCHAR),'__NULL__'),
    COALESCE(CAST(available_to_ms AS VARCHAR),'__NULL__'),COALESCE(available_source_file,'__NULL__'),available_coverage
    FROM classified ORDER BY itemid,timestamp,visitorid,event,transactionid NULLS FIRST;"""


def parameters(event_rows,interval_rows):
    return dict(events=len(event_rows),duplicates=len(event_rows)-len(set(event_rows)),intervals=len(interval_rows),
                categoryid=sum(row[1]=='categoryid' for row in interval_rows),available=sum(row[1]=='available' for row in interval_rows))


def adjusted(sql,event_rows,interval_rows,override=None):
    p={**parameters(event_rows,interval_rows),**(override or {})}
    replacement=(f"SELECT {p['events']}::BIGINT AS expected_event_rows,{p['duplicates']}::BIGINT AS expected_duplicate_surplus,"
                 f"{p['intervals']}::BIGINT AS expected_interval_rows,{p['categoryid']}::BIGINT AS expected_category_rows,"
                 f"{p['available']}::BIGINT AS expected_available_rows,{MAX_MS}::BIGINT AS max_supported_ms")
    assert sql.count(PARAMETER_SQL)==1
    return sql.replace(PARAMETER_SQL,replacement)


def make_report(actual,expected):
    return [dict(check_order=i,check_name=name,actual=value,expected=target,
                 status='BLOCKED' if value is None else 'INFO' if target is None else 'PASS' if value==target else 'FAIL')
            for i,(name,value,target) in enumerate(zip(CHECKS,actual,expected),1)]


def blank_match_stats():
    stats=dict(event_rows=0,event_duplicate_surplus=0,maximum_current_event_item_history_rows=0)
    for name in CHECKS[20:]:
        stats[name]=0
    return stats


def healthy_report(source_counts,interval_stats,match_stats):
    count=match_stats['event_rows']
    assert count==source_counts['event_rows']
    for prop in ['categoryid','available']:
        assert sum(match_stats[prop+'_'+kind+'_rows'] for kind in ['matched','before_first','no_history'])==count
        assert match_stats[prop+'_open_tail_match_rows']<=match_stats[prop+'_matched_rows']
    controls=[count,0,0,match_stats['event_duplicate_surplus'],interval_stats['rows'],0,0,0,0,
              source_counts['categoryid'],source_counts['available'],0,count,count,0,0,0,0,0,0]
    return make_report(controls+[match_stats[name] for name in CHECKS[20:]],controls+[None]*8)


def event_key(row):
    return (row[3],row[0],row[1],row[2],-1 if row[4] is None else row[4])


def event_chunks(path,folder,chunk_rows=CHUNK_ROWS):
    paths,chunk=[],[]
    counts=dict(event_rows=0,view_rows=0,addtocart_rows=0,transaction_rows=0,null_transaction_rows=0)
    def flush():
        chunk.sort(key=event_key)
        output=folder/f'coverage-events-{len(paths):04d}.csv'
        with output.open('w',encoding='utf-8',newline='') as stream:
            csv.writer(stream).writerows(chunk)
        paths.append(output);chunk.clear()
    with path.open('r',encoding='utf-8',newline='') as stream:
        reader=csv.reader(stream,strict=True)
        assert next(reader)==events.FIELDS
        for raw in reader:
            assert len(raw)==5,'Private event source width differs'
            row=tuple(None if index==4 and value=='' else value for index,value in enumerate(raw))
            assert events.valid_row(row) and int(row[0])<=MAX_MS,'Private event source contract failed; values withheld'
            typed=events.typed(row)
            counts['event_rows']+=1;counts[typed[2]+'_rows']+=1;counts['null_transaction_rows']+=typed[4] is None
            chunk.append(typed)
            if len(chunk)==chunk_rows:
                flush()
    if chunk:
        flush()
    assert counts['event_rows']>0
    return paths,counts


def merged_events(paths):
    def typed(reader):
        for row in reader:
            assert len(row)==5
            yield (int(row[0]),int(row[1]),row[2],int(row[3]),None if row[4]=='' else int(row[4]))
    with ExitStack() as stack:
        streams=[typed(csv.reader(stack.enter_context(path.open('r',encoding='utf-8',newline='')),strict=True)) for path in paths]
        yield from heapq.merge(*streams,key=event_key)


def classify(history,starts,timestamp):
    if not history:
        return (None,None,None,None,'NO_HISTORY')
    index=bisect.bisect_right(starts,timestamp)-1
    if index<0:
        return (None,None,None,None,'BEFORE_FIRST')
    row=history[index]
    assert row[3]<=timestamp and (row[4] is None or timestamp<row[4]),'Private expected interval boundary violated'
    return (row[2],row[3],row[4],row[5],'MATCHED')


def expected_matches(event_paths,property_paths,stats,interval_stats,history_cap=HISTORY_CAP):
    source=iter(histories.expected_intervals(histories.merged_source(property_paths),interval_stats))
    next_interval=next(source,None)
    current_item=None;current={};starts={};previous_event=None
    for event in merged_events(event_paths):
        item=event[3]
        if current_item!=item:
            while next_interval is not None and next_interval[0]<item:
                next_interval=next(source,None)
            current={'categoryid':[],'available':[]};buffered=0
            while next_interval is not None and next_interval[0]==item:
                assert buffered<history_cap,'Private current-item history budget exceeded; no rows filtered'
                current[next_interval[1]].append(next_interval);buffered+=1
                next_interval=next(source,None)
            stats['maximum_current_event_item_history_rows']=max(stats['maximum_current_event_item_history_rows'],buffered)
            starts={prop:[row[3] for row in current[prop]] for prop in current}
            current_item=item
        matched=[]
        for prop in ['categoryid','available']:
            result=classify(current[prop],starts[prop],event[0])
            stats[prop+'_'+result[4].lower()+'_rows']+=1
            if result[4]=='MATCHED' and result[2] is None:
                stats[prop+'_open_tail_match_rows']+=1
            matched.extend(result)
        stats['event_rows']+=1;stats['event_duplicate_surplus']+=event==previous_event
        previous_event=event
        yield tuple(event)+tuple(matched)
    # Every remaining source observation is still reconciled, even for items with no events.
    for _ in source:
        pass


def setup(event_rows,interval_rows,event_schema=EVENT_SCHEMA,interval_schema=INTERVAL_SCHEMA):
    query='CREATE SCHEMA rr_stg; CREATE SCHEMA rr_core;\n'
    def table(name,columns,fields,rows):
        text='CREATE TABLE '+name+' ('+','.join(field+' '+kind for field,kind in columns)+');\n'
        def literal(value):
            return 'NULL' if value is None else "'"+str(value).replace("'","''")+"'"
        if rows:
            records=[]
            for row in rows:
                logical=dict(zip(fields,row))
                records.append('('+','.join(literal(logical[field]) for field,_ in columns)+')')
            text+='INSERT INTO '+name+' VALUES '+','.join(records)+';\n'
        return text
    return query+table('rr_stg.events',event_schema,events.FIELDS,event_rows)+table('rr_core.item_state_intervals',interval_schema,histories.FIELDS,interval_rows)


def parse_wide(row):
    assert len(row)==15,'Private wide match stream width differs'
    result=[]
    numeric={0,1,3,4,6,7,11,12}
    for index,value in enumerate(row):
        result.append(None if value=='__NULL__' else int(value) if index in numeric else value)
    return tuple(result)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--duckdb',required=True)
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--fixtures-only',action='store_true')
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    script_path='sql/68_audit_retailrocket_event_property_coverage.sql'
    validator_path='validation/preflight_retailrocket_event_property_coverage.py'
    method_path='docs/RETAILROCKET_EVENT_PROPERTY_COVERAGE_VALIDATION.md'
    output=root/'data/retailrocket_event_property_coverage_preflight.json'
    assert args.output.resolve()==output.resolve()
    dependencies=[script_path,validator_path,'sql/56_import_retailrocket_properties.sql','sql/65_stage_retailrocket_item_state_observations.sql',
                  'sql/67_build_retailrocket_item_state_intervals.sql','sql/54_import_retailrocket_events.sql','sql/63_stage_retailrocket_events.sql',
                  'validation/preflight_retailrocket_item_state_intervals.py','validation/preflight_retailrocket_item_state_observations.py',
                  'validation/preflight_retailrocket_properties_import.py','validation/preflight_retailrocket_events_staging.py',
                  'validation/preflight_retailrocket_events_import.py','data/retailrocket_source_audit.json',
                  'data/retailrocket_item_state_intervals_preflight.json','data/retailrocket_item_state_intervals_learner_acceptance.json',
                  'docs/RETAILROCKET_ITEM_STATE_INTERVALS_VALIDATION.md','data/retailrocket_events_staging_preflight.json',
                  'data/retailrocket_events_staging_learner_acceptance.json','data/retailrocket_event_time_preflight.json']
    hashes={path:previous.sha256(root/path) for path in dependencies}
    contract=(root/method_path).read_bytes().split(b'\n## Executed results\n',1)[0]
    assert hashlib.sha256(contract).hexdigest()==CONTRACT_SHA
    sql=(root/script_path).read_text(encoding='utf-8')
    cleaned=re.sub(r'--[^\n]*','',sql)
    assert cleaned.lstrip().startswith('WITH ') and not re.search(r'\b(CREATE|INSERT|UPDATE|DELETE|DROP|ALTER|COPY|ATTACH|DETACH|SET)\b',cleaned,re.I)
    assert sql.count(REPORT_MARKER)==1 and sql.count('ASOF LEFT JOIN')==2
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

    def execute(folder,database,query,readonly=False):
        started=time.perf_counter()
        run=subprocess.run([args.duckdb,str(database),'-bail','-json']+(['-readonly'] if readonly else []),
                           input=settings(folder,database)+query,text=True,encoding='utf-8',capture_output=True,timeout=120)
        assert run.returncode==0,'Private coverage execution failed; row-bearing diagnostics withheld'
        observe(folder)
        return run,round(time.perf_counter()-started,3)

    def compare_stream(folder,database,query,event_paths,property_paths):
        started,timed_out=time.perf_counter(),threading.Event()
        private_query=query.split(REPORT_MARKER,1)[0]+PRIVATE_SELECT
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
                assert parse_wide(observed)==wanted,'Private 15-field coverage occurrence differs; values withheld'
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
                    (2,6,'view',10,None),(9,7,'view',99,None),(0,8,'view',20,None),(1000,9,'view',2,None)]
    fixture_interval_stats=histories.blank_interval_stats()
    fixture_intervals=list(histories.expected_intervals(sorted(histories.ordered_source(row) for row in fixture_properties),fixture_interval_stats))
    cases=[]
    with tempfile.TemporaryDirectory(prefix='rr-coverage-fixture-',dir=tmp_root) as temporary:
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
        category2=[row for row in fixture_intervals if row[:2]==(2,'categoryid')]
        assert classify(category2,[1,5],0)==(None,None,None,None,'BEFORE_FIRST')
        assert classify(category2,[1,5],1)==('001',1,5,p1,'MATCHED')
        assert classify(category2,[1,5],5)==('7',5,None,p2,'MATCHED')
        assert classify([],[],5)==(None,None,None,None,'NO_HISTORY')
        assert expected_stats['categoryid_matched_rows']==8 and expected_stats['categoryid_before_first_rows']==2 and expected_stats['categoryid_no_history_rows']==2
        assert expected_stats['available_matched_rows']==6 and expected_stats['available_before_first_rows']==2 and expected_stats['available_no_history_rows']==4
        try:
            list(expected_matches(event_paths,property_paths,blank_match_stats(),histories.blank_interval_stats(),history_cap=1))
            raise AssertionError('History cap did not abort')
        except AssertionError as error:
            assert 'history budget exceeded' in str(error)
        execute(folder,database,setup(fixture_events,fixture_intervals))
        before_db=previous.sha256(database)
        query=adjusted(sql,fixture_events,fixture_intervals)
        run,_=execute(folder,database,query,readonly=True)
        report=json.loads(run.stdout)
        source_counts=dict(event_rows=12,categoryid=3,available=3)
        assert report==healthy_report(source_counts,expected_interval_stats,expected_stats)
        compared,compared_intervals,_=compare_stream(folder,database,query,event_paths,property_paths)
        assert compared==expected_stats and compared_intervals==expected_interval_stats
        assert previous.sha256(database)==before_db
        cases.append(dict(case='numeric_cross_chunk_event_occurrences_all_coverage_classes_exact_boundaries_duplicates_and_null_transactions',passed=True,
                          fixture_events=12,fixture_intervals=6,event_chunks=6,property_chunks=3))
        cases.append(dict(case='current_item_history_budget_aborts_without_truncation',passed=True,fixture_budget_rows=1))
    assert not folder.exists()

    def replace_interval(index,field,value):
        changed=list(fixture_intervals)
        row=list(changed[index]);row[field]=value;changed[index]=tuple(row)
        return changed
    cat_first=next(index for index,row in enumerate(fixture_intervals) if row[:2]==(2,'categoryid') and row[3]==1)
    cat_last=next(index for index,row in enumerate(fixture_intervals) if row[:2]==(2,'categoryid') and row[3]==5)
    invalid=[
        ('empty_events',[],fixture_intervals,None,EVENT_SCHEMA,INTERVAL_SCHEMA,'source_contract_violations'),
        ('empty_intervals',fixture_events,[],None,EVENT_SCHEMA,INTERVAL_SCHEMA,'source_contract_violations'),
        ('wrong_event_count',fixture_events,fixture_intervals,{'events':13},EVENT_SCHEMA,INTERVAL_SCHEMA,'event_rows'),
        ('wrong_duplicate_count',fixture_events,fixture_intervals,{'duplicates':0},EVENT_SCHEMA,INTERVAL_SCHEMA,'event_duplicate_surplus'),
        ('null_event_time',[(None,*fixture_events[0][1:])]+fixture_events[1:],fixture_intervals,None,EVENT_SCHEMA,INTERVAL_SCHEMA,'invalid_event_rows'),
        ('negative_event_item',[(0,1,'view',-1,None)]+fixture_events[1:],fixture_intervals,None,EVENT_SCHEMA,INTERVAL_SCHEMA,'invalid_event_rows'),
        ('wrong_event_type',[(str(row[0]),*row[1:]) for row in fixture_events],fixture_intervals,None,[('timestamp','VARCHAR')]+EVENT_SCHEMA[1:],INTERVAL_SCHEMA,'event_schema_mismatch'),
        ('wrong_interval_order',fixture_events,fixture_intervals,None,EVENT_SCHEMA,[INTERVAL_SCHEMA[1],INTERVAL_SCHEMA[0],*INTERVAL_SCHEMA[2:]],'interval_schema_mismatch'),
        ('duplicate_interval_key',fixture_events,fixture_intervals+[fixture_intervals[cat_first]],None,EVENT_SCHEMA,INTERVAL_SCHEMA,'interval_candidate_key_surplus'),
        ('overlapping_chain',fixture_events,replace_interval(cat_first,4,6),None,EVENT_SCHEMA,INTERVAL_SCHEMA,'interval_chain_errors'),
        ('gapped_chain',fixture_events,replace_interval(cat_first,4,4),None,EVENT_SCHEMA,INTERVAL_SCHEMA,'interval_chain_errors'),
        ('closed_final_tail',fixture_events,replace_interval(cat_last,4,10),None,EVENT_SCHEMA,INTERVAL_SCHEMA,'interval_chain_errors'),
        ('invalid_interval_value',fixture_events,replace_interval(cat_first,2,'bad'),None,EVENT_SCHEMA,INTERVAL_SCHEMA,'invalid_interval_rows'),
        ('unknown_provenance',fixture_events,replace_interval(cat_first,5,'unknown.csv'),None,EVENT_SCHEMA,INTERVAL_SCHEMA,'invalid_interval_rows')]
    with tempfile.TemporaryDirectory(prefix='rr-coverage-invalid-',dir=tmp_root) as temporary:
        folder=Path(temporary)
        for label,erows,irows,override,eschema,ischema,failed_check in invalid:
            database=folder/(label+'.duckdb')
            execute(folder,database,setup(erows,irows,eschema,ischema))
            before_db=previous.sha256(database)
            run,_=execute(folder,database,adjusted(sql,erows,irows,override),readonly=True)
            report=json.loads(run.stdout)
            assert len(report)==28 and [row['check_name'] for row in report]==CHECKS,label
            assert next(row for row in report if row['check_name']==failed_check)['status']=='FAIL',label
            assert next(row for row in report if row['check_name']=='source_contract_violations')['actual']==1,label
            assert all(row['actual'] is None and row['status']=='BLOCKED' for row in report[12:]),label
            assert previous.sha256(database)==before_db,label
        cases.append(dict(case='invalid_source_count_schema_values_duplicate_keys_overlap_gap_and_tail_block_all_joins',passed=True,
                          subcases=[case[0] for case in invalid]))
    assert not folder.exists()
    print(json.dumps({'fixture_families_passed':len(cases),'invalid_prerequisite_subcases':len(invalid)}),flush=True)
    if args.fixtures_only:
        return

    before={name:previous.snapshot(path) for name,path in source_paths.items()}
    assert all(before[name]['sha256']==source_hashes[name] for name in FILES)
    assert sum(before[name]['size_bytes'] for name in FILES)==987483569
    historical={str(path.relative_to(root)):previous.sha256(path) for path in (root/'data').glob('*preflight.json') if path.resolve()!=output.resolve()}
    with tempfile.TemporaryDirectory(prefix='rr-coverage-real-',dir=tmp_root) as temporary:
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
        prop_code='\n'.join(prefixes[path] for path in ['sql/56_import_retailrocket_properties.sql','sql/65_stage_retailrocket_item_state_observations.sql','sql/67_build_retailrocket_item_state_intervals.sql'])
        event_code='\n'.join(prefixes[path] for path in ['sql/54_import_retailrocket_events.sql','sql/63_stage_retailrocket_events.sql'])
        _,property_reconstruction_seconds=execute(folder,database,prop_code)
        _,event_reconstruction_seconds=execute(folder,database,event_code)
        database_before=previous.sha256(database)
        run,audit_seconds=execute(folder,database,sql,readonly=True)
        report=json.loads(run.stdout)
        assert [row['status'] for row in report]==['PASS']*20+['INFO']*8
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
        source_files=FILES,source_before=before,source_after=after,source_hashes_and_metadata_unchanged=True,
        reconstruction_prefix_sha256={path:hashlib.sha256(code.encode()).hexdigest() for path,code in prefixes.items()},
        reconstruction_basis='Only SQL56/65/67 property/interval creation prefixes and SQL54/63 event creation prefixes, in two reconstruction phases; no prior full checks.',
        source_tables=['rr_stg.events','rr_core.item_state_intervals'],query_read_only=True,
        real_property_reconstruction_executions=1,real_event_reconstruction_executions=1,real_audit_script_executions=1,real_private_stream_executions=1,
        report_rows=28,report_columns=5,output_columns=COLUMNS,checks_passed=20,info_rows=8,fail_rows=0,blocked_rows=0,
        results=report,report_sha256=previous.report_hash(report),report_fingerprint_contract='SHA-256 of ordered compact JSON arrays in output-column order, each followed by LF; actual/expected are integer counts or JSON null.',
        independent_python_property_source_counts=property_counts,independent_python_event_source_counts=event_counts,
        independent_python_interval_counts=interval_stats,independent_python_match_counts=match_stats,
        independent_python_numeric_external_sort=True,independent_python_current_item_binary_search=True,independent_python_report_matched=True,
        independent_stream_occurrences_compared=match_stats['event_rows'],independent_stream_fields_compared=15,
        independent_stream_all_occurrences_matched=True,independent_original_event_fields_and_duplicates_preserved=True,
        independent_original_property_values_and_provenance_preserved=True,all_source_property_intervals_reconciled=True,
        coverage_partitions_reconciled=True,open_tail_counts_are_matched_subsets=True,no_backward_fill_verified=True,
        maximum_current_event_item_history_rows_observed=match_stats['maximum_current_event_item_history_rows'],current_item_history_budget_rows=HISTORY_CAP,
        history_buffer_cap_abort_verified=True,null_marker='__NULL__',
        private_database_sha256_before_readonly=database_before,private_database_sha256_after_readonly=database_after,private_database_bytes_unchanged=True,
        fixture_case_count=len(cases),fixture_cases=cases,invalid_prerequisite_subcase_count=len(invalid),
        blocked_dependencies_verified=True,info_requires_all_controls_pass_verified=True,overlap_gap_and_invalid_tail_admission_blocked=True,
        preflight_settings=dict(threads=2,memory_limit='1GB',max_temp_directory_size='2GB',timeout_seconds_per_cli_phase=120,
                                python_sort_chunk_rows=CHUNK_ROWS,current_item_history_rows=HISTORY_CAP,private_directory_budget_bytes=5*1024**3),
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
        elapsed_readonly_audit_seconds=audit_seconds,elapsed_private_stream_seconds=stream_seconds,
        timing_scope='Four CLI phases: property prefix chain, event prefix chain, read-only SQL68 report and read-only 15-field wide stream. Independent source sorting timed separately; hashing/fixtures excluded; not a performance benchmark.',
        scope='Assistant technical event-to-observation coverage audit passed; learner SQL68 pending. Each original event occurrence retained. MATCHED means greatest recorded start at/before event with interval compliance, not confirmed business truth or freshness. NO_HISTORY and BEFORE_FIRST retained without backfill. Open-tail matches are subsets, not a fourth class. No persistent fact table, category reference repair, expiry age, inventory, conversion or causal claim.')
    output.write_text(json.dumps(evidence,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps({'report_rows':28,'checks_passed':20,'info_rows':8,'event_occurrences_compared':match_stats['event_rows'],
                      'readonly_audit_seconds':audit_seconds,'report_sha256':evidence['report_sha256']}),flush=True)


if __name__=='__main__':
    main()
