"""Verify the real price audit and tiny fault fixtures in disposable memory DBs.

Reference tables contain only the source columns needed for existence checks.
No learner database is opened. Fixture assertions use diagnostic values because
production expected totals deliberately remain unchanged in the audit SQL.
"""
import argparse
import hashlib
import json
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path


def sha256(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--duckdb', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    audit_path = root / 'sql/07_audit_prices.sql'
    audit = audit_path.read_text(encoding='utf-8')
    setup = (root / 'sql/06_import_prices.sql').read_text(encoding='utf-8').split('-- BASIC CHECKS:')[0]
    setup += """
    CREATE TABLE raw.m5_sales_wide AS
      SELECT item_id, store_id FROM read_csv(
        'D:/database/m5-forecasting-accuracy/sales_train_evaluation.csv',header=true,all_varchar=true);
    CREATE TABLE raw.m5_calendar AS
      SELECT wm_yr_wk FROM read_csv(
        'D:/database/m5-forecasting-accuracy/calendar.csv',header=true,all_varchar=true);
    """
    registry = json.loads((root / 'data/m5_source_audit.json').read_text(encoding='utf-8'))
    sources = {name: Path('D:/database/m5-forecasting-accuracy') / name
               for name in ('sell_prices.csv', 'sales_train_evaluation.csv', 'calendar.csv')}
    hashes = {name: sha256(path) for name, path in sources.items()}
    assert all(value == registry['files'][name]['sha256'] for name, value in hashes.items())
    tmp_root = root / 'tmp'
    tmp_root.mkdir(exist_ok=True)

    def run_sql(sql):
        with tempfile.TemporaryDirectory(prefix='price-audit-', dir=tmp_root) as spill:
            assert Path(spill).resolve().is_relative_to(tmp_root.resolve())
            spill_sql = Path(spill).as_posix().replace("'", "''")
            settings = f"SET threads=2; SET memory_limit='3GB'; SET temp_directory='{spill_sql}';\n"
            started = time.perf_counter()
            run = subprocess.run([args.duckdb, ':memory:', '-bail', '-json'],
                                 input=settings + sql, text=True, encoding='utf-8',
                                 capture_output=True, check=True)
            return json.loads(run.stdout), round(time.perf_counter() - started, 3)

    baseline, elapsed = run_sql(setup + '\n' + audit)
    assert len(baseline) == 15 and all(row['status'] == 'PASS' for row in baseline), baseline
    assert all(sha256(path) == hashes[name] for name, path in sources.items())
    print(json.dumps({'baseline_checks_passed': 15, 'setup_and_audit_seconds': elapsed}), flush=True)
    source_expression = """read_csv(
        'D:/database/m5-forecasting-accuracy/sell_prices.csv',
        header = true, all_varchar = true
    )"""
    assert audit.count(source_expression) == 1
    fixture_audit = audit.replace(source_expression, 'fixture_source')
    fixture_setup = """
    CREATE TABLE fixture_source AS SELECT * FROM (VALUES
      ('S','A','11101','1.25'), ('S','A','11102','2.50'), ('S','B','11101','3.00')
    ) AS p(store_id,item_id,wm_yr_wk,sell_price);
    CREATE SCHEMA raw;
    CREATE TABLE raw.m5_prices AS SELECT * FROM fixture_source;
    CREATE TABLE raw.m5_sales_wide AS SELECT * FROM (VALUES ('S','A'),('S','B')) AS s(store_id,item_id);
    CREATE TABLE raw.m5_calendar AS SELECT * FROM (VALUES ('11101'),('11102')) AS c(wm_yr_wk);
    """
    cases = [
        ('clean_tiny_fixture', '', {'valid_numeric_price_rows': 3, 'minimum_price': '1.25', 'maximum_price': 3, 'source_only_rows': 0, 'table_only_rows': 0}),
        ('missing_price_values', "UPDATE raw.m5_prices SET sell_price=CASE WHEN wm_yr_wk='11101' THEN NULL ELSE ' ' END WHERE item_id='A';",
         {'missing_required_rows': 2, 'invalid_price_rows': 0, 'valid_numeric_price_rows': 1, 'source_only_rows': 2, 'table_only_rows': 2}),
        ('invalid_text', "UPDATE raw.m5_prices SET sell_price='bad' WHERE item_id='B';",
         {'invalid_price_rows': 1, 'valid_numeric_price_rows': 2}),
        ('nonfinite_price_values', "UPDATE raw.m5_prices SET sell_price=CASE WHEN wm_yr_wk='11101' THEN 'NaN' ELSE 'Infinity' END WHERE item_id='A';",
         {'invalid_price_rows': 2, 'valid_numeric_price_rows': 1, 'minimum_price': 3, 'maximum_price': 3}),
        ('nonpositive_prices', "UPDATE raw.m5_prices SET sell_price=CASE WHEN wm_yr_wk='11101' THEN '0' ELSE '-1' END WHERE item_id='A';",
         {'nonpositive_price_rows': 2, 'valid_numeric_price_rows': 3}),
        ('additional_precision', "UPDATE raw.m5_prices SET sell_price='1.234567891' WHERE item_id='A' AND wm_yr_wk='11101';",
         {'invalid_price_rows': 0, 'valid_numeric_price_rows': 3, 'source_only_rows': 1, 'table_only_rows': 1}),
        ('duplicate_record', "INSERT INTO raw.m5_prices SELECT * FROM fixture_source WHERE item_id='B';",
         {'table_rows': 4, 'duplicate_key_rows': 1, 'source_only_rows': 0, 'table_only_rows': 1}),
        ('missing_record', "DELETE FROM raw.m5_prices WHERE item_id='A' AND wm_yr_wk='11102';",
         {'table_rows': 2, 'sales_pairs_without_any_price': 0, 'source_only_rows': 1, 'table_only_rows': 0}),
        ('unknown_pair', "UPDATE raw.m5_prices SET store_id='unknown' WHERE item_id='B';",
         {'orphan_item_store_rows': 1, 'sales_pairs_without_any_price': 1, 'source_only_rows': 1, 'table_only_rows': 1}),
        ('invalid_and_unknown_weeks', "UPDATE raw.m5_prices SET wm_yr_wk=CASE WHEN wm_yr_wk='11101' THEN 'bad' ELSE '99999' END WHERE item_id='A';",
         {'invalid_week_code_rows': 1, 'unknown_calendar_week_rows': 2}),
        ('sales_pair_without_prices', "DELETE FROM raw.m5_prices WHERE item_id='A';",
         {'sales_pairs_without_any_price': 1, 'source_only_rows': 2, 'table_only_rows': 0}),
        ('equivalent_numeric_text', "UPDATE raw.m5_prices SET sell_price='1.2500' WHERE item_id='A' AND wm_yr_wk='11101';",
         {'valid_numeric_price_rows': 3, 'minimum_price': '1.25', 'maximum_price': 3, 'source_only_rows': 1, 'table_only_rows': 1}),
    ]
    results = []
    for name, mutation, expected in cases:
        rows, seconds = run_sql(fixture_setup + mutation + '\n' + fixture_audit)
        actual = {row['check_name']: row['actual'] for row in rows}
        assert len(rows) == 15
        assert all(Decimal(actual[key]) == Decimal(str(value)) for key, value in expected.items()), (name, actual, expected)
        results.append({'case': name, 'assertions_passed': True, 'elapsed_seconds': seconds,
                        'checked_actuals': {key: actual[key] for key in expected}})
    report = {
        'checked_at_utc': datetime.now(timezone.utc).isoformat(), 'executor': 'assistant',
        'engine': subprocess.check_output([args.duckdb, '-version'], text=True).strip(),
        'database': ':memory:', 'settings': {'threads': 2, 'memory_limit': '3GB'},
        'script': 'sql/07_audit_prices.sql', 'script_sha256': sha256(audit_path),
        'source_sha256': hashes, 'source_hashes_unchanged': True,
        'reference_scope': 'Only item_id/store_id from the sales CSV and wm_yr_wk from calendar are imported as reference projections.',
        'baseline_checks_passed': 15, 'baseline_setup_and_audit_seconds': elapsed,
        'baseline_results': baseline, 'fixture_cases_passed': len(results), 'fixture_cases': results,
        'scope': 'Assistant real-source baseline and tiny fixtures only. Learner detailed price audit remains pending. No daily price-coverage check or sales-value calculation.',
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'baseline_checks_passed': 15, 'fixture_cases_passed': len(results)}))


if __name__ == '__main__':
    main()
