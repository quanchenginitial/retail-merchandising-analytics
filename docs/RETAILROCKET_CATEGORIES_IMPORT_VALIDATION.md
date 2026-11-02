# Retailrocket categories: raw reference import

[SQL55](../sql/55_import_retailrocket_categories.sql) imports only the audited `category_tree.csv` into **rr_raw.category_tree**. On 2 November 2026, the assistant's isolated preflight passed all **15 checks across five report columns**. Learner execution and acceptance remain pending. This step preserves the raw reference and checks import integrity plus basic keys and parent references. It does not join events, properties or M5, and it does not perform recursive hierarchy, cycle, depth or root-membership analysis.

## Frozen import and report contract

The input is `D:/database/retailrocket/category_tree.csv`: 14,454 bytes, SHA-256 `94e865eb0a3d48cbbfe3b79079018dd92509315c88f5fd8d00d0b4b5af434f5b`. This is the observed local hash recorded by the [source audit](../data/retailrocket_source_audit.json), not a publisher-certified checksum. The [independent source checks](../data/retailrocket_independent_checks.json) establish the expected category counts and immediate-parent diagnostics.

The two stored columns are **categoryid, parentid**, both VARCHAR in source order. Explicit CSV settings require UTF-8, strict parsing, two fields per record and no skipped or padded rows. Only exact-empty parentid becomes NULL. Category empty strings, leading zeros, spaces and duplicate observations remain unchanged; invalid required or numeric text is flagged rather than silently corrected. Numeric validity checks do not change stored types. Parent/self/key comparisons use exact raw text, so a leading-zero identifier is not collapsed into a different spelling.

Plain CREATE TABLE protects an existing table from replacement or appending. If rr_raw.category_tree already exists, the learner should run only the marked checks query. No automatic drop or replacement is provided.

The frozen report contains **15 rows × 5 columns**: check_order, check_name, actual, expected, status. Expectations come from the already-audited source. All actual values matched these expectations, and every status was PASS in the assistant preflight:

| Check | Expected |
|---|---:|
| row_count | 1,669 |
| column_count | 2 |
| varchar_column_count | 2 |
| column_sequence_errors | 0 |
| missing_categoryid_rows | 0 |
| invalid_categoryid_rows | 0 |
| invalid_parentid_rows | 0 |
| distinct_categoryids | 1,669 |
| null_parentid_rows | 25 |
| duplicate_categoryid_surplus_rows | 0 |
| self_parent_rows | 0 |
| orphan_parent_rows | 0 |
| source_rows_absent_from_table | 0 |
| table_rows_absent_from_source | 0 |
| duplicate_surplus_rows_preserved | 0 |

The 25 NULL-parent records are **root candidates**, not proof of a fully validated taxonomy. No immediate orphan or self-parent does not rule out a longer cycle. Category-key duplicate surplus means total rows minus distinct category identifiers; full-row duplicate surplus uses both fields. These are separate checks. Both directions of EXCEPT ALL compare every raw field, including NULLs and multiplicity.

## Bounded validation actually executed

The [validator](../validation/preflight_retailrocket_categories_import.py) used DuckDB 1.5.5 entirely in memory and independently read the complete 1,669 × 2 source with Python csv. Its Counter comparison checked every two-field tuple and multiplicity against the imported table, finding zero differences in either direction. Real identifiers remained only in process memory and never entered public evidence or logs. The two SQL EXCEPT ALL comparisons also returned zero. Source, dependency and historical-preflight hashes remained unchanged. No other Retailrocket CSV, M5 source or learner database was opened.

Three focused synthetic cases passed:

1. Optional NULLs, leading-zero strings and duplicate observations survived unchanged; duplicate category keys produced a uniqueness failure, reimport into an existing table was rejected, and removing one duplicate caused the intended multiplicity failure.
2. Required empty strings and whitespace remained stored, while invalid IDs, self-parent and immediate-orphan checks produced their intended failures.
3. Both extra and missing CSV fields were rejected rather than skipped or padded.

The one real-source CLI execution took **0.156 seconds**, including import, checks and the private table projection; hashing, Python reference construction and fixtures are excluded. Two threads and a 512MB DuckDB memory setting were used, with a 60-second execution timeout; this is not a total-process memory guarantee or a performance benchmark. Temporary fixture files and spills were removed; every database execution used `:memory:`.

Run from the repository root with Python 3.11+ and DuckDB 1.5.5:

```powershell
python validation/preflight_retailrocket_categories_import.py --duckdb "E:/DuckDB/duckdb.exe" --output "data/retailrocket_categories_import_preflight.json"
```

The [aggregate preflight evidence](../data/retailrocket_categories_import_preflight.json) records code/dependency hashes, preservation checks, fixture results and the full 15-row report. Its report fingerprint is `80c8b1c3380d86eef37c9968dcedfda999fa20ecc4a1b8417538b932e588bced`: ordered compact JSON arrays in output-column order, followed by LF, with integer counts/order and string labels/status.

The next learner action is to run SQL55 and return the complete 15-row, five-column report with every status visible. Raw property import, typed staging, category hierarchy validation, time-aware joins and RF/funnel/basket definitions remain subsequent work. Passing these checks does not establish that the category structure is acyclic or that a category is linked to a valid root.
