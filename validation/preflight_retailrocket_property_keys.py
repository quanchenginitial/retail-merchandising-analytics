"""One private raw-key audit, frozen SQL56 import only, independent tiny fixtures.

No real keyed groups or property values are exported. Full-source Python Counter
and historical comparison suites are deliberately outside this bounded step.
"""
import argparse
import csv
import hashlib
import json
import re
import shutil
import subprocess
import tempfile
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import preflight_retailrocket_properties_import as previous


FIELDS = previous.TABLE_FIELDS
FILES = previous.FILES
COLUMNS = previous.COLUMNS
EXPECTED_COUNTS = (20275902, 10999999, 9275903)
COUNT_SQL = 'SELECT 20275902::BIGINT AS expected_rows,10999999::BIGINT AS expected_part1,9275903::BIGINT AS expected_part2'
CHECKS = ['raw_rows', 'part1_rows', 'part2_rows', 'missing_core_rows', 'unknown_source_file_rows',
          'distinct_items', 'distinct_property_names', 'distinct_item_property_pairs', 'candidate_keys',
          'distinct_exact_tuples', 'exact_duplicate_surplus_rows', 'conflicting_candidate_keys',
          'rows_in_conflicting_keys', 'cross_part_exact_tuples', 'cross_part_candidate_keys',
          'part_rows_reconciled', 'tuple_rows_reconciled', 'key_rows_reconciled',
          'exact_tuple_surplus_reconciled', 'key_value_groups_reconciled']
CONTRACT_SHA = 'dd56b37a1ca2359634876f9985460ff7fdb19e40830a34616d32fa608944e5b0'
GIB = previous.GIB


def reference(rows, expected_counts):
    """Independent Counter/set definitions, used only with tiny synthetic rows."""
    tuples = Counter(row[:4] for row in rows)
    key_values, key_rows, tuple_parts, key_parts = defaultdict(set), Counter(), defaultdict(set), defaultdict(set)
    for row in rows:
        key_values[row[:3]].add(row[3])
        key_rows[row[:3]] += 1
        tuple_parts[row[:4]].add(row[4])
        key_parts[row[:3]].add(row[4])
    n, p1, p2 = len(rows), sum(row[4] == FILES[0] for row in rows), sum(row[4] == FILES[1] for row in rows)
    missing = sum(any(value is None or value == '' for value in row[:4]) for row in rows)
    unknown = sum(row[4] not in FILES for row in rows)
    conflicts = {key for key, values in key_values.items() if len(values) > 1}
    actual = [n, p1, p2, missing, unknown, len({r[1] for r in rows if r[1] is not None}),
              len({r[2] for r in rows if r[2] is not None}), len({r[1:3] for r in rows}),
              len(key_values), len(tuples), sum(count - 1 for count in tuples.values()),
              len(conflicts), sum(key_rows[key] for key in conflicts),
              sum(set(FILES) <= parts for parts in tuple_parts.values()),
              sum(set(FILES) <= parts for parts in key_parts.values()),
              p1 + p2, sum(tuples.values()), sum(key_rows.values()),
              len(tuples) + sum(count - 1 for count in tuples.values()), sum(map(len, key_values.values()))]
    expected = [*expected_counts, 0, 0] + [None] * 10 + [n, n, n, n, len(tuples)]
    valid = actual[:5] == expected[:5]
    return [dict(check_order=i, check_name=name, actual=value, expected=target,
                 status=('INFO' if valid else 'BLOCKED') if target is None else ('PASS' if value == target else 'FAIL'))
            for i, (name, value, target) in enumerate(zip(CHECKS, actual, expected), 1)]


def fixture_input(rows, fields=FIELDS):
    def literal(value):
        return 'NULL' if value is None else "'" + value.replace("'", "''") + "'"
    create = 'CREATE SCHEMA rr_raw; CREATE TABLE rr_raw.item_properties (' + ','.join(f'{f} VARCHAR' for f in fields) + ');\n'
    if rows:
        create += 'INSERT INTO rr_raw.item_properties VALUES ' + ','.join('(' + ','.join(map(literal, row)) + ')' for row in rows) + ';\n'
    return create


def adjusted(sql, counts):
    replacement = f'SELECT {counts[0]}::BIGINT AS expected_rows,{counts[1]}::BIGINT AS expected_part1,{counts[2]}::BIGINT AS expected_part2'
    assert sql.count(COUNT_SQL) == 1
    return sql.replace(COUNT_SQL, replacement)


def report_hash(rows):
    text = ''.join(json.dumps([row[key] for key in COLUMNS], separators=(',', ':')) + '\n' for row in rows)
    return hashlib.sha256(text.encode()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--duckdb', required=True)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--fixtures-only', action='store_true')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    script_path = 'sql/57_audit_retailrocket_property_keys.sql'
    validator_path = 'validation/preflight_retailrocket_property_keys.py'
    method_path = 'docs/RETAILROCKET_PROPERTY_KEYS_VALIDATION.md'
    audit_path = 'data/retailrocket_source_audit.json'
    prior_path = 'data/retailrocket_properties_import_preflight.json'
    output = root / 'data/retailrocket_property_keys_preflight.json'
    assert args.output.resolve() == output.resolve(), 'Output must be the fixed aggregate evidence path'
    dependencies = [script_path, validator_path, audit_path, 'scripts/audit_retailrocket_sources.py',
                    'sql/56_import_retailrocket_properties.sql', 'validation/preflight_retailrocket_properties_import.py',
                    prior_path, 'data/retailrocket_properties_import_learner_acceptance.json',
                    'docs/RETAILROCKET_PROPERTIES_IMPORT_VALIDATION.md']
    hashes = {name: previous.sha256(root / name) for name in dependencies}
    # Pin the accepted SQL56 evidence and updated acceptance/method explicitly.
    assert hashes['data/retailrocket_properties_import_learner_acceptance.json'] == '4d0c325a456fd22af3edb7b14e37ad857b9ae7f7b9a08f14d1305823c25c856e'
    assert hashes['docs/RETAILROCKET_PROPERTIES_IMPORT_VALIDATION.md'] == '64f7f519cc30a760a97a2b0535e0bda7b8404c7565dc4d94a88f0dfe2ad6296f'
    contract = (root / method_path).read_bytes()
    # Measured results may be appended later without changing this frozen prefix.
    contract_marker = b'\n## Executed results\n'
    if contract_marker in contract:
        contract = contract.split(contract_marker, 1)[0]
    assert hashlib.sha256(contract).hexdigest() == CONTRACT_SHA, 'Frozen method contract changed'
    sql = (root / script_path).read_text(encoding='utf-8')
    statements = re.sub(r'--[^\n]*', '', sql)
    assert not re.search(r'\b(CREATE|INSERT|UPDATE|DELETE|DROP|COPY|MERGE|read_csv)\b', statements, re.I), 'Audit must remain read-only'
    assert 'tuple_groups AS MATERIALIZED' in sql and 'key_groups AS MATERIALIZED' in sql
    prefix = (root / 'sql/56_import_retailrocket_properties.sql').read_text(encoding='utf-8').split(previous.CHECK_MARKER, 1)[0]
    assert 'EXCEPT ALL' not in prefix and prefix.count('read_csv(') == 2
    prior = json.loads((root / prior_path).read_text(encoding='utf-8'))
    audit = json.loads((root / audit_path).read_text(encoding='utf-8'))
    assert prior['checks_passed'] == 14 and all(row['status'] == 'PASS' for row in prior['results'])
    assert prior['source_sha256'] == previous.SOURCE_HASHES and audit['all_checks_passed']
    assert prior['script_sha256'] == hashes['sql/56_import_retailrocket_properties.sql']
    assert prior['source_audit_sha256'] == hashes[audit_path]
    for name in FILES:
        assert audit['files'][name]['sha256'] == previous.SOURCE_HASHES[name]
        assert audit['files'][name]['rows'] == previous.SOURCE_ROWS[name]
    tmp_root = root / 'tmp'
    tmp_root.mkdir(exist_ok=True)
    free_before, memory = shutil.disk_usage(tmp_root).free, previous.memory_availability()
    assert free_before >= 12 * GIB, 'At least 12 GiB free workspace disk is required'
    peak_directory_bytes = 0

    def execute(folder, database, query, phase, allow_error=False):
        # Same bounded execution controls as SQL56; diagnostics stay private.
        nonlocal peak_directory_bytes
        assert folder.resolve().is_relative_to(tmp_root.resolve())
        if database != ':memory:':
            assert Path(database).resolve().is_relative_to(folder.resolve())
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
                            pass
                    peak_directory_bytes = max(peak_directory_bytes, current)
                    assert current <= 12 * GIB and shutil.disk_usage(tmp_root).free >= 2 * GIB, 'Private disk budget/reserve reached'
                    elapsed = time.perf_counter() - started
                    assert elapsed <= 600, 'Bounded DuckDB execution timeout reached'
                    if elapsed >= next_update:
                        print(json.dumps({'phase': phase, 'elapsed_seconds': round(elapsed, 1), 'private_bytes_observed': current}), flush=True)
                        next_update += 30
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate()
        if not allow_error:
            assert process.returncode == 0, 'Private DuckDB execution failed; source diagnostics withheld'
        current = sum(path.stat().st_size for path in folder.rglob('*') if path.is_file())
        peak_directory_bytes = max(peak_directory_bytes, current)
        assert current <= 12 * GIB
        return dict(returncode=process.returncode, stdout=stdout, stderr=stderr), round(time.perf_counter() - started, 3)

    cases = []
    with tempfile.TemporaryDirectory(prefix='rr-property-keys-fixture-', dir=tmp_root) as temporary:
        folder = Path(temporary)
        a, b = FILES
        rows = [('10', '001', 'alpha', '01', a), ('10', '001', 'alpha', '01', a),
                ('10', '001', 'alpha', '1', a), ('11', '001', 'alpha', '01', a),
                ('20', '002', 'beta', ' x y ', a), ('10', '001', 'alpha', '01', b),
                ('10', '001', 'alpha', 'NULL', b), ('20', '002', 'beta', 'different', b),
                ('30', '003', 'gamma', 'zero', b)]
        expected = reference(rows, (9, 5, 4))
        assert [row['actual'] for row in expected] == [9, 5, 4, 0, 0, 3, 3, 3, 4, 7, 2, 2, 7, 1, 2, 9, 9, 9, 9, 7]
        run, _ = execute(folder, ':memory:', fixture_input(rows) + adjusted(sql, (9, 5, 4)), 'fixture')
        assert json.loads(run['stdout']) == expected, 'Independent duplicate/conflict/overlap fixture mismatch'
        cases.append(dict(case='independent_hand_checked_counter_within_cross_part_duplicates_conflicts_and_different_value_overlap', passed=True))
        rows = [('010', '001', 'p', 'x', a), ('10', '1', 'p', 'x', a),
                ('010', '001', ' p ', 'x', a), ('010', '001', 'p', ' x ', a)]
        expected = reference(rows, (4, 4, 0))
        assert [row['actual'] for row in expected][5:15] == [2, 2, 3, 3, 4, 0, 1, 2, 0, 0]
        run, _ = execute(folder, ':memory:', fixture_input(rows) + adjusted(sql, (4, 4, 0)), 'fixture')
        assert json.loads(run['stdout']) == expected, 'Raw-text distinctions were collapsed'
        cases.append(dict(case='leading_zero_timestamp_item_and_whitespace_property_value_identity_remains_exact_text', passed=True))
        rows = [('1', '1', 'p', '', a), ('2', '2', 'p', None, b), ('3', '3', 'p', 'x', None)]
        run, _ = execute(folder, ':memory:', fixture_input(rows) + adjusted(sql, (3, 1, 2)), 'fixture')
        assert json.loads(run['stdout']) == reference(rows, (3, 1, 2)), 'Invalid input did not block observations'
        run, _ = execute(folder, ':memory:', fixture_input([]) + sql, 'fixture')
        assert json.loads(run['stdout']) == reference([], EXPECTED_COUNTS), 'Empty input suppressed the fixed report'
        wrong_order = [FIELDS[1], FIELDS[0], *FIELDS[2:]]
        rejected, _ = execute(folder, ':memory:', fixture_input([], wrong_order) + sql, 'fixture', allow_error=True)
        assert rejected['returncode'] != 0 and 'SQL57 requires' in rejected['stderr'], 'Schema/order guard did not reject invalid input'
        wrong_type = fixture_input([]).replace('timestamp VARCHAR', 'timestamp BIGINT')
        rejected, _ = execute(folder, ':memory:', wrong_type + sql, 'fixture', allow_error=True)
        assert rejected['returncode'] != 0 and 'SQL57 requires' in rejected['stderr'], 'Raw-type guard did not reject invalid input'
        cases.append(dict(case='missing_core_unknown_provenance_and_empty_inputs_block_observations_wrong_schema_rejected', passed=True, expected_rejection=True))
    assert not folder.exists()
    print(json.dumps({'focused_cases_passed': len(cases)}), flush=True)
    if args.fixtures_only:
        return

    source_before = {name: previous.snapshot(previous.SOURCE_DIR / name) for name in FILES}
    for name, observed in source_before.items():
        assert observed['sha256'] == previous.SOURCE_HASHES[name] and observed['size_bytes'] == previous.SOURCE_BYTES[name], 'Audited source snapshot changed'
        with (previous.SOURCE_DIR / name).open('r', encoding='utf-8', newline='') as stream:
            assert next(csv.reader(stream, strict=True)) == previous.RAW_FIELDS, 'Source header changed'
    historical = {str(path.relative_to(root)): previous.sha256(path) for path in (root / 'data').glob('*preflight.json')
                  if path.resolve() != output.resolve()}
    with tempfile.TemporaryDirectory(prefix='rr-property-keys-audit-', dir=tmp_root) as temporary:
        folder, database = Path(temporary), Path(temporary) / 'preflight.duckdb'
        run, import_seconds = execute(folder, database, prefix, 'frozen_raw_import')
        assert not run['stdout'].strip()
        print(json.dumps({'frozen_raw_import_completed': True, 'elapsed_seconds': import_seconds}), flush=True)
        run, audit_seconds = execute(folder, database, sql, 'property_key_audit')
        report = json.loads(run['stdout'])
        assert len(report) == 20 and all(list(row) == COLUMNS for row in report)
        assert [row['check_name'] for row in report] == CHECKS
        assert [row['check_order'] for row in report] == list(range(1, 21))
        assert all(row['status'] == 'PASS' and row['actual'] == row['expected'] for row in report[:5] + report[15:])
        assert [row['actual'] for row in report[:5]] == [*EXPECTED_COUNTS, 0, 0]
        assert all(row['status'] == 'INFO' and row['expected'] is None and isinstance(row['actual'], int) and row['actual'] >= 0 for row in report[5:15])
        values = {row['check_name']: row['actual'] for row in report}
        assert values['distinct_exact_tuples'] + values['exact_duplicate_surplus_rows'] == values['raw_rows']
        assert values['conflicting_candidate_keys'] <= values['candidate_keys'] <= values['distinct_exact_tuples'] <= values['raw_rows']
        assert values['rows_in_conflicting_keys'] <= values['raw_rows']
        assert values['cross_part_exact_tuples'] <= values['distinct_exact_tuples']
        assert values['cross_part_candidate_keys'] <= values['candidate_keys']
        database_bytes = database.stat().st_size
    assert not folder.exists()
    source_after = {name: previous.snapshot(previous.SOURCE_DIR / name) for name in FILES}
    assert source_before == source_after
    assert all(previous.sha256(root / name) == digest for name, digest in hashes.items()), 'Frozen dependency changed'
    assert all(previous.sha256(root / name) == digest for name, digest in historical.items()), 'Historical preflight changed'
    assert (root / method_path).read_bytes().startswith(contract), 'Frozen method contract changed'
    evidence = dict(
        checked_at_utc=datetime.now(timezone.utc).isoformat(), executor='assistant',
        engine=subprocess.check_output([args.duckdb, '-version'], text=True).strip(),
        script=script_path, script_sha256=hashes[script_path], validator=validator_path, validator_sha256=hashes[validator_path],
        code_and_dependency_sha256=hashes, method_contract=method_path,
        method_contract_prefix_sha256=CONTRACT_SHA, method_contract_prefix_bytes=len(contract),
        source_audit=audit_path, source_audit_sha256=hashes[audit_path], accepted_copy_preflight=prior_path,
        accepted_copy_preflight_sha256=hashes[prior_path], source_files=FILES,
        source_before=source_before, source_after=source_after, source_hashes_and_metadata_unchanged=True,
        source_rows=previous.SOURCE_ROWS, input_rows=20275902, input_fields=5, input_columns=FIELDS,
        raw_table='rr_raw.item_properties', raw_import_prefix_sha256=hashlib.sha256(prefix.encode()).hexdigest(),
        raw_import_basis='Only the accepted SQL56 import prefix; unchanged source hashes and frozen independent source audit/SQL56 complete copy proof. SQL56 comparisons were not rerun.',
        full_source_python_counter_or_row_fingerprint_rerun=False, real_audit_executions=1,
        report_rows=20, report_columns=5, output_columns=COLUMNS, checks_passed=10, info_rows=10,
        fail_rows=0, blocked_rows=0, results=report, report_sha256=report_hash(report),
        report_fingerprint_contract='SHA-256 of ordered compact JSON arrays in output_columns order, each followed by LF; counts/order are integers, expected is integer or null, labels/status are strings.',
        fixture_case_count=len(cases), fixture_cases=cases, independent_synthetic_counter_reports_matched=True,
        candidate_key_definition=['itemid', 'property', 'timestamp'], exact_tuple_definition=['itemid', 'property', 'timestamp', 'value'],
        identity='Exact raw strings; source_file excluded from content identity and retained for cross-part presence.',
        duplicates_or_conflicts_required_to_be_zero=False,
        database='Private disposable DuckDB file under ignored repository tmp; removed after validation.',
        preflight_settings={'threads': 2, 'memory_limit': '2GB', 'max_temp_directory_size': '8GB', 'private_directory_budget_bytes': 12 * GIB, 'timeout_seconds_per_phase': 600},
        workspace_free_bytes_before=free_before, workspace_free_bytes_after=shutil.disk_usage(tmp_root).free,
        memory_availability_before=memory, peak_private_directory_bytes_observed=peak_directory_bytes,
        private_database_bytes_before_cleanup=database_bytes, temporary_databases_and_spills_removed=True,
        source_records_or_identifiers_or_property_values_exported_or_logged=False,
        learner_database_opened=False, other_source_csvs_read=False,
        historical_comparison_or_analysis_suites_rerun=False, historical_preflight_files_unchanged=len(historical),
        elapsed_import_seconds=import_seconds, elapsed_audit_seconds=audit_seconds,
        elapsed_import_and_audit_seconds=round(import_seconds + audit_seconds, 3),
        timing_scope='One frozen-prefix import and one grouped audit; excludes hashes and tiny fixtures. Disk samples are once per second; memory_limit is not a process cap.',
        scope='Assistant raw property grain/key audit complete; learner SQL57 execution/acceptance pending. INFO observations do not impose zero targets or choose deduplication/conflict policies. No typed staging, latest-state selection, as-of joins or business/value interpretation.')
    output.write_text(json.dumps(evidence, indent=2) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps({'report_rows': 20, 'report_columns': 5, 'checks_passed': 10, 'info_rows': 10,
                      'focused_cases_passed': len(cases), 'report_sha256': evidence['report_sha256'],
                      'elapsed_seconds': evidence['elapsed_import_and_audit_seconds'],
                      'peak_private_directory_bytes_observed': peak_directory_bytes}), flush=True)


if __name__ == '__main__':
    main()
