"""Verify the fixed 12-week item/store sales-price mart in an isolated, disposable database."""
import argparse
import csv
import hashlib
import json
import re
import subprocess
import tempfile
import time
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path


START = date(2016, 1, 30)
END = date(2016, 4, 22)
TARGET = 'mart.m5_item_store_weekly_prices_12w'
FIELDS = ['item_id', 'store_id', 'dept_id', 'cat_id', 'state_id', 'wm_yr_wk',
          'week_start', 'week_end', 'units', 'source_daily_rows', 'sell_price', 'has_price']
REPORT_FIELDS = ['retail_week', 'week_start', 'week_end', 'series_week_rows', 'source_daily_rows',
                 'units', 'zero_sales_series_weeks', 'priced_series_weeks', 'missing_price_series_weeks',
                 'missing_price_positive_sales_weeks', 'priced_units', 'check_status']
PRICE_FIELDS = ['store_id', 'item_id', 'wm_yr_wk', 'sell_price']


def sha256(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def quote(value):
    return "'" + str(value).replace("'", "''") + "'"


def parsed(text):
    return json.loads(text, parse_float=Decimal)


def canonical_hash(rows):
    digest = hashlib.sha256()
    for row in rows:
        digest.update((json.dumps(row, ensure_ascii=True, separators=(',', ':'), default=str) + '\n').encode())
    return digest.hexdigest()


def expected_rows(series, prices):
    for row in sorted(series, key=lambda r: (r['item_id'], r['store_id'])):
        for offset in range(12):
            week = 11601 + offset
            start = START + timedelta(days=7 * offset)
            price = prices.get((row['item_id'], row['store_id'], week))
            units = sum(row['days'][7 * offset:7 * offset + 7])
            assert price is not None or units == 0, 'Independent reference has positive unpriced sales'
            yield [row['item_id'], row['store_id'], row['dept_id'], row['cat_id'], row['state_id'], week,
                   start.isoformat(), (start + timedelta(days=6)).isoformat(), units, 7,
                   None if price is None else format(price, '.2f'), price is not None]


def report_reference(series, prices):
    rows = []
    for offset in range(12):
        week = 11601 + offset
        start = START + timedelta(days=7 * offset)
        units = [sum(row['days'][7 * offset:7 * offset + 7]) for row in series]
        has_price = [(row['item_id'], row['store_id'], week) in prices for row in series]
        rows.append(dict(zip(REPORT_FIELDS, [str(week), start.isoformat(), (start + timedelta(days=6)).isoformat(),
            len(series), len(series) * 7, sum(units), sum(u == 0 for u in units), sum(has_price),
            len(series) - sum(has_price), sum(u > 0 and not p for u, p in zip(units, has_price)),
            sum(u for u, p in zip(units, has_price) if p), 'PASS'])))
    total = dict(retail_week='TOTAL', week_start=START.isoformat(), week_end=END.isoformat())
    total.update({key: sum(row[key] for row in rows) for key in REPORT_FIELDS[3:-1]})
    total['check_status'] = 'PASS'
    rows.append(total)
    return rows


def assert_report(actual, expected):
    assert len(actual) == 13 and all(list(row) == REPORT_FIELDS for row in actual), 'Report shape/order mismatch'
    for row in actual:
        for key in REPORT_FIELDS[3:-1]:
            value = Decimal(str(row[key]))
            assert value.is_finite() and value == int(value), 'Noninteger report control'
            row[key] = int(value)
    assert actual == expected, 'Report differs from independent source reference'
    for row in actual:
        assert row['priced_series_weeks'] + row['missing_price_series_weeks'] == row['series_week_rows']
        assert row['source_daily_rows'] == 7 * row['series_week_rows']
        assert row['missing_price_positive_sales_weeks'] == 0 and row['priced_units'] == row['units']


def normalize_export(row):
    assert list(row) == FIELDS, 'Unexpected target CSV schema'
    return [row[key] if key not in ('wm_yr_wk', 'units', 'source_daily_rows', 'sell_price', 'has_price')
            else int(row[key]) if key in ('wm_yr_wk', 'units', 'source_daily_rows')
            else None if key == 'sell_price' and row[key] == ''
            else format(Decimal(row[key]), '.2f') if key == 'sell_price'
            else {'true': True, 'false': False}[row[key]] for key in FIELDS]


def compare_export(path, expected):
    digest = hashlib.sha256()
    count = 0
    with path.open(newline='', encoding='utf-8') as stream:
        reader = csv.DictReader(stream)
        for reference in expected:
            actual = next(reader, None)
            assert actual is not None, 'Target extract ended before independent reference'
            normalized = normalize_export(actual)
            assert normalized == reference, 'Exact item/store/week field comparison failed'
            digest.update((json.dumps(normalized, ensure_ascii=True, separators=(',', ':')) + '\n').encode())
            count += 1
        assert next(reader, None) is None, 'Target extract contains extra rows'
    return count, digest.hexdigest()


def fixture(all_zero=False, no_prices=False):
    series = []
    for item in range(1, 4):
        for store in range(1, 3):
            series.append(dict(item_id=f'P{item}', store_id=f'S{store}', dept_id='FOODS_1', cat_id='FOODS',
                state_id='CA' if store == 1 else 'TX',
                days=[0 if all_zero or item == 3 or (item == 2 and offset // 7 in (2, 6))
                      else item * store + offset % 3 for offset in range(84)]))
    prices = {}
    for row in series:
        for offset in range(12):
            # Missing zero-sales observations, priced zeros, and an internal price gap coexist.
            if no_prices or (row['item_id'] == 'P3' and offset % 2 == 0) or (row['item_id'] == 'P2' and offset == 2):
                continue
            prices[(row['item_id'], row['store_id'], 11601 + offset)] = Decimal(100 + offset + int(row['store_id'][1:])) / 100
    raw_values = ','.join('(' + ','.join(quote(row[key]) for key in ['item_id', 'store_id', 'dept_id', 'cat_id', 'state_id']) + ')' for row in series)
    price_values = ','.join(f'({quote(s)},{quote(i)},{w},{p})' for (i, s, w), p in prices.items())
    daily_values = ','.join(f"({quote(row['item_id'])},{quote(row['store_id'])},'d_{1828 + offset}',DATE '{(START + timedelta(days=offset)).isoformat()}',{11601 + offset // 7},{units})"
                            for row in series for offset, units in enumerate(row['days']))
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
"""
    if price_values:
        setup += f'INSERT INTO stg.m5_prices VALUES {price_values};\n'
    return setup, series, prices


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--duckdb', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--fixtures-only', action='store_true')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    validator_hash = sha256(Path(__file__))
    tmp_root = root / 'tmp'
    tmp_root.mkdir(exist_ok=True)
    script_path = root / 'sql/44_build_item_store_weekly_prices.sql'
    sql_bytes = script_path.read_bytes()
    build, audit = sql_bytes.decode('utf-8').split('-- VALIDATION:', 1)
    audit = '-- VALIDATION:' + audit
    pooled_path = root / 'sql/23_build_product_weekly.sql'
    pooled_bytes = pooled_path.read_bytes()
    pooled_build = pooled_bytes.decode('utf-8').split('-- VALIDATION:', 1)[0]
    cases = []

    def execute(database, folder, sql, fail=False):
        assert database.resolve().is_relative_to(tmp_root.resolve())
        settings = f"SET threads=2; SET memory_limit='2GB'; SET temp_directory={quote((folder / 'spill').as_posix())};\n"
        start = time.perf_counter()
        result = subprocess.run([args.duckdb, str(database), '-bail', '-json'], input=settings + sql,
                                text=True, encoding='utf-8', capture_output=True)
        if not fail:
            assert result.returncode == 0, result.stderr
        return result, round(time.perf_counter() - start, 3)

    def tiny(family, name, before='', after='', rejection=False, all_zero=False, no_prices=False,
             rerun=False, reverse=False):
        setup, series, prices = fixture(all_zero=all_zero, no_prices=no_prices)
        transform = lambda text: text.replace('3049 AS expected_items,10 AS expected_stores', '3 AS expected_items,2 AS expected_stores')
        with tempfile.TemporaryDirectory(prefix='item-store-weekly-case-', dir=tmp_root) as name_dir:
            folder = Path(name_dir)
            assert folder.resolve().is_relative_to(tmp_root.resolve())
            database = folder / 'fixture.duckdb'
            execute(database, folder, setup + transform(pooled_build))
            if reverse:
                before += "CREATE TABLE mart.reverse_daily AS SELECT * FROM mart.m5_sales_daily ORDER BY item_id DESC,store_id DESC,date DESC; DROP TABLE mart.m5_sales_daily; ALTER TABLE mart.reverse_daily RENAME TO m5_sales_daily;"
            run, _ = execute(database, folder, before + transform(build) + after + transform(audit), fail=rejection)
            if rejection:
                assert run.returncode != 0, f'Fixture did not reject: {family}/{name}'
                expected_error = 'Item-store weekly validation blocked' if after else 'Item-store weekly build blocked'
                assert expected_error in run.stderr, f'Fixture did not reach its intended guard: {family}/{name}'
                if not after:
                    check, _ = execute(database, folder, f"SELECT COUNT(*) AS n FROM information_schema.tables WHERE table_schema='mart' AND table_name='m5_item_store_weekly_prices_12w';")
                    assert parsed(check.stdout) == [{'n': 0}], 'Failed build left a target table'
            else:
                assert_report(parsed(run.stdout), report_reference(series, prices))
                export = folder / 'target.csv'
                execute(database, folder, f"COPY (SELECT * FROM {TARGET} ORDER BY item_id,store_id,wm_yr_wk) TO {quote(export.as_posix())} (HEADER,FORMAT CSV);")
                count, fingerprint = compare_export(export, expected_rows(series, prices))
                assert count == 72 and fingerprint == canonical_hash(expected_rows(series, prices))
                if rerun:
                    second, _ = execute(database, folder, transform(audit))
                    assert_report(parsed(second.stdout), report_reference(series, prices))
                    refused, _ = execute(database, folder, transform(build), fail=True)
                    assert refused.returncode != 0 and 'already exists' in refused.stderr
                    final, _ = execute(database, folder, transform(audit))
                    assert_report(parsed(final.stdout), report_reference(series, prices))
        assert not folder.exists(), 'Fixture directory was not removed'
        cases.append(dict(family=family, case=name, passed=True, expected_rejection=rejection))

    tiny('valid_zero_and_missing_price_semantics', 'priced_zeros_unpriced_zeros_and_internal_gaps')
    tiny('valid_zero_and_missing_price_semantics', 'all_zero_all_prices_absent', all_zero=True, no_prices=True)
    tiny('valid_zero_and_missing_price_semantics', 'input_order_irrelevant', reverse=True)
    for name, mutation in [
        ('duplicate_replaces_missing_day', "UPDATE mart.m5_sales_daily SET date=DATE '2016-02-02',d='d_1831' WHERE item_id='P1' AND store_id='S1' AND date=DATE '2016-02-01';"),
        ('missing_series', "DELETE FROM mart.m5_sales_daily WHERE item_id='P1' AND store_id='S1';"),
        ('null_units', "UPDATE mart.m5_sales_daily SET units=NULL WHERE item_id='P1' AND store_id='S1' AND d='d_1828';"),
        ('negative_units', "UPDATE mart.m5_sales_daily SET units=-1 WHERE item_id='P1' AND store_id='S1' AND d='d_1828';"),
        ('wrong_units_type', 'ALTER TABLE mart.m5_sales_daily ALTER units TYPE BIGINT;'),
    ]:
        tiny('daily_completeness_and_values', name, before=mutation, rejection=True)
    for name, mutation in [
        ('fact_wrong_week', "UPDATE mart.m5_sales_daily SET wm_yr_wk=11602 WHERE item_id='P1' AND d='d_1828';"),
        ('calendar_duplicate_day', "INSERT INTO core.m5_calendar SELECT * FROM core.m5_calendar WHERE d='d_1828';"),
        ('full_week_cannot_be_clipped', "UPDATE core.m5_calendar SET wm_yr_wk=11601 WHERE d='d_1827';"),
    ]:
        tiny('calendar_and_boundaries', name, before=mutation, rejection=True)
    for name, mutation in [
        ('duplicate_product', "INSERT INTO core.m5_product SELECT * FROM core.m5_product WHERE item_id='P1';"),
        ('valid_but_wrong_department', "UPDATE core.m5_product SET dept_id='FOODS_2' WHERE item_id='P1';"),
        ('wrong_store_state', "UPDATE core.m5_store SET state_id='WI' WHERE store_id='S1';"),
        ('duplicate_raw_pair', 'INSERT INTO raw.m5_sales_wide SELECT * FROM raw.m5_sales_wide LIMIT 1;'),
    ]:
        tiny('dimension_and_pair_mapping', name, before=mutation, rejection=True)
    for name, mutation in [
        ('duplicate_equal_price', "INSERT INTO stg.m5_prices SELECT * FROM stg.m5_prices WHERE item_id='P1' AND store_id='S1' AND wm_yr_wk=11601;"),
        ('orphan_item', "INSERT INTO stg.m5_prices VALUES ('S1','UNKNOWN',11601,1.00);"),
        ('null_week', "INSERT INTO stg.m5_prices VALUES ('S1','P1',NULL,1.00);"),
        ('invalid_null_price_at_zero_sales', "UPDATE stg.m5_prices SET sell_price=NULL WHERE item_id='P3' AND wm_yr_wk=11602;"),
        ('invalid_zero_price_at_zero_sales', "UPDATE stg.m5_prices SET sell_price=0 WHERE item_id='P3' AND wm_yr_wk=11602;"),
        ('wrong_price_type', 'ALTER TABLE stg.m5_prices ALTER sell_price TYPE DOUBLE;'),
        ('cannot_borrow_other_store_or_week', "DELETE FROM stg.m5_prices WHERE item_id='P1' AND store_id='S1' AND wm_yr_wk=11605;"),
    ]:
        tiny('price_keys_values_and_coverage', name, before=mutation, rejection=True)
    for name, mutation in [
        ('accepted_pooled_units_changed', "UPDATE mart.m5_product_weekly_12w SET units=units+1 WHERE item_id='P1' AND wm_yr_wk=11601;"),
        ('accepted_pooled_duplicate', 'INSERT INTO mart.m5_product_weekly_12w SELECT * FROM mart.m5_product_weekly_12w LIMIT 1;'),
        ('accepted_pooled_schema_changed', 'ALTER TABLE mart.m5_product_weekly_12w ALTER units TYPE BIGINT;'),
    ]:
        tiny('accepted_product_week_reconciliation', name, before=mutation, rejection=True)
    for name, mutation in [
        ('total_preserving_unit_redistribution', f"UPDATE {TARGET} SET units=units+CASE store_id WHEN 'S1' THEN 1 ELSE -1 END WHERE item_id='P1' AND wm_yr_wk=11601;"),
        ('prices_swapped_between_stores', f"UPDATE {TARGET} SET sell_price=CASE store_id WHEN 'S1' THEN 1.02 ELSE 1.01 END WHERE item_id='P1' AND wm_yr_wk=11601;"),
        ('missing_price_imputed_zero', f"UPDATE {TARGET} SET sell_price=0 WHERE item_id='P3' AND wm_yr_wk=11601;"),
        ('coverage_flag_changed', f"UPDATE {TARGET} SET has_price=false WHERE item_id='P1' AND wm_yr_wk=11601;"),
        ('stored_schema_changed', f'ALTER TABLE {TARGET} ALTER units TYPE BIGINT;'),
        ('stored_week_missing', f"DELETE FROM {TARGET} WHERE item_id='P3' AND store_id='S1' AND wm_yr_wk=11601;"),
    ]:
        tiny('exact_stored_fields_and_schema', name, after=mutation, rejection=True)
    tiny('rerun_and_scope_preservation', 'validation_repeat_and_existing_target_refusal', rerun=True)
    tiny('rerun_and_scope_preservation', 'outside_window_and_unused_daily_fields', before="""
INSERT INTO mart.m5_sales_daily VALUES ('P1','S1','d_1914',DATE '2016-04-25',11613,999999);
INSERT INTO stg.m5_prices VALUES ('OUTSIDE','OUTSIDE',11613,-1.00);
ALTER TABLE mart.m5_sales_daily ADD COLUMN sell_price DOUBLE DEFAULT -999;
ALTER TABLE mart.m5_sales_daily ADD COLUMN has_price BOOLEAN DEFAULT false;
""")
    families = sorted({case['family'] for case in cases})
    assert len(families) == 8
    print(json.dumps({'fixture_families_passed': len(families), 'fixture_subcases_passed': len(cases)}), flush=True)
    if args.fixtures_only:
        return

    # Full-source execution is intentionally separate from synthetic fixture validation.
    protocol_path = root / 'docs/ITEM_STORE_WEEKLY_PRICES_PROTOCOL.md'
    protocol_hash = sha256(protocol_path)
    assert protocol_hash == '3fcf8b110d8f67b8c79f8a8404a2517a2848344c03012ec800b7e8fbd80d4630', 'Frozen protocol changed'
    source_root = Path('D:/database/m5-forecasting-accuracy')
    sources = {name: source_root / name for name in ['sales_train_evaluation.csv', 'calendar.csv', 'sell_prices.csv']}
    registry = json.loads((root / 'data/m5_source_audit.json').read_text(encoding='utf-8'))
    source_hashes = {name: sha256(path) for name, path in sources.items()}
    assert all(source_hashes[name] == registry['files'][name]['sha256'] for name in sources), 'Registered source hash mismatch'
    historical = {str(path.relative_to(root)): sha256(path) for path in (root / 'data').glob('*preflight.json') if path.resolve() != args.output.resolve()}
    accepted_path = root / 'data/product_weekly_learner_acceptance.json'
    accepted_hash = sha256(accepted_path)
    accepted = json.loads(accepted_path.read_text(encoding='utf-8'))
    series, prices, source_controls, independent_seconds = read_original_sources(sources)
    expected_report = report_reference(series, prices)
    assert len(series) == 30490 and sum(sum(r['days']) for r in series) == 3536539
    for row, prior in zip(expected_report, accepted['results']):
        assert row['retail_week'] == prior['retail_week'] and row['units'] == int(prior['units'])
        assert row['source_daily_rows'] == int(prior['source_daily_rows'])
    columns = ','.join(f'd_{n}' for n in range(1828, 1912))
    setup = f"""
CREATE SCHEMA raw; CREATE SCHEMA core; CREATE SCHEMA mart; CREATE SCHEMA stg;
CREATE TABLE raw.m5_sales_wide AS SELECT id,item_id,dept_id,cat_id,store_id,state_id,{columns}
FROM read_csv({quote(sources['sales_train_evaluation.csv'].as_posix())},header=true,all_varchar=true);
CREATE TABLE core.m5_product AS SELECT DISTINCT item_id,dept_id,cat_id FROM raw.m5_sales_wide;
CREATE TABLE core.m5_store AS SELECT DISTINCT store_id,state_id FROM raw.m5_sales_wide;
CREATE TABLE core.m5_calendar AS SELECT d,CAST(date AS DATE) AS date,CAST(wm_yr_wk AS INTEGER) AS wm_yr_wk
FROM read_csv({quote(sources['calendar.csv'].as_posix())},header=true,all_varchar=true);
CREATE TABLE mart.m5_sales_daily AS
WITH unpivoted AS (UNPIVOT raw.m5_sales_wide ON {columns} INTO NAME d VALUE units_text)
SELECT u.item_id,u.store_id,u.d,c.date,c.wm_yr_wk,
    CASE WHEN regexp_full_match(units_text,'[0-9]+') AND TRY_CAST(units_text AS INTEGER) IS NOT NULL
        THEN CAST(units_text AS INTEGER) ELSE error('Invalid original window units') END AS units
FROM unpivoted u JOIN core.m5_calendar c ON u.d=c.d;
CREATE TABLE raw.m5_prices AS SELECT * FROM read_csv({quote(sources['sell_prices.csv'].as_posix())},header=true,all_varchar=true)
WHERE TRY_CAST(wm_yr_wk AS INTEGER) BETWEEN 11601 AND 11612 OR TRY_CAST(wm_yr_wk AS INTEGER) IS NULL;
"""
    price_path = root / 'sql/09_stage_prices.sql'
    price_hash = sha256(price_path)
    price_build = price_path.read_text(encoding='utf-8').split('-- VALIDATION:', 1)[0]
    snapshots = {
        'source_wide_84d': 'SELECT * FROM raw.m5_sales_wide ORDER BY item_id,store_id',
        'daily_84d': 'SELECT item_id,store_id,d,date,wm_yr_wk,units FROM mart.m5_sales_daily ORDER BY item_id,store_id,date',
        'calendar': 'SELECT * FROM core.m5_calendar ORDER BY date,d,wm_yr_wk',
        'products': 'SELECT * FROM core.m5_product ORDER BY item_id',
        'stores': 'SELECT * FROM core.m5_store ORDER BY store_id',
        'prices_12w': 'SELECT * FROM stg.m5_prices ORDER BY item_id,store_id,wm_yr_wk',
        'accepted_product_weekly': 'SELECT * FROM mart.m5_product_weekly_12w ORDER BY item_id,wm_yr_wk',
    }
    with tempfile.TemporaryDirectory(prefix='item-store-weekly-', dir=tmp_root) as name_dir:
        folder = Path(name_dir)
        assert folder.resolve().is_relative_to(tmp_root.resolve())
        database = folder / 'preflight.duckdb'
        _, setup_seconds = execute(database, folder, setup + price_build + pooled_build)
        before_hashes = {}
        for name, query in snapshots.items():
            path = folder / f'before_{name}.csv'
            execute(database, folder, f'COPY ({query}) TO {quote(path.as_posix())} (HEADER,FORMAT CSV);')
            before_hashes[name] = sha256(path)
        daily_rows_compared = compare_daily_export(folder / 'before_daily_84d.csv', series)
        price_rows_compared = compare_price_export(folder / 'before_prices_12w.csv', prices)
        pooled_rows_compared, pooled_reference_hash = compare_pooled_export(folder / 'before_accepted_product_weekly.csv', series)
        _, build_seconds = execute(database, folder, build)
        run, audit_seconds = execute(database, folder, audit)
        results = parsed(run.stdout)
        assert_report(results, expected_report)
        export = folder / 'target.csv'
        execute(database, folder, f'COPY (SELECT * FROM {TARGET} ORDER BY item_id,store_id,wm_yr_wk) TO {quote(export.as_posix())} (HEADER,FORMAT CSV);')
        stored_count, stored_hash = compare_export(export, expected_rows(series, prices))
        reference_hash = canonical_hash(expected_rows(series, prices))
        assert stored_count == 365880 and stored_hash == reference_hash
        after_hashes = {}
        for name, query in snapshots.items():
            path = folder / f'after_{name}.csv'
            execute(database, folder, f'COPY ({query}) TO {quote(path.as_posix())} (HEADER,FORMAT CSV);')
            after_hashes[name] = sha256(path)
        assert before_hashes == after_hashes, 'A scoped input snapshot changed'
        repeated, _ = execute(database, folder, audit)
        assert_report(parsed(repeated.stdout), expected_report)
        database_bytes = database.stat().st_size
    assert not folder.exists(), 'Private directory was not removed'
    assert all(sha256(path) == source_hashes[name] for name, path in sources.items()), 'Original source changed'
    assert all(sha256(root / path) == fingerprint for path, fingerprint in historical.items()), 'Historical evidence changed'
    assert sha256(accepted_path) == accepted_hash and sha256(script_path) == hashlib.sha256(sql_bytes).hexdigest()
    assert sha256(protocol_path) == protocol_hash and sha256(pooled_path) == hashlib.sha256(pooled_bytes).hexdigest()
    assert sha256(price_path) == price_hash and sha256(Path(__file__)) == validator_hash
    evidence = dict(
        checked_at_utc=datetime.now(timezone.utc).isoformat(), executor='assistant',
        engine=subprocess.check_output([args.duckdb, '-version'], text=True).strip(),
        script='sql/44_build_item_store_weekly_prices.sql', script_sha256=hashlib.sha256(sql_bytes).hexdigest(),
        validator='validation/preflight_item_store_weekly_prices.py', validator_sha256=validator_hash,
        protocol='docs/ITEM_STORE_WEEKLY_PRICES_PROTOCOL.md', protocol_sha256=protocol_hash,
        table=TARGET, settings={'threads': 2, 'memory_limit': '2GB'},
        window={'start_date': START.isoformat(), 'end_date': END.isoformat(), 'days': 84,
                'retail_weeks': list(range(11601, 11613)), 'series': 30490},
        source_sha256=source_hashes, source_hashes_unchanged=True, source_controls=source_controls,
        independent_reference='Python csv reads original sales columns d_1828..d_1911, original calendar mapping and original weekly prices with Decimal exact cents; all expected pair/week membership comes from original CSVs, not SQL44 output.',
        preflight_strategy='Private database contains only 84 sales day columns, their 2,561,160 daily cells, complete small calendar/dimensions and 12 price weeks. Unchanged SQL09 build stages scoped prices; unchanged SQL23 build establishes the accepted pooled dependency. No forecast or ABC pipeline is rerun; learner database is never opened.',
        independent_source_read_seconds=independent_seconds, setup_seconds=setup_seconds,
        build_seconds=build_seconds, validation_seconds=audit_seconds,
        timing_scope='One-run elapsed times; CLI timings exclude Python comparisons and hashing. DuckDB memory_limit is not a total-process memory cap.',
        daily_rows_compared=daily_rows_compared, daily_fields_compared=6,
        price_rows_compared=price_rows_compared, price_fields_compared=4,
        pooled_rows_compared=pooled_rows_compared, pooled_fields_compared=8,
        pooled_independent_rows_sha256=pooled_reference_hash, pooled_exact_field_mismatches=0,
        stored_rows_compared=stored_count, stored_fields_compared=12, exact_stored_field_mismatches=0,
        stored_rows_sha256=stored_hash, independent_rows_sha256=reference_hash,
        fingerprint_contract='SHA-256 over sorted item/store/week rows encoded as compact JSON arrays plus LF; exact price cents are two-decimal strings, missing price null, has_price boolean.',
        pooled_dependency_script='sql/23_build_product_weekly.sql', pooled_dependency_sha256=hashlib.sha256(pooled_bytes).hexdigest(),
        price_dependency_script='sql/09_stage_prices.sql', price_dependency_sha256=price_hash,
        accepted_product_week_evidence='data/product_weekly_learner_acceptance.json',
        accepted_product_week_evidence_sha256=accepted_hash, accepted_weekly_units_and_daily_counts_matched=True,
        scoped_input_sha256_before=before_hashes, scoped_input_sha256_after=after_hashes,
        scoped_inputs_unchanged=True, historical_preflight_files_unchanged=len(historical),
        temporary_database_removed=True, temporary_database_bytes_after_close=database_bytes,
        fixture_family_count=len(families), fixture_subcase_count=len(cases), fixture_cases=cases,
        report_rows=13, report_columns=12, report_sha256=canonical_hash([[row[key] for key in REPORT_FIELDS] for row in results]),
        results=results, scope='Assistant independent preflight only; learner SQL44 execution pending. Missing prices remain NULL and zero-sales series/weeks remain present. No price-change association, anomaly finding, causal elasticity, promotion or stockout identification is claimed. Public evidence contains aggregate results and fingerprints only.')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, default=str) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps({'fixture_families_passed': len(families), 'fixture_subcases_passed': len(cases),
                      'stored_rows_compared': stored_count, 'build_seconds': build_seconds,
                      'validation_seconds': audit_seconds, 'results': results}, default=str), flush=True)


def read_original_sources(sources):
    started = time.perf_counter()
    with sources['calendar.csv'].open(newline='', encoding='utf-8-sig') as stream:
        calendar = list(csv.DictReader(stream))
    by_day = {row['d']: row for row in calendar}
    assert len(by_day) == len(calendar) == 1969
    for offset in range(84):
        row = by_day[f'd_{1828 + offset}']
        assert row['date'] == (START + timedelta(days=offset)).isoformat() and int(row['wm_yr_wk']) == 11601 + offset // 7
    for week in range(11601, 11613):
        assert sum(int(row['wm_yr_wk']) == week for row in calendar) == 7
    series, pairs, products, stores = [], set(), {}, {}
    with sources['sales_train_evaluation.csv'].open(newline='', encoding='utf-8-sig') as stream:
        reader = csv.DictReader(stream)
        assert reader.fieldnames == ['id', 'item_id', 'dept_id', 'cat_id', 'store_id', 'state_id'] + [f'd_{n}' for n in range(1, 1942)]
        for row in reader:
            item, store = row['item_id'], row['store_id']
            assert (item, store) not in pairs and all(row[key].strip() for key in reader.fieldnames[:6])
            pairs.add((item, store))
            mapping = (row['dept_id'], row['cat_id'])
            assert item not in products or products[item] == mapping
            assert store not in stores or stores[store] == row['state_id']
            products[item], stores[store] = mapping, row['state_id']
            days = []
            for day in range(1828, 1912):
                value = row[f'd_{day}']
                assert re.fullmatch(r'[0-9]+', value) and 0 <= int(value) <= 2147483647
                days.append(int(value))
            series.append({**{key: row[key] for key in ['item_id', 'store_id', 'dept_id', 'cat_id', 'state_id']}, 'days': days})
    assert len(pairs) == 30490 and len(products) == 3049 and len(stores) == 10
    assert pairs == {(item, store) for item in products for store in stores}
    prices = {}
    with sources['sell_prices.csv'].open(newline='', encoding='utf-8-sig') as stream:
        reader = csv.DictReader(stream)
        assert reader.fieldnames == PRICE_FIELDS
        for row in reader:
            assert re.fullmatch(r'[1-9][0-9]{4}', row['wm_yr_wk'])
            week = int(row['wm_yr_wk'])
            if not 11601 <= week <= 11612:
                continue
            key = row['item_id'], row['store_id'], week
            assert key[:2] in pairs and key not in prices
            assert re.fullmatch(r'[0-9]+([.][0-9]{1,2}0*)?', row['sell_price'])
            price = Decimal(row['sell_price'])
            assert price.is_finite() and 0 < price < Decimal('10000000000000000') and price == price.quantize(Decimal('.01'))
            prices[key] = price
    controls = dict(source_series=len(series), source_products=len(products), source_stores=len(stores),
                    calendar_rows=len(calendar), window_daily_cells=len(series) * 84, source_price_rows=len(prices),
                    window_units=sum(sum(row['days']) for row in series))
    return series, prices, controls, round(time.perf_counter() - started, 3)


def compare_daily_export(path, series):
    count = 0
    with path.open(newline='', encoding='utf-8') as stream:
        reader = csv.DictReader(stream)
        assert reader.fieldnames == ['item_id', 'store_id', 'd', 'date', 'wm_yr_wk', 'units']
        for source in sorted(series, key=lambda row: (row['item_id'], row['store_id'])):
            for offset, units in enumerate(source['days']):
                row = next(reader, None)
                expected = [source['item_id'], source['store_id'], f'd_{1828 + offset}',
                            (START + timedelta(days=offset)).isoformat(), str(11601 + offset // 7), str(units)]
                assert row is not None and list(row.values()) == expected, 'Exact daily source projection mismatch'
                count += 1
        assert next(reader, None) is None, 'Unexpected extra daily source row'
    return count


def compare_price_export(path, prices):
    count = 0
    with path.open(newline='', encoding='utf-8') as stream:
        reader = csv.DictReader(stream)
        assert reader.fieldnames == PRICE_FIELDS
        for (item, store, week), price in sorted(prices.items()):
            row = next(reader, None)
            assert row is not None and list(row.values()) == [store, item, str(week), format(price, '.2f')], 'Exact price source projection mismatch'
            count += 1
        assert next(reader, None) is None, 'Unexpected extra scoped price row'
    return count


def compare_pooled_export(path, series):
    pooled = {}
    for row in series:
        item = row['item_id']
        if item not in pooled:
            pooled[item] = [row['dept_id'], row['cat_id'], [0] * 12, 0]
        pooled[item][3] += 1
        for offset in range(12):
            pooled[item][2][offset] += sum(row['days'][7 * offset:7 * offset + 7])
    expected = []
    for item, (department, category, weeks, store_count) in sorted(pooled.items()):
        for offset, units in enumerate(weeks):
            start = START + timedelta(days=7 * offset)
            expected.append([item, department, category, 11601 + offset, start.isoformat(),
                             (start + timedelta(days=6)).isoformat(), units, store_count * 7])
    with path.open(newline='', encoding='utf-8') as stream:
        reader = csv.DictReader(stream)
        assert reader.fieldnames == ['item_id', 'dept_id', 'cat_id', 'wm_yr_wk', 'week_start', 'week_end', 'units', 'source_daily_rows']
        for reference in expected:
            row = next(reader, None)
            assert row is not None and list(row.values()) == [str(value) for value in reference], 'Exact accepted product/week reference mismatch'
        assert next(reader, None) is None, 'Unexpected extra accepted product/week row'
    assert len(expected) == 36588
    return len(expected), canonical_hash(expected)


if __name__ == '__main__':
    main()
