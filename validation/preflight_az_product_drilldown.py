"""Verify local A x Z product detail privately; publish aggregates and fingerprints only."""
import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
import time
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

sys.dont_write_bytecode = True
from preflight_product_abc_xyz import reference, matrix, assert_combined
from preflight_abc_xyz_contribution import SNAPSHOTS, contribution_reference
from preflight_abc_threshold_sensitivity import baseline_summary
from preflight_product_variability import (
    assert_exact_rows, fingerprint, parse, quote, reference_report, sha256,
    source_weekly_rows, source_weekly_report,
)
from preflight_product_xyz import assert_xyz, xyz_report

PRODUCT_FIELDS = ('item_id', 'units_90d', 'units_84d', 'cv_weekly', 'zero_sales_weeks', 'mean_positive_gap_weeks')


def rounded(value):
    return None if value is None else Decimal(str(value)).quantize(Decimal('.000001'), rounding=ROUND_HALF_UP)


def detail_reference(combined):
    cohort = sorted((r for r in combined if r['abc_class'] == 'A' and r['xyz_class'] == 'Z'),
                    key=lambda r: (-int(r['units_90d']), r['item_id']))
    result = []
    for row in cohort or [None]:
        result.append(dict(
            segment='A × Z', item_id=None if row is None else row['item_id'],
            units_90d=None if row is None else int(row['units_90d']),
            units_84d=None if row is None else int(row['units_84d']),
            cv_weekly=None if row is None else rounded(row['cv_weekly']),
            zero_sales_weeks=None if row is None else row['zero_sales_weeks'],
            mean_positive_gap_weeks=None if row is None else rounded(row['mean_positive_gap_weeks']),
            abc_window='2016-01-26..2016-04-24', xyz_window='2016-01-30..2016-04-22',
            check_status='EMPTY' if row is None else 'PASS'))
    return cohort, result


def canonical_detail(rows):
    """Stable integer/decimal representations for cross-runtime evidence hashes."""
    result = []
    for row in rows:
        converted = dict(row)
        for key in ('units_90d', 'units_84d', 'zero_sales_weeks'):
            converted[key] = None if row[key] is None else int(row[key])
        for key in ('cv_weekly', 'mean_positive_gap_weeks'):
            converted[key] = None if row[key] is None else format(rounded(row[key]), '.6f')
        result.append(converted)
    return result


def row_hash(rows):
    return hashlib.sha256(json.dumps(rows, ensure_ascii=False, sort_keys=True,
                                     separators=(',', ':')).encode('utf-8')).hexdigest()


def assert_detail(actual, combined, context):
    cohort, expected = detail_reference(combined)
    assert all(len(row) == 10 for row in actual), context
    assert_exact_rows(actual, expected, context)
    assert canonical_detail(actual) == canonical_detail(expected), context
    if cohort:
        keys = [(-int(r['units_90d']), r['item_id']) for r in actual]
        assert keys == sorted(keys), context + ' order'
        assert len({r['item_id'] for r in actual}) == len(actual) == len(cohort)
    else:
        assert len(actual) == 1 and actual[0]['check_status'] == 'EMPTY'
        assert all(actual[0][key] is None for key in PRODUCT_FIELDS)
    return cohort, expected


def aggregate_detail(rows):
    active = [r for r in rows if r['item_id'] is not None]

    def bounds(key):
        values = [r[key] for r in active if r[key] is not None]
        return {'minimum': min(values) if values else None, 'maximum': max(values) if values else None}

    canonical = canonical_detail(active)
    units90 = [int(r['units_90d']) for r in active]
    units84 = [int(r['units_84d']) for r in active]
    return dict(
        product_count=len(active), units_90d=sum(units90), units_84d=sum(units84),
        excluded_six_day_units=sum(units90) - sum(units84),
        units_90d_range={'minimum': min(units90) if units90 else None, 'maximum': max(units90) if units90 else None},
        units_84d_range={'minimum': min(units84) if units84 else None, 'maximum': max(units84) if units84 else None},
        displayed_cv_range=bounds('cv_weekly'), zero_sales_weeks_range=bounds('zero_sales_weeks'),
        zero_sales_product_weeks=sum(int(r['zero_sales_weeks']) for r in active),
        displayed_mean_positive_gap_range=bounds('mean_positive_gap_weeks'),
        null_mean_positive_gap_products=sum(r['mean_positive_gap_weeks'] is None for r in active),
        units_90d_tied_value_groups=sum(count > 1 for count in Counter(units90).values()),
        ordered_detail_sha256=row_hash(canonical),
        ordered_membership_sha256=row_hash([r['item_id'] for r in active]))


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
        '27': 'sql/27_build_product_abc_xyz.sql', '29': 'sql/29_az_product_drilldown.sql',
    }
    script_bytes = {key: (root / path).read_bytes() for key, path in script_paths.items()}
    scripts = {}
    for key in ('21', '23', '24', '25', '27'):
        build, audit = script_bytes[key].decode('utf-8').split('-- VALIDATION:', 1)
        scripts[key] = (build, '-- VALIDATION:' + audit)
    query = script_bytes['29'].decode('utf-8')
    helper_paths = [
        'validation/preflight_product_abc_xyz.py', 'validation/preflight_abc_xyz_contribution.py',
        'validation/preflight_abc_threshold_sensitivity.py', 'validation/preflight_product_variability.py',
        'validation/preflight_product_xyz.py', 'validation/preflight_xyz_threshold_sensitivity.py',
    ]
    helper_hashes = {path: sha256(root / path) for path in helper_paths}
    historical = {p.relative_to(root).as_posix(): sha256(p) for p in (root / 'data').glob('*_preflight.json')
                  if p.name != 'az_product_drilldown_preflight.json'}
    mixed = [[120] + [0] * 11, [60] + [0] * 10 + [60], [10] * 12,
             [0] * 6 + [20] * 6, [0] * 12, [1] * 12, [0] * 12]
    mixed_bridge = [0, 0, 0, 0, 500, 0, 0]
    cases = []

    def tiny(name, vectors=None, bridges=None, mutation='', reject=False,
             metric_perturbation='', reverse_input=False):
        vectors = mixed if vectors is None else vectors
        bridges = mixed_bridge if bridges is None else bridges
        assert len(vectors) == len(bridges)
        source = [dict(item_id=f'P{i:03d}', dept_id='FOODS_1', cat_id='FOODS', weeks=vector,
                       units_90d=sum(vector) + bridge, excluded_six_day_units=bridge)
                  for i, (vector, bridge) in enumerate(zip(vectors, bridges), 1)]
        abc, _, expected = reference(source)
        products = ','.join(f"({quote(r['item_id'])},'FOODS_1','FOODS')" for r in source)

        def values(rows):
            rows = list(reversed(rows)) if reverse_input else rows
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
        result_count = None
        with tempfile.TemporaryDirectory(prefix='az-drilldown-fixture-', dir=tmp_root) as folder:
            assert Path(folder).resolve().is_relative_to(tmp_root.resolve())
            database = Path(folder) / 'fixture.duckdb'
            settings = "SET threads=2; SET memory_limit='2GB';\n"

            def execute(sql):
                return subprocess.run([args.duckdb, str(database), '-bail', '-json'], input=settings + sql,
                                      text=True, encoding='utf-8', capture_output=True)

            run = execute(setup + scripts['24'][0].replace(old, new) + metric_perturbation
                          + scripts['25'][0].replace(old, new) + scripts['27'][0].replace(old, new) + mutation)
            assert run.returncode == 0, (name, run.stderr)
            before = {}
            for key, sql in SNAPSHOTS.items():
                run = execute(sql)
                assert run.returncode == 0, (name, run.stderr)
                before[key] = parse(run.stdout)
            run = execute(query.replace(old, new))
            if reject:
                assert run.returncode != 0 and ('A Z drilldown blocked' in run.stderr or 'XYZ blocked' in run.stderr), (name, run.stderr)
            else:
                assert run.returncode == 0, (name, run.stderr)
                assert_combined(before['combined'], source, before)
                observed = parse(run.stdout)
                cohort, _ = assert_detail(observed, expected, name)
                result_count = len(observed)
                if name == 'z_above_exact_boundary_kept_when_display_cv_is_one':
                    assert len(cohort) == 1 and cohort[0]['cv_weekly'] > 1
                    assert Decimal(str(observed[0]['cv_weekly'])) == 1
                if name == 'equal_units_use_item_tiebreak_despite_reverse_source_rows':
                    assert len(cohort) == 10
                    assert len({r['units_90d'] for r in observed}) == 1
                    assert [r['item_id'] for r in observed] == sorted(r['item_id'] for r in observed)
                if name == 'mixed_null_and_nonnull_gaps_with_tied_product_units':
                    assert len(cohort) == 2
                    assert observed[0]['mean_positive_gap_weeks'] is None
                    assert Decimal(str(observed[1]['mean_positive_gap_weeks'])) == 11
            for key, sql in SNAPSHOTS.items():
                run = execute(sql)
                assert run.returncode == 0 and parse(run.stdout) == before[key], (name, key, 'input changed')
        assert not Path(folder).exists()
        cases.append(dict(case=name, passed=True, rejected=reject, returned_rows=result_count,
                          all_five_input_tables_unchanged=True))
        if len(cases) == 1:
            print(json.dumps({'first_fixture_passed': name}), flush=True)

    tiny('mixed_null_and_nonnull_gaps_with_tied_product_units')
    tiny('equal_units_use_item_tiebreak_despite_reverse_source_rows',
         vectors=[[120] + [0] * 11] * 12, bridges=[0] * 12, reverse_input=True)
    tiny('valid_empty_positive_sources_return_one_null_sentinel', vectors=[[10] * 12] * 2, bridges=[0, 0])
    tiny('valid_empty_all_zero_sources_return_one_null_sentinel', vectors=[[0] * 12] * 2, bridges=[0, 0])
    tiny('z_above_exact_boundary_kept_when_display_cv_is_one',
         vectors=[[0] * 6 + [2000000] * 5 + [2000001]], bridges=[0])
    tiny('accepted_metric_float_tolerance_preserves_labels',
         metric_perturbation="UPDATE mart.m5_product_variability_12w SET cv_weekly=cv_weekly+1e-10 WHERE item_id='P001';")
    target = 'mart.m5_product_abc_xyz'
    tiny('invalid_empty_positive_source_cannot_bypass_guard', vectors=[[10] * 12] * 2, bridges=[0, 0],
         mutation=f"UPDATE {target} SET cv_weekly=cv_weekly+1e-10 WHERE item_id='P001';", reject=True)
    for name, mutation in [
        ('empty_combined_snapshot_is_invalid_not_empty_cohort', f'DELETE FROM {target};'),
        ('duplicate_combined_product', f"INSERT INTO {target} SELECT * FROM {target} WHERE item_id='P001';"),
        ('removed_whole_cohort_is_rejected', f"DELETE FROM {target} WHERE abc_class='A' AND xyz_class='Z';"),
        ('incorrect_cohort_labels_are_rejected', f"UPDATE {target} SET xyz_class='X' WHERE abc_class='A' AND xyz_class='Z';"),
        ('combined_copied_float_drift', f"UPDATE {target} SET cv_weekly=cv_weekly+1e-10 WHERE item_id='P001';"),
        ('combined_wrong_window', f"UPDATE {target} SET abc_window_start=abc_window_start+1 WHERE item_id='P001';"),
        ('combined_wrong_schema', f'ALTER TABLE {target} ALTER cv_weekly TYPE DECIMAL(30,12);'),
        ('incorrect_abc_source_rank', "UPDATE mart.m5_product_abc_90d SET sku_rank=sku_rank+1 WHERE item_id='P001';"),
        ('incorrect_xyz_source_label', "UPDATE mart.m5_product_xyz_12w SET xyz_class='X' WHERE item_id='P001';"),
        ('missing_source_week', "DELETE FROM mart.m5_product_weekly_12w WHERE item_id='P001' AND wm_yr_wk=11601;"),
        ('nonfinite_source_metric', "UPDATE mart.m5_product_variability_12w SET stddev_weekly_units='NaN'::DOUBLE WHERE item_id='P001';"),
    ]:
        tiny(name, mutation=mutation, reject=True)
    assert len(cases) == 18
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
    accepted_path = 'data/abc_xyz_contribution_learner_acceptance.json'
    accepted_bytes = (root / accepted_path).read_bytes()
    accepted = json.loads(accepted_bytes.decode('utf-8'))
    assert accepted['rows_with_pass_status'] == 17 and accepted['both_windows_visible_in_screenshot']
    accepted_az = next(r for r in accepted['results'] if r['segment'] == 'A × Z')
    timings = {}
    with tempfile.TemporaryDirectory(prefix='az-drilldown-', dir=tmp_root) as folder:
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
        for key in ('21', '23', '24', '25', '27'):
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
        assert_exact_rows(before['abc'], abc, 'original wide ABC fields')
        assert_exact_rows(before['weekly'], source_weekly_rows(source, 10), 'original wide weekly values')
        assert_exact_rows(upstream['21'], baseline_summary(abc), 'original wide ABC report')
        assert_exact_rows(upstream['23'], source_weekly_report(source_weekly_rows(source, 10)), 'original wide weekly report')
        assert_exact_rows(upstream['24'], reference_report([{k: v for k, v in r.items() if k != 'xyz_class'} for r in xyz]), 'original wide metrics')
        assert_xyz(before['xyz'], xyz, before['metrics'])
        assert_exact_rows(upstream['25'], xyz_report(xyz), 'original wide XYZ report')
        float_errors = assert_combined(before['combined'], source, before)
        assert_exact_rows(upstream['27'], matrix(expected), 'original wide combined matrix')
        _, contribution, _ = contribution_reference(expected)
        assert_exact_rows(accepted['results'], contribution, 'learner accepted contribution report')
        input_hashes = {key: fingerprint(rows) for key, rows in before.items()}
        actual = execute(query, 'drilldown_query_seconds')
        cohort, expected_detail = assert_detail(actual, expected, 'full-source A x Z detail')
        assert len(cohort) == len(actual) == int(accepted_az['sku_count']) == 15
        aggregates = aggregate_detail(actual)
        assert aggregates['units_90d'] == int(accepted_az['units_90d'])
        assert aggregates['units_84d'] == int(accepted_az['units_84d'])
        expected_detail_hash = row_hash(canonical_detail(expected_detail))
        assert aggregates['ordered_detail_sha256'] == expected_detail_hash
        after = {key: execute(sql) for key, sql in SNAPSHOTS.items()}
        for key in SNAPSHOTS:
            assert before[key] == after[key] and input_hashes[key] == fingerprint(after[key]), (key, 'input changed')
        database_bytes = database.stat().st_size
    assert not Path(folder).exists()
    assert all(sha256(path) == hashes[path.name] for path in sources)
    assert all(sha256(root / path) == value for path, value in historical.items())
    assert all((root / script_paths[key]).read_bytes() == value for key, value in script_bytes.items())
    assert all(sha256(root / path) == value for path, value in helper_hashes.items())
    report = dict(
        checked_at_utc=datetime.now(timezone.utc).isoformat(), executor='assistant',
        engine=subprocess.check_output([args.duckdb, '-version'], text=True).strip(),
        baseline_database='Private temporary on-disk DuckDB under repository tmp; removed after verification.',
        temporary_baseline_removed=True, temporary_database_bytes_after_close=database_bytes,
        settings={'threads': 2, 'memory_limit': '2GB'}, script=script_paths['29'],
        script_sha256=hashlib.sha256(script_bytes['29']).hexdigest(),
        prerequisite_script_sha256={script_paths[key]: hashlib.sha256(script_bytes[key]).hexdigest() for key in ('21', '23', '24', '25', '27')},
        reference_helper_sha256=helper_hashes, source_sha256=hashes, source_hashes_unchanged=True,
        historical_preflight_sha256=historical, historical_preflights_unchanged=True,
        preflight_strategy='Original sales/calendar CSVs feed a private 90-day daily table and actual SQL21,23,24,25,27, followed by read-only SQL29. This is not a full-history rebuild and never opens the learner database.',
        independent_reference='Original wide 90-day arrays and twelve seven-day vectors independently define ABC using prefix endpoints and XYZ using exact centered Fraction variance. Seventy-digit Decimal metrics and explicit adjacent positive-week gaps provide all product-level expected values; Decimal half-up rounding defines the six-place display.',
        analysis_windows={'abc': {'start_date': '2016-01-26', 'end_date': '2016-04-24', 'days': 90},
                          'xyz': {'start_date': '2016-01-30', 'end_date': '2016-04-22', 'days': 84, 'weeks': 12}},
        cohort_policy='All products labelled A and Z by the accepted exact baselines; no Top-N or rounded-CV filter. Sort units_90d descending then item_id ascending. A valid empty cohort returns one EMPTY row with every product field NULL; invalid empty inputs still raise an error.',
        timings=timings, timing_scope='DuckDB CLI process timings; excludes Python comparisons and file hashing.',
        combined_product_rows_compared=3049, combined_columns_compared=22, combined_field_mismatches=0,
        combined_float_error_summary=float_errors, cohort_rows_compared=len(cohort), result_columns=10,
        cohort_field_mismatches=0, sorting_verified=True, result_rows=len(actual), rows_with_pass_status=len(actual),
        cohort_aggregates=aggregates, independent_reference_detail_sha256=expected_detail_hash,
        fingerprint_method='SHA256 of UTF-8 compact JSON with sorted object keys, ensure_ascii=False; list order is SQL units_90d DESC,item_id ASC. Detail integers are JSON integers; CV/gap are six-decimal strings or NULL. Membership fingerprint hashes only the ordered item_id string list. SHA256 is 32 bytes, displayed as 64 hex characters.',
        real_sku_rows_published=False, real_sku_identifiers_published=False,
        accepted_contribution_matched=True, accepted_baseline_evidence=accepted_path,
        accepted_baseline_evidence_sha256=hashlib.sha256(accepted_bytes).hexdigest(),
        accepted_cohort_aggregate={'sku_count': int(accepted_az['sku_count']),
                                   'units_90d': int(accepted_az['units_90d']), 'units_84d': int(accepted_az['units_84d'])},
        all_input_tables_unchanged=True, input_rows_sha256_before=input_hashes,
        input_rows_sha256_after={key: fingerprint(rows) for key, rows in after.items()},
        fixture_cases_passed=len(cases), fixture_cases=cases,
        scope='Assistant preflight only; learner local product drilldown execution pending. Public evidence contains cohort aggregates and one-way fingerprints only, never actual SKU rows or identifiers. High recorded-sales variability does not establish unmet demand, inventory shortages or optimal replenishment.')
    serialized = json.dumps(report, indent=2, default=str, ensure_ascii=False) + '\n'
    assert all(row['item_id'] not in serialized for row in source), 'Public report contains a real product identifier'
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(serialized, encoding='utf-8', newline='\n')
    print(json.dumps({'fixture_cases_passed': len(cases), 'cohort_aggregates': aggregates,
                      'timings': timings, 'public_identifiers': False}, default=str), flush=True)


if __name__ == '__main__':
    main()
