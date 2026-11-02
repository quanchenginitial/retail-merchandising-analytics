"""One private named-property audit; independent synthetic reports, no real row exports."""
import argparse
import csv
import hashlib
import json
import re
import shutil
import subprocess
import tempfile
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import preflight_retailrocket_properties_import as previous

FIELDS = previous.TABLE_FIELDS
FILES = previous.FILES + ['category_tree.csv']
HEADERS = {name: previous.RAW_FIELDS for name in previous.FILES}
HEADERS['category_tree.csv'] = ['categoryid', 'parentid']
HASHES = dict(previous.SOURCE_HASHES, **{'category_tree.csv': '94e865eb0a3d48cbbfe3b79079018dd92509315c88f5fd8d00d0b4b5af434f5b'})
COLUMNS = previous.COLUMNS
GIB = previous.GIB
COUNTS = (20275902, 10999999, 9275903, 1669)
COUNT_SQL = ('SELECT 20275902::BIGINT AS expected_rows,10999999::BIGINT AS expected_part1,\n'
             '        9275903::BIGINT AS expected_part2,1669::BIGINT AS expected_reference_rows')
CONTRACT_SHA = 'b4fb0f9d84ad0fb628ff36788be01fe2f8c86b960363fcfdaa1795a5576cbc59'
CHECKS = ['raw_rows', 'part1_rows', 'part2_rows', 'unknown_source_file_rows',
          'category_reference_rows', 'category_reference_duplicate_id_surplus', 'category_reference_missing_ids',
          'categoryid_rows', 'categoryid_items', 'available_rows', 'available_items', 'other_property_rows',
          'available_zero_rows', 'available_one_rows', 'available_other_rows', 'category_invalid_value_rows',
          'category_unmatched_exact_rows', 'named_missing_identity_rows', 'named_invalid_identifier_or_timestamp_rows',
          'property_partition_reconciled', 'availability_partition_reconciled', 'category_match_partition_reconciled']


def valid_integer(value):
    return value is not None and re.fullmatch(r'[0-9]+', value) is not None and int(value) <= 9223372036854775807


def reference(rows, categories, expected_counts):
    """Pure Python sets/counts on tiny synthetic data; never run on real source rows."""
    counts = Counter(r[0] for r in categories)
    ids = {r[0] for r in categories if r[0] is not None}
    cat = [r for r in rows if r[2] == 'categoryid']
    avail = [r for r in rows if r[2] == 'available']
    named = cat + avail
    n = len(rows)
    p1 = sum(r[4] == previous.FILES[0] for r in rows)
    p2 = sum(r[4] == previous.FILES[1] for r in rows)
    unmatched = sum(r[3] is None or r[3] not in ids for r in cat)
    zero, one = sum(r[3] == '0' for r in avail), sum(r[3] == '1' for r in avail)
    other_avail = sum(r[3] not in ('0', '1') for r in avail)
    other_props = sum(r[2] not in ('categoryid', 'available') for r in rows)
    actual = [n, p1, p2, sum(r[4] not in previous.FILES for r in rows), len(categories),
              sum(v - 1 for v in counts.values()), sum(r[0] in (None, '') for r in categories),
              len(cat), len({r[1] for r in cat if r[1] is not None}),
              len(avail), len({r[1] for r in avail if r[1] is not None}), other_props,
              zero, one, other_avail, sum(not valid_integer(r[3]) for r in cat), unmatched,
              sum(r[0] in (None, '') or r[1] in (None, '') for r in named),
              sum(any(v not in (None, '') and not valid_integer(v) for v in r[:2]) for r in named),
              len(cat) + len(avail) + other_props, zero + one + other_avail, len(cat) - unmatched + unmatched]
    expected = [*expected_counts[:3], 0, expected_counts[3], 0, 0] + [None] * 12 + [n, len(avail), len(cat)]
    healthy = actual[:7] == expected[:7]
    return [dict(check_order=i, check_name=name, actual=value, expected=target,
                 status=('INFO' if healthy else 'BLOCKED') if target is None else ('PASS' if value == target else 'FAIL'))
            for i, (name, value, target) in enumerate(zip(CHECKS, actual, expected), 1)]


def fixture_sql(rows, categories):
    def literal(value):
        return 'NULL' if value is None else "'" + value.replace("'", "''") + "'"
    sql = 'CREATE SCHEMA rr_raw; CREATE TABLE rr_raw.item_properties (' + ','.join(f'{f} VARCHAR' for f in FIELDS) + ');\n'
    sql += 'CREATE TABLE rr_raw.category_tree (categoryid VARCHAR,parentid VARCHAR);\n'
    for table, records in [('item_properties', rows), ('category_tree', categories)]:
        if records:
            sql += f'INSERT INTO rr_raw.{table} VALUES ' + ','.join('(' + ','.join(map(literal, row)) + ')' for row in records) + ';\n'
    return sql


def adjusted(sql, counts):
    replacement = (f'SELECT {counts[0]}::BIGINT AS expected_rows,{counts[1]}::BIGINT AS expected_part1,\n'
                   f'        {counts[2]}::BIGINT AS expected_part2,{counts[3]}::BIGINT AS expected_reference_rows')
    assert sql.count(COUNT_SQL) == 1
    return sql.replace(COUNT_SQL, replacement)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--duckdb', required=True)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--fixtures-only', action='store_true')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    script_path = 'sql/58_audit_retailrocket_named_properties.sql'
    validator_path = 'validation/preflight_retailrocket_named_properties.py'
    method_path = 'docs/RETAILROCKET_NAMED_PROPERTIES_VALIDATION.md'
    output = root / 'data/retailrocket_named_properties_preflight.json'
    assert args.output.resolve() == output.resolve()
    dependencies = [script_path, validator_path, 'validation/preflight_retailrocket_properties_import.py',
                    'sql/55_import_retailrocket_categories.sql', 'sql/56_import_retailrocket_properties.sql',
                    'data/retailrocket_source_audit.json', 'scripts/audit_retailrocket_sources.py',
                    'data/retailrocket_categories_import_preflight.json', 'data/retailrocket_properties_import_preflight.json',
                    'data/retailrocket_property_keys_preflight.json', 'data/retailrocket_property_keys_learner_acceptance.json',
                    'docs/RETAILROCKET_PROPERTY_KEYS_VALIDATION.md']
    hashes = {p: previous.sha256(root / p) for p in dependencies}
    assert hashes['data/retailrocket_property_keys_learner_acceptance.json'] == '9aae83843dd60827646f91f136c697f14b2bc142e772fc1f064c47e06746adf4'
    assert hashes['docs/RETAILROCKET_PROPERTY_KEYS_VALIDATION.md'] == '01e77e08348714366c20606b67b1f6cc33f4ae0c5292903632409751a5434022'
    contract = (root / method_path).read_bytes().split(b'\n## Executed results\n', 1)[0]
    assert hashlib.sha256(contract).hexdigest() == CONTRACT_SHA
    sql = (root / script_path).read_text(encoding='utf-8')
    assert not re.search(r'\b(CREATE|INSERT|UPDATE|DELETE|DROP|COPY|MERGE|read_csv)\b', re.sub(r'--[^\n]*', '', sql), re.I)
    audit = json.loads((root / 'data/retailrocket_source_audit.json').read_text(encoding='utf-8'))
    assert audit['all_checks_passed']
    for name in FILES:
        assert audit['files'][name]['sha256'] == HASHES[name]
    prefixes = {
        'sql/55_import_retailrocket_categories.sql': (root / 'sql/55_import_retailrocket_categories.sql').read_text(encoding='utf-8').split('-- CHECKS:', 1)[0],
        'sql/56_import_retailrocket_properties.sql': (root / 'sql/56_import_retailrocket_properties.sql').read_text(encoding='utf-8').split(previous.CHECK_MARKER, 1)[0],
    }
    for path, evidence_path, checks in [
        ('sql/55_import_retailrocket_categories.sql', 'data/retailrocket_categories_import_preflight.json', 15),
        ('sql/56_import_retailrocket_properties.sql', 'data/retailrocket_properties_import_preflight.json', 14),
    ]:
        evidence = json.loads((root / evidence_path).read_text(encoding='utf-8'))
        assert evidence['script_sha256'] == hashes[path] and evidence['checks_passed'] == checks
    import_sql = '\n'.join(prefixes.values())
    assert import_sql.count('read_csv(') == 3 and 'EXCEPT ALL' not in import_sql
    tmp_root = root / 'tmp'
    tmp_root.mkdir(exist_ok=True)
    free_before, memory = shutil.disk_usage(tmp_root).free, previous.memory_availability()
    assert free_before >= 12 * GIB
    peak_bytes = 0

    def execute(folder, database, query, phase, allow_error=False):
        nonlocal peak_bytes
        assert folder.resolve().is_relative_to(tmp_root.resolve())
        if database != ':memory:':
            assert Path(database).resolve().is_relative_to(folder.resolve())
        spill = (folder / 'spill').as_posix().replace("'", "''")
        settings = f"SET threads=2; SET memory_limit='2GB'; SET max_temp_directory_size='8GB'; SET temp_directory='{spill}';\n"
        process = subprocess.Popen([args.duckdb, str(database), '-bail', '-json'], stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8')
        started, first, next_update = time.perf_counter(), True, 30
        try:
            while True:
                try:
                    stdout, stderr = process.communicate(input=settings + query if first else None, timeout=1)
                    break
                except subprocess.TimeoutExpired:
                    first = False
                    size = 0
                    for p in folder.rglob('*'):
                        try:
                            if p.is_file():
                                size += p.stat().st_size
                        except FileNotFoundError:
                            pass
                    peak_bytes = max(peak_bytes, size)
                    elapsed = time.perf_counter() - started
                    assert size <= 12 * GIB and shutil.disk_usage(tmp_root).free >= 2 * GIB, 'Private disk budget/reserve reached'
                    assert elapsed <= 600, 'Private execution timeout'
                    if elapsed >= next_update:
                        print(json.dumps({'phase': phase, 'elapsed_seconds': round(elapsed, 1), 'private_bytes_observed': size}), flush=True)
                        next_update += 30
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate()
        if not allow_error:
            assert process.returncode == 0, 'Private DuckDB execution failed; row-bearing diagnostics withheld'
        size = sum(p.stat().st_size for p in folder.rglob('*') if p.is_file())
        peak_bytes = max(peak_bytes, size)
        assert size <= 12 * GIB
        return dict(returncode=process.returncode, stdout=stdout, stderr=stderr), round(time.perf_counter() - started, 3)

    cases = []
    with tempfile.TemporaryDirectory(prefix='rr-named-fixture-', dir=tmp_root) as temporary:
        folder = Path(temporary)
        p1, p2 = previous.FILES
        categories = [('7', None), ('08', '7')]
        rows = [('1', '1', 'categoryid', '7', p1), ('2', '1', 'categoryid', '07', p1),
                ('3', '2', 'categoryid', 'x', p1), ('4', '3', 'categoryid', None, p1),
                ('5', '3', 'available', '0', p1), ('6', '4', 'available', '1', p2),
                ('7', '5', 'available', '01', p2), ('8', '5', 'available', '', p2),
                ('9', '6', 'available', None, p2), ('10', '7', 'opaque', 's', p2),
                ('11', '8', None, 's', p2), ('12', '9', 'categoryid', '08', p2)]
        expected = reference(rows, categories, (12, 5, 7, 2))
        assert [r['actual'] for r in expected] == [12, 5, 7, 0, 2, 0, 0, 5, 4, 5, 4, 2, 1, 1, 3, 2, 3, 0, 0, 12, 5, 5]
        result, _ = execute(folder, ':memory:', fixture_sql(rows, categories) + adjusted(sql, (12, 5, 7, 2)), 'fixture')
        assert json.loads(result['stdout']) == expected, 'Independent value/reference fixture mismatch'
        cases.append(dict(case='hand_checked_exact_matches_leading_zero_mismatch_binary_other_null_empty_opaque_partition', passed=True))
        categories = [('7', None), ('7', None), (None, None), (None, None), ('', None)]
        rows = [('', '1', 'categoryid', '7', p1), ('bad', '', 'available', '1', p2),
                ('1', None, 'available', 'x', None), ('9223372036854775808', '2', 'categoryid', '99999999999999999999', p2),
                (None, '-1', 'categoryid', None, p2), ('2', '3', 'categoryid', '', p2)]
        expected = reference(rows, categories, (6, 1, 5, 5))
        result, _ = execute(folder, ':memory:', fixture_sql(rows, categories) + adjusted(sql, (6, 1, 5, 5)), 'fixture')
        assert json.loads(result['stdout']) == expected, 'Reference duplication or identity/null overlap mismatch'
        assert expected[5]['actual'] == 2 and expected[6]['actual'] == 3
        assert all(r['status'] == 'BLOCKED' for r in expected[7:19])
        cases.append(dict(case='duplicate_and_missing_reference_ids_do_not_multiply_counts_invalid_missing_identity_overlap_blocks_input', passed=True))
        result, _ = execute(folder, ':memory:', fixture_sql([], []) + sql, 'fixture')
        assert json.loads(result['stdout']) == reference([], [], COUNTS)
        for setup in [fixture_sql([], []).replace('timestamp VARCHAR', 'timestamp BIGINT'),
                      fixture_sql([], []).replace('categoryid VARCHAR,parentid VARCHAR', 'parentid VARCHAR,categoryid VARCHAR')]:
            result, _ = execute(folder, ':memory:', setup + sql, 'fixture', allow_error=True)
            assert result['returncode'] != 0
            # Incompatible raw types can fail binding before the explicit guard.
            assert 'SQL58 requires' in result['stderr'] or ('Binder Error' in result['stderr'] and 'regexp_full_match' in result['stderr'])
        cases.append(dict(case='empty_inputs_keep_report_and_bad_raw_schema_order_or_type_rejected', passed=True, expected_rejection=True))
    assert not folder.exists()
    print(json.dumps({'focused_cases_passed': len(cases)}), flush=True)
    if args.fixtures_only:
        return

    source_before = {name: previous.snapshot(previous.SOURCE_DIR / name) for name in FILES}
    for name, observed in source_before.items():
        assert observed['sha256'] == HASHES[name] and observed['size_bytes'] == audit['files'][name]['size_bytes']
        with (previous.SOURCE_DIR / name).open('r', encoding='utf-8', newline='') as stream:
            assert next(csv.reader(stream, strict=True)) == HEADERS[name]
    historical = {str(p.relative_to(root)): previous.sha256(p) for p in (root / 'data').glob('*preflight.json') if p.resolve() != output.resolve()}
    with tempfile.TemporaryDirectory(prefix='rr-named-audit-', dir=tmp_root) as temporary:
        folder = Path(temporary)
        database = folder / 'preflight.duckdb'
        result, import_seconds = execute(folder, database, import_sql, 'frozen_raw_imports')
        assert not result['stdout'].strip()
        print(json.dumps({'raw_reconstruction_completed': True, 'elapsed_seconds': import_seconds}), flush=True)
        result, audit_seconds = execute(folder, database, sql, 'named_property_audit')
        report = json.loads(result['stdout'])
        assert len(report) == 22 and [r['check_name'] for r in report] == CHECKS
        for i, row in enumerate(report, 1):
            assert list(row) == COLUMNS and row['check_order'] == i and isinstance(row['actual'], int) and row['actual'] >= 0
            if 8 <= i <= 19:
                assert row['expected'] is None and row['status'] == 'INFO'
            else:
                assert row['actual'] == row['expected'] and row['status'] == 'PASS'
        assert [r['actual'] for r in report[:7]] == [*COUNTS[:3], 0, COUNTS[3], 0, 0]
        database_bytes = database.stat().st_size
    assert not folder.exists()
    source_after = {name: previous.snapshot(previous.SOURCE_DIR / name) for name in FILES}
    assert source_before == source_after
    assert all(previous.sha256(root / p) == h for p, h in hashes.items())
    assert all(previous.sha256(root / p) == h for p, h in historical.items())
    assert (root / method_path).read_bytes().startswith(contract)
    evidence = dict(
        checked_at_utc=datetime.now(timezone.utc).isoformat(), executor='assistant',
        engine=subprocess.check_output([args.duckdb, '-version'], text=True).strip(),
        script=script_path, script_sha256=hashes[script_path], validator=validator_path, validator_sha256=hashes[validator_path],
        code_and_dependency_sha256=hashes, method_contract=method_path, method_contract_prefix_bytes=len(contract),
        method_contract_prefix_sha256=CONTRACT_SHA, source_files=FILES, source_before=source_before, source_after=source_after,
        source_hashes_and_metadata_unchanged=True, raw_import_prefix_sha256={p: hashlib.sha256(s.encode()).hexdigest() for p, s in prefixes.items()},
        raw_reconstruction_basis='Frozen SQL55 and SQL56 import prefixes only; unchanged hashes and prior accepted copy proofs. No full prior comparisons or SQL57 key audit rerun.',
        input_property_rows=20275902, input_category_rows=1669, real_audit_executions=1,
        report_rows=22, report_columns=5, output_columns=COLUMNS, checks_passed=10, info_rows=12, fail_rows=0, blocked_rows=0,
        results=report, report_sha256=previous.report_hash(report),
        report_fingerprint_contract='SHA-256 of ordered compact JSON arrays in output_columns order, each followed by LF; counts are integers, expected is integer or null.',
        fixture_case_count=len(cases), fixture_cases=cases, independent_synthetic_counter_reports_matched=True,
        full_source_python_counter_or_row_fingerprint_rerun=False, semantic_exceptions_required_to_be_zero=False,
        identity='Exact raw text category membership via EXISTS. No numeric category normalization or typed-key collision audit.',
        preflight_settings=dict(threads=2, memory_limit='2GB', max_temp_directory_size='8GB', private_directory_budget_bytes=12 * GIB, timeout_seconds_per_phase=600),
        workspace_free_bytes_before=free_before, workspace_free_bytes_after=shutil.disk_usage(tmp_root).free,
        memory_availability_before=memory, peak_private_directory_bytes_observed=peak_bytes,
        private_database_bytes_before_cleanup=database_bytes, temporary_databases_and_spills_removed=True,
        learner_database_opened=False, other_source_csvs_read=False, source_records_or_identifiers_or_category_values_exported_or_logged=False,
        historical_comparison_or_analysis_suites_rerun=False, historical_preflight_files_unchanged=len(historical),
        elapsed_import_seconds=import_seconds, elapsed_audit_seconds=audit_seconds,
        elapsed_import_and_audit_seconds=round(import_seconds + audit_seconds, 3),
        timing_scope='One frozen-prefix reconstruction and one read-only audit; excludes hashes and fixtures. Memory limit is not a process cap; disk observations are sampled.',
        scope='Assistant named-property audit passed; learner SQL58 execution/acceptance pending. INFO values are descriptive. No typed staging, canonical matching, event/as-of join, cleanup or inventory/causal/monetary conclusion.')
    output.write_text(json.dumps(evidence, indent=2) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps({'report_rows': 22, 'checks_passed': 10, 'info_rows': 12, 'focused_cases_passed': len(cases),
                      'elapsed_seconds': evidence['elapsed_import_and_audit_seconds'], 'report_sha256': evidence['report_sha256']}), flush=True)


if __name__ == '__main__':
    main()
