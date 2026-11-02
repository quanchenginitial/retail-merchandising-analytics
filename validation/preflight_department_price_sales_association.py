"""Bounded original-source verification of the frozen department price-sales breakdown."""
import argparse
import json
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

sys.dont_write_bytecode = True
import preflight_item_store_weekly_prices as weekly
import preflight_price_variation as variation
import preflight_price_sales_association as association
import preflight_weekly_price_sales_association as calendar_association


COLUMNS = ['dept_id', 'series_count', 'price_up_transitions', 'price_up_mean_unit_change',
           'price_down_transitions', 'price_down_mean_unit_change', 'unchanged_transitions',
           'unchanged_mean_unit_change', 'missing_endpoint_transitions', 'total_transitions',
           'total_unit_difference', 'check_status']
CELL_COLUMNS = ['dept_id', 'series_count', *association.COLUMNS]
MEANS = calendar_association.MEANS
KNOWN_SERIES = {'FOODS_1': 2160, 'FOODS_2': 3980, 'FOODS_3': 8230, 'HOBBIES_1': 4160,
                'HOBBIES_2': 1490, 'HOUSEHOLD_1': 5320, 'HOUSEHOLD_2': 5150}
PROTOCOL_SHA = 'e6ca5262430cb721f3f408e8184a6a0e21742f0638b56fe023fea35cea59aba4'


def reference(series, prices):
    """Source metadata supplies membership; direct weekly lookups supply every transition."""
    buckets = {dept: [] for dept in KNOWN_SERIES}
    pairs = {dept: set() for dept in KNOWN_SERIES}
    all_records = []
    for source in series:
        dept = source['dept_id']
        assert dept in buckets and source['cat_id'] == dept.rsplit('_', 1)[0]
        pair = source['item_id'], source['store_id']
        pairs[dept].add(pair)
        units = [sum(source['days'][7 * offset:7 * offset + 7]) for offset in range(12)]
        for offset in range(1, 12):
            previous = prices.get((*pair, 11600 + offset))
            current = prices.get((*pair, 11601 + offset))
            direction = ('MISSING_ENDPOINT' if previous is None or current is None else
                         'UP' if current > previous else 'DOWN' if current < previous else 'UNCHANGED')
            record = (pair, direction, units[offset - 1], units[offset])
            buckets[dept].append(record)
            all_records.append(record)
    report, cells = [], []
    for dept, records in buckets.items():
        groups = association.summarize(records)
        series_count = len(pairs[dept])
        cells.extend(dict(dept_id=dept, series_count=series_count, **group) for group in groups[:-1])
        report.append(dict(zip(COLUMNS, [dept, series_count,
            groups[0]['transitions'], groups[0]['mean_unit_change'],
            groups[1]['transitions'], groups[1]['mean_unit_change'],
            groups[2]['transitions'], groups[2]['mean_unit_change'],
            groups[3]['transitions'], groups[4]['transitions'], groups[4]['unit_difference'], 'PASS'])))
    return report, cells, association.summarize(all_records)


def assert_report(actual, expected):
    assert len(actual) == 7 and all(list(row) == COLUMNS for row in actual), 'Department report shape/order mismatch'
    for row in actual:
        for key in COLUMNS[1:-1]:
            if key in MEANS:
                calendar_association.normalize_decimal(row, key, 6)
            else:
                calendar_association.normalize_integer(row, key)
        assert row['total_transitions'] == 11 * row['series_count']
        assert row['total_transitions'] == sum(row[key] for key in
            ['price_up_transitions', 'price_down_transitions', 'unchanged_transitions', 'missing_endpoint_transitions'])
    assert actual == expected, 'Department report differs from independent source reference'


def assert_cells(actual, expected):
    assert len(actual) == 28 and all(list(row) == CELL_COLUMNS for row in actual), 'Internal department cell shape/order mismatch'
    for row in actual:
        for key in ['series_count', *association.COLUMNS[1:6]]:
            calendar_association.normalize_integer(row, key)
        for key in association.COLUMNS[6:11]:
            calendar_association.normalize_decimal(row, key, 6 if key in association.COLUMNS[6:8] else 4)
        assert row['distinct_pairs'] <= row['series_count'] and row['distinct_pairs'] <= row['transitions']
        assert row['unit_difference'] == row['current_units'] - row['previous_units']
    assert actual == expected, 'Internal 28-cell report differs from independent reference'


def reconcile_reports(report, cells, global_report):
    for group in global_report[:-1]:
        selected = [row for row in cells if row['price_direction'] == group['price_direction']]
        # Departments partition pairs; within a department, direction-specific pairs can overlap.
        for key in ['transitions', 'distinct_pairs', 'previous_units', 'current_units', 'unit_difference']:
            assert sum(row[key] for row in selected) == group[key]
        n = sum(row['transitions'] for row in selected)
        exact_mean = None if not n else association.rounded(Decimal(sum(row['unit_difference'] for row in selected)) / n, 6)
        assert exact_mean == group['mean_unit_change']
    assert sum(row['series_count'] for row in report) == global_report[-1]['distinct_pairs']
    assert sum(row['total_transitions'] for row in report) == global_report[-1]['transitions']
    assert sum(row['total_unit_difference'] for row in report) == global_report[-1]['unit_difference']


def fixture():
    series, prices = [], {}
    for item, dept in enumerate(KNOWN_SERIES, start=1):
        for store in [1, 2]:
            units, cents = [0] * 12, [100 * store] * 12
            if (item, store) == (1, 1):
                units, cents = [0, 1, 0, 3] + [0] * 8, [100, 101, 100, 101] + [100] * 8
            elif (item, store) == (2, 1):
                units, cents = [0, 0, 0, 5] + [0] * 8, [100] * 3 + [101] * 9
            elif (item, store) == (4, 1):
                units, cents = [0, 3] + [0] * 10, [None, 100, None] + [100] * 9
            row = dict(item_id=f'P{item}', store_id=f'S{store}', dept_id=dept,
                       cat_id=dept.rsplit('_', 1)[0], state_id='CA' if store == 1 else 'TX',
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--duckdb', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--fixtures-only', action='store_true')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    tmp_root = root / 'tmp'
    tmp_root.mkdir(exist_ok=True)
    script_path = 'sql/48_department_price_sales_association.sql'
    validator_path = 'validation/preflight_department_price_sales_association.py'
    protocol_path = 'docs/DEPARTMENT_PRICE_SALES_ASSOCIATION_PROTOCOL.md'
    sql_paths = {'09': 'sql/09_stage_prices.sql', '23': 'sql/23_build_product_weekly.sql',
                 '44': 'sql/44_build_item_store_weekly_prices.sql', '45': 'sql/45_audit_price_variation.sql',
                 '46': 'sql/46_price_sales_association.sql', '47': 'sql/47_weekly_price_sales_association.sql'}
    evidence_paths = {'44': 'data/item_store_weekly_prices_preflight.json', '45': 'data/price_variation_preflight.json',
                      '46': 'data/price_sales_association_preflight.json', '47': 'data/weekly_price_sales_association_preflight.json'}
    paths = [script_path, validator_path, protocol_path, *sql_paths.values(), *evidence_paths.values(),
             'validation/preflight_item_store_weekly_prices.py', 'validation/preflight_price_variation.py',
             'validation/preflight_price_sales_association.py', 'validation/preflight_weekly_price_sales_association.py',
             'docs/PRICE_VARIATION_PROTOCOL.md', 'docs/PRICE_SALES_ASSOCIATION_PROTOCOL.md',
             'docs/WEEKLY_PRICE_SALES_ASSOCIATION_PROTOCOL.md']
    hashes = {path: weekly.sha256(root / path) for path in paths}
    assert hashes[protocol_path] == PROTOCOL_SHA, 'Frozen department protocol changed'
    audit = (root / script_path).read_text(encoding='utf-8')
    scripts = {key: (root / path).read_text(encoding='utf-8') for key, path in sql_paths.items()}
    prefix = lambda sql, boundary: sql[sql.index('WITH parameters AS ('):sql.index(boundary)]
    assert prefix(audit, '), expected_department_series(') == prefix(scripts['47'], '), categories('), 'Accepted input/transition checks changed'
    measures = lambda sql: sql[sql.index('        COUNT(*) AS transitions'):sql.index('\n    FROM transitions GROUP BY')]
    assert measures(audit) == measures(scripts['46']), 'Accepted aggregate expressions changed'
    percentages = lambda sql: sql[sql.index('        CAST(ROUND(100.0*a.sales_up'):sql.index('        COALESCE(a.sales_up,0)')]
    assert percentages(audit) == percentages(scripts['46']), 'Accepted percentage rounding expressions changed'
    cell_sql = audit[:audit.rindex('\nSELECT r.dept_id,r.series_count,')] + '\nSELECT r.dept_id,r.series_count,' + \
        ','.join('r.' + key for key in association.COLUMNS[:-1]) + """,
    CASE WHEN COALESCE(i.passed AND t.passed AND h.passed,false) THEN 'PASS'
         ELSE error('Department price-sales internal cells blocked') END AS check_status
FROM input_health i CROSS JOIN transition_health t CROSS JOIN report_health h
LEFT JOIN cells r ON true
ORDER BY r.dept_id,r.sort_order;
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
    reconcile_reports(expected, expected_cells, expected_global)
    assert [row['series_count'] for row in expected] == [2] * 7
    assert [row['total_transitions'] for row in expected] == [22] * 7
    assert [(expected[i]['price_up_transitions'], expected[i]['price_up_mean_unit_change']) for i in [0, 1]] == [(2, '2.000000'), (1, '5.000000')]
    assert expected_global[0]['mean_unit_change'] == '3.000000'  # Unweighted department mean would be 3.5.
    assert sum(row['distinct_pairs'] for row in expected_cells[:4]) == 4 > expected[0]['series_count']
    assert expected[4]['price_up_transitions'] == 0 and expected[4]['price_up_mean_unit_change'] is None
    assert [expected_cells[15][key] for key in ['transitions', 'previous_units', 'current_units']] == [3, 3, 3]
    expected_units = sum(sum(row['days']) for row in series)

    def transform(sql):
        sql = sql.replace('3049 AS expected_items,10 AS expected_stores', '7 AS expected_items,2 AS expected_stores')
        sql = sql.replace('3536539 AS expected_units', f'{expected_units} AS expected_units')
        for dept, count in KNOWN_SERIES.items():
            sql = sql.replace(f"('{dept}',{count})", f"('{dept}',2)")
        return sql

    cases = []
    mutations = [
        ('department_membership_pair_support_empty_groups_and_weighted_composition', ''),
        ('wrong_department_mapping_rejected', f"UPDATE {weekly.TARGET} SET dept_id='FOODS_2' WHERE item_id='P1' AND store_id='S1';"),
        ('empty_calendar_rejected', 'DELETE FROM core.m5_calendar;'),
    ]
    for name, mutation in mutations:
        with tempfile.TemporaryDirectory(prefix='department-association-case-', dir=tmp_root) as temp:
            folder = Path(temp)
            database = folder / 'case.duckdb'
            execute(database, folder, setup + transform(builds['23']) + transform(builds['44']))
            run, _ = execute(database, folder, mutation + transform(audit), allow_error=bool(mutation))
            if mutation:
                assert run.returncode != 0 and 'Department price-sales association blocked' in run.stderr, 'Intended department guard did not reject fixture'
            else:
                assert_report(weekly.parsed(run.stdout), expected)
                run, _ = execute(database, folder, transform(cell_sql))
                assert_cells(weekly.parsed(run.stdout), expected_cells)
        assert not folder.exists()
        cases.append(dict(case=name, passed=True, expected_rejection=bool(mutation)))
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
    assert {row['dept_id']: row['series_count'] for row in expected} == KNOWN_SERIES, 'Established department roster changed'
    accepted = {key: json.loads((root / path).read_text(encoding='utf-8')) for key, path in evidence_paths.items()}
    variation.assert_report(variation.reference(series, prices), accepted['45']['results'])
    association.assert_report(expected_global, accepted['46']['results'])
    weekly_reference, _, weekly_global = calendar_association.reference(series, prices)
    calendar_association.assert_report(weekly_reference, accepted['47']['results'])
    association.assert_report(weekly_global, accepted['46']['results'])
    reconcile_reports(expected, expected_cells, expected_global)
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
    with tempfile.TemporaryDirectory(prefix='department-price-sales-', dir=tmp_root) as temp:
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
        run, cell_seconds = execute(database, folder, cell_sql)
        cells = weekly.parsed(run.stdout)
        assert_cells(cells, expected_cells)
        run, audit_seconds = execute(database, folder, audit)
        results = weekly.parsed(run.stdout)
        assert_report(results, expected)
        reconcile_reports(results, cells, expected_global)
        after = snapshot('after')
        assert before == after, 'Read-only department analysis changed a scoped input'
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
        independent_reference='Original-source csv/Decimal helpers reconstruct every weekly input field. Source department metadata and direct same-pair adjacent lookups form seven four-direction groups. Integer differences, distinct pair sets, sorted medians and Decimal half-up rounding verify all 28 internal cells across 14 fields and all seven displayed rows across 12 fields. Full-window statistics are recomputed from all differences, never group medians or unweighted means.',
        preflight_strategy='One bounded private database stages only 84 sales columns and twelve price weeks through unchanged SQL09/23/44. Unchanged SQL45/46/47 reports reconcile to accepted evidence. Historical guard suites/forecasting are not rerun; learner persistent database is never opened.',
        weekly_input_rows_compared=row_count, weekly_input_fields_compared=12, weekly_input_exact_mismatches=0,
        weekly_input_rows_sha256=input_hash, accepted_sql44_input_fingerprint_matched=True,
        pooled_rows_compared=pooled_count, pooled_fields_compared=8, pooled_rows_sha256=pooled_hash,
        price_rows_compared=price_count, price_fields_compared=4, transition_positions_evaluated=335390,
        sql45_rows_reconciled=12, sql45_fields_reconciled=12, sql45_accepted_report_matched=True,
        sql46_rows_reconciled=5, sql46_fields_reconciled=12, sql46_accepted_report_matched=True,
        sql47_rows_reconciled=11, sql47_fields_reconciled=12, sql47_accepted_report_matched=True,
        sql47_input_transition_guard_prefix_unchanged=True, sql46_aggregate_rounding_expressions_unchanged=True,
        internal_cell_rows_compared=28, internal_cell_fields_compared=14, internal_cell_exact_mismatches=0,
        internal_cell_sha256=weekly.canonical_hash([[row[key] for key in CELL_COLUMNS] for row in cells]),
        department_counts_pairs_and_unit_sums_reconciled=True, window_means_recomputed_from_exact_sums_and_counts=True,
        scoped_input_sha256_before=before, scoped_input_sha256_after=after, scoped_inputs_unchanged=True,
        historical_preflight_files_unchanged=len(historical), temporary_database_removed=True,
        temporary_database_bytes_after_close=database_bytes, fixture_case_count=len(cases), fixture_cases=cases,
        independent_source_read_seconds=reference_seconds, setup_seconds=setup_seconds,
        sql45_reconciliation_seconds=sql45_seconds, sql46_reconciliation_seconds=sql46_seconds,
        sql47_reconciliation_seconds=sql47_seconds, internal_cell_query_seconds=cell_seconds, audit_seconds=audit_seconds,
        timing_scope='One-run elapsed seconds; CLI timings exclude hashing/Python comparisons. DuckDB memory_limit is not a total-process cap.',
        report_rows=7, report_columns=12,
        report_sha256=weekly.canonical_hash([[row[key] for key in COLUMNS] for row in results]),
        report_fingerprint_contract='SHA-256 over ordered compact JSON arrays plus LF; counts/unit sums are integers, department identifiers are strings, displayed means are fixed-six-place strings or null. Internal cell means/medians use six places and percentages four.',
        results=results,
        scope='Assistant independent preflight only; learner SQL48 execution pending. Exploratory descriptive department breakdown across all eleven weeks, not a joint week-by-department adjustment or causal control. Product/store mix, timing and baseline demand can remain unequal. Adjacent observations overlap; all zero sales and missing endpoints remain included. No causal effect, elasticity, regression, significance test, promotion or anomaly claim. Public evidence contains aggregates and fingerprints only.')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, default=str) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps({'fixture_cases_passed': len(cases), 'weekly_input_rows_compared': row_count,
                      'audit_seconds': audit_seconds, 'results': results}), flush=True)


if __name__ == '__main__':
    main()
