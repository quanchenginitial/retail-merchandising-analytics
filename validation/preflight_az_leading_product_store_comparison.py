"""Verify selected-product store comparison against original daily CSV cells in private databases."""
import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
import time
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
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

COLUMNS = ['item_id', 'store_id', 'state_id', 'units_first6w', 'units_last6w', 'unit_difference',
           'late_unit_share_pct', 'units_84d', 'first6w_window', 'last6w_window', 'check_status']
CORE_STORES = 'SELECT store_id,state_id FROM core.m5_store ORDER BY store_id,state_id;'
RAW_STORES = 'SELECT DISTINCT store_id,state_id FROM raw.m5_sales_wide ORDER BY store_id,state_id;'


def pct(part, whole):
    return None if whole == 0 else (Decimal(part) * 100 / Decimal(whole)).quantize(Decimal('.0001'), rounding=ROUND_HALF_UP)


def daily_rows(item, stores):
    result = []
    for store in sorted(stores, key=lambda r: r['store_id']):
        assert len(store['days']) == 84
        for i, units in enumerate(store['days']):
            assert isinstance(units, int) and 0 <= units <= 2147483647
            result.append(dict(item_id=item, store_id=store['store_id'], d=f'd_{1828+i}',
                               date=(date(2016, 1, 30) + timedelta(days=i)).isoformat(),
                               wm_yr_wk=11601+i//7, units=units))
    return result


def daily_projection(item):
    condition = 'false' if item is None else f'item_id={quote(item)}'
    return f"SELECT item_id,store_id,d,date,wm_yr_wk,units FROM mart.m5_sales_daily WHERE {condition} AND date BETWEEN DATE '2016-01-30' AND DATE '2016-04-22' ORDER BY store_id,date,d,wm_yr_wk,units;"


def store_reference(selected, stores):
    if selected is None:
        result = dict.fromkeys(COLUMNS[:8])
        result.update(first6w_window='2016-01-30..2016-03-11', last6w_window='2016-03-12..2016-04-22', check_status='EMPTY')
        return [result]
    late_total = sum(sum(s['days'][42:]) for s in stores)
    records = []
    for store in sorted(stores, key=lambda s: s['store_id']):
        early, late = sum(store['days'][:42]), sum(store['days'][42:])
        records.append(dict(item_id=selected['item_id'], store_id=store['store_id'], state_id=store['state_id'],
                            units_first6w=early, units_last6w=late, unit_difference=late-early,
                            late_unit_share_pct=pct(late, late_total), units_84d=early+late,
                            first6w_window='2016-01-30..2016-03-11', last6w_window='2016-03-12..2016-04-22', check_status='PASS'))
    early_total = sum(r['units_first6w'] for r in records)
    records.append(dict(item_id=selected['item_id'], store_id='TOTAL', state_id=None,
                        units_first6w=early_total, units_last6w=late_total, unit_difference=late_total-early_total,
                        late_unit_share_pct=pct(late_total, late_total), units_84d=early_total+late_total,
                        first6w_window='2016-01-30..2016-03-11', last6w_window='2016-03-12..2016-04-22', check_status='PASS'))
    assert records[-1]['units_84d'] == int(selected['units_84d'])
    return records


def canonical_store_report(rows):
    result = []
    for row in rows:
        assert list(row) == COLUMNS, 'Unexpected output column names/order'
        normalized = dict(row)
        for key in ('units_first6w', 'units_last6w', 'unit_difference', 'units_84d'):
            if row[key] is not None:
                value = Decimal(str(row[key]))
                assert value.is_finite() and value == int(value)
                normalized[key] = int(value)
        normalized['late_unit_share_pct'] = None if row['late_unit_share_pct'] is None else format(Decimal(str(row['late_unit_share_pct'])).quantize(Decimal('.0001')), '.4f')
        result.append(normalized)
    return result


def assert_store_report(actual, selected, stores, context):
    expected = store_reference(selected, stores)
    assert_exact_rows(actual, expected, context)
    assert canonical_store_report(actual) == canonical_store_report(expected), context
    if selected is None:
        assert len(actual) == 1 and actual[0]['check_status'] == 'EMPTY'
        assert all(actual[0][key] is None for key in COLUMNS[:8])
    else:
        assert len(actual) == len(stores)+1 and actual[-1]['store_id'] == 'TOTAL'
        assert actual[-1]['state_id'] is None
        assert [r['store_id'] for r in actual[:-1]] == sorted(s['store_id'] for s in stores)
        for field in ('units_first6w', 'units_last6w', 'unit_difference', 'units_84d'):
            assert sum(int(r[field]) for r in actual[:-1]) == int(actual[-1][field])
    return expected


def aggregate_stores(rows):
    stores, total = canonical_store_report(rows[:-1]), canonical_store_report(rows[-1:])[0]
    late = [r['units_last6w'] for r in stores]
    differences = [r['unit_difference'] for r in stores]
    denominator = total['units_last6w']
    return dict(
        store_count=len(stores), units_first6w=total['units_first6w'], units_last6w=denominator,
        unit_difference=total['unit_difference'], units_84d=total['units_84d'],
        increased_stores=sum(v > 0 for v in differences), decreased_stores=sum(v < 0 for v in differences),
        unchanged_stores=sum(v == 0 for v in differences),
        zero_first6w_stores=sum(r['units_first6w'] == 0 for r in stores), zero_last6w_stores=sum(v == 0 for v in late),
        zero_84d_stores=sum(r['units_84d'] == 0 for r in stores),
        positive_unit_differences=sum(v for v in differences if v > 0), negative_unit_differences=sum(v for v in differences if v < 0),
        store_unit_difference_min=min(differences), store_unit_difference_max=max(differences),
        store_last6w_units_min=min(late), store_last6w_units_max=max(late),
        largest_store_last6w_share_pct=pct(max(late), denominator),
        top_three_stores_last6w_units=sum(sorted(late, reverse=True)[:3]),
        top_three_stores_last6w_share_pct=pct(sum(sorted(late, reverse=True)[:3]), denominator),
        displayed_store_share_sum=None if denominator == 0 else sum(Decimal(r['late_unit_share_pct']) for r in stores),
        total_share_pct=total['late_unit_share_pct'], ordered_store_report_sha256=row_hash(canonical_store_report(rows)))


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
        '21': 'sql/21_build_product_abc_units.sql', '23': 'sql/23_build_product_weekly.sql',
        '24': 'sql/24_build_product_variability.sql', '25': 'sql/25_build_product_xyz.sql',
        '27': 'sql/27_build_product_abc_xyz.sql', '30': 'sql/30_az_leading_product_weekly.sql',
        '31': 'sql/31_az_leading_product_store_comparison.sql',
    }
    script_bytes = {key: (root / path).read_bytes() for key, path in script_paths.items()}
    scripts = {}
    for key in ('21', '23', '24', '25', '27'):
        build, audit = script_bytes[key].decode('utf-8').split('-- VALIDATION:', 1)
        scripts[key] = (build, '-- VALIDATION:' + audit)
    query = script_bytes['31'].decode('utf-8')
    helper_paths = ['validation/preflight_product_abc_xyz.py', 'validation/preflight_abc_xyz_contribution.py',
                    'validation/preflight_az_product_drilldown.py', 'validation/preflight_az_leading_product_weekly.py',
                    'validation/preflight_abc_threshold_sensitivity.py', 'validation/preflight_product_variability.py',
                    'validation/preflight_product_xyz.py', 'validation/preflight_xyz_threshold_sensitivity.py']
    helper_hashes = {path: sha256(root / path) for path in helper_paths}
    historical = {p.relative_to(root).as_posix(): sha256(p) for p in (root / 'data').glob('*_preflight.json')
                  if p.name != 'az_leading_product_store_comparison_preflight.json'}
    cases = []

    def sparse(entries):
        return [entries.get(i, 0) for i in range(84)]

    mixed = [sparse({0: 10, 42: 50, 49: 50}), sparse({0: 50, 42: 20}), [0]*84]

    def tiny(name, vectors=None, mutation='', reject=False, reverse_input=False):
        vectors = mixed if vectors is None else vectors
        stores = [dict(store_id=store, state_id=state, days=vector) for store, state, vector in
                  zip(('S02', 'S01', 'S03'), ('WEST', 'EAST', 'NORTH'), vectors)]
        weekly = [sum(sum(s['days'][i*7:(i+1)*7]) for s in stores) for i in range(12)]
        source = [dict(item_id='P001', dept_id='FOODS_1', cat_id='FOODS', weeks=weekly,
                       units_90d=sum(weekly), excluded_six_day_units=0)]
        abc, _, expected = reference(source)
        selected, _ = trajectory_reference(source, expected)
        expected_days = daily_rows('P001', stores)

        def values(rows):
            rows = list(reversed(rows)) if reverse_input else rows
            return ','.join('(' + ','.join('NULL' if v is None else str(v) if isinstance(v, int) else quote(v)
                                          for v in row.values()) + ')' for row in rows)

        mappings = [dict(store_id=s['store_id'], state_id=s['state_id']) for s in stores]
        setup = f"""CREATE SCHEMA raw; CREATE SCHEMA core; CREATE SCHEMA mart;
CREATE TABLE core.m5_product(item_id VARCHAR,dept_id VARCHAR,cat_id VARCHAR);
INSERT INTO core.m5_product VALUES ('P001','FOODS_1','FOODS');
CREATE TABLE core.m5_store(store_id VARCHAR,state_id VARCHAR);
INSERT INTO core.m5_store VALUES {values(mappings)};
CREATE TABLE raw.m5_sales_wide(store_id VARCHAR,state_id VARCHAR);
INSERT INTO raw.m5_sales_wide VALUES {values(mappings)};
CREATE TABLE mart.m5_product_weekly_12w(item_id VARCHAR,dept_id VARCHAR,cat_id VARCHAR,wm_yr_wk INTEGER,
week_start DATE,week_end DATE,units HUGEINT,source_daily_rows BIGINT);
INSERT INTO mart.m5_product_weekly_12w VALUES {values(source_weekly_rows(source, 3))};
CREATE TABLE mart.m5_product_abc_90d(item_id VARCHAR,dept_id VARCHAR,cat_id VARCHAR,window_start DATE,
window_end DATE,units HUGEINT,sku_rank BIGINT,cumulative_units HUGEINT,abc_class VARCHAR);
INSERT INTO mart.m5_product_abc_90d VALUES {values(abc)};
CREATE TABLE mart.m5_sales_daily(item_id VARCHAR,store_id VARCHAR,d VARCHAR,date DATE,wm_yr_wk INTEGER,units INTEGER);
INSERT INTO mart.m5_sales_daily VALUES {values(expected_days)};
"""
        old, new = '3049 AS expected_items,10 AS expected_stores', '1 AS expected_items,3 AS expected_stores'
        with tempfile.TemporaryDirectory(prefix='az-store-fixture-', dir=tmp_root) as folder:
            assert Path(folder).resolve().is_relative_to(tmp_root.resolve())
            database = Path(folder) / 'fixture.duckdb'
            settings = "SET threads=2; SET memory_limit='2GB';\n"

            def execute(sql):
                return subprocess.run([args.duckdb, str(database), '-bail', '-json'], input=settings+sql,
                                      text=True, encoding='utf-8', capture_output=True)

            run = execute(setup + scripts['24'][0].replace(old,new) + scripts['25'][0].replace(old,new)
                          + scripts['27'][0].replace(old,new) + mutation)
            assert run.returncode == 0, (name,run.stderr)
            queries = dict(SNAPSHOTS, selected_daily_84d=daily_projection(None if selected is None else selected['item_id']),
                           core_store_mapping=CORE_STORES, raw_distinct_store_mapping=RAW_STORES)
            before = {}
            for key, sql in queries.items():
                run = execute(sql)
                assert run.returncode == 0, (name,run.stderr)
                before[key] = parse(run.stdout)
            run = execute(query.replace(old,new))
            if reject:
                assert run.returncode != 0 and ('A Z store comparison blocked' in run.stderr or 'XYZ blocked' in run.stderr), (name,run.stderr)
            else:
                assert run.returncode == 0, (name,run.stderr)
                assert_combined(before['combined'],source,before)
                observed = parse(run.stdout)
                assert_store_report(observed,selected,stores,name)
                assert_exact_rows(before['selected_daily_84d'],[] if selected is None else expected_days,name+' raw daily cells')
                if name == 'real_zero_store_negative_change_and_store_order':
                    assert any(int(r['unit_difference']) < 0 for r in observed[:-1])
                    assert any(int(r['units_84d']) == 0 for r in observed[:-1])
                    assert observed[0]['store_id'] == 'S01'
                if name == 'late_window_zero_denominator_is_null_including_total':
                    assert all(r['late_unit_share_pct'] is None for r in observed)
                    assert int(observed[-1]['unit_difference']) < 0
                if name == 'halfway_shares_round_individually_and_total_separately':
                    assert Decimal(str(next(r['late_unit_share_pct'] for r in observed if r['store_id']=='S02'))) == Decimal('.7813')
                    assert sum(Decimal(str(r['late_unit_share_pct'])) for r in observed[:-1]) == Decimal('100.0001')
                    assert Decimal(str(observed[-1]['late_unit_share_pct'])) == 100
            for key, sql in queries.items():
                run = execute(sql)
                assert run.returncode == 0 and parse(run.stdout) == before[key], (name,key,'input projection changed')
        assert not Path(folder).exists()
        cases.append(dict(case=name,passed=True,rejected=reject,five_snapshots_and_three_projections_unchanged=True))
        if len(cases)==1:
            print(json.dumps({'first_fixture_passed':name}),flush=True)

    tiny('real_zero_store_negative_change_and_store_order',reverse_input=True)
    tiny('late_window_zero_denominator_is_null_including_total',vectors=[sparse({0:5}),sparse({0:3}),[0]*84])
    tiny('halfway_shares_round_individually_and_total_separately',vectors=[sparse({42:1}),sparse({42:127}),[0]*84])
    tiny('valid_empty_positive_sources_have_eight_null_fields',vectors=[[1]*84]*3)
    tiny('valid_empty_zero_sources_have_eight_null_fields',vectors=[[0]*84]*3)
    tiny('unused_price_columns_do_not_change_unit_query',mutation="ALTER TABLE mart.m5_sales_daily ADD COLUMN sell_price DECIMAL(18,2); ALTER TABLE mart.m5_sales_daily ADD COLUMN has_price BOOLEAN; ALTER TABLE mart.m5_sales_daily ADD COLUMN estimated_sales_value DECIMAL(28,2);")
    tiny('invalid_empty_mapping_still_rejected',vectors=[[1]*84]*3,
         mutation="UPDATE core.m5_store SET state_id='WRONG' WHERE store_id='S01';",reject=True)
    for name, mutation in [
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
    ]:
        tiny(name,mutation=mutation,reject=True)
    assert len(cases)==20
    print(json.dumps({'fixture_cases_passed':len(cases)}),flush=True)
    if args.fixtures_only:
        return

    source_root=Path('D:/database/m5-forecasting-accuracy')
    sources=[source_root/name for name in ('sales_train_evaluation.csv','calendar.csv')]
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
    timings={}
    with tempfile.TemporaryDirectory(prefix='az-store-comparison-',dir=tmp_root) as folder:
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
        queries=dict(SNAPSHOTS,selected_daily_84d=daily_projection(selected['item_id']),core_store_mapping=CORE_STORES,raw_distinct_store_mapping=RAW_STORES)
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
        actual=execute(query,'store_comparison_query_seconds')
        expected_report=assert_store_report(actual,selected,store_source,'full-source eleven-row store report')
        aggregates=aggregate_stores(actual)
        assert aggregates['units_first6w']==accepted_aggregates['first_six_weeks_units']
        assert aggregates['units_last6w']==accepted_aggregates['last_six_weeks_units']
        expected_hash=row_hash(canonical_store_report(expected_report))
        assert aggregates['ordered_store_report_sha256']==expected_hash
        after={key:execute(sql) for key,sql in queries.items()}
        for key in queries:
            assert before[key]==after[key] and input_hashes[key]==fingerprint(after[key]),(key,'input projection changed')
        database_bytes=database.stat().st_size
    assert not Path(folder).exists()
    assert all(sha256(p)==hashes[p.name] for p in sources)
    assert all(sha256(root/path)==value for path,value in historical.items())
    assert all((root/script_paths[key]).read_bytes()==value for key,value in script_bytes.items())
    assert all(sha256(root/path)==value for path,value in helper_hashes.items())
    report=dict(
        checked_at_utc=datetime.now(timezone.utc).isoformat(),executor='assistant',
        engine=subprocess.check_output([args.duckdb,'-version'],text=True).strip(),
        baseline_database='Private temporary on-disk DuckDB under repository tmp; removed after verification.',
        temporary_baseline_removed=True,temporary_database_bytes_after_close=database_bytes,
        settings={'threads':2,'memory_limit':'2GB'},script=script_paths['31'],script_sha256=hashlib.sha256(script_bytes['31']).hexdigest(),
        prerequisite_script_sha256={script_paths[key]:hashlib.sha256(script_bytes[key]).hexdigest() for key in ('21','23','24','25','27','30')},
        reference_helper_sha256=helper_hashes,source_sha256=hashes,source_hashes_unchanged=True,
        historical_preflight_sha256=historical,historical_preflights_unchanged=True,
        preflight_strategy='Original sales/calendar CSVs feed a private 90-day six-column daily table, actual SQL21,23,24,25,27 and read-only SQL30,31. core.m5_store includes original state_id; a raw.m5_sales_wide view exposes only original store/state columns. No learner database is opened.',
        independent_reference='Original wide arrays independently define all product ABC/XYZ fields and select the leading A x Z product. Its ten original 84-day store arrays supply every one of 840 reference daily cells, the 12-week vector, and per-store 42-day sums. Decimal half-up rounding defines shares of the all-store late-window total.',
        comparison_windows={'first6w':{'start_date':'2016-01-30','end_date':'2016-03-11','days':42},
                            'last6w':{'start_date':'2016-03-12','end_date':'2016-04-22','days':42}},
        selection_policy='Same accepted highest-90-day-unit A x Z product, with item_id ascending as tie-break. Preserve all ten stores including true zeros; missing daily records fail rather than being treated as zero.',
        share_policy='Late share uses all stores late-window units, not net change. Zero late-window denominator gives NULL in every share including TOTAL. Signed unit differences and equal-length windows describe recorded-sales changes only.',
        timings=timings,timing_scope='DuckDB CLI process timings; excludes Python comparisons and hashing.',
        combined_product_rows_compared=3049,combined_columns_compared=22,combined_field_mismatches=0,combined_float_error_summary=float_errors,
        selected_daily_rows_compared=len(expected_days),daily_projection_columns_compared=6,selected_daily_cell_mismatches=0,
        stores_compared=10,distinct_days_per_store=84,first_half_days_per_store=42,last_half_days_per_store=42,
        first_half_daily_rows=420,last_half_daily_rows=420,original_store_state_mapping_matched=True,original_twelve_week_vector_matched=True,
        accepted_trajectory_fingerprints_matched=True,accepted_baseline_evidence=accepted_path,
        accepted_baseline_evidence_sha256=hashlib.sha256(accepted_bytes).hexdigest(),
        selected_product_sha256=selected_hash,reconstructed_trajectory_sha256=trajectory_hash,reconstructed_weekly_units_sha256=weekly_hash,
        result_rows=len(actual),rows_with_pass_status=len(actual),result_columns=len(COLUMNS),output_columns=COLUMNS,
        result_field_mismatches=0,column_names_and_order_verified=True,store_order_and_total_verified=True,
        store_aggregates=aggregates,independent_reference_store_report_sha256=expected_hash,
        fingerprint_method='SHA256 of UTF-8 compact JSON with sorted object keys and ensure_ascii=False. Store report rows remain in store_id ascending order with TOTAL last; units/differences are JSON integers, late shares four-decimal strings or NULL. Identifiers occur only in memory before hashing.',
        unchanged_input_scope='Five complete accepted snapshots (ABC, weekly, variability, XYZ, combined), plus the selected product six-column 840-row daily projection, complete two-column core store mapping and distinct raw store/state mapping. This is not a full-table daily or raw-wide equality audit.',
        five_snapshots_and_three_projections_unchanged=True,input_rows_sha256_before=input_hashes,
        input_rows_sha256_after={key:fingerprint(rows) for key,rows in after.items()},
        input_projection_row_counts={key:len(rows) for key,rows in before.items()},
        real_sku_identifiers_published=False,real_store_identifiers_published=False,store_detail_rows_published=False,daily_or_weekly_vectors_published=False,
        fixture_cases_passed=len(cases),fixture_cases=cases,
        scope='Assistant preflight only; learner local store comparison pending. Public evidence contains cross-store aggregates and one-way fingerprints, never real item/store identifiers, store rows or day/week vectors. Results do not establish promotion, demand growth, availability, stockout causes or replenishment needs.')
    serialized=json.dumps(report,indent=2,default=str,ensure_ascii=False)+'\n'
    assert all(row['item_id'] not in serialized for row in source),'Public report contains a real product identifier'
    assert all(s['store_id'] not in serialized for s in store_source),'Public report contains a real store identifier'
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(serialized,encoding='utf-8',newline='\n')
    print(json.dumps({'fixture_cases_passed':len(cases),'store_aggregates':aggregates,'timings':timings,'public_identifiers':False},default=str),flush=True)


if __name__=='__main__':
    main()
