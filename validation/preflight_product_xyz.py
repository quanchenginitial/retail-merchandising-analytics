"""Verify XYZ labels and metric snapshots in isolated databases; never open the learner database."""
import argparse
import hashlib
import json
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from preflight_product_variability import (
    assert_exact_rows, assert_metrics, fingerprint, parse, quote, reference_metrics,
    reference_report, sha256, source_weekly_rows, source_weekly_report, quantile_type7,
    WEEKLY_SNAPSHOT, METRIC_SNAPSHOT,
)

XYZ_SNAPSHOT = 'SELECT * FROM mart.m5_product_xyz_12w ORDER BY item_id;'


def classify(vector):
    """Exact integer reference, independently cross-checked against 70-digit centered SD."""
    total = sum(vector)
    if total == 0:
        return 'ZERO_SALES'
    numerator = len(vector) * sum(x * x for x in vector) - total * total
    return 'X' if 4 * numerator <= total * total else 'Y' if numerator <= total * total else 'Z'


def xyz_reference(source):
    metrics, _ = reference_metrics(source)
    vectors = {row['item_id']: row['weeks'] for row in source}
    for row in metrics:
        row['xyz_class'] = classify(vectors[row['item_id']])
        cv = row['cv_weekly']
        decimal_class = 'ZERO_SALES' if cv is None else 'X' if cv <= Decimal('.5') else 'Y' if cv <= 1 else 'Z'
        assert row['xyz_class'] == decimal_class, (row['item_id'], cv)
    return metrics


def xyz_report(rows):
    total_units = sum(row['units'] for row in rows)
    result = []
    for label in ['X', 'Y', 'Z', 'ZERO_SALES', 'TOTAL']:
        members = rows if label == 'TOTAL' else [r for r in rows if r['xyz_class'] == label]
        units = sum(row['units'] for row in members)
        result.append(dict(
            xyz_class=label, sku_count=len(members),
            sku_share_pct=(Decimal(100) * len(members) / len(rows)).quantize(Decimal('.0001'), rounding=ROUND_HALF_UP),
            units=units,
            unit_share_pct=None if total_units == 0 else (Decimal(100) * units / total_units).quantize(Decimal('.0001'), rounding=ROUND_HALF_UP),
            zero_sales_product_weeks=sum(row['zero_sales_weeks'] for row in members),
            median_cv=quantile_type7([row['cv_weekly'] for row in members if row['cv_weekly'] is not None], '.5'),
            check_status='PASS'))
    return result


def assert_xyz(actual, expected, metric_snapshot):
    assert [r['xyz_class'] for r in actual] == [r['xyz_class'] for r in expected]
    actual_metrics = [{k: v for k, v in row.items() if k != 'xyz_class'} for row in actual]
    expected_metrics = [{k: v for k, v in row.items() if k != 'xyz_class'} for row in expected]
    errors = assert_metrics(actual_metrics, expected_metrics, 'XYZ full source-reference fields')
    assert actual_metrics == metric_snapshot, 'XYZ failed to preserve source metric snapshot exactly'
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--duckdb', required=True)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--fixtures-only', action='store_true')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    tmp_root = root / 'tmp'
    tmp_root.mkdir(exist_ok=True)
    scripts = {}
    for name in ['23_build_product_weekly', '24_build_product_variability', '25_build_product_xyz']:
        value = (root / 'sql' / (name + '.sql')).read_text(encoding='utf-8')
        build, audit = value.split('-- VALIDATION:', 1)
        scripts[name[:2]] = (build, '-- VALIDATION:' + audit)
    build, audit = scripts['25']
    mixed = [
        [10] * 12, [0] * 12, [12] + [0] * 11,
        [1] * 6 + [3] * 6,
        [1000000] * 6 + [3000001] * 6,
        [1000000] * 6 + [2999999] * 6,
        [0] * 6 + [2] * 6,
        [0] * 6 + [2000000] * 5 + [2000001],
        [1] + [0] * 5 + [2000000] * 6,
    ]
    cases = []

    def tiny(name, vectors=None, before='', after='', reject=False, metric_perturbation=''):
        vectors = mixed if vectors is None else vectors
        source = [dict(item_id=f'P{i:03d}', dept_id='FOODS_1', cat_id='FOODS', weeks=v)
                  for i, v in enumerate(vectors, 1)]
        products = ','.join(f"({quote(r['item_id'])},'FOODS_1','FOODS')" for r in source)
        values = ','.join('(' + ','.join(str(v) if isinstance(v, int) else quote(v) for v in row.values()) + ')'
                          for row in source_weekly_rows(source, 2))
        setup = f"""CREATE SCHEMA core; CREATE SCHEMA mart;
CREATE TABLE core.m5_product(item_id VARCHAR,dept_id VARCHAR,cat_id VARCHAR);
INSERT INTO core.m5_product VALUES {products};
CREATE TABLE mart.m5_product_weekly_12w(item_id VARCHAR,dept_id VARCHAR,cat_id VARCHAR,wm_yr_wk INTEGER,
week_start DATE,week_end DATE,units HUGEINT,source_daily_rows BIGINT);
INSERT INTO mart.m5_product_weekly_12w VALUES {values};
"""
        old = '3049 AS expected_items,10 AS expected_stores'
        new = f'{len(vectors)} AS expected_items,2 AS expected_stores'
        with tempfile.TemporaryDirectory(prefix='xyz-fixture-', dir=tmp_root) as folder:
            assert Path(folder).resolve().is_relative_to(tmp_root.resolve())
            database = Path(folder) / 'test.duckdb'
            settings = "SET threads=2; SET memory_limit='2GB';\n"

            def execute(sql):
                return subprocess.run([args.duckdb, str(database), '-bail', '-json'], input=settings + sql,
                                      text=True, encoding='utf-8', capture_output=True)

            run = execute(setup + scripts['24'][0].replace(old, new) + metric_perturbation + before)
            assert run.returncode == 0, (name, run.stderr)
            w = execute(WEEKLY_SNAPSHOT)
            m = execute(METRIC_SNAPSHOT)
            assert w.returncode == m.returncode == 0
            weekly_before, metrics_before = parse(w.stdout), parse(m.stdout)
            run = execute(build.replace(old, new) + after + audit.replace(old, new))
            if reject:
                assert run.returncode != 0, (name, 'invalid input accepted', run.stdout)
                assert 'XYZ' in run.stderr, (name, run.stderr)
                if not after:
                    r = execute("SELECT COUNT(*) AS n FROM information_schema.tables WHERE table_schema='mart' AND table_name='m5_product_xyz_12w';")
                    assert r.returncode == 0 and parse(r.stdout) == [{'n': 0}], (name, r.stdout)
            else:
                assert run.returncode == 0, (name, run.stderr)
                expected = xyz_reference(source)
                assert_exact_rows(parse(run.stdout), xyz_report(expected), name + ' report')
                r = execute(XYZ_SNAPSHOT)
                assert r.returncode == 0
                assert_xyz(parse(r.stdout), expected, metrics_before)
                if vectors is mixed:
                    assert [r['xyz_class'] for r in expected] == ['X', 'ZERO_SALES', 'Z', 'X', 'Y', 'X', 'Y', 'Z', 'Y']
            w, m = execute(WEEKLY_SNAPSHOT), execute(METRIC_SNAPSHOT)
            assert parse(w.stdout) == weekly_before and parse(m.stdout) == metrics_before, name + ' source changed'
        assert not Path(folder).exists()
        cases.append(dict(case=name, passed=True, rejected=reject, input_tables_unchanged=True,
                          failed_build_left_no_target=True if reject and not after else None))

    tiny('exact_and_near_thresholds_population_cv')
    tiny('all_zero_products_and_empty_xyz_groups', vectors=[[0] * 12] * 3)
    tiny('constant_positive_and_empty_y_z_zero_groups', vectors=[[5] * 12, [7] * 12])
    tiny('upper_supported_integer_daily_bound', vectors=[[14 * 2147483647] * 12])
    tiny('tolerated_cv_drift_does_not_move_exact_boundary',
         metric_perturbation="UPDATE mart.m5_product_variability_12w SET cv_weekly=cv_weekly+1e-10 WHERE item_id='P004';")
    for name, mutation in [
        ('empty_weekly_source', 'DELETE FROM mart.m5_product_weekly_12w;'),
        ('missing_week', "DELETE FROM mart.m5_product_weekly_12w WHERE item_id='P001' AND wm_yr_wk=11601;"),
        ('duplicate_week', "INSERT INTO mart.m5_product_weekly_12w SELECT * FROM mart.m5_product_weekly_12w WHERE item_id='P001' AND wm_yr_wk=11601;"),
        ('unsafe_square_input', "UPDATE mart.m5_product_weekly_12w SET units=1000000000000000000000000000000::HUGEINT WHERE item_id='P001' AND wm_yr_wk=11601;"),
        ('empty_metric_source', 'DELETE FROM mart.m5_product_variability_12w;'),
        ('duplicate_metric_source', "INSERT INTO mart.m5_product_variability_12w SELECT * FROM mart.m5_product_variability_12w WHERE item_id='P001';"),
        ('wrong_metric_cv', "UPDATE mart.m5_product_variability_12w SET cv_weekly=0.1 WHERE item_id='P004';"),
        ('nan_metric_sd', "UPDATE mart.m5_product_variability_12w SET stddev_weekly_units='NaN'::DOUBLE WHERE item_id='P001';"),
        ('zero_metric_cv_not_null', "UPDATE mart.m5_product_variability_12w SET cv_weekly=0 WHERE item_id='P002';"),
        ('wrong_metric_window', "UPDATE mart.m5_product_variability_12w SET window_end=window_end+1 WHERE item_id='P001';"),
        ('metric_wrong_schema', 'ALTER TABLE mart.m5_product_variability_12w ALTER cv_weekly TYPE DECIMAL(30,12);'),
        ('duplicate_dimension', "INSERT INTO core.m5_product SELECT * FROM core.m5_product WHERE item_id='P001';"),
    ]:
        tiny(name, before=mutation, reject=True)
    for name, mutation in [
        ('missing_target_product', "DELETE FROM mart.m5_product_xyz_12w WHERE item_id='P002';"),
        ('duplicate_target_product', "INSERT INTO mart.m5_product_xyz_12w SELECT * FROM mart.m5_product_xyz_12w WHERE item_id='P001';"),
        ('swapped_labels_preserve_class_counts', "UPDATE mart.m5_product_xyz_12w SET xyz_class=CASE item_id WHEN 'P004' THEN 'Y' ELSE 'X' END WHERE item_id IN ('P004','P007');"),
        ('zero_class_cannot_be_x', "UPDATE mart.m5_product_xyz_12w SET xyz_class='X' WHERE item_id='P002';"),
        ('copied_float_must_match_exactly', "UPDATE mart.m5_product_xyz_12w SET cv_weekly=cv_weekly+1e-10 WHERE item_id='P004';"),
        ('copied_gap_changed', "UPDATE mart.m5_product_xyz_12w SET mean_positive_gap_weeks=2 WHERE item_id='P001';"),
        ('wrong_target_schema', 'ALTER TABLE mart.m5_product_xyz_12w ALTER cv_weekly TYPE DECIMAL(30,12);'),
    ]:
        tiny(name, after=mutation, reject=True)
    print(json.dumps({'fixture_cases_passed': len(cases)}), flush=True)
    if args.fixtures_only:
        return

    source_root = Path('D:/database/m5-forecasting-accuracy')
    sources = [source_root / n for n in ['sales_train_evaluation.csv', 'calendar.csv']]
    registry = json.loads((root / 'data/m5_source_audit.json').read_text(encoding='utf-8'))
    hashes = {p.name: sha256(p) for p in sources}
    assert all(hashes[p.name] == registry['files'][p.name]['sha256'] for p in sources)
    columns = ','.join(f'd_{d}' for d in range(1828, 1912))
    setup = f"""CREATE SCHEMA raw; CREATE SCHEMA core; CREATE SCHEMA mart;
CREATE TABLE core.m5_calendar AS SELECT d,CAST(date AS DATE) AS date,CAST(wm_yr_wk AS INTEGER) AS wm_yr_wk
FROM read_csv({quote(sources[1].as_posix())},header=true,all_varchar=true);
CREATE TABLE raw.sales_window_wide AS SELECT id,item_id,dept_id,cat_id,store_id,state_id,{columns}
FROM read_csv({quote(sources[0].as_posix())},header=true,all_varchar=true);
CREATE TABLE core.m5_product AS SELECT DISTINCT item_id,dept_id,cat_id FROM raw.sales_window_wide;
CREATE TABLE core.m5_store AS SELECT DISTINCT store_id FROM raw.sales_window_wide;
CREATE TABLE mart.m5_sales_daily AS
WITH u AS (UNPIVOT raw.sales_window_wide ON {columns} INTO NAME d VALUE units_text)
SELECT u.item_id,u.store_id,u.d,c.date,c.wm_yr_wk,
CASE WHEN regexp_full_match(u.units_text,'[0-9]+') AND TRY_CAST(u.units_text AS INTEGER) IS NOT NULL
THEN CAST(u.units_text AS INTEGER) ELSE error('Source requires nonnegative INTEGER units') END AS units
FROM u JOIN core.m5_calendar c USING (d);
"""
    expressions = []
    for i in range(12):
        names = ','.join(f'd_{d}' for d in range(1828 + i * 7, 1835 + i * 7))
        expressions.append(f"SUM(list_sum(list_transform(list_value({names}),lambda x: CAST(x AS BIGINT)))) AS w{i}")
    vector_sql = 'SELECT item_id,dept_id,cat_id,' + ','.join(expressions) + ' FROM raw.sales_window_wide GROUP BY item_id,dept_id,cat_id ORDER BY item_id;'
    timings = {}
    with tempfile.TemporaryDirectory(prefix='product-xyz-', dir=tmp_root) as folder:
        assert Path(folder).resolve().is_relative_to(tmp_root.resolve())
        database = Path(folder) / 'preflight.duckdb'
        settings = f"SET threads=2; SET memory_limit='2GB'; SET temp_directory={quote((Path(folder)/'spill').as_posix())};\n"

        def execute(sql, label=None):
            started = time.perf_counter()
            run = subprocess.run([args.duckdb, str(database), '-bail', '-json'], input=settings + sql,
                                 text=True, encoding='utf-8', capture_output=True)
            assert run.returncode == 0, run.stderr
            if label:
                timings[label] = round(time.perf_counter() - started, 3)
            return parse(run.stdout) if run.stdout.strip() else None

        execute(setup, 'window_setup_seconds')
        for number in ['23', '24']:
            execute(scripts[number][0], f'sql{number}_build_seconds')
            execute(scripts[number][1], f'sql{number}_validation_seconds')
        vector_rows = execute(vector_sql, 'independent_vector_seconds')
        source = [dict(item_id=r['item_id'], dept_id=r['dept_id'], cat_id=r['cat_id'],
                       weeks=[int(r[f'w{i}']) for i in range(12)]) for r in vector_rows]
        assert len(source) == 3049 and len({r['item_id'] for r in source}) == 3049
        weekly_before, metrics_before = execute(WEEKLY_SNAPSHOT), execute(METRIC_SNAPSHOT)
        assert_exact_rows(weekly_before, source_weekly_rows(source, 10), 'weekly versus original wide vectors')
        expected = xyz_reference(source)
        bare_expected = [{k: v for k, v in r.items() if k != 'xyz_class'} for r in expected]
        assert_metrics(metrics_before, bare_expected, 'metrics versus independent centered variance')
        accepted = json.loads((root/'data/product_variability_learner_acceptance.json').read_text(encoding='utf-8'))
        assert accepted['rows_with_pass_status'] == 3
        normalized = [{k: Decimal(v) if k in ['units','zero_sales_product_weeks','median_cv','p90_cv','max_cv'] and v is not None else v
                       for k, v in row.items()} for row in accepted['results']]
        assert_exact_rows(reference_report(bare_expected), normalized, 'learner accepted metrics report')
        execute(build, 'xyz_build_seconds')
        results = execute(audit, 'xyz_validation_seconds')
        actual = execute(XYZ_SNAPSHOT)
        float_errors = assert_xyz(actual, expected, metrics_before)
        assert_exact_rows(results, xyz_report(expected), 'XYZ independent report')
        weekly_after, metrics_after = execute(WEEKLY_SNAPSHOT), execute(METRIC_SNAPSHOT)
        assert weekly_before == weekly_after and metrics_before == metrics_after
        database_bytes = database.stat().st_size
    assert not Path(folder).exists()
    assert all(sha256(p) == hashes[p.name] for p in sources)
    report = dict(
        checked_at_utc=datetime.now(timezone.utc).isoformat(), executor='assistant',
        engine=subprocess.check_output([args.duckdb, '-version'], text=True).strip(),
        script='sql/25_build_product_xyz.sql', script_sha256=sha256(root/'sql/25_build_product_xyz.sql'),
        dependencies_sha256={str(p.relative_to(root)).replace('\\','/'): sha256(p) for p in [
            root/'sql/23_build_product_weekly.sql',root/'sql/24_build_product_variability.sql',
            root/'validation/preflight_product_variability.py',root/'data/product_variability_learner_acceptance.json']},
        temporary_baseline_removed=True, temporary_database_bytes_after_close=database_bytes,
        settings={'threads':2,'memory_limit':'2GB'}, source_sha256=hashes, source_hashes_unchanged=True,
        preflight_strategy='Read only sales/calendar. Build private 84-day daily fixture, then actual SQL23, SQL24 and SQL25. Original seven-column wide sums provide independent twelve-week vectors. No learner database or ABC table is opened; no full SQL17 rebuild.',
        independent_reference='All 3049 labels checked with Python arbitrary-precision integer moments and independently with centered 70-digit Decimal population variance/sqrt. All 14 metric fields checked against these source vectors, and copied snapshot fields checked exactly.',
        threshold_rule={'X':'positive total and population CV <= 0.5','Y':'0.5 < population CV <= 1','Z':'population CV > 1','ZERO_SALES':'zero total, CV NULL'},
        threshold_comparison='n=12; N=n*sum(x^2)-sum(x)^2; D=sum(x)^2. Positive X iff 4*N<=D, else Y iff N<=D, else Z. HUGEINT with weekly units guarded at 7*expected_stores*2147483647 before squaring.',
        analysis_window={'start_date':'2016-01-30','end_date':'2016-04-22','weeks':12,'days':84,'stores_pooled':10},
        timings=timings, timing_scope='CLI timings only, excluding source hashing and Python reference work.',
        weekly_rows_compared=36588, weekly_columns_compared=8, metric_rows_compared=3049,
        xyz_columns_compared=15, class_mismatches=0, copied_metric_mismatches=0,
        float_error_summary=float_errors, weekly_input_unchanged=True, metric_input_unchanged=True,
        weekly_before_sha256=fingerprint(weekly_before), weekly_after_sha256=fingerprint(weekly_after),
        metrics_before_sha256=fingerprint(metrics_before), metrics_after_sha256=fingerprint(metrics_after),
        accepted_variability_report_matched=True, fixture_cases_passed=len(cases), fixture_cases=cases,
        result_rows=5, results=results,
        scope='Assistant preflight only; learner SQL25 execution pending. Descriptive baseline choices, not optimized thresholds or forecast skill. Short window and store pooling limit interpretation; no inventory or availability inference. No row-level source data published.')
    args.output.write_text(json.dumps(report, indent=2, default=str)+'\n', encoding='utf-8', newline='\n')
    print(json.dumps({'fixture_cases_passed':len(cases),'results':results,'timings':timings},default=str),flush=True)


if __name__ == '__main__':
    main()
