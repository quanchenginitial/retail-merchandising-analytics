# Sales wide-table import acceptance and preflight

27 October 2026. The learner has completed the calendar's 17-check audit and now supplied a DBeaver screenshot showing all 14 sales import checks with status PASS. The [screenshot transcription](../data/sales_import_learner_acceptance.json) records the displayed values. This accepts the raw wide-table structure and identifiers; it does not establish equality of all daily sales values.

## Import contract

[04_import_sales.sql](../sql/04_import_sales.sql) uses CREATE TABLE AS SELECT from the existing evaluation CSV with header=true and all_varchar=true. The script preserves the source's wide layout. It does not append the overlapping validation snapshot, replace an existing table, unpivot, impute or convert sales values. Existing tables cause the create statement to fail; the BASIC CHECKS query can be run separately for an existing table.

The 14 output rows check 30,490 series, 1,947 VARCHAR columns, six expected identifiers, 1,941 ordered daily columns, 30,490 distinct series IDs and item/store pairs, 3,049 items, 10 stores, three states, seven departments, three categories and zero rows with missing identifiers. Metadata is limited to the current database and the intended raw table. These checks do not establish full-value equality or reconcile all 59,181,090 daily sales cells.

## Executed assistant preflight

[Preflight runner](../validation/preflight_sales_import.py) executed the unchanged SQL once using DuckDB v1.5.5 in :memory:. All 14 checks passed. Import plus checks took 12.326 seconds in this run; this is an observation, not a performance guarantee. The preflight used two threads and a DuckDB memory_limit setting of 2GB, which is not a bound on total process memory. These settings apply only to the preflight connection.

The source SHA-256 matched the [earlier source audit](../data/m5_source_audit.json) before execution and remained unchanged afterward. The [preflight evidence](../data/sales_import_preflight.json) records source and SQL fingerprints, settings and all check results. No learner database was opened or modified, and no raw records are published.

To reproduce from the repository root:

```powershell
python validation/preflight_sales_import.py --duckdb "E:/DuckDB/duckdb.exe" --output "data/sales_import_preflight.json"
```

The SQL and runner currently reference the learner's local M5 source directory; adjust both when reproducing elsewhere. The learner import is accepted, and the subsequent [detailed sales audit](SALES_AUDIT_VALIDATION.md) has also passed all 15 checks. The next learner instructions for price import are in [the current step](FIRST_STEP_ZH.md).
