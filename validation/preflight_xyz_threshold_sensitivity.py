"""Verify read-only XYZ sensitivity against exact centered Fraction variance and original CSVs."""
import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from fractions import Fraction
from pathlib import Path

sys.dont_write_bytecode = True
from preflight_product_variability import (
    assert_exact_rows, fingerprint, parse, quote, reference_metrics, reference_report,
    sha256, source_weekly_rows, source_weekly_report, WEEKLY_SNAPSHOT, METRIC_SNAPSHOT,
)
from preflight_product_xyz import XYZ_SNAPSHOT, assert_xyz, xyz_report

SCENARIOS = [
    ('BASE_050_100', 5, 10, None),
    ('X040_Y100', 4, 10, ('X', 'Y')),
    ('X060_Y100', 6, 10, ('Y', 'X')),
    ('X050_Y090', 5, 9, ('Y', 'Z')),
    ('X050_Y110', 5, 11, ('Z', 'Y')),
]
SNAPSHOTS = {'weekly': WEEKLY_SNAPSHOT, 'metrics': METRIC_SNAPSHOT, 'xyz': XYZ_SNAPSHOT}


def centered_cv_squared(vector):
    """Exact centered population variance; deliberately not SQL's raw-moment formula."""
    assert len(vector) == 12 and all(isinstance(value, int) and value >= 0 for value in vector)
    mean = Fraction(sum(vector), len(vector))
    if mean == 0:
        return None
    variance = sum((Fraction(value) - mean) ** 2 for value in vector) / len(vector)
    return variance / (mean * mean)


def classify(squared_cv, x_tenths=5, y_tenths=10):
    if squared_cv is None:
        return 'ZERO_SALES'
    return ('X' if squared_cv <= Fraction(x_tenths, 10) ** 2
            else 'Y' if squared_cv <= Fraction(y_tenths, 10) ** 2 else 'Z')


def reference(source):
    metrics, _ = reference_metrics(source)
    squared = {row['item_id']: centered_cv_squared(row['weeks']) for row in source}
    baseline = []
    for row in metrics:
        baseline.append(dict(row, xyz_class=classify(squared[row['item_id']])))
    memberships, summaries = [], []
    total_units = sum(row['units'] for row in baseline)
    for scenario, x_tenths, y_tenths, allowed in SCENARIOS:
        current = []
        for row in baseline:
            label = classify(squared[row['item_id']], x_tenths, y_tenths)
            if label != row['xyz_class']:
                assert (row['xyz_class'], label) == allowed
            current.append(dict(scenario=scenario, item_id=row['item_id'], units=row['units'],
                                baseline_class=row['xyz_class'], scenario_class=label))
        changed = [row for row in current if row['baseline_class'] != row['scenario_class']]
        changed_units = sum(row['units'] for row in changed)
        summaries.append(dict(
            scenario=scenario, x_skus=sum(row['scenario_class'] == 'X' for row in current),
            y_skus=sum(row['scenario_class'] == 'Y' for row in current),
            z_skus=sum(row['scenario_class'] == 'Z' for row in current),
            zero_skus=sum(row['scenario_class'] == 'ZERO_SALES' for row in current),
            changed_skus=len(changed),
            changed_sku_pct=(Decimal(100) * len(changed) / len(baseline)).quantize(Decimal('.0001'), rounding=ROUND_HALF_UP),
            changed_unit_share_pct=None if total_units == 0 else
                (Decimal(100) * changed_units / total_units).quantize(Decimal('.0001'), rounding=ROUND_HALF_UP),
            check_status='PASS'))
        memberships.extend(current)
    return baseline, summaries, sorted(memberships, key=lambda row: (row['scenario'], row['item_id']))


def boundary_vectors():
    exact = [(4, [3] * 6 + [7] * 6), (5, [1] * 6 + [3] * 6),
             (6, [2] * 6 + [8] * 6), (9, [1] * 6 + [19] * 6),
             (10, [0] * 6 + [2] * 6), (11, [0] * 6 + [31, 9, 22, 18, 21, 19])]
    vectors = []
    for tenths, small in exact:
        middle = [value * 1000000 for value in small]
        below, above = middle.copy(), middle.copy()
        largest = max(range(12), key=lambda index: middle[index])
        if tenths == 10:
            below[below.index(0)] += 1
        else:
            below[largest] -= 1
        above[largest] += 1
        target = Fraction(tenths, 10) ** 2
        assert centered_cv_squared(middle) == target
        assert centered_cv_squared(below) < target < centered_cv_squared(above)
        vectors.extend([middle, below, above])
    return vectors + [[0] * 12, [10] * 12]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--duckdb', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--fixtures-only', action='store_true')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    tmp_root = root / 'tmp'
    tmp_root.mkdir(exist_ok=True)
    script_paths = {
        '23': 'sql/23_build_product_weekly.sql', '24': 'sql/24_build_product_variability.sql',
        '25': 'sql/25_build_product_xyz.sql', '26': 'sql/26_xyz_threshold_sensitivity.sql',
    }
    script_bytes = {key: (root / path).read_bytes() for key, path in script_paths.items()}
    scripts = {}
    for key in ('23', '24', '25'):
        build, audit = script_bytes[key].decode('utf-8').split('-- VALIDATION:', 1)
        scripts[key] = (build, '-- VALIDATION:' + audit)
    query = script_bytes['26'].decode('utf-8')
    membership_suffix = 'SELECT scenario,item_id,units,baseline_class,scenario_class FROM scenario_members ORDER BY scenario,item_id;'
    helper_paths = ['validation/preflight_product_variability.py', 'validation/preflight_product_xyz.py']
    helper_hashes = {path: sha256(root / path) for path in helper_paths}
    mixed = boundary_vectors()
    cases = []

    def tiny(name, vectors=None, mutation='', reject=False, metric_perturbation='', null_threshold=False):
        vectors = mixed if vectors is None else vectors
        source = [dict(item_id=f'P{index:03d}', dept_id='FOODS_1', cat_id='FOODS', weeks=vector)
                  for index, vector in enumerate(vectors, 1)]
        products = ','.join(f"({quote(row['item_id'])},'FOODS_1','FOODS')" for row in source)
        values = ','.join('(' + ','.join(str(value) if isinstance(value, int) else quote(value)
                                        for value in row.values()) + ')' for row in source_weekly_rows(source, 2))
        setup = f"""CREATE SCHEMA core; CREATE SCHEMA mart;
CREATE TABLE core.m5_product(item_id VARCHAR,dept_id VARCHAR,cat_id VARCHAR);
INSERT INTO core.m5_product VALUES {products};
CREATE TABLE mart.m5_product_weekly_12w(item_id VARCHAR,dept_id VARCHAR,cat_id VARCHAR,wm_yr_wk INTEGER,
week_start DATE,week_end DATE,units HUGEINT,source_daily_rows BIGINT);
INSERT INTO mart.m5_product_weekly_12w VALUES {values};
"""
        old = '3049 AS expected_items,10 AS expected_stores'
        new = f'{len(vectors)} AS expected_items,2 AS expected_stores'
        fixture_query = query.replace(old, new)
        if null_threshold:
            assert "(2,'X040_Y100',4,10" in fixture_query
            fixture_query = fixture_query.replace("(2,'X040_Y100',4,10", "(2,'X040_Y100',NULL,10")
        with tempfile.TemporaryDirectory(prefix='xyz-sensitivity-fixture-', dir=tmp_root) as folder:
            assert Path(folder).resolve().is_relative_to(tmp_root.resolve())
            database = Path(folder) / 'fixture.duckdb'
            settings = "SET threads=2; SET memory_limit='2GB';\n"

            def execute(sql):
                return subprocess.run([args.duckdb, str(database), '-bail', '-json'], input=settings + sql,
                                      text=True, encoding='utf-8', capture_output=True)

            run = execute(setup + scripts['24'][0].replace(old, new) + metric_perturbation
                          + scripts['25'][0].replace(old, new) + mutation)
            assert run.returncode == 0, (name, run.stderr)
            before = {}
            for key, sql in SNAPSHOTS.items():
                run = execute(sql)
                assert run.returncode == 0, (name, run.stderr)
                before[key] = parse(run.stdout)
            run = execute(fixture_query)
            if reject:
                assert run.returncode != 0 and 'XYZ' in run.stderr, (name, run.stderr, run.stdout)
                if name == 'unsafe_weekly_square_input':
                    assert 'outside supported' in run.stderr, run.stderr
            else:
                assert run.returncode == 0, (name, run.stderr)
                expected, report, members = reference(source)
                assert_xyz(before['xyz'], expected, before['metrics'])
                assert_exact_rows(parse(run.stdout), report, name + ' report')
                run = execute(fixture_query.split('-- REPORT:', 1)[0] + membership_suffix)
                assert run.returncode == 0, (name, run.stderr)
                assert_exact_rows(parse(run.stdout), members, name + ' scenario members')
            for key, sql in SNAPSHOTS.items():
                run = execute(sql)
                assert run.returncode == 0 and parse(run.stdout) == before[key], (name, key, 'input changed')
        assert not Path(folder).exists()
        cases.append(dict(case=name, passed=True, rejected=reject, all_three_input_tables_unchanged=True))

    tiny('six_exact_boundaries_and_adjacent_integer_vectors')
    tiny('all_zero_shares_are_null', vectors=[[0] * 12] * 3)
    tiny('constant_positive_empty_y_z_zero_groups', vectors=[[5] * 12, [7] * 12])
    tiny('upper_supported_bound_keeps_integer_comparisons_safe', vectors=[[0] * 6 + [14 * 2147483647] * 6])
    tiny('tolerated_double_cv_drift_does_not_move_exact_memberships',
         metric_perturbation="UPDATE mart.m5_product_variability_12w SET cv_weekly=cv_weekly+1e-10 WHERE item_id='P004';")
    for name, mutation in [
        ('empty_weekly_source', 'DELETE FROM mart.m5_product_weekly_12w;'),
        ('missing_source_week', "DELETE FROM mart.m5_product_weekly_12w WHERE item_id='P001' AND wm_yr_wk=11601;"),
        ('duplicate_and_missing_source_week', "UPDATE mart.m5_product_weekly_12w SET wm_yr_wk=11602,week_start=DATE '2016-02-06',week_end=DATE '2016-02-12' WHERE item_id='P001' AND wm_yr_wk=11601;"),
        ('wrong_source_week_date', "UPDATE mart.m5_product_weekly_12w SET week_start=week_start+1 WHERE item_id='P001' AND wm_yr_wk=11601;"),
        ('unsafe_weekly_square_input', "UPDATE mart.m5_product_weekly_12w SET units=1000000000000000000000000000000::HUGEINT WHERE item_id='P001' AND wm_yr_wk=11601;"),
        ('wrong_source_metric_cv', "UPDATE mart.m5_product_variability_12w SET cv_weekly=0.1 WHERE item_id='P004';"),
        ('nan_source_metric_sd', "UPDATE mart.m5_product_variability_12w SET stddev_weekly_units='NaN'::DOUBLE WHERE item_id='P001';"),
        ('duplicate_product_mapping', "INSERT INTO core.m5_product SELECT * FROM core.m5_product WHERE item_id='P001';"),
        ('missing_baseline_product', "DELETE FROM mart.m5_product_xyz_12w WHERE item_id='P019';"),
        ('duplicate_baseline_product', "INSERT INTO mart.m5_product_xyz_12w SELECT * FROM mart.m5_product_xyz_12w WHERE item_id='P001';"),
        ('swapped_labels_preserve_class_counts_and_units', "UPDATE mart.m5_product_xyz_12w SET xyz_class=CASE item_id WHEN 'P001' THEN 'Y' ELSE 'X' END WHERE item_id IN ('P001','P007');"),
        ('baseline_copied_float_drift', "UPDATE mart.m5_product_xyz_12w SET cv_weekly=cv_weekly+1e-10 WHERE item_id='P004';"),
        ('wrong_baseline_window', "UPDATE mart.m5_product_xyz_12w SET window_end=window_end+1 WHERE item_id='P001';"),
        ('zero_baseline_class_cannot_be_x', "UPDATE mart.m5_product_xyz_12w SET xyz_class='X' WHERE item_id='P019';"),
        ('wrong_baseline_schema', 'ALTER TABLE mart.m5_product_xyz_12w ALTER cv_weekly TYPE DECIMAL(30,12);'),
    ]:
        tiny(name, mutation=mutation, reject=True)
    tiny('null_scenario_boundary_rejected', null_threshold=True, reject=True)
    assert len(cases) == 21
    print(json.dumps({'fixture_cases_passed': len(cases)}), flush=True)
    if args.fixtures_only:
        return

    source_root = Path('D:/database/m5-forecasting-accuracy')
    sources = [source_root / name for name in ['sales_train_evaluation.csv', 'calendar.csv']]
    registry = json.loads((root / 'data/m5_source_audit.json').read_text(encoding='utf-8'))
    hashes = {path.name: sha256(path) for path in sources}
    assert all(hashes[path.name] == registry['files'][path.name]['sha256'] for path in sources)
    columns = ','.join(f'd_{day}' for day in range(1828, 1912))
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
    for index in range(12):
        names = ','.join(f'd_{day}' for day in range(1828 + index * 7, 1835 + index * 7))
        expressions.append(f"SUM(list_sum(list_transform(list_value({names}),lambda x: CASE WHEN regexp_full_match(x,'[0-9]+') AND TRY_CAST(x AS INTEGER) IS NOT NULL THEN CAST(x AS BIGINT) ELSE error('Wide reference requires nonnegative INTEGER units') END))) AS w{index}")
    vector_sql = 'SELECT item_id,dept_id,cat_id,' + ','.join(expressions) + ' FROM raw.sales_window_wide GROUP BY item_id,dept_id,cat_id ORDER BY item_id;'
    accepted_path = root / 'data/product_xyz_learner_acceptance.json'
    accepted_bytes = accepted_path.read_bytes()
    accepted = json.loads(accepted_bytes.decode('utf-8'))
    assert accepted['rows_with_pass_status'] == 5
    assert accepted['analysis_window']['start_date'] == '2016-01-30'
    assert accepted['analysis_window']['end_date'] == '2016-04-22'
    timings = {}
    with tempfile.TemporaryDirectory(prefix='xyz-sensitivity-', dir=tmp_root) as folder:
        assert Path(folder).resolve().is_relative_to(tmp_root.resolve())
        database = Path(folder) / 'preflight.duckdb'
        assert database.resolve().is_relative_to(Path(folder).resolve())
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
        print(json.dumps({'window_setup_seconds': timings['window_setup_seconds']}), flush=True)
        upstream_results = {}
        for key in ('23', '24', '25'):
            execute(scripts[key][0], f'sql{key}_build_seconds')
            upstream_results[key] = execute(scripts[key][1], f'sql{key}_validation_seconds')
        raw_vectors = execute(vector_sql, 'independent_wide_vector_query_seconds')
        assert len(raw_vectors) == 3049 and len({row['item_id'] for row in raw_vectors}) == 3049
        source = [dict(item_id=row['item_id'], dept_id=row['dept_id'], cat_id=row['cat_id'],
                       weeks=[int(row[f'w{index}']) for index in range(12)]) for row in raw_vectors]
        expected, expected_summary, expected_members = reference(source)
        before = {key: execute(sql) for key, sql in SNAPSHOTS.items()}
        assert_exact_rows(before['weekly'], source_weekly_rows(source, 10), 'weekly values from original wide CSV')
        assert_exact_rows(upstream_results['23'], source_weekly_report(source_weekly_rows(source, 10)), 'weekly source report')
        metric_reference = [{key: value for key, value in row.items() if key != 'xyz_class'} for row in expected]
        assert_exact_rows(upstream_results['24'], reference_report(metric_reference), 'metric source report')
        float_errors = assert_xyz(before['xyz'], expected, before['metrics'])
        assert_exact_rows(upstream_results['25'], xyz_report(expected), 'baseline XYZ source report')
        normalized_accepted = [{key: None if value is None else Decimal(str(value)) if key.endswith('_pct') or key == 'median_cv'
                                else int(value) if key in ('sku_count', 'units', 'zero_sales_product_weeks') else value
                                for key, value in row.items()} for row in accepted['results']]
        assert_exact_rows(upstream_results['25'], normalized_accepted, 'learner accepted XYZ baseline')
        input_hashes = {key: fingerprint(rows) for key, rows in before.items()}
        results = execute(query, 'sensitivity_query_seconds')
        assert_exact_rows(results, expected_summary, 'five scenario reports')
        members = execute(query.split('-- REPORT:', 1)[0] + membership_suffix, 'scenario_membership_query_seconds')
        assert len(members) == 15245
        assert_exact_rows(members, expected_members, 'all scenario/product memberships')
        after = {key: execute(sql) for key, sql in SNAPSHOTS.items()}
        for key in SNAPSHOTS:
            assert before[key] == after[key] and input_hashes[key] == fingerprint(after[key]), (key, 'input changed')
        database_bytes = database.stat().st_size
    assert not Path(folder).exists()
    assert all(sha256(path) == hashes[path.name] for path in sources)
    report = dict(
        checked_at_utc=datetime.now(timezone.utc).isoformat(), executor='assistant',
        engine=subprocess.check_output([args.duckdb, '-version'], text=True).strip(),
        baseline_database='Private temporary on-disk DuckDB under repository tmp; removed after verification.',
        temporary_baseline_removed=True, temporary_database_bytes_after_close=database_bytes,
        settings={'threads': 2, 'memory_limit': '2GB'},
        script=script_paths['26'], script_sha256=hashlib.sha256(script_bytes['26']).hexdigest(),
        prerequisite_script_sha256={script_paths[key]: hashlib.sha256(script_bytes[key]).hexdigest() for key in ('23', '24', '25')},
        reference_helper_sha256=helper_hashes, source_sha256=hashes, source_hashes_unchanged=True,
        preflight_strategy='Read only sales/calendar CSVs. Build a private 84-day six-column daily table and small dimensions, then execute actual SQL23/24/25 before read-only SQL26. This is not a full-history rebuild; no learner database or ABC table is opened.',
        independent_reference='Original wide seven-day arrays supply twelve integer values per SKU. Fraction computes centered population variance / mean squared exactly, rather than the SQL raw-moment expression. Inclusive rational threshold comparisons define all labels; reused 70-digit Decimal metric references verify the fifteen-field baseline.',
        analysis_window={'start_date': '2016-01-30', 'end_date': '2016-04-22', 'inclusive_days': 84,
                         'week_count': 12, 'scope': 'Each product pooled across all ten stores, retaining zero-sales weeks.'},
        scenarios=[dict(scenario=name, x_tenths=x, y_tenths=y,
                        allowed_change=None if allowed is None else list(allowed)) for name, x, y, allowed in SCENARIOS],
        scenario_design='One boundary at a time, fixed before outputs. Absolute CV changes are 0.1; relative changes are 20% for X and 10% for Y. These are illustrative scenarios, not optimized thresholds.',
        timings=timings, timing_scope='DuckDB CLI process timings; excludes Python reference/comparison and file hashing.',
        baseline_sku_rows_compared=3049, baseline_columns_compared=15, baseline_label_mismatches=0,
        baseline_float_error_summary=float_errors, copied_metric_fields_match_exactly=True,
        scenario_sku_rows_compared=15245, scenario_membership_mismatches=0,
        accepted_xyz_baseline_matched=True, accepted_xyz_evidence='data/product_xyz_learner_acceptance.json',
        accepted_xyz_evidence_sha256=hashlib.sha256(accepted_bytes).hexdigest(),
        all_input_tables_unchanged=True, input_rows_sha256_before=input_hashes,
        input_rows_sha256_after={key: fingerprint(rows) for key, rows in after.items()},
        baseline_results=upstream_results['25'], result_rows=5, results=results,
        exact_boundary_controls=['0.4', '0.5', '0.6', '0.9', '1.0', '1.1'],
        fixture_cases_passed=len(cases), fixture_cases=cases,
        scope='Assistant preflight only; learner XYZ sensitivity execution pending. Changed-unit share is historical units belonging to reclassified products, not a sales change. Query rechecks accepted weekly, metric and XYZ snapshots without daily rescan; this private preflight independently compares original CSV totals. No optimization, temporal-stability or forecast-performance claim, no SKU-level extract and no ABC-table access.')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, default=str) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps({'fixture_cases_passed': len(cases), 'scenario_sku_rows_compared': 15245,
                      'all_input_tables_unchanged': True, 'timings': timings, 'results': results}, default=str), flush=True)


if __name__ == '__main__':
    main()
