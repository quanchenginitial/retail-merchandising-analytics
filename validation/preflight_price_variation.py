"""Bounded, independent source verification of the read-only adjacent-week price audit."""
import argparse
import json
import subprocess
import sys
import tempfile
import time
from datetime import timedelta, datetime, timezone
from decimal import Decimal
from pathlib import Path

sys.dont_write_bytecode = True
import preflight_item_store_weekly_prices as weekly


COLUMNS = ['retail_week', 'week_start', 'week_end', 'potential_transitions', 'comparable_transitions',
           'missing_endpoint_transitions', 'price_up_transitions', 'price_down_transitions',
           'unchanged_price_transitions', 'comparable_pairs', 'changed_pairs', 'check_status']
PROTOCOL_SHA = '6f2f1e11f0467c4cd0337ae93b3a7a867a5412c525f54667bc203968d33ebba4'


def reference(series, prices):
    """Direct adjacent lookups from original pair membership; no SQL output defines the reference."""
    result, all_comparable, all_changed = [], set(), set()
    for offset in range(1, 12):
        comparable, changed = set(), set()
        up = down = unchanged = 0
        for source in series:
            pair = source['item_id'], source['store_id']
            prior = prices.get((*pair, 11600 + offset))
            current = prices.get((*pair, 11601 + offset))
            if prior is None or current is None:
                continue
            comparable.add(pair)
            if current > prior:
                up += 1
                changed.add(pair)
            elif current < prior:
                down += 1
                changed.add(pair)
            else:
                unchanged += 1
        all_comparable |= comparable
        all_changed |= changed
        start = weekly.START + timedelta(days=7 * offset)
        result.append(dict(zip(COLUMNS, [str(11601 + offset), start.isoformat(),
            (start + timedelta(days=6)).isoformat(), len(series), len(comparable),
            len(series) - len(comparable), up, down, unchanged, len(comparable), len(changed), 'PASS'])))
    total = dict(retail_week='TOTAL', week_start=result[0]['week_start'], week_end=result[-1]['week_end'])
    total.update({key: sum(row[key] for row in result) for key in COLUMNS[3:9]})
    total.update(comparable_pairs=len(all_comparable), changed_pairs=len(all_changed), check_status='PASS')
    result.append(total)
    return result


def assert_report(actual, expected):
    assert len(actual) == 12 and all(list(row) == COLUMNS for row in actual), 'Report shape/order mismatch'
    for row in actual:
        for key in COLUMNS[3:-1]:
            value = Decimal(str(row[key]))
            assert value.is_finite() and value == int(value), 'Noninteger transition count'
            row[key] = int(value)
        assert row['comparable_transitions'] + row['missing_endpoint_transitions'] == row['potential_transitions']
        assert row['price_up_transitions'] + row['price_down_transitions'] + row['unchanged_price_transitions'] == row['comparable_transitions']
        assert 0 <= row['changed_pairs'] <= row['comparable_pairs']
        if row['retail_week'] != 'TOTAL':
            assert row['comparable_pairs'] == row['comparable_transitions']
            assert row['changed_pairs'] == row['price_up_transitions'] + row['price_down_transitions']
    assert actual == expected, 'Price variation report differs from independent reference'


def fixture(pattern):
    setup, series, _ = weekly.fixture(all_zero=True)
    prices = {}
    for row in series:
        pair = row['item_id'], row['store_id']
        if pattern == 'unchanged':
            values = [100 + 100 * int(row['store_id'][1:])] * 12
        elif pattern == 'missing':
            values = [None] * 12
        else:
            values = {('P1', 'S1'): [100, 101] + [100] * 10,
                      ('P1', 'S2'): [200] * 12,
                      ('P2', 'S1'): [None, 100, 101, None] + [102] * 8,
                      ('P2', 'S2'): [100] * 12}.get(pair, [None] * 12)
        for offset, cents in enumerate(values):
            if cents is not None:
                prices[(*pair, 11601 + offset)] = Decimal(cents) / 100
    setup += 'DELETE FROM stg.m5_prices;\n'
    if prices:
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
    paths = ['sql/45_audit_price_variation.sql', 'validation/preflight_price_variation.py',
             'docs/PRICE_VARIATION_PROTOCOL.md', 'sql/09_stage_prices.sql', 'sql/23_build_product_weekly.sql',
             'sql/44_build_item_store_weekly_prices.sql', 'validation/preflight_item_store_weekly_prices.py']
    code_hashes = {path: weekly.sha256(root / path) for path in paths}
    assert code_hashes['docs/PRICE_VARIATION_PROTOCOL.md'] == PROTOCOL_SHA
    audit = (root / paths[0]).read_text(encoding='utf-8')
    builds = {number: (root / path).read_text(encoding='utf-8').split('-- VALIDATION:', 1)[0]
              for number, path in [('09', paths[3]), ('23', paths[4]), ('44', paths[5])]}

    def execute(database, folder, query, allow_error=False):
        assert database.resolve().is_relative_to(tmp_root.resolve())
        settings = f"SET threads=2; SET memory_limit='2GB'; SET temp_directory={weekly.quote((folder / 'spill').as_posix())};\n"
        started = time.perf_counter()
        run = subprocess.run([args.duckdb, str(database), '-bail', '-json'], input=settings + query,
                             text=True, encoding='utf-8', capture_output=True)
        if not allow_error:
            assert run.returncode == 0, run.stderr
        return run, round(time.perf_counter() - started, 3)

    cases = []
    fixture_cases = [
        ('mixed_adjacent_boundaries_exact_cents_return_zero_sales_store_separation', 'mixed', ''),
        ('all_unchanged_different_store_prices', 'unchanged', ''),
        ('all_missing_zero_sales', 'missing', ''),
        ('reversed_input_order', 'mixed', 'reverse'),
        ('empty_input_rejected', 'mixed', f'DELETE FROM {weekly.TARGET};'),
        ('duplicate_replaces_missing_week_rejected', 'mixed', f"UPDATE {weekly.TARGET} SET wm_yr_wk=11602 WHERE item_id='P1' AND store_id='S1' AND wm_yr_wk=11601;"),
        ('stored_price_mismatch_rejected', 'mixed', f"UPDATE {weekly.TARGET} SET sell_price=1.00 WHERE item_id='P1' AND store_id='S1' AND wm_yr_wk=11602;"),
        ('weekly_price_type_rejected', 'mixed', f'ALTER TABLE {weekly.TARGET} ALTER sell_price TYPE DOUBLE;'),
        ('invalid_present_price_at_zero_sales_rejected', 'mixed', "UPDATE stg.m5_prices SET sell_price=NULL WHERE item_id='P1' AND store_id='S1' AND wm_yr_wk=11601;"),
    ]
    transform = lambda text: text.replace('3049 AS expected_items,10 AS expected_stores', '3 AS expected_items,2 AS expected_stores').replace('3536539 AS expected_units', '0 AS expected_units')
    for name, pattern, mutation in fixture_cases:
        setup, series, prices = fixture(pattern)
        expected = reference(series, prices)
        if pattern == 'mixed':
            assert [expected[-1][key] for key in COLUMNS[3:-1]] == [66, 41, 25, 2, 1, 38, 4, 2], 'Hand-counted mixed fixture failed'
        rejected = bool(mutation and mutation != 'reverse')
        with tempfile.TemporaryDirectory(prefix='variation-case-', dir=tmp_root) as name_dir:
            folder = Path(name_dir)
            assert folder.resolve().is_relative_to(tmp_root.resolve())
            database = folder / 'case.duckdb'
            execute(database, folder, setup + transform(builds['23']) + transform(builds['44']))
            if mutation == 'reverse':
                mutation = f'CREATE TABLE mart.reversed AS SELECT * FROM {weekly.TARGET} ORDER BY item_id DESC,store_id DESC,wm_yr_wk DESC; DROP TABLE {weekly.TARGET}; ALTER TABLE mart.reversed RENAME TO m5_item_store_weekly_prices_12w;'
            run, _ = execute(database, folder, mutation + transform(audit), allow_error=rejected)
            if rejected:
                assert run.returncode != 0 and 'Price variation audit blocked' in run.stderr, 'Intended audit guard did not reject fixture'
            else:
                assert_report(weekly.parsed(run.stdout), expected)
        assert not folder.exists()
        cases.append(dict(case=name, passed=True, expected_rejection=rejected))
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
    with tempfile.TemporaryDirectory(prefix='price-variation-', dir=tmp_root) as name_dir:
        folder = Path(name_dir)
        assert folder.resolve().is_relative_to(tmp_root.resolve())
        database = folder / 'preflight.duckdb'
        _, setup_seconds = execute(database, folder, setup + builds['09'] + builds['23'] + builds['44'])

        def snapshot(prefix):
            result = {}
            for name, query in snapshots.items():
                path = folder / f'{prefix}_{name}.csv'
                execute(database, folder, f'COPY ({query}) TO {weekly.quote(path.as_posix())} (HEADER,FORMAT CSV);')
                result[name] = weekly.sha256(path)
            return result

        before = snapshot('before')
        rows_compared, input_hash = weekly.compare_export(folder / 'before_weekly_input.csv', weekly.expected_rows(series, prices))
        assert rows_compared == 365880 and input_hash == weekly.canonical_hash(weekly.expected_rows(series, prices))
        accepted_preflight = json.loads((root / 'data/item_store_weekly_prices_preflight.json').read_text(encoding='utf-8'))
        assert input_hash == accepted_preflight['stored_rows_sha256'], 'SQL44 original input fingerprint changed'
        pooled_count, pooled_hash = weekly.compare_pooled_export(folder / 'before_pooled_input.csv', series)
        price_count = weekly.compare_price_export(folder / 'before_prices_12w.csv', prices)
        run, audit_seconds = execute(database, folder, audit)
        results = weekly.parsed(run.stdout)
        assert_report(results, expected)
        after = snapshot('after')
        assert before == after, 'Read-only audit changed a scoped input'
        database_bytes = database.stat().st_size
    assert not folder.exists()
    assert all(weekly.sha256(path) == source_hashes[name] for name, path in sources.items())
    assert all(weekly.sha256(root / path) == value for path, value in historical.items())
    assert all(weekly.sha256(root / path) == value for path, value in code_hashes.items())
    evidence = dict(
        checked_at_utc=datetime.now(timezone.utc).isoformat(), executor='assistant',
        engine=subprocess.check_output([args.duckdb, '-version'], text=True).strip(),
        script=paths[0], script_sha256=code_hashes[paths[0]], validator=paths[1], validator_sha256=code_hashes[paths[1]],
        protocol=paths[2], protocol_sha256=PROTOCOL_SHA, code_and_dependency_sha256=code_hashes,
        settings={'threads': 2, 'memory_limit': '2GB'},
        source_sha256=source_hashes, source_hashes_unchanged=True, source_controls=controls,
        input_window={'start_date': '2016-01-30', 'end_date': '2016-04-22', 'weeks': 12, 'pairs': 30490},
        report_window={'first_current_week': 11602, 'last_current_week': 11612, 'start_date': '2016-02-06', 'end_date': '2016-04-22'},
        independent_reference='Reused SQL44 Python csv/Decimal readers derive complete pair membership and exact weekly values from original files. Direct previous/current week lookups independently classify all 335,390 adjacent positions and distinct pair sets; every report field and order is compared.',
        preflight_strategy='Only 84 sales columns and twelve price weeks are staged privately. Unchanged SQL09/23/44 builds establish the input; their historical test suites and the forecasting pipeline are not rerun. SQL45 reads weekly input, metadata, calendar, pooled checks and staging prices; no daily-fact scan.',
        weekly_input_rows_compared=rows_compared, weekly_input_fields_compared=12, weekly_input_exact_mismatches=0,
        weekly_input_rows_sha256=input_hash, accepted_sql44_input_fingerprint_matched=True,
        pooled_rows_compared=pooled_count, pooled_fields_compared=8, pooled_rows_sha256=pooled_hash,
        price_rows_compared=price_count, price_fields_compared=4, transition_positions_evaluated=335390,
        scoped_input_sha256_before=before, scoped_input_sha256_after=after, scoped_inputs_unchanged=True,
        historical_preflight_files_unchanged=len(historical), temporary_database_removed=True,
        temporary_database_bytes_after_close=database_bytes, fixture_case_count=len(cases), fixture_cases=cases,
        independent_source_read_seconds=reference_seconds, setup_seconds=setup_seconds, audit_seconds=audit_seconds,
        timing_scope='One-run elapsed seconds; CLI timings exclude hashing/Python comparisons. DuckDB memory_limit is not a total-process memory cap.',
        report_rows=12, report_columns=12, report_sha256=weekly.canonical_hash([[row[key] for key in COLUMNS] for row in results]),
        report_fingerprint_contract='SHA-256 over ordered report rows as compact JSON arrays plus LF; counts are integers, dates are ISO strings.',
        results=results, scope='Assistant independent preflight only; learner SQL45 execution pending. Distinct TOTAL pair counts are nonadditive. All zero-sales positions remain included. No price effect, causal elasticity, promotion mechanism or anomaly is estimated. Public output contains aggregates and fingerprints only.')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, default=str) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps({'fixture_cases_passed': len(cases), 'weekly_input_rows_compared': rows_compared,
                      'audit_seconds': audit_seconds, 'results': results}, default=str), flush=True)


if __name__ == '__main__':
    main()
