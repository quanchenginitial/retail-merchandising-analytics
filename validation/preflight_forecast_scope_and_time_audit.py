"""Independently audit the frozen forecast slice and time boundaries in private DuckDB files."""
import argparse
import csv
import hashlib
import json
import re
import subprocess
import tempfile
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path


FIRST_DATE = date(2011, 1, 29)
ORIGINS = [('DEVELOPMENT_1', 1829), ('DEVELOPMENT_2', 1857), ('DEVELOPMENT_3', 1885), ('FINAL_HOLDOUT', 1913)]
COLUMNS = ['origin', 'dept_id', 'store_id', 'series_count', 'train_end_day', 'train_end', 'forecast_start',
           'forecast_end', 'training_rows', 'last7_rows', 'last28_rows', 'forecast_calendar_days', 'check_status']
FROZEN_MEMBERSHIP = '6cabe9ae29616ce129fdf89fb02fec1cffd31ccb8194c4694b8bdf0ed85e622f'
DAILY_FIELDS = ['item_id', 'store_id', 'd', 'date', 'wm_yr_wk', 'units']
METADATA_FIELDS = ['item_id', 'dept_id', 'cat_id', 'store_id', 'state_id']


def quote(value):
    return "'" + str(value).replace("'", "''") + "'"


def sha256(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def json_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def membership_hash(pairs):
    assert all(re.fullmatch(r'[A-Z0-9_]+', value) for pair in pairs for value in pair)
    return hashlib.sha256('\n'.join(item+'|'+store for item, store in sorted(pairs)).encode('utf-8')).hexdigest()


def reference_report(department, store, series_count, calendar):
    rows = []
    for origin, last in ORIGINS:
        horizon = [calendar[n]['date'] for n in range(last+1, last+29)]
        assert horizon == [(FIRST_DATE+timedelta(days=n-1)).isoformat() for n in range(last+1, last+29)]
        rows.append(dict(origin=origin, dept_id=department, store_id=store, series_count=series_count,
                         train_end_day=last, train_end=calendar[last]['date'], forecast_start=horizon[0],
                         forecast_end=horizon[-1], training_rows=series_count*last, last7_rows=series_count*7,
                         last28_rows=series_count*28, forecast_calendar_days=len(horizon), check_status='PASS'))
    return rows


def canonical_report(rows):
    result = []
    integer_fields = ['series_count', 'train_end_day', 'training_rows', 'last7_rows', 'last28_rows', 'forecast_calendar_days']
    for row in rows:
        assert list(row) == COLUMNS
        row = dict(row)
        for key in integer_fields:
            row[key] = int(row[key])
        result.append(row)
    return result


def original_reference(sales_path, calendar_path):
    calendar = {}
    with calendar_path.open(newline='', encoding='utf-8-sig') as stream:
        for row in csv.DictReader(stream):
            assert re.fullmatch(r'd_[1-9][0-9]*', row['d'])
            day = int(row['d'][2:])
            assert day not in calendar and 1 <= day <= 1969
            assert row['date'] == (FIRST_DATE+timedelta(days=day-1)).isoformat()
            assert re.fullmatch(r'[1-9][0-9]{4}', row['wm_yr_wk'])
            calendar[day] = dict(d=row['d'], date=row['date'], day_number=day, wm_yr_wk=int(row['wm_yr_wk']))
    assert set(calendar) == set(range(1, 1970))
    metadata = []
    with sales_path.open(newline='', encoding='utf-8-sig') as stream:
        reader = csv.reader(stream)
        header = next(reader)
        assert header[:6] == ['id', 'item_id', 'dept_id', 'cat_id', 'store_id', 'state_id']
        assert header[6:1919] == [f'd_{n}' for n in range(1, 1914)]
        for row in reader:
            metadata.append(tuple(row[1:6]))
    products = sorted({r[:3] for r in metadata})
    stores = sorted({r[3:] for r in metadata})
    assert len(metadata) == 30490 and len(products) == 3049 and len(stores) == 10
    assert len({(r[0], r[3]) for r in metadata}) == len(metadata)
    assert len({r[0] for r in products}) == len(products) and len({r[0] for r in stores}) == len(stores)
    department, store = min(r[1] for r in products), min(r[0] for r in stores)
    items = sorted(r[0] for r in products if r[1] == department)
    pairs = [(item, store) for item in items]
    assert (department, store, len(items)) == ('FOODS_1', 'CA_1', 216)
    assert membership_hash(pairs) == FROZEN_MEMBERSHIP
    training = {}
    # CSV tokenization sees complete records; only selected d_1..d_1913 fields are inspected or converted.
    # Future day cells are discarded without accessing their values or computing outcomes.
    with sales_path.open(newline='', encoding='utf-8-sig') as stream:
        reader = csv.reader(stream)
        next(reader)
        for row in reader:
            if row[1] not in items or row[4] != store:
                continue
            values = row[6:1919]
            assert len(values) == 1913 and all(re.fullmatch(r'[0-9]+', v) for v in values)
            units = [int(v) for v in values]
            assert all(0 <= v <= 2147483647 for v in units) and row[1] not in training
            training[row[1]] = units
    assert sorted(training) == items
    return calendar, metadata, products, stores, department, store, pairs, training


def selected_daily_query():
    return """SELECT f.item_id,f.store_id,f.d,f.date,f.wm_yr_wk,f.units
FROM mart.m5_sales_daily f JOIN core.m5_product p USING(item_id)
WHERE p.dept_id=(SELECT MIN(dept_id) FROM core.m5_product)
AND f.store_id=(SELECT MIN(store_id) FROM core.m5_store)
AND f.d IN (SELECT 'd_'||CAST(n AS VARCHAR) FROM range(1,1914) t(n))
ORDER BY f.item_id,f.store_id,TRY_CAST(SUBSTR(f.d,3) AS INTEGER),f.date,f.wm_yr_wk,f.units"""


SNAPSHOTS = {
    'product_dimension': 'SELECT item_id,dept_id,cat_id FROM core.m5_product ORDER BY item_id,dept_id,cat_id',
    'store_dimension': 'SELECT store_id,state_id FROM core.m5_store ORDER BY store_id,state_id',
    'calendar_projection': 'SELECT d,date,day_number,wm_yr_wk FROM core.m5_calendar ORDER BY day_number,d,date,wm_yr_wk',
    'raw_metadata_projection': 'SELECT item_id,dept_id,cat_id,store_id,state_id FROM raw.m5_sales_wide ORDER BY item_id,store_id,dept_id,cat_id,state_id',
    'selected_training_projection': selected_daily_query(),
}


def export_snapshots(folder, prefix):
    paths = {key: folder/(prefix+'-'+key+'.csv') for key in SNAPSHOTS}
    sql = '\n'.join(f'COPY ({query}) TO {quote(paths[key].as_posix())} (HEADER, DELIMITER \',\');' for key, query in SNAPSHOTS.items())
    return paths, sql


def compare_csv(path, fields, rows, label):
    count = 0
    with path.open(newline='', encoding='utf-8') as stream:
        reader = csv.reader(stream)
        assert next(reader) == fields, label+' columns'
        for expected in rows:
            actual = next(reader, None)
            assert actual == [str(v) for v in expected], (label, count, 'source field mismatch')
            count += 1
        assert next(reader, None) is None, label+' unexpected extra row'
    return count


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--duckdb', required=True)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--fixtures-only', action='store_true')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    tmp_root = root/'tmp'
    tmp_root.mkdir(exist_ok=True)
    assert tmp_root.resolve().is_relative_to(root.resolve())
    sql_path = root/'sql/33_forecast_scope_and_time_audit.sql'
    sql_bytes = sql_path.read_bytes()
    query = sql_bytes.decode('utf-8')
    historical = {p.relative_to(root).as_posix(): sha256(p) for p in (root/'data').glob('*_preflight.json')
                  if p.name != 'forecast_scope_and_time_audit_preflight.json'}
    prerequisite_paths = ['sql/08_stage_calendar.sql', 'sql/12_build_product_dimension.sql',
                          'sql/13_build_store_dimension.sql', 'sql/14_build_calendar_dimension.sql']
    prerequisites = {p: (root/p).read_bytes() for p in prerequisite_paths}
    cases = []
    fixture_membership = membership_hash([('P001', 'CA_1'), ('P002', 'CA_1')])
    fixture_query = query.replace('3049 AS expected_products,10 AS expected_stores', '3 AS expected_products,2 AS expected_stores')
    fixture_query = fixture_query.replace('216 AS expected_scope_series', '2 AS expected_scope_series').replace(FROZEN_MEMBERSHIP, fixture_membership)
    fixture_calendar = {n: dict(date=(FIRST_DATE+timedelta(days=n-1)).isoformat()) for n in range(1, 1970)}
    fixture_expected = reference_report('FOODS_1', 'CA_1', 2, fixture_calendar)
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

    def tiny(name, mutation='', reject=False):
        with tempfile.TemporaryDirectory(prefix='forecast-scope-fixture-', dir=tmp_root) as value:
            folder = Path(value).resolve()
            assert folder.is_relative_to(tmp_root.resolve())
            database = folder/'fixture.duckdb'
            settings = "SET threads=2; SET memory_limit='2GB';\n"
            def execute(sql):
                return subprocess.run([args.duckdb, str(database), '-bail', '-json'], input=settings+sql,
                                      text=True, encoding='utf-8', capture_output=True)
            before, export_before = export_snapshots(folder, 'before')
            after, export_after = export_snapshots(folder, 'after')
            run = execute(fixture_setup+mutation+export_before)
            assert run.returncode == 0, (name, run.stderr)
            run = execute(fixture_query)
            if reject:
                assert run.returncode != 0 and 'Forecast scope/time audit blocked' in run.stderr, (name, run.stderr)
            else:
                assert run.returncode == 0, (name, run.stderr)
                assert canonical_report(json.loads(run.stdout)) == fixture_expected, name
            run = execute(export_after)
            assert run.returncode == 0, (name, run.stderr)
            assert all(sha256(before[k]) == sha256(after[k]) for k in before), name+' input changed'
        assert not folder.exists()
        cases.append(dict(case=name, passed=True, rejected=reject, scoped_input_projections_unchanged=True))

    tiny('metadata_order_independent_and_zero_series_retained')
    tiny('all_training_units_zero_still_retains_every_series', "UPDATE mart.m5_sales_daily SET units=0 WHERE d IN (SELECT 'd_'||CAST(n AS VARCHAR) FROM range(1,1914) t(n));")
    tiny('holdout_negative_null_units_and_changed_dates_ignored', "UPDATE mart.m5_sales_daily SET units=CASE WHEN item_id='P001' THEN -99 ELSE NULL END,date=DATE '2016-01-01' WHERE CAST(SUBSTR(d,3) AS INTEGER)>1913;")
    tiny('holdout_observations_absent_calendar_still_available', "DELETE FROM mart.m5_sales_daily WHERE CAST(SUBSTR(d,3) AS INTEGER)>1913;")
    tiny('unselected_series_bad_units_ignored', "INSERT INTO mart.m5_sales_daily VALUES ('P003','CA_1','d_1',DATE '2011-01-29',11000,-9);")
    for name, mutation in [
        ('missing_zero_training_day', "DELETE FROM mart.m5_sales_daily WHERE item_id='P002' AND d='d_100';"),
        ('balanced_duplicate_and_missing_training_day', "DELETE FROM mart.m5_sales_daily WHERE item_id='P002' AND d='d_100'; INSERT INTO mart.m5_sales_daily SELECT * FROM mart.m5_sales_daily WHERE item_id='P002' AND d='d_101';"),
        ('swapped_training_dates', "UPDATE mart.m5_sales_daily SET date=CASE WHEN d='d_100' THEN DATE '2011-05-09' ELSE DATE '2011-05-08' END WHERE item_id='P001' AND d IN ('d_100','d_101');"),
        ('noncanonical_training_day_label', "UPDATE mart.m5_sales_daily SET d='d_0001' WHERE item_id='P001' AND d='d_1';"),
        ('extra_malformed_training_record_not_silently_dropped', "INSERT INTO mart.m5_sales_daily VALUES ('P001','CA_1',NULL,DATE '2011-01-29',11000,0);"),
        ('training_key_moved_beyond_cutoff', "UPDATE mart.m5_sales_daily SET d='d_1941' WHERE item_id='P001' AND d='d_1913';"),
        ('null_training_units', "UPDATE mart.m5_sales_daily SET units=NULL WHERE item_id='P002' AND d='d_100';"),
        ('negative_training_units', "UPDATE mart.m5_sales_daily SET units=-1 WHERE item_id='P002' AND d='d_100';"),
        ('fractional_training_column_rejected', "ALTER TABLE mart.m5_sales_daily ALTER units TYPE DOUBLE; UPDATE mart.m5_sales_daily SET units=0.5 WHERE item_id='P002' AND d='d_100';"),
        ('changed_training_retail_week', "UPDATE mart.m5_sales_daily SET wm_yr_wk=1 WHERE item_id='P001' AND d='d_100';"),
        ('selected_training_store_changed', "UPDATE mart.m5_sales_daily SET store_id='TX_1' WHERE item_id='P001' AND d='d_100';"),
        ('entire_training_input_empty_errors_instead_of_no_rows', "DELETE FROM mart.m5_sales_daily;"),
        ('empty_product_dimension_errors_instead_of_no_rows', "DELETE FROM core.m5_product;"),
        ('duplicate_product_key', "INSERT INTO core.m5_product SELECT * FROM core.m5_product WHERE item_id='P001';"),
        ('product_source_mapping_changed', "UPDATE core.m5_product SET dept_id='FOODS_2' WHERE item_id='P002';"),
        ('same_count_membership_changed_consistently_in_all_tables', "UPDATE core.m5_product SET item_id='P004' WHERE item_id='P002'; UPDATE raw.m5_sales_wide SET item_id='P004' WHERE item_id='P002'; UPDATE mart.m5_sales_daily SET item_id='P004' WHERE item_id='P002';"),
        ('frozen_department_changed_consistently', "UPDATE core.m5_product SET dept_id='FOODS_0' WHERE dept_id='FOODS_1'; UPDATE raw.m5_sales_wide SET dept_id='FOODS_0' WHERE dept_id='FOODS_1';"),
        ('selected_raw_series_missing', "DELETE FROM raw.m5_sales_wide WHERE item_id='P002' AND store_id='CA_1';"),
        ('duplicate_selected_raw_series', "INSERT INTO raw.m5_sales_wide SELECT * FROM raw.m5_sales_wide WHERE item_id='P002' AND store_id='CA_1';"),
        ('store_state_mapping_changed', "UPDATE core.m5_store SET state_id='WRONG' WHERE store_id='CA_1';"),
        ('missing_calendar_training_date', "DELETE FROM core.m5_calendar WHERE day_number=100;"),
        ('balanced_duplicate_and_missing_calendar_day', "DELETE FROM core.m5_calendar WHERE day_number=100; INSERT INTO core.m5_calendar SELECT * FROM core.m5_calendar WHERE day_number=101;"),
        ('altered_forecast_calendar_boundary', "UPDATE core.m5_calendar SET date=date+1 WHERE day_number=1941;"),
        ('missing_final_forecast_calendar_day', "DELETE FROM core.m5_calendar WHERE day_number=1941;"),
        ('calendar_derived_day_number_corrupted', "UPDATE core.m5_calendar SET day_number=999 WHERE d='d_100';"),
        ('future_calendar_key_reassigned_to_training_day', "UPDATE core.m5_calendar SET day_number=1913 WHERE d='d_1914';"),
        ('calendar_day_number_wrong_type', "ALTER TABLE core.m5_calendar ALTER day_number TYPE BIGINT;"),
        ('extra_product_schema_column', "ALTER TABLE core.m5_product ADD COLUMN extra VARCHAR;"),
    ]:
        tiny(name, mutation, True)
    print(json.dumps({'fixture_cases_passed': len(cases)}), flush=True)
    if args.fixtures_only:
        return

    source_root = Path('D:/database/m5-forecasting-accuracy')
    sources = [source_root/'sales_train_evaluation.csv', source_root/'calendar.csv']
    registry = json.loads((root/'data/m5_source_audit.json').read_text(encoding='utf-8'))
    source_hashes = {p.name: sha256(p) for p in sources}
    assert all(source_hashes[p.name] == registry['files'][p.name]['sha256'] for p in sources)
    timings = {}
    started = time.perf_counter()
    calendar, metadata, products, stores, department, store, pairs, training = original_reference(*sources)
    timings['independent_python_csv_reference_seconds'] = round(time.perf_counter()-started, 3)
    expected = reference_report(department, store, len(pairs), calendar)
    day_columns = ','.join(f'd_{n}' for n in range(1, 1914))
    with tempfile.TemporaryDirectory(prefix='forecast-scope-source-', dir=tmp_root) as value:
        folder = Path(value).resolve()
        assert folder.is_relative_to(tmp_root.resolve())
        database = folder/'preflight.duckdb'
        settings = f"SET threads=2; SET memory_limit='2GB'; SET temp_directory={quote((folder/'spill').as_posix())};\n"
        def execute(sql, label=None):
            started = time.perf_counter()
            run = subprocess.run([args.duckdb, str(database), '-bail', '-json'], input=settings+sql,
                                 text=True, encoding='utf-8', capture_output=True)
            assert run.returncode == 0, run.stderr
            if label:
                timings[label] = round(time.perf_counter()-started, 3)
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
        before, export_before = export_snapshots(folder, 'before')
        after, export_after = export_snapshots(folder, 'after')
        execute(setup+export_before, 'private_setup_and_input_export_seconds')
        row_counts = {}
        row_counts['product_dimension'] = compare_csv(before['product_dimension'], ['item_id','dept_id','cat_id'], products, 'original product mapping')
        row_counts['store_dimension'] = compare_csv(before['store_dimension'], ['store_id','state_id'], stores, 'original store mapping')
        row_counts['calendar_projection'] = compare_csv(before['calendar_projection'], ['d','date','day_number','wm_yr_wk'],
            ((calendar[n][k] for k in ('d','date','day_number','wm_yr_wk')) for n in range(1,1970)), 'original calendar mapping')
        row_counts['raw_metadata_projection'] = compare_csv(before['raw_metadata_projection'], METADATA_FIELDS,
            sorted(metadata,key=lambda r:(r[0],r[3],r[1],r[2],r[4])), 'original raw metadata')
        def original_daily_rows():
            for item, selected_store in sorted(pairs):
                for n, units in enumerate(training[item], 1):
                    yield item, selected_store, f'd_{n}', calendar[n]['date'], calendar[n]['wm_yr_wk'], units
        row_counts['selected_training_projection'] = compare_csv(before['selected_training_projection'], DAILY_FIELDS,
            original_daily_rows(), 'all original selected training cells')
        assert row_counts['selected_training_projection'] == 216*1913
        runtime_membership = execute("SELECT sha256(string_agg(item_id||'|'||s.store_id,chr(10) ORDER BY item_id,s.store_id)) AS membership_sha256 FROM core.m5_product CROSS JOIN (SELECT MIN(store_id) AS store_id FROM core.m5_store) s WHERE dept_id=(SELECT MIN(dept_id) FROM core.m5_product);")
        assert runtime_membership[0]['membership_sha256'] == membership_hash(pairs) == FROZEN_MEMBERSHIP
        actual = canonical_report(execute(query, 'scope_time_audit_query_seconds'))
        assert actual == expected
        execute(export_after, 'unchanged_input_export_seconds')
        before_hashes = {key: sha256(path) for key, path in before.items()}
        after_hashes = {key: sha256(path) for key, path in after.items()}
        assert before_hashes == after_hashes
        database_bytes = database.stat().st_size
    assert not folder.exists()
    assert all(sha256(path) == source_hashes[path.name] for path in sources)
    assert sql_path.read_bytes() == sql_bytes
    assert all((root/path).read_bytes() == content for path, content in prerequisites.items())
    assert all(sha256(root/path) == value for path, value in historical.items())
    report = dict(
        checked_at_utc=datetime.now(timezone.utc).isoformat(), executor='assistant',
        engine=subprocess.check_output([args.duckdb,'-version'],text=True).strip(),
        script=sql_path.relative_to(root).as_posix(), script_sha256=hashlib.sha256(sql_bytes).hexdigest(),
        prerequisite_script_sha256={path:hashlib.sha256(content).hexdigest() for path,content in prerequisites.items()},
        source_sha256=source_hashes, source_hashes_unchanged=True,
        historical_preflight_sha256=historical, historical_preflights_unchanged=True,
        baseline_database='Private temporary DuckDB and row-level CSV exports under ignored repository tmp; resolved containment checked; all removed after verification. Learner database never opened.',
        settings={'threads':2,'memory_limit':'2GB'}, temporary_baseline_removed=True,
        temporary_database_bytes_after_close=database_bytes,
        selection_policy='Lexicographically first department and first store from validated source-backed dimensions. Frozen retrospective released-catalog benchmark roster; no observed-sales eligibility filter and no claim of origin-time active assortment.',
        frozen_scope={'dept_id':department,'store_id':store,'series_count':len(pairs),'series_membership_sha256':membership_hash(pairs)},
        membership_fingerprint_method='SHA256 of UTF-8 item_id|store_id lines sorted by item_id and store_id, LF separator, no trailing LF. Alphanumeric/underscore codes cannot contain separators. SQL runtime and independent Python hashes both match the frozen value.',
        training_start={'day':'d_1','date':FIRST_DATE.isoformat()},maximum_training_day=1913,
        selected_training_rows_compared=row_counts['selected_training_projection'],selected_training_columns_compared=6,
        selected_training_field_mismatches=0,metadata_and_calendar_source_projection_mismatches=0,
        final_holdout_unit_values_inspected=False,forecasts_computed=False,forecast_errors_computed=False,
        calendar_coverage_is_target_observation_coverage=False,
        schema_scope='Full product/store column names and types; required raw metadata, four calendar and six daily field names/types. Unused calendar, event, price/value fields are not re-audited.',
        independent_reference='Python csv reads original metadata and calendar, independently selects and hashes membership, validates canonical dates, parses selected training integers, and compares every one of 413208 six-field daily records through private streamed CSV exports. No holdout unit value is accessed or converted. Expected four report rows are derived independently from source calendar mappings and the complete series/day roster.',
        timings=timings,timing_scope='Named Python CSV reference and DuckDB process/export timings; remaining Python comparisons and hashing excluded.',
        result_rows=len(actual),result_columns=len(COLUMNS),rows_with_pass_status=4,output_columns=COLUMNS,
        result_field_mismatches=0,origin_order_verified=True,results=actual,ordered_result_sha256=json_hash(actual),
        input_projection_row_counts=row_counts,input_projection_sha256_before=before_hashes,input_projection_sha256_after=after_hashes,
        scoped_input_projections_unchanged=True,
        input_fingerprint_method='SHA256 of deterministic UTF-8 DuckDB CSV exports with header and fixed column/row order. Row-level files remain private and are deleted with the temporary directory.',
        fixture_cases_passed=len(cases),fixture_cases=cases,
        real_product_identifiers_published=False,individual_series_rows_published=False,daily_or_target_vectors_published=False,
        scope='Assistant preflight only; learner SQL33 execution pending. Public output contains four scope/time aggregates, frozen scope labels and fingerprints, with no product membership list, daily records, target-unit values or forecasts. Every training window starts at d1 and retains zero observations. The forecast windows contain 28 calendar dates each; this does not audit target sales-record coverage. Earlier engineering reconciliation observed full-snapshot totals; this step does not claim wholly unseen holdout data or use ABC/XYZ/price features.')
    serialized = json.dumps(report, indent=2, ensure_ascii=False)+'\n'
    assert all(item not in serialized for item,_,_ in products), 'Real product identifier in public report'
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(serialized, encoding='utf-8', newline='\n')
    print(json.dumps({'fixture_cases_passed':len(cases),'frozen_scope':report['frozen_scope'],
                      'selected_training_rows_compared':row_counts['selected_training_projection'],'results':actual,
                      'ordered_result_sha256':report['ordered_result_sha256'],'timings':timings}), flush=True)


if __name__ == '__main__':
    main()
