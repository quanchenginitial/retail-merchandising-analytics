"""Verify full sales-dimension joins in a private temporary database, never the learner DB."""
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
    sql_path=root/'sql/15_audit_sales_dimension_joins.sql'
    sql=sql_path.read_text(encoding='utf-8')
    fixture="""
CREATE SCHEMA stg; CREATE SCHEMA core;
CREATE TABLE stg.m5_sales_daily AS SELECT * FROM
    (VALUES ('A','S1','d_1',0),('A','S1','d_2',2),('B','S2','d_1',0),('B','S2','d_2',1))
    AS t(item_id,store_id,d,units);
CREATE TABLE core.m5_product AS SELECT * FROM
    (VALUES ('A','D1','C1'),('B','D2','C2')) AS t(item_id,dept_id,cat_id);
CREATE TABLE core.m5_store AS SELECT * FROM
    (VALUES ('S1','CA'),('S2','TX')) AS t(store_id,state_id);
CREATE TABLE core.m5_calendar AS SELECT * FROM
    (VALUES ('d_1',DATE '2011-01-29',11101,1),('d_2',DATE '2011-01-30',11101,2),
            ('d_1942',DATE '2016-05-23',11617,1942)) AS t(d,"date",wm_yr_wk,day_number);
"""
    # Adapt only expected snapshot controls. The observation upper bound stays 1941.
    fixture_sql=sql
    for old,new in [("'3049'","'2'"),("'10'","'2'"),("'1969'","'3'"),
                    ("'59181090'","'4'"),("'66927173'","'3'"),("'40241819'","'2'"),
                    ("'2016-05-22'","'2011-01-30'")]:
        fixture_sql=fixture_sql.replace(old,new)
    cases=[]
    def tiny(name,mutation='',expected=None,error=None):
        result=subprocess.run([args.duckdb,':memory:','-bail','-json'],
                              input=fixture+mutation+'\n'+fixture_sql,
                              text=True,encoding='utf-8',capture_output=True)
        if error:
            assert result.returncode!=0 and error in result.stderr,(name,result.stderr)
            cases.append({'case':name,'passed':True,'guard_rejected':True})
            return
        assert result.returncode==0,(name,result.stderr)
        rows=json.loads(result.stdout)
        actual={r['check_name']:r['actual'] for r in rows}
        if expected is None:
            assert all(r['status']=='PASS' for r in rows),rows
        else:
            assert all(actual[k]==str(v) for k,v in expected.items()),(name,actual)
            assert any(r['status']=='FAIL' for r in rows),name
        cases.append({'case':name,'passed':True,'checked_actuals':{k:actual[k] for k in (expected or actual)}})
    tiny('correct_three_joins_preserve_zero_rows')
    tiny('missing_product',"DELETE FROM core.m5_product WHERE item_id='A';",
         {'missing_product_rows':2,'joined_rows':4,'joined_units':3})
    tiny('missing_store',"DELETE FROM core.m5_store WHERE store_id='S1';",
         {'missing_store_rows':2,'joined_rows':4,'joined_units':3})
    tiny('missing_calendar_key_for_zero_only_rows',"DELETE FROM core.m5_calendar WHERE d='d_1';",
         {'missing_calendar_rows':2,'joined_rows':4,'joined_units':3,'joined_zero_rows':2})
    for name,mutation,error in [
        ('duplicate_product_key',"INSERT INTO core.m5_product SELECT * FROM core.m5_product WHERE item_id='A';",'Product dimension'),
        ('duplicate_store_key',"INSERT INTO core.m5_store SELECT * FROM core.m5_store WHERE store_id='S1';",'Store dimension'),
        ('duplicate_unused_future_calendar_key',"INSERT INTO core.m5_calendar SELECT * FROM core.m5_calendar WHERE d='d_1942';",'Calendar dimension'),
        ('null_product_key',"UPDATE core.m5_product SET item_id=NULL WHERE item_id='A';",'Product dimension'),
        ('missing_product_attribute',"UPDATE core.m5_product SET cat_id=NULL WHERE item_id='A';",'Product dimension'),
        ('missing_store_attribute',"UPDATE core.m5_store SET state_id=' ' WHERE store_id='S1';",'Store dimension'),
        ('missing_calendar_attribute',"UPDATE core.m5_calendar SET wm_yr_wk=NULL WHERE d='d_1';",'Calendar dimension'),
    ]:
        tiny(name,mutation,error=error)
    tiny('sale_uses_post_observation_calendar_day',"UPDATE stg.m5_sales_daily SET d='d_1942' WHERE item_id='A' AND d='d_1';",
         {'invalid_joined_day_rows':1,'missing_calendar_rows':0,'row_count_difference':0,'units_difference':0})
    tiny('null_units_cannot_hide_in_sum',"UPDATE stg.m5_sales_daily SET units=NULL WHERE item_id='A' AND d='d_1';",
         {'source_missing_core_rows':1,'base_units':3,'joined_units':3})
    tiny('negative_units',"UPDATE stg.m5_sales_daily SET units=-1 WHERE item_id='A' AND d='d_1';",
         {'source_negative_units_rows':1,'base_units':2,'joined_units':2})
    tiny('wrong_joined_date',"UPDATE core.m5_calendar SET \"date\"=DATE '2011-01-30' WHERE d='d_1';",
         {'invalid_joined_day_rows':2,'joined_rows':4,'joined_units':3})
    print(json.dumps({'fixture_cases_passed':len(cases)}),flush=True)

    sources=[Path('D:/database/m5-forecasting-accuracy/sales_train_evaluation.csv'),
             Path('D:/database/m5-forecasting-accuracy/calendar.csv')]
    registry=json.loads((root/'data/m5_source_audit.json').read_text(encoding='utf-8'))
    hashes={p.name:sha256(p) for p in sources}
    assert all(hashes[p.name]==registry['files'][p.name]['sha256'] for p in sources)
    pieces=[]
    for name,marker in [('02_import_calendar.sql','-- On a repeat visit'),
                        ('04_import_sales.sql','-- BASIC CHECKS:'),
                        ('08_stage_calendar.sql','-- VALIDATION:'),
                        ('10_stage_sales_daily.sql','-- VALIDATION:'),
                        ('12_build_product_dimension.sql','-- VALIDATION:'),
                        ('13_build_store_dimension.sql','-- VALIDATION:'),
                        ('14_build_calendar_dimension.sql','-- VALIDATION:')]:
        pieces.append((root/'sql'/name).read_text(encoding='utf-8').split(marker)[0])
    setup='\n'.join(pieces)
    tmp_root=root/'tmp'
    tmp_root.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='dimension-joins-',dir=tmp_root) as workspace:
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
        run,join_seconds=execute(sql)
        baseline=json.loads(run.stdout)
        assert len(baseline)==20 and all(r['status']=='PASS' for r in baseline),baseline
        database_bytes=database.stat().st_size
    assert not Path(workspace).exists()
    assert all(sha256(p)==hashes[p.name] for p in sources)
    report={
        'checked_at_utc':datetime.now(timezone.utc).isoformat(),'executor':'assistant',
        'engine':subprocess.check_output([args.duckdb,'-version'],text=True).strip(),
        'baseline_database':'Private temporary on-disk DuckDB under repository tmp; removed after verification.',
        'temporary_baseline_removed':True,'temporary_database_bytes_after_close':database_bytes,
        'settings':{'threads':2,'memory_limit':'2GB'},
        'script':'sql/15_audit_sales_dimension_joins.sql','script_sha256':sha256(sql_path),
        'source_sha256':hashes,'source_hashes_unchanged':True,
        'setup_seconds':setup_seconds,'full_join_audit_seconds':join_seconds,
        'checks_passed':20,'results':baseline,'fixture_cases_passed':len(cases),'fixture_cases':cases,
        'scope':'Assistant-only full LEFT JOIN audit against the three accepted dimensions. Verifies match coverage and preservation of base rows, units, zero rows and store controls. Relies on previously accepted source values/dimension semantics; not a new raw-cell reconciliation. Learner execution pending; no prices, financial values or persisted joined fact table.'
    }
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'checks_passed':20,'fixture_cases_passed':len(cases),'full_join_audit_seconds':join_seconds}),flush=True)


if __name__=='__main__':
    main()
