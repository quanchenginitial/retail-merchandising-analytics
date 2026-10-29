"""Verify exact four-weekday means against original training inputs and preserve the first baseline."""
import argparse
import csv
import hashlib
import json
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

sys.dont_write_bytecode = True
from preflight_forecast_scope_and_time_audit import (
    FIRST_DATE, ORIGINS, FROZEN_MEMBERSHIP, DAILY_FIELDS, METADATA_FIELDS,
    quote, sha256, json_hash, membership_hash, original_reference, reference_report,
    canonical_report as canonical_scope_report, export_snapshots, compare_csv,
)

from preflight_seasonal_naive_forecasts import (
    FORECAST_QUERY as SNAIVE_QUERY, FORECAST_COLUMNS as SNAIVE_COLUMNS,
    forecast_reference as snaive_reference, forecast_report as snaive_report,
    canonical_report as canonical_snaive_report, read_forecast_csv as read_snaive_csv,
)

TABLE = 'mart.m5_forecast_weekday4_28d'
FORECAST_COLUMNS = ['model','origin','dept_id','item_id','store_id','train_end_day','train_end','horizon_day',
                    'forecast_day','forecast_date','source_first_day','source_last_day','source_observations','source_units_sum','predicted_units']
INTEGER_COLUMNS = ['train_end_day','horizon_day','forecast_day','source_first_day','source_last_day','source_observations','source_units_sum']
REPORT_COLUMNS = ['origin','dept_id','store_id','series_count','forecast_rows','forecast_start','forecast_end',
                  'last28_units','predicted_units','zero_forecast_rows','fractional_forecast_rows','check_status']
FORECAST_QUERY = f"SELECT {','.join(FORECAST_COLUMNS)} FROM {TABLE} ORDER BY train_end_day,item_id,store_id,horizon_day"


def forecast_reference(department,pairs,training,calendar):
    """Split the last 28 inputs into four seven-day blocks; average their columns using Decimal."""
    rows=[]
    for origin,last in ORIGINS:
        for item,store in sorted(pairs):
            history=training[item][last-28:last]
            assert len(history)==28 and all(isinstance(v,int) and 0<=v<=2147483647 for v in history)
            weeks=[history[i:i+7] for i in range(0,28,7)]
            numerators=[sum(values) for values in zip(*weeks)]
            means=[(Decimal(total)/Decimal(4)).quantize(Decimal('.01')) for total in numerators]
            for repeat in range(4):
                for position,(numerator,mean) in enumerate(zip(numerators,means),1):
                    horizon=repeat*7+position
                    rows.append(dict(model='WEEKDAY4',origin=origin,dept_id=department,item_id=item,store_id=store,
                                     train_end_day=last,train_end=calendar[last]['date'],horizon_day=horizon,
                                     forecast_day=last+horizon,forecast_date=calendar[last+horizon]['date'],
                                     source_first_day=last-28+position,source_last_day=last-7+position,
                                     source_observations=4,source_units_sum=numerator,predicted_units=mean))
    assert len(rows)==4*len(pairs)*28
    assert len({(r['model'],r['origin'],r['item_id'],r['store_id'],r['horizon_day']) for r in rows})==len(rows)
    return rows


def canonical_forecasts(rows):
    result=[]
    for row in rows:
        assert list(row)==FORECAST_COLUMNS
        normalized=dict(row)
        value=Decimal(str(row['predicted_units']))
        assert value.is_finite() and value>=0 and value*4==int(value*4)
        normalized['predicted_units']=format(value,'.2f')
        result.append(normalized)
    return result


def forecast_report(department,store,pairs,training,calendar,forecasts):
    rows=[]
    for origin,last in ORIGINS:
        origin_rows=[r for r in forecasts if r['origin']==origin]
        last28=sum(sum(training[item][last-28:last]) for item,_ in pairs)
        predicted=sum((r['predicted_units'] for r in origin_rows),Decimal(0))
        assert predicted==last28
        rows.append(dict(origin=origin,dept_id=department,store_id=store,series_count=len(pairs),
                         forecast_rows=len(origin_rows),forecast_start=calendar[last+1]['date'],
                         forecast_end=calendar[last+28]['date'],last28_units=last28,predicted_units=format(predicted,'.2f'),
                         zero_forecast_rows=sum(r['predicted_units']==0 for r in origin_rows),
                         fractional_forecast_rows=sum(r['predicted_units']!=int(r['predicted_units']) for r in origin_rows),check_status='PASS'))
    return rows


def canonical_report(rows):
    result=[]
    for row in rows:
        assert list(row)==REPORT_COLUMNS
        row=dict(row)
        for key in ('series_count','forecast_rows','last28_units','zero_forecast_rows','fractional_forecast_rows'):
            row[key]=int(row[key])
        row['predicted_units']=format(Decimal(str(row['predicted_units'])),'.2f')
        result.append(row)
    return result


def read_forecast_csv(path):
    with path.open(newline='',encoding='utf-8') as stream:
        reader=csv.DictReader(stream)
        assert reader.fieldnames==FORECAST_COLUMNS
        rows=[]
        for row in reader:
            for key in INTEGER_COLUMNS:
                row[key]=int(row[key])
            row['predicted_units']=Decimal(row['predicted_units'])
            rows.append(row)
    return rows


def forecast_export(path):
    return f"COPY ({FORECAST_QUERY}) TO {quote(path.as_posix())} (HEADER, DELIMITER ',');"


def snaive_export(path):
    return f"COPY ({SNAIVE_QUERY}) TO {quote(path.as_posix())} (HEADER, DELIMITER ',');"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--duckdb',required=True)
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--fixtures-only',action='store_true')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    tmp_root = root/'tmp'
    tmp_root.mkdir(exist_ok=True)
    assert tmp_root.resolve().is_relative_to(root.resolve())
    sql_path = root/'sql/35_build_weekday_mean_forecasts.sql'
    sql_bytes = sql_path.read_bytes()
    sql = sql_bytes.decode('utf-8')
    build, validation = sql.split('-- VALIDATION:',1)
    validation = '-- VALIDATION:'+validation
    scope_path = root/'sql/33_forecast_scope_and_time_audit.sql'
    scope_bytes = scope_path.read_bytes()
    scope_sql = scope_bytes.decode('utf-8')
    prefix = scope_sql[scope_sql.index('WITH parameters AS ('):scope_sql.index('\nSELECT o.origin,s.dept_id,s.store_id,t.series_count')]
    assert sql.count(prefix) == 2, 'Both SQL35 scope/time CTE prefixes must exactly match SQL33'
    helper_path = root/'validation/preflight_forecast_scope_and_time_audit.py'
    helper_hash = sha256(helper_path)
    snaive_helper_path=root/'validation/preflight_seasonal_naive_forecasts.py'
    snaive_helper_hash=sha256(snaive_helper_path)
    snaive_sql_path=root/'sql/34_build_seasonal_naive_forecasts.sql'
    snaive_sql_bytes=snaive_sql_path.read_bytes()
    snaive_build,snaive_validation=snaive_sql_bytes.decode('utf-8').split('-- VALIDATION:',1)
    snaive_validation='-- VALIDATION:'+snaive_validation
    historical = {p.relative_to(root).as_posix():sha256(p) for p in (root/'data').glob('*_preflight.json')
                  if p.name != 'weekday_mean_forecasts_preflight.json'}
    prerequisite_paths = ['sql/08_stage_calendar.sql','sql/12_build_product_dimension.sql',
                          'sql/13_build_store_dimension.sql','sql/14_build_calendar_dimension.sql']
    prerequisites = {p:(root/p).read_bytes() for p in prerequisite_paths}
    cases = []
    fixture_hash = membership_hash([('P001','CA_1'),('P002','CA_1')])
    def fixture_sql(text):
        return text.replace('3049 AS expected_products,10 AS expected_stores','3 AS expected_products,2 AS expected_stores').replace(
            '216 AS expected_scope_series','2 AS expected_scope_series').replace(FROZEN_MEMBERSHIP,fixture_hash)
    fixture_build, fixture_validation = fixture_sql(build), fixture_sql(validation)
    fixture_snaive_build=fixture_sql(snaive_build)
    from datetime import timedelta
    fixture_calendar = {n:dict(date=(FIRST_DATE+timedelta(days=n-1)).isoformat()) for n in range(1,1970)}
    fixture_pairs = [('P001','CA_1'),('P002','CA_1')]
    baseline_training = {'P001':[n%29 for n in range(1,1914)],'P002':[0]*1913}
    known_blocks=[[0,1,0,2,0,1,5],[1,3,0,0,1,2,6],[4,6,0,3,1,3,5],[8,8,0,6,3,4,7]]
    baseline_training['P001'][1801:1829]=[value for block in known_blocks for value in block]
    baseline_forecasts = forecast_reference('FOODS_1',fixture_pairs,baseline_training,fixture_calendar)
    fixture_setup = """CREATE SCHEMA raw; CREATE SCHEMA core; CREATE SCHEMA mart;
CREATE TABLE core.m5_product(item_id VARCHAR,dept_id VARCHAR,cat_id VARCHAR);
INSERT INTO core.m5_product VALUES ('P003','FOODS_2','FOODS'),('P002','FOODS_1','FOODS'),('P001','FOODS_1','FOODS');
CREATE TABLE core.m5_store(store_id VARCHAR,state_id VARCHAR);
INSERT INTO core.m5_store VALUES ('TX_1','TX'),('CA_1','CA');
CREATE TABLE raw.m5_sales_wide AS SELECT p.item_id,p.dept_id,p.cat_id,s.store_id,s.state_id
FROM core.m5_product p CROSS JOIN core.m5_store s;
CREATE TABLE core.m5_calendar AS SELECT 'd_'||CAST(n AS VARCHAR) AS d,
DATE '2011-01-29'+CAST(n AS INTEGER)-1 AS date,CAST(n AS INTEGER) AS day_number,CAST(11000+n//7 AS INTEGER) AS wm_yr_wk
FROM range(1,1970) t(n);
CREATE TABLE mart.m5_sales_daily AS SELECT p.item_id,'CA_1'::VARCHAR AS store_id,c.d,c.date,c.wm_yr_wk,
CAST(CASE WHEN p.item_id='P002' THEN 0 ELSE c.day_number%29 END AS INTEGER) AS units
FROM core.m5_product p CROSS JOIN core.m5_calendar c WHERE p.dept_id='FOODS_1' AND c.day_number<=1941;
"""

    fixture_values=','.join(f"('d_{1802+i}',{v})" for i,v in enumerate(baseline_training['P001'][1801:1829]))
    fixture_setup+=f"UPDATE mart.m5_sales_daily SET units=v.units FROM (VALUES {fixture_values}) v(d,units) WHERE mart.m5_sales_daily.item_id='P001' AND mart.m5_sales_daily.d=v.d;"

    def tiny(name,input_mutation='',forecast_mutation='',reject_creation=False,reject_validation=False,training=None,check_no_overwrite=False):
        training = baseline_training if training is None else training
        expected = forecast_reference('FOODS_1',fixture_pairs,training,fixture_calendar)
        expected_report = forecast_report('FOODS_1','CA_1',fixture_pairs,training,fixture_calendar,expected)
        with tempfile.TemporaryDirectory(prefix='weekday4-fixture-',dir=tmp_root) as value:
            folder = Path(value).resolve()
            assert folder.is_relative_to(tmp_root.resolve())
            database = folder/'fixture.duckdb'
            settings = "SET threads=2; SET memory_limit='2GB';\n"
            def execute(text):
                return subprocess.run([args.duckdb,str(database),'-bail','-json'],input=settings+text,
                                      text=True,encoding='utf-8',capture_output=True)
            before,export_before = export_snapshots(folder,'before')
            after,export_after = export_snapshots(folder,'after')
            old_before,old_after=folder/'snaive-before.csv',folder/'snaive-after.csv'
            run = execute(fixture_setup+fixture_snaive_build+input_mutation+export_before+snaive_export(old_before))
            assert run.returncode == 0,(name,run.stderr)
            run = execute(fixture_build)
            if reject_creation:
                assert run.returncode != 0 and 'Weekday mean forecast creation blocked' in run.stderr,(name,run.stderr)
                table_count = execute("SELECT COUNT(*) AS tables FROM information_schema.tables WHERE table_schema='mart' AND table_name='m5_forecast_weekday4_28d';")
                assert table_count.returncode == 0 and json.loads(table_count.stdout)[0]['tables'] == 0
            else:
                assert run.returncode == 0,(name,run.stderr)
                forecast_before,forecast_after = folder/'forecast-before.csv',folder/'forecast-after.csv'
                run = execute(forecast_mutation+forecast_export(forecast_before))
                assert run.returncode == 0,(name,run.stderr)
                if check_no_overwrite:
                    existing = execute(fixture_build)
                    assert existing.returncode != 0 and 'already exists' in existing.stderr,(name,existing.stderr)
                run = execute(fixture_validation)
                if reject_validation:
                    assert run.returncode != 0 and 'Weekday mean forecast validation blocked' in run.stderr,(name,run.stderr)
                else:
                    assert run.returncode == 0,(name,run.stderr)
                    assert canonical_report(json.loads(run.stdout,parse_float=Decimal)) == expected_report,name
                    observed = read_forecast_csv(forecast_before)
                    assert observed == expected,(name,'independent forecast fields differ')
                    if name=='distinct_four_week_inputs_include_zero_and_exact_quarters':
                        first=[r for r in observed if r['origin']=='DEVELOPMENT_1' and r['item_id']=='P001']
                        assert [r['predicted_units'] for r in first]==list(map(Decimal,['3.25','4.50','0.00','2.75','1.25','2.50','5.75']))*4
                        assert all(r['source_observations']==4 for r in first)
                    if name=='integer_maximum_inputs_do_not_overflow':
                        assert all(r['source_units_sum']==8589934588 and r['predicted_units']==Decimal('2147483647.00') for r in observed)
                    if name in ('final_holdout_values_changed_without_effect','final_holdout_observations_absent_without_effect'):
                        assert observed==baseline_forecasts,name
                    if name=='future_origin_days_do_not_feed_earlier_forecasts':
                        assert [r for r in observed if r['origin']=='DEVELOPMENT_1']==[r for r in baseline_forecasts if r['origin']=='DEVELOPMENT_1']
                        assert [r for r in observed if r['origin']=='DEVELOPMENT_2']!=[r for r in baseline_forecasts if r['origin']=='DEVELOPMENT_2']
                run = execute(forecast_export(forecast_after))
                assert run.returncode == 0 and sha256(forecast_before)==sha256(forecast_after),(name,'saved forecasts changed')
            run = execute(export_after+snaive_export(old_after))
            assert sha256(old_before)==sha256(old_after),(name,'existing SNAIVE7 forecasts changed')
            assert run.returncode == 0,(name,run.stderr)
            assert all(sha256(before[k])==sha256(after[k]) for k in before),(name,'source projection changed')
        assert not folder.exists()
        cases.append(dict(case=name,passed=True,creation_rejected=reject_creation,validation_rejected=reject_validation,
                          source_projections_unchanged=True,existing_snaive7_forecasts_unchanged=True,saved_forecast_validation_read_only=not reject_creation,
                          failed_creation_left_no_table=reject_creation))

    tiny('distinct_four_week_inputs_include_zero_and_exact_quarters',check_no_overwrite=True)
    tiny('all_zero_series_produce_all_zero_forecasts',input_mutation="UPDATE mart.m5_sales_daily SET units=0;",training={k:[0]*1913 for k in baseline_training})
    tiny('integer_maximum_inputs_do_not_overflow',input_mutation="UPDATE mart.m5_sales_daily SET units=2147483647;",training={k:[2147483647]*1913 for k in baseline_training})
    changed_training={k:list(v) for k,v in baseline_training.items()}
    changed_training['P001'][1829:1850]=[1000]*21
    tiny('future_origin_days_do_not_feed_earlier_forecasts',input_mutation="UPDATE mart.m5_sales_daily SET units=1000 WHERE item_id='P001' AND CAST(SUBSTR(d,3) AS INTEGER) BETWEEN 1830 AND 1850;",training=changed_training)
    tiny('final_holdout_values_changed_without_effect',input_mutation="UPDATE mart.m5_sales_daily SET units=CASE WHEN item_id='P001' THEN -99 ELSE NULL END,date=DATE '2016-01-01' WHERE CAST(SUBSTR(d,3) AS INTEGER)>1913;")
    tiny('final_holdout_observations_absent_without_effect',input_mutation="DELETE FROM mart.m5_sales_daily WHERE CAST(SUBSTR(d,3) AS INTEGER)>1913;")
    for name,mutation in [
        ('missing_one_of_four_weekday_observations',"DELETE FROM mart.m5_sales_daily WHERE item_id='P002' AND d='d_1802';"),
        ('balanced_duplicate_and_missing_training_day',"DELETE FROM mart.m5_sales_daily WHERE item_id='P002' AND d='d_1802'; INSERT INTO mart.m5_sales_daily SELECT * FROM mart.m5_sales_daily WHERE item_id='P002' AND d='d_1803';"),
        ('null_training_units',"UPDATE mart.m5_sales_daily SET units=NULL WHERE item_id='P001' AND d='d_1829';"),
        ('empty_input_cannot_create_empty_forecast_table',"DELETE FROM mart.m5_sales_daily;"),
    ]:
        tiny(name,input_mutation=mutation,reject_creation=True)
    for name,mutation in [
        ('saved_quarter_forecast_value_changed',f"UPDATE {TABLE} SET predicted_units=predicted_units+0.25 WHERE origin='DEVELOPMENT_1' AND item_id='P001' AND horizon_day=1;"),
        ('saved_values_swapped_without_changing_total',f"UPDATE {TABLE} SET predicted_units=CASE WHEN horizon_day=1 THEN 4.50 ELSE 3.25 END WHERE origin='DEVELOPMENT_1' AND item_id='P001' AND horizon_day IN (1,2);"),
        ('saved_source_window_leaks_beyond_origin',f"UPDATE {TABLE} SET source_last_day=train_end_day+1 WHERE origin='DEVELOPMENT_1' AND item_id='P001' AND horizon_day=8;"),
        ('saved_denominator_excludes_zero_observation',f"UPDATE {TABLE} SET source_observations=3 WHERE origin='DEVELOPMENT_1' AND item_id='P001' AND horizon_day=1;"),
        ('saved_integer_numerator_changed',f"UPDATE {TABLE} SET source_units_sum=source_units_sum+1 WHERE origin='DEVELOPMENT_1' AND item_id='P001' AND horizon_day=1;"),
        ('saved_duplicate_and_missing_key_preserve_count',f"DELETE FROM {TABLE} WHERE origin='DEVELOPMENT_1' AND item_id='P001' AND horizon_day=1; INSERT INTO {TABLE} SELECT * FROM {TABLE} WHERE origin='DEVELOPMENT_1' AND item_id='P001' AND horizon_day=2;"),
        ('saved_forecast_row_missing',f"DELETE FROM {TABLE} WHERE origin='DEVELOPMENT_1' AND item_id='P001' AND horizon_day=1;"),
        ('saved_prediction_decimal_type_changed',f"ALTER TABLE {TABLE} ALTER predicted_units TYPE DOUBLE;"),
        ('saved_extra_schema_column',f"ALTER TABLE {TABLE} ADD COLUMN extra VARCHAR;"),
    ]:
        tiny(name,forecast_mutation=mutation,reject_validation=True)
    print(json.dumps({'fixture_cases_passed':len(cases)}),flush=True)
    if args.fixtures_only:
        return

    source_root = Path('D:/database/m5-forecasting-accuracy')
    sources = [source_root/'sales_train_evaluation.csv',source_root/'calendar.csv']
    registry = json.loads((root/'data/m5_source_audit.json').read_text(encoding='utf-8'))
    source_hashes = {p.name:sha256(p) for p in sources}
    assert all(source_hashes[p.name]==registry['files'][p.name]['sha256'] for p in sources)
    accepted_path = root/'data/forecast_scope_and_time_audit_learner_acceptance.json'
    accepted_bytes = accepted_path.read_bytes()
    accepted = json.loads(accepted_bytes.decode('utf-8'))
    snaive_accepted_path=root/'data/seasonal_naive_forecasts_learner_acceptance.json'
    snaive_accepted_bytes=snaive_accepted_path.read_bytes()
    snaive_accepted=json.loads(snaive_accepted_bytes.decode('utf-8'))
    snaive_preflight=json.loads((root/'data/seasonal_naive_forecasts_preflight.json').read_text(encoding='utf-8'))
    timings = {}
    started = time.perf_counter()
    calendar,metadata,products,stores,department,store,pairs,training = original_reference(*sources)
    expected_forecasts = forecast_reference(department,pairs,training,calendar)
    expected_report = forecast_report(department,store,pairs,training,calendar,expected_forecasts)
    expected_snaive=snaive_reference(department,pairs,training,calendar)
    expected_snaive_report=snaive_report(department,store,pairs,training,calendar,expected_snaive)
    timings['independent_python_source_and_forecast_reference_seconds'] = round(time.perf_counter()-started,3)
    day_columns = ','.join(f'd_{n}' for n in range(1,1914))
    with tempfile.TemporaryDirectory(prefix='weekday4-source-',dir=tmp_root) as value:
        folder = Path(value).resolve()
        assert folder.is_relative_to(tmp_root.resolve())
        database = folder/'preflight.duckdb'
        settings = f"SET threads=2; SET memory_limit='2GB'; SET temp_directory={quote((folder/'spill').as_posix())};\n"
        def execute(text,label=None):
            started = time.perf_counter()
            run = subprocess.run([args.duckdb,str(database),'-bail','-json'],input=settings+text,text=True,encoding='utf-8',capture_output=True)
            assert run.returncode==0,run.stderr
            if label:
                timings[label]=round(time.perf_counter()-started,3)
            return json.loads(run.stdout,parse_float=Decimal) if run.stdout.strip() else None
        setup = f"""CREATE SCHEMA raw; CREATE SCHEMA mart;
CREATE TABLE raw.m5_sales_wide AS SELECT item_id,dept_id,cat_id,store_id,state_id
FROM read_csv({quote(sources[0].as_posix())},header=true,all_varchar=true);
CREATE TABLE raw.m5_calendar AS SELECT * FROM read_csv({quote(sources[1].as_posix())},header=true,all_varchar=true);
"""
        setup += '\n'.join(prerequisites[p].decode('utf-8').split('-- VALIDATION:')[0] for p in prerequisite_paths)
        setup += f"""CREATE TABLE raw.training_wide AS SELECT item_id,store_id,{day_columns}
FROM read_csv({quote(sources[0].as_posix())},header=true,all_varchar=true)
WHERE dept_id=(SELECT MIN(dept_id) FROM core.m5_product) AND store_id=(SELECT MIN(store_id) FROM core.m5_store);
CREATE TABLE mart.m5_sales_daily AS
WITH u AS (SELECT item_id,store_id,d,units_text FROM raw.training_wide
UNPIVOT INCLUDE NULLS (units_text FOR d IN ({day_columns})))
SELECT u.item_id,u.store_id,u.d,c.date,c.wm_yr_wk,
CASE WHEN regexp_full_match(u.units_text,'[0-9]+') AND TRY_CAST(u.units_text AS INTEGER)>=0
THEN CAST(u.units_text AS INTEGER) ELSE error('Selected source training units violate INTEGER contract') END AS units
FROM u JOIN core.m5_calendar c USING(d);
"""
        before,export_before = export_snapshots(folder,'before')
        after,export_after = export_snapshots(folder,'after')
        execute(setup+export_before,'private_setup_and_input_export_seconds')
        row_counts = {}
        row_counts['product_dimension']=compare_csv(before['product_dimension'],['item_id','dept_id','cat_id'],products,'original products')
        row_counts['store_dimension']=compare_csv(before['store_dimension'],['store_id','state_id'],stores,'original stores')
        row_counts['calendar_projection']=compare_csv(before['calendar_projection'],['d','date','day_number','wm_yr_wk'],
            ((calendar[n][k] for k in ('d','date','day_number','wm_yr_wk')) for n in range(1,1970)),'original calendar')
        row_counts['raw_metadata_projection']=compare_csv(before['raw_metadata_projection'],METADATA_FIELDS,
            sorted(metadata,key=lambda r:(r[0],r[3],r[1],r[2],r[4])),'original raw metadata')
        def original_daily_rows():
            for item,selected_store in sorted(pairs):
                for n,units in enumerate(training[item],1):
                    yield item,selected_store,f'd_{n}',calendar[n]['date'],calendar[n]['wm_yr_wk'],units
        row_counts['selected_training_projection']=compare_csv(before['selected_training_projection'],DAILY_FIELDS,original_daily_rows(),'original training cells')
        assert row_counts['selected_training_projection']==413208
        reconstructed_scope = canonical_scope_report(execute(scope_sql,'accepted_scope_audit_seconds'))
        assert reconstructed_scope==reference_report(department,store,len(pairs),calendar)
        assert json_hash(reconstructed_scope)==accepted['ordered_result_sha256']
        execute(snaive_build,'existing_snaive_creation_seconds')
        reconstructed_snaive_report=canonical_snaive_report(execute(snaive_validation,'existing_snaive_validation_seconds'))
        assert reconstructed_snaive_report==expected_snaive_report
        assert json_hash(reconstructed_snaive_report)==snaive_accepted['ordered_result_sha256']
        old_before,old_after=folder/'snaive-before.csv',folder/'snaive-after.csv'
        execute(snaive_export(old_before))
        snaive_rows=compare_csv(old_before,SNAIVE_COLUMNS,
            (tuple(row[k] for k in SNAIVE_COLUMNS) for row in expected_snaive),'all original SNAIVE7 forecast fields')
        actual_snaive=read_snaive_csv(old_before)
        assert actual_snaive==expected_snaive and snaive_rows==24192
        reconstructed_snaive_hash=json_hash(actual_snaive)
        assert reconstructed_snaive_hash==snaive_preflight['ordered_forecast_rows_sha256']
        execute(build,'forecast_creation_seconds')
        forecast_before,forecast_after = folder/'forecast-before.csv',folder/'forecast-after.csv'
        execute(forecast_export(forecast_before))
        forecast_rows = compare_csv(forecast_before,FORECAST_COLUMNS,
            (tuple(row[k] for k in FORECAST_COLUMNS) for row in expected_forecasts),'all independent forecast fields')
        actual_forecasts = read_forecast_csv(forecast_before)
        assert actual_forecasts==expected_forecasts and forecast_rows==24192
        actual_report = canonical_report(execute(validation,'saved_forecast_validation_seconds'))
        assert actual_report==expected_report
        execute(export_after+forecast_export(forecast_after)+snaive_export(old_after),'unchanged_input_and_forecast_export_seconds')
        before_hashes = {key:sha256(path) for key,path in before.items()}
        after_hashes = {key:sha256(path) for key,path in after.items()}
        assert before_hashes==after_hashes
        assert sha256(forecast_before)==sha256(forecast_after)
        forecast_csv_hash = sha256(forecast_before)
        assert sha256(old_before)==sha256(old_after)
        snaive_csv_hash=sha256(old_before)
        actual_forecast_hash,expected_forecast_hash = json_hash(canonical_forecasts(actual_forecasts)),json_hash(canonical_forecasts(expected_forecasts))
        assert actual_forecast_hash==expected_forecast_hash
        database_bytes = database.stat().st_size
    assert not folder.exists()
    assert all(sha256(path)==source_hashes[path.name] for path in sources)
    assert sql_path.read_bytes()==sql_bytes and scope_path.read_bytes()==scope_bytes
    assert sha256(helper_path)==helper_hash and sha256(snaive_helper_path)==snaive_helper_hash
    assert snaive_sql_path.read_bytes()==snaive_sql_bytes
    assert all((root/path).read_bytes()==content for path,content in prerequisites.items())
    assert all(sha256(root/path)==value for path,value in historical.items())
    assert accepted_path.read_bytes()==accepted_bytes and snaive_accepted_path.read_bytes()==snaive_accepted_bytes
    report = dict(
        checked_at_utc=datetime.now(timezone.utc).isoformat(),executor='assistant',
        engine=subprocess.check_output([args.duckdb,'-version'],text=True).strip(),
        script=sql_path.relative_to(root).as_posix(),script_sha256=hashlib.sha256(sql_bytes).hexdigest(),
        accepted_scope_script=scope_path.relative_to(root).as_posix(),accepted_scope_script_sha256=hashlib.sha256(scope_bytes).hexdigest(),
        accepted_scope_cte_prefix_copies=2,accepted_scope_cte_prefix_sha256=hashlib.sha256(prefix.encode('utf-8')).hexdigest(),
        reference_helper_sha256={helper_path.relative_to(root).as_posix():helper_hash,snaive_helper_path.relative_to(root).as_posix():snaive_helper_hash},
        prerequisite_script_sha256={path:hashlib.sha256(content).hexdigest() for path,content in prerequisites.items()},
        accepted_scope_evidence=accepted_path.relative_to(root).as_posix(),accepted_scope_evidence_sha256=hashlib.sha256(accepted_bytes).hexdigest(),
        reconstructed_scope_result_sha256=json_hash(reconstructed_scope),accepted_scope_result_fingerprint_matched=True,
        existing_snaive_script=snaive_sql_path.relative_to(root).as_posix(),existing_snaive_script_sha256=hashlib.sha256(snaive_sql_bytes).hexdigest(),
        accepted_snaive_evidence=snaive_accepted_path.relative_to(root).as_posix(),accepted_snaive_evidence_sha256=hashlib.sha256(snaive_accepted_bytes).hexdigest(),
        reconstructed_snaive_result_sha256=json_hash(reconstructed_snaive_report),accepted_snaive_result_fingerprint_matched=True,
        preserved_snaive_rows_compared=snaive_rows,preserved_snaive_columns_compared=len(SNAIVE_COLUMNS),preserved_snaive_field_mismatches=0,
        reconstructed_snaive_forecast_rows_sha256=reconstructed_snaive_hash,accepted_snaive_forecast_fingerprint_matched=True,
        snaive_forecast_csv_sha256_before=snaive_csv_hash,snaive_forecast_csv_sha256_after=snaive_csv_hash,existing_snaive_forecasts_unchanged=True,
        source_sha256=source_hashes,source_hashes_unchanged=True,historical_preflight_sha256=historical,historical_preflights_unchanged=True,
        baseline_database='Private temporary DuckDB and detailed CSV exports under ignored repository tmp; resolved containment checked; removed after verification. Learner database never opened.',
        settings={'threads':2,'memory_limit':'2GB'},temporary_baseline_removed=True,temporary_database_bytes_after_close=database_bytes,
        frozen_scope={'dept_id':department,'store_id':store,'series_count':len(pairs),'series_membership_sha256':membership_hash(pairs)},
        model='WEEKDAY4',model_status='Baseline candidate generation, not final model selection or holdout evaluation.',
        forecast_rule='For origin T and offset r=(h-1)%7, average T-27+r, T-20+r, T-13+r and T-6+r including zeros. Sum as BIGINT and multiply by exact decimal 0.25. Preserve DECIMAL(18,2) quarter-unit predictions; repeat the seven means four times.',
        table=TABLE,table_grain=['model','origin','item_id','store_id','horizon_day'],table_columns=FORECAST_COLUMNS,
        table_rows=forecast_rows,forecast_columns_compared=len(FORECAST_COLUMNS),forecast_field_mismatches=0,
        source_training_rows_compared=413208,source_training_columns_compared=6,source_training_field_mismatches=0,
        source_metadata_and_calendar_projection_mismatches=0,saved_table_schema_and_order_verified=True,saved_table_unique_keys_verified=True,
        all_forecast_source_days_at_or_before_origin=True,all_source_days_within_origin_last_twenty_eight=True,exact_four_observation_denominator=True,decimal_quarter_units_preserved=True,
        final_holdout_unit_values_inspected=False,forecast_errors_computed=False,final_model_selected=False,
        independent_reference='Unmodified SQL33 Python helper independently parses original metadata/calendar and only selected d1..d1913 integers. This runner splits the last 28 inputs into four consecutive seven-day blocks, sums their columns and uses Python Decimal division by four; every one of 24192 saved rows and all fifteen fields are compared. It also checks all 413208 six-field training records and reconstructs all 24192 thirteen-field SNAIVE7 rows against its unmodified helper and accepted fingerprints. Calendar supplies future dates only.',
        result_rows=len(actual_report),result_columns=len(REPORT_COLUMNS),rows_with_pass_status=4,output_columns=REPORT_COLUMNS,
        results=actual_report,ordered_result_sha256=json_hash(actual_report),result_field_mismatches=0,
        ordered_forecast_rows_sha256=actual_forecast_hash,independent_reference_forecast_rows_sha256=expected_forecast_hash,
        forecast_fingerprint_method='SHA256 of UTF-8 compact JSON with sorted object keys and ensure_ascii=False. Rows ordered by train_end_day,item_id,store_id,horizon_day; source/count fields remain JSON integers, predictions are two-decimal strings, and DATE fields ISO strings. Detailed rows and identifiers exist only privately before hashing.',
        forecast_csv_sha256_before_validation=forecast_csv_hash,forecast_csv_sha256_after_validation=forecast_csv_hash,
        saved_forecast_validation_read_only=True,input_projection_row_counts=row_counts,
        input_projection_sha256_before=before_hashes,input_projection_sha256_after=after_hashes,scoped_input_projections_unchanged=True,
        input_fingerprint_method='SHA256 of deterministic private DuckDB CSV exports with header and fixed field/row order. Full product/store dimensions plus used calendar/raw metadata fields and only the selected canonical training projection are compared; this is not a full daily-fact audit.',
        timings=timings,timing_scope='Named Python source/reference and DuckDB process/export timings; remaining Python comparisons and hashing excluded.',
        fixture_cases_passed=len(cases),fixture_cases=cases,existing_forecast_table_never_overwritten=True,
        real_product_identifiers_published=False,individual_forecasts_published=False,daily_or_target_vectors_published=False,
        scope='Assistant preflight only; learner SQL35 creation/validation pending. Public evidence contains aggregate scope labels, per-origin controls and fingerprints. All original training dates through each origin remain available; development horizon days may become valid training at later origins, but each prediction uses four matching weekdays from its own last 28 origin-available observations. The existing SNAIVE7 table is preserved. Final holdout unit values are not accessed or scored. No forecast accuracy, model superiority, operational benefit or final selection is established.')
    serialized=json.dumps(report,indent=2,ensure_ascii=False)+'\n'
    assert all(item not in serialized for item,_,_ in products),'Real product identifier in public report'
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(serialized,encoding='utf-8',newline='\n')
    print(json.dumps({'fixture_cases_passed':len(cases),'table_rows':forecast_rows,'results':actual_report,
                      'ordered_forecast_rows_sha256':actual_forecast_hash,'timings':timings}),flush=True)


if __name__=='__main__':
    main()
