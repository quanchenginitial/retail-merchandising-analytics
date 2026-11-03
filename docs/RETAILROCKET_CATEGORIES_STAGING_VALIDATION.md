# Retailrocket typed category-reference staging

This SQL60 contract was frozen on 3 November 2026 before the new stage was executed. The learner has accepted [SQL59](../data/retailrocket_unmatched_categories_learner_acceptance.json): its 167 exact-unmatched category-property records have no reference candidates under the defined numeric diagnostic. These records remain retained in the raw property table. Their absence from the supplied reference is not treated as a proven source error or repaired by inventing categories.

## Purpose and fixed transformation

[SQL60](../sql/60_stage_retailrocket_categories.sql) creates **rr_stg.category_tree** from the already accepted **rr_raw.category_tree**. It has two columns in order: categoryid BIGINT and parentid BIGINT. The 1,669 supplied reference records and all 25 NULL parent observations must be preserved. NULL parents remain root candidates; this step does not establish full tree validity.

The raw table remains unchanged. Both non-NULL values must be ASCII digits fitting a nonnegative signed BIGINT and must convert back to exactly the original VARCHAR text. This deliberately conservative stage rejects leading zeros, spaces, signs, decimals, non-ASCII digits, overflow and any other non-roundtripping spelling rather than deciding how to recode them. NULL category IDs and exact-empty non-NULL values are rejected. NULL parent IDs remain NULL. Accepted roundtripping values retain their identity, without trimming, merging or numeric-alias resolution.

The creation guard checks the exact two-column VARCHAR source schema/order, 1,669 rows, 25 NULL parents, zero invalid/non-roundtripping field rows, unique nonmissing category IDs, no numeric aliases, and no direct self-parent or orphan-parent links. Numeric aliases count parsed integers with more than one distinct original category-ID spelling; identical duplicate rows are covered separately. Existing accepted raw integrity is therefore required before casting.

## Failure and rerun behavior

Plain CREATE TABLE protects an existing destination. The singleton aggregate guard is LEFT JOINed to the raw rows, ensuring one error-bearing row survives even if the source is empty. Both output fields use a guarded CASE; invalid input raises an error inside the atomic CREATE TABLE AS statement instead of silently producing an empty or partial destination. A preceding CREATE SCHEMA IF NOT EXISTS can leave an empty rr_stg schema after failure; no whole-script rollback or absence of every schema mutation is claimed.

The staged key's uniqueness and non-NULL property are validated data conditions, not declared primary-key/NOT-NULL database constraints. No subsequent appends or updates are implemented. If the destination already exists, do not rerun creation or replace it: run only the query following the exact marker **-- CHECKS: if rr_stg.category_tree already exists, run only the query below.** The checks inspect the current table; they do not silently rebuild it.

## Frozen 18-row report

The output is **18 rows × 5 columns**: check_order, check_name, actual, expected, status. All 18 controls are expected to PASS for the accepted input. There are no new INFO observations in this stage.

| Order | Check | Expected |
|---:|---|---:|
| 1 | staging_rows | 1,669 |
| 2 | column_count | 2 |
| 3 | bigint_column_count | 2 |
| 4 | schema_mismatch_count | 0 |
| 5 | distinct_categoryids | 1,669 |
| 6 | missing_categoryids | 0 |
| 7 | duplicate_key_surplus | 0 |
| 8 | null_parent_rows | 25 |
| 9 | self_parent_rows | 0 |
| 10 | orphan_parent_rows | 0 |
| 11 | raw_rows | 1,669 |
| 12 | raw_value_contract_violations | 0 |
| 13 | raw_only_rows | 0 |
| 14 | staging_only_rows | 0 |
| 15 | raw_null_parent_rows | 25 |
| 16 | root_set_difference | 0 |
| 17 | numeric_key_collisions | 0 |
| 18 | raw_schema_mismatch | 0 |

raw_value_contract_violations counts raw records with a missing category ID or at least one field failing the nonnegative ASCII/BIGINT/exact-roundtrip rule; it is not a sum of overlapping field errors. raw_schema_mismatch is a 0/1 indicator. The two full-table comparisons cast staging values back to VARCHAR and use EXCEPT ALL in both directions, preserving NULLs and multiplicity. The separate root-set comparison counts the symmetric difference of category IDs whose parents are NULL. Schema and key checks establish data conditions at execution time, not future write constraints or publisher authenticity.

## Bounded validation

The [validator](../validation/preflight_retailrocket_categories_staging.py) reconstructs only the small raw category table using the frozen SQL55 import prefix, then runs SQL60 once in an isolated temporary DuckDB database. It reads only category_tree.csv, verifies its established SHA-256 and metadata before/after, and pins the accepted raw import and SQL59 evidence. It does not read the property/event/M5 source files or open the learner's database, and it does not rerun previous full audit suites.

Independent synthetic Python Counter references check a small valid typed result and its full aggregate report. Rejection fixtures cover empty input, wrong row/root counts, wrong schema/order, lossy strings/numeric aliases, malformed/NULL/overflow keys, duplicate keys, direct self/orphan links, and an already-existing destination. Failed-creation tests reopen the private database and verify destination absence and raw preservation. A second creation attempt must preserve a deliberately changed existing staged sentinel. A changed staged tuple must fail the full multiset checks. These synthetic mutations never touch the learner database or actual source records.

For the real 1,669-row reference, an independent Python CSV Counter compares all typed tuples privately with the isolated staged table and checks that the raw table remains the original string/NULL multiset. These private tuples are held only in process memory and are never printed or exported. Only the aggregate report, resource observations and hashes are saved. This small direct comparison is scoped to the category reference, not all property/event sources.

Execution uses two threads, a 512MB DuckDB memory setting, a 1GB spill limit and a 60-second timeout per CLI phase. A temporary directory under repository tmp owns all private database/spill files and is removed on completion. Settings are not a total-process memory guarantee; final directory size is an observation rather than a continuously measured peak. Historical preflight evidence and frozen inputs must remain unchanged.

```powershell
python validation/preflight_retailrocket_categories_staging.py --duckdb "E:/DuckDB/duckdb.exe" --output "data/retailrocket_categories_staging_preflight.json"
```

Measured results will be appended and recorded in [aggregate evidence](../data/retailrocket_categories_staging_preflight.json). Recursive cycles, root reachability, hierarchy depth, event/property typed keys, historical availability, event-time joins and unmatched-reference handling in later joins remain separate steps. No affected-item history or business-impact claim is made here.

## Executed results

The assistant's isolated SQL60 preflight completed on 3 November 2026: **18 rows × 5 columns, all 18 PASS**. Learner execution and screenshot acceptance remain pending. The frozen 7,118-byte method prefix is unchanged, with SHA-256 `e382b2c65139cdd215d938c04515dd593feab92488e0e796b21093598a979313`.

The stage contains **1,669 distinct category IDs in two BIGINT columns**, preserving all **25 NULL parents**. Missing/duplicate category IDs, direct self-parent/orphan links, source value-contract violations, numeric aliases and schema mismatches are zero. Both full multiset differences and the root-candidate set difference are zero. All supplied reference values passed the exact VARCHAR-to-BIGINT-to-VARCHAR roundtrip; no recoding or inferred category was needed.

The independent Python CSV Counter matched all 1,669 two-field staged tuples and their multiplicities. The private raw-table projection also matched the original string/NULL Counter, confirming that raw observations stayed unchanged in this isolated execution. These private records were held only in process memory and were not exported or logged. The public [aggregate evidence](../data/retailrocket_categories_staging_preflight.json) has report fingerprint `20805154a073ff8c9ecca82f2ea7acf0eec440b97bc9738572dccdf499ca9cae`.

Three focused fixture families passed, including **15 invalid-input subcases**. A single leading-zero root with otherwise valid counts isolated the exact-roundtrip refusal; a separate alias fixture retained collision coverage. Wrong-type and wrong-column-order fixtures used otherwise valid one-row content, so an empty-source/count failure could not mask the schema check. Reopening each rejected private database confirmed no staging table and preserved raw contents. Plain CREATE refused a second attempt and preserved a deliberately changed existing staged sentinel. The modified tuple was detected by the orphan and both full multiset checks.

The one real category-only run took **0.219 seconds**, including the frozen SQL55 import prefix, guarded staging, 18 checks and private projections; it excludes hashes, Python references and fixtures and is not a performance benchmark. The real private database was **798,720 bytes** before cleanup. The largest post-phase directory observation across all fixture and real phases was **7,786,496 bytes**; this includes multiple rejection-fixture databases sharing one temporary directory and is not a continuous peak measurement. All temporary databases and spills were removed.

The category source hash and metadata, all **11 pinned code/evidence dependencies**, and **58 historical preflight files** remained unchanged. No property/event/M5 source, learner database, SQL59 rerun or prior full audit suite was opened or rerun. The 167 unmatched property records remain outside this reference stage and unchanged in the raw property table; no unknown category was invented. Cycles, root reachability, depth, future database constraints and time-aware event joins remain unvalidated by this stage.

## Learner screenshot acceptance — 3 November 2026

The learner supplied the final SQL60 DBeaver report. All **18 rows × 5 columns, 90 fields**, are fully visible and match the frozen assistant preflight: **54 integer fields, 18 complete check names and 18 PASS statuses**. All five column headers are visible. There are no cropped labels, inferred values, INFO/NULL expectations, FAIL rows or mismatches. See the [aggregate acceptance record](../data/retailrocket_categories_staging_learner_acceptance.json).

The screenshot reproduces 1,669 staged rows and distinct category IDs, two BIGINT columns, 25 NULL parents, and zero schema/key/direct-reference/roundtrip/full-multiset/root-set discrepancies. The 25 NULL parents remain root candidates; SQL60 does not establish an acyclic hierarchy, complete root reachability or depth. The checks validate observed data, not declared PRIMARY KEY/NOT NULL constraints or future writes. No unresolved property record is repaired or assigned an invented category.

The independently transcribed report has fingerprint `20805154a073ff8c9ecca82f2ea7acf0eec440b97bc9738572dccdf499ca9cae`, matching the frozen reference. The assistant did not reopen the learner database, rerun SQL/source preflights or fixtures, or save the screenshot or source identifiers to the repository. All prior method bytes, including the frozen 7,118-byte contract and executed results, remain unchanged; the earlier pending statements are historical, and this appended record establishes learner acceptance.
