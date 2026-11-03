# Retailrocket reusable category root/depth dimension

This SQL62 contract was frozen on 3 November 2026 before building the dimension. The learner has accepted [SQL61](../data/retailrocket_category_hierarchy_learner_acceptance.json): the supplied 1,669-node reference is a rooted forest with 25 roots and maximum depth 5, with roots at depth zero. SQL62 persists that validated structural mapping for later category rollups.

## Purpose and table contract

[SQL62](../sql/62_build_retailrocket_category_dimension.sql) creates **rr_core.dim_category** from rr_stg.category_tree. Its columns, in order, are **categoryid BIGINT, parentid BIGINT, root_categoryid BIGINT, depth BIGINT**. Each known category has one row. Original parent links and 25 NULL parents remain intact. A root maps to itself at depth zero; every other node inherits its parent's root and has depth one greater than its parent.

The expected 1,669 rows, 25 roots and maximum depth 5 are already accepted SQL61 snapshot baselines, not newly discovered thresholds. This is a reusable mapping of the supplied reference, not a full ancestor-closure table, named taxonomy, historical validity interval or event-time association. No unknown category is invented; the 167 unmatched property records remain unresolved and unmodified elsewhere.

## Guarded creation and bounded traversal

Plain CREATE TABLE refuses an existing target. The exact two-column BIGINT input schema/order, accepted positive row count, unique nonmissing/nonnegative IDs and closed parent references admit nodes to recursion. Negative checks cover both identifiers. Expected root count and direct self-links are also checked before creation can succeed.

The root-down walk carries categoryid, parentid, root_categoryid and depth. Roots start at depth zero, and recursion expands only below N-1. The final singleton guard requires complete N-row/N-distinct coverage, no repeated traversal rows, no child edge beyond the depth bound, the accepted 25 roots, zero self-links and maximum depth 5. A disconnected cycle, including its feeders, cannot pass complete coverage even when another component is correctly rooted.

The singleton guard is LEFT JOINed to the walk and all four output fields use CASE/error. An empty or rootless input therefore still produces an error-bearing row; an invalid or partly rooted graph cannot silently persist a partial dimension. Failure inside CREATE TABLE AS leaves no target table. The preceding CREATE SCHEMA IF NOT EXISTS may leave an empty rr_core schema; whole-script rollback is not claimed. Unusable schemas may fail binding earlier. The original staging table is read-only throughout.

No primary-key or NOT-NULL constraints are declared by CTAS. Key, nonmissing and graph properties are validated snapshot conditions. For an existing target, preserve it and execute only the query following **-- CHECKS: if rr_core.dim_category already exists, run only the query below.** The check query does not rebuild the target.

## Frozen 20-row report

The report contains **20 rows × 5 columns**: check_order, check_name, actual, expected, status. All 20 controls are expected PASS for the accepted input and correctly built dimension.

| Order | Check | Expected |
|---:|---|---:|
| 1 | dimension_rows | 1,669 |
| 2 | column_count | 4 |
| 3 | schema_mismatch_count | 0 |
| 4 | distinct_categoryids | 1,669 |
| 5 | missing_required_rows | 0 |
| 6 | duplicate_key_surplus | 0 |
| 7 | null_parent_rows | 25 |
| 8 | distinct_root_ids | 25 |
| 9 | root_identity_errors | 0 |
| 10 | root_reference_errors | 0 |
| 11 | parent_mapping_errors | 0 |
| 12 | parent_root_depth_errors | 0 |
| 13 | negative_depth_rows | 0 |
| 14 | max_depth | 5 |
| 15 | source_only_rows | 0 |
| 16 | dimension_only_rows | 0 |
| 17 | expected_mapping_only_rows | 0 |
| 18 | dimension_mapping_only_rows | 0 |
| 19 | source_contract_violations | 0 |
| 20 | source_rows | 1,669 |

missing_required_rows counts rows with NULL categoryid, root_categoryid or depth; parentid is nullable. Duplicate surplus counts non-NULL category-ID occurrences minus distinct non-NULL IDs. Root identity uses NULL-safe comparisons. Root and parent reference checks use NOT EXISTS so missing or NULL root IDs are counted without join multiplication. Parent root/depth consistency requires an existing parent with the same non-NULL root ID and depth exactly one less; a wider integer intermediate prevents overflow when checking bad stored depth values.

source_contract_violations is a **0/1 indicator** of the complete source/graph guard, not a count of bad records or separate failed conditions. The two source/dimension differences compare full category-parent multisets with EXCEPT ALL. The two mapping differences compare all four fields with the freshly derived expected walk, preserving multiplicity. These keyed checks can detect a wrong root or depth even when global row/root/depth summaries are unchanged.

## Bounded independent validation

The [validator](../validation/preflight_retailrocket_category_dimension.py) reconstructs only the frozen SQL55 raw import and SQL60 staging creation prefixes in a disposable database, then executes SQL62 once. It reads only category_tree.csv and freshly verifies its hash/metadata. SQL61's accepted evidence supplies baseline metadata; its full audit is not rerun. No property/event/M5 CSV or learner database is opened.

An independent Python reference follows each category's parent chain using a visited set, discovering its root and counting edges. It compares every four-field dimension tuple and its multiplicity for all 1,669 known categories, and independently builds the aggregate checks. The input tuple multiset is compared after execution. Real identifiers and node mappings remain process memory only; public evidence contains aggregates and hashes.

Tiny fixtures cover a branching forest, singleton root and maximum-length chain; an otherwise valid mapping with a wrong root or depth must fail keyed checks even when row count, root count and maximum depth remain unchanged. Empty, rootless-cycle and mixed rooted/cyclic inputs verify atomic target absence. Other rejection cases isolate row/root/depth baselines, duplicate/NULL/negative/orphan/self keys and otherwise valid schema mismatches. Reopening rejected private databases verifies no target and preserved input. A second CREATE must preserve an existing altered target sentinel. No fixture alters real source records.

Execution uses two threads, 512MB DuckDB memory setting, 1GB spill limit and 60 seconds per CLI phase. Private directories are below repository tmp and removed afterward. Post-phase directory observations are not continuous peaks, and the memory setting is not a total-process cap. Historical evidence and source hashes must remain unchanged.

```powershell
python validation/preflight_retailrocket_category_dimension.py --duckdb "E:/DuckDB/duckdb.exe" --output "data/retailrocket_category_dimension_preflight.json"
```

Measured results will be appended and saved in [aggregate evidence](../data/retailrocket_category_dimension_preflight.json). Later behavior metrics must choose the correct aggregation level and event-time property state; this static reference dimension alone does not resolve those definitions.

## Executed results

The assistant's isolated SQL62 preflight completed on 3 November 2026: **20 rows × 5 columns, all 20 PASS**. Learner execution and screenshot acceptance remain pending. The frozen method prefix above is unchanged, with SHA-256 `5cd3ebab26b643a29c87a57c71f612f7d850991c666bfdb6971144dddf6fa593`.

The dimension contains **1,669 rows in four BIGINT columns**, one per supplied category, with **25 NULL parents, 25 distinct root IDs and maximum depth 5**. Root identity/reference, parent mapping/root/depth consistency, required-key and duplicate checks all pass. Both full source-pair differences and both full four-field mapping differences are zero. The complete source guard passes. The root count and maximum depth reproduce the accepted SQL61 baselines rather than constitute new discoveries.

The independent Python parent-chain reference matched **all 1,669 four-field tuples and their multiplicities**, including the root ID assigned to every category. The separate aggregate-report oracle and input tuple multiset also matched. Real identifiers and mappings stayed in process memory and were not exported or logged. The [aggregate evidence](../data/retailrocket_category_dimension_preflight.json) has report fingerprint `e4536879004701f2d4a733e0b259f8ef628934d094a056d520ddc028ff2aaa0e`.

Three focused fixture families passed, including **13 rejection subcases**. Hand-checked forest, singleton and N-1 chain fixtures produced complete correct maps. Swapping two nodes' root assignments or depths kept global row/root/max-depth summaries unchanged while failing the parent-consistency and full keyed-map checks. Plain CREATE then refused a repeated build and preserved the altered target sentinel. Empty, rootless-cycle and mixed rooted/cyclic inputs left no target table; in the mixed fixture, the rooted component already matched its root/depth baselines, so incomplete coverage was specifically tested. Otherwise-valid schema and other input failures also preserved the original staged tuples.

The one real CLI run took **0.237 seconds**, including the frozen SQL55/60 reconstruction prefixes, guarded dimension creation, its 20-row check query and private input/dimension projections. Creation and checking each derive the finite walk; SQL61's full audit was not rerun. Timing excludes hashes, Python reference work and fixtures and is not a benchmark.

The real private database was **1,060,864 bytes** before cleanup. The largest post-phase directory observation across fixtures and the real run was **4,878,336 bytes**, including multiple fixture databases; it is not a continuously measured peak. All private databases and spills were removed. The category source hash and metadata, **13 pinned code/evidence dependencies**, and **60 historical preflight files** remained unchanged.

No learner database or property/event/M5 CSV was opened. This delivers the verified dimension construction and validation script; the learner's persistent table still awaits execution. No history intervals, decoded category labels, full ancestor closure, inferred unknown category, event attribution or declared database key constraints were added.
