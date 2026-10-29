"""Stream-check both full-catalog baselines; use only private databases and read-only original files."""
import argparse
from array import array
import csv
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time

sys.dont_write_bytecode = True
from preflight_forecast_scope_and_time_audit import (
    FIRST_DATE, ORIGINS, DAILY_FIELDS, METADATA_FIELDS, SNAPSHOTS, original_reference,
    membership_hash, quote, sha256, json_hash, compare_csv, export_snapshots,
)
from preflight_seasonal_naive_forecasts import (
    FORECAST_COLUMNS as S7_COLUMNS, FORECAST_QUERY as S7_QUERY,
    forecast_reference as s7_reference, forecast_report as s7_report,
    canonical_report as s7_canonical_report, read_forecast_csv as s7_read,
)
from preflight_weekday_mean_forecasts import (
    FORECAST_COLUMNS as W4_COLUMNS, FORECAST_QUERY as W4_QUERY,
    forecast_reference as w4_reference, forecast_report as w4_report,
    canonical_report as w4_canonical_report, read_forecast_csv as w4_read,
    canonical_forecasts as w4_canonical_forecasts,
)

TABLE = 'mart.m5_forecast_baselines_all_28d'
MEMBERSHIP = 'dfa7ed458d1aa6d5afa80b9847aa1c0a98d98d06e7c3347acb9881bbb0584114'
METADATA = 'c36d6ca2fb1e0555b5a6f150832c1cd7648c7f0a76891ee8fbc88cae9dce6cbf'
COLUMNS = ['model','origin','item_id','store_id','train_end_day','train_end','horizon_day',
           'forecast_day','forecast_date','source_first_day','source_last_day','source_observations',
           'source_units_sum','predicted_units']
REPORT_COLUMNS = ['origin','model','series_count','forecast_rows','forecast_start','forecast_end',
                  'input_days','input_units','predicted_units','zero_forecast_rows','fractional_forecast_rows','check_status']
FORECAST_QUERY = f"SELECT {','.join(COLUMNS)} FROM {TABLE} ORDER BY train_end_day,model,item_id,store_id,horizon_day"
RECENT_QUERY = """SELECT item_id,store_id,d,date,wm_yr_wk,units FROM mart.m5_sales_daily
WHERE regexp_full_match(d,'d_[1-9][0-9]*') AND TRY_CAST(SUBSTR(d,3) AS INTEGER) BETWEEN 1802 AND 1913
ORDER BY item_id,store_id,TRY_CAST(SUBSTR(d,3) AS INTEGER),date,wm_yr_wk,units"""


def metadata_hash(rows):
    return hashlib.sha256('\n'.join('|'.join(row) for row in sorted(rows)).encode()).hexdigest()


def source_recent(path):
    """Inspect exactly 112 quantity fields per source series; keep compact unsigned integer arrays."""
    metadata, recent = [], {}
    with path.open(newline='',encoding='utf-8-sig') as stream:
        reader = csv.reader(stream)
        header = next(reader)
        assert header[1807:1919] == [f'd_{n}' for n in range(1802,1914)]
        for row in reader:
            meta = tuple(row[1:6])
            assert all(re.fullmatch(r'[A-Z0-9_]+',v) for v in meta)
            metadata.append(meta)
            key = (row[1],row[4])
            assert key not in recent
            values = row[1807:1919]
            assert len(values)==112 and all(re.fullmatch(r'[0-9]+',v) for v in values)
            units = [int(v) for v in values]
            assert all(0<=v<=2147483647 for v in units)
            recent[key] = array('I',units)
    assert len(recent)==30490 and membership_hash(recent)==MEMBERSHIP
    assert metadata_hash(metadata)==METADATA
    return metadata,recent


def reference_rows(recent,calendar):
    """Four chronological seven-day blocks, then column sums; no SQL modulo expression is copied."""
    for origin_index,(origin,last) in enumerate(ORIGINS):
        for model in ('SNAIVE7','WEEKDAY4'):
            for (item,store),values in sorted(recent.items()):
                window = values[origin_index*28:(origin_index+1)*28]
                weeks = [window[n:n+7] for n in (0,7,14,21)]
                totals = list(weeks[-1]) if model=='SNAIVE7' else [sum(v) for v in zip(*weeks)]
                observations = 1 if model=='SNAIVE7' else 4
                predictions = [format(Decimal(n)/Decimal(observations),'.2f') for n in totals]
                for repeat in range(4):
                    for offset,(total,prediction) in enumerate(zip(totals,predictions)):
                        horizon = repeat*7+offset+1
                        source_last = last-6+offset
                        source_first = source_last if observations==1 else last-27+offset
                        yield (model,origin,item,store,last,calendar[last]['date'],horizon,last+horizon,
                               calendar[last+horizon]['date'],source_first,source_last,observations,total,prediction)


def reference_report(recent,calendar):
    results=[]
    for index,(origin,last) in enumerate(ORIGINS):
        for model in ('SNAIVE7','WEEKDAY4'):
            input_units=zero=fractional=0
            for values in recent.values():
                window=values[index*28:(index+1)*28]
                weeks=[window[n:n+7] for n in (0,7,14,21)]
                totals=list(weeks[-1]) if model=='SNAIVE7' else [sum(v) for v in zip(*weeks)]
                input_units+=sum(totals)
                zero+=4*sum(v==0 for v in totals)
                fractional+=0 if model=='SNAIVE7' else 4*sum(v%4!=0 for v in totals)
            predicted=input_units*4 if model=='SNAIVE7' else input_units
            results.append(dict(origin=origin,model=model,series_count=len(recent),forecast_rows=len(recent)*28,
                                forecast_start=calendar[last+1]['date'],forecast_end=calendar[last+28]['date'],
                                input_days=7 if model=='SNAIVE7' else 28,input_units=input_units,
                                predicted_units=format(Decimal(predicted),'.2f'),zero_forecast_rows=zero,
                                fractional_forecast_rows=fractional,check_status='PASS'))
    return results


def canonical_report(rows):
    for row in rows:
        assert list(row)==REPORT_COLUMNS
        for key in ('series_count','forecast_rows','input_days','input_units','zero_forecast_rows','fractional_forecast_rows'):
            row[key]=int(row[key])
        row['predicted_units']=format(Decimal(str(row['predicted_units'])),'.2f')
    return rows


def stream_compare(path,fields,expected):
    """Keep one observed and one expected row; fingerprint both independently after exact comparison."""
    observed_hash,expected_hash=hashlib.sha256(),hashlib.sha256()
    count=0
    with path.open(newline='',encoding='utf-8') as stream:
        reader=csv.reader(stream)
        assert next(reader)==fields
        for row in expected:
            wanted=[str(value) for value in row]
            got=next(reader,None)
            assert got==wanted,('Stream field mismatch',count)
            observed_hash.update(('\t'.join(got)+'\n').encode('utf-8'))
            expected_hash.update(('\t'.join(wanted)+'\n').encode('utf-8'))
            count+=1
        assert next(reader,None) is None,'Unexpected extra stream row'
    assert observed_hash.hexdigest()==expected_hash.hexdigest()
    return dict(rows=count,columns=len(fields),field_mismatches=0,
                observed_sha256=observed_hash.hexdigest(),independent_reference_sha256=expected_hash.hexdigest())


def copy(query,path):
    return f"COPY ({query}) TO {quote(path.as_posix())} (HEADER, DELIMITER ',');\n"


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--duckdb',required=True)
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--fixtures-only',action='store_true')
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    tmp_root=(root/'tmp').resolve()
    tmp_root.mkdir(exist_ok=True)
    assert tmp_root.is_relative_to(root.resolve())
    sql_path=root/'sql/38_build_full_catalog_baseline_forecasts.sql'
    sql=sql_path.read_text(encoding='utf-8')
    build,validation=sql.split('-- VALIDATION:',1)
    validation='-- VALIDATION:'+validation
    protocol=root/'docs/FULL_CATALOG_BASELINE_FORECASTS_PROTOCOL.md'
    assert protocol.exists()
    pinned_paths=[protocol,root/'docs/EVALUATION_PLAN.md',sql_path,Path(__file__)]
    pinned_paths+=list((root/'data').glob('*_preflight.json'))+list((root/'data').glob('*_learner_acceptance.json'))
    pinned_paths+=[root/'data/m5_source_audit.json']
    pinned_paths+=[root/p for p in ('validation/preflight_forecast_scope_and_time_audit.py',
        'validation/preflight_seasonal_naive_forecasts.py','validation/preflight_weekday_mean_forecasts.py',
        'sql/33_forecast_scope_and_time_audit.sql','sql/34_build_seasonal_naive_forecasts.sql',
        'sql/35_build_weekday_mean_forecasts.sql','sql/08_stage_calendar.sql','sql/12_build_product_dimension.sql',
        'sql/13_build_store_dimension.sql','sql/14_build_calendar_dimension.sql')]
    pinned={p.relative_to(root).as_posix():sha256(p) for p in pinned_paths
            if p.name!='full_catalog_baseline_forecasts_preflight.json'}
    cases=[]
    calendar={n:dict(date=(FIRST_DATE+timedelta(days=n-1)).isoformat()) for n in range(1,1970)}
    metadata=[(item,'DEPT','CAT',store,state) for item in ('P001','P002') for store,state in (('S1','A'),('S2','B'))]
    baseline={}
    for item,_,_,store,_ in metadata:
        baseline[item,store]=array('I',((n%17+(0 if item=='P001' else 11)+(0 if store=='S1' else 27)) for n in range(112)))
    baseline['P002','S2']=array('I',[0]*112)
    blocks=[[0,1,0,2,0,1,5],[1,3,0,0,1,2,6],[4,6,0,3,1,3,5],[8,8,0,6,3,4,7]]
    baseline['P001','S1'][:28]=array('I',[v for block in blocks for v in block])
    def fixture_sql(text):
        return text.replace('3049 AS expected_products,10 AS expected_stores','2 AS expected_products,2 AS expected_stores').replace(
            '30490 AS expected_scope_series','4 AS expected_scope_series').replace(MEMBERSHIP,membership_hash(baseline)).replace(METADATA,metadata_hash(metadata))
    fixture_build,fixture_validation=fixture_sql(build),fixture_sql(validation)
    fixture_setup="""CREATE SCHEMA raw; CREATE SCHEMA core; CREATE SCHEMA mart;
CREATE TABLE core.m5_product(item_id VARCHAR,dept_id VARCHAR,cat_id VARCHAR);
INSERT INTO core.m5_product VALUES ('P001','DEPT','CAT'),('P002','DEPT','CAT');
CREATE TABLE core.m5_store(store_id VARCHAR,state_id VARCHAR);
INSERT INTO core.m5_store VALUES ('S1','A'),('S2','B');
CREATE TABLE raw.m5_sales_wide AS SELECT item_id,dept_id,cat_id,store_id,state_id
FROM core.m5_product CROSS JOIN core.m5_store;
CREATE TABLE core.m5_calendar AS SELECT 'd_'||CAST(n AS VARCHAR) AS d,
DATE '2011-01-29'+CAST(n AS INTEGER)-1 AS date,CAST(n AS INTEGER) AS day_number,CAST(11000+n//7 AS INTEGER) AS wm_yr_wk
FROM range(1,1970) t(n);
CREATE TABLE mart.m5_sales_daily(item_id VARCHAR,store_id VARCHAR,d VARCHAR,date DATE,wm_yr_wk INTEGER,units INTEGER);
"""
    for pair,values in baseline.items():
        data=','.join(f"({1802+i},{value})" for i,value in enumerate(values))
        fixture_setup+=f"INSERT INTO mart.m5_sales_daily SELECT {quote(pair[0])},{quote(pair[1])},c.d,c.date,c.wm_yr_wk,v.units FROM (VALUES {data}) v(n,units) JOIN core.m5_calendar c ON c.day_number=v.n;\n"
    fixture_setup+="""INSERT INTO mart.m5_sales_daily SELECT p.item_id,s.store_id,c.d,c.date,c.wm_yr_wk,-999
FROM core.m5_product p CROSS JOIN core.m5_store s CROSS JOIN core.m5_calendar c WHERE c.day_number=1914;
CREATE TABLE mart.m5_forecast_snaive7_28d AS SELECT 'pilot sentinel' AS unchanged;
CREATE TABLE mart.m5_forecast_weekday4_28d AS SELECT 'pilot sentinel' AS unchanged;
"""

    def fixture(name,input_mutation='',saved_mutation='',reject_creation=False,reject_validation=False,reference=None,no_overwrite=False):
        expected=baseline if reference is None else reference
        with tempfile.TemporaryDirectory(prefix='full-baselines-fixture-',dir=tmp_root) as value:
            folder=Path(value).resolve()
            assert folder.is_relative_to(tmp_root)
            database=folder/'fixture.duckdb'
            def execute(text):
                return subprocess.run([args.duckdb,str(database),'-bail','-json'],input="SET threads=2; SET memory_limit='2GB';\n"+text,
                                      text=True,encoding='utf-8',capture_output=True)
            setup=execute(fixture_setup+input_mutation)
            assert setup.returncode==0,(name,setup.stderr)
            run=execute(fixture_build)
            if reject_creation:
                assert run.returncode!=0 and 'Full catalog baseline creation blocked' in run.stderr,(name,run.stderr)
                result=execute("SELECT COUNT(*) AS n FROM information_schema.tables WHERE table_schema='mart' AND table_name='m5_forecast_baselines_all_28d';")
                assert json.loads(result.stdout)[0]['n']==0
            else:
                assert run.returncode==0,(name,run.stderr)
                if no_overwrite:
                    repeat=execute(fixture_build)
                    assert repeat.returncode!=0 and 'already exists' in repeat.stderr
                before=folder/'before.csv'
                run=execute(saved_mutation+copy(FORECAST_QUERY,before))
                assert run.returncode==0,(name,run.stderr)
                before_hash=sha256(before)
                run=execute(fixture_validation)
                if reject_validation:
                    assert run.returncode!=0 and 'Full catalog baseline validation blocked' in run.stderr,(name,run.stderr)
                else:
                    assert run.returncode==0,(name,run.stderr)
                    observed_report=canonical_report(json.loads(run.stdout,parse_float=Decimal))
                    wanted_report=reference_report(expected,calendar)
                    assert observed_report==wanted_report,(name,observed_report,wanted_report)
                    compared=stream_compare(before,COLUMNS,reference_rows(expected,calendar))
                    assert compared['rows']==896
                    if name=='distinct_products_stores_and_zero_inclusive_quarters':
                        first=[r[-1] for r in reference_rows(expected,calendar) if r[0]=='WEEKDAY4' and r[1]=='DEVELOPMENT_1' and r[2:4]==('P001','S1')]
                        assert first==['3.25','4.50','0.00','2.75','1.25','2.50','5.75']*4
                    if name=='integer_maximum_inputs_use_wide_exact_arithmetic':
                        assert all(r[-1]=='2147483647.00' and r[-2]==(2147483647 if r[0]=='SNAIVE7' else 8589934588)
                                   for r in reference_rows(expected,calendar))
                    if name=='later_origin_inputs_do_not_change_earlier_forecasts':
                        base=list(reference_rows(baseline,calendar));changed=list(reference_rows(expected,calendar))
                        assert [r for r in base if r[1]=='DEVELOPMENT_1']==[r for r in changed if r[1]=='DEVELOPMENT_1']
                        assert [r for r in base if r[1]=='DEVELOPMENT_2']!=[r for r in changed if r[1]=='DEVELOPMENT_2']
                run=execute(copy(FORECAST_QUERY,before))
                assert run.returncode==0 and sha256(before)==before_hash
            sentinel=execute("SELECT * FROM mart.m5_forecast_snaive7_28d UNION ALL SELECT * FROM mart.m5_forecast_weekday4_28d;")
            assert json.loads(sentinel.stdout)==[{'unchanged':'pilot sentinel'}]*2
        assert not folder.exists()
        cases.append(dict(case=name,passed=True,creation_rejected=reject_creation,validation_rejected=reject_validation,private_database_removed=True))

    fixture('distinct_products_stores_and_zero_inclusive_quarters',no_overwrite=True)
    fixture('all_zero_series_and_forecast_positions_retained','UPDATE mart.m5_sales_daily SET units=0 WHERE d<>\'d_1914\';',
            reference={k:array('I',[0]*112) for k in baseline})
    fixture('integer_maximum_inputs_use_wide_exact_arithmetic',"UPDATE mart.m5_sales_daily SET units=2147483647 WHERE d<>'d_1914';",
            reference={k:array('I',[2147483647]*112) for k in baseline})
    changed={k:array('I',v) for k,v in baseline.items()}
    for values in changed.values():
        values[28:49]=array('I',[99]*21)
    fixture('later_origin_inputs_do_not_change_earlier_forecasts',"UPDATE mart.m5_sales_daily SET units=99 WHERE TRY_CAST(SUBSTR(d,3) AS INTEGER) BETWEEN 1830 AND 1850;",reference=changed)
    fixture('final_holdout_records_removed_without_effect',"DELETE FROM mart.m5_sales_daily WHERE d='d_1914';")
    fixture('balanced_missing_duplicate_global_roster_rejected',"DELETE FROM raw.m5_sales_wide WHERE item_id='P001' AND store_id='S1'; INSERT INTO raw.m5_sales_wide SELECT * FROM raw.m5_sales_wide WHERE item_id='P001' AND store_id='S2';",reject_creation=True)
    fixture('balanced_missing_duplicate_recent_day_rejected',"DELETE FROM mart.m5_sales_daily WHERE item_id='P001' AND store_id='S1' AND d='d_1802'; INSERT INTO mart.m5_sales_daily SELECT * FROM mart.m5_sales_daily WHERE item_id='P001' AND store_id='S1' AND d='d_1803';",reject_creation=True)
    fixture('negative_recent_units_rejected',"UPDATE mart.m5_sales_daily SET units=-1 WHERE d='d_1802';",reject_creation=True)
    fixture('recent_date_mapping_corruption_rejected',"UPDATE mart.m5_sales_daily SET date=date+1 WHERE d='d_1802';",reject_creation=True)
    fixture('empty_recent_inputs_rejected',"DELETE FROM mart.m5_sales_daily;",reject_creation=True)
    fixture('stored_total_preserving_forecast_swap_rejected',saved_mutation=f"UPDATE {TABLE} SET predicted_units=CASE WHEN horizon_day=1 THEN 4.50 ELSE 3.25 END WHERE model='WEEKDAY4' AND origin='DEVELOPMENT_1' AND item_id='P001' AND store_id='S1' AND horizon_day IN (1,2);",reject_validation=True)
    fixture('stored_balanced_missing_duplicate_key_rejected',saved_mutation=f"DELETE FROM {TABLE} WHERE model='SNAIVE7' AND origin='DEVELOPMENT_1' AND item_id='P001' AND store_id='S1' AND horizon_day=1; INSERT INTO {TABLE} SELECT * FROM {TABLE} WHERE model='SNAIVE7' AND origin='DEVELOPMENT_1' AND item_id='P001' AND store_id='S1' AND horizon_day=2;",reject_validation=True)
    fixture('stored_wrong_decimal_schema_rejected',saved_mutation=f'ALTER TABLE {TABLE} ALTER COLUMN predicted_units TYPE DECIMAL(20,2);',reject_validation=True)
    print(json.dumps({'fixture_cases_passed':len(cases)}),flush=True)
    if args.fixtures_only:
        return

    timings={}
    sources=[Path('D:/database/m5-forecasting-accuracy')/name for name in ('sales_train_evaluation.csv','calendar.csv','sell_prices.csv')]
    registry=json.loads((root/'data/m5_source_audit.json').read_text(encoding='utf-8'))
    source_hashes={p.name:sha256(p) for p in sources}
    assert all(source_hashes[p.name]==registry['files'][p.name]['sha256'] for p in sources)
    started=time.perf_counter()
    calendar,old_metadata,products,stores,department,store,pilot_pairs,pilot_training=original_reference(sources[0],sources[1])
    metadata,recent=source_recent(sources[0])
    assert metadata==old_metadata
    expected_report=reference_report(recent,calendar)
    expected_s7=s7_reference(department,pilot_pairs,pilot_training,calendar)
    expected_w4=w4_reference(department,pilot_pairs,pilot_training,calendar)
    timings['independent_source_reference_seconds']=round(time.perf_counter()-started,3)
    print(json.dumps({'source_reference_ready':True,'recent_rows':len(recent)*112,'full_forecast_rows':len(recent)*224}),flush=True)
    pilot_scripts={n:(root/f'sql/{name}').read_text(encoding='utf-8') for n,name in
                   ((34,'34_build_seasonal_naive_forecasts.sql'),(35,'35_build_weekday_mean_forecasts.sql'))}
    prerequisites=['sql/08_stage_calendar.sql','sql/12_build_product_dimension.sql','sql/13_build_store_dimension.sql','sql/14_build_calendar_dimension.sql']
    recent_columns=','.join(f'd_{n}' for n in range(1802,1914))
    early_columns=','.join(f'd_{n}' for n in range(1,1802))
    with tempfile.TemporaryDirectory(prefix='full-baselines-source-',dir=tmp_root) as value:
        folder=Path(value).resolve()
        assert folder.is_relative_to(tmp_root)
        database=folder/'preflight.duckdb'
        settings=f"SET threads=2; SET memory_limit='2GB'; SET temp_directory={quote((folder/'spill').as_posix())};\n"
        def execute(text,label=None):
            started=time.perf_counter()
            run=subprocess.run([args.duckdb,str(database),'-bail','-json'],input=settings+text,text=True,encoding='utf-8',capture_output=True)
            assert run.returncode==0,run.stderr
            if label:
                timings[label]=round(time.perf_counter()-started,3)
                print(json.dumps({'completed':label,'seconds':timings[label]}),flush=True)
            return json.loads(run.stdout,parse_float=Decimal) if run.stdout.strip() else None
        setup=f"""CREATE SCHEMA raw; CREATE SCHEMA mart;
CREATE TABLE raw.m5_sales_wide AS SELECT item_id,dept_id,cat_id,store_id,state_id FROM read_csv({quote(sources[0].as_posix())},header=true,all_varchar=true);
CREATE TABLE raw.m5_calendar AS SELECT * FROM read_csv({quote(sources[1].as_posix())},header=true,all_varchar=true);
"""
        setup+='\n'.join((root/p).read_text(encoding='utf-8').split('-- VALIDATION:')[0] for p in prerequisites)
        setup+=f"""CREATE TABLE raw.recent_wide AS SELECT item_id,store_id,{recent_columns}
FROM read_csv({quote(sources[0].as_posix())},header=true,all_varchar=true);
CREATE TABLE raw.pilot_early_wide AS SELECT item_id,store_id,{early_columns}
FROM read_csv({quote(sources[0].as_posix())},header=true,all_varchar=true)
WHERE dept_id={quote(department)} AND store_id={quote(store)};
CREATE TABLE mart.m5_sales_daily AS
WITH u AS (
SELECT item_id,store_id,d,units_text FROM raw.recent_wide UNPIVOT INCLUDE NULLS (units_text FOR d IN ({recent_columns}))
UNION ALL
SELECT item_id,store_id,d,units_text FROM raw.pilot_early_wide UNPIVOT INCLUDE NULLS (units_text FOR d IN ({early_columns})))
SELECT u.item_id,u.store_id,u.d,c.date,c.wm_yr_wk,
CASE WHEN regexp_full_match(u.units_text,'[0-9]+') AND TRY_CAST(u.units_text AS INTEGER)>=0
THEN CAST(u.units_text AS INTEGER) ELSE error('Source inputs violate INTEGER contract') END AS units
FROM u JOIN core.m5_calendar c USING(d);
"""
        before,exports_before=export_snapshots(folder,'before')
        after,exports_after=export_snapshots(folder,'after')
        before['full_recent_projection']=folder/'before-recent.csv'
        after['full_recent_projection']=folder/'after-recent.csv'
        exports_before+=copy(RECENT_QUERY,before['full_recent_projection'])
        exports_after+=copy(RECENT_QUERY,after['full_recent_projection'])
        execute(setup+exports_before,'private_setup_and_input_export_seconds')
        counts={}
        counts['products']=compare_csv(before['product_dimension'],['item_id','dept_id','cat_id'],products,'products')
        counts['stores']=compare_csv(before['store_dimension'],['store_id','state_id'],stores,'stores')
        counts['calendar']=compare_csv(before['calendar_projection'],['d','date','day_number','wm_yr_wk'],
                                     ((calendar[n][k] for k in ('d','date','day_number','wm_yr_wk')) for n in range(1,1970)),'calendar')
        counts['metadata']=compare_csv(before['raw_metadata_projection'],METADATA_FIELDS,
                                     sorted(metadata,key=lambda r:(r[0],r[3],r[1],r[2],r[4])),'metadata')
        def daily_reference():
            for (item,selected_store),values in sorted(recent.items()):
                for day,units in enumerate(values,1802):
                    yield item,selected_store,f'd_{day}',calendar[day]['date'],calendar[day]['wm_yr_wk'],units
        recent_comparison=stream_compare(before['full_recent_projection'],DAILY_FIELDS,daily_reference())
        assert recent_comparison['rows']==3414880
        counts['pilot_training']=compare_csv(before['selected_training_projection'],DAILY_FIELDS,
            ((item,selected_store,f'd_{n}',calendar[n]['date'],calendar[n]['wm_yr_wk'],units)
             for item,selected_store in sorted(pilot_pairs) for n,units in enumerate(pilot_training[item],1)),'pilot training')
        assert counts['pilot_training']==413208
        pilot_files={}
        pilot_results={}
        pilot_fingerprints={}
        for number,model,columns,query,reference,reader,normalize in (
                (34,'SNAIVE7',S7_COLUMNS,S7_QUERY,expected_s7,s7_read,lambda rows:rows),
                (35,'WEEKDAY4',W4_COLUMNS,W4_QUERY,expected_w4,w4_read,w4_canonical_forecasts)):
            creation,check=pilot_scripts[number].split('-- VALIDATION:',1)
            execute(creation,f'pilot_{model}_creation_seconds')
            summary=execute('-- VALIDATION:'+check,f'pilot_{model}_validation_seconds')
            summary=(s7_canonical_report if number==34 else w4_canonical_report)(summary)
            expected_summary=(s7_report if number==34 else w4_report)(department,store,pilot_pairs,pilot_training,calendar,reference)
            assert summary==expected_summary
            filename='seasonal_naive_forecasts' if number==34 else 'weekday_mean_forecasts'
            acceptance=json.loads((root/f'data/{filename}_learner_acceptance.json').read_text(encoding='utf-8'))
            accepted_preflight=json.loads((root/f'data/{filename}_preflight.json').read_text(encoding='utf-8'))
            assert json_hash(summary)==acceptance['ordered_result_sha256']
            path=folder/f'{model}-before.csv'
            execute(copy(query,path))
            assert compare_csv(path,columns,(tuple(row[k] for k in columns) for row in reference),model)==24192
            observed=reader(path)
            assert observed==reference
            fingerprint=json_hash(normalize(observed))
            assert fingerprint==accepted_preflight['ordered_forecast_rows_sha256']
            pilot_files[model]=(path,query,sha256(path))
            pilot_results[model]=json_hash(summary)
            pilot_fingerprints[model]=fingerprint
        execute(build,'full_forecast_creation_seconds')
        forecast_path=folder/'full-forecasts.csv'
        execute(copy(FORECAST_QUERY,forecast_path),'full_forecast_export_seconds')
        started=time.perf_counter()
        forecast_comparison=stream_compare(forecast_path,COLUMNS,reference_rows(recent,calendar))
        assert forecast_comparison['rows']==6829760
        timings['all_forecast_fields_stream_comparison_seconds']=round(time.perf_counter()-started,3)
        print(json.dumps({'full_forecast_stream_compared':forecast_comparison['rows']}),flush=True)
        saved_hash=sha256(forecast_path)
        results=canonical_report(execute(validation,'saved_full_forecast_validation_seconds'))
        assert results==expected_report
        overlap={}
        for model,reference in [('SNAIVE7',expected_s7),('WEEKDAY4',expected_w4)]:
            path=folder/f'{model}-overlap.csv'
            query=FORECAST_QUERY.replace(' ORDER BY',f" WHERE model={quote(model)} AND item_id IN (SELECT item_id FROM core.m5_product WHERE dept_id={quote(department)}) AND store_id={quote(store)} ORDER BY")
            execute(copy(query,path))
            def mapped_pilot():
                for row in reference:
                    yield (row['model'],row['origin'],row['item_id'],row['store_id'],row['train_end_day'],row['train_end'],
                           row['horizon_day'],row['forecast_day'],row['forecast_date'],
                           row['source_day'] if model=='SNAIVE7' else row['source_first_day'],
                           row['source_day'] if model=='SNAIVE7' else row['source_last_day'],
                           1 if model=='SNAIVE7' else row['source_observations'],
                           row['predicted_units'] if model=='SNAIVE7' else row['source_units_sum'],
                           format(Decimal(row['predicted_units']),'.2f'))
            overlap[model]=stream_compare(path,COLUMNS,mapped_pilot())
            assert overlap[model]['rows']==24192
        execute(exports_after+copy(FORECAST_QUERY,forecast_path),'unchanged_inputs_and_full_forecast_export_seconds')
        assert sha256(forecast_path)==saved_hash
        before_hashes={k:sha256(p) for k,p in before.items()}
        after_hashes={k:sha256(p) for k,p in after.items()}
        assert before_hashes==after_hashes
        pilot_csv_hashes={}
        for model,(path,query,old_hash) in pilot_files.items():
            execute(copy(query,path))
            assert sha256(path)==old_hash
            pilot_csv_hashes[model]=old_hash
        database_bytes=database.stat().st_size
    assert not folder.exists()
    assert all(sha256(p)==source_hashes[p.name] for p in sources)
    assert all(sha256(root/p)==value for p,value in pinned.items())
    evidence=dict(checked_at_utc=datetime.now(timezone.utc).isoformat(),executor='assistant',
        engine=subprocess.check_output([args.duckdb,'-version'],text=True).strip(),
        script=sql_path.relative_to(root).as_posix(),script_sha256=sha256(sql_path),
        frozen_protocol=protocol.relative_to(root).as_posix(),frozen_protocol_sha256=sha256(protocol),
        repository_dependency_sha256=pinned,repository_dependencies_unchanged=True,
        source_sha256=source_hashes,source_hashes_unchanged=True,
        private_database='Private DuckDB and detail CSV files only within resolved repository tmp; learner database never opened.',
        temporary_baseline_removed=True,temporary_database_bytes_after_close=database_bytes,
        settings={'threads':2,'memory_limit':'2GB'},
        scope={'products':len(products),'stores':len(stores),'series_count':len(recent),
               'departments':len({p[1] for p in products}),'categories':len({p[2] for p in products}),
               'states':len({s[1] for s in stores}),'series_membership_sha256':membership_hash(recent),'metadata_sha256':metadata_hash(metadata),
               'definition':'Complete released retrospective catalog product x store roster; no sales, active-assortment or performance filter.'},
        recent_input_first_day=1802,recent_input_last_day=1913,recent_input_distinct_days=112,
        recent_input_comparison=recent_comparison,full_forecast_comparison=forecast_comparison,
        comparison_fingerprint_method='SHA256 of UTF-8 canonical field strings separated by TAB, each row followed by LF, excluding header. Forecast order: train_end_day,model,item_id,store_id,horizon_day. Prediction fields have exactly two decimals; dates use ISO. Recent input order: item_id,store_id,numeric day. No detail records are published.',
        compact_reference_quantity_storage='30490 arrays of 112 unsigned 32-bit integers; forecast rows generated one at a time; no millions-of-dictionaries forecast collection.',
        independent_reference='Python csv reads metadata and only d1802..d1913 quantities for the full roster. Four consecutive seven-day blocks independently yield SNAIVE7 last-block values and WEEKDAY4 column sums divided using Decimal. Each seven-value pattern repeats four times. Existing unmodified helpers separately reconstruct the pilot from its original d1..d1913 inputs. Final target values are discarded without inspection.',
        table=TABLE,table_grain=['model','origin','item_id','store_id','horizon_day'],table_columns=COLUMNS,
        table_rows=forecast_comparison['rows'],saved_schema_and_row_multiplicity_verified=True,
        pilot_full_field_comparison={'SNAIVE7':{'rows':24192,'columns':13,'field_mismatches':0},'WEEKDAY4':{'rows':24192,'columns':15,'field_mismatches':0}},
        pilot_training_rows_compared=counts['pilot_training'],pilot_training_columns_compared=6,pilot_training_field_mismatches=0,
        pilot_accepted_report_sha256=pilot_results,pilot_accepted_forecast_sha256=pilot_fingerprints,
        full_catalog_pilot_overlap=overlap,pilot_tables_unchanged=True,
        pilot_table_csv_sha256_before=pilot_csv_hashes,pilot_table_csv_sha256_after=pilot_csv_hashes,
        input_projection_row_counts=counts,input_projection_sha256_before=before_hashes,input_projection_sha256_after=after_hashes,
        input_projections_unchanged=True,full_forecast_csv_sha256_before_validation=saved_hash,
        full_forecast_csv_sha256_after_validation=saved_hash,saved_validation_read_only=True,
        result_rows=len(results),result_columns=len(REPORT_COLUMNS),rows_with_pass_status=8,output_columns=REPORT_COLUMNS,
        results=results,ordered_result_sha256=json_hash(results),result_field_mismatches=0,
        fixture_cases_passed=len(cases),fixture_cases=cases,timings=timings,
        final_holdout_unit_values_inspected=False,forecast_errors_computed=False,full_history_rmsse_scales_audited=False,
        final_model_selected=False,existing_full_forecast_table_never_overwritten=True,
        real_product_identifiers_published=False,individual_forecasts_published=False,
        evidence_scope='Assistant preflight of recent-input construction and full saved forecast fields; learner SQL38 execution pending. Logical 112-day selection does not guarantee a 112-day-only physical scan. Full training-history coverage and RMSSE scales are not established by this step; final calendar coverage is not target-outcome coverage.')
    serialized=json.dumps(evidence,ensure_ascii=False,indent=2)+'\n'
    assert all(item not in serialized for item,_,_ in products)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(serialized,encoding='utf-8',newline='\n')
    print(json.dumps({'fixture_cases_passed':len(cases),'table_rows':forecast_comparison['rows'],'results':results,
                      'ordered_forecast_rows_sha256':forecast_comparison['observed_sha256'],'timings':timings}),flush=True)


if __name__=='__main__':
    main()
