# Daily sales reshape preflight and acceptance scope

27 October 2026. The learner screenshot confirms all 14 checks from [10_stage_sales_daily.sql](../sql/10_stage_sales_daily.sql) passed. The four-column daily sales table is accepted for schema, complete unique day keys, zero preservation and aggregate controls. The [acceptance transcription](../data/sales_daily_learner_acceptance.json) is separate from the assistant preflight below. Full per-cell value reconciliation remains the next learner step.

## Table and transformation contract

The table has four columns: item_id, store_id and d as VARCHAR; units as INTEGER. Its grain is one item/store/source-day. The six original identifier fields remain in raw.m5_sales_wide; category, department and state belong in later dimensions rather than being repeated in every long-table row. The transformation neither creates new transactions nor joins dates or prices.

UNPIVOT INCLUDE NULLS expands the 1,941 day columns without dropping missing values. Before casting, each units value must match nonnegative integer text and fit INTEGER; NULL, fractions, negatives and overflow abort creation. Zero values are retained. Ordinary CREATE TABLE AS SELECT does not replace an existing table. Constraints are checked by validation rather than a 59-million-row primary-key index.

## Key and aggregate checks

A single per-series aggregation checks rows, required values, negatives, zeros, sums, maxima and invalid day labels. For each item/store pair, a bounded bitstring records which day numbers 1 through 1,941 occur. DuckDB's [bitstring_agg documentation](https://duckdb.org/docs/1.5/sql/functions/aggregates) describes its distinct-integer coverage behaviour. Invalid or out-of-range day labels are counted separately and excluded from that bounded aggregate.

Exactly 1,941 rows together with 1,941 covered valid day numbers proves that every expected day key occurs exactly once in each series. This avoids keeping a hash entry for each of the 59,181,090 composite daily keys. The small series-key table is compared in both directions with the raw item/store set, so equal pair counts alone are not considered sufficient. Ten store totals are checked against the original source-audit controls.

The baseline controls are 59,181,090 rows, 30,490 series, 40,241,819 zero-sales rows, 66,927,173 total units and maximum units of 763. Each series must have 1,941 rows and complete day coverage, with zero schema, missing-value, negative-unit, day-label, pair-set or store-total errors.

These tests do not establish equality of each individual unit value to its original wide cell. A same-total shift between two dates can preserve every key and aggregate. Full value reconciliation is a separate next acceptance step; no analytical model or price coverage is claimed here.

## Independent execution and resources

[Preflight runner](../validation/preflight_sales_daily.py) executed the unchanged SQL on the full source with DuckDB v1.5.5. All 14 checks passed. The baseline used its own temporary on-disk database under the ignored repository tmp folder, not the learner database and not a large in-memory-only database. It used two threads, a DuckDB memory_limit of 2GB and a spill directory within the same temporary folder. This setting is not a total-process memory bound and does not change the learner's connection.

Source import, daily-table creation and validation took 74.952 seconds in this run. After close, the temporary database containing the baseline raw and daily tables occupied 300,429,312 bytes. That is not peak working storage or a prediction of the learner database size. The temporary directory was verified as contained within the intended workspace and removed after execution. The original CSV hash matched the registered snapshot and remained unchanged.

Eight targeted fixture cases passed. A two-series fixture contains all 1,941 days and verifies zero preservation. Four cases reject missing, fractional, negative and overflowing units. A duplicate day replacing another day preserves row count but fails coverage; an out-of-range day fails validity and coverage. A final case intentionally shifts a unit between dates without changing totals, demonstrating the need for the next value-reconciliation step. Production expected totals remain unchanged for fixtures; the runner asserts selected diagnostic values rather than all production-sized PASS rows.

The [preflight evidence](../data/sales_daily_preflight.json) records source/SQL hashes, resource settings, baseline output, directory cleanup confirmation and all fixture outcomes. No raw rows, database files or learner screenshots are published.

To reproduce from the repository root:

```powershell
python validation/preflight_sales_daily.py --duckdb "E:/DuckDB/duckdb.exe" --output "data/sales_daily_preflight.json"
```

The production script reads raw tables only. The runner and raw import contain the local CSV path; adjust those when reproducing elsewhere. For an existing daily table, run only the VALIDATION query. Follow [the current step](FIRST_STEP_ZH.md) for the learner action.
