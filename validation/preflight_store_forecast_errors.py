"""Independently verify store/state attribution, weighted controls and development metrics in private streams."""
import argparse
from array import array
import copy as copying
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
from preflight_forecast_scope_and_time_audit import FIRST_DATE,ORIGINS,METADATA_FIELDS,quote,sha256,json_hash,membership_hash,compare_csv,SNAPSHOTS
from preflight_full_catalog_baseline_forecasts import (
    TABLE,COLUMNS as FORECAST_COLUMNS,FORECAST_QUERY,MEMBERSHIP,METADATA,metadata_hash,
    reference_rows as forecast_reference,reference_report as forecast_report,
    canonical_report as canonical_forecast_report,stream_compare,copy,
)
from preflight_full_catalog_development_errors import Reference,original_inputs,MAP_QUERY,HISTORY_QUERY,MAPPING_QUERY
from preflight_development_forecast_errors import DIAGNOSTIC_COLUMNS,REPORT_COLUMNS as ERROR_REPORT_COLUMNS,six
from preflight_series_forecast_improvements import PAIRED_COLUMNS,REPORT_COLUMNS as PAIR_REPORT_COLUMNS,ABS_TOL,REL_TOL,exact_pair_hash
from preflight_department_forecast_errors import (
    compare_department, literal_report, DEPARTMENT_MAP_QUERY,
    GROUP_COLUMNS as DEPARTMENT_GROUP_COLUMNS, DEPT_PAIR_COLUMNS, REPORT_COLUMNS as DEPARTMENT_REPORT_COLUMNS,
)

ASSIGNED_COLUMNS=DIAGNOSTIC_COLUMNS+['dept_id','state_id']
GROUP_COLUMNS=['origin','store_id','state_id','model','series_count','evaluated_rows','actual_units','predicted_quarters',
               'absolute_error_quarters','error_quarters','rmsse_valid_series','rmsse_undefined_series','rmsse_sum','macro_rmsse']
STORE_PAIR_COLUMNS=['origin','store_id','state_id','series_count','rmsse_valid_series','mean_rmsse_delta']
GLOBAL_COLUMNS=[c for c in GROUP_COLUMNS if c not in ('store_id','state_id','rmsse_sum')]
REPORT_COLUMNS=['origin','store_id','state_id','series_count','rmsse_valid_series','rmsse_undefined_series',
                'snaive7_mae','weekday4_mae','mae_delta','snaive7_mean_error','weekday4_mean_error',
                'snaive7_macro_rmsse','weekday4_macro_rmsse','rmsse_delta','check_status']
STORE_MAP_QUERY='SELECT store_id,state_id FROM core.m5_store ORDER BY store_id'


class StoreReference:
    def __init__(self,reference,departments,states):
        self.source=copying.copy(reference);self.departments=departments;self.states=states
        self.groups=[];self.pairs=[];self.results=[]

    def rows(self):
        groups={};pairs={};pending={}
        with localcontext() as ctx:
            ctx.prec=70
            for d in self.source.diagnostics():
                origin,model,item,store=d[:4];dept=self.departments[item];state=self.states[store]
                g=groups.setdefault((origin,store,state,model),[0]*8+[Decimal(0)])
                # Eight exact totals followed by the high-precision root sum.
                for index,value in enumerate((1,d[8],d[9],d[10],d[11],d[12],int(d[15] is not None),int(d[15] is None))):g[index]+=value
                if d[15] is not None:g[8]+=d[15]
                key=(origin,item,store)
                if model=='SNAIVE7':assert key not in pending;pending[key]=d[15]
                else:
                    a=pending.pop(key);assert (a is None)==(d[15] is None)
                    p=pairs.setdefault((origin,store,state),[0,0,Decimal(0)]);p[0]+=1
                    if a is not None:p[1]+=1;p[2]+=d[15]-a
                yield (*d,dept,state)
            assert not pending
            for key,g in sorted(groups.items()):
                self.groups.append(dict(zip(GROUP_COLUMNS,(*key,*g[:8],g[8] if g[6] else None,g[8]/g[6] if g[6] else None))))
            for key,p in sorted(pairs.items()):
                self.pairs.append(dict(zip(STORE_PAIR_COLUMNS,(*key,p[0],p[1],p[2]/p[1] if p[1] else None))))
            indexed={(g['origin'],g['store_id'],g['state_id'],g['model']):g for g in self.groups}
            for p in self.pairs:
                origin,store,state=p['origin'],p['store_id'],p['state_id'];a=indexed[origin,store,state,'SNAIVE7'];b=indexed[origin,store,state,'WEEKDAY4']
                for key in ('series_count','evaluated_rows','actual_units','rmsse_valid_series','rmsse_undefined_series'):assert a[key]==b[key]
                assert a['series_count']==p['series_count'] and a['rmsse_valid_series']==p['rmsse_valid_series']
                n=4*a['evaluated_rows']
                if p['mean_rmsse_delta'] is not None:
                    assert abs(p['mean_rmsse_delta']-(b['macro_rmsse']-a['macro_rmsse']))<=ABS_TOL
                self.results.append(dict(origin=origin,store_id=store,state_id=state,series_count=a['series_count'],rmsse_valid_series=a['rmsse_valid_series'],
                    rmsse_undefined_series=a['rmsse_undefined_series'],snaive7_mae=six(Decimal(a['absolute_error_quarters'])/n),
                    weekday4_mae=six(Decimal(b['absolute_error_quarters'])/n),mae_delta=six(Decimal(b['absolute_error_quarters']-a['absolute_error_quarters'])/n),
                    snaive7_mean_error=six(Decimal(a['error_quarters'])/n),weekday4_mean_error=six(Decimal(b['error_quarters'])/n),
                    snaive7_macro_rmsse=six(a['macro_rmsse']),weekday4_macro_rmsse=six(b['macro_rmsse']),
                    rmsse_delta=six(p['mean_rmsse_delta']),check_status='PASS'))


def combined_export(sql,sql41,sql40,sql39,path):
    prefix=sql.split('-- REPORT:',1)[0].rstrip()
    prefix+=', user_report AS ('+literal_report(sql40)+'), prior_user_report AS ('+literal_report(sql39)+'), department_user_report AS ('+literal_report(sql41)+'), store_user_report AS ('+literal_report(sql)+')\n'
    streams=[
        ('ASSIGNED',ASSIGNED_COLUMNS,'store_diagnostics'),
        ('STORE_GLOBAL',GLOBAL_COLUMNS,'report_totals'),
        ('STORE_GROUP',GROUP_COLUMNS,'store_totals'),
        ('STORE_PAIR',STORE_PAIR_COLUMNS,'store_pair_totals'),
        ('STORE_REPORT',REPORT_COLUMNS,'store_user_report'),
        ('DEPARTMENT_GLOBAL',GLOBAL_COLUMNS,'report_totals'),
        ('DEPARTMENT_GROUP',DEPARTMENT_GROUP_COLUMNS,'department_totals'),
        ('DEPARTMENT_PAIR',DEPT_PAIR_COLUMNS,'department_pair_totals'),
        ('DEPARTMENT_REPORT',DEPARTMENT_REPORT_COLUMNS,'department_user_report'),
        ('PAIR',PAIRED_COLUMNS,'paired_series'),
        ('PAIRED_MAE',['origin','mean_numerator','mean_denominator','median_numerator','median_denominator'],'mae_totals'),
        ('PAIRED_RMSSE',['origin','mean_delta','median_delta'],
         '(SELECT origin,AVG(rmsse_delta) AS mean_delta,MEDIAN(rmsse_delta) AS median_delta FROM paired_series GROUP BY origin) t'),
        ('PRIOR_FULL',['origin','model','absolute_error_quarters','evaluated_rows','macro_rmsse'],'report_totals'),
        ('PRIOR_REPORT',ERROR_REPORT_COLUMNS,'prior_user_report'),('REPORT',PAIR_REPORT_COLUMNS,'user_report'),
    ]
    parts=[]
    for kind,fields,source in streams:
        values=[f'CAST({field} AS VARCHAR) AS c{i+1}' for i,field in enumerate(fields)]+[f'NULL::VARCHAR AS c{i}' for i in range(len(fields)+1,19)]
        parts.append(f"SELECT '{kind}' AS record_kind,"+','.join(values)+' FROM '+source)
    return copy(prefix+'SELECT * FROM ('+' UNION ALL '.join(parts)+') outputs ORDER BY record_kind,c1,c2,c3,c4',path)


def compare_store(path,reference,departments,states,base_path):
    independent=StoreReference(reference,departments,states);generator=iter(independent.rows())
    observed_hash=hashlib.sha256();expected_hash=hashlib.sha256();count=0
    collected={k:[] for k in ('STORE_GLOBAL','STORE_GROUP','STORE_PAIR','STORE_REPORT')}
    maximum_root=maximum_sum=maximum_metric=maximum_reconciliation=Decimal(0)
    global_pair_means={}
    with localcontext() as ctx:
        ctx.prec=70
        def numeric(actual,expected):
            value=None if actual=='' else Decimal(actual)
            assert (value is None)==(expected is None)
            error=Decimal(0) if expected is None else abs(value-expected)
            if value is not None:assert value.is_finite() and error<=ABS_TOL+REL_TOL*abs(expected)
            return value,error
        with path.open(newline='',encoding='utf-8') as source,base_path.open('w',newline='',encoding='utf-8') as target:
            reader=csv.reader(source);header=next(reader);assert header==['record_kind']+[f'c{i}' for i in range(1,19)]
            writer=csv.writer(target);writer.writerow(['record_kind']+[f'c{i}' for i in range(1,18)])
            for record in reader:
                kind=record[0];row=record[1:]
                if kind=='ASSIGNED':
                    expected=next(generator,None);assert expected is not None
                    indices=list(range(15))+[16,17]
                    actual=[row[i] for i in indices];wanted=['' if expected[i] is None else str(expected[i]) for i in indices]
                    assert actual==wanted,('Store assignment/exact diagnostic mismatch',count)
                    observed_hash.update(('\t'.join(actual)+'\n').encode());expected_hash.update(('\t'.join(wanted)+'\n').encode())
                    _,error=numeric(row[15],expected[15]);maximum_root=max(maximum_root,error);count+=1
                    writer.writerow(['ASSIGNED',*row[:17]])
                elif kind in collected:collected[kind].append(row)
                else:
                    writer.writerow([kind,*row[:17]])
                    if kind=='PAIRED_RMSSE':global_pair_means[row[0]]=None if row[1]=='' else Decimal(row[1])
        assert next(generator,None) is None
        assert observed_hash.hexdigest()==expected_hash.hexdigest()
        store_count=len(states)
        assert len(collected['STORE_GROUP'])==6*store_count
        assert len(collected['STORE_PAIR'])==len(collected['STORE_REPORT'])==3*store_count
        assert len(collected['STORE_GLOBAL'])==6
        observed_groups={};group_exact=hashlib.sha256();group_reference_hash=hashlib.sha256()
        for row,expected in zip(collected['STORE_GROUP'],independent.groups):
            wanted=[str(expected[k]) for k in GROUP_COLUMNS[:12]]
            assert row[:12]==wanted,'Exact store totals differ'
            group_exact.update(('\t'.join(row[:12])+'\n').encode())
            group_reference_hash.update(('\t'.join(wanted)+'\n').encode())
            total,error=numeric(row[12],expected['rmsse_sum']);maximum_sum=max(maximum_sum,error)
            macro,error=numeric(row[13],expected['macro_rmsse']);maximum_metric=max(maximum_metric,error)
            observed_groups[row[0],row[1],row[2],row[3]]=dict(expected,rmsse_sum=total,macro_rmsse=macro)
        observed_pairs={}
        for row,expected in zip(collected['STORE_PAIR'],independent.pairs):
            assert row[:5]==[str(expected[k]) for k in STORE_PAIR_COLUMNS[:5]]
            delta,error=numeric(row[5],expected['mean_rmsse_delta']);maximum_metric=max(maximum_metric,error)
            a=observed_groups[row[0],row[1],row[2],'SNAIVE7']['macro_rmsse'];b=observed_groups[row[0],row[1],row[2],'WEEKDAY4']['macro_rmsse']
            assert (delta is None)==(a is None)==(b is None)
            if delta is not None:
                error=abs(delta-(b-a));assert error<=ABS_TOL+REL_TOL*abs(b-a);maximum_reconciliation=max(maximum_reconciliation,error)
            observed_pairs[row[0],row[1],row[2]]=dict(expected,mean_rmsse_delta=delta)
        # Compare unrounded integer totals and valid-count weighted macros with the global controls.
        for row in collected['STORE_GLOBAL']:
            origin,model=row[:2];groups=[g for g in observed_groups.values() if (g['origin'],g['model'])==(origin,model)]
            assert len(groups)==store_count
            for i,key in enumerate(GLOBAL_COLUMNS[2:-1],2):assert int(row[i])==sum(g[key] for g in groups),(key,'Global integer reconciliation')
            valid=sum(g['rmsse_valid_series'] for g in groups)
            weighted=None if not valid else sum(g['macro_rmsse']*g['rmsse_valid_series'] for g in groups if g['rmsse_valid_series'])/valid
            _,error=numeric(row[10],weighted);maximum_reconciliation=max(maximum_reconciliation,error)
            macro_from_sums=None if not valid else sum(g['rmsse_sum'] for g in groups if g['rmsse_valid_series'])/valid
            _,error=numeric(row[10],macro_from_sums);maximum_reconciliation=max(maximum_reconciliation,error)
        for origin,_ in ORIGINS[:3]:
            groups=[p for p in observed_pairs.values() if p['origin']==origin];valid=sum(p['rmsse_valid_series'] for p in groups)
            weighted=None if not valid else sum(p['mean_rmsse_delta']*p['rmsse_valid_series'] for p in groups if p['rmsse_valid_series'])/valid
            target=global_pair_means[origin];assert (weighted is None)==(target is None)
            if target is not None:
                error=abs(weighted-target);assert error<=ABS_TOL+REL_TOL*abs(target);maximum_reconciliation=max(maximum_reconciliation,error)
        results=[]
        for row in collected['STORE_REPORT']:
            d=dict(zip(REPORT_COLUMNS,row[:15]))
            for key in REPORT_COLUMNS[3:6]:d[key]=int(d[key])
            for key in REPORT_COLUMNS[6:14]:
                assert d[key]=='' or re.fullmatch(r'-?[0-9]+\.[0-9]{6}',d[key]),'Report metric must retain its six-decimal SQL contract'
                d[key]=None if d[key]=='' else six(Decimal(d[key]))
            results.append(d)
        assert results==independent.results,'Store report differs'
    base=compare_department(base_path,reference,departments,base_path.with_name('preserved-global.csv'))
    assigned=dict(rows=count,columns=18,exact_columns=17,exact_field_mismatches=0,
                  observed_exact_sha256=observed_hash.hexdigest(),independent_exact_sha256=expected_hash.hexdigest())
    assert group_exact.hexdigest()==group_reference_hash.hexdigest()
    group=dict(rows=len(independent.groups),columns=14,exact_columns=12,exact_field_mismatches=0,
               observed_exact_sha256=group_exact.hexdigest(),independent_exact_sha256=group_reference_hash.hexdigest())
    numeric_evidence=dict(maximum_assigned_root_absolute_difference=str(maximum_root),maximum_group_root_sum_absolute_difference=str(maximum_sum),
                          maximum_group_metric_absolute_difference=str(maximum_metric),maximum_weighted_reconciliation_absolute_difference=str(maximum_reconciliation),
                          integer_group_totals_and_mae_bias_weights_reconciled_exactly=True)
    return assigned,group,results,numeric_evidence,base,independent


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--duckdb',required=True)
    parser.add_argument('--output',required=True,type=Path);parser.add_argument('--fixtures-only',action='store_true');args=parser.parse_args()
    root=Path(__file__).resolve().parents[1];tmp=(root/'tmp').resolve();tmp.mkdir(exist_ok=True);assert tmp.is_relative_to(root.resolve())
    sql_path=root/'sql/42_compare_store_forecast_errors.sql';sql=sql_path.read_text(encoding='utf-8')
    path41=root/'sql/41_compare_department_forecast_errors.sql';sql41=path41.read_text(encoding='utf-8')
    path40=root/'sql/40_compare_full_catalog_paired_improvement.sql';sql40=path40.read_text(encoding='utf-8')
    path39=root/'sql/39_compare_full_catalog_development_errors.sql';sql39=path39.read_text(encoding='utf-8')
    prefix41=sql41[sql41.index('WITH parameters AS ('):sql41.index('-- REPORT:')];assert sql.count(prefix41)==1
    baseline_path=root/'sql/38_build_full_catalog_baseline_forecasts.sql';baseline_sql=baseline_path.read_text(encoding='utf-8')
    baseline_build,baseline_validation=baseline_sql.split('-- VALIDATION:',1)
    protocol=root/'docs/STORE_FORECAST_ERRORS_PROTOCOL.md';assert protocol.exists() and sha256(protocol)=='55e15ffe4ff0e95d6acb37e97256638657e90ba8e5aff9d5665ddbb13f3c6726'
    helpers=['validation/preflight_forecast_scope_and_time_audit.py','validation/preflight_seasonal_naive_forecasts.py',
        'validation/preflight_weekday_mean_forecasts.py','validation/preflight_development_forecast_errors.py',
        'validation/preflight_series_forecast_improvements.py','validation/preflight_full_catalog_baseline_forecasts.py',
        'validation/preflight_full_catalog_development_errors.py','validation/preflight_full_catalog_paired_improvement.py','validation/preflight_department_forecast_errors.py']
    prerequisites=['sql/08_stage_calendar.sql','sql/12_build_product_dimension.sql','sql/13_build_store_dimension.sql','sql/14_build_calendar_dimension.sql']
    paths=[sql_path,path41,path40,path39,baseline_path,Path(__file__),protocol,root/'docs/EVALUATION_PLAN.md',root/'data/m5_source_audit.json']
    paths += [root/p for p in helpers+prerequisites]+list((root/'docs').glob('*_PROTOCOL.md'))+list((root/'data').glob('*_preflight.json'))+list((root/'data').glob('*_learner_acceptance.json'))
    inherited_pins=json.loads((root/'data/department_forecast_errors_preflight.json').read_text(encoding='utf-8'))['repository_dependency_sha256']
    assert all(sha256(root/p)==value for p,value in inherited_pins.items())
    paths += [root/p for p in inherited_pins]
    pinned={p.relative_to(root).as_posix():sha256(p) for p in paths if p.name!='store_forecast_errors_preflight.json'}
    calendar={n:dict(date=(FIRST_DATE+timedelta(days=n-1)).isoformat()) for n in range(1,1970)}
    base={(item,store):array('I',[1+n%2 for n in range(1913)]) for item in ('P001','P002','P003') for store in ('S1','S2')}
    departments={'P001':'DEPT_A','P002':'DEPT_A','P003':'DEPT_B'}
    for (item,store),values in base.items():
        values[1801:1829]=array('I',[0]*21+[4]*7)
        target=2 if (item,store)==('P001','S2') else 3 if item=='P003' else 1
        values[1829:1857]=array('I',[target]*28)
    base['P003','S2']=array('I',[5]*1913)
    cases=[]
    def fixture(name,history=None,mapping=None,mutation='',reject=False):
        history=base if history is None else history;mapping=departments if mapping is None else mapping
        items=sorted({p[0] for p in history});stores=sorted({p[1] for p in history});assert len(history)==len(items)*len(stores)
        states={store:'STATE' for store in stores}
        metadata=[(item,mapping[item],'CAT',store,states[store]) for item in items for store in stores]
        def adapt(text):
            return text.replace('3049 AS expected_products,10 AS expected_stores',f'{len(items)} AS expected_products,{len(stores)} AS expected_stores').replace(
                '30490 AS expected_scope_series',f'{len(history)} AS expected_scope_series').replace(MEMBERSHIP,membership_hash(history)).replace(METADATA,metadata_hash(metadata)).replace(
                '7 AS expected_departments',f'{len(set(mapping.values()))} AS expected_departments')
        with tempfile.TemporaryDirectory(prefix='store-errors-fixture-',dir=tmp) as value:
            folder=Path(value).resolve();assert folder.is_relative_to(tmp);database=folder/'fixture.duckdb'
            def execute(text):
                return subprocess.run([args.duckdb,str(database),'-bail','-json'],input="SET threads=2; SET memory_limit='2GB';\n"+text,text=True,encoding='utf-8',capture_output=True)
            setup="CREATE SCHEMA raw; CREATE SCHEMA core; CREATE SCHEMA mart; CREATE TABLE core.m5_product(item_id VARCHAR,dept_id VARCHAR,cat_id VARCHAR);"
            setup+='INSERT INTO core.m5_product VALUES '+','.join(f"({quote(item)},{quote(mapping[item])},'CAT')" for item in items)+';'
            setup+="CREATE TABLE core.m5_store(store_id VARCHAR,state_id VARCHAR); INSERT INTO core.m5_store VALUES "+','.join(f"({quote(store)},'STATE')" for store in stores)+';'
            setup+="""CREATE TABLE raw.m5_sales_wide AS SELECT item_id,dept_id,cat_id,store_id,state_id FROM core.m5_product CROSS JOIN core.m5_store;
CREATE TABLE core.m5_calendar AS SELECT 'd_'||CAST(n AS VARCHAR) AS d,DATE '2011-01-29'+CAST(n AS INTEGER)-1 AS date,
CAST(n AS INTEGER) AS day_number,CAST(11000+n//7 AS INTEGER) AS wm_yr_wk FROM range(1,1970) t(n);
CREATE TABLE mart.m5_sales_daily(item_id VARCHAR,store_id VARCHAR,d VARCHAR,date DATE,wm_yr_wk INTEGER,units INTEGER);
"""
            for (item,store),values in history.items():
                tuples=','.join(f'({n},{v})' for n,v in enumerate(values,1))
                setup+=f"INSERT INTO mart.m5_sales_daily SELECT {quote(item)},{quote(store)},c.d,c.date,c.wm_yr_wk,t.units FROM (VALUES {tuples}) t(n,units) JOIN core.m5_calendar c ON c.day_number=t.n;"
            setup+="INSERT INTO mart.m5_sales_daily SELECT p.item_id,s.store_id,c.d,c.date,c.wm_yr_wk,-999 FROM core.m5_product p CROSS JOIN core.m5_store s CROSS JOIN core.m5_calendar c WHERE c.day_number=1914;"
            run=execute(setup+adapt(baseline_build)+mutation);assert run.returncode==0,(name,run.stderr)
            candidate=folder/'candidate.csv';run=execute(copy(FORECAST_QUERY,candidate));assert run.returncode==0;before=sha256(candidate)
            if reject:
                run=execute(adapt(sql))
                assert run.returncode!=0 and 'Store forecast comparison blocked' in run.stderr,(name,run.stderr)
            else:
                output=folder/'store.csv';run=execute(combined_export(adapt(sql),adapt(sql41),adapt(sql40),adapt(sql39),output));assert run.returncode==0,(name,run.stderr)
                assigned,groups,results,_,department_result,store_reference=compare_store(output,Reference(history,calendar),mapping,states,folder/'department.csv')
                assert assigned['rows']==6*len(history) and groups['rows']==6*len(stores)
                first={r['store_id']:r for r in results if r['origin']=='DEVELOPMENT_1'}
                assert all(row['series_count']==len(items) and row['state_id']=='STATE' for row in first.values())
                if name=='equal_store_sizes_different_eligibility_shared_state':
                    assert len(first)==2 and (first['S1']['rmsse_valid_series'],first['S2']['rmsse_valid_series'])==(3,2)
                    assert (first['S1']['snaive7_mae'],first['S2']['snaive7_mae'])==('2.333333','1.666667')
                    g=[r for r in store_reference.groups if r['origin']=='DEVELOPMENT_1' and r['model']=='SNAIVE7']
                    with localcontext() as ctx:
                        ctx.prec=70
                        weighted=sum(r['macro_rmsse']*r['rmsse_valid_series'] for r in g)/5
                        equal=sum(r['macro_rmsse'] for r in g)/2
                        assert abs(weighted-equal)>Decimal('0.000001')
                if name=='all_undefined_store_is_retained':
                    row=first['S2'];assert row['series_count']==3 and row['rmsse_valid_series']==0 and row['rmsse_undefined_series']==3
                    assert all(row[k] is None for k in ('snaive7_macro_rmsse','weekday4_macro_rmsse','rmsse_delta')) and row['snaive7_mae']=='0.000000'
                if name=='bias_cancellation_and_unrounded_quarter_delta':
                    row=first['S1'];assert row['snaive7_mae']==row['weekday4_mae']=='1.000000'
                    assert row['snaive7_mean_error']==row['weekday4_mean_error']=='0.000000'
                    row=first['S2'];assert (row['snaive7_mae'],row['weekday4_mae'],row['mae_delta'])==('0.035714','0.089286','0.053571')
                    assert Decimal(row['weekday4_mae'])-Decimal(row['snaive7_mae'])!=Decimal(row['mae_delta'])
            run=execute(copy(FORECAST_QUERY,candidate));assert run.returncode==0 and sha256(candidate)==before
        assert not folder.exists();cases.append(dict(case=name,passed=True,rejected=reject,private_database_removed=True))
    fixture('equal_store_sizes_different_eligibility_shared_state')
    changed={k:array('I',v) for k,v in base.items()}
    for item in ('P001','P002','P003'):changed[item,'S2']=array('I',[5]*1913)
    fixture('all_undefined_store_is_retained',changed)
    changed={(item,store):array('I',[1+n%2 for n in range(1913)]) for item in ('P001','P003') for store in ('S1','S2')}
    for (item,store),values in changed.items():
        if store=='S1':
            values[1801:1829]=array('I',[2]*28);values[1829:1857]=array('I',[1 if item=='P001' else 3]*28)
        else:values[1801:1857]=array('I',[3]+[0]*27+[1]+[0]*27)
    fixture('bias_cancellation_and_unrounded_quarter_delta',changed,{'P001':'DEPT_A','P003':'DEPT_B'})
    fixture('state_inconsistent_across_source_products_rejected',mutation="UPDATE raw.m5_sales_wide SET state_id='OTHER' WHERE store_id='S1' AND item_id='P001';",reject=True)
    fixture('empty_store_mapping_raises_standalone_error',mutation='DELETE FROM core.m5_store;',reject=True)
    fixture('duplicate_store_state_mapping_rejected',mutation="INSERT INTO core.m5_store SELECT * FROM core.m5_store WHERE store_id='S1';",reject=True)
    fixture('null_store_state_mapping_rejected',mutation="UPDATE core.m5_store SET state_id=NULL WHERE store_id='S1';",reject=True)
    fixture('damaged_saved_candidate_rejected',mutation=f"UPDATE {TABLE} SET predicted_units=predicted_units+0.25 WHERE origin='FINAL_HOLDOUT' AND horizon_day=1;",reject=True)
    print(json.dumps({'fixture_cases_passed':len(cases)}),flush=True)
    if args.fixtures_only:return

    timings={};sources=[Path('D:/database/m5-forecasting-accuracy')/name for name in ('sales_train_evaluation.csv','calendar.csv','sell_prices.csv')]
    registry=json.loads((root/'data/m5_source_audit.json').read_text(encoding='utf-8'))
    source_hashes={p.name:sha256(p) for p in sources};assert all(source_hashes[p.name]==registry['files'][p.name]['sha256'] for p in sources)
    started=time.perf_counter();calendar,metadata,history=original_inputs(sources[0],sources[1])
    products=sorted({r[:3] for r in metadata});stores=sorted({r[3:] for r in metadata})
    departments={p[0]:p[1] for p in products}
    states={r[0]:r[1] for r in stores}
    assert len(states)==len(stores)==10 and all(states[row[3]]==row[4] for row in metadata)
    assert all(departments[row[0]]==row[1] for row in metadata)
    department=min(p[1] for p in products);store=min(s[0] for s in stores)
    pilot_pairs=[(p[0],store) for p in products if p[1]==department]
    assert len(pilot_pairs)==216
    reference=Reference(history,calendar,pilot_pairs)
    recent={key:array('I',values[1801:1913]) for key,values in history.items()}
    timings['independent_source_and_scale_reference_seconds']=round(time.perf_counter()-started,3)
    print(json.dumps({'source_reference_ready':True,'history_rows':len(history)*1913,'packed_history_bytes':sum(len(v)*v.itemsize for v in history.values())}),flush=True)
    with tempfile.TemporaryDirectory(prefix='store-errors-source-',dir=tmp) as value:
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
        snapshot_queries['department_assignment']=DEPARTMENT_MAP_QUERY
        snapshot_queries['store_state_assignment']=STORE_MAP_QUERY
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
        previous39=json.loads((root/'data/full_catalog_development_errors_preflight.json').read_text(encoding='utf-8'))
        accepted39=json.loads((root/'data/full_catalog_development_errors_learner_acceptance.json').read_text(encoding='utf-8'))
        previous40=json.loads((root/'data/full_catalog_paired_improvement_preflight.json').read_text(encoding='utf-8'))
        accepted40=json.loads((root/'data/full_catalog_paired_improvement_learner_acceptance.json').read_text(encoding='utf-8'))
        assert history_comparison['observed_sha256']==previous40['indexed_history_comparison']['observed_sha256']
        assert map_comparison['observed_sha256']==previous40['series_index_map_comparison']['observed_sha256']
        previous41=json.loads((root/'data/department_forecast_errors_preflight.json').read_text(encoding='utf-8'))
        accepted41=json.loads((root/'data/department_forecast_errors_learner_acceptance.json').read_text(encoding='utf-8'))
        assert sha256(root/'data/department_forecast_errors_learner_acceptance.json')=='c9d794aac6f423ac68b71b25bc2cff2c82aabe7e4b3349997c84b1ea6d7f9bc9'
        output=folder/'store-diagnostic-report.csv'
        execute(combined_export(sql,sql41,sql40,sql39,output),'guarded_history_scoring_store_export_seconds')
        started=time.perf_counter()
        assigned_comparison,group_comparison,results,store_numeric,department_base,store_reference=compare_store(
            output,reference,departments,states,folder/'preserved-department-streams.csv')
        preserved_assigned,preserved_groups,results41,department_numeric,base,department_reference=department_base
        comparisons,paired,results40,results39,maximum,aggregate_max,reconciliation_max=base
        timings['assigned_diagnostic_group_and_global_comparison_seconds']=round(time.perf_counter()-started,3)
        assert assigned_comparison['rows']==182940 and group_comparison['rows']==60 and len(results)==30
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
        print(json.dumps({'store_department_and_global_controls_compared':True,'accepted_sql39_sql40_sql41_pilot37_reconciled':True}),flush=True)
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
        exact_sql41_validated_cte_prefix_copies=1,exact_sql41_validated_cte_prefix_sha256=hashlib.sha256(prefix41.encode()).hexdigest(),
        scope={'series_count':30490,'products':len(products),'stores':len(stores),'department_count':len(set(departments.values())),
               'series_membership_sha256':membership_hash(history),'grouping':'All ten stores with all 3,049 released products per store. Original state codes are context only; no state or origin pooling.'},
        settings={'threads':2,'memory_limit':'2GB'},private_database='Private temporary database and detailed CSV exports under resolved repository tmp; learner database never opened.',
        temporary_baseline_removed=True,temporary_database_bytes_after_close=database_bytes,packed_history_quantity_bytes=sum(len(v)*v.itemsize for v in history.values()),
        training_first_day=1,training_last_day=1913,series_index_map_comparison=map_comparison,indexed_history_comparison=history_comparison,
        department_assignment_map_comparison=department_map_comparison,store_state_map_comparison=store_map_comparison,history_direct_fields=['series_index','day_number','units'],
        separate_fact_calendar_mapping_before=mapping_before,separate_fact_calendar_mapping_after=mapping_after,
        history_comparison_scope='All indexed history triples, index/item/store mappings and item/store/department assignments and complete store/state mappings are independently compared. Calendar fields are separately compared and all 58,327,370 fact date/week mappings checked before and after. No six-field history CSV comparison is claimed.',
        saved_candidate_comparison=forecast_comparison,accepted_sql38_report_sha256=json_hash(forecast_summary),accepted_sql38_forecast_fingerprint_matched=True,
        assigned_diagnostics_comparison=assigned_comparison,store_group_comparison=group_comparison,
        preserved_department_assigned_comparison=preserved_assigned,preserved_department_group_comparison=preserved_groups,
        assigned_diagnostic_columns=ASSIGNED_COLUMNS,store_group_columns=GROUP_COLUMNS,store_pair_control_rows=30,store_pair_control_columns=STORE_PAIR_COLUMNS,
        preserved_series_diagnostics_comparison=comparisons['DIAGNOSTIC'],preserved_paired_series_comparison=comparisons['PAIR'],
        accepted_sql39_report_sha256=json_hash(results39),accepted_sql40_report_sha256=json_hash(results40),accepted_sql41_report_sha256=json_hash(results41),accepted_diagnostic_and_pair_fingerprints_matched=True,accepted_department_fingerprints_matched=True,
        daily_error_rows_directly_compared=0,daily_error_comparison_scope='The unchanged SQL41 prefix recomputes and guards the accepted scoring/pairing logic. This step directly compares complete assigned diagnostics, group totals and paired records, not a new export of 5,122,320 daily error rows.',
        numerical_reference=dict(precision_digits=70,absolute_tolerance=str(ABS_TOL),relative_tolerance=str(REL_TOL),**store_numeric,preserved_department_numeric=department_numeric,
            maximum_preserved_root_or_pair_absolute_difference=maximum,maximum_preserved_aggregate_absolute_difference=aggregate_max,
            maximum_preserved_mean_delta_reconciliation_difference=reconciliation_max),
        comparison_fingerprint_method='SHA256 of TAB-separated canonical exact field strings with LF per ordered row and no header; empty string represents NULL. Assigned rows order by origin,model,item_id,store_id and hash the 15 original exact fields plus observed dept_id and state_id. Store group rows order by origin,store_id,state_id,model and hash their first 12 exact fields. Observed department projections directly reproduce earlier assigned/group fingerprints. Roots/root sums/macros are separately checked with Decimal-70. Base diagnostic and paired fingerprints retain the inherited methods.',
        independent_reference='Original CSV quantities and complete product/store/state metadata feed unchanged packed-history/scale and paired references. A separate store accumulator verifies every assigned diagnostic, sums exact quarter numerators and subtracts Decimal-70 roots within each store. State is never pooled. Weighted integer totals and valid-series macro controls reconcile with global diagnostics. The observed department assignment and controls are passed to the frozen SQL41 comparator. One guarded SQL execution contains literal SQL39/40/41/42 reports and all required detail/control streams.',
        result_rows=30,result_columns=15,output_columns=REPORT_COLUMNS,results=results,rows_with_pass_status=30,ordered_result_sha256=json_hash(results),result_field_mismatches=0,
        preserved_sql39_results=results39,preserved_sql40_results=results40,preserved_sql41_results=results41,rmsse_status_summary=reference.status_summary,
        pilot_series_count=216,pilot_paired_rows_compared=len(paired.pilot_pairs),pilot_exact_pairs_sha256=exact_pair_hash(paired.pilot_pairs),
        pilot_accepted_sql37_report_sha256=json_hash(paired.pilot_reports),pilot_previous_evidence_matched=True,
        prior_pilot_tables_rebuilt=False,sql42_has_no_table_writes=True,input_projection_row_counts=counts,
        input_projection_sha256_before=before_hashes,input_projection_sha256_after=after_hashes,input_projections_unchanged=True,
        candidate_csv_sha256_before=candidate_before,candidate_csv_sha256_after=candidate_before,saved_candidate_unchanged=True,
        fixture_cases_passed=len(cases),fixture_cases=cases,timings=timings,
        final_holdout_unit_values_inspected=False,final_holdout_errors_computed=False,final_model_selected=False,
        real_product_identifiers_published=False,individual_assigned_diagnostics_published=False,
        evidence_scope='Assistant store preflight only; learner SQL42 execution pending. All ten stores, 3,049 products per store and seven departments remain represented; state codes are context only. MAE/bias retain all series; RMSSE uses the common defined-scale cohort and preserves NULL for zero-valid groups. Store deltas are unrounded differences before display, not per-series win counts or a selection policy. All sources, candidates, prior evidence and fixed protocols remain unchanged.')
    serialized=json.dumps(evidence,indent=2,ensure_ascii=False)+'\n'
    assert all(item not in serialized for item,_,_ in products)
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(serialized,encoding='utf-8',newline='\n')
    print(json.dumps({'fixture_cases_passed':len(cases),'results':results,'ordered_result_sha256':json_hash(results),'timings':timings}),flush=True)


if __name__=='__main__':main()
