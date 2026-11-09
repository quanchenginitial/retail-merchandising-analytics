"""Verify fixed first-view UTC cohorts with a bounded independent category-funnel fold."""
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

import preflight_retailrocket_category_7day_funnel as funnel

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
CONTRACT_SHA='37bc38da4693e6173afea477dedbca8090b53b4e2d981f1dc37587686dee8859'
COHORT_BOUNDARY_MS=1435708800000
COHORTS=['EARLY','LATE']
LABELS=['OTHER_MAPPED','UNKNOWN_REFERENCE','BEFORE_FIRST','NO_HISTORY','TOTAL']
OUTPUT=['cohort','segment','categoryid','eligible_pairs','cart_pairs','transaction_pairs','cart_rate_pct','transaction_rate_pct','cart_to_transaction_rate_pct','check_status']
FACT_FIELDS=coverage.FACT_FIELDS
PARAMETERS=funnel.PARAMETERS+',1435708800000::BIGINT AS cohort_boundary_ms'
ENRICHMENT=coverage.ENRICHMENT
STREAM=coverage.STREAM
literal=coverage.literal
category_build=coverage.category_build
event_chunks=coverage.event_chunks
merged_events=coverage.merged_events
category_chunks=coverage.category_chunks
reference_ids=coverage.reference_ids
fixture_events_sql=coverage.fixture_events_sql

def blank_stats():
    result=funnel.blank_stats()
    result.update(cohort_totals={name:[0,0,0] for name in COHORTS},maximum_aggregate_cells=0)
    return result

def expected_stream(event_paths,category_paths,ids,end_ms,stats,interval_stats,history_cap=HISTORY_CAP):
    source=iter(histories.expected_intervals(histories.merged_source(category_paths),interval_stats));pending=next(source,None)
    current_item=None;history=[];starts=[];current_pair=None;first_view=None;first_snapshot=None;cart_ms=None;transaction_ms=None;prior_event=None
    def close_pair():
        stats['observed_pairs']+=1
        if first_view is None:return
        stats['viewed_pairs']+=1
        if first_view+WINDOW_MS>end_ms:return
        stats['eligible_pairs']+=1
        status=first_snapshot[4]
        mapped=('MAPPED' if int(first_snapshot[0]) in ids else 'UNKNOWN_REFERENCE') if status=='MATCHED' else status
        assert mapped in coverage.LABELS[:-1];stats[mapped]+=1
        stats['cart_pairs']+=cart_ms is not None;stats['transaction_pairs']+=transaction_ms is not None
        key=int(first_snapshot[0]) if mapped=='MAPPED' else mapped
        cohort_index=0 if first_view<COHORT_BOUNDARY_MS else 1
        group=stats['groups'].setdefault(key,[[0,0,0],[0,0,0]])[cohort_index]
        group[0]+=1;group[1]+=cart_ms is not None;group[2]+=transaction_ms is not None
        cohort_total=stats['cohort_totals'][COHORTS[cohort_index]]
        cohort_total[0]+=1;cohort_total[1]+=cart_ms is not None;cohort_total[2]+=transaction_ms is not None
        stats['maximum_aggregate_cells']=max(stats['maximum_aggregate_cells'],2*len(stats['groups']))
        assert len(stats['groups'])<=len(ids)+3
        stats['maximum_aggregate_groups']=max(stats['maximum_aggregate_groups'],len(stats['groups']))
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
            current_pair=pair;first_view=None;first_snapshot=None;cart_ms=None;transaction_ms=None;stats['maximum_simultaneous_pair_states']=1
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

def reference_report(stats,top_n=10):
    groups=stats['groups']
    mapped=sorted((key for key in groups if isinstance(key,int)),key=lambda key:(-sum(cell[0] for cell in groups[key]),key))
    report=[]
    for ci,cohort in enumerate(COHORTS):
        rows=[('TOP_CATEGORY',key,groups[key][ci]) for key in mapped[:top_n]]
        rows.append(('OTHER_MAPPED',None,[sum(groups[key][ci][i] for key in mapped[top_n:]) for i in range(3)]))
        rows.extend((name,None,groups.get(name,[[0,0,0],[0,0,0]])[ci]) for name in LABELS[1:-1])
        rows.append(('TOTAL',None,stats['cohort_totals'][cohort]))
        cohort_report=[]
        for label,category,counts in rows:
            eligible,carts,transactions=counts;assert eligible>=carts>=transactions
            cohort_report.append(dict(zip(OUTPUT,[cohort,label,category,eligible,carts,transactions,funnel.rate(carts,eligible),funnel.rate(transactions,eligible),funnel.rate(transactions,carts),'PASS'])))
        assert all(sum(row[field] for row in cohort_report[:-1])==cohort_report[-1][field] for field in ['eligible_pairs','cart_pairs','transaction_pairs'])
        report.extend(cohort_report)
    assert len(report)==2*(min(top_n,len(mapped))+5)
    return report

def global_reference_report(stats,top_n=10):
    report=reference_report(stats,top_n);half=len(report)//2;result=[]
    for early,late in zip(report[:half],report[half:]):
        assert early['segment']==late['segment'] and early['categoryid']==late['categoryid']
        eligible,carts,transactions=[early[field]+late[field] for field in ['eligible_pairs','cart_pairs','transaction_pairs']]
        result.append(dict(zip(funnel.OUTPUT,[early['segment'],early['categoryid'],eligible,carts,transactions,funnel.rate(carts,eligible),funnel.rate(transactions,eligible),funnel.rate(transactions,carts),'PASS'])))
    assert [result[-1][field] for field in ['eligible_pairs','cart_pairs','transaction_pairs']]==[stats['eligible_pairs'],stats['cart_pairs'],stats['transaction_pairs']]
    return result

def expected_values(report):
    def value(v):return 'NULL::BIGINT' if v is None else literal(v) if isinstance(v,str) else str(v)
    return ',\n    '.join('('+','.join(value(row[name]) for name in ['segment','categoryid','eligible_pairs','cart_pairs','transaction_pairs'])+')' for row in report)

def replace_expected(sql,report):
    before,tail=sql.split('-- EXPECTED SQL74 COUNTS BEGIN\n',1)
    _,after=tail.split('\n-- EXPECTED SQL74 COUNTS END',1)
    return before+'-- EXPECTED SQL74 COUNTS BEGIN\n'+expected_values(report)+'\n-- EXPECTED SQL74 COUNTS END'+after

def report_hash(report):
    return hashlib.sha256(''.join(json.dumps([row[name] for name in OUTPUT],separators=(',',':'))+'\n' for row in report).encode()).hexdigest()

def adjusted(sql,event_rows,reference_count,stats,top_n=10,override=None):
    counts=Counter(row[2] for row in event_rows);end=max(row[0] for row in event_rows)
    values=dict(expected_rows=len(event_rows),expected_views=counts['view'],expected_carts=counts['addtocart'],expected_transactions=counts['transaction'],
        expected_duplicate_surplus=len(event_rows)-len(set(event_rows)),max_supported_ms=MAX_MS,window_ms=WINDOW_MS,
        expected_observation_end_ms=end,expected_eligible_pairs=stats['eligible_pairs'],expected_reference_ids=reference_count,
        expected_mapped_pairs=stats['MAPPED'],expected_unknown_reference_pairs=stats['UNKNOWN_REFERENCE'],expected_before_first_pairs=stats['BEFORE_FIRST'],
        expected_no_history_pairs=stats['NO_HISTORY'],expected_cart_pairs=stats['cart_pairs'],expected_transaction_pairs=stats['transaction_pairs'],top_n=top_n,cohort_boundary_ms=COHORT_BOUNDARY_MS)
    values.update(override or {});assert sql.count(PARAMETERS)==1
    sql=sql.replace(PARAMETERS,'SELECT '+','.join(f'{value}::BIGINT AS {name}' for name,value in values.items()))
    return replace_expected(sql,global_reference_report(stats,top_n))

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--duckdb',required=True);parser.add_argument('--output',required=True);parser.add_argument('--fixtures-only',action='store_true');args=parser.parse_args()
    root=Path(__file__).resolve().parents[1];output=(root/args.output).resolve()
    assert output.is_relative_to((root/'data').resolve())
    script_path='sql/75_analyze_retailrocket_category_funnel_time_cohorts.sql'
    validator_path='validation/preflight_retailrocket_category_funnel_time_cohorts.py'
    method_path='docs/RETAILROCKET_CATEGORY_FUNNEL_TIME_COHORTS_VALIDATION.md'
    dependencies=[script_path,validator_path,'validation/preflight_retailrocket_category_7day_funnel.py','validation/preflight_retailrocket_first_view_category_coverage.py','sql/54_import_retailrocket_events.sql','sql/63_stage_retailrocket_events.sql',
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
        'docs/RETAILROCKET_CATEGORY_7DAY_FUNNEL_VALIDATION.md']
    hashes={name:previous.sha256(root/name) for name in dependencies}
    contract=(root/method_path).read_bytes().split(b'\n## Executed results\n',1)[0]
    assert hashlib.sha256(contract).hexdigest()==CONTRACT_SHA
    for stem,script in [('category_dimension','sql/62_build_retailrocket_category_dimension.sql'),
                        ('events_enriched','sql/69_build_retailrocket_events_enriched.sql'),
                        ('7day_visitor_item_funnel','sql/72_analyze_retailrocket_7day_visitor_item_funnel.sql'),
                        ('first_view_category_coverage','sql/73_audit_retailrocket_first_view_category_coverage.sql'),
                        ('category_7day_funnel','sql/74_analyze_retailrocket_category_7day_funnel.sql')]:
        old=json.loads((root/f'data/retailrocket_{stem}_preflight.json').read_text(encoding='utf-8'))
        accepted=json.loads((root/f'data/retailrocket_{stem}_learner_acceptance.json').read_text(encoding='utf-8'))
        assert accepted['acceptance_status'].startswith('accepted') and accepted['report_sha256']==old['report_sha256']
        assert old['script_sha256']==hashes[script]
    baseline=old
    old_coverage=json.loads((root/'data/retailrocket_first_view_category_coverage_preflight.json').read_text(encoding='utf-8'))
    assert [row['eligible_pairs'] for row in old_coverage['results']]==[1527206,0,304405,210699,2042310]
    overall_funnel=json.loads((root/'data/retailrocket_7day_visitor_item_funnel_preflight.json').read_text(encoding='utf-8'))
    assert [row['visitor_item_pairs'] for row in overall_funnel['results']][-3:]==[2042310,43147,15520]
    sql=(root/script_path).read_text(encoding='utf-8')
    assert sql.split('-- EXPECTED SQL74 COUNTS BEGIN\n',1)[1].split('\n-- EXPECTED SQL74 COUNTS END',1)[0]==expected_values(baseline['results'])
    delta=datetime(2015,7,1,tzinfo=timezone.utc)-datetime(1970,1,1,tzinfo=timezone.utc)
    assert (delta.days*86400+delta.seconds)*1000+delta.microseconds//1000==COHORT_BOUNDARY_MS
    clean=re.sub(r'--[^\n]*','',sql)
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
            raise AssertionError('Private category time-cohort CLI failure: '+category+'; row-bearing details withheld')
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

    w,b=WINDOW_MS,COHORT_BOUNDARY_MS
    fixture_rows=[
        (b-1,2,'view',2,None),(b,2,'addtocart',2,None),(b+1,2,'transaction',2,0),
        (b-2,3,'view',2,None),(b-2,3,'addtocart',2,None),(b-1,3,'transaction',2,1),
        (b-3,4,'view',2,None),(b+w-4,4,'addtocart',2,None),(b+w-3,4,'transaction',2,2),
        (b,10,'view',10,None),(b,10,'view',10,None),(b+1,10,'addtocart',10,None),(b+2,10,'transaction',10,3),
        (b+1,11,'view',10,None),(b+1,11,'addtocart',10,None),(b+2,11,'addtocart',10,None),(b+2,11,'transaction',10,4),
        (b+2,20,'view',20,None),(b+w+2,20,'addtocart',20,None),(b+w+3,20,'transaction',20,5),
        (b-4,40,'view',40,None),(b-3,40,'addtocart',40,None),(b-2,40,'transaction',40,6),
        (b+3,50,'view',50,None),(b+11,50,'addtocart',50,None),(b+12,50,'transaction',50,7),
        (b-5,60,'view',60,None),(b-4,60,'addtocart',60,None),(b-3,60,'transaction',60,8),
        (b+w+1,70,'view',70,None),(b+w+2,70,'addtocart',70,None),(b+w+3,70,'transaction',70,9),
        (b+2*w,99,'transaction',99,10)]
    properties=[(b-20,2,'categoryid','001',PROPERTY_FILES[0]),(b,2,'categoryid','2',PROPERTY_FILES[1]),
        (b-20,10,'categoryid','2',PROPERTY_FILES[0]),(b-20,20,'categoryid','10',PROPERTY_FILES[1]),
        (b-20,40,'categoryid','999',PROPERTY_FILES[1]),(b+10,50,'categoryid','2',PROPERTY_FILES[0]),
        (b-20,70,'categoryid','1',PROPERTY_FILES[1])]
    cases=[]
    def fixture_source(folder,rows):
        for name in PROPERTY_FILES:
            with (folder/name).open('w',encoding='utf-8',newline='') as stream:
                writer=csv.writer(stream);writer.writerow(['timestamp','itemid','property','value']);writer.writerows(row[:4] for row in reversed(properties) if row[4]==name)
        with (folder/'category_tree.csv').open('w',encoding='utf-8',newline='') as stream:
            writer=csv.writer(stream);writer.writerow(['categoryid','parentid']);writer.writerows((value,'') for value in [1,2,10])
        with (folder/'events.csv').open('w',encoding='utf-8',newline='') as stream:
            writer=csv.writer(stream);writer.writerow(staging.FIELDS);writer.writerows(reversed(rows))
        ep,ec=event_chunks(folder/'events.csv',folder,3);cp,cc=category_chunks(folder,folder,2);ids=reference_ids(folder/'category_tree.csv')
        stats=blank_stats()
        for _ in expected_stream(ep,cp,ids,ec['observation_end_ms'],stats,histories.blank_interval_stats()):pass
        return ep,ec,cp,cc,ids,stats
    with tempfile.TemporaryDirectory(prefix='rr-time-cohort-fixture-',dir=tmp_root) as temporary:
        folder,database=Path(temporary),Path(temporary)/'fixture.duckdb'
        ep,ec,cp,cc,ids,wanted=fixture_source(folder,fixture_rows)
        reference,_=execute(folder,database,category_build(folder,len(properties),len(ids))+'SELECT categoryid FROM rr_core.dim_category ORDER BY categoryid;')
        assert [row['categoryid'] for row in reference]==sorted(ids)
        execute(folder,database,fixture_events_sql(fixture_rows)+'ALTER TABLE rr_mart.events_enriched ADD COLUMN unqueried_fixture VARCHAR;',enrichment=True)
        query=adjusted(sql,fixture_rows,len(ids),wanted,top_n=1)
        before_db=previous.sha256(database)
        report,_=execute(folder,database,query,readonly=True)
        stats,interval_stats,_=compare_stream(folder,database,ep,cp,ids,ec['observation_end_ms'])
        assert report==reference_report(stats,1) and stats==wanted and previous.sha256(database)==before_db
        assert len(report)==12 and [row['categoryid'] for row in report if row['segment']=='TOP_CATEGORY']==[1,1]
        assert [row['eligible_pairs'] for row in report if row['segment']=='TOP_CATEGORY']==[3,0]
        assert [row['eligible_pairs'] for row in report if row['segment']=='OTHER_MAPPED']==[0,3]
        assert stats['cohort_totals']=={'EARLY':[5,4,4],'LATE':[4,4,2]}
        assert [stats[name] for name in ['eligible_pairs','cart_pairs','transaction_pairs']]==[9,8,6]
        assert stats['duplicate_surplus']==1 and interval_stats['rows']==7
        assert report[0]['transaction_pairs']==2 and report[6]['eligible_pairs']==0
        assert all(report[6][name] is None for name in OUTPUT[6:9])
        assert global_reference_report(stats,1)[0]['categoryid']==1
        cases.append(dict(case='exact_UTC_boundary_cross_boundary_followup_fixed_global_label_despite_local_rank_shared_deadline_and_ties',passed=True,
            event_rows=len(fixture_rows),category_rows=len(properties),top_n=1,expected_cohort_counts={'EARLY':[5,4,4],'LATE':[4,4,2]},
            expected_TOP_category_ids_both_cohorts=[1,1],expected_TOP_eligible_counts=[3,0],expected_OTHER_eligible_counts=[0,3],complete_readset_fields=10))
        def assert_blocked(rows):
            assert [(row['cohort'],row['segment']) for row in rows]==[(cohort,label) for cohort in COHORTS for label in LABELS]
            assert all(row['categoryid'] is None and row['check_status']=='BLOCKED' and all(row[name] is None for name in OUTPUT[3:-1]) for row in rows)
        blocked,_=execute(folder,database,adjusted(sql,fixture_rows,len(ids),wanted,top_n=1,override={'cohort_boundary_ms':b+1}),readonly=True);assert_blocked(blocked)
        wrong=global_reference_report(stats,1)
        wrong[0]['cart_pairs']+=1;wrong[1]['cart_pairs']-=1
        assert sum(row['cart_pairs'] for row in wrong[:-1])==wrong[-1]['cart_pairs']
        blocked,_=execute(folder,database,replace_expected(query,wrong),readonly=True);assert_blocked(blocked)
        one=f"rowid=(SELECT MIN(rowid) FROM rr_mart.events_enriched WHERE timestamp={b} AND visitorid=10 AND itemid=10 AND event='view')"
        blocked,_=execute(folder,database,'BEGIN;UPDATE rr_mart.events_enriched SET categoryid_value=\'1\' WHERE '+one+';'+query+'ROLLBACK;');assert_blocked(blocked)
        cases.append(dict(case='wrong_split_wrong_per_group_contract_with_unchanged_grand_total_and_conflicting_first_view_block_TOP_release',passed=True,subcases=3))
    assert not folder.exists()
    with tempfile.TemporaryDirectory(prefix='rr-time-cohort-empty-',dir=tmp_root) as temporary:
        parent=Path(temporary)
        for label,rows in [
            ('empty_LATE',[(b-10,1,'view',2,None),(b-9,1,'addtocart',2,None),(b-8,1,'transaction',2,0),(b+2*w,99,'transaction',99,1)]),
            ('zero_eligible',[(b+w+1,1,'view',2,None),(b+2*w,99,'transaction',99,0)])]:
            folder=parent/label;folder.mkdir();database=folder/'fixture.duckdb'
            ep,ec,cp,cc,ids,wanted=fixture_source(folder,rows)
            execute(folder,database,category_build(folder,len(properties),len(ids)))
            execute(folder,database,fixture_events_sql(rows),enrichment=True)
            report,_=execute(folder,database,adjusted(sql,rows,len(ids),wanted),readonly=True)
            stats,interval_stats,_=compare_stream(folder,database,ep,cp,ids,ec['observation_end_ms'])
            assert report==reference_report(stats)
            empty=[row for row in report if row['cohort']=='LATE'] if label=='empty_LATE' else report
            assert all(row['eligible_pairs']==0 and all(row[name] is None for name in OUTPUT[6:9]) for row in empty)
            if label=='empty_LATE':assert len(report)==12 and empty[0]['categoryid']==1
            else:assert len(report)==10
        cases.append(dict(case='empty_cohort_keeps_global_TOP_labels_and_zero_eligible_keeps_ten_aggregate_rows_with_NULL_rates',passed=True,subcases=2))
    assert not parent.exists()
    print(json.dumps({'fixture_families_passed':len(cases),'invalid_admission_subcases':3}),flush=True)
    if args.fixtures_only:return

    before={name:staging.snapshot(source_dir/name) for name in FILES}
    assert all(before[name]['sha256']==audit['files'][name]['sha256'] and before[name]['size_bytes']==audit['publisher_expected_bytes'][name] for name in FILES)
    historical={str(path.relative_to(root)):previous.sha256(path) for path in (root/'data').glob('*preflight.json') if path.resolve()!=output.resolve()}
    assert len(historical)==73
    with tempfile.TemporaryDirectory(prefix='rr-time-cohort-real-',dir=tmp_root) as temporary:
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
        assert [row['check_status'] for row in report]==['PASS']*30 and all(list(row)==OUTPUT for row in report)
        print(json.dumps({'phase':3,'result':'SQL75 thirty-row time-cohort funnel passed'}),flush=True)
        stats,interval_stats,stream_seconds=compare_stream(folder,database,ep,cp,ids,event_counts['observation_end_ms'])
        assert report==reference_report(stats) and stats['rows']==2756101 and stats['duplicate_surplus']==460 and stats['eligible_pairs']==2042310 and stats['cart_pairs']==43147 and stats['transaction_pairs']==15520
        assert interval_stats['rows']==788214 and stats['maximum_simultaneous_pair_states']==1
        assert [stats[label] for label in coverage.LABELS[:-1]]==[1527206,0,304405,210699]
        assert global_reference_report(stats)==baseline['results']
        fixed_top_ids=[row['categoryid'] for row in baseline['results'] if row['segment']=='TOP_CATEGORY']
        assert all([row['categoryid'] for row in report if row['cohort']==cohort and row['segment']=='TOP_CATEGORY']==fixed_top_ids for cohort in COHORTS)
        aggregate_counts={key:value for key,value in stats.items() if key not in {'groups','cohort_totals'}}
        aggregate_counts['mapped_category_groups']=sum(isinstance(key,int) for key in stats['groups'])
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
        SQL69_rerun=False,SQL62_hierarchy_rerun=False,SQL70_rerun=False,SQL71_rerun=False,SQL72_rerun=False,SQL73_rerun=False,SQL74_rerun=False,learner_database_opened=False,
        query_read_only=True,private_stream_read_only=True,real_source_attempts=1,real_cli_phases=4,
        real_category_build_executions=1,real_category_enrichment_executions=1,real_analysis_script_executions=1,real_private_stream_executions=1,
        report_rows=30,report_columns=10,output_columns=OUTPUT,checks_passed=30,fail_rows=0,blocked_rows=0,results=report,report_sha256=report_hash(report),
        report_fingerprint_contract='SHA-256 of compact JSON arrays in output-column order followed by LF; four-place DECIMAL shares are JSON strings, counts integers and undefined shares null.',
        independent_python_event_counts=event_counts,independent_python_category_counts=category_counts,
        independent_python_interval_counts=interval_stats,independent_python_aggregate_counts=aggregate_counts,independent_python_cohort_aggregate_counts=stats['cohort_totals'],
        independent_python_report_matched=True,independent_python_Decimal_rates_matched=True,independent_one_pair_streaming_state=True,
        independent_stream_occurrences_compared=stats['rows'],independent_stream_fields_compared=10,independent_stream_all_occurrences_matched=True,
        independent_original_event_fields_and_duplicates_preserved=True,independent_category_values_bounds_provenance_statuses_matched=True,
        selected_category_history_fully_drained=True,eligible_first_view_tie_consistency_verified=True,numeric_reference_lookup_preserves_original_text=True,
        cohort_boundary_ms=COHORT_BOUNDARY_MS,cohort_boundary_utc=base.utc_text(COHORT_BOUNDARY_MS),cohort_labels=COHORTS,
        fixed_global_category_labels=fixed_top_ids,independent_per_cohort_report_matched=True,across_cohort_group_counts_match_SQL74=True,
        cohort_assignment_uses_first_view_only=True,cross_boundary_followup_preserved=True,no_within_cohort_reranking=True,
        window_ms=WINDOW_MS,observation_end_ms=event_counts['observation_end_ms'],observation_end_utc=base.utc_text(event_counts['observation_end_ms']),
        eligibility_cutoff_ms=event_counts['observation_end_ms']-WINDOW_MS,eligibility_cutoff_utc=base.utc_text(event_counts['observation_end_ms']-WINDOW_MS),
        eligible_pairs=stats['eligible_pairs'],expected_eligible_pairs=2042310,coverage_partition_reconciled=True,global_flow_counts_reconciled=True,report_count_partition_reconciled=True,
        first_view_attribution_fixed_through_outcomes=True,shared_first_view_deadline_verified=True,strict_stage_order_verified=True,
        TOP_selection_uses_population_not_outcomes=True,OTHER_and_TOTAL_rates_recomputed_from_counts=True,
        maximum_simultaneous_pair_states=stats['maximum_simultaneous_pair_states'],maximum_current_item_history_rows=stats['maximum_current_item_history_rows'],
        private_database_sha256_before_readonly=database_before,private_database_sha256_after_readonly=database_after,private_database_bytes_unchanged=True,
        fixture_case_count=len(cases),fixture_cases=cases,invalid_admission_fixture_subcases=3,
        invalid_admission_blocks_all_metrics_verified=True,additional_unqueried_columns_allowed_verified=True,zero_denominator_NULLs_verified=True,
        preflight_settings=dict(threads=2,default_memory_limit='1GB',default_max_temp_directory_size='2GB',
            category_enrichment_memory_limit='2GB',category_enrichment_max_temp_directory_size='4GB',timeout_seconds_per_cli_phase=120,
            python_sort_chunk_rows=CHUNK_ROWS,current_item_history_row_cap=HISTORY_CAP,simultaneous_pair_state_budget=1,category_aggregate_group_budget=1672,category_cohort_counter_cell_budget=3344,
            minimum_free_bytes=8*1024**3,private_directory_budget_bytes=7*1024**3),
        private_event_comparison_chunks=len(ep),private_category_comparison_chunks=len(cp),private_comparison_chunk_bytes=chunk_bytes,
        private_database_bytes_before_cleanup=database_bytes,largest_private_directory_bytes_observed_after_phase=max(sizes),
        workspace_free_bytes_before=free_before,workspace_free_bytes_after=shutil.disk_usage(tmp_root).free,
        temporary_databases_and_spills_removed=True,private_source_comparison_spools_removed=True,
        historical_preflight_files_unchanged=len(historical),historical_comparison_or_analysis_suites_rerun=False,
        aggregate_category_ids_in_public_report=True,source_records_or_visitor_item_transaction_ids_published=False,raw_category_history_rows_published=False,
        elapsed_python_category_scan_sort_seconds=category_sort_seconds,elapsed_python_event_scan_sort_seconds=event_sort_seconds,
        elapsed_category_build_seconds=category_build_seconds,elapsed_category_enrichment_seconds=enrichment_seconds,
        elapsed_readonly_time_cohort_funnel_seconds=query_seconds,elapsed_private_stream_seconds=stream_seconds,
        timing_scope='Four CLI phases: category-only import/intervals and ID projection; frozen event prefixes plus category-only enrichment; read-only SQL75; read-only ten-field source comparison. Sorting timed separately; hashing and fixtures excluded.',
        scope='Assistant SQL75 passed; learner execution pending. Two fixed first-view UTC cohorts retain global SQL74 category labels and original seven-day follow-up across the split; every across-cohort group count reconciles to SQL74. Unequal retrospective calendar blocks are descriptive, not seasonality, statistical or causal proof, predictive validation, people/order/session conversion.')
    output.write_text(json.dumps(evidence,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps({'report_rows':30,'checks_passed':30,'occurrences_compared':stats['rows'],'fields_compared':10,'report_sha256':evidence['report_sha256']}),flush=True)

if __name__=='__main__':main()
