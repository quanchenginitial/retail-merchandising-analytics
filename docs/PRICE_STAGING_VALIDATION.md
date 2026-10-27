# Price typed staging preflight and precision contract

27 October 2026. The learner has accepted calendar staging. [09_stage_prices.sql](../sql/09_stage_prices.sql) prepares stg.m5_prices; learner execution remains pending.

## Observed source precision

The full source profile found 6,841,121 ordinary positive decimal prices: 624,039 with one fractional digit and 6,217,082 with two, with no higher-precision spellings. The maximum integer length is three digits. These measured facts support DECIMAL(18,2) for this snapshot. The type holds fixed-point decimal values; width is the total digit capacity and scale the fractional digits, as described in [DuckDB 1.5 numeric types](https://duckdb.org/docs/1.5/sql/data_types/numeric).

The [preflight evidence](../data/price_staging_preflight.json) records this complete profile. Formatting as fixed two-decimal text changes 624,039 source spellings, such as 2.0 to 2.00, without changing their values. Raw source text is preserved in raw.m5_prices.

## Conversion and equality contract

Item/store columns remain VARCHAR, wm_yr_wk becomes INTEGER, and sell_price becomes DECIMAL(18,2). Ordinary CREATE TABLE AS SELECT does not overwrite an existing staging table. The week guard accepts five-digit numeric codes with a nonzero first digit. The price guard requires positive, in-range ordinary decimal text with no nonzero digits beyond the second fractional position; extra trailing zeros are allowed. It rejects nonzero sub-cent precision, exponent notation, missing/nonpositive values and overflow before the conversion can round. These are this stage's declared representation requirements, not a universal rule that all other numeric price formats are invalid.

For example, 001.2500 is exactly representable and accepted; 1.2501 is rejected. The type guard is repeated as a diagnostic in the validation query so an existing table cannot conceal a later incompatible raw change. Table key constraints are not yet enforced by DDL; uniqueness and required fields are checked in the result and must pass before proceeding.

Reconciliation compares item/store/week and canonical price text in both directions with EXCEPT ALL. Canonicalisation removes only integer leading zeros and fractional trailing zeros (and omits an empty fractional part). Crucially, raw price text is not first cast to DECIMAL or DOUBLE, so a nonzero sub-cent change is still visible. Equality means exact decimal value equivalence under this explicit policy, including duplicate multiplicity, rather than identical original price spelling. The preceding raw-layer audit separately established literal CSV equality.

The 13 checks verify row count, every column's name/type/order, unique item/store/week keys, required values, positive prices, exact min/max, pair/week counts, raw conversion-contract compliance and both canonical differences. No daily sales-price join or sales-value measure is produced.

## Independent assistant verification

[Preflight runner](../validation/preflight_price_staging.py) imported the full price source into a disposable :memory: database, profiled its precision and executed the unchanged staging SQL. All 13 checks passed with DuckDB v1.5.5. Setup, profiling and validation took 29.825 seconds in this run. The preflight used two threads, a DuckDB memory_limit setting of 3GB and a temporary spill folder under the ignored project tmp directory. This is not a total-process memory bound and does not change the learner's connection. Actual runtime can differ.

Seven targeted cases passed: exact values with format variants; rejection of nonzero sub-cent precision, decimal overflow, NULL price, zero price and a fractional week; and detection by the validation-only query of a raw 2.0001 value after the staging value was already 2.00. Small valid fixtures assert selected diagnostics, not full-source expected totals. These are focused checks, not exhaustive coverage.

The source SHA-256 matched the [registered snapshot](../data/m5_source_audit.json) before execution and remained unchanged afterward. The [recorded evidence](../data/price_staging_preflight.json) includes the SQL fingerprint, precision profile, baseline results and targeted cases. The learner's database was never opened and raw data is not published.

To reproduce from the repository root:

```powershell
python validation/preflight_price_staging.py --duckdb "E:/DuckDB/duckdb.exe" --output "data/price_staging_preflight.json"
```

The production staging script reads raw tables only; the preflight and raw import contain local source paths. Follow [the current step](FIRST_STEP_ZH.md) for learner execution. Sales reshaping, daily price coverage, core dimensions and analytical outputs remain pending.
