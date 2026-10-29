"""Stream full-catalog development errors against original CSV history in a private DuckDB."""
import argparse
from array import array
import csv
from datetime import datetime, timedelta, timezone
from decimal import Decimal, localcontext
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time

sys.dont_write_bytecode=True
from preflight_forecast_scope_and_time_audit import FIRST_DATE,ORIGINS,METADATA_FIELDS,quote,sha256,json_hash,membership_hash,compare_csv,SNAPSHOTS
from preflight_full_catalog_baseline_forecasts import (
    TABLE,COLUMNS as FORECAST_COLUMNS,FORECAST_QUERY,MEMBERSHIP,METADATA,metadata_hash,
    reference_rows as forecast_reference,reference_report as forecast_report,
    canonical_report as canonical_forecast_report,stream_compare,copy,
)
from preflight_development_forecast_errors import SCORED_COLUMNS,DIAGNOSTIC_COLUMNS,REPORT_COLUMNS,six,canonical_report,ABS_TOL,REL_TOL

MAP_QUERY="SELECT CAST(ROW_NUMBER() OVER(ORDER BY item_id,store_id) AS INTEGER) AS series_index,item_id,store_id FROM core.m5_product CROSS JOIN core.m5_store"
HISTORY_QUERY=f"""WITH catalog AS ({MAP_QUERY})
SELECT s.series_index,TRY_CAST(SUBSTR(f.d,3) AS INTEGER) AS day_number,f.units
FROM mart.m5_sales_daily f LEFT JOIN catalog s USING(item_id,store_id)
WHERE regexp_full_match(f.d,'d_[1-9][0-9]*') AND TRY_CAST(SUBSTR(f.d,3) AS INTEGER) BETWEEN 1 AND 1913
ORDER BY s.series_index,day_number,f.units"""
MAPPING_QUERY="""SELECT COUNT(*) AS checked_rows,COUNT(*) FILTER(WHERE c.d IS NULL OR f.date IS DISTINCT FROM c.date
OR f.wm_yr_wk IS DISTINCT FROM c.wm_yr_wk) AS mapping_errors
FROM mart.m5_sales_daily f LEFT JOIN core.m5_calendar c USING(d)
WHERE regexp_full_match(f.d,'d_[1-9][0-9]*') AND TRY_CAST(SUBSTR(f.d,3) AS INTEGER) BETWEEN 1 AND 1913"""


def original_inputs(sales,calendar_path):
    calendar={}
    with calendar_path.open(newline='',encoding='utf-8-sig') as stream:
        for row in csv.DictReader(stream):
            assert re.fullmatch(r'd_[1-9][0-9]*',row['d'])
            n=int(row['d'][2:])
            assert n not in calendar and 1<=n<=1969
            assert row['date']==(FIRST_DATE+timedelta(days=n-1)).isoformat()
            assert re.fullmatch(r'[1-9][0-9]{4}',row['wm_yr_wk'])
            calendar[n]=dict(d=row['d'],date=row['date'],day_number=n,wm_yr_wk=int(row['wm_yr_wk']))
    assert set(calendar)==set(range(1,1970))
    metadata,history=[],{}
    with sales.open(newline='',encoding='utf-8-sig') as stream:
        reader=csv.reader(stream);header=next(reader)
        assert header[:6]==['id','item_id','dept_id','cat_id','store_id','state_id']
        assert header[6:1919]==[f'd_{n}' for n in range(1,1914)]
        for row in reader:
            meta=tuple(row[1:6]);key=(row[1],row[4])
            assert all(re.fullmatch(r'[A-Z0-9_]+',v) for v in meta) and key not in history
            metadata.append(meta)
            # CSV tokenization sees the record; no field d1914 or later is inspected or converted.
            values=row[6:1919]
            assert len(values)==1913 and all(v.isascii() and v.isdecimal() for v in values)
            units=array('I',(int(v) for v in values))
            assert units.itemsize==4 and max(units)<=2147483647
            history[key]=units
    assert len(history)==30490 and membership_hash(history)==MEMBERSHIP and metadata_hash(metadata)==METADATA
    return calendar,metadata,history


class Reference:
    """Packed histories, one-pass integer scale prefixes, and streamed errors/diagnostics."""
    def __init__(self,history,calendar,pilot_pairs=()):
        self.history,self.calendar,self.pairs=history,calendar,sorted(history)
        self.pilot_pairs=set(pilot_pairs)
        self.scales={}
        for key,values in history.items():
            first=None;sse=0;previous=0;scales=[]
            for day,units in enumerate(values[:1885],1):
                if first is None:
                    if units>0:first=day
                else:sse+=(units-previous)**2
                if day in (1829,1857,1885):
                    scales.append((first,None if first is None else day-first,None if first is None else sse))
                previous=units
            self.scales[key]=scales
        self.reports=[];self.status_summary=[];self.macros=[];self.pilot_reports=[];self.pilot_exact=[]

    def quarter_pattern(self,key,last,model):
        weeks=[self.history[key][start:start+7] for start in range(last-28,last,7)]
        return [4*v for v in weeks[-1]] if model=='SNAIVE7' else [sum(v) for v in zip(*weeks)]

    def scored(self):
        for origin,last in ORIGINS[:3]:
            for model in ('SNAIVE7','WEEKDAY4'):
                for item,store in self.pairs:
                    pattern=self.quarter_pattern((item,store),last,model)*4
                    for horizon,prediction in enumerate(pattern,1):
                        actual=self.history[item,store][last+horizon-1];q=prediction-4*actual
                        yield (origin,model,item,store,horizon,last+horizon,self.calendar[last+horizon]['date'],
                               actual,prediction,q,abs(q),q*q)

    @staticmethod
    def empty_totals():
        return dict(series=0,actual=0,prediction=0,absolute=0,signed=0,valid=0,root_sum=Decimal(0))

    @staticmethod
    def accumulate(t,row):
        t['series']+=1;t['actual']+=row[9];t['prediction']+=row[10];t['absolute']+=row[11];t['signed']+=row[12]
        if row[15] is not None:t['valid']+=1;t['root_sum']+=row[15]

    @staticmethod
    def report(origin,model,t):
        n=t['series']*28
        macro=None if not t['valid'] else t['root_sum']/t['valid']
        return dict(origin=origin,model=model,series_count=t['series'],evaluated_rows=n,actual_units=t['actual'],
                    predicted_units=format(Decimal(t['prediction'])/4,'.2f'),mae=six(Decimal(t['absolute'])/(4*n)),
                    mean_error=six(Decimal(t['signed'])/(4*n)),rmsse_valid_series=t['valid'],
                    rmsse_undefined_series=t['series']-t['valid'],macro_rmsse=six(macro),check_status='PASS')

    def diagnostics(self):
        self.reports=[];self.status_summary=[];self.macros=[];self.pilot_reports=[];self.pilot_exact=[]
        with localcontext() as ctx:
            ctx.prec=70
            for index,(origin,last) in enumerate(ORIGINS[:3]):
                for model in ('SNAIVE7','WEEKDAY4'):
                    totals=self.empty_totals();pilot=self.empty_totals();statuses={}
                    for item,store in self.pairs:
                        key=(item,store);first,count,scale=self.scales[key][index]
                        status=('no_positive_training' if first is None else 'insufficient_retained_history' if count<1
                                else 'zero_scale' if scale==0 else 'VALID')
                        actual=self.history[key][last:last+28]
                        predictions=self.quarter_pattern(key,last,model)*4
                        errors=[p-4*a for p,a in zip(predictions,actual)]
                        sse=sum(q*q for q in errors)
                        root=None if status!='VALID' else (Decimal(sse)/Decimal(16*28)/(Decimal(scale)/Decimal(count))).sqrt()
                        row=(origin,model,item,store,last,first,count,scale,28,sum(actual),sum(predictions),
                             sum(abs(q) for q in errors),sum(errors),sse,status,root)
                        self.accumulate(totals,row)
                        self.accumulate(statuses.setdefault(status,self.empty_totals()),row)
                        if key in self.pilot_pairs:
                            self.accumulate(pilot,row)
                            self.pilot_exact.append(dict(zip(DIAGNOSTIC_COLUMNS[:-1],row[:-1])))
                        yield row
                    self.reports.append(self.report(origin,model,totals))
                    self.macros.append((origin,model,None if not totals['valid'] else totals['root_sum']/totals['valid']))
                    if pilot['series']:self.pilot_reports.append(self.report(origin,model,pilot))
                    for status,t in sorted(statuses.items()):
                        positions=t['series']*28
                        self.status_summary.append(dict(origin=origin,model=model,rmsse_status=status,series_count=t['series'],
                            evaluated_rows=positions,mae=six(Decimal(t['absolute'])/(4*positions)),mean_error=six(Decimal(t['signed'])/(4*positions))))


def combined_export(sql,path):
    """One execution consumes all internal streams and the literal user report, avoiding repeated LAG passes."""
    prefix,report=sql.split('-- REPORT:',1)
    report=report[report.index('\nSELECT '):].strip().rstrip(';')
    prefix=prefix.rstrip()+', user_report AS ('+report+')\n'
    parts=[]
    for kind,fields,source in [('DIAGNOSTIC',DIAGNOSTIC_COLUMNS,'series_diagnostics'),('ERROR',SCORED_COLUMNS,'scored_rows'),
                             ('MACRO',['origin','model','macro_rmsse'],'report_totals'),('REPORT',REPORT_COLUMNS,'user_report')]:
        values=[f'CAST({field} AS VARCHAR) AS c{i+1}' for i,field in enumerate(fields)]
        values += [f'NULL::VARCHAR AS c{i}' for i in range(len(fields)+1,17)]
        parts.append(f"SELECT '{kind}' AS record_kind,"+','.join(values)+' FROM '+source)
    query=prefix+'SELECT * FROM ('+' UNION ALL '.join(parts)+') outputs ORDER BY record_kind,c1,c2,c3,c4,TRY_CAST(c5 AS INTEGER)'
    return copy(query,path)


def compare_combined(path,reference):
    generators={'DIAGNOSTIC':iter(reference.diagnostics()),'ERROR':iter(reference.scored())}
    observed_hash={key:hashlib.sha256() for key in generators};expected_hash={key:hashlib.sha256() for key in generators}
    counts={key:0 for key in generators};root_max=macro_max=Decimal(0);reports=[];macros=[]
    with localcontext() as ctx:
        ctx.prec=70
        with path.open(newline='',encoding='utf-8') as stream:
            reader=csv.reader(stream);assert next(reader)==['record_kind']+[f'c{i}' for i in range(1,17)]
            for row in reader:
                kind=row[0];values=row[1:]
                if kind in generators:
                    expected=next(generators[kind],None);assert expected is not None,(kind,'extra row')
                    width=15 if kind=='DIAGNOSTIC' else 12
                    wanted=['' if v is None else str(v) for v in expected[:width]]
                    assert values[:width]==wanted,(kind,counts[kind],'exact field mismatch')
                    for hashes,fields in ((observed_hash,values[:width]),(expected_hash,wanted)):
                        hashes[kind].update(('\t'.join(fields)+'\n').encode('utf-8'))
                    if kind=='DIAGNOSTIC':
                        actual=None if values[15]=='' else Decimal(values[15]);target=expected[15]
                        assert (actual is None)==(target is None)
                        if target is not None:
                            error=abs(actual-target);assert actual.is_finite() and error<=ABS_TOL+REL_TOL*abs(target)
                            root_max=max(root_max,error)
                    counts[kind]+=1
                elif kind=='MACRO':macros.append(values[:3])
                elif kind=='REPORT':reports.append(dict(zip(REPORT_COLUMNS,values[:12])))
                else:raise AssertionError('Unexpected internal record kind')
        for key,generator in generators.items():assert next(generator,None) is None,(key,'missing row')
        assert len(macros)==6 and len(reports)==6
        for got,expected in zip(macros,reference.macros):
            assert got[:2]==list(expected[:2])
            actual=None if got[2]=='' else Decimal(got[2]);target=expected[2]
            assert (actual is None)==(target is None)
            if target is not None:
                error=abs(actual-target);assert actual.is_finite() and error<=ABS_TOL+REL_TOL*abs(target)
                macro_max=max(macro_max,error)
        for row in reports:
            if row['macro_rmsse']=='':row['macro_rmsse']=None
        reports=canonical_report(reports)
        assert reports==reference.reports,'Six aggregate report rows differ'
    evidence={key:dict(rows=counts[key],columns=16 if key=='DIAGNOSTIC' else 12,exact_columns=15 if key=='DIAGNOSTIC' else 12,
        exact_field_mismatches=0,observed_exact_sha256=observed_hash[key].hexdigest(),independent_exact_sha256=expected_hash[key].hexdigest()) for key in counts}
    assert all(v['observed_exact_sha256']==v['independent_exact_sha256'] for v in evidence.values())
    return evidence,str(root_max),str(macro_max),reports


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--duckdb',required=True);parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--fixtures-only',action='store_true');args=parser.parse_args()
    root=Path(__file__).resolve().parents[1];tmp=(root/'tmp').resolve();tmp.mkdir(exist_ok=True)
    assert tmp.is_relative_to(root.resolve())
    sql_path=root/'sql/39_compare_full_catalog_development_errors.sql';sql=sql_path.read_text(encoding='utf-8')
    baseline_path=root/'sql/38_build_full_catalog_baseline_forecasts.sql';baseline_sql=baseline_path.read_text(encoding='utf-8')
    baseline_build,baseline_validation=baseline_sql.split('-- VALIDATION:',1)
    prefix=baseline_validation[baseline_validation.index('WITH parameters AS ('):baseline_validation.index('\nSELECT o.origin,m.model,s.series_count')]
    assert sql.count(prefix)==1
    protocol=root/'docs/FULL_CATALOG_DEVELOPMENT_ERRORS_PROTOCOL.md';assert protocol.exists()
    helpers=['validation/preflight_forecast_scope_and_time_audit.py','validation/preflight_seasonal_naive_forecasts.py',
             'validation/preflight_weekday_mean_forecasts.py','validation/preflight_development_forecast_errors.py',
             'validation/preflight_full_catalog_baseline_forecasts.py']
    prerequisites=['sql/08_stage_calendar.sql','sql/12_build_product_dimension.sql','sql/13_build_store_dimension.sql','sql/14_build_calendar_dimension.sql']
    paths=[sql_path,baseline_path,Path(__file__),protocol,root/'docs/EVALUATION_PLAN.md',root/'docs/FULL_CATALOG_BASELINE_FORECASTS_PROTOCOL.md',root/'data/m5_source_audit.json']
    paths += [root/p for p in helpers+prerequisites]+list((root/'data').glob('*_preflight.json'))+list((root/'data').glob('*_learner_acceptance.json'))
    pinned={p.relative_to(root).as_posix():sha256(p) for p in paths if p.name!='full_catalog_development_errors_preflight.json'}
    calendar={n:dict(date=(FIRST_DATE+timedelta(days=n-1)).isoformat()) for n in range(1,1970)}
    metadata=[(item,'DEPT','CAT',store,state) for item in ('P001','P002') for store,state in (('S1','A'),('S2','B'))]
    base={('P001','S1'):array('I',[0]*1826+[2,0,2]+[1]*84),('P001','S2'):array('I',[2]*1913),
          ('P002','S1'):array('I',[0]*1828+[5]+[n%3 for n in range(84)]),
          ('P002','S2'):array('I',[0]*1829+[3]+[n%4 for n in range(83)])}
    def adapt(text):
        return text.replace('3049 AS expected_products,10 AS expected_stores','2 AS expected_products,2 AS expected_stores').replace(
            '30490 AS expected_scope_series','4 AS expected_scope_series').replace(MEMBERSHIP,membership_hash(base)).replace(METADATA,metadata_hash(metadata))
    fixture_query,fixture_build=adapt(sql),adapt(baseline_build)
    cases=[];fixture_metrics={}
    def fixture(name,history=None,mutation='',candidate_mutation='',reject=False,remove_future=False):
        history=base if history is None else history
        reference=Reference(history,calendar)
        with tempfile.TemporaryDirectory(prefix='full-errors-fixture-',dir=tmp) as value:
            folder=Path(value).resolve();assert folder.is_relative_to(tmp)
            database=folder/'fixture.duckdb'
            def execute(text):
                return subprocess.run([args.duckdb,str(database),'-bail','-json'],input="SET threads=2; SET memory_limit='2GB';\n"+text,text=True,encoding='utf-8',capture_output=True)
            setup="""CREATE SCHEMA raw; CREATE SCHEMA core; CREATE SCHEMA mart;
CREATE TABLE core.m5_product(item_id VARCHAR,dept_id VARCHAR,cat_id VARCHAR);
INSERT INTO core.m5_product VALUES ('P001','DEPT','CAT'),('P002','DEPT','CAT');
CREATE TABLE core.m5_store(store_id VARCHAR,state_id VARCHAR); INSERT INTO core.m5_store VALUES ('S1','A'),('S2','B');
CREATE TABLE raw.m5_sales_wide AS SELECT item_id,dept_id,cat_id,store_id,state_id FROM core.m5_product CROSS JOIN core.m5_store;
CREATE TABLE core.m5_calendar AS SELECT 'd_'||CAST(n AS VARCHAR) AS d,DATE '2011-01-29'+CAST(n AS INTEGER)-1 AS date,
CAST(n AS INTEGER) AS day_number,CAST(11000+n//7 AS INTEGER) AS wm_yr_wk FROM range(1,1970) t(n);
CREATE TABLE mart.m5_sales_daily(item_id VARCHAR,store_id VARCHAR,d VARCHAR,date DATE,wm_yr_wk INTEGER,units INTEGER);
"""
            for (item,store),values in history.items():
                tuples=','.join(f'({n},{v})' for n,v in enumerate(values,1))
                setup+=f"INSERT INTO mart.m5_sales_daily SELECT {quote(item)},{quote(store)},c.d,c.date,c.wm_yr_wk,t.units FROM (VALUES {tuples}) t(n,units) JOIN core.m5_calendar c ON c.day_number=t.n;\n"
            if not remove_future:
                setup+="INSERT INTO mart.m5_sales_daily SELECT p.item_id,s.store_id,c.d,c.date,c.wm_yr_wk,-999 FROM core.m5_product p CROSS JOIN core.m5_store s CROSS JOIN core.m5_calendar c WHERE c.day_number=1914;"
            run=execute(setup+fixture_build+mutation+candidate_mutation);assert run.returncode==0,(name,run.stderr)
            candidate=folder/'candidate.csv';run=execute(copy(FORECAST_QUERY,candidate));assert run.returncode==0
            before=sha256(candidate)
            output=folder/'outputs.csv';run=execute(combined_export(fixture_query,output))
            if reject:
                assert run.returncode!=0 and 'Full catalog development comparison blocked' in run.stderr,(name,run.stderr)
            else:
                assert run.returncode==0,(name,run.stderr)
                comparisons,_,_,results=compare_combined(output,reference)
                assert comparisons['ERROR']['rows']==672 and comparisons['DIAGNOSTIC']['rows']==24
                fixture_metrics[name]=(comparisons,reference)
                if name=='cross_store_first_positive_and_undefined_scales':
                    assert reference.scales['P001','S1'][0]==(1827,2,8)
                    assert {r['rmsse_status'] for r in reference.status_summary if r['origin']=='DEVELOPMENT_1'}=={
                        'VALID','zero_scale','insufficient_retained_history','no_positive_training'}
                if name=='all_zero_history_keeps_mae_and_null_rmsse':
                    assert all(r['mae']=='0.000000' and r['macro_rmsse'] is None and r['rmsse_undefined_series']==4 for r in results)
                if name=='integer_extremes_keep_exact_large_squared_errors':
                    assert max(r[-1] for r in reference.scored())>2**63-1
                if name=='early_scale_change_keeps_forecasts_and_errors':
                    baseline=fixture_metrics['cross_store_first_positive_and_undefined_scales'][0]
                    assert comparisons['ERROR']['observed_exact_sha256']==baseline['ERROR']['observed_exact_sha256']
                    assert comparisons['DIAGNOSTIC']['observed_exact_sha256']!=baseline['DIAGNOSTIC']['observed_exact_sha256']
                if name=='first_positive_after_origin_never_enters_earlier_scale':
                    assert reference.scales['P002','S2'][0]==(None,None,None)
                    assert reference.scales['P002','S2'][1][0]==1850
                if name=='final_holdout_records_removed_without_effect':
                    assert comparisons==fixture_metrics['cross_store_first_positive_and_undefined_scales'][0]
            run=execute(copy(FORECAST_QUERY,candidate));assert run.returncode==0 and sha256(candidate)==before
        assert not folder.exists()
        cases.append(dict(case=name,passed=True,rejected=reject,private_database_removed=True))
    fixture('cross_store_first_positive_and_undefined_scales')
    fixture('all_zero_history_keeps_mae_and_null_rmsse',{k:array('I',[0]*1913) for k in base})
    fixture('integer_extremes_keep_exact_large_squared_errors',{k:array('I',[2147483647 if n%2 else 0 for n in range(1913)]) for k in base})
    changed={k:array('I',v) for k,v in base.items()};changed['P001','S1'][99]=1
    fixture('early_scale_change_keeps_forecasts_and_errors',changed)
    changed={k:array('I',v) for k,v in base.items()};changed['P002','S2'][1829:1849]=array('I',[0]*20);changed['P002','S2'][1849]=3
    fixture('first_positive_after_origin_never_enters_earlier_scale',changed)
    fixture('final_holdout_records_removed_without_effect',remove_future=True)
    fixture('balanced_early_day_loss_and_duplicate_rejected',mutation="DELETE FROM mart.m5_sales_daily WHERE item_id='P001' AND store_id='S1' AND d='d_1'; INSERT INTO mart.m5_sales_daily SELECT * FROM mart.m5_sales_daily WHERE item_id='P001' AND store_id='S1' AND d='d_2';",reject=True)
    fixture('unknown_and_null_early_roster_keys_rejected',mutation="INSERT INTO mart.m5_sales_daily SELECT 'UNKNOWN',store_id,d,date,wm_yr_wk,units FROM mart.m5_sales_daily WHERE item_id='P001' AND store_id='S1' AND d='d_1'; INSERT INTO mart.m5_sales_daily SELECT NULL,store_id,d,date,wm_yr_wk,units FROM mart.m5_sales_daily WHERE item_id='P001' AND store_id='S1' AND d='d_1';",reject=True)
    fixture('early_fact_calendar_mapping_rejected',mutation="UPDATE mart.m5_sales_daily SET date=date+1 WHERE d='d_1';",reject=True)
    fixture('negative_early_training_units_rejected',mutation="UPDATE mart.m5_sales_daily SET units=-1 WHERE d='d_1';",reject=True)
    fixture('damaged_unscored_final_candidate_rejected',candidate_mutation=f"UPDATE {TABLE} SET predicted_units=predicted_units+1 WHERE origin='FINAL_HOLDOUT' AND horizon_day=1;",reject=True)
    print(json.dumps({'fixture_cases_passed':len(cases)}),flush=True)
    if args.fixtures_only:return

    timings={};sources=[Path('D:/database/m5-forecasting-accuracy')/name for name in ('sales_train_evaluation.csv','calendar.csv','sell_prices.csv')]
    registry=json.loads((root/'data/m5_source_audit.json').read_text(encoding='utf-8'))
    source_hashes={p.name:sha256(p) for p in sources};assert all(source_hashes[p.name]==registry['files'][p.name]['sha256'] for p in sources)
    started=time.perf_counter();calendar,metadata,history=original_inputs(sources[0],sources[1])
    products=sorted({r[:3] for r in metadata});stores=sorted({r[3:] for r in metadata})
    department=min(p[1] for p in products);store=min(s[0] for s in stores)
    pilot_pairs=[(p[0],store) for p in products if p[1]==department]
    assert len(pilot_pairs)==216
    reference=Reference(history,calendar,pilot_pairs)
    recent={key:array('I',values[1801:1913]) for key,values in history.items()}
    timings['independent_source_and_scale_reference_seconds']=round(time.perf_counter()-started,3)
    print(json.dumps({'source_reference_ready':True,'history_rows':len(history)*1913,'packed_history_bytes':sum(len(v)*v.itemsize for v in history.values())}),flush=True)
    with tempfile.TemporaryDirectory(prefix='full-errors-source-',dir=tmp) as value:
        folder=Path(value).resolve();assert folder.is_relative_to(tmp)
        database=folder/'preflight.duckdb'
        settings=f"SET threads=2; SET memory_limit='2GB'; SET temp_directory={quote((folder/'spill').as_posix())};\n"
        def execute(text,label=None):
            started=time.perf_counter();run=subprocess.run([args.duckdb,str(database),'-bail','-json'],input=settings+text,text=True,encoding='utf-8',capture_output=True)
            assert run.returncode==0,run.stderr
            if label:
                timings[label]=round(time.perf_counter()-started,3);print(json.dumps({'completed':label,'seconds':timings[label]}),flush=True)
            return json.loads(run.stdout,parse_float=Decimal) if run.stdout.strip() else None
        days=','.join(f'd_{n}' for n in range(1,1914))
        setup=f"""CREATE SCHEMA raw; CREATE SCHEMA mart;
CREATE TABLE raw.m5_sales_wide AS SELECT item_id,dept_id,cat_id,store_id,state_id FROM read_csv({quote(sources[0].as_posix())},header=true,all_varchar=true);
CREATE TABLE raw.m5_calendar AS SELECT * FROM read_csv({quote(sources[1].as_posix())},header=true,all_varchar=true);
"""+'\n'.join((root/p).read_text(encoding='utf-8').split('-- VALIDATION:')[0] for p in prerequisites)
        setup+=f"""CREATE TABLE raw.training_wide AS SELECT item_id,store_id,{days} FROM read_csv({quote(sources[0].as_posix())},header=true,all_varchar=true);
CREATE TABLE mart.m5_sales_daily AS
WITH u AS (SELECT item_id,store_id,d,units_text FROM raw.training_wide UNPIVOT INCLUDE NULLS (units_text FOR d IN ({days})))
SELECT u.item_id,u.store_id,u.d,c.date,c.wm_yr_wk,
CASE WHEN regexp_full_match(u.units_text,'[0-9]+') AND TRY_CAST(u.units_text AS INTEGER)>=0
THEN CAST(u.units_text AS INTEGER) ELSE error('Source history violates INTEGER contract') END AS units
FROM u JOIN core.m5_calendar c USING(d);
"""
        snapshot_queries={key:query for key,query in SNAPSHOTS.items() if key!='selected_training_projection'}
        snapshot_queries['series_index_mapping']=MAP_QUERY+' ORDER BY series_index'
        snapshot_queries['indexed_history']=HISTORY_QUERY
        before={k:folder/(k+'.csv') for k in snapshot_queries}
        export=''.join(copy(query,before[key]) for key,query in snapshot_queries.items())
        execute(setup+export,'private_full_history_setup_and_export_seconds')
        counts={}
        counts['product_dimension']=compare_csv(before['product_dimension'],['item_id','dept_id','cat_id'],products,'products')
        counts['store_dimension']=compare_csv(before['store_dimension'],['store_id','state_id'],stores,'stores')
        counts['calendar_projection']=compare_csv(before['calendar_projection'],['d','date','day_number','wm_yr_wk'],
            ((calendar[n][k] for k in ('d','date','day_number','wm_yr_wk')) for n in range(1,1970)),'calendar')
        counts['raw_metadata_projection']=compare_csv(before['raw_metadata_projection'],METADATA_FIELDS,sorted(metadata,key=lambda r:(r[0],r[3],r[1],r[2],r[4])),'metadata')
        map_comparison=stream_compare(before['series_index_mapping'],['series_index','item_id','store_id'],
                                     ((i,*pair) for i,pair in enumerate(sorted(history),1)))
        started=time.perf_counter()
        history_comparison=stream_compare(before['indexed_history'],['series_index','day_number','units'],
            ((i,day,units) for i,pair in enumerate(sorted(history),1) for day,units in enumerate(history[pair],1)))
        assert history_comparison['rows']==58327370 and map_comparison['rows']==30490
        timings['indexed_history_stream_comparison_seconds']=round(time.perf_counter()-started,3)
        mapping_before=execute(MAPPING_QUERY);assert mapping_before==[{'checked_rows':58327370,'mapping_errors':0}]
        before_hashes={k:sha256(p) for k,p in before.items()}
        print(json.dumps({'history_stream_compared':history_comparison['rows'],'all_fact_calendar_mappings_valid':True}),flush=True)
        execute(baseline_build,'full_candidate_reconstruction_seconds')
        forecast_summary=canonical_forecast_report(execute('-- VALIDATION:'+baseline_validation,'accepted_full_candidate_validation_seconds'))
        assert forecast_summary==forecast_report(recent,calendar)
        accepted=json.loads((root/'data/full_catalog_baseline_forecasts_learner_acceptance.json').read_text(encoding='utf-8'))
        accepted_preflight=json.loads((root/'data/full_catalog_baseline_forecasts_preflight.json').read_text(encoding='utf-8'))
        assert json_hash(forecast_summary)==accepted['ordered_result_sha256']
        candidate=folder/'full-candidates.csv';execute(copy(FORECAST_QUERY,candidate),'full_candidate_export_seconds')
        forecast_comparison=stream_compare(candidate,FORECAST_COLUMNS,forecast_reference(recent,calendar))
        assert forecast_comparison['rows']==6829760
        assert forecast_comparison['observed_sha256']==accepted_preflight['full_forecast_comparison']['observed_sha256']
        candidate_before=sha256(candidate)
        outputs=folder/'error-diagnostic-report.csv'
        execute(combined_export(sql,outputs),'full_history_audit_scales_scoring_and_export_seconds')
        started=time.perf_counter();comparisons,root_max,macro_max,results=compare_combined(outputs,reference)
        timings['error_diagnostic_reference_comparison_seconds']=round(time.perf_counter()-started,3)
        assert comparisons['ERROR']['rows']==5122320 and comparisons['DIAGNOSTIC']['rows']==182940
        old=json.loads((root/'data/development_forecast_errors_preflight.json').read_text(encoding='utf-8'))
        old_acceptance=json.loads((root/'data/development_forecast_errors_learner_acceptance.json').read_text(encoding='utf-8'))
        assert json_hash(reference.pilot_exact)==old['ordered_exact_series_diagnostics_sha256']
        assert json_hash(reference.pilot_reports)==old_acceptance['ordered_result_sha256']
        print(json.dumps({'errors_and_diagnostics_compared':True,'pilot_results_reconciled':True}),flush=True)
        execute(export+copy(FORECAST_QUERY,candidate),'unchanged_inputs_candidates_export_seconds')
        after_hashes={k:sha256(p) for k,p in before.items()};assert after_hashes==before_hashes
        assert sha256(candidate)==candidate_before
        mapping_after=execute(MAPPING_QUERY);assert mapping_after==mapping_before
        database_bytes=database.stat().st_size
    assert not folder.exists()
    assert all(sha256(p)==source_hashes[p.name] for p in sources)
    assert all(sha256(root/p)==value for p,value in pinned.items())
    evidence=dict(checked_at_utc=datetime.now(timezone.utc).isoformat(),executor='assistant',engine=subprocess.check_output([args.duckdb,'-version'],text=True).strip(),
        script=sql_path.relative_to(root).as_posix(),script_sha256=sha256(sql_path),frozen_protocol=protocol.relative_to(root).as_posix(),frozen_protocol_sha256=sha256(protocol),
        repository_dependency_sha256=pinned,repository_dependencies_unchanged=True,source_sha256=source_hashes,source_hashes_unchanged=True,
        exact_sql38_candidate_validation_prefix_copies=1,exact_sql38_candidate_validation_prefix_sha256=hashlib.sha256(prefix.encode()).hexdigest(),
        scope={'series_count':30490,'products':len(products),'stores':len(stores),'series_membership_sha256':membership_hash(history)},
        settings={'threads':2,'memory_limit':'2GB'},private_database='Private temporary database and detailed CSV exports under resolved repository tmp; learner database never opened.',
        temporary_baseline_removed=True,temporary_database_bytes_after_close=database_bytes,packed_history_quantity_bytes=sum(len(v)*v.itemsize for v in history.values()),
        training_first_day=1,training_last_day=1913,series_index_map_comparison=map_comparison,indexed_history_comparison=history_comparison,
        history_direct_fields=['series_index','day_number','units'],separate_fact_calendar_mapping_before=mapping_before,separate_fact_calendar_mapping_after=mapping_after,
        history_comparison_scope='Every indexed history key and integer quantity is directly compared. The complete independent index/item/store map and calendar projection are separately compared; all 58,327,370 fact date/week mappings are checked against that calendar before and after. This is not a six-field history CSV comparison.',
        saved_candidate_comparison=forecast_comparison,accepted_sql38_report_sha256=json_hash(forecast_summary),accepted_sql38_forecast_fingerprint_matched=True,
        scored_rows_comparison=comparisons['ERROR'],series_diagnostics_comparison=comparisons['DIAGNOSTIC'],
        rmsse_numeric_reference={'precision_digits':70,'absolute_tolerance':str(ABS_TOL),'relative_tolerance':str(REL_TOL),
            'maximum_series_absolute_difference':root_max,'maximum_macro_absolute_difference':macro_max,'null_statuses_compared_exactly':True},
        comparison_fingerprint_method='SHA256 of TAB-separated canonical field strings with LF after every ordered row, no header. History order: series_index,day_number. Errors/diagnostics: origin,model,item_id,store_id,then horizon where present. Empty string represents NULL. Diagnostic fingerprints include all 15 exact fields, excluding the floating RMSSE which is independently checked against Decimal-70.',
        independent_reference='Python csv inspects only original d1..d1913 quantities and stores compact uint32 arrays. One Python loop records first-positive and integer successive-difference SSE at each development cutoff. Four seven-day blocks independently reconstruct both unchanged baseline formulas; exact errors and per-series Decimal-70 roots stream through comparison. The complete SQL report and internal outputs are exported together from one guarded execution.',
        result_rows=6,result_columns=12,output_columns=REPORT_COLUMNS,results=results,rows_with_pass_status=6,ordered_result_sha256=json_hash(results),result_field_mismatches=0,
        rmsse_status_summary=reference.status_summary,pilot_series_count=216,pilot_diagnostic_rows_compared=len(reference.pilot_exact),
        pilot_exact_diagnostics_sha256=json_hash(reference.pilot_exact),pilot_accepted_report_sha256=json_hash(reference.pilot_reports),pilot_previous_evidence_matched=True,
        prior_pilot_tables_rebuilt=False,sql39_has_no_table_writes=True,input_projection_row_counts=counts,
        input_projection_sha256_before=before_hashes,input_projection_sha256_after=after_hashes,input_projections_unchanged=True,
        candidate_csv_sha256_before=candidate_before,candidate_csv_sha256_after=candidate_before,saved_candidate_unchanged=True,
        fixture_cases_passed=len(cases),fixture_cases=cases,timings=timings,
        final_holdout_unit_values_inspected=False,final_holdout_errors_computed=False,final_model_selected=False,
        real_product_identifiers_published=False,individual_errors_or_diagnostics_published=False,
        evidence_scope='Assistant full-catalog development preflight only; learner SQL39 execution pending. All series contribute to MAE and bias; macro RMSSE excludes undefined scales and their coverage is separately reported. Timings refer to this private execution, not a promised learner runtime. All sources, saved candidates, prior evidence and fixed protocols remain unchanged.')
    serialized=json.dumps(evidence,indent=2,ensure_ascii=False)+'\n'
    assert all(item not in serialized for item,_,_ in products)
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(serialized,encoding='utf-8',newline='\n')
    print(json.dumps({'fixture_cases_passed':len(cases),'results':results,'rmsse_status_summary':reference.status_summary,
        'ordered_result_sha256':json_hash(results),'timings':timings}),flush=True)


if __name__=='__main__':main()
