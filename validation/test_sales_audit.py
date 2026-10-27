"""Check the real sales source once, then exercise audit logic on tiny fixtures.

All databases are :memory:. No learner database is opened or modified.
Fault fixtures replace the CSV relation; production expected totals are unchanged,
so fixture assertions check selected actual diagnostics, not all PASS statuses.
"""
import argparse
import hashlib
import json
import subprocess
import tempfile
import time
from datetime import datetime, timezone
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
    audit_path = root / 'sql/05_audit_sales.sql'
    audit = audit_path.read_text(encoding='utf-8')
    setup = (root / 'sql/04_import_sales.sql').read_text(encoding='utf-8').split('-- BASIC CHECKS:')[0]
    source_path = Path('D:/database/m5-forecasting-accuracy/sales_train_evaluation.csv')
    registered = json.loads((root / 'data/m5_source_audit.json').read_text(encoding='utf-8'))
    before = sha256(source_path)
    assert before == registered['files'][source_path.name]['sha256'], 'Source snapshot changed'
    tmp_root = root / 'tmp'
    tmp_root.mkdir(exist_ok=True)

    def run_sql(sql):
        with tempfile.TemporaryDirectory(prefix='sales-audit-', dir=tmp_root) as spill:
            spill_sql = Path(spill).as_posix().replace("'", "''")
            prefix = f"SET threads=2; SET memory_limit='3GB'; SET temp_directory='{spill_sql}';\n"
            started = time.perf_counter()
            run = subprocess.run([args.duckdb, ':memory:', '-bail', '-json'],
                                 input=prefix + sql, text=True, encoding='utf-8',
                                 capture_output=True, check=True)
            rows = json.loads(run.stdout)
            # DuckDB CLI serializes HUGEINT as JSON strings. Keep exact integers
            # in Python; the SQL retains HUGEINT for safe SUM(BIGINT) totals.
            for row in rows:
                for key in ('actual', 'expected'):
                    if row[key] is not None:
                        row[key] = int(row[key])
            return rows, round(time.perf_counter() - started, 3)

    baseline, elapsed = run_sql(setup + '\n' + audit)
    assert len(baseline) == 15 and all(row['status'] == 'PASS' for row in baseline), baseline
    assert sha256(source_path) == before, 'Source changed during baseline'
    print(json.dumps({'baseline_checks_passed': 15, 'import_and_audit_seconds': elapsed}), flush=True)

    source_expression = """read_csv(
        'D:/database/m5-forecasting-accuracy/sales_train_evaluation.csv',
        header = true, all_varchar = true
    )"""
    assert audit.count(source_expression) == 1
    fixture_audit = audit.replace(source_expression, 'fixture_source')
    fixture_setup = """
    CREATE TABLE fixture_source AS
    SELECT * FROM (VALUES
      ('A_S_evaluation', 'A', 'D', 'C', 'S', 'CA', '2', '5'),
      ('B_S_evaluation', 'B', 'D', 'C', 'S', 'CA', '3', '4')
    ) AS t(id,item_id,dept_id,cat_id,store_id,state_id,d_1,d_2);
    CREATE SCHEMA raw;
    CREATE TABLE raw.m5_sales_wide AS SELECT * FROM fixture_source;
    """
    cases = [
        ('clean_tiny_fixture', '', {'daily_cells': 4, 'total_units': 14, 'source_only_rows': 0, 'table_only_rows': 0}),
        ('null_cell', "UPDATE raw.m5_sales_wide SET d_1=NULL WHERE item_id='A';",
         {'daily_cells': 4, 'missing_sales_cells': 1, 'valid_integer_sales_cells': 3, 'source_only_rows': 1, 'table_only_rows': 1}),
        ('whitespace_cell', "UPDATE raw.m5_sales_wide SET d_1=' ' WHERE item_id='A';",
         {'daily_cells': 4, 'missing_sales_cells': 1, 'invalid_integer_sales_cells': 0}),
        ('decimal_cell', "UPDATE raw.m5_sales_wide SET d_1='1.5' WHERE item_id='A';",
         {'invalid_integer_sales_cells': 1, 'total_units': 12, 'source_only_rows': 1, 'table_only_rows': 1}),
        ('exponent_cell', "UPDATE raw.m5_sales_wide SET d_1='1e2' WHERE item_id='A';",
         {'invalid_integer_sales_cells': 1, 'valid_integer_sales_cells': 3}),
        ('overflow_cell', "UPDATE raw.m5_sales_wide SET d_1='9223372036854775808' WHERE item_id='A';",
         {'invalid_integer_sales_cells': 1, 'valid_integer_sales_cells': 3}),
        ('negative_cell', "UPDATE raw.m5_sales_wide SET d_1='-2' WHERE item_id='A';",
         {'negative_sales_cells': 1, 'valid_integer_sales_cells': 4, 'total_units': 10}),
        ('duplicate_row', "INSERT INTO raw.m5_sales_wide SELECT * FROM fixture_source WHERE item_id='A';",
         {'table_rows': 3, 'daily_cells': 6, 'source_only_rows': 0, 'table_only_rows': 1}),
        ('missing_row', "DELETE FROM raw.m5_sales_wide WHERE item_id='A';",
         {'table_rows': 1, 'daily_cells': 2, 'source_only_rows': 1, 'table_only_rows': 0}),
        ('offsetting_values', "UPDATE raw.m5_sales_wide SET d_1=CASE WHEN item_id='A' THEN '3' ELSE '2' END;",
         {'daily_cells': 4, 'total_units': 14, 'zero_sales_cells': 0, 'max_daily_units': 5, 'source_only_rows': 2, 'table_only_rows': 2}),
        ('identifier_change', "UPDATE raw.m5_sales_wide SET id='changed' WHERE item_id='A';",
         {'id_label_mismatches': 1, 'source_only_rows': 1, 'table_only_rows': 1}),
        ('column_name_change', 'ALTER TABLE raw.m5_sales_wide RENAME COLUMN d_2 TO d_3;',
         {'daily_cells': 4, 'total_units': 14, 'source_only_rows': 2, 'table_only_rows': 2}),
    ]
    results = []
    for name, mutation, expected in cases:
        rows, seconds = run_sql(fixture_setup + mutation + '\n' + fixture_audit)
        actual = {row['check_name']: row['actual'] for row in rows}
        assert len(rows) == 15
        assert all(actual[key] == value for key, value in expected.items()), (name, actual, expected)
        results.append({'case': name, 'assertions_passed': True, 'elapsed_seconds': seconds,
                        'checked_actuals': {key: actual[key] for key in expected}})
    report = {
        'checked_at_utc': datetime.now(timezone.utc).isoformat(), 'executor': 'assistant',
        'engine': subprocess.check_output([args.duckdb, '-version'], text=True).strip(),
        'database': ':memory:', 'settings': {'threads': 2, 'memory_limit': '3GB'},
        'script': 'sql/05_audit_sales.sql', 'script_sha256': sha256(audit_path),
        'source_file': source_path.name, 'source_sha256': before, 'source_hash_unchanged': True,
        'baseline_checks_passed': 15, 'baseline_import_and_audit_seconds': elapsed,
        'baseline_results': baseline, 'fixture_cases_passed': len(results), 'fixture_cases': results,
        'scope': 'Real-source baseline plus tiny disposable fixtures. Learner sales-value audit remains pending. Full-record comparison uses exact JSON text, not a checksum.',
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'baseline_checks_passed': 15, 'fixture_cases_passed': len(results)}))


if __name__ == '__main__':
    main()
