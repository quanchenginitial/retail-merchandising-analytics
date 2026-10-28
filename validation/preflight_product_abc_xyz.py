"""Verify the two-window ABC x XYZ snapshot in private databases against original CSVs."""
import argparse
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
from preflight_abc_threshold_sensitivity import prefix_reference, baseline_summary, SNAPSHOT_SQL as ABC_SNAPSHOT
from preflight_product_variability import (
    assert_exact_rows, fingerprint, parse, quote, reference_metrics, reference_report,
    sha256, source_weekly_rows, source_weekly_report, WEEKLY_SNAPSHOT, METRIC_SNAPSHOT,
)
from preflight_product_xyz import XYZ_SNAPSHOT, assert_xyz, xyz_report
from preflight_xyz_threshold_sensitivity import centered_cv_squared, classify

SNAPSHOTS = {'abc': ABC_SNAPSHOT, 'weekly': WEEKLY_SNAPSHOT, 'metrics': METRIC_SNAPSHOT, 'xyz': XYZ_SNAPSHOT}
COMBINED_SNAPSHOT = 'SELECT * FROM mart.m5_product_abc_xyz ORDER BY item_id;'
TARGET = 'mart.m5_product_abc_xyz'


def assemble(abc, xyz):
    """Copy each independent/source snapshot without rounding floats; add its integer bridge."""
    by_item = {row['item_id']: row for row in xyz}
    assert len(by_item) == len(xyz) == len(abc)
    assert set(by_item) == {row['item_id'] for row in abc}
    result = []
    for a in sorted(abc, key=lambda row: row['item_id']):
        x = by_item[a['item_id']]
        assert (a['dept_id'], a['cat_id']) == (x['dept_id'], x['cat_id'])
        result.append(dict(
            item_id=a['item_id'], dept_id=a['dept_id'], cat_id=a['cat_id'],
            abc_window_start=a['window_start'], abc_window_end=a['window_end'],
            xyz_window_start=x['window_start'], xyz_window_end=x['window_end'],
            units_90d=int(a['units']), units_84d=int(x['units']),
            excluded_six_day_units=int(a['units']) - int(x['units']),
            abc_sku_rank=a['sku_rank'], abc_cumulative_units=a['cumulative_units'],
            abc_class=a['abc_class'], xyz_class=x['xyz_class'], week_count=x['week_count'],
            mean_weekly_units=x['mean_weekly_units'], stddev_weekly_units=x['stddev_weekly_units'],
            cv_weekly=x['cv_weekly'], zero_sales_weeks=x['zero_sales_weeks'],
            zero_week_share=x['zero_week_share'], positive_weeks=x['positive_weeks'],
            mean_positive_gap_weeks=x['mean_positive_gap_weeks']))
    return result


def reference(source):
    abc = prefix_reference([dict(item_id=r['item_id'], dept_id=r['dept_id'], cat_id=r['cat_id'],
                                 units=r['units_90d']) for r in source])
    xyz, _ = reference_metrics(source)
    vectors = {r['item_id']: r['weeks'] for r in source}
    for row in xyz:
        row['xyz_class'] = classify(centered_cv_squared(vectors[row['item_id']]))
    return abc, xyz, assemble(abc, xyz)


def matrix(rows):
    result = []
    for label in ('A', 'B', 'C', 'ZERO_SALES', 'TOTAL'):
        members = rows if label == 'TOTAL' else [r for r in rows if r['abc_class'] == label]
        result.append(dict(
            abc_class=label, x_skus=sum(r['xyz_class'] == 'X' for r in members),
            y_skus=sum(r['xyz_class'] == 'Y' for r in members), z_skus=sum(r['xyz_class'] == 'Z' for r in members),
            zero_xyz_skus=sum(r['xyz_class'] == 'ZERO_SALES' for r in members), total_skus=len(members),
            abc_window='2016-01-26..2016-04-24', xyz_window='2016-01-30..2016-04-22', check_status='PASS'))
    return result


def extract_abc(rows):
    return [dict(item_id=r['item_id'], dept_id=r['dept_id'], cat_id=r['cat_id'],
                 window_start=r['abc_window_start'], window_end=r['abc_window_end'], units=r['units_90d'],
                 sku_rank=r['abc_sku_rank'], cumulative_units=r['abc_cumulative_units'], abc_class=r['abc_class'])
            for r in rows]


def extract_xyz(rows):
    return [dict(item_id=r['item_id'], dept_id=r['dept_id'], cat_id=r['cat_id'],
                 window_start=r['xyz_window_start'], window_end=r['xyz_window_end'], week_count=r['week_count'],
                 units=r['units_84d'], mean_weekly_units=r['mean_weekly_units'],
                 stddev_weekly_units=r['stddev_weekly_units'], cv_weekly=r['cv_weekly'],
                 zero_sales_weeks=r['zero_sales_weeks'], zero_week_share=r['zero_week_share'],
                 positive_weeks=r['positive_weeks'], mean_positive_gap_weeks=r['mean_positive_gap_weeks'],
                 xyz_class=r['xyz_class']) for r in rows]


def assert_combined(actual, source, snapshots):
    expected_abc, expected_xyz, expected = reference(source)
    assert all(len(r) == 22 for r in actual)
    assert_exact_rows(actual, assemble(snapshots['abc'], snapshots['xyz']), 'all 22 copied source fields')
    assert_exact_rows(extract_abc(actual), expected_abc, 'nine ABC fields from original wide totals')
    errors = assert_xyz(extract_xyz(actual), expected_xyz, snapshots['metrics'])
    by_item = {r['item_id']: r for r in source}
    for row in actual:
        raw = by_item[row['item_id']]
        assert int(row['units_90d']) == sum(raw['weeks']) + raw['excluded_six_day_units']
        assert int(row['excluded_six_day_units']) == raw['excluded_six_day_units'] >= 0
        assert (int(row['units_90d']) != 0 or row['xyz_class'] == 'ZERO_SALES')
    assert matrix(actual) == matrix(expected)
    return errors


def normalized_report(rows):
    integer_fields = {'sku_count', 'units', 'first_rank', 'last_rank', 'zero_sales_product_weeks'}
    return [{key: None if value is None else Decimal(str(value)) if key.endswith('_pct') or key == 'median_cv'
             else int(value) if key in integer_fields else value for key, value in row.items()} for row in rows]


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
        '21': 'sql/21_build_product_abc_units.sql', '23': 'sql/23_build_product_weekly.sql',
        '24': 'sql/24_build_product_variability.sql', '25': 'sql/25_build_product_xyz.sql',
        '27': 'sql/27_build_product_abc_xyz.sql',
    }
    script_bytes = {key: (root / path).read_bytes() for key, path in script_paths.items()}
    scripts = {}
    for key, contents in script_bytes.items():
        build, audit = contents.decode('utf-8').split('-- VALIDATION:', 1)
        scripts[key] = (build, '-- VALIDATION:' + audit)
    helper_paths = [
        'validation/preflight_abc_threshold_sensitivity.py', 'validation/preflight_product_variability.py',
        'validation/preflight_product_xyz.py', 'validation/preflight_xyz_threshold_sensitivity.py',
    ]
    helper_hashes = {path: sha256(root / path) for path in helper_paths}
    historical_path = root / 'data/product_abc_units_preflight.json'
    historical_hash = sha256(historical_path)
    mixed = [[10] * 12, [0] * 6 + [20] * 6, [120] + [0] * 11, [0] * 12,
             [0] * 12, [1] * 12, [0] * 6 + [4] * 6, [0] * 12]
    mixed_bridge = [0, 0, 0, 500, 0, 0, 0, 1]
    cases = []

    def tiny(name, vectors=None, bridges=None, mutation='', after='', reject=None,
             metric_perturbation='', invalid_nesting=False):
        vectors = mixed if vectors is None else vectors
        bridges = mixed_bridge if bridges is None else bridges
        assert len(vectors) == len(bridges)
        source = [dict(item_id=f'P{i:03d}', dept_id='FOODS_1', cat_id='FOODS', weeks=vector,
                       units_90d=sum(vector) + bridge, excluded_six_day_units=bridge)
                  for i, (vector, bridge) in enumerate(zip(vectors, bridges), 1)]
        if invalid_nesting:
            source[0]['units_90d'] = sum(source[0]['weeks']) - 1
        abc, _, _ = reference(source)
        products = ','.join(f"({quote(r['item_id'])},'FOODS_1','FOODS')" for r in source)

        def values(rows):
            return ','.join('(' + ','.join('NULL' if v is None else str(v) if isinstance(v, int) else quote(v)
                                          for v in row.values()) + ')' for row in rows)

        setup = f"""CREATE SCHEMA core; CREATE SCHEMA mart;
CREATE TABLE core.m5_product(item_id VARCHAR,dept_id VARCHAR,cat_id VARCHAR);
INSERT INTO core.m5_product VALUES {products};
CREATE TABLE mart.m5_product_weekly_12w(item_id VARCHAR,dept_id VARCHAR,cat_id VARCHAR,wm_yr_wk INTEGER,
week_start DATE,week_end DATE,units HUGEINT,source_daily_rows BIGINT);
INSERT INTO mart.m5_product_weekly_12w VALUES {values(source_weekly_rows(source, 2))};
CREATE TABLE mart.m5_product_abc_90d(item_id VARCHAR,dept_id VARCHAR,cat_id VARCHAR,window_start DATE,
window_end DATE,units HUGEINT,sku_rank BIGINT,cumulative_units HUGEINT,abc_class VARCHAR);
INSERT INTO mart.m5_product_abc_90d VALUES {values(abc)};
"""
        old, new = '3049 AS expected_items,10 AS expected_stores', f'{len(source)} AS expected_items,2 AS expected_stores'
        with tempfile.TemporaryDirectory(prefix='abc-xyz-fixture-', dir=tmp_root) as folder:
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
            run = execute(scripts['27'][0].replace(old, new))
            if reject == 'build':
                assert run.returncode != 0 and ('ABC XYZ' in run.stderr or 'XYZ blocked' in run.stderr), (name, run.stderr)
                probe = execute("SELECT COUNT(*) AS n FROM information_schema.tables WHERE table_schema='mart' AND table_name='m5_product_abc_xyz';")
                assert probe.returncode == 0 and parse(probe.stdout) == [{'n': 0}], (name, 'failed build left a table')
            else:
                assert run.returncode == 0, (name, run.stderr)
                if after:
                    run = execute(after)
                    assert run.returncode == 0, (name, run.stderr)
                run = execute(scripts['27'][1].replace(old, new))
                if reject == 'validation':
                    assert run.returncode != 0 and 'ABC XYZ validation blocked' in run.stderr, (name, run.stderr)
                else:
                    assert run.returncode == 0, (name, run.stderr)
                    assert_exact_rows(parse(run.stdout), matrix(reference(source)[2]), name + ' matrix')
                    actual = execute(COMBINED_SNAPSHOT)
                    assert actual.returncode == 0, (name, actual.stderr)
                    rows = parse(actual.stdout)
                    assert_combined(rows, source, before)
                    if name == 'mixed_labels_and_positive_90d_zero_84d_can_be_a':
                        row = next(r for r in rows if r['item_id'] == 'P004')
                        assert row['abc_class'] == 'A' and row['xyz_class'] == 'ZERO_SALES'
            for key, sql in SNAPSHOTS.items():
                run = execute(sql)
                assert run.returncode == 0 and parse(run.stdout) == before[key], (name, key, 'input changed')
        assert not Path(folder).exists()
        cases.append(dict(case=name, passed=True, rejected_at=reject, all_four_input_tables_unchanged=True,
                          failed_build_leaves_no_target=True if reject == 'build' else None))
        if len(cases) == 1:
            print(json.dumps({'first_fixture_passed': name}), flush=True)

    tiny('mixed_labels_and_positive_90d_zero_84d_can_be_a')
    tiny('all_zero_preserves_null_ranks_and_cv', vectors=[[0] * 12] * 2, bridges=[0, 0])
    tiny('constant_positive_empty_matrix_cells_are_zero', vectors=[[10] * 12] * 2, bridges=[0, 0])
    tiny('accepted_float_tolerance_is_copied_exactly',
         metric_perturbation="UPDATE mart.m5_product_variability_12w SET cv_weekly=cv_weekly+1e-10 WHERE item_id='P002';")
    for name, mutation in [
        ('empty_abc_source', 'DELETE FROM mart.m5_product_abc_90d;'),
        ('duplicate_abc_product', "INSERT INTO mart.m5_product_abc_90d SELECT * FROM mart.m5_product_abc_90d WHERE item_id='P001';"),
        ('missing_xyz_product', "DELETE FROM mart.m5_product_xyz_12w WHERE item_id='P005';"),
        ('abc_product_mapping_conflict', "UPDATE mart.m5_product_abc_90d SET dept_id='FOODS_2' WHERE item_id='P001';"),
        ('wrong_abc_rank', "UPDATE mart.m5_product_abc_90d SET sku_rank=sku_rank+1 WHERE item_id='P001';"),
        ('wrong_abc_class', "UPDATE mart.m5_product_abc_90d SET abc_class='C' WHERE item_id='P001';"),
        ('wrong_abc_window', "UPDATE mart.m5_product_abc_90d SET window_end=window_end-1 WHERE item_id='P001';"),
        ('missing_source_week', "DELETE FROM mart.m5_product_weekly_12w WHERE item_id='P001' AND wm_yr_wk=11601;"),
        ('xyz_source_copied_float_drift', "UPDATE mart.m5_product_xyz_12w SET cv_weekly=cv_weekly+1e-10 WHERE item_id='P002';"),
    ]:
        tiny(name, mutation=mutation, reject='build')
    tiny('individually_valid_abc_has_units_below_84d', invalid_nesting=True, reject='build')
    for name, mutation in [
        ('target_copied_float_drift', f"UPDATE {TARGET} SET cv_weekly=cv_weekly+1e-10 WHERE item_id='P002';"),
        ('target_six_day_bridge_drift', f"UPDATE {TARGET} SET excluded_six_day_units=excluded_six_day_units+1 WHERE item_id='P001';"),
        ('target_xyz_window_drift', f"UPDATE {TARGET} SET xyz_window_start=xyz_window_start+1 WHERE item_id='P001';"),
        ('target_swap_labels_preserves_count_and_unit_margins', f"UPDATE {TARGET} SET xyz_class=CASE item_id WHEN 'P001' THEN 'Y' ELSE 'X' END WHERE item_id IN ('P001','P002');"),
        ('target_duplicate_product', f"INSERT INTO {TARGET} SELECT * FROM {TARGET} WHERE item_id='P001';"),
        ('target_wrong_schema', f'ALTER TABLE {TARGET} ALTER cv_weekly TYPE DECIMAL(30,12);'),
    ]:
        tiny(name, after=mutation, reject='validation')
    assert len(cases) == 20
    print(json.dumps({'fixture_cases_passed': len(cases)}), flush=True)
    if args.fixtures_only:
        return

    source_root = Path('D:/database/m5-forecasting-accuracy')
    sources = [source_root / name for name in ('sales_train_evaluation.csv', 'calendar.csv')]
    registry = json.loads((root / 'data/m5_source_audit.json').read_text(encoding='utf-8'))
    hashes = {path.name: sha256(path) for path in sources}
    assert all(hashes[p.name] == registry['files'][p.name]['sha256'] for p in sources)
    columns = ','.join(f'd_{day}' for day in range(1824, 1914))
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

    def wide_sum(days, alias):
        names = ','.join(f'd_{day}' for day in days)
        return f"SUM(list_sum(list_transform(list_value({names}),lambda x: CASE WHEN regexp_full_match(x,'[0-9]+') AND TRY_CAST(x AS INTEGER) IS NOT NULL THEN CAST(x AS BIGINT) ELSE error('Wide reference requires nonnegative INTEGER units') END))) AS {alias}"

    expressions = [wide_sum(range(1828 + i * 7, 1835 + i * 7), f'w{i}') for i in range(12)]
    expressions += [wide_sum(range(1824, 1914), 'units_90d'),
                    wide_sum([1824, 1825, 1826, 1827, 1912, 1913], 'excluded_six_day_units')]
    vector_sql = 'SELECT item_id,dept_id,cat_id,' + ','.join(expressions) + ' FROM raw.sales_window_wide GROUP BY item_id,dept_id,cat_id ORDER BY item_id;'
    accepted_paths = {'abc': 'data/product_abc_units_learner_acceptance.json',
                      'xyz': 'data/product_xyz_learner_acceptance.json'}
    accepted_bytes = {key: (root / path).read_bytes() for key, path in accepted_paths.items()}
    accepted = {key: json.loads(value.decode('utf-8')) for key, value in accepted_bytes.items()}
    assert all(value['rows_with_pass_status'] == 5 for value in accepted.values())
    timings = {}
    with tempfile.TemporaryDirectory(prefix='abc-xyz-', dir=tmp_root) as folder:
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
        print(json.dumps({'window_setup_seconds': timings['window_setup_seconds']}), flush=True)
        upstream = {}
        for key in ('21', '23', '24', '25'):
            execute(scripts[key][0], f'sql{key}_build_seconds')
            upstream[key] = execute(scripts[key][1], f'sql{key}_validation_seconds')
        raw = execute(vector_sql, 'independent_wide_vector_query_seconds')
        assert len(raw) == len({row['item_id'] for row in raw}) == 3049
        source = [dict(item_id=r['item_id'], dept_id=r['dept_id'], cat_id=r['cat_id'],
                       weeks=[int(r[f'w{i}']) for i in range(12)], units_90d=int(r['units_90d']),
                       excluded_six_day_units=int(r['excluded_six_day_units'])) for r in raw]
        for row in source:
            assert row['units_90d'] == sum(row['weeks']) + row['excluded_six_day_units']
        abc, xyz, expected = reference(source)
        before = {key: execute(sql) for key, sql in SNAPSHOTS.items()}
        assert_exact_rows(before['abc'], abc, 'original wide 90-day ABC fields')
        assert_exact_rows(before['weekly'], source_weekly_rows(source, 10), 'original wide weekly values')
        assert_exact_rows(upstream['21'], baseline_summary(abc), 'original wide ABC report')
        assert_exact_rows(upstream['23'], source_weekly_report(source_weekly_rows(source, 10)), 'original wide weekly report')
        assert_exact_rows(upstream['24'], reference_report([{k: v for k, v in r.items() if k != 'xyz_class'} for r in xyz]), 'original wide metric report')
        assert_xyz(before['xyz'], xyz, before['metrics'])
        assert_exact_rows(upstream['25'], xyz_report(xyz), 'original wide XYZ report')
        assert_exact_rows(upstream['21'], normalized_report(accepted['abc']['results']), 'learner accepted ABC report')
        assert_exact_rows(upstream['25'], normalized_report(accepted['xyz']['results']), 'learner accepted XYZ report')
        input_hashes = {key: fingerprint(rows) for key, rows in before.items()}
        execute(scripts['27'][0], 'combined_build_seconds')
        results = execute(scripts['27'][1], 'combined_validation_seconds')
        actual = execute(COMBINED_SNAPSHOT, 'combined_snapshot_query_seconds')
        assert len(actual) == 3049
        float_errors = assert_combined(actual, source, before)
        assert_exact_rows(results, matrix(expected), 'five-row matrix')
        after = {key: execute(sql) for key, sql in SNAPSHOTS.items()}
        for key in SNAPSHOTS:
            assert before[key] == after[key] and input_hashes[key] == fingerprint(after[key]), (key, 'input changed')
        database_bytes = database.stat().st_size
    assert not Path(folder).exists()
    assert all(sha256(path) == hashes[path.name] for path in sources)
    assert sha256(historical_path) == historical_hash
    assert all((root / script_paths[key]).read_bytes() == value for key, value in script_bytes.items())
    assert all(sha256(root / path) == value for path, value in helper_hashes.items())
    bridge_only = [r for r in source if r['units_90d'] > 0 and sum(r['weeks']) == 0]
    controls = dict(units_90d=sum(r['units_90d'] for r in source), units_84d=sum(sum(r['weeks']) for r in source),
                    excluded_six_day_units=sum(r['excluded_six_day_units'] for r in source),
                    zero_90d_products=sum(r['units_90d'] == 0 for r in source),
                    zero_84d_products=sum(sum(r['weeks']) == 0 for r in source),
                    positive_90d_zero_84d_products=len(bridge_only),
                    positive_90d_zero_84d_units=sum(r['units_90d'] for r in bridge_only),
                    per_product_bridge_mismatches=0)
    assert controls['zero_90d_products'] == 4 and controls['zero_84d_products'] == 7 and len(bridge_only) == 3
    report = dict(
        checked_at_utc=datetime.now(timezone.utc).isoformat(), executor='assistant',
        engine=subprocess.check_output([args.duckdb, '-version'], text=True).strip(),
        baseline_database='Private temporary on-disk DuckDB under repository tmp; removed after verification.',
        temporary_baseline_removed=True, temporary_database_bytes_after_close=database_bytes,
        settings={'threads': 2, 'memory_limit': '2GB'}, script=script_paths['27'],
        script_sha256=hashlib.sha256(script_bytes['27']).hexdigest(),
        prerequisite_script_sha256={script_paths[key]: hashlib.sha256(script_bytes[key]).hexdigest() for key in ('21', '23', '24', '25')},
        reference_helper_sha256=helper_hashes, source_sha256=hashes, source_hashes_unchanged=True,
        historical_abc_preflight='data/product_abc_units_preflight.json', historical_abc_preflight_sha256=historical_hash,
        historical_abc_preflight_unchanged=True,
        preflight_strategy='Read only original sales/calendar CSVs. A private 90-day six-column daily table feeds actual SQL21,23,24,25 and27. This is not a full-history rebuild; the learner database is never opened.',
        independent_reference='Original wide arrays independently supply per-product 90-day totals, twelve seven-day vectors and six excluded-day totals. Python crossing-prefix endpoints label ABC; centered Fraction population CV squared labels XYZ. Seventy-digit Decimal references verify five float fields with absolute 1e-9 plus relative 1e-9 tolerance. All 22 copied fields also match the accepted input snapshots exactly.',
        analysis_windows={'abc': {'start_date': '2016-01-26', 'end_date': '2016-04-24', 'days': 90},
                          'xyz': {'start_date': '2016-01-30', 'end_date': '2016-04-22', 'days': 84, 'weeks': 12},
                          'scope': 'Every product pooled across all ten stores; zero observations are retained.'},
        timings=timings, timing_scope='DuckDB CLI process timings; excludes Python reference/comparison and file hashing.',
        product_rows_compared=3049, columns_compared=22, field_mismatches=0,
        copied_snapshot_fields_match_exactly=True, float_error_summary=float_errors, source_controls=controls,
        abc_count_and_unit_margins_matched=True, xyz_count_and_unit_margins_matched=True,
        accepted_baselines_matched=True, accepted_baseline_evidence=accepted_paths,
        accepted_baseline_evidence_sha256={key: hashlib.sha256(value).hexdigest() for key, value in accepted_bytes.items()},
        all_input_tables_unchanged=True, input_rows_sha256_before=input_hashes,
        input_rows_sha256_after={key: fingerprint(rows) for key, rows in after.items()},
        result_rows=5, results=results, fixture_cases_passed=len(cases), fixture_cases=cases,
        scope='Assistant preflight only; learner combined-table execution pending. This count matrix combines two explicitly different historical windows. It does not estimate inventory, profitability, replenishment targets or forecast performance. No SKU-level extract is saved.')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, default=str) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps({'fixture_cases_passed': len(cases), 'source_controls': controls,
                      'timings': timings, 'results': results}, default=str), flush=True)


if __name__ == '__main__':
    main()
