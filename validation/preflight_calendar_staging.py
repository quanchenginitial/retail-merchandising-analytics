"""Preflight the calendar staging script in a disposable in-memory database.

Only the calendar CSV is read. The learner database is never opened.
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
    sql_path = root / 'sql/08_stage_calendar.sql'
    source_path = Path('D:/database/m5-forecasting-accuracy/calendar.csv')
    registry = json.loads((root / 'data/m5_source_audit.json').read_text(encoding='utf-8'))
    source_hash = sha256(source_path)
    assert source_hash == registry['files']['calendar.csv']['sha256']
    setup = (root / 'sql/02_import_calendar.sql').read_text(encoding='utf-8').split('-- On a repeat visit')[0]
    started = time.perf_counter()
    run = subprocess.run([args.duckdb, ':memory:', '-bail', '-json'],
                         input=setup + '\n' + sql_path.read_text(encoding='utf-8'),
                         text=True, encoding='utf-8', capture_output=True, check=True)
    elapsed = round(time.perf_counter() - started, 3)
    rows = json.loads(run.stdout)
    assert len(rows) == 13 and all(row['status'] == 'PASS' for row in rows), rows
    assert sha256(source_path) == source_hash
    report = {
        'checked_at_utc': datetime.now(timezone.utc).isoformat(), 'executor': 'assistant',
        'engine': subprocess.check_output([args.duckdb, '-version'], text=True).strip(),
        'database': ':memory:', 'script': 'sql/08_stage_calendar.sql',
        'script_sha256': sha256(sql_path), 'source_file': 'calendar.csv',
        'source_sha256': source_hash, 'source_hash_unchanged': True,
        'elapsed_raw_setup_staging_and_checks_seconds': elapsed,
        'checks_passed': 13, 'results': rows,
        'scope': 'Assistant calendar staging preflight only. Round-trip comparison uses the imported raw calendar, not a second CSV read. Learner staging remains pending; no core dimension or sales-price coverage is built.',
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'checks_passed': 13, 'elapsed_seconds': elapsed}))


if __name__ == '__main__':
    main()
