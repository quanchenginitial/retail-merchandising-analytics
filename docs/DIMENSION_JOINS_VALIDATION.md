# Full daily-sales joins to product, store and calendar

27 October 2026. All three dimensions have passed learner acceptance. The next action is [15_audit_sales_dimension_joins.sql](../sql/15_audit_sales_dimension_joins.sql), a single read-only query that executes the three joins over the complete sales table. Assistant preflight is complete; learner execution remains pending.

## Purpose and scope

The dimensions separately describe product classification, store state and source-day dates/weeks. Before using those descriptions to group sales, each sales observation must match exactly one row in each dimension. A missing lookup can leave records unclassified; a duplicated lookup can multiply sales. Comparing total units alone cannot identify a missing lookup for a zero-sales row.

This query uses three LEFT JOINs on item_id, store_id and d, preserving unmatched source observations so they can be counted explicitly. It creates no table or view, does not join prices and does not calculate a financial measure. It relies on the already accepted source values and dimension semantics; it does not rerun raw-cell reconciliation or every dimension-to-source comparison.

## Why the preservation checks are sufficient

Before the large joins, each small dimension is materialized through a guard driven by its full-table health summary. Duplicate, NULL or blank keys and missing required attributes cause an error. The checks include unused calendar keys, such as dates after the observed sales period. Required attributes are product department/category, store state, and calendar date/week/day_number. Event NULLs are unrelated to join coverage and are not treated as missing matches.

A unique dimension key guarantees at most one match for each source row. Zero unmatched rows establishes at least one match. Together they establish exactly one match in each of the three joins. Sales join keys and units are taken directly from stg.m5_sales_daily, with no filtering or rewriting of units. Thus this join definition preserves every source observation; the proof does not depend only on aggregate totals or a hash.

Independent scans aggregate base and joined data by source store. The query compares overall row counts, units and zero rows against accepted snapshot controls and compares rows, units and zero rows separately for every store. It also checks source missing fields/negative units, joined day/date relationships and the observed date range. There is no separate 59-million-row EXCEPT ALL operation in this step, and no persisted joined fact table is claimed.

All 20 result rows must pass. Expected base and joined controls are 59,181,090 rows, 66,927,173 units and 40,241,819 zero-sales rows. Product/store/calendar unmatched counts, overall differences, invalid joined days and store-control mismatches must be zero. Dates must cover 2011-01-29 through 2016-05-22. A sales row linked to d_1942 or later fails the observed-snapshot check even though that calendar key legitimately exists.

An invalid dimension guard stops the query instead of returning the 20-row grid. A missing dimension key, including an empty lookup table, produces unmatched rows and fails acceptance. Passing the row-count or units check alone does not establish success; all results are required.

## Independent full-source execution

The [runner](../validation/preflight_dimension_joins.py) created its own temporary on-disk DuckDB under the ignored repository tmp directory. It reproduced raw calendar/sales, typed calendar/daily sales and the three dimensions using their creation scripts, then ran the final unchanged join-audit query. It never opened the learner database and did not read price data.

With DuckDB v1.5.5, two threads, memory_limit=2GB and a spill directory inside the temporary folder, setup took 62.148 seconds and the separate full join audit took 5.936 seconds. All 20 checks passed. These are one-run measurements; the configured memory limit is not a total-process memory measurement and does not change learner settings. Both input file hashes matched the registered snapshots and remained unchanged. The temporary workspace was checked to be inside the intended repository directory and removed afterward. [Preflight evidence](../data/dimension_joins_preflight.json) records all results, hashes and resource settings.

Fifteen targeted fixtures passed. The valid fixture preserves four observations, including two zeros. Deleting a product, store or zero-only calendar key leaves sales totals unchanged under LEFT JOIN but produces explicit unmatched-row failures. Duplicate product/store keys and an unused future calendar key are rejected, as are NULL keys or missing required attributes. Other cases detect a sales row on a post-observation date, NULL units hidden by SUM, negative units and a wrongly assigned date. Fixture cardinality/date expectations are adapted to the small data; the observed upper day bound and comparison logic are unchanged.

To reproduce from the repository root:

```powershell
python validation/preflight_dimension_joins.py --duckdb "E:/DuckDB/duckdb.exe" --output "data/dimension_joins_preflight.json"
```

The reproduction setup uses current local CSV paths. The learner query reads existing named tables only and can be rerun safely. Follow [the current step](FIRST_STEP_ZH.md) and return all 20 rows for acceptance. Daily price coverage and fact-table creation remain subsequent steps.
