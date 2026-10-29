"""Verify selected-product weekly price context against original CSVs in private databases."""
import argparse
import csv
import re
import hashlib
import json
import subprocess
import sys
import tempfile
import time
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

sys.dont_write_bytecode = True
from preflight_product_abc_xyz import reference, matrix, assert_combined
from preflight_abc_xyz_contribution import SNAPSHOTS
from preflight_az_product_drilldown import row_hash
from preflight_az_leading_product_weekly import trajectory_reference, assert_trajectory, canonical_trajectory
from preflight_abc_threshold_sensitivity import baseline_summary
from preflight_product_variability import (
    assert_exact_rows, fingerprint, parse, quote, reference_report, sha256,
    source_weekly_rows, source_weekly_report,
)
from preflight_product_xyz import assert_xyz, xyz_report
from preflight_az_leading_product_store_comparison import (
    CORE_STORES, RAW_STORES, daily_rows, daily_projection, store_reference, canonical_store_report,
)

COLUMNS = ['item_id', 'week_start', 'week_end', 'units', 'priced_stores', 'missing_price_stores',
           'min_price_usd', 'max_price_usd', 'comparable_stores', 'price_up_stores', 'price_down_stores', 'check_status']
PRICE_FIELDS = ['store_id', 'item_id', 'wm_yr_wk', 'sell_price']
INTEGER_FIELDS = ['units', 'priced_stores', 'missing_price_stores', 'comparable_stores', 'price_up_stores', 'price_down_stores']


def source_price_rows(path, item, stores):
    """Stream the original text CSV; retain and verify only this item and displayed weeks."""
    result, seen = [], set()
    with path.open(newline='', encoding='utf-8-sig') as stream:
        reader = csv.DictReader(stream)
        assert reader.fieldnames == PRICE_FIELDS
        for row in reader:
            if row['item_id'] != item:
                continue
            assert re.fullmatch(r'[1-9][0-9]{4}', row['wm_yr_wk'])
            week = int(row['wm_yr_wk'])
            if not 11601 <= week <= 11612:
                continue
            assert row['store_id'] in stores
            assert re.fullmatch(r'[0-9]+([.][0-9]{1,2}0*)?', row['sell_price'])
            price = Decimal(row['sell_price'])
            assert price.is_finite() and 0 < price < Decimal('10000000000000000')
            assert price == price.quantize(Decimal('.01'))
            key = (row['store_id'], week)
            assert key not in seen
            seen.add(key)
            result.append(dict(store_id=row['store_id'], item_id=item, wm_yr_wk=week, sell_price=price))
    return sorted(result, key=lambda r: (r['store_id'], r['wm_yr_wk']))


def price_projection(item):
    condition = 'false' if item is None else f'item_id={quote(item)}'
    return f"SELECT store_id,item_id,wm_yr_wk,sell_price FROM stg.m5_prices WHERE {condition} AND (wm_yr_wk BETWEEN 11601 AND 11612 OR wm_yr_wk IS NULL) ORDER BY store_id,wm_yr_wk,sell_price;"


def price_reference(selected, stores, prices):
    if selected is None:
        return [dict(zip(COLUMNS, [None]*11+['EMPTY']))]
    price_map = {(r['store_id'], r['wm_yr_wk']): r['sell_price'] for r in prices}
    assert len(price_map) == len(prices)
    rows = []
    for i in range(12):
        week = 11601+i
        pairs = [(price_map.get((s['store_id'], week)), price_map.get((s['store_id'], week-1))) for s in stores]
        current = [price for price, prior in pairs if price is not None]
        comparable = [(price, prior) for price, prior in pairs if price is not None and prior is not None]
        units = sum(sum(s['days'][7*i:7*(i+1)]) for s in stores)
        for store in stores:
            if sum(store['days'][7*i:7*(i+1)]) > 0:
                assert (store['store_id'], week) in price_map
        rows.append(dict(item_id=selected['item_id'], week_start=(date(2016,1,30)+timedelta(days=7*i)).isoformat(),
                         week_end=(date(2016,2,5)+timedelta(days=7*i)).isoformat(), units=units,
                         priced_stores=len(current), missing_price_stores=len(stores)-len(current),
                         min_price_usd=min(current) if current else None, max_price_usd=max(current) if current else None,
                         comparable_stores=None if i==0 else len(comparable),
                         price_up_stores=None if i==0 else sum(price>prior for price,prior in comparable),
                         price_down_stores=None if i==0 else sum(price<prior for price,prior in comparable),check_status='PASS'))
    assert sum(r['units'] for r in rows)==int(selected['units_84d'])
    return rows


def canonical_price_report(rows):
    result=[]
    for row in rows:
        assert list(row)==COLUMNS, 'Unexpected output column names/order'
        normalized=dict(row)
        for key in INTEGER_FIELDS:
            if row[key] is not None:
                value=Decimal(str(row[key]))
                assert value.is_finite() and value==int(value)
                normalized[key]=int(value)
        for key in ('min_price_usd','max_price_usd'):
            value=None if row[key] is None else Decimal(str(row[key]))
            if value is not None:
                assert value.is_finite() and value>0 and value==value.quantize(Decimal('.01'))
            normalized[key]=None if value is None else format(value,'.2f')
        result.append(normalized)
    return result


def assert_price_report(actual, selected, stores, prices, context):
    expected=price_reference(selected,stores,prices)
    assert_exact_rows(actual,expected,context)
    assert canonical_price_report(actual)==canonical_price_report(expected),context
    if selected is None:
        assert len(actual)==1 and all(actual[0][key] is None for key in COLUMNS[:-1])
        assert actual[0]['check_status']=='EMPTY'
    else:
        assert len(actual)==12
        assert [r['week_start'] for r in actual]==sorted(r['week_start'] for r in actual)
        assert all(actual[0][key] is None for key in ('comparable_stores','price_up_stores','price_down_stores'))
        assert all(r['priced_stores']+r['missing_price_stores']==len(stores) for r in actual)
        assert all(r['price_up_stores']+r['price_down_stores']<=r['comparable_stores']<=r['priced_stores'] for r in actual[1:])
    return expected


def aggregate_prices(rows):
    rows=canonical_price_report(rows)
    comparable=sum(r['comparable_stores'] for r in rows[1:])
    up=sum(r['price_up_stores'] for r in rows[1:])
    down=sum(r['price_down_stores'] for r in rows[1:])
    prices=[Decimal(r[key]) for r in rows for key in ('min_price_usd','max_price_usd') if r[key] is not None]
    return dict(week_count=len(rows),units_total=sum(r['units'] for r in rows),
                priced_store_weeks=sum(r['priced_stores'] for r in rows),missing_price_store_weeks=sum(r['missing_price_stores'] for r in rows),
                minimum_priced_stores_per_week=min(r['priced_stores'] for r in rows),maximum_priced_stores_per_week=max(r['priced_stores'] for r in rows),
                weeks_with_missing_prices=sum(r['missing_price_stores']>0 for r in rows),weeks_without_any_price=sum(r['priced_stores']==0 for r in rows),
                minimum_price_usd=None if not prices else format(min(prices),'.2f'),maximum_price_usd=None if not prices else format(max(prices),'.2f'),
                comparable_store_transitions=comparable,price_up_store_transitions=up,price_down_store_transitions=down,unchanged_price_store_transitions=comparable-up-down,
                weeks_with_price_up=sum(r['price_up_stores']>0 for r in rows[1:]),weeks_with_price_down=sum(r['price_down_stores']>0 for r in rows[1:]),
                first_week_comparison_fields_null=True,ordered_price_context_sha256=row_hash(canonical_price_report(rows)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--duckdb', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--fixtures-only', action='store_true')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    tmp_root = root / 'tmp'
    tmp_root.mkdir(exist_ok=True)
    script_paths = {
        '09': 'sql/09_stage_prices.sql',
        '21': 'sql/21_build_product_abc_units.sql', '23': 'sql/23_build_product_weekly.sql',
        '24': 'sql/24_build_product_variability.sql', '25': 'sql/25_build_product_xyz.sql',
        '27': 'sql/27_build_product_abc_xyz.sql', '30': 'sql/30_az_leading_product_weekly.sql',
        '31': 'sql/31_az_leading_product_store_comparison.sql',
        '32': 'sql/32_az_leading_product_price_context.sql',
    }
    script_bytes = {key: (root / path).read_bytes() for key, path in script_paths.items()}
    scripts = {}
    for key in ('09', '21', '23', '24', '25', '27'):
        build, audit = script_bytes[key].decode('utf-8').split('-- VALIDATION:', 1)
        scripts[key] = (build, '-- VALIDATION:' + audit)
    query = script_bytes['32'].decode('utf-8')
    helper_paths = ['validation/preflight_product_abc_xyz.py', 'validation/preflight_abc_xyz_contribution.py',
                    'validation/preflight_az_product_drilldown.py', 'validation/preflight_az_leading_product_weekly.py',
                    'validation/preflight_abc_threshold_sensitivity.py', 'validation/preflight_product_variability.py',
                    'validation/preflight_product_xyz.py', 'validation/preflight_xyz_threshold_sensitivity.py',
                    'validation/preflight_az_leading_product_store_comparison.py']
    helper_hashes = {path: sha256(root / path) for path in helper_paths}
    historical = {p.relative_to(root).as_posix(): sha256(p) for p in (root / 'data').glob('*_preflight.json')
                  if p.name != 'az_leading_product_price_context_preflight.json'}
    cases = []

    def sparse(entries):
        return [entries.get(i, 0) for i in range(84)]

    mixed = [sparse({0:10,42:50,49:50}),sparse({0:50,42:20}),[0]*84]

    def tiny(name, vectors=None, mutation='', reject=False, reverse_input=False, omitted=()):
        vectors=mixed if vectors is None else vectors
        stores=[dict(store_id=store,state_id=state,days=vector) for store,state,vector in
                zip(('S02','S01','S03'),('WEST','EAST','NORTH'),vectors)]
        weekly=[sum(sum(s['days'][i*7:(i+1)*7]) for s in stores) for i in range(12)]
        source=[dict(item_id='P001',dept_id='FOODS_1',cat_id='FOODS',weeks=weekly,
                     units_90d=sum(weekly),excluded_six_day_units=0)]
        abc,_,expected=reference(source)
        selected,_=trajectory_reference(source,expected)
        expected_days=daily_rows('P001',stores)
        price_vectors={'S02':['1.01','1.02','1.02','1.01']+['1.01']*8,
                       'S01':['2.00','1.00','1.00','3.00']+['3.00']*8,'S03':['0.01']*12}
        prices=[dict(store_id=store,item_id='P001',wm_yr_wk=11601+i,sell_price=Decimal(value))
                for store,vector in sorted(price_vectors.items()) for i,value in enumerate(vector)
                if (store,11601+i) not in omitted]

        def values(rows):
            rows=list(reversed(rows)) if reverse_input else rows
            return ','.join('('+','.join('NULL' if v is None else str(v) if isinstance(v,int) else quote(v)
                                         for v in row.values())+')' for row in rows)

        mappings=[dict(store_id=s['store_id'],state_id=s['state_id']) for s in stores]
        setup=f"""CREATE SCHEMA raw; CREATE SCHEMA core; CREATE SCHEMA mart; CREATE SCHEMA stg;
CREATE TABLE core.m5_product(item_id VARCHAR,dept_id VARCHAR,cat_id VARCHAR);
INSERT INTO core.m5_product VALUES ('P001','FOODS_1','FOODS');
CREATE TABLE core.m5_store(store_id VARCHAR,state_id VARCHAR);
INSERT INTO core.m5_store VALUES {values(mappings)};
CREATE TABLE raw.m5_sales_wide(store_id VARCHAR,state_id VARCHAR);
INSERT INTO raw.m5_sales_wide VALUES {values(mappings)};
CREATE TABLE mart.m5_product_weekly_12w(item_id VARCHAR,dept_id VARCHAR,cat_id VARCHAR,wm_yr_wk INTEGER,
week_start DATE,week_end DATE,units HUGEINT,source_daily_rows BIGINT);
INSERT INTO mart.m5_product_weekly_12w VALUES {values(source_weekly_rows(source,3))};
CREATE TABLE mart.m5_product_abc_90d(item_id VARCHAR,dept_id VARCHAR,cat_id VARCHAR,window_start DATE,
window_end DATE,units HUGEINT,sku_rank BIGINT,cumulative_units HUGEINT,abc_class VARCHAR);
INSERT INTO mart.m5_product_abc_90d VALUES {values(abc)};
CREATE TABLE mart.m5_sales_daily(item_id VARCHAR,store_id VARCHAR,d VARCHAR,date DATE,wm_yr_wk INTEGER,units INTEGER);
INSERT INTO mart.m5_sales_daily VALUES {values(expected_days)};
CREATE TABLE stg.m5_prices(store_id VARCHAR,item_id VARCHAR,wm_yr_wk INTEGER,sell_price DECIMAL(18,2));
INSERT INTO stg.m5_prices VALUES {values(prices)};
"""
        old,new='3049 AS expected_items,10 AS expected_stores','1 AS expected_items,3 AS expected_stores'
        with tempfile.TemporaryDirectory(prefix='az-price-fixture-',dir=tmp_root) as folder:
            assert Path(folder).resolve().is_relative_to(tmp_root.resolve())
            database=Path(folder)/'fixture.duckdb'
            settings="SET threads=2; SET memory_limit='2GB';\n"

            def execute(sql):
                return subprocess.run([args.duckdb,str(database),'-bail','-json'],input=settings+sql,
                                      text=True,encoding='utf-8',capture_output=True)

            run=execute(setup+scripts['24'][0].replace(old,new)+scripts['25'][0].replace(old,new)
                        +scripts['27'][0].replace(old,new)+mutation)
            assert run.returncode==0,(name,run.stderr)
            queries=dict(SNAPSHOTS,selected_daily_84d=daily_projection(None if selected is None else selected['item_id']),
                         core_store_mapping=CORE_STORES,raw_distinct_store_mapping=RAW_STORES,
                         selected_price_projection=price_projection(None if selected is None else selected['item_id']))
            before={}
            for key,sql in queries.items():
                run=execute(sql)
                assert run.returncode==0,(name,run.stderr)
                before[key]=parse(run.stdout)
            run=execute(query.replace(old,new))
            if reject:
                assert run.returncode!=0 and ('A Z price context blocked' in run.stderr or 'XYZ blocked' in run.stderr),(name,run.stderr)
            else:
                assert run.returncode==0,(name,run.stderr)
                assert_combined(before['combined'],source,before)
                observed=parse(run.stdout)
                assert_price_report(observed,selected,stores,prices,name)
                assert_exact_rows(before['selected_daily_84d'],[] if selected is None else expected_days,name+' raw daily cells')
                assert_exact_rows(before['selected_price_projection'],[] if selected is None else prices,name+' selected source prices')
                if name=='exact_cent_changes_equal_prices_and_reversed_input':
                    assert observed[1]['price_up_stores']==observed[1]['price_down_stores']==1
                    assert observed[2]['price_up_stores']==observed[2]['price_down_stores']==0
                if name=='missing_zero_sales_price_then_return_does_not_bridge_gap':
                    assert observed[1]['missing_price_stores']==1
                    assert observed[2]['priced_stores']==3 and observed[2]['comparable_stores']==2
                if name=='all_prices_missing_in_zero_sales_week_keep_null_extrema':
                    assert int(observed[2]['units'])==observed[2]['priced_stores']==0
                    assert observed[2]['min_price_usd'] is observed[2]['max_price_usd'] is None
                    assert observed[3]['comparable_stores']==0
            for key,sql in queries.items():
                run=execute(sql)
                assert run.returncode==0 and parse(run.stdout)==before[key],(name,key,'input projection changed')
        assert not Path(folder).exists()
        cases.append(dict(case=name,passed=True,rejected=reject,five_snapshots_and_four_projections_unchanged=True))
        if len(cases)==1:
            print(json.dumps({'first_fixture_passed':name}),flush=True)

    tiny('exact_cent_changes_equal_prices_and_reversed_input',reverse_input=True)
    tiny('missing_zero_sales_price_then_return_does_not_bridge_gap',omitted=(('S03',11602),))
    tiny('all_prices_missing_in_zero_sales_week_keep_null_extrema',omitted=tuple((s,11603) for s in ('S01','S02','S03')))
    tiny('missing_first_week_zero_sales_price_keeps_first_comparisons_null',omitted=(('S03',11601),))
    tiny('valid_empty_positive_sources_have_eleven_null_fields',vectors=[[1]*84]*3)
    tiny('valid_empty_zero_sources_have_eleven_null_fields',vectors=[[0]*84]*3)
    tiny('unused_daily_price_columns_do_not_change_context',mutation="ALTER TABLE mart.m5_sales_daily ADD COLUMN sell_price DECIMAL(18,2); ALTER TABLE mart.m5_sales_daily ADD COLUMN has_price BOOLEAN; ALTER TABLE mart.m5_sales_daily ADD COLUMN estimated_sales_value DECIMAL(28,2);")
    tiny('unrelated_product_and_outside_window_prices_are_out_of_scope',mutation="INSERT INTO stg.m5_prices VALUES ('OTHER','OTHER',11601,NULL),('S01','P001',11600,NULL);")
    tiny('invalid_empty_price_schema_still_rejected',vectors=[[1]*84]*3,mutation="ALTER TABLE stg.m5_prices ALTER sell_price TYPE DOUBLE;",reject=True)
    tiny('invalid_empty_mapping_still_rejected',vectors=[[1]*84]*3,mutation="UPDATE core.m5_store SET state_id='WRONG' WHERE store_id='S01';",reject=True)
    for name,mutation in [
        ('missing_price_with_positive_units',"DELETE FROM stg.m5_prices WHERE store_id='S02' AND wm_yr_wk=11601;"),
        ('duplicate_price_key',"INSERT INTO stg.m5_prices SELECT * FROM stg.m5_prices WHERE store_id='S01' AND wm_yr_wk=11601;"),
        ('null_price_is_invalid_record_not_valid_missing_key',"UPDATE stg.m5_prices SET sell_price=NULL WHERE store_id='S03' AND wm_yr_wk=11602;"),
        ('zero_price_rejected',"UPDATE stg.m5_prices SET sell_price=0 WHERE store_id='S03' AND wm_yr_wk=11602;"),
        ('negative_price_rejected',"UPDATE stg.m5_prices SET sell_price=-1 WHERE store_id='S03' AND wm_yr_wk=11602;"),
        ('null_price_store_rejected',"UPDATE stg.m5_prices SET store_id=NULL WHERE store_id='S03' AND wm_yr_wk=11602;"),
        ('orphan_price_store_rejected',"UPDATE stg.m5_prices SET store_id='ORPHAN' WHERE store_id='S03' AND wm_yr_wk=11602;"),
        ('null_selected_price_week_rejected',"UPDATE stg.m5_prices SET wm_yr_wk=NULL WHERE store_id='S03' AND wm_yr_wk=11602;"),
        ('price_double_type_rejected',"ALTER TABLE stg.m5_prices ALTER sell_price TYPE DOUBLE;"),
        ('price_week_bigint_type_rejected',"ALTER TABLE stg.m5_prices ALTER wm_yr_wk TYPE BIGINT;"),
        ('extra_price_schema_column_rejected',"ALTER TABLE stg.m5_prices ADD COLUMN extra VARCHAR;"),
        ('missing_zero_day_cannot_be_filled_as_zero',"DELETE FROM mart.m5_sales_daily WHERE store_id='S02' AND d='d_1829';"),
        ('duplicate_and_missing_zero_day_preserve_count_and_units',"UPDATE mart.m5_sales_daily SET d='d_1830',date=DATE '2016-02-01' WHERE store_id='S02' AND d='d_1829';"),
        ('incorrect_day_identifier',"UPDATE mart.m5_sales_daily SET d='d_0000' WHERE store_id='S02' AND d='d_1829';"),
        ('incorrect_retail_week',"UPDATE mart.m5_sales_daily SET wm_yr_wk=11602 WHERE store_id='S02' AND d='d_1829';"),
        ('incorrect_daily_date',"UPDATE mart.m5_sales_daily SET date=date+1 WHERE store_id='S02' AND d='d_1829';"),
        ('orphan_daily_store',"UPDATE mart.m5_sales_daily SET store_id='ORPHAN' WHERE store_id='S02' AND d='d_1829';"),
        ('core_state_mapping_disagrees_with_raw',"UPDATE core.m5_store SET state_id='WRONG' WHERE store_id='S01';"),
        ('conflicting_raw_store_state_mapping',"INSERT INTO raw.m5_sales_wide VALUES ('S01','WRONG');"),
        ('missing_core_store',"DELETE FROM core.m5_store WHERE store_id='S03';"),
        ('duplicate_core_store',"INSERT INTO core.m5_store SELECT * FROM core.m5_store WHERE store_id='S03';"),
        ('null_daily_units_not_zero',"UPDATE mart.m5_sales_daily SET units=NULL WHERE store_id='S02' AND d='d_1829';"),
        ('negative_daily_units',"UPDATE mart.m5_sales_daily SET units=-1 WHERE store_id='S02' AND d='d_1829';"),
        ('daily_integer_contract_wrong_type',"ALTER TABLE mart.m5_sales_daily ALTER units TYPE BIGINT;"),
        ('combined_copied_field_corruption',"UPDATE mart.m5_product_abc_xyz SET excluded_six_day_units=1;"),
        ('abc_class_corruption',"UPDATE mart.m5_product_abc_90d SET abc_class='B';"),
    ]:
        tiny(name,mutation=mutation,reject=True)
    print(json.dumps({'fixture_cases_passed':len(cases)}),flush=True)
    if args.fixtures_only:
        return

    source_root=Path('D:/database/m5-forecasting-accuracy')
    sources=[source_root/name for name in ('sales_train_evaluation.csv','calendar.csv','sell_prices.csv')]
    registry=json.loads((root/'data/m5_source_audit.json').read_text(encoding='utf-8'))
    hashes={p.name:sha256(p) for p in sources}
    assert all(hashes[p.name]==registry['files'][p.name]['sha256'] for p in sources)
    columns=','.join(f'd_{day}' for day in range(1824,1914))
    setup=f"""CREATE SCHEMA raw; CREATE SCHEMA core; CREATE SCHEMA mart;
CREATE TABLE core.m5_calendar AS SELECT d,CAST(date AS DATE) AS date,CAST(wm_yr_wk AS INTEGER) AS wm_yr_wk
FROM read_csv({quote(sources[1].as_posix())},header=true,all_varchar=true);
CREATE TABLE raw.sales_window_wide AS SELECT id,item_id,dept_id,cat_id,store_id,state_id,{columns}
FROM read_csv({quote(sources[0].as_posix())},header=true,all_varchar=true);
CREATE VIEW raw.m5_sales_wide AS SELECT store_id,state_id FROM raw.sales_window_wide;
CREATE TABLE core.m5_product AS SELECT DISTINCT item_id,dept_id,cat_id FROM raw.sales_window_wide;
CREATE TABLE core.m5_store AS SELECT DISTINCT store_id,state_id FROM raw.sales_window_wide;
CREATE TABLE mart.m5_sales_daily AS
WITH u AS (UNPIVOT raw.sales_window_wide ON {columns} INTO NAME d VALUE units_text)
SELECT u.item_id,u.store_id,u.d,c.date,c.wm_yr_wk,
CASE WHEN regexp_full_match(u.units_text,'[0-9]+') AND TRY_CAST(u.units_text AS INTEGER) IS NOT NULL
THEN CAST(u.units_text AS INTEGER) ELSE error('Source requires nonnegative INTEGER units') END AS units
FROM u JOIN core.m5_calendar c USING(d);
"""

    def wide_sum(days,alias):
        names=','.join(f'd_{day}' for day in days)
        return f"SUM(list_sum(list_transform(list_value({names}),lambda x: CASE WHEN regexp_full_match(x,'[0-9]+') AND TRY_CAST(x AS INTEGER) IS NOT NULL THEN CAST(x AS BIGINT) ELSE error('Wide reference requires nonnegative INTEGER units') END))) AS {alias}"

    expressions=[wide_sum(range(1828+i*7,1835+i*7),f'w{i}') for i in range(12)]
    expressions += [wide_sum(range(1824,1914),'units_90d'),wide_sum([1824,1825,1826,1827,1912,1913],'excluded_six_day_units')]
    vector_sql='SELECT item_id,dept_id,cat_id,'+','.join(expressions)+' FROM raw.sales_window_wide GROUP BY item_id,dept_id,cat_id ORDER BY item_id;'
    accepted_path='data/az_leading_product_weekly_learner_acceptance.json'
    accepted_bytes=(root/accepted_path).read_bytes()
    accepted=json.loads(accepted_bytes.decode('utf-8'))
    assert accepted['rows_with_pass_status']==12
    store_accepted_path='data/az_leading_product_store_comparison_learner_acceptance.json'
    store_accepted_bytes=(root/store_accepted_path).read_bytes()
    store_accepted=json.loads(store_accepted_bytes.decode('utf-8'))
    assert store_accepted['rows_with_pass_status']==11
    timings={}
    with tempfile.TemporaryDirectory(prefix='az-price-context-',dir=tmp_root) as folder:
        assert Path(folder).resolve().is_relative_to(tmp_root.resolve())
        database=Path(folder)/'preflight.duckdb'
        settings=f"SET threads=2; SET memory_limit='2GB'; SET temp_directory={quote((Path(folder)/'spill').as_posix())};\n"

        def execute(sql,label=None):
            started=time.perf_counter()
            run=subprocess.run([args.duckdb,str(database),'-bail','-json'],input=settings+sql,text=True,encoding='utf-8',capture_output=True)
            assert run.returncode==0,run.stderr
            if label:
                timings[label]=round(time.perf_counter()-started,3)
            return parse(run.stdout) if run.stdout.strip() else None

        execute(setup,'window_setup_seconds')
        print(json.dumps({'window_setup_seconds':timings['window_setup_seconds']}),flush=True)
        upstream={}
        for key in ('21','23','24','25','27'):
            execute(scripts[key][0],f'sql{key}_build_seconds')
            upstream[key]=execute(scripts[key][1],f'sql{key}_validation_seconds')
        raw=execute(vector_sql,'independent_wide_vector_query_seconds')
        assert len(raw)==len({r['item_id'] for r in raw})==3049
        source=[dict(item_id=r['item_id'],dept_id=r['dept_id'],cat_id=r['cat_id'],weeks=[int(r[f'w{i}']) for i in range(12)],
                     units_90d=int(r['units_90d']),excluded_six_day_units=int(r['excluded_six_day_units'])) for r in raw]
        for row in source:
            assert row['units_90d']==sum(row['weeks'])+row['excluded_six_day_units']
        abc,xyz,expected=reference(source)
        selected,_=trajectory_reference(source,expected)
        assert selected is not None
        wide_days=','.join(f'd_{day}' for day in range(1828,1912))
        original_stores=execute(f"SELECT store_id,state_id,list_value({wide_days}) AS day_values FROM raw.sales_window_wide WHERE item_id={quote(selected['item_id'])} ORDER BY store_id;",'independent_store_day_arrays_query_seconds')
        assert len(original_stores)==len({s['store_id'] for s in original_stores})==10
        store_source=[dict(store_id=s['store_id'],state_id=s['state_id'],days=[int(x) for x in s['day_values']]) for s in original_stores]
        expected_days=daily_rows(selected['item_id'],store_source)
        raw_mapping=execute('SELECT DISTINCT store_id,state_id FROM raw.sales_window_wide ORDER BY store_id,state_id;')
        assert_exact_rows([{k:s[k] for k in ('store_id','state_id')} for s in store_source],raw_mapping,'original item/store mapping')
        price_started=time.perf_counter()
        original_prices=source_price_rows(sources[2],selected['item_id'],{s['store_id'] for s in store_source})
        timings['independent_python_price_csv_stream_seconds']=round(time.perf_counter()-price_started,3)
        execute(f"""CREATE TABLE raw.m5_prices AS
SELECT store_id,item_id,wm_yr_wk,sell_price FROM read_csv({quote(sources[2].as_posix())},header=true,all_varchar=true)
WHERE item_id={quote(selected['item_id'])} AND (TRY_CAST(wm_yr_wk AS INTEGER) BETWEEN 11601 AND 11612 OR TRY_CAST(wm_yr_wk AS INTEGER) IS NULL);
"""+scripts['09'][0],'selected_price_csv_staging_seconds')
        queries=dict(SNAPSHOTS,selected_daily_84d=daily_projection(selected['item_id']),core_store_mapping=CORE_STORES,
                     raw_distinct_store_mapping=RAW_STORES,selected_price_projection=price_projection(selected['item_id']))
        before={key:execute(sql) for key,sql in queries.items()}
        assert_exact_rows(before['abc'],abc,'original wide ABC fields')
        assert_exact_rows(before['weekly'],source_weekly_rows(source,10),'original wide weekly values')
        assert_exact_rows(upstream['21'],baseline_summary(abc),'original wide ABC report')
        assert_exact_rows(upstream['23'],source_weekly_report(source_weekly_rows(source,10)),'original wide weekly report')
        assert_exact_rows(upstream['24'],reference_report([{k:v for k,v in r.items() if k!='xyz_class'} for r in xyz]),'original wide metrics')
        assert_xyz(before['xyz'],xyz,before['metrics'])
        assert_exact_rows(upstream['25'],xyz_report(xyz),'original wide XYZ report')
        float_errors=assert_combined(before['combined'],source,before)
        assert_exact_rows(upstream['27'],matrix(expected),'original wide combined matrix')
        assert_exact_rows(before['selected_daily_84d'],expected_days,'all original selected 840 daily cells')
        assert_exact_rows(before['core_store_mapping'],raw_mapping,'original core store mapping')
        assert_exact_rows(before['raw_distinct_store_mapping'],raw_mapping,'original raw store mapping')
        selected_vector=next(r['weeks'] for r in source if r['item_id']==selected['item_id'])
        assert [sum(sum(s['days'][i*7:(i+1)*7]) for s in store_source) for i in range(12)]==selected_vector
        assert_exact_rows(before['selected_price_projection'],original_prices,'original selected price CSV rows and exact cents')
        reconstructed_store_report=store_reference(selected,store_source)
        reconstructed_store_hash=row_hash(canonical_store_report(reconstructed_store_report))
        assert reconstructed_store_hash==store_accepted['store_aggregates']['ordered_store_report_sha256']
        input_hashes={key:fingerprint(rows) for key,rows in before.items()}
        trajectory=execute(script_bytes['30'].decode('utf-8'),'accepted_trajectory_query_seconds')
        assert_trajectory(trajectory,source,expected,'reconstructed accepted weekly trajectory')
        trajectory_hash=row_hash(canonical_trajectory(trajectory))
        selected_hash=row_hash([selected['item_id']])
        weekly_hash=row_hash([int(r['units']) for r in trajectory])
        accepted_aggregates=accepted['trajectory_aggregates']
        assert trajectory_hash==accepted_aggregates['ordered_trajectory_sha256']
        assert selected_hash==accepted_aggregates['selected_product_sha256']
        assert weekly_hash==accepted_aggregates['ordered_weekly_units_sha256']
        actual=execute(query,'price_context_query_seconds')
        expected_report=assert_price_report(actual,selected,store_source,original_prices,'full-source twelve-week price context')
        aggregates=aggregate_prices(actual)
        assert aggregates['units_total']==accepted_aggregates['units_total']
        expected_hash=row_hash(canonical_price_report(expected_report))
        assert aggregates['ordered_price_context_sha256']==expected_hash
        after={key:execute(sql) for key,sql in queries.items()}
        for key in queries:
            assert before[key]==after[key] and input_hashes[key]==fingerprint(after[key]),(key,'input projection changed')
        database_bytes=database.stat().st_size
    assert not Path(folder).exists()
    assert all(sha256(p)==hashes[p.name] for p in sources)
    assert all(sha256(root/path)==value for path,value in historical.items())
    assert all((root/script_paths[key]).read_bytes()==value for key,value in script_bytes.items())
    assert all(sha256(root/path)==value for path,value in helper_hashes.items())
    assert (root/accepted_path).read_bytes()==accepted_bytes
    assert (root/store_accepted_path).read_bytes()==store_accepted_bytes
    report=dict(
        checked_at_utc=datetime.now(timezone.utc).isoformat(),executor='assistant',
        engine=subprocess.check_output([args.duckdb,'-version'],text=True).strip(),
        baseline_database='Private temporary on-disk DuckDB under ignored repository tmp; resolved paths checked for containment; removed after verification.',
        temporary_baseline_removed=True,temporary_database_bytes_after_close=database_bytes,
        settings={'threads':2,'memory_limit':'2GB'},script=script_paths['32'],script_sha256=hashlib.sha256(script_bytes['32']).hexdigest(),
        prerequisite_script_sha256={script_paths[key]:hashlib.sha256(script_bytes[key]).hexdigest() for key in ('09','21','23','24','25','27','30','31')},
        reference_helper_sha256=helper_hashes,source_sha256=hashes,source_hashes_unchanged=True,
        historical_preflight_sha256=historical,historical_preflights_unchanged=True,
        preflight_strategy='Original sales/calendar CSVs feed a private 90-day six-column daily table and actual SQL21,23,24,25,27. Original selected price rows for the displayed twelve weeks pass the unmodified SQL09 staging conversion. Read-only SQL30 anchors the accepted trajectory; SQL32 supplies the price report. No learner database is opened.',
        independent_reference='Original wide arrays independently define all product ABC/XYZ fields and select the leading A x Z product. Ten original 84-day store arrays supply every one of 840 reference daily cells and all weekly/store sums. A separate Python csv/Decimal stream of original sell_prices.csv checks the selected rows, unique known-store keys, positive exact cents and computes every weekly price field without SQL window functions.',
        price_source_scope='Selected product only, retail weeks 11601 through 11612. Source file hashes identify the complete supplied files; price row comparisons do not re-audit all 6.8 million price rows or the full 59-million-cell sales history.',
        analysis_window={'start_date':'2016-01-30','end_date':'2016-04-22','weeks':12,'days':84},
        selection_policy='Same accepted highest-90-day-unit A x Z product, item_id ascending tie-break; no hard-coded source identifier.',
        price_policy='Same-store prices are compared only with the immediately preceding displayed week when both records exist. First-week comparable/up/down counts are NULL. Missing zero-sales store/week prices remain unknown and are not zero-filled or bridged; missing prices with positive recorded units fail. Min/max use observed prices only.',
        timings=timings,timing_scope='DuckDB CLI process timings and the explicitly named independent Python price CSV stream; other Python comparisons and hashing excluded.',
        combined_product_rows_compared=3049,combined_columns_compared=22,combined_field_mismatches=0,combined_float_error_summary=float_errors,
        selected_daily_rows_compared=len(expected_days),daily_projection_columns_compared=6,selected_daily_cell_mismatches=0,
        stores_compared=10,distinct_days_per_store=84,store_week_grid_positions_covered=len(store_source)*12,
        original_store_state_mapping_matched=True,original_twelve_week_vector_matched=True,
        selected_price_source_rows_compared=len(original_prices),price_projection_columns_compared=4,selected_price_field_mismatches=0,
        selected_price_keys_unique=True,selected_source_prices_positive_exact_cents=True,missing_positive_sales_price_cells=0,
        accepted_trajectory_fingerprints_matched=True,accepted_baseline_evidence=accepted_path,
        accepted_baseline_evidence_sha256=hashlib.sha256(accepted_bytes).hexdigest(),
        accepted_store_report_fingerprint_matched=True,accepted_store_evidence=store_accepted_path,
        accepted_store_evidence_sha256=hashlib.sha256(store_accepted_bytes).hexdigest(),reconstructed_store_report_sha256=reconstructed_store_hash,
        selected_product_sha256=selected_hash,reconstructed_trajectory_sha256=trajectory_hash,reconstructed_weekly_units_sha256=weekly_hash,
        result_rows=len(actual),rows_with_pass_status=len(actual),result_columns=len(COLUMNS),output_columns=COLUMNS,
        result_field_mismatches=0,column_names_and_order_verified=True,chronological_week_order_verified=True,
        price_context_aggregates=aggregates,independent_reference_price_report_sha256=expected_hash,
        fingerprint_method='SHA256 of UTF-8 compact JSON with sorted object keys and ensure_ascii=False. Report rows are chronological; units and counts are JSON integers, price extrema two-decimal strings or NULL, and first-week comparison counts NULL. Identifiers occur only in memory before hashing.',
        unchanged_input_scope='Five complete accepted snapshots (ABC, weekly, variability, XYZ, combined), plus selected six-column 840-row daily projection, complete two-column core store mapping, distinct raw store/state mapping and selected four-column price projection. This is not a full-table daily/raw-wide/price equality audit.',
        five_snapshots_and_four_projections_unchanged=True,input_rows_sha256_before=input_hashes,
        input_rows_sha256_after={key:fingerprint(rows) for key,rows in after.items()},
        input_projection_row_counts={key:len(rows) for key,rows in before.items()},
        real_sku_identifiers_published=False,real_store_identifiers_published=False,store_detail_rows_published=False,
        daily_or_weekly_vectors_published=False,weekly_price_rows_published=False,
        fixture_cases_passed=len(cases),fixture_cases=cases,
        scope='Assistant preflight only; learner local price context pending. Public evidence contains aggregate controls and one-way fingerprints, never real item/store identifiers, row-level prices or day/week vectors. Published weekly sell_price is descriptive context and does not establish realised transaction prices, promotions, price causation, demand growth, availability, stockouts or replenishment needs.')
    serialized=json.dumps(report,indent=2,default=str,ensure_ascii=False)+'\n'
    assert all(row['item_id'] not in serialized for row in source),'Public report contains a real product identifier'
    assert all(s['store_id'] not in serialized for s in store_source),'Public report contains a real store identifier'
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(serialized,encoding='utf-8',newline='\n')
    print(json.dumps({'fixture_cases_passed':len(cases),'price_context_aggregates':aggregates,'timings':timings,'public_identifiers':False},default=str),flush=True)


if __name__=='__main__':
    main()
