"""Verify weekly allocation of frozen retrospective candidates without retuning their rules."""
import argparse
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
import preflight_anomaly_candidates as candidates


COLUMNS = ['retail_week', 'week_start', 'target_rows', 'sudden_zero_rows', 'large_increase_rows',
           'large_decrease_rows', 'none_rows', 'candidate_rows', 'candidate_share_pct',
           'upward_gap_units', 'downward_gap_units', 'check_status']
CLASSIFIED_FIELDS = candidates.CLASSIFIED_FIELDS
PROTOCOL_SHA = '9ccae37df71d05f511bcac186cfd41dcd37b543c1d8086b363b4d0e33a51bf56'
RULES_SHA = candidates.RULES_SHA
FROZEN_CLASSIFIED_SHA = '901d908b825f192b0dd1a7baabfe9ad38cdf96add65f7fa891b7aa15dea85e31'
FROZEN_FEATURE_SHA = '556c07cf090b18fc6d60c00770b524d2d71464d3aece8968c438fea0c558c38f'


def reference_report(rows):
    groups = {str(week): dict(targets=0, classes={label: 0 for label in candidates.CLASSES[:-1]}, up_x4=0, down_x4=0)
              for week in range(11605, 11613)}
    for values in rows:
        row = dict(zip(CLASSIFIED_FIELDS, values))
        group = groups[str(row['wm_yr_wk'])]
        group['targets'] += 1
        group['classes'][row['candidate_class']] += 1
        if row['candidate_class'] == 'LARGE_INCREASE':
            group['up_x4'] += row['unit_difference_x4']
        elif row['candidate_class'] in ['SUDDEN_ZERO', 'LARGE_DECREASE']:
            group['down_x4'] -= row['unit_difference_x4']
    result = []
    for week, group in groups.items():
        counts = group['classes']
        count = sum(counts[label] for label in candidates.CLASSES[:3])
        assert group['targets'] > 0 and group['up_x4'] >= 0 and group['down_x4'] >= 0
        result.append(dict(zip(COLUMNS, [week, (weekly.START + timedelta(days=7 * (int(week) - 11601))).isoformat(),
            group['targets'], counts['SUDDEN_ZERO'], counts['LARGE_INCREASE'], counts['LARGE_DECREASE'], counts['NONE'],
            count, candidates.fixed_fraction(Fraction(100 * count, group['targets']), 4),
            candidates.fixed_fraction(Fraction(group['up_x4'], 4), 2),
            candidates.fixed_fraction(Fraction(group['down_x4'], 4), 2), 'PASS'])))
    return result


def assert_report(actual, expected):
    assert len(actual) == 8 and all(list(row) == COLUMNS for row in actual), 'Weekly triage shape/order mismatch'
    for row in actual:
        for key in COLUMNS[2:-1]:
            value = Decimal(str(row[key]))
            assert value.is_finite()
            if key in ['candidate_share_pct', 'upward_gap_units', 'downward_gap_units']:
                places = 4 if key == 'candidate_share_pct' else 2
                fixed = candidates.fixed_fraction(Fraction(value), places)
                assert value == Decimal(fixed)
                if places == 2:
                    assert value >= 0 and value * 4 == int(value * 4)
                row[key] = fixed
            else:
                assert value == int(value)
                row[key] = int(value)
        assert row['candidate_rows'] == row['sudden_zero_rows'] + row['large_increase_rows'] + row['large_decrease_rows']
        assert row['candidate_rows'] + row['none_rows'] == row['target_rows']
    assert actual == expected, 'Weekly triage differs from independent source target allocation'


def reconcile_report(report, aggregate, baseline_report):
    classes = {row['candidate_class']: row for row in aggregate}
    for key, label in [('sudden_zero_rows', 'SUDDEN_ZERO'), ('large_increase_rows', 'LARGE_INCREASE'),
                       ('large_decrease_rows', 'LARGE_DECREASE'), ('none_rows', 'NONE'), ('target_rows', 'TOTAL')]:
        assert sum(row[key] for row in report) == classes[label]['target_rows']
    assert sum(Decimal(row['upward_gap_units']) for row in report) == Decimal(classes['LARGE_INCREASE']['unit_difference'])
    assert sum(Decimal(row['downward_gap_units']) for row in report) == -sum(
        Decimal(classes[label]['unit_difference']) for label in ['SUDDEN_ZERO', 'LARGE_DECREASE'])
    known_targets = {row['retail_week']: row['scored_rows'] for row in baseline_report}
    assert all(row['target_rows'] == known_targets[row['retail_week']] for row in report)


def fixture():
    profiles = [[7, 8, 8, 8] + [0] * 8, [1, 2, 3, 5, 10] + [0] * 7,
                [14, 14, 14, 14, 14] + [7] * 7, [0] * 12]
    series, prices = [], {}
    for item, units in enumerate(profiles, start=1):
        row = dict(item_id=f'P{item}', store_id='S1', dept_id='FOODS_1', cat_id='FOODS', state_id='CA',
                   days=[value if day == 0 else 0 for value in units for day in range(7)])
        series.append(row)
        if item != 4:
            for offset in range(12):
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
    script_path = 'sql/52_weekly_anomaly_triage.sql'
    validator_path = 'validation/preflight_weekly_anomaly_triage.py'
    protocol_path = 'docs/WEEKLY_ANOMALY_TRIAGE_PROTOCOL.md'
    sql_paths = {'09': 'sql/09_stage_prices.sql', '23': 'sql/23_build_product_weekly.sql',
                 '44': 'sql/44_build_item_store_weekly_prices.sql', '45': 'sql/45_audit_price_variation.sql',
                 '46': 'sql/46_price_sales_association.sql', '47': 'sql/47_weekly_price_sales_association.sql',
                 '48': 'sql/48_department_price_sales_association.sql', '49': 'sql/49_week_department_price_contrasts.sql', '50': 'sql/50_audit_anomaly_baseline_scope.sql', '51': 'sql/51_screen_anomaly_candidates.sql'}
    prior_evidence = ['data/item_store_weekly_prices_preflight.json', 'data/price_variation_preflight.json',
                      'data/price_sales_association_preflight.json', 'data/weekly_price_sales_association_preflight.json',
                      'data/department_price_sales_association_preflight.json', 'data/week_department_price_contrasts_preflight.json',
                      'data/anomaly_baseline_scope_preflight.json', 'data/anomaly_candidates_preflight.json']
    paths = [script_path, validator_path, protocol_path, *sql_paths.values(), *prior_evidence,
             'validation/preflight_item_store_weekly_prices.py', 'validation/preflight_anomaly_baseline_scope.py', 'validation/preflight_anomaly_candidates.py',
             'docs/ANOMALY_CANDIDATES_PROTOCOL.md', 'data/anomaly_candidates_learner_acceptance.json', 'docs/ANOMALY_CANDIDATES_VALIDATION.md', 'docs/ANOMALY_SCREENING_PROTOCOL.md', 'docs/ITEM_STORE_WEEKLY_PRICES_PROTOCOL.md',
             'docs/PRICE_VARIATION_PROTOCOL.md', 'docs/PRICE_SALES_ASSOCIATION_PROTOCOL.md',
             'docs/WEEKLY_PRICE_SALES_ASSOCIATION_PROTOCOL.md', 'docs/DEPARTMENT_PRICE_SALES_ASSOCIATION_PROTOCOL.md',
             'docs/WEEK_DEPARTMENT_PRICE_CONTRASTS_PROTOCOL.md']
    hashes = {path: weekly.sha256(root / path) for path in paths}
    assert hashes[protocol_path] == PROTOCOL_SHA, 'Frozen candidate report protocol changed'
    assert hashes['docs/ANOMALY_SCREENING_PROTOCOL.md'] == RULES_SHA, 'Already-frozen screening rules changed'
    audit = (root / script_path).read_text(encoding='utf-8')
    scripts = {key: (root / path).read_text(encoding='utf-8') for key, path in sql_paths.items()}
    prefix = lambda sql, boundary: sql[sql.index('WITH parameters AS ('):sql.index(boundary)]
    assert prefix(audit, '), target_weeks AS (') == prefix(scripts['51'], '), categories('), 'Accepted input guard prefix changed'
    classified_sql = audit[:audit.rindex('\nSELECT CAST(r.wm_yr_wk')] + '\nSELECT ' + ','.join('f.' + key for key in CLASSIFIED_FIELDS) + """
FROM input_health i CROSS JOIN history_health h CROSS JOIN report_health c
LEFT JOIN classified f ON true
WHERE CASE WHEN COALESCE(i.passed AND h.passed AND c.passed,false) THEN true
           ELSE error('Weekly triage private classifications blocked') END
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

    setup, series, prices = fixture()
    classified = list(candidates.expected_classified(series, prices))
    expected = reference_report(iter(classified))
    aggregate = candidates.summarize_classified(iter(classified))
    reconcile_report(expected, aggregate, baseline.reference_report(series, prices))
    assert [expected[0][key] for key in COLUMNS[2:-1]] == [4, 1, 1, 0, 2, 2, '50.0000', '7.25', '7.75']
    assert [expected[1][key] for key in COLUMNS[2:-1]] == [4, 0, 0, 1, 3, 1, '25.0000', '0.00', '7.00']
    assert all(row['candidate_rows'] == 0 and row['none_rows'] == 4 and row['candidate_share_pct'] == '0.0000'
               and row['upward_gap_units'] == row['downward_gap_units'] == '0.00' for row in expected[2:])
    assert sum(not row[11] for row in classified) == 8  # Unpriced zero targets stay in every week's denominator.
    expected_units = sum(sum(row['days']) for row in series)
    transform = lambda sql: sql.replace('3049 AS expected_items,10 AS expected_stores',
                                        '4 AS expected_items,1 AS expected_stores').replace(
                                            '3536539 AS expected_units', f'{expected_units} AS expected_units')
    cases = []
    with tempfile.TemporaryDirectory(prefix='weekly-triage-case-', dir=tmp_root) as temp:
        folder = Path(temp)
        database = folder / 'case.duckdb'
        execute(database, folder, setup + transform(builds['23']) + transform(builds['44']))
        run, _ = execute(database, folder, transform(audit))
        assert_report(weekly.parsed(run.stdout), expected)
        export = folder / 'classified.csv'
        execute(database, folder, f'COPY ({transform(classified_sql)}) TO {weekly.quote(export.as_posix())} (HEADER,FORMAT CSV);')
        count, feature_hash, classified_hash = candidates.compare_classified_export(export, iter(classified))
        assert count == 32 and feature_hash == weekly.canonical_hash(baseline.expected_features(series, prices))
        assert classified_hash == weekly.canonical_hash(classified)
        cases.append(dict(case='weekly_allocation_all_target_denominator_zero_candidate_weeks_exact_quarter_gap_signs_missing_zeros', passed=True))
        rejected, _ = execute(database, folder, 'DELETE FROM core.m5_calendar;\n' + transform(audit), allow_error=True)
        assert rejected.returncode != 0 and 'Weekly anomaly triage blocked' in rejected.stderr
        cases.append(dict(case='empty_calendar_intended_rejection', passed=True, expected_rejection=True))
    assert not folder.exists()
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
    expected = reference_report(candidates.expected_classified(series, prices))
    accepted_weekly = json.loads((root / prior_evidence[0]).read_text(encoding='utf-8'))
    accepted_baseline = json.loads((root / 'data/anomaly_baseline_scope_preflight.json').read_text(encoding='utf-8'))
    accepted_candidates = json.loads((root / 'data/anomaly_candidates_preflight.json').read_text(encoding='utf-8'))
    candidates.assert_report(candidates.summarize_classified(candidates.expected_classified(series, prices)), accepted_candidates['results'])
    reconcile_report(expected, accepted_candidates['results'], accepted_baseline['results'])
    assert accepted_candidates['classified_rows_sha256'] == FROZEN_CLASSIFIED_SHA
    assert accepted_baseline['target_feature_rows_sha256'] == FROZEN_FEATURE_SHA

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
    with tempfile.TemporaryDirectory(prefix='weekly-anomaly-triage-', dir=tmp_root) as temp:
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
        export = folder / 'classified_targets.csv'
        _, classified_seconds = execute(database, folder,
            f'COPY ({classified_sql}) TO {weekly.quote(export.as_posix())} (HEADER,FORMAT CSV);')
        classified_count, feature_hash, classified_hash = candidates.compare_classified_export(export, candidates.expected_classified(series, prices))
        assert classified_count == 243920 and feature_hash == FROZEN_FEATURE_SHA
        assert classified_hash == FROZEN_CLASSIFIED_SHA, 'Accepted SQL51 classification fingerprint changed'
        run, audit_seconds = execute(database, folder, audit)
        results = weekly.parsed(run.stdout)
        assert_report(results, expected)
        reconcile_report(results, accepted_candidates['results'], accepted_baseline['results'])
        after = snapshot('after')
        assert before == after, 'Read-only weekly triage changed a scoped input'
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
        target_window={'first_week': 11605, 'last_week': 11612, 'start_date': '2016-02-27', 'end_date': '2016-04-22', 'weeks': 8, 'target_rows': 243920},
        independent_reference='Original-source prior-four slices and exact reference rules reproduce every accepted twenty-field classification and embedded eighteen-field feature. An independent current-week bucket accumulates all four class counts and exact signed integer differences before quarter-unit formatting; Fraction arithmetic rounds all-target shares. Every eight-row/twelve-field report value and order compares exactly.',
        preflight_strategy='One bounded private database stages only 84 sales columns and twelve price weeks through unchanged SQL09/23/44. Accepted SQL51 classification fingerprint and complete independently reconstructed five-row report establish this weekly allocation. Older descriptive/forecast queries and SQL51 boundary suites are not rerun; learner persistent database is never opened.',
        weekly_input_rows_compared=row_count, weekly_input_fields_compared=12, weekly_input_exact_mismatches=0,
        weekly_input_rows_sha256=input_hash, accepted_sql44_input_fingerprint_matched=True,
        pooled_rows_compared=pooled_count, pooled_fields_compared=8, pooled_rows_sha256=pooled_hash,
        price_rows_compared=price_count, price_fields_compared=4,
        target_feature_rows_compared=classified_count, target_feature_fields_compared=18,
        target_feature_exact_mismatches=0, target_feature_rows_sha256=feature_hash,
        accepted_sql50_feature_fingerprint_matched=True,
        classified_rows_compared=classified_count, classified_fields_compared=20, classified_exact_mismatches=0,
        classified_rows_sha256=classified_hash, classified_columns=CLASSIFIED_FIELDS,
        accepted_sql51_classified_fingerprint_matched=True, sql51_input_history_classification_prefix_unchanged=True,
        sql51_rows_reconciled=5, sql51_fields_reconciled=12, sql51_accepted_report_matched=True,
        sql51_reconciliation_method='Full original-source reference report plus exact accepted classified fingerprint; SQL51 query and boundary suite not rerun.',
        sql50_weekly_target_counts_reconciled=True, weekly_class_counts_reconciled_to_sql51=True,
        weekly_directional_gap_sums_reconciled_to_sql51=True, exact_quarter_gaps_and_all_target_denominator_verified=True,
        scoped_input_sha256_before=before, scoped_input_sha256_after=after, scoped_inputs_unchanged=True,
        historical_preflight_files_unchanged=len(historical), temporary_database_removed=True,
        temporary_database_bytes_after_close=database_bytes, fixture_case_count=len(cases), fixture_cases=cases,
        independent_source_read_seconds=reference_seconds, setup_seconds=setup_seconds,
        classified_export_seconds=classified_seconds, audit_seconds=audit_seconds,
        timing_scope='One-run elapsed seconds; CLI timings exclude hashing/Python comparisons. DuckDB memory_limit is not a total-process cap.',
        report_rows=8, report_columns=12,
        report_sha256=weekly.canonical_hash([[row[key] for key in COLUMNS] for row in results]),
        report_fingerprint_contract='SHA-256 over ordered compact JSON arrays plus LF; counts are integers, week identifiers/ISO dates strings, candidate share fixed-four-place string and nonnegative upward/downward gaps fixed-two-place quarter-unit strings.',
        results=results,
        scope='Assistant independent preflight only; learner SQL52 execution pending. Weekly overview of unchanged heuristic review candidates, not verified anomalies, independent incidents, stockouts, lost sales, causal price effects or detection-performance estimates. Directional gaps cover only the three candidate classes and exclude NONE; they are historical-baseline unit differences, not financial losses. Public evidence contains aggregates and fingerprints only.')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, default=str) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps({'fixture_cases_passed': len(cases), 'weekly_input_rows_compared': row_count,
                      'classified_rows_compared': classified_count, 'audit_seconds': audit_seconds, 'results': results}), flush=True)


if __name__ == '__main__':
    main()
