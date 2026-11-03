"""One small hierarchy report with an independent parent-chain graph oracle."""
import argparse
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

import preflight_retailrocket_categories_staging as staging

previous = staging.previous
COLUMNS = previous.COLUMNS
COUNT_SQL = 'SELECT 1669::BIGINT AS expected_rows,25::BIGINT AS expected_roots'
CONTRACT_SHA = 'a5a5a9991287be24ca976055557803b0a5e9e83770ff5b546f2a80f0e64b0881'
CHECKS = ['category_rows', 'column_count', 'schema_mismatch', 'distinct_categoryids',
          'missing_categoryids', 'duplicate_key_surplus', 'negative_identifier_rows', 'root_nodes',
          'self_parent_rows', 'orphan_parent_rows', 'root_reachable_nodes', 'cycle_affected_nodes',
          'repeated_traversal_rows', 'depth_limit_child_edges', 'max_root_depth', 'leaf_nodes',
          'branching_nodes', 'max_children_per_node']
SOURCE_QUERY = 'SELECT categoryid,parentid FROM rr_stg.category_tree;'


def graph_reference(rows, expected_rows, expected_roots, schema_ok=True):
    """Follow every parent chain independently of SQL's root-down recursion."""
    keys = {key for key, _ in rows if key is not None}
    base = [len(rows), 2, 0 if schema_ok else 1, len(keys),
            sum(key is None for key, _ in rows), sum(key is not None for key, _ in rows)-len(keys),
            sum((key is not None and key < 0) or (parent is not None and parent < 0) for key, parent in rows),
            sum(parent is None for _, parent in rows),
            sum(key is not None and parent is not None and key == parent for key, parent in rows),
            sum(parent is not None and parent not in keys for _, parent in rows)]
    expected = [expected_rows, 2, 0, expected_rows, 0, 0, 0, expected_roots, 0, 0,
                expected_rows, 0, 0, 0, None, None, None, None]
    admitted = schema_ok and len(rows) == expected_rows and len(rows) > 0 and all(base[i] == 0 for i in (4, 5, 6, 9))
    depths, affected = {}, 0
    if admitted:
        parents = dict(rows)
        for start in parents:
            node, depth, seen = start, 0, set()
            while node not in seen:
                seen.add(node)
                parent = parents[node]
                if parent is None:
                    depths[start] = depth
                    break
                assert parent in parents
                node, depth = parent, depth+1
            else:
                affected += 1
        assert len(depths)+affected == len(rows)
        assert all(depth < len(rows) for depth in depths.values())
        graph = [len(depths), affected, 0, 0]
    else:
        graph = [None]*4
    healthy = admitted and base == expected[:10] and len(depths) == len(rows)
    if healthy:
        children = Counter(parent for _, parent in rows if parent is not None)
        observations = [max(depths.values()), sum(children[key] == 0 for key in keys),
                        sum(children[key] > 1 for key in keys), max(children[key] for key in keys)]
    else:
        observations = [None]*4
    actual = base+graph+observations
    report = [dict(check_order=i, check_name=name, actual=value, expected=target,
                   status='BLOCKED' if value is None else 'INFO' if target is None else 'PASS' if value == target else 'FAIL')
              for i, (name, value, target) in enumerate(zip(CHECKS, actual, expected), 1)]
    return report, depths


def setup(rows, schema='categoryid BIGINT,parentid BIGINT'):
    query = f'CREATE SCHEMA rr_stg; CREATE TABLE rr_stg.category_tree ({schema});\n'
    if rows:
        query += 'INSERT INTO rr_stg.category_tree VALUES ' + ','.join(
            '('+','.join('NULL' if value is None else str(value) for value in row)+')' for row in rows) + ';\n'
    return query


def adjusted(sql, count, roots):
    assert sql.count(COUNT_SQL) == 1
    return sql.replace(COUNT_SQL, f'SELECT {count}::BIGINT AS expected_rows,{roots}::BIGINT AS expected_roots')


def depth_projection(sql):
    assert sql.count('\nSELECT check_order,check_name,actual::BIGINT') == 1
    return sql.split('\nSELECT check_order,check_name,actual::BIGINT', 1)[0] + '\nSELECT categoryid,depth FROM rooted_walk ORDER BY categoryid;'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--duckdb', required=True)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--fixtures-only', action='store_true')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    script_path = 'sql/61_audit_retailrocket_category_hierarchy.sql'
    validator_path = 'validation/preflight_retailrocket_category_hierarchy.py'
    method_path = 'docs/RETAILROCKET_CATEGORY_HIERARCHY_VALIDATION.md'
    output = root/'data/retailrocket_category_hierarchy_preflight.json'
    assert args.output.resolve() == output.resolve()
    dependencies = [script_path, validator_path, 'validation/preflight_retailrocket_categories_staging.py',
                    'validation/preflight_retailrocket_categories_import.py', 'sql/55_import_retailrocket_categories.sql',
                    'sql/60_stage_retailrocket_categories.sql', 'data/retailrocket_source_audit.json',
                    'data/retailrocket_categories_import_preflight.json', 'data/retailrocket_categories_staging_preflight.json',
                    'data/retailrocket_categories_staging_learner_acceptance.json', 'docs/RETAILROCKET_CATEGORIES_STAGING_VALIDATION.md']
    hashes = {p: previous.sha256(root/p) for p in dependencies}
    assert hashes['data/retailrocket_categories_staging_learner_acceptance.json'] == 'a602c9d2618a0527d83ae62d23fcceb20e65fc4958020a284bb2199d69ed86d1'
    assert hashes['docs/RETAILROCKET_CATEGORIES_STAGING_VALIDATION.md'] == '0547afad690aea53695b0e750f31b553e7879bdeceadf0665bb5b5d34d40e258'
    contract = (root/method_path).read_bytes().split(b'\n## Executed results\n', 1)[0]
    assert hashlib.sha256(contract).hexdigest() == CONTRACT_SHA
    sql = (root/script_path).read_text(encoding='utf-8')
    assert not re.search(r'\b(CREATE|INSERT|UPDATE|DELETE|DROP|COPY|MERGE|read_csv)\b', re.sub(r'--[^\n]*', '', sql), re.I)
    raw_sql = (root/'sql/55_import_retailrocket_categories.sql').read_text(encoding='utf-8').split('-- CHECKS:', 1)[0]
    stage_sql = (root/'sql/60_stage_retailrocket_categories.sql').read_text(encoding='utf-8').split(staging.CHECK_MARKER, 1)[0]
    assert raw_sql.count('read_csv(') == 1 and 'EXCEPT ALL' not in raw_sql+stage_sql
    for path, evidence, expected_pass in [
        ('sql/55_import_retailrocket_categories.sql', 'data/retailrocket_categories_import_preflight.json', 15),
        ('sql/60_stage_retailrocket_categories.sql', 'data/retailrocket_categories_staging_preflight.json', 18),
    ]:
        prior = json.loads((root/evidence).read_text(encoding='utf-8'))
        assert prior['script_sha256'] == hashes[path] and prior['checks_passed'] == expected_pass
    audit = json.loads((root/'data/retailrocket_source_audit.json').read_text(encoding='utf-8'))
    assert audit['all_checks_passed'] and audit['files']['category_tree.csv']['sha256'] == previous.SOURCE_SHA
    tmp_root = root/'tmp'
    tmp_root.mkdir(exist_ok=True)
    free_before = shutil.disk_usage(tmp_root).free
    assert free_before >= 2*1024**3
    sizes = []

    def execute(folder, database, query):
        assert folder.resolve().is_relative_to(tmp_root.resolve())
        assert Path(database).resolve().is_relative_to(folder.resolve())
        spill = (folder/'spill').as_posix().replace("'", "''")
        settings = f"SET threads=2; SET memory_limit='512MB'; SET max_temp_directory_size='1GB'; SET temp_directory='{spill}';\n"
        start = time.perf_counter()
        run = subprocess.run([args.duckdb, str(database), '-bail', '-json'], input=settings+query,
                             text=True, encoding='utf-8', capture_output=True, timeout=60)
        assert run.returncode == 0, 'Private hierarchy audit failed; row-bearing diagnostics withheld'
        size = sum(p.stat().st_size for p in folder.rglob('*') if p.is_file())
        assert size <= 2*1024**3
        sizes.append(size)
        return previous.json_outputs(run.stdout), round(time.perf_counter()-start, 3)

    cases = []
    with tempfile.TemporaryDirectory(prefix='rr-hierarchy-fixtures-', dir=tmp_root) as temporary:
        folder = Path(temporary)

        def check(label, rows, count, roots, schema='categoryid BIGINT,parentid BIGINT', logical_rows=None, schema_ok=True):
            logical = rows if logical_rows is None else logical_rows
            expected, depths = graph_reference(logical, count, roots, schema_ok)
            query = adjusted(sql, count, roots)
            results, _ = execute(folder, folder/(label+'.duckdb'), setup(rows, schema)+query+'\n'+depth_projection(query)+'\n'+SOURCE_QUERY)
            report, observed_depths, observed_rows = results
            assert report == expected, label+' aggregate oracle mismatch'
            assert Counter((r['categoryid'], r['depth']) for r in observed_depths) == Counter(depths.items()), label+' depth oracle mismatch'
            assert previous.table_counter(observed_rows) == Counter(logical), label+' changed input rows'
            return report

        forest = [(1, None), (2, 1), (3, 1), (4, 2), (5, None)]
        report = check('forest', forest, 5, 2)
        assert [r['actual'] for r in report] == [5, 2, 0, 5, 0, 0, 0, 2, 0, 0, 5, 0, 0, 0, 2, 3, 1, 2]
        singleton = check('singleton', [(1, None)], 1, 1)
        assert [r['actual'] for r in singleton[14:]] == [0, 1, 0, 0]
        chain = [(1, None)]+[(i, i-1) for i in range(2, 13)]
        chain_report = check('maximum_length_chain', chain, 12, 1)
        assert chain_report[13]['actual'] == 0 and chain_report[14]['actual'] == 11
        cases.append(dict(case='hand_checked_branching_forest_isolated_root_singleton_and_maximum_N_minus_1_chain', passed=True))

        cycle = [(1, None), (2, 1), (10, 11), (11, 12), (12, 10), (13, 10)]
        cycle_report = check('three_cycle_with_feeder', cycle, 6, 1)
        assert cycle_report[10]['actual'] == 2 and cycle_report[11]['actual'] == 4
        assert cycle_report[10]['status'] == cycle_report[11]['status'] == 'FAIL'
        self_report = check('self_cycle_with_root', [(1, None), (2, 2)], 2, 1)
        assert self_report[8]['actual'] == self_report[11]['actual'] == 1
        all_cycle = check('rootless_cycle', [(1, 2), (2, 3), (3, 1)], 3, 0)
        assert all_cycle[10]['actual'] == 0 and all_cycle[11]['actual'] == 3
        assert all(r['status']=='BLOCKED' and r['actual'] is None for r in cycle_report[14:])
        cases.append(dict(case='admitted_three_node_cycle_with_feeder_self_cycle_and_rootless_cycle_detected_finitely', passed=True))

        invalid = [
            ('orphan', [(1, None), (2, 9)], 2, 1),
            ('duplicate', [(1, None), (1, None)], 2, 2),
            ('missing_id', [(None, None)], 1, 1),
            ('negative_id', [(-1, None)], 1, 1),
            ('negative_parent', [(1, None), (2, -1)], 2, 1),
            ('empty', [], 0, 0),
            ('wrong_count', [(1, None)], 2, 1),
        ]
        for label, rows, count, roots in invalid:
            rejected = check(label, rows, count, roots)
            assert all(r['status']=='BLOCKED' and r['actual'] is None for r in rejected[10:])
        wrong_roots = check('wrong_root_baseline', [(1, None)], 1, 2)
        assert wrong_roots[7]['status']=='FAIL' and wrong_roots[10]['status']=='PASS'
        assert all(r['status']=='BLOCKED' for r in wrong_roots[14:])
        for label, schema, rows, logical in [
            ('wrong_integer_type', 'categoryid INTEGER,parentid BIGINT', [(1, None)], [(1, None)]),
            ('wrong_order', 'parentid BIGINT,categoryid BIGINT', [(None, 1)], [(1, None)]),
        ]:
            rejected = check(label, rows, 1, 1, schema, logical, False)
            assert rejected[2]['actual']==1 and all(r['status']=='BLOCKED' for r in rejected[10:])
        cases.append(dict(case='orphan_duplicate_missing_negative_empty_count_and_populated_schema_inputs_suppress_graph_root_baseline_does_not',
                          subcases=[x[0] for x in invalid]+['wrong_root_baseline', 'wrong_integer_type', 'wrong_order'], passed=True))
    assert not folder.exists()
    print(json.dumps({'focused_cases_passed': len(cases)}), flush=True)
    if args.fixtures_only:
        return

    source = Path(previous.SOURCE)
    before = staging.snapshot(source)
    assert before['sha256'] == previous.SOURCE_SHA and before['size_bytes'] == 14454
    raw_counter = previous.source_counter(source)
    typed_counter = staging.typed_counter(raw_counter)
    assert len(typed_counter) == sum(typed_counter.values()) == 1669
    expected_report, expected_depths = graph_reference(list(typed_counter.elements()), 1669, 25)
    assert all(r['status']=='PASS' for r in expected_report[:14]) and all(r['status']=='INFO' for r in expected_report[14:])
    historical = {str(p.relative_to(root)): previous.sha256(p) for p in (root/'data').glob('*preflight.json') if p.resolve()!=output.resolve()}
    with tempfile.TemporaryDirectory(prefix='rr-hierarchy-real-', dir=tmp_root) as temporary:
        folder, database = Path(temporary), Path(temporary)/'preflight.duckdb'
        results, elapsed = execute(folder, database, raw_sql+'\n'+stage_sql+'\n'+sql+'\n'+depth_projection(sql)+'\n'+SOURCE_QUERY)
        report, depth_rows, source_rows = results
        assert report == expected_report
        assert Counter((r['categoryid'], r['depth']) for r in depth_rows) == Counter(expected_depths.items())
        assert previous.table_counter(source_rows) == typed_counter
        database_bytes = database.stat().st_size
        depth_rows.clear(); source_rows.clear(); expected_depths.clear(); typed_counter.clear(); raw_counter.clear()
    assert not folder.exists()
    after = staging.snapshot(source)
    assert before == after
    assert all(previous.sha256(root/p)==h for p,h in hashes.items())
    assert all(previous.sha256(root/p)==h for p,h in historical.items())
    assert (root/method_path).read_bytes().startswith(contract)
    evidence = dict(
        checked_at_utc=datetime.now(timezone.utc).isoformat(), executor='assistant',
        engine=subprocess.check_output([args.duckdb, '-version'], text=True).strip(),
        script=script_path, script_sha256=hashes[script_path], validator=validator_path, validator_sha256=hashes[validator_path],
        code_and_dependency_sha256=hashes, method_contract=method_path, method_contract_prefix_bytes=len(contract),
        method_contract_prefix_sha256=CONTRACT_SHA, source_files=['category_tree.csv'],
        source_before={'category_tree.csv': before}, source_after={'category_tree.csv': after}, source_hashes_and_metadata_unchanged=True,
        reconstruction_prefix_sha256={'sql/55_import_retailrocket_categories.sql': hashlib.sha256(raw_sql.encode()).hexdigest(),
                                      'sql/60_stage_retailrocket_categories.sql': hashlib.sha256(stage_sql.encode()).hexdigest()},
        reconstruction_basis='Frozen SQL55 import and SQL60 creation prefixes only; one category CSV, no previous full report suites.',
        real_audit_report_executions=1, private_depth_projection_executions=1,
        report_rows=18, report_columns=5, output_columns=COLUMNS, checks_passed=14, info_rows=4, fail_rows=0, blocked_rows=0,
        results=report, report_sha256=previous.fingerprint(report),
        report_fingerprint_contract='SHA-256 of ordered compact JSON arrays in output-column order, each followed by LF; actual counts are integers and INFO expectations are null.',
        independent_python_parent_chain_report_matched=True, independent_python_all_node_depths_matched=True,
        independent_python_depth_nodes_compared=1669, independent_python_input_tuples_unchanged=True,
        fixture_case_count=len(cases), fixture_cases=cases, independent_synthetic_graph_reports_and_depths_matched=True,
        preflight_settings=dict(threads=2, memory_limit='512MB', max_temp_directory_size='1GB', timeout_seconds_per_phase=60),
        workspace_free_bytes_before=free_before, workspace_free_bytes_after=shutil.disk_usage(tmp_root).free,
        private_database_bytes_before_cleanup=database_bytes, largest_private_directory_bytes_observed_after_phase=max(sizes),
        temporary_databases_and_spills_removed=True, learner_database_opened=False, other_source_csvs_read=False,
        historical_comparison_or_analysis_suites_rerun=False, historical_preflight_files_unchanged=len(historical),
        source_records_identifiers_paths_or_depth_maps_exported_or_logged=False, real_comparison_records_held_only_in_process_memory=True,
        elapsed_prefixes_report_private_depths_and_input_query_seconds=elapsed,
        timing_scope='One bounded CLI execution: two reconstruction prefixes, one public aggregate audit, one private SQL traversal projection and one private input projection; excludes hashes/Python oracle/fixtures. Directory observations are post-phase, not continuous peaks.',
        scope='Assistant hierarchy audit passed; learner SQL61 execution pending. Known-reference forest only. No root/depth table, category meaning, unmatched-property repair, event-time coverage or future database constraint is established.')
    output.write_text(json.dumps(evidence, indent=2)+'\n', encoding='utf-8', newline='\n')
    print(json.dumps({'report_rows':18, 'checks_passed':14, 'info_rows':4, 'focused_cases_passed':len(cases),
                      'elapsed_seconds':elapsed, 'report_sha256':evidence['report_sha256']}), flush=True)


if __name__ == '__main__':
    main()
