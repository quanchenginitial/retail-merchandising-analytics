"""Verify read-only per-cell reconciliation without opening the learner database."""
import argparse
import hashlib
import json
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path


def sha256(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--duckdb', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    sql_path = root / 'sql/11_reconcile_sales_daily.sql'
    sql = sql_path.read_text(encoding='utf-8')
    reshape = (root / 'sql/10_stage_sales_daily.sql').read_text(encoding='utf-8').split('-- VALIDATION:')[0]
    days = ','.join(f"'{ {2:2,10:3,1941:1}.get(day,0)}' AS d_{day}" for day in range(1,1942))
    fixture = "CREATE SCHEMA raw; CREATE TABLE raw.m5_sales_wide AS SELECT item_id||store_id AS id,item_id,'DEPT' AS dept_id,'CAT' AS cat_id,store_id,'CA' AS state_id," + days + " FROM (VALUES ('A','CA_1'),('B','CA_1')) AS p(item_id,store_id);\n"
    cases = []

    # Only fixture cardinality controls change; all reconciliation logic is identical.
    fixture_sql = sql.replace("'30490'", "'2'").replace("'59181090'", "'3882'")
    def tiny(name, mutation='', expected=None, rejected=False, value_status='INCOMPLETE'):
        script = fixture + reshape + mutation + '\n' + fixture_sql
        run = subprocess.run([args.duckdb, ':memory:', '-bail', '-json'], input=script,
                             text=True, encoding='utf-8', capture_output=True)
        if rejected:
            assert run.returncode != 0 and 'Raw daily sales must be nonnegative integers' in run.stderr, (name, run.stderr)
            cases.append({'case':name,'passed':True,'raw_value_rejected':True})
            return
        assert run.returncode == 0, (name, run.stderr)
        rows = json.loads(run.stdout)
        actual = {r['check_name']:r['actual'] for r in rows}
        assert all(actual[k] == str(v) for k,v in expected.items()), (name, actual)
        assert all(r['status']==value_status for r in rows if r['check_order'] in (14,15)), rows
        if value_status=='PASS':
            assert all(r['status']=='PASS' for r in rows), rows
        cases.append({'case':name,'passed':True,'checked_actuals':{k:actual[k] for k in expected},'value_check_status':value_status})

    tiny('correct_values_with_reverse_physical_order',
         'CREATE OR REPLACE TABLE stg.m5_sales_daily AS SELECT * FROM stg.m5_sales_daily ORDER BY d DESC;',
         {'compared_cells':3882,'value_mismatch_series':0,'value_mismatch_cells':0,'raw_day_sequence_errors':0},value_status='PASS')
    tiny('same_total_same_zero_count_two_day_shift',
         "UPDATE stg.m5_sales_daily SET units=CASE WHEN d='d_1' THEN 1 ELSE 0 END WHERE item_id='A' AND d IN ('d_1','d_1941');",
         {'compared_cells':3882,'value_mismatch_series':1,'value_mismatch_cells':2,'series_day_coverage_errors':0},value_status='FAIL')
    tiny('duplicate_and_missing_day_with_equal_values',
         "UPDATE stg.m5_sales_daily SET d='d_3' WHERE item_id='A' AND d='d_4';",
         {'series_row_count_errors':0,'series_day_coverage_errors':1,'compared_cells':1941})
    tiny('missing_day',"DELETE FROM stg.m5_sales_daily WHERE item_id='A' AND d='d_1';",
         {'series_row_count_errors':1,'series_day_coverage_errors':1,'compared_cells':1941})
    tiny('noncanonical_day',"UPDATE stg.m5_sales_daily SET d='d_01' WHERE item_id='A' AND d='d_1';",
         {'invalid_day_rows':1,'series_day_coverage_errors':1,'compared_cells':1941})
    tiny('out_of_range_day',"UPDATE stg.m5_sales_daily SET d='d_2000' WHERE item_id='A' AND d='d_1';",
         {'invalid_day_rows':1,'series_day_coverage_errors':1,'compared_cells':1941})
    tiny('null_units',"UPDATE stg.m5_sales_daily SET units=NULL WHERE item_id='A' AND d='d_1';",
         {'missing_core_rows':1,'compared_cells':1941})
    tiny('replaced_series_key',"UPDATE stg.m5_sales_daily SET item_id='C' WHERE item_id='A';",
         {'raw_only_series':1,'staging_only_series':1,'compared_cells':1941})
    tiny('extra_series_beyond_complete_comparable_grid',
         "INSERT INTO stg.m5_sales_daily SELECT 'C',store_id,d,units FROM stg.m5_sales_daily WHERE item_id='A';",
         {'staging_rows':5823,'staging_only_series':1,'compared_cells':3882,'value_mismatch_cells':0})
    tiny('raw_duplicate_key',"INSERT INTO raw.m5_sales_wide SELECT * FROM raw.m5_sales_wide WHERE item_id='A';",
         {'raw_key_error_rows':2,'compared_cells':1941})
    tiny('raw_null_key',"UPDATE raw.m5_sales_wide SET item_id=NULL WHERE item_id='A';",
         {'raw_key_error_rows':1,'raw_only_series':1,'staging_only_series':1,'compared_cells':1941})
    tiny('raw_day_columns_reordered',
         'CREATE OR REPLACE TABLE raw.m5_sales_wide AS SELECT id,item_id,dept_id,cat_id,store_id,state_id,d_2,d_1,* EXCLUDE(id,item_id,dept_id,cat_id,store_id,state_id,d_1,d_2) FROM raw.m5_sales_wide;',
         {'raw_day_columns':1941,'raw_day_sequence_errors':2,'compared_cells':0})
    # Mutate raw after creating a correct long table: this specifically exercises SQL 11.
    for name,value in [('null','NULL'),('fractional',"'1.5'"),('negative',"'-1'"),('overflow',"'2147483648'")]:
        tiny('raw_'+name, f"UPDATE raw.m5_sales_wide SET d_1={value} WHERE item_id='A';", rejected=True)
    print(json.dumps({'fixture_cases_passed':len(cases)}), flush=True)

    source = Path('D:/database/m5-forecasting-accuracy/sales_train_evaluation.csv')
    registry = json.loads((root/'data/m5_source_audit.json').read_text(encoding='utf-8'))
    source_hash = sha256(source)
    assert source_hash == registry['files'][source.name]['sha256']
    setup = (root/'sql/04_import_sales.sql').read_text(encoding='utf-8').split('-- BASIC CHECKS:')[0]
    tmp_root = root/'tmp'
    tmp_root.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='sales-reconcile-',dir=tmp_root) as workspace:
        assert Path(workspace).resolve().is_relative_to(tmp_root.resolve())
        database = Path(workspace)/'preflight.duckdb'
        assert database.resolve().is_relative_to(Path(workspace).resolve())
        spill = (Path(workspace)/'spill').as_posix().replace("'","''")
        settings = f"SET threads=2; SET memory_limit='2GB'; SET temp_directory='{spill}';\n"
        def execute(script):
            started = time.perf_counter()
            run = subprocess.run([args.duckdb,str(database),'-bail','-json'],input=settings+script,
                                 text=True,encoding='utf-8',capture_output=True)
            assert run.returncode==0,run.stderr
            return run,round(time.perf_counter()-started,3)
        _,setup_seconds = execute(setup+'\n'+reshape)
        print(json.dumps({'setup_seconds':setup_seconds}), flush=True)
        run,audit_seconds = execute(sql)
        baseline = json.loads(run.stdout)
        assert len(baseline)==15 and all(r['status']=='PASS' for r in baseline),baseline
        database_bytes = database.stat().st_size
    assert not Path(workspace).exists()
    assert sha256(source)==source_hash
    report = {
        'checked_at_utc':datetime.now(timezone.utc).isoformat(),'executor':'assistant',
        'engine':subprocess.check_output([args.duckdb,'-version'],text=True).strip(),
        'baseline_database':'Private temporary on-disk DuckDB under repository tmp; removed after verification.',
        'temporary_baseline_removed':True,'temporary_database_bytes_after_close':database_bytes,
        'settings':{'threads':2,'memory_limit':'2GB'},
        'script':'sql/11_reconcile_sales_daily.sql','script_sha256':sha256(sql_path),
        'source_file':source.name,'source_sha256':source_hash,'source_hash_unchanged':True,
        'setup_seconds':setup_seconds,'reconciliation_seconds':audit_seconds,
        'checks_passed':15,'results':baseline,'fixture_cases_passed':len(cases),'fixture_cases':cases,
        'scope':'Exact daily values, multiplicity and key coverage reconcile to the current raw wide table. Assistant-only execution; learner reconciliation is pending. No daily price joins or business findings.'
    }
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'checks_passed':15,'reconciliation_seconds':audit_seconds,'fixture_cases_passed':len(cases)}),flush=True)


if __name__=='__main__':
    main()
