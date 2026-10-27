"""Validate a persisted units-based ABC table with independent per-SKU and prefix references."""
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
    sql_path=root/'sql/21_build_product_abc_units.sql'
    sql_bytes=sql_path.read_bytes();sql=sql_bytes.decode('utf-8')
    build,audit=sql.split('-- VALIDATION:',1);audit='-- VALIDATION:'+audit
    def parse(output): return json.loads(output,parse_float=Decimal)
    def pct(n,d):
        return None if d==0 else (Decimal(n)*100/Decimal(d)).quantize(Decimal('0.0001'),rounding=ROUND_HALF_UP)
    def reference_labels(source):
        # Independent implementation: find minimal prefix endpoints, then label by rank intervals.
        positive=sorted([x for x in source if int(x['units'])>0],key=lambda x:(-int(x['units']),x['item_id']))
        total=sum(int(x['units']) for x in source)
        cutoffs={80:0,95:0};cumulative=0;ranks={}
        for rank,x in enumerate(positive,1):
            cumulative+=int(x['units']);ranks[x['item_id']]=(rank,cumulative)
            for target in cutoffs:
                if cutoffs[target]==0 and cumulative*100>=total*target:cutoffs[target]=rank
        expected=[]
        for x in sorted(source,key=lambda x:x['item_id']):
            rank,cum=ranks.get(x['item_id'],(None,None))
            label='ZERO_SALES' if rank is None else 'A' if rank<=cutoffs[80] else 'B' if rank<=cutoffs[95] else 'C'
            expected.append(dict(item_id=x['item_id'],dept_id=x['dept_id'],cat_id=x['cat_id'],
                window_start='2016-01-26',window_end='2016-04-24',units=int(x['units']),
                sku_rank=rank,cumulative_units=cum,abc_class=label))
        return expected
    def assert_memberships(actual,expected):
        assert len(actual)==len(expected)
        for a,e in zip(actual,expected):
            for key in e:
                value=a[key]
                if value is not None and key in ('units','sku_rank','cumulative_units'):value=int(value)
                assert value==e[key],(key,a,e)
    def assert_report(actual,labels):
        assert len(actual)==5
        total=sum(x['units'] for x in labels)
        for a,kind in zip(actual,['A','B','C','ZERO_SALES','TOTAL']):
            members=labels if kind=='TOTAL' else [x for x in labels if x['abc_class']==kind]
            units=sum(x['units'] for x in members);ranks=[x['sku_rank'] for x in members if x['sku_rank'] is not None]
            assert a['abc_class']==kind and a['check_status']=='PASS',a
            assert int(a['sku_count'])==len(members) and int(a['units'])==units,a
            assert (None if a['sku_share_pct'] is None else Decimal(str(a['sku_share_pct'])))==pct(len(members),len(labels)),a
            assert (None if a['unit_share_pct'] is None else Decimal(str(a['unit_share_pct'])))==pct(units,total),a
            assert a['first_rank']==(min(ranks) if ranks else None) and a['last_rank']==(max(ranks) if ranks else None),a
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
    def tiny(name,weights,before='',after='',error=None,expected_classes=None):
        replacements=('3049 AS expected_items,10 AS expected_stores',f'{len(weights)} AS expected_items,2 AS expected_stores')
        tiny_build=build.replace(*replacements);tiny_audit=audit.replace(*replacements)
        with tempfile.TemporaryDirectory(prefix='abc-fixture-',dir=root/'tmp') as folder:
            assert Path(folder).resolve().is_relative_to((root/'tmp').resolve())
            database=Path(folder)/'fixture.duckdb'
            def execute(script):
                return subprocess.run([args.duckdb,str(database),'-bail','-json'],input=script,
                                      text=True,encoding='utf-8',capture_output=True)
            run=execute(fixture(weights)+before+'\n'+tiny_build+'\n'+after+'\n'+tiny_audit)
            if error:
                assert run.returncode!=0 and error in run.stderr,(name,run.stderr)
                if error=='ABC build blocked':
                    absent=execute("SELECT COUNT(*) AS table_count FROM information_schema.tables WHERE table_schema='mart' AND table_name='m5_product_abc_90d';")
                    assert absent.returncode==0 and parse(absent.stdout)==[{'table_count':0}],(name,absent.stdout)
            else:
                assert run.returncode==0,(name,run.stderr)
                source=[dict(item_id=f'P{i:03d}',dept_id='FOODS_1',cat_id='FOODS',units=w) for i,w in enumerate(weights,1)]
                expected=reference_labels(source);assert_report(parse(run.stdout),expected)
                members=execute('SELECT * FROM mart.m5_product_abc_90d ORDER BY item_id;')
                assert members.returncode==0,members.stderr
                assert_memberships(parse(members.stdout),expected)
                if expected_classes is not None:assert [x['abc_class'] for x in expected]==expected_classes
        assert not Path(folder).exists()
        cases.append({'case':name,'passed':True,'guard_rejected':error is not None})
    (root/'tmp').mkdir(exist_ok=True)
    tiny('exact_boundaries',[80,15,5,0],expected_classes=['A','B','C','ZERO_SALES'])
    tiny('crossing_item_in_earlier_class',[79,16,5,0],expected_classes=['A','A','C','ZERO_SALES'])
    tiny('one_item_crosses_both_thresholds',[96,4,0],expected_classes=['A','C','ZERO_SALES'])
    tiny('equal_units_deterministic_ties',[40,40,15,5,0],expected_classes=['A','A','B','C','ZERO_SALES'])
    tiny('all_zero_empty_positive_classes',[0,0,0],expected_classes=['ZERO_SALES']*3)
    tiny('single_positive_sku',[5,0],expected_classes=['A','ZERO_SALES'])
    tiny('inclusive_window_excludes_adjacent_days',[80,15,5,0],before="""INSERT INTO mart.m5_sales_daily VALUES
('P001','S1','d_1823',DATE '2016-01-25',99999),('P001','S1','d_1914',DATE '2016-04-25',99999);""")
    for name,after in [
        ('wrong_class',"UPDATE mart.m5_product_abc_90d SET abc_class='C' WHERE item_id='P001';"),
        ('wrong_rank',"UPDATE mart.m5_product_abc_90d SET sku_rank=2 WHERE item_id='P001';"),
        ('wrong_cumulative_units',"UPDATE mart.m5_product_abc_90d SET cumulative_units=81 WHERE item_id='P001';"),
        ('zero_rank_must_remain_null',"UPDATE mart.m5_product_abc_90d SET sku_rank=0,cumulative_units=100 WHERE item_id='P004';"),
        ('wrong_window',"UPDATE mart.m5_product_abc_90d SET window_end=DATE '2016-04-25' WHERE item_id='P001';"),
        ('wrong_hierarchy',"UPDATE mart.m5_product_abc_90d SET dept_id='FOODS_2' WHERE item_id='P001';"),
        ('duplicate_product_row',"INSERT INTO mart.m5_product_abc_90d SELECT * FROM mart.m5_product_abc_90d WHERE item_id='P001';"),
        ('missing_product_row',"DELETE FROM mart.m5_product_abc_90d WHERE item_id='P004';"),
        ('same_total_units_redistribution',"UPDATE mart.m5_product_abc_90d SET units=CASE item_id WHEN 'P001' THEN 79 WHEN 'P002' THEN 16 ELSE units END;"),
        ('schema_type_changed',"ALTER TABLE mart.m5_product_abc_90d ALTER units TYPE BIGINT;"),
    ]:tiny(name,[80,15,5,0],after=after,error='ABC validation failed')
    for name,before in [
        ('empty_window_source',"DELETE FROM mart.m5_sales_daily;"),
        ('negative_source_units',"UPDATE mart.m5_sales_daily SET units=-1 WHERE item_id='P001' AND date=DATE '2016-02-01';"),
        ('duplicate_missing_source_day',"UPDATE mart.m5_sales_daily SET date=DATE '2016-02-02',d='d_1831' WHERE item_id='P001' AND store_id='S1' AND date=DATE '2016-02-01';"),
        ('duplicate_product_mapping',"INSERT INTO core.m5_product SELECT * FROM core.m5_product WHERE item_id='P001';"),
    ]:tiny(name,[80,15,5,0],before=before,error='ABC build blocked')
    print(json.dumps({'fixture_cases_passed':len(cases)}),flush=True)
    if args.fixtures_only:return
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
    with tempfile.TemporaryDirectory(prefix='abc-units-',dir=tmp_root) as folder:
        assert Path(folder).resolve().is_relative_to(tmp_root.resolve())
        database=Path(folder)/'preflight.duckdb'
        assert database.resolve().is_relative_to(Path(folder).resolve())
        spill=(Path(folder)/'spill').as_posix().replace("'","''")
        settings=f"SET threads=2; SET memory_limit='2GB'; SET temp_directory='{spill}';\n"
        def execute(script):
            started=time.perf_counter()
            run=subprocess.run([args.duckdb,str(database),'-bail','-json'],input=settings+script,
                               text=True,encoding='utf-8',capture_output=True)
            assert run.returncode==0,run.stderr
            return run,round(time.perf_counter()-started,3)
        _,setup_seconds=execute(setup);print(json.dumps({'setup_seconds':setup_seconds}),flush=True)
        _,build_seconds=execute(build)
        run,audit_seconds=execute(audit);results=parse(run.stdout)
        run,reference_seconds=execute(reference_sql);source=parse(run.stdout)
        expected=reference_labels(source)
        run,_=execute('SELECT * FROM mart.m5_product_abc_90d ORDER BY item_id;')
        assert len(expected)==3049;assert_memberships(parse(run.stdout),expected);assert_report(results,expected)
        accepted_path=root/'data/product_unit_concentration_learner_acceptance.json'
        accepted_bytes=accepted_path.read_bytes();accepted=json.loads(accepted_bytes.decode('utf-8'))
        assert accepted['analysis_window']['start_date']=='2016-01-26' and accepted['analysis_window']['end_date']=='2016-04-24'
        prefix={x['segment']:x for x in accepted['results']};classes={x['abc_class']:x for x in results}
        for key,group in [('REACH_80_PCT',['A']),('REACH_95_PCT',['A','B']),('ALL_POSITIVE',['A','B','C']),('ZERO_SALES',['ZERO_SALES']),('ALL_PRODUCTS',['TOTAL'])]:
            assert sum(int(classes[k]['sku_count']) for k in group)==int(prefix[key]['sku_count'])
            assert sum(int(classes[k]['units']) for k in group)==int(prefix[key]['units'])
        database_bytes=database.stat().st_size
    assert not Path(folder).exists()
    assert all(sha256(p)==hashes[p.name] for p in sources)
    report={
        'checked_at_utc':datetime.now(timezone.utc).isoformat(),'executor':'assistant',
        'engine':subprocess.check_output([args.duckdb,'-version'],text=True).strip(),
        'baseline_database':'Private temporary on-disk DuckDB under repository tmp; removed after verification.',
        'temporary_baseline_removed':True,'temporary_database_bytes_after_close':database_bytes,
        'settings':{'threads':2,'memory_limit':'2GB'},
        'script':'sql/21_build_product_abc_units.sql','script_sha256':hashlib.sha256(sql_bytes).hexdigest(),
        'prerequisite_script_sha256':prerequisite_hashes,'source_sha256':hashes,'source_hashes_unchanged':True,
        'analysis_window':{'start_date':'2016-01-26','end_date':'2016-04-24','inclusive_days':90,
                           'scope':'Global product unit totals across all 10 stores, including zero-sales source products.'},
        'table':'mart.m5_product_abc_90d','table_columns':9,
        'classification_rule':'ZERO_SALES first; positives sorted units DESC,item_id ASC. Prior cumulative units*100 < total*80 => A; else <total*95 => B; else C. Crossing SKU remains in earlier class. Threshold membership uses exact integers.',
        'setup_seconds':setup_seconds,'abc_build_seconds':build_seconds,'abc_validation_seconds':audit_seconds,
        'independent_reference_seconds':reference_seconds,'sku_rows_compared':len(expected),'row_mismatches':0,
        'result_rows':len(results),'independent_reference_matched':True,'accepted_concentration_prefixes_matched':True,
        'accepted_concentration_evidence':'data/product_unit_concentration_learner_acceptance.json',
        'accepted_concentration_evidence_sha256':hashlib.sha256(accepted_bytes).hexdigest(),'results':results,
        'fixture_cases_passed':len(cases),'fixture_cases':cases,
        'scope':'Assistant preflight only; learner ABC build pending. All stored fields independently compared against staging/raw SKU totals and Python prefix-based labels. Five-row summary reconciles to accepted SQL20. No SKU-level extract published. This is an 80/95 unit-based baseline; threshold sensitivity, XYZ and downstream business actions remain pending.'
    }
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2,default=str)+'\n',encoding='utf-8')
    print(json.dumps({'rows':len(results),'fixtures':len(cases),'build_seconds':build_seconds,'validation_seconds':audit_seconds,
                      'source_SKUs_compared':len(expected),'accepted_prefixes_matched':True,'results':results},default=str),flush=True)


if __name__=='__main__':main()
