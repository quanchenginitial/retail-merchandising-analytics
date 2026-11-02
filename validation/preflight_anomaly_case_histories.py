"""Privately verify deterministic illustrative case histories and publish fingerprints only."""
import argparse
import csv
import json
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

sys.dont_write_bytecode = True
import preflight_item_store_weekly_prices as weekly
import preflight_anomaly_baseline_scope as baseline
import preflight_anomaly_candidates as candidates


COLUMNS = ['case_id', 'selected_class', 'retail_week', 'week_start', 'relative_week', 'units',
           'rolling_baseline_units', 'screen_class', 'context_role', 'sell_price', 'has_price', 'check_status']
SELECTION_FIELDS = ['case_id', 'selected_class', 'item_id', 'store_id', 'selected_week',
                    'candidate_pool_rows', 'selected_rank', 'unit_difference_x4']
CLASSIFIED_FIELDS = candidates.CLASSIFIED_FIELDS
PROTOCOL_SHA = '3753621c151d3e6e16e904876e86f6da18de65cf8bbd8106ceb41ef18141727b'
RULES_SHA = candidates.RULES_SHA
FROZEN_CLASSIFIED_SHA = '901d908b825f192b0dd1a7baabfe9ad38cdf96add65f7fa891b7aa15dea85e31'
FROZEN_FEATURE_SHA = '556c07cf090b18fc6d60c00770b524d2d71464d3aece8968c438fea0c558c38f'
PRIVATE_REFERENCE = 'exports/private/sql53_case_history_reference.json'


def selection_reference(rows):
    pools = {label: [] for label in candidates.CLASSES[:3]}
    for row in rows:
        if row[-1] in pools:
            pools[row[-1]].append(row)
    selected = []
    for case_number, (label, pool) in enumerate(pools.items(), start=1):
        assert pool, 'Required candidate class is absent'
        ordered = sorted(pool, key=lambda row: (abs(row[-2]), row[0], row[1], row[5]))
        rank = (len(pool) + 1) // 2
        target = ordered[rank - 1]
        selected.append(dict(zip(SELECTION_FIELDS, [f'CASE_{case_number}', label, target[0], target[1],
            target[5], len(pool), rank, target[-2]])))
    return selected


def history_reference(series, prices, selected):
    sources = {(row['item_id'], row['store_id']): row for row in series}
    results = []
    for selection in selected:
        source = sources[(selection['item_id'], selection['store_id'])]
        own_features = {row[5]: row for row in candidates.expected_classified([source], prices)}
        for row in weekly.expected_rows([source], prices):
            week = row[5]
            relative = week - selection['selected_week']
            feature = own_features.get(week)
            role = 'EARLIER' if relative < -4 else 'BASELINE' if relative < 0 else 'TARGET' if relative == 0 else 'LATER'
            results.append(dict(zip(COLUMNS, [selection['case_id'], selection['selected_class'], str(week), row[6],
                relative, row[8], None if feature is None else feature[17], 'WARMUP' if feature is None else feature[-1],
                role, row[10], row[11], 'PASS'])))
    return results


def normalize_report(actual):
    assert len(actual) == 36 and all(list(row) == COLUMNS for row in actual), 'Private history report shape/order mismatch'
    for row in actual:
        for key in ['relative_week', 'units']:
            value = Decimal(str(row[key]))
            assert value.is_finite() and value == int(value)
            row[key] = int(value)
        for key in ['rolling_baseline_units', 'sell_price']:
            if row[key] is not None:
                value = Decimal(str(row[key]))
                assert value.is_finite() and value * 100 == int(value * 100)
                if key == 'rolling_baseline_units':
                    assert value * 4 == int(value * 4)
                row[key] = format(value, '.2f')
        assert type(row['has_price']) is bool and row['has_price'] == (row['sell_price'] is not None)
    return actual


def case_summaries(report, selected):
    summaries = []
    for selection in selected:
        rows = [row for row in report if row['case_id'] == selection['case_id']]
        target = [row for row in rows if row['context_role'] == 'TARGET']
        prior = [row for row in rows if row['context_role'] == 'BASELINE']
        warmup = [row for row in rows if row['screen_class'] == 'WARMUP']
        assert len(rows) == 12 and len({row['retail_week'] for row in rows}) == 12
        assert [row['retail_week'] for row in rows] == [str(week) for week in range(11601, 11613)]
        assert len(target) == 1 and len(prior) == 4 and len(warmup) == 4
        assert target[0]['screen_class'] == selection['selected_class']
        assert target[0]['relative_week'] == 0
        assert [row['relative_week'] for row in prior] == [-4, -3, -2, -1]
        assert Decimal(target[0]['rolling_baseline_units']) * 4 == sum(row['units'] for row in prior)
        assert 4 * target[0]['units'] - sum(row['units'] for row in prior) == selection['unit_difference_x4']
        assert all(row['rolling_baseline_units'] is None for row in warmup)
        assert all(row['rolling_baseline_units'] is not None for row in rows if row not in warmup)
        assert all(row['check_status'] == 'PASS' for row in rows)
        summaries.append(dict(case_id=selection['case_id'], selected_class=selection['selected_class'],
            candidate_pool_rows=selection['candidate_pool_rows'], selected_rank=selection['selected_rank'],
            selected_cases=1, context_rows=12, baseline_role_rows=4, target_role_rows=1,
            warmup_rows=4, eligible_rows=8, check_status='PASS'))
    return summaries


def compare_selection_export(path, expected):
    with path.open(newline='', encoding='utf-8') as stream:
        reader = csv.DictReader(stream)
        assert reader.fieldnames == SELECTION_FIELDS, 'Private selection field/order mismatch'
        actual = list(reader)
    assert len(actual) == 3, 'Private selection count mismatch'
    for row in actual:
        for key in SELECTION_FIELDS[4:]:
            row[key] = int(row[key])
    assert actual == expected, 'Selected private keys/ranks differ from independent complete-pool sort'
    return weekly.canonical_hash([[row[key] for key in SELECTION_FIELDS] for row in actual])


def fixture(missing_class=False):
    profiles = [[7, 7, 7, 7] + [0] * 7 + [0 if missing_class else 7], [14, 14, 14, 14] + [7] * 8]
    series, prices = [], {}
    for item, units in enumerate(profiles, start=1):
        row = dict(item_id=f'P{item}', store_id='S1', dept_id='FOODS_1', cat_id='FOODS', state_id='CA',
                   days=[value if day == 0 else 0 for value in units for day in range(7)])
        series.append(row)
        for offset in range(12):
            if item == 1 and offset == 4:
                continue
            prices[(row['item_id'], 'S1', 11601 + offset)] = Decimal('1.00')
    raw_values = ','.join('(' + ','.join(weekly.quote(row[key]) for key in
        ['item_id', 'store_id', 'dept_id', 'cat_id', 'state_id']) + ')' for row in series)
    daily_values = ','.join(f"({weekly.quote(row['item_id'])},'S1','d_{1828 + offset}',"
        f"DATE '{(weekly.START + timedelta(days=offset)).isoformat()}',{11601 + offset // 7},{units})"
        for row in series for offset, units in enumerate(row['days']))
    price_values = ','.join(f"('S1',{weekly.quote(item)},{week},{price})" for (item, _, week), price in prices.items())
    setup = f"""
CREATE SCHEMA raw; CREATE SCHEMA core; CREATE SCHEMA mart; CREATE SCHEMA stg;
CREATE TABLE raw.m5_sales_wide AS SELECT * FROM (VALUES {raw_values}) t(item_id,store_id,dept_id,cat_id,state_id);
CREATE TABLE core.m5_product AS SELECT DISTINCT item_id,dept_id,cat_id FROM raw.m5_sales_wide;
CREATE TABLE core.m5_store AS SELECT DISTINCT store_id,state_id FROM raw.m5_sales_wide;
CREATE TABLE core.m5_calendar AS SELECT 'd_'||CAST(n AS VARCHAR) AS d,
    DATE '2011-01-29'+CAST(n-1 AS INTEGER) AS date,
    CAST(11601+floor((n-1828)/7) AS INTEGER) AS wm_yr_wk FROM range(1,1970) t(n);
CREATE TABLE mart.m5_sales_daily(item_id VARCHAR,store_id VARCHAR,d VARCHAR,date DATE,wm_yr_wk INTEGER,units INTEGER);
INSERT INTO mart.m5_sales_daily VALUES {daily_values};
CREATE TABLE stg.m5_prices(store_id VARCHAR,item_id VARCHAR,wm_yr_wk INTEGER,sell_price DECIMAL(18,2));
INSERT INTO stg.m5_prices VALUES {price_values};
"""
    return setup, series, prices


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--duckdb', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--fixtures-only', action='store_true')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    tmp_root = root / 'tmp'
    tmp_root.mkdir(exist_ok=True)
    script_path = 'sql/53_review_anomaly_case_histories.sql'
    validator_path = 'validation/preflight_anomaly_case_histories.py'
    protocol_path = 'docs/ANOMALY_CASE_HISTORIES_PROTOCOL.md'
    sql_paths = {'09': 'sql/09_stage_prices.sql', '23': 'sql/23_build_product_weekly.sql',
                 '44': 'sql/44_build_item_store_weekly_prices.sql', '45': 'sql/45_audit_price_variation.sql',
                 '46': 'sql/46_price_sales_association.sql', '47': 'sql/47_weekly_price_sales_association.sql',
                 '48': 'sql/48_department_price_sales_association.sql', '49': 'sql/49_week_department_price_contrasts.sql', '50': 'sql/50_audit_anomaly_baseline_scope.sql', '51': 'sql/51_screen_anomaly_candidates.sql', '52': 'sql/52_weekly_anomaly_triage.sql'}
    prior_evidence = ['data/item_store_weekly_prices_preflight.json', 'data/price_variation_preflight.json',
                      'data/price_sales_association_preflight.json', 'data/weekly_price_sales_association_preflight.json',
                      'data/department_price_sales_association_preflight.json', 'data/week_department_price_contrasts_preflight.json',
                      'data/anomaly_baseline_scope_preflight.json', 'data/anomaly_candidates_preflight.json', 'data/weekly_anomaly_triage_preflight.json']
    paths = [script_path, validator_path, protocol_path, *sql_paths.values(), *prior_evidence,
             'validation/preflight_item_store_weekly_prices.py', 'validation/preflight_anomaly_baseline_scope.py', 'validation/preflight_anomaly_candidates.py',
             'docs/ANOMALY_CANDIDATES_PROTOCOL.md', 'data/anomaly_candidates_learner_acceptance.json', 'docs/ANOMALY_CANDIDATES_VALIDATION.md', 'validation/preflight_weekly_anomaly_triage.py',
             'docs/WEEKLY_ANOMALY_TRIAGE_PROTOCOL.md', 'data/weekly_anomaly_triage_learner_acceptance.json',
             'docs/WEEKLY_ANOMALY_TRIAGE_VALIDATION.md', '.gitignore', 'docs/ANOMALY_SCREENING_PROTOCOL.md', 'docs/ITEM_STORE_WEEKLY_PRICES_PROTOCOL.md',
             'docs/PRICE_VARIATION_PROTOCOL.md', 'docs/PRICE_SALES_ASSOCIATION_PROTOCOL.md',
             'docs/WEEKLY_PRICE_SALES_ASSOCIATION_PROTOCOL.md', 'docs/DEPARTMENT_PRICE_SALES_ASSOCIATION_PROTOCOL.md',
             'docs/WEEK_DEPARTMENT_PRICE_CONTRASTS_PROTOCOL.md']
    hashes = {path: weekly.sha256(root / path) for path in paths}
    assert hashes[protocol_path] == PROTOCOL_SHA, 'Frozen candidate report protocol changed'
    assert hashes['docs/ANOMALY_SCREENING_PROTOCOL.md'] == RULES_SHA, 'Already-frozen screening rules changed'
    audit = (root / script_path).read_text(encoding='utf-8')
    scripts = {key: (root / path).read_text(encoding='utf-8') for key, path in sql_paths.items()}
    prefix = lambda sql, boundary: sql[sql.index('WITH parameters AS ('):sql.index(boundary)]
    assert prefix(audit, '), case_plan(') == prefix(scripts['52'], '), target_weeks AS ('), 'Accepted input guard prefix changed'
    base_query = audit[:audit.rindex('\nSELECT r.case_id,r.selected_class,')]
    private_from = """
FROM input_health i CROSS JOIN history_health h CROSS JOIN selection_health s CROSS JOIN report_health c
"""
    private_guard = """
WHERE CASE WHEN COALESCE(i.passed AND h.passed AND s.passed AND c.passed,false) THEN true
           ELSE error('Anomaly case private validation blocked') END
"""
    classified_sql = base_query + '\nSELECT ' + ','.join('f.' + key for key in CLASSIFIED_FIELDS) + \
        private_from + 'LEFT JOIN classified f ON true\n' + private_guard + 'ORDER BY f.item_id,f.store_id,f.wm_yr_wk'
    selection_projection = """SELECT r.case_id,r.selected_class,r.item_id,r.store_id,r.selected_week,
        r.pool_rows AS candidate_pool_rows,r.selection_rank AS selected_rank,r.selected_difference_x4 AS unit_difference_x4
"""
    selection_sql = base_query + '\n' + selection_projection + private_from + \
        'LEFT JOIN selected_cases r ON true\n' + private_guard + 'ORDER BY r.case_order'
    builds = {key: scripts[key].split('-- VALIDATION:', 1)[0] for key in ['09', '23', '44']}

    def execute(database, folder, query, allow_error=False):
        assert database.resolve().is_relative_to(tmp_root.resolve()) and folder.resolve().is_relative_to(tmp_root.resolve())
        settings = f"SET threads=2; SET memory_limit='2GB'; SET temp_directory={weekly.quote((folder / 'spill').as_posix())};\n"
        started = time.perf_counter()
        run = subprocess.run([args.duckdb, str(database), '-bail', '-json'], input=settings + query,
                             text=True, encoding='utf-8', capture_output=True)
        if not allow_error:
            assert run.returncode == 0, run.stderr
        return run, round(time.perf_counter() - started, 3)

    private_path = root / PRIVATE_REFERENCE
    assert private_path.resolve().is_relative_to(root.resolve())
    assert private_path.resolve().is_relative_to((root / 'exports/private').resolve())
    ignore_rules = [line.strip() for line in (root / '.gitignore').read_text(encoding='utf-8').splitlines()]
    assert 'exports/**' in ignore_rules and not any(line.startswith(('!exports', '!/exports')) for line in ignore_rules)
    assert not (root / 'exports/.gitignore').exists() and not (root / 'exports/private/.gitignore').exists()
    public_artifacts = [script_path, validator_path, protocol_path, 'data/anomaly_case_histories_preflight.json']
    assert PRIVATE_REFERENCE not in public_artifacts and not any(path.startswith('exports/') for path in public_artifacts)
    assert args.output.resolve() == (root / public_artifacts[-1]).resolve()

    cases = []
    for missing_class in [False, True]:
        setup, series, prices = fixture(missing_class)
        expected_units = sum(sum(row['days']) for row in series)
        transform = lambda sql: sql.replace('3049 AS expected_items,10 AS expected_stores',
                                            '2 AS expected_items,1 AS expected_stores').replace(
                                                '3536539 AS expected_units', f'{expected_units} AS expected_units')
        with tempfile.TemporaryDirectory(prefix='case-history-fixture-', dir=tmp_root) as temp:
            folder = Path(temp)
            database = folder / 'case.duckdb'
            execute(database, folder, setup + transform(builds['23']) + transform(builds['44']))
            run, _ = execute(database, folder, transform(audit), allow_error=missing_class)
            if missing_class:
                assert run.returncode != 0 and 'Anomaly case histories blocked' in run.stderr
                cases.append(dict(case='missing_one_candidate_class_rejected', passed=True, expected_rejection=True))
                continue
            selected = selection_reference(candidates.expected_classified(series, prices))
            expected = history_reference(series, prices, selected)
            actual = normalize_report(weekly.parsed(run.stdout))
            assert actual == expected, 'Synthetic private history mismatch'
            case_summaries(actual, selected)
            assert [row['selected_week'] for row in selected] == [11605, 11612, 11605]
            assert selected[0]['item_id'] == selected[1]['item_id']
            assert not any(row['context_role'] == 'LATER' for row in actual if row['case_id'] == 'CASE_2')
            assert any(row['sell_price'] is None and row['has_price'] is False for row in actual)
            selection_export = folder / 'selected.csv'
            execute(database, folder, f'COPY ({transform(selection_sql)}) TO {weekly.quote(selection_export.as_posix())} (HEADER,FORMAT CSV);')
            compare_selection_export(selection_export, selected)
            cases.append(dict(case='full_history_early_late_targets_shared_pair_warmup_null_prices_and_prior_role_baseline', passed=True))
            rejected, _ = execute(database, folder, 'DELETE FROM core.m5_calendar;\n' + transform(audit), allow_error=True)
            assert rejected.returncode != 0 and 'Anomaly case histories blocked' in rejected.stderr
            cases.append(dict(case='empty_calendar_intended_rejection', passed=True, expected_rejection=True))
        assert not folder.exists()

    # Rank actual production selection CTEs on deliberately unsorted synthetic pools.
    mock = [('SUDDEN_ZERO', 'A', 'S2', 11606, -28), ('SUDDEN_ZERO', 'A', 'S1', 11607, -28),
            ('SUDDEN_ZERO', 'A', 'S1', 11605, -28), ('SUDDEN_ZERO', 'B', 'S1', 11605, -28),
            ('LARGE_INCREASE', 'A', 'S1', 11608, 28), ('LARGE_INCREASE', 'A', 'S1', 11609, 32),
            ('LARGE_INCREASE', 'A', 'S1', 11610, 32), ('LARGE_INCREASE', 'A', 'S2', 11610, 40),
            ('LARGE_INCREASE', 'B', 'S2', 11611, 44), ('LARGE_DECREASE', 'A', 'S1', 11611, -60),
            ('LARGE_DECREASE', 'B', 'S2', 11612, -28)]
    mock_rows = []
    for label, item, store, week, delta in mock:
        row = [None] * len(CLASSIFIED_FIELDS)
        row[0], row[1], row[5], row[-2], row[-1] = item, store, week, delta, label
        mock_rows.append(row)
    mock_expected = selection_reference(mock_rows)
    assert [(row['candidate_pool_rows'], row['selected_rank']) for row in mock_expected] == [(4, 2), (5, 3), (2, 1)]
    assert [(row['item_id'], row['store_id'], row['selected_week']) for row in mock_expected] == [
        ('A', 'S1', 11607), ('A', 'S1', 11610), ('B', 'S2', 11612)]
    values = ','.join(f'({weekly.quote(label)},{weekly.quote(item)},{weekly.quote(store)},{week},{delta}::HUGEINT)'
                      for label, item, store, week, delta in reversed(mock))
    selection_ctes = audit[audit.index('), case_plan('):audit.index('), case_history AS MATERIALIZED (')] + ')\n'
    mock_sql = ('WITH classified AS (SELECT * FROM (VALUES ' + values +
        ') t(candidate_class,item_id,store_id,wm_yr_wk,unit_difference_x4)\n' + selection_ctes +
        selection_projection + 'FROM selected_cases r ORDER BY r.case_order')
    with tempfile.TemporaryDirectory(prefix='case-rank-fixture-', dir=tmp_root) as temp:
        folder = Path(temp)
        selection_export = folder / 'selected.csv'
        execute(folder / 'case.duckdb', folder, f'COPY ({mock_sql}) TO {weekly.quote(selection_export.as_posix())} (HEADER,FORMAT CSV);')
        compare_selection_export(selection_export, mock_expected)
    assert not folder.exists()
    cases.append(dict(case='production_lower_median_even_odd_absolute_gap_and_item_store_week_tie_order', passed=True))
    print(json.dumps({'fixture_cases_passed': len(cases)}), flush=True)
    if args.fixtures_only:
        return

    sources = {name: Path('D:/database/m5-forecasting-accuracy') / name
               for name in ['sales_train_evaluation.csv', 'calendar.csv', 'sell_prices.csv']}
    registry = json.loads((root / 'data/m5_source_audit.json').read_text(encoding='utf-8'))
    source_hashes = {name: weekly.sha256(path) for name, path in sources.items()}
    assert all(source_hashes[name] == registry['files'][name]['sha256'] for name in sources)
    historical = {str(path.relative_to(root)): weekly.sha256(path) for path in (root / 'data').glob('*preflight.json')
                  if path.resolve() != args.output.resolve()}
    series, prices, controls, reference_seconds = weekly.read_original_sources(sources)
    selected = selection_reference(candidates.expected_classified(series, prices))
    expected = history_reference(series, prices, selected)
    summaries = case_summaries(expected, selected)
    accepted_weekly = json.loads((root / prior_evidence[0]).read_text(encoding='utf-8'))
    accepted_candidates = json.loads((root / 'data/anomaly_candidates_preflight.json').read_text(encoding='utf-8'))
    candidates.assert_report(candidates.summarize_classified(candidates.expected_classified(series, prices)), accepted_candidates['results'])
    class_counts = {row['candidate_class']: row['target_rows'] for row in accepted_candidates['results']}
    assert all(row['candidate_pool_rows'] == class_counts[row['selected_class']] for row in summaries)

    day_columns = ','.join(f'd_{n}' for n in range(1828, 1912))
    setup = f"""
CREATE SCHEMA raw; CREATE SCHEMA core; CREATE SCHEMA mart; CREATE SCHEMA stg;
CREATE TABLE raw.m5_sales_wide AS SELECT id,item_id,dept_id,cat_id,store_id,state_id,{day_columns}
FROM read_csv({weekly.quote(sources['sales_train_evaluation.csv'].as_posix())},header=true,all_varchar=true);
CREATE TABLE core.m5_product AS SELECT DISTINCT item_id,dept_id,cat_id FROM raw.m5_sales_wide;
CREATE TABLE core.m5_store AS SELECT DISTINCT store_id,state_id FROM raw.m5_sales_wide;
CREATE TABLE core.m5_calendar AS SELECT d,CAST(date AS DATE) AS date,CAST(wm_yr_wk AS INTEGER) AS wm_yr_wk
FROM read_csv({weekly.quote(sources['calendar.csv'].as_posix())},header=true,all_varchar=true);
CREATE TABLE mart.m5_sales_daily AS WITH unpivoted AS
(UNPIVOT raw.m5_sales_wide ON {day_columns} INTO NAME d VALUE units_text)
SELECT u.item_id,u.store_id,u.d,c.date,c.wm_yr_wk,
CASE WHEN regexp_full_match(units_text,'[0-9]+') AND TRY_CAST(units_text AS INTEGER) IS NOT NULL
THEN CAST(units_text AS INTEGER) ELSE error('Invalid original window units') END AS units
FROM unpivoted u JOIN core.m5_calendar c USING (d);
CREATE TABLE raw.m5_prices AS SELECT * FROM read_csv({weekly.quote(sources['sell_prices.csv'].as_posix())},header=true,all_varchar=true)
WHERE TRY_CAST(wm_yr_wk AS INTEGER) BETWEEN 11601 AND 11612 OR TRY_CAST(wm_yr_wk AS INTEGER) IS NULL;
"""
    snapshots = {
        'weekly_input': f'SELECT * FROM {weekly.TARGET} ORDER BY item_id,store_id,wm_yr_wk',
        'pooled_input': 'SELECT * FROM mart.m5_product_weekly_12w ORDER BY item_id,wm_yr_wk',
        'raw_metadata': 'SELECT item_id,store_id,dept_id,cat_id,state_id FROM raw.m5_sales_wide ORDER BY item_id,store_id',
        'calendar_date_week_projection': 'SELECT * FROM core.m5_calendar ORDER BY date,d,wm_yr_wk',
        'products': 'SELECT * FROM core.m5_product ORDER BY item_id',
        'stores': 'SELECT * FROM core.m5_store ORDER BY store_id',
        'prices_12w': 'SELECT * FROM stg.m5_prices ORDER BY item_id,store_id,wm_yr_wk',
    }
    with tempfile.TemporaryDirectory(prefix='anomaly-case-histories-', dir=tmp_root) as temp:
        folder = Path(temp)
        database = folder / 'preflight.duckdb'
        _, setup_seconds = execute(database, folder, setup + builds['09'] + builds['23'] + builds['44'])

        def snapshot(prefix_name):
            query = ''.join(f'COPY ({query}) TO {weekly.quote((folder / (prefix_name + "_" + name + ".csv")).as_posix())} (HEADER,FORMAT CSV);\n'
                            for name, query in snapshots.items())
            execute(database, folder, query)
            return {name: weekly.sha256(folder / f'{prefix_name}_{name}.csv') for name in snapshots}

        before = snapshot('before')
        row_count, input_hash = weekly.compare_export(folder / 'before_weekly_input.csv', weekly.expected_rows(series, prices))
        assert row_count == 365880 and input_hash == weekly.canonical_hash(weekly.expected_rows(series, prices))
        assert input_hash == accepted_weekly['stored_rows_sha256'], 'SQL44 accepted input fingerprint changed'
        pooled_count, pooled_hash = weekly.compare_pooled_export(folder / 'before_pooled_input.csv', series)
        price_count = weekly.compare_price_export(folder / 'before_prices_12w.csv', prices)
        classified_export = folder / 'classified_targets.csv'
        _, classified_seconds = execute(database, folder,
            f'COPY ({classified_sql}) TO {weekly.quote(classified_export.as_posix())} (HEADER,FORMAT CSV);')
        classified_count, feature_hash, classified_hash = candidates.compare_classified_export(
            classified_export, candidates.expected_classified(series, prices))
        assert classified_count == 243920 and feature_hash == FROZEN_FEATURE_SHA and classified_hash == FROZEN_CLASSIFIED_SHA
        selection_export = folder / 'selected_keys.csv'
        _, selection_seconds = execute(database, folder,
            f'COPY ({selection_sql}) TO {weekly.quote(selection_export.as_posix())} (HEADER,FORMAT CSV);')
        selection_hash = compare_selection_export(selection_export, selected)
        run, audit_seconds = execute(database, folder, audit)
        actual = normalize_report(weekly.parsed(run.stdout))
        assert actual == expected, 'Private 36-row context differs from independent original-source history'
        assert case_summaries(actual, selected) == summaries
        report_hash = weekly.canonical_hash([[row[key] for key in COLUMNS] for row in actual])
        after = snapshot('after')
        assert before == after, 'Read-only case review changed a scoped input'
        database_bytes = database.stat().st_size
    assert not folder.exists()
    assert all(weekly.sha256(path) == source_hashes[name] for name, path in sources.items())
    assert all(weekly.sha256(root / path) == value for path, value in historical.items())
    assert all(weekly.sha256(root / path) == value for path, value in hashes.items())

    # Sole intentional retained row-level artifact; never place its contents in public evidence/stdout.
    private_payload = {'output_columns': COLUMNS, 'results': expected}
    assert all(list(row) == COLUMNS and 'item_id' not in row and 'store_id' not in row for row in expected)
    private_path.parent.mkdir(parents=True, exist_ok=True)
    assert private_path.resolve().is_relative_to(root.resolve())
    private_path.write_text(json.dumps(private_payload, indent=2) + '\n', encoding='utf-8', newline='\n')
    assert json.loads(private_path.read_text(encoding='utf-8')) == private_payload
    private_hash = weekly.sha256(private_path)
    evidence = dict(
        checked_at_utc=datetime.now(timezone.utc).isoformat(), executor='assistant',
        engine=subprocess.check_output([args.duckdb, '-version'], text=True).strip(),
        script=script_path, script_sha256=hashes[script_path], validator=validator_path, validator_sha256=hashes[validator_path],
        protocol=protocol_path, protocol_sha256=PROTOCOL_SHA, original_screening_protocol_sha256=RULES_SHA,
        code_and_dependency_sha256=hashes, settings={'threads': 2, 'memory_limit': '2GB'},
        source_sha256=source_hashes, source_hashes_unchanged=True, source_controls=controls,
        input_window={'start_date': '2016-01-30', 'end_date': '2016-04-22', 'weeks': 12, 'pairs': 30490},
        target_window={'first_week': 11605, 'last_week': 11612, 'start_date': '2016-02-27', 'end_date': '2016-04-22', 'weeks': 8, 'target_rows': 243920},
        independent_reference='Original-source weekly observations and direct prior-four classification reproduce the complete accepted twenty-field target fingerprint. Independent Python sorting of every class pool by absolute integer gap, item, store and target week verifies all three private keys/ranks. Original-source twelve-week histories and own-week features verify every private 36-row/twelve-field value and selected-target baseline; only aggregate coverage and fingerprints are published.',
        preflight_strategy='One private bounded database builds only the accepted 84-day projection/twelve-week prices through unchanged SQL09/23/44. Old forecast/price analyses and classification boundary suites are not rerun; learner persistent database is never opened. All actual key exports, input/classification snapshots and the database are removed; one explicitly ignored expected learner report is retained privately.',
        weekly_input_rows_compared=row_count, weekly_input_fields_compared=12, weekly_input_exact_mismatches=0,
        weekly_input_rows_sha256=input_hash, accepted_sql44_input_fingerprint_matched=True,
        pooled_rows_compared=pooled_count, pooled_fields_compared=8, pooled_rows_sha256=pooled_hash,
        price_rows_compared=price_count, price_fields_compared=4,
        target_feature_rows_compared=classified_count, target_feature_fields_compared=18,
        target_feature_exact_mismatches=0, target_feature_rows_sha256=feature_hash,
        accepted_sql50_feature_fingerprint_matched=True,
        classified_rows_compared=classified_count, classified_fields_compared=20, classified_exact_mismatches=0,
        classified_rows_sha256=classified_hash, accepted_sql51_classified_fingerprint_matched=True,
        sql52_input_history_classification_prefix_unchanged=True,
        sql51_rows_reconciled=5, sql51_fields_reconciled=12, sql51_accepted_report_matched=True,
        selection_rows_compared=3, selection_fields_compared=8, selection_exact_mismatches=0,
        selection_rows_sha256=selection_hash, selection_uses_all_class_targets=True,
        exact_lower_median_and_tiebreaks_verified=True, selected_target_classes_matched=True,
        own_week_baselines_and_warmup_verified=True, displayed_prior_units_reconcile_target_baseline=True,
        retrospective_later_context_excluded_from_target_baseline=True,
        report_rows=36, report_columns=12, output_columns=COLUMNS, report_exact_mismatches=0,
        report_sha256=report_hash, case_summaries=summaries,
        report_fingerprint_contract='SHA-256 over ordered compact JSON arrays plus LF in output_columns order; units/relative weeks are integers, prices/baselines fixed-two-place strings or null, has_price Boolean, dates/week IDs/labels strings. Full report values remain in the ignored private reference only.',
        private_reference_path=PRIVATE_REFERENCE, private_reference_sha256=private_hash,
        private_reference_retained=True, private_reference_gitignored=True, private_reference_gitignore_rule='exports/**',
        private_reference_excluded_from_public_artifacts=True, public_artifacts=public_artifacts,
        public_evidence_contains_case_values=False,
        scoped_input_sha256_before=before, scoped_input_sha256_after=after, scoped_inputs_unchanged=True,
        historical_preflight_files_unchanged=len(historical), temporary_database_removed=True,
        temporary_selection_exports_removed=True, temporary_intermediate_exports_removed=True,
        temporary_database_bytes_after_close=database_bytes, fixture_case_count=len(cases), fixture_cases=cases,
        independent_source_read_seconds=reference_seconds, setup_seconds=setup_seconds,
        classified_export_seconds=classified_seconds, selection_export_seconds=selection_seconds, audit_seconds=audit_seconds,
        timing_scope='One-run elapsed seconds; CLI timings exclude hashing/Python comparisons. DuckDB memory_limit is not a total-process cap.',
        scope='Assistant independent preflight only; learner SQL53 execution pending. Three deterministic illustrative median-gap target histories, not a representative sample, verified anomalies or causal explanations. Aliases are labels, not anonymisation. Actual identifiers and context values are excluded from public evidence. The ignored private expected report is intentionally retained for acceptance; databases, actual-key exports and other intermediates are deleted.')
    assert 'results' not in evidence and all(set(row) == {'case_id', 'selected_class', 'candidate_pool_rows',
        'selected_rank', 'selected_cases', 'context_rows', 'baseline_role_rows', 'target_role_rows',
        'warmup_rows', 'eligible_rows', 'check_status'} for row in evidence['case_summaries'])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps({'fixture_cases_passed': len(cases), 'weekly_input_rows_compared': row_count,
        'classified_rows_compared': classified_count, 'report_rows': 36, 'report_columns': 12,
        'audit_seconds': audit_seconds, 'case_summaries': summaries, 'report_sha256': report_hash,
        'private_reference_retained': True}), flush=True)


if __name__ == '__main__':
    main()
