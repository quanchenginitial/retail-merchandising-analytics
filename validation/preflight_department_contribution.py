"""Validate department contribution and reconcile it to accepted categories in private databases."""
import argparse
import hashlib
import json
import subprocess
import tempfile
import time
from datetime import datetime,timezone
from decimal import Decimal,ROUND_HALF_UP
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
    sql_path=root/'sql/19_department_contribution.sql'
    sql_bytes=sql_path.read_bytes();sql=sql_bytes.decode('utf-8')
    fixture="""
CREATE SCHEMA core; CREATE SCHEMA mart;
CREATE TABLE core.m5_product AS SELECT * FROM (VALUES
    ('A','FOODS_1','FOODS'),('B','FOODS_2','FOODS'),('C','FOODS_3','FOODS'),
    ('D','HOBBIES_1','HOBBIES'),('E','HOBBIES_2','HOBBIES'),
    ('F','HOUSEHOLD_1','HOUSEHOLD'),('G','HOUSEHOLD_2','HOUSEHOLD')) t(item_id,dept_id,cat_id);
CREATE TABLE core.m5_store AS SELECT * FROM (VALUES ('S1'),('S2')) t(store_id);
CREATE TABLE mart.m5_sales_daily AS
WITH cells AS (
    SELECT p.item_id,s.store_id,DATE '2016-01-26'+CAST(n-1 AS INTEGER) AS "date",
        CAST(CASE WHEN s.store_id='S1' AND n=1 THEN ascii(p.item_id)-64
             WHEN s.store_id='S2' AND n=2 AND p.item_id='A' THEN 2 ELSE 0 END AS INTEGER) AS units,
        CAST(CASE WHEN p.item_id='A' AND s.store_id='S1' AND n=3 THEN NULL
             ELSE ascii(p.item_id)-64 END AS DECIMAL(18,2)) AS sell_price
    FROM core.m5_product p CROSS JOIN core.m5_store s CROSS JOIN range(1,91) t(n)
)
SELECT item_id,store_id,'d_'||CAST(date_diff('day',DATE '2011-01-29',"date")+1 AS VARCHAR) AS d,
    "date",11101::INTEGER AS wm_yr_wk,units,sell_price,sell_price IS NOT NULL AS has_price,
    CAST(CASE WHEN units=0 THEN 0 ELSE units*sell_price END AS DECIMAL(28,2)) AS estimated_sales_value
FROM cells;
"""
    cases=[]
    def parse(output): return json.loads(output,parse_float=Decimal)
    def decimal(value): return None if value is None else Decimal(value)
    def pct(n,d):
        return None if d==0 else (Decimal(n)*100/Decimal(d)).quantize(Decimal('0.0001'),rounding=ROUND_HALF_UP)
    def assert_report(rows,reference):
        assert len(rows)==8 and rows[-1]['department']=='TOTAL',rows
        categories={}
        for e in reference:
            categories[e['category']]=categories.get(e['category'],0)+int(e['value_cents'])
        ordered=sorted(reference,key=lambda e:(-categories[e['category']],e['category'],-int(e['value_cents']),e['department']))
        assert [x['department'] for x in rows[:-1]]==[x['department'] for x in ordered],rows
        total={k:sum(int(x[k]) for x in reference) for k in ['sku_count','units','value_cents']}
        expected=reference+[dict(total,category='TOTAL',department='TOTAL')]
        by_department={x['department']:x for x in rows}
        for e in expected:
            a=by_department[e['department']]
            assert a['category']==e['category'] and int(a['sku_count'])==int(e['sku_count']),(a,e)
            assert int(a['units'])==int(e['units']),(a,e)
            assert Decimal(a['estimated_sales_value_usd'])==Decimal(e['value_cents'])/100,(a,e)
            assert decimal(a['unit_share_pct'])==pct(e['units'],total['units']),(a,e)
            assert decimal(a['value_share_pct'])==pct(e['value_cents'],total['value_cents']),(a,e)
            within=None if e['category']=='TOTAL' else pct(e['value_cents'],categories[e['category']])
            assert decimal(a['within_category_value_share_pct'])==within,(a,e)
            assert a['check_status']=='PASS',a
    manual=[]
    for i,(department,category) in enumerate([('FOODS_1','FOODS'),('FOODS_2','FOODS'),('FOODS_3','FOODS'),
        ('HOBBIES_1','HOBBIES'),('HOBBIES_2','HOBBIES'),('HOUSEHOLD_1','HOUSEHOLD'),('HOUSEHOLD_2','HOUSEHOLD')],1):
        manual.append(dict(category=category,department=department,sku_count=1,
                           units=i+(2 if i==1 else 0),value_cents=100*(i*i+(2 if i==1 else 0))))
    def tiny(name,mutation='',error=False,zero=False,zero_foods=False,extra_zero_sku=False):
        tiny_sql=sql.replace('3049 AS expected_items,10 AS expected_stores',f"{8 if extra_zero_sku else 7} AS expected_items,2 AS expected_stores")
        run=subprocess.run([args.duckdb,':memory:','-bail','-json'],input=fixture+mutation+'\n'+tiny_sql,
                           text=True,encoding='utf-8',capture_output=True)
        if error:
            assert run.returncode!=0 and 'Department report blocked' in run.stderr,(name,run.stderr)
        else:
            assert run.returncode==0,(name,run.stderr)
            expected=[dict(x) for x in manual]
            for x in expected:
                if zero or (zero_foods and x['category']=='FOODS'): x.update(units=0,value_cents=0)
                if extra_zero_sku and x['department']=='FOODS_3': x['sku_count']=2
            assert_report(parse(run.stdout),expected)
        cases.append({'case':name,'passed':True,'guard_rejected':error})
    tiny('manual_global_and_within_category_shares_cross_store_skus_missing_price_zero')
    tiny('entirely_zero_sku_is_retained',"""INSERT INTO core.m5_product VALUES ('H','FOODS_3','FOODS');
INSERT INTO mart.m5_sales_daily SELECT 'H',store_id,d,date,wm_yr_wk,0,sell_price,has_price,0
FROM mart.m5_sales_daily WHERE item_id='C';""",extra_zero_sku=True)
    tiny('inclusive_window_excludes_adjacent_days',"""INSERT INTO mart.m5_sales_daily VALUES
('A','S1','d_1823',DATE '2016-01-25',11101,99999,1,true,99999),
('A','S1','d_1914',DATE '2016-04-25',11101,99999,1,true,99999);""")
    tiny('all_zero_denominators_and_total_within_share_null',"UPDATE mart.m5_sales_daily SET units=0,estimated_sales_value=0;",zero=True)
    tiny('one_zero_category_within_share_null',"UPDATE mart.m5_sales_daily SET units=0,estimated_sales_value=0 WHERE item_id IN ('A','B','C');",zero_foods=True)
    for name,mutation in [
        ('wrong_department_category',"UPDATE core.m5_product SET cat_id='HOBBIES' WHERE item_id='A';"),
        ('unknown_department',"UPDATE core.m5_product SET dept_id='FOODS_4' WHERE item_id='A';"),
        ('null_department',"UPDATE core.m5_product SET dept_id=NULL WHERE item_id='A';"),
        ('missing_department_valid_codes',"UPDATE core.m5_product SET dept_id='FOODS_2' WHERE item_id='A';"),
        ('duplicate_product',"INSERT INTO core.m5_product SELECT * FROM core.m5_product WHERE item_id='A';"),
        ('orphan_item',"UPDATE mart.m5_sales_daily SET item_id='X' WHERE item_id='A';"),
        ('same_count_duplicate_and_missing_day',"UPDATE mart.m5_sales_daily SET date=DATE '2016-02-02',d='d_1831' WHERE item_id='A' AND store_id='S1' AND date=DATE '2016-02-01';"),
        ('positive_units_without_price',"UPDATE mart.m5_sales_daily SET sell_price=NULL,has_price=false WHERE item_id='A' AND units>0;"),
        ('wrong_value',"UPDATE mart.m5_sales_daily SET estimated_sales_value=1 WHERE item_id='A' AND date=DATE '2016-02-01';"),
    ]: tiny(name,mutation,error=True)
    print(json.dumps({'fixture_cases_passed':len(cases)}),flush=True)
    if args.fixtures_only: return
    sources=[Path('D:/database/m5-forecasting-accuracy')/name for name in
             ['sales_train_evaluation.csv','calendar.csv','sell_prices.csv']]
    registry=json.loads((root/'data/m5_source_audit.json').read_text(encoding='utf-8'))
    hashes={p.name:sha256(p) for p in sources}
    assert all(hashes[p.name]==registry['files'][p.name]['sha256'] for p in sources)
    pieces=[]
    prerequisite_hashes={}
    for name,marker in [('02_import_calendar.sql','-- On a repeat visit'),
                        ('04_import_sales.sql','-- BASIC CHECKS:'),('06_import_prices.sql','-- BASIC CHECKS:'),
                        ('08_stage_calendar.sql','-- VALIDATION:'),('09_stage_prices.sql','-- VALIDATION:'),
                        ('10_stage_sales_daily.sql','-- VALIDATION:'),('12_build_product_dimension.sql','-- VALIDATION:'),
                        ('13_build_store_dimension.sql','-- VALIDATION:'),('14_build_calendar_dimension.sql','-- VALIDATION:'),
                        ('17_build_sales_fact.sql','-- VALIDATION:')]:
        path=root/'sql'/name
        prerequisite_hashes['sql/'+name]=sha256(path)
        pieces.append(path.read_text(encoding='utf-8').split(marker)[0])
    setup='\n'.join(pieces)
    # Independent aggregation: staging sales/calendar/prices and raw product mappings,
    # not the fact's stored dates, amounts, flags or category rollup. Sum integer cents.
    reference_sql="""
WITH products AS (SELECT DISTINCT item_id,dept_id,cat_id FROM raw.m5_sales_wide), source_rows AS (
    SELECT p.cat_id AS category,p.dept_id AS department,s.item_id,s.units,pr.wm_yr_wk AS price_week,
        CASE WHEN s.units=0 THEN 0::HUGEINT
             ELSE s.units::HUGEINT*CAST(pr.sell_price*100 AS BIGINT) END AS value_cents
    FROM stg.m5_sales_daily s
    JOIN stg.m5_calendar c ON s.d=c.d
    JOIN products p ON s.item_id=p.item_id
    LEFT JOIN stg.m5_prices pr ON s.item_id=pr.item_id AND s.store_id=pr.store_id AND c.wm_yr_wk=pr.wm_yr_wk
    WHERE c.date BETWEEN DATE '2016-01-26' AND DATE '2016-04-24'
)
SELECT category,department,COUNT(DISTINCT item_id) AS sku_count,COUNT(*) AS daily_rows,
    SUM(units)::VARCHAR AS units,SUM(value_cents)::VARCHAR AS value_cents,
    COUNT(*) FILTER (WHERE price_week IS NOT NULL) AS priced_daily_rows,
    COUNT(*) FILTER (WHERE units>0 AND price_week IS NULL) AS missing_price_positive_rows
FROM source_rows GROUP BY category,department ORDER BY category,department;
"""
    tmp_root=root/'tmp';tmp_root.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='department-contribution-',dir=tmp_root) as workspace:
        assert Path(workspace).resolve().is_relative_to(tmp_root.resolve())
        database=Path(workspace)/'preflight.duckdb'
        assert database.resolve().is_relative_to(Path(workspace).resolve())
        spill=(Path(workspace)/'spill').as_posix().replace("'","''")
        settings=f"SET threads=2; SET memory_limit='2GB'; SET temp_directory='{spill}';\n"
        def execute(script):
            started=time.perf_counter()
            run=subprocess.run([args.duckdb,str(database),'-bail','-json'],input=settings+script,
                               text=True,encoding='utf-8',capture_output=True)
            assert run.returncode==0,run.stderr
            return run,round(time.perf_counter()-started,3)
        _,setup_seconds=execute(setup)
        print(json.dumps({'setup_seconds':setup_seconds}),flush=True)
        run,report_seconds=execute(sql);results=parse(run.stdout)
        run,reference_seconds=execute(reference_sql);reference=parse(run.stdout)
        assert sum(x['daily_rows'] for x in reference)==2744100
        assert all(x['missing_price_positive_rows']==0 for x in reference),reference
        assert_report(results,reference)
        # Aggregate independently reconstructed departments to the accepted SQL18 categories.
        accepted_path=root/'data/category_contribution_learner_acceptance.json'
        accepted_bytes=accepted_path.read_bytes()
        accepted=json.loads(accepted_bytes.decode('utf-8'))
        category_rollup={}
        for x in reference:
            c=category_rollup.setdefault(x['category'],dict(sku_count=0,units=0,value_cents=0))
            for k in c: c[k]+=int(x[k])
        accepted_categories={x['category']:x for x in accepted['results'] if x['category']!='TOTAL'}
        assert set(category_rollup)==set(accepted_categories)
        for cat,totals in category_rollup.items():
            expected=accepted_categories[cat]
            assert totals['sku_count']==int(expected['sku_count'])
            assert totals['units']==int(expected['units'])
            assert Decimal(totals['value_cents'])/100==Decimal(expected['estimated_sales_value_usd'])
        total=next(x for x in accepted['results'] if x['category']=='TOTAL')
        assert int(results[-1]['sku_count'])==int(total['sku_count'])
        assert int(results[-1]['units'])==int(total['units'])
        assert Decimal(results[-1]['estimated_sales_value_usd'])==Decimal(total['estimated_sales_value_usd'])
        database_bytes=database.stat().st_size
    assert not Path(workspace).exists()
    assert all(sha256(p)==hashes[p.name] for p in sources)
    report={
        'checked_at_utc':datetime.now(timezone.utc).isoformat(),'executor':'assistant',
        'engine':subprocess.check_output([args.duckdb,'-version'],text=True).strip(),
        'baseline_database':'Private temporary on-disk DuckDB under repository tmp; removed after verification.',
        'temporary_baseline_removed':True,'temporary_database_bytes_after_close':database_bytes,
        'settings':{'threads':2,'memory_limit':'2GB'},
        'script':'sql/19_department_contribution.sql','script_sha256':hashlib.sha256(sql_bytes).hexdigest(),
        'prerequisite_script_sha256':prerequisite_hashes,'source_sha256':hashes,'source_hashes_unchanged':True,
        'analysis_window':{'start_date':'2016-01-26','end_date':'2016-04-24','inclusive_days':90,
                           'daily_rows':2744100,'scope':'All 3049 source products, 7 departments, 3 categories and 10 stores, including zero sales.'},
        'setup_seconds':setup_seconds,'department_query_seconds':report_seconds,'independent_reference_seconds':reference_seconds,
        'result_rows':len(results),'independent_reference_matched':True,'accepted_category_totals_matched':True,
        'accepted_category_evidence':'data/category_contribution_learner_acceptance.json',
        'accepted_category_evidence_sha256':hashlib.sha256(accepted_bytes).hexdigest(),'results':results,
        'independent_reference_results':reference,'fixture_cases_passed':len(cases),'fixture_cases':cases,
        'scope':'Assistant preflight only; learner department report pending. Independent source-department totals use staging values and integer cents, and roll up exactly to learner-accepted SQL18 category totals. Final 28-day forecast holdout excluded. Descriptive department contribution, not ABC classification, forecast evaluation, causality, profit or an availability estimate.'
    }
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2,default=str)+'\n',encoding='utf-8')
    print(json.dumps({'rows':len(results),'fixture_cases':len(cases),'query_seconds':report_seconds,
                      'independent_reference_matched':True,'results':results},default=str),flush=True)


if __name__=='__main__':
    main()
