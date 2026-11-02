"""Verify the frozen weekly price-sales breakdown from original sources in a bounded private database."""
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


COLUMNS = ['retail_week', 'week_start', 'price_up_transitions', 'price_up_mean_unit_change',
           'price_down_transitions', 'price_down_mean_unit_change', 'unchanged_transitions',
           'unchanged_mean_unit_change', 'missing_endpoint_transitions', 'total_transitions',
           'total_unit_difference', 'check_status']
CELL_COLUMNS = ['retail_week', 'week_start', *association.COLUMNS]
MEANS = ['price_up_mean_unit_change', 'price_down_mean_unit_change', 'unchanged_mean_unit_change']
PROTOCOL_SHA = '3abebf3728fd1b208ea6b2fc1a2be0c973beb1668500435022d53d9259dc4479'


def reference(series, prices):
    """Independent direct lookups retain every source pair/week and missing endpoint."""
    buckets = {11601 + offset: [] for offset in range(1, 12)}
    all_records = []
    for source in series:
        pair = source['item_id'], source['store_id']
        units = [sum(source['days'][7 * offset:7 * offset + 7]) for offset in range(12)]
        for offset in range(1, 12):
            previous = prices.get((*pair, 11600 + offset))
            current = prices.get((*pair, 11601 + offset))
            direction = ('MISSING_ENDPOINT' if previous is None or current is None else
                         'UP' if current > previous else 'DOWN' if current < previous else 'UNCHANGED')
            record = (pair, direction, units[offset - 1], units[offset])
            buckets[11601 + offset].append(record)
            all_records.append(record)
    report, cells = [], []
    for week, records in buckets.items():
        start = (weekly.START + timedelta(days=7 * (week - 11601))).isoformat()
        groups = association.summarize(records)
        cells.extend(dict(retail_week=str(week), week_start=start, **group) for group in groups[:-1])
        report.append(dict(zip(COLUMNS, [str(week), start,
            groups[0]['transitions'], groups[0]['mean_unit_change'],
            groups[1]['transitions'], groups[1]['mean_unit_change'],
            groups[2]['transitions'], groups[2]['mean_unit_change'],
            groups[3]['transitions'], groups[4]['transitions'], groups[4]['unit_difference'], 'PASS'])))
    return report, cells, association.summarize(all_records)


def normalize_integer(row, key):
    value = Decimal(str(row[key]))
    assert value.is_finite() and value == int(value), 'Noninteger report count or unit sum'
    row[key] = int(value)


def normalize_decimal(row, key, places):
    if row[key] is not None:
        value = Decimal(str(row[key]))
        assert value.is_finite()
        fixed = association.rounded(value, places)
        assert value == Decimal(fixed), 'SQL output exceeded frozen precision'
        row[key] = fixed


def assert_report(actual, expected):
    assert len(actual) == 11 and all(list(row) == COLUMNS for row in actual), 'Weekly report shape/order mismatch'
    for row in actual:
        for key in COLUMNS[2:-1]:
            if key in MEANS:
                normalize_decimal(row, key, 6)
            else:
                normalize_integer(row, key)
        assert row['total_transitions'] == sum(row[key] for key in
            ['price_up_transitions', 'price_down_transitions', 'unchanged_transitions', 'missing_endpoint_transitions'])
    assert actual == expected, 'Weekly report differs from independent original-source reference'


def assert_cells(actual, expected):
    assert len(actual) == 44 and all(list(row) == CELL_COLUMNS for row in actual), 'Internal weekly cell shape/order mismatch'
    for row in actual:
        for key in association.COLUMNS[1:6]:
            normalize_integer(row, key)
        for key in association.COLUMNS[6:11]:
            normalize_decimal(row, key, 6 if key in association.COLUMNS[6:8] else 4)
        assert row['distinct_pairs'] == row['transitions']
        assert row['unit_difference'] == row['current_units'] - row['previous_units']
    assert actual == expected, 'Internal 44-cell report differs from independent reference'


def concentrated_fixture():
    setup, series, prices = association.fixture(False)
    for row in series:
        pair = row['item_id'], row['store_id']
        if pair == ('P1', 'S1'):
            units, cents = [0, 1, 0, 3] + [0] * 8, [100, 101, 100, 101] + [100] * 8
        elif pair == ('P1', 'S2'):
            units, cents = [0, 0, 0, 5] + [0] * 8, [200] * 3 + [201] * 9
        else:
            continue
        row['days'] = [u if day == 0 else 0 for u in units for day in range(7)]
        for offset, units_value in enumerate(units):
            setup += (f'UPDATE mart.m5_sales_daily SET units={units_value} WHERE item_id={weekly.quote(pair[0])}'
                      f' AND store_id={weekly.quote(pair[1])} AND d={weekly.quote("d_" + str(1828 + 7 * offset))};\n')
            price = Decimal(cents[offset]) / 100
            prices[(*pair, 11601 + offset)] = price
            setup += (f'UPDATE stg.m5_prices SET sell_price={price} WHERE item_id={weekly.quote(pair[0])}'
                      f' AND store_id={weekly.quote(pair[1])} AND wm_yr_wk={11601 + offset};\n')
    return setup, series, prices


def reconcile_reports(report, cells, global_report, price_report):
    for row, old in zip(report, price_report[:-1]):
        assert row['retail_week'] == old['retail_week'] and row['week_start'] == old['week_start']
        assert [row[key] for key in ['price_up_transitions', 'price_down_transitions', 'unchanged_transitions',
                                    'missing_endpoint_transitions', 'total_transitions']] == [old[key] for key in
            ['price_up_transitions', 'price_down_transitions', 'unchanged_price_transitions',
             'missing_endpoint_transitions', 'potential_transitions']]
    for group in global_report[:-1]:
        selected = [row for row in cells if row['price_direction'] == group['price_direction']]
        for key in ['transitions', 'previous_units', 'current_units', 'unit_difference']:
            assert sum(row[key] for row in selected) == group[key]
        # Reconstruct the window mean using exact sums and counts, never rounded weekly means.
        n = sum(row['transitions'] for row in selected)
        exact_mean = None if not n else association.rounded(Decimal(sum(row['unit_difference'] for row in selected)) / n, 6)
        assert exact_mean == group['mean_unit_change']
    assert sum(row['total_transitions'] for row in report) == global_report[-1]['transitions']
    assert sum(row['total_unit_difference'] for row in report) == global_report[-1]['unit_difference']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--duckdb', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--fixtures-only', action='store_true')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    tmp_root = root / 'tmp'
    tmp_root.mkdir(exist_ok=True)
    paths = ['sql/47_weekly_price_sales_association.sql', 'validation/preflight_weekly_price_sales_association.py',
             'docs/WEEKLY_PRICE_SALES_ASSOCIATION_PROTOCOL.md', 'sql/09_stage_prices.sql',
             'sql/23_build_product_weekly.sql', 'sql/44_build_item_store_weekly_prices.sql',
             'validation/preflight_item_store_weekly_prices.py', 'sql/45_audit_price_variation.sql',
             'validation/preflight_price_variation.py', 'sql/46_price_sales_association.sql',
             'validation/preflight_price_sales_association.py', 'docs/PRICE_SALES_ASSOCIATION_PROTOCOL.md',
             'data/price_variation_preflight.json', 'data/item_store_weekly_prices_preflight.json',
             'data/price_sales_association_preflight.json', 'docs/PRICE_VARIATION_PROTOCOL.md']
    hashes = {path: weekly.sha256(root / path) for path in paths}
    assert hashes[paths[2]] == PROTOCOL_SHA, 'Frozen weekly protocol changed'
    audit = (root / paths[0]).read_text(encoding='utf-8')
    prior_sql = {number: (root / path).read_text(encoding='utf-8') for number, path in
                 [('45', paths[7]), ('46', paths[9])]}
    prefix = lambda sql: sql[sql.index('WITH parameters AS ('):sql.index('), categories(')]
    assert prefix(audit) == prefix(prior_sql['46']), 'SQL46 accepted-input/transition checks changed'
    measures = lambda sql: sql[sql.index('        COUNT(*) AS transitions'):sql.index('\n    FROM transitions GROUP BY')]
    assert measures(audit) == measures(prior_sql['46']), 'Accepted aggregate expressions changed'
    percentages = lambda sql: sql[sql.index('        CAST(ROUND(100.0*a.sales_up'):sql.index('        COALESCE(a.sales_up,0)')]
    assert percentages(audit) == percentages(prior_sql['46']), 'Accepted percentage rounding expressions changed'
    # Expose only aggregate cells with the identical production guards; no extra persistent table.
    cell_sql = audit[:audit.rindex('\nSELECT CAST(r.wm_yr_wk')] + """
SELECT CAST(r.wm_yr_wk AS VARCHAR) AS retail_week,r.week_start,
""" + ','.join('r.' + key for key in association.COLUMNS[:-1]) + """,
    CASE WHEN COALESCE(i.passed AND t.passed AND h.passed,false) THEN 'PASS'
         ELSE error('Weekly price-sales internal cells blocked') END AS check_status
FROM input_health i CROSS JOIN transition_health t CROSS JOIN report_health h
LEFT JOIN cells r ON true
ORDER BY r.week_start,r.sort_order;
"""
    builds = {key: (root / path).read_text(encoding='utf-8').split('-- VALIDATION:', 1)[0]
              for key, path in [('09', paths[3]), ('23', paths[4]), ('44', paths[5])]}

    def execute(database, folder, query, allow_error=False):
        assert database.resolve().is_relative_to(tmp_root.resolve()) and folder.resolve().is_relative_to(tmp_root.resolve())
        settings = f"SET threads=2; SET memory_limit='2GB'; SET temp_directory={weekly.quote((folder / 'spill').as_posix())};\n"
        started = time.perf_counter()
        run = subprocess.run([args.duckdb, str(database), '-bail', '-json'], input=settings + query,
                             text=True, encoding='utf-8', capture_output=True)
        if not allow_error:
            assert run.returncode == 0, run.stderr
        return run, round(time.perf_counter() - started, 3)

    cases = []
    for case in ['mixed_zero_endpoints_missing_gaps_and_half_medians', 'all_zero_empty_week_groups',
                 'calendar_concentration_unequal_support_requires_weighted_mean']:
        setup, series, prices = (concentrated_fixture() if case.startswith('calendar')
                                  else association.fixture(case.startswith('mixed')))
        expected, expected_cells, expected_global = reference(series, prices)
        reconcile_reports(expected, expected_cells, expected_global, variation.reference(series, prices))
        if case.startswith('mixed'):
            assert expected[0]['price_up_mean_unit_change'] == '1.000000'
            assert expected[2]['price_up_mean_unit_change'] == '2.000000'
            assert expected_global[0]['median_unit_change'] == '1.500000'
            assert expected_global[1]['median_unit_change'] == '-1.500000'
            missing = [row for row in expected_cells if row['price_direction'] == 'MISSING_ENDPOINT']
            assert [row['unit_difference'] for row in missing[:3]] == [3, -3, 0]
            assert [row['transitions'] for row in missing[:4]] == [1, 1, 1, 0]
        elif case.startswith('all_zero'):
            assert all(row['price_up_transitions'] == 0 and row['price_up_mean_unit_change'] is None
                       and row['price_down_transitions'] == 0 and row['price_down_mean_unit_change'] is None
                       and row['unchanged_transitions'] == 6 and row['unchanged_mean_unit_change'] == '0.000000'
                       and row['missing_endpoint_transitions'] == 0 and row['total_unit_difference'] == 0 for row in expected)
        else:
            assert [(expected[i]['price_up_transitions'], expected[i]['price_up_mean_unit_change'])
                    for i in [0, 2]] == [(1, '1.000000'), (2, '4.000000')]
            assert expected_global[0]['mean_unit_change'] == '3.000000'
            assert (Decimal(expected[0]['price_up_mean_unit_change']) + Decimal(expected[2]['price_up_mean_unit_change'])) / 2 == Decimal('2.5')
            assert expected_cells[8]['median_unit_change'] == '4.000000'
        expected_units = sum(sum(row['days']) for row in series)
        transform = lambda sql: sql.replace('3049 AS expected_items,10 AS expected_stores',
                                            '3 AS expected_items,2 AS expected_stores').replace(
                                                '3536539 AS expected_units', f'{expected_units} AS expected_units')
        with tempfile.TemporaryDirectory(prefix='weekly-association-case-', dir=tmp_root) as temp:
            folder = Path(temp)
            database = folder / 'case.duckdb'
            execute(database, folder, setup + transform(builds['23']) + transform(builds['44']))
            run, _ = execute(database, folder, transform(audit))
            assert_report(weekly.parsed(run.stdout), expected)
            run, _ = execute(database, folder, transform(cell_sql))
            assert_cells(weekly.parsed(run.stdout), expected_cells)
            if case.startswith('all_zero'):
                rejected, _ = execute(database, folder, 'DELETE FROM core.m5_calendar;\n' + transform(audit), allow_error=True)
                assert rejected.returncode != 0 and 'Weekly price-sales association blocked' in rejected.stderr, 'Empty calendar silently suppressed validation'
                cases.append(dict(case='empty_calendar_scaffold_rejected_instead_of_silent_zero_rows', passed=True, expected_rejection=True))
        assert not folder.exists()
        cases.append(dict(case=case, passed=True))
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
    accepted_variation = json.loads((root / paths[12]).read_text(encoding='utf-8'))
    accepted_weekly = json.loads((root / paths[13]).read_text(encoding='utf-8'))
    accepted_association = json.loads((root / paths[14]).read_text(encoding='utf-8'))
    variation.assert_report(variation.reference(series, prices), accepted_variation['results'])
    association.assert_report(expected_global, accepted_association['results'])
    reconcile_reports(expected, expected_cells, expected_global, accepted_variation['results'])
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
    with tempfile.TemporaryDirectory(prefix='weekly-price-sales-', dir=tmp_root) as temp:
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
        assert input_hash == accepted_weekly['stored_rows_sha256'], 'SQL44 accepted input fingerprint changed'
        pooled_count, pooled_hash = weekly.compare_pooled_export(folder / 'before_pooled_input.csv', series)
        price_count = weekly.compare_price_export(folder / 'before_prices_12w.csv', prices)
        run, sql45_seconds = execute(database, folder, prior_sql['45'])
        variation.assert_report(weekly.parsed(run.stdout), accepted_variation['results'])
        run, sql46_seconds = execute(database, folder, prior_sql['46'])
        association.assert_report(weekly.parsed(run.stdout), accepted_association['results'])
        run, cell_seconds = execute(database, folder, cell_sql)
        cells = weekly.parsed(run.stdout)
        assert_cells(cells, expected_cells)
        run, audit_seconds = execute(database, folder, audit)
        results = weekly.parsed(run.stdout)
        assert_report(results, expected)
        reconcile_reports(results, cells, expected_global, accepted_variation['results'])
        after = snapshot('after')
        assert before == after, 'Read-only weekly analysis changed a scoped input'
        database_bytes = database.stat().st_size
    assert not folder.exists()
    assert all(weekly.sha256(path) == source_hashes[name] for name, path in sources.items())
    assert all(weekly.sha256(root / path) == value for path, value in historical.items())
    assert all(weekly.sha256(root / path) == value for path, value in hashes.items())
    evidence = dict(
        checked_at_utc=datetime.now(timezone.utc).isoformat(), executor='assistant',
        engine=subprocess.check_output([args.duckdb, '-version'], text=True).strip(),
        script=paths[0], script_sha256=hashes[paths[0]], validator=paths[1], validator_sha256=hashes[paths[1]],
        protocol=paths[2], protocol_sha256=PROTOCOL_SHA, code_and_dependency_sha256=hashes,
        settings={'threads': 2, 'memory_limit': '2GB'}, source_sha256=source_hashes,
        source_hashes_unchanged=True, source_controls=controls,
        input_window={'start_date': '2016-01-30', 'end_date': '2016-04-22', 'weeks': 12, 'pairs': 30490},
        report_window={'first_current_week': 11602, 'last_current_week': 11612,
                       'start_date': '2016-02-06', 'end_date': '2016-04-22'},
        independent_reference='Original-source csv/Decimal helpers reconstruct every weekly input field. Direct same-pair adjacent lookups independently form eleven four-direction groups. Integer differences, sorted medians and Decimal half-up rounding verify all 44 internal cells across 14 fields and all 11 displayed rows across 12 fields. Full-window statistics are independently recomputed from all differences, never weekly medians or unweighted weekly means.',
        preflight_strategy='One bounded private database stages only 84 sales columns and twelve price weeks through unchanged SQL09/23/44. Unchanged SQL45/46 reports reconcile to accepted evidence. Historical guard suites/forecasting are not rerun; learner persistent database is never opened.',
        weekly_input_rows_compared=row_count, weekly_input_fields_compared=12, weekly_input_exact_mismatches=0,
        weekly_input_rows_sha256=input_hash, accepted_sql44_input_fingerprint_matched=True,
        pooled_rows_compared=pooled_count, pooled_fields_compared=8, pooled_rows_sha256=pooled_hash,
        price_rows_compared=price_count, price_fields_compared=4, transition_positions_evaluated=335390,
        sql45_rows_reconciled=12, sql45_fields_reconciled=12, sql45_accepted_report_matched=True,
        sql46_rows_reconciled=5, sql46_fields_reconciled=12, sql46_accepted_report_matched=True,
        sql46_input_transition_guard_prefix_unchanged=True, sql46_aggregate_rounding_expressions_unchanged=True,
        internal_cell_rows_compared=44, internal_cell_fields_compared=14, internal_cell_exact_mismatches=0,
        internal_cell_sha256=weekly.canonical_hash([[row[key] for key in CELL_COLUMNS] for row in cells]),
        weekly_counts_and_unit_sums_reconciled=True, window_means_recomputed_from_exact_sums_and_counts=True,
        scoped_input_sha256_before=before, scoped_input_sha256_after=after, scoped_inputs_unchanged=True,
        historical_preflight_files_unchanged=len(historical), temporary_database_removed=True,
        temporary_database_bytes_after_close=database_bytes, fixture_case_count=len(cases), fixture_cases=cases,
        independent_source_read_seconds=reference_seconds, setup_seconds=setup_seconds,
        sql45_reconciliation_seconds=sql45_seconds, sql46_reconciliation_seconds=sql46_seconds,
        internal_cell_query_seconds=cell_seconds, audit_seconds=audit_seconds,
        timing_scope='One-run elapsed seconds; CLI timings exclude hashing/Python comparisons. DuckDB memory_limit is not a total-process cap.',
        report_rows=11, report_columns=12,
        report_sha256=weekly.canonical_hash([[row[key] for key in COLUMNS] for row in results]),
        report_fingerprint_contract='SHA-256 over ordered compact JSON arrays plus LF; counts/unit sums are integers, week identifiers and ISO dates are strings, displayed means are fixed-six-place strings or null. Internal cell means/medians use six places and percentages four.',
        results=results,
        scope='Assistant independent preflight only; learner SQL47 execution pending. Descriptive calendar breakdown only; same-week groups have unequal product/store mix and are not causal controls. Adjacent observations overlap; all zero sales and missing endpoints remain included. No causal effect, elasticity, regression, significance test, promotion or anomaly claim. Public evidence contains aggregates and fingerprints only.')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, default=str) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps({'fixture_cases_passed': len(cases), 'weekly_input_rows_compared': row_count,
                      'audit_seconds': audit_seconds, 'results': results}), flush=True)


if __name__ == '__main__':
    main()
