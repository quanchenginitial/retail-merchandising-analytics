"""Execute the sales import once in a disposable in-memory DuckDB database.

Reads the supplied source; never opens or changes the learner's database.
This checks import structure and identifiers, not all daily sales values.
"""
import argparse
import hashlib
import json
import subprocess
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
    sql_path = root / 'sql/04_import_sales.sql'
    source_path = Path('D:/database/m5-forecasting-accuracy/sales_train_evaluation.csv')
    recorded = json.loads((root / 'data/m5_source_audit.json').read_text(encoding='utf-8'))
    source_hash = sha256(source_path)
    assert source_hash == recorded['files'][source_path.name]['sha256'], 'Source snapshot changed'
    started = time.perf_counter()
    run = subprocess.run(
        [args.duckdb, ':memory:', '-bail', '-json'],
        input="SET threads=2; SET memory_limit='2GB';\n" + sql_path.read_text(encoding='utf-8'),
        text=True, encoding='utf-8', capture_output=True, check=True,
    )
    elapsed = time.perf_counter() - started
    rows = json.loads(run.stdout)
    assert len(rows) == 14, 'Unexpected check count'
    assert all(row['status'] == 'PASS' for row in rows), rows
    assert sha256(source_path) == source_hash, 'Source changed during preflight'
    report = {
        'checked_at_utc': datetime.now(timezone.utc).isoformat(),
        'executor': 'assistant',
        'engine': subprocess.check_output([args.duckdb, '-version'], text=True).strip(),
        'database': ':memory:',
        'preflight_settings': {'threads': 2, 'memory_limit': '2GB'},
        'script': 'sql/04_import_sales.sql',
        'script_sha256': sha256(sql_path),
        'source_file': source_path.name,
        'source_sha256': source_hash,
        'source_hash_unchanged': True,
        'elapsed_import_and_checks_seconds': round(elapsed, 3),
        'checks_passed': len(rows),
        'results': rows,
        'scope': 'Assistant in-memory import and basic checks only. Learner sales import and full-value reconciliation remain pending.',
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'checks_passed': len(rows), 'elapsed_seconds': round(elapsed, 3)}))


if __name__ == '__main__':
    main()
