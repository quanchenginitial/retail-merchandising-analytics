"""Verify descriptive 12-week variability against original wide sales in private databases."""
import argparse
import hashlib
import json
import statistics
import subprocess
import tempfile
import time
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP, localcontext
from pathlib import Path


START = date(2016, 1, 30)
FLOAT_FIELDS = ['mean_weekly_units', 'stddev_weekly_units', 'cv_weekly',
                'zero_week_share', 'mean_positive_gap_weeks']
ABS_TOL = Decimal('1e-9')
REL_TOL = Decimal('1e-9')
WEEKLY_SNAPSHOT = 'SELECT * FROM mart.m5_product_weekly_12w ORDER BY item_id,wm_yr_wk;'
METRIC_SNAPSHOT = 'SELECT * FROM mart.m5_product_variability_12w ORDER BY item_id;'


def sha256(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def parse(output):
    return json.loads(output, parse_float=Decimal)


def quote(value):
    return "'" + str(value).replace("'", "''") + "'"


def fingerprint(rows):
    value = json.dumps(rows, sort_keys=True, separators=(',', ':'), default=str)
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def assert_exact_rows(actual, expected, context):
    assert len(actual) == len(expected), (context, len(actual), len(expected))
    for observed, reference in zip(actual, expected):
        assert set(observed) == set(reference), (context, observed, reference)
        for key, value in reference.items():
            actual_value = observed[key]
            if isinstance(value, (Decimal, int)) and actual_value is not None:
                actual_value = Decimal(str(actual_value))
            assert actual_value == value, (context, key, observed, reference)


def reference_metrics(source):
    """Use centered population variance at 70 decimal digits and explicit positive-week gaps."""
    expected = []
    max_pstdev_error = Decimal(0)
    with localcontext() as ctx:
        ctx.prec = 70
        for row in sorted(source, key=lambda x: x['item_id']):
            vector = [int(value) for value in row['weeks']]
            assert len(vector) == 12 and all(value >= 0 for value in vector)
            total = sum(vector)
            mean = Decimal(total) / 12
            variance = sum((Decimal(value) - mean) ** 2 for value in vector) / 12
            sd = variance.sqrt()
            pstdev_error = abs(Decimal(str(statistics.pstdev(vector))) - sd)
            assert pstdev_error <= ABS_TOL + REL_TOL * abs(sd)
            max_pstdev_error = max(max_pstdev_error, pstdev_error)
            positive_positions = [index for index, value in enumerate(vector, 1) if value > 0]
            gaps = [right - left for left, right in zip(positive_positions, positive_positions[1:])]
            zero_weeks = sum(value == 0 for value in vector)
            expected.append(dict(
                item_id=row['item_id'], dept_id=row['dept_id'], cat_id=row['cat_id'],
                window_start='2016-01-30', window_end='2016-04-22', week_count=12, units=total,
                mean_weekly_units=mean, stddev_weekly_units=sd, cv_weekly=None if total == 0 else sd / mean,
                zero_sales_weeks=zero_weeks, zero_week_share=Decimal(zero_weeks) / 12,
                positive_weeks=len(positive_positions),
                mean_positive_gap_weeks=None if not gaps else Decimal(sum(gaps)) / len(gaps)))
    return expected, max_pstdev_error


def assert_metrics(actual, expected, context):
    assert len(actual) == len(expected), (context, len(actual), len(expected))
    errors = {field: dict(nonnull_values_compared=0, null_values_compared=0,
                          max_absolute_error=Decimal(0), max_error_to_tolerance_ratio=Decimal(0),
                          max_allowed_tolerance=Decimal(0)) for field in FLOAT_FIELDS}
    for observed, reference in zip(actual, expected):
        assert set(observed) == set(reference), (context, observed, reference)
        for key, value in reference.items():
            actual_value = observed[key]
            if key not in FLOAT_FIELDS:
                if isinstance(value, int) and actual_value is not None:
                    actual_value = Decimal(str(actual_value))
                assert actual_value == value, (context, key, observed, reference)
                continue
            if value is None:
                assert actual_value is None, (context, key, observed, reference)
                errors[key]['null_values_compared'] += 1
                continue
            assert actual_value is not None, (context, key, observed, reference)
            actual_value = Decimal(str(actual_value))
            assert actual_value.is_finite() and value.is_finite(), (context, key, observed, reference)
            difference = abs(actual_value - value)
            tolerance = ABS_TOL + REL_TOL * abs(value)
            assert difference <= tolerance, (context, key, str(difference), str(tolerance), observed, reference)
            stats = errors[key]
            stats['nonnull_values_compared'] += 1
            stats['max_absolute_error'] = max(stats['max_absolute_error'], difference)
            stats['max_error_to_tolerance_ratio'] = max(stats['max_error_to_tolerance_ratio'], difference / tolerance)
            stats['max_allowed_tolerance'] = max(stats['max_allowed_tolerance'], tolerance)
    return errors


def quantile_type7(values, probability):
    if not values:
        return None
    ordered = sorted(values)
    with localcontext() as ctx:
        ctx.prec = 70
        position = Decimal(probability) * (len(ordered) - 1)
        lower = int(position)
        fraction = position - lower
        value = ordered[lower] if fraction == 0 else ordered[lower] + fraction * (ordered[lower + 1] - ordered[lower])
        return value.quantize(Decimal('0.000001'), rounding=ROUND_HALF_UP)


def reference_report(metrics):
    report = []
    for group in ['POSITIVE_12W', 'ZERO_12W', 'TOTAL']:
        members = metrics if group == 'TOTAL' else [row for row in metrics if (row['units'] > 0) == (group == 'POSITIVE_12W')]
        values = [row['cv_weekly'] for row in members if row['cv_weekly'] is not None]
        report.append(dict(sales_group=group, sku_count=len(members), units=sum(row['units'] for row in members),
                           zero_sales_product_weeks=sum(row['zero_sales_weeks'] for row in members),
                           median_cv=quantile_type7(values, '0.5'), p90_cv=quantile_type7(values, '0.9'),
                           max_cv=None if not values else max(values).quantize(Decimal('0.000001'), rounding=ROUND_HALF_UP),
                           check_status='PASS'))
    return report


def source_weekly_rows(source, stores):
    rows = []
    for product in sorted(source, key=lambda x: x['item_id']):
        for index, units in enumerate(product['weeks']):
            start = START + timedelta(days=index * 7)
            rows.append(dict(item_id=product['item_id'], dept_id=product['dept_id'], cat_id=product['cat_id'],
                             wm_yr_wk=11601 + index, week_start=start.isoformat(),
                             week_end=(start + timedelta(days=6)).isoformat(), units=int(units), source_daily_rows=stores * 7))
    return rows


def source_weekly_report(rows):
    result = []
    for week in list(range(11601, 11613)) + [None]:
        members = rows if week is None else [row for row in rows if row['wm_yr_wk'] == week]
        result.append(dict(retail_week='TOTAL' if week is None else str(week),
                           week_start=min(row['week_start'] for row in members),
                           week_end=max(row['week_end'] for row in members), product_week_rows=len(members),
                           source_daily_rows=sum(row['source_daily_rows'] for row in members),
                           units=sum(row['units'] for row in members),
                           zero_sales_product_weeks=sum(row['units'] == 0 for row in members), check_status='PASS'))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--duckdb', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--fixtures-only', action='store_true')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    tmp_root = root / 'tmp'
    tmp_root.mkdir(exist_ok=True)
    sql_path = root / 'sql/24_build_product_variability.sql'
    sql_bytes = sql_path.read_bytes()
    build, audit = sql_bytes.decode('utf-8').split('-- VALIDATION:', 1)
    audit = '-- VALIDATION:' + audit
    weekly_path = root / 'sql/23_build_product_weekly.sql'
    weekly_bytes = weekly_path.read_bytes()
    weekly_build, weekly_audit = weekly_bytes.decode('utf-8').split('-- VALIDATION:', 1)
    weekly_audit = '-- VALIDATION:' + weekly_audit
    cases = []

    mixed_vectors = [
        [10] * 12,
        [0] * 12,
        [12] + [0] * 11,
        [7] + [0] * 10 + [7],
        [0, 7, 7] + [0] * 9,
        [1, 0, 2, 0, 3, 0, 0, 4, 0, 0, 0, 5],
        [1000000] * 11 + [1000001],
        list(range(1, 13)),
    ]

    def fixture(vectors):
        source = [dict(item_id=f'P{index:03d}', dept_id='FOODS_1', cat_id='FOODS', weeks=vector)
                  for index, vector in enumerate(vectors, 1)]
        products = ','.join(f"({quote(row['item_id'])},'FOODS_1','FOODS')" for row in source)
        values = []
        for row in source_weekly_rows(source, 2):
            values.append('(' + ','.join(str(value) if isinstance(value, int) else quote(value)
                                        for value in row.values()) + ')')
        setup = f"""
CREATE SCHEMA core; CREATE SCHEMA mart;
CREATE TABLE core.m5_product(item_id VARCHAR,dept_id VARCHAR,cat_id VARCHAR);
INSERT INTO core.m5_product VALUES {products};
CREATE TABLE mart.m5_product_weekly_12w(item_id VARCHAR,dept_id VARCHAR,cat_id VARCHAR,wm_yr_wk INTEGER,
week_start DATE,week_end DATE,units HUGEINT,source_daily_rows BIGINT);
INSERT INTO mart.m5_product_weekly_12w VALUES {','.join(values)};
"""
        return source, setup

    def tiny(name, vectors=None, before='', after='', error=None):
        vectors = mixed_vectors if vectors is None else vectors
        source, setup = fixture(vectors)
        replacement = ('3049 AS expected_items,10 AS expected_stores',
                       f'{len(vectors)} AS expected_items,2 AS expected_stores')
        fixture_build = build.replace(*replacement)
        fixture_audit = audit.replace(*replacement)
        with tempfile.TemporaryDirectory(prefix='variability-fixture-', dir=tmp_root) as folder:
            assert Path(folder).resolve().is_relative_to(tmp_root.resolve())
            database = Path(folder) / 'fixture.duckdb'

            def execute(script):
                return subprocess.run([args.duckdb, str(database), '-bail', '-json'], input=script,
                                      text=True, encoding='utf-8', capture_output=True)

            run = execute(setup + before)
            assert run.returncode == 0, (name, run.stderr)
            previous = execute(WEEKLY_SNAPSHOT)
            assert previous.returncode == 0, previous.stderr
            weekly_before = parse(previous.stdout)
            run = execute(fixture_build + '\n' + after + '\n' + fixture_audit)
            if error:
                assert run.returncode != 0 and error in run.stderr, (name, run.stderr)
                if error == 'Variability build blocked':
                    absent = execute("SELECT COUNT(*) AS table_count FROM information_schema.tables WHERE table_schema='mart' AND table_name='m5_product_variability_12w';")
                    assert absent.returncode == 0 and parse(absent.stdout) == [{'table_count': 0}], (name, absent.stdout)
            else:
                assert run.returncode == 0, (name, run.stderr)
                expected, _ = reference_metrics(source)
                assert_exact_rows(parse(run.stdout), reference_report(expected), name + ' six-decimal report')
                current = execute(METRIC_SNAPSHOT)
                assert current.returncode == 0, current.stderr
                assert_metrics(parse(current.stdout), expected, name + ' fourteen stored fields')
                if vectors is mixed_vectors:
                    controls = {row['item_id']: row for row in expected}
                    assert controls['P001']['stddev_weekly_units'] == 0 and controls['P001']['cv_weekly'] == 0
                    assert controls['P002']['cv_weekly'] is None and controls['P002']['mean_positive_gap_weeks'] is None
                    assert abs(controls['P003']['cv_weekly'] - Decimal(11).sqrt()) < Decimal('1e-25')
                    assert controls['P003']['mean_positive_gap_weeks'] is None
                    assert controls['P004']['mean_positive_gap_weeks'] == 11
                    assert controls['P005']['mean_positive_gap_weeks'] == 1
                    assert controls['P006']['mean_positive_gap_weeks'] == Decimal('2.75')
                    assert 0 < controls['P007']['stddev_weekly_units'] < 1
            unchanged = execute(WEEKLY_SNAPSHOT)
            assert unchanged.returncode == 0 and parse(unchanged.stdout) == weekly_before, (name, 'weekly input changed')
        assert not Path(folder).exists()
        cases.append(dict(case=name, passed=True, guard_rejected=error is not None, weekly_input_unchanged=True,
                          failed_build_left_no_target_table=True if error == 'Variability build blocked' else None))

    tiny('mixed_exact_controls_population_sd_gaps_and_near_constant')
    tiny('all_zero_products_empty_positive_report', vectors=[[0] * 12] * 3)
    tiny('no_zero_products_empty_zero_report', vectors=[[5] * 12, list(range(1, 13))])
    for name, before in [
        ('empty_weekly_source', 'DELETE FROM mart.m5_product_weekly_12w;'),
        ('missing_source_week', "DELETE FROM mart.m5_product_weekly_12w WHERE item_id='P001' AND wm_yr_wk=11601;"),
        ('duplicate_and_missing_source_week', "UPDATE mart.m5_product_weekly_12w SET wm_yr_wk=11602,week_start=DATE '2016-02-06',week_end=DATE '2016-02-12' WHERE item_id='P001' AND wm_yr_wk=11601;"),
        ('wrong_source_week_date', "UPDATE mart.m5_product_weekly_12w SET week_start=week_start+1 WHERE item_id='P001' AND wm_yr_wk=11601;"),
        ('wrong_source_daily_count', "UPDATE mart.m5_product_weekly_12w SET source_daily_rows=13 WHERE item_id='P001' AND wm_yr_wk=11601;"),
        ('negative_source_units', "UPDATE mart.m5_product_weekly_12w SET units=-1 WHERE item_id='P001' AND wm_yr_wk=11601;"),
        ('null_source_units', "UPDATE mart.m5_product_weekly_12w SET units=NULL WHERE item_id='P001' AND wm_yr_wk=11601;"),
        ('duplicate_product_mapping', "INSERT INTO core.m5_product SELECT * FROM core.m5_product WHERE item_id='P001';"),
        ('wrong_source_units_type', 'ALTER TABLE mart.m5_product_weekly_12w ALTER units TYPE DOUBLE;'),
    ]:
        tiny(name, before=before, error='Variability build blocked')
    for name, after in [
        ('missing_metric_product', "DELETE FROM mart.m5_product_variability_12w WHERE item_id='P002';"),
        ('duplicate_metric_product', "INSERT INTO mart.m5_product_variability_12w SELECT * FROM mart.m5_product_variability_12w WHERE item_id='P001';"),
        ('positive_cv_cannot_be_null', "UPDATE mart.m5_product_variability_12w SET cv_weekly=NULL WHERE item_id='P003';"),
        ('nan_standard_deviation', "UPDATE mart.m5_product_variability_12w SET stddev_weekly_units='NaN'::DOUBLE WHERE item_id='P001';"),
        ('infinite_mean', "UPDATE mart.m5_product_variability_12w SET mean_weekly_units='Infinity'::DOUBLE WHERE item_id='P001';"),
        ('zero_sales_cv_must_remain_null', "UPDATE mart.m5_product_variability_12w SET cv_weekly=0 WHERE item_id='P002';"),
        ('wrong_positive_gap_inside_valid_range', "UPDATE mart.m5_product_variability_12w SET mean_positive_gap_weeks=1 WHERE item_id='P004';"),
        ('offsetting_zero_and_positive_counts', "UPDATE mart.m5_product_variability_12w SET zero_sales_weeks=zero_sales_weeks+1,positive_weeks=positive_weeks-1 WHERE item_id='P006';"),
        ('same_total_units_redistributed_between_products', "UPDATE mart.m5_product_variability_12w SET units=units+CASE item_id WHEN 'P001' THEN 1 ELSE -1 END WHERE item_id IN ('P001','P008');"),
        ('wrong_target_float_schema', 'ALTER TABLE mart.m5_product_variability_12w ALTER mean_weekly_units TYPE DECIMAL(38,12);'),
    ]:
        tiny(name, after=after, error='Variability validation blocked')
    assert len(cases) == 22
    print(json.dumps({'fixture_cases_passed': len(cases)}), flush=True)
    if args.fixtures_only:
        return

    source_root = Path('D:/database/m5-forecasting-accuracy')
    sources = [source_root / name for name in ['sales_train_evaluation.csv', 'calendar.csv']]
    registry = json.loads((root / 'data/m5_source_audit.json').read_text(encoding='utf-8'))
    hashes = {path.name: sha256(path) for path in sources}
    assert all(hashes[path.name] == registry['files'][path.name]['sha256'] for path in sources)
    day_columns = ','.join(f'd_{day}' for day in range(1828, 1912))
    setup = f"""
CREATE SCHEMA raw; CREATE SCHEMA core; CREATE SCHEMA mart;
CREATE TABLE core.m5_calendar AS
SELECT d,CAST(date AS DATE) AS date,CAST(wm_yr_wk AS INTEGER) AS wm_yr_wk
FROM read_csv({quote(sources[1].as_posix())},header=true,all_varchar=true);
CREATE TABLE raw.sales_window_wide AS
SELECT id,item_id,dept_id,cat_id,store_id,state_id,{day_columns}
FROM read_csv({quote(sources[0].as_posix())},header=true,all_varchar=true);
CREATE TABLE core.m5_product AS SELECT DISTINCT item_id,dept_id,cat_id FROM raw.sales_window_wide;
CREATE TABLE core.m5_store AS SELECT DISTINCT store_id FROM raw.sales_window_wide;
CREATE TABLE mart.m5_sales_daily AS
WITH unpivoted AS (UNPIVOT raw.sales_window_wide ON {day_columns} INTO NAME d VALUE units_text)
SELECT u.item_id,u.store_id,u.d,c.date,c.wm_yr_wk,
CASE WHEN regexp_full_match(u.units_text,'[0-9]+') AND TRY_CAST(u.units_text AS INTEGER) IS NOT NULL
     THEN CAST(u.units_text AS INTEGER) ELSE error('Window source requires nonnegative INTEGER sales') END AS units
FROM unpivoted u JOIN core.m5_calendar c ON u.d=c.d;
"""
    controls_sql = """
SELECT (SELECT COUNT(*) FROM raw.sales_window_wide) AS source_series,
       (SELECT COUNT(*) FROM core.m5_product) AS source_products,
       (SELECT COUNT(*) FROM core.m5_store) AS source_stores,
       (SELECT COUNT(*) FROM core.m5_calendar) AS calendar_rows,
       (SELECT COUNT(DISTINCT d) FROM core.m5_calendar) AS calendar_day_keys,
       (SELECT COUNT(DISTINCT date) FROM core.m5_calendar) AS calendar_dates,
       (SELECT COUNT(DISTINCT wm_yr_wk) FROM core.m5_calendar) AS calendar_weeks,
       (SELECT COUNT(*) FROM core.m5_calendar WHERE d IS DISTINCT FROM 'd_'||CAST(date_diff('day',DATE '2011-01-29',date)+1 AS VARCHAR)) AS calendar_mapping_errors,
       (SELECT COUNT(*) FROM mart.m5_sales_daily) AS private_84d_daily_rows;
"""
    vector_expressions = []
    for index in range(12):
        columns = ','.join(f'd_{day}' for day in range(1828 + index * 7, 1835 + index * 7))
        vector_expressions.append(f"SUM(list_sum(list_transform(list_value({columns}),lambda x: CASE WHEN regexp_full_match(x,'[0-9]+') AND TRY_CAST(x AS INTEGER) IS NOT NULL THEN CAST(x AS BIGINT) ELSE error('Wide reference requires nonnegative INTEGER sales') END))) AS week_{index + 1:02d}")
    vector_sql = 'SELECT item_id,dept_id,cat_id,' + ','.join(vector_expressions) + '\nFROM raw.sales_window_wide GROUP BY item_id,dept_id,cat_id ORDER BY item_id;'
    accepted_path = root / 'data/product_weekly_learner_acceptance.json'
    accepted_bytes = accepted_path.read_bytes()
    accepted = json.loads(accepted_bytes.decode('utf-8'))
    assert accepted['rows_with_pass_status'] == 13
    assert accepted['weekly_window']['start_date'] == '2016-01-30'
    assert accepted['weekly_window']['end_date'] == '2016-04-22'
    with tempfile.TemporaryDirectory(prefix='product-variability-', dir=tmp_root) as folder:
        assert Path(folder).resolve().is_relative_to(tmp_root.resolve())
        database = Path(folder) / 'preflight.duckdb'
        assert database.resolve().is_relative_to(Path(folder).resolve())
        spill = (Path(folder) / 'spill').as_posix().replace("'", "''")
        settings = f"SET threads=2; SET memory_limit='2GB'; SET temp_directory='{spill}';\n"

        def execute(script):
            started = time.perf_counter()
            run = subprocess.run([args.duckdb, str(database), '-bail', '-json'], input=settings + script,
                                 text=True, encoding='utf-8', capture_output=True)
            assert run.returncode == 0, run.stderr
            return run, round(time.perf_counter() - started, 3)

        _, setup_seconds = execute(setup)
        run, _ = execute(controls_sql)
        controls = parse(run.stdout)[0]
        assert controls == dict(source_series=30490, source_products=3049, source_stores=10,
                                calendar_rows=1969, calendar_day_keys=1969, calendar_dates=1969,
                                calendar_weeks=282, calendar_mapping_errors=0, private_84d_daily_rows=2561160), controls
        print(json.dumps({'window_setup_seconds': setup_seconds, 'source_controls': controls}), flush=True)
        _, weekly_build_seconds = execute(weekly_build)
        run, weekly_validation_seconds = execute(weekly_audit)
        weekly_results = parse(run.stdout)
        normalized_accepted = [{key: int(value) if key in ('product_week_rows', 'source_daily_rows', 'units', 'zero_sales_product_weeks')
                                else value for key, value in row.items()} for row in accepted['results']]
        assert_exact_rows(weekly_results, normalized_accepted, 'accepted weekly summary')
        run, vector_seconds = execute(vector_sql)
        vectors = parse(run.stdout)
        assert len(vectors) == 3049 and len({row['item_id'] for row in vectors}) == 3049
        source = [dict(item_id=row['item_id'], dept_id=row['dept_id'], cat_id=row['cat_id'],
                       weeks=[int(row[f'week_{index:02d}']) for index in range(1, 13)]) for row in vectors]
        expected_weekly = source_weekly_rows(source, 10)
        run, _ = execute(WEEKLY_SNAPSHOT)
        weekly_before = parse(run.stdout)
        assert_exact_rows(weekly_before, expected_weekly, 'weekly input versus original wide columns')
        assert_exact_rows(weekly_results, source_weekly_report(expected_weekly), 'weekly source summary')
        weekly_before_hash = fingerprint(weekly_before)
        expected_metrics, pstdev_error = reference_metrics(source)
        expected_report = reference_report(expected_metrics)
        _, build_seconds = execute(build)
        run, validation_seconds = execute(audit)
        results = parse(run.stdout)
        assert_exact_rows(results, expected_report, 'three six-decimal report rows')
        run, snapshot_seconds = execute(METRIC_SNAPSHOT)
        actual_metrics = parse(run.stdout)
        float_errors = assert_metrics(actual_metrics, expected_metrics, 'all fourteen stored fields')
        run, _ = execute(WEEKLY_SNAPSHOT)
        weekly_after = parse(run.stdout)
        assert weekly_before == weekly_after and weekly_before_hash == fingerprint(weekly_after), 'Weekly source changed'
        database_bytes = database.stat().st_size
    assert not Path(folder).exists()
    assert all(sha256(path) == hashes[path.name] for path in sources)
    positive_counts = Counter(row['positive_weeks'] for row in expected_metrics)
    zero_counts = Counter(row['zero_sales_weeks'] for row in expected_metrics)
    report = dict(
        checked_at_utc=datetime.now(timezone.utc).isoformat(), executor='assistant',
        engine=subprocess.check_output([args.duckdb, '-version'], text=True).strip(),
        baseline_database='Private temporary on-disk DuckDB under repository tmp; removed after verification.',
        temporary_baseline_removed=True, temporary_database_bytes_after_close=database_bytes,
        settings={'threads': 2, 'memory_limit': '2GB'},
        script='sql/24_build_product_variability.sql', script_sha256=hashlib.sha256(sql_bytes).hexdigest(),
        weekly_script='sql/23_build_product_weekly.sql', weekly_script_sha256=hashlib.sha256(weekly_bytes).hexdigest(),
        preflight_strategy='Read only sales/calendar CSVs. Project six source identifiers and d_1828..d_1911 into a private raw table; construct a six-column 84-day daily table and small dimensions. Execute actual SQL23 build/validation followed by SQL24. This is a window-only fixture, not a full SQL17 rebuild. No ABC table is needed, opened or built.',
        independent_reference='Aggregate each of the twelve original seven-column wide sales arrays directly per SKU, without reading the daily or weekly fact. Compute centered population variance and square root at 70 Decimal digits; cross-check Python statistics.pstdev. Positive gaps are explicit adjacent positive-week differences. CV quantiles use Type7 linear interpolation on unrounded values, then ROUND_HALF_UP to six display decimals.',
        source_sha256=hashes, source_hashes_unchanged=True,
        source_scope='Sales and calendar only; prices are irrelevant and were neither read nor hashed.',
        analysis_window={'start_date': '2016-01-30', 'end_date': '2016-04-22', 'inclusive_days': 84,
                         'week_count': 12, 'scope': 'Each product pooled across all 10 stores; zero-sales weeks retained.'},
        source_controls=controls, window_setup_seconds=setup_seconds, weekly_build_seconds=weekly_build_seconds,
        weekly_validation_seconds=weekly_validation_seconds, independent_wide_vector_query_seconds=vector_seconds,
        variability_build_seconds=build_seconds, variability_validation_seconds=validation_seconds,
        variability_snapshot_query_seconds=snapshot_seconds,
        timing_scope='DuckDB CLI process timings only; excludes Python references/comparisons and source-file hashing.',
        weekly_input_rows_compared=36588, weekly_input_columns_compared=8, weekly_input_mismatches=0,
        accepted_weekly_evidence='data/product_weekly_learner_acceptance.json',
        accepted_weekly_evidence_sha256=hashlib.sha256(accepted_bytes).hexdigest(), accepted_weekly_summary_matched=True,
        weekly_input_unchanged=True, weekly_rows_sha256_before=weekly_before_hash, weekly_rows_sha256_after=fingerprint(weekly_after),
        sku_rows_compared=3049, columns_compared=14, exact_columns=9, floating_columns=5,
        exact_field_mismatches=0, floating_field_mismatches=0, null_field_mismatches=0,
        numeric_tolerance={'absolute': '1e-9', 'relative': '1e-9',
                           'rule': 'abs(actual-reference) <= 1e-9 + 1e-9*abs(reference); NULL patterns exact and all compared non-NULL floats finite.'},
        float_error_summary=float_errors, reference_pstdev_max_absolute_difference=pstdev_error,
        positive_weeks_distribution=[dict(positive_weeks=count, sku_count=positive_counts[count]) for count in range(13)],
        zero_sales_weeks_distribution=[dict(zero_sales_weeks=count, sku_count=zero_counts[count]) for count in range(13)],
        undefined_cv_skus=sum(row['cv_weekly'] is None for row in expected_metrics),
        undefined_positive_gap_skus=sum(row['mean_positive_gap_weeks'] is None for row in expected_metrics),
        result_rows=3, results=results, fixture_cases_passed=len(cases), fixture_cases=cases,
        scope='Assistant preflight only; learner variability-table execution pending. Population SD describes the observed twelve weeks. CV is undefined for all-zero products; mean positive gap is undefined below two positive weeks and excludes edge censoring. Report quantiles describe per-SKU CVs, not variability of pooled aggregate demand. No XYZ labels, availability inference, forecast or SKU-level extract is published; no learner database is opened.')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, default=str) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps({'fixture_cases_passed': len(cases), 'sku_rows_compared': 3049, 'columns_compared': 14,
                      'weekly_input_unchanged': True, 'variability_build_seconds': build_seconds,
                      'variability_validation_seconds': validation_seconds, 'float_error_summary': float_errors,
                      'undefined_positive_gap_skus': report['undefined_positive_gap_skus'], 'results': results}, default=str), flush=True)


if __name__ == '__main__':
    main()
