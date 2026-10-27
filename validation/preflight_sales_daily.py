"""Preflight the full sales reshape in a private temporary on-disk database.

The large baseline uses its own file under the ignored workspace tmp directory,
removed on exit. Tiny fixtures use :memory:. Never opens the learner database.
"""
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
    sql_path = root / 'sql/10_stage_sales_daily.sql'
    sql = sql_path.read_text(encoding='utf-8')
    source = Path('D:/database/m5-forecasting-accuracy/sales_train_evaluation.csv')
    registry = json.loads((root / 'data/m5_source_audit.json').read_text(encoding='utf-8'))
    source_hash = sha256(source)
    assert source_hash == registry['files'][source.name]['sha256']
    setup = (root / 'sql/04_import_sales.sql').read_text(encoding='utf-8').split('-- BASIC CHECKS:')[0]
    tmp_root = root / 'tmp'
    tmp_root.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='sales-daily-',dir=tmp_root) as workspace:
        assert Path(workspace).resolve().is_relative_to(tmp_root.resolve())
        database = Path(workspace) / 'preflight.duckdb'
        assert database.resolve().is_relative_to(Path(workspace).resolve())
        spill = (Path(workspace) / 'spill').as_posix().replace("'","''")
        settings = f"SET threads=2; SET memory_limit='2GB'; SET temp_directory='{spill}';\n"
        started = time.perf_counter()
        run = subprocess.run([args.duckdb,str(database),'-bail','-json'],
                             input=settings+setup+'\n'+sql, text=True,encoding='utf-8',
                             capture_output=True)
        elapsed = round(time.perf_counter()-started,3)
        assert run.returncode == 0,run.stderr
        baseline = json.loads(run.stdout)
        assert len(baseline)==14 and all(row['status']=='PASS' for row in baseline),baseline
        database_bytes = database.stat().st_size
    assert not Path(workspace).exists(), 'Temporary baseline directory was not removed'
    assert sha256(source)==source_hash
    print(json.dumps({'baseline_checks_passed':14,'baseline_seconds':elapsed,
                      'temporary_database_bytes_after_close':database_bytes}),flush=True)

    # Two complete 1,941-day series keep the bitmap/key checks meaningful.
    days = ','.join(f"'{1 if day==1941 else 0}' AS d_{day}" for day in range(1,1942))
    fixture = "CREATE SCHEMA raw; CREATE TABLE raw.m5_sales_wide AS SELECT item_id,store_id,"+days+" FROM (VALUES ('A','CA_1'),('B','CA_1')) AS p(item_id,store_id);\n"
    def run_tiny(script):
        return subprocess.run([args.duckdb,':memory:','-bail','-json'],input=script,
                              text=True,encoding='utf-8',capture_output=True)
    good=run_tiny(fixture+sql)
    assert good.returncode==0,good.stderr
    actual={row['check_name']:row['actual'] for row in json.loads(good.stdout)}
    expected={'staging_rows':'3882','schema_mismatch_count':'0','missing_core_rows':'0',
              'zero_sales_rows':'3880','total_units':'2','max_daily_units':'1','series_count':'2',
              'series_row_count_errors':'0','series_day_coverage_errors':'0',
              'invalid_day_rows':'0','series_set_difference_rows':'0'}
    assert all(actual[k]==value for k,value in expected.items()),actual
    cases=[{'case':'two_complete_series_preserve_zeros','passed':True,'checked_actuals':expected}]
    for name,value in [('missing_sales','NULL'),('fractional_sales',"'1.5'"),
                       ('negative_sales',"'-1'"),('integer_overflow',"'2147483648'")]:
        failed=run_tiny(fixture+f"UPDATE raw.m5_sales_wide SET d_1={value} WHERE item_id='A';\n"+sql)
        assert failed.returncode!=0 and 'Raw daily sales must be nonnegative integers' in failed.stderr,(name,failed.stderr)
        cases.append({'case':name,'passed':True,'conversion_rejected':True})
    create_sql,validate_sql=sql.split('-- VALIDATION:',1)
    validate_sql=validate_sql.split('\n',1)[1]
    mutations=[
        ('duplicate_and_missing_day_same_row_count',"UPDATE stg.m5_sales_daily SET d='d_1' WHERE item_id='A' AND d='d_2';",
         {'staging_rows':'3882','series_row_count_errors':'0','series_day_coverage_errors':'1','invalid_day_rows':'0'}),
        ('out_of_range_day',"UPDATE stg.m5_sales_daily SET d='d_2000' WHERE item_id='A' AND d='d_1';",
         {'series_day_coverage_errors':'1','invalid_day_rows':'1'}),
        ('same_total_shift_is_outside_this_check_scope',"UPDATE stg.m5_sales_daily SET units=CASE WHEN d='d_1' THEN 1 ELSE 0 END WHERE item_id='A' AND d IN ('d_1','d_1941');",
         {'staging_rows':'3882','zero_sales_rows':'3880','total_units':'2','max_daily_units':'1','series_row_count_errors':'0','series_day_coverage_errors':'0','series_set_difference_rows':'0'}),
    ]
    for name,mutation,expected in mutations:
        run=run_tiny(fixture+create_sql+mutation+'\n'+validate_sql)
        assert run.returncode==0,run.stderr
        actual={row['check_name']:row['actual'] for row in json.loads(run.stdout)}
        assert all(actual[k]==value for k,value in expected.items()),(name,actual)
        cases.append({'case':name,'passed':True,'checked_actuals':{k:actual[k] for k in expected}})
    report={
        'checked_at_utc':datetime.now(timezone.utc).isoformat(),'executor':'assistant',
        'engine':subprocess.check_output([args.duckdb,'-version'],text=True).strip(),
        'baseline_database':'Private temporary on-disk DuckDB under repository tmp; removed after verification.',
        'temporary_baseline_removed':True,'temporary_database_bytes_after_close':database_bytes,
        'settings':{'threads':2,'memory_limit':'2GB'},
        'script':'sql/10_stage_sales_daily.sql','script_sha256':sha256(sql_path),
        'source_file':source.name,'source_sha256':source_hash,'source_hash_unchanged':True,
        'baseline_setup_reshape_and_checks_seconds':elapsed,'checks_passed':14,'results':baseline,
        'fixture_cases_passed':len(cases),'fixture_cases':cases,
        'scope':'Assistant-only reshape, schema, key completeness and aggregate controls. Full per-cell value reconciliation and learner execution remain pending. No calendar/price join or sales-value calculation.',
    }
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'checks_passed':14,'fixture_cases_passed':len(cases)}))


if __name__=='__main__':
    main()
