"""Run real-source baseline and synthetic fault tests in disposable memory DBs.

The SQL source path must point to the audited M5 calendar snapshot.
Never opens the learner's persistent DuckDB file.
"""
import argparse
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--duckdb', required=True)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    setup = (root / 'sql/02_import_calendar.sql').read_text(encoding='utf-8').split('-- On a repeat visit')[0]
    audit_path = root / 'sql/03_audit_calendar.sql'
    audit = audit_path.read_text(encoding='utf-8')
    cases = [
        ('clean_source', '', {}),
        ('duplicate_row', "INSERT INTO raw.m5_calendar SELECT * FROM raw.m5_calendar WHERE d='d_1';",
         {'table_rows': 1970, 'duplicate_dates': 1, 'duplicate_day_ids': 1, 'table_only_rows': 1, 'source_only_rows': 0}),
        ('missing_row', "DELETE FROM raw.m5_calendar WHERE d='d_1';",
         {'table_rows': 1968, 'source_only_rows': 1, 'table_only_rows': 0}),
        ('null_snap', "UPDATE raw.m5_calendar SET snap_CA=NULL WHERE d='d_1';",
         {'invalid_snap_rows': 1, 'missing_core_rows': 1, 'source_only_rows': 1, 'table_only_rows': 1}),
        ('invalid_date', "UPDATE raw.m5_calendar SET date='invalid-date' WHERE d='d_1';",
         {'invalid_dates': 1, 'day_date_mapping_errors': 1, 'calendar_attribute_errors': 1}),
        ('changed_event_text', "UPDATE raw.m5_calendar SET event_name_1='synthetic_changed_event' WHERE d=(SELECT MIN(d) FROM raw.m5_calendar WHERE event_name_1 IS NOT NULL);",
         {'event_1_pair_errors': 0, 'event_1_nulls': 1807, 'source_only_rows': 1, 'table_only_rows': 1}),
    ]
    results = []
    for name, mutation, expected in cases:
        run = subprocess.run([args.duckdb, ':memory:', '-json'], input=setup + '\n' + mutation + '\n' + audit,
                             text=True, encoding='utf-8', capture_output=True, check=True)
        checks = json.loads(run.stdout)
        actual = {row['check_name']: row['actual'] for row in checks}
        assert len(checks) == 17, name
        assert all(actual[key] == value for key, value in expected.items()), name
        if not mutation:
            assert all(row['status'] == 'PASS' for row in checks), name
        else:
            assert any(row['status'] == 'FAIL' for row in checks), name
        results.append({'case': name, 'synthetic_fault': bool(mutation), 'assertions_passed': True,
                        'checked_actuals': {key: actual[key] for key in expected},
                        'failed_check_names': [row['check_name'] for row in checks if row['status'] == 'FAIL'],
                        **({'baseline_results': checks} if not mutation else {})})
    report = {'checked_at_utc': datetime.now(timezone.utc).isoformat(),
              'engine': subprocess.check_output([args.duckdb, '-version'], text=True).strip(),
              'database': ':memory:', 'executor': 'assistant',
              'audit_script_sha256': hashlib.sha256(audit_path.read_bytes()).hexdigest(),
              'scope': 'All mutations affect disposable in-memory fixtures only. Learner detailed audit remains pending.',
              'cases_passed': len(results), 'cases': results}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'cases_passed': len(results), 'baseline_checks_passed': 17}))


if __name__ == '__main__':
    main()
