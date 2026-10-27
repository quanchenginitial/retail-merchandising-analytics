"""Audit full daily price coverage in private databases; never opens the learner DB."""
import argparse
import hashlib
import json
import subprocess
import tempfile
import time
from datetime import datetime,timezone
from pathlib import Path


def sha256(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--duckdb',required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    sql_path=root/'sql/16_audit_price_coverage.sql'
    sql=sql_path.read_text(encoding='utf-8')
    fixture="""
CREATE SCHEMA stg; CREATE SCHEMA core;
CREATE TABLE stg.m5_sales_daily AS SELECT * FROM
    (VALUES ('A','S1','d_1',0),('A','S1','d_8',2),('A','S1','d_9',3),
            ('A','S2','d_1',0),('A','S2','d_8',0),('A','S2','d_9',0)) AS t(item_id,store_id,d,units);
CREATE TABLE core.m5_calendar AS SELECT * FROM
    (VALUES ('d_1',11101),('d_8',11102),('d_9',11102)) AS t(d,wm_yr_wk);
CREATE TABLE stg.m5_prices(store_id VARCHAR,item_id VARCHAR,wm_yr_wk INTEGER,sell_price DECIMAL(18,2));
INSERT INTO stg.m5_prices VALUES ('S1','A',11102,2.50),('S2','A',11101,3.00),('S1','B',11103,4.00);
"""
    cases=[]
    def tiny(name,mutation='',expected=None,gate_status='PASS',error=None,units=5,zero_rows=4,incomplete=False):
        # Only accepted input controls change to match the defined synthetic fixture.
        fixture_sql=sql
        for old,new in [("'6841121'","'3'"),("'59181090'","'6'"),
                        ("'66927173'",f"'{units}'"),("'40241819'",f"'{zero_rows}'")]:
            fixture_sql=fixture_sql.replace(old,new)
        result=subprocess.run([args.duckdb,':memory:','-bail','-json'],input=fixture+mutation+'\n'+fixture_sql,
                              text=True,encoding='utf-8',capture_output=True)
        if error:
            assert result.returncode!=0 and error in result.stderr,(name,result.stderr)
            cases.append({'case':name,'passed':True,'guard_rejected':True})
            return
        assert result.returncode==0,(name,result.stderr)
        rows=json.loads(result.stdout)
        actual={r['check_name']:r['actual'] for r in rows}
        assert all(actual[k]==(None if v is None else str(v)) for k,v in expected.items()),(name,actual)
        if incomplete:
            assert any(r['status']=='FAIL' for r in rows if r['check_order']<=12),rows
            assert all(r['status']=='INCOMPLETE' for r in rows if r['check_order']>=13),rows
        else:
            assert all(r['status']=='PASS' for r in rows if r['check_order']<=12),rows
            assert all(r['status']==gate_status for r in rows if r['check_order'] in (13,14)),rows
            assert all(r['status']==('N/A' if r['actual'] is None else 'INFO') for r in rows if r['check_order']>=15),rows
        cases.append({'case':name,'passed':True,'checked_actuals':{k:actual[k] for k in expected},
                      'coverage_status':'INCOMPLETE' if incomplete else gate_status})
    tiny('same_week_shared_price_and_zero_sales_gaps',expected={
        'joined_rows':6,'joined_units':5,'priced_daily_rows':3,'missing_price_daily_rows':3,
        'missing_price_zero_rows':3,'missing_price_positive_rows':0,'daily_row_coverage_pct':'50.0000',
        'positive_row_coverage_pct':'100.0000','units_coverage_pct':'100.0000'})
    tiny('positive_sales_without_price',"UPDATE stg.m5_sales_daily SET units=1 WHERE store_id='S2' AND d='d_8';",
         {'missing_price_positive_rows':1,'missing_price_units':1,'missing_price_zero_rows':2,
          'positive_row_coverage_pct':'66.6667','units_coverage_pct':'83.3333'},gate_status='FAIL',units=6,zero_rows=3)
    tiny('another_store_price_cannot_be_borrowed',"UPDATE stg.m5_prices SET store_id='S3' WHERE store_id='S1' AND item_id='A';",
         {'priced_daily_rows':1,'missing_price_positive_rows':2,'missing_price_units':5},gate_status='FAIL')
    tiny('adjacent_week_price_cannot_fill_gap',"UPDATE stg.m5_prices SET wm_yr_wk=11103 WHERE store_id='S1' AND item_id='A';",
         {'priced_daily_rows':1,'missing_price_positive_rows':2,'missing_price_units':5},gate_status='FAIL')
    for name,mutation,error in [
        ('duplicate_unused_price_key',"INSERT INTO stg.m5_prices SELECT * FROM stg.m5_prices WHERE item_id='B';",'Price table'),
        ('null_price',"UPDATE stg.m5_prices SET sell_price=NULL WHERE item_id='B';",'Price table'),
        ('zero_price',"UPDATE stg.m5_prices SET sell_price=0 WHERE item_id='B';",'Price table'),
        ('negative_price',"UPDATE stg.m5_prices SET sell_price=-1 WHERE item_id='B';",'Price table'),
        ('nonfinite_price',"ALTER TABLE stg.m5_prices ALTER sell_price TYPE DOUBLE; UPDATE stg.m5_prices SET sell_price=CAST('NaN' AS DOUBLE) WHERE item_id='B';",'Price table'),
        ('empty_price_key',"UPDATE stg.m5_prices SET store_id='' WHERE item_id='B';",'Price table'),
        ('null_price_week',"UPDATE stg.m5_prices SET wm_yr_wk=NULL WHERE item_id='B';",'Price table'),
        ('duplicate_calendar_day',"INSERT INTO core.m5_calendar SELECT * FROM core.m5_calendar WHERE d='d_1';",'Calendar has'),
    ]:
        tiny(name,mutation,error=error)
    tiny('missing_calendar_is_not_valid_price_coverage',"DELETE FROM core.m5_calendar WHERE d='d_8';",
         {'missing_calendar_rows':2,'joined_rows':6,'joined_units':5},incomplete=True)
    tiny('null_sales_units_invalidates_coverage',"UPDATE stg.m5_sales_daily SET units=NULL WHERE store_id='S1' AND d='d_1';",
         {'invalid_sales_rows':1,'joined_units':5},zero_rows=3,incomplete=True)
    tiny('all_zero_sales_rates_are_not_applicable',"UPDATE stg.m5_sales_daily SET units=0;",
         {'positive_sales_rows':0,'priced_units':0,'daily_row_coverage_pct':'50.0000',
          'positive_row_coverage_pct':None,'units_coverage_pct':None},units=0,zero_rows=6)
    print(json.dumps({'fixture_cases_passed':len(cases)}),flush=True)

    sources=[Path('D:/database/m5-forecasting-accuracy')/name for name in
             ['sales_train_evaluation.csv','calendar.csv','sell_prices.csv']]
    registry=json.loads((root/'data/m5_source_audit.json').read_text(encoding='utf-8'))
    hashes={p.name:sha256(p) for p in sources}
    assert all(hashes[p.name]==registry['files'][p.name]['sha256'] for p in sources)
    pieces=[]
    for name,marker in [('02_import_calendar.sql','-- On a repeat visit'),
                        ('04_import_sales.sql','-- BASIC CHECKS:'),
                        ('06_import_prices.sql','-- BASIC CHECKS:'),
                        ('08_stage_calendar.sql','-- VALIDATION:'),
                        ('09_stage_prices.sql','-- VALIDATION:'),
                        ('10_stage_sales_daily.sql','-- VALIDATION:'),
                        ('14_build_calendar_dimension.sql','-- VALIDATION:')]:
        pieces.append((root/'sql'/name).read_text(encoding='utf-8').split(marker)[0])
    setup='\n'.join(pieces)
    tmp_root=root/'tmp'
    tmp_root.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='price-coverage-',dir=tmp_root) as workspace:
        assert Path(workspace).resolve().is_relative_to(tmp_root.resolve())
        database=Path(workspace)/'preflight.duckdb'
        assert database.resolve().is_relative_to(Path(workspace).resolve())
        spill=(Path(workspace)/'spill').as_posix().replace("'","''")
        settings=f"SET threads=2; SET memory_limit='2GB'; SET temp_directory='{spill}';\n"
        def execute(script):
            started=time.perf_counter()
            result=subprocess.run([args.duckdb,str(database),'-bail','-json'],input=settings+script,
                                  text=True,encoding='utf-8',capture_output=True)
            assert result.returncode==0,result.stderr
            return result,round(time.perf_counter()-started,3)
        _,setup_seconds=execute(setup)
        print(json.dumps({'setup_seconds':setup_seconds}),flush=True)
        run,audit_seconds=execute(sql)
        baseline=json.loads(run.stdout)
        assert len(baseline)==23,baseline
        assert all(r['status']=='PASS' for r in baseline if r['check_order']<=12),baseline
        assert all(r['status']=='INFO' for r in baseline if r['check_order']>=15),baseline
        database_bytes=database.stat().st_size
    assert not Path(workspace).exists()
    assert all(sha256(p)==hashes[p.name] for p in sources)
    gates=[r for r in baseline if r['check_order'] in (13,14)]
    report={
        'checked_at_utc':datetime.now(timezone.utc).isoformat(),'executor':'assistant',
        'engine':subprocess.check_output([args.duckdb,'-version'],text=True).strip(),
        'baseline_database':'Private temporary on-disk DuckDB under repository tmp; removed after verification.',
        'temporary_baseline_removed':True,'temporary_database_bytes_after_close':database_bytes,
        'settings':{'threads':2,'memory_limit':'2GB'},
        'script':'sql/16_audit_price_coverage.sql','script_sha256':sha256(sql_path),
        'source_sha256':hashes,'source_hashes_unchanged':True,
        'setup_seconds':setup_seconds,'full_price_coverage_seconds':audit_seconds,
        'mechanical_checks_passed':12,'coverage_gates_passed':sum(r['status']=='PASS' for r in gates),
        'observation_rows':9,'results':baseline,'fixture_cases_passed':len(cases),'fixture_cases':cases,
        'scope':'Assistant-only daily price coverage using exact item/store/source-week keys. Observed missing prices remain missing; no stockout/listing inference or imputation. Positive-sales coverage gates determine eligibility for a complete sales-value proxy, not source-data correctness. Learner execution pending; no financial totals or fact table created.'
    }
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'mechanical_checks_passed':12,'coverage_gates_passed':report['coverage_gates_passed'],
                      'fixture_cases_passed':len(cases),'full_price_coverage_seconds':audit_seconds,
                      'coverage':{r['check_name']:r['actual'] for r in baseline if r['check_order']>=13}}),flush=True)


if __name__=='__main__':
    main()
