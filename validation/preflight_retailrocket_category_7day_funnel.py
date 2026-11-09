"""Verify the seven-day category funnel through a bounded independent source fold."""
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

import preflight_retailrocket_first_view_category_coverage as coverage

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
CONTRACT_SHA='02fd845c6842d8f2d21211ea502df7baef6c2b29f5520f5cd2c8fa38558387a3'
LABELS=['OTHER_MAPPED','UNKNOWN_REFERENCE','BEFORE_FIRST','NO_HISTORY','TOTAL']
OUTPUT=['segment','categoryid','eligible_pairs','cart_pairs','transaction_pairs','cart_rate_pct','transaction_rate_pct','cart_to_transaction_rate_pct','check_status']
FACT_FIELDS=coverage.FACT_FIELDS
PARAMETERS=coverage.PARAMETERS+",\n        1527206::BIGINT AS expected_mapped_pairs,0::BIGINT AS expected_unknown_reference_pairs,\n        304405::BIGINT AS expected_before_first_pairs,210699::BIGINT AS expected_no_history_pairs,\n        43147::BIGINT AS expected_cart_pairs,15520::BIGINT AS expected_transaction_pairs,10::BIGINT AS top_n"
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
    result=coverage.blank_stats()
    result.update(cart_pairs=0,transaction_pairs=0,groups={},maximum_aggregate_groups=0)
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
        group=stats['groups'].setdefault(key,[0,0,0]);group[0]+=1;group[1]+=cart_ms is not None;group[2]+=transaction_ms is not None
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

def rate(numerator,denominator):
    return None if denominator==0 else format((Decimal(numerator)*100/Decimal(denominator)).quantize(Decimal('0.0001'),rounding=ROUND_HALF_UP),'.4f')

def reference_report(stats,top_n=10):
    groups=stats['groups'];mapped=sorted((key for key in groups if isinstance(key,int)),key=lambda key:(-groups[key][0],key))
    rows=[('TOP_CATEGORY',key,groups[key]) for key in mapped[:top_n]]
    remainder=[sum(groups[key][i] for key in mapped[top_n:]) for i in range(3)]
    rows.append(('OTHER_MAPPED',None,remainder))
    rows.extend((name,None,groups.get(name,[0,0,0])) for name in LABELS[1:-1])
    rows.append(('TOTAL',None,[stats['eligible_pairs'],stats['cart_pairs'],stats['transaction_pairs']]))
    report=[]
    for label,category,counts in rows:
        eligible,carts,transactions=counts;assert eligible>=carts>=transactions
        report.append(dict(zip(OUTPUT,[label,category,eligible,carts,transactions,rate(carts,eligible),rate(transactions,eligible),rate(transactions,carts),'PASS'])))
    assert all(sum(row[field] for row in report[:-1])==report[-1][field] for field in ['eligible_pairs','cart_pairs','transaction_pairs'])
    return report

def report_hash(report):
    return hashlib.sha256(''.join(json.dumps([row[name] for name in OUTPUT],separators=(',',':'))+'\n' for row in report).encode()).hexdigest()

def adjusted(sql,event_rows,reference_count,stats,top_n=10,override=None):
    counts=Counter(row[2] for row in event_rows);end=max(row[0] for row in event_rows)
    values=dict(expected_rows=len(event_rows),expected_views=counts['view'],expected_carts=counts['addtocart'],expected_transactions=counts['transaction'],
        expected_duplicate_surplus=len(event_rows)-len(set(event_rows)),max_supported_ms=MAX_MS,window_ms=WINDOW_MS,
        expected_observation_end_ms=end,expected_eligible_pairs=stats['eligible_pairs'],expected_reference_ids=reference_count,
        expected_mapped_pairs=stats['MAPPED'],expected_unknown_reference_pairs=stats['UNKNOWN_REFERENCE'],expected_before_first_pairs=stats['BEFORE_FIRST'],
        expected_no_history_pairs=stats['NO_HISTORY'],expected_cart_pairs=stats['cart_pairs'],expected_transaction_pairs=stats['transaction_pairs'],top_n=top_n)
    values.update(override or {});assert sql.count(PARAMETERS)==1
    return sql.replace(PARAMETERS,'SELECT '+','.join(f'{value}::BIGINT AS {name}' for name,value in values.items()))

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--duckdb',required=True);parser.add_argument('--output',required=True);parser.add_argument('--fixtures-only',action='store_true');args=parser.parse_args()
    root=Path(__file__).resolve().parents[1];output=(root/args.output).resolve()
    assert output.is_relative_to((root/'data').resolve())
    script_path='sql/74_analyze_retailrocket_category_7day_funnel.sql'
    validator_path='validation/preflight_retailrocket_category_7day_funnel.py'
    method_path='docs/RETAILROCKET_CATEGORY_7DAY_FUNNEL_VALIDATION.md'
    dependencies=[script_path,validator_path,'validation/preflight_retailrocket_first_view_category_coverage.py','sql/54_import_retailrocket_events.sql','sql/63_stage_retailrocket_events.sql',
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
        'docs/RETAILROCKET_FIRST_VIEW_CATEGORY_COVERAGE_VALIDATION.md']
    hashes={name:previous.sha256(root/name) for name in dependencies}
    contract=(root/method_path).read_bytes().split(b'\n## Executed results\n',1)[0]
    assert hashlib.sha256(contract).hexdigest()==CONTRACT_SHA
    for stem,script in [('category_dimension','sql/62_build_retailrocket_category_dimension.sql'),
                        ('events_enriched','sql/69_build_retailrocket_events_enriched.sql'),
                        ('7day_visitor_item_funnel','sql/72_analyze_retailrocket_7day_visitor_item_funnel.sql'),
                        ('first_view_category_coverage','sql/73_audit_retailrocket_first_view_category_coverage.sql')]:
        old=json.loads((root/f'data/retailrocket_{stem}_preflight.json').read_text(encoding='utf-8'))
        accepted=json.loads((root/f'data/retailrocket_{stem}_learner_acceptance.json').read_text(encoding='utf-8'))
        assert accepted['acceptance_status'].startswith('accepted') and accepted['report_sha256']==old['report_sha256']
        assert old['script_sha256']==hashes[script]
    assert [row['eligible_pairs'] for row in old['results']]==[1527206,0,304405,210699,2042310]
    funnel=json.loads((root/'data/retailrocket_7day_visitor_item_funnel_preflight.json').read_text(encoding='utf-8'))
    assert [row['visitor_item_pairs'] for row in funnel['results']][-3:]==[2042310,43147,15520]
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
            raise AssertionError('Private category-funnel CLI failure: '+category+'; row-bearing details withheld')
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
    fixture_rows=[
        (5,2,'view',2,None),(5,2,'view',2,None),(11,2,'addtocart',2,None),(12,2,'transaction',2,0),
        (0,3,'view',2,None),(w-1,3,'addtocart',2,None),(w,3,'transaction',2,1),
        (0,10,'view',10,None),(w,10,'addtocart',10,None),(w+1,10,'transaction',10,2),
        (0,11,'view',10,None),(0,11,'addtocart',10,None),(1,11,'transaction',10,3),
        (0,20,'view',20,None),(1,20,'addtocart',20,None),(2,20,'transaction',20,4),
        (0,21,'view',20,None),(1,21,'addtocart',20,None),(1,21,'transaction',20,5),
        (0,30,'view',30,None),
        (6,40,'view',40,None),(7,40,'addtocart',40,None),(8,40,'transaction',40,6),
        (5,50,'view',50,None),(10,50,'addtocart',50,None),(11,50,'transaction',50,7),
        (0,60,'view',60,None),(1,60,'addtocart',60,None),(2,60,'transaction',60,8),
        (w+1,70,'view',70,None),(w+2,70,'addtocart',70,None),(w+3,70,'transaction',70,9),
        (2*w,99,'transaction',99,10)]
    properties=[(0,2,'categoryid','001',PROPERTY_FILES[0]),(10,2,'categoryid','2',PROPERTY_FILES[1]),
        (0,10,'categoryid','2',PROPERTY_FILES[0]),(0,20,'categoryid','10',PROPERTY_FILES[1]),
        (0,30,'categoryid','20',PROPERTY_FILES[0]),(5,40,'categoryid','999',PROPERTY_FILES[1]),
        (10,50,'categoryid','2',PROPERTY_FILES[0]),(0,70,'categoryid','1',PROPERTY_FILES[1])]
    cases=[]
    def fixture_source(folder,rows,props=properties,ids=(1,2,10,20)):
        for name in PROPERTY_FILES:
            with (folder/name).open('w',encoding='utf-8',newline='') as stream:
                writer=csv.writer(stream);writer.writerow(['timestamp','itemid','property','value'])
                writer.writerows(row[:4] for row in reversed(props) if row[4]==name)
                writer.writerow((1,2,'available','1'));writer.writerow((1,2,'opaque','x'))
        with (folder/'category_tree.csv').open('w',encoding='utf-8',newline='') as stream:
            writer=csv.writer(stream);writer.writerow(['categoryid','parentid']);writer.writerows((value,'') for value in ids)
        with (folder/'events.csv').open('w',encoding='utf-8',newline='') as stream:
            writer=csv.writer(stream);writer.writerow(staging.FIELDS);writer.writerows(reversed(rows))
        ep,ec=event_chunks(folder/'events.csv',folder,3);cp,cc=category_chunks(folder,folder,2);refs=reference_ids(folder/'category_tree.csv')
        stats=blank_stats();interval_stats=histories.blank_interval_stats()
        for _ in expected_stream(ep,cp,refs,ec['observation_end_ms'],stats,interval_stats):pass
        return ep,ec,cp,cc,refs,stats
    with tempfile.TemporaryDirectory(prefix='rr-category-funnel-fixture-',dir=tmp_root) as temporary:
        folder,database=Path(temporary),Path(temporary)/'fixture.duckdb'
        ep,ec,cp,cc,ids,wanted_stats=fixture_source(folder,fixture_rows)
        reference,_=execute(folder,database,category_build(folder,len(properties),len(ids))+'SELECT categoryid FROM rr_core.dim_category ORDER BY categoryid;')
        assert [row['categoryid'] for row in reference]==sorted(ids)
        execute(folder,database,fixture_events_sql(fixture_rows)+'ALTER TABLE rr_mart.events_enriched ADD COLUMN unqueried_fixture VARCHAR;',enrichment=True)
        before_db=previous.sha256(database)
        report,_=execute(folder,database,adjusted(sql,fixture_rows,len(ids),wanted_stats,top_n=2),readonly=True)
        stats,interval_stats,_=compare_stream(folder,database,ep,cp,ids,ec['observation_end_ms'])
        assert report==reference_report(stats,2) and stats==wanted_stats
        assert [row['categoryid'] for row in report[:2]]==[1,2]
        assert [[row[field] for field in ['eligible_pairs','cart_pairs','transaction_pairs']] for row in report]==[[2,2,2],[2,1,0],[3,2,1],[1,1,1],[1,1,1],[1,1,1],[10,8,6]]
        assert [report[2][field] for field in OUTPUT[5:8]]==['66.6667','33.3333','50.0000']
        assert [report[-1][field] for field in OUTPUT[5:8]]==['80.0000','60.0000','75.0000']
        assert previous.sha256(database)==before_db and stats['duplicate_surplus']==1 and stats['maximum_simultaneous_pair_states']==1
        assert stats['maximum_current_item_history_rows']==2 and interval_stats['rows']==8 and stats['viewed_pairs']==11
        full,_=execute(folder,database,adjusted(sql,fixture_rows,len(ids),wanted_stats),readonly=True)
        assert full==reference_report(stats) and len(full)==9
        other=next(row for row in full if row['segment']=='OTHER_MAPPED')
        assert other['eligible_pairs']==0 and all(other[field] is None for field in OUTPUT[5:8])
        cases.append(dict(case='first_view_attribution_stays_fixed_shared_deadline_ties_population_rank_numeric_tie_OTHER_count_aggregation',passed=True,
            event_rows=len(fixture_rows),category_rows=len(properties),top_n=2,expected_top_category_ids=[1,2],expected_total_counts=[10,8,6],
            expected_other_counts=[3,2,1],complete_readset_fields=10,extra_unqueried_column_allowed=True,empty_OTHER_rates_NULL=True))
        one="rowid=(SELECT MIN(rowid) FROM rr_mart.events_enriched WHERE timestamp=5 AND visitorid=2 AND itemid=2 AND event='view')"
        mutations=[('conflicting_tied_value',f"UPDATE rr_mart.events_enriched SET categoryid_value='2' WHERE {one};"),
            ('conflicting_tied_provenance',f'UPDATE rr_mart.events_enriched SET categoryid_source_file={literal(PROPERTY_FILES[1])} WHERE {one};'),
            ('expired_match',f'UPDATE rr_mart.events_enriched SET categoryid_to_ms=5 WHERE {one};'),
            ('duplicate_reference_id','INSERT INTO rr_core.dim_category VALUES (1);'),
            ('fact_wrong_type','ALTER TABLE rr_mart.events_enriched ALTER COLUMN categoryid_from_ms TYPE VARCHAR;'),
            ('empty_fact','DELETE FROM rr_mart.events_enriched;')]
        def assert_blocked(report):
            assert [row['segment'] for row in report]==LABELS
            assert all(row['categoryid'] is None and row['check_status']=='BLOCKED' and all(row[field] is None for field in OUTPUT[2:-1]) for row in report)
        for label,mutation in mutations:
            blocked,_=execute(folder,database,'BEGIN;'+mutation+adjusted(sql,fixture_rows,len(ids),wanted_stats,top_n=2)+'ROLLBACK;');assert_blocked(blocked)
        invalid_parameters=[('expected_eligible_pairs',11),('expected_mapped_pairs',8),('expected_unknown_reference_pairs',0),
            ('expected_cart_pairs',9),('expected_transaction_pairs',7),('expected_observation_end_ms',2*w+1),('expected_duplicate_surplus',0),('top_n',0)]
        for name,value in invalid_parameters:
            blocked,_=execute(folder,database,adjusted(sql,fixture_rows,len(ids),wanted_stats,top_n=2,override={name:value}),readonly=True);assert_blocked(blocked)
        cases.append(dict(case='invalid_source_ties_reference_cohort_coverage_and_flow_reconciliations_suppress_TOP_and_block_every_metric',passed=True,
            subcases=[name for name,_ in mutations]+['wrong_'+name for name,_ in invalid_parameters]))
    assert not folder.exists()
    with tempfile.TemporaryDirectory(prefix='rr-category-funnel-zero-',dir=tmp_root) as temporary:
        parent=Path(temporary)
        for label,rows,props in [
            ('no_unknown_reference',fixture_rows,[row[:3]+('1',)+row[4:] if row[3]=='999' else row for row in properties]),
            ('zero_eligible',[(w+1,1,'view',2,None),(2*w,99,'transaction',99,0)],properties)]:
            folder=parent/label;folder.mkdir();database=folder/'fixture.duckdb'
            ep,ec,cp,cc,ids,wanted_stats=fixture_source(folder,rows,props)
            execute(folder,database,category_build(folder,len(props),len(ids)))
            execute(folder,database,fixture_events_sql(rows),enrichment=True)
            report,_=execute(folder,database,adjusted(sql,rows,len(ids),wanted_stats),readonly=True)
            stats,interval_stats,_=compare_stream(folder,database,ep,cp,ids,ec['observation_end_ms'])
            assert report==reference_report(stats)
            unknown=next(row for row in report if row['segment']=='UNKNOWN_REFERENCE')
            assert unknown['eligible_pairs']==0 and all(unknown[field] is None for field in OUTPUT[5:8])
            if label=='zero_eligible':
                assert len(report)==5 and all(row['eligible_pairs']==0 and all(row[field] is None for field in OUTPUT[5:8]) for row in report)
        cases.append(dict(case='zero_unknown_bucket_retained_zero_eligible_five_rows_and_all_undefined_rates_NULL',passed=True,subcases=2))
    assert not parent.exists()
    print(json.dumps({'fixture_families_passed':len(cases),'invalid_admission_subcases':len(mutations)+len(invalid_parameters)}),flush=True)
    if args.fixtures_only:return

    before={name:staging.snapshot(source_dir/name) for name in FILES}
    assert all(before[name]['sha256']==audit['files'][name]['sha256'] and before[name]['size_bytes']==audit['publisher_expected_bytes'][name] for name in FILES)
    historical={str(path.relative_to(root)):previous.sha256(path) for path in (root/'data').glob('*preflight.json') if path.resolve()!=output.resolve()}
    assert len(historical)==72
    with tempfile.TemporaryDirectory(prefix='rr-category-funnel-real-',dir=tmp_root) as temporary:
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
        assert [row['check_status'] for row in report]==['PASS']*15 and all(list(row)==OUTPUT for row in report)
        print(json.dumps({'phase':3,'result':'SQL74 fifteen-row category funnel passed'}),flush=True)
        stats,interval_stats,stream_seconds=compare_stream(folder,database,ep,cp,ids,event_counts['observation_end_ms'])
        assert report==reference_report(stats) and stats['rows']==2756101 and stats['duplicate_surplus']==460 and stats['eligible_pairs']==2042310 and stats['cart_pairs']==43147 and stats['transaction_pairs']==15520
        assert interval_stats['rows']==788214 and stats['maximum_simultaneous_pair_states']==1
        assert [stats[label] for label in coverage.LABELS[:-1]]==[1527206,0,304405,210699]
        aggregate_counts={key:value for key,value in stats.items() if key!='groups'}
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
        SQL69_rerun=False,SQL62_hierarchy_rerun=False,SQL70_rerun=False,SQL71_rerun=False,SQL72_rerun=False,SQL73_rerun=False,learner_database_opened=False,
        query_read_only=True,private_stream_read_only=True,real_source_attempts=1,real_cli_phases=4,
        real_category_build_executions=1,real_category_enrichment_executions=1,real_analysis_script_executions=1,real_private_stream_executions=1,
        report_rows=15,report_columns=9,output_columns=OUTPUT,checks_passed=15,fail_rows=0,blocked_rows=0,results=report,report_sha256=report_hash(report),
        report_fingerprint_contract='SHA-256 of compact JSON arrays in output-column order followed by LF; four-place DECIMAL shares are JSON strings, counts integers and undefined shares null.',
        independent_python_event_counts=event_counts,independent_python_category_counts=category_counts,
        independent_python_interval_counts=interval_stats,independent_python_aggregate_counts=aggregate_counts,
        independent_python_report_matched=True,independent_python_Decimal_rates_matched=True,independent_one_pair_streaming_state=True,
        independent_stream_occurrences_compared=stats['rows'],independent_stream_fields_compared=10,independent_stream_all_occurrences_matched=True,
        independent_original_event_fields_and_duplicates_preserved=True,independent_category_values_bounds_provenance_statuses_matched=True,
        selected_category_history_fully_drained=True,eligible_first_view_tie_consistency_verified=True,numeric_reference_lookup_preserves_original_text=True,
        window_ms=WINDOW_MS,observation_end_ms=event_counts['observation_end_ms'],observation_end_utc=base.utc_text(event_counts['observation_end_ms']),
        eligibility_cutoff_ms=event_counts['observation_end_ms']-WINDOW_MS,eligibility_cutoff_utc=base.utc_text(event_counts['observation_end_ms']-WINDOW_MS),
        eligible_pairs=stats['eligible_pairs'],expected_eligible_pairs=2042310,coverage_partition_reconciled=True,global_flow_counts_reconciled=True,report_count_partition_reconciled=True,
        first_view_attribution_fixed_through_outcomes=True,shared_first_view_deadline_verified=True,strict_stage_order_verified=True,
        TOP_selection_uses_population_not_outcomes=True,OTHER_and_TOTAL_rates_recomputed_from_counts=True,
        maximum_simultaneous_pair_states=stats['maximum_simultaneous_pair_states'],maximum_current_item_history_rows=stats['maximum_current_item_history_rows'],
        private_database_sha256_before_readonly=database_before,private_database_sha256_after_readonly=database_after,private_database_bytes_unchanged=True,
        fixture_case_count=len(cases),fixture_cases=cases,invalid_admission_fixture_subcases=len(mutations)+len(invalid_parameters),
        invalid_admission_blocks_all_metrics_verified=True,additional_unqueried_columns_allowed_verified=True,zero_denominator_NULLs_verified=True,
        preflight_settings=dict(threads=2,default_memory_limit='1GB',default_max_temp_directory_size='2GB',
            category_enrichment_memory_limit='2GB',category_enrichment_max_temp_directory_size='4GB',timeout_seconds_per_cli_phase=120,
            python_sort_chunk_rows=CHUNK_ROWS,current_item_history_row_cap=HISTORY_CAP,simultaneous_pair_state_budget=1,category_aggregate_group_budget=1672,
            minimum_free_bytes=8*1024**3,private_directory_budget_bytes=7*1024**3),
        private_event_comparison_chunks=len(ep),private_category_comparison_chunks=len(cp),private_comparison_chunk_bytes=chunk_bytes,
        private_database_bytes_before_cleanup=database_bytes,largest_private_directory_bytes_observed_after_phase=max(sizes),
        workspace_free_bytes_before=free_before,workspace_free_bytes_after=shutil.disk_usage(tmp_root).free,
        temporary_databases_and_spills_removed=True,private_source_comparison_spools_removed=True,
        historical_preflight_files_unchanged=len(historical),historical_comparison_or_analysis_suites_rerun=False,
        aggregate_category_ids_in_public_report=True,source_records_or_visitor_item_transaction_ids_published=False,raw_category_history_rows_published=False,
        elapsed_python_category_scan_sort_seconds=category_sort_seconds,elapsed_python_event_scan_sort_seconds=event_sort_seconds,
        elapsed_category_build_seconds=category_build_seconds,elapsed_category_enrichment_seconds=enrichment_seconds,
        elapsed_readonly_category_funnel_seconds=query_seconds,elapsed_private_stream_seconds=stream_seconds,
        timing_scope='Four CLI phases: category-only import/intervals and ID projection; frozen event prefixes plus category-only enrichment; read-only SQL74; read-only ten-field source comparison. Sorting timed separately; hashing and fixtures excluded.',
        scope='Assistant SQL74 passed; learner execution pending. Descriptive ordered visitor-item seven-day paths attributed to the fixed earliest-view category; TOP categories selected by eligible cohort size, all unmatched buckets retained. Counts reconcile with accepted overall flow and coverage. Not people, orders, sessions, causal conversion or a performance ranking.')
    output.write_text(json.dumps(evidence,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps({'report_rows':15,'checks_passed':15,'occurrences_compared':stats['rows'],'fields_compared':10,'report_sha256':evidence['report_sha256']}),flush=True)

if __name__=='__main__':main()
