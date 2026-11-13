"""Check key-only pair counts using the accepted membership fingerprint and a bounded pair reference."""
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
from datetime import datetime, timezone
from itertools import combinations, groupby, zip_longest
from pathlib import Path

import preflight_retailrocket_transaction_basket_items as model

grain=model.grain
staging=model.staging
source_reference=model.source_reference
CONTRACT_SHA='069c296001badd3789a4a652e368af6805eaf65b8497932622bcb8be7d8d9b86'
KEYS=['visitorid','transactionid','itemid']
OUTPUT=['check_order','check_name','actual','expected','status']
CHECKS=['membership_rows','required_key_schema_mismatch','invalid_key_rows','duplicate_membership_keys',
        'candidate_baskets','single_item_baskets','multi_item_baskets','max_items_per_basket','pair_occurrences',
        'distinct_item_pairs','pairs_seen_once','pairs_seen_2plus','max_baskets_per_pair',
        'pair_occurrence_reconciliation_difference','pair_frequency_partition_difference']
TRANSACTION_CAP=100000
PAIR_CAP=100000


def canonical_hash(rows):
    return hashlib.sha256(''.join(json.dumps(row,separators=(',',':'))+'\n' for row in rows).encode()).hexdigest()


def scan_source(path):
    counts=dict(rows=0,view=0,addtocart=0,transaction=0,null_transaction_ids=0);transactions=[]
    with path.open('r',encoding='utf-8',newline='') as stream:
        reader=csv.reader(stream,strict=True);assert next(reader)==staging.FIELDS
        for raw in reader:
            assert len(raw)==5
            logical=tuple(None if i==4 and value=='' else value for i,value in enumerate(raw))
            assert staging.valid_row(logical),'Private source value contract failed; values withheld'
            row=staging.typed(logical);assert row[0]<=model.events.utc_reference.MAX_MS
            counts['rows']+=1;counts[row[2]]+=1;counts['null_transaction_ids']+=row[4] is None
            if row[2]=='transaction':
                assert len(transactions)<TRANSACTION_CAP,'Private transaction cap exceeded; no filtering'
                transactions.append(row)
    return model.memberships(transactions),counts


def pair_reference(rows):
    assert len(rows)<=TRANSACTION_CAP
    pairs=Counter();sizes=[];occurrences=0;seen=set()
    for basket,members in groupby(rows,key=lambda row:row[:2]):
        items=[row[2] for row in members]
        assert items==sorted(items) and len(items)==len(set(items))
        assert basket not in seen;seen.add(basket);sizes.append(len(items))
        for pair in combinations(items,2):
            assert pair[0]<pair[1] and occurrences<PAIR_CAP,'Private pair-occurrence cap exceeded; no filtering'
            if pair not in pairs:assert len(pairs)<PAIR_CAP,'Private distinct-pair cap exceeded; no filtering'
            pairs[pair]+=1;occurrences+=1
    stats=dict(memberships=len(rows),baskets=len(sizes),single_baskets=sum(size==1 for size in sizes),
        multi_baskets=sum(size>1 for size in sizes),max_items=max(sizes,default=None),pair_occurrences=occurrences,
        combinatorial_pair_occurrences=sum(size*(size-1)//2 for size in sizes),distinct_pairs=len(pairs),
        pairs_seen_once=sum(count==1 for count in pairs.values()),pairs_seen_2plus=sum(count>=2 for count in pairs.values()),
        max_baskets_per_pair=max(pairs.values(),default=None))
    assert stats['pair_occurrences']==stats['combinatorial_pair_occurrences']
    return stats,[pair+(count,) for pair,count in sorted(pairs.items())]


def reference_report(stats):
    values=[stats['memberships'],0,0,0,stats['baskets'],stats['single_baskets'],stats['multi_baskets'],stats['max_items'],
        stats['pair_occurrences'],stats['distinct_pairs'],stats['pairs_seen_once'],stats['pairs_seen_2plus'],
        stats['max_baskets_per_pair'],0,0]
    return [dict(zip(OUTPUT,[i,name,value,None if 9<=i<=13 else value,'INFO' if 9<=i<=13 else 'PASS']))
            for i,(name,value) in enumerate(zip(CHECKS,values),1)]


def adjusted(sql,stats,override=None):
    values={name:stats[key] for name,key in [('expected_memberships','memberships'),('expected_baskets','baskets'),
        ('expected_single_baskets','single_baskets'),('expected_multi_baskets','multi_baskets'),('expected_max_items','max_items')]}
    values.update(override or {})
    for name,value in values.items():
        sql,n=re.subn(r'\b[0-9]+::BIGINT AS '+name+r'\b',f'{value}::BIGINT AS {name}',sql);assert n==1
    return sql


def pair_stream_sql(sql):
    assert sql.count('), checks AS (')==1
    return sql.split('), checks AS (',1)[0]+')\nSELECT item_a,item_b,basket_count FROM pair_counts ORDER BY item_a,item_b;'


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--duckdb',required=True)
    parser.add_argument('--output',required=True);parser.add_argument('--fixtures-only',action='store_true');args=parser.parse_args()
    root=Path(__file__).resolve().parents[1];output=(root/args.output).resolve()
    script_path='sql/80_analyze_retailrocket_basket_pair_counts.sql'
    validator_path='validation/preflight_retailrocket_basket_pair_counts.py';method_path='docs/RETAILROCKET_BASKET_PAIR_COUNTS_VALIDATION.md'
    assert output==(root/'data/retailrocket_basket_pair_counts_preflight.json').resolve()
    old=json.loads((root/'data/retailrocket_transaction_basket_items_preflight.json').read_text(encoding='utf-8'))
    accepted=json.loads((root/'data/retailrocket_transaction_basket_items_learner_acceptance.json').read_text(encoding='utf-8'))
    assert accepted['acceptance_status']=='accepted' and accepted['report_sha256']==old['report_sha256']
    deps=list(old['code_and_dependency_sha256'])+[script_path,validator_path,'data/retailrocket_transaction_basket_items_preflight.json',
        'data/retailrocket_transaction_basket_items_learner_acceptance.json','docs/RETAILROCKET_TRANSACTION_BASKET_ITEMS_VALIDATION.md']
    hashes={name:source_reference.sha256(root/name) for name in deps}
    assert all(hashes[name]==digest for name,digest in old['code_and_dependency_sha256'].items())
    contract=(root/method_path).read_bytes().split(b'\n## Executed results\n',1)[0]
    assert hashlib.sha256(contract).hexdigest()==CONTRACT_SHA
    sql=(root/script_path).read_text(encoding='utf-8');clean=re.sub(r'--[^\n]*','',sql)
    assert clean.lstrip().startswith('WITH ') and not re.search(r'\b(CREATE|INSERT|UPDATE|DELETE|DROP|ALTER|COPY|SET|ATTACH|DETACH)\b',clean,re.I)
    assert all(name not in clean for name in ['first_timestamp_ms','last_timestamp_ms','source_event_rows','rr_stg','rr_core','categoryid','available'])
    stream_sql=pair_stream_sql(sql)
    source=Path(source_reference.SOURCE);source_audit=json.loads((root/'data/retailrocket_source_audit.json').read_text(encoding='utf-8'))
    tmp_root=root/'tmp';tmp_root.mkdir(exist_ok=True);free_before=shutil.disk_usage(tmp_root).free
    assert free_before>=8*1024**3;sizes=[]
    def settings(folder,database):
        assert folder.resolve().is_relative_to(tmp_root.resolve()) and Path(database).resolve().is_relative_to(folder.resolve())
        spill=(folder/'spill').as_posix().replace("'","''")
        return f"SET threads=2;SET memory_limit='1GB';SET max_temp_directory_size='2GB';SET temp_directory='{spill}';\n"
    def observe(folder):
        size=sum(p.stat().st_size for p in folder.rglob('*') if p.is_file());assert size<=7*1024**3;sizes.append(size)
    def execute(folder,database,query,readonly=False):
        started=time.perf_counter();run=subprocess.run([args.duckdb,str(database),'-bail','-json']+(['-readonly'] if readonly else []),
            input=settings(folder,database)+query,text=True,encoding='utf-8',capture_output=True,timeout=120)
        if run.returncode:
            diagnostic=run.stderr.lower()
            category=next((name for name,patterns in [('out_of_memory',['out of memory','failed to allocate']),('disk_or_spill',['no space left','max_temp_directory_size']),
                ('parser',['parser error']),('binder',['binder error']),('invalid_input',['invalid input error'])]
                if any(pattern in diagnostic for pattern in patterns)),'unclassified_cli_error')
            raise AssertionError('Private pair-count CLI failure: '+category+'; row-bearing details withheld')
        observe(folder)
        return json.loads(run.stdout) if run.stdout.strip() else None,round(time.perf_counter()-started,3)
    def load_memberships(folder,database,rows):
        path=folder/'memberships.csv'
        with path.open('w',encoding='utf-8',newline='') as stream:
            writer=csv.writer(stream);writer.writerow(model.FIELDS);writer.writerows(rows)
        columns=','.join("'"+name+"':'BIGINT'" for name in model.FIELDS)
        query="CREATE SCHEMA rr_mart;CREATE TABLE rr_mart.transaction_basket_items AS SELECT * FROM read_csv('"+path.as_posix().replace("'","''")+"',header=true,columns={"+columns+"});\n"+model.MEMBERSHIP_STREAM
        observed,seconds=execute(folder,database,query)
        actual=[tuple(row[name] for name in model.FIELDS) for row in observed]
        assert actual==rows,'Private membership input readback differs; values withheld'
        return canonical_hash(actual),seconds,path.stat().st_size
    def compare_pairs(folder,database,query,expected):
        started=time.perf_counter();expired=threading.Event();count=0;sentinel=object();digest=hashlib.sha256()
        process=subprocess.Popen([args.duckdb,str(database),'-bail','-readonly','-csv','-noheader'],stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,encoding='utf-8')
        def expire():expired.set();process.kill()
        timer=threading.Timer(120,expire);timer.start()
        try:
            process.stdin.write(settings(folder,database)+query);process.stdin.close()
            for observed,wanted in zip_longest(csv.reader(process.stdout,strict=True),expected,fillvalue=sentinel):
                assert observed is not sentinel and wanted is not sentinel,'Private pair aggregation count differs'
                assert len(observed)==3;actual=tuple(int(value) for value in observed)
                assert actual==wanted,'Private pair aggregation tuple differs; values withheld'
                digest.update((json.dumps(actual,separators=(',',':'))+'\n').encode());count+=1
            assert process.wait(timeout=120)==0 and not expired.is_set()
        finally:
            timer.cancel()
            if process.poll() is None:process.kill();process.wait()
            process.stdout.close()
        observe(folder)
        return dict(rows=count,fields=3,sha256=digest.hexdigest()),round(time.perf_counter()-started,3)

    transaction_rows=[(100,1,'transaction',2,10),(101,1,'transaction',2,10),(102,1,'transaction',10,10),(103,1,'transaction',20,10),
        (104,2,'transaction',2,10),(105,2,'transaction',10,10),(106,3,'transaction',99,30),
        (107,4,'transaction',10,40),(108,4,'transaction',30,40)]
    rows=model.memberships(transaction_rows);stats,pairs=pair_reference(rows);cases=[]
    with tempfile.TemporaryDirectory(prefix='rr-pair-count-fixture-',dir=tmp_root) as temporary:
        folder,database=Path(temporary),Path(temporary)/'fixture.duckdb'
        input_hash,_,_=load_memberships(folder,database,rows);assert input_hash==canonical_hash(rows)
        execute(folder,database,'ALTER TABLE rr_mart.transaction_basket_items ADD COLUMN unqueried_fixture VARCHAR;')
        query=adjusted(sql,stats);before_db=source_reference.sha256(database)
        report,_=execute(folder,database,query,readonly=True);proof,_=compare_pairs(folder,database,pair_stream_sql(query),iter(pairs))
        assert report==reference_report(stats) and source_reference.sha256(database)==before_db
        assert pairs==[(2,10,2),(2,20,1),(10,20,1),(10,30,1)]
        assert stats['memberships']==8 and stats['baskets']==4 and stats['pair_occurrences']==5 and proof['rows']==4
        ignored,_=execute(folder,database,'BEGIN;UPDATE rr_mart.transaction_basket_items SET source_event_rows=source_event_rows+1000;'+query+'ROLLBACK;')
        assert ignored==report
        cases.append(dict(case='numeric_unordered_pairs_three_items_singletons_shared_transaction_ids_repeated_pair_and_unweighted_occurrences',passed=True,
            input_memberships=8,candidate_baskets=4,pair_occurrences=5,distinct_item_pairs=4,complete_pair_aggregate_fields=3))
        mutations=[('duplicate_key','INSERT INTO rr_mart.transaction_basket_items SELECT * FROM rr_mart.transaction_basket_items LIMIT 1;'),
            ('null_key','UPDATE rr_mart.transaction_basket_items SET itemid=NULL WHERE visitorid=1 AND itemid=2;'),
            ('wrong_key_type','ALTER TABLE rr_mart.transaction_basket_items ALTER COLUMN itemid TYPE VARCHAR;'),
            ('empty_input','DELETE FROM rr_mart.transaction_basket_items;')]
        for label,mutation in mutations:
            blocked,_=execute(folder,database,'BEGIN;'+mutation+query+'ROLLBACK;')
            assert [row['check_name'] for row in blocked]==CHECKS
            assert all(row['actual'] is None and row['status']=='BLOCKED' for row in blocked),label
            assert [row['expected'] for row in blocked]==[row['expected'] for row in report]
        blocked,_=execute(folder,database,adjusted(sql,stats,{'expected_max_items':4}),readonly=True)
        assert all(row['actual'] is None and row['status']=='BLOCKED' for row in blocked)
        cases.append(dict(case='duplicate_NULL_wrong_type_empty_or_wrong_expected_keys_block_before_join_keep_expectations',passed=True,subcases=5))
    assert not folder.exists()
    with tempfile.TemporaryDirectory(prefix='rr-pair-count-singletons-',dir=tmp_root) as temporary:
        folder,database=Path(temporary),Path(temporary)/'fixture.duckdb';single_rows=[(1,10,2,100,100,1),(2,10,10,100,100,1)]
        single_stats,single_pairs=pair_reference(single_rows);load_memberships(folder,database,single_rows)
        query=adjusted(sql,single_stats);report,_=execute(folder,database,query,readonly=True)
        proof,_=compare_pairs(folder,database,pair_stream_sql(query),iter(single_pairs))
        assert report==reference_report(single_stats) and proof['rows']==0 and report[12]['actual'] is None
        assert Counter(row['status'] for row in report)==Counter(PASS=10,INFO=5)
        cases.append(dict(case='singleton_only_population_retains_baskets_zero_pairs_and_NULL_maximum',passed=True))
    assert not folder.exists()
    print(json.dumps({'fixture_families_passed':len(cases),'invalid_admission_subcases':5}),flush=True)
    if args.fixtures_only:return

    before={'events.csv':staging.snapshot(source)}
    assert all(before['events.csv'][key]==source_audit['source_before']['events.csv'][key]==source_audit['source_after']['events.csv'][key]
        for key in ['size_bytes','modified_time_ns','sha256'])
    historical={str(p.relative_to(root)):source_reference.sha256(p) for p in (root/'data').glob('*preflight.json') if p.resolve()!=output.resolve()}
    assert len(historical)==78
    started=time.perf_counter();rows,source_counts=scan_source(source);source_seconds=round(time.perf_counter()-started,3)
    assert source_counts==old['independent_python_source_counts'] and len(rows)==22323
    input_hash=canonical_hash(rows);assert input_hash==old['independent_membership_stream_sha256']
    started=time.perf_counter();stats,pairs=pair_reference(rows);reference_seconds=round(time.perf_counter()-started,3)
    assert [stats[name] for name in ['memberships','baskets','single_baskets','multi_baskets','max_items']]==[22323,17672,15029,2643,31]
    print(json.dumps({'phase':'single source scan and accepted six-field membership fingerprint matched'}),flush=True)
    with tempfile.TemporaryDirectory(prefix='rr-pair-count-real-',dir=tmp_root) as temporary:
        folder,database=Path(temporary),Path(temporary)/'preflight.duckdb'
        readback_hash,load_seconds,csv_bytes=load_memberships(folder,database,rows);assert readback_hash==input_hash
        database_before=source_reference.sha256(database)
        report,query_seconds=execute(folder,database,sql,readonly=True)
        assert report==reference_report(stats) and Counter(row['status'] for row in report)==Counter(PASS=10,INFO=5)
        print(json.dumps({'phase':'SQL80 fifteen-row pair-count report passed','PASS':10,'INFO':5}),flush=True)
        proof,stream_seconds=compare_pairs(folder,database,stream_sql,iter(pairs))
        assert proof['rows']==stats['distinct_pairs'] and proof['sha256']==canonical_hash(pairs)
        database_after=source_reference.sha256(database);assert database_before==database_after
        database_bytes=database.stat().st_size
    assert not folder.exists()
    after={'events.csv':staging.snapshot(source)}
    assert before==after and all(source_reference.sha256(root/name)==digest for name,digest in hashes.items())
    assert all(source_reference.sha256(root/name)==digest for name,digest in historical.items())
    assert (root/method_path).read_bytes().startswith(contract)
    evidence=dict(checked_at_utc=datetime.now(timezone.utc).isoformat(),executor='assistant',engine=subprocess.check_output([args.duckdb,'-version'],text=True).strip(),
        script=script_path,script_sha256=hashes[script_path],validator=validator_path,validator_sha256=hashes[validator_path],code_and_dependency_sha256=hashes,
        method_contract=method_path,method_contract_prefix_bytes=len(contract),method_contract_prefix_sha256=CONTRACT_SHA,
        source_files=['events.csv'],source_before=before,source_after=after,source_hashes_and_metadata_unchanged=True,
        source_table='rr_mart.transaction_basket_items',readset_fields=KEYS,required_readset_columns=3,
        private_input_fields=model.FIELDS,private_input_rows=len(rows),private_input_columns=6,
        reconstructed_membership_sha256=input_hash,accepted_SQL79_membership_sha256=old['independent_membership_stream_sha256'],
        accepted_SQL79_membership_fingerprint_matched=True,private_input_readback_sha256=readback_hash,private_input_readback_matched=True,
        accepted_original_five_field_proof_reused=True,original_five_field_occurrence_comparison_rerun=False,original_event_external_sort_rerun=False,
        SQL54_rerun=False,SQL63_rerun=False,SQL79_rerun=False,stored_membership_timestamps_and_counts_in_query_readset=False,
        property_files_read=False,category_csv_read=False,UTC_fields_read=False,property_history_reconstructed=False,category_hierarchy_reverified=False,
        learner_database_opened=False,query_read_only=True,private_pair_stream_read_only=True,
        real_source_attempts=1,real_event_csv_parse_passes=1,real_cli_phases=3,real_private_input_load_executions=1,real_analysis_script_executions=1,real_private_pair_stream_executions=1,
        report_rows=15,report_columns=5,output_columns=OUTPUT,checks_passed=10,info_rows=5,fail_rows=0,blocked_rows=0,results=report,
        report_sha256=canonical_hash([[row[key] for key in OUTPUT] for row in report]),
        report_fingerprint_contract='SHA-256 of compact JSON arrays in output-column order followed by LF; integer counts and null INFO expectations retained.',
        independent_python_source_counts=source_counts,independent_python_pair_counts=stats,independent_python_report_matched=True,
        independent_pair_aggregate_rows_compared=proof['rows'],independent_pair_aggregate_fields_compared=3,
        independent_pair_aggregate_sha256=proof['sha256'],independent_pair_aggregates_all_matched=True,
        pair_aggregation_stream_sql_sha256=hashlib.sha256(stream_sql.encode()).hexdigest(),
        candidate_basket_key=['visitorid','transactionid'],unordered_numeric_pair_verified=True,singleton_baskets_retained_in_population=True,
        choose_two_invariant_verified=True,source_event_rows_used_as_pair_weight=False,association_metrics_calculated=False,
        candidate_baskets_are_verified_orders=False,retained_transaction_occurrences=source_counts['transaction'],
        transaction_occurrence_cap=TRANSACTION_CAP,pair_occurrence_cap=PAIR_CAP,distinct_pair_key_cap=PAIR_CAP,
        private_database_sha256_before_readonly=database_before,private_database_sha256_after_readonly=database_after,private_database_bytes_unchanged=True,
        fixture_case_count=len(cases),fixture_cases=cases,invalid_admission_fixture_subcases=5,
        invalid_admission_blocks_all_actuals_verified=True,static_expectations_preserved_on_blocked_verified=True,
        additional_unqueried_columns_allowed_verified=True,unqueried_source_event_rows_ignored_verified=True,singleton_only_maximum_NULL_verified=True,
        preflight_settings=dict(threads=2,memory_limit='1GB',max_temp_directory_size='2GB',timeout_seconds_per_cli_phase=120,
            transaction_occurrence_cap=TRANSACTION_CAP,pair_occurrence_cap=PAIR_CAP,distinct_pair_key_cap=PAIR_CAP,
            minimum_free_bytes=8*1024**3,private_directory_budget_bytes=7*1024**3),
        private_input_csv_bytes=csv_bytes,private_database_bytes_before_cleanup=database_bytes,
        largest_private_directory_bytes_observed_after_phase=max(sizes),workspace_free_bytes_before=free_before,workspace_free_bytes_after=shutil.disk_usage(tmp_root).free,
        temporary_databases_and_spills_removed=True,private_membership_csv_removed=True,historical_preflight_files_unchanged=len(historical),
        historical_comparison_or_analysis_suites_rerun=False,source_records_or_identifiers_uploaded_or_logged=False,raw_pair_list_published=False,
        elapsed_python_source_scan_reconstruction_seconds=source_seconds,elapsed_python_pair_reference_seconds=reference_seconds,
        elapsed_private_input_load_readback_seconds=load_seconds,elapsed_readonly_pair_count_seconds=query_seconds,elapsed_private_pair_stream_seconds=stream_seconds,
        timing_scope='One source-order CSV parse and bounded membership/pair reference, plus three CLI phases: small private input load/readback, read-only report, read-only pair stream. No original-event sorted stream or old SQL reruns.',
        scope='Assistant SQL80 preparation passed; learner execution pending. Key-only unordered item co-occurrence counts, with all candidate baskets retained. No quantities, verified order semantics, support/confidence/lift, rankings or causal effects.')
    output.write_text(json.dumps(evidence,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps({'report_rows':15,'checks_passed':10,'info_rows':5,'pair_aggregate_rows_compared':proof['rows'],
                      'pair_aggregate_fields':3,'report_sha256':evidence['report_sha256']}),flush=True)


if __name__=='__main__':main()
