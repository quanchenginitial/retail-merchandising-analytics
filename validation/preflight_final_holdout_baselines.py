"""Verify the frozen final evaluation once, in a private database after a public protocol commit."""
import argparse
from array import array
import csv
from datetime import datetime,timedelta,timezone
from decimal import Decimal,localcontext
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time

sys.dont_write_bytecode=True
from preflight_store_forecast_errors import (
    FIRST_DATE,ORIGINS,METADATA_FIELDS,quote,sha256,json_hash,membership_hash,compare_csv,SNAPSHOTS,
    TABLE,FORECAST_COLUMNS,FORECAST_QUERY,MEMBERSHIP,METADATA,metadata_hash,forecast_reference,forecast_report,
    canonical_forecast_report,stream_compare,copy,Reference,original_inputs,MAP_QUERY,HISTORY_QUERY,MAPPING_QUERY,
    DIAGNOSTIC_COLUMNS,ERROR_REPORT_COLUMNS,ABS_TOL,REL_TOL,six,exact_pair_hash,DEPARTMENT_MAP_QUERY,STORE_MAP_QUERY,
    combined_export as store_export,compare_store,literal_report,
)
from preflight_development_forecast_errors import SCORED_COLUMNS

PROTOCOL_SHA='ad621241d935f9fe14d4ec491a527b332dfe8ff27b3439d11239eaa4f8212669'
FREEZE_COMMIT='6d270efb8c06bc06632f6e3a400066cb11e3d626'
TARGET_QUERY=HISTORY_QUERY.replace('BETWEEN 1 AND 1913','BETWEEN 1914 AND 1941')
TARGET_MAPPING_QUERY=MAPPING_QUERY.replace('BETWEEN 1 AND 1913','BETWEEN 1914 AND 1941')
STATUS_COLUMNS=['origin','model','rmsse_status','series_count','evaluated_rows','absolute_error_quarters','error_quarters']
REPORT_COLUMNS=ERROR_REPORT_COLUMNS


def original_targets(path,history):
    """Only called after the explicit public-freeze gate; inspect the final 28 quantities separately."""
    targets={}
    with path.open(newline='',encoding='utf-8-sig') as stream:
        reader=csv.reader(stream);header=next(reader)
        assert header[1919:1947]==[f'd_{n}' for n in range(1914,1942)]
        for row in reader:
            key=(row[1],row[4]);assert key in history and key not in targets
            fields=row[1919:1947];assert len(fields)==28 and all(v.isascii() and v.isdecimal() for v in fields)
            values=array('I',(int(v) for v in fields));assert max(values)<=2147483647
            targets[key]=values
    assert targets.keys()==history.keys()
    return targets


class FinalReference:
    def __init__(self,development,targets):
        self.source=development;self.targets=targets;self.scales={}
        for key,values in development.history.items():
            first=next((day for day,value in enumerate(values,1) if value>0),None)
            retained=[] if first is None else values[first-1:1913]
            sse=None if first is None else sum((b-a)**2 for a,b in zip(retained,retained[1:]))
            self.scales[key]=(first,None if first is None else 1913-first,sse)
        self.reports=[];self.macros=[];self.statuses=[];self.status_summary=[]

    def errors(self):
        for model in ('SNAIVE7','WEEKDAY4'):
            for item,store in self.source.pairs:
                predictions=self.source.quarter_pattern((item,store),1913,model)*4
                for h,(prediction,actual) in enumerate(zip(predictions,self.targets[item,store]),1):
                    q=prediction-4*actual
                    yield ('FINAL_HOLDOUT',model,item,store,h,1913+h,self.source.calendar[1913+h]['date'],actual,prediction,q,abs(q),q*q)

    def diagnostics(self):
        self.reports=[];self.macros=[];self.statuses=[];self.status_summary=[]
        with localcontext() as ctx:
            ctx.prec=70
            for model in ('SNAIVE7','WEEKDAY4'):
                totals=Reference.empty_totals();statuses={}
                for item,store in self.source.pairs:
                    key=(item,store);first,count,sse=self.scales[key]
                    status='no_positive_training' if first is None else 'insufficient_retained_history' if count<1 else 'zero_scale' if sse==0 else 'VALID'
                    predictions=self.source.quarter_pattern(key,1913,model)*4;actual=self.targets[key]
                    errors=[p-4*a for p,a in zip(predictions,actual)];squared=sum(q*q for q in errors)
                    root=None if status!='VALID' else (Decimal(squared)/Decimal(16*28)/(Decimal(sse)/Decimal(count))).sqrt()
                    row=('FINAL_HOLDOUT',model,item,store,1913,first,count,sse,28,sum(actual),sum(predictions),sum(abs(q) for q in errors),sum(errors),squared,status,root)
                    Reference.accumulate(totals,row);Reference.accumulate(statuses.setdefault(status,Reference.empty_totals()),row)
                    yield row
                self.reports.append(Reference.report('FINAL_HOLDOUT',model,totals))
                self.macros.append(('FINAL_HOLDOUT',model,totals['root_sum'] if totals['valid'] else None,
                                    totals['root_sum']/totals['valid'] if totals['valid'] else None))
                for status,t in sorted(statuses.items()):
                    self.statuses.append(('FINAL_HOLDOUT',model,status,t['series'],t['series']*28,t['absolute'],t['signed']))
                    self.status_summary.append(dict(origin='FINAL_HOLDOUT',model=model,rmsse_status=status,series_count=t['series'],
                        evaluated_rows=t['series']*28,mae=six(Decimal(t['absolute'])/(112*t['series'])),mean_error=six(Decimal(t['signed'])/(112*t['series']))))


def combined_export(sql,sql42,sql41,sql40,sql39,path):
    # Preserve the literal earlier export construction, adding only the new final streams.
    prior=store_export(sql42,sql41,sql40,sql39,path)
    old_prefix=sql42.split('-- REPORT:',1)[0].rstrip();new_prefix=sql.split('-- REPORT:',1)[0].rstrip()
    assert prior.count(old_prefix)==1;query=prior.replace(old_prefix,new_prefix,1)
    marker="\nSELECT * FROM (SELECT 'ASSIGNED' AS record_kind,"
    assert query.count(marker)==1
    query=query.replace(marker,', final_user_report AS ('+literal_report(sql)+')'+marker,1)
    streams=[('FINAL_DIAGNOSTIC',DIAGNOSTIC_COLUMNS,'final_series_diagnostics'),('FINAL_ERROR',SCORED_COLUMNS,'final_scored_rows'),
        ('FINAL_MACRO',['origin','model','rmsse_sum','macro_rmsse'],
         '(SELECT origin,model,SUM(rmsse) AS rmsse_sum,AVG(rmsse) AS macro_rmsse FROM final_series_diagnostics GROUP BY origin,model) x'),
        ('FINAL_STATUS',STATUS_COLUMNS,'final_status_totals'),('FINAL_REPORT',REPORT_COLUMNS,'final_user_report')]
    parts=[]
    for kind,fields,source in streams:
        values=[f'CAST({field} AS VARCHAR) AS c{i+1}' for i,field in enumerate(fields)]+[f'NULL::VARCHAR AS c{i}' for i in range(len(fields)+1,19)]
        parts.append(f"SELECT '{kind}' AS record_kind,"+','.join(values)+' FROM '+source)
    marker=') outputs ORDER BY record_kind,c1,c2,c3,c4'
    assert query.count(marker)==1
    return query.replace(marker,' UNION ALL '+' UNION ALL '.join(parts)+marker+',TRY_CAST(c5 AS INTEGER)',1)


def compare_final(path,reference,development,departments,states,prior_path):
    generators={'FINAL_DIAGNOSTIC':iter(reference.diagnostics()),'FINAL_ERROR':iter(reference.errors())}
    observed={k:hashlib.sha256() for k in generators};wanted_hash={k:hashlib.sha256() for k in generators};counts={k:0 for k in generators}
    maximum_root=maximum_sum=maximum_macro=Decimal(0);collected={k:[] for k in ('FINAL_MACRO','FINAL_STATUS','FINAL_REPORT')}
    with localcontext() as ctx:
        ctx.prec=70
        with path.open(newline='',encoding='utf-8') as source,prior_path.open('w',newline='',encoding='utf-8') as target:
            reader=csv.reader(source);header=next(reader);assert header==['record_kind']+[f'c{i}' for i in range(1,19)]
            writer=csv.writer(target);writer.writerow(header)
            for record in reader:
                kind=record[0];row=record[1:]
                if kind in generators:
                    expected=next(generators[kind],None);assert expected is not None
                    width=15 if kind=='FINAL_DIAGNOSTIC' else 12
                    wanted=['' if v is None else str(v) for v in expected[:width]]
                    assert row[:width]==wanted,(kind,counts[kind],'exact mismatch')
                    observed[kind].update(('\t'.join(row[:width])+'\n').encode());wanted_hash[kind].update(('\t'.join(wanted)+'\n').encode())
                    if kind=='FINAL_DIAGNOSTIC':
                        value=None if row[15]=='' else Decimal(row[15]);goal=expected[15]
                        assert (value is None)==(goal is None)
                        if goal is not None:
                            error=abs(value-goal);assert value.is_finite() and error<=ABS_TOL+REL_TOL*abs(goal);maximum_root=max(maximum_root,error)
                    counts[kind]+=1
                elif kind in collected:collected[kind].append(row)
                else:writer.writerow(record)
        for generator in generators.values():assert next(generator,None) is None
        assert len(collected['FINAL_MACRO'])==len(collected['FINAL_REPORT'])==2
        assert [tuple(r[:7]) for r in collected['FINAL_STATUS']]==[tuple(str(v) for v in r) for r in reference.statuses]
        for row,expected in zip(collected['FINAL_MACRO'],reference.macros):
            assert row[:2]==list(expected[:2])
            for i in (2,3):
                value=None if row[i]=='' else Decimal(row[i]);goal=expected[i];assert (value is None)==(goal is None)
                if goal is not None:
                    error=abs(value-goal);assert value.is_finite() and error<=ABS_TOL+REL_TOL*abs(goal)
                    if i==2:maximum_sum=max(maximum_sum,error)
                    else:maximum_macro=max(maximum_macro,error)
        results=[]
        for row in collected['FINAL_REPORT']:
            d=dict(zip(REPORT_COLUMNS,row[:12]))
            for k in ('series_count','evaluated_rows','actual_units','rmsse_valid_series','rmsse_undefined_series'):d[k]=int(d[k])
            assert re.fullmatch(r'[0-9]+\.[0-9]{2}',d['predicted_units'])
            for k in ('mae','mean_error','macro_rmsse'):
                assert d[k]=='' or re.fullmatch(r'-?[0-9]+\.[0-9]{6}',d[k])
                d[k]=None if d[k]=='' else six(Decimal(d[k]))
            results.append(d)
        assert results==reference.reports
    comparisons={k:dict(rows=counts[k],columns=16 if k=='FINAL_DIAGNOSTIC' else 12,exact_columns=15 if k=='FINAL_DIAGNOSTIC' else 12,
        exact_field_mismatches=0,observed_exact_sha256=observed[k].hexdigest(),independent_exact_sha256=wanted_hash[k].hexdigest()) for k in generators}
    assert all(d['observed_exact_sha256']==d['independent_exact_sha256'] for d in comparisons.values())
    prior=compare_store(prior_path,development,departments,states,prior_path.with_name('preserved-department.csv'))
    return comparisons,results,dict(maximum_root_absolute_difference=str(maximum_root),maximum_root_sum_absolute_difference=str(maximum_sum),
        maximum_macro_absolute_difference=str(maximum_macro)),prior

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--duckdb',required=True)
    parser.add_argument('--output',required=True,type=Path);parser.add_argument('--fixtures-only',action='store_true');parser.add_argument('--public-freeze-commit');args=parser.parse_args()
    if not args.fixtures_only:assert args.public_freeze_commit==FREEZE_COMMIT,'Public freeze commit required before reading final quantities'
    root=Path(__file__).resolve().parents[1];tmp=(root/'tmp').resolve();tmp.mkdir(exist_ok=True);assert tmp.is_relative_to(root.resolve())
    sql_path=root/'sql/43_evaluate_final_holdout_baselines.sql';sql=sql_path.read_text(encoding='utf-8')
    path42=root/'sql/42_compare_store_forecast_errors.sql';sql42=path42.read_text(encoding='utf-8')
    path41=root/'sql/41_compare_department_forecast_errors.sql';sql41=path41.read_text(encoding='utf-8')
    path40=root/'sql/40_compare_full_catalog_paired_improvement.sql';sql40=path40.read_text(encoding='utf-8')
    path39=root/'sql/39_compare_full_catalog_development_errors.sql';sql39=path39.read_text(encoding='utf-8')
    prefix42=sql42[sql42.index('WITH parameters AS ('):sql42.index('-- REPORT:')];assert sql.count(prefix42)==1
    baseline_path=root/'sql/38_build_full_catalog_baseline_forecasts.sql';baseline_sql=baseline_path.read_text(encoding='utf-8')
    baseline_build,baseline_validation=baseline_sql.split('-- VALIDATION:',1)
    protocol=root/'docs/FINAL_HOLDOUT_BASELINE_PROTOCOL.md';assert protocol.exists() and sha256(protocol)==PROTOCOL_SHA
    helpers=['validation/preflight_forecast_scope_and_time_audit.py','validation/preflight_seasonal_naive_forecasts.py',
        'validation/preflight_weekday_mean_forecasts.py','validation/preflight_development_forecast_errors.py',
        'validation/preflight_series_forecast_improvements.py','validation/preflight_full_catalog_baseline_forecasts.py',
        'validation/preflight_full_catalog_development_errors.py','validation/preflight_full_catalog_paired_improvement.py','validation/preflight_department_forecast_errors.py','validation/preflight_store_forecast_errors.py']
    prerequisites=['sql/08_stage_calendar.sql','sql/12_build_product_dimension.sql','sql/13_build_store_dimension.sql','sql/14_build_calendar_dimension.sql']
    paths=[sql_path,path42,path41,path40,path39,baseline_path,Path(__file__),protocol,root/'docs/EVALUATION_PLAN.md',root/'data/m5_source_audit.json']
    paths += [root/p for p in helpers+prerequisites]+list((root/'docs').glob('*_PROTOCOL.md'))+list((root/'data').glob('*_preflight.json'))+list((root/'data').glob('*_learner_acceptance.json'))
    inherited_pins=json.loads((root/'data/store_forecast_errors_preflight.json').read_text(encoding='utf-8'))['repository_dependency_sha256']
    assert all(sha256(root/p)==value for p,value in inherited_pins.items())
    paths += [root/p for p in inherited_pins]
    pinned={p.relative_to(root).as_posix():sha256(p) for p in paths if p.name!='final_holdout_baselines_preflight.json'}
    calendar={n:dict(date=(FIRST_DATE+timedelta(days=n-1)).isoformat()) for n in range(1,1970)}
    base={(item,store):array('I',[1+n%2 for n in range(1913)]) for item in ('P001','P002') for store in ('S1','S2')}
    weeks={('P001','S1'):[0,1,2,4],('P001','S2'):[0,0,0,0],('P002','S1'):[0,2,4,6],('P002','S2'):[1,1,4,7]}
    targets={key:array('I',[actual]*28) for key,actual in zip(sorted(base),(1,0,4,3))}
    for key,values in base.items():values[1885:1913]=array('I',[v for week in weeks[key] for v in [week]*7])
    cases=[]
    def fixture(name,history=None,actuals=None,mutations=None,change_targets=False):
        history=base if history is None else history;actuals=targets if actuals is None else actuals
        items=sorted({p[0] for p in history});stores=sorted({p[1] for p in history})
        departments={item:'DEPT_'+item for item in items};states={store:'STATE' for store in stores}
        metadata=[(item,departments[item],'CAT',store,states[store]) for item,store in sorted(history)]
        assert len(history)==len(items)*len(stores)
        def adapt(text):
            return text.replace('3049 AS expected_products,10 AS expected_stores',f'{len(items)} AS expected_products,{len(stores)} AS expected_stores').replace(
                '30490 AS expected_scope_series',f'{len(history)} AS expected_scope_series').replace(MEMBERSHIP,membership_hash(history)).replace(METADATA,metadata_hash(metadata)).replace(
                '7 AS expected_departments',f'{len(items)} AS expected_departments')
        subcases=[]
        with tempfile.TemporaryDirectory(prefix='final-baselines-fixture-',dir=tmp) as value:
            folder=Path(value).resolve();assert folder.is_relative_to(tmp);database=folder/'fixture.duckdb'
            def execute(text):
                return subprocess.run([args.duckdb,str(database),'-bail','-json'],input="SET threads=2; SET memory_limit='2GB';\n"+text,text=True,encoding='utf-8',capture_output=True)
            setup="CREATE SCHEMA raw; CREATE SCHEMA core; CREATE SCHEMA mart; CREATE TABLE core.m5_product(item_id VARCHAR,dept_id VARCHAR,cat_id VARCHAR);"
            setup+='INSERT INTO core.m5_product VALUES '+','.join(f"({quote(item)},{quote(departments[item])},'CAT')" for item in items)+';'
            setup+="CREATE TABLE core.m5_store(store_id VARCHAR,state_id VARCHAR); INSERT INTO core.m5_store VALUES "+','.join(f"({quote(store)},'STATE')" for store in stores)+';'
            setup+="""CREATE TABLE raw.m5_sales_wide AS SELECT item_id,dept_id,cat_id,store_id,state_id FROM core.m5_product CROSS JOIN core.m5_store;
CREATE TABLE core.m5_calendar AS SELECT 'd_'||CAST(n AS VARCHAR) AS d,DATE '2011-01-29'+CAST(n AS INTEGER)-1 AS date,
CAST(n AS INTEGER) AS day_number,CAST(11000+n//7 AS INTEGER) AS wm_yr_wk FROM range(1,1970) t(n);
CREATE TABLE mart.m5_sales_daily(item_id VARCHAR,store_id VARCHAR,d VARCHAR,date DATE,wm_yr_wk INTEGER,units INTEGER);
"""
            for (item,store),values in history.items():
                combined=list(values)+list(actuals[item,store]);tuples=','.join(f'({n},{v})' for n,v in enumerate(combined,1))
                setup+=f"INSERT INTO mart.m5_sales_daily SELECT {quote(item)},{quote(store)},c.d,c.date,c.wm_yr_wk,t.units FROM (VALUES {tuples}) t(n,units) JOIN core.m5_calendar c ON c.day_number=t.n;"
            setup+="INSERT INTO mart.m5_sales_daily SELECT p.item_id,s.store_id,c.d,c.date,c.wm_yr_wk,-999 FROM core.m5_product p CROSS JOIN core.m5_store s CROSS JOIN core.m5_calendar c WHERE c.day_number=1942;"
            run=execute(setup+adapt(baseline_build));assert run.returncode==0,(name,run.stderr)
            if name=='hand_metrics_fractional_zero_and_store_keys':
                plan=execute('EXPLAIN (FORMAT JSON) '+adapt(sql));assert plan.returncode==0,plan.stderr
                plan_text=plan.stdout  # CLI prints a plan heading before the FORMAT JSON payload.
                assert plan_text.count('LAG(units)')==1,'The historical lag must be shared by development and final scales'
            candidate=folder/'candidate.csv';run=execute(copy(FORECAST_QUERY,candidate));assert run.returncode==0;before=sha256(candidate)
            if mutations:
                for label,mutation in mutations:
                    run=execute('BEGIN TRANSACTION;'+mutation+adapt(sql))
                    assert run.returncode!=0 and 'Final holdout evaluation blocked' in run.stderr,(name,label,run.stderr)
                    subcases.append(dict(subcase=label,passed=True,rejected=True))
            else:
                def verify(target_values,label):
                    ref=Reference(history,calendar);final=FinalReference(ref,target_values);output=folder/'combined.csv'
                    run=execute(combined_export(adapt(sql),adapt(sql42),adapt(sql41),adapt(sql40),adapt(sql39),output));assert run.returncode==0,(name,run.stderr)
                    checked,results,numeric,prior=compare_final(output,final,ref,departments,states,folder/'previous.csv')
                    assert checked['FINAL_ERROR']['rows']==2*len(history)*28 and checked['FINAL_DIAGNOSTIC']['rows']==2*len(history)
                    subcases.append(dict(subcase=label,passed=True,rejected=False))
                    return results,final,prior,sha256(folder/'previous.csv')
                results,final,prior,old_export=verify(actuals,'base_targets')
                if name=='hand_metrics_fractional_zero_and_store_keys':
                    assert results[0]['mae']=='2.250000' and results[1]['mae']=='0.500000'
                    assert results[0]['mean_error']=='2.250000' and results[1]['mean_error']=='0.000000'
                    assert results[0]['actual_units']==results[1]['actual_units']==224
                if name=='training_only_undefined_scales_and_first_jump':
                    statuses={r['rmsse_status']:r['series_count'] for r in final.status_summary if r['model']=='SNAIVE7'}
                    assert statuses=={'VALID':1,'no_positive_training':1,'insufficient_retained_history':1,'zero_scale':1}
                    assert final.scales['P002','S2']==(1911,2,8)
                if change_targets:
                    changed={key:array('I',[int(v//4) for v in final.source.quarter_pattern(key,1913,'SNAIVE7')]*4) for key in history}
                    run=execute(f"UPDATE mart.m5_sales_daily f SET units=CAST(p.predicted_units AS INTEGER) FROM {TABLE} p WHERE p.origin='FINAL_HOLDOUT' AND p.model='SNAIVE7' AND f.item_id=p.item_id AND f.store_id=p.store_id AND f.d='d_'||CAST(p.forecast_day AS VARCHAR);")
                    assert run.returncode==0
                    changed_results,changed_final,changed_prior,new_export=verify(changed,'selected_model_loses_after_target_mutation')
                    assert changed_final.scales==final.scales
                    # Compare every preserved exact stream/report; numeric roots can differ at insignificant accumulation bits.
                    assert changed_prior[0]['observed_exact_sha256']==prior[0]['observed_exact_sha256']
                    assert changed_prior[1]['observed_exact_sha256']==prior[1]['observed_exact_sha256'] and changed_prior[2]==prior[2]
                    assert changed_prior[4][2]==prior[4][2] and changed_prior[4][4][2:4]==prior[4][4][2:4]
                    assert changed_results[0]['mae']=='0.000000' and Decimal(changed_results[1]['mae'])>0
                    assert changed_results[0]['macro_rmsse']=='0.000000' and Decimal(changed_results[1]['macro_rmsse'])>0
                    assert all(r['check_status']=='PASS' for r in changed_results)
            run=execute(copy(FORECAST_QUERY,candidate));assert run.returncode==0 and sha256(candidate)==before
        assert not folder.exists();cases.append(dict(case=name,passed=True,subcases=subcases,private_database_removed=True))
    fixture('hand_metrics_fractional_zero_and_store_keys')
    fixture('target_mutation_leaves_choice_forecasts_scales_and_development_unchanged',change_targets=True)
    changed={('P001','S1'):array('I',[0]*1913),('P001','S2'):array('I',[0]*1912+[2]),
             ('P002','S1'):array('I',[2]*1913),('P002','S2'):array('I',[0]*1910+[2,0,2])}
    fixture('training_only_undefined_scales_and_first_jump',changed,{key:array('I',[1]*28) for key in changed})
    selected="item_id='P001' AND store_id='S1' AND d='d_1914'"
    fixture('balanced_missing_and_duplicate_targets',mutations=[('balanced_keys',f"DELETE FROM mart.m5_sales_daily WHERE {selected}; INSERT INTO mart.m5_sales_daily SELECT * FROM mart.m5_sales_daily WHERE item_id='P001' AND store_id='S1' AND d='d_1915';")])
    fixture('target_series_and_calendar_integrity',mutations=[
        ('unknown_series',f"UPDATE mart.m5_sales_daily SET item_id='UNKNOWN' WHERE {selected};"),
        ('null_series',f"UPDATE mart.m5_sales_daily SET store_id=NULL WHERE {selected};"),
        ('malformed_extra_day',f"INSERT INTO mart.m5_sales_daily SELECT item_id,store_id,'bad',date,wm_yr_wk,units FROM mart.m5_sales_daily WHERE {selected};"),
        ('wrong_date',f"UPDATE mart.m5_sales_daily SET date=date+1 WHERE {selected};"),
        ('wrong_week',f"UPDATE mart.m5_sales_daily SET wm_yr_wk=99999 WHERE {selected};")])
    fixture('target_unit_contract',mutations=[
        ('null_units',f"UPDATE mart.m5_sales_daily SET units=NULL WHERE {selected};"),
        ('negative_units',f"UPDATE mart.m5_sales_daily SET units=-1 WHERE {selected};"),
        ('fractional_schema',f"ALTER TABLE mart.m5_sales_daily ALTER COLUMN units TYPE DECIMAL(18,2); UPDATE mart.m5_sales_daily SET units=0.5 WHERE {selected};")])
    fixture('damaged_saved_final_candidate',mutations=[('changed_prediction',f"UPDATE {TABLE} SET predicted_units=predicted_units+0.25 WHERE origin='FINAL_HOLDOUT' AND horizon_day=1;")])
    print(json.dumps({'fixture_cases_passed':len(cases),'fixture_subcases_passed':sum(len(c['subcases']) for c in cases)}),flush=True)
    if args.fixtures_only:return
    final_access_started_utc=datetime.now(timezone.utc).isoformat()
    timings={};sources=[Path('D:/database/m5-forecasting-accuracy')/name for name in ('sales_train_evaluation.csv','calendar.csv','sell_prices.csv')]
    registry=json.loads((root/'data/m5_source_audit.json').read_text(encoding='utf-8'))
    source_hashes={p.name:sha256(p) for p in sources};assert all(source_hashes[p.name]==registry['files'][p.name]['sha256'] for p in sources)
    started=time.perf_counter();calendar,metadata,history=original_inputs(sources[0],sources[1])
    targets=original_targets(sources[0],history)
    products=sorted({r[:3] for r in metadata});stores=sorted({r[3:] for r in metadata})
    departments={p[0]:p[1] for p in products}
    states={r[0]:r[1] for r in stores}
    assert len(states)==len(stores)==10 and all(states[row[3]]==row[4] for row in metadata)
    assert all(departments[row[0]]==row[1] for row in metadata)
    department=min(p[1] for p in products);store=min(s[0] for s in stores)
    pilot_pairs=[(p[0],store) for p in products if p[1]==department]
    assert len(pilot_pairs)==216
    reference=Reference(history,calendar,pilot_pairs)
    final_reference=FinalReference(reference,targets)
    recent={key:array('I',values[1801:1913]) for key,values in history.items()}
    timings['independent_source_and_scale_reference_seconds']=round(time.perf_counter()-started,3)
    print(json.dumps({'source_reference_ready':True,'history_rows':len(history)*1913,'packed_history_bytes':sum(len(v)*v.itemsize for v in history.values())}),flush=True)
    with tempfile.TemporaryDirectory(prefix='final-baselines-source-',dir=tmp) as value:
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
        target_days=','.join(f'd_{n}' for n in range(1914,1942))
        setup+=f"""CREATE TABLE raw.final_target_wide AS SELECT item_id,store_id,{target_days} FROM read_csv({quote(sources[0].as_posix())},header=true,all_varchar=true);
INSERT INTO mart.m5_sales_daily
WITH u AS (SELECT item_id,store_id,d,units_text FROM raw.final_target_wide UNPIVOT INCLUDE NULLS (units_text FOR d IN ({target_days})))
SELECT u.item_id,u.store_id,u.d,c.date,c.wm_yr_wk,
CASE WHEN regexp_full_match(u.units_text,'[0-9]+') AND TRY_CAST(u.units_text AS INTEGER)>=0
THEN CAST(u.units_text AS INTEGER) ELSE error('Source final targets violate INTEGER contract') END AS units
FROM u JOIN core.m5_calendar c USING(d);
"""
        snapshot_queries={key:query for key,query in SNAPSHOTS.items() if key!='selected_training_projection'}
        snapshot_queries['series_index_mapping']=MAP_QUERY+' ORDER BY series_index'
        snapshot_queries['indexed_history']=HISTORY_QUERY
        snapshot_queries['department_assignment']=DEPARTMENT_MAP_QUERY
        snapshot_queries['store_state_assignment']=STORE_MAP_QUERY
        snapshot_queries['indexed_final_targets']=TARGET_QUERY
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
        department_map_comparison=stream_compare(before['department_assignment'],['item_id','store_id','dept_id'],
            ((item,selected_store,departments[item]) for item,selected_store in sorted(history)))
        assert department_map_comparison['rows']==30490
        store_map_comparison=stream_compare(before['store_state_assignment'],['store_id','state_id'],sorted(states.items()))
        assert store_map_comparison['rows']==10
        started=time.perf_counter()
        history_comparison=stream_compare(before['indexed_history'],['series_index','day_number','units'],
            ((i,day,units) for i,pair in enumerate(sorted(history),1) for day,units in enumerate(history[pair],1)))
        assert history_comparison['rows']==58327370 and map_comparison['rows']==30490
        target_comparison=stream_compare(before['indexed_final_targets'],['series_index','day_number','units'],
            ((i,day,units) for i,pair in enumerate(sorted(history),1) for day,units in enumerate(targets[pair],1914)))
        assert target_comparison['rows']==853720
        target_mapping_before=execute(TARGET_MAPPING_QUERY);assert target_mapping_before==[{'checked_rows':853720,'mapping_errors':0}]
        timings['indexed_history_and_target_stream_comparison_seconds']=round(time.perf_counter()-started,3)
        mapping_before=execute(MAPPING_QUERY);assert mapping_before==[{'checked_rows':58327370,'mapping_errors':0}]
        before_hashes={k:sha256(p) for k,p in before.items()}
        print(json.dumps({'history_stream_compared':history_comparison['rows'],'final_targets_compared':target_comparison['rows'],'all_fact_calendar_mappings_valid':True}),flush=True)
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
        previous39=json.loads((root/'data/full_catalog_development_errors_preflight.json').read_text(encoding='utf-8'))
        accepted39=json.loads((root/'data/full_catalog_development_errors_learner_acceptance.json').read_text(encoding='utf-8'))
        previous40=json.loads((root/'data/full_catalog_paired_improvement_preflight.json').read_text(encoding='utf-8'))
        accepted40=json.loads((root/'data/full_catalog_paired_improvement_learner_acceptance.json').read_text(encoding='utf-8'))
        assert history_comparison['observed_sha256']==previous40['indexed_history_comparison']['observed_sha256']
        assert map_comparison['observed_sha256']==previous40['series_index_map_comparison']['observed_sha256']
        previous41=json.loads((root/'data/department_forecast_errors_preflight.json').read_text(encoding='utf-8'))
        accepted41=json.loads((root/'data/department_forecast_errors_learner_acceptance.json').read_text(encoding='utf-8'))
        assert sha256(root/'data/department_forecast_errors_learner_acceptance.json')=='c9d794aac6f423ac68b71b25bc2cff2c82aabe7e4b3349997c84b1ea6d7f9bc9'
        previous42=json.loads((root/'data/store_forecast_errors_preflight.json').read_text(encoding='utf-8'))
        accepted42=json.loads((root/'data/store_forecast_errors_learner_acceptance.json').read_text(encoding='utf-8'))
        assert sha256(root/'data/store_forecast_errors_learner_acceptance.json')=='889e002b20167033c37eee53b9f0805599e2297c8aec6df87290dfee16cfbbde'
        output=folder/'final-errors-diagnostics-report.csv'
        execute(combined_export(sql,sql42,sql41,sql40,sql39,output),'guarded_final_and_development_export_seconds')
        started=time.perf_counter()
        final_comparisons,results,final_numeric,store_base=compare_final(output,final_reference,reference,departments,states,folder/'preserved-store-streams.csv')
        assigned_comparison,group_comparison,results42,store_numeric,department_base,store_reference=store_base
        preserved_assigned,preserved_groups,results41,department_numeric,base,department_reference=department_base
        comparisons,paired,results40,results39,maximum,aggregate_max,reconciliation_max=base
        timings['final_errors_diagnostics_and_development_comparison_seconds']=round(time.perf_counter()-started,3)
        assert assigned_comparison['rows']==182940 and group_comparison['rows']==60 and len(results42)==30
        assert len(results)==2 and final_comparisons['FINAL_ERROR']['rows']==1707440 and final_comparisons['FINAL_DIAGNOSTIC']['rows']==60980
        assert assigned_comparison['observed_exact_sha256']==previous42['assigned_diagnostics_comparison']['observed_exact_sha256']
        assert group_comparison['observed_exact_sha256']==previous42['store_group_comparison']['observed_exact_sha256']
        assert json_hash(results42)==accepted42['ordered_result_sha256']
        assert preserved_assigned['observed_exact_sha256']==previous41['assigned_diagnostics_comparison']['observed_exact_sha256']
        assert preserved_groups['observed_exact_sha256']==previous41['department_group_comparison']['observed_exact_sha256']
        assert department_map_comparison['observed_sha256']==previous41['department_assignment_map_comparison']['observed_sha256']
        assert json_hash(results41)==accepted41['ordered_result_sha256']
        assert comparisons['DIAGNOSTIC']['rows']==182940 and comparisons['PAIR']['rows']==91470
        assert comparisons['DIAGNOSTIC']['observed_exact_sha256']==previous39['series_diagnostics_comparison']['observed_exact_sha256']
        assert comparisons['PAIR']['observed_exact_sha256']==previous40['paired_series_comparison']['observed_exact_sha256']
        assert json_hash(results39)==accepted39['ordered_result_sha256'] and json_hash(results40)==accepted40['ordered_result_sha256']
        pilot_preflight=json.loads((root/'data/series_forecast_improvements_preflight.json').read_text(encoding='utf-8'))
        pilot_acceptance=json.loads((root/'data/series_forecast_improvements_learner_acceptance.json').read_text(encoding='utf-8'))
        assert len(paired.pilot_pairs)==648 and exact_pair_hash(paired.pilot_pairs)==pilot_preflight['ordered_exact_paired_diagnostics_sha256']
        assert json_hash(paired.pilot_reports)==pilot_acceptance['ordered_result_sha256']
        print(json.dumps({'final_errors_diagnostics_report_compared':True,'accepted_sql39_sql40_sql41_sql42_pilot37_reconciled':True}),flush=True)
        execute(export+copy(FORECAST_QUERY,candidate),'unchanged_inputs_candidates_export_seconds')
        after_hashes={k:sha256(p) for k,p in before.items()};assert after_hashes==before_hashes
        assert sha256(candidate)==candidate_before
        mapping_after=execute(MAPPING_QUERY);assert mapping_after==mapping_before
        target_mapping_after=execute(TARGET_MAPPING_QUERY);assert target_mapping_after==target_mapping_before
        database_bytes=database.stat().st_size
    assert not folder.exists()
    assert all(sha256(p)==source_hashes[p.name] for p in sources)
    assert all(sha256(root/p)==value for p,value in pinned.items())
    evidence=dict(checked_at_utc=datetime.now(timezone.utc).isoformat(),executor='assistant',engine=subprocess.check_output([args.duckdb,'-version'],text=True).strip(),
        script=sql_path.relative_to(root).as_posix(),script_sha256=sha256(sql_path),frozen_protocol=protocol.relative_to(root).as_posix(),frozen_protocol_sha256=sha256(protocol),
        public_protocol_freeze_commit=args.public_freeze_commit,public_freeze_verified_by_parent_before_target_access=True,
        final_target_access_started_utc=final_access_started_utc,selected_model='WEEKDAY4',reference_model='SNAIVE7',model_choice_frozen_before_final_evaluation=True,
        repository_dependency_sha256=pinned,repository_dependencies_unchanged=True,source_sha256=source_hashes,source_hashes_unchanged=True,
        exact_sql42_validated_cte_prefix_copies=1,exact_sql42_validated_cte_prefix_sha256=hashlib.sha256(prefix42.encode()).hexdigest(),
        scope=dict(series_count=30490,products=len(products),stores=len(stores),department_count=len(set(departments.values())),
            series_membership_sha256=membership_hash(history),origin='FINAL_HOLDOUT',train_end_day=1913,target_first_day=1914,target_last_day=1941,
            train_end=calendar[1913]['date'],target_start=calendar[1914]['date'],target_end=calendar[1941]['date']),
        settings={'threads':2,'memory_limit':'2GB'},private_database='Resolved private temporary database and detailed CSV exports under repository tmp; learner database never opened.',
        temporary_baseline_removed=True,temporary_database_bytes_after_close=database_bytes,
        packed_history_quantity_bytes=sum(len(v)*v.itemsize for v in history.values()),packed_final_target_quantity_bytes=sum(len(v)*v.itemsize for v in targets.values()),
        training_first_day=1,training_last_day=1913,series_index_map_comparison=map_comparison,indexed_history_comparison=history_comparison,
        final_target_comparison=target_comparison,department_assignment_map_comparison=department_map_comparison,store_state_map_comparison=store_map_comparison,
        history_direct_fields=['series_index','day_number','units'],target_direct_fields=['series_index','day_number','units'],
        separate_fact_calendar_mapping_before=mapping_before,separate_fact_calendar_mapping_after=mapping_after,
        separate_target_calendar_mapping_before=target_mapping_before,separate_target_calendar_mapping_after=target_mapping_after,
        history_and_target_comparison_scope='58,327,370 training triples and 853,720 final target triples compared separately, with complete independently sorted series maps, department/state assignments and calendar; every date/week relationship reconciled separately. No six-field history export claimed.',
        saved_candidate_comparison=forecast_comparison,accepted_sql38_report_sha256=json_hash(forecast_summary),accepted_sql38_forecast_fingerprint_matched=True,
        final_error_rows_comparison=final_comparisons['FINAL_ERROR'],final_series_diagnostics_comparison=final_comparisons['FINAL_DIAGNOSTIC'],
        final_error_columns=SCORED_COLUMNS,final_diagnostic_columns=DIAGNOSTIC_COLUMNS,final_status_control_columns=STATUS_COLUMNS,
        final_status_control_rows=len(final_reference.statuses),final_rmsse_status_summary=final_reference.status_summary,
        preserved_store_assigned_comparison=assigned_comparison,preserved_store_group_comparison=group_comparison,
        preserved_department_assigned_comparison=preserved_assigned,preserved_department_group_comparison=preserved_groups,
        preserved_series_diagnostics_comparison=comparisons['DIAGNOSTIC'],preserved_paired_series_comparison=comparisons['PAIR'],
        accepted_sql39_report_sha256=json_hash(results39),accepted_sql40_report_sha256=json_hash(results40),
        accepted_sql41_report_sha256=json_hash(results41),accepted_sql42_report_sha256=json_hash(results42),accepted_development_fingerprints_matched=True,
        final_error_rows_directly_compared=1707440,development_error_rows_directly_compared=0,
        error_comparison_scope='This new final-period error stream is directly compared. The unchanged SQL42 prefix retains development scoring and controls, but no new export/comparison of 5,122,320 development daily errors is claimed.',
        numerical_reference=dict(precision_digits=70,absolute_tolerance=str(ABS_TOL),relative_tolerance=str(REL_TOL),**final_numeric,
            preserved_store_numeric=store_numeric,preserved_department_numeric=department_numeric,
            maximum_preserved_root_or_pair_absolute_difference=maximum,maximum_preserved_aggregate_absolute_difference=aggregate_max,
            maximum_preserved_mean_delta_reconciliation_difference=reconciliation_max),
        comparison_fingerprint_method='SHA256 of TAB-separated canonical exact fields with LF per ordered row and no header; empty string represents NULL. Final errors order by origin,model,item_id,store_id,numeric horizon and hash all 12 fields. Final diagnostics order by origin,model,item_id,store_id and hash their first 15 exact fields. Roots and unrounded root sums/macros are checked separately with Decimal-70. Preserved streams retain frozen earlier encodings.',
        independent_reference='Unchanged source/history/forecast/development helpers are combined with a separately read 28-value target array. The final reference independently locates the first positive within d1–d1913 and zips retained adjacent training values for integer scale SSE, independently computes quarter errors and Decimal-70 roots, and checks every final error/diagnostic/status/report field. Targets never enter predictions or training scales. A single guarded export contains the literal final report and all preserved SQL39–42 streams.',
        result_rows=2,result_columns=12,output_columns=REPORT_COLUMNS,results=results,rows_with_pass_status=2,
        ordered_result_sha256=json_hash(results),result_field_mismatches=0,
        preserved_sql39_results=results39,preserved_sql40_results=results40,preserved_sql41_results=results41,preserved_sql42_results=results42,
        pilot_series_count=216,pilot_paired_rows_compared=len(paired.pilot_pairs),pilot_exact_pairs_sha256=exact_pair_hash(paired.pilot_pairs),
        pilot_accepted_sql37_report_sha256=json_hash(paired.pilot_reports),pilot_previous_evidence_matched=True,
        prior_pilot_tables_rebuilt=False,sql43_has_no_table_writes=True,input_projection_row_counts=counts,
        input_projection_sha256_before=before_hashes,input_projection_sha256_after=after_hashes,input_projections_unchanged=True,
        candidate_csv_sha256_before=candidate_before,candidate_csv_sha256_after=candidate_before,saved_candidate_unchanged=True,
        fixture_cases_passed=len(cases),fixture_subcases_passed=sum(len(c['subcases']) for c in cases),fixture_cases=cases,timings=timings,
        real_source_evaluation_attempts=1,final_holdout_unit_values_inspected=True,final_holdout_errors_computed=True,
        synthetic_plan_history_lag_operators=1,
        final_model_choice_changed_after_evaluation=False,tree_model_completed=False,
        real_product_identifiers_published=False,individual_final_errors_or_diagnostics_published=False,
        evidence_scope='Assistant final preflight under the publicly frozen baseline-only protocol; learner SQL43 reproduction/acceptance remains pending. WEEKDAY4 remains selected and SNAIVE7 the fixed reference regardless of holdout ranking. No tuning, state/group model switching, tree model, fresh future final test or deployed business benefit is claimed. Sources, inputs, candidates and historical evidence are unchanged.')
    serialized=json.dumps(evidence,indent=2,ensure_ascii=False)+'\n';assert all(item not in serialized for item,_,_ in products)
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(serialized,encoding='utf-8',newline='\n')
    print(json.dumps({'fixture_cases_passed':len(cases),'fixture_subcases_passed':sum(len(c['subcases']) for c in cases),
        'results':results,'ordered_result_sha256':json_hash(results),'timings':timings}),flush=True)


if __name__=='__main__':main()
