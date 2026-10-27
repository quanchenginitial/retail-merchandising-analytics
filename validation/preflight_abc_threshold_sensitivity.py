"""Verify read-only ABC scenarios against original 90-day wide sales, in private databases."""
import argparse
import hashlib
import json
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path


SCENARIOS = [
    ('BASE_80_95', 80, 95, None),
    ('A75_95', 75, 95, ('A', 'B')),
    ('A85_95', 85, 95, ('B', 'A')),
    ('AB80_92', 80, 92, ('B', 'C')),
    ('AB80_98', 80, 98, ('C', 'B')),
]
LABELS = ['A', 'B', 'C', 'ZERO_SALES']
SNAPSHOT_SQL = 'SELECT * FROM mart.m5_product_abc_90d ORDER BY item_id,dept_id,cat_id,window_start,window_end,units,sku_rank,cumulative_units,abc_class;'


def sha256(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def parse(output):
    return json.loads(output, parse_float=Decimal)


def pct(numerator, denominator):
    if denominator == 0:
        return None
    return (Decimal(numerator) * 100 / Decimal(denominator)).quantize(
        Decimal('0.0001'), rounding=ROUND_HALF_UP)


def quote(value):
    return "'" + str(value).replace("'", "''") + "'"


def fingerprint(rows):
    serialized = json.dumps(rows, sort_keys=True, separators=(',', ':'), default=str)
    return hashlib.sha256(serialized.encode('utf-8')).hexdigest()


def prefix_reference(source, a_target=80, ab_target=95):
    """Find crossing prefix endpoints, independently of SQL's prior-cumulative rule."""
    positive = sorted((x for x in source if int(x['units']) > 0),
                      key=lambda x: (-int(x['units']), x['item_id']))
    total = sum(int(x['units']) for x in source)
    endpoints = {a_target: 0, ab_target: 0}
    ranks = {}
    cumulative = 0
    for rank, row in enumerate(positive, 1):
        cumulative += int(row['units'])
        ranks[row['item_id']] = (rank, cumulative)
        for target in endpoints:
            if endpoints[target] == 0 and cumulative * 100 >= total * target:
                endpoints[target] = rank
    result = []
    for row in sorted(source, key=lambda x: x['item_id']):
        rank, cumulative = ranks.get(row['item_id'], (None, None))
        label = ('ZERO_SALES' if rank is None else 'A' if rank <= endpoints[a_target]
                 else 'B' if rank <= endpoints[ab_target] else 'C')
        result.append(dict(item_id=row['item_id'], dept_id=row['dept_id'], cat_id=row['cat_id'],
                           window_start='2016-01-26', window_end='2016-04-24',
                           units=int(row['units']), sku_rank=rank,
                           cumulative_units=cumulative, abc_class=label))
    return result


def expected_scenarios(source):
    baseline = {x['item_id']: x for x in prefix_reference(source)}
    total = sum(int(x['units']) for x in source)
    summaries, memberships = [], []
    for scenario, a_target, ab_target, allowed_direction in SCENARIOS:
        current = prefix_reference(source, a_target, ab_target)
        changed = [x for x in current if x['abc_class'] != baseline[x['item_id']]['abc_class']]
        for row in changed:
            assert (baseline[row['item_id']]['abc_class'], row['abc_class']) == allowed_direction
        summaries.append(dict(
            scenario=scenario,
            a_skus=sum(x['abc_class'] == 'A' for x in current),
            b_skus=sum(x['abc_class'] == 'B' for x in current),
            c_skus=sum(x['abc_class'] == 'C' for x in current),
            zero_skus=sum(x['abc_class'] == 'ZERO_SALES' for x in current),
            changed_skus=len(changed), changed_sku_pct=pct(len(changed), len(source)),
            changed_unit_share_pct=pct(sum(x['units'] for x in changed), total), check_status='PASS'))
        memberships.extend(dict(scenario=scenario, item_id=x['item_id'], units=x['units'],
                                baseline_class=baseline[x['item_id']]['abc_class'],
                                scenario_class=x['abc_class']) for x in current)
    return summaries, sorted(memberships, key=lambda x: (x['scenario'], x['item_id']))


def assert_rows(actual, expected, context):
    assert len(actual) == len(expected), (context, len(actual), len(expected))
    for observed, reference in zip(actual, expected):
        assert set(observed) == set(reference), (context, observed, reference)
        for key, value in reference.items():
            observed_value = observed[key]
            if isinstance(value, (Decimal, int)) and observed_value is not None:
                observed_value = Decimal(str(observed_value))
            assert observed_value == value, (context, key, observed, reference)


def baseline_summary(labels):
    total = sum(x['units'] for x in labels)
    result = []
    for label in LABELS + ['TOTAL']:
        members = labels if label == 'TOTAL' else [x for x in labels if x['abc_class'] == label]
        units = sum(x['units'] for x in members)
        ranks = [x['sku_rank'] for x in members if x['sku_rank'] is not None]
        result.append(dict(abc_class=label, sku_count=len(members), sku_share_pct=pct(len(members), len(labels)),
                           units=units, unit_share_pct=pct(units, total),
                           first_rank=min(ranks) if ranks else None, last_rank=max(ranks) if ranks else None,
                           check_status='PASS'))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--duckdb', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--fixtures-only', action='store_true')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    tmp_root = root / 'tmp'
    tmp_root.mkdir(exist_ok=True)
    sql_path = root / 'sql/22_abc_threshold_sensitivity.sql'
    sql_bytes = sql_path.read_bytes()
    sql = sql_bytes.decode('utf-8')
    baseline_path = root / 'sql/21_build_product_abc_units.sql'
    baseline_bytes = baseline_path.read_bytes()
    baseline_build, baseline_audit = baseline_bytes.decode('utf-8').split('-- VALIDATION:', 1)
    baseline_audit = '-- VALIDATION:' + baseline_audit
    membership_suffix = """
SELECT scenario,item_id,units,baseline_class,scenario_class FROM scenario_assignments
ORDER BY scenario,item_id;
"""
    cases = []

    def fixture_setup(weights):
        source = [dict(item_id=f'P{i:03d}', dept_id='FOODS_1', cat_id='FOODS', units=int(weight))
                  for i, weight in enumerate(weights, 1)]
        labels = prefix_reference(source)
        products = ','.join(f"({quote(x['item_id'])},'FOODS_1','FOODS')" for x in source)
        values = []
        for row in labels:
            values.append('(' + ','.join('NULL' if value is None else str(value) if isinstance(value, int)
                                        else quote(value) for value in row.values()) + ')')
        script = f"""
CREATE SCHEMA core; CREATE SCHEMA mart;
CREATE TABLE core.m5_product(item_id VARCHAR,dept_id VARCHAR,cat_id VARCHAR);
INSERT INTO core.m5_product VALUES {products};
CREATE TABLE mart.m5_product_abc_90d(item_id VARCHAR,dept_id VARCHAR,cat_id VARCHAR,
window_start DATE,window_end DATE,units HUGEINT,sku_rank BIGINT,cumulative_units HUGEINT,abc_class VARCHAR);
INSERT INTO mart.m5_product_abc_90d VALUES {','.join(values)};
"""
        return source, script

    def tiny(name, weights, mutation='', scenario_null=False):
        source, setup = fixture_setup(weights)
        query = sql.replace('3049 AS expected_items', f'{len(weights)} AS expected_items')
        if scenario_null:
            assert "(2,'A75_95',75,95" in query
            query = query.replace("(2,'A75_95',75,95", "(2,'A75_95',NULL,95")
        with tempfile.TemporaryDirectory(prefix='abc-sensitivity-fixture-', dir=tmp_root) as folder:
            assert Path(folder).resolve().is_relative_to(tmp_root.resolve())
            database = Path(folder) / 'fixture.duckdb'

            def execute(script):
                return subprocess.run([args.duckdb, str(database), '-bail', '-json'], input=script,
                                      text=True, encoding='utf-8', capture_output=True)

            run = execute(setup + mutation)
            assert run.returncode == 0, (name, run.stderr)
            before = execute(SNAPSHOT_SQL)
            assert before.returncode == 0, before.stderr
            before_rows = parse(before.stdout)
            run = execute(query)
            rejected = bool(mutation or scenario_null)
            if rejected:
                assert run.returncode != 0 and 'ABC sensitivity blocked' in run.stderr, (name, run.stderr)
            else:
                assert run.returncode == 0, (name, run.stderr)
                expected, memberships = expected_scenarios(source)
                assert_rows(parse(run.stdout), expected, name + ' summary')
                details = execute(query.split('-- REPORT:', 1)[0] + membership_suffix)
                assert details.returncode == 0, (name, details.stderr)
                assert_rows(parse(details.stdout), memberships, name + ' memberships')
            after = execute(SNAPSHOT_SQL)
            assert after.returncode == 0 and parse(after.stdout) == before_rows, (name, 'baseline changed')
        assert not Path(folder).exists()
        cases.append(dict(case=name, passed=True, guard_rejected=rejected, baseline_unchanged=True))

    exact = [60, 15, 5, 5, 4, 3, 3, 3, 2, 0]
    tiny('all_six_exact_threshold_boundaries', exact)
    tiny('crossing_items_remain_in_earlier_band', [61, 14, 6, 5, 4, 3, 3, 2, 2, 0])
    tiny('dominant_sku_can_make_every_scenario_unchanged', [99, 1, 0])
    tiny('equal_units_use_item_id_ties', [20, 20, 20, 20, 15, 5, 0])
    tiny('all_zero_volume_share_is_null', [0, 0, 0])
    tiny('one_positive_sku', [5, 0])
    tiny('no_zero_sales_products', exact[:-1])
    for name, mutation in [
        ('empty_baseline', 'DELETE FROM mart.m5_product_abc_90d;'),
        ('duplicate_baseline_item', "INSERT INTO mart.m5_product_abc_90d SELECT * FROM mart.m5_product_abc_90d WHERE item_id='P001';"),
        ('missing_baseline_item', "DELETE FROM mart.m5_product_abc_90d WHERE item_id='P010';"),
        ('null_units', "UPDATE mart.m5_product_abc_90d SET units=NULL WHERE item_id='P001';"),
        ('negative_units', "UPDATE mart.m5_product_abc_90d SET units=-1 WHERE item_id='P001';"),
        ('wrong_start_date', "UPDATE mart.m5_product_abc_90d SET window_start=DATE '2016-01-25' WHERE item_id='P001';"),
        ('wrong_end_date', "UPDATE mart.m5_product_abc_90d SET window_end=DATE '2016-04-25' WHERE item_id='P001';"),
        ('wrong_rank', "UPDATE mart.m5_product_abc_90d SET sku_rank=2 WHERE item_id='P001';"),
        ('wrong_cumulative_units', "UPDATE mart.m5_product_abc_90d SET cumulative_units=61 WHERE item_id='P001';"),
        ('wrong_baseline_class', "UPDATE mart.m5_product_abc_90d SET abc_class='B' WHERE item_id='P001';"),
        ('zero_rank_and_cumulative_must_be_null', "UPDATE mart.m5_product_abc_90d SET sku_rank=10,cumulative_units=100 WHERE item_id='P010';"),
        ('wrong_product_mapping', "UPDATE mart.m5_product_abc_90d SET dept_id='FOODS_2' WHERE item_id='P001';"),
        ('duplicate_core_product', "INSERT INTO core.m5_product SELECT * FROM core.m5_product WHERE item_id='P001';"),
        ('missing_core_product', "DELETE FROM core.m5_product WHERE item_id='P001';"),
        ('wrong_units_type', 'ALTER TABLE mart.m5_product_abc_90d ALTER units TYPE BIGINT;'),
        ('unexpected_column', 'ALTER TABLE mart.m5_product_abc_90d ADD COLUMN unexpected VARCHAR;'),
        ('empty_item_identifier', "UPDATE mart.m5_product_abc_90d SET item_id='' WHERE item_id='P001';"),
        ('same_total_redistribution_invalidates_saved_cumulative', "UPDATE mart.m5_product_abc_90d SET units=CASE item_id WHEN 'P001' THEN 61 WHEN 'P002' THEN 14 ELSE units END;"),
    ]:
        tiny(name, exact, mutation=mutation)
    tiny('null_scenario_threshold_rejected', exact, scenario_null=True)
    print(json.dumps({'fixture_cases_passed': len(cases)}), flush=True)
    if args.fixtures_only:
        return

    source_root = Path('D:/database/m5-forecasting-accuracy')
    sources = [source_root / name for name in ['sales_train_evaluation.csv', 'calendar.csv']]
    registry = json.loads((root / 'data/m5_source_audit.json').read_text(encoding='utf-8'))
    hashes = {path.name: sha256(path) for path in sources}
    assert all(hashes[path.name] == registry['files'][path.name]['sha256'] for path in sources)
    columns = ','.join(f'd_{day}' for day in range(1824, 1914))
    setup = f"""
CREATE SCHEMA raw; CREATE SCHEMA core; CREATE SCHEMA mart;
CREATE TABLE raw.calendar_source AS
SELECT d,CAST(date AS DATE) AS date FROM read_csv({quote(sources[1].as_posix())},header=true,all_varchar=true);
CREATE TABLE raw.sales_window_wide AS
SELECT id,item_id,dept_id,cat_id,store_id,state_id,{columns}
FROM read_csv({quote(sources[0].as_posix())},header=true,all_varchar=true);
CREATE TABLE core.m5_product AS SELECT DISTINCT item_id,dept_id,cat_id FROM raw.sales_window_wide;
CREATE TABLE core.m5_store AS SELECT DISTINCT store_id FROM raw.sales_window_wide;
CREATE TABLE mart.m5_sales_daily AS
WITH unpivoted AS (UNPIVOT raw.sales_window_wide ON {columns} INTO NAME d VALUE units_text)
SELECT u.item_id,u.store_id,u.d,c.date,
CASE WHEN regexp_full_match(u.units_text,'[0-9]+') AND TRY_CAST(u.units_text AS INTEGER) IS NOT NULL
     THEN CAST(u.units_text AS INTEGER) ELSE error('Window source requires nonnegative INTEGER sales') END AS units
FROM unpivoted u JOIN raw.calendar_source c ON u.d=c.d;
"""
    source_controls_sql = """
SELECT (SELECT COUNT(*) FROM raw.sales_window_wide) AS source_series,
       (SELECT COUNT(*) FROM core.m5_product) AS source_products,
       (SELECT COUNT(*) FROM core.m5_store) AS source_stores,
       (SELECT COUNT(*) FROM raw.calendar_source) AS calendar_rows,
       (SELECT COUNT(DISTINCT d) FROM raw.calendar_source) AS calendar_day_keys,
       (SELECT COUNT(DISTINCT date) FROM raw.calendar_source) AS calendar_dates,
       (SELECT COUNT(*) FROM raw.calendar_source WHERE date BETWEEN DATE '2016-01-26' AND DATE '2016-04-24') AS window_calendar_days,
       (SELECT COUNT(*) FROM raw.calendar_source WHERE d IS DISTINCT FROM 'd_'||CAST(date_diff('day',DATE '2011-01-29',date)+1 AS VARCHAR)) AS calendar_mapping_errors,
       (SELECT COUNT(*) FROM mart.m5_sales_daily) AS private_window_daily_rows;
"""
    # Independent arithmetic route: list sums directly from the original wide 90 columns.
    reference_sql = f"""
SELECT item_id,dept_id,cat_id,
SUM(list_sum(list_transform(list_value({columns}),lambda x:
CASE WHEN regexp_full_match(x,'[0-9]+') AND TRY_CAST(x AS INTEGER) IS NOT NULL
     THEN CAST(x AS BIGINT) ELSE error('Wide reference requires nonnegative INTEGER sales') END)))::VARCHAR AS units
FROM raw.sales_window_wide GROUP BY item_id,dept_id,cat_id ORDER BY item_id;
"""
    accepted_path = root / 'data/product_abc_units_learner_acceptance.json'
    accepted_bytes = accepted_path.read_bytes()
    accepted = json.loads(accepted_bytes.decode('utf-8'))
    assert accepted['baseline_accepted'] is True
    assert accepted['analysis_window']['start_date'] == '2016-01-26'
    assert accepted['analysis_window']['end_date'] == '2016-04-24'
    with tempfile.TemporaryDirectory(prefix='abc-sensitivity-', dir=tmp_root) as folder:
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
        run, _ = execute(source_controls_sql)
        controls = parse(run.stdout)[0]
        assert controls == dict(source_series=30490, source_products=3049, source_stores=10,
                                calendar_rows=1969, calendar_day_keys=1969, calendar_dates=1969,
                                window_calendar_days=90, calendar_mapping_errors=0,
                                private_window_daily_rows=2744100), controls
        print(json.dumps({'window_setup_seconds': setup_seconds, 'source_controls': controls}), flush=True)
        _, baseline_build_seconds = execute(baseline_build)
        run, baseline_validation_seconds = execute(baseline_audit)
        actual_baseline_summary = parse(run.stdout)
        run, reference_seconds = execute(reference_sql)
        source = parse(run.stdout)
        assert len(source) == 3049 and len({x['item_id'] for x in source}) == 3049
        reference_baseline = prefix_reference(source)
        assert_rows(actual_baseline_summary, baseline_summary(reference_baseline), 'source baseline summary')
        normalized_accepted = []
        for row in accepted['results']:
            normalized_accepted.append({key: None if value is None else Decimal(str(value)) if key.endswith('_pct')
                                        else int(value) if key in ('sku_count', 'units', 'first_rank', 'last_rank') else value
                                        for key, value in row.items()})
        assert_rows(actual_baseline_summary, normalized_accepted, 'learner accepted baseline summary')
        run, _ = execute(SNAPSHOT_SQL)
        before = parse(run.stdout)
        assert_rows(before, reference_baseline, 'all nine baseline fields')
        before_hash = fingerprint(before)
        run, scenario_seconds = execute(sql)
        results = parse(run.stdout)
        expected_summary, expected_memberships = expected_scenarios(source)
        assert_rows(results, expected_summary, 'scenario summary')
        run, membership_seconds = execute(sql.split('-- REPORT:', 1)[0] + membership_suffix)
        actual_memberships = parse(run.stdout)
        assert len(actual_memberships) == 15245
        assert_rows(actual_memberships, expected_memberships, 'every scenario/item assignment')
        run, _ = execute(SNAPSHOT_SQL)
        after = parse(run.stdout)
        assert before == after and before_hash == fingerprint(after), 'Baseline changed after sensitivity'
        run, _ = execute(baseline_audit)
        assert_rows(parse(run.stdout), actual_baseline_summary, 'baseline validation after sensitivity')
        database_bytes = database.stat().st_size
    assert not Path(folder).exists()
    assert all(sha256(path) == hashes[path.name] for path in sources)
    report = dict(
        checked_at_utc=datetime.now(timezone.utc).isoformat(), executor='assistant',
        engine=subprocess.check_output([args.duckdb, '-version'], text=True).strip(),
        baseline_database='Private temporary on-disk DuckDB under repository tmp; removed after verification.',
        temporary_baseline_removed=True, temporary_database_bytes_after_close=database_bytes,
        settings={'threads': 2, 'memory_limit': '2GB'},
        script='sql/22_abc_threshold_sensitivity.sql', script_sha256=hashlib.sha256(sql_bytes).hexdigest(),
        baseline_script='sql/21_build_product_abc_units.sql', baseline_script_sha256=hashlib.sha256(baseline_bytes).hexdigest(),
        preflight_strategy='Read only sales/calendar CSVs. Persist six source identifiers plus d_1824..d_1913 in a private raw projection; construct a 2,744,100-row, five-column window-only daily fact and small dimensions. Execute actual SQL21 build/validation, then SQL22. The private daily table is not a full SQL17 rebuild or a schema replica of the learner fact.',
        independent_reference='Sum original wide 90-day arrays per SKU, without using the private daily fact. Python finds minimal crossing prefix endpoints independently of SQL prior-cumulative comparisons.',
        source_sha256=hashes, source_hashes_unchanged=True,
        source_scope='Sales and calendar only; price is irrelevant to these unit-based scenarios and was neither read nor hashed.',
        analysis_window={'start_date': '2016-01-26', 'end_date': '2016-04-24', 'inclusive_days': 90,
                         'scope': 'Global units across all 10 stores, including zero-sales products.'},
        scenarios=[dict(scenario=name, a_target=a, ab_target=ab,
                        allowed_change=None if direction is None else list(direction))
                   for name, a, ab, direction in SCENARIOS],
        source_controls=controls, window_setup_seconds=setup_seconds,
        baseline_build_seconds=baseline_build_seconds, baseline_validation_seconds=baseline_validation_seconds,
        independent_wide_reference_seconds=reference_seconds, sensitivity_seconds=scenario_seconds,
        scenario_membership_comparison_seconds=membership_seconds,
        baseline_sku_rows_compared=3049, baseline_columns_compared=9, baseline_row_mismatches=0,
        scenario_sku_rows_compared=15245, scenario_membership_mismatches=0,
        source_reference_matched=True, accepted_baseline_matched=True,
        accepted_baseline_evidence='data/product_abc_units_learner_acceptance.json',
        accepted_baseline_evidence_sha256=hashlib.sha256(accepted_bytes).hexdigest(),
        baseline_unchanged=True, baseline_rows_sha256_before=before_hash, baseline_rows_sha256_after=fingerprint(after),
        baseline_results=actual_baseline_summary, result_rows=5, results=results,
        fixture_cases_passed=len(cases), fixture_cases=cases,
        scope='Assistant preflight only; learner sensitivity execution pending. Fixed one-boundary-at-a-time scenarios are illustrative, not optimized thresholds. Changed unit share means historical units carried by relabelled products, not a sales change. The learner query checks snapshot consistency and relies on accepted SQL21 source equality; this private preflight independently checks original source totals. No SKU-level extract published and no learner database opened.')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, default=str) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps({'fixture_cases_passed': len(cases), 'baseline_sku_rows_compared': 3049,
                      'scenario_sku_rows_compared': 15245, 'baseline_unchanged': True,
                      'sensitivity_seconds': scenario_seconds, 'results': results}, default=str), flush=True)


if __name__ == '__main__':
    main()
