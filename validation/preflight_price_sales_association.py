"""Bounded original-source verification of the fixed descriptive price-sales report."""
import argparse
import json
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

sys.dont_write_bytecode = True
import preflight_item_store_weekly_prices as weekly
import preflight_price_variation as variation


COLUMNS = ['price_direction', 'transitions', 'distinct_pairs', 'previous_units', 'current_units',
           'unit_difference', 'mean_unit_change', 'median_unit_change', 'sales_up_pct',
           'sales_down_pct', 'sales_unchanged_pct', 'check_status']
DIRECTIONS = ['UP', 'DOWN', 'UNCHANGED', 'MISSING_ENDPOINT', 'TOTAL']
PROTOCOL_SHA = 'f397cabcbf294ffc024ed88be5c777ab4ba18531db349d441f14e68ffb32119b'


def rounded(value, places):
    if value is None:
        return None
    return format(Decimal(value).quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP), f'.{places}f')


def summarize(records):
    """Records are (pair, price direction, previous integer units, current integer units)."""
    result = []
    for direction in DIRECTIONS:
        selected = records if direction == 'TOTAL' else [r for r in records if r[1] == direction]
        deltas = sorted(r[3] - r[2] for r in selected)
        count = len(deltas)
        median = None if not count else (Decimal(deltas[(count - 1) // 2]) + deltas[count // 2]) / 2
        percentages = [None if not count else rounded(Decimal(100) * sum(predicate(d) for d in deltas) / count, 4)
                       for predicate in [lambda d: d > 0, lambda d: d < 0, lambda d: d == 0]]
        result.append(dict(zip(COLUMNS, [direction, count, len({r[0] for r in selected}),
            sum(r[2] for r in selected), sum(r[3] for r in selected), sum(deltas),
            None if not count else rounded(Decimal(sum(deltas)) / count, 6), rounded(median, 6),
            *percentages, 'PASS'])))
    return result


def reference(series, prices):
    records = []
    for source in series:
        pair = source['item_id'], source['store_id']
        units = [sum(source['days'][7 * offset:7 * offset + 7]) for offset in range(12)]
        for offset in range(1, 12):
            previous = prices.get((*pair, 11600 + offset))
            current = prices.get((*pair, 11601 + offset))
            direction = ('MISSING_ENDPOINT' if previous is None or current is None else
                         'UP' if current > previous else 'DOWN' if current < previous else 'UNCHANGED')
            records.append((pair, direction, units[offset - 1], units[offset]))
    return summarize(records)


def assert_report(actual, expected):
    assert len(actual) == 5 and all(list(row) == COLUMNS for row in actual), 'Report shape/order mismatch'
    for row in actual:
        for key in COLUMNS[1:6]:
            value = Decimal(str(row[key]))
            assert value.is_finite() and value == int(value), 'Noninteger report control'
            row[key] = int(value)
        for key in COLUMNS[6:11]:
            value = row[key]
            if value is not None:
                decimal = Decimal(str(value))
                places = 6 if key in COLUMNS[6:8] else 4
                normalized = rounded(decimal, places)
                assert decimal == Decimal(normalized), 'SQL field exceeded frozen display precision'
                row[key] = normalized
        assert row['unit_difference'] == row['current_units'] - row['previous_units']
    assert actual == expected, 'Price-sales report differs from independent Decimal reference'
    for key in ['transitions', 'previous_units', 'current_units', 'unit_difference']:
        assert sum(row[key] for row in actual[:-1]) == actual[-1][key]


def fixture(mixed):
    setup, series, _ = weekly.fixture(all_zero=True)
    prices = {}
    setup += 'DELETE FROM stg.m5_prices;\n'
    for row in series:
        pair = row['item_id'], row['store_id']
        units = [0] * 12
        cents = [100 + 100 * int(row['store_id'][1:])] * 12
        if mixed and pair == ('P1', 'S1'):
            units = [0, 1, 0, 2] + [0] * 8
            cents = [100, 101, 100, 101] + [100] * 8
        elif mixed and pair == ('P1', 'S2'):
            units = [2] + [0] * 11
        elif mixed and pair == ('P2', 'S1'):
            cents = [None, 100, None] + [100] * 9
            units = [0, 3] + [0] * 10
        row['days'] = [u if day == 0 else 0 for u in units for day in range(7)]
        for offset, value in enumerate(units):
            if value:
                setup += (f'UPDATE mart.m5_sales_daily SET units={value} WHERE item_id={weekly.quote(pair[0])}'
                          f' AND store_id={weekly.quote(pair[1])} AND d={weekly.quote("d_" + str(1828 + 7 * offset))};\n')
        for offset, value in enumerate(cents):
            if value is not None:
                prices[(*pair, 11601 + offset)] = Decimal(value) / 100
    values = ','.join(f'({weekly.quote(store)},{weekly.quote(item)},{week},{price})'
                      for (item, store, week), price in prices.items())
    setup += 'INSERT INTO stg.m5_prices VALUES ' + values + ';\n'
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
    paths = ['sql/46_price_sales_association.sql', 'validation/preflight_price_sales_association.py',
             'docs/PRICE_SALES_ASSOCIATION_PROTOCOL.md', 'sql/09_stage_prices.sql',
             'sql/23_build_product_weekly.sql', 'sql/44_build_item_store_weekly_prices.sql',
             'validation/preflight_item_store_weekly_prices.py', 'sql/45_audit_price_variation.sql',
             'validation/preflight_price_variation.py', 'docs/PRICE_VARIATION_PROTOCOL.md',
             'data/price_variation_preflight.json', 'data/item_store_weekly_prices_preflight.json']
    hashes = {path: weekly.sha256(root / path) for path in paths}
    assert hashes[paths[2]] == PROTOCOL_SHA, 'Frozen protocol changed'
    audit = (root / paths[0]).read_text(encoding='utf-8')
    old_audit = (root / paths[7]).read_text(encoding='utf-8')
    # The original accepted-input checks are preserved byte-for-byte after text decoding.
    prefix = lambda sql: sql[sql.index('WITH parameters AS ('):sql.index('), lagged AS MATERIALIZED (')]
    assert prefix(audit) == prefix(old_audit), 'SQL45 accepted-input guard prefix changed'
    builds = {key: (root / path).read_text(encoding='utf-8').split('-- VALIDATION:', 1)[0]
              for key, path in [('09', paths[3]), ('23', paths[4]), ('44', paths[5])]}

    def execute(database, folder, query):
        assert database.resolve().is_relative_to(tmp_root.resolve())
        assert folder.resolve().is_relative_to(tmp_root.resolve())
        settings = f"SET threads=2; SET memory_limit='2GB'; SET temp_directory={weekly.quote((folder / 'spill').as_posix())};\n"
        started = time.perf_counter()
        run = subprocess.run([args.duckdb, str(database), '-bail', '-json'], input=settings + query,
                             text=True, encoding='utf-8', capture_output=True)
        assert run.returncode == 0, run.stderr
        return run, round(time.perf_counter() - started, 3)

    cases = []
    for mixed in [True, False]:
        setup, series, prices = fixture(mixed)
        expected = reference(series, prices)
        if mixed:
            assert [r['transitions'] for r in expected] == [2, 2, 59, 3, 66]
            assert [r['distinct_pairs'] for r in expected] == [1, 1, 6, 1, 6]
            assert expected[0]['median_unit_change'] == '1.500000'
            assert expected[1]['median_unit_change'] == '-1.500000'
            assert expected[2]['mean_unit_change'] == '-0.033898'
            assert [expected[3][k] for k in ['previous_units', 'current_units', 'unit_difference']] == [3, 3, 0]
            assert [expected[3][k] for k in COLUMNS[8:11]] == ['33.3333'] * 3
            assert [expected[-1][k] for k in ['previous_units', 'current_units', 'unit_difference']] == [8, 6, -2]
        else:
            assert [r['transitions'] for r in expected] == [0, 0, 66, 0, 66]
            assert all(expected[0][key] is None for key in COLUMNS[6:11])
        expected_units = sum(sum(r['days']) for r in series)
        transform = lambda sql: sql.replace('3049 AS expected_items,10 AS expected_stores',
                                            '3 AS expected_items,2 AS expected_stores').replace(
                                                '3536539 AS expected_units', f'{expected_units} AS expected_units')
        with tempfile.TemporaryDirectory(prefix='association-case-', dir=tmp_root) as temp:
            folder = Path(temp)
            database = folder / 'case.duckdb'
            execute(database, folder, setup + transform(builds['23']) + transform(builds['44']))
            run, _ = execute(database, folder, transform(audit))
            assert_report(weekly.parsed(run.stdout), expected)
        assert not folder.exists()
        cases.append(dict(case=('zero_endpoints_signed_half_medians_missing_gaps_store_separation_nonadditive_pairs'
                                if mixed else 'all_zero_unchanged_with_three_empty_categories'), passed=True))

    # Exercise the actual production aggregate/report CTEs at exact half-rounding ties.
    aggregate_ctes = audit[audit.index('), categories('):audit.index('), report_health AS (')] + ')\n'
    rounding_records = [(('P', direction), direction, 1, 1 + (sign if n == 0 else 0))
                        for direction, sign in [('UP', 1), ('DOWN', -1)] for n in range(128)]
    rounding_sql = """WITH transitions AS (
    SELECT 'P' AS item_id,direction AS store_id,direction AS price_direction,1::HUGEINT AS previous_units,
        (1+CASE WHEN n=0 THEN sign ELSE 0 END)::HUGEINT AS units,
        (CASE WHEN n=0 THEN sign ELSE 0 END)::HUGEINT AS unit_change
    FROM (VALUES ('UP',1),('DOWN',-1)) v(direction,sign) CROSS JOIN range(128) t(n)
""" + aggregate_ctes + 'SELECT ' + ','.join('r.' + key for key in COLUMNS[:-1]) + ", 'PASS' AS check_status FROM report r ORDER BY sort_order;"
    with tempfile.TemporaryDirectory(prefix='association-rounding-', dir=tmp_root) as temp:
        folder = Path(temp)
        run, _ = execute(folder / 'case.duckdb', folder, rounding_sql)
        expected = summarize(rounding_records)
        assert expected[0]['mean_unit_change'] == '0.007813' and expected[1]['mean_unit_change'] == '-0.007813'
        assert expected[0]['sales_up_pct'] == '0.7813' and expected[1]['sales_down_pct'] == '0.7813'
        assert_report(weekly.parsed(run.stdout), expected)
    assert not folder.exists()
    cases.append(dict(case='production_aggregates_exact_positive_negative_mean_and_percentage_half_rounding', passed=True))
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
    expected = reference(series, prices)
    accepted_variation = json.loads((root / paths[10]).read_text(encoding='utf-8'))
    accepted_weekly = json.loads((root / paths[11]).read_text(encoding='utf-8'))
    variation.assert_report(variation.reference(series, prices), accepted_variation['results'])
    assert [r['transitions'] for r in expected] == [accepted_variation['results'][-1][key] for key in
        ['price_up_transitions', 'price_down_transitions', 'unchanged_price_transitions',
         'missing_endpoint_transitions', 'potential_transitions']]
    weekly_totals = weekly.report_reference(series, prices)
    assert expected[-1]['previous_units'] == weekly_totals[-1]['units'] - weekly_totals[-2]['units']
    assert expected[-1]['current_units'] == weekly_totals[-1]['units'] - weekly_totals[0]['units']
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
    with tempfile.TemporaryDirectory(prefix='price-sales-association-', dir=tmp_root) as temp:
        folder = Path(temp)
        database = folder / 'preflight.duckdb'
        _, setup_seconds = execute(database, folder, setup + builds['09'] + builds['23'] + builds['44'])

        def snapshot(prefix_name):
            results = {}
            # One process and database open for all seven bounded read-only exports.
            query = ''.join(f'COPY ({query}) TO {weekly.quote((folder / (prefix_name + "_" + name + ".csv")).as_posix())} (HEADER,FORMAT CSV);\n'
                            for name, query in snapshots.items())
            execute(database, folder, query)
            for name in snapshots:
                results[name] = weekly.sha256(folder / f'{prefix_name}_{name}.csv')
            return results

        before = snapshot('before')
        row_count, input_hash = weekly.compare_export(folder / 'before_weekly_input.csv', weekly.expected_rows(series, prices))
        assert row_count == 365880 and input_hash == weekly.canonical_hash(weekly.expected_rows(series, prices))
        assert input_hash == accepted_weekly['stored_rows_sha256'], 'SQL44 accepted weekly input fingerprint changed'
        pooled_count, pooled_hash = weekly.compare_pooled_export(folder / 'before_pooled_input.csv', series)
        price_count = weekly.compare_price_export(folder / 'before_prices_12w.csv', prices)
        old_run, old_seconds = execute(database, folder, old_audit)
        old_results = weekly.parsed(old_run.stdout)
        variation.assert_report(old_results, accepted_variation['results'])
        run, audit_seconds = execute(database, folder, audit)
        results = weekly.parsed(run.stdout)
        assert_report(results, expected)
        after = snapshot('after')
        assert before == after, 'Read-only association query changed a scoped input'
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
        independent_reference='Original-source Python csv/Decimal SQL44 helpers derive the complete weekly input. Direct adjacent weekly unit and exact-price lookups independently classify every transition; sorted integer changes determine medians, Decimal arithmetic determines means and percentages, and ROUND_HALF_UP fixes final 6/4 decimal strings. Every report field and order compares exactly.',
        preflight_strategy='One private bounded database stages only 84 sales columns and twelve price weeks through unchanged SQL09/23/44. Unchanged SQL45 is reconciled in full to its published evidence. Historical guard suites and forecasting are not rerun; learner persistent database is never opened.',
        weekly_input_rows_compared=row_count, weekly_input_fields_compared=12, weekly_input_exact_mismatches=0,
        weekly_input_rows_sha256=input_hash, accepted_sql44_input_fingerprint_matched=True,
        pooled_rows_compared=pooled_count, pooled_fields_compared=8, pooled_rows_sha256=pooled_hash,
        price_rows_compared=price_count, price_fields_compared=4, transition_positions_evaluated=335390,
        sql45_rows_reconciled=12, sql45_fields_reconciled=12, sql45_accepted_report_matched=True,
        sql45_input_guard_prefix_unchanged=True, endpoint_totals_reconciled_to_first_last_weeks=True,
        scoped_input_sha256_before=before, scoped_input_sha256_after=after, scoped_inputs_unchanged=True,
        historical_preflight_files_unchanged=len(historical), temporary_database_removed=True,
        temporary_database_bytes_after_close=database_bytes, fixture_case_count=len(cases), fixture_cases=cases,
        independent_source_read_seconds=reference_seconds, setup_seconds=setup_seconds,
        sql45_reconciliation_seconds=old_seconds, audit_seconds=audit_seconds,
        timing_scope='One-run elapsed seconds; CLI timings exclude hashing/Python comparisons. DuckDB memory_limit is not a total-process cap.',
        report_rows=5, report_columns=12,
        report_sha256=weekly.canonical_hash([[row[key] for key in COLUMNS] for row in results]),
        report_fingerprint_contract='SHA-256 over ordered compact JSON arrays plus LF; counts/unit sums are integers, mean/median are fixed-six-place strings, percentages are fixed-four-place strings, empty statistics are null.',
        results=results,
        scope='Assistant independent preflight only; learner SQL46 execution pending. Descriptive association only; unchanged price is not a causal control, repeated adjacent observations overlap, group mix/calendar can confound comparisons. All zero sales and missing endpoints remain included. No causal effect, elasticity, regression, significance test, promotion or anomaly claim. Public output contains aggregates and fingerprints only.')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, default=str) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps({'fixture_cases_passed': len(cases), 'weekly_input_rows_compared': row_count,
                      'audit_seconds': audit_seconds, 'results': results}), flush=True)


if __name__ == '__main__':
    main()
