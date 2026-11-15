"""Validate within-cell and global candidate-basket concentration without publishing IDs."""
import argparse
import csv
import hashlib
import json
import math
import re
import shutil
import subprocess
import tempfile
import threading
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from fractions import Fraction
from itertools import zip_longest
from pathlib import Path

import preflight_retailrocket_visitor_rf_segments as previous

counts=previous.counts
model=previous.model
staging=previous.staging
source_reference=previous.source_reference
READSET=['visitorid','transactionid','itemid','last_timestamp_ms']
DISPLAY_TOL=previous.DISPLAY_TOL
CONTRACT_SHA='0cce795a2e7d4dbbacd85b0b37ae518b415730bee0f6c818a4592cb14fad8ee7'
REFERENCE_MS=1442545187788
REFERENCE_UTC='2015-09-18T02:59:47.788000Z'
SOURCE_MIN_MS=1430622004384
DAY_MS=86400000
BOUNDARIES=[7*DAY_MS,30*DAY_MS,60*DAY_MS]
OUTPUT=['recency_band','frequency_band','visitor_ids','candidate_baskets','top1_baskets','top1_share_pct','top5_baskets','top5_share_pct','check_status']
RANKED_FIELDS=['visitorid','basket_count','last_transaction_ms','recency_ms','recency_band','frequency_band','cell_rank','global_rank']
R_BANDS=['R_LT_7D','R_7_TO_LT_30D','R_30_TO_LT_60D','R_GE_60D']
F_BANDS=['F_1','F_2','F_3_4','F_5_PLUS']
LABELS=[(r,f) for r in R_BANDS for f in F_BANDS]+[('TOTAL','TOTAL')]
RANKED_CAP=100000


def concentration_reference(rows):
    assert len({row[:3] for row in rows})==len(rows)
    basket_items=Counter(row[:2] for row in rows);visitor_baskets=defaultdict(set);latest={}
    for row in rows:
        assert isinstance(row[4],int) and SOURCE_MIN_MS<=row[4]<=REFERENCE_MS
        visitor_baskets[row[0]].add(row[:2])
        latest[row[0]]=max(latest.get(row[0],SOURCE_MIN_MS),row[4])
    assert 0<len(latest)<=RANKED_CAP
    rf=[];groups={label:[] for label in LABELS[:-1]}
    for visitor in sorted(latest):
        frequency=len(visitor_baskets[visitor]);stamp=latest[visitor];recency=REFERENCE_MS-stamp
        r_label=R_BANDS[sum(recency>=boundary for boundary in BOUNDARIES)]
        f_label='F_1' if frequency==1 else 'F_2' if frequency==2 else 'F_3_4' if frequency<=4 else 'F_5_PLUS'
        assert 0<=recency<=REFERENCE_MS-SOURCE_MIN_MS and recency+stamp==REFERENCE_MS
        record=(visitor,frequency,stamp,recency,r_label,f_label)
        rf.append(record);groups[(r_label,f_label)].append(record)
    stats=dict(memberships=len(rows),baskets=len(basket_items),single_baskets=sum(value==1 for value in basket_items.values()),
        multi_baskets=sum(value>1 for value in basket_items.values()),max_items=max(basket_items.values(),default=None),visitor_ids=len(latest))
    ordered_all=sorted(rf,key=lambda row:(-row[1],row[0]));global_ranks={row[0]:rank for rank,row in enumerate(ordered_all,1)}
    cell_ranks={}
    for group in groups.values():
        for rank,row in enumerate(sorted(group,key=lambda row:(-row[1],row[0])),1):cell_ranks[row[0]]=rank
    ranked=[row+(cell_ranks[row[0]],global_ranks[row[0]]) for row in rf]
    groups[('TOTAL','TOTAL')]=rf
    report=[]
    for labels in LABELS:
        group=sorted(groups[labels],key=lambda row:(-row[1],row[0]));n=len(group);baskets=sum(row[1] for row in group)
        top1=group[0][1] if group else 0;top5=sum(row[1] for row in group[:5])
        assert 0<=top1<=top5<=baskets and (n>5 or top5==baskets)
        report.append(dict(zip(OUTPUT,[*labels,n,baskets,top1,Fraction(100*top1,baskets) if baskets else None,
            top5,Fraction(100*top5,baskets) if baskets else None,'PASS'])))
    assert sum(row['visitor_ids'] for row in report[:-1])==report[-1]['visitor_ids']==stats['visitor_ids']
    assert sum(row['candidate_baskets'] for row in report[:-1])==report[-1]['candidate_baskets']==stats['baskets']
    return stats,ranked,report,counts.canonical_hash(rf)


def compare_report(observed,expected):
    assert len(observed)==len(expected)==17
    for actual,wanted in zip(observed,expected):
        assert list(actual)==OUTPUT
        for key in OUTPUT:
            if key not in ['top1_share_pct','top5_share_pct'] or wanted[key] is None:
                assert actual[key]==wanted[key],'Private concentration label/count/NULL/status differs; values withheld'
            else:
                assert math.isfinite(actual[key]) and abs(actual[key]-float(wanted[key]))<=DISPLAY_TOL,'Private concentration share differs; values withheld'
                assert abs(actual[key]*1e6-round(actual[key]*1e6))<=1e-5


def adjusted(sql,stats):
    query=counts.adjusted(sql,stats)
    query,n=re.subn(r'\b[0-9]+::BIGINT AS expected_visitor_ids\b',f"{stats['visitor_ids']}::BIGINT AS expected_visitor_ids",query);assert n==1
    return query


def ranked_stream_sql(sql):
    assert sql.count('), rank_cells AS (')==1
    return sql.split('), rank_cells AS (',1)[0]+')\nSELECT '+','.join(RANKED_FIELDS)+' FROM visitor_ranked ORDER BY visitorid;'


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--duckdb',required=True)
    parser.add_argument('--output',required=True);args=parser.parse_args()
    root=Path(__file__).resolve().parents[1];output=(root/args.output).resolve()
    script_path='sql/88_analyze_retailrocket_rf_basket_concentration.sql'
    validator_path='validation/preflight_retailrocket_rf_basket_concentration.py';method_path='docs/RETAILROCKET_RF_BASKET_CONCENTRATION_VALIDATION.md'
    assert output==(root/'data/retailrocket_rf_basket_concentration_preflight.json').resolve()
    old_path='data/retailrocket_visitor_rf_segments_preflight.json';accepted_path='data/retailrocket_visitor_rf_segments_learner_acceptance.json'
    old=json.loads((root/old_path).read_text(encoding='utf-8'));accepted=json.loads((root/accepted_path).read_text(encoding='utf-8'))
    assert accepted['acceptance_status']=='accepted' and accepted['script']=='sql/87_analyze_retailrocket_visitor_rf_segments.sql'
    assert accepted['report_sha256']==old['report_sha256'] and accepted['assistant_preflight_sha256']==source_reference.sha256(root/old_path)
    assert old['reference_endpoint_ms']==REFERENCE_MS and old['reference_endpoint_utc']==REFERENCE_UTC
    assert old['source_lower_timestamp_ms']==SOURCE_MIN_MS and old['accepted_SQL86_fixed_endpoint_provenance_reused']
    assert old['independent_visitor_RF_rows_compared']==11719 and old['independent_visitor_RF_fields_compared']==6
    assert old['independent_visitor_RF_all_matched']
    for proof in [old,accepted]:
        total=proof['results'][-1];assert [total['visitor_ids'],total['candidate_baskets']]==[11719,17672]
    deps=list(old['code_and_dependency_sha256'])+[script_path,validator_path,old_path,accepted_path,
        'docs/RETAILROCKET_VISITOR_RF_SEGMENTS_VALIDATION.md']
    hashes={name:source_reference.sha256(root/name) for name in deps}
    assert all(hashes[name]==digest for name,digest in old['code_and_dependency_sha256'].items())
    assert hashes[accepted_path]=='4ede984e7aa6c0a927a94cf670ff46fb03060036eade780c2b5e00b6e2523e2c'
    assert hashes['docs/RETAILROCKET_VISITOR_RF_SEGMENTS_VALIDATION.md']=='aac919e215eb5a619bdc0b6587b584c41915ba4494612e6738201389a3bf95d2'
    contract=(root/method_path).read_bytes().split(b'\n## Executed results\n',1)[0]
    assert hashlib.sha256(contract).hexdigest()==CONTRACT_SHA
    sql=(root/script_path).read_text(encoding='utf-8');clean=re.sub(r'--[^\n]*','',sql)
    assert clean.lstrip().startswith('WITH ') and not re.search(r'\b(CREATE|INSERT|UPDATE|DELETE|DROP|ALTER|COPY|SET|ATTACH|DETACH|LIMIT|CURRENT_DATE|CURRENT_TIMESTAMP|NOW)\b',clean,re.I)
    assert 'last_timestamp_ms' in clean and all(name not in clean for name in ['first_timestamp_ms','source_event_rows','rr_stg','rr_core','categoryid','available','pair_counts','selected_pairs'])
    stream_sql=ranked_stream_sql(sql)
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
            raise AssertionError('Private association CLI failure: '+category+'; row-bearing details withheld')
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
        return counts.canonical_hash(actual),seconds,path.stat().st_size
    def compare_ranked(folder,database,query,expected):
        started=time.perf_counter();expired=threading.Event();count=0;sentinel=object();digest=hashlib.sha256()
        process=subprocess.Popen([args.duckdb,str(database),'-bail','-readonly','-csv','-noheader'],stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,encoding='utf-8')
        def expire():expired.set();process.kill()
        timer=threading.Timer(120,expire);timer.start()
        try:
            process.stdin.write(settings(folder,database)+query);process.stdin.close()
            for observed,wanted in zip_longest(csv.reader(process.stdout,strict=True),expected,fillvalue=sentinel):
                assert observed is not sentinel and wanted is not sentinel,'Private ranked row count differs'
                assert len(observed)==8 and count<RANKED_CAP
                actual=tuple(int(value) for value in observed[:4])+tuple(observed[4:6])+tuple(int(value) for value in observed[6:])
                assert actual==wanted,'Private ranked tuple differs; identifiers withheld'
                digest.update((json.dumps(actual,separators=(',',':'))+'\n').encode());count+=1
            assert process.wait(timeout=120)==0 and not expired.is_set()
        finally:
            timer.cancel()
            if process.poll() is None:process.kill();process.wait()
            process.stdout.close()
        observe(folder)
        return dict(rows=count,fields=8,sha256=digest.hexdigest()),round(time.perf_counter()-started,3)

    # One narrow concentration family: occupied cell sizes 7, 6, 4 and 5.
    groups=[(3,[12,10,8,7,6,6,5]),(15,[1]*6),(45,[2]*4),(90,[3]*5)]
    rows=[];visitor=0
    for days,frequencies in groups:
        for frequency in frequencies:
            visitor+=1
            for basket in range(1,frequency+1):
                stamp=REFERENCE_MS-days*DAY_MS-(basket-1)*1000
                rows.append((visitor,basket,100+visitor,stamp-1000,stamp,7))
    rows.append((1,1,999,REFERENCE_MS-4*DAY_MS,REFERENCE_MS-3*DAY_MS,7));rows.sort()
    stats,records,expected,rf_hash=concentration_reference(rows)
    assert [stats[name] for name in ['memberships','baskets','single_baskets','multi_baskets','max_items','visitor_ids']]==[84,83,82,1,2,22]
    assert expected[-1]['top1_baskets']==12 and expected[-1]['top5_baskets']==43
    assert sum(row['top1_baskets'] for row in expected[:-1])==18
    assert sum(row['top5_baskets'] for row in expected[:-1])==71
    assert records[4][6:]==(5,5) and records[5][6:]==(6,6)
    assert [row[6] for row in records[7:13]]==list(range(1,7))
    empty_cells=sum(row['visitor_ids']==0 for row in expected[:-1]);assert empty_cells==12
    cases=[]
    with tempfile.TemporaryDirectory(prefix='rr-rf-concentration-fixture-',dir=tmp_root) as temporary:
        folder,database=Path(temporary),Path(temporary)/'fixture.duckdb';load_memberships(folder,database,rows)
        query=adjusted(sql,stats);before_db=source_reference.sha256(database)
        report,_=execute(folder,database,query,readonly=True);compare_report(report,expected)
        proof,_=compare_ranked(folder,database,ranked_stream_sql(query),iter(records))
        assert proof['rows']==22 and source_reference.sha256(database)==before_db
        assert all(row['candidate_baskets']==row['top1_baskets']==row['top5_baskets']==0 and row['top1_share_pct'] is None
            and row['top5_share_pct'] is None for row in report[:-1] if row['visitor_ids']==0)
        assert all(row['top5_share_pct']==100 for row in report if 0<row['visitor_ids']<=5)
        blocked,_=execute(folder,database,'BEGIN;UPDATE rr_mart.transaction_basket_items SET last_timestamp_ms=NULL WHERE visitorid=1;'+query+'ROLLBACK;')
        assert [(row['recency_band'],row['frequency_band']) for row in blocked]==LABELS
        assert all(row['check_status']=='BLOCKED' and all(row[key] is None for key in OUTPUT[2:-1]) for row in blocked)
        bad_rank=query.replace('ROW_NUMBER() OVER (PARTITION BY recency_band,frequency_band ORDER BY basket_count DESC,visitorid ASC)',
            'RANK() OVER (PARTITION BY recency_band,frequency_band ORDER BY basket_count DESC)')
        assert bad_rank!=query
        bad_top=query.replace('v.cell_rank<=5','v.cell_rank<=4');assert bad_top!=query
        for broken in [bad_rank,bad_top]:
            failed,_=execute(folder,database,broken,readonly=True)
            assert [(row['recency_band'],row['frequency_band']) for row in failed]==LABELS
            assert all(row['check_status']=='FAIL' and all(row[key] is None for key in OUTPUT[2:-1]) for row in failed)
        cases.append(dict(case='tied_fifth_cutoff_F1_ties_small_exact5_large_cells_dense_NULL_shares_global_rerank_and_masking',passed=True,
            memberships=84,candidate_baskets=83,visitor_ids=22,private_ranked_fields=8,empty_cells=12,invalid_control_subcases=3))
    assert not folder.exists()
    print(json.dumps({'fixture_families_passed':len(cases),'invalid_control_subcases':3}),flush=True)

    before={'events.csv':staging.snapshot(source)}
    assert all(before['events.csv'][key]==source_audit['source_before']['events.csv'][key]==source_audit['source_after']['events.csv'][key]
        for key in ['size_bytes','modified_time_ns','sha256'])
    historical={str(p.relative_to(root)):source_reference.sha256(p) for p in (root/'data').glob('*preflight.json') if p.resolve()!=output.resolve()}
    assert len(historical)==86
    started=time.perf_counter();rows,source_counts=counts.scan_source(source);source_seconds=round(time.perf_counter()-started,3)
    assert source_counts==old['independent_python_source_counts'] and len(rows)==22323
    input_hash=counts.canonical_hash(rows);assert input_hash==old['accepted_SQL79_membership_sha256']
    started=time.perf_counter();stats,records,expected,rf_hash=concentration_reference(rows);reference_seconds=round(time.perf_counter()-started,3)
    assert [stats[name] for name in ['memberships','baskets','single_baskets','multi_baskets','max_items','visitor_ids']]==[22323,17672,15029,2643,31,11719]
    assert rf_hash==old['independent_visitor_RF_stream_sha256']
    for proof in [old,accepted]:
        assert [(row['recency_band'],row['frequency_band'],row['visitor_ids'],row['candidate_baskets']) for row in expected]==[
            (row['recency_band'],row['frequency_band'],row['visitor_ids'],row['candidate_baskets']) for row in proof['results']]
    print(json.dumps({'phase':'single canonical parse, accepted memberships and RF fingerprint/cell totals matched'}),flush=True)
    with tempfile.TemporaryDirectory(prefix='rr-rf-concentration-real-',dir=tmp_root) as temporary:
        folder,database=Path(temporary),Path(temporary)/'preflight.duckdb'
        readback_hash,load_seconds,csv_bytes=load_memberships(folder,database,rows);assert readback_hash==input_hash
        database_before=source_reference.sha256(database)
        report,query_seconds=execute(folder,database,sql,readonly=True);compare_report(report,expected)
        assert Counter(row['check_status'] for row in report)==Counter(PASS=17)
        proof,stream_seconds=compare_ranked(folder,database,stream_sql,iter(records))
        assert proof['rows']==11719 and proof['sha256']==counts.canonical_hash(records)
        database_after=source_reference.sha256(database);assert database_before==database_after;database_bytes=database.stat().st_size
    assert not folder.exists()
    after={'events.csv':staging.snapshot(source)}
    assert before==after and all(source_reference.sha256(root/name)==digest for name,digest in hashes.items())
    assert all(source_reference.sha256(root/name)==digest for name,digest in historical.items())
    assert (root/method_path).read_bytes().startswith(contract)
    evidence=dict(checked_at_utc=datetime.now(timezone.utc).isoformat(),executor='assistant',engine=subprocess.check_output([args.duckdb,'-version'],text=True).strip(),
        script=script_path,script_sha256=hashes[script_path],validator=validator_path,validator_sha256=hashes[validator_path],code_and_dependency_sha256=hashes,
        method_contract=method_path,method_contract_prefix_bytes=len(contract),method_contract_prefix_sha256=CONTRACT_SHA,
        source_files=['events.csv'],source_before=before,source_after=after,source_hashes_and_metadata_unchanged=True,
        source_table='rr_mart.transaction_basket_items',readset_fields=READSET,required_readset_columns=4,
        private_input_fields=model.FIELDS,private_input_rows=len(rows),private_input_columns=6,
        reconstructed_membership_sha256=input_hash,accepted_SQL79_membership_sha256=old['accepted_SQL79_membership_sha256'],
        accepted_SQL79_membership_fingerprint_matched=True,private_input_readback_sha256=readback_hash,private_input_readback_matched=True,
        accepted_original_five_field_proof_reused=True,accepted_SQL87_RF_fingerprint=rf_hash,accepted_SQL87_RF_fingerprint_matched=True,
        accepted_SQL87_cell_and_TOTAL_counts_matched=True,accepted_fixed_endpoint_provenance_reused=True,
        reference_endpoint_ms=REFERENCE_MS,reference_endpoint_utc=REFERENCE_UTC,source_lower_timestamp_ms=SOURCE_MIN_MS,
        reference_endpoint_scope='Frozen global observed event endpoint, not a confirmed collection cutoff.',reference_is_today=False,reference_is_latest_transaction_timestamp=False,
        original_five_field_occurrence_comparison_rerun=False,original_event_external_sort_rerun=False,
        SQL54_rerun=False,SQL63_rerun=False,SQL64_rerun=False,SQL70_rerun=False,SQL79_rerun=False,SQL80_rerun=False,SQL81_rerun=False,SQL82_rerun=False,SQL83_rerun=False,SQL84_rerun=False,SQL85_rerun=False,SQL86_rerun=False,SQL87_rerun=False,
        old_frequency_recency_RF_pair_or_month_streams_recompared=False,previous_RF_boundary_fixtures_rerun=False,
        stored_last_timestamp_ms_in_query_readset=True,stored_first_timestamp_and_source_count_in_query_readset=False,
        property_files_read=False,category_csv_read=False,enriched_fact_read=False,learner_database_opened=False,query_read_only=True,private_ranked_stream_read_only=True,
        integrated_fixture_and_real_run_count=1,real_source_attempts=1,real_event_csv_parse_passes=1,real_cli_phases=3,
        real_private_input_load_executions=1,real_analysis_script_executions=1,real_private_ranked_stream_executions=1,
        report_rows=17,report_columns=9,output_columns=OUTPUT,checks_passed=17,fail_rows=0,blocked_rows=0,results=report,
        report_sha256=counts.canonical_hash([[row[key] for key in OUTPUT] for row in report]),
        report_fingerprint_contract='SHA-256 of returned compact JSON arrays in output-column order followed by LF; dense cells, NULL shares and independently ranked TOTAL preserved.',
        independent_python_source_counts=source_counts,independent_python_concentration_scope_counts=stats,
        independent_python_report_matched_with_display_tolerance=True,labels_counts_NULLs_and_status_compared_exactly=True,
        report_display_absolute_tolerance=DISPLAY_TOL,report_display_decimal_places=6,
        independent_ranked_rows_compared=proof['rows'],independent_ranked_fields_compared=8,private_ranked_columns=RANKED_FIELDS,
        independent_ranked_six_integer_fields_two_labels_exact=True,independent_ranked_stream_sha256=proof['sha256'],independent_ranked_all_matched=True,
        ranked_stream_sql_sha256=hashlib.sha256(stream_sql.encode()).hexdigest(),candidate_basket_key=['visitorid','transactionid'],
        full_composite_basket_keys_counted_once=True,last_transaction_MAX_across_all_memberships=True,integer_elapsed_ms_before_classification=True,
        recency_day_ms=DAY_MS,raw_ms_boundaries=BOUNDARIES,recency_bands=R_BANDS,frequency_bands=F_BANDS,
        dense_cells=16,dense_order='R major, F minor; then TOTAL/TOTAL',empty_cells=sum(row['visitor_ids']==0 for row in report[:-1]),
        matrix_visitor_sum=11719,matrix_candidate_basket_sum=17672,
        ranking_order='basket_count DESC, visitorid ASC',rank_method='ROW_NUMBER',top5_ids_per_row='min(5,visitor_ids)',
        deterministic_tie_break_verified=True,cell_and_global_rankings_compared_exactly=True,
        concentration_share_denominator='Each row candidate_baskets; TOTAL uses all 17672.',
        cell_baskets_sum_full_window_visitor_frequency=True,cell_baskets_restricted_to_recency_interval=False,
        TOTAL_ranked_globally_again=True,TOTAL_top_counts_summed_from_cell_tops=False,
        empty_cell_counts_zero_and_shares_NULL=True,small_cell_top5_share_100_by_construction=True,
        population='Transaction-recorded visitor IDs only; not all event visitors or non-purchasers.',
        all_event_visitors_in_denominator=False,nontransaction_visitors_included=False,
        customer_value_loyalty_churn_fraud_or_bot_classification_claimed=False,monetary_analysis_performed=False,RFM_claimed=False,
        thresholds_optimized=False,finite_window_and_unequal_visitor_exposure_acknowledged=True,
        retained_transaction_occurrences=source_counts['transaction'],transaction_occurrence_cap=counts.TRANSACTION_CAP,ranked_row_cap=RANKED_CAP,
        private_database_sha256_before_readonly=database_before,private_database_sha256_after_readonly=database_after,private_database_bytes_unchanged=True,
        fixture_case_count=len(cases),fixture_cases=cases,invalid_control_fixture_subcases=3,
        fifth_cutoff_and_F1_ties_verified=True,small_exact5_large_cells_verified=True,
        dense_empty_NULL_shares_verified=True,global_vs_sum_of_cell_tops_distinction_verified=True,
        invalid_source_BLOCKED_verified=True,duplicate_rank_and_wrong_top_selection_FAIL_verified=True,
        preflight_settings=dict(threads=2,memory_limit='1GB',max_temp_directory_size='2GB',timeout_seconds_per_cli_phase=120,
            transaction_occurrence_cap=counts.TRANSACTION_CAP,ranked_row_cap=RANKED_CAP,
            minimum_free_bytes=8*1024**3,private_directory_budget_bytes=7*1024**3),
        private_input_csv_bytes=csv_bytes,private_database_bytes_before_cleanup=database_bytes,
        largest_private_directory_bytes_observed_after_phase=max(sizes),workspace_free_bytes_before=free_before,workspace_free_bytes_after=shutil.disk_usage(tmp_root).free,
        temporary_databases_and_spills_removed=True,private_membership_csv_removed=True,historical_preflight_files_unchanged=len(historical),
        historical_comparison_or_analysis_suites_rerun=False,source_records_or_identifiers_uploaded_or_logged=False,raw_visitor_identifiers_published=False,
        elapsed_python_source_scan_reconstruction_seconds=source_seconds,elapsed_python_concentration_reference_seconds=reference_seconds,
        elapsed_private_input_load_readback_seconds=load_seconds,elapsed_readonly_concentration_report_seconds=query_seconds,elapsed_private_ranked_stream_seconds=stream_seconds,
        timing_scope='One integrated narrow fixture family then one canonical parse and new Python cell/global ranking; three real CLI phases. Old result streams and boundary suites not repeated.',
        scope='Assistant SQL88 preparation passed; learner execution pending. Descriptive within-RF-cell basket concentration with globally recomputed TOTAL; no value, fraud, churn, monetary RFM or causal effect classification.')
    output.write_text(json.dumps(evidence,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps({'report_rows':17,'checks_passed':17,'ranked_rows_compared':proof['rows'],
        'ranked_fields':8,'report_sha256':evidence['report_sha256']}),flush=True)


if __name__=='__main__':main()
