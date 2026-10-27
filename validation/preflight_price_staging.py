"""Profile real price precision, preflight staging and test conversion guards.

Only disposable in-memory databases are used. Never opens the learner database.
"""
import argparse
import hashlib
import json
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path


def sha256(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def json_results(text):
    results, decoder = [], json.JSONDecoder()
    remaining = text.strip()
    while remaining:
        value, end = decoder.raw_decode(remaining)
        results.append(value)
        remaining = remaining[end:].strip()
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--duckdb', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    sql_path = root / 'sql/09_stage_prices.sql'
    sql = sql_path.read_text(encoding='utf-8')
    source = Path('D:/database/m5-forecasting-accuracy/sell_prices.csv')
    registry = json.loads((root / 'data/m5_source_audit.json').read_text(encoding='utf-8'))
    source_hash = sha256(source)
    assert source_hash == registry['files'][source.name]['sha256']
    setup = (root / 'sql/06_import_prices.sql').read_text(encoding='utf-8').split('-- BASIC CHECKS:')[0]
    profile_sql = """
    SELECT COUNT(*) AS row_count,
      COUNT(*) FILTER (WHERE NOT COALESCE(regexp_full_match(sell_price,'[0-9]+([.][0-9]+)?'),false)) AS non_plain_decimal_rows,
      MAX(length(split_part(sell_price,'.',1))) AS max_integer_digits,
      MAX(length(split_part(sell_price,'.',2))) AS max_fraction_digits,
      COUNT(*) FILTER (WHERE length(split_part(sell_price,'.',2))=1) AS one_decimal_rows,
      COUNT(*) FILTER (WHERE length(split_part(sell_price,'.',2))=2) AS two_decimal_rows,
      COUNT(*) FILTER (WHERE length(split_part(sell_price,'.',2))>2) AS more_than_two_decimal_rows,
      COUNT(*) FILTER (WHERE sell_price IS DISTINCT FROM CAST(TRY_CAST(sell_price AS DECIMAL(18,2)) AS VARCHAR)) AS fixed_scale_text_differences
    FROM raw.m5_prices;
    """
    tmp_root = root / 'tmp'
    tmp_root.mkdir(exist_ok=True)

    def run_sql(script):
        with tempfile.TemporaryDirectory(prefix='price-stage-', dir=tmp_root) as spill:
            assert Path(spill).resolve().is_relative_to(tmp_root.resolve())
            spill_sql = Path(spill).as_posix().replace("'", "''")
            settings = f"SET threads=2; SET memory_limit='3GB'; SET temp_directory='{spill_sql}';\n"
            started = time.perf_counter()
            result = subprocess.run([args.duckdb, ':memory:', '-bail', '-json'],
                                    input=settings + script, text=True, encoding='utf-8', capture_output=True)
            return result, round(time.perf_counter() - started, 3)

    run, elapsed = run_sql(setup + profile_sql + sql)
    assert run.returncode == 0, run.stderr
    profile_result, baseline = json_results(run.stdout)
    profile = profile_result[0]
    assert profile == {'row_count': 6841121, 'non_plain_decimal_rows': 0, 'max_integer_digits': 3,
                       'max_fraction_digits': 2, 'one_decimal_rows': 624039, 'two_decimal_rows': 6217082,
                       'more_than_two_decimal_rows': 0, 'fixed_scale_text_differences': 624039}, profile
    assert len(baseline) == 13 and all(row['status'] == 'PASS' for row in baseline), baseline
    assert sha256(source) == source_hash
    print(json.dumps({'baseline_checks_passed': 13, 'baseline_seconds': elapsed}), flush=True)
    fixture = """
    CREATE SCHEMA raw;
    CREATE TABLE raw.m5_prices AS SELECT * FROM (VALUES
      ('S','A','11101','2.0'), ('S','A','11102','001.2500'), ('S','B','11101','0.01')
    ) AS p(store_id,item_id,wm_yr_wk,sell_price);
    """
    good, _ = run_sql(fixture + sql)
    assert good.returncode == 0, good.stderr
    tiny = {row['check_name']: row['actual'] for row in json_results(good.stdout)[0]}
    for key, value in {'schema_mismatch_count': '0', 'raw_contract_violation_rows': '0',
                       'raw_canonical_only_rows': '0', 'staging_canonical_only_rows': '0'}.items():
        assert tiny[key] == value, (key, tiny[key])
    cases = [{'case': 'exact_values_with_format_variants', 'passed': True,
              'checked_actuals': {k: tiny[k] for k in ('schema_mismatch_count','raw_canonical_only_rows','staging_canonical_only_rows')}}]
    rejected = [
        ('nonzero_subcent_precision', "UPDATE raw.m5_prices SET sell_price='1.2501' WHERE item_id='B';", 'Raw price'),
        ('decimal_overflow', "UPDATE raw.m5_prices SET sell_price='10000000000000000.00' WHERE item_id='B';", 'Raw price'),
        ('missing_price', "UPDATE raw.m5_prices SET sell_price=NULL WHERE item_id='B';", 'Raw price'),
        ('nonpositive_price', "UPDATE raw.m5_prices SET sell_price='0' WHERE item_id='B';", 'Raw price'),
        ('fractional_week', "UPDATE raw.m5_prices SET wm_yr_wk='11101.5' WHERE item_id='B';", 'Raw week'),
    ]
    for name, mutation, message in rejected:
        failed, _ = run_sql(fixture + mutation + sql)
        assert failed.returncode != 0 and message in failed.stderr, (name, failed.stderr)
        cases.append({'case': name, 'passed': True, 'conversion_rejected': True})
    # This changed raw value violates the contract and would round to 2.00.
    # Running only validation must still expose the difference without decimal-casting raw text.
    create_part, validation = sql.split('-- VALIDATION:', 1)
    validation = validation.split('\n', 1)[1]
    changed, _ = run_sql(fixture + create_part + "UPDATE raw.m5_prices SET sell_price='2.0001' WHERE item_id='A' AND wm_yr_wk='11101';\n" + validation)
    assert changed.returncode == 0, changed.stderr
    actual = {row['check_name']: row['actual'] for row in json_results(changed.stdout)[0]}
    assert all(actual[k] == '1' for k in ('raw_contract_violation_rows','raw_canonical_only_rows','staging_canonical_only_rows')), actual
    cases.append({'case': 'validation_detects_subcent_change', 'passed': True,
                  'checked_actuals': {k: actual[k] for k in ('raw_contract_violation_rows','raw_canonical_only_rows','staging_canonical_only_rows')}})
    report = {
        'checked_at_utc': datetime.now(timezone.utc).isoformat(), 'executor': 'assistant',
        'engine': subprocess.check_output([args.duckdb, '-version'], text=True).strip(),
        'database': ':memory:', 'settings': {'threads': 2, 'memory_limit': '3GB'},
        'script': 'sql/09_stage_prices.sql', 'script_sha256': sha256(sql_path),
        'source_file': source.name, 'source_sha256': source_hash, 'source_hash_unchanged': True,
        'precision_profile': profile, 'baseline_setup_profile_and_checks_seconds': elapsed,
        'checks_passed': 13, 'results': baseline, 'fixture_cases_passed': len(cases), 'fixture_cases': cases,
        'scope': 'Assistant price staging preflight only. Exact decimal value equality under documented text canonicalisation; not raw spelling equality or daily price coverage. Learner staging remains pending.',
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'checks_passed': 13, 'fixture_cases_passed': len(cases)}))


if __name__ == '__main__':
    main()
