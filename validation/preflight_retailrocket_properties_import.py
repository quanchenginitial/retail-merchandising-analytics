"""Bounded raw property import: exact SQL multisets, frozen source audit, tiny fixtures.

Never open the learner database or log real attribute records. Only source hashes
and headers are reread with Python; no full-source Python Counter is constructed.
"""
import argparse
import csv
import ctypes
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


FILES = ['item_properties_part1.csv', 'item_properties_part2.csv']
SOURCE_DIR = Path('D:/database/retailrocket')
SOURCE_HASHES = {
    FILES[0]: '30aad5aeca58b2dc27dcc73e1708565f5818e45adb3eb57401f91e87355b0b81',
    FILES[1]: 'd5e7d1a91dc40f522aeb596b267e6c87d8aed689a7192d12369cfb165eb987e5',
}
SOURCE_BYTES = {FILES[0]: 484315749, FILES[1]: 408929907}
SOURCE_ROWS = {FILES[0]: 10999999, FILES[1]: 9275903}
RAW_FIELDS = ['timestamp', 'itemid', 'property', 'value']
TABLE_FIELDS = RAW_FIELDS + ['source_file']
COLUMNS = ['check_order', 'check_name', 'actual', 'expected', 'status']
CHECKS = ['row_count', 'part1_row_count', 'part2_row_count', 'column_count',
          'varchar_column_count', 'column_sequence_errors', 'missing_required_rows',
          'invalid_timestamp_rows', 'invalid_itemid_rows', 'unknown_source_file_rows',
          'part1_source_rows_absent_from_table', 'part1_table_rows_absent_from_source',
          'part2_source_rows_absent_from_table', 'part2_table_rows_absent_from_source']
EXPECTED = [20275902, 10999999, 9275903, 5, 5] + [0] * 9
COUNT_SQL = 'SELECT 20275902 AS expected_rows,10999999 AS expected_part1,9275903 AS expected_part2'
CHECK_MARKER = 'CREATE OR REPLACE TEMP TABLE rr_properties_import_checks AS'
PRIVATE_FIXTURE_QUERY = 'SELECT timestamp,itemid,property,value,source_file FROM rr_raw.item_properties;'
GIB = 1024**3


def sha256(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def snapshot(path):
    before = path.stat()
    digest = sha256(path)
    after = path.stat()
    assert (before.st_size, before.st_mtime_ns) == (after.st_size, after.st_mtime_ns), 'Source changed while hashing'
    return dict(size_bytes=after.st_size, modified_time_ns=after.st_mtime_ns, sha256=digest)


def report_hash(rows):
    text = ''.join(json.dumps([row[key] for key in COLUMNS], separators=(',', ':')) + '\n' for row in rows)
    return hashlib.sha256(text.encode()).hexdigest()


def json_outputs(text):
    decoder, results = json.JSONDecoder(), []
    while text.strip():
        text = text.lstrip()
        value, end = decoder.raw_decode(text)
        results.append(value)
        text = text[end:]
    return results


def assert_report(rows, actual, expected):
    assert len(rows) == 14, 'Aggregate report length mismatch'
    for order, (row, name, value, target) in enumerate(zip(rows, CHECKS, actual, expected), 1):
        assert list(row) == COLUMNS, 'Aggregate report field/order mismatch'
        assert row == dict(check_order=order, check_name=name, actual=value, expected=target,
                           status='PASS' if value == target else 'FAIL'), 'Aggregate report value mismatch'


def write_fixture(folder, parts):
    for name, rows in zip(FILES, parts):
        with (folder / name).open('w', encoding='utf-8', newline='') as stream:
            writer = csv.writer(stream)
            writer.writerow(RAW_FIELDS)
            writer.writerows(rows)


def fixture_counter(folder):
    # Used only for tiny synthetic records, never for the real source files.
    result = Counter()
    for name in FILES:
        with (folder / name).open('r', encoding='utf-8', newline='') as stream:
            reader = csv.reader(stream, strict=True)
            assert next(reader) == RAW_FIELDS
            for row in reader:
                assert len(row) == 4
                result[tuple(row) + (name,)] += 1
    return result


def adjust_fixture(sql, folder, parts):
    replacement = f'SELECT {sum(map(len, parts))} AS expected_rows,{len(parts[0])} AS expected_part1,{len(parts[1])} AS expected_part2'
    assert sql.count(COUNT_SQL) == 1
    adjusted = sql.replace(COUNT_SQL, replacement)
    for name in FILES:
        source = (SOURCE_DIR / name).as_posix()
        assert adjusted.count(source) == 3
        adjusted = adjusted.replace(source, (folder / name).as_posix().replace("'", "''"))
    return adjusted


def memory_availability():
    if os.name != 'nt':
        return {'method': 'Windows memory API unavailable on this platform'}
    class MemoryStatus(ctypes.Structure):
        _fields_ = [('length', ctypes.c_ulong), ('load', ctypes.c_ulong),
                    ('total_phys', ctypes.c_ulonglong), ('avail_phys', ctypes.c_ulonglong),
                    ('total_page', ctypes.c_ulonglong), ('avail_page', ctypes.c_ulonglong),
                    ('total_virtual', ctypes.c_ulonglong), ('avail_virtual', ctypes.c_ulonglong),
                    ('avail_extended', ctypes.c_ulonglong)]
    status = MemoryStatus()
    status.length = ctypes.sizeof(status)
    assert ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)), 'Memory availability could not be read'
    return {'method': 'GlobalMemoryStatusEx', 'physical_memory_bytes': status.total_phys,
            'available_physical_memory_bytes': status.avail_phys,
            'available_page_file_bytes': status.avail_page}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--duckdb', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--fixtures-only', action='store_true')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    script_path = 'sql/56_import_retailrocket_properties.sql'
    validator_path = 'validation/preflight_retailrocket_properties_import.py'
    audit_path = 'data/retailrocket_source_audit.json'
    output = root / 'data/retailrocket_properties_import_preflight.json'
    assert args.output.resolve() == output.resolve(), 'Output must be the fixed aggregate evidence path'
    dependencies = [script_path, validator_path, audit_path, 'scripts/audit_retailrocket_sources.py',
                    'data/retailrocket_independent_checks.json', 'validation/retailrocket_source_check.sql',
                    'sql/54_import_retailrocket_events.sql', 'validation/preflight_retailrocket_events_import.py',
                    'data/retailrocket_events_import_preflight.json',
                    'sql/55_import_retailrocket_categories.sql', 'validation/preflight_retailrocket_categories_import.py',
                    'data/retailrocket_categories_import_preflight.json',
                    'data/retailrocket_categories_import_learner_acceptance.json',
                    'docs/RETAILROCKET_CATEGORIES_IMPORT_VALIDATION.md']
    hashes = {name: sha256(root / name) for name in dependencies}
    assert hashes['data/retailrocket_categories_import_learner_acceptance.json'] == '486f344d9fc80f2f7f2980fb9a0fdfd236c91a875ef5906a8b43d56d05137f26'
    assert hashes['docs/RETAILROCKET_CATEGORIES_IMPORT_VALIDATION.md'] == '583354d485af1a0aee5936c2c731fc0cd73920d8280c6814e956d8d9074370cd'
    sql = (root / script_path).read_text(encoding='utf-8')
    split = sql.index(CHECK_MARKER)
    import_sql, checks_sql = sql[:split], sql[split:]
    assert 'CREATE TABLE rr_raw.item_properties AS' in import_sql and 'OR REPLACE' not in import_sql
    assert 'CREATE TABLE IF NOT EXISTS' not in import_sql and import_sql.count('UNION ALL') == 1
    assert sql.count('EXCEPT ALL') == 4 and sql.count('INSERT INTO rr_properties_import_checks') == 4
    assert sql.count('strict_mode=true') == sql.count('ignore_errors=false') == 6
    assert sql.count("force_not_null=['timestamp','itemid','property','value']") == 6
    audit = json.loads((root / audit_path).read_text(encoding='utf-8'))
    assert audit['all_checks_passed']
    for name in FILES:
        observed = audit['files'][name]
        assert observed['sha256'] == SOURCE_HASHES[name] and observed['size_bytes'] == SOURCE_BYTES[name]
        assert observed['rows'] == SOURCE_ROWS[name] and observed['column_names'] == RAW_FIELDS
        assert not any(observed['empty_fields'].values()) and not observed['timestamp']['invalid_nonempty_values']
    tmp_root = root / 'tmp'
    tmp_root.mkdir(exist_ok=True)
    available_disk = shutil.disk_usage(tmp_root).free
    assert available_disk >= 12 * GIB, 'At least 12 GiB free workspace disk is required'
    memory = memory_availability()
    peak_directory_bytes = 0

    def execute(folder, database, query, phase, allow_error=False):
        nonlocal peak_directory_bytes
        assert folder.resolve().is_relative_to(tmp_root.resolve()), 'Private folder escapes repository tmp'
        if database != ':memory:':
            assert Path(database).resolve().is_relative_to(folder.resolve()), 'Private database escapes task folder'
        spill = (folder / 'spill').as_posix().replace("'", "''")
        settings = f"SET threads=2; SET memory_limit='2GB'; SET max_temp_directory_size='8GB'; SET temp_directory='{spill}';\n"
        started, next_update = time.perf_counter(), 30
        process = subprocess.Popen([args.duckdb, str(database), '-bail', '-json'], stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8')
        first = True
        try:
            while True:
                try:
                    stdout, stderr = process.communicate(input=settings + query if first else None, timeout=1)
                    break
                except subprocess.TimeoutExpired:
                    first = False
                    current = 0
                    for path in folder.rglob('*'):
                        try:
                            if path.is_file():
                                current += path.stat().st_size
                        except FileNotFoundError:
                            pass  # A spill file may be retired during this observation.
                    peak_directory_bytes = max(peak_directory_bytes, current)
                    assert current <= 12 * GIB, 'Private-directory disk budget exceeded'
                    assert shutil.disk_usage(tmp_root).free >= 2 * GIB, 'Workspace free-space reserve reached'
                    elapsed = time.perf_counter() - started
                    assert elapsed <= 600, 'Bounded DuckDB execution timeout reached'
                    if elapsed >= next_update:
                        print(json.dumps({'phase': phase, 'elapsed_seconds': round(elapsed, 1), 'private_bytes_observed': current}), flush=True)
                        next_update += 30
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate()
        # Captured diagnostics can quote source fields and must never be logged.
        if not allow_error:
            assert process.returncode == 0, 'Private DuckDB execution failed; source diagnostics withheld'
        current = sum(path.stat().st_size for path in folder.rglob('*') if path.is_file())
        peak_directory_bytes = max(peak_directory_bytes, current)
        assert current <= 12 * GIB, 'Private-directory disk budget exceeded'
        return dict(returncode=process.returncode, stdout=stdout, stderr=stderr), round(time.perf_counter() - started, 3)

    cases = []
    with tempfile.TemporaryDirectory(prefix='rr-properties-fixture-', dir=tmp_root) as temporary:
        folder = Path(temporary)
        parts = [[['0001', '001', 'categoryid', '01'], ['0001', '001', 'categoryid', '01'],
                  ['2', '002', 'custom', '  red blue n5.000  '], ['3', '003', 'available', 'NULL']],
                 [['0001', '001', 'categoryid', '01'], ['4', '004', 'custom', 'null'],
                  ['5', '005', 'custom', 'nan'], ['6', '006', 'custom', '0'], ['7', '007', 'custom', 'one,two']]]
        write_fixture(folder, parts)
        counter = fixture_counter(folder)
        adjusted = adjust_fixture(sql, folder, parts)
        load, checks = adjusted[:adjusted.index(CHECK_MARKER)], adjusted[adjusted.index(CHECK_MARKER):]
        run, _ = execute(folder, ':memory:', adjusted + '\n' + PRIVATE_FIXTURE_QUERY, 'fixture')
        report, records = json_outputs(run['stdout'])
        values = [9, 4, 5, 5, 5] + [0] * 9
        assert_report(report, values, values)
        assert all(list(row) == TABLE_FIELDS for row in records)
        assert Counter(tuple(row[key] for key in TABLE_FIELDS) for row in records) == counter, 'Synthetic text/provenance/multiplicity mismatch'
        rejected, _ = execute(folder, ':memory:', adjusted + '\n' + adjusted, 'fixture', allow_error=True)
        assert rejected['returncode'] != 0 and 'already exists' in rejected['stderr'], 'Existing raw table was not protected'
        select_one = "rowid=(SELECT MIN(rowid) FROM rr_raw.item_properties WHERE source_file='item_properties_part1.csv')"
        mutations = [
            (f'DELETE FROM rr_raw.item_properties WHERE {select_one};', {'part1_source_rows_absent_from_table': 1, 'part1_table_rows_absent_from_source': 0}),
            (f"UPDATE rr_raw.item_properties SET value='changed' WHERE {select_one};", {'part1_source_rows_absent_from_table': 1, 'part1_table_rows_absent_from_source': 1}),
            (f"UPDATE rr_raw.item_properties SET source_file='item_properties_part2.csv' WHERE {select_one};", {'part1_source_rows_absent_from_table': 1, 'part2_table_rows_absent_from_source': 1}),
            (f"UPDATE rr_raw.item_properties SET source_file='unknown.csv' WHERE {select_one};", {'unknown_source_file_rows': 1, 'part1_source_rows_absent_from_table': 1}),
        ]
        for mutation, failures in mutations:
            run, _ = execute(folder, ':memory:', load + '\n' + mutation + '\n' + checks, 'fixture')
            observed = {row['check_name']: row for row in json_outputs(run['stdout'])[0]}
            for name, value in failures.items():
                assert observed[name]['actual'] == value and observed[name]['status'] == ('FAIL' if value else 'PASS'), 'Intended corruption was not detected'
        cases.append(dict(case='preserve_duplicates_across_parts_literals_spaces_leading_zeros_and_provenance_reject_reimport_detect_corruption', passed=True))
    assert not folder.exists()

    with tempfile.TemporaryDirectory(prefix='rr-properties-fixture-', dir=tmp_root) as temporary:
        folder = Path(temporary)
        parts = [[['', '001', '', ''], ['1', ' 2 ', 'custom', '  ']], [['3.5', '3', 'custom', 'NA']]]
        write_fixture(folder, parts)
        run, _ = execute(folder, ':memory:', adjust_fixture(sql, folder, parts) + '\n' + PRIVATE_FIXTURE_QUERY, 'fixture')
        report, records = json_outputs(run['stdout'])
        actual = [3, 2, 1, 5, 5, 0, 1, 2, 1, 0, 0, 0, 0, 0]
        expected = [3, 2, 1, 5, 5] + [0] * 9
        assert_report(report, actual, expected)
        assert Counter(tuple(row[key] for key in TABLE_FIELDS) for row in records) == fixture_counter(folder), 'Invalid raw text was silently changed'
        cases.append(dict(case='preserve_empty_and_whitespace_fields_but_flag_required_and_numeric_failures', passed=True))
    assert not folder.exists()

    with tempfile.TemporaryDirectory(prefix='rr-properties-fixture-', dir=tmp_root) as temporary:
        folder = Path(temporary)
        parts = [[['1', '1', 'custom', 'x']], [['2', '2', 'custom', 'y']]]
        write_fixture(folder, parts)
        adjusted = adjust_fixture(sql, folder, parts)
        (folder / FILES[1]).unlink()
        missing, _ = execute(folder, ':memory:', adjusted, 'fixture', allow_error=True)
        assert missing['returncode'] != 0, 'Missing source part was silently accepted'
        for malformed in ([['2', '2', 'custom', 'y', 'extra']], [['2', '2', 'custom']]):
            write_fixture(folder, [parts[0], malformed])
            rejected, _ = execute(folder, ':memory:', adjusted, 'fixture', allow_error=True)
            assert rejected['returncode'] != 0, 'Malformed CSV width was skipped or padded'
        cases.append(dict(case='reject_missing_source_part_and_malformed_extra_or_missing_fields', passed=True, expected_rejection=True))
    assert not folder.exists()
    print(json.dumps({'focused_cases_passed': len(cases)}), flush=True)
    if args.fixtures_only:
        return

    source_before = {name: snapshot(SOURCE_DIR / name) for name in FILES}
    for name, observed in source_before.items():
        assert observed['sha256'] == SOURCE_HASHES[name] and observed['size_bytes'] == SOURCE_BYTES[name], 'Property source differs from audited snapshot'
        with (SOURCE_DIR / name).open('r', encoding='utf-8', newline='') as stream:
            assert next(csv.reader(stream, strict=True)) == RAW_FIELDS, 'Property source header changed'
    historical = {str(path.relative_to(root)): sha256(path) for path in (root / 'data').glob('*preflight.json')
                  if path.resolve() != output.resolve()}
    with tempfile.TemporaryDirectory(prefix='rr-properties-import-', dir=tmp_root) as temporary:
        folder = Path(temporary)
        database = folder / 'preflight.duckdb'
        run, import_elapsed = execute(folder, database, import_sql, 'real_source_import')
        assert not run['stdout'].strip(), 'Import unexpectedly emitted source output'
        print(json.dumps({'source_import_completed': True, 'elapsed_seconds': import_elapsed}), flush=True)
        run, checks_elapsed = execute(folder, database, checks_sql, 'sequential_source_comparisons')
        reports = json_outputs(run['stdout'])
        assert len(reports) == 1
        report = reports[0]
        assert_report(report, EXPECTED, EXPECTED)
        database_bytes = database.stat().st_size
    assert not folder.exists()
    source_after = {name: snapshot(SOURCE_DIR / name) for name in FILES}
    assert source_before == source_after, 'Property sources changed during preflight'
    assert all(sha256(root / name) == digest for name, digest in hashes.items()), 'Frozen code/evidence dependency changed'
    assert all(sha256(root / name) == digest for name, digest in historical.items()), 'Historical preflight changed'
    evidence = dict(
        checked_at_utc=datetime.now(timezone.utc).isoformat(), executor='assistant',
        engine=subprocess.check_output([args.duckdb, '-version'], text=True).strip(),
        script=script_path, script_sha256=hashes[script_path], validator=validator_path, validator_sha256=hashes[validator_path],
        code_and_dependency_sha256=hashes, source_audit=audit_path, source_audit_sha256=hashes[audit_path],
        source_files=FILES, source_bytes=SOURCE_BYTES, source_sha256=SOURCE_HASHES, source_rows=SOURCE_ROWS,
        source_before=source_before, source_after=source_after, source_hashes_and_metadata_unchanged=True,
        source_header=RAW_FIELDS, table='rr_raw.item_properties', raw_fields=5, raw_types=['VARCHAR'] * 5,
        import_semantics='UNION ALL of two strict four-VARCHAR CSV readers with fixed VARCHAR source_file tags. All four strings, including exact empties, whitespace and duplicates, remain unchanged. Raw table uses plain CREATE; only a session TEMP aggregate helper is replaceable.',
        source_rows_compared=20275902, source_fields_compared=5, source_only_rows=0, table_only_rows=0,
        per_part_multiset_checks=[dict(source_file=name, source_rows=SOURCE_ROWS[name], fields=5, source_only_rows=0, table_only_rows=0) for name in FILES],
        full_source_multiset_comparison='Four separate production EXCEPT ALL statements: each part in both directions, across all five raw/provenance fields. Unknown provenance is separately counted. Multiplicity is retained without requiring zero duplicate/conflicting keys.',
        independent_validation_basis='Frozen independently executed Python standard-library source audit of all raw records, plus unchanged file hashes and current headers. Small synthetic CSV Counter comparisons independently check preservation; no full real-source Python tuple comparison is claimed.',
        full_source_python_counter_or_row_fingerprint_rerun=False,
        report_rows=14, report_columns=5, output_columns=COLUMNS, checks_passed=14, results=report, report_sha256=report_hash(report),
        report_fingerprint_contract='SHA-256 of ordered compact JSON arrays in output_columns order, each followed by LF; counts/order are integers and labels/status are strings.',
        fixture_case_count=len(cases), fixture_cases=cases,
        database='Private temporary DuckDB file under ignored repository tmp; removed after validation.',
        preflight_settings={'threads': 2, 'memory_limit': '2GB', 'max_temp_directory_size': '8GB', 'private_directory_budget_bytes': 12 * GIB, 'timeout_seconds_per_phase': 600},
        workspace_free_bytes_before=available_disk, workspace_free_bytes_after=shutil.disk_usage(tmp_root).free,
        memory_availability_before=memory, peak_private_directory_bytes_observed=peak_directory_bytes,
        private_database_bytes_before_cleanup=database_bytes,
        source_records_or_identifiers_exported_or_logged=False, learner_database_opened=False,
        other_source_csvs_read=False, m5_queries_or_historical_suites_rerun=False,
        historical_preflight_files_unchanged=len(historical), temporary_databases_and_spills_removed=True,
        elapsed_import_seconds=import_elapsed, elapsed_checks_seconds=checks_elapsed,
        elapsed_import_and_checks_seconds=round(import_elapsed + checks_elapsed, 3),
        timing_scope='Two private CLI executions: import, then sequential checks. Excludes hashes and fixtures. Memory setting is not a process-wide cap; disk observations are sampled once per second.',
        scope='Assistant raw property import preflight passed; learner SQL56 execution/acceptance pending. No semantic property interpretation, key conflict profiling, deduplication, latest-state selection, as-of joins or behavioral/monetary metrics.')
    output.write_text(json.dumps(evidence, indent=2) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps({'checks_passed': 14, 'report_rows': 14, 'report_columns': 5,
                      'focused_cases_passed': len(cases), 'source_rows_compared': 20275902,
                      'report_sha256': evidence['report_sha256'], 'elapsed_seconds': evidence['elapsed_import_and_checks_seconds'],
                      'peak_private_directory_bytes_observed': peak_directory_bytes}), flush=True)


if __name__ == '__main__':
    main()
