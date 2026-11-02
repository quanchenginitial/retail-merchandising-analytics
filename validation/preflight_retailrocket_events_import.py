"""Verify only the Retailrocket events raw import in isolated DuckDB databases.

Real source records and identifiers never enter exports, public evidence or logs.
The source CSV remains immutable; no learner database is opened.
"""
import argparse
import csv
import hashlib
import json
import subprocess
import tempfile
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


SOURCE = 'D:/database/retailrocket/events.csv'
SOURCE_SHA = '3745aa83238b1e6d44d8fda209807899f420084398f94ddf745f3cbcfecbf9e7'
FIELDS = ['timestamp', 'visitorid', 'event', 'itemid', 'transactionid']
COLUMNS = ['check_order', 'check_name', 'actual', 'expected', 'status']
CHECKS = ['row_count', 'column_count', 'varchar_column_count', 'column_sequence_errors',
          'missing_required_rows', 'invalid_timestamp_rows', 'invalid_visitorid_rows',
          'invalid_itemid_rows', 'invalid_transactionid_rows', 'unexpected_event_rows',
          'view_event_rows', 'addtocart_event_rows', 'transaction_event_rows',
          'transactions_missing_id', 'null_transactionid_rows', 'source_rows_absent_from_table',
          'table_rows_absent_from_source', 'duplicate_surplus_rows_preserved']
EXPECTED = [2756101, 5, 5, 0, 0, 0, 0, 0, 0, 0, 2664312, 69332, 22457, 0, 2733644, 0, 0, 460]
COUNT_SQL = ('SELECT 2756101 AS expected_rows,2664312 AS expected_views,\n'
             '        69332 AS expected_carts,22457 AS expected_transactions,2733644 AS expected_null_transaction_ids')


def sha256(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def report_hash(rows):
    payload = ''.join(json.dumps([row[key] for key in COLUMNS], separators=(',', ':')) + '\n' for row in rows)
    return hashlib.sha256(payload.encode()).hexdigest()


def assert_report(rows, expected):
    assert len(rows) == 18, 'Unexpected aggregate report length'
    for index, (row, name, value) in enumerate(zip(rows, CHECKS, expected), start=1):
        assert list(row) == COLUMNS, 'Unexpected aggregate report fields/order'
        assert row == dict(check_order=index, check_name=name, actual=value, expected=value, status='PASS'), 'Aggregate report mismatch'


def fixture_sql(sql, path, rows):
    counts = Counter(row[2] for row in rows)
    expected_counts = (f'SELECT {len(rows)} AS expected_rows,{counts["view"]} AS expected_views,\n'
                       f'        {counts["addtocart"]} AS expected_carts,{counts["transaction"]} AS expected_transactions,'
                       f'{sum(row[4] == "" for row in rows)} AS expected_null_transaction_ids')
    assert sql.count(COUNT_SQL) == 1 and sql.count(SOURCE) == 2
    return sql.replace(COUNT_SQL, expected_counts).replace(SOURCE, path.as_posix().replace("'", "''"))


def write_fixture(path, rows):
    with path.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(FIELDS)
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--duckdb', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--fixtures-only', action='store_true')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    script_path = 'sql/54_import_retailrocket_events.sql'
    validator_path = 'validation/preflight_retailrocket_events_import.py'
    audit_path = 'data/retailrocket_source_audit.json'
    output_path = root / 'data/retailrocket_events_import_preflight.json'
    assert args.output.resolve() == output_path.resolve(), 'Output must be the fixed aggregate evidence path'
    independent_path = 'data/retailrocket_independent_checks.json'
    code_paths = [script_path, validator_path, audit_path, 'scripts/audit_retailrocket_sources.py',
                  independent_path, 'validation/retailrocket_source_check.sql']
    hashes = {path: sha256(root / path) for path in code_paths}
    sql = (root / script_path).read_text(encoding='utf-8')
    assert 'CREATE TABLE rr_raw.events AS' in sql and 'OR REPLACE' not in sql and 'CREATE TABLE IF NOT EXISTS' not in sql
    assert sql.count('EXCEPT ALL') == 2 and sql.count('ignore_errors=false') == 2
    assert sql.count('strict_mode=true') == 2 and sql.count('force_not_null=') == 2
    audit = json.loads((root / audit_path).read_text(encoding='utf-8'))
    source_evidence = audit['files']['events.csv']
    assert audit['all_checks_passed'] and source_evidence['sha256'] == SOURCE_SHA
    assert source_evidence['rows'] == EXPECTED[0] and source_evidence['column_names'] == FIELDS
    assert source_evidence['event_counts'] == {'view': EXPECTED[10], 'addtocart': EXPECTED[11], 'transaction': EXPECTED[12]}
    assert source_evidence['empty_fields']['transactionid'] == EXPECTED[14]
    independent = json.loads((root / independent_path).read_text(encoding='utf-8'))
    assert independent['source_before']['events.csv']['sha256'] == SOURCE_SHA
    assert independent['source_hashes_unchanged']
    assert independent['exact_event_duplicates']['surplus_rows'] == EXPECTED[17]
    tmp_root = root / 'tmp'
    tmp_root.mkdir(exist_ok=True)

    def execute(database, folder, query, allow_error=False):
        assert folder.resolve().is_relative_to(tmp_root.resolve()), 'Temporary folder escapes repository tmp'
        if database != ':memory:':
            assert Path(database).resolve().is_relative_to(folder.resolve()), 'Database escapes temporary folder'
        spill = (folder / 'spill').as_posix().replace("'", "''")
        settings = f"SET threads=2; SET memory_limit='2GB'; SET temp_directory='{spill}';\n"
        started = time.perf_counter()
        run = subprocess.run([args.duckdb, str(database), '-bail', '-json'], input=settings + query,
                             text=True, encoding='utf-8', capture_output=True)
        # DuckDB errors can quote source values: never include stdout/stderr in diagnostics.
        if not allow_error:
            assert run.returncode == 0, 'Isolated DuckDB execution failed; source diagnostics withheld'
        return run, round(time.perf_counter() - started, 3)

    cases = []
    with tempfile.TemporaryDirectory(prefix='rr-events-fixture-', dir=tmp_root) as temporary:
        folder = Path(temporary)
        source = folder / 'synthetic.csv'
        database = folder / 'fixture.duckdb'
        rows = [['0000000000001', '001', 'view', '010', ''],
                ['0000000000001', '001', 'view', '010', ''],
                ['2', '2', 'addtocart', '20', ''], ['3', '2', 'transaction', '20', '009'],
                ['4', '3', 'view', '30', '']]
        write_fixture(source, rows)
        adjusted = fixture_sql(sql, source, rows)
        run, _ = execute(database, folder, adjusted)
        assert_report(json.loads(run.stdout), [5, 5, 5, 0, 0, 0, 0, 0, 0, 0, 3, 1, 1, 0, 4, 0, 0, 1])
        raw, _ = execute(database, folder, 'SELECT timestamp,visitorid,event,itemid,transactionid FROM rr_raw.events ORDER BY rowid;')
        expected_rows = [dict(zip(FIELDS, [*row[:4], row[4] or None])) for row in rows]
        assert json.loads(raw.stdout) == expected_rows, 'Synthetic raw strings or duplicate positions changed'
        rerun, _ = execute(database, folder, adjusted, allow_error=True)
        assert rerun.returncode != 0 and 'already exists' in rerun.stderr, 'Existing table must not be replaced'
        suffix = adjusted[adjusted.index('WITH expected_counts AS ('):]
        lost, _ = execute(database, folder, 'DELETE FROM rr_raw.events WHERE rowid=(SELECT MIN(rowid) FROM rr_raw.events);\n' + suffix)
        observed = {row['check_name']: row for row in json.loads(lost.stdout)}
        assert observed['source_rows_absent_from_table']['actual'] == 1 and observed['source_rows_absent_from_table']['status'] == 'FAIL'
        assert observed['table_rows_absent_from_source']['actual'] == 0
        assert observed['duplicate_surplus_rows_preserved']['actual'] == 0 and observed['duplicate_surplus_rows_preserved']['expected'] == 1
        cases.append(dict(case='preserve_duplicate_null_and_leading_zero_strings_reject_reimport_detect_lost_multiplicity', passed=True))
    assert not folder.exists()

    with tempfile.TemporaryDirectory(prefix='rr-events-fixture-', dir=tmp_root) as temporary:
        folder = Path(temporary)
        source = folder / 'synthetic.csv'
        database = folder / 'fixture.duckdb'
        rows = [[' 5 ', '4', ' view ', '40', ''], ['6', '', 'transaction', '50', ''],
                ['7', '5', 'view', '60', ' 123 ']]
        write_fixture(source, rows)
        adjusted = fixture_sql(sql, source, rows)
        run, _ = execute(database, folder, adjusted)
        observed = {row['check_name']: row for row in json.loads(run.stdout)}
        for name in ['missing_required_rows', 'invalid_timestamp_rows', 'invalid_visitorid_rows',
                     'invalid_transactionid_rows', 'unexpected_event_rows', 'transactions_missing_id']:
            assert observed[name]['actual'] == 1 and observed[name]['status'] == 'FAIL', 'Synthetic quality check failed'
        raw, _ = execute(database, folder, 'SELECT timestamp,visitorid,event,itemid,transactionid FROM rr_raw.events ORDER BY rowid;')
        assert json.loads(raw.stdout) == [dict(zip(FIELDS, [*row[:4], row[4] or None])) for row in rows], 'Raw whitespace or required empty string changed'
        assert observed['source_rows_absent_from_table']['actual'] == observed['table_rows_absent_from_source']['actual'] == 0
        cases.append(dict(case='retain_whitespace_and_required_empty_strings_but_flag_invalid_fields', passed=True))
    assert not folder.exists()

    with tempfile.TemporaryDirectory(prefix='rr-events-fixture-', dir=tmp_root) as temporary:
        folder = Path(temporary)
        source = folder / 'synthetic.csv'
        rows = [['1', '1', 'view', '1', '', 'unexpected_extra_field']]
        write_fixture(source, rows)
        rejected, _ = execute(':memory:', folder, fixture_sql(sql, source, rows), allow_error=True)
        assert rejected.returncode != 0, 'Malformed CSV width was silently accepted'
        cases.append(dict(case='strict_csv_rejects_extra_field_without_skipping_row', passed=True, expected_rejection=True))
    assert not folder.exists()
    print(json.dumps({'focused_cases_passed': len(cases)}), flush=True)
    if args.fixtures_only:
        return

    source = Path(SOURCE)
    source_hash = sha256(source)
    assert source_hash == SOURCE_SHA and source.stat().st_size == source_evidence['size_bytes'], 'Source differs from audited snapshot'
    with source.open('r', encoding='utf-8', newline='') as stream:
        assert next(csv.reader(stream, strict=True)) == FIELDS, 'Source header changed'
    historical = {str(path.relative_to(root)): sha256(path) for path in (root / 'data').glob('*preflight.json')
                  if path.resolve() != output_path.resolve()}
    with tempfile.TemporaryDirectory(prefix='rr-events-import-', dir=tmp_root) as temporary:
        folder = Path(temporary)
        run, elapsed = execute(':memory:', folder, sql)
        report = json.loads(run.stdout)
        assert_report(report, EXPECTED)
    assert not folder.exists()
    assert sha256(source) == source_hash, 'Source changed during import preflight'
    assert all(sha256(root / path) == digest for path, digest in hashes.items()), 'Code or source audit changed during preflight'
    assert all(sha256(root / path) == digest for path, digest in historical.items()), 'Historical preflight changed'
    evidence = dict(
        checked_at_utc=datetime.now(timezone.utc).isoformat(), executor='assistant',
        engine=subprocess.check_output([args.duckdb, '-version'], text=True).strip(),
        script=script_path, script_sha256=hashes[script_path], validator=validator_path, validator_sha256=hashes[validator_path],
        code_and_dependency_sha256=hashes, source_audit=audit_path, source_audit_sha256=hashes[audit_path],
        independent_source_checks=independent_path, independent_source_checks_sha256=hashes[independent_path],
        source_file='events.csv', source_bytes=source.stat().st_size, source_sha256=source_hash,
        source_hash_unchanged=True, source_header=FIELDS, database=':memory:',
        preflight_settings={'threads': 2, 'memory_limit': '2GB'},
        table='rr_raw.events', raw_fields=5, raw_types=['VARCHAR'] * 5,
        import_semantics='Preserve all observations and exact field strings, including duplicates and leading zeros; only exact-empty transactionid becomes SQL NULL. No timestamp conversion, trim, filter, deduplication or replacement.',
        full_source_multiset_comparison='Both directions use EXCEPT ALL on all five raw fields with identical documented NULL parsing; zero difference rows preserves multiplicity, including NULL-bearing duplicate rows.',
        source_rows_compared=2756101, source_fields_compared=5, source_only_rows=0, table_only_rows=0,
        duplicate_surplus_rows_preserved=460, duplicate_surplus_definition='Total rows minus distinct full five-field tuples; retained, not treated as an automatic defect.',
        expected_report_basis='Frozen local source audit row/type/missingness counts plus independently observed 460 duplicate surplus; complete CSV/table multiset checks and targeted synthetic preservation/detection cases.',
        report_rows=18, report_columns=5, output_columns=COLUMNS, checks_passed=18,
        results=report, report_sha256=report_hash(report),
        report_fingerprint_contract='SHA-256 of ordered compact JSON arrays in output_columns order, each followed by LF; counts/order are integers, labels/status are strings.',
        fixture_case_count=len(cases), fixture_cases=cases,
        source_records_or_identifiers_exported_or_logged=False,
        learner_database_opened=False, m5_queries_or_historical_suites_rerun=False,
        historical_preflight_files_unchanged=len(historical), temporary_databases_and_spills_removed=True,
        elapsed_import_and_checks_seconds=elapsed,
        timing_scope='One CLI execution includes import and all checks; excludes hashes and synthetic fixtures. memory_limit is not a total-process cap.',
        scope='Assistant bounded raw import preflight passed; learner SQL54 execution and acceptance pending. No Retailrocket staging, deduplication policy, session/order definitions, as-of joins or behavioral metrics have been implemented. Raw records are not validated persons or orders; no M5 identity linkage.')
    output_path.write_text(json.dumps(evidence, indent=2) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps({'checks_passed': 18, 'report_rows': 18, 'report_columns': 5,
                      'focused_cases_passed': len(cases), 'source_rows_compared': 2756101,
                      'duplicate_surplus_rows_preserved': 460, 'report_sha256': evidence['report_sha256'],
                      'elapsed_seconds': elapsed}), flush=True)


if __name__ == '__main__':
    main()
