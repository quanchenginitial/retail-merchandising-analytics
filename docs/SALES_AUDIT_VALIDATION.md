# Sales-value audit and source reconciliation

27 October 2026. The learner's screenshot confirms all 14 sales raw import checks passed. The [acceptance transcription](../data/sales_import_learner_acceptance.json) records the observed values. The subsequent learner screenshot shows all 15 detailed sales checks with status PASS. The [detailed acceptance transcription](../data/sales_audit_learner_acceptance.json) records the displayed totals, error counts and zero differences in both directions. This is learner-provided evidence, not a new direct read of the persistent database.

## Read-only audit contract

[05_audit_sales.sql](../sql/05_audit_sales.sql) returns 15 checks. It runs after the basic import checks have passed and does not create a persistent long table or change raw values. The query temporarily expands the daily columns using UNPIVOT INCLUDE NULLS so missing cells remain observable. The syntax and dynamic COLUMNS selection are documented in [DuckDB 1.5 UNPIVOT](https://duckdb.org/docs/1.5/sql/statements/unpivot).

A value is a valid integer only when it matches -?[0-9]+ and fits BIGINT. The query tests integer syntax before conversion, so values such as 1.5 and 1e2 are not accepted through numeric rounding or coercion. NULL and empty/whitespace-only cells are counted as missing; non-missing malformed or out-of-range cells are counted as invalid. Negative valid integers are counted separately. SUM(BIGINT) retains the wider HUGEINT total type. Invalid cells are excluded from numeric totals and independently cause FAIL, so totals alone cannot imply valid data.

The expected controls come from the [earlier independent source audit](../data/m5_source_audit.json): 30,490 source and table rows; 59,181,090 daily cells and valid integers; zero missing, invalid or negative cells; 40,241,819 zero cells; total units 66,927,173; maximum item/store/day units 763. Additional checks cover series ID labels and inconsistent product/department/category or store/state mappings. These supplement the preceding six-identifier missingness and uniqueness checks.

## Exact source comparison

Each full raw row, including its field names, is serialized to JSON text with to_json(row). Both sides originate as VARCHAR fields. The query compares the complete strings, not hashes or totals. JSON encoding preserves text values and NULLs and distinguishes changed column names. Two directional EXCEPT ALL operations retain duplicate multiplicities, as defined in [DuckDB 1.5 set operations](https://duckdb.org/docs/1.5/sql/query_syntax/setops). Both difference counts must be zero. This comparison also requires the same column order established by the import contract.

The record-string CTEs are materialized for reuse; the full wide-row and daily-cell CTEs are not explicitly materialized. Query execution may use temporary storage, but does not persist an analysis table. This query compares the current CSV; it does not independently rehash the source snapshot during learner execution.

## Executed assistant verification

[Test runner](../validation/test_sales_audit.py) passed the real-source 15-check baseline in DuckDB v1.5.5. Import plus audit took 58.027 seconds in the recorded successful run. The preflight used two threads, a DuckDB memory_limit setting of 3GB and a temporary spill directory under the ignored project tmp folder. The memory setting is not a bound on total process memory and these settings do not change the learner's connection. Actual learner runtime can differ.

Twelve tiny fixture cases passed: clean data, NULL, whitespace, decimal, scientific notation, integer overflow, negative units, a duplicate row, a removed row, offsetting edits with unchanged total, a changed identifier and a renamed day column. The offsetting case also preserves cell count, zero count and maximum, showing why these controls do not replace full-record comparison. Fixtures use two series and two daily columns; the runner asserts selected diagnostic values rather than production-size PASS totals. These cases are not exhaustive coverage.

The [recorded evidence](../data/sales_audit_preflight.json) contains the exact SQL fingerprint, baseline results and fixture diagnostics. The source hash matched the prior registered snapshot and remained unchanged through the real-source baseline. All databases were :memory:, and the learner's persistent database was never opened. No raw records or user screenshot are published.

To reproduce from the repository root:

```powershell
python validation/test_sales_audit.py --duckdb "E:/DuckDB/duckdb.exe" --output "data/sales_audit_preflight.json"
```

Adjust the local source paths in both SQL and runner when reproducing elsewhere. The learner has now supplied and passed all 15 result rows. The next step is [price import and basic checks](PRICE_IMPORT_VALIDATION.md), following [the current step](FIRST_STEP_ZH.md). Price import and downstream modelling remain pending. Zero recorded sales do not by themselves establish a stockout or unconstrained demand.
