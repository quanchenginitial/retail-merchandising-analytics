"""Verify category item cart-volume bands and exact item-mean reference rates."""
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
from decimal import Decimal, ROUND_HALF_UP, localcontext
from fractions import Fraction
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
CONTRACT_SHA='66cdc63127de43a55421f280d1a69fd52bcc809b59861303fd02cb92290446fd'
TARGET_CATEGORY=1613
LABELS=['ZERO_CART','CART_01_04','CART_05_19','CART_20_PLUS','TOTAL']
OUTPUT=['cart_volume_band','item_count','eligible_pairs','cart_pairs','transaction_pairs','cart_share_pct','weighted_cart_to_transaction_rate_pct','mean_item_cart_to_transaction_rate_pct','zero_transaction_cart_items','check_status']
FACT_FIELDS=coverage.FACT_FIELDS
PARAMETERS=funnel.PARAMETERS.replace('10::BIGINT AS top_n','1613::BIGINT AS target_categoryid,25105::BIGINT AS expected_target_pairs,\n        483::BIGINT AS expected_target_carts,76::BIGINT AS expected_target_transactions')
ENRICHMENT=coverage.ENRICHMENT
STREAM=coverage.STREAM
literal=coverage.literal
category_build=coverage.category_build
event_chunks=coverage.event_chunks
merged_events=coverage.merged_events
category_chunks=coverage.category_chunks
reference_ids=coverage.reference_ids
fixture_events_sql=coverage.fixture_events_sql

def blank_band():
    return dict(item_count=0,eligible_pairs=0,cart_pairs=0,transaction_pairs=0,positive_cart_items=0,zero_transaction_cart_items=0,ratio_sum=Fraction(0,1))

def band_for(carts):
    return 'ZERO_CART' if carts==0 else 'CART_01_04' if carts<=4 else 'CART_05_19' if carts<=19 else 'CART_20_PLUS'

def blank_stats():
    result=coverage.blank_stats()
    result.update(cart_pairs=0,transaction_pairs=0,selected_item_count=0,selected_eligible_pairs=0,selected_cart_pairs=0,selected_transaction_pairs=0,
        selected_positive_cart_items=0,selected_zero_transaction_cart_items=0,maximum_current_item_counters=0,
        band_counts={label:blank_band() for label in LABELS[:-1]})
    return result

def expected_stream(event_paths,category_paths,ids,end_ms,stats,interval_stats,history_cap=HISTORY_CAP):
    source=iter(histories.expected_intervals(histories.merged_source(category_paths),interval_stats));pending=next(source,None)
    current_item=None;history=[];starts=[];current_pair=None;first_view=None;first_snapshot=None;cart_ms=None;transaction_ms=None;prior_event=None;item_counts=[0,0,0]
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
        if mapped=='MAPPED' and int(first_snapshot[0])==TARGET_CATEGORY:
            item_counts[0]+=1;item_counts[1]+=cart_ms is not None;item_counts[2]+=transaction_ms is not None
            stats['selected_eligible_pairs']+=1;stats['selected_cart_pairs']+=cart_ms is not None;stats['selected_transaction_pairs']+=transaction_ms is not None
    def close_item():
        eligible,carts,transactions=item_counts
        if eligible==0:return
        assert eligible>=carts>=transactions
        stats['selected_item_count']+=1;stats['selected_positive_cart_items']+=carts>0
        stats['selected_zero_transaction_cart_items']+=carts>0 and transactions==0
        group=stats['band_counts'][band_for(carts)]
        group['item_count']+=1;group['eligible_pairs']+=eligible;group['cart_pairs']+=carts;group['transaction_pairs']+=transactions
        group['positive_cart_items']+=carts>0;group['zero_transaction_cart_items']+=carts>0 and transactions==0
        if carts>0:group['ratio_sum']+=Fraction(transactions,carts)
    for event in merged_events(event_paths):
        item=event[3];pair=(item,event[1])
        if current_pair!=pair:
            if current_pair is not None:close_pair()
            if current_item!=item:
                if current_item is not None:close_item()
                while pending is not None and pending[0]<item:pending=next(source,None)
                history=[]
                while pending is not None and pending[0]==item:
                    assert len(history)<history_cap,'Private current-item history cap exceeded; no filtering'
                    history.append(pending);pending=next(source,None)
                starts=[row[3] for row in history];current_item=item;item_counts=[0,0,0]
                stats['maximum_current_item_history_rows']=max(stats['maximum_current_item_history_rows'],len(history))
                stats['maximum_current_item_counters']=1
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
    if current_item is not None:close_item()
    for _ in source:pass
    assert sum(stats[label] for label in coverage.LABELS[:-1])==stats['eligible_pairs']
    assert stats['observed_max_timestamp_ms']==end_ms

def percent(ratio):
    if ratio is None:return None
    with localcontext() as context:
        context.prec=60
        return format((Decimal(ratio.numerator)*100/Decimal(ratio.denominator)).quantize(Decimal('0.0001'),rounding=ROUND_HALF_UP),'.4f')

def combined_band(stats):
    result=blank_band()
    for band in stats['band_counts'].values():
        for name in result:result[name]+=band[name]
    return result

def reference_report(stats):
    total=combined_band(stats);report=[]
    assert [total[name] for name in ['item_count','eligible_pairs','cart_pairs','transaction_pairs','positive_cart_items','zero_transaction_cart_items']]==[
        stats['selected_item_count'],stats['selected_eligible_pairs'],stats['selected_cart_pairs'],stats['selected_transaction_pairs'],
        stats['selected_positive_cart_items'],stats['selected_zero_transaction_cart_items']]
    for label in LABELS:
        row=total if label=='TOTAL' else stats['band_counts'][label]
        share=None if total['cart_pairs']==0 else Fraction(row['cart_pairs'],total['cart_pairs'])
        weighted=None if row['cart_pairs']==0 else Fraction(row['transaction_pairs'],row['cart_pairs'])
        mean=None if row['positive_cart_items']==0 else row['ratio_sum']/row['positive_cart_items']
        report.append(dict(zip(OUTPUT,[label,row['item_count'],row['eligible_pairs'],row['cart_pairs'],row['transaction_pairs'],
            percent(share),percent(weighted),percent(mean),row['zero_transaction_cart_items'],'PASS'])))
    assert all(sum(row[field] for row in report[:-1])==report[-1][field] for field in ['item_count','eligible_pairs','cart_pairs','transaction_pairs','zero_transaction_cart_items'])
    return report

def report_hash(report):
    return hashlib.sha256(''.join(json.dumps([row[name] for name in OUTPUT],separators=(',',':'))+'\n' for row in report).encode()).hexdigest()

def adjusted(sql,event_rows,reference_count,stats,override=None):
    counts=Counter(row[2] for row in event_rows);end=max(row[0] for row in event_rows)
    values=dict(expected_rows=len(event_rows),expected_views=counts['view'],expected_carts=counts['addtocart'],expected_transactions=counts['transaction'],
        expected_duplicate_surplus=len(event_rows)-len(set(event_rows)),max_supported_ms=MAX_MS,window_ms=WINDOW_MS,
        expected_observation_end_ms=end,expected_eligible_pairs=stats['eligible_pairs'],expected_reference_ids=reference_count,
        expected_mapped_pairs=stats['MAPPED'],expected_unknown_reference_pairs=stats['UNKNOWN_REFERENCE'],expected_before_first_pairs=stats['BEFORE_FIRST'],
        expected_no_history_pairs=stats['NO_HISTORY'],expected_cart_pairs=stats['cart_pairs'],expected_transaction_pairs=stats['transaction_pairs'],target_categoryid=TARGET_CATEGORY,
        expected_target_pairs=stats['selected_eligible_pairs'],expected_target_carts=stats['selected_cart_pairs'],expected_target_transactions=stats['selected_transaction_pairs'])
    values.update(override or {});assert sql.count(PARAMETERS)==1
    return sql.replace(PARAMETERS,'SELECT '+','.join(f'{value}::BIGINT AS {name}' for name,value in values.items()))

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--duckdb',required=True);parser.add_argument('--output',required=True);parser.add_argument('--fixtures-only',action='store_true');args=parser.parse_args()
    root=Path(__file__).resolve().parents[1];output=(root/args.output).resolve()
    assert output.is_relative_to((root/'data').resolve())
    script_path='sql/76_analyze_retailrocket_category_item_cart_concentration.sql'
    validator_path='validation/preflight_retailrocket_category_item_cart_concentration.py'
    method_path='docs/RETAILROCKET_CATEGORY_ITEM_CART_CONCENTRATION_VALIDATION.md'
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
        'docs/RETAILROCKET_CATEGORY_7DAY_FUNNEL_VALIDATION.md','sql/75_analyze_retailrocket_category_funnel_time_cohorts.sql',
        'data/retailrocket_category_funnel_time_cohorts_preflight.json','data/retailrocket_category_funnel_time_cohorts_learner_acceptance.json',
        'docs/RETAILROCKET_CATEGORY_FUNNEL_TIME_COHORTS_VALIDATION.md']
    hashes={name:previous.sha256(root/name) for name in dependencies}
    contract=(root/method_path).read_bytes().split(b'\n## Executed results\n',1)[0]
    assert hashlib.sha256(contract).hexdigest()==CONTRACT_SHA
    for stem,script in [('category_dimension','sql/62_build_retailrocket_category_dimension.sql'),
                        ('events_enriched','sql/69_build_retailrocket_events_enriched.sql'),
                        ('7day_visitor_item_funnel','sql/72_analyze_retailrocket_7day_visitor_item_funnel.sql'),
                        ('first_view_category_coverage','sql/73_audit_retailrocket_first_view_category_coverage.sql'),
                        ('category_7day_funnel','sql/74_analyze_retailrocket_category_7day_funnel.sql'),
                        ('category_funnel_time_cohorts','sql/75_analyze_retailrocket_category_funnel_time_cohorts.sql')]:
        old=json.loads((root/f'data/retailrocket_{stem}_preflight.json').read_text(encoding='utf-8'))
        accepted=json.loads((root/f'data/retailrocket_{stem}_learner_acceptance.json').read_text(encoding='utf-8'))
        assert accepted['acceptance_status'].startswith('accepted') and accepted['report_sha256']==old['report_sha256']
        assert old['script_sha256']==hashes[script]
    periods=old
    category=json.loads((root/'data/retailrocket_category_7day_funnel_preflight.json').read_text(encoding='utf-8'))
    parent=next(row for row in category['results'] if row['categoryid']==TARGET_CATEGORY)
    assert [parent[name] for name in ['eligible_pairs','cart_pairs','transaction_pairs']]==[25105,483,76]
    assert [sum(row[name] for row in periods['results'] if row['categoryid']==TARGET_CATEGORY) for name in ['eligible_pairs','cart_pairs','transaction_pairs']]==[25105,483,76]
    overall=json.loads((root/'data/retailrocket_7day_visitor_item_funnel_preflight.json').read_text(encoding='utf-8'))
    assert [row['visitor_item_pairs'] for row in overall['results']][-3:]==[2042310,43147,15520]
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
            raise AssertionError('Private item cart-concentration CLI failure: '+category+'; row-bearing details withheld')
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
    specifications=[(2,2,0,0),(10,1,1,1),(20,4,4,0),(30,5,5,2),(40,19,19,1),(50,20,20,10)]
    fixture_rows=[];transaction_id=0
    for item,eligible,carts,transactions in specifications:
        for index in range(eligible):
            visitor=item*100+index;fixture_rows.append((0,visitor,'view',item,None))
            cart_time=w-1 if item==50 and index==0 else w if item==50 and index==19 else 1
            if index<carts:fixture_rows.append((cart_time,visitor,'addtocart',item,None))
            if index<transactions:
                fixture_rows.append((w if item==50 and index==0 else 2,visitor,'transaction',item,transaction_id));transaction_id+=1
    fixture_rows.extend([(0,2000,'view',20,None),(0,200,'addtocart',2,None),(1,200,'transaction',2,100),
        (1,3002,'transaction',30,101),(w+1,5019,'transaction',50,102),
        (20,9990,'view',50,None),(21,9990,'addtocart',50,None),(22,9990,'transaction',50,103),
        (w+1,9991,'view',2,None),(w+2,9991,'addtocart',2,None),(w+3,9991,'transaction',2,104),
        (2*w,9999,'addtocart',999,None)])
    properties=[(0,item,'categoryid','01613',PROPERTY_FILES[index%2]) for index,(item,_,_,_) in enumerate(specifications)]
    properties.extend([(1,10,'categoryid','2',PROPERTY_FILES[1]),(10,50,'categoryid','2',PROPERTY_FILES[0])])
    cases=[]
    def fixture_source(folder,rows):
        for name in PROPERTY_FILES:
            with (folder/name).open('w',encoding='utf-8',newline='') as stream:
                writer=csv.writer(stream);writer.writerow(['timestamp','itemid','property','value']);writer.writerows(row[:4] for row in reversed(properties) if row[4]==name)
        with (folder/'category_tree.csv').open('w',encoding='utf-8',newline='') as stream:
            writer=csv.writer(stream);writer.writerow(['categoryid','parentid']);writer.writerows((value,'') for value in [2,TARGET_CATEGORY])
        with (folder/'events.csv').open('w',encoding='utf-8',newline='') as stream:
            writer=csv.writer(stream);writer.writerow(staging.FIELDS);writer.writerows(reversed(rows))
        ep,ec=event_chunks(folder/'events.csv',folder,3);cp,cc=category_chunks(folder,folder,2);ids=reference_ids(folder/'category_tree.csv')
        stats=blank_stats()
        for _ in expected_stream(ep,cp,ids,ec['observation_end_ms'],stats,histories.blank_interval_stats()):pass
        return ep,ec,cp,cc,ids,stats
    with tempfile.TemporaryDirectory(prefix='rr-item-band-fixture-',dir=tmp_root) as temporary:
        folder,database=Path(temporary),Path(temporary)/'fixture.duckdb'
        ep,ec,cp,cc,ids,wanted=fixture_source(folder,fixture_rows)
        reference,_=execute(folder,database,category_build(folder,len(properties),len(ids))+'SELECT categoryid FROM rr_core.dim_category ORDER BY categoryid;')
        assert [row['categoryid'] for row in reference]==sorted(ids)
        execute(folder,database,fixture_events_sql(fixture_rows)+'ALTER TABLE rr_mart.events_enriched ADD COLUMN unqueried_fixture VARCHAR;',enrichment=True)
        query=adjusted(sql,fixture_rows,len(ids),wanted)
        before_db=previous.sha256(database);report,_=execute(folder,database,query,readonly=True)
        stats,interval_stats,_=compare_stream(folder,database,ep,cp,ids,ec['observation_end_ms'])
        assert report==reference_report(stats) and stats==wanted and previous.sha256(database)==before_db
        assert [[row[name] for name in ['item_count','eligible_pairs','cart_pairs','transaction_pairs']] for row in report]==[[1,2,0,0],[2,5,5,1],[2,24,24,3],[1,20,20,10],[6,51,49,14]]
        assert report[1]['weighted_cart_to_transaction_rate_pct']=='20.0000' and report[1]['mean_item_cart_to_transaction_rate_pct']=='50.0000'
        assert report[2]['weighted_cart_to_transaction_rate_pct']=='12.5000' and report[2]['mean_item_cart_to_transaction_rate_pct']=='22.6316'
        assert report[-1]['weighted_cart_to_transaction_rate_pct']=='28.5714' and report[-1]['mean_item_cart_to_transaction_rate_pct']=='39.0526'
        assert [row['zero_transaction_cart_items'] for row in report]==[0,1,0,0,1]
        assert report[0]['cart_share_pct']=='0.0000' and report[0]['mean_item_cart_to_transaction_rate_pct'] is None
        assert stats['maximum_current_item_counters']==1 and stats['duplicate_surplus']==1 and stats['selected_positive_cart_items']==5
        assert interval_stats['rows']==8
        cases.append(dict(case='cart_band_edges_0_1_4_5_19_20_unequal_volume_Fraction_means_fixed_category_strict_deadline_and_duplicates',passed=True,
            event_rows=len(fixture_rows),selected_items=6,expected_target_counts=[51,49,14],expected_total_weighted_pct='28.5714',
            expected_total_item_mean_pct='39.0526',positive_cart_items=5,zero_transaction_cart_items=1,complete_readset_fields=10))
        def assert_blocked(rows):
            assert [row['cart_volume_band'] for row in rows]==LABELS
            assert all(row['check_status']=='BLOCKED' and all(row[name] is None for name in OUTPUT[1:-1]) for row in rows)
        for name,value in [('expected_target_pairs',52),('expected_target_carts',50),('expected_target_transactions',15),('target_categoryid',2)]:
            blocked,_=execute(folder,database,adjusted(sql,fixture_rows,len(ids),wanted,override={name:value}),readonly=True);assert_blocked(blocked)
        one="rowid=(SELECT MIN(rowid) FROM rr_mart.events_enriched WHERE timestamp=0 AND visitorid=2000 AND itemid=20 AND event='view')"
        blocked,_=execute(folder,database,'BEGIN;UPDATE rr_mart.events_enriched SET categoryid_value=\'2\' WHERE '+one+';'+query+'ROLLBACK;');assert_blocked(blocked)
        cases.append(dict(case='wrong_target_parent_counts_or_selector_and_conflicting_first_view_block_all_metrics',passed=True,subcases=5))
    assert not folder.exists()
    with tempfile.TemporaryDirectory(prefix='rr-item-band-empty-',dir=tmp_root) as temporary:
        parent_folder=Path(temporary)
        for label,rows in [
            ('zero_cart_only',[(0,1,'view',2,None),(0,1,'addtocart',2,None),(1,1,'transaction',2,0),(2*w,99,'addtocart',999,None)]),
            ('no_target_items',[(20,1,'view',50,None),(21,1,'addtocart',50,None),(22,1,'transaction',50,0),(2*w,99,'addtocart',999,None)])]:
            folder=parent_folder/label;folder.mkdir();database=folder/'fixture.duckdb'
            ep,ec,cp,cc,ids,wanted=fixture_source(folder,rows)
            execute(folder,database,category_build(folder,len(properties),len(ids)))
            execute(folder,database,fixture_events_sql(rows),enrichment=True)
            report,_=execute(folder,database,adjusted(sql,rows,len(ids),wanted),readonly=True)
            stats,interval_stats,_=compare_stream(folder,database,ep,cp,ids,ec['observation_end_ms'])
            assert report==reference_report(stats) and len(report)==5
            assert all(all(row[name] is None for name in OUTPUT[5:8]) for row in report)
            assert all(row['zero_transaction_cart_items']==0 for row in report)
            if label=='zero_cart_only':assert report[0]['item_count']==1 and report[-1]['eligible_pairs']==1
            else:assert all(row['item_count']==0 and row['eligible_pairs']==0 for row in report)
        cases.append(dict(case='zero_cart_and_no_selected_item_populations_keep_five_rows_and_undefined_rates_NULL',passed=True,subcases=2))
    assert not parent_folder.exists()
    print(json.dumps({'fixture_families_passed':len(cases),'invalid_admission_subcases':5}),flush=True)
    if args.fixtures_only:return

    before={name:staging.snapshot(source_dir/name) for name in FILES}
    assert all(before[name]['sha256']==audit['files'][name]['sha256'] and before[name]['size_bytes']==audit['publisher_expected_bytes'][name] for name in FILES)
    historical={str(path.relative_to(root)):previous.sha256(path) for path in (root/'data').glob('*preflight.json') if path.resolve()!=output.resolve()}
    assert len(historical)==74
    with tempfile.TemporaryDirectory(prefix='rr-item-band-real-',dir=tmp_root) as temporary:
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
        print(json.dumps({'phase':3,'result':'SQL76 five-row item cart-concentration passed'}),flush=True)
        stats,interval_stats,stream_seconds=compare_stream(folder,database,ep,cp,ids,event_counts['observation_end_ms'])
        assert report==reference_report(stats) and stats['rows']==2756101 and stats['duplicate_surplus']==460 and stats['eligible_pairs']==2042310 and stats['cart_pairs']==43147 and stats['transaction_pairs']==15520
        assert interval_stats['rows']==788214 and stats['maximum_simultaneous_pair_states']==1
        assert [stats[label] for label in coverage.LABELS[:-1]]==[1527206,0,304405,210699]
        assert [stats[name] for name in ['selected_eligible_pairs','selected_cart_pairs','selected_transaction_pairs']]==[25105,483,76]
        assert [report[-1][name] for name in ['eligible_pairs','cart_pairs','transaction_pairs']]==[parent[name] for name in ['eligible_pairs','cart_pairs','transaction_pairs']]
        aggregate_counts={key:value for key,value in stats.items() if key!='band_counts'}
        band_counts={label:{key:value for key,value in values.items() if key!='ratio_sum'} for label,values in stats['band_counts'].items()}
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
        SQL69_rerun=False,SQL62_hierarchy_rerun=False,SQL70_rerun=False,SQL71_rerun=False,SQL72_rerun=False,SQL73_rerun=False,SQL74_rerun=False,SQL75_rerun=False,learner_database_opened=False,
        query_read_only=True,private_stream_read_only=True,real_source_attempts=1,real_cli_phases=4,
        real_category_build_executions=1,real_category_enrichment_executions=1,real_analysis_script_executions=1,real_private_stream_executions=1,
        report_rows=5,report_columns=10,output_columns=OUTPUT,checks_passed=5,fail_rows=0,blocked_rows=0,results=report,report_sha256=report_hash(report),
        report_fingerprint_contract='SHA-256 of compact JSON arrays in output-column order followed by LF; four-place DECIMAL shares are JSON strings, counts integers and undefined shares null.',
        independent_python_event_counts=event_counts,independent_python_category_counts=category_counts,
        independent_python_interval_counts=interval_stats,independent_python_aggregate_counts=aggregate_counts,independent_python_band_counts=band_counts,
        independent_python_report_matched=True,independent_python_Decimal_rates_matched=True,independent_one_pair_streaming_state=True,
        independent_stream_occurrences_compared=stats['rows'],independent_stream_fields_compared=10,independent_stream_all_occurrences_matched=True,
        independent_original_event_fields_and_duplicates_preserved=True,independent_category_values_bounds_provenance_statuses_matched=True,
        selected_category_history_fully_drained=True,eligible_first_view_tie_consistency_verified=True,numeric_reference_lookup_preserves_original_text=True,
        target_categoryid=TARGET_CATEGORY,target_parent_counts_match_SQL74_and_SQL75=True,independent_item_partition_matched=True,
        independent_Fraction_item_ratio_sums_verified=True,total_item_mean_uses_all_positive_cart_items=True,no_all_item_aggregate_map=True,
        maximum_current_item_counters=stats['maximum_current_item_counters'],band_aggregate_count=4,
        window_ms=WINDOW_MS,observation_end_ms=event_counts['observation_end_ms'],observation_end_utc=base.utc_text(event_counts['observation_end_ms']),
        eligibility_cutoff_ms=event_counts['observation_end_ms']-WINDOW_MS,eligibility_cutoff_utc=base.utc_text(event_counts['observation_end_ms']-WINDOW_MS),
        eligible_pairs=stats['eligible_pairs'],expected_eligible_pairs=2042310,coverage_partition_reconciled=True,global_flow_counts_reconciled=True,report_count_partition_reconciled=True,
        first_view_attribution_fixed_through_outcomes=True,shared_first_view_deadline_verified=True,strict_stage_order_verified=True,
        band_membership_uses_global_qualified_cart_count=True,pooled_rates_use_sum_transactions_over_sum_carts=True,
        maximum_simultaneous_pair_states=stats['maximum_simultaneous_pair_states'],maximum_current_item_history_rows=stats['maximum_current_item_history_rows'],
        private_database_sha256_before_readonly=database_before,private_database_sha256_after_readonly=database_after,private_database_bytes_unchanged=True,
        fixture_case_count=len(cases),fixture_cases=cases,invalid_admission_fixture_subcases=5,
        invalid_admission_blocks_all_metrics_verified=True,additional_unqueried_columns_allowed_verified=True,zero_denominator_NULLs_verified=True,
        preflight_settings=dict(threads=2,default_memory_limit='1GB',default_max_temp_directory_size='2GB',
            category_enrichment_memory_limit='2GB',category_enrichment_max_temp_directory_size='4GB',timeout_seconds_per_cli_phase=120,
            python_sort_chunk_rows=CHUNK_ROWS,current_item_history_row_cap=HISTORY_CAP,simultaneous_pair_state_budget=1,current_item_counter_budget=1,band_aggregate_budget=4,
            minimum_free_bytes=8*1024**3,private_directory_budget_bytes=7*1024**3),
        private_event_comparison_chunks=len(ep),private_category_comparison_chunks=len(cp),private_comparison_chunk_bytes=chunk_bytes,
        private_database_bytes_before_cleanup=database_bytes,largest_private_directory_bytes_observed_after_phase=max(sizes),
        workspace_free_bytes_before=free_before,workspace_free_bytes_after=shutil.disk_usage(tmp_root).free,
        temporary_databases_and_spills_removed=True,private_source_comparison_spools_removed=True,
        historical_preflight_files_unchanged=len(historical),historical_comparison_or_analysis_suites_rerun=False,
        aggregate_category_ids_in_public_report=False,target_categoryid_published_as_aggregate_context=True,raw_item_ids_in_public_report=False,source_records_or_visitor_item_transaction_ids_published=False,raw_category_history_rows_published=False,
        elapsed_python_category_scan_sort_seconds=category_sort_seconds,elapsed_python_event_scan_sort_seconds=event_sort_seconds,
        elapsed_category_build_seconds=category_build_seconds,elapsed_category_enrichment_seconds=enrichment_seconds,
        elapsed_readonly_item_concentration_seconds=query_seconds,elapsed_private_stream_seconds=stream_seconds,
        timing_scope='Four CLI phases: category-only import/intervals and ID projection; frozen event prefixes plus category-only enrichment; read-only SQL76; read-only ten-field source comparison. Sorting timed separately; hashing and fixtures excluded.',
        scope='Assistant SQL76 passed; learner execution pending. Global item cart-volume bands within fixed first-view category 1613; pooled and equal-positive-cart-item mean rates are descriptive exploratory diagnostics after target selection. No ranking, item identifiers, cohort split, significance or causal effect; zero transaction counts concern this defined seven-day path, not lifetime sales.')
    output.write_text(json.dumps(evidence,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps({'report_rows':5,'checks_passed':5,'occurrences_compared':stats['rows'],'fields_compared':10,'report_sha256':evidence['report_sha256']}),flush=True)

if __name__=='__main__':main()
