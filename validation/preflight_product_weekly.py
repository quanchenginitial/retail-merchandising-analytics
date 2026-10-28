"""Verify complete retail-week SKU sales against original wide CSV columns in private databases."""
import argparse
import hashlib
import json
import subprocess
import tempfile
import time
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path


START_90 = date(2016, 1, 26)
START_84 = date(2016, 1, 30)
END_84 = date(2016, 4, 22)
WEEKLY_SNAPSHOT = 'SELECT * FROM mart.m5_product_weekly_12w ORDER BY item_id,wm_yr_wk;'
ABC_SNAPSHOT = 'SELECT * FROM mart.m5_product_abc_90d ORDER BY item_id;'


def sha256(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def parse(output):
    return json.loads(output, parse_float=Decimal)


def quote(value):
    return "'" + str(value).replace("'", "''") + "'"


def fingerprint(rows):
    value = json.dumps(rows, sort_keys=True, separators=(',', ':'), default=str)
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def pct(numerator, denominator):
    return None if denominator == 0 else (Decimal(numerator) * 100 / Decimal(denominator)).quantize(
        Decimal('0.0001'), rounding=ROUND_HALF_UP)


def assert_rows(actual, expected, context):
    assert len(actual) == len(expected), (context, len(actual), len(expected))
    for observed, reference in zip(actual, expected):
        assert set(observed) == set(reference), (context, observed, reference)
        for key, value in reference.items():
            actual_value = observed[key]
            if isinstance(value, (Decimal, int)) and actual_value is not None:
                actual_value = Decimal(str(actual_value))
            assert actual_value == value, (context, key, observed, reference)


def abc_reference(source):
    """Independent baseline check via minimal crossing prefixes, without daily-fact aggregates."""
    positive = sorted((x for x in source if int(x['units']) > 0),
                      key=lambda x: (-int(x['units']), x['item_id']))
    total = sum(int(x['units']) for x in source)
    cutoffs = {80: 0, 95: 0}
    cumulative, ranks = 0, {}
    for rank, row in enumerate(positive, 1):
        cumulative += int(row['units'])
        ranks[row['item_id']] = (rank, cumulative)
        for target in cutoffs:
            if cutoffs[target] == 0 and cumulative * 100 >= total * target:
                cutoffs[target] = rank
    labels = []
    for row in sorted(source, key=lambda x: x['item_id']):
        rank, cumulative = ranks.get(row['item_id'], (None, None))
        label = ('ZERO_SALES' if rank is None else 'A' if rank <= cutoffs[80]
                 else 'B' if rank <= cutoffs[95] else 'C')
        labels.append(dict(item_id=row['item_id'], dept_id=row['dept_id'], cat_id=row['cat_id'],
                           window_start='2016-01-26', window_end='2016-04-24', units=int(row['units']),
                           sku_rank=rank, cumulative_units=cumulative, abc_class=label))
    summary = []
    for label in ['A', 'B', 'C', 'ZERO_SALES', 'TOTAL']:
        members = labels if label == 'TOTAL' else [row for row in labels if row['abc_class'] == label]
        units = sum(row['units'] for row in members)
        ranks = [row['sku_rank'] for row in members if row['sku_rank'] is not None]
        summary.append(dict(abc_class=label, sku_count=len(members), sku_share_pct=pct(len(members), len(labels)),
                            units=units, unit_share_pct=pct(units, total), first_rank=min(ranks) if ranks else None,
                            last_rank=max(ranks) if ranks else None, check_status='PASS'))
    return labels, summary


def weekly_summary(rows):
    report = []
    for week in list(range(11601, 11613)) + [None]:
        members = rows if week is None else [row for row in rows if int(row['wm_yr_wk']) == week]
        report.append(dict(retail_week='TOTAL' if week is None else str(week),
                           week_start=min(row['week_start'] for row in members),
                           week_end=max(row['week_end'] for row in members), product_week_rows=len(members),
                           source_daily_rows=sum(int(row['source_daily_rows']) for row in members),
                           units=sum(int(row['units']) for row in members),
                           zero_sales_product_weeks=sum(int(row['units']) == 0 for row in members),
                           check_status='PASS'))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--duckdb', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--fixtures-only', action='store_true')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    tmp_root = root / 'tmp'
    tmp_root.mkdir(exist_ok=True)
    sql_path = root / 'sql/23_build_product_weekly.sql'
    sql_bytes = sql_path.read_bytes()
    build, audit = sql_bytes.decode('utf-8').split('-- VALIDATION:', 1)
    audit = '-- VALIDATION:' + audit
    abc_path = root / 'sql/21_build_product_abc_units.sql'
    abc_bytes = abc_path.read_bytes()
    abc_build, abc_audit = abc_bytes.decode('utf-8').split('-- VALIDATION:', 1)
    abc_audit = '-- VALIDATION:' + abc_audit
    cases = []

    def fixture(all_zero=False, adjacent=False):
        rows = []
        for item in range(1, 4):
            for store in range(1, 3):
                for offset in range(90):
                    current = START_90 + timedelta(days=offset)
                    inside = 4 <= offset < 88
                    week_index = (offset - 4) // 7
                    if all_zero:
                        units = 0
                    elif item == 1:
                        units = (week_index + 1) * store if inside else 10 * store
                    elif item == 2:
                        units = 0 if inside else 5 * store
                    else:
                        units = store if inside and week_index % 2 == 0 else 0
                    rows.append(dict(item_id=f'P{item:03d}', store_id=f'S{store}',
                                     d=f'd_{1824 + offset}', date=current.isoformat(),
                                     wm_yr_wk=11601 + week_index, units=units))
        if adjacent:
            rows.extend([
                dict(item_id='P001', store_id='S1', d='d_1823', date='2016-01-25', wm_yr_wk=11600, units=99999),
                dict(item_id='P001', store_id='S1', d='d_1914', date='2016-04-25', wm_yr_wk=11613, units=99999),
            ])
        values = ','.join('(' + ','.join(str(value) if isinstance(value, int) else quote(value)
                                        for value in row.values()) + ')' for row in rows)
        setup = f"""
CREATE SCHEMA core; CREATE SCHEMA mart;
CREATE TABLE core.m5_product AS SELECT * FROM (VALUES
('P001','FOODS_1','FOODS'),('P002','FOODS_1','FOODS'),('P003','FOODS_1','FOODS')) t(item_id,dept_id,cat_id);
CREATE TABLE core.m5_store AS SELECT * FROM (VALUES ('S1'),('S2')) t(store_id);
CREATE TABLE core.m5_calendar AS SELECT 'd_'||CAST(n AS VARCHAR) AS d,
DATE '2011-01-29'+CAST(n-1 AS INTEGER) AS date,
CAST(11601+floor((n-1828)/7) AS INTEGER) AS wm_yr_wk FROM range(1,1970) t(n);
CREATE TABLE mart.m5_sales_daily(item_id VARCHAR,store_id VARCHAR,d VARCHAR,date DATE,wm_yr_wk INTEGER,units INTEGER);
INSERT INTO mart.m5_sales_daily VALUES {values};
"""
        aggregate = defaultdict(lambda: [0, 0])
        for row in rows:
            current = date.fromisoformat(row['date'])
            if START_84 <= current <= END_84:
                week_index = (current - START_84).days // 7
                values = aggregate[(row['item_id'], week_index)]
                values[0] += row['units']
                values[1] += 1
        expected = []
        for (item, index), (units, daily_rows) in sorted(aggregate.items()):
            start = START_84 + timedelta(days=index * 7)
            expected.append(dict(item_id=item, dept_id='FOODS_1', cat_id='FOODS', wm_yr_wk=11601 + index,
                                 week_start=start.isoformat(), week_end=(start + timedelta(days=6)).isoformat(),
                                 units=units, source_daily_rows=daily_rows))
        return setup, expected

    def tiny(name, before='', after='', error=None, all_zero=False, adjacent=False):
        setup, expected = fixture(all_zero=all_zero, adjacent=adjacent)
        replacements = ('3049 AS expected_items,10 AS expected_stores', '3 AS expected_items,2 AS expected_stores')
        fixture_build = build.replace(*replacements)
        fixture_audit = audit.replace(*replacements)
        with tempfile.TemporaryDirectory(prefix='weekly-fixture-', dir=tmp_root) as folder:
            assert Path(folder).resolve().is_relative_to(tmp_root.resolve())
            database = Path(folder) / 'fixture.duckdb'

            def execute(script):
                return subprocess.run([args.duckdb, str(database), '-bail', '-json'], input=script,
                                      text=True, encoding='utf-8', capture_output=True)

            run = execute(setup + before + '\n' + fixture_build + '\n' + after + '\n' + fixture_audit)
            if error:
                assert run.returncode != 0 and error in run.stderr, (name, run.stderr)
                if error == 'Weekly build blocked':
                    absent = execute("SELECT COUNT(*) AS table_count FROM information_schema.tables WHERE table_schema='mart' AND table_name='m5_product_weekly_12w';")
                    assert absent.returncode == 0 and parse(absent.stdout) == [{'table_count': 0}], (name, absent.stdout)
            else:
                assert run.returncode == 0, (name, run.stderr)
                assert_rows(parse(run.stdout), weekly_summary(expected), name + ' summary')
                actual = execute(WEEKLY_SNAPSHOT)
                assert actual.returncode == 0, (name, actual.stderr)
                assert_rows(parse(actual.stdout), expected, name + ' stored rows')
                if not all_zero:
                    assert all(row['units'] == 0 for row in expected if row['item_id'] == 'P002')
        assert not Path(folder).exists()
        cases.append(dict(case=name, passed=True, guard_rejected=error is not None,
                          failed_build_left_no_target_table=True if error == 'Weekly build blocked' else None))

    tiny('full_weeks_zero_weeks_and_edge_only_sales_product')
    tiny('all_zero_sales_still_keep_every_week', all_zero=True)
    tiny('adjacent_and_holdout_days_are_excluded', adjacent=True)
    for name, before in [
        ('empty_daily_source', 'DELETE FROM mart.m5_sales_daily;'),
        ('duplicate_and_missing_day_preserves_counts', "UPDATE mart.m5_sales_daily SET date=DATE '2016-02-02',d='d_1831' WHERE item_id='P001' AND store_id='S1' AND date=DATE '2016-02-01';"),
        ('missing_store_daily_records', "DELETE FROM mart.m5_sales_daily WHERE store_id='S2';"),
        ('wrong_fact_source_week', "UPDATE mart.m5_sales_daily SET wm_yr_wk=11602 WHERE item_id='P001' AND store_id='S1' AND date=DATE '2016-02-01';"),
        ('wrong_fact_day_identifier', "UPDATE mart.m5_sales_daily SET d='d_999' WHERE item_id='P001' AND store_id='S1' AND date=DATE '2016-02-01';"),
        ('duplicate_selected_calendar_day', "INSERT INTO core.m5_calendar SELECT * FROM core.m5_calendar WHERE date=DATE '2016-02-01';"),
        ('seven_nonconsecutive_calendar_dates', "UPDATE core.m5_calendar SET date=DATE '2016-02-12',d='d_1841' WHERE date=DATE '2016-02-05';"),
        ('clipped_partial_week_cannot_become_selected', "DELETE FROM core.m5_calendar WHERE date BETWEEN DATE '2016-01-23' AND DATE '2016-01-25';"),
        ('negative_daily_units', "UPDATE mart.m5_sales_daily SET units=-1 WHERE item_id='P001' AND store_id='S1' AND date=DATE '2016-02-01';"),
        ('duplicate_product_mapping', "INSERT INTO core.m5_product SELECT * FROM core.m5_product WHERE item_id='P001';"),
    ]:
        tiny(name, before=before, error='Weekly build blocked')
    for name, after in [
        ('wrong_stored_week_boundary', "UPDATE mart.m5_product_weekly_12w SET week_end=week_end+1 WHERE item_id='P001' AND wm_yr_wk=11601;"),
        ('same_week_total_preserving_sku_redistribution', "UPDATE mart.m5_product_weekly_12w SET units=units+CASE item_id WHEN 'P001' THEN 1 ELSE -1 END WHERE item_id IN ('P001','P003') AND wm_yr_wk=11601;"),
        ('wrong_stored_source_row_count', "UPDATE mart.m5_product_weekly_12w SET source_daily_rows=13 WHERE item_id='P001' AND wm_yr_wk=11601;"),
        ('duplicate_product_week', "INSERT INTO mart.m5_product_weekly_12w SELECT * FROM mart.m5_product_weekly_12w WHERE item_id='P001' AND wm_yr_wk=11601;"),
        ('missing_product_week', "DELETE FROM mart.m5_product_weekly_12w WHERE item_id='P002' AND wm_yr_wk=11601;"),
        ('wrong_units_schema', 'ALTER TABLE mart.m5_product_weekly_12w ALTER units TYPE BIGINT;'),
        ('wrong_stored_product_hierarchy', "UPDATE mart.m5_product_weekly_12w SET dept_id='FOODS_2' WHERE item_id='P001' AND wm_yr_wk=11601;"),
    ]:
        tiny(name, after=after, error='Weekly validation blocked')
    assert len(cases) == 20
    print(json.dumps({'fixture_cases_passed': len(cases)}), flush=True)
    if args.fixtures_only:
        return

    source_root = Path('D:/database/m5-forecasting-accuracy')
    sources = [source_root / name for name in ['sales_train_evaluation.csv', 'calendar.csv']]
    registry = json.loads((root / 'data/m5_source_audit.json').read_text(encoding='utf-8'))
    hashes = {path.name: sha256(path) for path in sources}
    assert all(hashes[path.name] == registry['files'][path.name]['sha256'] for path in sources)
    columns_90 = ','.join(f'd_{day}' for day in range(1824, 1914))
    setup = f"""
CREATE SCHEMA raw; CREATE SCHEMA core; CREATE SCHEMA mart;
CREATE TABLE core.m5_calendar AS
SELECT d,CAST(date AS DATE) AS date,CAST(wm_yr_wk AS INTEGER) AS wm_yr_wk
FROM read_csv({quote(sources[1].as_posix())},header=true,all_varchar=true);
CREATE TABLE raw.sales_window_wide AS
SELECT id,item_id,dept_id,cat_id,store_id,state_id,{columns_90}
FROM read_csv({quote(sources[0].as_posix())},header=true,all_varchar=true);
CREATE TABLE core.m5_product AS SELECT DISTINCT item_id,dept_id,cat_id FROM raw.sales_window_wide;
CREATE TABLE core.m5_store AS SELECT DISTINCT store_id FROM raw.sales_window_wide;
CREATE TABLE mart.m5_sales_daily AS
WITH unpivoted AS (UNPIVOT raw.sales_window_wide ON {columns_90} INTO NAME d VALUE units_text)
SELECT u.item_id,u.store_id,u.d,c.date,c.wm_yr_wk,
CASE WHEN regexp_full_match(u.units_text,'[0-9]+') AND TRY_CAST(u.units_text AS INTEGER) IS NOT NULL
     THEN CAST(u.units_text AS INTEGER) ELSE error('Window source requires nonnegative INTEGER sales') END AS units
FROM unpivoted u JOIN core.m5_calendar c ON u.d=c.d;
"""
    controls_sql = """
SELECT (SELECT COUNT(*) FROM raw.sales_window_wide) AS source_series,
       (SELECT COUNT(*) FROM core.m5_product) AS source_products,
       (SELECT COUNT(*) FROM core.m5_store) AS source_stores,
       (SELECT COUNT(*) FROM core.m5_calendar) AS calendar_rows,
       (SELECT COUNT(DISTINCT d) FROM core.m5_calendar) AS calendar_day_keys,
       (SELECT COUNT(DISTINCT date) FROM core.m5_calendar) AS calendar_dates,
       (SELECT COUNT(DISTINCT wm_yr_wk) FROM core.m5_calendar) AS calendar_weeks,
       (SELECT COUNT(*) FROM core.m5_calendar WHERE d IS DISTINCT FROM 'd_'||CAST(date_diff('day',DATE '2011-01-29',date)+1 AS VARCHAR)) AS calendar_mapping_errors,
       (SELECT COUNT(*) FROM mart.m5_sales_daily) AS private_90d_daily_rows,
       (SELECT COUNT(*) FROM mart.m5_sales_daily WHERE date BETWEEN DATE '2016-01-30' AND DATE '2016-04-22') AS private_84d_daily_rows;
"""

    def wide_sum(days):
        columns = ','.join(f'd_{day}' for day in days)
        return f"SUM(list_sum(list_transform(list_value({columns}),lambda x: CASE WHEN regexp_full_match(x,'[0-9]+') AND TRY_CAST(x AS INTEGER) IS NOT NULL THEN CAST(x AS BIGINT) ELSE error('Wide reference requires nonnegative INTEGER sales') END)))"

    weekly_branches = []
    for index in range(12):
        start = START_84 + timedelta(days=index * 7)
        end = start + timedelta(days=6)
        weekly_branches.append(f"""SELECT item_id,dept_id,cat_id,{11601 + index}::INTEGER AS wm_yr_wk,
DATE {quote(start.isoformat())} AS week_start,DATE {quote(end.isoformat())} AS week_end,
{wide_sum(range(1828 + index * 7, 1835 + index * 7))} AS units,COUNT(*)*7 AS source_daily_rows
FROM raw.sales_window_wide GROUP BY item_id,dept_id,cat_id""")
    weekly_reference_sql = '\nUNION ALL\n'.join(weekly_branches) + '\nORDER BY item_id,wm_yr_wk;'
    balance_sql = f"""
SELECT item_id,dept_id,cat_id,{wide_sum(range(1824,1914))} AS units_90d,
{wide_sum(range(1828,1912))} AS units_84d,
{wide_sum([1824,1825,1826,1827,1912,1913])} AS excluded_6d_units
FROM raw.sales_window_wide GROUP BY item_id,dept_id,cat_id ORDER BY item_id;
"""
    accepted_path = root / 'data/product_abc_units_learner_acceptance.json'
    accepted_bytes = accepted_path.read_bytes()
    accepted = json.loads(accepted_bytes.decode('utf-8'))
    assert accepted['baseline_accepted'] is True
    assert accepted['analysis_window']['start_date'] == '2016-01-26'
    assert accepted['analysis_window']['end_date'] == '2016-04-24'
    with tempfile.TemporaryDirectory(prefix='product-weekly-', dir=tmp_root) as folder:
        assert Path(folder).resolve().is_relative_to(tmp_root.resolve())
        database = Path(folder) / 'preflight.duckdb'
        assert database.resolve().is_relative_to(Path(folder).resolve())
        spill = (Path(folder) / 'spill').as_posix().replace("'", "''")
        settings = f"SET threads=2; SET memory_limit='2GB'; SET temp_directory='{spill}';\n"

        def execute(script):
            started = time.perf_counter()
            run = subprocess.run([args.duckdb, str(database), '-bail', '-json'], input=settings + script,
                                 text=True, encoding='utf-8', capture_output=True)
            assert run.returncode == 0, run.stderr
            return run, round(time.perf_counter() - started, 3)

        _, setup_seconds = execute(setup)
        run, _ = execute(controls_sql)
        controls = parse(run.stdout)[0]
        assert controls == dict(source_series=30490, source_products=3049, source_stores=10,
                                calendar_rows=1969, calendar_day_keys=1969, calendar_dates=1969,
                                calendar_weeks=282, calendar_mapping_errors=0,
                                private_90d_daily_rows=2744100, private_84d_daily_rows=2561160), controls
        print(json.dumps({'window_setup_seconds': setup_seconds, 'source_controls': controls}), flush=True)
        run, balance_seconds = execute(balance_sql)
        balances = parse(run.stdout)
        assert len(balances) == 3049 and len({row['item_id'] for row in balances}) == 3049
        for row in balances:
            assert int(row['units_90d']) == int(row['units_84d']) + int(row['excluded_6d_units']), row
        source_90d = [dict(item_id=row['item_id'], dept_id=row['dept_id'], cat_id=row['cat_id'],
                           units=int(row['units_90d'])) for row in balances]
        expected_abc, expected_abc_summary = abc_reference(source_90d)
        normalized_accepted = []
        for row in accepted['results']:
            normalized_accepted.append({key: None if value is None else Decimal(str(value)) if key.endswith('_pct')
                                        else int(value) if key in ('sku_count', 'units', 'first_rank', 'last_rank') else value
                                        for key, value in row.items()})
        assert_rows(expected_abc_summary, normalized_accepted, '90-day source versus accepted ABC')
        _, abc_build_seconds = execute(abc_build)
        run, abc_validation_seconds = execute(abc_audit)
        assert_rows(parse(run.stdout), expected_abc_summary, 'private ABC baseline summary')
        run, _ = execute(ABC_SNAPSHOT)
        abc_before = parse(run.stdout)
        assert_rows(abc_before, expected_abc, 'private ABC baseline all fields')
        abc_before_hash = fingerprint(abc_before)
        _, build_seconds = execute(build)
        run, validation_seconds = execute(audit)
        results = parse(run.stdout)
        run, reference_seconds = execute(weekly_reference_sql)
        expected_weekly = parse(run.stdout)
        assert len(expected_weekly) == 36588
        assert len({(row['item_id'], row['wm_yr_wk']) for row in expected_weekly}) == 36588
        run, extraction_seconds = execute(WEEKLY_SNAPSHOT)
        actual_weekly = parse(run.stdout)
        assert_rows(actual_weekly, expected_weekly, 'all eight weekly fields')
        assert_rows(results, weekly_summary(expected_weekly), 'thirteen weekly summary rows')
        stored_units = defaultdict(int)
        stored_weeks = defaultdict(set)
        for row in actual_weekly:
            stored_units[row['item_id']] += int(row['units'])
            stored_weeks[row['item_id']].add(int(row['wm_yr_wk']))
        for row in balances:
            assert stored_units[row['item_id']] == int(row['units_84d']), row
            assert stored_weeks[row['item_id']] == set(range(11601, 11613)), row
        run, _ = execute(ABC_SNAPSHOT)
        abc_after = parse(run.stdout)
        assert abc_before == abc_after and abc_before_hash == fingerprint(abc_after), 'ABC baseline changed'
        run, _ = execute(abc_audit)
        assert_rows(parse(run.stdout), expected_abc_summary, 'ABC remains valid after weekly build')
        database_bytes = database.stat().st_size
    assert not Path(folder).exists()
    assert all(sha256(path) == hashes[path.name] for path in sources)
    comparison = dict(
        sku_rows_compared=3049, per_sku_90_equals_84_plus_6=True, per_sku_balance_mismatches=0,
        units_90d=sum(int(row['units_90d']) for row in balances),
        units_84d=sum(int(row['units_84d']) for row in balances),
        excluded_6d_units=sum(int(row['excluded_6d_units']) for row in balances),
        zero_sales_skus_90d=sum(int(row['units_90d']) == 0 for row in balances),
        zero_sales_skus_84d=sum(int(row['units_84d']) == 0 for row in balances),
        zero_sales_product_weeks_12w=sum(int(row['units']) == 0 for row in actual_weekly),
        positive_90d_but_zero_84d_skus=sum(int(row['units_90d']) > 0 and int(row['units_84d']) == 0 for row in balances),
        excluded_dates=['2016-01-26', '2016-01-27', '2016-01-28', '2016-01-29', '2016-04-23', '2016-04-24'])
    report = dict(
        checked_at_utc=datetime.now(timezone.utc).isoformat(), executor='assistant',
        engine=subprocess.check_output([args.duckdb, '-version'], text=True).strip(),
        baseline_database='Private temporary on-disk DuckDB under repository tmp; removed after verification.',
        temporary_baseline_removed=True, temporary_database_bytes_after_close=database_bytes,
        settings={'threads': 2, 'memory_limit': '2GB'},
        script='sql/23_build_product_weekly.sql', script_sha256=hashlib.sha256(sql_bytes).hexdigest(),
        abc_baseline_script='sql/21_build_product_abc_units.sql', abc_baseline_script_sha256=hashlib.sha256(abc_bytes).hexdigest(),
        preflight_strategy='Only sales/calendar CSVs are read. A private raw projection retains six identifiers and the 90 day columns. A six-column, 2,744,100-row daily table and small dimensions support actual SQL21 and SQL23; this is a window-only fixture, not a full SQL17 rebuild or learner database access.',
        independent_reference='For each of the twelve fixed source retail weeks, sum its original seven wide CSV columns per SKU, without using the daily fact. Separately sum original 90-day, 84-day and excluded-six-day arrays per SKU. Independent Python crossing-prefix labels reconcile the 90-day data to accepted ABC evidence.',
        source_sha256=hashes, source_hashes_unchanged=True,
        source_scope='Sales and calendar only; price is irrelevant and was neither read nor hashed.',
        weekly_window={'start_date': '2016-01-30', 'end_date': '2016-04-22', 'inclusive_days': 84,
                       'retail_weeks': list(range(11601, 11613)), 'week_count': 12,
                       'scope': 'Each SKU pooled over all 10 stores; observed zero-sales weeks retained.'},
        abc_window={'start_date': '2016-01-26', 'end_date': '2016-04-24', 'inclusive_days': 90},
        source_controls=controls, window_setup_seconds=setup_seconds,
        independent_balance_query_seconds=balance_seconds, abc_build_seconds=abc_build_seconds,
        abc_validation_seconds=abc_validation_seconds, weekly_build_seconds=build_seconds,
        weekly_validation_seconds=validation_seconds, independent_weekly_reference_query_seconds=reference_seconds,
        weekly_snapshot_query_seconds=extraction_seconds,
        timing_scope='DuckDB CLI process timings; excludes Python comparison and source-file hashing time.',
        weekly_rows_compared=36588, weekly_columns_compared=8, weekly_row_mismatches=0,
        source_reference_matched=True, per_sku_week_set_matched=True, window_comparison=comparison,
        accepted_abc_baseline_matched=True, accepted_abc_evidence='data/product_abc_units_learner_acceptance.json',
        accepted_abc_evidence_sha256=hashlib.sha256(accepted_bytes).hexdigest(),
        abc_baseline_unchanged=True, abc_rows_sha256_before=abc_before_hash, abc_rows_sha256_after=fingerprint(abc_after),
        abc_sku_rows_compared=3049, abc_baseline_results=expected_abc_summary,
        result_rows=13, results=results, fixture_cases_passed=len(cases), fixture_cases=cases,
        scope='Assistant preflight only; learner weekly-table execution pending. The 84-day weekly sequence is separate from the unchanged 90-day ABC baseline. Missing source records are rejected, not filled with zero. No XYZ labels, stockout inference or store-specific variability claim is made. No SKU-level extract is published and no learner database is opened.')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, default=str) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps({'fixture_cases_passed': len(cases), 'weekly_rows_compared': 36588,
                      'abc_baseline_unchanged': True, 'weekly_build_seconds': build_seconds,
                      'weekly_validation_seconds': validation_seconds, 'window_comparison': comparison,
                      'results': results}, default=str), flush=True)


if __name__ == '__main__':
    main()
