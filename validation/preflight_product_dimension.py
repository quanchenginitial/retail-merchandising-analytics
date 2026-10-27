"""Check product-dimension creation using only a private in-memory database."""
import argparse
import hashlib
import json
import subprocess
import time
from datetime import datetime, timezone
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
    sql_path=root/'sql/12_build_product_dimension.sql'
    sql=sql_path.read_text(encoding='utf-8')
    source=Path('D:/database/m5-forecasting-accuracy/sales_train_evaluation.csv')
    registry=json.loads((root/'data/m5_source_audit.json').read_text(encoding='utf-8'))
    source_hash=sha256(source)
    assert source_hash==registry['files'][source.name]['sha256']
    settings="SET threads=2; SET memory_limit='512MB';\n"
    def run(script):
        return subprocess.run([args.duckdb,':memory:','-bail','-json'],input=settings+script,
                              text=True,encoding='utf-8',capture_output=True)
    # Every source row is read, but only the three fields used by SQL 12 are stored.
    source_sql=source.as_posix().replace("'","''")
    setup="CREATE SCHEMA raw; CREATE TABLE raw.m5_sales_wide AS SELECT item_id,dept_id,cat_id FROM read_csv('"+source_sql+"',header=true,all_varchar=true);\n"
    started=time.perf_counter()
    baseline_run=run(setup+sql)
    seconds=round(time.perf_counter()-started,3)
    assert baseline_run.returncode==0,baseline_run.stderr
    baseline=json.loads(baseline_run.stdout)
    assert len(baseline)==15 and all(r['status']=='PASS' for r in baseline),baseline
    assert sha256(source)==source_hash

    fixture="CREATE SCHEMA raw; CREATE TABLE raw.m5_sales_wide AS SELECT * FROM (VALUES ('001','D1','C1'),('001','D1','C1'),('002','D2','C2')) AS t(item_id,dept_id,cat_id);\n"
    # Adapt only the expected item/department/category counts for the tiny fixture.
    fixture_sql=sql.replace("'3049'","'2'").replace("'7'","'2'").replace("distinct_categories::VARCHAR,'3'","distinct_categories::VARCHAR,'2'")
    create_sql,validation_sql=fixture_sql.split('-- VALIDATION:',1)
    validation_sql=validation_sql.split('\n',1)[1]
    good=run(fixture+fixture_sql)
    assert good.returncode==0,good.stderr
    assert all(r['status']=='PASS' for r in json.loads(good.stdout))
    cases=[{'case':'identical_product_rows_collapse_and_source_codes_preserved','passed':True}]
    for name,mutation in [
        ('conflicting_item_mapping',"INSERT INTO raw.m5_sales_wide VALUES ('001','D2','C2');"),
        ('department_has_two_categories',"UPDATE raw.m5_sales_wide SET dept_id='D1' WHERE item_id='002';"),
        ('null_category',"UPDATE raw.m5_sales_wide SET cat_id=NULL WHERE item_id='002';"),
        ('empty_item',"UPDATE raw.m5_sales_wide SET item_id='' WHERE item_id='002';"),
        ('space_only_department',"UPDATE raw.m5_sales_wide SET dept_id='   ' WHERE item_id='002';"),
    ]:
        failed=run(fixture+mutation+'\n'+create_sql)
        assert failed.returncode!=0 and 'Product mapping must have nonblank codes' in failed.stderr,(name,failed.stderr)
        cases.append({'case':name,'passed':True,'creation_rejected':True})
    for name,mutation,expected in [
        ('duplicate_dimension_row',"INSERT INTO core.m5_product SELECT * FROM core.m5_product WHERE item_id='001';",
         {'duplicate_or_null_item_rows':1,'dimension_only_product_rows':1,'source_key_join_errors':1}),
        ('changed_mapping_with_same_row_count',"UPDATE core.m5_product SET dept_id='D1' WHERE item_id='002';",
         {'product_rows':2,'raw_only_product_rows':1,'dimension_only_product_rows':1,'dimension_department_conflicts':1}),
        ('missing_product',"DELETE FROM core.m5_product WHERE item_id='002';",
         {'raw_only_product_rows':1,'source_key_join_errors':1}),
        ('extra_product',"INSERT INTO core.m5_product VALUES ('003','D1','C1');",
         {'dimension_only_product_rows':1,'product_rows':3}),
        ('reordered_columns',"CREATE OR REPLACE TABLE core.m5_product AS SELECT dept_id,item_id,cat_id FROM core.m5_product;",
         {'schema_mismatch_count':2,'raw_only_product_rows':0,'dimension_only_product_rows':0}),
    ]:
        result=run(fixture+create_sql+mutation+'\n'+validation_sql)
        assert result.returncode==0,(name,result.stderr)
        rows=json.loads(result.stdout)
        actual={r['check_name']:r['actual'] for r in rows}
        assert all(actual[k]==str(v) for k,v in expected.items()),(name,actual)
        assert any(r['status']=='FAIL' for r in rows),name
        cases.append({'case':name,'passed':True,'checked_actuals':{k:actual[k] for k in expected}})
    empty=run(fixture+'DELETE FROM raw.m5_sales_wide;\n'+fixture_sql)
    assert empty.returncode==0,empty.stderr
    empty_rows=json.loads(empty.stdout)
    assert next(r for r in empty_rows if r['check_name']=='product_rows')['status']=='FAIL'
    cases.append({'case':'empty_source_fails_acceptance_even_if_ctas_succeeds','passed':True})
    report={
        'checked_at_utc':datetime.now(timezone.utc).isoformat(),'executor':'assistant',
        'engine':subprocess.check_output([args.duckdb,'-version'],text=True).strip(),
        'baseline_database':'Private in-memory DuckDB; learner database never opened.',
        'baseline_source_projection':['item_id','dept_id','cat_id'],
        'settings':{'threads':2,'memory_limit':'512MB'},
        'script':'sql/12_build_product_dimension.sql','script_sha256':sha256(sql_path),
        'source_file':source.name,'source_sha256':source_hash,'source_hash_unchanged':True,
        'source_projection_creation_and_validation_seconds':seconds,
        'checks_passed':15,'results':baseline,'fixture_cases_passed':len(cases),'fixture_cases':cases,
        'scope':'Assistant preflight of one-row-per-product mapping and exact source triple coverage. Learner execution pending. Key uniqueness is checked, not enforced by a physical PRIMARY KEY. No daily sales join or category sales analysis.'
    }
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'checks_passed':15,'fixture_cases_passed':len(cases),'baseline_seconds':seconds}))


if __name__=='__main__':
    main()
