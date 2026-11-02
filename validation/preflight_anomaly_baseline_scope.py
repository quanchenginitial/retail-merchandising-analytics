"""Verify prior-four-actual-week scope and exact quarter baselines without calculating flags."""
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
from pathlib import Path

sys.dont_write_bytecode = True
import preflight_item_store_weekly_prices as weekly


COLUMNS = ['retail_week', 'week_start', 'series_count', 'scored_rows', 'history_rows', 'baseline_units',
           'observed_units', 'zero_observed_rows', 'zero_baseline_rows', 'priced_target_rows',
           'missing_price_target_rows', 'check_status']
FEATURE_FIELDS = [*weekly.FIELDS, 'history_rows', 'history_units', 'positive_history_weeks',
                  'first_history_week', 'last_history_week', 'baseline_units']
PROTOCOL_SHA = 'dd2376b370d2350d51d49e20b7ba29254b0fc49215e3c58e79d2d7b4ed4c7b2d'


def expected_features(series, prices):
    for source in sorted(series, key=lambda row: (row['item_id'], row['store_id'])):
        input_rows = list(weekly.expected_rows([source], prices))
        units = [sum(source['days'][7 * offset:7 * offset + 7]) for offset in range(12)]
        for offset in range(4, 12):
            prior = units[offset - 4:offset]
            history_sum = sum(prior)
            yield [*input_rows[offset], len(prior), history_sum, sum(value > 0 for value in prior),
                   11601 + offset - 4, 11601 + offset - 1, format(Decimal(history_sum) / 4, '.2f')]


def reference_report(series, prices):
    groups = {str(week): dict(pairs=set(), rows=0, history_rows=0, history_units=0,
                            units=0, zero_observed=0, zero_baseline=0, priced=0, missing=0)
              for week in range(11605, 11613)}
    for values in expected_features(series, prices):
        row = dict(zip(FEATURE_FIELDS, values))
        group = groups[str(row['wm_yr_wk'])]
        group['pairs'].add((row['item_id'], row['store_id']))
        group['rows'] += 1
        group['history_rows'] += row['history_rows']
        group['history_units'] += row['history_units']
        group['units'] += row['units']
        group['zero_observed'] += row['units'] == 0
        group['zero_baseline'] += row['history_units'] == 0
        group['priced'] += row['has_price']
        group['missing'] += not row['has_price']
    return [dict(zip(COLUMNS, [week, (weekly.START + timedelta(days=7 * (int(week) - 11601))).isoformat(),
        len(group['pairs']), group['rows'], group['history_rows'], format(Decimal(group['history_units']) / 4, '.2f'),
        group['units'], group['zero_observed'], group['zero_baseline'], group['priced'], group['missing'], 'PASS']))
        for week, group in groups.items()]


def assert_report(actual, expected):
    assert len(actual) == 8 and all(list(row) == COLUMNS for row in actual), 'Scope report shape/order mismatch'
    for row in actual:
        for key in COLUMNS[2:-1]:
            value = Decimal(str(row[key]))
            assert value.is_finite()
            if key == 'baseline_units':
                assert value * 4 == int(value * 4), 'Baseline total is not an exact quarter'
                fixed = format(value, '.2f')
                assert value == Decimal(fixed)
                row[key] = fixed
            else:
                assert value == int(value), 'Noninteger scope control'
                row[key] = int(value)
        assert row['series_count'] == row['scored_rows']
        assert row['history_rows'] == 4 * row['scored_rows']
        assert row['priced_target_rows'] + row['missing_price_target_rows'] == row['scored_rows']
    assert actual == expected, 'Scope report differs from independent original-source four-week slices'


def compare_feature_export(path, expected):
    digest = hashlib.sha256()
    count = 0
    with path.open(newline='', encoding='utf-8') as stream:
        reader = csv.DictReader(stream)
        assert reader.fieldnames == FEATURE_FIELDS, 'Unexpected feature schema/order'
        for reference in expected:
            row = next(reader, None)
            assert row is not None, 'Feature extract ended before reference'
            normalized = weekly.normalize_export({key: row[key] for key in weekly.FIELDS})
            normalized += [int(row[key]) for key in FEATURE_FIELDS[12:-1]]
            baseline = Decimal(row['baseline_units'])
            assert baseline * 4 == int(baseline * 4)
            normalized.append(format(baseline, '.2f'))
            assert normalized == reference, 'Exact rolling feature field comparison failed'
            digest.update((json.dumps(normalized, ensure_ascii=True, separators=(',', ':')) + '\n').encode())
            count += 1
        assert next(reader, None) is None, 'Feature extract contains extra rows'
    return count, digest.hexdigest()


def fixture():
    setup, series, _ = weekly.fixture(all_zero=True)
    setup += 'DELETE FROM stg.m5_prices;\n'
    prices = {}
    for row in series:
        pair = row['item_id'], row['store_id']
        units = [0] * 12
        if pair == ('P1', 'S1'):
            units = [1, 2, 3, 5, 100, 0, 7, 8, 9, 10, 11, 999]
        elif pair == ('P1', 'S2'):
            units = [10] * 12
        elif pair == ('P2', 'S1'):
            units = [0, 0, 0, 0, 7, 0, 0, 0, 0, 0, 0, 0]
        row['days'] = [value if day == 0 else 0 for value in units for day in range(7)]
        for offset, value in enumerate(units):
            if value:
                setup += (f'UPDATE mart.m5_sales_daily SET units={value} WHERE item_id={weekly.quote(pair[0])}'
                          f' AND store_id={weekly.quote(pair[1])} AND d={weekly.quote("d_" + str(1828 + 7 * offset))};\n')
            if pair == ('P3', 'S1'):
                continue  # Valid unpriced zero targets remain in the baseline roster.
            prices[(*pair, 11601 + offset)] = Decimal(100 * int(row['store_id'][1:])) / 100
    price_values = ','.join(f'({weekly.quote(store)},{weekly.quote(item)},{week},{price})'
                          for (item, store, week), price in prices.items())
    setup += 'INSERT INTO stg.m5_prices VALUES ' + price_values + ';\n'
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
    script_path = 'sql/50_audit_anomaly_baseline_scope.sql'
    validator_path = 'validation/preflight_anomaly_baseline_scope.py'
    protocol_path = 'docs/ANOMALY_SCREENING_PROTOCOL.md'
    sql_paths = {'09': 'sql/09_stage_prices.sql', '23': 'sql/23_build_product_weekly.sql',
                 '44': 'sql/44_build_item_store_weekly_prices.sql', '45': 'sql/45_audit_price_variation.sql',
                 '46': 'sql/46_price_sales_association.sql', '47': 'sql/47_weekly_price_sales_association.sql',
                 '48': 'sql/48_department_price_sales_association.sql', '49': 'sql/49_week_department_price_contrasts.sql'}
    prior_evidence = ['data/item_store_weekly_prices_preflight.json', 'data/price_variation_preflight.json',
                      'data/price_sales_association_preflight.json', 'data/weekly_price_sales_association_preflight.json',
                      'data/department_price_sales_association_preflight.json', 'data/week_department_price_contrasts_preflight.json']
    paths = [script_path, validator_path, protocol_path, *sql_paths.values(), *prior_evidence,
             'validation/preflight_item_store_weekly_prices.py', 'docs/ITEM_STORE_WEEKLY_PRICES_PROTOCOL.md',
             'docs/PRICE_VARIATION_PROTOCOL.md', 'docs/PRICE_SALES_ASSOCIATION_PROTOCOL.md',
             'docs/WEEKLY_PRICE_SALES_ASSOCIATION_PROTOCOL.md', 'docs/DEPARTMENT_PRICE_SALES_ASSOCIATION_PROTOCOL.md',
             'docs/WEEK_DEPARTMENT_PRICE_CONTRASTS_PROTOCOL.md']
    hashes = {path: weekly.sha256(root / path) for path in paths}
    assert hashes[protocol_path] == PROTOCOL_SHA, 'Frozen screening protocol changed'
    audit = (root / script_path).read_text(encoding='utf-8')
    scripts = {key: (root / path).read_text(encoding='utf-8') for key, path in sql_paths.items()}
    prefix = lambda sql, boundary: sql[sql.index('WITH parameters AS ('):sql.index(boundary)]
    assert prefix(audit, '), history AS MATERIALIZED (') == prefix(scripts['48'], '), lagged AS MATERIALIZED ('), 'Accepted input guard prefix changed'
    feature_sql = audit[:audit.rindex('\nSELECT CAST(r.wm_yr_wk')] + '\nSELECT ' + ','.join('f.' + key for key in FEATURE_FIELDS) + """
FROM input_health i CROSS JOIN history_health h CROSS JOIN report_health c
LEFT JOIN features f ON true
WHERE CASE WHEN COALESCE(i.passed AND h.passed AND c.passed,false) THEN true
           ELSE error('Anomaly baseline private features blocked') END
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
    expected = reference_report(series, prices)
    features = list(expected_features(series, prices))
    first_pair = [dict(zip(FEATURE_FIELDS, row)) for row in features if row[:2] == ['P1', 'S1']]
    assert [row['history_units'] for row in first_pair] == [11, 110, 108, 112, 115, 24, 34, 38]
    assert first_pair[0]['baseline_units'] == '2.75' and first_pair[0]['units'] == 100
    assert first_pair[-1]['baseline_units'] == '9.50' and first_pair[-1]['units'] == 999
    assert first_pair[1]['history_units'] == 110  # Previous actual jump remains; current zero is excluded.
    zero_pair = [dict(zip(FEATURE_FIELDS, row)) for row in features if row[:2] == ['P2', 'S1']]
    assert zero_pair[0]['baseline_units'] == '0.00' and zero_pair[0]['units'] == 7
    assert zero_pair[1]['history_units'] == 7 and zero_pair[4]['history_units'] == 7 and zero_pair[5]['history_units'] == 0
    assert all(row['missing_price_target_rows'] == 1 for row in expected)
    expected_units = sum(sum(row['days']) for row in series)
    transform = lambda sql: sql.replace('3049 AS expected_items,10 AS expected_stores',
                                        '3 AS expected_items,2 AS expected_stores').replace(
                                            '3536539 AS expected_units', f'{expected_units} AS expected_units')
    cases = []
    with tempfile.TemporaryDirectory(prefix='baseline-scope-case-', dir=tmp_root) as temp:
        folder = Path(temp)
        database = folder / 'case.duckdb'
        execute(database, folder, setup + transform(builds['23']) + transform(builds['44']))
        run, _ = execute(database, folder, transform(audit))
        assert_report(weekly.parsed(run.stdout), expected)
        feature_export = folder / 'features.csv'
        execute(database, folder, f'COPY ({transform(feature_sql)}) TO {weekly.quote(feature_export.as_posix())} (HEADER,FORMAT CSV);')
        count, fingerprint = compare_feature_export(feature_export, iter(features))
        assert count == 48 and fingerprint == weekly.canonical_hash(features)
        cases.append(dict(case='prior_four_actual_slices_exact_quarters_zero_histories_current_future_exclusion_store_separation_missing_prices', passed=True))
        rejected, _ = execute(database, folder, 'DELETE FROM core.m5_calendar;\n' + transform(audit), allow_error=True)
        assert rejected.returncode != 0 and 'Anomaly baseline scope blocked' in rejected.stderr
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
    expected = reference_report(series, prices)
    accepted_weekly = json.loads((root / prior_evidence[0]).read_text(encoding='utf-8'))
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
    with tempfile.TemporaryDirectory(prefix='anomaly-baseline-scope-', dir=tmp_root) as temp:
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
        feature_export = folder / 'target_features.csv'
        _, feature_seconds = execute(database, folder,
            f'COPY ({feature_sql}) TO {weekly.quote(feature_export.as_posix())} (HEADER,FORMAT CSV);')
        feature_count, feature_hash = compare_feature_export(feature_export, expected_features(series, prices))
        assert feature_count == 243920 and feature_hash == weekly.canonical_hash(expected_features(series, prices))
        run, audit_seconds = execute(database, folder, audit)
        results = weekly.parsed(run.stdout)
        assert_report(results, expected)
        accepted_units = {row['retail_week']: row['units'] for row in accepted_weekly['results']}
        assert all(row['observed_units'] == accepted_units[row['retail_week']] for row in results)
        after = snapshot('after')
        assert before == after, 'Read-only scope audit changed a scoped input'
        database_bytes = database.stat().st_size
    assert not folder.exists()
    assert all(weekly.sha256(path) == source_hashes[name] for name, path in sources.items())
    assert all(weekly.sha256(root / path) == value for path, value in historical.items())
    assert all(weekly.sha256(root / path) == value for path, value in hashes.items())
    evidence = dict(
        checked_at_utc=datetime.now(timezone.utc).isoformat(), executor='assistant',
        engine=subprocess.check_output([args.duckdb, '-version'], text=True).strip(),
        script=script_path, script_sha256=hashes[script_path], validator=validator_path, validator_sha256=hashes[validator_path],
        protocol=protocol_path, protocol_sha256=PROTOCOL_SHA, code_and_dependency_sha256=hashes,
        settings={'threads': 2, 'memory_limit': '2GB'}, source_sha256=source_hashes,
        source_hashes_unchanged=True, source_controls=controls,
        input_window={'start_date': '2016-01-30', 'end_date': '2016-04-22', 'weeks': 12, 'pairs': 30490},
        warmup_window={'first_week': 11601, 'last_week': 11604, 'start_date': '2016-01-30', 'end_date': '2016-02-26'},
        target_window={'first_week': 11605, 'last_week': 11612, 'start_date': '2016-02-27', 'end_date': '2016-04-22', 'weeks': 8, 'target_rows': 243920},
        independent_reference='Original-source csv/Decimal helpers derive every accepted weekly field. Direct slices of each pair\'s four immediately prior actual weekly unit values independently derive all 243,920 target features across eighteen fields, including history bounds/count/sum, positive-week count and exact quarter baseline. Every displayed scope field/order is compared; no flags or candidate counts are calculated.',
        preflight_strategy='One bounded private database stages only 84 sales columns and twelve price weeks through unchanged SQL09/23/44. Exact accepted weekly input fingerprint and original-source rows establish this branch. Accepted SQL45–49 SQL/protocol/evidence hashes remain unchanged; their descriptive reports and all historical forecasting/guard suites are not rerun. Learner persistent database is never opened.',
        weekly_input_rows_compared=row_count, weekly_input_fields_compared=12, weekly_input_exact_mismatches=0,
        weekly_input_rows_sha256=input_hash, accepted_sql44_input_fingerprint_matched=True,
        pooled_rows_compared=pooled_count, pooled_fields_compared=8, pooled_rows_sha256=pooled_hash,
        price_rows_compared=price_count, price_fields_compared=4,
        target_feature_rows_compared=feature_count, target_feature_fields_compared=18,
        target_feature_exact_mismatches=0, target_feature_rows_sha256=feature_hash,
        target_feature_columns=FEATURE_FIELDS, exact_quarter_baselines_verified=True,
        current_future_units_excluded_from_history_verified=True, actual_prior_zero_weeks_retained=True,
        sql44_target_week_unit_totals_reconciled=True, sql48_accepted_input_guard_prefix_unchanged=True,
        future_flag_rules_evaluated=False, candidate_counts_computed=False,
        scoped_input_sha256_before=before, scoped_input_sha256_after=after, scoped_inputs_unchanged=True,
        historical_preflight_files_unchanged=len(historical), temporary_database_removed=True,
        temporary_database_bytes_after_close=database_bytes, fixture_case_count=len(cases), fixture_cases=cases,
        independent_source_read_seconds=reference_seconds, setup_seconds=setup_seconds,
        target_feature_export_seconds=feature_seconds, audit_seconds=audit_seconds,
        timing_scope='One-run elapsed seconds; CLI timings exclude hashing/Python comparisons. DuckDB memory_limit is not a total-process cap.',
        report_rows=8, report_columns=12,
        report_sha256=weekly.canonical_hash([[row[key] for key in COLUMNS] for row in results]),
        report_fingerprint_contract='SHA-256 over ordered compact JSON arrays plus LF; counts and observed units are integers, week identifiers and dates are strings, baseline_units is a fixed-two-place string. Private feature hashes use normalized input fields, integer history fields and a fixed-two-place baseline.',
        results=results,
        scope='Assistant independent preflight only; learner SQL50 execution pending. Prior-four-actual-week retrospective baseline scope only. Scored rows are target positions; no anomaly score, flag or candidate count is computed. Future SQL51 rules are frozen in the protocol but unimplemented. Zeros and missing-price context are retained. No new forecast evaluation, true-anomaly, stockout, lost-demand, price-causality or performance claim. Public evidence contains aggregates and fingerprints only.')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, default=str) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps({'fixture_cases_passed': len(cases), 'weekly_input_rows_compared': row_count,
                      'target_feature_rows_compared': feature_count, 'audit_seconds': audit_seconds, 'results': results}), flush=True)


if __name__ == '__main__':
    main()
