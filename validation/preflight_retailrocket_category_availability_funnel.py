"""Verify the first-view recorded-availability funnel with both named histories."""
import argparse
import bisect
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
from datetime import datetime, timezone
from itertools import zip_longest
from pathlib import Path

import preflight_retailrocket_category_item_cart_concentration as item_analysis

funnel=item_analysis.funnel
coverage=funnel.coverage
base=coverage.base
histories=coverage.histories
staging=coverage.staging
previous=coverage.previous
PROPERTY_FILES=coverage.PROPERTY_FILES
FILES=coverage.FILES
MAX_MS=coverage.MAX_MS
WINDOW_MS=coverage.WINDOW_MS
OBSERVATION_END_MS=coverage.OBSERVATION_END_MS
CHUNK_ROWS=coverage.CHUNK_ROWS
HISTORY_CAP=coverage.HISTORY_CAP
CONTRACT_SHA='33311c7d9048a25a0f260b8c1ccef6d91bc8cbcf71d526dfd55dbf585c87f02c'
TARGET_CATEGORY=1613
LABELS=['RECORDED_1','RECORDED_0','BEFORE_FIRST','NO_HISTORY','TOTAL']
OUTPUT=['availability_status','eligible_pairs','cart_pairs','transaction_pairs','eligible_share_pct','cart_rate_pct','transaction_rate_pct','cart_to_transaction_rate_pct','check_status']
FACT_FIELDS=coverage.FACT_FIELDS+['available_value','available_from_ms','available_to_ms','available_source_file','available_coverage']
PARAMETERS=item_analysis.PARAMETERS
literal=coverage.literal
event_chunks=coverage.event_chunks
merged_events=coverage.merged_events
reference_ids=coverage.reference_ids
adjusted=item_analysis.adjusted

ENRICHMENT='''CREATE SCHEMA rr_mart;
CREATE TABLE rr_mart.events_enriched AS
WITH first_history AS (SELECT itemid,
 MIN(observed_from_ms) FILTER(WHERE property='categoryid') AS first_category,
 MIN(observed_from_ms) FILTER(WHERE property='available') AS first_available
 FROM rr_private.item_state_intervals GROUP BY itemid)
SELECT e.timestamp,e.visitorid,e.event,e.itemid,e.transactionid,
 c.value AS categoryid_value,c.observed_from_ms AS categoryid_from_ms,c.observed_to_ms AS categoryid_to_ms,c.source_file AS categoryid_source_file,
 CASE WHEN c.observed_from_ms IS NOT NULL THEN 'MATCHED' WHEN h.first_category IS NULL THEN 'NO_HISTORY'
      WHEN e.timestamp<h.first_category THEN 'BEFORE_FIRST' ELSE 'INVALID' END AS categoryid_coverage,
 a.value AS available_value,a.observed_from_ms AS available_from_ms,a.observed_to_ms AS available_to_ms,a.source_file AS available_source_file,
 CASE WHEN a.observed_from_ms IS NOT NULL THEN 'MATCHED' WHEN h.first_available IS NULL THEN 'NO_HISTORY'
      WHEN e.timestamp<h.first_available THEN 'BEFORE_FIRST' ELSE 'INVALID' END AS available_coverage
FROM rr_stg.events e LEFT JOIN first_history h ON e.itemid=h.itemid
ASOF LEFT JOIN (SELECT * FROM rr_private.item_state_intervals WHERE property='categoryid') c ON e.itemid=c.itemid AND e.timestamp>=c.observed_from_ms
ASOF LEFT JOIN (SELECT * FROM rr_private.item_state_intervals WHERE property='available') a ON e.itemid=a.itemid AND e.timestamp>=a.observed_from_ms;'''
STREAM='''SELECT timestamp,visitorid,event,itemid,COALESCE(CAST(transactionid AS VARCHAR),'__NULL__'),
 COALESCE(categoryid_value,'__NULL__'),COALESCE(CAST(categoryid_from_ms AS VARCHAR),'__NULL__'),
 COALESCE(CAST(categoryid_to_ms AS VARCHAR),'__NULL__'),COALESCE(categoryid_source_file,'__NULL__'),categoryid_coverage,
 COALESCE(available_value,'__NULL__'),COALESCE(CAST(available_from_ms AS VARCHAR),'__NULL__'),
 COALESCE(CAST(available_to_ms AS VARCHAR),'__NULL__'),COALESCE(available_source_file,'__NULL__'),available_coverage
FROM rr_mart.events_enriched ORDER BY itemid,visitorid,timestamp,event,transactionid NULLS FIRST;'''

def named_build(source_dir,category_rows,available_rows,reference_count):
    reads=[]
    for name in PROPERTY_FILES:
        path=(source_dir/name).as_posix()
        reads.append(f"SELECT timestamp,itemid,property,value,{literal(name)} AS source_file FROM read_csv({literal(path)},header=true,auto_detect=false,columns={{'timestamp':'VARCHAR','itemid':'VARCHAR','property':'VARCHAR','value':'VARCHAR'}},delim=',',quote='\"',escape='\"',nullstr='',force_not_null=['timestamp','itemid','property','value'],strict_mode=true,ignore_errors=false,null_padding=false) WHERE property IN ('categoryid','available')")
    reference_sql=coverage.category_build(source_dir,category_rows,reference_count).split('CREATE SCHEMA rr_core;',1)[1]
    return f'''CREATE SCHEMA rr_private;
CREATE TABLE rr_private.item_state_observations AS
WITH selected AS MATERIALIZED ({' UNION ALL '.join(reads)}), health AS (
 SELECT COUNT(*) AS rows,COUNT(DISTINCT (itemid,property,timestamp)) AS keys,
 COUNT(*) FILTER(WHERE property='categoryid') AS category_rows,COUNT(*) FILTER(WHERE property='available') AS available_rows,
 COUNT(*) FILTER(WHERE NOT COALESCE(regexp_full_match(timestamp,'[0-9]+') AND TRY_CAST(timestamp AS BIGINT) BETWEEN 0 AND {MAX_MS}
 AND CAST(TRY_CAST(timestamp AS BIGINT) AS VARCHAR)=timestamp AND regexp_full_match(itemid,'[0-9]+') AND TRY_CAST(itemid AS BIGINT)>=0
 AND CAST(TRY_CAST(itemid AS BIGINT) AS VARCHAR)=itemid AND
 ((property='categoryid' AND regexp_full_match(value,'[0-9]+') AND TRY_CAST(value AS BIGINT) IS NOT NULL)
 OR (property='available' AND value IN ('0','1'))),false)) AS invalid_rows FROM selected
), guard AS (SELECT rows={category_rows+available_rows} AND rows>0 AND category_rows={category_rows} AND available_rows={available_rows} AND keys=rows AND invalid_rows=0 AS valid FROM health)
SELECT CASE WHEN g.valid THEN CAST(s.itemid AS BIGINT) ELSE error('SQL77 private named source guard failed') END AS itemid,
 CASE WHEN g.valid THEN CAST(s.timestamp AS BIGINT) ELSE error('SQL77 private named source guard failed') END AS timestamp,
 CASE WHEN g.valid THEN s.property ELSE error('SQL77 private named source guard failed') END AS property,
 CASE WHEN g.valid THEN s.value ELSE error('SQL77 private named source guard failed') END AS value,
 CASE WHEN g.valid THEN s.source_file ELSE error('SQL77 private named source guard failed') END AS source_file
FROM guard g LEFT JOIN selected s ON g.valid;
CREATE TABLE rr_private.item_state_intervals AS SELECT itemid,property,value,timestamp AS observed_from_ms,
 LEAD(timestamp) OVER(PARTITION BY itemid,property ORDER BY timestamp) AS observed_to_ms,source_file FROM rr_private.item_state_observations;
CREATE SCHEMA rr_core;'''+reference_sql

def named_chunks(source_dir,folder,chunk_rows=CHUNK_ROWS):
    paths,chunk=[],[];counts=dict(raw_rows=0,raw_parts={},selected_rows=0,categoryid_rows=0,available_rows=0,selected_parts={})
    def flush():
        chunk.sort();output=folder/f'named-history-{len(paths):04d}.csv'
        with output.open('w',encoding='utf-8',newline='') as stream:csv.writer(stream).writerows(chunk)
        paths.append(output);chunk.clear()
    for name in PROPERTY_FILES:
        counts['raw_parts'][name]=0;counts['selected_parts'][name]=0
        with (source_dir/name).open('r',encoding='utf-8',newline='') as stream:
            reader=csv.reader(stream,strict=True);assert next(reader)==['timestamp','itemid','property','value']
            for raw in reader:
                assert len(raw)==4
                counts['raw_rows']+=1;counts['raw_parts'][name]+=1
                if raw[2] not in ('categoryid','available'):continue
                assert histories.staging.valid_named(raw) and int(raw[0])<=MAX_MS,'Private named source rule failure; values withheld'
                chunk.append((int(raw[1]),raw[2],int(raw[0]),raw[3],name))
                counts['selected_rows']+=1;counts[raw[2]+'_rows']+=1;counts['selected_parts'][name]+=1
                if len(chunk)==chunk_rows:flush()
    if chunk:flush()
    assert counts['selected_rows']>0
    return paths,counts

def fixture_events_sql(rows):
    return coverage.fixture_events_sql(rows).rsplit(coverage.ENRICHMENT,1)[0]+ENRICHMENT

def blank_stats():
    result=coverage.blank_stats()
    result.update(cart_pairs=0,transaction_pairs=0,selected_eligible_pairs=0,selected_cart_pairs=0,selected_transaction_pairs=0,
                  availability_counts={label:[0,0,0] for label in LABELS[:-1]})
    return result

def expected_stream(event_paths,named_paths,ids,end_ms,stats,interval_stats,history_cap=HISTORY_CAP):
    source=iter(histories.expected_intervals(histories.merged_source(named_paths),interval_stats));pending=next(source,None)
    current_item=None;history={};starts={};current_pair=None;first_view=None;first_snapshot=None;cart_ms=None;transaction_ms=None;prior_event=None
    def close_pair():
        stats['observed_pairs']+=1
        if first_view is None:return
        stats['viewed_pairs']+=1
        if first_view+WINDOW_MS>end_ms:return
        stats['eligible_pairs']+=1
        status=first_snapshot[4]
        mapped=('MAPPED' if int(first_snapshot[0]) in ids else 'UNKNOWN_REFERENCE') if status=='MATCHED' else status
        assert mapped in coverage.LABELS[:-1];stats[mapped]+=1
        counts=[1,int(cart_ms is not None),int(transaction_ms is not None)]
        stats['cart_pairs']+=counts[1];stats['transaction_pairs']+=counts[2]
        if mapped=='MAPPED' and int(first_snapshot[0])==TARGET_CATEGORY:
            status=first_snapshot[9]
            bucket='RECORDED_'+first_snapshot[5] if status=='MATCHED' else status
            assert bucket in LABELS[:-1]
            for i,name in enumerate(['selected_eligible_pairs','selected_cart_pairs','selected_transaction_pairs']):
                stats[name]+=counts[i];stats['availability_counts'][bucket][i]+=counts[i]
    for event in merged_events(event_paths):
        item=event[3];pair=(item,event[1])
        if current_pair!=pair:
            if current_pair is not None:close_pair()
            if current_item!=item:
                while pending is not None and pending[0]<item:pending=next(source,None)
                history={'categoryid':[],'available':[]};combined=0
                while pending is not None and pending[0]==item:
                    assert combined<history_cap,'Private combined current-item history cap exceeded; no filtering'
                    history[pending[1]].append(pending);combined+=1;pending=next(source,None)
                starts={name:[row[3] for row in rows] for name,rows in history.items()};current_item=item
                stats['maximum_current_item_history_rows']=max(stats['maximum_current_item_history_rows'],combined)
            current_pair=pair;first_view=None;first_snapshot=None;cart_ms=None;transaction_ms=None;stats['maximum_simultaneous_pair_states']=1
        snapshot=()
        for name in ('categoryid','available'):
            index=bisect.bisect_right(starts[name],event[0])-1
            if not history[name]:part=(None,None,None,None,'NO_HISTORY')
            elif index<0:part=(None,None,None,None,'BEFORE_FIRST')
            else:
                row=history[name][index];assert row[3]<=event[0] and (row[4] is None or event[0]<row[4])
                part=(row[2],row[3],row[4],row[5],'MATCHED')
            snapshot+=part
        if event[2]=='view':
            if first_view is None:first_view=event[0];first_snapshot=snapshot
            if event[0]==first_view and first_view+WINDOW_MS<=end_ms:
                assert snapshot==first_snapshot;stats['first_view_occurrences']+=1
        if first_view is not None and event[0]<=first_view+WINDOW_MS:
            if event[2]=='addtocart' and event[0]>first_view and cart_ms is None:cart_ms=event[0]
            elif event[2]=='transaction' and cart_ms is not None and event[0]>cart_ms and transaction_ms is None:transaction_ms=event[0]
        stats['rows']+=1;stats['duplicate_surplus']+=event==prior_event;prior_event=event
        stats['observed_max_timestamp_ms']=event[0] if stats['observed_max_timestamp_ms'] is None else max(stats['observed_max_timestamp_ms'],event[0])
        yield event+snapshot
    if current_pair is not None:close_pair()
    for _ in source:pass
    assert sum(stats[label] for label in coverage.LABELS[:-1])==stats['eligible_pairs']
    assert stats['observed_max_timestamp_ms']==end_ms

def reference_report(stats):
    total=[stats[name] for name in ['selected_eligible_pairs','selected_cart_pairs','selected_transaction_pairs']];report=[]
    assert [sum(counts[i] for counts in stats['availability_counts'].values()) for i in range(3)]==total
    for label in LABELS:
        eligible,carts,transactions=total if label=='TOTAL' else stats['availability_counts'][label]
        assert eligible>=carts>=transactions
        report.append(dict(zip(OUTPUT,[label,eligible,carts,transactions,funnel.rate(eligible,total[0]),funnel.rate(carts,eligible),
                                       funnel.rate(transactions,eligible),funnel.rate(transactions,carts),'PASS'])))
    return report

def report_hash(report):
    return hashlib.sha256(''.join(json.dumps([row[name] for name in OUTPUT],separators=(',',':'))+'\n' for row in report).encode()).hexdigest()

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--duckdb',required=True);parser.add_argument('--output',required=True);parser.add_argument('--fixtures-only',action='store_true');args=parser.parse_args()
    root=Path(__file__).resolve().parents[1];output=(root/args.output).resolve()
    assert output.is_relative_to((root/'data').resolve())
    script_path='sql/77_analyze_retailrocket_category_availability_funnel.sql'
    validator_path='validation/preflight_retailrocket_category_availability_funnel.py'
    method_path='docs/RETAILROCKET_CATEGORY_AVAILABILITY_FUNNEL_VALIDATION.md'
    dependencies=[script_path,validator_path,'validation/preflight_retailrocket_category_item_cart_concentration.py','validation/preflight_retailrocket_category_7day_funnel.py','validation/preflight_retailrocket_first_view_category_coverage.py','sql/54_import_retailrocket_events.sql','sql/63_stage_retailrocket_events.sql',
        'validation/preflight_retailrocket_events_import.py','validation/preflight_retailrocket_events_staging.py',
        'validation/preflight_retailrocket_properties_import.py','validation/preflight_retailrocket_item_state_observations.py',
        'validation/preflight_retailrocket_item_state_intervals.py','validation/preflight_retailrocket_7day_visitor_item_funnel.py',
        'data/retailrocket_source_audit.json','data/retailrocket_event_time_preflight.json',
        'sql/62_build_retailrocket_category_dimension.sql','data/retailrocket_category_dimension_preflight.json',
        'data/retailrocket_category_dimension_learner_acceptance.json','docs/RETAILROCKET_CATEGORY_DIMENSION_VALIDATION.md',
        'sql/69_build_retailrocket_events_enriched.sql','data/retailrocket_events_enriched_preflight.json',
        'data/retailrocket_events_enriched_learner_acceptance.json','docs/RETAILROCKET_EVENTS_ENRICHED_VALIDATION.md',
        'sql/72_analyze_retailrocket_7day_visitor_item_funnel.sql','data/retailrocket_7day_visitor_item_funnel_preflight.json',
        'data/retailrocket_7day_visitor_item_funnel_learner_acceptance.json','docs/RETAILROCKET_7DAY_VISITOR_ITEM_FUNNEL_VALIDATION.md','sql/73_audit_retailrocket_first_view_category_coverage.sql',
        'data/retailrocket_first_view_category_coverage_preflight.json','data/retailrocket_first_view_category_coverage_learner_acceptance.json',
        'docs/RETAILROCKET_FIRST_VIEW_CATEGORY_COVERAGE_VALIDATION.md','sql/74_analyze_retailrocket_category_7day_funnel.sql',
        'data/retailrocket_category_7day_funnel_preflight.json','data/retailrocket_category_7day_funnel_learner_acceptance.json',
        'docs/RETAILROCKET_CATEGORY_7DAY_FUNNEL_VALIDATION.md','sql/75_analyze_retailrocket_category_funnel_time_cohorts.sql',
        'data/retailrocket_category_funnel_time_cohorts_preflight.json','data/retailrocket_category_funnel_time_cohorts_learner_acceptance.json',
        'docs/RETAILROCKET_CATEGORY_FUNNEL_TIME_COHORTS_VALIDATION.md','sql/76_analyze_retailrocket_category_item_cart_concentration.sql',
        'data/retailrocket_category_item_cart_concentration_preflight.json','data/retailrocket_category_item_cart_concentration_learner_acceptance.json',
        'docs/RETAILROCKET_CATEGORY_ITEM_CART_CONCENTRATION_VALIDATION.md']
    hashes={name:previous.sha256(root/name) for name in dependencies}
    contract=(root/method_path).read_bytes().split(b'\n## Executed results\n',1)[0]
    assert hashlib.sha256(contract).hexdigest()==CONTRACT_SHA
    for stem,script in [('category_dimension','sql/62_build_retailrocket_category_dimension.sql'),
                        ('events_enriched','sql/69_build_retailrocket_events_enriched.sql'),
                        ('7day_visitor_item_funnel','sql/72_analyze_retailrocket_7day_visitor_item_funnel.sql'),
                        ('first_view_category_coverage','sql/73_audit_retailrocket_first_view_category_coverage.sql'),
                        ('category_7day_funnel','sql/74_analyze_retailrocket_category_7day_funnel.sql'),
                        ('category_funnel_time_cohorts','sql/75_analyze_retailrocket_category_funnel_time_cohorts.sql'),
                        ('category_item_cart_concentration','sql/76_analyze_retailrocket_category_item_cart_concentration.sql')]:
        old=json.loads((root/f'data/retailrocket_{stem}_preflight.json').read_text(encoding='utf-8'))
        accepted=json.loads((root/f'data/retailrocket_{stem}_learner_acceptance.json').read_text(encoding='utf-8'))
        assert accepted['acceptance_status'].startswith('accepted') and accepted['report_sha256']==old['report_sha256']
        assert old['script_sha256']==hashes[script]
    assert [old['results'][-1][name] for name in ['eligible_pairs','cart_pairs','transaction_pairs']]==[25105,483,76]
    periods=json.loads((root/'data/retailrocket_category_funnel_time_cohorts_preflight.json').read_text(encoding='utf-8'))
    category=json.loads((root/'data/retailrocket_category_7day_funnel_preflight.json').read_text(encoding='utf-8'))
    parent=next(row for row in category['results'] if row['categoryid']==TARGET_CATEGORY)
    assert [parent[name] for name in ['eligible_pairs','cart_pairs','transaction_pairs']]==[25105,483,76]
    assert [sum(row[name] for row in periods['results'] if row['categoryid']==TARGET_CATEGORY) for name in ['eligible_pairs','cart_pairs','transaction_pairs']]==[25105,483,76]
    overall=json.loads((root/'data/retailrocket_7day_visitor_item_funnel_preflight.json').read_text(encoding='utf-8'))
    assert [row['visitor_item_pairs'] for row in overall['results']][-3:]==[2042310,43147,15520]
    sql=(root/script_path).read_text(encoding='utf-8');clean=re.sub(r'--[^\n]*','',sql)
    assert clean.lstrip().startswith('WITH ') and not re.search(r'\b(CREATE|INSERT|UPDATE|DELETE|DROP|ALTER|COPY|ATTACH|DETACH|SET)\b',clean,re.I)
    assert all(name not in clean for name in ['event_timestamp_utc','event_date_utc','parentid','root_categoryid','depth'])
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
            raise AssertionError('Private availability funnel CLI failure: '+category+'; row-bearing details withheld')
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
                assert observed is not sentinel and wanted is not sentinel,'Private fifteen-field occurrence count differs'
                assert len(observed)==15
                actual=tuple(None if value=='__NULL__' else int(value) if i in {0,1,3,4,6,7,11,12} else value for i,value in enumerate(observed))
                assert actual==wanted,'Private fifteen-field occurrence differs; values withheld';count+=1
            assert process.wait(timeout=120)==0 and not expired.is_set()
        finally:
            timer.cancel()
            if process.poll() is None:process.kill();process.wait()
            process.stdout.close()
        assert count==stats['rows'];observe(folder)
        return stats,interval_stats,round(time.perf_counter()-started,3)


    w=WINDOW_MS
    properties=[(0,item,'categoryid','01613',PROPERTY_FILES[0]) for item in [2,10,20,30,60]]
    properties.extend([(10,40,'categoryid','1613',PROPERTY_FILES[1]),(0,50,'categoryid','2',PROPERTY_FILES[0]),
        (0,2,'available','1',PROPERTY_FILES[0]),(10,2,'available','0',PROPERTY_FILES[1]),
        (0,10,'available','0',PROPERTY_FILES[0]),(10,10,'available','1',PROPERTY_FILES[1]),
        (10,20,'available','1',PROPERTY_FILES[1]),(0,40,'available','1',PROPERTY_FILES[1]),
        (0,50,'available','1',PROPERTY_FILES[1]),(0,60,'available','1',PROPERTY_FILES[1])])
    fixture_rows=[]
    for item,visitor,view,cart,transaction in [(2,2,5,11,12),(10,10,5,11,12),(20,20,5,11,12),(30,30,5,6,7),
        (2,3,10,11,12),(60,60,0,w,w+1),(60,61,0,0,1),(40,40,5,11,12),(50,50,0,1,2),(2,99,w+1,w+2,w+3)]:
        fixture_rows.extend([(view,visitor,'view',item,None),(cart,visitor,'addtocart',item,None),(transaction,visitor,'transaction',item,visitor)])
    fixture_rows.extend([(5,2,'view',2,None),(2*w,999,'addtocart',999,None)])
    cases=[]
    def fixture_source(folder,rows):
        for name in PROPERTY_FILES:
            with (folder/name).open('w',encoding='utf-8',newline='') as stream:
                writer=csv.writer(stream);writer.writerow(['timestamp','itemid','property','value']);writer.writerows(row[:4] for row in reversed(properties) if row[4]==name)
        with (folder/'category_tree.csv').open('w',encoding='utf-8',newline='') as stream:
            writer=csv.writer(stream);writer.writerow(['categoryid','parentid']);writer.writerows((value,'') for value in [2,TARGET_CATEGORY])
        with (folder/'events.csv').open('w',encoding='utf-8',newline='') as stream:
            writer=csv.writer(stream);writer.writerow(staging.FIELDS);writer.writerows(reversed(rows))
        ep,ec=event_chunks(folder/'events.csv',folder,3);cp,cc=named_chunks(folder,folder,2);ids=reference_ids(folder/'category_tree.csv')
        stats=blank_stats()
        for _ in expected_stream(ep,cp,ids,ec['observation_end_ms'],stats,histories.blank_interval_stats()):pass
        return ep,ec,cp,cc,ids,stats
    with tempfile.TemporaryDirectory(prefix='rr-availability-fixture-',dir=tmp_root) as temporary:
        folder,database=Path(temporary),Path(temporary)/'fixture.duckdb'
        ep,ec,cp,cc,ids,wanted=fixture_source(folder,fixture_rows)
        reference,_=execute(folder,database,named_build(folder,cc['categoryid_rows'],cc['available_rows'],len(ids))+'SELECT categoryid FROM rr_core.dim_category ORDER BY categoryid;')
        assert [row['categoryid'] for row in reference]==sorted(ids)
        execute(folder,database,fixture_events_sql(fixture_rows)+'ALTER TABLE rr_mart.events_enriched ADD COLUMN unqueried_fixture VARCHAR;',enrichment=True)
        query=adjusted(sql,fixture_rows,len(ids),wanted)
        before_db=previous.sha256(database);report,_=execute(folder,database,query,readonly=True)
        stats,interval_stats,_=compare_stream(folder,database,ep,cp,ids,ec['observation_end_ms'])
        assert report==reference_report(stats) and stats==wanted and previous.sha256(database)==before_db
        assert [[row[name] for name in ['eligible_pairs','cart_pairs','transaction_pairs']] for row in report]==[[3,2,1],[2,2,2],[1,1,1],[1,1,1],[7,6,5]]
        assert stats['duplicate_surplus']==1 and interval_stats['rows']==15 and stats['maximum_current_item_history_rows']==3
        cases.append(dict(case='two_recorded_values_two_missing_classes_independent_observation_clocks_fixed_first_view_exact_boundary_strict_deadline_and_duplicates',passed=True,
            event_rows=len(fixture_rows),expected_target_counts=[7,6,5],complete_readset_fields=15,named_history_rows=15))
        def assert_blocked(rows):
            assert [row['availability_status'] for row in rows]==LABELS
            assert all(row['check_status']=='BLOCKED' and all(row[name] is None for name in OUTPUT[1:-1]) for row in rows)
        blocked,_=execute(folder,database,adjusted(sql,fixture_rows,len(ids),wanted,override={'expected_target_pairs':8}),readonly=True);assert_blocked(blocked)
        one="rowid=(SELECT MIN(rowid) FROM rr_mart.events_enriched WHERE timestamp=5 AND visitorid=2 AND itemid=2 AND event='view')"
        mutations=["available_value='0'", "available_value='01'", "available_from_ms=6", "available_to_ms=5", "available_coverage='NO_HISTORY'", "available_source_file='other.csv'"]
        for mutation in mutations:
            blocked,_=execute(folder,database,'BEGIN;UPDATE rr_mart.events_enriched SET '+mutation+' WHERE '+one+';'+query+'ROLLBACK;');assert_blocked(blocked)
        blocked,_=execute(folder,database,"BEGIN;UPDATE rr_mart.events_enriched SET available_value='1' WHERE itemid=30;"+query+'ROLLBACK;');assert_blocked(blocked)
        cases.append(dict(case='target_count_conflicting_tied_availability_noncanonical_value_future_expired_unknown_provenance_and_unmatched_nonnull_block',passed=True,subcases=8))
        try:
            for _ in expected_stream(ep,cp,ids,ec['observation_end_ms'],blank_stats(),histories.blank_interval_stats(),history_cap=2):pass
        except AssertionError as error:assert 'combined current-item history cap' in str(error)
        else:raise AssertionError('Combined property-history cap did not reject')
        cases.append(dict(case='combined_two_property_history_cap_aborts_without_filtering',passed=True))
        with (folder/PROPERTY_FILES[0]).open('a',encoding='utf-8',newline='') as stream:csv.writer(stream).writerow((0,2,'available','1'))
        invalid_db=folder/'invalid.duckdb'
        try:execute(folder,invalid_db,named_build(folder,7,9,len(ids)))
        except AssertionError as error:assert 'invalid_input' in str(error)
        else:raise AssertionError('Duplicate named observation key was accepted')
        existing,_=execute(folder,invalid_db,"SELECT COUNT(*) AS n FROM information_schema.tables WHERE table_schema='rr_private' AND table_name='item_state_observations';",readonly=True)
        assert existing==[{'n':0}]
        cases.append(dict(case='duplicate_named_observation_key_prevents_private_history_table_creation',passed=True))
    assert not folder.exists()
    with tempfile.TemporaryDirectory(prefix='rr-availability-empty-',dir=tmp_root) as temporary:
        parent_folder=Path(temporary)
        for label,rows in [
            ('one_recorded_bucket_zero_carts',[(5,1,'view',2,None),(5,1,'addtocart',2,None),(6,1,'transaction',2,0),(2*w,99,'addtocart',999,None)]),
            ('no_target_pairs',[(0,1,'view',50,None),(1,1,'addtocart',50,None),(2,1,'transaction',50,0),(2*w,99,'addtocart',999,None)])]:
            folder=parent_folder/label;folder.mkdir();database=folder/'fixture.duckdb'
            ep,ec,cp,cc,ids,wanted=fixture_source(folder,rows)
            execute(folder,database,named_build(folder,cc['categoryid_rows'],cc['available_rows'],len(ids)))
            execute(folder,database,fixture_events_sql(rows),enrichment=True)
            report,_=execute(folder,database,adjusted(sql,rows,len(ids),wanted),readonly=True)
            stats,interval_stats,_=compare_stream(folder,database,ep,cp,ids,ec['observation_end_ms'])
            assert report==reference_report(stats) and len(report)==5
            assert all(row['cart_to_transaction_rate_pct'] is None for row in report)
            if label=='one_recorded_bucket_zero_carts':
                assert report[0]['eligible_pairs']==1 and report[0]['eligible_share_pct']=='100.0000'
                assert all(row['eligible_share_pct']=='0.0000' and row['cart_rate_pct'] is None for row in report[1:-1])
            else:assert all(row['eligible_pairs']==0 and all(row[name] is None for name in OUTPUT[4:8]) for row in report)
        cases.append(dict(case='empty_buckets_zero_cart_and_empty_target_denominators_remain_explicit_NULL',passed=True,subcases=2))
    assert not parent_folder.exists()
    print(json.dumps({'fixture_families_passed':len(cases),'invalid_admission_subcases':8}),flush=True)
    if args.fixtures_only:return

    before={name:staging.snapshot(source_dir/name) for name in FILES}
    assert all(before[name]['sha256']==audit['files'][name]['sha256'] and before[name]['size_bytes']==audit['publisher_expected_bytes'][name] for name in FILES)
    historical={str(path.relative_to(root)):previous.sha256(path) for path in (root/'data').glob('*preflight.json') if path.resolve()!=output.resolve()}
    assert len(historical)==75
    with tempfile.TemporaryDirectory(prefix='rr-availability-real-',dir=tmp_root) as temporary:
        folder,database=Path(temporary),Path(temporary)/'preflight.duckdb'
        started=time.perf_counter();cp,category_counts=named_chunks(source_dir,folder);category_sort_seconds=round(time.perf_counter()-started,3)
        assert category_counts['raw_rows']==20275902 and category_counts['selected_rows']==2291853 and category_counts['categoryid_rows']==788214 and category_counts['available_rows']==1503639
        assert list(category_counts['raw_parts'].values())==[10999999,9275903]
        print(json.dumps({'phase':'both named histories source selection and sorting complete','selected_observations':2291853}),flush=True)
        started=time.perf_counter();ep,event_counts=event_chunks(source_dir/'events.csv',folder);event_sort_seconds=round(time.perf_counter()-started,3)
        assert event_counts==dict(rows=2756101,view=2664312,addtocart=69332,transaction=22457,null_transaction_ids=2733644,observation_end_ms=OBSERVATION_END_MS)
        ids=reference_ids(source_dir/'category_tree.csv');assert len(ids)==1669
        chunk_bytes=sum(path.stat().st_size for path in cp+ep)
        reference,category_build_seconds=execute(folder,database,named_build(source_dir,788214,1503639,1669)+'SELECT categoryid FROM rr_core.dim_category ORDER BY categoryid;')
        assert [row['categoryid'] for row in reference]==sorted(ids)
        print(json.dumps({'phase':1,'result':'both named intervals and complete reference-ID projection passed'}),flush=True)
        _,enrichment_seconds=execute(folder,database,'\n'.join(prefixes.values())+'\n'+ENRICHMENT,enrichment=True)
        print(json.dumps({'phase':2,'result':'two-property fifteen-field projection built'}),flush=True)
        database_before=previous.sha256(database)
        report,query_seconds=execute(folder,database,sql,readonly=True)
        assert [row['check_status'] for row in report]==['PASS']*5 and all(list(row)==OUTPUT for row in report)
        print(json.dumps({'phase':3,'result':'SQL77 five-row availability funnel passed'}),flush=True)
        stats,interval_stats,stream_seconds=compare_stream(folder,database,ep,cp,ids,event_counts['observation_end_ms'])
        assert report==reference_report(stats) and stats['rows']==2756101 and stats['duplicate_surplus']==460 and stats['eligible_pairs']==2042310 and stats['cart_pairs']==43147 and stats['transaction_pairs']==15520
        assert interval_stats['rows']==2291853 and stats['maximum_simultaneous_pair_states']==1
        assert [stats[label] for label in coverage.LABELS[:-1]]==[1527206,0,304405,210699]
        assert [stats[name] for name in ['selected_eligible_pairs','selected_cart_pairs','selected_transaction_pairs']]==[25105,483,76]
        assert [report[-1][name] for name in ['eligible_pairs','cart_pairs','transaction_pairs']]==[parent[name] for name in ['eligible_pairs','cart_pairs','transaction_pairs']]
        aggregate_counts={key:value for key,value in stats.items() if key!='availability_counts'}
        availability_counts=stats['availability_counts']
        database_after=previous.sha256(database);assert database_before==database_after
        database_bytes=database.stat().st_size
        private_category_build_hash=hashlib.sha256(named_build(source_dir,788214,1503639,1669).encode()).hexdigest()
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
        private_named_history_build_sha256=private_category_build_hash,private_two_property_enrichment_sha256=hashlib.sha256(ENRICHMENT.encode()).hexdigest(),
        projection_scope='Two-property fifteen-field disposable fact plus ID-only category reference. SQL69 full seventeen-field fact and SQL62 hierarchy remain supported by their accepted evidence and are not rebuilt or reverified.',
        source_table='rr_mart.events_enriched',readset_fields=FACT_FIELDS,required_readset_columns=15,
        reference_table='rr_core.dim_category',reference_readset_fields=['categoryid'],reference_ids_compared=1669,independent_reference_id_set_matched=True,
        full17_not_reverified=True,reference_hierarchy_not_reverified=True,property_files_read=True,category_csv_read=True,
        category_only_history_reconstructed=False,availability_history_reconstructed=True,named_property_histories_reconstructed=True,UTC_fields_read=False,
        SQL69_rerun=False,SQL62_hierarchy_rerun=False,SQL70_rerun=False,SQL71_rerun=False,SQL72_rerun=False,SQL73_rerun=False,SQL74_rerun=False,SQL75_rerun=False,SQL76_rerun=False,learner_database_opened=False,
        query_read_only=True,private_stream_read_only=True,real_source_attempts=1,real_cli_phases=4,
        real_named_history_build_executions=1,real_two_property_enrichment_executions=1,real_analysis_script_executions=1,real_private_stream_executions=1,
        report_rows=5,report_columns=9,output_columns=OUTPUT,checks_passed=5,fail_rows=0,blocked_rows=0,results=report,report_sha256=report_hash(report),
        report_fingerprint_contract='SHA-256 of compact JSON arrays in output-column order followed by LF; four-place DECIMAL shares are JSON strings, counts integers and undefined shares null.',
        independent_python_event_counts=event_counts,independent_python_named_property_counts=category_counts,
        independent_python_interval_counts=interval_stats,independent_python_aggregate_counts=aggregate_counts,independent_python_availability_counts=availability_counts,
        independent_python_report_matched=True,independent_python_Decimal_rates_matched=True,independent_one_pair_streaming_state=True,
        independent_stream_occurrences_compared=stats['rows'],independent_stream_fields_compared=15,independent_stream_all_occurrences_matched=True,
        independent_original_event_fields_and_duplicates_preserved=True,independent_category_values_bounds_provenance_statuses_matched=True,independent_availability_values_bounds_provenance_statuses_matched=True,
        selected_named_history_fully_drained=True,eligible_first_view_tie_consistency_verified=True,combined_category_availability_tie_consistency_verified=True,numeric_reference_lookup_preserves_original_text=True,
        target_categoryid=TARGET_CATEGORY,target_parent_counts_match_SQL74_SQL75_SQL76=True,no_all_item_aggregate_map=True,availability_aggregate_count=4,
        window_ms=WINDOW_MS,observation_end_ms=event_counts['observation_end_ms'],observation_end_utc=base.utc_text(event_counts['observation_end_ms']),
        eligibility_cutoff_ms=event_counts['observation_end_ms']-WINDOW_MS,eligibility_cutoff_utc=base.utc_text(event_counts['observation_end_ms']-WINDOW_MS),
        eligible_pairs=stats['eligible_pairs'],expected_eligible_pairs=2042310,coverage_partition_reconciled=True,global_flow_counts_reconciled=True,report_count_partition_reconciled=True,
        first_view_attribution_fixed_through_outcomes=True,shared_first_view_deadline_verified=True,strict_stage_order_verified=True,
        availability_first_view_attribution_fixed=True,pooled_rates_use_sum_transactions_over_sum_carts=True,
        maximum_simultaneous_pair_states=stats['maximum_simultaneous_pair_states'],maximum_current_item_history_rows=stats['maximum_current_item_history_rows'],
        private_database_sha256_before_readonly=database_before,private_database_sha256_after_readonly=database_after,private_database_bytes_unchanged=True,
        fixture_case_count=len(cases),fixture_cases=cases,invalid_admission_fixture_subcases=8,
        invalid_admission_blocks_all_metrics_verified=True,additional_unqueried_columns_allowed_verified=True,zero_denominator_NULLs_verified=True,
        preflight_settings=dict(threads=2,default_memory_limit='1GB',default_max_temp_directory_size='2GB',
            category_enrichment_memory_limit='2GB',category_enrichment_max_temp_directory_size='4GB',timeout_seconds_per_cli_phase=120,
            python_sort_chunk_rows=CHUNK_ROWS,current_item_history_row_cap=HISTORY_CAP,simultaneous_pair_state_budget=1,combined_property_history_row_cap=HISTORY_CAP,availability_aggregate_budget=4,
            minimum_free_bytes=8*1024**3,private_directory_budget_bytes=7*1024**3),
        private_event_comparison_chunks=len(ep),private_named_history_comparison_chunks=len(cp),private_comparison_chunk_bytes=chunk_bytes,
        private_database_bytes_before_cleanup=database_bytes,largest_private_directory_bytes_observed_after_phase=max(sizes),
        workspace_free_bytes_before=free_before,workspace_free_bytes_after=shutil.disk_usage(tmp_root).free,
        temporary_databases_and_spills_removed=True,private_source_comparison_spools_removed=True,
        historical_preflight_files_unchanged=len(historical),historical_comparison_or_analysis_suites_rerun=False,
        aggregate_category_ids_in_public_report=False,target_categoryid_published_as_aggregate_context=True,raw_item_ids_in_public_report=False,source_records_or_visitor_item_transaction_ids_published=False,raw_category_history_rows_published=False,raw_availability_history_rows_published=False,
        elapsed_python_named_history_scan_sort_seconds=category_sort_seconds,elapsed_python_event_scan_sort_seconds=event_sort_seconds,
        elapsed_named_history_build_seconds=category_build_seconds,elapsed_two_property_enrichment_seconds=enrichment_seconds,
        elapsed_readonly_availability_funnel_seconds=query_seconds,elapsed_private_stream_seconds=stream_seconds,
        timing_scope='Four CLI phases: both named histories/intervals and ID projection; frozen event prefixes plus two-property enrichment; read-only SQL77; read-only fifteen-field source comparison. Sorting timed separately; hashing and fixtures excluded.',
        scope='Assistant SQL77 passed; learner execution pending. Seven-day funnel by availability recorded at the first eligible view in fixed category 1613. Post-hoc descriptive diagnosis; recorded values are historical context, not verified inventory, availability throughout follow-up or a causal explanation. Missing history is retained. No UTC or category hierarchy rebuild.')
    output.write_text(json.dumps(evidence,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps({'report_rows':5,'checks_passed':5,'occurrences_compared':stats['rows'],'fields_compared':15,'report_sha256':evidence['report_sha256']}),flush=True)

if __name__=='__main__':main()
