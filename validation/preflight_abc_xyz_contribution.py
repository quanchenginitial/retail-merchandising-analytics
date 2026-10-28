"""Verify read-only ABC x XYZ unit contribution from original wide CSVs in private databases."""
import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

sys.dont_write_bytecode = True
from preflight_product_abc_xyz import (
    SNAPSHOTS as BASE_SNAPSHOTS, COMBINED_SNAPSHOT, reference, matrix, assert_combined,
)
from preflight_abc_threshold_sensitivity import baseline_summary
from preflight_product_variability import (
    assert_exact_rows, fingerprint, parse, quote, reference_report, sha256,
    source_weekly_rows, source_weekly_report,
)
from preflight_product_xyz import assert_xyz, xyz_report

SNAPSHOTS = dict(BASE_SNAPSHOTS, combined=COMBINED_SNAPSHOT)
CELL_SUFFIX = 'SELECT abc_class,xyz_class,sku_count,units_90d,units_84d FROM cells ORDER BY display_order;'
MEMBER_SUFFIX = 'SELECT item_id,abc_class,xyz_class,units_90d,units_84d FROM combined_actual ORDER BY item_id;'


def pct(part, whole):
    if whole == 0:
        return None
    return (Decimal(part) * 100 / Decimal(whole)).quantize(Decimal('.0001'), rounding=ROUND_HALF_UP)


def contribution_reference(rows):
    """Group independent source-derived product labels and integer totals, then round display shares."""
    cells = []
    for abc in ('A', 'B', 'C', 'ZERO_SALES'):
        for xyz in ('X', 'Y', 'Z', 'ZERO_SALES'):
            group = [r for r in rows if r['abc_class'] == abc and r['xyz_class'] == xyz]
            cells.append(dict(abc_class=abc, xyz_class=xyz, sku_count=len(group),
                              units_90d=sum(int(r['units_90d']) for r in group),
                              units_84d=sum(int(r['units_84d']) for r in group)))
    totals = dict(sku_count=len(rows), units_90d=sum(int(r['units_90d']) for r in rows),
                  units_84d=sum(int(r['units_84d']) for r in rows))
    for field in totals:
        assert sum(c[field] for c in cells) == totals[field]
    for axis, labels in [('abc_class', ('A', 'B', 'C', 'ZERO_SALES')),
                         ('xyz_class', ('X', 'Y', 'Z', 'ZERO_SALES'))]:
        for label in labels:
            product_group = [r for r in rows if r[axis] == label]
            cell_group = [c for c in cells if c[axis] == label]
            assert sum(c['sku_count'] for c in cell_group) == len(product_group)
            for units in ('units_90d', 'units_84d'):
                assert sum(c[units] for c in cell_group) == sum(int(r[units]) for r in product_group)
    result = []
    for cell in cells + [totals]:
        result.append(dict(
            segment=cell['abc_class'] + ' × ' + cell['xyz_class'] if 'abc_class' in cell else 'TOTAL',
            sku_count=cell['sku_count'], sku_share_pct=pct(cell['sku_count'], totals['sku_count']),
            units_90d=cell['units_90d'], unit_share_90d_pct=pct(cell['units_90d'], totals['units_90d']),
            units_84d=cell['units_84d'], unit_share_84d_pct=pct(cell['units_84d'], totals['units_84d']),
            abc_window='2016-01-26..2016-04-24', xyz_window='2016-01-30..2016-04-22', check_status='PASS'))
    members = [{key: r[key] for key in ('item_id', 'abc_class', 'xyz_class', 'units_90d', 'units_84d')}
               for r in sorted(rows, key=lambda r: r['item_id'])]
    return cells, result, members


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
        '27': 'sql/27_build_product_abc_xyz.sql', '28': 'sql/28_abc_xyz_contribution.sql',
    }
    script_bytes = {key: (root / path).read_bytes() for key, path in script_paths.items()}
    scripts = {}
    for key in ('21', '23', '24', '25', '27'):
        build, audit = script_bytes[key].decode('utf-8').split('-- VALIDATION:', 1)
        scripts[key] = (build, '-- VALIDATION:' + audit)
    query = script_bytes['28'].decode('utf-8')
    prefix = query.split('-- REPORT:', 1)[0]
    helper_paths = ['validation/preflight_product_abc_xyz.py', 'validation/preflight_abc_threshold_sensitivity.py',
                    'validation/preflight_product_variability.py', 'validation/preflight_product_xyz.py',
                    'validation/preflight_xyz_threshold_sensitivity.py']
    helper_hashes = {path: sha256(root / path) for path in helper_paths}
    historical = {p.relative_to(root).as_posix(): sha256(p) for p in (root / 'data').glob('*_preflight.json')
                  if p.name != 'abc_xyz_contribution_preflight.json'}
    mixed = [[10] * 12, [0] * 6 + [20] * 6, [120] + [0] * 11, [0] * 12,
             [0] * 12, [1] * 12, [0] * 6 + [4] * 6, [0] * 12]
    mixed_bridge = [0, 0, 0, 500, 0, 0, 0, 1]
    cases = []

    def tiny(name, vectors=None, bridges=None, mutation='', reject=False, metric_perturbation=''):
        vectors = mixed if vectors is None else vectors
        bridges = mixed_bridge if bridges is None else bridges
        assert len(vectors) == len(bridges)
        source = [dict(item_id=f'P{i:03d}', dept_id='FOODS_1', cat_id='FOODS', weeks=vector,
                       units_90d=sum(vector) + bridge, excluded_six_day_units=bridge)
                  for i, (vector, bridge) in enumerate(zip(vectors, bridges), 1)]
        abc, _, expected = reference(source)
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
        with tempfile.TemporaryDirectory(prefix='contribution-fixture-', dir=tmp_root) as folder:
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
                assert run.returncode != 0 and ('ABC XYZ contribution blocked' in run.stderr or 'XYZ blocked' in run.stderr), (name, run.stderr)
            else:
                assert run.returncode == 0, (name, run.stderr)
                assert_combined(before['combined'], source, before)
                cells, reports, members = contribution_reference(expected)
                observed = parse(run.stdout)
                assert_exact_rows(observed, reports, name + ' 17 display rows')
                for suffix, expected_rows, context in [(CELL_SUFFIX, cells, '16 integer cells'),
                                                       (MEMBER_SUFFIX, members, 'all product memberships')]:
                    run = execute(prefix.replace(old, new) + suffix)
                    assert run.returncode == 0, (name, run.stderr)
                    assert_exact_rows(parse(run.stdout), expected_rows, name + ' ' + context)
                if name == 'all_zero_both_unit_share_columns_are_null':
                    assert all(r['unit_share_90d_pct'] is None and r['unit_share_84d_pct'] is None for r in observed)
                if name == 'positive_90d_and_all_zero_84d_use_separate_denominators':
                    assert all(r['unit_share_90d_pct'] is not None and r['unit_share_84d_pct'] is None for r in observed)
            for key, sql in SNAPSHOTS.items():
                run = execute(sql)
                assert run.returncode == 0 and parse(run.stdout) == before[key], (name, key, 'input changed')
        assert not Path(folder).exists()
        cases.append(dict(case=name, passed=True, rejected=reject, all_five_input_tables_unchanged=True))
        if len(cases) == 1:
            print(json.dumps({'first_fixture_passed': name}), flush=True)

    tiny('mixed_labels_complete_cells_and_independent_denominators')
    tiny('all_zero_both_unit_share_columns_are_null', vectors=[[0] * 12] * 2, bridges=[0, 0])
    tiny('positive_90d_and_all_zero_84d_use_separate_denominators', vectors=[[0] * 12] * 3, bridges=[100, 25, 0])
    tiny('constant_positive_empty_classes_are_retained', vectors=[[10] * 12] * 2, bridges=[0, 0])
    tiny('accepted_metric_float_tolerance_is_preserved',
         metric_perturbation="UPDATE mart.m5_product_variability_12w SET cv_weekly=cv_weekly+1e-10 WHERE item_id='P002';")
    target = 'mart.m5_product_abc_xyz'
    for name, mutation in [
        ('empty_combined_snapshot', f'DELETE FROM {target};'),
        ('missing_combined_product', f"DELETE FROM {target} WHERE item_id='P005';"),
        ('duplicate_combined_product', f"INSERT INTO {target} SELECT * FROM {target} WHERE item_id='P001';"),
        ('combined_copied_float_drift', f"UPDATE {target} SET cv_weekly=cv_weekly+1e-10 WHERE item_id='P002';"),
        ('combined_six_day_bridge_drift', f"UPDATE {target} SET excluded_six_day_units=excluded_six_day_units+1 WHERE item_id='P001';"),
        ('combined_wrong_window', f"UPDATE {target} SET xyz_window_start=xyz_window_start+1 WHERE item_id='P001';"),
        ('swapped_product_labels_preserve_count_and_unit_margins', f"UPDATE {target} SET xyz_class=CASE item_id WHEN 'P001' THEN 'Y' ELSE 'X' END WHERE item_id IN ('P001','P002');"),
        ('combined_wrong_schema', f'ALTER TABLE {target} ALTER cv_weekly TYPE DECIMAL(30,12);'),
        ('duplicate_abc_source_key', "INSERT INTO mart.m5_product_abc_90d SELECT * FROM mart.m5_product_abc_90d WHERE item_id='P001';"),
        ('incorrect_abc_source_class', "UPDATE mart.m5_product_abc_90d SET abc_class='C' WHERE item_id='P001';"),
        ('incorrect_xyz_source_class', "UPDATE mart.m5_product_xyz_12w SET xyz_class='Z' WHERE item_id='P001';"),
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
    accepted_path = 'data/product_abc_xyz_learner_acceptance.json'
    accepted_bytes = (root / accepted_path).read_bytes()
    accepted = json.loads(accepted_bytes.decode('utf-8'))
    assert accepted['rows_with_pass_status'] == 5 and accepted['both_windows_visible_in_screenshot']
    timings = {}
    with tempfile.TemporaryDirectory(prefix='abc-xyz-contribution-', dir=tmp_root) as folder:
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
        assert_exact_rows(before['abc'], abc, 'original wide 90-day ABC fields')
        assert_exact_rows(before['weekly'], source_weekly_rows(source, 10), 'original wide weekly values')
        assert_exact_rows(upstream['21'], baseline_summary(abc), 'original wide ABC report')
        assert_exact_rows(upstream['23'], source_weekly_report(source_weekly_rows(source, 10)), 'original wide weekly report')
        assert_exact_rows(upstream['24'], reference_report([{k: v for k, v in r.items() if k != 'xyz_class'} for r in xyz]), 'original wide metric report')
        assert_xyz(before['xyz'], xyz, before['metrics'])
        assert_exact_rows(upstream['25'], xyz_report(xyz), 'original wide XYZ report')
        float_errors = assert_combined(before['combined'], source, before)
        assert_exact_rows(upstream['27'], matrix(expected), 'original wide combined matrix')
        assert_exact_rows(upstream['27'], accepted['results'], 'learner accepted combined matrix')
        expected_cells, expected_report, expected_members = contribution_reference(expected)
        input_hashes = {key: fingerprint(rows) for key, rows in before.items()}
        results = execute(query, 'contribution_query_seconds')
        assert_exact_rows(results, expected_report, '17 contribution display rows')
        cells = execute(prefix + CELL_SUFFIX, 'integer_cells_query_seconds')
        assert_exact_rows(cells, expected_cells, '16 integer cells')
        members = execute(prefix + MEMBER_SUFFIX, 'product_membership_query_seconds')
        assert_exact_rows(members, expected_members, '3049 product memberships and unit totals')
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
        settings={'threads': 2, 'memory_limit': '2GB'}, script=script_paths['28'],
        script_sha256=hashlib.sha256(script_bytes['28']).hexdigest(),
        prerequisite_script_sha256={script_paths[key]: hashlib.sha256(script_bytes[key]).hexdigest() for key in ('21', '23', '24', '25', '27')},
        reference_helper_sha256=helper_hashes, source_sha256=hashes, source_hashes_unchanged=True,
        historical_preflight_sha256=historical, historical_preflights_unchanged=True,
        preflight_strategy='Read only original sales/calendar CSVs. Build a private 90-day six-column daily table, execute actual SQL21,23,24,25,27, then read-only SQL28. This is not a full-history rebuild; the learner database is never opened.',
        independent_reference='Original wide arrays independently supply each product 90-day total, twelve seven-day vectors and excluded-six-day total. Python prefix endpoints define ABC, centered Fraction population CV squared defines XYZ, and Decimal half-up rounding defines displayed four-decimal percentages. Compare every product membership and 22 combined fields before independently grouping all sixteen cells.',
        analysis_windows={'abc': {'start_date': '2016-01-26', 'end_date': '2016-04-24', 'days': 90},
                          'xyz': {'start_date': '2016-01-30', 'end_date': '2016-04-22', 'days': 84, 'weeks': 12},
                          'scope': 'Every product pooled across all ten stores; zero observations retained.'},
        denominator_policy='SKU share uses all 3049 products; each unit share uses its own window total. Empty cells have zero counts and units; if a whole-window unit total is zero, every corresponding unit share including TOTAL is NULL. Rounded cell percentages are not required to sum exactly to 100.',
        timings=timings, timing_scope='DuckDB CLI process timings; excludes Python comparison and file hashing.',
        combined_product_rows_compared=3049, combined_columns_compared=22, combined_field_mismatches=0,
        combined_float_error_summary=float_errors, product_memberships_compared=3049, membership_mismatches=0,
        integer_cells_compared=16, integer_cell_mismatches=0,
        row_and_column_count_and_both_unit_margins_matched=True,
        source_controls={'product_count': 3049, 'units_90d': sum(r['units_90d'] for r in source),
                         'units_84d': sum(sum(r['weeks']) for r in source),
                         'excluded_six_day_units': sum(r['excluded_six_day_units'] for r in source),
                         'empty_cells': sum(c['sku_count'] == 0 for c in expected_cells)},
        accepted_combined_baseline_matched=True, accepted_baseline_evidence=accepted_path,
        accepted_baseline_evidence_sha256=hashlib.sha256(accepted_bytes).hexdigest(),
        all_input_tables_unchanged=True, input_rows_sha256_before=input_hashes,
        input_rows_sha256_after={key: fingerprint(rows) for key, rows in after.items()},
        integer_cells=cells, result_rows=17, results=results,
        fixture_cases_passed=len(cases), fixture_cases=cases,
        scope='Assistant preflight only; learner contribution query execution pending. Recorded units in different-length nested historical windows are not a before/after growth comparison. This descriptive report does not estimate inventory, profitability, replenishment or forecast performance; no product-level extract is saved.')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, default=str, ensure_ascii=False) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps({'fixture_cases_passed': len(cases), 'source_controls': report['source_controls'],
                      'timings': timings, 'results': results}, default=str), flush=True)


if __name__ == '__main__':
    main()
