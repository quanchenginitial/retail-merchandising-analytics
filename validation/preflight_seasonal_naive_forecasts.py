"""Verify seasonal-naive forecasts independently from original training-only CSV values."""
import argparse
import csv
import hashlib
import json
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

sys.dont_write_bytecode = True
from preflight_forecast_scope_and_time_audit import (
    FIRST_DATE, ORIGINS, FROZEN_MEMBERSHIP, DAILY_FIELDS, METADATA_FIELDS,
    quote, sha256, json_hash, membership_hash, original_reference, reference_report,
    canonical_report as canonical_scope_report, export_snapshots, compare_csv,
)


TABLE = 'mart.m5_forecast_snaive7_28d'
FORECAST_COLUMNS = ['model','origin','dept_id','item_id','store_id','train_end_day','train_end','horizon_day',
                    'forecast_day','forecast_date','source_day','source_date','predicted_units']
INTEGER_COLUMNS = ['train_end_day','horizon_day','forecast_day','source_day','predicted_units']
REPORT_COLUMNS = ['origin','dept_id','store_id','series_count','forecast_rows','forecast_start','forecast_end',
                  'last7_units','predicted_units','zero_forecast_rows','check_status']
FORECAST_QUERY = f"SELECT {','.join(FORECAST_COLUMNS)} FROM {TABLE} ORDER BY train_end_day,item_id,store_id,horizon_day"


def forecast_reference(department, pairs, training, calendar):
    """Repeat an extracted seven-element Python slice four times; do not look up future outcomes."""
    rows = []
    for origin, last in ORIGINS:
        for item, store in sorted(pairs):
            pattern = training[item][last-7:last]
            assert len(pattern) == 7 and all(isinstance(v,int) and 0 <= v <= 2147483647 for v in pattern)
            for repeat in range(4):
                for position, units in enumerate(pattern, 1):
                    horizon = repeat*7+position
                    source = last-7+position
                    rows.append(dict(model='SNAIVE7',origin=origin,dept_id=department,item_id=item,store_id=store,
                                     train_end_day=last,train_end=calendar[last]['date'],horizon_day=horizon,
                                     forecast_day=last+horizon,forecast_date=calendar[last+horizon]['date'],
                                     source_day=source,source_date=calendar[source]['date'],predicted_units=units))
    assert len(rows) == 4*len(pairs)*28
    assert len({(r['model'],r['origin'],r['item_id'],r['store_id'],r['horizon_day']) for r in rows}) == len(rows)
    return rows


def forecast_report(department, store, pairs, training, calendar, forecasts):
    rows = []
    for origin, last in ORIGINS:
        origin_rows = [r for r in forecasts if r['origin'] == origin]
        last7 = sum(sum(training[item][last-7:last]) for item,_ in pairs)
        predicted = sum(r['predicted_units'] for r in origin_rows)
        assert predicted == 4*last7
        rows.append(dict(origin=origin,dept_id=department,store_id=store,series_count=len(pairs),
                         forecast_rows=len(origin_rows),forecast_start=calendar[last+1]['date'],
                         forecast_end=calendar[last+28]['date'],last7_units=last7,predicted_units=predicted,
                         zero_forecast_rows=sum(r['predicted_units']==0 for r in origin_rows),check_status='PASS'))
    return rows


def canonical_report(rows):
    result = []
    for row in rows:
        assert list(row) == REPORT_COLUMNS
        row = dict(row)
        for key in ('series_count','forecast_rows','last7_units','predicted_units','zero_forecast_rows'):
            row[key] = int(row[key])
        result.append(row)
    return result


def read_forecast_csv(path):
    with path.open(newline='',encoding='utf-8') as stream:
        reader = csv.DictReader(stream)
        assert reader.fieldnames == FORECAST_COLUMNS
        rows = []
        for row in reader:
            for key in INTEGER_COLUMNS:
                row[key] = int(row[key])
            rows.append(row)
    return rows


def forecast_export(path):
    return f"COPY ({FORECAST_QUERY}) TO {quote(path.as_posix())} (HEADER, DELIMITER ',');"


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
    sql_path = root/'sql/34_build_seasonal_naive_forecasts.sql'
    sql_bytes = sql_path.read_bytes()
    sql = sql_bytes.decode('utf-8')
    build, validation = sql.split('-- VALIDATION:',1)
    validation = '-- VALIDATION:'+validation
    scope_path = root/'sql/33_forecast_scope_and_time_audit.sql'
    scope_bytes = scope_path.read_bytes()
    scope_sql = scope_bytes.decode('utf-8')
    prefix = scope_sql[scope_sql.index('WITH parameters AS ('):scope_sql.index('\nSELECT o.origin,s.dept_id,s.store_id,t.series_count')]
    assert sql.count(prefix) == 2, 'Both SQL34 scope/time CTE prefixes must exactly match SQL33'
    helper_path = root/'validation/preflight_forecast_scope_and_time_audit.py'
    helper_hash = sha256(helper_path)
    historical = {p.relative_to(root).as_posix():sha256(p) for p in (root/'data').glob('*_preflight.json')
                  if p.name != 'seasonal_naive_forecasts_preflight.json'}
    prerequisite_paths = ['sql/08_stage_calendar.sql','sql/12_build_product_dimension.sql',
                          'sql/13_build_store_dimension.sql','sql/14_build_calendar_dimension.sql']
    prerequisites = {p:(root/p).read_bytes() for p in prerequisite_paths}
    cases = []
    fixture_hash = membership_hash([('P001','CA_1'),('P002','CA_1')])
    def fixture_sql(text):
        return text.replace('3049 AS expected_products,10 AS expected_stores','3 AS expected_products,2 AS expected_stores').replace(
            '216 AS expected_scope_series','2 AS expected_scope_series').replace(FROZEN_MEMBERSHIP,fixture_hash)
    fixture_build, fixture_validation = fixture_sql(build), fixture_sql(validation)
    from datetime import timedelta
    fixture_calendar = {n:dict(date=(FIRST_DATE+timedelta(days=n-1)).isoformat()) for n in range(1,1970)}
    fixture_pairs = [('P001','CA_1'),('P002','CA_1')]
    baseline_training = {'P001':[n%7 for n in range(1,1914)],'P002':[0]*1913}
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
CAST(CASE WHEN p.item_id='P002' THEN 0 ELSE c.day_number%7 END AS INTEGER) AS units
FROM core.m5_product p CROSS JOIN core.m5_calendar c WHERE p.dept_id='FOODS_1' AND c.day_number<=1941;
"""

    def tiny(name,input_mutation='',forecast_mutation='',reject_creation=False,reject_validation=False,training=None,check_no_overwrite=False):
        training = baseline_training if training is None else training
        expected = forecast_reference('FOODS_1',fixture_pairs,training,fixture_calendar)
        expected_report = forecast_report('FOODS_1','CA_1',fixture_pairs,training,fixture_calendar,expected)
        with tempfile.TemporaryDirectory(prefix='snaive7-fixture-',dir=tmp_root) as value:
            folder = Path(value).resolve()
            assert folder.is_relative_to(tmp_root.resolve())
            database = folder/'fixture.duckdb'
            settings = "SET threads=2; SET memory_limit='2GB';\n"
            def execute(text):
                return subprocess.run([args.duckdb,str(database),'-bail','-json'],input=settings+text,
                                      text=True,encoding='utf-8',capture_output=True)
            before,export_before = export_snapshots(folder,'before')
            after,export_after = export_snapshots(folder,'after')
            run = execute(fixture_setup+input_mutation+export_before)
            assert run.returncode == 0,(name,run.stderr)
            run = execute(fixture_build)
            if reject_creation:
                assert run.returncode != 0 and 'Seasonal naive forecast creation blocked' in run.stderr,(name,run.stderr)
                table_count = execute("SELECT COUNT(*) AS tables FROM information_schema.tables WHERE table_schema='mart' AND table_name='m5_forecast_snaive7_28d';")
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
                    assert run.returncode != 0 and 'Seasonal naive forecast validation blocked' in run.stderr,(name,run.stderr)
                else:
                    assert run.returncode == 0,(name,run.stderr)
                    assert canonical_report(json.loads(run.stdout)) == expected_report,name
                    observed = read_forecast_csv(forecast_before)
                    assert observed == expected,(name,'independent forecast fields differ')
                    if name == 'distinct_seven_day_pattern_repeats_four_times_and_zeros_remain':
                        first = [r for r in observed if r['origin']=='DEVELOPMENT_1' and r['item_id']=='P001']
                        assert [r['predicted_units'] for r in first] == [3,4,5,6,0,1,2]*4
                        assert [r['source_day'] for r in first] == list(range(1823,1830))*4
                    if name in ('future_weeks_inside_development_horizon_do_not_feed_later_horizons','final_holdout_values_changed_without_effect','final_holdout_observations_absent_without_effect'):
                        assert observed == baseline_forecasts,name
                    if name == 'later_origin_input_changes_leave_earlier_origin_unchanged':
                        assert [r for r in observed if r['origin']=='DEVELOPMENT_1'] == [r for r in baseline_forecasts if r['origin']=='DEVELOPMENT_1']
                        assert [r for r in observed if r['origin']=='DEVELOPMENT_2'] != [r for r in baseline_forecasts if r['origin']=='DEVELOPMENT_2']
                run = execute(forecast_export(forecast_after))
                assert run.returncode == 0 and sha256(forecast_before)==sha256(forecast_after),(name,'saved forecasts changed')
            run = execute(export_after)
            assert run.returncode == 0,(name,run.stderr)
            assert all(sha256(before[k])==sha256(after[k]) for k in before),(name,'source projection changed')
        assert not folder.exists()
        cases.append(dict(case=name,passed=True,creation_rejected=reject_creation,validation_rejected=reject_validation,
                          source_projections_unchanged=True,saved_forecast_validation_read_only=not reject_creation,
                          failed_creation_left_no_table=reject_creation))

    tiny('distinct_seven_day_pattern_repeats_four_times_and_zeros_remain',check_no_overwrite=True)
    tiny('all_zero_series_produce_all_zero_forecasts',input_mutation="UPDATE mart.m5_sales_daily SET units=0;",training={k:[0]*1913 for k in baseline_training})
    future_mutation = "UPDATE mart.m5_sales_daily SET units=1000 WHERE item_id='P001' AND CAST(SUBSTR(d,3) AS INTEGER) BETWEEN 1830 AND 1850;"
    changed_future_training = {k:list(v) for k,v in baseline_training.items()}
    changed_future_training['P001'][1829:1850] = [1000]*21
    tiny('future_weeks_inside_development_horizon_do_not_feed_later_horizons',input_mutation=future_mutation,training=changed_future_training)
    changed_later_training = {k:list(v) for k,v in baseline_training.items()}
    changed_later_training['P001'][1856] = 99
    tiny('later_origin_input_changes_leave_earlier_origin_unchanged',input_mutation="UPDATE mart.m5_sales_daily SET units=99 WHERE item_id='P001' AND d='d_1857';",training=changed_later_training)
    tiny('final_holdout_values_changed_without_effect',input_mutation="UPDATE mart.m5_sales_daily SET units=CASE WHEN item_id='P001' THEN -99 ELSE NULL END,date=DATE '2016-01-01' WHERE CAST(SUBSTR(d,3) AS INTEGER)>1913;")
    tiny('final_holdout_observations_absent_without_effect',input_mutation="DELETE FROM mart.m5_sales_daily WHERE CAST(SUBSTR(d,3) AS INTEGER)>1913;")
    for name,mutation in [
        ('missing_origin_last_seven_day_input','DELETE FROM mart.m5_sales_daily WHERE item_id=\'P002\' AND d=\'d_1829\';'),
        ('balanced_duplicate_and_missing_training_day',"DELETE FROM mart.m5_sales_daily WHERE item_id='P002' AND d='d_100'; INSERT INTO mart.m5_sales_daily SELECT * FROM mart.m5_sales_daily WHERE item_id='P002' AND d='d_101';"),
        ('null_training_units',"UPDATE mart.m5_sales_daily SET units=NULL WHERE item_id='P001' AND d='d_1829';"),
        ('empty_input_cannot_create_empty_forecast_table',"DELETE FROM mart.m5_sales_daily;"),
        ('fractional_training_type_rejected',"ALTER TABLE mart.m5_sales_daily ALTER units TYPE DOUBLE; UPDATE mart.m5_sales_daily SET units=0.5 WHERE item_id='P001' AND d='d_1829';"),
    ]:
        tiny(name,input_mutation=mutation,reject_creation=True)
    for name,mutation in [
        ('saved_forecast_value_changed',f"UPDATE {TABLE} SET predicted_units=predicted_units+1 WHERE origin='DEVELOPMENT_1' AND item_id='P001' AND horizon_day=1;"),
        ('saved_values_swapped_without_changing_total',f"UPDATE {TABLE} SET predicted_units=CASE WHEN horizon_day=1 THEN 4 ELSE 3 END WHERE origin='DEVELOPMENT_1' AND item_id='P001' AND horizon_day IN (1,2);"),
        ('saved_source_day_leaks_beyond_origin',f"UPDATE {TABLE} SET source_day=train_end_day+1,source_date=train_end+1 WHERE origin='DEVELOPMENT_1' AND item_id='P001' AND horizon_day=8;"),
        ('saved_duplicate_and_missing_key_preserve_count',f"DELETE FROM {TABLE} WHERE origin='DEVELOPMENT_1' AND item_id='P001' AND horizon_day=1; INSERT INTO {TABLE} SELECT * FROM {TABLE} WHERE origin='DEVELOPMENT_1' AND item_id='P001' AND horizon_day=2;"),
        ('saved_forecast_row_missing',f"DELETE FROM {TABLE} WHERE origin='DEVELOPMENT_1' AND item_id='P001' AND horizon_day=1;"),
        ('saved_forecast_date_changed',f"UPDATE {TABLE} SET forecast_date=forecast_date+1 WHERE origin='DEVELOPMENT_1' AND item_id='P001' AND horizon_day=1;"),
        ('saved_predicted_units_wrong_type',f"ALTER TABLE {TABLE} ALTER predicted_units TYPE BIGINT;"),
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
    timings = {}
    started = time.perf_counter()
    calendar,metadata,products,stores,department,store,pairs,training = original_reference(*sources)
    expected_forecasts = forecast_reference(department,pairs,training,calendar)
    expected_report = forecast_report(department,store,pairs,training,calendar,expected_forecasts)
    timings['independent_python_source_and_forecast_reference_seconds'] = round(time.perf_counter()-started,3)
    day_columns = ','.join(f'd_{n}' for n in range(1,1914))
    with tempfile.TemporaryDirectory(prefix='snaive7-source-',dir=tmp_root) as value:
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
            return json.loads(run.stdout) if run.stdout.strip() else None
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
        execute(build,'forecast_creation_seconds')
        forecast_before,forecast_after = folder/'forecast-before.csv',folder/'forecast-after.csv'
        execute(forecast_export(forecast_before))
        forecast_rows = compare_csv(forecast_before,FORECAST_COLUMNS,
            (tuple(row[k] for k in FORECAST_COLUMNS) for row in expected_forecasts),'all independent forecast fields')
        actual_forecasts = read_forecast_csv(forecast_before)
        assert actual_forecasts==expected_forecasts and forecast_rows==24192
        actual_report = canonical_report(execute(validation,'saved_forecast_validation_seconds'))
        assert actual_report==expected_report
        execute(export_after+forecast_export(forecast_after),'unchanged_input_and_forecast_export_seconds')
        before_hashes = {key:sha256(path) for key,path in before.items()}
        after_hashes = {key:sha256(path) for key,path in after.items()}
        assert before_hashes==after_hashes
        assert sha256(forecast_before)==sha256(forecast_after)
        forecast_csv_hash = sha256(forecast_before)
        actual_forecast_hash,expected_forecast_hash = json_hash(actual_forecasts),json_hash(expected_forecasts)
        assert actual_forecast_hash==expected_forecast_hash
        database_bytes = database.stat().st_size
    assert not folder.exists()
    assert all(sha256(path)==source_hashes[path.name] for path in sources)
    assert sql_path.read_bytes()==sql_bytes and scope_path.read_bytes()==scope_bytes
    assert sha256(helper_path)==helper_hash
    assert all((root/path).read_bytes()==content for path,content in prerequisites.items())
    assert all(sha256(root/path)==value for path,value in historical.items())
    assert accepted_path.read_bytes()==accepted_bytes
    report = dict(
        checked_at_utc=datetime.now(timezone.utc).isoformat(),executor='assistant',
        engine=subprocess.check_output([args.duckdb,'-version'],text=True).strip(),
        script=sql_path.relative_to(root).as_posix(),script_sha256=hashlib.sha256(sql_bytes).hexdigest(),
        accepted_scope_script=scope_path.relative_to(root).as_posix(),accepted_scope_script_sha256=hashlib.sha256(scope_bytes).hexdigest(),
        accepted_scope_cte_prefix_copies=2,accepted_scope_cte_prefix_sha256=hashlib.sha256(prefix.encode('utf-8')).hexdigest(),
        reference_helper_sha256={helper_path.relative_to(root).as_posix():helper_hash},
        prerequisite_script_sha256={path:hashlib.sha256(content).hexdigest() for path,content in prerequisites.items()},
        accepted_scope_evidence=accepted_path.relative_to(root).as_posix(),accepted_scope_evidence_sha256=hashlib.sha256(accepted_bytes).hexdigest(),
        reconstructed_scope_result_sha256=json_hash(reconstructed_scope),accepted_scope_result_fingerprint_matched=True,
        source_sha256=source_hashes,source_hashes_unchanged=True,historical_preflight_sha256=historical,historical_preflights_unchanged=True,
        baseline_database='Private temporary DuckDB and detailed CSV exports under ignored repository tmp; resolved containment checked; removed after verification. Learner database never opened.',
        settings={'threads':2,'memory_limit':'2GB'},temporary_baseline_removed=True,temporary_database_bytes_after_close=database_bytes,
        frozen_scope={'dept_id':department,'store_id':store,'series_count':len(pairs),'series_membership_sha256':membership_hash(pairs)},
        model='SNAIVE7',model_status='Baseline candidate generation, not final model selection or holdout evaluation.',
        forecast_rule='For origin T and h=1..28, source day is T-6+((h-1)%7). Repeat the same last-seven-day pattern four times; preserve zero INTEGER predictions.',
        table=TABLE,table_grain=['model','origin','item_id','store_id','horizon_day'],table_columns=FORECAST_COLUMNS,
        table_rows=forecast_rows,forecast_columns_compared=len(FORECAST_COLUMNS),forecast_field_mismatches=0,
        source_training_rows_compared=413208,source_training_columns_compared=6,source_training_field_mismatches=0,
        source_metadata_and_calendar_projection_mismatches=0,saved_table_schema_and_order_verified=True,saved_table_unique_keys_verified=True,
        all_forecast_source_days_at_or_before_origin=True,all_source_days_within_origin_last_seven=True,
        final_holdout_unit_values_inspected=False,forecast_errors_computed=False,final_model_selected=False,
        independent_reference='Unmodified SQL33 Python helper independently parses original metadata/calendar and only selected d1..d1913 integers. This runner extracts each seven-element origin-local slice and repeats it four times in Python; every one of 24192 persisted rows and all thirteen fields are compared, together with all 413208 six-field training records. Calendar supplies future dates only.',
        result_rows=len(actual_report),result_columns=len(REPORT_COLUMNS),rows_with_pass_status=4,output_columns=REPORT_COLUMNS,
        results=actual_report,ordered_result_sha256=json_hash(actual_report),result_field_mismatches=0,
        ordered_forecast_rows_sha256=actual_forecast_hash,independent_reference_forecast_rows_sha256=expected_forecast_hash,
        forecast_fingerprint_method='SHA256 of UTF-8 compact JSON with sorted object keys and ensure_ascii=False. Rows ordered by train_end_day,item_id,store_id,horizon_day; integer fields remain JSON integers and DATE fields ISO strings. Detailed rows and identifiers exist only privately before hashing.',
        forecast_csv_sha256_before_validation=forecast_csv_hash,forecast_csv_sha256_after_validation=forecast_csv_hash,
        saved_forecast_validation_read_only=True,input_projection_row_counts=row_counts,
        input_projection_sha256_before=before_hashes,input_projection_sha256_after=after_hashes,scoped_input_projections_unchanged=True,
        input_fingerprint_method='SHA256 of deterministic private DuckDB CSV exports with header and fixed field/row order. Full product/store dimensions plus used calendar/raw metadata fields and only the selected canonical training projection are compared; this is not a full daily-fact audit.',
        timings=timings,timing_scope='Named Python source/reference and DuckDB process/export timings; remaining Python comparisons and hashing excluded.',
        fixture_cases_passed=len(cases),fixture_cases=cases,existing_forecast_table_never_overwritten=True,
        real_product_identifiers_published=False,individual_forecasts_published=False,daily_or_target_vectors_published=False,
        scope='Assistant preflight only; learner SQL34 creation/validation pending. Public evidence contains aggregate scope labels, per-origin controls and fingerprints. All original training dates through each origin remain available; development horizon days may become valid training at later origins, but each prediction uses only its own last seven origin-available observations. Final holdout unit values are not accessed or scored. No forecast accuracy, model superiority, operational benefit or final selection is established.')
    serialized=json.dumps(report,indent=2,ensure_ascii=False)+'\n'
    assert all(item not in serialized for item,_,_ in products),'Real product identifier in public report'
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(serialized,encoding='utf-8',newline='\n')
    print(json.dumps({'fixture_cases_passed':len(cases),'table_rows':forecast_rows,'results':actual_report,
                      'ordered_forecast_rows_sha256':actual_forecast_hash,'timings':timings}),flush=True)


if __name__=='__main__':
    main()
