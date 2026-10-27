"""Verify SKU-unit concentration, exact threshold boundaries and source SKU totals in private databases."""
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
    sql_path=root/'sql/20_product_unit_concentration.sql'
    sql_bytes=sql_path.read_bytes();sql=sql_bytes.decode('utf-8')
    ctes=sql.split('-- REPORT:',1)[0]
    def parse(output): return json.loads(output,parse_float=Decimal)
    def pct(n,d):
        return None if d==0 else str((Decimal(n)*100/Decimal(d)).quantize(Decimal('0.0001'),rounding=ROUND_HALF_UP))
    def expected_report(source):
        positive=sorted([x for x in source if int(x['units'])>0],key=lambda x:(-int(x['units']),x['item_id']))
        zeros=[x for x in source if int(x['units'])==0]
        total=sum(int(x['units']) for x in source)
        prefixes={}
        for target in [80,95]:
            acc=0;chosen=[]
            for x in positive:
                chosen.append(x);acc+=int(x['units'])
                if acc*100>=total*target: break
            prefixes[target]=chosen if total else None
        segments=[('TOP_10',positive[:10]),('TOP_50',positive[:50]),('TOP_100',positive[:100]),
                  ('REACH_80_PCT',prefixes[80]),('REACH_95_PCT',prefixes[95]),
                  ('ALL_POSITIVE',positive),('ZERO_SALES',zeros),('ALL_PRODUCTS',source)]
        return [dict(segment=name,sku_count=None if selected is None else len(selected),
                     sku_share_pct=None if selected is None else pct(len(selected),len(source)),
                     units=None if selected is None else str(sum(int(x['units']) for x in selected)),
                     unit_share_pct=None if selected is None else pct(sum(int(x['units']) for x in selected),total),
                     check_status='N/A' if selected is None else 'PASS') for name,selected in segments]
    def assert_report(actual,reference):
        expected=expected_report(reference)
        assert len(actual)==8
        for a,e in zip(actual,expected):
            assert a['segment']==e['segment'] and a['check_status']==e['check_status'],(a,e)
            for k in ['sku_count','units','sku_share_pct','unit_share_pct']:
                av=None if a[k] is None else Decimal(str(a[k]));ev=None if e[k] is None else Decimal(str(e[k]))
                assert av==ev,(k,a,e)
    def assert_rank(rows,source):
        ordered=sorted([x for x in source if int(x['units'])>0],key=lambda x:(-int(x['units']),x['item_id']))
        assert len(rows)==len(ordered)
        cumulative=0
        for i,(a,e) in enumerate(zip(rows,ordered),1):
            cumulative+=int(e['units'])
            assert a['item_id']==e['item_id'] and int(a['sku_rank'])==i
            assert int(a['units'])==int(e['units']) and int(a['cumulative_units'])==cumulative
    cases=[]
    def fixture(weights):
        values=','.join(f"('P{i:03d}',{int(w)})" for i,w in enumerate(weights,1))
        return f"""
CREATE SCHEMA core; CREATE SCHEMA mart;
CREATE TABLE weights AS SELECT * FROM (VALUES {values}) t(item_id,total_units);
CREATE TABLE core.m5_product AS SELECT item_id,'FOODS_1'::VARCHAR AS dept_id,'FOODS'::VARCHAR AS cat_id FROM weights;
CREATE TABLE core.m5_store AS SELECT * FROM (VALUES ('S1'),('S2')) t(store_id);
CREATE TABLE mart.m5_sales_daily AS
SELECT w.item_id,s.store_id,'d_'||CAST(n+1823 AS VARCHAR) AS d,
    DATE '2016-01-26'+CAST(n-1 AS INTEGER) AS date,
    CAST(CASE WHEN n<>1 THEN 0 WHEN s.store_id='S1' THEN floor(w.total_units/2)
         ELSE w.total_units-floor(w.total_units/2) END AS INTEGER) AS units
FROM weights w CROSS JOIN core.m5_store s CROSS JOIN range(1,91) t(n);
"""
    def tiny(name,weights,mutation='',error=False):
        synthetic=fixture(weights)
        current=sql.replace('3049 AS expected_items,10 AS expected_stores',f'{len(weights)} AS expected_items,2 AS expected_stores')
        run=subprocess.run([args.duckdb,':memory:','-bail','-json'],input=synthetic+mutation+'\n'+current,
                           text=True,encoding='utf-8',capture_output=True)
        if error:
            assert run.returncode!=0 and 'Product concentration blocked' in run.stderr,(name,run.stderr)
        else:
            assert run.returncode==0,(name,run.stderr)
            reference=[dict(item_id=f'P{i:03d}',units=str(w)) for i,w in enumerate(weights,1)]
            assert_report(parse(run.stdout),reference)
            # Inspect the actual production ranking CTE, including tie order and ROWS cumulative sums.
            probe=current.split('-- REPORT:',1)[0]+'SELECT item_id,units,sku_rank,cumulative_units FROM ranked ORDER BY sku_rank;'
            ranked=subprocess.run([args.duckdb,':memory:','-bail','-json'],input=synthetic+mutation+'\n'+probe,
                                  text=True,encoding='utf-8',capture_output=True)
            assert ranked.returncode==0,ranked.stderr
            assert_rank(parse(ranked.stdout) if ranked.stdout.strip() else [],reference)
        cases.append({'case':name,'passed':True,'guard_rejected':error})
    tiny('exact_80_and_95_boundaries_cross_store_zero_sku',[80,15,5,0])
    tiny('crossing_sku_included',[79,16,5,0])
    tiny('one_sku_crosses_both_thresholds',[96,4,0])
    tiny('ties_and_explicit_rowwise_cumulative_units',[40,40,15,5,0])
    tiny('top_10_50_100_are_distinct_prefixes',list(range(1,121))+[0,0])
    tiny('all_zero_thresholds_undefined',[0,0,0])
    tiny('positive_sku_count_below_ten',[2,0,3])
    tiny('excluded_adjacent_dates',[80,15,5,0],"""INSERT INTO mart.m5_sales_daily VALUES
('P001','S1','d_1823',DATE '2016-01-25',99999),('P001','S1','d_1914',DATE '2016-04-25',99999);""")
    for name,mutation in [
        ('duplicate_product_key',"INSERT INTO core.m5_product SELECT * FROM core.m5_product WHERE item_id='P001';"),
        ('orphan_product_key',"UPDATE mart.m5_sales_daily SET item_id='UNKNOWN' WHERE item_id='P001';"),
        ('duplicate_missing_day_same_count',"UPDATE mart.m5_sales_daily SET date=DATE '2016-02-02',d='d_1831' WHERE item_id='P001' AND store_id='S1' AND date=DATE '2016-02-01';"),
        ('negative_units',"UPDATE mart.m5_sales_daily SET units=-1 WHERE item_id='P001' AND date=DATE '2016-02-01';"),
        ('null_units',"UPDATE mart.m5_sales_daily SET units=NULL WHERE item_id='P001' AND date=DATE '2016-02-01';"),
        ('missing_store_mapping',"DELETE FROM core.m5_store WHERE store_id='S2';"),
    ]: tiny(name,[80,15,5,0],mutation,error=True)
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
    # Independent units reference: staging day mapping and raw product hierarchy, no fact aggregates.
    reference_sql="""
WITH products AS (SELECT DISTINCT item_id,dept_id,cat_id FROM raw.m5_sales_wide)
SELECT s.item_id,p.dept_id,p.cat_id,SUM(s.units)::VARCHAR AS units
FROM stg.m5_sales_daily s JOIN stg.m5_calendar c ON s.d=c.d
JOIN products p ON s.item_id=p.item_id
WHERE c.date BETWEEN DATE '2016-01-26' AND DATE '2016-04-24'
GROUP BY s.item_id,p.dept_id,p.cat_id ORDER BY s.item_id;
"""
    tmp_root=root/'tmp';tmp_root.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='product-concentration-',dir=tmp_root) as workspace:
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
        run,sku_comparison_seconds=execute(ctes+'SELECT item_id,dept_id,cat_id,units FROM product_totals ORDER BY item_id;')
        actual_skus=parse(run.stdout)
        canonical=lambda rows:[(x['item_id'],x['dept_id'],x['cat_id'],int(x['units'])) for x in rows]
        assert len(reference)==3049 and canonical(actual_skus)==canonical(reference)
        run,rank_comparison_seconds=execute(ctes+'SELECT item_id,units,sku_rank,cumulative_units FROM ranked ORDER BY sku_rank;')
        assert_rank(parse(run.stdout),reference)
        assert_report(results,reference)
        accepted_path=root/'data/department_contribution_learner_acceptance.json'
        accepted_bytes=accepted_path.read_bytes();accepted=json.loads(accepted_bytes.decode('utf-8'))
        assert accepted['analysis_window']['start_date']=='2016-01-26' and accepted['analysis_window']['end_date']=='2016-04-24'
        departments={}
        for x in reference:
            current=departments.setdefault(x['dept_id'],dict(sku_count=0,units=0))
            current['sku_count']+=1;current['units']+=int(x['units'])
        accepted_departments={x['department']:x for x in accepted['results'] if x['department']!='TOTAL'}
        assert set(departments)==set(accepted_departments)
        for dept,x in departments.items():
            assert x['sku_count']==int(accepted_departments[dept]['sku_count'])
            assert x['units']==int(accepted_departments[dept]['units'])
        total=next(x for x in accepted['results'] if x['department']=='TOTAL')
        assert results[-1]['sku_count']==int(total['sku_count']) and int(results[-1]['units'])==int(total['units'])
        database_bytes=database.stat().st_size
    assert not Path(workspace).exists()
    assert all(sha256(p)==hashes[p.name] for p in sources)
    report={
        'checked_at_utc':datetime.now(timezone.utc).isoformat(),'executor':'assistant',
        'engine':subprocess.check_output([args.duckdb,'-version'],text=True).strip(),
        'baseline_database':'Private temporary on-disk DuckDB under repository tmp; removed after verification.',
        'temporary_baseline_removed':True,'temporary_database_bytes_after_close':database_bytes,
        'settings':{'threads':2,'memory_limit':'2GB'},
        'script':'sql/20_product_unit_concentration.sql','script_sha256':hashlib.sha256(sql_bytes).hexdigest(),
        'prerequisite_script_sha256':prerequisite_hashes,'source_sha256':hashes,'source_hashes_unchanged':True,
        'analysis_window':{'start_date':'2016-01-26','end_date':'2016-04-24','inclusive_days':90,
                           'daily_rows':2744100,'scope':'SKU totals across all 10 stores; source product universe includes zeros.'},
        'ranking_rule':'Sum units by item_id across stores; positive units descending, item_id ascending; explicit ROWS cumulative sums.',
        'threshold_rule':'Smallest positive-SKU prefix with cumulative_units*100 >= total_units*target; crossing SKU included; undefined for zero total units.',
        'setup_seconds':setup_seconds,'report_query_seconds':report_seconds,'independent_reference_seconds':reference_seconds,
        'sku_comparison_seconds':sku_comparison_seconds,'rank_comparison_seconds':rank_comparison_seconds,
        'result_rows':len(results),'sku_aggregates_compared':len(reference),'sku_mismatches':0,
        'positive_rank_rows_compared':sum(int(x['units'])>0 for x in reference),'rank_mismatches':0,
        'independent_reference_matched':True,'accepted_department_counts_units_matched':True,
        'accepted_department_evidence':'data/department_contribution_learner_acceptance.json',
        'accepted_department_evidence_sha256':hashlib.sha256(accepted_bytes).hexdigest(),
        'results':results,'independent_department_unit_rollup':departments,
        'fixture_cases_passed':len(cases),'fixture_cases':cases,
        'scope':'Assistant preflight only; learner concentration report pending. Every SKU total/mapping and every positive rank/cumulative total checked against independently aggregated staging/raw inputs and Python ranking. No SKU-level extracts published. Overlapping segment summaries are not ABC classes. Units basis only, not revenue/profit concentration or inventory decisions.'
    }
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2,default=str)+'\n',encoding='utf-8')
    print(json.dumps({'rows':len(results),'fixtures':len(cases),'query_seconds':report_seconds,
                      'source_sku_comparisons':len(reference),'department_units_matched':True,'results':results},default=str),flush=True)


if __name__=='__main__': main()
