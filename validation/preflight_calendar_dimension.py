"""Check core calendar and its derived day number in private in-memory databases."""
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


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--duckdb',required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    sql_path=root/'sql/14_build_calendar_dimension.sql'
    sql=sql_path.read_text(encoding='utf-8')
    source=Path('D:/database/m5-forecasting-accuracy/calendar.csv')
    registry=json.loads((root/'data/m5_source_audit.json').read_text(encoding='utf-8'))
    source_hash=sha256(source)
    assert source_hash==registry['files'][source.name]['sha256']
    setup=(root/'sql/02_import_calendar.sql').read_text(encoding='utf-8').split('-- On a repeat visit')[0]
    setup+='\n'+(root/'sql/08_stage_calendar.sql').read_text(encoding='utf-8').split('-- VALIDATION:')[0]
    settings="SET threads=2; SET memory_limit='512MB';\n"
    def run(script):
        return subprocess.run([args.duckdb,':memory:','-bail','-json'],input=settings+script,
                              text=True,encoding='utf-8',capture_output=True)
    started=time.perf_counter()
    baseline_run=run(setup+sql)
    seconds=round(time.perf_counter()-started,3)
    assert baseline_run.returncode==0,baseline_run.stderr
    baseline=json.loads(baseline_run.stdout)
    assert len(baseline)==17 and all(r['status']=='PASS' for r in baseline),baseline
    create_sql,validation_sql=sql.split('-- VALIDATION:',1)
    validation_sql=validation_sql.split('\n',1)[1]
    cases=[]
    # This calendar is small: each fault case starts from the same full 1,969-day fixture.
    for name,mutation in [
        ('duplicate_source_day_and_date',"INSERT INTO stg.m5_calendar SELECT * FROM stg.m5_calendar WHERE d='d_1';"),
        ('noncanonical_day_label',"UPDATE stg.m5_calendar SET d='d_01' WHERE d='d_1';"),
        ('out_of_range_day',"UPDATE stg.m5_calendar SET d='d_2000' WHERE d='d_1';"),
        ('null_day',"UPDATE stg.m5_calendar SET d=NULL WHERE d='d_1';"),
        ('swapped_day_labels_preserve_counts',"UPDATE stg.m5_calendar SET d=CASE WHEN d='d_1' THEN 'd_2' ELSE 'd_1' END WHERE d IN ('d_1','d_2');"),
    ]:
        failed=run(setup+mutation+'\n'+create_sql)
        assert failed.returncode!=0 and 'Calendar requires complete core fields' in failed.stderr,(name,failed.stderr)
        cases.append({'case':name,'passed':True,'creation_rejected':True})
    for name,mutation,expected in [
        ('wrong_derived_day_number_source_fields_unchanged',"UPDATE core.m5_calendar SET day_number=2 WHERE d='d_1';",
         {'invalid_day_mapping_rows':1,'stg_only_rows':0,'core_only_rows':0,'distinct_day_numbers':1968}),
        ('changed_event_text',"UPDATE core.m5_calendar SET event_name_1='TEST_EVENT' WHERE d='d_1';",
         {'stg_only_rows':1,'core_only_rows':1}),
        ('lost_existing_event_value',"UPDATE core.m5_calendar SET event_name_1=NULL WHERE d=(SELECT d FROM core.m5_calendar WHERE event_name_1 IS NOT NULL ORDER BY day_number LIMIT 1);",
         {'stg_only_rows':1,'core_only_rows':1}),
        ('trimmed_post_observation_dates',"DELETE FROM core.m5_calendar WHERE day_number>1941;",
         {'calendar_rows':1941,'observed_sales_days':1941,'post_observation_days':0,'stg_only_rows':28,'source_key_join_errors':28}),
        ('missing_interior_day',"DELETE FROM core.m5_calendar WHERE d='d_100';",
         {'calendar_rows':1968,'stg_only_rows':1,'source_key_join_errors':1}),
        ('duplicate_dimension_row',"INSERT INTO core.m5_calendar SELECT * FROM core.m5_calendar WHERE d='d_1';",
         {'calendar_rows':1970,'distinct_dates':1969,'core_only_rows':1,'source_key_join_errors':1}),
        ('reordered_columns',"CREATE OR REPLACE TABLE core.m5_calendar AS SELECT day_number,* EXCLUDE(day_number) FROM core.m5_calendar;",
         {'schema_mismatch_count':15,'stg_only_rows':0,'core_only_rows':0}),
    ]:
        result=run(setup+create_sql+mutation+'\n'+validation_sql)
        assert result.returncode==0,(name,result.stderr)
        rows=json.loads(result.stdout)
        actual={r['check_name']:r['actual'] for r in rows}
        assert all(actual[k]==str(v) for k,v in expected.items()),(name,actual)
        assert any(r['status']=='FAIL' for r in rows),name
        cases.append({'case':name,'passed':True,'checked_actuals':{k:actual[k] for k in expected}})
    empty=run(setup+'DELETE FROM stg.m5_calendar;\n'+sql)
    assert empty.returncode==0,empty.stderr
    assert next(r for r in json.loads(empty.stdout) if r['check_name']=='calendar_rows')['status']=='FAIL'
    cases.append({'case':'empty_source_fails_acceptance_even_if_ctas_succeeds','passed':True})
    assert sha256(source)==source_hash
    report={
        'checked_at_utc':datetime.now(timezone.utc).isoformat(),'executor':'assistant',
        'engine':subprocess.check_output([args.duckdb,'-version'],text=True).strip(),
        'baseline_database':'Private in-memory DuckDB; learner database never opened.',
        'settings':{'threads':2,'memory_limit':'512MB'},
        'script':'sql/14_build_calendar_dimension.sql','script_sha256':sha256(sql_path),
        'source_file':source.name,'source_sha256':source_hash,'source_hash_unchanged':True,
        'raw_staging_core_creation_and_validation_seconds':seconds,
        'checks_passed':17,'results':baseline,'fixture_cases_passed':len(cases),'fixture_cases':cases,
        'scope':'Assistant preflight of core calendar keys, exact preservation of 14 staging fields and derived day_number. Learner execution pending. The 1,941/28 day partition uses the accepted sales snapshot boundary, not a scan of daily sales or a model-specific training cutoff. No daily price coverage or physical PRIMARY KEY.'
    }
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'checks_passed':17,'fixture_cases_passed':len(cases),'baseline_seconds':seconds}))


if __name__=='__main__':
    main()
