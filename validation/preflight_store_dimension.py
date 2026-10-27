"""Check store-dimension creation in private in-memory databases only."""
import argparse
import hashlib
import json
import subprocess
import time
from datetime import datetime,timezone
from pathlib import Path


def sha256(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def json_results(output):
    decoder=json.JSONDecoder()
    results=[]
    remaining=output.strip()
    while remaining:
        value,end=decoder.raw_decode(remaining)
        results.append(value)
        remaining=remaining[end:].strip()
    return results


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--duckdb',required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    sql_path=root/'sql/13_build_store_dimension.sql'
    sql=sql_path.read_text(encoding='utf-8')
    source=Path('D:/database/m5-forecasting-accuracy/sales_train_evaluation.csv')
    registry=json.loads((root/'data/m5_source_audit.json').read_text(encoding='utf-8'))
    source_hash=sha256(source)
    assert source_hash==registry['files'][source.name]['sha256']
    settings="SET threads=2; SET memory_limit='512MB';\n"
    def run(script):
        return subprocess.run([args.duckdb,':memory:','-bail','-json'],input=settings+script,
                              text=True,encoding='utf-8',capture_output=True)
    source_sql=source.as_posix().replace("'","''")
    # Read every source row, storing only the two fields used by SQL 13.
    setup="CREATE SCHEMA raw; CREATE TABLE raw.m5_sales_wide AS SELECT store_id,state_id FROM read_csv('"+source_sql+"',header=true,all_varchar=true);\n"
    profile="SELECT state_id,COUNT(*) AS store_count FROM (SELECT DISTINCT store_id,state_id FROM raw.m5_sales_wide) GROUP BY state_id ORDER BY state_id;"
    started=time.perf_counter()
    baseline_run=run(setup+sql+'\n'+profile)
    seconds=round(time.perf_counter()-started,3)
    assert baseline_run.returncode==0,baseline_run.stderr
    baseline,state_counts=json_results(baseline_run.stdout)
    assert len(baseline)==13 and all(r['status']=='PASS' for r in baseline),baseline
    assert {r['state_id']:int(r['store_count']) for r in state_counts}=={'CA':4,'TX':3,'WI':3},state_counts
    assert sha256(source)==source_hash

    fixture="CREATE SCHEMA raw; CREATE TABLE raw.m5_sales_wide AS SELECT * FROM (VALUES ('CA_1','CA'),('CA_1','CA'),('TX_1','TX')) AS t(store_id,state_id);\n"
    # Adapt only snapshot cardinalities and state store counts for the tiny fixture.
    fixture_sql=sql.replace("'10'","'2'").replace("distinct_states::VARCHAR,'3'","distinct_states::VARCHAR,'2'").replace("('CA',4),('TX',3),('WI',3)","('CA',1),('TX',1)")
    create_sql,validation_sql=fixture_sql.split('-- VALIDATION:',1)
    validation_sql=validation_sql.split('\n',1)[1]
    good=run(fixture+fixture_sql)
    assert good.returncode==0,good.stderr
    assert all(r['status']=='PASS' for r in json.loads(good.stdout))
    cases=[{'case':'identical_store_state_rows_collapse','passed':True}]
    for name,mutation in [
        ('conflicting_store_mapping',"INSERT INTO raw.m5_sales_wide VALUES ('CA_1','TX');"),
        ('null_state',"UPDATE raw.m5_sales_wide SET state_id=NULL WHERE store_id='TX_1';"),
        ('empty_store',"UPDATE raw.m5_sales_wide SET store_id='' WHERE store_id='TX_1';"),
        ('space_only_state',"UPDATE raw.m5_sales_wide SET state_id='   ' WHERE store_id='TX_1';"),
    ]:
        failed=run(fixture+mutation+'\n'+create_sql)
        assert failed.returncode!=0 and 'Store mapping must have nonblank codes' in failed.stderr,(name,failed.stderr)
        cases.append({'case':name,'passed':True,'creation_rejected':True})
    for name,mutation,expected in [
        ('duplicate_dimension_row',"INSERT INTO core.m5_store SELECT * FROM core.m5_store WHERE store_id='CA_1';",
         {'duplicate_or_null_store_rows':1,'dimension_only_store_rows':1,'source_key_join_errors':1,'state_store_count_mismatches':1}),
        ('swapped_states_preserve_all_counts',"UPDATE core.m5_store SET state_id=CASE WHEN state_id='CA' THEN 'TX' ELSE 'CA' END;",
         {'store_rows':2,'distinct_states':2,'state_store_count_mismatches':0,'raw_only_store_rows':2,'dimension_only_store_rows':2}),
        ('missing_store',"DELETE FROM core.m5_store WHERE store_id='TX_1';",
         {'raw_only_store_rows':1,'source_key_join_errors':1,'state_store_count_mismatches':1}),
        ('extra_store_and_state',"INSERT INTO core.m5_store VALUES ('OTHER_1','OTHER');",
         {'dimension_only_store_rows':1,'store_rows':3,'state_store_count_mismatches':1}),
        ('reordered_columns',"CREATE OR REPLACE TABLE core.m5_store AS SELECT state_id,store_id FROM core.m5_store;",
         {'schema_mismatch_count':2,'raw_only_store_rows':0,'dimension_only_store_rows':0}),
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
    assert next(r for r in json.loads(empty.stdout) if r['check_name']=='store_rows')['status']=='FAIL'
    cases.append({'case':'empty_source_fails_acceptance_even_if_ctas_succeeds','passed':True})
    report={
        'checked_at_utc':datetime.now(timezone.utc).isoformat(),'executor':'assistant',
        'engine':subprocess.check_output([args.duckdb,'-version'],text=True).strip(),
        'baseline_database':'Private in-memory DuckDB; learner database never opened.',
        'baseline_source_projection':['store_id','state_id'],'source_state_store_counts':state_counts,
        'settings':{'threads':2,'memory_limit':'512MB'},
        'script':'sql/13_build_store_dimension.sql','script_sha256':sha256(sql_path),
        'source_file':source.name,'source_sha256':source_hash,'source_hash_unchanged':True,
        'source_projection_creation_validation_and_profile_seconds':seconds,
        'checks_passed':13,'results':baseline,'fixture_cases_passed':len(cases),'fixture_cases':cases,
        'scope':'Assistant preflight of one-row-per-store mapping and exact source pair coverage. Learner execution pending. State is read from the source column, not inferred from store code prefixes. No physical PRIMARY KEY or full daily sales join.'
    }
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'checks_passed':13,'fixture_cases_passed':len(cases),'baseline_seconds':seconds,'source_state_store_counts':state_counts}))


if __name__=='__main__':
    main()
