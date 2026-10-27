# Price-value audit and source reconciliation

27 October 2026. The learner has completed price raw import and supplied all 12 basic checks with status PASS. The [acceptance transcription](../data/price_import_learner_acceptance.json) records that screenshot. The subsequent learner screenshot shows all 15 detailed audit checks with status PASS, including both exact source differences at zero. The [detailed acceptance transcription](../data/price_audit_learner_acceptance.json) records these displayed results. This is learner-provided evidence, not a new direct database read.

## Read-only audit contract

[07_audit_prices.sql](../sql/07_audit_prices.sql) runs after the basic price checks and prior calendar/sales audits pass. It checks source/table row counts, required values, duplicate item/store/week keys, price numeric validity and positivity, min/max, week-code shape, pair/week existence and exact full-row source equality. No persistent table is created or changed.

TRY_CAST to DOUBLE plus isfinite is used only for finite-number, sign and range diagnostics. Missing prices are counted separately from malformed or non-finite values such as NaN and Infinity. Extra decimal precision is not rejected solely for having more than two digits. Binary floating-point parsing is not an exact decimal-money representation; no money sums or sales-value calculations occur here. Underflow to zero fails the nonpositive check, while overflow/non-finite values fail validity. Later typed staging must choose its decimal type from verified precision requirements.

The numeric controls are 6,841,121 finite prices, zero missing/invalid/nonpositive values, minimum 0.01 and maximum 107.32. Source and table row counts must each equal 6,841,121. The displayed actual/expected fields are text so integer counts and price ranges remain readable in one result table; the min/max expected strings are cast from the same DOUBLE type as the observed values.

## Relationships and exact reconciliation

NOT EXISTS checks compare price item/store pairs against the validated raw sales table and price weeks against the validated raw calendar. A separate reverse check counts distinct sales pairs without any price. These existence checks do not join sales quantities and cannot inflate them. Their zero results establish set membership at the pair/week level, not price availability for every daily sales record or a complete estimated sales-value measure.

Both directional EXCEPT ALL operations compare all four original VARCHAR fields. They retain duplicate multiplicities and compare price text exactly, without reducing records to numeric prices or hashes. For example, changing 1.25 to 1.2500 is detected even though the numeric price is equal. The query compares the current CSV; it does not recompute the historic snapshot hash during learner execution.

## Independent assistant verification

[Test runner](../validation/test_price_audit.py) passed all 15 real-source checks with DuckDB v1.5.5. Baseline setup plus audit took 26.689 seconds in the recorded run. The baseline imported prices and only the item/store and week columns needed from the sales/calendar source files as temporary reference tables. It did not reconstruct a persistent sales model or open the learner's database.

The preflight used two threads, a DuckDB memory_limit setting of 3GB and a temporary spill directory beneath the ignored project tmp folder. That setting is not a total-process memory limit and does not alter the learner's connection. Actual runtime can differ. All three input hashes matched the [source registry evidence](../data/m5_source_audit.json) and remained unchanged across the real-source baseline.

Twelve tiny fixture cases passed: clean data; NULL/blank prices; malformed text; NaN/Infinity; zero/negative prices; additional precision; a duplicate row; a removed row; an unknown item/store pair; malformed and unknown week codes; a sales pair with all price rows removed; and an equivalent numeric value with changed text. The removed-single-row case still has zero sales pairs without prices, demonstrating that this check does not establish full period coverage. Fixture assertions check selected diagnostics because production totals remain unchanged in the SQL. These cases are not exhaustive coverage.

The [recorded evidence](../data/price_audit_preflight.json) contains the SQL fingerprint, source hashes, baseline output and fixture diagnostics. All databases were :memory: and no raw rows or learner screenshot are published.

To reproduce from the repository root:

```powershell
python validation/test_price_audit.py --duckdb "E:/DuckDB/duckdb.exe" --output "data/price_audit_preflight.json"
```

The SQL and runner contain the current local source paths; adjust them when reproducing elsewhere. The learner has now supplied and passed all 15 audit rows, completing the [raw-layer checkpoint](RAW_LAYER_CHECKPOINT.md). [Typed calendar staging](CALENDAR_STAGING_VALIDATION.md) has subsequently been accepted. Follow [the current step](FIRST_STEP_ZH.md) for the next learner action. Daily price coverage and downstream modelling remain pending.
