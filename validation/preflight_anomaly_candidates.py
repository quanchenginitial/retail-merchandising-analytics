"""Independently verify frozen retrospective screening labels and aggregate candidates."""
import argparse
import csv
import hashlib
import json
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from fractions import Fraction
from pathlib import Path

sys.dont_write_bytecode = True
import preflight_item_store_weekly_prices as weekly
import preflight_anomaly_baseline_scope as baseline


COLUMNS = ['candidate_class', 'target_rows', 'target_share_pct', 'distinct_series', 'baseline_units',
           'observed_units', 'unit_difference', 'mean_unit_difference', 'zero_observed_rows',
           'zero_baseline_rows', 'missing_price_rows', 'check_status']
CLASSES = ['SUDDEN_ZERO', 'LARGE_INCREASE', 'LARGE_DECREASE', 'NONE', 'TOTAL']
FEATURE_FIELDS = baseline.FEATURE_FIELDS
CLASSIFIED_FIELDS = [*FEATURE_FIELDS, 'unit_difference_x4', 'candidate_class']
PROTOCOL_SHA = 'ddce2fb220adf2e7c2050ce1ab8586b5378df5adef97a3d083504983d0b4652f'
RULES_SHA = 'dd2376b370d2350d51d49e20b7ba29254b0fc49215e3c58e79d2d7b4ed4c7b2d'


def fixed_fraction(value, places):
    if value is None:
        return None
    scale = 10 ** places
    quotient, remainder = divmod(abs(value.numerator) * scale, value.denominator)
    quotient += 2 * remainder >= value.denominator
    sign = '-' if value < 0 and quotient else ''
    return f'{sign}{quotient // scale}.{quotient % scale:0{places}d}'


def classify_reference(row):
    """Compare exact rational unit levels, independently of SQL's scaled inequalities."""
    current = row['units']
    mean = Fraction(row['history_units'], 4)
    if current == 0 and row['positive_history_weeks'] == 4 and mean >= 7:
        return 'SUDDEN_ZERO'
    if current >= 2 * mean and current - mean >= 7:
        return 'LARGE_INCREASE'
    if current <= mean / 2 and mean - current >= 7:
        return 'LARGE_DECREASE'
    return 'NONE'


def expected_classified(series, prices):
    for values in baseline.expected_features(series, prices):
        row = dict(zip(FEATURE_FIELDS, values))
        yield [*values, 4 * row['units'] - row['history_units'], classify_reference(row)]


def summarize_classified(rows):
    groups = {label: dict(n=0, pairs=set(), history_sum=0, units=0, difference_x4=0,
                         zero_observed=0, zero_baseline=0, missing_price=0) for label in CLASSES}
    for values in rows:
        row = dict(zip(CLASSIFIED_FIELDS, values))
        for label in [row['candidate_class'], 'TOTAL']:
            group = groups[label]
            group['n'] += 1
            group['pairs'].add((row['item_id'], row['store_id']))
            group['history_sum'] += row['history_units']
            group['units'] += row['units']
            group['difference_x4'] += row['unit_difference_x4']
            group['zero_observed'] += row['units'] == 0
            group['zero_baseline'] += row['history_units'] == 0
            group['missing_price'] += not row['has_price']
    total = groups['TOTAL']['n']
    assert total > 0
    return [dict(zip(COLUMNS, [label, group['n'], fixed_fraction(Fraction(100 * group['n'], total), 4),
        len(group['pairs']), fixed_fraction(Fraction(group['history_sum'], 4), 2), group['units'],
        fixed_fraction(Fraction(group['difference_x4'], 4), 2),
        None if not group['n'] else fixed_fraction(Fraction(group['difference_x4'], 4 * group['n']), 6),
        group['zero_observed'], group['zero_baseline'], group['missing_price'], 'PASS']))
        for label, group in groups.items()]


def assert_report(actual, expected):
    assert len(actual) == 5 and all(list(row) == COLUMNS for row in actual), 'Candidate report shape/order mismatch'
    precision = {'target_share_pct': 4, 'baseline_units': 2, 'unit_difference': 2, 'mean_unit_difference': 6}
    for row in actual:
        for key in COLUMNS[1:-1]:
            if row[key] is None:
                assert key == 'mean_unit_difference' and row['target_rows'] == 0
                continue
            value = Decimal(str(row[key]))
            assert value.is_finite()
            if key in precision:
                fixed = fixed_fraction(Fraction(value), precision[key])
                assert value == Decimal(fixed), 'Output exceeds frozen display precision'
                row[key] = fixed
                if key in ['baseline_units', 'unit_difference']:
                    assert value * 4 == int(value * 4), 'Unit sum is not an exact quarter'
            else:
                assert value == int(value)
                row[key] = int(value)
        assert Decimal(row['unit_difference']) == row['observed_units'] - Decimal(row['baseline_units'])
    assert actual == expected, 'Candidate report differs from independent exact Fraction reference'
    for key in ['target_rows', 'baseline_units', 'observed_units', 'unit_difference',
                'zero_observed_rows', 'zero_baseline_rows', 'missing_price_rows']:
        assert sum(Decimal(str(row[key])) for row in actual[:-1]) == Decimal(str(actual[-1][key]))


def compare_classified_export(path, expected):
    feature_digest, classified_digest = hashlib.sha256(), hashlib.sha256()
    count = 0
    with path.open(newline='', encoding='utf-8') as stream:
        reader = csv.DictReader(stream)
        assert reader.fieldnames == CLASSIFIED_FIELDS, 'Unexpected classified feature schema/order'
        for reference in expected:
            row = next(reader, None)
            assert row is not None, 'Classified extract ended before reference'
            feature = weekly.normalize_export({key: row[key] for key in weekly.FIELDS})
            feature += [int(row[key]) for key in FEATURE_FIELDS[12:-1]]
            baseline_value = Decimal(row['baseline_units'])
            assert baseline_value * 4 == int(baseline_value * 4)
            feature.append(format(baseline_value, '.2f'))
            classified = [*feature, int(row['unit_difference_x4']), row['candidate_class']]
            assert classified == reference, 'Exact target feature/difference/class comparison failed'
            for digest, values in [(feature_digest, feature), (classified_digest, classified)]:
                digest.update((json.dumps(values, ensure_ascii=True, separators=(',', ':')) + '\n').encode())
            count += 1
        assert next(reader, None) is None, 'Classified extract contains extra rows'
    return count, feature_digest.hexdigest(), classified_digest.hexdigest()


def fixture(empty=False):
    specifications = [
        ('priority_at_28', [7, 7, 7, 7], 0, 'SUDDEN_ZERO', False),
        ('below_28', [6, 7, 7, 7], 0, 'NONE', False),
        ('prior_zero_decrease', [0, 8, 10, 10], 0, 'LARGE_DECREASE', False),
        ('zero_baseline_6', [0, 0, 0, 0], 6, 'NONE', False),
        ('zero_baseline_7', [0, 0, 0, 0], 7, 'LARGE_INCREASE', False),
        ('increase_both_equal', [7, 7, 7, 7], 14, 'LARGE_INCREASE', False),
        ('increase_ratio_fails_absolute_passes', [8, 8, 8, 8], 15, 'NONE', False),
        ('increase_ratio_passes_absolute_fails', [1, 1, 1, 1], 7, 'NONE', False),
        ('increase_absolute_equal', [1, 1, 1, 1], 8, 'LARGE_INCREASE', False),
        ('decrease_both_equal', [14, 14, 14, 14], 7, 'LARGE_DECREASE', False),
        ('decrease_ratio_fails_absolute_passes', [15, 15, 15, 15], 8, 'NONE', False),
        ('decrease_ratio_passes_absolute_fails', [12, 12, 12, 12], 6, 'NONE', False),
        ('quarter_increase', [1, 2, 3, 5], 10, 'LARGE_INCREASE', False),
        ('quarter_absolute_fails', [1, 2, 3, 5], 9, 'NONE', False),
        ('unpriced_sudden_zero', [7, 7, 7, 7], 0, 'SUDDEN_ZERO', True),
    ] if not empty else [('all_zero', [0, 0, 0, 0], 0, 'NONE', True)]
    series, prices = [], {}
    for item, (name, prior, current, label, missing) in enumerate(specifications, start=1):
        units = prior + [current] + [0] * 7
        row = dict(item_id=f'P{item}', store_id='S1', dept_id='FOODS_1', cat_id='FOODS', state_id='CA',
                   days=[value if day == 0 else 0 for value in units for day in range(7)])
        series.append(row)
        for offset in range(12):
            if missing and offset == 4:
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
    return setup, series, prices, specifications


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--duckdb', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--fixtures-only', action='store_true')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    tmp_root = root / 'tmp'
    tmp_root.mkdir(exist_ok=True)
    script_path = 'sql/51_screen_anomaly_candidates.sql'
    validator_path = 'validation/preflight_anomaly_candidates.py'
    protocol_path = 'docs/ANOMALY_CANDIDATES_PROTOCOL.md'
    sql_paths = {'09': 'sql/09_stage_prices.sql', '23': 'sql/23_build_product_weekly.sql',
                 '44': 'sql/44_build_item_store_weekly_prices.sql', '45': 'sql/45_audit_price_variation.sql',
                 '46': 'sql/46_price_sales_association.sql', '47': 'sql/47_weekly_price_sales_association.sql',
                 '48': 'sql/48_department_price_sales_association.sql', '49': 'sql/49_week_department_price_contrasts.sql', '50': 'sql/50_audit_anomaly_baseline_scope.sql'}
    prior_evidence = ['data/item_store_weekly_prices_preflight.json', 'data/price_variation_preflight.json',
                      'data/price_sales_association_preflight.json', 'data/weekly_price_sales_association_preflight.json',
                      'data/department_price_sales_association_preflight.json', 'data/week_department_price_contrasts_preflight.json',
                      'data/anomaly_baseline_scope_preflight.json']
    paths = [script_path, validator_path, protocol_path, *sql_paths.values(), *prior_evidence,
             'validation/preflight_item_store_weekly_prices.py', 'validation/preflight_anomaly_baseline_scope.py', 'docs/ANOMALY_SCREENING_PROTOCOL.md', 'docs/ITEM_STORE_WEEKLY_PRICES_PROTOCOL.md',
             'docs/PRICE_VARIATION_PROTOCOL.md', 'docs/PRICE_SALES_ASSOCIATION_PROTOCOL.md',
             'docs/WEEKLY_PRICE_SALES_ASSOCIATION_PROTOCOL.md', 'docs/DEPARTMENT_PRICE_SALES_ASSOCIATION_PROTOCOL.md',
             'docs/WEEK_DEPARTMENT_PRICE_CONTRASTS_PROTOCOL.md']
    hashes = {path: weekly.sha256(root / path) for path in paths}
    assert hashes[protocol_path] == PROTOCOL_SHA, 'Frozen candidate report protocol changed'
    assert hashes['docs/ANOMALY_SCREENING_PROTOCOL.md'] == RULES_SHA, 'Already-frozen screening rules changed'
    audit = (root / script_path).read_text(encoding='utf-8')
    scripts = {key: (root / path).read_text(encoding='utf-8') for key, path in sql_paths.items()}
    prefix = lambda sql, boundary: sql[sql.index('WITH parameters AS ('):sql.index(boundary)]
    assert prefix(audit, '), classified AS MATERIALIZED (') == prefix(scripts['50'], '), report AS MATERIALIZED ('), 'Accepted input guard prefix changed'
    classified_sql = audit[:audit.rindex('\nSELECT r.candidate_class,')] + '\nSELECT ' + ','.join('f.' + key for key in CLASSIFIED_FIELDS) + """
FROM input_health i CROSS JOIN history_health h CROSS JOIN report_health c
LEFT JOIN classified f ON true
WHERE CASE WHEN COALESCE(i.passed AND h.passed AND c.passed,false) THEN true
           ELSE error('Anomaly candidate private classifications blocked') END
ORDER BY f.item_id,f.store_id,f.wm_yr_wk
"""
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

    cases = []
    for empty in [False, True]:
        setup, series, prices, specifications = fixture(empty)
        classified = list(expected_classified(series, prices))
        expected = summarize_classified(iter(classified))
        first_targets = {row[0]: row for row in classified if row[5] == 11605}
        for item, (name, _, _, label, _) in enumerate(specifications, start=1):
            assert first_targets[f'P{item}'][-1] == label, f'Hand-labelled boundary failed: {name}'
        if not empty:
            assert first_targets['P13'][17:19] == ['2.75', 29]
            following_flagged_actual = next(row for row in classified if row[0] == 'P6' and row[5] == 11606)
            assert following_flagged_actual[13] == 35 and following_flagged_actual[-1] == 'SUDDEN_ZERO'
            assert first_targets['P15'][11] is False and first_targets['P15'][-1] == 'SUDDEN_ZERO'
            assert sum(row['distinct_series'] for row in expected[:-1]) > expected[-1]['distinct_series']
        else:
            assert all(row['target_rows'] == 0 and row['target_share_pct'] == '0.0000'
                       and row['mean_unit_difference'] is None for row in expected[:3])
            assert expected[3]['target_rows'] == expected[-1]['target_rows'] == 8
        expected_units = sum(sum(row['days']) for row in series)
        transform = lambda sql: sql.replace('3049 AS expected_items,10 AS expected_stores',
                                            f'{len(series)} AS expected_items,1 AS expected_stores').replace(
                                                '3536539 AS expected_units', f'{expected_units} AS expected_units')
        with tempfile.TemporaryDirectory(prefix='candidate-boundary-case-', dir=tmp_root) as temp:
            folder = Path(temp)
            database = folder / 'case.duckdb'
            execute(database, folder, setup + transform(builds['23']) + transform(builds['44']))
            run, _ = execute(database, folder, transform(audit))
            assert_report(weekly.parsed(run.stdout), expected)
            export = folder / 'classified.csv'
            execute(database, folder, f'COPY ({transform(classified_sql)}) TO {weekly.quote(export.as_posix())} (HEADER,FORMAT CSV);')
            count, feature_hash, classified_hash = compare_classified_export(export, iter(classified))
            assert count == 8 * len(series)
            assert feature_hash == weekly.canonical_hash(baseline.expected_features(series, prices))
            assert classified_hash == weekly.canonical_hash(classified)
            cases.append(dict(case=('all_zero_three_empty_candidate_classes' if empty else
                'inclusive_priority_ratio_and_absolute_boundaries_quarters_zero_baselines_missing_prices_prior_actuals_nonadditive_series'),
                passed=True, hand_labelled_first_targets=len(specifications)))
            if empty:
                rejected, _ = execute(database, folder, 'DELETE FROM core.m5_calendar;\n' + transform(audit), allow_error=True)
                assert rejected.returncode != 0 and 'Anomaly candidates blocked' in rejected.stderr
                cases.append(dict(case='empty_calendar_intended_rejection', passed=True, expected_rejection=True))
        assert not folder.exists()

    # Real rule-valid feature values exercise production classification and aggregate rounding.
    arithmetic = []
    for label, count in [('LARGE_INCREASE', 128), ('LARGE_DECREASE', 128), ('SUDDEN_ZERO', 4), ('NONE', 252)]:
        for offset in range(count):
            history_sum = {'LARGE_INCREASE': 28, 'LARGE_DECREASE': 56, 'SUDDEN_ZERO': 28, 'NONE': 0}[label]
            units = (15 if offset == 0 else 14) if label == 'LARGE_INCREASE' else \
                    (6 if offset == 0 else 7) if label == 'LARGE_DECREASE' else 0
            feature = [f'R{len(arithmetic)}', 'S1', 'FOODS_1', 'FOODS', 'CA', 11605,
                       '2016-02-27', '2016-03-04', units, 7, '1.00', True, 4, history_sum,
                       4 if history_sum else 0, 11601, 11604, fixed_fraction(Fraction(history_sum, 4), 2)]
            assert classify_reference(dict(zip(FEATURE_FIELDS, feature))) == label
            arithmetic.append([*feature, 4 * units - history_sum, label])
    arithmetic_expected = summarize_classified(iter(arithmetic))
    assert arithmetic_expected[1]['mean_unit_difference'] == '7.007813'
    assert arithmetic_expected[2]['mean_unit_difference'] == '-7.007813'
    assert arithmetic_expected[0]['target_share_pct'] == '0.7813'
    assert sum(Decimal(row['target_share_pct']) for row in arithmetic_expected[:-1]) == Decimal('100.0001')
    values = ','.join(f"({weekly.quote(row[0])},'S1',{row[8]}::HUGEINT,{row[13]}::HUGEINT,{row[14]},"
                      f"{row[17]}::DECIMAL(24,2),true)" for row in arithmetic)
    production_ctes = audit[audit.index('), classified AS MATERIALIZED ('):audit.index('), report_health AS (')] + ')\n'
    arithmetic_sql = ('WITH features AS (SELECT * FROM (VALUES ' + values +
        ') t(item_id,store_id,units,history_units,positive_history_weeks,baseline_units,has_price)\n' + production_ctes +
        'SELECT ' + ','.join('r.' + key for key in COLUMNS[:-1]) + ", 'PASS' AS check_status FROM report r ORDER BY sort_order;")
    with tempfile.TemporaryDirectory(prefix='candidate-rounding-case-', dir=tmp_root) as temp:
        folder = Path(temp)
        run, _ = execute(folder / 'case.duckdb', folder, arithmetic_sql)
        assert_report(weekly.parsed(run.stdout), arithmetic_expected)
    assert not folder.exists()
    cases.append(dict(case='production_rules_and_aggregates_positive_negative_mean_half_rounding_independent_share_rounding', passed=True))
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
    expected = summarize_classified(expected_classified(series, prices))
    accepted_weekly = json.loads((root / prior_evidence[0]).read_text(encoding='utf-8'))
    accepted_baseline = json.loads((root / 'data/anomaly_baseline_scope_preflight.json').read_text(encoding='utf-8'))
    baseline.assert_report(baseline.reference_report(series, prices), accepted_baseline['results'])

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
    with tempfile.TemporaryDirectory(prefix='anomaly-candidates-', dir=tmp_root) as temp:
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
        run, sql50_seconds = execute(database, folder, scripts['50'])
        baseline.assert_report(weekly.parsed(run.stdout), accepted_baseline['results'])
        export = folder / 'classified_targets.csv'
        _, classified_seconds = execute(database, folder,
            f'COPY ({classified_sql}) TO {weekly.quote(export.as_posix())} (HEADER,FORMAT CSV);')
        classified_count, feature_hash, classified_hash = compare_classified_export(export, expected_classified(series, prices))
        assert classified_count == 243920
        assert feature_hash == accepted_baseline['target_feature_rows_sha256'], 'Accepted SQL50 feature fingerprint changed'
        assert classified_hash == weekly.canonical_hash(expected_classified(series, prices))
        run, audit_seconds = execute(database, folder, audit)
        results = weekly.parsed(run.stdout)
        assert_report(results, expected)
        total = results[-1]
        assert total['target_rows'] == sum(row['scored_rows'] for row in accepted_baseline['results'])
        assert Decimal(total['baseline_units']) == sum(Decimal(row['baseline_units']) for row in accepted_baseline['results'])
        for target_key, old_key in [('observed_units', 'observed_units'), ('zero_observed_rows', 'zero_observed_rows'),
                                    ('zero_baseline_rows', 'zero_baseline_rows'), ('missing_price_rows', 'missing_price_target_rows')]:
            assert total[target_key] == sum(row[old_key] for row in accepted_baseline['results'])
        assert total['distinct_series'] == 30490
        after = snapshot('after')
        assert before == after, 'Read-only candidate query changed a scoped input'
        database_bytes = database.stat().st_size
    assert not folder.exists()
    assert all(weekly.sha256(path) == source_hashes[name] for name, path in sources.items())
    assert all(weekly.sha256(root / path) == value for path, value in historical.items())
    assert all(weekly.sha256(root / path) == value for path, value in hashes.items())
    evidence = dict(
        checked_at_utc=datetime.now(timezone.utc).isoformat(), executor='assistant',
        engine=subprocess.check_output([args.duckdb, '-version'], text=True).strip(),
        script=script_path, script_sha256=hashes[script_path], validator=validator_path, validator_sha256=hashes[validator_path],
        protocol=protocol_path, protocol_sha256=PROTOCOL_SHA, original_screening_protocol_sha256=RULES_SHA,
        code_and_dependency_sha256=hashes, settings={'threads': 2, 'memory_limit': '2GB'},
        source_sha256=source_hashes, source_hashes_unchanged=True, source_controls=controls,
        input_window={'start_date': '2016-01-30', 'end_date': '2016-04-22', 'weeks': 12, 'pairs': 30490},
        warmup_window={'first_week': 11601, 'last_week': 11604, 'start_date': '2016-01-30', 'end_date': '2016-02-26'},
        target_window={'first_week': 11605, 'last_week': 11612, 'start_date': '2016-02-27', 'end_date': '2016-04-22', 'weeks': 8, 'target_rows': 243920},
        independent_reference='Original-source csv/Decimal helpers and direct prior-four slices derive all eighteen accepted features. Separate exact Fraction comparisons against the baseline independently classify every target and its integer-scaled difference. All 243,920 twenty-field rows, the accepted eighteen-field fingerprint, and every aggregate field/order compare exactly. Integer quotient/remainder rounding verifies means and shares without coarse tolerance.',
        preflight_strategy='One bounded private database stages only 84 sales columns and twelve price weeks through unchanged SQL09/23/44. Unchanged SQL50 is executed once and reconciled fully. Accepted SQL45–49 SQL/protocol/evidence remain hash-pinned without rerunning their analyses. Historical forecasting/guard suites and learner persistent database are not opened or rerun.',
        weekly_input_rows_compared=row_count, weekly_input_fields_compared=12, weekly_input_exact_mismatches=0,
        weekly_input_rows_sha256=input_hash, accepted_sql44_input_fingerprint_matched=True,
        pooled_rows_compared=pooled_count, pooled_fields_compared=8, pooled_rows_sha256=pooled_hash,
        price_rows_compared=price_count, price_fields_compared=4,
        target_feature_rows_compared=classified_count, target_feature_fields_compared=18,
        target_feature_exact_mismatches=0, target_feature_rows_sha256=feature_hash,
        accepted_sql50_feature_fingerprint_matched=True,
        classified_rows_compared=classified_count, classified_fields_compared=20, classified_exact_mismatches=0,
        classified_rows_sha256=classified_hash, classified_columns=CLASSIFIED_FIELDS,
        classification_rules_verified_against_exact_fraction_reference=True, all_targets_assigned_one_class=True,
        original_screening_rules_unchanged=True, exact_quarter_sums_and_final_rounding_verified=True,
        sql50_rows_reconciled=8, sql50_fields_reconciled=12, sql50_accepted_report_matched=True,
        sql50_input_history_guard_prefix_unchanged=True, total_controls_reconciled_to_sql50=True,
        scoped_input_sha256_before=before, scoped_input_sha256_after=after, scoped_inputs_unchanged=True,
        historical_preflight_files_unchanged=len(historical), temporary_database_removed=True,
        temporary_database_bytes_after_close=database_bytes, fixture_case_count=len(cases), fixture_cases=cases,
        independent_source_read_seconds=reference_seconds, setup_seconds=setup_seconds,
        sql50_reconciliation_seconds=sql50_seconds, classified_export_seconds=classified_seconds, audit_seconds=audit_seconds,
        timing_scope='One-run elapsed seconds; CLI timings exclude hashing/Python comparisons. DuckDB memory_limit is not a total-process cap.',
        report_rows=5, report_columns=12,
        report_sha256=weekly.canonical_hash([[row[key] for key in COLUMNS] for row in results]),
        report_fingerprint_contract='SHA-256 over ordered compact JSON arrays plus LF; counts and observed units are integers, shares are fixed-four-place strings, baseline/difference sums fixed-two-place strings, means fixed-six-place strings or null. Classified rows append integer unit_difference_x4 and class text to the accepted eighteen normalized feature fields.',
        results=results,
        scope='Assistant independent preflight only; learner SQL51 execution pending. Frozen retrospective heuristic review candidates, not verified anomalies, stockouts, lost demand, causal price effects, new forecast errors or detection-performance estimates. All targets, zeros and missing-price context remain included; prior actuals remain in future history. Public evidence contains aggregates and fingerprints only, without candidate identifiers.')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, default=str) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps({'fixture_cases_passed': len(cases), 'weekly_input_rows_compared': row_count,
                      'classified_rows_compared': classified_count, 'audit_seconds': audit_seconds, 'results': results}), flush=True)


if __name__ == '__main__':
    main()
