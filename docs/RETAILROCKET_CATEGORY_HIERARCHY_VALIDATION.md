# Retailrocket category hierarchy audit

This SQL61 contract was frozen on 3 November 2026 before computing hierarchy outcomes. The learner has accepted [SQL60](../data/retailrocket_categories_staging_learner_acceptance.json): 1,669 typed reference rows and 25 NULL parent observations, with preserved identities and direct references. Those controls alone did not establish an acyclic hierarchy or a path from each category to a root.

## Purpose and graph contract

[SQL61](../sql/61_audit_retailrocket_category_hierarchy.sql) reads only rr_stg.category_tree. It checks that every known category can reach a NULL-parent root, then reports a small number of shape observations. No identifier, path or category-level history is exported; no table or mapping is created. The 167 unmatched property records remain separate and unresolved. A valid supplied reference does not make every property or event reference valid.

The required input is the accepted two BIGINT columns in order, categoryid then parentid, with 1,669 rows. Graph admission requires a nonempty exact row count, unique nonmissing category IDs, nonnegative IDs in both fields, and every non-NULL parent found in the reference. The negative-row check counts a row once if either categoryid or parentid is negative. Duplicate-key surplus is non-NULL category-ID occurrences minus distinct non-NULL IDs; missing IDs are checked separately.

Expected root count 25 and zero direct self-links are checked but do not control graph admission. This permits a closed, unique graph containing a self-cycle or longer cycle to be diagnosed rather than suppressed. If admission fails, graph metrics are NULL/BLOCKED; input checks still display their counts. An unusable schema may fail SQL binding before a report can be produced. A type/order mismatch that remains bindable produces schema failure and suppresses recursion.

## Finite traversal and interpretation

Traversal starts at each NULL-parent category with depth **0** and follows child edges. Recursion expands only while the current depth is less than N-1, where N is the admitted row count. A separate depth_limit_child_edges control counts child edges leaving a reached node at depth N-1. Merely having a leaf at depth N-1 is valid and does not fail this check.

Under unique IDs and one resolved parent per nonroot node, a root-reachable path cannot enter a cycle: a cycle member already has its parent inside the cycle. Each reachable category therefore has one rooted path. Cycles are disconnected from roots, together with all descendants whose parent chains lead into those cycles. With closed finite parent references, nodes not reached from roots are **cycle-affected**, which includes feeder nodes and is not a count of cycle members.

cycle_affected_nodes is N minus distinct root-reachable nodes only when admission succeeds and both repeated-traversal and depth-boundary counts are zero. Otherwise this attribution is NULL/BLOCKED. This avoids attributing a traversal failure to a cycle. The finite N-1 bound, admission filtering and duplicate-path check are explicit; the query does not enumerate ancestry paths from every start node.

The four shape observations are reported only when all integrity/hierarchy controls pass. They have expected=NULL and no predetermined target. If controls fail, their actual values are NULL and their status is BLOCKED, not zero-valued INFO. A leaf has no direct children and includes an isolated root. A branching node has more than one direct child. Maximum children is calculated over all known nodes, including nodes with zero children. Maximum root depth counts edges, so a singleton root has depth zero.

## Frozen 18-row report

Output columns are check_order, check_name, actual, expected, status. Valid data produces **14 PASS controls and 4 INFO observations**.

| Order | Check | Expected / role |
|---:|---|---|
| 1 | category_rows | 1,669 |
| 2 | column_count | 2 |
| 3 | schema_mismatch | 0 |
| 4 | distinct_categoryids | 1,669 |
| 5 | missing_categoryids | 0 |
| 6 | duplicate_key_surplus | 0 |
| 7 | negative_identifier_rows | 0 |
| 8 | root_nodes | 25 |
| 9 | self_parent_rows | 0 |
| 10 | orphan_parent_rows | 0 |
| 11 | root_reachable_nodes | 1,669 |
| 12 | cycle_affected_nodes | 0 |
| 13 | repeated_traversal_rows | 0 |
| 14 | depth_limit_child_edges | 0 |
| 15 | max_root_depth | NULL / INFO |
| 16 | leaf_nodes | NULL / INFO |
| 17 | branching_nodes | NULL / INFO |
| 18 | max_children_per_node | NULL / INFO |

Schema mismatch is a 0/1 indicator covering count, names, order and exact BIGINT types. Graph input has no declared database key constraints; checks describe the current snapshot. A successful report establishes the stated forest properties of supplied category IDs, not category meanings, publisher authenticity, event-time coverage or future data integrity.

## Bounded independent validation

The [validator](../validation/preflight_retailrocket_category_hierarchy.py) reconstructs only SQL55's frozen category import prefix and SQL60's frozen category staging prefix in a disposable database. It reads only the 14,454-byte category_tree.csv, verifies its source hash and metadata before/after, and preserves earlier accepted code/evidence hashes. It does not rerun prior full check suites, read property/event/M5 sources or open the learner database.

An independent Python graph reference follows each node's parent chain with a visited set until a root, repeated node or missing parent is found. It compares the complete aggregate report and, privately, all root-reachable node depths with the SQL root-down traversal. This algorithm differs from the SQL traversal. Only counts and hashes are published; real identifiers, tuples and depth maps remain process memory only.

Tiny hand-checked fixtures include a branching forest with an isolated root, a singleton root, a maximum-length N-1 chain, a three-node cycle with a feeder plus a rooted component, and a direct self-cycle. The cycle fixtures are admitted and must produce nonzero cycle-affected counts and failed reachability controls. Orphan, duplicate, missing/negative-ID, empty/count and bindable wrong-schema fixtures verify graph suppression; schema fixtures use otherwise valid nonempty data. Input tuples are compared before/after to establish read-only behavior. No synthetic error is inserted into real data.

Execution uses two threads, a 512MB DuckDB memory setting, 1GB spill limit and 60-second timeout per CLI phase. Private directories are under repository tmp and removed after completion. Final directory-size observations are not continuous peak measurements, and the memory setting is not a total-process cap. Source and historical-preflight hashes must remain unchanged.

```powershell
python validation/preflight_retailrocket_category_hierarchy.py --duckdb "E:/DuckDB/duckdb.exe" --output "data/retailrocket_category_hierarchy_preflight.json"
```

Measured results will be appended and saved in [aggregate evidence](../data/retailrocket_category_hierarchy_preflight.json). This step audits the graph; reusable root/depth mappings, other typed identifiers, unmatched-reference policies and time-aware event joins are subsequent work.

## Executed results

The assistant's isolated SQL61 preflight completed on 3 November 2026: **18 rows × 5 columns, 14 PASS controls and 4 INFO observations**, with no FAIL or BLOCKED rows. Learner execution and screenshot acceptance remain pending. The frozen method prefix above is unchanged, with SHA-256 `a5a5a9991287be24ca976055557803b0a5e9e83770ff5b546f2a80f0e64b0881`.

All **1,669 known category nodes reach a NULL-parent root**, across the **25 roots** in this snapshot. Cycle-affected nodes, repeated traversal rows and child edges beyond the depth bound are all zero. Together with the unique/nonmissing, nonnegative and closed-parent conditions, this establishes a rooted forest for the supplied reference. It does not validate the 167 unmatched property records, category meanings or any event-time association.

| Observation | Actual | Status |
|---|---:|---|
| max_root_depth | 5 | INFO |
| leaf_nodes | 1,307 | INFO |
| branching_nodes | 318 | INFO |
| max_children_per_node | 31 | INFO |

Depth counts edges from a root at depth zero: the maximum of five is not a claim of only five node levels. Leaves have no direct children, branching nodes have more than one, and the maximum direct-child count is 31. These are observed graph properties with NULL expectations; they were not selected as success thresholds.

The independent Python parent-chain oracle matched the full 18-row report and all **1,669 private node depths** against SQL's root-down traversal. The typed input tuple multiset also remained unchanged. No identifiers, node-level depths or paths were exported or logged. The public [aggregate evidence](../data/retailrocket_category_hierarchy_preflight.json) has report fingerprint `bfe1a20d4724ad252b11137ac1e5ddc39ed19096e3dd5110a92fc1277e86a61f`.

Three focused fixture families passed. Hand counts verified a branching forest with an isolated root, the singleton's depth zero, and a 12-node chain whose valid leaf is at N-1 without a boundary violation. An admitted three-node cycle with one feeder produced four cycle-affected nodes; self-cycle and rootless-cycle fixtures also failed reachability finitely. Orphan, duplicate, missing/negative-ID, empty/count and populated wrong-schema cases suppressed graph interpretation. A wrong expected root count failed its own control without suppressing otherwise valid traversal. Every fixture retained its input tuples.

The one real CLI run took **0.224 seconds**, including the frozen SQL55/60 reconstruction prefixes, one aggregate audit report, one private SQL traversal projection for depth comparison, and one private input projection. There are two SQL traversal evaluations, explicitly recorded as one report and one private projection; neither is a rerun of an earlier audit suite. Timing excludes hashes, Python reference work and fixtures and is not a benchmark.

The real private database was **798,720 bytes** before cleanup. The largest post-phase directory observation across fixture and real runs was **6,225,920 bytes**, including multiple fixture databases in one private directory; it is not a continuously measured peak. All private databases and spills were removed. The category source hash and metadata, **11 pinned code/evidence dependencies**, and **59 historical preflight files** remained unchanged.

This validation opened no learner database and read no property, event or M5 CSV. It created no reusable root/depth mapping or future database constraint. The next learner action is to execute the read-only SQL61 report and return its 18 rows with INFO distinguished from PASS.
