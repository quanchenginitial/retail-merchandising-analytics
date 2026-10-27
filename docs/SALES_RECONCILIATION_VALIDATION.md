# Daily sales exact value reconciliation

27 October 2026. The learner has passed all 14 sales-reshape checks and all 15 checks from [11_reconcile_sales_daily.sql](../sql/11_reconcile_sales_daily.sql). The [latest screenshot transcription](../data/sales_reconciliation_learner_acceptance.json) confirms 59,181,090 compared cells, zero mismatching series/cells and complete unique daily keys. Exact daily value reconciliation is accepted. The assistant preflight below is separate evidence; see the [staging checkpoint](STAGING_LAYER_CHECKPOINT.md) and [current step](FIRST_STEP_ZH.md) for subsequent work.

## What the query proves

This single read-only query compares the current raw wide table with the daily staging table. It reads existing tables without creating or modifying them. The source CSV was previously reconciled to raw; this query does not independently authenticate the historical download or repeat a source-file hash check in the learner database.

For each raw item/store row, the 1,941 daily values become an INTEGER list. The original day-column count and physical ordinal positions are checked, so list position n corresponds to d_n. Each source value must be nonnegative integer text within INTEGER range; NULL, fractional, negative or overflowing values cause an error rather than being rounded or silently dropped. Original text stays in raw.

For each staging item/store pair, units are collected in numeric day order. Sorting by the textual label would put d_10 before d_2, so the query explicitly parses the numeric suffix. Before accepting a comparison, it requires exactly 1,941 rows, 1,941 covered valid day numbers, canonical day labels and no missing required values. Row count plus bounded day coverage proves every expected day appears exactly once, including zero-sales days.

Raw keys must be unique and nonempty. Both directions of the item/store set difference must be empty. Complete ordered value lists are compared directly with IS DISTINCT FROM; there is no hash or aggregate-total substitute for equality. For differing eligible series, element-by-element comparison counts the specific mismatching cells. Series with incomplete or invalid keys are excluded from this value count and reported by separate failing controls.

All 15 checks must pass together. The expected comparison covers 30,490 series × 1,941 days = 59,181,090 cells, with zero mismatching series and cells. If any of the first 13 structure/coverage checks fails, the two value checks show INCOMPLETE, even when the comparable subset has zero mismatches. Thus extra orphan series outside an otherwise complete matching grid cannot give an apparently complete value result.

This establishes numeric value equivalence and daily-key multiplicity against raw, under the accepted SQL 10 column types. It does not establish daily price coverage, inventory availability, financial amounts or business findings.

## Independent full-source validation

The [runner](../validation/preflight_sales_reconciliation.py) created its own temporary on-disk DuckDB under the ignored repository tmp directory, loaded raw sales and created daily staging, then executed the final unchanged reconciliation SQL. It never opened the learner database. The final run used DuckDB v1.5.5, two threads, memory_limit=2GB and a spill directory inside the same temporary folder. The limit is a DuckDB setting, not a measured ceiling on total process memory; the learner connection settings are not changed.

All 15 full-source checks passed. Setup took 79.983 seconds and the separate reconciliation took 12.597 seconds. These are one-run measurements, not a runtime guarantee. The registered source SHA-256 matched before execution and was unchanged afterward. The temporary directory was checked to be inside the intended workspace and removed after the run. Full results, hashes and timings are in [preflight evidence](../data/sales_reconciliation_preflight.json).

The comparison operates on 30,490 ordered series lists rather than building a separate hash entry for every daily key. The bounded-memory full-source execution demonstrates this implementation on the current dataset; it is not a general guarantee for arbitrarily larger data.

## Targeted checks

Sixteen fixture cases passed. The fixture uses two complete 1,941-day series; only the expected production cardinalities are adjusted to two series and 3,882 cells. All comparison logic is unchanged. The correct case passes every check despite reverse physical row ordering. A two-day shift preserves total units and zero count but reports one differing series and two differing cells.

Other cases cover duplicate-plus-missing days with equal values, a removed day, noncanonical and out-of-range labels, NULL units, a replaced series key, an additional orphan series beyond a complete comparable grid, duplicate or NULL raw keys, reordered raw day columns, and four invalid raw value cases: NULL, fractional, negative and overflow. Structural failures show INCOMPLETE for value checks; value shifts with complete keys show FAIL. No fixture changes are applied to user tables or source files.

To reproduce from the repository root:

```powershell
python validation/preflight_sales_reconciliation.py --duckdb "E:/DuckDB/duckdb.exe" --output "data/sales_reconciliation_preflight.json"
```

The runner and import script use the current local CSV path; adjust them for another machine. The learner query reads only named tables and can be rerun safely. Learner acceptance is now recorded above; follow [the current step](FIRST_STEP_ZH.md) for the next action.
