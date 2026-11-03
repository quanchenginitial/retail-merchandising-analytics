"""Isolated typed category staging with tiny rejection fixtures and private Counters."""
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

import preflight_retailrocket_categories_import as previous

COLUMNS = previous.COLUMNS
COUNT_SQL = 'SELECT 1669::BIGINT AS expected_rows,25::BIGINT AS expected_null_parents'
CHECK_MARKER = '-- CHECKS: if rr_stg.category_tree already exists, run only the query below.'
CONTRACT_SHA = 'e382b2c65139cdd215d938c04515dd593feab92488e0e796b21093598a979313'
CHECKS = ['staging_rows', 'column_count', 'bigint_column_count', 'schema_mismatch_count',
          'distinct_categoryids', 'missing_categoryids', 'duplicate_key_surplus', 'null_parent_rows',
          'self_parent_rows', 'orphan_parent_rows', 'raw_rows', 'raw_value_contract_violations',
          'raw_only_rows', 'staging_only_rows', 'raw_null_parent_rows', 'root_set_difference',
          'numeric_key_collisions', 'raw_schema_mismatch']
EXPECTED = [1669, 2, 2, 0, 1669, 0, 0, 25, 0, 0, 1669, 0, 0, 0, 25, 0, 0, 0]
PRIVATE_QUERY = 'SELECT categoryid,parentid FROM rr_raw.category_tree; SELECT categoryid,parentid FROM rr_stg.category_tree;'


def valid(value):
    return (value is not None and re.fullmatch('[0-9]+', value) is not None
            and int(value) <= 9223372036854775807 and str(int(value)) == value)


def typed_counter(raw):
    assert all(valid(key) and (parent is None or valid(parent)) for key, parent in raw)
    return Counter((int(key), None if parent is None else int(parent)) for key, parent in raw.elements())


def reference(raw, staged, expected_rows, expected_roots):
    rows = list(staged.elements())
    keys = {key for key, _ in rows if key is not None}
    text = Counter((None if key is None else str(key), None if parent is None else str(parent)) for key, parent in rows)
    raw_roots = {key for key, parent in raw if parent is None}
    staged_roots = {str(key) for key, parent in rows if parent is None and key is not None}
    groups = defaultdict(set)
    for key, _ in raw:
        if key is not None and re.fullmatch('[0-9]+', key) and int(key) <= 9223372036854775807:
            groups[int(key)].add(key)
    actual = [len(rows), 2, 2, 0, len(keys), sum(key is None for key, _ in rows), len(rows)-len(keys),
              sum(parent is None for _, parent in rows), sum(key == parent for key, parent in rows if parent is not None),
              sum(parent is not None and parent not in keys for _, parent in rows), sum(raw.values()),
              sum(n for (key, parent), n in raw.items() if not valid(key) or (parent is not None and not valid(parent))),
              sum((raw-text).values()), sum((text-raw).values()), sum(n for (_, parent), n in raw.items() if parent is None),
              len(raw_roots ^ staged_roots), sum(len(values)>1 for values in groups.values()), 0]
    expected = [expected_rows, 2, 2, 0, expected_rows, 0, 0, expected_roots, 0, 0, expected_rows, 0, 0, 0, expected_roots, 0, 0, 0]
    return [dict(check_order=i, check_name=name, actual=value, expected=target,
                 status='PASS' if value == target else 'FAIL')
            for i, (name, value, target) in enumerate(zip(CHECKS, actual, expected), 1)]


def setup(rows, schema='categoryid VARCHAR,parentid VARCHAR'):
    def literal(value):
        return 'NULL' if value is None else "'" + value.replace("'", "''") + "'"
    query = f'CREATE SCHEMA rr_raw; CREATE TABLE rr_raw.category_tree ({schema});\n'
    if rows:
        query += 'INSERT INTO rr_raw.category_tree VALUES ' + ','.join('('+','.join(map(literal, row))+')' for row in rows) + ';\n'
    return query


def adjusted(sql, count, roots):
    assert sql.count(COUNT_SQL) == 2
    return sql.replace(COUNT_SQL, f'SELECT {count}::BIGINT AS expected_rows,{roots}::BIGINT AS expected_null_parents')


def snapshot(path):
    s = path.stat()
    return dict(size_bytes=s.st_size, modified_time_ns=s.st_mtime_ns, sha256=previous.sha256(path))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--duckdb', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--fixtures-only', action='store_true')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    script_path = 'sql/60_stage_retailrocket_categories.sql'
    validator_path = 'validation/preflight_retailrocket_categories_staging.py'
    method_path = 'docs/RETAILROCKET_CATEGORIES_STAGING_VALIDATION.md'
    output = root/'data/retailrocket_categories_staging_preflight.json'
    assert args.output.resolve() == output.resolve()
    dependencies = [script_path, validator_path, 'validation/preflight_retailrocket_categories_import.py',
                    'sql/55_import_retailrocket_categories.sql', 'data/retailrocket_source_audit.json',
                    'data/retailrocket_categories_import_preflight.json', 'data/retailrocket_categories_import_learner_acceptance.json',
                    'docs/RETAILROCKET_CATEGORIES_IMPORT_VALIDATION.md', 'data/retailrocket_unmatched_categories_preflight.json',
                    'data/retailrocket_unmatched_categories_learner_acceptance.json', 'docs/RETAILROCKET_UNMATCHED_CATEGORIES_VALIDATION.md']
    hashes = {p: previous.sha256(root/p) for p in dependencies}
    assert hashes['data/retailrocket_unmatched_categories_learner_acceptance.json'] == '8f7527610ce24b8f0405ae23858b770b7873ac717e6fd1b4ea1a1a3f719994cb'
    assert hashes['docs/RETAILROCKET_UNMATCHED_CATEGORIES_VALIDATION.md'] == 'cede079c23aa0039f620de9365e7433504fa122515f823b1d63c07535e9f14d6'
    contract = (root/method_path).read_bytes().split(b'\n## Executed results\n', 1)[0]
    assert hashlib.sha256(contract).hexdigest() == CONTRACT_SHA
    sql = (root/script_path).read_text(encoding='utf-8')
    assert 'CREATE TABLE rr_stg.category_tree AS' in sql and 'OR REPLACE' not in sql and 'CREATE TABLE IF NOT EXISTS' not in sql
    assert sql.count(CHECK_MARKER) == 1 and sql.count('EXCEPT ALL') == 2
    raw_sql = (root/'sql/55_import_retailrocket_categories.sql').read_text(encoding='utf-8').split('-- CHECKS:', 1)[0]
    assert raw_sql.count('read_csv(') == 1 and 'EXCEPT ALL' not in raw_sql
    prior = json.loads((root/'data/retailrocket_categories_import_preflight.json').read_text(encoding='utf-8'))
    assert prior['script_sha256'] == hashes['sql/55_import_retailrocket_categories.sql'] and prior['checks_passed'] == 15
    audit = json.loads((root/'data/retailrocket_source_audit.json').read_text(encoding='utf-8'))
    assert audit['all_checks_passed'] and audit['files']['category_tree.csv']['sha256'] == previous.SOURCE_SHA
    tmp_root = root/'tmp'
    tmp_root.mkdir(exist_ok=True)
    free_before = shutil.disk_usage(tmp_root).free
    assert free_before >= 2*1024**3
    final_sizes = []

    def execute(folder, database, query, allow_error=False):
        assert folder.resolve().is_relative_to(tmp_root.resolve())
        assert Path(database).resolve().is_relative_to(folder.resolve())
        spill = (folder/'spill').as_posix().replace("'", "''")
        settings = f"SET threads=2; SET memory_limit='512MB'; SET max_temp_directory_size='1GB'; SET temp_directory='{spill}';\n"
        started = time.perf_counter()
        run = subprocess.run([args.duckdb, str(database), '-bail', '-json'], input=settings+query,
                             text=True, encoding='utf-8', capture_output=True, timeout=60)
        if not allow_error:
            assert run.returncode == 0, 'Private category staging execution failed; row-bearing diagnostics withheld'
        size = sum(p.stat().st_size for p in folder.rglob('*') if p.is_file())
        assert size <= 2*1024**3
        final_sizes.append(size)
        return run, round(time.perf_counter()-started, 3)

    cases = []
    with tempfile.TemporaryDirectory(prefix='rr-category-stage-fixture-', dir=tmp_root) as temporary:
        folder, database = Path(temporary), Path(temporary)/'valid.duckdb'
        rows = [('1', None), ('2', '1'), ('3', '1'), ('4', None)]
        raw = Counter(rows)
        changed_sql = adjusted(sql, 4, 2)
        run, _ = execute(folder, database, setup(rows)+changed_sql+'\n'+PRIVATE_QUERY)
        report, raw_rows, staged_rows = previous.json_outputs(run.stdout)
        staged = previous.table_counter(staged_rows)
        expected = reference(raw, typed_counter(raw), 4, 2)
        assert [r['actual'] for r in expected] == [4, 2, 2, 0, 4, 0, 0, 2, 0, 0, 4, 0, 0, 0, 2, 0, 0, 0]
        assert report == expected and staged == typed_counter(raw) and previous.table_counter(raw_rows) == raw
        run, _ = execute(folder, database, 'UPDATE rr_stg.category_tree SET parentid=999 WHERE categoryid=2;\n'+changed_sql.split(CHECK_MARKER, 1)[1]+'\n'+PRIVATE_QUERY)
        bad_report, raw_rows, staged_rows = previous.json_outputs(run.stdout)
        sentinel = previous.table_counter(staged_rows)
        assert bad_report == reference(raw, sentinel, 4, 2)
        assert bad_report[9]['actual'] == bad_report[12]['actual'] == bad_report[13]['actual'] == 1
        rejected, _ = execute(folder, database, changed_sql, allow_error=True)
        assert rejected.returncode != 0 and 'already exists' in rejected.stderr
        run, _ = execute(folder, database, PRIVATE_QUERY)
        raw_rows, staged_rows = previous.json_outputs(run.stdout)
        assert previous.table_counter(raw_rows) == raw and previous.table_counter(staged_rows) == sentinel
        cases.append(dict(case='hand_checked_typed_null_preservation_counter_report_changed_tuple_detected_existing_sentinel_preserved', passed=True))
    assert not folder.exists()

    invalid = [
        ('empty_input', [], 1, 0),
        ('wrong_row_count', [('1', None)], 2, 1),
        ('wrong_root_count', [('1', None)], 1, 0),
        ('single_leading_zero', [('01', None)], 1, 1),
        ('leading_zero_aliases', [('1', None), ('01', None)], 2, 2),
        ('parent_leading_zero', [('1', None), ('2', '01')], 2, 1),
        ('null_category', [(None, None)], 1, 1),
        ('empty_category', [('', None)], 1, 1),
        ('whitespace_category', [(' 1', None)], 1, 1),
        ('overflow_category', [('9223372036854775808', None)], 1, 1),
        ('negative_category', [('-1', None)], 1, 1),
        ('empty_parent', [('1', None), ('2', '')], 2, 1),
        ('duplicate_key', [('1', None), ('1', None)], 2, 2),
        ('self_parent', [('1', '1')], 1, 0),
        ('orphan_parent', [('1', None), ('2', '9')], 2, 1),
    ]
    with tempfile.TemporaryDirectory(prefix='rr-category-stage-reject-', dir=tmp_root) as temporary:
        folder = Path(temporary)
        for label, rows, count, roots in invalid:
            database = folder/(label+'.duckdb')
            rejected, _ = execute(folder, database, setup(rows)+adjusted(sql, count, roots), allow_error=True)
            assert rejected.returncode != 0 and 'SQL60 raw category contract failed' in rejected.stderr, label
            run, _ = execute(folder, database, "SELECT COUNT(*) AS target_tables FROM information_schema.tables WHERE table_schema='rr_stg' AND table_name='category_tree'; SELECT categoryid,parentid FROM rr_raw.category_tree;")
            target, raw_rows = previous.json_outputs(run.stdout)
            assert target == [{'target_tables': 0}] and previous.table_counter(raw_rows) == Counter(rows), label
        cases.append(dict(case='invalid_or_lossy_input_rejected_atomically_with_no_destination_and_raw_multiset_preserved', subcases=[x[0] for x in invalid], passed=True, expected_rejection=True))
    assert not folder.exists()

    with tempfile.TemporaryDirectory(prefix='rr-category-stage-schema-', dir=tmp_root) as temporary:
        folder = Path(temporary)
        schema_cases = [
            ('categoryid BIGINT,parentid VARCHAR', [('1', None)], [{'categoryid': 1, 'parentid': None}]),
            ('parentid VARCHAR,categoryid VARCHAR', [(None, '1')], [{'categoryid': '1', 'parentid': None}]),
        ]
        for index, (raw_schema, rows, expected_raw) in enumerate(schema_cases):
            database = folder/f'schema-{index}.duckdb'
            rejected, _ = execute(folder, database, setup(rows, raw_schema)+adjusted(sql, 1, 1), allow_error=True)
            assert rejected.returncode != 0
            if index == 1:
                assert 'SQL60 raw category contract failed' in rejected.stderr
            else:
                assert 'SQL60 raw category contract failed' in rejected.stderr or ('Binder Error' in rejected.stderr and 'regexp_full_match' in rejected.stderr)
            run, _ = execute(folder, database, "SELECT COUNT(*) AS target_tables FROM information_schema.tables WHERE table_schema='rr_stg' AND table_name='category_tree'; SELECT categoryid,parentid FROM rr_raw.category_tree;")
            target, raw_rows = previous.json_outputs(run.stdout)
            assert target == [{'target_tables': 0}] and raw_rows == expected_raw
        cases.append(dict(case='wrong_raw_type_or_order_rejected_without_staging_table', passed=True, expected_rejection=True))
    assert not folder.exists()
    print(json.dumps({'focused_cases_passed': len(cases), 'invalid_input_subcases': len(invalid)}), flush=True)
    if args.fixtures_only:
        return

    source = Path(previous.SOURCE)
    before = snapshot(source)
    assert before['sha256'] == previous.SOURCE_SHA and before['size_bytes'] == 14454
    raw_counter = previous.source_counter(source)
    expected_typed = typed_counter(raw_counter)
    assert len(expected_typed) == sum(expected_typed.values()) == 1669
    expected_report = reference(raw_counter, expected_typed, 1669, 25)
    assert [r['actual'] for r in expected_report] == EXPECTED and all(r['status']=='PASS' for r in expected_report)
    historical = {str(p.relative_to(root)): previous.sha256(p) for p in (root/'data').glob('*preflight.json') if p.resolve()!=output.resolve()}
    with tempfile.TemporaryDirectory(prefix='rr-category-stage-real-', dir=tmp_root) as temporary:
        folder, database = Path(temporary), Path(temporary)/'preflight.duckdb'
        run, elapsed = execute(folder, database, raw_sql+'\n'+sql+'\n'+PRIVATE_QUERY)
        report, raw_rows, staged_rows = previous.json_outputs(run.stdout)
        assert report == expected_report
        actual_raw, actual_typed = previous.table_counter(raw_rows), previous.table_counter(staged_rows)
        assert actual_raw == raw_counter and actual_typed == expected_typed
        database_bytes = database.stat().st_size
        actual_raw.clear(); actual_typed.clear(); raw_rows.clear(); staged_rows.clear()
    assert not folder.exists()
    after = snapshot(source)
    assert before == after
    assert all(previous.sha256(root/p)==h for p, h in hashes.items())
    assert all(previous.sha256(root/p)==h for p, h in historical.items())
    assert (root/method_path).read_bytes().startswith(contract)
    evidence = dict(
        checked_at_utc=datetime.now(timezone.utc).isoformat(), executor='assistant',
        engine=subprocess.check_output([args.duckdb, '-version'], text=True).strip(),
        script=script_path, script_sha256=hashes[script_path], validator=validator_path, validator_sha256=hashes[validator_path],
        code_and_dependency_sha256=hashes, method_contract=method_path, method_contract_prefix_bytes=len(contract),
        method_contract_prefix_sha256=CONTRACT_SHA, source_files=['category_tree.csv'],
        source_before={'category_tree.csv': before}, source_after={'category_tree.csv': after}, source_hashes_and_metadata_unchanged=True,
        raw_import_prefix_sha256=hashlib.sha256(raw_sql.encode()).hexdigest(),
        reconstruction_basis='Frozen SQL55 import prefix only; fresh category CSV hash and private Python Counter. No property/event/M5 source or earlier full audit suite read/rerun.',
        source_rows_compared=1669, source_fields_compared=2, table='rr_stg.category_tree', staged_types=['BIGINT', 'BIGINT'],
        transformation='Exact reversible ASCII/BIGINT conversion of known reference rows only; NULL parents preserved. Plain guarded CTAS refuses invalid input and protects an existing destination.',
        real_staging_executions=1, report_rows=18, report_columns=5, output_columns=COLUMNS, checks_passed=18, fail_rows=0,
        results=report, report_sha256=previous.fingerprint(report),
        report_fingerprint_contract='SHA-256 of ordered compact JSON arrays in output-column order, each followed by LF; counts are integers.',
        independent_python_csv_counter_typed_rows_matched=True, independent_python_csv_counter_raw_rows_unchanged=True,
        independent_python_typed_source_only_rows=0, independent_python_typed_staging_only_rows=0,
        fixture_case_count=len(cases), fixture_cases=cases, invalid_input_subcase_count=len(invalid),
        invalid_creation_destination_absence_verified=True, existing_destination_sentinel_preserved=True,
        independent_synthetic_counter_reports_matched=True,
        preflight_settings=dict(threads=2, memory_limit='512MB', max_temp_directory_size='1GB', timeout_seconds_per_phase=60),
        workspace_free_bytes_before=free_before, workspace_free_bytes_after=shutil.disk_usage(tmp_root).free,
        private_database_bytes_before_cleanup=database_bytes, largest_private_directory_bytes_observed_after_phase=max(final_sizes),
        temporary_databases_and_spills_removed=True, learner_database_opened=False, other_source_csvs_read=False,
        historical_comparison_or_analysis_suites_rerun=False, historical_preflight_files_unchanged=len(historical),
        source_records_or_identifiers_exported_or_logged=False, real_comparison_records_held_only_in_process_memory=True,
        elapsed_import_staging_checks_and_private_queries_seconds=elapsed,
        timing_scope='One bounded CLI run of raw prefix, guarded staging, checks and private projections; excludes hashing/Python reference/fixtures. Final directory-size observations are not continuous peaks.',
        scope='Assistant category staging passed; learner SQL60 execution pending. No PK/NOT NULL constraints, cyclicity/depth/root-path guarantee, invented unknown category, property/event staging or time-aware join.')
    output.write_text(json.dumps(evidence, indent=2)+'\n', encoding='utf-8', newline='\n')
    print(json.dumps({'report_rows':18,'checks_passed':18,'focused_cases_passed':len(cases),
                      'elapsed_seconds':elapsed,'report_sha256':evidence['report_sha256']}), flush=True)


if __name__ == '__main__':
    main()
