"""Verify exact paired-series improvement coverage using immutable development diagnostics."""
import argparse
import csv
import hashlib
import json
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP, localcontext
from pathlib import Path

sys.dont_write_bytecode = True
from preflight_forecast_scope_and_time_audit import (
    FIRST_DATE, ORIGINS, FROZEN_MEMBERSHIP, DAILY_FIELDS, METADATA_FIELDS, quote, sha256, json_hash,
    membership_hash, original_reference, export_snapshots, compare_csv,
)
from preflight_seasonal_naive_forecasts import (
    FORECAST_COLUMNS as S7_COLUMNS, FORECAST_QUERY as S7_QUERY, forecast_reference as s7_reference,
    forecast_report as s7_report, canonical_report as canonical_s7_report, read_forecast_csv as read_s7_csv,
)
from preflight_weekday_mean_forecasts import (
    FORECAST_COLUMNS as W4_COLUMNS, FORECAST_QUERY as W4_QUERY, forecast_reference as w4_reference,
    forecast_report as w4_report, canonical_report as canonical_w4_report,
    canonical_forecasts as canonical_w4_forecasts, read_forecast_csv as read_w4_csv,
)
from preflight_development_forecast_errors import (
    independent_errors, canonical_report as canonical_development_report, exact_diagnostic_hash, six,
)

PAIRED_COLUMNS = ['origin','item_id','store_id','snaive_absolute_error_quarters','weekday4_absolute_error_quarters',
                  'snaive_squared_error_sixteenths','weekday4_squared_error_sixteenths','mae_delta_quarters',
                  'first_positive_day','scale_diff_count','training_sse','rmsse_status','snaive_rmsse','weekday4_rmsse',
                  'rmsse_delta','mae_winner','rmsse_winner']
REPORT_COLUMNS = ['origin','metric','total_series','compared_series','excluded_series','weekday4_wins','ties','snaive7_wins',
                  'weekday4_win_pct','mean_delta','median_delta','check_status']
FLOAT_FIELDS = ['snaive_rmsse','weekday4_rmsse','rmsse_delta']
ABS_TOL=Decimal('1e-12')
REL_TOL=Decimal('1e-13')


def paired_reference(diagnostics):
    indexed={(d['origin'],d['model'],d['item_id'],d['store_id']):d for d in diagnostics}
    keys=sorted({(d['origin'],d['item_id'],d['store_id']) for d in diagnostics})
    rows=[]
    with localcontext() as ctx:
        ctx.prec=70
        for origin,item,store in keys:
            a=indexed[(origin,'SNAIVE7',item,store)];b=indexed[(origin,'WEEKDAY4',item,store)]
            for field in ('actual_units','evaluated_rows','first_positive_day','scale_diff_count','training_sse','rmsse_status'):
                assert a[field]==b[field]
            assert a['evaluated_rows']==28
            valid=a['rmsse_status']=='VALID'
            def winner(x,y):
                return 'WEEKDAY4' if y<x else 'TIE' if y==x else 'SNAIVE7'
            rows.append(dict(origin=origin,item_id=item,store_id=store,
                snaive_absolute_error_quarters=a['absolute_error_quarters'],weekday4_absolute_error_quarters=b['absolute_error_quarters'],
                snaive_squared_error_sixteenths=a['squared_error_sixteenths'],weekday4_squared_error_sixteenths=b['squared_error_sixteenths'],
                mae_delta_quarters=b['absolute_error_quarters']-a['absolute_error_quarters'],first_positive_day=a['first_positive_day'],
                scale_diff_count=a['scale_diff_count'],training_sse=a['training_sse'],rmsse_status=a['rmsse_status'],
                snaive_rmsse=a['rmsse'],weekday4_rmsse=b['rmsse'],rmsse_delta=b['rmsse']-a['rmsse'] if valid else None,
                mae_winner=winner(a['absolute_error_quarters'],b['absolute_error_quarters']),
                rmsse_winner=winner(a['squared_error_sixteenths'],b['squared_error_sixteenths']) if valid else None))
        report=[];full_rmsse=[]
        for origin,_ in ORIGINS[:3]:
            origin_rows=[r for r in rows if r['origin']==origin]
            for metric in ('MAE','RMSSE'):
                group=origin_rows if metric=='MAE' else [r for r in origin_rows if r['rmsse_status']=='VALID']
                n=len(group);winner_key='mae_winner' if metric=='MAE' else 'rmsse_winner'
                wins=sum(r[winner_key]=='WEEKDAY4' for r in group);ties=sum(r[winner_key]=='TIE' for r in group)
                losses=sum(r[winner_key]=='SNAIVE7' for r in group)
                if not n:
                    mean=median=pct=None
                else:
                    values=sorted(r['mae_delta_quarters'] if metric=='MAE' else r['rmsse_delta'] for r in group)
                    central=[values[i] for i in sorted({(n-1)//2,n//2})]
                    denominator=Decimal(112) if metric=='MAE' else Decimal(1)
                    mean=Decimal(sum(values))/Decimal(n)/denominator
                    median=Decimal(sum(central))/Decimal(len(central))/denominator
                    pct=format((Decimal(wins)*100/Decimal(n)).quantize(Decimal('.0001'),rounding=ROUND_HALF_UP),'.4f')
                report.append(dict(origin=origin,metric=metric,total_series=len(origin_rows),compared_series=n,
                    excluded_series=len(origin_rows)-n,weekday4_wins=wins,ties=ties,snaive7_wins=losses,
                    weekday4_win_pct=pct,mean_delta=six(mean),median_delta=six(median),check_status='PASS'))
                if metric=='RMSSE':
                    full_rmsse.append(dict(origin=origin,mean_delta=mean,median_delta=median))
    return rows,report,full_rmsse


def canonical_report(rows):
    result=[]
    for row in rows:
        assert list(row)==REPORT_COLUMNS
        normalized=dict(row)
        for key in ('total_series','compared_series','excluded_series','weekday4_wins','ties','snaive7_wins'):
            normalized[key]=int(row[key])
        for key,places in [('weekday4_win_pct',4),('mean_delta',6),('median_delta',6)]:
            value=None if row[key] is None else Decimal(str(row[key]))
            normalized[key]=None if value is None else format(abs(value) if value==0 else value,f'.{places}f')
        result.append(normalized)
    return result


def exact_pair_hash(rows):
    return json_hash([{k:v for k,v in r.items() if k not in FLOAT_FIELDS} for r in rows])


def copy_query(query,path):
    return f"COPY ({query}) TO {quote(path.as_posix())} (HEADER, DELIMITER ',');"


def internal_exports(prefix,folder):
    paths={'pairs':folder/'pairs.csv','aggregates':folder/'paired-aggregates.csv'}
    selects={
        'pairs':f"SELECT {','.join(PAIRED_COLUMNS)} FROM paired_series ORDER BY origin,item_id,store_id",
        'aggregates':"SELECT o.origin,AVG(p.rmsse_delta) AS mean_delta,MEDIAN(p.rmsse_delta) AS median_delta FROM development_origins o LEFT JOIN paired_series p ON p.origin=o.origin AND p.rmsse_status='VALID' GROUP BY o.origin ORDER BY o.origin",
    }
    return paths,'\n'.join(copy_query(prefix+select,paths[key]) for key,select in selects.items())


def compare_internal(paths,expected):
    text_fields={'origin','item_id','store_id','rmsse_status','mae_winner','rmsse_winner'}
    with paths['pairs'].open(newline='',encoding='utf-8') as stream:
        reader=csv.DictReader(stream);assert reader.fieldnames==PAIRED_COLUMNS
        actual=[]
        for row in reader:
            for key in PAIRED_COLUMNS:
                row[key]=None if row[key]=='' else row[key] if key in text_fields else Decimal(row[key]) if key in FLOAT_FIELDS else int(row[key])
            actual.append(row)
    assert len(actual)==len(expected[0])
    assert exact_pair_hash(actual)==exact_pair_hash(expected[0]),'Exact pairing, eligibility or winner differs'
    maximum=Decimal(0)
    for a,e in zip(actual,expected[0]):
        for key in FLOAT_FIELDS:
            assert (a[key] is None)==(e[key] is None)
            if e[key] is not None:
                error=abs(a[key]-e[key]);assert a[key].is_finite() and error<=ABS_TOL+REL_TOL*abs(e[key]),(key,'full precision differs')
                maximum=max(maximum,error)
    with paths['aggregates'].open(newline='',encoding='utf-8') as stream:
        aggregates=list(csv.DictReader(stream))
    assert len(aggregates)==len(expected[2]);aggregate_max=Decimal(0)
    for a,e in zip(aggregates,expected[2]):
        assert a['origin']==e['origin']
        for key in ('mean_delta','median_delta'):
            value=None if a[key]=='' else Decimal(a[key])
            assert (value is None)==(e[key] is None)
            if value is not None:
                error=abs(value-e[key]);assert value.is_finite() and error<=ABS_TOL+REL_TOL*abs(e[key])
                aggregate_max=max(aggregate_max,error)
    return maximum,aggregate_max


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--duckdb',required=True)
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--fixtures-only',action='store_true')
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    tmp_root=root/'tmp';tmp_root.mkdir(exist_ok=True)
    assert tmp_root.resolve().is_relative_to(root.resolve())
    sql_path=root/'sql/37_compare_series_forecast_improvements.sql'
    sql_bytes=sql_path.read_bytes();query=sql_bytes.decode('utf-8')
    internal_prefix=query.split('-- REPORT:',1)[0]
    dependencies=['sql/08_stage_calendar.sql','sql/12_build_product_dimension.sql','sql/13_build_store_dimension.sql',
                  'sql/14_build_calendar_dimension.sql','sql/33_forecast_scope_and_time_audit.sql',
                  'sql/34_build_seasonal_naive_forecasts.sql','sql/35_build_weekday_mean_forecasts.sql',
                  'sql/36_compare_development_forecast_errors.sql']
    scripts={p:(root/p).read_bytes() for p in dependencies}
    builds={number:scripts[path].decode('utf-8').split('-- VALIDATION:',1)[0] for number,path in
            [('34','sql/34_build_seasonal_naive_forecasts.sql'),('35','sql/35_build_weekday_mean_forecasts.sql')]}
    validations={number:'-- VALIDATION:'+scripts[path].decode('utf-8').split('-- VALIDATION:',1)[1] for number,path in
                 [('34','sql/34_build_seasonal_naive_forecasts.sql'),('35','sql/35_build_weekday_mean_forecasts.sql')]}
    scope=scripts['sql/33_forecast_scope_and_time_audit.sql'].decode('utf-8')
    scope_prefix=scope[scope.index('WITH parameters AS ('):scope.index('\nSELECT o.origin,s.dept_id,s.store_id,t.series_count')]
    assert query.count(scope_prefix)==1
    development_sql=scripts['sql/36_compare_development_forecast_errors.sql'].decode('utf-8')
    development_prefix=development_sql[development_sql.index('WITH parameters AS ('):development_sql.index('-- REPORT:')]
    assert query.count(development_prefix)==1
    helper_paths=['validation/preflight_forecast_scope_and_time_audit.py','validation/preflight_seasonal_naive_forecasts.py',
                  'validation/preflight_weekday_mean_forecasts.py','validation/preflight_development_forecast_errors.py']
    helper_hashes={p:sha256(root/p) for p in helper_paths}
    protocol_path=root/'docs/SERIES_FORECAST_IMPROVEMENTS_PROTOCOL.md'
    protocol_hash=sha256(protocol_path)
    historical={p.relative_to(root).as_posix():sha256(p) for p in (root/'data').glob('*_preflight.json')
                if p.name!='series_forecast_improvements_preflight.json'}
    cases=[]
    fixture_calendar={n:dict(d=f'd_{n}',date=(FIRST_DATE+timedelta(days=n-1)).isoformat(),day_number=n,wm_yr_wk=11000+n//7) for n in range(1,1970)}
    baseline={item:[n%5 for n in range(1,1914)] for item in ('P001','P002')}
    baseline_pairs=[(item,'CA_1') for item in sorted(baseline)]
    baseline_diagnostics=independent_errors(baseline_pairs,baseline,s7_reference('FOODS_1',baseline_pairs,baseline,fixture_calendar),w4_reference('FOODS_1',baseline_pairs,baseline,fixture_calendar))
    baseline_expected=paired_reference(baseline_diagnostics[1])
    def tiny(name,training=None,mutation='',reject=False,future_changed=False,future_absent=False):
        training=baseline if training is None else training
        pairs=[(item,'CA_1') for item in sorted(training)]
        def adapt(text):
            return text.replace('3049 AS expected_products,10 AS expected_stores',f'{len(pairs)+1} AS expected_products,2 AS expected_stores').replace(
                '216 AS expected_scope_series',f'{len(pairs)} AS expected_scope_series').replace(FROZEN_MEMBERSHIP,membership_hash(pairs))
        s7=s7_reference('FOODS_1',pairs,training,fixture_calendar);w4=w4_reference('FOODS_1',pairs,training,fixture_calendar)
        expected=paired_reference(independent_errors(pairs,training,s7,w4)[1])
        with tempfile.TemporaryDirectory(prefix='paired-improvement-fixture-',dir=tmp_root) as value:
            folder=Path(value).resolve();assert folder.is_relative_to(tmp_root.resolve())
            data=folder/'input.csv'
            with data.open('w',newline='',encoding='utf-8') as stream:
                writer=csv.writer(stream);writer.writerow(DAILY_FIELDS)
                for item,store in pairs:
                    for n in range(1,1914 if future_absent else 1942):
                        units=training[item][n-1] if n<=1913 else (-99 if item==pairs[0][0] else None) if future_changed else 0
                        writer.writerow([item,store,f'd_{n}','2016-01-01' if n>1913 and future_changed else fixture_calendar[n]['date'],fixture_calendar[n]['wm_yr_wk'],units])
            database=folder/'fixture.duckdb';settings="SET threads=2; SET memory_limit='2GB';\n"
            def execute(text):
                return subprocess.run([args.duckdb,str(database),'-bail','-json'],input=settings+text,text=True,encoding='utf-8',capture_output=True)
            product_values=','.join(f"({quote(item)},'FOODS_1','FOODS')" for item,_ in pairs)+",('OTHER','FOODS_2','FOODS')"
            setup=f"""CREATE SCHEMA raw; CREATE SCHEMA core; CREATE SCHEMA mart;
CREATE TABLE core.m5_product(item_id VARCHAR,dept_id VARCHAR,cat_id VARCHAR); INSERT INTO core.m5_product VALUES {product_values};
CREATE TABLE core.m5_store(store_id VARCHAR,state_id VARCHAR); INSERT INTO core.m5_store VALUES ('TX_1','TX'),('CA_1','CA');
CREATE TABLE raw.m5_sales_wide AS SELECT p.item_id,p.dept_id,p.cat_id,s.store_id,s.state_id FROM core.m5_product p CROSS JOIN core.m5_store s;
CREATE TABLE core.m5_calendar AS SELECT 'd_'||CAST(n AS VARCHAR) AS d,DATE '2011-01-29'+CAST(n AS INTEGER)-1 AS date,
CAST(n AS INTEGER) AS day_number,CAST(11000+n//7 AS INTEGER) AS wm_yr_wk FROM range(1,1970) t(n);
CREATE TABLE mart.m5_sales_daily AS SELECT item_id,store_id,d,CAST(date AS DATE) AS date,CAST(wm_yr_wk AS INTEGER) AS wm_yr_wk,
CAST(units AS INTEGER) AS units FROM read_csv({quote(data.as_posix())},header=true,all_varchar=true);
"""
            before,before_sql=export_snapshots(folder,'before');after,after_sql=export_snapshots(folder,'after')
            for key,candidate_query in [('s7',S7_QUERY),('w4',W4_QUERY)]:
                before[key]=folder/('before-'+key+'.csv');after[key]=folder/('after-'+key+'.csv')
                before_sql+=copy_query(candidate_query,before[key]);after_sql+=copy_query(candidate_query,after[key])
            run=execute(setup+adapt(builds['34'])+adapt(builds['35'])+mutation+before_sql)
            assert run.returncode==0,(name,run.stderr)
            run=execute(adapt(query))
            if reject:
                assert run.returncode!=0 and 'Paired improvement coverage blocked' in run.stderr,(name,run.stderr)
            else:
                assert run.returncode==0,(name,run.stderr)
                observed=canonical_report(json.loads(run.stdout,parse_float=Decimal))
                assert observed==expected[1],(name,'report mismatch',observed,expected[1])
                paths,export=internal_exports(adapt(internal_prefix),folder)
                run=execute(export);assert run.returncode==0,(name,run.stderr)
                compare_internal(paths,expected)
                mae,rmsse=observed[:2]
                if name=='wins_exact_ties_and_losses_same_series':
                    assert (mae['weekday4_wins'],mae['ties'],mae['snaive7_wins'])==(1,1,1)
                if name=='odd_median_is_middle_paired_difference':
                    assert mae['mean_delta']=='0.333333' and mae['median_delta']=='2.000000'
                if name=='even_median_averages_two_central_differences':
                    assert mae['mean_delta']==mae['median_delta']=='-1.000000'
                if name=='exact_rmsse_win_can_display_as_zero_delta':
                    assert rmsse['weekday4_wins']==1 and rmsse['ties']==1
                    assert rmsse['mean_delta']==rmsse['median_delta']=='0.000000'
                    assert any(r['rmsse_delta'] is not None and r['rmsse_delta']<0 for r in expected[0] if r['origin']=='DEVELOPMENT_1')
                if name=='undefined_scale_excluded_only_from_rmsse_denominator':
                    assert mae['compared_series']==2 and rmsse['compared_series']==1 and rmsse['excluded_series']==1
                    assert mae['weekday4_win_pct']=='50.0000' and rmsse['weekday4_win_pct']=='100.0000'
                if name=='all_zero_rmsse_cohort_retains_null_summaries':
                    assert mae['ties']==2 and mae['compared_series']==2
                    assert rmsse['compared_series']==0 and rmsse['excluded_series']==2
                    assert all(rmsse[k] is None for k in ('weekday4_win_pct','mean_delta','median_delta'))
                if name in ('final_holdout_changes_ignored','final_holdout_absence_ignored'):
                    assert expected==baseline_expected
            run=execute(after_sql);assert run.returncode==0,(name,run.stderr)
            assert all(sha256(before[key])==sha256(after[key]) for key in before),(name,'input changed')
        assert not folder.exists()
        cases.append(dict(case=name,passed=True,rejected=reject,source_and_saved_candidates_unchanged=True))

    def scenario(specifications):
        training={f'P{i+1:03d}':[1+n%2 for n in range(1,1914)] for i in range(len(specifications))}
        for (item,values),(blocks,target) in zip(training.items(),specifications):
            values[1801:1829]=[value for block in blocks for value in [block]*7]
            values[1829:1857]=[target]*28
        return training
    tiny('wins_exact_ties_and_losses_same_series',scenario([([0,0,0,4],1),([2,2,2,2],2),([0,0,0,4],4)]))
    tiny('odd_median_is_middle_paired_difference',scenario([([0,0,0,4],1),([4,4,8,0],1),([1,1,2,4],4)]))
    tiny('even_median_averages_two_central_differences',scenario([([0,0,0,4],1),([0,0,0,4],3)]))
    near={item:[2147483647 if n%2 else 0 for n in range(1,1914)] for item in ('P001','P002')}
    near['P001'][1801:1829]=[0]*21+[1]*7;near['P002'][1801:1829]=[0]*28
    near['P001'][1829:1857]=near['P002'][1829:1857]=[0]*28
    tiny('exact_rmsse_win_can_display_as_zero_delta',near)
    excluded=scenario([([0,0,0,4],1),([2,2,2,2],2)]);excluded['P002']=[2]*1913
    tiny('undefined_scale_excluded_only_from_rmsse_denominator',excluded)
    tiny('all_zero_rmsse_cohort_retains_null_summaries',{item:[0]*1913 for item in ('P001','P002')})
    tiny('final_holdout_changes_ignored',future_changed=True)
    tiny('final_holdout_absence_ignored',future_absent=True)
    tiny('missing_saved_candidate_row_rejected',mutation="DELETE FROM mart.m5_forecast_snaive7_28d WHERE origin='DEVELOPMENT_1' AND item_id='P001' AND horizon_day=1;",reject=True)
    tiny('corrupt_final_candidate_rejected_without_scoring_final_actuals',mutation="UPDATE mart.m5_forecast_weekday4_28d SET predicted_units=predicted_units+0.25 WHERE origin='FINAL_HOLDOUT' AND item_id='P001' AND horizon_day=1;",reject=True)
    print(json.dumps({'fixture_cases_passed':len(cases)}),flush=True)
    if args.fixtures_only:
        return

    source_root=Path('D:/database/m5-forecasting-accuracy')
    sources=[source_root/'sales_train_evaluation.csv',source_root/'calendar.csv']
    registry=json.loads((root/'data/m5_source_audit.json').read_text(encoding='utf-8'))
    source_hashes={p.name:sha256(p) for p in sources}
    assert all(source_hashes[p.name]==registry['files'][p.name]['sha256'] for p in sources)
    acceptance_paths=['data/seasonal_naive_forecasts_learner_acceptance.json','data/weekday_mean_forecasts_learner_acceptance.json','data/development_forecast_errors_learner_acceptance.json']
    accepted_bytes={p:(root/p).read_bytes() for p in acceptance_paths}
    accepted={p:json.loads(value.decode('utf-8')) for p,value in accepted_bytes.items()}
    timings={};started=time.perf_counter()
    calendar,metadata,products,stores,department,store,pairs,training=original_reference(*sources)
    s7=s7_reference(department,pairs,training,calendar);w4=w4_reference(department,pairs,training,calendar)
    development_expected=independent_errors(pairs,training,s7,w4)
    expected=paired_reference(development_expected[1])
    previous_preflight=json.loads((root/'data/development_forecast_errors_preflight.json').read_text(encoding='utf-8'))
    assert json_hash(development_expected[0])==previous_preflight['ordered_scored_rows_sha256']
    assert exact_diagnostic_hash(development_expected[1])==previous_preflight['ordered_exact_series_diagnostics_sha256']
    timings['independent_source_and_paired_reference_seconds']=round(time.perf_counter()-started,3)
    days=','.join(f'd_{n}' for n in range(1,1914))
    with tempfile.TemporaryDirectory(prefix='paired-improvement-source-',dir=tmp_root) as value:
        folder=Path(value).resolve();assert folder.is_relative_to(tmp_root.resolve())
        database=folder/'preflight.duckdb'
        settings=f"SET threads=2; SET memory_limit='2GB'; SET temp_directory={quote((folder/'spill').as_posix())};\n"
        def execute(text,label=None):
            start=time.perf_counter()
            run=subprocess.run([args.duckdb,str(database),'-bail','-json'],input=settings+text,text=True,encoding='utf-8',capture_output=True)
            assert run.returncode==0,run.stderr
            if label:
                timings[label]=round(time.perf_counter()-start,3)
            return json.loads(run.stdout,parse_float=Decimal) if run.stdout.strip() else None
        setup=f"""CREATE SCHEMA raw; CREATE SCHEMA mart;
CREATE TABLE raw.m5_sales_wide AS SELECT item_id,dept_id,cat_id,store_id,state_id FROM read_csv({quote(sources[0].as_posix())},header=true,all_varchar=true);
CREATE TABLE raw.m5_calendar AS SELECT * FROM read_csv({quote(sources[1].as_posix())},header=true,all_varchar=true);
"""
        setup+='\n'.join(scripts[p].decode('utf-8').split('-- VALIDATION:')[0] for p in dependencies[:4])
        setup+=f"""CREATE TABLE raw.training_wide AS SELECT item_id,store_id,{days}
FROM read_csv({quote(sources[0].as_posix())},header=true,all_varchar=true)
WHERE dept_id=(SELECT MIN(dept_id) FROM core.m5_product) AND store_id=(SELECT MIN(store_id) FROM core.m5_store);
CREATE TABLE mart.m5_sales_daily AS WITH u AS (SELECT item_id,store_id,d,units_text FROM raw.training_wide
UNPIVOT INCLUDE NULLS (units_text FOR d IN ({days})))
SELECT u.item_id,u.store_id,u.d,c.date,c.wm_yr_wk,
CASE WHEN regexp_full_match(u.units_text,'[0-9]+') AND TRY_CAST(u.units_text AS INTEGER)>=0
THEN CAST(u.units_text AS INTEGER) ELSE error('Original training integer contract failed') END AS units
FROM u JOIN core.m5_calendar c USING(d);
"""
        before,before_sql=export_snapshots(folder,'before');after,after_sql=export_snapshots(folder,'after')
        execute(setup,'private_source_setup_seconds')
        execute(builds['34']+builds['35'],'private_candidate_creation_seconds')
        for key,candidate_query in [('s7',S7_QUERY),('w4',W4_QUERY)]:
            before[key]=folder/('before-'+key+'.csv');after[key]=folder/('after-'+key+'.csv')
            before_sql+=copy_query(candidate_query,before[key]);after_sql+=copy_query(candidate_query,after[key])
        execute(before_sql,'private_input_and_candidate_export_seconds')
        counts={}
        counts['product_dimension']=compare_csv(before['product_dimension'],['item_id','dept_id','cat_id'],products,'original products')
        counts['store_dimension']=compare_csv(before['store_dimension'],['store_id','state_id'],stores,'original stores')
        counts['calendar_projection']=compare_csv(before['calendar_projection'],['d','date','day_number','wm_yr_wk'],
            ((calendar[n][k] for k in ('d','date','day_number','wm_yr_wk')) for n in range(1,1970)),'original calendar')
        counts['raw_metadata_projection']=compare_csv(before['raw_metadata_projection'],METADATA_FIELDS,
            sorted(metadata,key=lambda r:(r[0],r[3],r[1],r[2],r[4])),'original metadata')
        def original_daily():
            for item,selected_store in sorted(pairs):
                for n,units in enumerate(training[item],1):
                    yield item,selected_store,f'd_{n}',calendar[n]['date'],calendar[n]['wm_yr_wk'],units
        counts['selected_training_projection']=compare_csv(before['selected_training_projection'],DAILY_FIELDS,original_daily(),'original training fields')
        counts['s7']=compare_csv(before['s7'],S7_COLUMNS,(tuple(r[k] for k in S7_COLUMNS) for r in s7),'all original SNAIVE7 fields')
        counts['w4']=compare_csv(before['w4'],W4_COLUMNS,(tuple(r[k] for k in W4_COLUMNS) for r in w4),'all original WEEKDAY4 fields')
        observed_s7=read_s7_csv(before['s7']);observed_w4=read_w4_csv(before['w4'])
        assert observed_s7==s7 and observed_w4==w4
        candidate_hashes={'SNAIVE7':json_hash(observed_s7),'WEEKDAY4':json_hash(canonical_w4_forecasts(observed_w4))}
        assert candidate_hashes['SNAIVE7']==json.loads((root/'data/seasonal_naive_forecasts_preflight.json').read_text(encoding='utf-8'))['ordered_forecast_rows_sha256']
        assert candidate_hashes['WEEKDAY4']==json.loads((root/'data/weekday_mean_forecasts_preflight.json').read_text(encoding='utf-8'))['ordered_forecast_rows_sha256']
        candidate_reports={'SNAIVE7':canonical_s7_report(execute(validations['34'])),
                           'WEEKDAY4':canonical_w4_report(execute(validations['35']))}
        assert candidate_reports['SNAIVE7']==s7_report(department,store,pairs,training,calendar,s7)
        assert candidate_reports['WEEKDAY4']==w4_report(department,store,pairs,training,calendar,w4)
        candidate_report_hashes={model:json_hash(rows) for model,rows in candidate_reports.items()}
        assert candidate_report_hashes['SNAIVE7']==accepted[acceptance_paths[0]]['ordered_result_sha256']
        assert candidate_report_hashes['WEEKDAY4']==accepted[acceptance_paths[1]]['ordered_result_sha256']
        reconstructed_development=canonical_development_report(execute(development_sql,'accepted_development_report_seconds'))
        assert reconstructed_development==development_expected[2]
        assert json_hash(reconstructed_development)==accepted[acceptance_paths[2]]['ordered_result_sha256']
        actual_report=canonical_report(execute(query,'paired_improvement_query_seconds'))
        assert actual_report==expected[1],('Six displayed rows differ',actual_report,expected[1])
        paths,export=internal_exports(internal_prefix,folder)
        execute(export,'private_paired_diagnostic_export_seconds')
        maximum_pair_error,maximum_aggregate_error=compare_internal(paths,expected)
        assert len(expected[0])==648
        execute(after_sql,'unchanged_source_and_candidate_export_seconds')
        before_hashes={key:sha256(path) for key,path in before.items()};after_hashes={key:sha256(path) for key,path in after.items()}
        assert before_hashes==after_hashes
        database_bytes=database.stat().st_size
    assert not folder.exists()
    assert all(sha256(path)==source_hashes[path.name] for path in sources)
    assert sql_path.read_bytes()==sql_bytes
    assert all((root/path).read_bytes()==content for path,content in scripts.items())
    assert all(sha256(root/path)==value for path,value in helper_hashes.items())
    assert all(sha256(root/path)==value for path,value in historical.items())
    assert all((root/path).read_bytes()==value for path,value in accepted_bytes.items())
    assert sha256(protocol_path)==protocol_hash
    report=dict(
        checked_at_utc=datetime.now(timezone.utc).isoformat(),executor='assistant',engine=subprocess.check_output([args.duckdb,'-version'],text=True).strip(),
        script=sql_path.relative_to(root).as_posix(),script_sha256=hashlib.sha256(sql_bytes).hexdigest(),
        frozen_improvement_protocol=protocol_path.relative_to(root).as_posix(),frozen_improvement_protocol_sha256=protocol_hash,
        protocol_unchanged_during_preflight=True,
        dependency_script_sha256={path:hashlib.sha256(value).hexdigest() for path,value in scripts.items()},reference_helper_sha256=helper_hashes,
        accepted_evidence_sha256={path:hashlib.sha256(value).hexdigest() for path,value in accepted_bytes.items()},
        accepted_candidate_report_fingerprints_matched=True,reconstructed_candidate_report_sha256=candidate_report_hashes,
        accepted_candidate_forecast_fingerprints_matched=True,reconstructed_candidate_forecast_sha256=candidate_hashes,
        accepted_development_report_fingerprint_matched=True,reconstructed_development_report_sha256=json_hash(reconstructed_development),
        historical_development_diagnostic_fingerprints_matched=True,
        reconstructed_development_scored_rows_sha256=json_hash(development_expected[0]),
        reconstructed_development_exact_series_diagnostics_sha256=exact_diagnostic_hash(development_expected[1]),
        source_sha256=source_hashes,source_hashes_unchanged=True,historical_preflight_sha256=historical,historical_preflights_unchanged=True,
        accepted_sql36_cte_prefix_copies=1,accepted_sql36_cte_prefix_sha256=hashlib.sha256(development_prefix.encode()).hexdigest(),
        baseline_database='Private temporary DuckDB and detailed CSV exports under ignored repository tmp; resolved containment checked; all removed. Learner database never opened.',
        settings={'threads':2,'memory_limit':'2GB'},temporary_baseline_removed=True,temporary_database_bytes_after_close=database_bytes,
        frozen_scope={'dept_id':department,'store_id':store,'series_count':len(pairs),'series_membership_sha256':membership_hash(pairs)},
        comparison_scope='Pair SNAIVE7 and WEEKDAY4 for each of 216 identical item/store series at each of three development origins. Actual totals, 28 evaluation positions, first positive training day, scale count/SSE and eligibility must match.',
        exact_winner_rule='MAE uses absolute-error-quarter sums; RMSSE uses squared-error-sixteenth sums on the common valid positive-scale cohort. Exact integer equality alone defines a tie, independent of displayed deltas or floating tolerance.',
        delta_definition='WEEKDAY4 metric minus SNAIVE7 metric for the same series. Negative favors WEEKDAY4. Mean and conventional median summarize paired deltas over each metric compared cohort, without sales weighting.',
        numerical_method='MAE deltas retain integer quarter-error numerators with denominator 112, including central-one/two median denominators, through exact six-place half-away rounding. Win percentages use exact integer four-place rounding. RMSSE deltas use the exact SSE difference divided by the sum of full roots after common scaling, algebraically equivalent to subtracting roots while avoiding cancellation.',
        undefined_policy='Undefined RMSSE pairs are excluded and counted, never set to zero. They remain in MAE. An empty compared cohort has zero win/tie/loss counts and NULL win percentage, mean and median.',
        source_training_rows_compared=413208,source_training_columns_compared=6,source_training_field_mismatches=0,
        candidate_rows_compared_per_model=24192,candidate_columns_compared={'SNAIVE7':13,'WEEKDAY4':15},candidate_field_mismatches=0,
        prior_error_rows_reference_reconstructed=len(development_expected[0]),prior_series_diagnostics_reference_reconstructed=len(development_expected[1]),
        paired_series_compared=len(expected[0]),paired_columns_compared=len(PAIRED_COLUMNS),exact_pairing_eligibility_and_winner_mismatches=0,
        independent_reference_precision_digits=70,floating_absolute_tolerance=str(ABS_TOL),floating_relative_tolerance=str(REL_TOL),
        maximum_paired_root_or_delta_absolute_error=str(maximum_pair_error),maximum_rmsse_aggregate_delta_absolute_error=str(maximum_aggregate_error),
        independent_reference='Original CSVs and unmodified helpers reconstruct all source training and saved forecasts plus SQL36 exact error/scale diagnostics. This runner independently pairs those diagnostics, classifies exact integer errors, computes rational MAE deltas/medians and subtracts 70-digit Decimal roots for RMSSE deltas before averaging/sorting. Every private paired field and six displayed summaries are compared.',
        result_rows=6,result_columns=len(REPORT_COLUMNS),rows_with_pass_status=6,output_columns=REPORT_COLUMNS,
        results=actual_report,ordered_result_sha256=json_hash(actual_report),result_field_mismatches=0,
        ordered_exact_paired_diagnostics_sha256=exact_pair_hash(expected[0]),
        detail_fingerprint_method='SHA256 of compact UTF-8 JSON with sorted object keys and ensure_ascii=False. Private rows ordered origin,item_id,store_id. Exact hash excludes the three approximate root/delta values but includes integer error sums, eligibility and exact winner labels.',
        input_projection_row_counts=counts,input_and_candidate_sha256_before=before_hashes,input_and_candidate_sha256_after=after_hashes,
        source_and_saved_candidates_unchanged=True,read_only_comparison=True,new_table_created=False,
        final_holdout_actual_values_inspected=False,final_holdout_scored=False,final_model_selected=False,
        timings=timings,timing_scope='Named Python reference and DuckDB process/export timings; remaining Python comparisons and hashing excluded.',
        fixture_cases_passed=len(cases),fixture_cases=cases,real_product_identifiers_published=False,individual_paired_diagnostics_published=False,
        scope='Assistant preflight only; learner SQL37 execution pending. Public evidence contains six paired-coverage aggregates and fingerprints, without product lists, individual error/metric deltas or observation vectors. This descriptive follow-up was specified after aggregate development scores were observed. Win percentages are whole-series counts, not daily accuracy frequencies, relative gains, independent trials, statistical significance, final holdout performance or final model selection.')
    serialized=json.dumps(report,indent=2,ensure_ascii=False)+'\n'
    assert all(item not in serialized for item,_,_ in products),'Product identifier in public evidence'
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(serialized,encoding='utf-8',newline='\n')
    print(json.dumps({'fixture_cases_passed':len(cases),'results':actual_report,
        'ordered_result_sha256':report['ordered_result_sha256'],'maximum_pair_error':str(maximum_pair_error),
        'maximum_aggregate_error':str(maximum_aggregate_error),'timings':timings}),flush=True)


if __name__=='__main__':
    main()
