"""Verify the automatically selected A x Z weekly trajectory privately; publish only aggregates."""
import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
import time
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

sys.dont_write_bytecode = True
from preflight_product_abc_xyz import reference, matrix, assert_combined
from preflight_abc_xyz_contribution import SNAPSHOTS
from preflight_az_product_drilldown import (
    detail_reference, canonical_detail, assert_detail, row_hash, rounded,
)
from preflight_abc_threshold_sensitivity import baseline_summary
from preflight_product_variability import (
    assert_exact_rows, fingerprint, parse, quote, reference_report, sha256,
    source_weekly_rows, source_weekly_report,
)
from preflight_product_xyz import assert_xyz, xyz_report

COLUMNS = ['item_id', 'week_start', 'week_end', 'units', 'unit_share_84d_pct',
           'cumulative_unit_share_84d_pct', 'zero_sales_week', 'abc_window', 'xyz_window', 'check_status']


def pct(part, whole):
    return (Decimal(part) * 100 / Decimal(whole)).quantize(Decimal('.0001'), rounding=ROUND_HALF_UP)


def trajectory_reference(source, combined):
    cohort, _ = detail_reference(combined)
    selected = cohort[0] if cohort else None
    result = []
    if selected is None:
        result.append(dict.fromkeys(COLUMNS[:7]))
        result[0].update(abc_window='2016-01-26..2016-04-24', xyz_window='2016-01-30..2016-04-22', check_status='EMPTY')
    else:
        product = next(row for row in source if row['item_id'] == selected['item_id'])
        vector = product['weeks']
        assert sum(vector) == selected['units_84d'] > 0
        cumulative = 0
        for i, units in enumerate(vector):
            cumulative += units
            start = date(2016, 1, 30) + timedelta(weeks=i)
            result.append(dict(item_id=selected['item_id'], week_start=start.isoformat(),
                               week_end=(start + timedelta(days=6)).isoformat(), units=units,
                               unit_share_84d_pct=pct(units, sum(vector)),
                               cumulative_unit_share_84d_pct=pct(cumulative, sum(vector)),
                               zero_sales_week=(units == 0), abc_window='2016-01-26..2016-04-24',
                               xyz_window='2016-01-30..2016-04-22', check_status='PASS'))
    return selected, result


def canonical_trajectory(rows):
    result = []
    for row in rows:
        assert list(row) == COLUMNS, 'Unexpected output column names/order'
        assert row['zero_sales_week'] is None or isinstance(row['zero_sales_week'], bool)
        normalized = dict(row)
        normalized['units'] = None if row['units'] is None else int(row['units'])
        for key in ('unit_share_84d_pct', 'cumulative_unit_share_84d_pct'):
            normalized[key] = None if row[key] is None else format(Decimal(str(row[key])).quantize(Decimal('.0001')), '.4f')
        result.append(normalized)
    return result


def assert_trajectory(actual, source, combined, context):
    selected, expected = trajectory_reference(source, combined)
    assert canonical_trajectory(actual) == canonical_trajectory(expected), context
    if selected is None:
        assert len(actual) == 1 and actual[0]['check_status'] == 'EMPTY'
        assert all(actual[0][key] is None for key in COLUMNS[:7])
    else:
        assert len(actual) == 12
        assert len({r['item_id'] for r in actual}) == 1
        assert len({r['week_start'] for r in actual}) == 12
        assert [r['week_start'] for r in actual] == sorted(r['week_start'] for r in actual)
        assert sum(int(r['units']) for r in actual) == int(selected['units_84d'])
        assert sum(r['zero_sales_week'] for r in actual) == selected['zero_sales_weeks']
        cumulative = [Decimal(str(r['cumulative_unit_share_84d_pct'])) for r in actual]
        assert cumulative == sorted(cumulative) and cumulative[-1] == 100
    return selected, expected


def trajectory_aggregates(actual, selected):
    values = [int(row['units']) for row in actual]
    total = sum(values)
    descending = sorted(values, reverse=True)
    return dict(
        selected_units_90d=int(selected['units_90d']), selected_units_84d=int(selected['units_84d']),
        selected_excluded_six_day_units=int(selected['excluded_six_day_units']),
        selected_cv_weekly_display=rounded(selected['cv_weekly']),
        week_count=len(values), positive_weeks=sum(v > 0 for v in values), zero_sales_weeks=sum(v == 0 for v in values),
        units_total=total, weekly_units_min=min(values), weekly_units_max=max(values),
        mean_weekly_units=Decimal(total) / len(values),
        peak_week_share_pct=pct(max(values), total), peak_week_count=sum(v == max(values) for v in values),
        top_three_weeks_units=sum(descending[:3]), top_three_weeks_share_pct=pct(sum(descending[:3]), total),
        first_six_weeks_units=sum(values[:6]), first_six_weeks_share_pct=pct(sum(values[:6]), total),
        last_six_weeks_units=sum(values[6:]), last_six_weeks_share_pct=pct(sum(values[6:]), total),
        displayed_weekly_share_sum=sum(Decimal(str(r['unit_share_84d_pct'])) for r in actual),
        final_cumulative_share_pct=Decimal(str(actual[-1]['cumulative_unit_share_84d_pct'])),
        cumulative_shares_monotone=True,
        selected_product_sha256=row_hash([selected['item_id']]),
        ordered_trajectory_sha256=row_hash(canonical_trajectory(actual)),
        ordered_weekly_units_sha256=row_hash(values))


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
        '30': 'sql/30_az_leading_product_weekly.sql',
    }
    script_bytes = {key: (root / path).read_bytes() for key, path in script_paths.items()}
    scripts = {}
    for key in ('21', '23', '24', '25', '27'):
        build, audit = script_bytes[key].decode('utf-8').split('-- VALIDATION:', 1)
        scripts[key] = (build, '-- VALIDATION:' + audit)
    query = script_bytes['30'].decode('utf-8')
    helper_paths = [
        'validation/preflight_product_abc_xyz.py', 'validation/preflight_abc_xyz_contribution.py',
        'validation/preflight_az_product_drilldown.py', 'validation/preflight_abc_threshold_sensitivity.py',
        'validation/preflight_product_variability.py', 'validation/preflight_product_xyz.py',
        'validation/preflight_xyz_threshold_sensitivity.py',
    ]
    helper_hashes = {path: sha256(root / path) for path in helper_paths}
    historical = {p.relative_to(root).as_posix(): sha256(p) for p in (root / 'data').glob('*_preflight.json')
                  if p.name != 'az_leading_product_weekly_preflight.json'}
    mixed = [[0, 10, 20, 0, 0, 30, 0, 0, 0, 0, 0, 160], [120] + [0] * 11, [10] * 12, [0] * 12]
    mixed_bridge = [20, 0, 0, 0]
    cases = []

    def tiny(name, vectors=None, bridges=None, mutation='', reject=False, reverse_input=False):
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
        with tempfile.TemporaryDirectory(prefix='az-weekly-fixture-', dir=tmp_root) as folder:
            assert Path(folder).resolve().is_relative_to(tmp_root.resolve())
            database = Path(folder) / 'fixture.duckdb'
            settings = "SET threads=2; SET memory_limit='2GB';\n"

            def execute(sql):
                return subprocess.run([args.duckdb, str(database), '-bail', '-json'], input=settings + sql,
                                      text=True, encoding='utf-8', capture_output=True)

            run = execute(setup + scripts['24'][0].replace(old, new) + scripts['25'][0].replace(old, new)
                          + scripts['27'][0].replace(old, new) + mutation)
            assert run.returncode == 0, (name, run.stderr)
            before = {}
            for key, sql in SNAPSHOTS.items():
                run = execute(sql)
                assert run.returncode == 0, (name, run.stderr)
                before[key] = parse(run.stdout)
            run = execute(query.replace(old, new))
            if reject:
                assert run.returncode != 0 and ('A Z weekly trajectory blocked' in run.stderr or 'XYZ blocked' in run.stderr), (name, run.stderr)
            else:
                assert run.returncode == 0, (name, run.stderr)
                assert_combined(before['combined'], source, before)
                observed = parse(run.stdout)
                selected, _ = assert_trajectory(observed, source, expected, name)
                result_count = len(observed)
                if name in ('select_by_90d_not_84d_units', 'tied_90d_selects_ascending_item_despite_reversed_source'):
                    assert selected['item_id'] == 'P001' and selected['units_84d'] < source[1]['units_90d']
                if name == 'halfway_rounding_and_integer_cumulative_not_rounded_sum':
                    assert Decimal(str(observed[0]['unit_share_84d_pct'])) == Decimal('.7813')
                    displayed_sum = sum(Decimal(str(r['unit_share_84d_pct'])) for r in observed)
                    assert displayed_sum == Decimal('100.0006')
                    assert sum(Decimal(str(r['unit_share_84d_pct'])) for r in observed[:3]) == Decimal('2.3439')
                    assert Decimal(str(observed[2]['cumulative_unit_share_84d_pct'])) == Decimal('2.3438')
                if name == 'exact_z_boundary_survives_display_rounding':
                    assert selected['cv_weekly'] > 1 and rounded(selected['cv_weekly']) == 1
            for key, sql in SNAPSHOTS.items():
                run = execute(sql)
                assert run.returncode == 0 and parse(run.stdout) == before[key], (name, key, 'input changed')
        assert not Path(folder).exists()
        cases.append(dict(case=name, passed=True, rejected=reject, returned_rows=result_count,
                          all_five_input_tables_unchanged=True))
        if len(cases) == 1:
            print(json.dumps({'first_fixture_passed': name}), flush=True)

    tiny('complete_zero_weeks_and_time_order_from_reversed_source', reverse_input=True)
    tiny('select_by_90d_not_84d_units', vectors=[[1] * 11 + [89], [200] + [0] * 11], bridges=[200, 0])
    tiny('tied_90d_selects_ascending_item_despite_reversed_source',
         vectors=[[120] + [0] * 11, [0] * 11 + [200]], bridges=[80, 0], reverse_input=True)
    tiny('halfway_rounding_and_integer_cumulative_not_rounded_sum', vectors=[[1] * 11 + [117]], bridges=[0])
    tiny('valid_empty_positive_sources_return_null_week_fields', vectors=[[10] * 12] * 2, bridges=[0, 0])
    tiny('valid_empty_zero_sources_return_null_week_fields', vectors=[[0] * 12] * 2, bridges=[0, 0])
    tiny('exact_z_boundary_survives_display_rounding', vectors=[[0] * 6 + [2000000] * 5 + [2000001]], bridges=[0])
    target = 'mart.m5_product_abc_xyz'
    tiny('invalid_empty_source_still_rejected', vectors=[[10] * 12] * 2, bridges=[0, 0],
         mutation=f"UPDATE {target} SET cv_weekly=cv_weekly+1e-10 WHERE item_id='P001';", reject=True)
    for name, mutation in [
        ('empty_combined_source_not_valid_empty_cohort', f'DELETE FROM {target};'),
        ('duplicate_combined_key', f"INSERT INTO {target} SELECT * FROM {target} WHERE item_id='P001';"),
        ('selected_combined_label_drift', f"UPDATE {target} SET xyz_class='X' WHERE item_id='P001';"),
        ('combined_copied_float_drift', f"UPDATE {target} SET cv_weekly=cv_weekly+1e-10 WHERE item_id='P001';"),
        ('wrong_weekly_schema', 'ALTER TABLE mart.m5_product_weekly_12w ALTER units TYPE DOUBLE;'),
        ('missing_selected_week', "DELETE FROM mart.m5_product_weekly_12w WHERE item_id='P001' AND wm_yr_wk=11601;"),
        ('duplicate_and_missing_selected_week_preserves_row_count', "UPDATE mart.m5_product_weekly_12w SET wm_yr_wk=11602,week_start=DATE '2016-02-06',week_end=DATE '2016-02-12' WHERE item_id='P001' AND wm_yr_wk=11601;"),
        ('wrong_week_date_mapping', "UPDATE mart.m5_product_weekly_12w SET week_end=week_end-1 WHERE item_id='P001' AND wm_yr_wk=11601;"),
        ('incorrect_abc_source_rank', "UPDATE mart.m5_product_abc_90d SET sku_rank=sku_rank+1 WHERE item_id='P001';"),
        ('incorrect_xyz_source_label', "UPDATE mart.m5_product_xyz_12w SET xyz_class='X' WHERE item_id='P001';"),
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
    accepted_path = 'data/az_product_drilldown_learner_acceptance.json'
    accepted_bytes = (root / accepted_path).read_bytes()
    accepted = json.loads(accepted_bytes.decode('utf-8'))
    assert accepted['rows_with_pass_status'] == 15 and accepted['both_windows_visible_in_screenshot']
    timings = {}
    with tempfile.TemporaryDirectory(prefix='az-leading-weekly-', dir=tmp_root) as folder:
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
        input_hashes = {key: fingerprint(rows) for key, rows in before.items()}
        detail = execute(script_bytes['29'].decode('utf-8'), 'accepted_drilldown_query_seconds')
        cohort, expected_detail = assert_detail(detail, expected, 'reconstructed accepted A x Z cohort')
        detail_hash = row_hash(canonical_detail(detail))
        membership_hash = row_hash([r['item_id'] for r in detail])
        assert detail_hash == row_hash(canonical_detail(expected_detail)) == accepted['cohort_aggregates']['ordered_detail_sha256']
        assert membership_hash == accepted['cohort_aggregates']['ordered_membership_sha256']
        actual = execute(query, 'weekly_trajectory_query_seconds')
        selected, expected_rows = assert_trajectory(actual, source, expected, 'full-source selected weekly trajectory')
        assert selected is not None and selected['item_id'] == detail[0]['item_id']
        aggregates = trajectory_aggregates(actual, selected)
        expected_trajectory_hash = row_hash(canonical_trajectory(expected_rows))
        assert aggregates['ordered_trajectory_sha256'] == expected_trajectory_hash
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
        settings={'threads': 2, 'memory_limit': '2GB'}, script=script_paths['30'],
        script_sha256=hashlib.sha256(script_bytes['30']).hexdigest(),
        prerequisite_script_sha256={script_paths[key]: hashlib.sha256(script_bytes[key]).hexdigest() for key in ('21', '23', '24', '25', '27', '29')},
        reference_helper_sha256=helper_hashes, source_sha256=hashes, source_hashes_unchanged=True,
        historical_preflight_sha256=historical, historical_preflights_unchanged=True,
        preflight_strategy='Original sales/calendar CSVs feed a private 90-day daily table and actual SQL21,23,24,25,27, followed by read-only SQL29 and30. This is not a full-history rebuild and never opens the learner database.',
        independent_reference='Original wide 90-day totals independently define ABC prefix labels and twelve weekly vectors define exact centered-Fraction XYZ labels. Select the first independently sorted A x Z product by 90-day units descending then item_id ascending. Python integer cumulative sums and Decimal half-up four-place percentages provide every trajectory field.',
        analysis_windows={'abc': {'start_date': '2016-01-26', 'end_date': '2016-04-24', 'days': 90},
                          'xyz': {'start_date': '2016-01-30', 'end_date': '2016-04-22', 'days': 84, 'weeks': 12}},
        selection_policy='Highest 90-day unit total among the accepted A x Z cohort, then ascending item_id for a tie. No hard-coded product identifier, peak-based selection or relabelling. A valid empty cohort yields one EMPTY row with all seven item/week fields NULL.',
        percentage_policy='Every weekly/cumulative share uses the selected product 84-day total. Cumulate integer weekly units before division and round only for display; rounded weekly shares need not sum exactly to 100.',
        timings=timings, timing_scope='DuckDB CLI process timings; excludes Python comparisons and file hashing.',
        combined_product_rows_compared=3049, combined_columns_compared=22, combined_field_mismatches=0,
        combined_float_error_summary=float_errors, reconstructed_cohort_rows=len(cohort),
        reconstructed_cohort_detail_sha256=detail_hash, reconstructed_cohort_membership_sha256=membership_hash,
        accepted_cohort_fingerprints_matched=True, accepted_baseline_evidence=accepted_path,
        accepted_baseline_evidence_sha256=hashlib.sha256(accepted_bytes).hexdigest(),
        selected_product_matches_independent_reference=True,
        trajectory_rows_compared=len(actual), result_columns=len(COLUMNS), output_columns=COLUMNS, trajectory_field_mismatches=0,
        result_rows=len(actual), rows_with_pass_status=len(actual), column_names_and_order_verified=True,
        time_order_verified=True, zero_weeks_retained=True, trajectory_aggregates=aggregates,
        independent_reference_trajectory_sha256=expected_trajectory_hash,
        fingerprint_method='SHA256 of UTF-8 compact JSON with sorted object keys and ensure_ascii=False. Selected-product hash encodes a one-element item_id string list. Trajectory hash encodes chronological rows with units as JSON integers, shares as four-decimal strings or NULL, and zero flags as JSON booleans or NULL. Weekly-units hash encodes the chronological integer vector. Only these digests are saved.',
        real_sku_identifiers_published=False, weekly_detail_rows_published=False,
        all_input_tables_unchanged=True, input_rows_sha256_before=input_hashes,
        input_rows_sha256_after={key: fingerprint(rows) for key, rows in after.items()},
        fixture_cases_passed=len(cases), fixture_cases=cases,
        scope='Assistant preflight only; learner local weekly trajectory execution pending. Public evidence contains aggregates and one-way fingerprints, never the selected product identifier or twelve weekly rows. Peak/three-week/half-window figures describe this observed series; they establish no demand cause, stockout, forecast error or replenishment target.')
    serialized = json.dumps(report, indent=2, default=str, ensure_ascii=False) + '\n'
    assert all(row['item_id'] not in serialized for row in source), 'Public report contains a real product identifier'
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(serialized, encoding='utf-8', newline='\n')
    print(json.dumps({'fixture_cases_passed': len(cases), 'trajectory_aggregates': aggregates,
                      'timings': timings, 'public_identifiers': False}, default=str), flush=True)


if __name__ == '__main__':
    main()
