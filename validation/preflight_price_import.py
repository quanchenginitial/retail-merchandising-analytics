"""Execute the price import once in a disposable in-memory DuckDB database.

Checks structure and keys, not price validity or sales-date coverage.
Never opens or modifies the learner's persistent database.
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
    sql_path = root / 'sql/06_import_prices.sql'
    source_path = Path('D:/database/m5-forecasting-accuracy/sell_prices.csv')
    recorded = json.loads((root / 'data/m5_source_audit.json').read_text(encoding='utf-8'))
    source_hash = sha256(source_path)
    assert source_hash == recorded['files'][source_path.name]['sha256'], 'Source snapshot changed'
    tmp_root = root / 'tmp'
    tmp_root.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='price-import-', dir=tmp_root) as spill:
        assert Path(spill).resolve().is_relative_to(tmp_root.resolve())
        spill_sql = Path(spill).as_posix().replace("'", "''")
        settings = f"SET threads=2; SET memory_limit='2GB'; SET temp_directory='{spill_sql}';\n"
        started = time.perf_counter()
        run = subprocess.run(
            [args.duckdb, ':memory:', '-bail', '-json'],
            input=settings + sql_path.read_text(encoding='utf-8'),
            text=True, encoding='utf-8', capture_output=True, check=True,
        )
        elapsed = time.perf_counter() - started
    rows = json.loads(run.stdout)
    for row in rows:
        for key in ('actual', 'expected'):
            if row[key] is not None:
                row[key] = int(row[key])
    assert len(rows) == 12, 'Unexpected check count'
    assert all(row['status'] == 'PASS' for row in rows), rows
    assert sha256(source_path) == source_hash, 'Source changed during preflight'
    report = {
        'checked_at_utc': datetime.now(timezone.utc).isoformat(),
        'executor': 'assistant',
        'engine': subprocess.check_output([args.duckdb, '-version'], text=True).strip(),
        'database': ':memory:',
        'preflight_settings': {'threads': 2, 'memory_limit': '2GB'},
        'script': 'sql/06_import_prices.sql',
        'script_sha256': sha256(sql_path),
        'source_file': source_path.name,
        'source_sha256': source_hash,
        'source_hash_unchanged': True,
        'elapsed_import_and_checks_seconds': round(elapsed, 3),
        'checks_passed': len(rows),
        'results': rows,
        'scope': 'Assistant in-memory price import and basic checks only. Learner price import, numeric audit, full source reconciliation and daily sales-price coverage remain pending.',
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'checks_passed': len(rows), 'elapsed_seconds': round(elapsed, 3)}))


if __name__ == '__main__':
    main()
