"""Bounded category raw-import verification; no learner database or other CSVs.

Real source tuples are compared privately in memory, never exported or logged.
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


SOURCE = 'D:/database/retailrocket/category_tree.csv'
SOURCE_SHA = '94e865eb0a3d48cbbfe3b79079018dd92509315c88f5fd8d00d0b4b5af434f5b'
FIELDS = ['categoryid', 'parentid']
COLUMNS = ['check_order', 'check_name', 'actual', 'expected', 'status']
CHECKS = ['row_count', 'column_count', 'varchar_column_count', 'column_sequence_errors',
          'missing_categoryid_rows', 'invalid_categoryid_rows', 'invalid_parentid_rows',
          'distinct_categoryids', 'null_parentid_rows', 'duplicate_categoryid_surplus_rows',
          'self_parent_rows', 'orphan_parent_rows', 'source_rows_absent_from_table',
          'table_rows_absent_from_source', 'duplicate_surplus_rows_preserved']
EXPECTED = [1669, 2, 2, 0, 0, 0, 0, 1669, 25, 0, 0, 0, 0, 0, 0]
COUNT_SQL = 'SELECT 1669 AS expected_rows,1669 AS expected_categories,25 AS expected_null_parents'
PRIVATE_QUERY = 'SELECT categoryid,parentid FROM rr_raw.category_tree;'


def sha256(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def fingerprint(rows):
    payload = ''.join(json.dumps([row[key] for key in COLUMNS], separators=(',', ':')) + '\n' for row in rows)
    return hashlib.sha256(payload.encode()).hexdigest()


def json_outputs(text):
    decoder, outputs = json.JSONDecoder(), []
    while text.strip():
        text = text.lstrip()
        value, end = decoder.raw_decode(text)
        outputs.append(value)
        text = text[end:]
    return outputs


def source_counter(path):
    with Path(path).open('r', encoding='utf-8', newline='') as stream:
        reader = csv.reader(stream, strict=True)
        assert next(reader) == FIELDS, 'Source header mismatch'
        result = Counter()
        for row in reader:
            assert len(row) == 2, 'Source width mismatch'
            result[(row[0], None if row[1] == '' else row[1])] += 1
    return result


def table_counter(rows):
    assert all(list(row) == FIELDS for row in rows), 'Private comparison field mismatch'
    return Counter((row['categoryid'], row['parentid']) for row in rows)


def reference(counter):
    rows = list(counter.elements())
    keys = {row[0] for row in rows}
    def invalid(value):
        return value is not None and not (value.isascii() and value.isdecimal() and int(value) <= 9223372036854775807)
    return [len(rows), 2, 2, 0, sum(row[0] is None or row[0] == '' for row in rows),
            sum(invalid(row[0]) for row in rows), sum(invalid(row[1]) for row in rows),
            len(keys), sum(row[1] is None for row in rows), len(rows) - len(keys),
            sum(row[1] is not None and row[0] == row[1] for row in rows),
            sum(row[1] is not None and row[1] not in keys for row in rows),
            0, 0, len(rows) - len(counter)]


def assert_report(rows, actual, expected):
    assert len(rows) == len(CHECKS), 'Aggregate report length mismatch'
    for order, (row, name, value, target) in enumerate(zip(rows, CHECKS, actual, expected), 1):
        assert list(row) == COLUMNS, 'Aggregate report schema/order mismatch'
        assert row == dict(check_order=order, check_name=name, actual=value, expected=target,
                           status='PASS' if value == target else 'FAIL'), 'Aggregate report value mismatch'


def fixture_sql(sql, path, counter):
    values = reference(counter)
    replacement = f'SELECT {values[0]} AS expected_rows,{values[7]} AS expected_categories,{values[8]} AS expected_null_parents'
    assert sql.count(COUNT_SQL) == 1 and sql.count(SOURCE) == 2
    return sql.replace(COUNT_SQL, replacement).replace(SOURCE, path.as_posix().replace("'", "''"))


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
    script_path = 'sql/55_import_retailrocket_categories.sql'
    validator_path = 'validation/preflight_retailrocket_categories_import.py'
    audit_path = 'data/retailrocket_source_audit.json'
    independent_path = 'data/retailrocket_independent_checks.json'
    output = root / 'data/retailrocket_categories_import_preflight.json'
    assert args.output.resolve() == output.resolve(), 'Output must be the fixed aggregate evidence path'
    dependencies = [script_path, validator_path, audit_path, 'scripts/audit_retailrocket_sources.py',
                    independent_path, 'validation/retailrocket_source_check.sql',
                    'sql/54_import_retailrocket_events.sql', 'validation/preflight_retailrocket_events_import.py',
                    'data/retailrocket_events_import_preflight.json']
    hashes = {name: sha256(root / name) for name in dependencies}
    sql = (root / script_path).read_text(encoding='utf-8')
    assert 'CREATE TABLE rr_raw.category_tree AS' in sql and 'OR REPLACE' not in sql and 'CREATE TABLE IF NOT EXISTS' not in sql
    assert sql.count('EXCEPT ALL') == 2 and sql.count('strict_mode=true') == 2
    assert sql.count('ignore_errors=false') == 2 and sql.count("force_not_null=['categoryid']") == 2
    audit = json.loads((root / audit_path).read_text(encoding='utf-8'))
    source_evidence = audit['files']['category_tree.csv']
    assert audit['all_checks_passed'] and source_evidence['sha256'] == SOURCE_SHA
    assert source_evidence['rows'] == EXPECTED[0] and source_evidence['column_names'] == FIELDS
    assert source_evidence['size_bytes'] == 14454 and source_evidence['empty_fields']['parentid'] == 25
    independent = json.loads((root / independent_path).read_text(encoding='utf-8'))
    assert independent['source_before']['category_tree.csv']['sha256'] == SOURCE_SHA
    assert independent['source_hashes_unchanged']
    tmp_root = root / 'tmp'
    tmp_root.mkdir(exist_ok=True)

    def execute(folder, query, allow_error=False):
        assert folder.resolve().is_relative_to(tmp_root.resolve()), 'Temporary directory escapes repository tmp'
        spill = (folder / 'spill').as_posix().replace("'", "''")
        settings = f"SET threads=2; SET memory_limit='512MB'; SET temp_directory='{spill}';\n"
        started = time.perf_counter()
        run = subprocess.run([args.duckdb, ':memory:', '-bail', '-json'], input=settings + query,
                             text=True, encoding='utf-8', capture_output=True, timeout=60)
        # Never print captured SQL diagnostics: they can quote source records.
        if not allow_error:
            assert run.returncode == 0, 'Isolated DuckDB execution failed; source diagnostics withheld'
        return run, round(time.perf_counter() - started, 3)

    cases = []
    with tempfile.TemporaryDirectory(prefix='rr-categories-fixture-', dir=tmp_root) as temporary:
        folder, path = Path(temporary), Path(temporary) / 'synthetic.csv'
        write_fixture(path, [['001', ''], ['002', '001'], ['002', '001'], ['003', '001']])
        counter = source_counter(path)
        adjusted = fixture_sql(sql, path, counter)
        run, _ = execute(folder, adjusted + '\n' + PRIVATE_QUERY)
        report, private = json_outputs(run.stdout)
        values = reference(counter)
        expected = values.copy()
        expected[9] = 0  # Raw duplicates are retained, while key uniqueness fails.
        assert_report(report, values, expected)
        assert table_counter(private) == counter, 'Synthetic string/NULL/multiplicity mismatch'
        rerun, _ = execute(folder, adjusted + '\n' + adjusted, allow_error=True)
        assert rerun.returncode != 0 and 'already exists' in rerun.stderr, 'Existing table was not protected'
        suffix = adjusted[adjusted.index('WITH expected_counts AS ('):]
        lost, _ = execute(folder, adjusted + "\nDELETE FROM rr_raw.category_tree WHERE rowid=(SELECT MIN(rowid) FROM rr_raw.category_tree WHERE categoryid='002');\n" + suffix)
        observed = {row['check_name']: row for row in json_outputs(lost.stdout)[1]}
        assert observed['source_rows_absent_from_table']['actual'] == 1 and observed['source_rows_absent_from_table']['status'] == 'FAIL'
        assert observed['table_rows_absent_from_source']['actual'] == 0
        assert observed['duplicate_surplus_rows_preserved']['actual'] == 0 and observed['duplicate_surplus_rows_preserved']['expected'] == 1
        cases.append(dict(case='preserve_null_leading_zeros_duplicates_flag_key_duplicates_reject_reimport_detect_lost_multiplicity', passed=True))
    assert not folder.exists()

    with tempfile.TemporaryDirectory(prefix='rr-categories-fixture-', dir=tmp_root) as temporary:
        folder, path = Path(temporary), Path(temporary) / 'synthetic.csv'
        write_fixture(path, [['', ''], [' 7 ', ''], ['2', ' 7 '], ['3', '3'], ['4', '999'], ['5', ' ']])
        counter = source_counter(path)
        run, _ = execute(folder, fixture_sql(sql, path, counter) + '\n' + PRIVATE_QUERY)
        report, private = json_outputs(run.stdout)
        values = reference(counter)
        assert values == [6, 2, 2, 0, 1, 2, 2, 6, 2, 0, 1, 2, 0, 0, 0]
        expected = values.copy()
        for index in (4, 5, 6, 10, 11):
            expected[index] = 0
        assert_report(report, values, expected)
        assert table_counter(private) == counter, 'Invalid raw strings were silently changed'
        cases.append(dict(case='retain_required_empty_whitespace_and_invalid_parent_text_flag_quality_and_immediate_links', passed=True))
    assert not folder.exists()

    with tempfile.TemporaryDirectory(prefix='rr-categories-fixture-', dir=tmp_root) as temporary:
        folder, path = Path(temporary), Path(temporary) / 'synthetic.csv'
        for malformed in ([['1', '', 'extra']], [['1']]):
            write_fixture(path, malformed)
            query = sql.replace(SOURCE, path.as_posix().replace("'", "''"))
            rejected, _ = execute(folder, query, allow_error=True)
            assert rejected.returncode != 0, 'Malformed CSV width was accepted or padded'
        cases.append(dict(case='strict_csv_rejects_extra_and_missing_fields', passed=True, expected_rejection=True))
    assert not folder.exists()
    print(json.dumps({'focused_cases_passed': len(cases)}), flush=True)
    if args.fixtures_only:
        return

    source = Path(SOURCE)
    source_hash = sha256(source)
    assert source_hash == SOURCE_SHA and source.stat().st_size == 14454, 'Category source differs from audited snapshot'
    counter = source_counter(source)
    assert reference(counter) == EXPECTED, 'Independent category reference differs from audited expectations'
    historical = {str(path.relative_to(root)): sha256(path) for path in (root / 'data').glob('*preflight.json')
                  if path.resolve() != output.resolve()}
    with tempfile.TemporaryDirectory(prefix='rr-categories-import-', dir=tmp_root) as temporary:
        folder = Path(temporary)
        run, elapsed = execute(folder, sql + '\n' + PRIVATE_QUERY)
        report, private = json_outputs(run.stdout)
        assert_report(report, EXPECTED, EXPECTED)
        imported = table_counter(private)
        python_source_only = sum((counter - imported).values())
        python_table_only = sum((imported - counter).values())
        assert python_source_only == python_table_only == 0, 'Independent full source/table multiset mismatch'
    assert not folder.exists()
    assert sha256(source) == source_hash and source.stat().st_size == 14454, 'Category source changed during preflight'
    assert all(sha256(root / name) == digest for name, digest in hashes.items()), 'Code/source audit dependency changed'
    assert all(sha256(root / name) == digest for name, digest in historical.items()), 'Historical preflight changed'
    evidence = dict(
        checked_at_utc=datetime.now(timezone.utc).isoformat(), executor='assistant',
        engine=subprocess.check_output([args.duckdb, '-version'], text=True).strip(),
        script=script_path, script_sha256=hashes[script_path], validator=validator_path, validator_sha256=hashes[validator_path],
        code_and_dependency_sha256=hashes, source_audit=audit_path, source_audit_sha256=hashes[audit_path],
        independent_source_checks=independent_path, independent_source_checks_sha256=hashes[independent_path],
        source_file='category_tree.csv', source_bytes=14454, source_sha256=source_hash, source_hash_unchanged=True,
        source_header=FIELDS, database=':memory:', preflight_settings={'threads': 2, 'memory_limit': '512MB', 'timeout_seconds': 60},
        table='rr_raw.category_tree', raw_fields=2, raw_types=['VARCHAR', 'VARCHAR'],
        import_semantics='Preserve all raw strings and observations, including leading zeros and duplicates; only exact-empty parentid becomes NULL. Plain CREATE protects an existing table. No trim, stored numeric cast, deduplication, replacement or joins to other tables.',
        source_rows_compared=1669, source_fields_compared=2, source_only_rows=0, table_only_rows=0,
        independent_python_csv_counter_source_only_rows=python_source_only,
        independent_python_csv_counter_table_only_rows=python_table_only,
        independent_python_csv_counter_all_tuples_and_multiplicities_matched=True,
        duplicate_surplus_rows_preserved=0, full_source_multiset_comparison='EXCEPT ALL in both directions plus an independent Python csv Counter comparison of all two-field tuples; NULL parent parsing is explicit.',
        report_rows=15, report_columns=5, output_columns=COLUMNS, checks_passed=15, results=report, report_sha256=fingerprint(report),
        report_fingerprint_contract='SHA-256 of ordered compact JSON arrays in output_columns order, each followed by LF; counts/order are integers and labels/status are strings.',
        fixture_case_count=len(cases), fixture_cases=cases,
        source_records_or_identifiers_exported_or_logged=False, real_comparison_records_held_only_in_process_memory=True,
        learner_database_opened=False, other_source_csvs_read=False, m5_queries_or_historical_suites_rerun=False,
        historical_preflight_files_unchanged=len(historical), temporary_databases_and_spills_removed=True,
        elapsed_import_checks_and_private_comparison_query_seconds=elapsed,
        timing_scope='One CLI execution includes import, all checks and private table projection; excludes hashing, Python reference and fixtures. memory_limit is not a process-wide cap.',
        scope='Assistant category raw-import preflight passed; learner SQL55 execution and acceptance pending. NULL parents are root candidates. No recursive cycles/depth/root membership, typed staging, property import, as-of joins or behavioral metrics are implemented by this step.')
    output.write_text(json.dumps(evidence, indent=2) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps({'checks_passed': 15, 'report_rows': 15, 'report_columns': 5,
                      'focused_cases_passed': len(cases), 'source_rows_compared': 1669,
                      'report_sha256': evidence['report_sha256'], 'elapsed_seconds': elapsed}), flush=True)


if __name__ == '__main__':
    main()
