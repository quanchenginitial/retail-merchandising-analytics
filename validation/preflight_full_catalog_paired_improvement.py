"""Verify full-catalog paired improvement with bounded independent references and private streams."""
import argparse
from array import array
import copy as copying
import csv
from datetime import datetime,timedelta,timezone
from decimal import Decimal,ROUND_HALF_UP,localcontext
import hashlib
import json
from pathlib import Path
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
from preflight_development_forecast_errors import DIAGNOSTIC_COLUMNS,REPORT_COLUMNS as ERROR_REPORT_COLUMNS,six,canonical_report as canonical_error_report
from preflight_series_forecast_improvements import PAIRED_COLUMNS,REPORT_COLUMNS,FLOAT_FIELDS,ABS_TOL,REL_TOL,canonical_report,exact_pair_hash

FLOAT_INDEX={12,13,14}


def summarize(origin,entries):
    """Entries hold only delta numerators, Decimal root differences and exact winner labels."""
    reports=[];full=None;mae_controls=None
    for metric in ('MAE','RMSSE'):
        group=entries if metric=='MAE' else [e for e in entries if e[1] is not None]
        n=len(group);winner_index=2 if metric=='MAE' else 3
        wins=sum(e[winner_index]=='WEEKDAY4' for e in group);ties=sum(e[winner_index]=='TIE' for e in group)
        losses=sum(e[winner_index]=='SNAIVE7' for e in group)
        values=sorted(e[0 if metric=='MAE' else 1] for e in group)
        central=[] if not n else [values[i] for i in sorted({(n-1)//2,n//2})]
        denominator=112 if metric=='MAE' else 1
        mean=None if not n else Decimal(sum(values))/Decimal(n*denominator)
        median=None if not n else Decimal(sum(central))/Decimal(len(central)*denominator)
        pct=None if not n else format((Decimal(wins)*100/n).quantize(Decimal('.0001'),rounding=ROUND_HALF_UP),'.4f')
        reports.append(dict(origin=origin,metric=metric,total_series=len(entries),compared_series=n,excluded_series=len(entries)-n,
            weekday4_wins=wins,ties=ties,snaive7_wins=losses,weekday4_win_pct=pct,mean_delta=six(mean),median_delta=six(median),check_status='PASS'))
        if metric=='MAE':mae_controls=(origin,sum(values),112*n,sum(central),112*len(central))
        else:full=(origin,mean,median)
    return reports,full,mae_controls


class PairReference:
    def __init__(self,reference):
        # Histories and already-computed scale prefixes are immutable shared inputs.
        # diagnostics() replaces its own result lists, so this shallow copy has independent accumulators.
        self.source=copying.copy(reference)
        self.reports=[];self.aggregates=[];self.mae_controls=[];self.pilot_reports=[];self.pilot_pairs=[]
        self.model_totals={}

    def rows(self):
        with localcontext() as ctx:
            ctx.prec=70
            current=None;pending={};entries=[];pilot=[]
            def finish():
                assert not pending
                report,aggregate,mae=summarize(current,entries)
                self.reports.extend(report);self.aggregates.append(aggregate);self.mae_controls.append(mae)
                if pilot:self.pilot_reports.extend(summarize(current,pilot)[0])
            for d in self.source.diagnostics():
                origin,model,item,store=d[:4]
                if origin!=current:
                    if current is not None:finish()
                    current=origin;entries=[];pilot=[]
                totals=self.model_totals.setdefault((origin,model),[0,0])
                totals[0]+=d[11];totals[1]+=d[8]
                if model=='SNAIVE7':
                    assert (item,store) not in pending;pending[item,store]=d;continue
                a=pending.pop((item,store))
                for index in (5,6,7,8,9,14):assert a[index]==d[index]
                assert a[8]==28
                valid=a[14]=='VALID'
                def winner(x,y):return 'WEEKDAY4' if y<x else 'TIE' if y==x else 'SNAIVE7'
                delta=d[15]-a[15] if valid else None  # Independent direct subtraction of Decimal-70 roots.
                row=(origin,item,store,a[11],d[11],a[13],d[13],d[11]-a[11],a[5],a[6],a[7],a[14],a[15],d[15],delta,
                     winner(a[11],d[11]),winner(a[13],d[13]) if valid else None)
                entry=(row[7],delta,row[15],row[16]);entries.append(entry)
                if (item,store) in self.source.pilot_pairs:
                    pilot.append(entry);self.pilot_pairs.append(dict(zip(PAIRED_COLUMNS,row)))
                yield row
            if current is not None:finish()


def combined_export(sql,prior_sql,path):
    prefix,report=sql.split('-- REPORT:',1)
    report=report[report.index('\nSELECT '):].strip().rstrip(';')
    prior=prior_sql.split('-- REPORT:',1)[1];prior=prior[prior.index('\nSELECT '):].strip().rstrip(';')
    prefix=prefix.rstrip()+', user_report AS ('+report+'), prior_user_report AS ('+prior+')\n'
    streams=[
        ('DIAGNOSTIC',DIAGNOSTIC_COLUMNS,'series_diagnostics'),
        ('PAIR',PAIRED_COLUMNS,'paired_series'),
        ('PAIRED_MAE',['origin','mean_numerator','mean_denominator','median_numerator','median_denominator'],'mae_totals'),
        ('PAIRED_RMSSE',['origin','mean_delta','median_delta'],
         '(SELECT origin,AVG(rmsse_delta) AS mean_delta,MEDIAN(rmsse_delta) AS median_delta FROM paired_series GROUP BY origin) t'),
        ('PRIOR_FULL',['origin','model','absolute_error_quarters','evaluated_rows','macro_rmsse'],'report_totals'),
        ('PRIOR_REPORT',ERROR_REPORT_COLUMNS,'prior_user_report'),
        ('REPORT',REPORT_COLUMNS,'user_report'),
    ]
    parts=[]
    for kind,fields,source in streams:
        values=[f'CAST({field} AS VARCHAR) AS c{i+1}' for i,field in enumerate(fields)]
        values += [f'NULL::VARCHAR AS c{i}' for i in range(len(fields)+1,18)]
        parts.append(f"SELECT '{kind}' AS record_kind,"+','.join(values)+' FROM '+source)
    return copy(prefix+'SELECT * FROM ('+' UNION ALL '.join(parts)+') outputs ORDER BY record_kind,c1,c2,c3,c4',path)


def compare_combined(path,reference):
    paired=PairReference(reference)
    generators={'DIAGNOSTIC':iter(reference.diagnostics()),'PAIR':iter(paired.rows())}
    observed_hash={k:hashlib.sha256() for k in generators};expected_hash={k:hashlib.sha256() for k in generators}
    counts={k:0 for k in generators};maximum=Decimal(0);aggregate_max=Decimal(0);reconciliation_max=Decimal(0)
    other={k:[] for k in ('PAIRED_MAE','PAIRED_RMSSE','PRIOR_FULL','PRIOR_REPORT','REPORT')}
    with localcontext() as ctx:
        ctx.prec=70
        with path.open(newline='',encoding='utf-8') as stream:
            reader=csv.reader(stream);assert next(reader)==['record_kind']+[f'c{i}' for i in range(1,18)]
            for record in reader:
                kind=record[0];row=record[1:]
                if kind not in generators:other[kind].append(row);continue
                expected=next(generators[kind],None);assert expected is not None,(kind,'extra row')
                indices=range(15) if kind=='DIAGNOSTIC' else [i for i in range(17) if i not in FLOAT_INDEX]
                wanted=['' if expected[i] is None else str(expected[i]) for i in indices]
                actual=[row[i] for i in indices]
                assert actual==wanted,(kind,counts[kind],'exact field mismatch')
                observed_hash[kind].update(('\t'.join(actual)+'\n').encode())
                expected_hash[kind].update(('\t'.join(wanted)+'\n').encode())
                for i in (15,) if kind=='DIAGNOSTIC' else FLOAT_INDEX:
                    a=None if row[i]=='' else Decimal(row[i]);e=expected[i]
                    assert (a is None)==(e is None)
                    if e is not None:
                        error=abs(a-e);assert a.is_finite() and error<=ABS_TOL+REL_TOL*abs(e)
                        maximum=max(maximum,error)
                counts[kind]+=1
        for kind,generator in generators.items():assert next(generator,None) is None,(kind,'missing row')
        assert len(other['REPORT'])==len(other['PRIOR_REPORT'])==len(other['PRIOR_FULL'])==6
        assert len(other['PAIRED_MAE'])==len(other['PAIRED_RMSSE'])==3
        reports=[dict(zip(REPORT_COLUMNS,row[:12])) for row in other['REPORT']]
        for row in reports:
            for key in ('weekday4_win_pct','mean_delta','median_delta'):
                if row[key]=='':row[key]=None
        reports=canonical_report(reports);assert reports==paired.reports
        prior=[dict(zip(ERROR_REPORT_COLUMNS,row[:12])) for row in other['PRIOR_REPORT']]
        for row in prior:
            if row['macro_rmsse']=='':row['macro_rmsse']=None
        prior=canonical_error_report(prior);assert prior==reference.reports==paired.source.reports
        prior_full={}
        for row,expected_macro in zip(other['PRIOR_FULL'],reference.macros):
            origin,model,absolute,n,macro=row[:5];absolute=int(absolute);n=int(n)
            value=None if macro=='' else Decimal(macro)
            assert (origin,model)==expected_macro[:2]
            assert [absolute,n]==paired.model_totals[origin,model]
            assert (value is None)==(expected_macro[2] is None)
            if value is not None:
                error=abs(value-expected_macro[2]);assert error<=ABS_TOL+REL_TOL*abs(expected_macro[2]);aggregate_max=max(aggregate_max,error)
            prior_full[origin,model]=(absolute,n,value)
        for row,expected in zip(other['PAIRED_MAE'],paired.mae_controls):
            actual=(row[0],*(int(v) for v in row[1:5]));assert actual==expected
            origin,num,den,_,_=actual
            a,b=prior_full[origin,'SNAIVE7'],prior_full[origin,'WEEKDAY4']
            assert a[1]==b[1] and num*(4*a[1])==(b[0]-a[0])*den,'Exact MAE mean/aggregate reconciliation'
        for row,expected in zip(other['PAIRED_RMSSE'],paired.aggregates):
            assert row[0]==expected[0]
            values=[None if v=='' else Decimal(v) for v in row[1:3]]
            for a,e in zip(values,expected[1:]):
                assert (a is None)==(e is None)
                if e is not None:
                    error=abs(a-e);assert error<=ABS_TOL+REL_TOL*abs(e);aggregate_max=max(aggregate_max,error)
            a,b=prior_full[row[0],'SNAIVE7'][2],prior_full[row[0],'WEEKDAY4'][2]
            assert (values[0] is None)==(a is None)==(b is None)
            if a is not None:
                difference=b-a;error=abs(values[0]-difference)
                assert error<=ABS_TOL+REL_TOL*abs(difference);reconciliation_max=max(reconciliation_max,error)
    comparisons={kind:dict(rows=counts[kind],columns=16 if kind=='DIAGNOSTIC' else 17,exact_columns=15 if kind=='DIAGNOSTIC' else 14,
        exact_field_mismatches=0,observed_exact_sha256=observed_hash[kind].hexdigest(),independent_exact_sha256=expected_hash[kind].hexdigest()) for kind in generators}
    assert all(v['observed_exact_sha256']==v['independent_exact_sha256'] for v in comparisons.values())
    return comparisons,paired,reports,prior,str(maximum),str(aggregate_max),str(reconciliation_max)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--duckdb',required=True)
    parser.add_argument('--output',required=True,type=Path);parser.add_argument('--fixtures-only',action='store_true');args=parser.parse_args()
    root=Path(__file__).resolve().parents[1];tmp=(root/'tmp').resolve();tmp.mkdir(exist_ok=True);assert tmp.is_relative_to(root.resolve())
    sql_path=root/'sql/40_compare_full_catalog_paired_improvement.sql';sql=sql_path.read_text(encoding='utf-8')
    prior_path=root/'sql/39_compare_full_catalog_development_errors.sql';prior_sql=prior_path.read_text(encoding='utf-8')
    prior_prefix=prior_sql[prior_sql.index('WITH parameters AS ('):prior_sql.index('-- REPORT:')];assert sql.count(prior_prefix)==1
    pilot_sql=(root/'sql/37_compare_series_forecast_improvements.sql').read_text(encoding='utf-8')
    pilot_block=pilot_sql[pilot_sql.index(', paired_raw AS MATERIALIZED ('):pilot_sql.index('-- REPORT:')];assert sql.count(pilot_block)==1
    baseline_path=root/'sql/38_build_full_catalog_baseline_forecasts.sql';baseline_sql=baseline_path.read_text(encoding='utf-8')
    baseline_build,baseline_validation=baseline_sql.split('-- VALIDATION:',1)
    protocol=root/'docs/FULL_CATALOG_PAIRED_IMPROVEMENT_PROTOCOL.md';assert protocol.exists()
    helpers=['validation/preflight_forecast_scope_and_time_audit.py','validation/preflight_seasonal_naive_forecasts.py',
        'validation/preflight_weekday_mean_forecasts.py','validation/preflight_development_forecast_errors.py',
        'validation/preflight_series_forecast_improvements.py','validation/preflight_full_catalog_baseline_forecasts.py',
        'validation/preflight_full_catalog_development_errors.py']
    prerequisites=['sql/08_stage_calendar.sql','sql/12_build_product_dimension.sql','sql/13_build_store_dimension.sql','sql/14_build_calendar_dimension.sql']
    paths=[sql_path,prior_path,baseline_path,root/'sql/37_compare_series_forecast_improvements.sql',Path(__file__),protocol,
        root/'docs/EVALUATION_PLAN.md',root/'docs/FULL_CATALOG_DEVELOPMENT_ERRORS_PROTOCOL.md',root/'docs/FULL_CATALOG_BASELINE_FORECASTS_PROTOCOL.md',
        root/'docs/SERIES_FORECAST_IMPROVEMENTS_PROTOCOL.md',root/'data/m5_source_audit.json']
    paths += [root/p for p in helpers+prerequisites]+list((root/'data').glob('*_preflight.json'))+list((root/'data').glob('*_learner_acceptance.json'))
    pinned={p.relative_to(root).as_posix():sha256(p) for p in paths if p.name!='full_catalog_paired_improvement_preflight.json'}
    calendar={n:dict(date=(FIRST_DATE+timedelta(days=n-1)).isoformat()) for n in range(1,1970)}
    base={(item,store):array('I',[1+n%2 for n in range(1913)]) for item in ('P001','P002') for store in ('S1','S2')}
    for store,target in [('S1',1),('S2',4)]:
        base['P001',store][1801:1829]=array('I',[0]*21+[4]*7);base['P001',store][1829:1857]=array('I',[target]*28)
    base['P002','S1']=array('I',[5]*1913)
    base['P002','S2']=array('I',[0]*1829+[3+n%2 for n in range(84)])
    cases=[]
    def fixture(name,history=None,mutation='',reject=False):
        history=base if history is None else history
        items=sorted({p[0] for p in history});stores=sorted({p[1] for p in history})
        assert len(history)==len(items)*len(stores)
        metadata=[(item,'DEPT','CAT',store,'STATE') for item in items for store in stores]
        def adapt(text):
            return text.replace('3049 AS expected_products,10 AS expected_stores',f'{len(items)} AS expected_products,{len(stores)} AS expected_stores').replace(
                '30490 AS expected_scope_series',f'{len(history)} AS expected_scope_series').replace(MEMBERSHIP,membership_hash(history)).replace(METADATA,metadata_hash(metadata))
        with tempfile.TemporaryDirectory(prefix='full-pairs-fixture-',dir=tmp) as value:
            folder=Path(value).resolve();assert folder.is_relative_to(tmp);database=folder/'fixture.duckdb'
            def execute(text):
                return subprocess.run([args.duckdb,str(database),'-bail','-json'],input="SET threads=2; SET memory_limit='2GB';\n"+text,text=True,encoding='utf-8',capture_output=True)
            setup="CREATE SCHEMA raw; CREATE SCHEMA core; CREATE SCHEMA mart; CREATE TABLE core.m5_product(item_id VARCHAR,dept_id VARCHAR,cat_id VARCHAR);"
            setup+='INSERT INTO core.m5_product VALUES '+','.join(f"({quote(item)},'DEPT','CAT')" for item in items)+';'
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
            output=folder/'paired.csv';run=execute(combined_export(adapt(sql),adapt(prior_sql),output))
            if reject:
                assert run.returncode!=0 and ('Full catalog paired improvement blocked' in run.stderr or 'Full catalog development comparison blocked' in run.stderr),(name,run.stderr)
            else:
                assert run.returncode==0,(name,run.stderr)
                comparisons,paired,results,_,_,_,_=compare_combined(output,Reference(history,calendar))
                assert comparisons['PAIR']['rows']==3*len(history) and comparisons['DIAGNOSTIC']['rows']==6*len(history)
                mae,rmsse=results[:2]
                if name=='multi_store_winners_and_origin_specific_eligibility':
                    assert (mae['weekday4_wins'],mae['ties'],mae['snaive7_wins'])==(1,2,1)
                    assert (rmsse['compared_series'],rmsse['excluded_series'],rmsse['weekday4_win_pct'])==(2,2,'50.0000')
                    assert results[3]['excluded_series']==1
                if name=='all_zero_cohort_has_null_rmsse_summary':
                    assert rmsse['compared_series']==0 and all(rmsse[k] is None for k in ('weekday4_win_pct','mean_delta','median_delta'))
                if name=='two_perfect_valid_roots_give_exact_zero_delta':
                    assert all(r['ties']==len(history) and r['excluded_series']==0 and r['mean_delta']=='0.000000' for r in results)
                if name=='exact_rmsse_win_despite_displayed_zero_delta':
                    assert (rmsse['weekday4_wins'],rmsse['ties'])==(1,1) and rmsse['mean_delta']==rmsse['median_delta']=='0.000000'
                if name=='odd_median_uses_paired_differences':assert mae['mean_delta']=='0.333333' and mae['median_delta']=='2.000000'
                if name=='even_median_averages_central_paired_differences':assert mae['mean_delta']==mae['median_delta']=='-1.000000'
            run=execute(copy(FORECAST_QUERY,candidate));assert run.returncode==0 and sha256(candidate)==before
        assert not folder.exists();cases.append(dict(case=name,passed=True,rejected=reject,private_database_removed=True))
    fixture('multi_store_winners_and_origin_specific_eligibility')
    fixture('all_zero_cohort_has_null_rmsse_summary',{k:array('I',[0]*1913) for k in base})
    fixture('two_perfect_valid_roots_give_exact_zero_delta',{k:array('I',[2]+[5]*1912) for k in base})
    near={(item,'S1'):array('I',[2147483647 if n%2 else 0 for n in range(1,1914)]) for item in ('P001','P002')}
    near['P001','S1'][1801:1857]=array('I',[0]*21+[1]*7+[0]*28);near['P002','S1'][1801:1857]=array('I',[0]*56)
    fixture('exact_rmsse_win_despite_displayed_zero_delta',near)
    def scenario(specs):
        histories={(f'P{i+1:03d}','S1'):array('I',[1+n%2 for n in range(1,1914)]) for i in range(len(specs))}
        for values,(blocks,target) in zip(histories.values(),specs):
            values[1801:1829]=array('I',[v for block in blocks for v in [block]*7]);values[1829:1857]=array('I',[target]*28)
        return histories
    fixture('odd_median_uses_paired_differences',scenario([([0,0,0,4],1),([4,4,8,0],1),([1,1,2,4],4)]))
    fixture('even_median_averages_central_paired_differences',scenario([([0,0,0,4],1),([0,0,0,4],3)]))
    fixture('missing_saved_candidate_rejected',mutation=f"DELETE FROM {TABLE} WHERE origin='DEVELOPMENT_1' AND model='SNAIVE7' AND item_id='P001' AND store_id='S1' AND horizon_day=1;",reject=True)
    fixture('damaged_unscored_final_candidate_rejected',mutation=f"UPDATE {TABLE} SET predicted_units=predicted_units+0.25 WHERE origin='FINAL_HOLDOUT' AND horizon_day=1;",reject=True)
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
    with tempfile.TemporaryDirectory(prefix='full-pairs-source-',dir=tmp) as value:
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
        previous=json.loads((root/'data/full_catalog_development_errors_preflight.json').read_text(encoding='utf-8'))
        previous_acceptance=json.loads((root/'data/full_catalog_development_errors_learner_acceptance.json').read_text(encoding='utf-8'))
        assert history_comparison['observed_sha256']==previous['indexed_history_comparison']['observed_sha256']
        assert map_comparison['observed_sha256']==previous['series_index_map_comparison']['observed_sha256']
        outputs=folder/'paired-diagnostic-report.csv'
        execute(combined_export(sql,prior_sql,outputs),'guarded_history_scoring_pairing_export_seconds')
        started=time.perf_counter()
        comparisons,paired,results,prior_results,maximum,aggregate_max,reconciliation_max=compare_combined(outputs,reference)
        timings['diagnostic_and_paired_reference_comparison_seconds']=round(time.perf_counter()-started,3)
        assert comparisons['DIAGNOSTIC']['rows']==182940 and comparisons['PAIR']['rows']==91470
        assert comparisons['DIAGNOSTIC']['observed_exact_sha256']==previous['series_diagnostics_comparison']['observed_exact_sha256']
        assert json_hash(prior_results)==previous_acceptance['ordered_result_sha256']==previous['ordered_result_sha256']
        pilot_preflight=json.loads((root/'data/series_forecast_improvements_preflight.json').read_text(encoding='utf-8'))
        pilot_acceptance=json.loads((root/'data/series_forecast_improvements_learner_acceptance.json').read_text(encoding='utf-8'))
        assert len(paired.pilot_pairs)==648 and exact_pair_hash(paired.pilot_pairs)==pilot_preflight['ordered_exact_paired_diagnostics_sha256']
        assert json_hash(paired.pilot_reports)==pilot_acceptance['ordered_result_sha256']
        print(json.dumps({'paired_rows_and_diagnostics_compared':True,'accepted_sql39_and_pilot37_reconciled':True}),flush=True)
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
        exact_sql39_validated_cte_prefix_copies=1,exact_sql39_validated_cte_prefix_sha256=hashlib.sha256(prior_prefix.encode()).hexdigest(),
        exact_sql37_paired_cte_block_copies=1,exact_sql37_paired_cte_block_sha256=hashlib.sha256(pilot_block.encode()).hexdigest(),
        scope={'series_count':30490,'products':len(products),'stores':len(stores),'series_membership_sha256':membership_hash(history)},
        settings={'threads':2,'memory_limit':'2GB'},private_database='Private temporary database and detailed CSV exports under resolved repository tmp; learner database never opened.',
        temporary_baseline_removed=True,temporary_database_bytes_after_close=database_bytes,packed_history_quantity_bytes=sum(len(v)*v.itemsize for v in history.values()),
        training_first_day=1,training_last_day=1913,series_index_map_comparison=map_comparison,indexed_history_comparison=history_comparison,
        history_direct_fields=['series_index','day_number','units'],separate_fact_calendar_mapping_before=mapping_before,separate_fact_calendar_mapping_after=mapping_after,
        history_comparison_scope='All indexed history triples and all index/item/store mappings are independently compared. Calendar fields are independently compared; all 58,327,370 fact date/week mappings are separately verified before and after. No six-field history CSV comparison is claimed.',
        saved_candidate_comparison=forecast_comparison,accepted_sql38_report_sha256=json_hash(forecast_summary),accepted_sql38_forecast_fingerprint_matched=True,
        series_diagnostics_comparison=comparisons['DIAGNOSTIC'],paired_series_comparison=comparisons['PAIR'],
        accepted_sql39_report_sha256=json_hash(prior_results),accepted_sql39_diagnostics_fingerprint_matched=True,
        daily_error_rows_directly_compared=0,daily_error_comparison_scope='The unchanged SQL39 CTE prefix recomputes and guards development scoring. SQL40 re-compares all 182,940 model diagnostics and their accepted exact fingerprint; it does not re-export or claim a new direct comparison of the 5,122,320 daily error rows.',
        numerical_reference={'precision_digits':70,'absolute_tolerance':str(ABS_TOL),'relative_tolerance':str(REL_TOL),
            'maximum_root_or_paired_delta_absolute_difference':maximum,'maximum_unrounded_aggregate_absolute_difference':aggregate_max,
            'maximum_mean_delta_vs_model_macro_difference':reconciliation_max,'mae_mean_vs_model_aggregates_reconciled_exactly':True,
            'exact_winner_and_null_status_comparisons':True},
        comparison_fingerprint_method='SHA256 of TAB-separated canonical field strings with LF after every ordered row, no header. History: series_index,day_number; diagnostics: origin,model,item_id,store_id; pairs: origin,item_id,store_id. Empty string represents NULL. Diagnostics hash 15 exact fields; pairs hash the 14 exact fields in their declared order, excluding only three root/delta values. Numeric fields are separately compared with Decimal-70.',
        paired_columns=PAIRED_COLUMNS,paired_exact_columns=[c for c in PAIRED_COLUMNS if c not in FLOAT_FIELDS],
        independent_reference='Reuse the unchanged original-source parser, packed histories and Python integer scale prefixes. Pair one origin at a time, buffering only its SNAIVE7 diagnostics and per-origin delta arrays; classify using exact quarter/sixteenth sums. Subtract independently computed Decimal-70 RMSSE roots directly, rather than using the SQL difference-of-squares formula. Compute rational MAE medians from central integer numerators. One guarded SQL execution exports both literal reports, diagnostics, pairs and unrounded aggregates.',
        result_rows=6,result_columns=12,output_columns=REPORT_COLUMNS,results=results,rows_with_pass_status=6,ordered_result_sha256=json_hash(results),result_field_mismatches=0,
        prior_sql39_results=prior_results,rmsse_status_summary=reference.status_summary,
        pilot_series_count=216,pilot_paired_rows_compared=len(paired.pilot_pairs),pilot_exact_pairs_sha256=exact_pair_hash(paired.pilot_pairs),
        pilot_accepted_sql37_report_sha256=json_hash(paired.pilot_reports),pilot_previous_evidence_matched=True,
        prior_pilot_tables_rebuilt=False,sql40_has_no_table_writes=True,input_projection_row_counts=counts,
        input_projection_sha256_before=before_hashes,input_projection_sha256_after=after_hashes,input_projections_unchanged=True,
        candidate_csv_sha256_before=candidate_before,candidate_csv_sha256_after=candidate_before,saved_candidate_unchanged=True,
        fixture_cases_passed=len(cases),fixture_cases=cases,timings=timings,
        final_holdout_unit_values_inspected=False,final_holdout_errors_computed=False,final_model_selected=False,
        real_product_identifiers_published=False,individual_pairs_or_diagnostics_published=False,
        evidence_scope='Assistant full-catalog paired preflight only; learner SQL40 execution pending. Every MAE series remains included, while undefined common RMSSE scales are excluded and counted. Exact equality defines ties, not displayed rounding. These are descriptive development comparisons, not significance tests, per-series model choices or final selection. All sources, candidates, prior evidence and fixed protocols remain unchanged.')
    serialized=json.dumps(evidence,indent=2,ensure_ascii=False)+'\n'
    assert all(item not in serialized for item,_,_ in products)
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(serialized,encoding='utf-8',newline='\n')
    print(json.dumps({'fixture_cases_passed':len(cases),'results':results,'ordered_result_sha256':json_hash(results),
                      'paired_exact_sha256':comparisons['PAIR']['observed_exact_sha256'],'timings':timings}),flush=True)


if __name__=='__main__':main()
