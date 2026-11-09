"""Verify category coverage at eligible first views using category-only source reconstruction."""
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
from decimal import Decimal, ROUND_HALF_UP
from itertools import zip_longest
from pathlib import Path

import preflight_retailrocket_7day_visitor_item_funnel as base
import preflight_retailrocket_item_state_intervals as histories

staging=base.staging
previous=base.previous
PROPERTY_FILES=histories.previous.FILES
FILES=[*PROPERTY_FILES,'events.csv','category_tree.csv']
MAX_MS=base.MAX_MS
WINDOW_MS=base.WINDOW_MS
OBSERVATION_END_MS=base.OBSERVATION_END_MS
CHUNK_ROWS=50000
HISTORY_CAP=50000
CONTRACT_SHA='f95f39277b2a7c61a5612ea70a7902ca3836991c64dfbc75b396fc5ec602c00e'
LABELS=['MAPPED','UNKNOWN_REFERENCE','BEFORE_FIRST','NO_HISTORY','TOTAL']
OUTPUT=['coverage_status','eligible_pairs','share_of_eligible_pairs_pct','check_status']
FACT_FIELDS=staging.FIELDS+['categoryid_value','categoryid_from_ms','categoryid_to_ms','categoryid_source_file','categoryid_coverage']
PARAMETERS='''SELECT 2756101::BIGINT AS expected_rows,2664312::BIGINT AS expected_views,
        69332::BIGINT AS expected_carts,22457::BIGINT AS expected_transactions,
        460::BIGINT AS expected_duplicate_surplus,253402300799999::BIGINT AS max_supported_ms,
        604800000::BIGINT AS window_ms,1442545187788::BIGINT AS expected_observation_end_ms,
        2042310::BIGINT AS expected_eligible_pairs,1669::BIGINT AS expected_reference_ids'''
ENRICHMENT='''CREATE SCHEMA rr_mart;
CREATE TABLE rr_mart.events_enriched AS
WITH first_history AS (SELECT itemid,MIN(observed_from_ms) AS first_start FROM rr_private.category_intervals GROUP BY itemid)
SELECT e.timestamp,e.visitorid,e.event,e.itemid,e.transactionid,
    c.value AS categoryid_value,c.observed_from_ms AS categoryid_from_ms,c.observed_to_ms AS categoryid_to_ms,
    c.source_file AS categoryid_source_file,
    CASE WHEN c.observed_from_ms IS NOT NULL THEN 'MATCHED' WHEN h.first_start IS NULL THEN 'NO_HISTORY'
         WHEN e.timestamp<h.first_start THEN 'BEFORE_FIRST' ELSE 'INVALID' END AS categoryid_coverage
FROM rr_stg.events e LEFT JOIN first_history h ON e.itemid=h.itemid
ASOF LEFT JOIN rr_private.category_intervals c ON e.itemid=c.itemid AND e.timestamp>=c.observed_from_ms;'''
STREAM='''SELECT timestamp,visitorid,event,itemid,COALESCE(CAST(transactionid AS VARCHAR),'__NULL__'),
    COALESCE(categoryid_value,'__NULL__'),COALESCE(CAST(categoryid_from_ms AS VARCHAR),'__NULL__'),
    COALESCE(CAST(categoryid_to_ms AS VARCHAR),'__NULL__'),COALESCE(categoryid_source_file,'__NULL__'),categoryid_coverage
FROM rr_mart.events_enriched ORDER BY itemid,visitorid,timestamp,event,transactionid NULLS FIRST;'''

def literal(value):
    return "'"+str(value).replace("'","''")+"'"

def category_build(source_dir,expected_rows,reference_count):
    reads=[]
    for name in PROPERTY_FILES:
        path=(source_dir/name).as_posix()
        reads.append(f"SELECT timestamp,itemid,property,value,{literal(name)} AS source_file FROM read_csv({literal(path)},header=true,auto_detect=false,columns={{'timestamp':'VARCHAR','itemid':'VARCHAR','property':'VARCHAR','value':'VARCHAR'}},delim=',',quote='\"',escape='\"',nullstr='',force_not_null=['timestamp','itemid','property','value'],strict_mode=true,ignore_errors=false,null_padding=false) WHERE property='categoryid'")
    return f'''CREATE SCHEMA rr_private;
CREATE TABLE rr_private.category_observations AS
WITH selected AS MATERIALIZED ({' UNION ALL '.join(reads)}), health AS (
 SELECT COUNT(*) AS rows,COUNT(DISTINCT (itemid,timestamp)) AS keys,
 COUNT(*) FILTER (WHERE NOT COALESCE(regexp_full_match(timestamp,'[0-9]+') AND TRY_CAST(timestamp AS BIGINT) BETWEEN 0 AND {MAX_MS}
 AND CAST(TRY_CAST(timestamp AS BIGINT) AS VARCHAR)=timestamp AND regexp_full_match(itemid,'[0-9]+') AND TRY_CAST(itemid AS BIGINT)>=0
 AND CAST(TRY_CAST(itemid AS BIGINT) AS VARCHAR)=itemid AND regexp_full_match(value,'[0-9]+') AND TRY_CAST(value AS BIGINT) IS NOT NULL,false)) AS invalid_rows FROM selected
), guard AS (SELECT rows={expected_rows} AND rows>0 AND keys=rows AND invalid_rows=0 AS valid FROM health)
SELECT CASE WHEN g.valid THEN CAST(s.itemid AS BIGINT) ELSE error('SQL73 private category source guard failed') END AS itemid,
 CASE WHEN g.valid THEN CAST(s.timestamp AS BIGINT) ELSE error('SQL73 private category source guard failed') END AS timestamp,
 CASE WHEN g.valid THEN s.value ELSE error('SQL73 private category source guard failed') END AS value,
 CASE WHEN g.valid THEN s.source_file ELSE error('SQL73 private category source guard failed') END AS source_file
FROM guard g LEFT JOIN selected s ON g.valid;
CREATE TABLE rr_private.category_intervals AS SELECT itemid,value,timestamp AS observed_from_ms,
 LEAD(timestamp) OVER (PARTITION BY itemid ORDER BY timestamp) AS observed_to_ms,source_file FROM rr_private.category_observations;
CREATE SCHEMA rr_core;
CREATE TABLE rr_core.dim_category AS
WITH source AS MATERIALIZED (SELECT categoryid FROM read_csv({literal((source_dir/'category_tree.csv').as_posix())},header=true,auto_detect=false,
 columns={{'categoryid':'VARCHAR','parentid':'VARCHAR'}},delim=',',quote='"',escape='"',nullstr='',force_not_null=['categoryid'],strict_mode=true,ignore_errors=false,null_padding=false)),
 guard AS (SELECT COUNT(*)={reference_count} AND COUNT(*)>0 AND COUNT(DISTINCT categoryid)=COUNT(*)
 AND COUNT(*) FILTER (WHERE NOT COALESCE(regexp_full_match(categoryid,'[0-9]+') AND TRY_CAST(categoryid AS BIGINT)>=0
 AND CAST(TRY_CAST(categoryid AS BIGINT) AS VARCHAR)=categoryid,false))=0 AS valid FROM source)
SELECT CASE WHEN g.valid THEN CAST(s.categoryid AS BIGINT) ELSE error('SQL73 private reference guard failed') END AS categoryid FROM guard g LEFT JOIN source s ON g.valid;'''

def event_key(row):
    return (row[3],row[1],row[0],row[2],-1 if row[4] is None else row[4])

def event_chunks(path,folder,chunk_rows=CHUNK_ROWS):
    paths,chunk=[],[];counts=dict(rows=0,view=0,addtocart=0,transaction=0,null_transaction_ids=0,observation_end_ms=None)
    def flush():
        chunk.sort(key=event_key);output=folder/f'category-events-{len(paths):04d}.csv'
        with output.open('w',encoding='utf-8',newline='') as stream:
            csv.writer(stream).writerows(chunk)
        paths.append(output);chunk.clear()
    with path.open('r',encoding='utf-8',newline='') as stream:
        reader=csv.reader(stream,strict=True);assert next(reader)==staging.FIELDS
        for raw in reader:
            assert len(raw)==5
            logical=tuple(None if i==4 and value=='' else value for i,value in enumerate(raw))
            assert staging.valid_row(logical),'Private event source rule failure; values withheld'
            row=staging.typed(logical);assert row[0]<=MAX_MS
            counts['rows']+=1;counts[row[2]]+=1;counts['null_transaction_ids']+=row[4] is None
            counts['observation_end_ms']=row[0] if counts['observation_end_ms'] is None else max(counts['observation_end_ms'],row[0])
            chunk.append(row)
            if len(chunk)==chunk_rows:flush()
    if chunk:flush()
    assert counts['rows']>0
    return paths,counts

def merged_events(paths):
    def typed(reader):
        for row in reader:
            assert len(row)==5
            yield (int(row[0]),int(row[1]),row[2],int(row[3]),None if row[4]=='' else int(row[4]))
    with ExitStack() as stack:
        yield from heapq.merge(*[typed(csv.reader(stack.enter_context(path.open('r',encoding='utf-8',newline='')),strict=True)) for path in paths],key=event_key)

def category_chunks(source_dir,folder,chunk_rows=CHUNK_ROWS):
    paths,chunk=[],[];counts=dict(raw_rows=0,raw_parts={},category_rows=0,selected_parts={})
    def flush():
        chunk.sort();output=folder/f'category-history-{len(paths):04d}.csv'
        with output.open('w',encoding='utf-8',newline='') as stream:csv.writer(stream).writerows(chunk)
        paths.append(output);chunk.clear()
    for name in PROPERTY_FILES:
        counts['raw_parts'][name]=0;counts['selected_parts'][name]=0
        with (source_dir/name).open('r',encoding='utf-8',newline='') as stream:
            reader=csv.reader(stream,strict=True);assert next(reader)==['timestamp','itemid','property','value']
            for raw in reader:
                assert len(raw)==4
                counts['raw_rows']+=1;counts['raw_parts'][name]+=1
                if raw[2]!='categoryid':continue
                assert histories.staging.valid_named(raw) and int(raw[0])<=MAX_MS,'Private category source rule failure; values withheld'
                chunk.append((int(raw[1]),'categoryid',int(raw[0]),raw[3],name));counts['category_rows']+=1;counts['selected_parts'][name]+=1
                if len(chunk)==chunk_rows:flush()
    if chunk:flush()
    assert counts['category_rows']>0
    return paths,counts

def reference_ids(path):
    ids=set();count=0
    with path.open('r',encoding='utf-8',newline='') as stream:
        reader=csv.reader(stream,strict=True);assert next(reader)==['categoryid','parentid']
        for row in reader:
            assert len(row)==2 and staging.canonical(row[0])
            value=int(row[0]);assert value not in ids,'Private category reference duplicate ID'
            ids.add(value);count+=1
    assert count>0
    return ids

def blank_stats():
    return dict(rows=0,duplicate_surplus=0,observed_pairs=0,viewed_pairs=0,eligible_pairs=0,first_view_occurrences=0,
                maximum_current_item_history_rows=0,maximum_simultaneous_pair_states=0,observed_max_timestamp_ms=None,
                **{label:0 for label in LABELS[:-1]})

def expected_stream(event_paths,category_paths,ids,end_ms,stats,interval_stats,history_cap=HISTORY_CAP):
    source=iter(histories.expected_intervals(histories.merged_source(category_paths),interval_stats));pending=next(source,None)
    current_item=None;history=[];starts=[];current_pair=None;first_view=None;first_snapshot=None;prior_event=None
    def close_pair():
        stats['observed_pairs']+=1
        if first_view is None:return
        stats['viewed_pairs']+=1
        if first_view+WINDOW_MS>end_ms:return
        stats['eligible_pairs']+=1
        status=first_snapshot[4]
        mapped=('MAPPED' if int(first_snapshot[0]) in ids else 'UNKNOWN_REFERENCE') if status=='MATCHED' else status
        assert mapped in LABELS[:-1];stats[mapped]+=1
    for event in merged_events(event_paths):
        item=event[3];pair=(item,event[1])
        if current_item!=item:
            while pending is not None and pending[0]<item:pending=next(source,None)
            history=[]
            while pending is not None and pending[0]==item:
                assert len(history)<history_cap,'Private current-item history cap exceeded; no filtering'
                history.append(pending);pending=next(source,None)
            starts=[row[3] for row in history];current_item=item
            stats['maximum_current_item_history_rows']=max(stats['maximum_current_item_history_rows'],len(history))
        if current_pair!=pair:
            if current_pair is not None:close_pair()
            current_pair=pair;first_view=None;first_snapshot=None;stats['maximum_simultaneous_pair_states']=1
        index=bisect.bisect_right(starts,event[0])-1
        if not history:snapshot=(None,None,None,None,'NO_HISTORY')
        elif index<0:snapshot=(None,None,None,None,'BEFORE_FIRST')
        else:
            row=history[index];assert row[3]<=event[0] and (row[4] is None or event[0]<row[4])
            snapshot=(row[2],row[3],row[4],row[5],'MATCHED')
        if event[2]=='view':
            if first_view is None:first_view=event[0];first_snapshot=snapshot
            if event[0]==first_view and first_view+WINDOW_MS<=end_ms:
                assert snapshot==first_snapshot;stats['first_view_occurrences']+=1
        stats['rows']+=1;stats['duplicate_surplus']+=event==prior_event;prior_event=event
        stats['observed_max_timestamp_ms']=event[0] if stats['observed_max_timestamp_ms'] is None else max(stats['observed_max_timestamp_ms'],event[0])
        yield event+snapshot
    if current_pair is not None:close_pair()
    for _ in source:pass
    assert sum(stats[label] for label in LABELS[:-1])==stats['eligible_pairs']
    assert stats['observed_max_timestamp_ms']==end_ms

def reference_report(stats):
    total=stats['eligible_pairs'];report=[]
    for label in LABELS:
        count=total if label=='TOTAL' else stats[label]
        share=None if total==0 else format((Decimal(count)*100/Decimal(total)).quantize(Decimal('0.0001'),rounding=ROUND_HALF_UP),'.4f')
        report.append(dict(zip(OUTPUT,[label,count,share,'PASS'])))
    return report

def report_hash(report):
    return hashlib.sha256(''.join(json.dumps([row[name] for name in OUTPUT],separators=(',',':'))+'\n' for row in report).encode()).hexdigest()

def adjusted(sql,event_rows,reference_count,override=None):
    counts=Counter(row[2] for row in event_rows);end=max(row[0] for row in event_rows);first={}
    for row in event_rows:
        if row[2]=='view':first[(row[1],row[3])]=min(first.get((row[1],row[3]),row[0]),row[0])
    values=dict(expected_rows=len(event_rows),expected_views=counts['view'],expected_carts=counts['addtocart'],expected_transactions=counts['transaction'],
                expected_duplicate_surplus=len(event_rows)-len(set(event_rows)),max_supported_ms=MAX_MS,window_ms=WINDOW_MS,
                expected_observation_end_ms=end,expected_eligible_pairs=sum(value+WINDOW_MS<=end for value in first.values()),expected_reference_ids=reference_count)
    values.update(override or {});assert sql.count(PARAMETERS)==1
    return sql.replace(PARAMETERS,'SELECT '+','.join(f'{value}::BIGINT AS {name}' for name,value in values.items()))

def fixture_events_sql(rows):
    query='CREATE SCHEMA rr_stg;CREATE TABLE rr_stg.events(timestamp BIGINT,visitorid BIGINT,event VARCHAR,itemid BIGINT,transactionid BIGINT);'
    return query+'INSERT INTO rr_stg.events VALUES '+','.join('('+','.join('NULL' if value is None else literal(value) for value in row)+')' for row in rows)+';'+ENRICHMENT

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--duckdb',required=True);parser.add_argument('--output',required=True);parser.add_argument('--fixtures-only',action='store_true');args=parser.parse_args()
    root=Path(__file__).resolve().parents[1];output=(root/args.output).resolve()
    assert output.is_relative_to((root/'data').resolve())
    script_path='sql/73_audit_retailrocket_first_view_category_coverage.sql'
    validator_path='validation/preflight_retailrocket_first_view_category_coverage.py'
    method_path='docs/RETAILROCKET_FIRST_VIEW_CATEGORY_COVERAGE_VALIDATION.md'
    dependencies=[script_path,validator_path,'sql/54_import_retailrocket_events.sql','sql/63_stage_retailrocket_events.sql',
        'validation/preflight_retailrocket_events_import.py','validation/preflight_retailrocket_events_staging.py',
        'validation/preflight_retailrocket_properties_import.py','validation/preflight_retailrocket_item_state_observations.py',
        'validation/preflight_retailrocket_item_state_intervals.py','validation/preflight_retailrocket_7day_visitor_item_funnel.py',
        'data/retailrocket_source_audit.json','data/retailrocket_event_time_preflight.json',
        'sql/62_build_retailrocket_category_dimension.sql','data/retailrocket_category_dimension_preflight.json',
        'data/retailrocket_category_dimension_learner_acceptance.json','docs/RETAILROCKET_CATEGORY_DIMENSION_VALIDATION.md',
        'sql/69_build_retailrocket_events_enriched.sql','data/retailrocket_events_enriched_preflight.json',
        'data/retailrocket_events_enriched_learner_acceptance.json','docs/RETAILROCKET_EVENTS_ENRICHED_VALIDATION.md',
        'sql/72_analyze_retailrocket_7day_visitor_item_funnel.sql','data/retailrocket_7day_visitor_item_funnel_preflight.json',
        'data/retailrocket_7day_visitor_item_funnel_learner_acceptance.json','docs/RETAILROCKET_7DAY_VISITOR_ITEM_FUNNEL_VALIDATION.md']
    hashes={name:previous.sha256(root/name) for name in dependencies}
    contract=(root/method_path).read_bytes().split(b'\n## Executed results\n',1)[0]
    assert hashlib.sha256(contract).hexdigest()==CONTRACT_SHA
    for stem,script in [('category_dimension','sql/62_build_retailrocket_category_dimension.sql'),
                        ('events_enriched','sql/69_build_retailrocket_events_enriched.sql'),
                        ('7day_visitor_item_funnel','sql/72_analyze_retailrocket_7day_visitor_item_funnel.sql')]:
        old=json.loads((root/f'data/retailrocket_{stem}_preflight.json').read_text(encoding='utf-8'))
        accepted=json.loads((root/f'data/retailrocket_{stem}_learner_acceptance.json').read_text(encoding='utf-8'))
        assert accepted['acceptance_status'].startswith('accepted') and accepted['report_sha256']==old['report_sha256']
        assert old['script_sha256']==hashes[script]
    assert next(row for row in old['results'] if row['stage']=='ELIGIBLE_VIEW_7D')['visitor_item_pairs']==2042310
    sql=(root/script_path).read_text(encoding='utf-8');clean=re.sub(r'--[^\n]*','',sql)
    assert clean.lstrip().startswith('WITH ') and not re.search(r'\b(CREATE|INSERT|UPDATE|DELETE|DROP|ALTER|COPY|ATTACH|DETACH|SET)\b',clean,re.I)
    assert all(name not in clean for name in ['available_value','event_timestamp_utc','event_date_utc','parentid','root_categoryid','depth'])
    prefixes={
        'sql/54_import_retailrocket_events.sql':(root/'sql/54_import_retailrocket_events.sql').read_text(encoding='utf-8').split('-- CHECKS:',1)[0],
        'sql/63_stage_retailrocket_events.sql':(root/'sql/63_stage_retailrocket_events.sql').read_text(encoding='utf-8').split(staging.CHECK_MARKER,1)[0]}
    old_time=json.loads((root/'data/retailrocket_event_time_preflight.json').read_text(encoding='utf-8'))
    assert int(next(row for row in old_time['results'] if row['check_name']=='max_timestamp_ms')['actual'])==OBSERVATION_END_MS
    assert all(hashlib.sha256(code.encode()).hexdigest()==old_time['reconstruction_prefix_sha256'][name] for name,code in prefixes.items())
    assert all('EXCEPT ALL' not in code for code in prefixes.values())
    audit=json.loads((root/'data/retailrocket_source_audit.json').read_text(encoding='utf-8'))
    source_dir=Path(previous.SOURCE).parent
    tmp_root=root/'tmp';tmp_root.mkdir(exist_ok=True);free_before=shutil.disk_usage(tmp_root).free
    assert free_before>=8*1024**3
    sizes=[]
    def settings(folder,database,enrichment=False):
        assert folder.resolve().is_relative_to(tmp_root.resolve()) and Path(database).resolve().is_relative_to(folder.resolve())
        spill=(folder/'spill').as_posix().replace("'","''")
        memory,limit=('2GB','4GB') if enrichment else ('1GB','2GB')
        return f"SET threads=2; SET memory_limit='{memory}'; SET max_temp_directory_size='{limit}'; SET temp_directory='{spill}';\n"
    def observe(folder):
        size=sum(path.stat().st_size for path in folder.rglob('*') if path.is_file());assert size<=7*1024**3;sizes.append(size)
    def execute(folder,database,query,readonly=False,enrichment=False):
        started=time.perf_counter()
        run=subprocess.run([args.duckdb,str(database),'-bail','-json']+(['-readonly'] if readonly else []),
            input=settings(folder,database,enrichment)+query,text=True,encoding='utf-8',capture_output=True,timeout=120)
        if run.returncode:
            diagnostic=run.stderr.lower()
            category=next((name for name,patterns in [('out_of_memory',['out of memory','failed to allocate']),('disk_or_spill',['no space left','max_temp_directory_size']),
                ('parser',['parser error']),('binder',['binder error']),('invalid_input',['invalid input error'])] if any(pattern in diagnostic for pattern in patterns)),'unclassified_cli_error')
            raise AssertionError('Private category-coverage CLI failure: '+category+'; row-bearing details withheld')
        observe(folder)
        return json.loads(run.stdout) if run.stdout.strip() else None,round(time.perf_counter()-started,3)
    def compare_stream(folder,database,event_paths,category_paths,ids,end_ms):
        started=time.perf_counter();expired=threading.Event();stats=blank_stats();interval_stats=histories.blank_interval_stats();count=0;sentinel=object()
        process=subprocess.Popen([args.duckdb,str(database),'-bail','-readonly','-csv','-noheader'],stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,encoding='utf-8')
        def expire():expired.set();process.kill()
        timer=threading.Timer(120,expire);timer.start()
        try:
            process.stdin.write(settings(folder,database)+STREAM);process.stdin.close()
            expected=expected_stream(event_paths,category_paths,ids,end_ms,stats,interval_stats)
            for observed,wanted in zip_longest(csv.reader(process.stdout,strict=True),expected,fillvalue=sentinel):
                assert observed is not sentinel and wanted is not sentinel,'Private ten-field occurrence count differs'
                assert len(observed)==10
                actual=tuple(None if value=='__NULL__' else int(value) if i in {0,1,3,4,6,7} else value for i,value in enumerate(observed))
                assert actual==wanted,'Private ten-field occurrence differs; values withheld';count+=1
            assert process.wait(timeout=120)==0 and not expired.is_set()
        finally:
            timer.cancel()
            if process.poll() is None:process.kill();process.wait()
            process.stdout.close()
        assert count==stats['rows'];observe(folder)
        return stats,interval_stats,round(time.perf_counter()-started,3)

    w=WINDOW_MS
    fixture_rows=[(5,2,'view',2,None),(5,2,'view',2,None),(20,2,'view',2,None),(6,2,'view',10,None),
        (5,10,'view',20,None),(5,10,'view',30,None),(w+1,20,'view',40,None),(2*w,99,'transaction',99,0),
        (7,2,'addtocart',2,None),(10,30,'view',2,None),(0,40,'view',2,None),(0,30,'view',10,None)]
    properties=[(0,2,'categoryid','001',PROPERTY_FILES[0]),(10,2,'categoryid','2',PROPERTY_FILES[1]),
        (5,10,'categoryid','999',PROPERTY_FILES[0]),(10,20,'categoryid','2',PROPERTY_FILES[1]),(0,40,'categoryid','2',PROPERTY_FILES[0])]
    cases=[]
    def fixture_source(folder,rows,props=properties,ids=(1,2)):
        for name in PROPERTY_FILES:
            with (folder/name).open('w',encoding='utf-8',newline='') as stream:
                writer=csv.writer(stream);writer.writerow(['timestamp','itemid','property','value'])
                writer.writerows(row[:4] for row in reversed(props) if row[4]==name)
                writer.writerow((1,2,'available','1'));writer.writerow((1,2,'opaque','x'))
        with (folder/'category_tree.csv').open('w',encoding='utf-8',newline='') as stream:
            writer=csv.writer(stream);writer.writerow(['categoryid','parentid']);writer.writerows((value,'') for value in ids)
        with (folder/'events.csv').open('w',encoding='utf-8',newline='') as stream:
            writer=csv.writer(stream);writer.writerow(staging.FIELDS);writer.writerows(reversed(rows))
        event_paths,event_counts=event_chunks(folder/'events.csv',folder,3)
        category_paths,category_counts=category_chunks(folder,folder,2)
        return event_paths,event_counts,category_paths,category_counts,reference_ids(folder/'category_tree.csv')
    with tempfile.TemporaryDirectory(prefix='rr-first-view-fixture-',dir=tmp_root) as temporary:
        folder,database=Path(temporary),Path(temporary)/'fixture.duckdb'
        ep,ec,cp,cc,ids=fixture_source(folder,fixture_rows)
        reference,_=execute(folder,database,category_build(folder,len(properties),len(ids))+'SELECT categoryid FROM rr_core.dim_category ORDER BY categoryid;')
        assert [row['categoryid'] for row in reference]==sorted(ids)
        execute(folder,database,fixture_events_sql(fixture_rows)+'ALTER TABLE rr_mart.events_enriched ADD COLUMN unqueried_fixture VARCHAR;',enrichment=True)
        before_db=previous.sha256(database)
        report,_=execute(folder,database,adjusted(sql,fixture_rows,len(ids)),readonly=True)
        stats,interval_stats,_=compare_stream(folder,database,ep,cp,ids,ec['observation_end_ms'])
        assert report==reference_report(stats) and [row['eligible_pairs'] for row in report]==[3,1,2,1,7]
        assert previous.sha256(database)==before_db and stats['duplicate_surplus']==1 and stats['maximum_simultaneous_pair_states']==1
        assert stats['maximum_current_item_history_rows']==2 and interval_stats['rows']==5
        assert len(ep)==4 and len(cp)==3 and cc['category_rows']==5 and cc['raw_rows']==9
        cases.append(dict(case='all_four_statuses_numeric_reference_original_text_temporal_boundaries_tied_duplicates_later_category_change',passed=True,
            event_rows=12,event_chunks=4,category_rows=5,category_chunks=3,expected_counts=[3,1,2,1,7],complete_readset_fields=10,extra_unqueried_column_allowed=True))
        one="rowid=(SELECT MIN(rowid) FROM rr_mart.events_enriched WHERE timestamp=5 AND visitorid=2 AND itemid=2 AND event='view')"
        mutations=[('conflicting_tied_value',f"UPDATE rr_mart.events_enriched SET categoryid_value='2' WHERE {one};"),
            ('conflicting_tied_provenance',f'UPDATE rr_mart.events_enriched SET categoryid_source_file={literal(PROPERTY_FILES[1])} WHERE {one};'),
            ('future_match',f'UPDATE rr_mart.events_enriched SET categoryid_from_ms=6 WHERE {one};'),
            ('expired_match',f'UPDATE rr_mart.events_enriched SET categoryid_to_ms=5 WHERE {one};'),
            ('malformed_category_value',f"UPDATE rr_mart.events_enriched SET categoryid_value='x' WHERE {one};"),
            ('unmatched_nonnull_field',"UPDATE rr_mart.events_enriched SET categoryid_value='1' WHERE categoryid_coverage='NO_HISTORY';"),
            ('invalid_status',f"UPDATE rr_mart.events_enriched SET categoryid_coverage='other' WHERE {one};"),
            ('duplicate_reference_id','INSERT INTO rr_core.dim_category VALUES (1);'),
            ('negative_reference_id','UPDATE rr_core.dim_category SET categoryid=-1 WHERE categoryid=1;'),
            ('null_reference_id','UPDATE rr_core.dim_category SET categoryid=NULL WHERE categoryid=1;'),
            ('reference_wrong_type','ALTER TABLE rr_core.dim_category ALTER COLUMN categoryid TYPE VARCHAR;'),
            ('fact_wrong_type','ALTER TABLE rr_mart.events_enriched ALTER COLUMN categoryid_from_ms TYPE VARCHAR;'),
            ('empty_fact','DELETE FROM rr_mart.events_enriched;')]
        for label,mutation in mutations:
            blocked,_=execute(folder,database,'BEGIN;'+mutation+adjusted(sql,fixture_rows,len(ids))+'ROLLBACK;')
            assert [row['coverage_status'] for row in blocked]==LABELS,label
            assert all(row['check_status']=='BLOCKED' and row['eligible_pairs'] is None and row['share_of_eligible_pairs_pct'] is None for row in blocked),label
        for name,value in [('expected_reference_ids',3),('expected_eligible_pairs',8),('expected_observation_end_ms',2*w+1),('expected_duplicate_surplus',0)]:
            blocked,_=execute(folder,database,adjusted(sql,fixture_rows,len(ids),{name:value}),readonly=True)
            assert all(row['check_status']=='BLOCKED' and row['eligible_pairs'] is None and row['share_of_eligible_pairs_pct'] is None for row in blocked)
        cap_failed=False
        try:
            for _ in expected_stream(ep,cp,ids,2*w,blank_stats(),histories.blank_interval_stats(),history_cap=1):pass
        except AssertionError as error:cap_failed='cap exceeded' in str(error)
        assert cap_failed
        cases.append(dict(case='bad_fact_reference_tied_snapshot_cohort_endpoint_and_duplicate_admission_block_all_metrics',passed=True,
            subcases=[name for name,_ in mutations]+['wrong_reference_count','wrong_cohort_count','wrong_endpoint','wrong_duplicate_count'],history_cap_abort_without_filtering=True))
    assert not folder.exists()
    with tempfile.TemporaryDirectory(prefix='rr-first-view-zero-',dir=tmp_root) as temporary:
        parent=Path(temporary)
        for label,rows,props,wanted in [
            ('no_unknown_reference',fixture_rows,[row[:3]+('1',)+row[4:] if row[3]=='999' else row for row in properties],[4,0,2,1,7]),
            ('zero_eligible',[(w+1,1,'view',2,None),(2*w,99,'transaction',99,0)],properties,[0,0,0,0,0])]:
            folder=parent/label;folder.mkdir();database=folder/'fixture.duckdb'
            ep,ec,cp,cc,ids=fixture_source(folder,rows,props)
            execute(folder,database,category_build(folder,len(props),len(ids)))
            execute(folder,database,fixture_events_sql(rows),enrichment=True)
            report,_=execute(folder,database,adjusted(sql,rows,len(ids)),readonly=True)
            stats,interval_stats,_=compare_stream(folder,database,ep,cp,ids,ec['observation_end_ms'])
            assert report==reference_report(stats) and [row['eligible_pairs'] for row in report]==wanted
            if label=='zero_eligible':assert all(row['share_of_eligible_pairs_pct'] is None for row in report)
        cases.append(dict(case='zero_unknown_reference_allowed_and_zero_eligible_all_shares_NULL',passed=True,subcases=2))
        folder=parent/'conflicting_source';folder.mkdir();database=folder/'fixture.duckdb'
        props=properties+[(0,2,'categoryid','2',PROPERTY_FILES[1])]
        fixture_source(folder,fixture_rows,props)
        rejected=subprocess.run([args.duckdb,str(database),'-bail','-json'],input=settings(folder,database)+category_build(folder,len(props),2),
            text=True,encoding='utf-8',capture_output=True,timeout=120)
        assert rejected.returncode!=0 and 'private category source guard failed' in rejected.stderr
        absent,_=execute(folder,database,"SELECT COUNT(*) AS rows FROM information_schema.tables WHERE table_schema='rr_private' AND table_name IN ('category_observations','category_intervals');",readonly=True)
        assert absent==[{'rows':0}]
        cases.append(dict(case='conflicting_source_observation_key_fails_before_interval_or_asof_creation',passed=True))
    assert not parent.exists()
    print(json.dumps({'fixture_families_passed':len(cases),'invalid_admission_subcases':len(mutations)+4,'source_key_conflict_rejected':True}),flush=True)
    if args.fixtures_only:return

    before={name:staging.snapshot(source_dir/name) for name in FILES}
    assert all(before[name]['sha256']==audit['files'][name]['sha256'] and before[name]['size_bytes']==audit['publisher_expected_bytes'][name] for name in FILES)
    historical={str(path.relative_to(root)):previous.sha256(path) for path in (root/'data').glob('*preflight.json') if path.resolve()!=output.resolve()}
    assert len(historical)==71
    with tempfile.TemporaryDirectory(prefix='rr-first-view-real-',dir=tmp_root) as temporary:
        folder,database=Path(temporary),Path(temporary)/'preflight.duckdb'
        started=time.perf_counter();cp,category_counts=category_chunks(source_dir,folder);category_sort_seconds=round(time.perf_counter()-started,3)
        assert category_counts['raw_rows']==20275902 and category_counts['category_rows']==788214
        assert list(category_counts['raw_parts'].values())==[10999999,9275903]
        print(json.dumps({'phase':'category-only source selection and sorting complete','selected_observations':788214}),flush=True)
        started=time.perf_counter();ep,event_counts=event_chunks(source_dir/'events.csv',folder);event_sort_seconds=round(time.perf_counter()-started,3)
        assert event_counts==dict(rows=2756101,view=2664312,addtocart=69332,transaction=22457,null_transaction_ids=2733644,observation_end_ms=OBSERVATION_END_MS)
        ids=reference_ids(source_dir/'category_tree.csv');assert len(ids)==1669
        chunk_bytes=sum(path.stat().st_size for path in cp+ep)
        reference,category_build_seconds=execute(folder,database,category_build(source_dir,788214,1669)+'SELECT categoryid FROM rr_core.dim_category ORDER BY categoryid;')
        assert [row['categoryid'] for row in reference]==sorted(ids)
        print(json.dumps({'phase':1,'result':'category-only intervals and complete reference-ID projection passed'}),flush=True)
        _,enrichment_seconds=execute(folder,database,'\n'.join(prefixes.values())+'\n'+ENRICHMENT,enrichment=True)
        print(json.dumps({'phase':2,'result':'category-only ten-field projection built'}),flush=True)
        database_before=previous.sha256(database)
        report,query_seconds=execute(folder,database,sql,readonly=True)
        assert [row['check_status'] for row in report]==['PASS']*5 and all(list(row)==OUTPUT for row in report)
        print(json.dumps({'phase':3,'result':'SQL73 five-row category coverage passed'}),flush=True)
        stats,interval_stats,stream_seconds=compare_stream(folder,database,ep,cp,ids,event_counts['observation_end_ms'])
        assert report==reference_report(stats) and stats['rows']==2756101 and stats['duplicate_surplus']==460 and stats['eligible_pairs']==2042310
        assert interval_stats['rows']==788214 and stats['maximum_simultaneous_pair_states']==1
        database_after=previous.sha256(database);assert database_before==database_after
        database_bytes=database.stat().st_size
        private_category_build_hash=hashlib.sha256(category_build(source_dir,788214,1669).encode()).hexdigest()
    assert not folder.exists()
    after={name:staging.snapshot(source_dir/name) for name in FILES}
    assert before==after and all(previous.sha256(root/name)==digest for name,digest in hashes.items())
    assert all(previous.sha256(root/name)==digest for name,digest in historical.items())
    assert (root/method_path).read_bytes().startswith(contract)
    evidence=dict(checked_at_utc=datetime.now(timezone.utc).isoformat(),executor='assistant',
        engine=subprocess.check_output([args.duckdb,'-version'],text=True).strip(),
        script=script_path,script_sha256=hashes[script_path],validator=validator_path,validator_sha256=hashes[validator_path],
        code_and_dependency_sha256=hashes,method_contract=method_path,method_contract_prefix_bytes=len(contract),method_contract_prefix_sha256=CONTRACT_SHA,
        source_files=FILES,source_before=before,source_after=after,source_hashes_and_metadata_unchanged=True,
        reconstruction_prefix_sha256={name:hashlib.sha256(code.encode()).hexdigest() for name,code in prefixes.items()},
        private_category_build_sha256=private_category_build_hash,private_category_enrichment_sha256=hashlib.sha256(ENRICHMENT.encode()).hexdigest(),
        projection_scope='Category-only ten-field disposable fact plus ID-only category reference. SQL69 full seventeen-field fact and SQL62 hierarchy remain supported by their accepted evidence and are not rebuilt or reverified.',
        source_table='rr_mart.events_enriched',readset_fields=FACT_FIELDS,required_readset_columns=10,
        reference_table='rr_core.dim_category',reference_readset_fields=['categoryid'],reference_ids_compared=1669,independent_reference_id_set_matched=True,
        full17_not_reverified=True,reference_hierarchy_not_reverified=True,property_files_read=True,category_csv_read=True,
        category_only_history_reconstructed=True,availability_history_reconstructed=False,UTC_fields_read=False,
        SQL69_rerun=False,SQL62_hierarchy_rerun=False,SQL70_rerun=False,SQL71_rerun=False,SQL72_rerun=False,learner_database_opened=False,
        query_read_only=True,private_stream_read_only=True,real_source_attempts=1,real_cli_phases=4,
        real_category_build_executions=1,real_category_enrichment_executions=1,real_analysis_script_executions=1,real_private_stream_executions=1,
        report_rows=5,report_columns=4,output_columns=OUTPUT,checks_passed=5,fail_rows=0,blocked_rows=0,results=report,report_sha256=report_hash(report),
        report_fingerprint_contract='SHA-256 of compact JSON arrays in output-column order followed by LF; four-place DECIMAL shares are JSON strings, counts integers and undefined shares null.',
        independent_python_event_counts=event_counts,independent_python_category_counts=category_counts,
        independent_python_interval_counts=interval_stats,independent_python_aggregate_counts=stats,
        independent_python_report_matched=True,independent_python_Decimal_shares_matched=True,independent_one_pair_streaming_state=True,
        independent_stream_occurrences_compared=stats['rows'],independent_stream_fields_compared=10,independent_stream_all_occurrences_matched=True,
        independent_original_event_fields_and_duplicates_preserved=True,independent_category_values_bounds_provenance_statuses_matched=True,
        selected_category_history_fully_drained=True,eligible_first_view_tie_consistency_verified=True,numeric_reference_lookup_preserves_original_text=True,
        window_ms=WINDOW_MS,observation_end_ms=event_counts['observation_end_ms'],observation_end_utc=base.utc_text(event_counts['observation_end_ms']),
        eligibility_cutoff_ms=event_counts['observation_end_ms']-WINDOW_MS,eligibility_cutoff_utc=base.utc_text(event_counts['observation_end_ms']-WINDOW_MS),
        eligible_pairs=stats['eligible_pairs'],expected_eligible_pairs=2042310,coverage_partition_reconciled=True,
        maximum_simultaneous_pair_states=stats['maximum_simultaneous_pair_states'],maximum_current_item_history_rows=stats['maximum_current_item_history_rows'],
        private_database_sha256_before_readonly=database_before,private_database_sha256_after_readonly=database_after,private_database_bytes_unchanged=True,
        fixture_case_count=len(cases),fixture_cases=cases,invalid_admission_fixture_subcases=len(mutations)+4,
        invalid_admission_blocks_all_metrics_verified=True,additional_unqueried_columns_allowed_verified=True,zero_denominator_NULLs_verified=True,
        preflight_settings=dict(threads=2,default_memory_limit='1GB',default_max_temp_directory_size='2GB',
            category_enrichment_memory_limit='2GB',category_enrichment_max_temp_directory_size='4GB',timeout_seconds_per_cli_phase=120,
            python_sort_chunk_rows=CHUNK_ROWS,current_item_history_row_cap=HISTORY_CAP,simultaneous_pair_state_budget=1,
            minimum_free_bytes=8*1024**3,private_directory_budget_bytes=7*1024**3),
        private_event_comparison_chunks=len(ep),private_category_comparison_chunks=len(cp),private_comparison_chunk_bytes=chunk_bytes,
        private_database_bytes_before_cleanup=database_bytes,largest_private_directory_bytes_observed_after_phase=max(sizes),
        workspace_free_bytes_before=free_before,workspace_free_bytes_after=shutil.disk_usage(tmp_root).free,
        temporary_databases_and_spills_removed=True,private_source_comparison_spools_removed=True,
        historical_preflight_files_unchanged=len(historical),historical_comparison_or_analysis_suites_rerun=False,
        source_records_or_identifiers_uploaded_or_logged=False,
        elapsed_python_category_scan_sort_seconds=category_sort_seconds,elapsed_python_event_scan_sort_seconds=event_sort_seconds,
        elapsed_category_build_seconds=category_build_seconds,elapsed_category_enrichment_seconds=enrichment_seconds,
        elapsed_readonly_category_coverage_seconds=query_seconds,elapsed_private_stream_seconds=stream_seconds,
        timing_scope='Four CLI phases: category-only import/intervals and ID projection; frozen event prefixes plus category-only enrichment; read-only SQL73; read-only ten-field source comparison. Sorting timed separately; hashing and fixtures excluded.',
        scope='Assistant SQL73 passed; learner execution pending. Category coverage at earliest observed view within the unchanged seven-day-eligible visitor-item cohort. MAPPED means observation assignment plus numeric static-reference membership, not validated freshness, business truth, inventory, hierarchy, or category-specific conversion.')
    output.write_text(json.dumps(evidence,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps({'report_rows':5,'checks_passed':5,'occurrences_compared':stats['rows'],'fields_compared':10,'report_sha256':evidence['report_sha256']}),flush=True)

if __name__=='__main__':main()
