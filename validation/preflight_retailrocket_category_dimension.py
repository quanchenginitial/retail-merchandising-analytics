"""Guarded category dimension preflight with independent full root/depth maps."""
import argparse
import hashlib
import json
import shutil
import subprocess
import tempfile
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import preflight_retailrocket_category_hierarchy as hierarchy

staging, previous = hierarchy.staging, hierarchy.previous
COLUMNS = previous.COLUMNS
FIELDS = ['categoryid', 'parentid', 'root_categoryid', 'depth']
COUNT_SQL = 'SELECT 1669::BIGINT AS expected_rows,25::BIGINT AS expected_roots,5::BIGINT AS expected_max_depth'
CHECK_MARKER = '-- CHECKS: if rr_core.dim_category already exists, run only the query below.'
CONTRACT_SHA = '5cd3ebab26b643a29c87a57c71f612f7d850991c666bfdb6971144dddf6fa593'
CHECKS = ['dimension_rows', 'column_count', 'schema_mismatch_count', 'distinct_categoryids',
          'missing_required_rows', 'duplicate_key_surplus', 'null_parent_rows', 'distinct_root_ids',
          'root_identity_errors', 'root_reference_errors', 'parent_mapping_errors', 'parent_root_depth_errors',
          'negative_depth_rows', 'max_depth', 'source_only_rows', 'dimension_only_rows',
          'expected_mapping_only_rows', 'dimension_mapping_only_rows', 'source_contract_violations', 'source_rows']
PRIVATE_QUERY = ('SELECT categoryid,parentid FROM rr_stg.category_tree; '
                 'SELECT categoryid,parentid,root_categoryid,depth FROM rr_core.dim_category;')


def mapping_reference(rows):
    """Independent per-start parent walks; no reuse of SQL's propagated root IDs."""
    assert len(rows) == len(dict(rows)) and all(key is not None for key, _ in rows)
    parents, result = dict(rows), Counter()
    for start, original_parent in rows:
        node, depth, seen = start, 0, set()
        while node not in seen:
            seen.add(node)
            parent = parents[node]
            if parent is None:
                result[(start, original_parent, node, depth)] += 1
                break
            assert parent in parents, 'Independent graph reference found unresolved parent'
            node, depth = parent, depth+1
        else:
            raise AssertionError('Independent graph reference found a cycle')
    return result


def tuple_counter(records):
    return Counter(tuple(row[field] for field in FIELDS) for row in records)


def report_reference(source, dimension, count, roots, maximum_depth):
    """Independent Counter/EXISTS semantics for otherwise valid typed source fixtures."""
    rows = list(dimension.elements())
    keys = {key for key, _, _, _ in rows if key is not None}
    root_ids = {root for _, _, root, _ in rows if root is not None}
    expected_map = mapping_reference(source)
    pairs = Counter((key, parent) for key, parent, _, _ in rows)
    source_pairs = Counter(source)
    source_valid = (len(source) == count and len(source) > 0 and len(dict(source)) == len(source)
                    and all(key >= 0 and (parent is None or parent >= 0) for key, parent in source)
                    and sum(parent is None for _, parent in source) == roots
                    and max(row[3] for row in expected_map) == maximum_depth)
    actual = [len(rows), 4, 0, len(keys),
              sum(key is None or root is None or depth is None for key, _, root, depth in rows),
              sum(key is not None for key, _, _, _ in rows)-len(keys),
              sum(parent is None for _, parent, _, _ in rows), len(root_ids),
              sum(parent is None and (key != root or depth != 0) for key, parent, root, depth in rows),
              sum(root is None or not any(k == root and p is None for k, p, _, _ in rows) for _, _, root, _ in rows),
              sum(parent is not None and parent not in keys for _, parent, _, _ in rows),
              sum(parent is not None and not any(
                  pkey is not None and pkey == parent and root is not None and proot == root
                  and depth is not None and pdepth is not None and depth == pdepth+1
                  for pkey, _, proot, pdepth in rows) for _, parent, root, depth in rows),
              sum(depth is not None and depth < 0 for _, _, _, depth in rows),
              max((depth for _, _, _, depth in rows if depth is not None), default=None),
              sum((source_pairs-pairs).values()), sum((pairs-source_pairs).values()),
              sum((expected_map-dimension).values()), sum((dimension-expected_map).values()),
              0 if source_valid else 1, len(source)]
    expected = [count, 4, 0, count, 0, 0, roots, roots, 0, 0, 0, 0, 0, maximum_depth, 0, 0, 0, 0, 0, count]
    return [dict(check_order=i, check_name=name, actual=value, expected=target,
                 status='PASS' if value == target else 'FAIL')
            for i, (name, value, target) in enumerate(zip(CHECKS, actual, expected), 1)]


def adjusted(sql, count, roots, depth):
    assert sql.count(COUNT_SQL) == 2
    return sql.replace(COUNT_SQL, f'SELECT {count}::BIGINT AS expected_rows,{roots}::BIGINT AS expected_roots,{depth}::BIGINT AS expected_max_depth')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--duckdb', required=True)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--fixtures-only', action='store_true')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    script_path = 'sql/62_build_retailrocket_category_dimension.sql'
    validator_path = 'validation/preflight_retailrocket_category_dimension.py'
    method_path = 'docs/RETAILROCKET_CATEGORY_DIMENSION_VALIDATION.md'
    output = root/'data/retailrocket_category_dimension_preflight.json'
    assert args.output.resolve() == output.resolve()
    dependencies = [script_path, validator_path, 'validation/preflight_retailrocket_category_hierarchy.py',
                    'validation/preflight_retailrocket_categories_staging.py', 'validation/preflight_retailrocket_categories_import.py',
                    'sql/55_import_retailrocket_categories.sql', 'sql/60_stage_retailrocket_categories.sql',
                    'data/retailrocket_source_audit.json', 'data/retailrocket_categories_import_preflight.json',
                    'data/retailrocket_categories_staging_preflight.json', 'data/retailrocket_category_hierarchy_preflight.json',
                    'data/retailrocket_category_hierarchy_learner_acceptance.json', 'docs/RETAILROCKET_CATEGORY_HIERARCHY_VALIDATION.md']
    hashes = {p: previous.sha256(root/p) for p in dependencies}
    assert hashes['data/retailrocket_category_hierarchy_learner_acceptance.json'] == '6dfa15b9ebe37d78d9280760cd6d09b40c3338a797c43aea5ffc0c495fe5f863'
    assert hashes['docs/RETAILROCKET_CATEGORY_HIERARCHY_VALIDATION.md'] == '93ccf261beed1a04af9353059e8cd2067f2506700f35554e97643035d8b1721f'
    contract = (root/method_path).read_bytes().split(b'\n## Executed results\n', 1)[0]
    assert hashlib.sha256(contract).hexdigest() == CONTRACT_SHA
    sql = (root/script_path).read_text(encoding='utf-8')
    assert 'CREATE TABLE rr_core.dim_category AS' in sql and 'OR REPLACE' not in sql and 'CREATE TABLE IF NOT EXISTS' not in sql
    assert sql.count(CHECK_MARKER) == 1 and sql.count('EXCEPT ALL') == 4
    raw_sql = (root/'sql/55_import_retailrocket_categories.sql').read_text(encoding='utf-8').split('-- CHECKS:', 1)[0]
    stage_sql = (root/'sql/60_stage_retailrocket_categories.sql').read_text(encoding='utf-8').split(staging.CHECK_MARKER, 1)[0]
    assert raw_sql.count('read_csv(') == 1 and 'EXCEPT ALL' not in raw_sql+stage_sql
    for path, evidence, expected_pass in [
        ('sql/55_import_retailrocket_categories.sql', 'data/retailrocket_categories_import_preflight.json', 15),
        ('sql/60_stage_retailrocket_categories.sql', 'data/retailrocket_categories_staging_preflight.json', 18),
    ]:
        prior = json.loads((root/evidence).read_text(encoding='utf-8'))
        assert prior['script_sha256'] == hashes[path] and prior['checks_passed'] == expected_pass
    prior_graph = json.loads((root/'data/retailrocket_category_hierarchy_preflight.json').read_text(encoding='utf-8'))
    prior_values = {r['check_name']:r['actual'] for r in prior_graph['results']}
    assert [prior_values[k] for k in ['category_rows', 'root_nodes', 'max_root_depth']] == [1669, 25, 5]
    audit = json.loads((root/'data/retailrocket_source_audit.json').read_text(encoding='utf-8'))
    assert audit['all_checks_passed'] and audit['files']['category_tree.csv']['sha256'] == previous.SOURCE_SHA
    tmp_root = root/'tmp'
    tmp_root.mkdir(exist_ok=True)
    free_before = shutil.disk_usage(tmp_root).free
    assert free_before >= 2*1024**3
    sizes = []

    def execute(folder, database, query, allow_error=False):
        assert folder.resolve().is_relative_to(tmp_root.resolve())
        assert Path(database).resolve().is_relative_to(folder.resolve())
        spill = (folder/'spill').as_posix().replace("'", "''")
        settings = f"SET threads=2; SET memory_limit='512MB'; SET max_temp_directory_size='1GB'; SET temp_directory='{spill}';\n"
        start = time.perf_counter()
        run = subprocess.run([args.duckdb, str(database), '-bail', '-json'], input=settings+query,
                             text=True, encoding='utf-8', capture_output=True, timeout=60)
        if not allow_error:
            assert run.returncode == 0, 'Private category dimension execution failed; row-bearing diagnostics withheld'
        size = sum(p.stat().st_size for p in folder.rglob('*') if p.is_file())
        assert size <= 2*1024**3
        sizes.append(size)
        return run, round(time.perf_counter()-start, 3)

    cases = []
    with tempfile.TemporaryDirectory(prefix='rr-dimension-fixtures-', dir=tmp_root) as temporary:
        folder = Path(temporary)
        forest = [(1, None), (2, 1), (3, 2), (4, 1), (10, None), (11, 10), (12, 11)]
        for label, rows, count, roots, depth in [
            ('forest', forest, 7, 2, 2), ('singleton', [(1, None)], 1, 1, 0),
            ('maximum_chain', [(1, None)]+[(i, i-1) for i in range(2, 13)], 12, 1, 11),
        ]:
            database = folder/(label+'.duckdb')
            query = adjusted(sql, count, roots, depth)
            run, _ = execute(folder, database, hierarchy.setup(rows)+query+'\n'+PRIVATE_QUERY)
            report, source_rows, dimension_rows = previous.json_outputs(run.stdout)
            expected = mapping_reference(rows)
            assert report == report_reference(rows, expected, count, roots, depth)
            assert tuple_counter(dimension_rows) == expected and previous.table_counter(source_rows) == Counter(rows)
            if label == 'forest':
                assert [r['actual'] for r in report] == [7,4,0,7,0,0,2,2,0,0,0,0,0,2,0,0,0,0,0,7]
            if label == 'singleton':
                assert tuple_counter(dimension_rows) == Counter({(1, None, 1, 0):1})
        cases.append(dict(case='hand_checked_branching_forest_singleton_and_N_minus_1_chain_full_four_field_maps', passed=True))

        database, query = folder/'forest.duckdb', adjusted(sql, 7, 2, 2)
        wrong_root = Counter((key, parent, 10 if key==2 else 1 if key==11 else rid, depth)
                             for key, parent, rid, depth in mapping_reference(forest).elements())
        run, _ = execute(folder, database, 'UPDATE rr_core.dim_category SET root_categoryid=CASE categoryid WHEN 2 THEN 10 WHEN 11 THEN 1 ELSE root_categoryid END;\n'+query.split(CHECK_MARKER,1)[1]+'\n'+PRIVATE_QUERY)
        report, source_rows, dimension_rows = previous.json_outputs(run.stdout)
        assert tuple_counter(dimension_rows) == wrong_root and report == report_reference(forest, wrong_root, 7, 2, 2)
        assert all(report[i]['status']=='PASS' for i in [0,3,6,7,8,9,13,14,15])
        assert report[11]['status']=='FAIL' and report[16]['actual']==report[17]['actual']==2
        wrong_depth = Counter((key, parent, rid, 2 if key==2 else 1 if key==3 else depth)
                              for key, parent, rid, depth in mapping_reference(forest).elements())
        run, _ = execute(folder, database, 'UPDATE rr_core.dim_category SET root_categoryid=CASE WHEN categoryid<10 THEN 1 ELSE 10 END,depth=CASE categoryid WHEN 2 THEN 2 WHEN 3 THEN 1 ELSE depth END;\n'+query.split(CHECK_MARKER,1)[1]+'\n'+PRIVATE_QUERY)
        report, source_rows, dimension_rows = previous.json_outputs(run.stdout)
        assert tuple_counter(dimension_rows)==wrong_depth and report==report_reference(forest,wrong_depth,7,2,2)
        assert all(report[i]['status']=='PASS' for i in [0,3,6,7,8,9,13,14,15])
        assert report[11]['status']=='FAIL' and report[16]['actual']==report[17]['actual']==2
        rejected, _ = execute(folder, database, query, allow_error=True)
        assert rejected.returncode!=0 and 'already exists' in rejected.stderr
        run, _ = execute(folder, database, PRIVATE_QUERY)
        source_rows, dimension_rows = previous.json_outputs(run.stdout)
        assert previous.table_counter(source_rows)==Counter(forest) and tuple_counter(dimension_rows)==wrong_depth
        cases.append(dict(case='keyed_wrong_root_and_depth_detected_despite_unchanged_global_summaries_existing_sentinel_preserved',passed=True))
    assert not folder.exists()

    invalid = [
        ('empty', [], 0, 0, 0),
        ('wrong_count', [(1,None)], 2, 1, 0),
        ('wrong_roots', [(1,None)], 1, 2, 0),
        ('wrong_depth', [(1,None),(2,1)], 2, 1, 0),
        ('duplicate', [(1,None),(1,None)], 2, 2, 0),
        ('missing', [(None,None)], 1, 1, 0),
        ('negative', [(-1,None)], 1, 1, 0),
        ('orphan', [(1,None),(2,9)], 2, 1, 1),
        ('self_cycle', [(1,None),(2,2)], 2, 1, 0),
        ('rootless_cycle', [(1,2),(2,3),(3,1)], 3, 0, 0),
        ('partial_rooted_cycle_with_feeder', [(1,None),(2,1),(10,11),(11,12),(12,10),(13,10)], 6, 1, 1),
    ]
    with tempfile.TemporaryDirectory(prefix='rr-dimension-reject-', dir=tmp_root) as temporary:
        folder = Path(temporary)
        for label, rows, count, roots, depth in invalid:
            database = folder/(label+'.duckdb')
            rejected, _ = execute(folder, database, hierarchy.setup(rows)+adjusted(sql,count,roots,depth),allow_error=True)
            assert rejected.returncode!=0 and 'SQL62 source hierarchy contract failed' in rejected.stderr,label
            run, _ = execute(folder, database, "SELECT COUNT(*) AS target_tables FROM information_schema.tables WHERE table_schema='rr_core' AND table_name='dim_category'; SELECT categoryid,parentid FROM rr_stg.category_tree;")
            target, input_rows = previous.json_outputs(run.stdout)
            assert target==[{'target_tables':0}] and previous.table_counter(input_rows)==Counter(rows),label
        for label, schema, rows, logical in [
            ('wrong_type','categoryid INTEGER,parentid BIGINT',[(1,None)],[(1,None)]),
            ('wrong_order','parentid BIGINT,categoryid BIGINT',[(None,1)],[(1,None)]),
        ]:
            database=folder/(label+'.duckdb')
            rejected,_=execute(folder,database,hierarchy.setup(rows,schema)+adjusted(sql,1,1,0),allow_error=True)
            assert rejected.returncode!=0 and 'SQL62 source hierarchy contract failed' in rejected.stderr
            run,_=execute(folder,database,"SELECT COUNT(*) AS target_tables FROM information_schema.tables WHERE table_schema='rr_core' AND table_name='dim_category'; SELECT categoryid,parentid FROM rr_stg.category_tree;")
            target,input_rows=previous.json_outputs(run.stdout)
            assert target==[{'target_tables':0}] and previous.table_counter(input_rows)==Counter(logical)
        cases.append(dict(case='invalid_empty_rootless_and_partly_rooted_graphs_or_populated_schema_rejected_atomically_input_preserved',
                          subcases=[x[0] for x in invalid]+['wrong_type','wrong_order'],passed=True,expected_rejection=True))
    assert not folder.exists()
    print(json.dumps({'focused_cases_passed':len(cases),'rejection_subcases':len(invalid)+2}),flush=True)
    if args.fixtures_only:
        return

    source = Path(previous.SOURCE)
    before=staging.snapshot(source)
    assert before['sha256']==previous.SOURCE_SHA and before['size_bytes']==14454
    raw_counter=previous.source_counter(source)
    typed_counter=staging.typed_counter(raw_counter)
    source_pairs=list(typed_counter.elements())
    expected_dimension=mapping_reference(source_pairs)
    expected_report=report_reference(source_pairs,expected_dimension,1669,25,5)
    assert len(expected_dimension)==sum(expected_dimension.values())==1669
    assert all(r['status']=='PASS' for r in expected_report)
    historical={str(p.relative_to(root)):previous.sha256(p) for p in (root/'data').glob('*preflight.json') if p.resolve()!=output.resolve()}
    with tempfile.TemporaryDirectory(prefix='rr-dimension-real-',dir=tmp_root) as temporary:
        folder,database=Path(temporary),Path(temporary)/'preflight.duckdb'
        run,elapsed=execute(folder,database,raw_sql+'\n'+stage_sql+'\n'+sql+'\n'+PRIVATE_QUERY)
        report,input_rows,dimension_rows=previous.json_outputs(run.stdout)
        assert report==expected_report and tuple_counter(dimension_rows)==expected_dimension
        assert previous.table_counter(input_rows)==typed_counter
        database_bytes=database.stat().st_size
        input_rows.clear();dimension_rows.clear();expected_dimension.clear();typed_counter.clear();raw_counter.clear();source_pairs.clear()
    assert not folder.exists()
    after=staging.snapshot(source)
    assert before==after
    assert all(previous.sha256(root/p)==h for p,h in hashes.items())
    assert all(previous.sha256(root/p)==h for p,h in historical.items())
    assert (root/method_path).read_bytes().startswith(contract)
    evidence=dict(
        checked_at_utc=datetime.now(timezone.utc).isoformat(),executor='assistant',
        engine=subprocess.check_output([args.duckdb,'-version'],text=True).strip(),
        script=script_path,script_sha256=hashes[script_path],validator=validator_path,validator_sha256=hashes[validator_path],
        code_and_dependency_sha256=hashes,method_contract=method_path,method_contract_prefix_bytes=len(contract),method_contract_prefix_sha256=CONTRACT_SHA,
        source_files=['category_tree.csv'],source_before={'category_tree.csv':before},source_after={'category_tree.csv':after},source_hashes_and_metadata_unchanged=True,
        reconstruction_prefix_sha256={'sql/55_import_retailrocket_categories.sql':hashlib.sha256(raw_sql.encode()).hexdigest(),'sql/60_stage_retailrocket_categories.sql':hashlib.sha256(stage_sql.encode()).hexdigest()},
        reconstruction_basis='Frozen SQL55 import/SQL60 creation prefixes only. SQL61 accepted evidence supplies baseline metadata, not a rerun of its audit.',
        table='rr_core.dim_category',dimension_fields=FIELDS,dimension_types=['BIGINT']*4,real_dimension_script_executions=1,
        report_rows=20,report_columns=5,output_columns=COLUMNS,checks_passed=20,fail_rows=0,results=report,report_sha256=previous.fingerprint(report),
        report_fingerprint_contract='SHA-256 of ordered compact JSON arrays in output-column order, each followed by LF; all count fields are integers.',
        independent_python_parent_chain_full_mapping_matched=True,independent_python_mapping_rows_compared=1669,independent_python_mapping_fields_compared=4,
        independent_python_input_tuples_unchanged=True,independent_python_report_matched=True,
        fixture_case_count=len(cases),fixture_cases=cases,rejection_subcase_count=len(invalid)+2,
        invalid_creation_destination_absence_verified=True,existing_destination_sentinel_preserved=True,keyed_wrong_root_and_depth_detected_with_unchanged_summaries=True,
        preflight_settings=dict(threads=2,memory_limit='512MB',max_temp_directory_size='1GB',timeout_seconds_per_phase=60),
        workspace_free_bytes_before=free_before,workspace_free_bytes_after=shutil.disk_usage(tmp_root).free,
        private_database_bytes_before_cleanup=database_bytes,largest_private_directory_bytes_observed_after_phase=max(sizes),temporary_databases_and_spills_removed=True,
        learner_database_opened=False,other_source_csvs_read=False,historical_comparison_or_analysis_suites_rerun=False,historical_preflight_files_unchanged=len(historical),
        source_records_identifiers_or_node_mappings_exported_or_logged=False,real_comparison_records_held_only_in_process_memory=True,
        elapsed_prefixes_dimension_checks_and_private_queries_seconds=elapsed,
        timing_scope='One CLI execution of reconstruction prefixes, guarded dimension creation, its aggregate check query and private input/dimension projections; excludes hashing/Python oracle/fixtures. Creation and checking each derive the finite walk; no prior full audit suite is rerun.',
        scope='Assistant static category dimension passed; learner SQL62 execution pending. Known reference only; no declared PK/NOT NULL constraints, time validity, full ancestor closure, category meaning, unknown-reference repair or event association.')
    output.write_text(json.dumps(evidence,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps({'report_rows':20,'checks_passed':20,'focused_cases_passed':len(cases),'elapsed_seconds':elapsed,'report_sha256':evidence['report_sha256']}),flush=True)


if __name__=='__main__':
    main()
