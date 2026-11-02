"""One private exact-unmatched category audit with independent tiny reference sets.

No source values, item IDs or keyed groups are exported; numeric interpretation
is never persisted. Reconstruct only frozen raw imports, not prior audit suites.
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

import preflight_retailrocket_named_properties as named

previous = named.previous
FILES, HEADERS, HASHES = named.FILES, named.HEADERS, named.HASHES
COLUMNS, GIB = named.COLUMNS, named.GIB
COUNTS = (20275902, 788214, 167, 1669)
COUNT_SQL = ('SELECT 20275902::BIGINT AS expected_rows,788214::BIGINT AS expected_category_rows,\n'
             '        167::BIGINT AS expected_unmatched_rows,1669::BIGINT AS expected_reference_rows')
CONTRACT_SHA = '9be6f7027aaaa81a126103a740470c8c4781ae180ebf9df5f493a2fa0484d9d4'
CHECKS = ['raw_rows', 'categoryid_rows', 'exact_unmatched_rows', 'category_reference_rows',
          'reference_duplicate_id_surplus', 'reference_missing_ids', 'unknown_source_file_rows',
          'unmatched_items', 'unmatched_raw_category_values', 'unmatched_raw_timestamps',
          'unmatched_part1_rows', 'unmatched_part2_rows', 'reference_numeric_ineligible_rows',
          'reference_ambiguous_normalized_ids', 'unmatched_numeric_eligible_rows',
          'unmatched_numeric_ineligible_rows', 'unmatched_numeric_unique_reference_rows',
          'unmatched_numeric_ambiguous_reference_rows', 'unmatched_numeric_no_reference_rows',
          'unmatched_part_rows_reconciled', 'unmatched_numeric_eligibility_reconciled',
          'unmatched_numeric_candidate_partition_reconciled']


def canonical(value):
    return int(value) if named.valid_integer(value) else None


def reference(rows, categories, expected_counts):
    """Independent tiny-data Counter/set oracle; never run on actual source rows."""
    counts = Counter(r[0] for r in categories)
    exact_ids = {value for value in counts if value is not None}
    candidates = defaultdict(set)
    ineligible_reference = 0
    for raw_id, multiplicity in counts.items():
        numeric_id = canonical(raw_id)
        if numeric_id is None:
            ineligible_reference += multiplicity
        else:
            candidates[numeric_id].add(raw_id)
    category_rows = [r for r in rows if r[2] == 'categoryid']
    cohort = [r for r in category_rows if r[3] is None or r[3] not in exact_ids]
    eligible = ineligible = unique = ambiguous = absent = 0
    for row in cohort:
        value = canonical(row[3])
        if value is None:
            ineligible += 1
            continue
        eligible += 1
        n = len(candidates.get(value, set()))
        unique += n == 1
        ambiguous += n > 1
        absent += n == 0
    p1 = sum(r[4] == previous.FILES[0] for r in cohort)
    p2 = sum(r[4] == previous.FILES[1] for r in cohort)
    actual = [len(rows), len(category_rows), len(cohort), len(categories),
              sum(n - 1 for n in counts.values()), sum(r[0] in (None, '') for r in categories),
              sum(r[4] not in previous.FILES for r in rows),
              len({r[1] for r in cohort if r[1] is not None}),
              len({r[3] for r in cohort if r[3] is not None}),
              len({r[0] for r in cohort if r[0] is not None}), p1, p2,
              ineligible_reference, sum(len(raw_ids) > 1 for raw_ids in candidates.values()),
              eligible, ineligible, unique, ambiguous, absent, p1 + p2,
              eligible + ineligible, unique + ambiguous + absent]
    expected = [*expected_counts, 0, 0, 0] + [None] * 12 + [len(cohort), len(cohort), eligible]
    healthy = actual[:7] == expected[:7]
    return [dict(check_order=i, check_name=name, actual=value, expected=target,
                 status=('INFO' if healthy else 'BLOCKED') if target is None else ('PASS' if value == target else 'FAIL'))
            for i, (name, value, target) in enumerate(zip(CHECKS, actual, expected), 1)]


def adjusted(sql, counts):
    replacement = (f'SELECT {counts[0]}::BIGINT AS expected_rows,{counts[1]}::BIGINT AS expected_category_rows,\n'
                   f'        {counts[2]}::BIGINT AS expected_unmatched_rows,{counts[3]}::BIGINT AS expected_reference_rows')
    assert sql.count(COUNT_SQL) == 1
    return sql.replace(COUNT_SQL, replacement)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--duckdb', required=True)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--fixtures-only', action='store_true')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    script_path = 'sql/59_audit_retailrocket_unmatched_categories.sql'
    validator_path = 'validation/preflight_retailrocket_unmatched_categories.py'
    method_path = 'docs/RETAILROCKET_UNMATCHED_CATEGORIES_VALIDATION.md'
    prior_path = 'data/retailrocket_named_properties_preflight.json'
    output = root / 'data/retailrocket_unmatched_categories_preflight.json'
    assert args.output.resolve() == output.resolve()
    dependencies = [script_path, validator_path, 'validation/preflight_retailrocket_named_properties.py',
                    'validation/preflight_retailrocket_properties_import.py', 'sql/58_audit_retailrocket_named_properties.sql',
                    'sql/55_import_retailrocket_categories.sql', 'sql/56_import_retailrocket_properties.sql',
                    'data/retailrocket_source_audit.json', 'scripts/audit_retailrocket_sources.py',
                    'data/retailrocket_categories_import_preflight.json', 'data/retailrocket_properties_import_preflight.json',
                    prior_path, 'data/retailrocket_named_properties_learner_acceptance.json',
                    'docs/RETAILROCKET_NAMED_PROPERTIES_VALIDATION.md']
    hashes = {p: previous.sha256(root / p) for p in dependencies}
    assert hashes['data/retailrocket_named_properties_learner_acceptance.json'] == '71f537ca4f4cbc2cc243aac117db34dc32974c8ee22ed5c38d67bd671cdd5612'
    assert hashes['docs/RETAILROCKET_NAMED_PROPERTIES_VALIDATION.md'] == 'eef9c0aabd84cddbe2e5137524c3d3778706c41615887e0b3ce6fd64850ddd97'
    contract = (root / method_path).read_bytes().split(b'\n## Executed results\n', 1)[0]
    assert hashlib.sha256(contract).hexdigest() == CONTRACT_SHA
    sql = (root / script_path).read_text(encoding='utf-8')
    assert not re.search(r'\b(CREATE|INSERT|UPDATE|DELETE|DROP|COPY|MERGE|read_csv)\b', re.sub(r'--[^\n]*', '', sql), re.I)
    audit = json.loads((root / 'data/retailrocket_source_audit.json').read_text(encoding='utf-8'))
    assert audit['all_checks_passed']
    for name in FILES:
        assert audit['files'][name]['sha256'] == HASHES[name]
    prior = json.loads((root / prior_path).read_text(encoding='utf-8'))
    prior_values = {row['check_name']: row['actual'] for row in prior['results']}
    assert prior['checks_passed'] == 10 and prior['info_rows'] == 12
    assert [prior_values[k] for k in ('raw_rows', 'categoryid_rows', 'category_unmatched_exact_rows', 'category_reference_rows')] == list(COUNTS)
    assert prior['script_sha256'] == hashes['sql/58_audit_retailrocket_named_properties.sql']
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
    with tempfile.TemporaryDirectory(prefix='rr-unmatched-fixture-', dir=tmp_root) as temporary:
        folder = Path(temporary)
        p1, p2 = previous.FILES
        categories = [('7', None), ('08', '7'), ('8', '7'), ('9', None), ('x', None)]
        rows = [('1', '10', 'categoryid', '7', p1), ('2', '10', 'categoryid', '007', p1),
                ('2', '10', 'categoryid', '0007', p1), ('3', '11', 'categoryid', '008', p1),
                ('4', '12', 'categoryid', '0008', p2), ('5', '13', 'categoryid', '10', p2),
                ('6', '14', 'categoryid', ' 7', p2), ('7', '15', 'categoryid', '9223372036854775808', p2),
                ('8', '16', 'categoryid', None, p2), ('9', '17', 'categoryid', '\u0667', p2),
                ('10', '18', 'categoryid', '08', p2), ('11', '19', 'opaque', 'whatever', p1),
                ('2', '10', 'categoryid', '007', p1)]
        expected = reference(rows, categories, (13, 12, 10, 5))
        assert [r['actual'] for r in expected] == [13, 12, 10, 5, 0, 0, 0, 8, 8, 8, 4, 6, 1, 1, 6, 4, 3, 2, 1, 10, 10, 6]
        result, _ = execute(folder, ':memory:', named.fixture_sql(rows, categories) + adjusted(sql, (13, 12, 10, 5)), 'fixture')
        assert json.loads(result['stdout']) == expected, 'Independent canonical-candidate partition mismatch'
        cases.append(dict(case='hand_checked_exact_cohort_leading_zeros_ambiguity_absence_whitespace_overflow_unicode_null_and_multiplicity', passed=True))
        categories = [('7', None), ('7', None), (None, None)]
        rows = [('1', '1', 'categoryid', '007', p1), ('2', '2', 'categoryid', None, p2), ('3', '3', 'categoryid', '7', p2)]
        expected = reference(rows, categories, (3, 3, 2, 3))
        assert expected[4]['actual'] == expected[5]['actual'] == 1
        assert expected[13]['actual'] == 0 and expected[16]['actual'] == 1
        result, _ = execute(folder, ':memory:', named.fixture_sql(rows, categories) + adjusted(sql, (3, 3, 2, 3)), 'fixture')
        assert json.loads(result['stdout']) == expected, 'Exact reference duplicates falsely created ambiguity or multiplied rows'
        assert all(row['status'] == 'BLOCKED' for row in expected[7:19])
        cases.append(dict(case='exact_duplicate_and_null_reference_rows_fail_integrity_without_false_numeric_ambiguity', passed=True))
        categories, rows = [('7', None)], [('1', '1', 'categoryid', '7', p1), ('2', '2', 'available', '0', p2)]
        result, _ = execute(folder, ':memory:', named.fixture_sql(rows, categories) + adjusted(sql, (2, 1, 0, 1)), 'fixture')
        assert json.loads(result['stdout']) == reference(rows, categories, (2, 1, 0, 1))
        rows = [('1', '1', 'categoryid', '007', None)]
        result, _ = execute(folder, ':memory:', named.fixture_sql(rows, categories) + adjusted(sql, (1, 1, 1, 1)), 'fixture')
        assert json.loads(result['stdout']) == reference(rows, categories, (1, 1, 1, 1))
        result, _ = execute(folder, ':memory:', named.fixture_sql([], []) + sql, 'fixture')
        assert json.loads(result['stdout']) == reference([], [], COUNTS)
        for setup in [named.fixture_sql([], []).replace('timestamp VARCHAR', 'timestamp BIGINT'),
                      named.fixture_sql([], []).replace('categoryid VARCHAR,parentid VARCHAR', 'parentid VARCHAR,categoryid VARCHAR')]:
            result, _ = execute(folder, ':memory:', setup + sql, 'fixture', allow_error=True)
            assert result['returncode'] != 0 and 'SQL59 requires' in result['stderr']
        cases.append(dict(case='zero_cohort_empty_input_and_unknown_provenance_keep_denominators_wrong_schema_rejected', passed=True, expected_rejection=True))
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
    with tempfile.TemporaryDirectory(prefix='rr-unmatched-audit-', dir=tmp_root) as temporary:
        folder, database = Path(temporary), Path(temporary) / 'preflight.duckdb'
        result, import_seconds = execute(folder, database, import_sql, 'frozen_raw_imports')
        assert not result['stdout'].strip()
        print(json.dumps({'raw_reconstruction_completed': True, 'elapsed_seconds': import_seconds}), flush=True)
        result, audit_seconds = execute(folder, database, sql, 'unmatched_category_audit')
        report = json.loads(result['stdout'])
        assert len(report) == 22 and [r['check_name'] for r in report] == CHECKS
        for i, row in enumerate(report, 1):
            assert list(row) == COLUMNS and row['check_order'] == i and isinstance(row['actual'], int) and row['actual'] >= 0
            if 8 <= i <= 19:
                assert row['expected'] is None and row['status'] == 'INFO'
            else:
                assert row['actual'] == row['expected'] and row['status'] == 'PASS'
        assert [r['actual'] for r in report[:7]] == [*COUNTS, 0, 0, 0]
        values = {row['check_name']: row['actual'] for row in report}
        assert values['unmatched_numeric_eligible_rows'] + values['unmatched_numeric_ineligible_rows'] == COUNTS[2]
        assert sum(values[k] for k in ['unmatched_numeric_unique_reference_rows', 'unmatched_numeric_ambiguous_reference_rows', 'unmatched_numeric_no_reference_rows']) == values['unmatched_numeric_eligible_rows']
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
        source_hashes_and_metadata_unchanged=True, accepted_cohort_preflight=prior_path, accepted_cohort_preflight_sha256=hashes[prior_path],
        raw_import_prefix_sha256={p: hashlib.sha256(s.encode()).hexdigest() for p, s in prefixes.items()},
        raw_reconstruction_basis='Frozen SQL55/56 import prefixes only and fresh three-source hashes; prior copy evidence and accepted SQL58 exact-unmatched baseline. No prior comparisons or SQL57/58 audit rerun.',
        input_property_rows=20275902, input_category_property_rows=788214, input_category_reference_rows=1669,
        exact_unmatched_cohort_rows=167, real_audit_executions=1,
        report_rows=22, report_columns=5, output_columns=COLUMNS, checks_passed=10, info_rows=12, fail_rows=0, blocked_rows=0,
        results=report, report_sha256=previous.report_hash(report),
        report_fingerprint_contract='SHA-256 of ordered compact JSON arrays in output_columns order, each followed by LF; counts are integers, expected is integer or null.',
        fixture_case_count=len(cases), fixture_cases=cases, independent_synthetic_counter_reports_matched=True,
        full_source_python_counter_or_row_fingerprint_rerun=False, diagnostic_results_required_to_be_zero=False,
        identity='Cohort remains exact raw-text unmatched. Numeric diagnostic eligibility is ASCII digits/BIGINT only; reference ambiguity counts distinct raw spellings, never duplicate row occurrences.',
        preflight_settings=dict(threads=2, memory_limit='2GB', max_temp_directory_size='8GB', private_directory_budget_bytes=12 * GIB, timeout_seconds_per_phase=600),
        workspace_free_bytes_before=free_before, workspace_free_bytes_after=shutil.disk_usage(tmp_root).free,
        memory_availability_before=memory, peak_private_directory_bytes_observed=peak_bytes,
        private_database_bytes_before_cleanup=database_bytes, temporary_databases_and_spills_removed=True,
        learner_database_opened=False, other_source_csvs_read=False, source_records_or_identifiers_or_category_values_exported_or_logged=False,
        historical_comparison_or_analysis_suites_rerun=False, historical_preflight_files_unchanged=len(historical),
        elapsed_import_seconds=import_seconds, elapsed_audit_seconds=audit_seconds,
        elapsed_import_and_audit_seconds=round(import_seconds + audit_seconds, 3),
        timing_scope='One frozen-prefix reconstruction and one read-only cohort audit; excludes hashes and fixtures. Memory limit is not a process cap; disk observations are sampled.',
        scope='Assistant cohort diagnostic audit passed; learner SQL59 execution/acceptance pending. No persisted normalization, repair, staging, typed item/timestamp key merging, affected-item history, event/as-of join or source-cause/business-impact claim.')
    output.write_text(json.dumps(evidence, indent=2) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps({'report_rows': 22, 'checks_passed': 10, 'info_rows': 12, 'focused_cases_passed': len(cases),
                      'elapsed_seconds': evidence['elapsed_import_and_audit_seconds'], 'report_sha256': evidence['report_sha256']}), flush=True)


if __name__ == '__main__':
    main()
