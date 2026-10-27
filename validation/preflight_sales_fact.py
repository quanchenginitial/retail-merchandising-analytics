"""Build and verify the daily sales fact in private databases; never opens the learner DB."""
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
    parser.add_argument('--fixtures-only',action='store_true')
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    sql_path=root/'sql/17_build_sales_fact.sql'
    sql_bytes=sql_path.read_bytes()
    script_digest=hashlib.sha256(sql_bytes).hexdigest()
    sql=sql_bytes.decode('utf-8')
    build,audit=sql.split('-- VALIDATION:',1)
    audit='-- VALIDATION:'+audit
    fixture="""
CREATE SCHEMA stg; CREATE SCHEMA core;
CREATE TABLE stg.m5_sales_daily AS
SELECT 'A'::VARCHAR AS item_id,store_id,'d_'||n AS d,
    CAST(CASE WHEN store_id='S1' AND n=8 THEN 2 WHEN store_id='S1' AND n=9 THEN 3 ELSE 0 END AS INTEGER) AS units
FROM range(1,1942) t(n) CROSS JOIN (VALUES ('S1'),('S2')) s(store_id);
CREATE TABLE core.m5_calendar AS SELECT 'd_'||n AS d,
    CAST(11101+floor((n-1)/7) AS INTEGER) AS wm_yr_wk,
    DATE '2011-01-29'+CAST(n-1 AS INTEGER) AS "date",CAST(n AS INTEGER) AS day_number
FROM range(1,1970) t(n);
CREATE TABLE core.m5_product AS SELECT 'A'::VARCHAR AS item_id;
CREATE TABLE core.m5_store AS SELECT * FROM (VALUES ('S1'),('S2')) t(store_id);
CREATE TABLE stg.m5_prices(store_id VARCHAR,item_id VARCHAR,wm_yr_wk INTEGER,sell_price DECIMAL(18,2));
INSERT INTO stg.m5_prices VALUES ('S1','A',11102,2.50),('S2','A',11101,3.00),('S1','B',11103,4.00);
"""
    fixture_audit=audit
    for old,new in [("'59181090'","'3882'"),("'66927173'","'5'"),("'40241819'","'3880'"),
                    ("'46881677'","'14'"),("'12299413'","'3868'"),("'30490'","'2'")]:
        fixture_audit=fixture_audit.replace(old,new)
    cases=[]
    def tiny(name,before='',after='',failures=None,error=None,query=None,expected=None):
        script=fixture+before+'\n'+build+'\n'+after+'\n'+(query or fixture_audit)
        run=subprocess.run([args.duckdb,':memory:','-bail','-json'],input=script,
                           text=True,encoding='utf-8',capture_output=True)
        if error:
            assert run.returncode!=0 and error in run.stderr,(name,run.stderr)
            cases.append({'case':name,'passed':True,'guard_rejected':True})
            return
        assert run.returncode==0,(name,run.stderr)
        rows=json.loads(run.stdout)
        if query:
            assert rows==expected,(name,rows,expected)
        else:
            actual={r['check_name']:r for r in rows}
            if failures:
                assert all(actual[k]['status']=='FAIL' for k in failures),(name,rows)
                assert rows[-1]['status']=='INCOMPLETE',(name,rows)
            else:
                assert all(r['status']=='PASS' for r in rows[:-1]),(name,rows)
                assert rows[-1]['status']=='INFO' and rows[-1]['actual']=='12.50',(name,rows)
        cases.append({'case':name,'passed':True,'expected_failures':failures or [],
                      'checked_values':expected if query else None})
    tiny('complete_series_and_missing_price_zero_policy')
    tiny('missing_price_is_not_imputed',query="""SELECT sell_price,has_price,estimated_sales_value::VARCHAR AS value
        FROM mart.m5_sales_daily WHERE store_id='S1' AND d='d_1';""",
        expected=[{'sell_price':None,'has_price':False,'value':'0.00'}])
    tiny('known_price_zero_units',query="""SELECT sell_price::VARCHAR AS price,has_price,estimated_sales_value::VARCHAR AS value
        FROM mart.m5_sales_daily WHERE store_id='S2' AND d='d_1';""",
        expected=[{'price':'3.00','has_price':True,'value':'0.00'}])
    for name,before,error in [
        ('positive_sales_unpriced',"UPDATE stg.m5_sales_daily SET units=1 WHERE store_id='S1' AND d='d_1';",'Positive sales require'),
        ('another_store_price',"UPDATE stg.m5_prices SET store_id='S3' WHERE item_id='A' AND store_id='S1';",'Positive sales require'),
        ('duplicate_unused_price_key',"INSERT INTO stg.m5_prices SELECT * FROM stg.m5_prices WHERE item_id='B';",'Price table requires'),
        ('null_price',"UPDATE stg.m5_prices SET sell_price=NULL WHERE item_id='B';",'Price table requires'),
        ('nonpositive_price',"UPDATE stg.m5_prices SET sell_price=0 WHERE item_id='B';",'Price table requires'),
        ('wrong_price_type',"ALTER TABLE stg.m5_prices ALTER sell_price TYPE DOUBLE;",'Price table requires'),
        ('missing_product',"DELETE FROM core.m5_product;",'Sales require'),
        ('missing_store',"DELETE FROM core.m5_store WHERE store_id='S2';",'Sales require'),
        ('duplicate_store',"INSERT INTO core.m5_store VALUES ('S2');",'Sales require'),
        ('missing_calendar',"DELETE FROM core.m5_calendar WHERE d='d_1';",'Sales require'),
        ('duplicate_future_calendar',"INSERT INTO core.m5_calendar SELECT * FROM core.m5_calendar WHERE d='d_1969';",'Calendar requires'),
        ('null_units',"UPDATE stg.m5_sales_daily SET units=NULL WHERE store_id='S1' AND d='d_1';",'Sales require'),
        ('negative_units',"UPDATE stg.m5_sales_daily SET units=-1 WHERE store_id='S1' AND d='d_1';",'Sales require'),
    ]:
        tiny(name,before=before,error=error)
    for name,after,failures in [
        ('price_tampered',"UPDATE mart.m5_sales_daily SET sell_price=7 WHERE store_id='S1' AND d='d_8';",['price_field_mismatches']),
        ('coverage_flag_tampered',"UPDATE mart.m5_sales_daily SET has_price=true WHERE store_id='S1' AND d='d_1';",['coverage_flag_mismatches']),
        ('null_amount',"UPDATE mart.m5_sales_daily SET estimated_sales_value=NULL WHERE store_id='S1' AND d='d_1';",['missing_core_rows','amount_mismatches']),
        ('same_total_daily_shift',"UPDATE mart.m5_sales_daily SET units=CASE d WHEN 'd_8' THEN 3 ELSE 2 END, estimated_sales_value=CASE d WHEN 'd_8' THEN 7.5 ELSE 5 END WHERE store_id='S1' AND d IN ('d_8','d_9');",['units_mismatch_series']),
        ('duplicate_and_missing_zero_day',"UPDATE mart.m5_sales_daily SET d='d_2',date=DATE '2011-01-30' WHERE store_id='S1' AND d='d_1';",['fact_key_coverage_errors']),
        ('self_consistent_wrong_week_price',"UPDATE mart.m5_sales_daily SET wm_yr_wk=11101,sell_price=NULL,has_price=false,estimated_sales_value=0 WHERE store_id='S1' AND d='d_10';",['calendar_field_mismatches','price_field_mismatches','coverage_flag_mismatches']),
        ('source_key_changed_after_build',"UPDATE stg.m5_sales_daily SET d='d_2' WHERE store_id='S1' AND d='d_1';",['source_key_coverage_errors']),
    ]:
        tiny(name,after=after,failures=failures)
    tiny('exact_decimal_cents',before="UPDATE stg.m5_prices SET sell_price=0.10 WHERE store_id='S1' AND item_id='A';",
         query="SELECT estimated_sales_value::VARCHAR AS value FROM mart.m5_sales_daily WHERE store_id='S1' AND d='d_9';",
         expected=[{'value':'0.30'}])
    tiny('declared_numeric_domain_maximum',before="UPDATE stg.m5_prices SET sell_price=9999999999999999.99 WHERE store_id='S1' AND item_id='A'; UPDATE stg.m5_sales_daily SET units=2147483647 WHERE store_id='S1' AND d='d_9';",
         query="SELECT estimated_sales_value::VARCHAR AS value,typeof(estimated_sales_value) AS value_type FROM mart.m5_sales_daily WHERE store_id='S1' AND d='d_9';",
         expected=[{'value':'21474836469999999978525163.53','value_type':'DECIMAL(28,2)'}])
    print(json.dumps({'fixture_cases_passed':len(cases)}),flush=True)
    if args.fixtures_only:
        return

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
                        ('12_build_product_dimension.sql','-- VALIDATION:'),
                        ('13_build_store_dimension.sql','-- VALIDATION:'),
                        ('14_build_calendar_dimension.sql','-- VALIDATION:')]:
        pieces.append((root/'sql'/name).read_text(encoding='utf-8').split(marker)[0])
    setup='\n'.join(pieces)
    tmp_root=root/'tmp'
    tmp_root.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='sales-fact-',dir=tmp_root) as workspace:
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
        run,build_seconds=execute(build)
        print(json.dumps({'fact_build_seconds':build_seconds}),flush=True)
        run,audit_seconds=execute(audit)
        baseline=json.loads(run.stdout)
        assert len(baseline)==21,baseline
        assert all(r['status']=='PASS' for r in baseline if r['check_order']<=20),baseline
        assert baseline[-1]['status']=='INFO',baseline
        database_bytes=database.stat().st_size
    assert not Path(workspace).exists()
    assert all(sha256(p)==hashes[p.name] for p in sources)
    report={
        'checked_at_utc':datetime.now(timezone.utc).isoformat(),'executor':'assistant',
        'engine':subprocess.check_output([args.duckdb,'-version'],text=True).strip(),
        'baseline_database':'Private temporary on-disk DuckDB under repository tmp; removed after verification.',
        'temporary_baseline_removed':True,'temporary_database_bytes_after_close':database_bytes,
        'settings':{'threads':2,'memory_limit':'2GB'},
        'script':'sql/17_build_sales_fact.sql','script_sha256':script_digest,
        'source_sha256':hashes,'source_hashes_unchanged':True,
        'setup_seconds':setup_seconds,'fact_build_seconds':build_seconds,'fact_validation_seconds':audit_seconds,
        'checks_passed':20,'observation_rows':1,'results':baseline,
        'fixture_cases_passed':len(cases),'fixture_cases':cases,
        'scope':'Assistant-only fact build and full per-series daily units reconciliation, independent date/week/price/flag/value validation. Learner execution pending. Zero units imply zero estimated value while missing price remains NULL. Published weekly price times units is a USD proxy, not transaction revenue or profit. No learner database opened.'
    }
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'checks_passed':20,'fixture_cases_passed':len(cases),
                      'fact_build_seconds':build_seconds,'fact_validation_seconds':audit_seconds,
                      'total_estimated_sales_value':baseline[-1]['actual']}),flush=True)


if __name__=='__main__':
    main()
