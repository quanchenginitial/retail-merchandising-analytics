"""Independently compare development errors and training-only RMSSE scales in private databases."""
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

SCORED_COLUMNS = ['origin','model','item_id','store_id','horizon_day','forecast_day','forecast_date','actual_units',
                  'predicted_quarters','error_quarters','absolute_error_quarters','squared_error_sixteenths']
DIAGNOSTIC_COLUMNS = ['origin','model','item_id','store_id','train_end_day','first_positive_day','scale_diff_count',
                      'training_sse','evaluated_rows','actual_units','predicted_quarters','absolute_error_quarters',
                      'error_quarters','squared_error_sixteenths','rmsse_status','rmsse']
REPORT_COLUMNS = ['origin','model','series_count','evaluated_rows','actual_units','predicted_units','mae','mean_error',
                  'rmsse_valid_series','rmsse_undefined_series','macro_rmsse','check_status']
ABS_TOL = Decimal('1e-10')
REL_TOL = Decimal('1e-13')


def six(value):
    if value is None:
        return None
    value = value.quantize(Decimal('.000001'), rounding=ROUND_HALF_UP)
    return format(abs(value) if value == 0 else value, '.6f')


def independent_errors(pairs, training, s7, w4):
    """Use exact Python integers and 70-digit Decimal roots; scales are separately sliced at each origin."""
    scored, diagnostics = [], []
    forecasts = {('SNAIVE7',r['origin'],r['item_id'],r['store_id'],r['horizon_day']):r for r in s7}
    forecasts.update({('WEEKDAY4',r['origin'],r['item_id'],r['store_id'],r['horizon_day']):r for r in w4})
    with localcontext() as ctx:
        ctx.prec = 70
        for origin,last in ORIGINS[:3]:
            for model in ('SNAIVE7','WEEKDAY4'):
                for item,store in sorted(pairs):
                    rows = []
                    history = training[item][:last]
                    positive = next((i for i,v in enumerate(history) if v > 0),None)
                    first = None if positive is None else positive+1
                    retained = [] if positive is None else history[positive:]
                    count = None if first is None else len(retained)-1
                    scale_sse = None if first is None else sum((right-left)**2 for left,right in zip(retained,retained[1:]))
                    status = ('no_positive_training' if first is None else 'insufficient_retained_history' if count<1
                              else 'zero_scale' if scale_sse==0 else 'VALID')
                    for horizon in range(1,29):
                        f = forecasts[(model,origin,item,store,horizon)]
                        actual = training[item][last+horizon-1]
                        prediction = Decimal(str(f['predicted_units']))*4
                        assert prediction == int(prediction)
                        q = int(prediction)-4*actual
                        row = dict(origin=origin,model=model,item_id=item,store_id=store,horizon_day=horizon,
                                   forecast_day=last+horizon,forecast_date=f['forecast_date'],actual_units=actual,
                                   predicted_quarters=int(prediction),error_quarters=q,absolute_error_quarters=abs(q),
                                   squared_error_sixteenths=q*q)
                        rows.append(row)
                    error_sse = sum(r['squared_error_sixteenths'] for r in rows)
                    rmsse = None if status!='VALID' else (Decimal(error_sse)/Decimal(16*28)
                             /(Decimal(scale_sse)/Decimal(count))).sqrt()
                    diagnostics.append(dict(origin=origin,model=model,item_id=item,store_id=store,train_end_day=last,
                        first_positive_day=first,scale_diff_count=count,training_sse=scale_sse,evaluated_rows=28,
                        actual_units=sum(r['actual_units'] for r in rows),predicted_quarters=sum(r['predicted_quarters'] for r in rows),
                        absolute_error_quarters=sum(r['absolute_error_quarters'] for r in rows),error_quarters=sum(r['error_quarters'] for r in rows),
                        squared_error_sixteenths=error_sse,rmsse_status=status,rmsse=rmsse))
                    scored.extend(rows)
        reports, status_summary, full_macro = [], [], []
        for origin,_ in ORIGINS[:3]:
            for model in ('SNAIVE7','WEEKDAY4'):
                group = [d for d in diagnostics if d['origin']==origin and d['model']==model]
                n = sum(d['evaluated_rows'] for d in group)
                valid = [d['rmsse'] for d in group if d['rmsse'] is not None]
                macro = None if not valid else sum(valid,Decimal(0))/len(valid)
                reports.append(dict(origin=origin,model=model,series_count=len(group),evaluated_rows=n,
                    actual_units=sum(d['actual_units'] for d in group),
                    predicted_units=format(Decimal(sum(d['predicted_quarters'] for d in group))/4,'.2f'),
                    mae=six(Decimal(sum(d['absolute_error_quarters'] for d in group))/Decimal(4*n)),
                    mean_error=six(Decimal(sum(d['error_quarters'] for d in group))/Decimal(4*n)),
                    rmsse_valid_series=len(valid),rmsse_undefined_series=len(group)-len(valid),macro_rmsse=six(macro),check_status='PASS'))
                full_macro.append(dict(origin=origin,model=model,macro_rmsse=macro))
                for status in sorted({d['rmsse_status'] for d in group}):
                    members = [d for d in group if d['rmsse_status']==status]
                    positions = sum(d['evaluated_rows'] for d in members)
                    status_summary.append(dict(origin=origin,model=model,rmsse_status=status,series_count=len(members),
                        evaluated_rows=positions,mae=six(Decimal(sum(d['absolute_error_quarters'] for d in members))/Decimal(4*positions)),
                        mean_error=six(Decimal(sum(d['error_quarters'] for d in members))/Decimal(4*positions))))
    return scored,diagnostics,reports,status_summary,full_macro


def canonical_report(rows):
    result=[]
    for row in rows:
        assert list(row)==REPORT_COLUMNS
        normalized=dict(row)
        for key in ('series_count','evaluated_rows','actual_units','rmsse_valid_series','rmsse_undefined_series'):
            normalized[key]=int(row[key])
        normalized['predicted_units']=format(Decimal(str(row['predicted_units'])),'.2f')
        for key in ('mae','mean_error','macro_rmsse'):
            normalized[key]=None if row[key] is None else format(Decimal(str(row[key])),'.6f')
        result.append(normalized)
    return result


def read_diagnostics(path):
    rows=[]
    text_fields={'origin','model','item_id','store_id','rmsse_status'}
    with path.open(newline='',encoding='utf-8') as stream:
        reader=csv.DictReader(stream)
        assert reader.fieldnames==DIAGNOSTIC_COLUMNS
        for row in reader:
            for key in DIAGNOSTIC_COLUMNS:
                if key in text_fields:
                    continue
                row[key]=None if row[key]=='' else Decimal(row[key]) if key=='rmsse' else int(row[key])
            rows.append(row)
    return rows


def assert_diagnostics(actual,expected):
    assert len(actual)==len(expected)
    maximum=Decimal(0)
    for observed,reference in zip(actual,expected):
        assert {k:v for k,v in observed.items() if k!='rmsse'}=={k:v for k,v in reference.items() if k!='rmsse'},'Exact series diagnostics mismatch'
        a,e=observed['rmsse'],reference['rmsse']
        assert (a is None)==(e is None),'RMSSE NULL status mismatch'
        if e is not None:
            error=abs(a-e)
            assert a.is_finite() and error<=ABS_TOL+REL_TOL*abs(e),'Full-precision RMSSE differs'
            maximum=max(maximum,error)
    return maximum


def exact_diagnostic_hash(rows):
    return json_hash([{k:v for k,v in r.items() if k!='rmsse'} for r in rows])


def copy_query(query,path):
    return f"COPY ({query}) TO {quote(path.as_posix())} (HEADER, DELIMITER ',');"


def internal_exports(prefix,folder):
    paths={'scored':folder/'scored.csv','diagnostics':folder/'diagnostics.csv','macro':folder/'macro.csv'}
    selects={
        'scored':f"SELECT {','.join(SCORED_COLUMNS)} FROM scored_rows ORDER BY origin,model,item_id,store_id,horizon_day",
        'diagnostics':f"SELECT {','.join(DIAGNOSTIC_COLUMNS)} FROM series_diagnostics ORDER BY origin,model,item_id,store_id",
        'macro':'SELECT origin,model,macro_rmsse FROM report_totals ORDER BY origin,model',
    }
    return paths,'\n'.join(copy_query(prefix+select,paths[key]) for key,select in selects.items())


def compare_internal(paths,expected):
    scored,diagnostics,_,_,macro=expected
    compare_csv(paths['scored'],SCORED_COLUMNS,(tuple(r[k] for k in SCORED_COLUMNS) for r in scored),'all exact scored fields')
    observed=read_diagnostics(paths['diagnostics'])
    maximum=assert_diagnostics(observed,diagnostics)
    assert exact_diagnostic_hash(observed)==exact_diagnostic_hash(diagnostics)
    macro_max=Decimal(0)
    with paths['macro'].open(newline='',encoding='utf-8') as stream:
        actual=list(csv.DictReader(stream))
    assert len(actual)==len(macro)
    for row,reference in zip(actual,macro):
        assert (row['origin'],row['model'])==(reference['origin'],reference['model'])
        value=None if row['macro_rmsse']=='' else Decimal(row['macro_rmsse'])
        target=reference['macro_rmsse']
        assert (value is None)==(target is None)
        if target is not None:
            error=abs(value-target)
            assert value.is_finite() and error<=ABS_TOL+REL_TOL*abs(target)
            macro_max=max(macro_max,error)
    return maximum,macro_max


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--duckdb',required=True)
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--fixtures-only',action='store_true')
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    tmp_root=root/'tmp';tmp_root.mkdir(exist_ok=True)
    assert tmp_root.resolve().is_relative_to(root.resolve())
    sql_path=root/'sql/36_compare_development_forecast_errors.sql'
    sql_bytes=sql_path.read_bytes();query=sql_bytes.decode('utf-8')
    internal_prefix=query.split('-- REPORT:',1)[0]
    dependencies=['sql/08_stage_calendar.sql','sql/12_build_product_dimension.sql','sql/13_build_store_dimension.sql',
                  'sql/14_build_calendar_dimension.sql','sql/33_forecast_scope_and_time_audit.sql',
                  'sql/34_build_seasonal_naive_forecasts.sql','sql/35_build_weekday_mean_forecasts.sql']
    scripts={p:(root/p).read_bytes() for p in dependencies}
    builds={number:scripts[path].decode('utf-8').split('-- VALIDATION:',1)[0] for number,path in
            [('34','sql/34_build_seasonal_naive_forecasts.sql'),('35','sql/35_build_weekday_mean_forecasts.sql')]}
    validations={number:'-- VALIDATION:'+scripts[path].decode('utf-8').split('-- VALIDATION:',1)[1] for number,path in
                 [('34','sql/34_build_seasonal_naive_forecasts.sql'),('35','sql/35_build_weekday_mean_forecasts.sql')]}
    scope=scripts['sql/33_forecast_scope_and_time_audit.sql'].decode('utf-8')
    scope_prefix=scope[scope.index('WITH parameters AS ('):scope.index('\nSELECT o.origin,s.dept_id,s.store_id,t.series_count')]
    assert query.count(scope_prefix)==1
    helper_paths=['validation/preflight_forecast_scope_and_time_audit.py','validation/preflight_seasonal_naive_forecasts.py',
                  'validation/preflight_weekday_mean_forecasts.py']
    helper_hashes={p:sha256(root/p) for p in helper_paths}
    protocol_path=root/'docs/EVALUATION_PLAN.md'
    protocol_hash=sha256(protocol_path)
    historical={p.relative_to(root).as_posix():sha256(p) for p in (root/'data').glob('*_preflight.json')
                if p.name!='development_forecast_errors_preflight.json'}
    cases=[]
    fixture_pairs=[('P001','CA_1'),('P002','CA_1')]
    fixture_hash=membership_hash(fixture_pairs)
    def adapt(text):
        return text.replace('3049 AS expected_products,10 AS expected_stores','3 AS expected_products,2 AS expected_stores').replace(
            '216 AS expected_scope_series','2 AS expected_scope_series').replace(FROZEN_MEMBERSHIP,fixture_hash)
    fixture_calendar={n:dict(d=f'd_{n}',date=(FIRST_DATE+timedelta(days=n-1)).isoformat(),day_number=n,wm_yr_wk=11000+n//7) for n in range(1,1970)}
    baseline={item:[n%5 for n in range(1,1914)] for item,_ in fixture_pairs}
    baseline_expected=independent_errors(fixture_pairs,baseline,s7_reference('FOODS_1',fixture_pairs,baseline,fixture_calendar),
                                        w4_reference('FOODS_1',fixture_pairs,baseline,fixture_calendar))
    fixture_setup="""CREATE SCHEMA raw; CREATE SCHEMA core; CREATE SCHEMA mart;
CREATE TABLE core.m5_product(item_id VARCHAR,dept_id VARCHAR,cat_id VARCHAR);
INSERT INTO core.m5_product VALUES ('P003','FOODS_2','FOODS'),('P002','FOODS_1','FOODS'),('P001','FOODS_1','FOODS');
CREATE TABLE core.m5_store(store_id VARCHAR,state_id VARCHAR);
INSERT INTO core.m5_store VALUES ('TX_1','TX'),('CA_1','CA');
CREATE TABLE raw.m5_sales_wide AS SELECT p.item_id,p.dept_id,p.cat_id,s.store_id,s.state_id FROM core.m5_product p CROSS JOIN core.m5_store s;
CREATE TABLE core.m5_calendar AS SELECT 'd_'||CAST(n AS VARCHAR) AS d,DATE '2011-01-29'+CAST(n AS INTEGER)-1 AS date,
CAST(n AS INTEGER) AS day_number,CAST(11000+n//7 AS INTEGER) AS wm_yr_wk FROM range(1,1970) t(n);
"""
    def tiny(name,training=None,mutation='',reject=False,future_changed=False,future_absent=False):
        training=baseline if training is None else training
        s7=s7_reference('FOODS_1',fixture_pairs,training,fixture_calendar)
        w4=w4_reference('FOODS_1',fixture_pairs,training,fixture_calendar)
        expected=independent_errors(fixture_pairs,training,s7,w4)
        with tempfile.TemporaryDirectory(prefix='development-error-fixture-',dir=tmp_root) as value:
            folder=Path(value).resolve();assert folder.is_relative_to(tmp_root.resolve())
            data=folder/'input.csv'
            with data.open('w',newline='',encoding='utf-8') as stream:
                writer=csv.writer(stream);writer.writerow(DAILY_FIELDS)
                for item,store in fixture_pairs:
                    for n in range(1,1914 if future_absent else 1942):
                        units=training[item][n-1] if n<=1913 else (-99 if item=='P001' else None) if future_changed else 0
                        day_date='2016-01-01' if n>1913 and future_changed else fixture_calendar[n]['date']
                        writer.writerow([item,store,f'd_{n}',day_date,fixture_calendar[n]['wm_yr_wk'],units])
            database=folder/'fixture.duckdb'
            settings="SET threads=2; SET memory_limit='2GB';\n"
            def execute(text):
                return subprocess.run([args.duckdb,str(database),'-bail','-json'],input=settings+text,text=True,encoding='utf-8',capture_output=True)
            setup=fixture_setup+f"CREATE TABLE mart.m5_sales_daily AS SELECT item_id,store_id,d,CAST(date AS DATE) AS date,CAST(wm_yr_wk AS INTEGER) AS wm_yr_wk,CAST(units AS INTEGER) AS units FROM read_csv({quote(data.as_posix())},header=true,all_varchar=true);"
            before,before_sql=export_snapshots(folder,'before');after,after_sql=export_snapshots(folder,'after')
            for key,candidate_query in [('s7',S7_QUERY),('w4',W4_QUERY)]:
                before[key]=folder/('before-'+key+'.csv');after[key]=folder/('after-'+key+'.csv')
                before_sql+=copy_query(candidate_query,before[key]);after_sql+=copy_query(candidate_query,after[key])
            run=execute(setup+adapt(builds['34'])+adapt(builds['35'])+mutation+before_sql)
            assert run.returncode==0,(name,run.stderr)
            run=execute(adapt(query))
            if reject:
                assert run.returncode!=0 and 'Development error comparison blocked' in run.stderr,(name,run.stderr)
            else:
                assert run.returncode==0,(name,run.stderr)
                observed=canonical_report(json.loads(run.stdout,parse_float=Decimal))
                assert observed==expected[2],(name,'displayed aggregate mismatch',observed,expected[2])
                paths,export=internal_exports(adapt(internal_prefix),folder)
                run=execute(export);assert run.returncode==0,(name,run.stderr)
                compare_internal(paths,expected)
                first=[d for d in expected[1] if d['origin']=='DEVELOPMENT_1' and d['model']=='SNAIVE7']
                if name=='macro_mean_of_roots_and_known_hand_metrics':
                    assert [d['rmsse'] for d in first]==[Decimal(1),Decimal(3)]
                    assert observed[0]['mae']=='2.000000' and observed[0]['mean_error']=='-2.000000' and observed[0]['macro_rmsse']=='2.000000'
                if name=='leading_zero_jump_excluded_and_later_zeros_retained':
                    assert (first[0]['first_positive_day'],first[0]['scale_diff_count'],first[0]['training_sse'])==(1827,2,8)
                if name=='only_one_retained_training_day_is_undefined':
                    assert first[0]['rmsse_status']=='insufficient_retained_history' and first[0]['rmsse'] is None
                if name=='positive_targets_do_not_leak_into_first_positive_search':
                    assert first[0]['rmsse_status']=='no_positive_training' and first[0]['absolute_error_quarters']==112
                if name=='signed_errors_cancel_but_absolute_errors_remain':
                    assert observed[0]['mae']=='0.500000' and observed[0]['mean_error']=='0.000000'
                if name=='huge_integer_error_and_training_squares_do_not_overflow':
                    assert max(r['squared_error_sixteenths'] for r in expected[0])>9223372036854775807
                    assert max(d['training_sse'] or 0 for d in expected[1])>9223372036854775807
                if name in ('final_holdout_changes_do_not_affect_any_development_error','final_holdout_absent_does_not_affect_development_errors'):
                    assert expected==baseline_expected
                if name=='development_targets_change_errors_not_earlier_training_scale':
                    baseline_first=[d for d in baseline_expected[1] if d['origin']=='DEVELOPMENT_1' and d['model']=='SNAIVE7']
                    assert first[0]['training_sse']==baseline_first[0]['training_sse'] and first[0]['squared_error_sixteenths']!=baseline_first[0]['squared_error_sixteenths']
                if name=='early_history_changes_scale_without_changing_forecasts':
                    assert expected[0]==baseline_expected[0] and expected[1][0]['training_sse']!=baseline_expected[1][0]['training_sse']
            run=execute(after_sql);assert run.returncode==0,(name,run.stderr)
            assert all(sha256(before[key])==sha256(after[key]) for key in before),(name,'input or saved candidate changed')
        assert not folder.exists()
        cases.append(dict(case=name,passed=True,rejected=reject,source_and_saved_candidates_unchanged=True))

    hand={item:[n%2 for n in range(1,1914)] for item,_ in fixture_pairs}
    for item,increment in [('P001',1),('P002',3)]:
        hand[item][1829:1857]=(hand[item][1822:1829]*4)
        hand[item][1829:1857]=[v+increment for v in hand[item][1829:1857]]
    tiny('macro_mean_of_roots_and_known_hand_metrics',hand)
    leading={item:[0]*1913 for item,_ in fixture_pairs};leading['P001'][1826:1829]=[2,0,2]
    tiny('leading_zero_jump_excluded_and_later_zeros_retained',leading)
    tiny('all_zero_perfect_forecasts_keep_rmsse_undefined',{item:[0]*1913 for item,_ in fixture_pairs})
    tiny('constant_positive_perfect_forecasts_have_zero_scale',{item:[2]*1913 for item,_ in fixture_pairs})
    one={item:[0]*1913 for item,_ in fixture_pairs};one['P001'][1828]=2
    tiny('only_one_retained_training_day_is_undefined',one)
    future_positive={item:[0]*1913 for item,_ in fixture_pairs};future_positive['P001'][1829:1857]=[1]*28
    tiny('positive_targets_do_not_leak_into_first_positive_search',future_positive)
    cancel={'P001':[2+n%2 for n in range(1,1914)],'P002':[0]*1913}
    cancel['P001'][1829:1857]=[v+(1 if i%2==0 else -1) for i,v in enumerate(cancel['P001'][1822:1829]*4)]
    tiny('signed_errors_cancel_but_absolute_errors_remain',cancel)
    extreme={item:[2147483647 if n%2 else 0 for n in range(1,1914)] for item,_ in fixture_pairs}
    for item in extreme:
        extreme[item][1829:1857]=[2147483647-v for v in extreme[item][1822:1829]*4]
    tiny('huge_integer_error_and_training_squares_do_not_overflow',extreme)
    early={k:list(v) for k,v in baseline.items()};early['P001'][1]=10
    tiny('early_history_changes_scale_without_changing_forecasts',early)
    changed={k:list(v) for k,v in baseline.items()};changed['P001'][1829:1857]=[7]*28
    tiny('development_targets_change_errors_not_earlier_training_scale',changed)
    tiny('final_holdout_changes_do_not_affect_any_development_error',future_changed=True)
    tiny('final_holdout_absent_does_not_affect_development_errors',future_absent=True)
    for name,mutation in [
        ('saved_snaive_value_tamper_is_not_silently_recomputed',"UPDATE mart.m5_forecast_snaive7_28d SET predicted_units=predicted_units+1 WHERE origin='DEVELOPMENT_1' AND item_id='P001' AND horizon_day=1;"),
        ('saved_weekday_quarter_value_tamper_rejected',"UPDATE mart.m5_forecast_weekday4_28d SET predicted_units=predicted_units+0.25 WHERE origin='DEVELOPMENT_1' AND item_id='P001' AND horizon_day=1;"),
        ('saved_duplicate_missing_forecast_key_preserves_count',"DELETE FROM mart.m5_forecast_snaive7_28d WHERE origin='DEVELOPMENT_1' AND item_id='P001' AND horizon_day=1; INSERT INTO mart.m5_forecast_snaive7_28d SELECT * FROM mart.m5_forecast_snaive7_28d WHERE origin='DEVELOPMENT_1' AND item_id='P001' AND horizon_day=2;"),
        ('saved_weekday_source_count_tamper_rejected',"UPDATE mart.m5_forecast_weekday4_28d SET source_observations=3 WHERE origin='DEVELOPMENT_1' AND item_id='P001' AND horizon_day=1;"),
        ('missing_development_actual_rejected',"DELETE FROM mart.m5_sales_daily WHERE item_id='P001' AND d='d_1830';"),
        ('balanced_duplicate_missing_development_actual_rejected',"DELETE FROM mart.m5_sales_daily WHERE item_id='P001' AND d='d_1830'; INSERT INTO mart.m5_sales_daily SELECT * FROM mart.m5_sales_daily WHERE item_id='P001' AND d='d_1831';"),
        ('null_development_actual_rejected',"UPDATE mart.m5_sales_daily SET units=NULL WHERE item_id='P001' AND d='d_1830';"),
        ('saved_candidate_decimal_schema_changed',"ALTER TABLE mart.m5_forecast_weekday4_28d ALTER predicted_units TYPE DOUBLE;"),
    ]:
        tiny(name,mutation=mutation,reject=True)
    print(json.dumps({'fixture_cases_passed':len(cases)}),flush=True)
    if args.fixtures_only:
        return

    source_root=Path('D:/database/m5-forecasting-accuracy')
    sources=[source_root/'sales_train_evaluation.csv',source_root/'calendar.csv']
    registry=json.loads((root/'data/m5_source_audit.json').read_text(encoding='utf-8'))
    source_hashes={p.name:sha256(p) for p in sources}
    assert all(source_hashes[p.name]==registry['files'][p.name]['sha256'] for p in sources)
    acceptance_paths=['data/seasonal_naive_forecasts_learner_acceptance.json','data/weekday_mean_forecasts_learner_acceptance.json']
    accepted_bytes={p:(root/p).read_bytes() for p in acceptance_paths}
    accepted={p:json.loads(value.decode('utf-8')) for p,value in accepted_bytes.items()}
    timings={};started=time.perf_counter()
    calendar,metadata,products,stores,department,store,pairs,training=original_reference(*sources)
    s7=s7_reference(department,pairs,training,calendar);w4=w4_reference(department,pairs,training,calendar)
    expected=independent_errors(pairs,training,s7,w4)
    timings['independent_source_forecast_and_error_reference_seconds']=round(time.perf_counter()-started,3)
    days=','.join(f'd_{n}' for n in range(1,1914))
    with tempfile.TemporaryDirectory(prefix='development-error-source-',dir=tmp_root) as value:
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
        actual_report=canonical_report(execute(query,'development_error_query_seconds'))
        assert actual_report==expected[2],('Six displayed rows differ',actual_report,expected[2])
        paths,export=internal_exports(internal_prefix,folder)
        execute(export,'private_row_and_series_diagnostic_export_seconds')
        maximum_rmsse_error,maximum_macro_error=compare_internal(paths,expected)
        assert len(expected[0])==36288 and len(expected[1])==1296
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
        prespecified_evaluation_plan=protocol_path.relative_to(root).as_posix(),prespecified_evaluation_plan_sha256=protocol_hash,
        evaluation_plan_unchanged_during_preflight=True,
        dependency_script_sha256={path:hashlib.sha256(value).hexdigest() for path,value in scripts.items()},reference_helper_sha256=helper_hashes,
        accepted_candidate_evidence_sha256={path:hashlib.sha256(value).hexdigest() for path,value in accepted_bytes.items()},
        accepted_candidate_report_fingerprints_matched=True,reconstructed_candidate_report_sha256=candidate_report_hashes,
        accepted_candidate_forecast_fingerprints_matched=True,reconstructed_candidate_forecast_sha256=candidate_hashes,
        source_sha256=source_hashes,source_hashes_unchanged=True,historical_preflight_sha256=historical,historical_preflights_unchanged=True,
        accepted_scope_cte_prefix_copies=1,accepted_scope_cte_prefix_sha256=hashlib.sha256(scope_prefix.encode()).hexdigest(),
        baseline_database='Private temporary DuckDB and detailed CSV exports under ignored repository tmp; resolved containment checked; all removed. Learner database never opened.',
        settings={'threads':2,'memory_limit':'2GB'},temporary_baseline_removed=True,temporary_database_bytes_after_close=database_bytes,
        frozen_scope={'dept_id':department,'store_id':store,'series_count':len(pairs),'series_membership_sha256':membership_hash(pairs)},
        evaluation_scope='Only DEVELOPMENT_1, DEVELOPMENT_2 and DEVELOPMENT_3. Every model/fold evaluates 216 series by 28 days, equally weighted. Final candidate fields may be validated from training but final actuals are not accessed or scored.',
        error_convention='Forecast minus actual in unit/day; exact integer quarters for signed and absolute errors and HUGEINT squares in sixteenths.',
        rmsse_definition='For each series and origin, s is the first positive training day. Scale = sum of successive squared differences for s+1 through T divided by T-s. Leading zero-to-first-positive jump excluded; later zero days retained. Per-series RMSSE is sqrt((sum quarter-error squares / 16 / 28) / scale). Macro is the mean of valid individual roots.',
        undefined_policy='no_positive_training, insufficient_retained_history or zero_scale gives NULL, never epsilon. All series remain in MAE and bias; RMSSE valid and undefined counts sum to the complete scope.',
        display_rounding='MAE and signed mean error use exact integer rational half-away-from-zero rounding to six decimals. Macro RMSSE uses a DOUBLE mean of per-series roots then six-place rounding; predictions use two decimal places.',
        source_training_rows_compared=413208,source_training_columns_compared=6,source_training_field_mismatches=0,
        candidate_rows_compared_per_model=24192,candidate_columns_compared={'SNAIVE7':13,'WEEKDAY4':15},candidate_field_mismatches=0,
        scored_rows_compared=len(expected[0]),scored_columns_compared=len(SCORED_COLUMNS),exact_scored_field_mismatches=0,
        series_diagnostics_compared=len(expected[1]),series_diagnostic_columns_compared=len(DIAGNOSTIC_COLUMNS),exact_integer_and_status_mismatches=0,
        independent_reference_precision_digits=70,rmsse_absolute_tolerance=str(ABS_TOL),rmsse_relative_tolerance=str(REL_TOL),
        maximum_per_series_rmsse_absolute_error=str(maximum_rmsse_error),maximum_macro_rmsse_absolute_error=str(maximum_macro_error),
        independent_reference='Original CSV integers and calendar mappings supply every input. Unmodified candidate reference helpers independently reproduce each saved row. This runner independently slices each origin history at first positive, zips retained successive observations, computes all errors with Python integers, then evaluates roots/means at 70 Decimal digits. All row-level errors, exact diagnostics, NULL statuses and displayed aggregates are compared.',
        result_rows=6,result_columns=len(REPORT_COLUMNS),rows_with_pass_status=6,output_columns=REPORT_COLUMNS,
        results=actual_report,ordered_result_sha256=json_hash(actual_report),result_field_mismatches=0,
        rmsse_status_summary=expected[3],status_summary_scope='Independent aggregate counts and MAE/bias for every present RMSSE status group, derived from the fully reconciled private series diagnostics. No individual series are published.',
        ordered_scored_rows_sha256=json_hash(expected[0]),ordered_exact_series_diagnostics_sha256=exact_diagnostic_hash(expected[1]),
        detail_fingerprint_method='SHA256 of compact UTF-8 JSON with sorted object keys and ensure_ascii=False. Private rows ordered origin,model,item_id,store_id then horizon where applicable. Integers stay integers; exact diagnostic hash omits approximate RMSSE but includes its eligibility status.',
        input_projection_row_counts=counts,input_and_candidate_sha256_before=before_hashes,input_and_candidate_sha256_after=after_hashes,
        source_and_saved_candidates_unchanged=True,read_only_comparison=True,new_table_created=False,
        final_holdout_actual_values_inspected=False,final_holdout_scored=False,final_model_selected=False,official_wrmsse_computed=False,
        timings=timings,timing_scope='Named Python reference and DuckDB process/export timings; remaining Python comparisons and hashing excluded.',
        fixture_cases_passed=len(cases),fixture_cases=cases,real_product_identifiers_published=False,individual_errors_or_diagnostics_published=False,
        scope='Assistant preflight only; learner SQL36 execution pending. Public evidence retains six development aggregates, status-group controls and fingerprints, without product lists, actual/predicted/error arrays or individual RMSSE. This is one retrospective department/store benchmark with overlapping expanding training histories and three nonoverlapping development outcome windows. Results do not establish final holdout performance, final model choice, official WRMSSE, deployment benefit or causal effects.')
    serialized=json.dumps(report,indent=2,ensure_ascii=False)+'\n'
    assert all(item not in serialized for item,_,_ in products),'Product identifier in public evidence'
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(serialized,encoding='utf-8',newline='\n')
    print(json.dumps({'fixture_cases_passed':len(cases),'results':actual_report,'rmsse_status_summary':expected[3],
        'ordered_result_sha256':report['ordered_result_sha256'],'maximum_rmsse_error':str(maximum_rmsse_error),
        'maximum_macro_error':str(maximum_macro_error),'timings':timings}),flush=True)


if __name__=='__main__':
    main()
