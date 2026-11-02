"""Verify supported week-by-department price contrasts with exact independent fractions."""
import argparse
import json
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from fractions import Fraction
from pathlib import Path

sys.dont_write_bytecode = True
import preflight_item_store_weekly_prices as weekly
import preflight_price_variation as variation
import preflight_price_sales_association as association
import preflight_weekly_price_sales_association as calendar_association
import preflight_department_price_sales_association as department_association


COLUMNS = ['dept_id', 'price_direction', 'direction_transitions', 'comparable_transitions',
           'unsupported_transitions', 'comparable_weeks', 'weighted_direction_mean_change',
           'weighted_unchanged_mean_change', 'mean_change_gap', 'positive_gap_weeks',
           'negative_gap_weeks', 'check_status']
CELL_COLUMNS = ['dept_id', 'retail_week', 'week_start', 'series_count', *association.COLUMNS]
MEANS = COLUMNS[6:9]
KNOWN_SERIES = department_association.KNOWN_SERIES
PROTOCOL_SHA = 'f7a64a26f4b96357941be56950c9cefe0b68849edccc50d403e2654b2b8321d4'


def round_fraction(value):
    if value is None:
        return None
    quotient, remainder = divmod(abs(value.numerator) * 1000000, value.denominator)
    quotient += 2 * remainder >= value.denominator
    sign = '-' if value < 0 and quotient else ''
    return f'{sign}{quotient // 1000000}.{quotient % 1000000:06d}'


def contrast_reference(cells):
    lookup = {(r['dept_id'], r['retail_week'], r['price_direction']): r for r in cells}
    result = []
    for dept in KNOWN_SERIES:
        for direction in ['UP', 'DOWN']:
            direction_count = supported_count = supported_weeks = positive = negative = 0
            target_sum, reference_sum, gap_sum = Fraction(0), Fraction(0), Fraction(0)
            for week in range(11602, 11613):
                target = lookup[(dept, str(week), direction)]
                unchanged = lookup[(dept, str(week), 'UNCHANGED')]
                n, u = target['transitions'], unchanged['transitions']
                direction_count += n
                if n == 0 or u == 0:
                    continue
                s, t = target['unit_difference'], unchanged['unit_difference']
                cross_product = s * u - t * n
                supported_count += n
                supported_weeks += 1
                target_sum += s
                reference_sum += Fraction(n * t, u)
                gap_sum += Fraction(cross_product, u)
                positive += cross_product > 0
                negative += cross_product < 0
            means = [None if not supported_count else round_fraction(value / supported_count)
                     for value in [target_sum, reference_sum, gap_sum]]
            result.append(dict(zip(COLUMNS, [dept, direction, direction_count, supported_count,
                direction_count - supported_count, supported_weeks, *means, positive, negative, 'PASS'])))
    return result


def reference(series, prices):
    buckets = {(dept, week): [] for dept in KNOWN_SERIES for week in range(11602, 11613)}
    pair_sets = {dept: set() for dept in KNOWN_SERIES}
    all_records = []
    for source in series:
        dept = source['dept_id']
        assert dept in KNOWN_SERIES and source['cat_id'] == dept.rsplit('_', 1)[0]
        pair = source['item_id'], source['store_id']
        pair_sets[dept].add(pair)
        units = [sum(source['days'][7 * offset:7 * offset + 7]) for offset in range(12)]
        for offset in range(1, 12):
            previous = prices.get((*pair, 11600 + offset))
            current = prices.get((*pair, 11601 + offset))
            direction = ('MISSING_ENDPOINT' if previous is None or current is None else
                         'UP' if current > previous else 'DOWN' if current < previous else 'UNCHANGED')
            record = (pair, direction, units[offset - 1], units[offset])
            buckets[(dept, 11601 + offset)].append(record)
            all_records.append(record)
    cells = []
    for (dept, week), records in buckets.items():
        start = (weekly.START + timedelta(days=7 * (week - 11601))).isoformat()
        cells.extend(dict(dept_id=dept, retail_week=str(week), week_start=start,
                          series_count=len(pair_sets[dept]), **group)
                     for group in association.summarize(records)[:-1])
    return contrast_reference(cells), cells, association.summarize(all_records)


def assert_report(actual, expected):
    assert len(actual) == 14 and all(list(row) == COLUMNS for row in actual), 'Contrast report shape/order mismatch'
    for row in actual:
        for key in COLUMNS[2:-1]:
            if key in MEANS:
                calendar_association.normalize_decimal(row, key, 6)
                if row[key] is not None and Decimal(row[key]) == 0:
                    row[key] = '0.000000'
            else:
                calendar_association.normalize_integer(row, key)
        assert row['direction_transitions'] == row['comparable_transitions'] + row['unsupported_transitions']
        assert row['positive_gap_weeks'] + row['negative_gap_weeks'] <= row['comparable_weeks'] <= 11
    assert actual == expected, 'Contrast report differs from exact independent Fraction reference'


def assert_cells(actual, expected):
    assert len(actual) == 308 and all(list(row) == CELL_COLUMNS for row in actual), 'Internal joint cell shape/order mismatch'
    for row in actual:
        for key in ['series_count', *association.COLUMNS[1:6]]:
            calendar_association.normalize_integer(row, key)
        for key in association.COLUMNS[6:11]:
            calendar_association.normalize_decimal(row, key, 6 if key in association.COLUMNS[6:8] else 4)
        assert row['distinct_pairs'] == row['transitions'] <= row['series_count']
        assert row['unit_difference'] == row['current_units'] - row['previous_units']
    assert actual == expected, 'Internal 308-cell report differs from original-source reference'


def reconcile_reports(report, cells, global_report, weekly_cells, department_cells):
    for margins, dimension in [(weekly_cells, 'retail_week'), (department_cells, 'dept_id')]:
        for margin in margins:
            selected = [row for row in cells if row[dimension] == margin[dimension]
                        and row['price_direction'] == margin['price_direction']]
            for key in ['transitions', 'previous_units', 'current_units', 'unit_difference']:
                assert sum(row[key] for row in selected) == margin[key]
    for group in global_report[:-1]:
        selected = [row for row in cells if row['price_direction'] == group['price_direction']]
        for key in ['transitions', 'previous_units', 'current_units', 'unit_difference']:
            assert sum(row[key] for row in selected) == group[key]
    for row in report:
        selected = [cell for cell in cells if cell['dept_id'] == row['dept_id']
                    and cell['price_direction'] == row['price_direction']]
        assert sum(cell['transitions'] for cell in selected) == row['direction_transitions']
    assert sum(row['transitions'] for row in cells) == global_report[-1]['transitions']
    assert sum(row['unit_difference'] for row in cells) == global_report[-1]['unit_difference']


def fixture():
    series, prices = [], {}
    for item, dept in enumerate(KNOWN_SERIES, start=1):
        for store in [1, 2, 3]:
            units, cents = [0] * 12, [100 * store] * 12
            if item == 1:
                if store == 1:
                    units, cents = [0, 1, 1] + [5] * 9, [100, 101, 101] + [102] * 9
                elif store == 2:
                    units, cents = [0, 1, 1] + [7] * 9, [200] * 3 + [201] * 9
                else:
                    units = [0] + [3] * 11
            elif item == 2:
                units = [0] + [1] * 11
                if store == 1:
                    cents = [100] + [101] * 11
            elif item == 3:
                units = [0] + [2] * 11
                cents = [100 * store] + [100 * store + 1] * 11
            elif (item, store) == (4, 1):
                units, cents = [0, 3] + [0] * 10, [None, 100, None] + [100] * 9
            row = dict(item_id=f'P{item}', store_id=f'S{store}', dept_id=dept,
                       cat_id=dept.rsplit('_', 1)[0], state_id={1: 'CA', 2: 'TX', 3: 'WI'}[store],
                       days=[u if day == 0 else 0 for u in units for day in range(7)])
            series.append(row)
            for offset, value in enumerate(cents):
                if value is not None:
                    prices[(row['item_id'], row['store_id'], 11601 + offset)] = Decimal(value) / 100
    raw_values = ','.join('(' + ','.join(weekly.quote(row[key]) for key in
        ['item_id', 'store_id', 'dept_id', 'cat_id', 'state_id']) + ')' for row in series)
    daily_values = ','.join(f"({weekly.quote(row['item_id'])},{weekly.quote(row['store_id'])},'d_{1828 + offset}',"
        f"DATE '{(weekly.START + timedelta(days=offset)).isoformat()}',{11601 + offset // 7},{units})"
        for row in series for offset, units in enumerate(row['days']))
    price_values = ','.join(f'({weekly.quote(store)},{weekly.quote(item)},{week},{price})'
                          for (item, store, week), price in prices.items())
    setup = f"""
CREATE SCHEMA raw; CREATE SCHEMA core; CREATE SCHEMA mart; CREATE SCHEMA stg;
CREATE TABLE raw.m5_sales_wide AS SELECT * FROM (VALUES {raw_values}) t(item_id,store_id,dept_id,cat_id,state_id);
CREATE TABLE core.m5_product AS SELECT DISTINCT item_id,dept_id,cat_id FROM raw.m5_sales_wide;
CREATE TABLE core.m5_store AS SELECT DISTINCT store_id,state_id FROM raw.m5_sales_wide;
CREATE TABLE core.m5_calendar AS SELECT 'd_'||CAST(n AS VARCHAR) AS d,
    DATE '2011-01-29'+CAST(n-1 AS INTEGER) AS date,
    CAST(11601+floor((n-1828)/7) AS INTEGER) AS wm_yr_wk FROM range(1,1970) t(n);
CREATE TABLE mart.m5_sales_daily(item_id VARCHAR,store_id VARCHAR,d VARCHAR,date DATE,wm_yr_wk INTEGER,units INTEGER);
INSERT INTO mart.m5_sales_daily VALUES {daily_values};
CREATE TABLE stg.m5_prices(store_id VARCHAR,item_id VARCHAR,wm_yr_wk INTEGER,sell_price DECIMAL(18,2));
INSERT INTO stg.m5_prices VALUES {price_values};
"""
    return setup, series, prices


def arithmetic_cells():
    values = {(dept, week, direction): [0, 0] for dept in KNOWN_SERIES for week in range(11602, 11613)
              for direction in association.DIRECTIONS[:-1]}
    for dept, n, s, u, t in [('FOODS_1', 128, 1, 1, 0), ('FOODS_2', 1, 0, 128, 1),
                            ('FOODS_3', 4096, 1, 4095, 1), ('HOUSEHOLD_1', 4095, 1, 4096, 1),
                            ('HOUSEHOLD_2', 1, 2, 1, 2)]:
        values[(dept, 11602, 'UP')] = [n, s]
        values[(dept, 11602, 'UNCHANGED')] = [u, t]
    for dept, sign in [('HOBBIES_1', 1), ('HOBBIES_2', -1)]:
        for week, n, s in [(11602, 3, sign), (11603, 192, -61 * sign)]:
            values[(dept, week, 'UP')] = [1, 0]
            values[(dept, week, 'UNCHANGED')] = [n, s]
    return [dict(dept_id=dept, retail_week=str(week), price_direction=direction,
                 transitions=n, unit_difference=s) for (dept, week, direction), (n, s) in values.items()]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--duckdb', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--fixtures-only', action='store_true')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    tmp_root = root / 'tmp'
    tmp_root.mkdir(exist_ok=True)
    script_path = 'sql/49_week_department_price_contrasts.sql'
    validator_path = 'validation/preflight_week_department_price_contrasts.py'
    protocol_path = 'docs/WEEK_DEPARTMENT_PRICE_CONTRASTS_PROTOCOL.md'
    sql_paths = {'09': 'sql/09_stage_prices.sql', '23': 'sql/23_build_product_weekly.sql',
                 '44': 'sql/44_build_item_store_weekly_prices.sql', '45': 'sql/45_audit_price_variation.sql',
                 '46': 'sql/46_price_sales_association.sql', '47': 'sql/47_weekly_price_sales_association.sql', '48': 'sql/48_department_price_sales_association.sql'}
    evidence_paths = {'44': 'data/item_store_weekly_prices_preflight.json', '45': 'data/price_variation_preflight.json',
                      '46': 'data/price_sales_association_preflight.json', '47': 'data/weekly_price_sales_association_preflight.json', '48': 'data/department_price_sales_association_preflight.json'}
    paths = [script_path, validator_path, protocol_path, *sql_paths.values(), *evidence_paths.values(),
             'validation/preflight_item_store_weekly_prices.py', 'validation/preflight_price_variation.py',
             'validation/preflight_price_sales_association.py', 'validation/preflight_weekly_price_sales_association.py', 'validation/preflight_department_price_sales_association.py',
             'docs/PRICE_VARIATION_PROTOCOL.md', 'docs/PRICE_SALES_ASSOCIATION_PROTOCOL.md',
             'docs/WEEKLY_PRICE_SALES_ASSOCIATION_PROTOCOL.md', 'docs/DEPARTMENT_PRICE_SALES_ASSOCIATION_PROTOCOL.md']
    hashes = {path: weekly.sha256(root / path) for path in paths}
    assert hashes[protocol_path] == PROTOCOL_SHA, 'Frozen department protocol changed'
    audit = (root / script_path).read_text(encoding='utf-8')
    scripts = {key: (root / path).read_text(encoding='utf-8') for key, path in sql_paths.items()}
    prefix = lambda sql, boundary: sql[sql.index('WITH parameters AS ('):sql.index(boundary)]
    assert prefix(audit, '), aggregates AS MATERIALIZED (') == prefix(scripts['48'], '), aggregates AS MATERIALIZED ('), 'Accepted input/transition checks changed'
    measures = lambda sql: sql[sql.index('        COUNT(*) AS transitions'):sql.index('\n    FROM transitions GROUP BY')]
    assert measures(audit) == measures(scripts['46']), 'Accepted aggregate expressions changed'
    percentages = lambda sql: sql[sql.index('        CAST(ROUND(100.0*a.sales_up'):sql.index('        COALESCE(a.sales_up,0)')]
    assert percentages(audit) == percentages(scripts['46']), 'Accepted percentage rounding expressions changed'
    cell_sql = audit[:audit.rindex('\nSELECT r.dept_id,r.price_direction,')] + """
SELECT r.dept_id,CAST(r.wm_yr_wk AS VARCHAR) AS retail_week,r.week_start,r.series_count,
""" + ','.join('r.' + key for key in association.COLUMNS[:-1]) + """,
    CASE WHEN COALESCE(i.passed AND t.passed AND h.passed,false) THEN 'PASS'
         ELSE error('Week-department contrast internal cells blocked') END AS check_status
FROM input_health i CROSS JOIN transition_health t CROSS JOIN report_health h
LEFT JOIN cells r ON true
ORDER BY r.dept_id,r.wm_yr_wk,r.sort_order;
"""
    builds = {key: scripts[key].split('-- VALIDATION:', 1)[0] for key in ['09', '23', '44']}

    def execute(database, folder, query, allow_error=False):
        assert database.resolve().is_relative_to(tmp_root.resolve()) and folder.resolve().is_relative_to(tmp_root.resolve())
        settings = f"SET threads=2; SET memory_limit='2GB'; SET temp_directory={weekly.quote((folder / 'spill').as_posix())};\n"
        started = time.perf_counter()
        run = subprocess.run([args.duckdb, str(database), '-bail', '-json'], input=settings + query,
                             text=True, encoding='utf-8', capture_output=True)
        if not allow_error:
            assert run.returncode == 0, run.stderr
        return run, round(time.perf_counter() - started, 3)

    setup, series, prices = fixture()
    expected, expected_cells, expected_global = reference(series, prices)
    weekly_report, weekly_cells, _ = calendar_association.reference(series, prices)
    department_report, department_cells, _ = department_association.reference(series, prices)
    reconcile_reports(expected, expected_cells, expected_global, weekly_cells, department_cells)
    assert [expected[0][key] for key in ['comparable_transitions', 'comparable_weeks', *MEANS,
                                       'positive_gap_weeks', 'negative_gap_weeks']] == [3, 2, '3.666667', '0.666667', '3.000000', 1, 1]
    assert expected[2]['comparable_weeks'] == 1 and expected[2]['mean_change_gap'] == '0.000000'
    assert expected[2]['positive_gap_weeks'] == expected[2]['negative_gap_weeks'] == 0
    assert expected[4]['direction_transitions'] == expected[4]['unsupported_transitions'] == 3
    assert expected[4]['comparable_transitions'] == 0 and all(expected[4][key] is None for key in MEANS)
    assert expected[1]['direction_transitions'] == 0 and all(expected[1][key] is None for key in MEANS)
    missing = [row for row in expected_cells if row['price_direction'] == 'MISSING_ENDPOINT']
    assert sum(row['transitions'] for row in missing) == 3
    assert sum(row['previous_units'] for row in missing) == sum(row['current_units'] for row in missing) == 3
    expected_units = sum(sum(row['days']) for row in series)

    def transform(sql):
        sql = sql.replace('3049 AS expected_items,10 AS expected_stores', '7 AS expected_items,3 AS expected_stores')
        sql = sql.replace('3536539 AS expected_units', f'{expected_units} AS expected_units')
        for dept, count in KNOWN_SERIES.items():
            sql = sql.replace(f"('{dept}',{count})", f"('{dept}',3)")
        return sql

    cases = []
    with tempfile.TemporaryDirectory(prefix='contrast-support-case-', dir=tmp_root) as temp:
        folder = Path(temp)
        database = folder / 'case.duckdb'
        execute(database, folder, setup + transform(builds['23']) + transform(builds['44']))
        run, _ = execute(database, folder, transform(audit))
        assert_report(weekly.parsed(run.stdout), expected)
        run, _ = execute(database, folder, transform(cell_sql))
        assert_cells(weekly.parsed(run.stdout), expected_cells)
        cases.append(dict(case='unequal_target_weights_unsupported_reference_absent_targets_exact_ties_zero_and_missing', passed=True))
        rejected, _ = execute(database, folder, 'DELETE FROM core.m5_calendar;\n' + transform(audit), allow_error=True)
        assert rejected.returncode != 0 and 'Week-department price contrasts blocked' in rejected.stderr
        cases.append(dict(case='empty_calendar_intended_rejection', passed=True, expected_rejection=True))
    assert not folder.exists()

    # Exercise the actual production contrast/report CTEs directly at difficult rational boundaries.
    math_cells = arithmetic_cells()
    math_expected = contrast_reference(math_cells)
    assert math_expected[0]['mean_change_gap'] == '0.007813'
    assert math_expected[2]['mean_change_gap'] == '-0.007813'
    assert math_expected[4]['mean_change_gap'] == '0.000000' and math_expected[4]['negative_gap_weeks'] == 1
    assert math_expected[6]['mean_change_gap'] == '-0.007813' and math_expected[8]['mean_change_gap'] == '0.007813'
    assert math_expected[10]['mean_change_gap'] == '0.000000' and math_expected[10]['positive_gap_weeks'] == 1
    assert math_expected[12]['mean_change_gap'] == '0.000000' and math_expected[12]['positive_gap_weeks'] == math_expected[12]['negative_gap_weeks'] == 0
    values = ','.join(f"({weekly.quote(row['dept_id'])},{row['retail_week']},{association.DIRECTIONS.index(row['price_direction']) + 1},"
        f"{weekly.quote(row['price_direction'])},{row['transitions']}::BIGINT,{row['unit_difference']}::HUGEINT)" for row in math_cells)
    contrast_ctes = audit[audit.index('), week_contrasts AS MATERIALIZED ('):audit.index('), report_health AS (')] + ')\n'
    math_sql = ('WITH cells AS (SELECT * FROM (VALUES ' + values +
        ') t(dept_id,wm_yr_wk,sort_order,price_direction,transitions,unit_difference)\n' + contrast_ctes +
        'SELECT ' + ','.join('r.' + key for key in COLUMNS[:-1]) +
        ", 'PASS' AS check_status FROM report r ORDER BY dept_id,sort_order;")
    with tempfile.TemporaryDirectory(prefix='contrast-rational-case-', dir=tmp_root) as temp:
        folder = Path(temp)
        run, _ = execute(folder / 'case.duckdb', folder, math_sql)
        assert_report(weekly.parsed(run.stdout), math_expected)
    assert not folder.exists()
    cases.append(dict(case='production_rational_contrasts_signed_rounding_boundaries_repeating_ratios_tiny_signs_and_exact_ties', passed=True))
    print(json.dumps({'fixture_cases_passed': len(cases)}), flush=True)
    if args.fixtures_only:
        return

    sources = {name: Path('D:/database/m5-forecasting-accuracy') / name
               for name in ['sales_train_evaluation.csv', 'calendar.csv', 'sell_prices.csv']}
    registry = json.loads((root / 'data/m5_source_audit.json').read_text(encoding='utf-8'))
    source_hashes = {name: weekly.sha256(path) for name, path in sources.items()}
    assert all(source_hashes[name] == registry['files'][name]['sha256'] for name in sources)
    historical = {str(path.relative_to(root)): weekly.sha256(path) for path in (root / 'data').glob('*preflight.json')
                  if path.resolve() != args.output.resolve()}
    series, prices, controls, reference_seconds = weekly.read_original_sources(sources)
    expected, expected_cells, expected_global = reference(series, prices)
    accepted = {key: json.loads((root / path).read_text(encoding='utf-8')) for key, path in evidence_paths.items()}
    variation.assert_report(variation.reference(series, prices), accepted['45']['results'])
    association.assert_report(expected_global, accepted['46']['results'])
    weekly_report, weekly_cells, weekly_global = calendar_association.reference(series, prices)
    calendar_association.assert_report(weekly_report, accepted['47']['results'])
    association.assert_report(weekly_global, accepted['46']['results'])
    department_report, department_cells, department_global = department_association.reference(series, prices)
    department_association.assert_report(department_report, accepted['48']['results'])
    association.assert_report(department_global, accepted['46']['results'])
    reconcile_reports(expected, expected_cells, expected_global, weekly_cells, department_cells)

    day_columns = ','.join(f'd_{n}' for n in range(1828, 1912))
    setup = f"""
CREATE SCHEMA raw; CREATE SCHEMA core; CREATE SCHEMA mart; CREATE SCHEMA stg;
CREATE TABLE raw.m5_sales_wide AS SELECT id,item_id,dept_id,cat_id,store_id,state_id,{day_columns}
FROM read_csv({weekly.quote(sources['sales_train_evaluation.csv'].as_posix())},header=true,all_varchar=true);
CREATE TABLE core.m5_product AS SELECT DISTINCT item_id,dept_id,cat_id FROM raw.m5_sales_wide;
CREATE TABLE core.m5_store AS SELECT DISTINCT store_id,state_id FROM raw.m5_sales_wide;
CREATE TABLE core.m5_calendar AS SELECT d,CAST(date AS DATE) AS date,CAST(wm_yr_wk AS INTEGER) AS wm_yr_wk
FROM read_csv({weekly.quote(sources['calendar.csv'].as_posix())},header=true,all_varchar=true);
CREATE TABLE mart.m5_sales_daily AS WITH unpivoted AS
(UNPIVOT raw.m5_sales_wide ON {day_columns} INTO NAME d VALUE units_text)
SELECT u.item_id,u.store_id,u.d,c.date,c.wm_yr_wk,
CASE WHEN regexp_full_match(units_text,'[0-9]+') AND TRY_CAST(units_text AS INTEGER) IS NOT NULL
THEN CAST(units_text AS INTEGER) ELSE error('Invalid original window units') END AS units
FROM unpivoted u JOIN core.m5_calendar c USING (d);
CREATE TABLE raw.m5_prices AS SELECT * FROM read_csv({weekly.quote(sources['sell_prices.csv'].as_posix())},header=true,all_varchar=true)
WHERE TRY_CAST(wm_yr_wk AS INTEGER) BETWEEN 11601 AND 11612 OR TRY_CAST(wm_yr_wk AS INTEGER) IS NULL;
"""
    snapshots = {
        'weekly_input': f'SELECT * FROM {weekly.TARGET} ORDER BY item_id,store_id,wm_yr_wk',
        'pooled_input': 'SELECT * FROM mart.m5_product_weekly_12w ORDER BY item_id,wm_yr_wk',
        'raw_metadata': 'SELECT item_id,store_id,dept_id,cat_id,state_id FROM raw.m5_sales_wide ORDER BY item_id,store_id',
        'calendar_date_week_projection': 'SELECT * FROM core.m5_calendar ORDER BY date,d,wm_yr_wk',
        'products': 'SELECT * FROM core.m5_product ORDER BY item_id',
        'stores': 'SELECT * FROM core.m5_store ORDER BY store_id',
        'prices_12w': 'SELECT * FROM stg.m5_prices ORDER BY item_id,store_id,wm_yr_wk',
    }
    with tempfile.TemporaryDirectory(prefix='week-department-contrasts-', dir=tmp_root) as temp:
        folder = Path(temp)
        database = folder / 'preflight.duckdb'
        _, setup_seconds = execute(database, folder, setup + builds['09'] + builds['23'] + builds['44'])

        def snapshot(prefix_name):
            query = ''.join(f'COPY ({query}) TO {weekly.quote((folder / (prefix_name + "_" + name + ".csv")).as_posix())} (HEADER,FORMAT CSV);\n'
                            for name, query in snapshots.items())
            execute(database, folder, query)
            return {name: weekly.sha256(folder / f'{prefix_name}_{name}.csv') for name in snapshots}

        before = snapshot('before')
        row_count, input_hash = weekly.compare_export(folder / 'before_weekly_input.csv', weekly.expected_rows(series, prices))
        assert row_count == 365880 and input_hash == weekly.canonical_hash(weekly.expected_rows(series, prices))
        assert input_hash == accepted['44']['stored_rows_sha256'], 'SQL44 accepted input fingerprint changed'
        pooled_count, pooled_hash = weekly.compare_pooled_export(folder / 'before_pooled_input.csv', series)
        price_count = weekly.compare_price_export(folder / 'before_prices_12w.csv', prices)
        run, sql45_seconds = execute(database, folder, scripts['45'])
        variation.assert_report(weekly.parsed(run.stdout), accepted['45']['results'])
        run, sql46_seconds = execute(database, folder, scripts['46'])
        association.assert_report(weekly.parsed(run.stdout), accepted['46']['results'])
        run, sql47_seconds = execute(database, folder, scripts['47'])
        calendar_association.assert_report(weekly.parsed(run.stdout), accepted['47']['results'])
        run, sql48_seconds = execute(database, folder, scripts['48'])
        department_association.assert_report(weekly.parsed(run.stdout), accepted['48']['results'])
        run, cell_seconds = execute(database, folder, cell_sql)
        cells = weekly.parsed(run.stdout)
        assert_cells(cells, expected_cells)
        run, audit_seconds = execute(database, folder, audit)
        results = weekly.parsed(run.stdout)
        assert_report(results, expected)
        reconcile_reports(results, cells, expected_global, weekly_cells, department_cells)
        after = snapshot('after')
        assert before == after, 'Read-only week-department contrast analysis changed a scoped input'
        database_bytes = database.stat().st_size
    assert not folder.exists()
    assert all(weekly.sha256(path) == source_hashes[name] for name, path in sources.items())
    assert all(weekly.sha256(root / path) == value for path, value in historical.items())
    assert all(weekly.sha256(root / path) == value for path, value in hashes.items())
    evidence = dict(
        checked_at_utc=datetime.now(timezone.utc).isoformat(), executor='assistant',
        engine=subprocess.check_output([args.duckdb, '-version'], text=True).strip(),
        script=script_path, script_sha256=hashes[script_path], validator=validator_path, validator_sha256=hashes[validator_path],
        protocol=protocol_path, protocol_sha256=PROTOCOL_SHA, code_and_dependency_sha256=hashes,
        settings={'threads': 2, 'memory_limit': '2GB'}, source_sha256=source_hashes,
        source_hashes_unchanged=True, source_controls=controls,
        input_window={'start_date': '2016-01-30', 'end_date': '2016-04-22', 'weeks': 12, 'pairs': 30490},
        report_window={'first_current_week': 11602, 'last_current_week': 11612,
                       'start_date': '2016-02-06', 'end_date': '2016-04-22'},
        department_series_roster=KNOWN_SERIES,
        independent_reference='Original-source csv/Decimal helpers reconstruct every weekly field and all 308 department-week-direction cells across 16 fields. Exact Fraction accumulation and integer quotient/remainder half-away rounding independently verify all 14 displayed contrasts across 12 fields. Integer cross-products classify signs before rounding. Full-window, weekly and department margins are recomputed from original transitions, never group medians or unweighted means.',
        preflight_strategy='One bounded private database stages only 84 sales columns and twelve price weeks through unchanged SQL09/23/44. Unchanged SQL45/46/47/48 reports reconcile to accepted evidence. Historical guard suites/forecasting are not rerun; learner persistent database is never opened.',
        weekly_input_rows_compared=row_count, weekly_input_fields_compared=12, weekly_input_exact_mismatches=0,
        weekly_input_rows_sha256=input_hash, accepted_sql44_input_fingerprint_matched=True,
        pooled_rows_compared=pooled_count, pooled_fields_compared=8, pooled_rows_sha256=pooled_hash,
        price_rows_compared=price_count, price_fields_compared=4, transition_positions_evaluated=335390,
        sql45_rows_reconciled=12, sql45_fields_reconciled=12, sql45_accepted_report_matched=True,
        sql46_rows_reconciled=5, sql46_fields_reconciled=12, sql46_accepted_report_matched=True,
        sql47_rows_reconciled=11, sql47_fields_reconciled=12, sql47_accepted_report_matched=True,
        sql48_rows_reconciled=7, sql48_fields_reconciled=12, sql48_accepted_report_matched=True,
        sql48_input_transition_department_guard_prefix_unchanged=True, sql46_aggregate_rounding_expressions_unchanged=True,
        internal_cell_rows_compared=308, internal_cell_fields_compared=16, internal_cell_exact_mismatches=0,
        internal_cell_sha256=weekly.canonical_hash([[row[key] for key in CELL_COLUMNS] for row in cells]),
        weekly_and_department_count_unit_margins_reconciled=True, exact_fraction_contrasts_and_rounding_matched=True,
        gap_signs_checked_by_exact_integer_cross_products=True, eligibility_uses_only_positive_direction_and_unchanged_counts=True,
        scoped_input_sha256_before=before, scoped_input_sha256_after=after, scoped_inputs_unchanged=True,
        historical_preflight_files_unchanged=len(historical), temporary_database_removed=True,
        temporary_database_bytes_after_close=database_bytes, fixture_case_count=len(cases), fixture_cases=cases,
        independent_source_read_seconds=reference_seconds, setup_seconds=setup_seconds,
        sql45_reconciliation_seconds=sql45_seconds, sql46_reconciliation_seconds=sql46_seconds,
        sql47_reconciliation_seconds=sql47_seconds, sql48_reconciliation_seconds=sql48_seconds,
        internal_cell_query_seconds=cell_seconds, audit_seconds=audit_seconds,
        timing_scope='One-run elapsed seconds; CLI timings exclude hashing/Python comparisons. DuckDB memory_limit is not a total-process cap.',
        report_rows=14, report_columns=12,
        report_sha256=weekly.canonical_hash([[row[key] for key in COLUMNS] for row in results]),
        report_fingerprint_contract='SHA-256 over ordered compact JSON arrays plus LF; counts/unit sums are integers, department identifiers are strings, displayed means/gaps are fixed-six-place strings or null with canonical positive zero. Internal cell means/medians use six places and percentages four.',
        results=results,
        scope='Assistant independent preflight only; learner SQL49 execution pending. Exploratory descriptive same-week/department contrasts use target-count weights and support-only eligibility. Unchanged references are not same-product/store or causal controls; baseline/product/store differences can remain. Adjacent observations overlap; zeros, missing endpoints and unsupported targets remain accounted for. No causal effect, elasticity, regression, significance test, promotion or anomaly claim. Public evidence contains aggregates and fingerprints only.')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, default=str) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps({'fixture_cases_passed': len(cases), 'weekly_input_rows_compared': row_count,
                      'audit_seconds': audit_seconds, 'results': results}), flush=True)


if __name__ == '__main__':
    main()
