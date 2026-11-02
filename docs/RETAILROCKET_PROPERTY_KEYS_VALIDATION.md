# Retailrocket property grain and raw-key audit

The following SQL57 contract was frozen on 3 November 2026, before computing new property-key outcomes. It follows the accepted raw import and asks whether repeated raw attribute records represent identical tuples, different values at the same candidate key, or overlap between physical source parts. It does not resolve those observations or create typed staging.

## Input and identity contract

[SQL57](../sql/57_audit_retailrocket_property_keys.sql) reads only **rr_raw.item_properties**. The five columns must be VARCHAR in the accepted order: timestamp, itemid, property, value, source_file. A schema guard rejects a different type/order contract. The learner query is read-only: no CSV reader, permanent/temporary table creation, update, deletion or join to another module is used. MATERIALIZED tuple and key CTEs reuse the large grouped intermediates.

All identities use exact original strings. There is no trimming, numeric canonicalization or timestamp conversion. Thus a numeric-looking value with different spelling remains a different raw value; later typed-key collision checks are a separate task.

- A candidate key **K = (itemid, property, timestamp)** is only a proposed observation grain, not an asserted unique database key.
- An exact tuple **T = (itemid, property, timestamp, value)** ignores source_file when identifying identical content. Each T group retains its raw multiplicity and whether it occurs in each physical part.
- Exact duplicate surplus is the sum of **n(T) − 1** across T groups. It counts excess raw occurrences, not duplicate groups or all rows involved in repetition.
- A conflicting candidate key has more than one distinct raw value, equivalently more than one T group within K. Rows in conflicting keys include **all raw occurrences** at those keys, including exact duplicates. These rows are not a separate additive partition from duplicate surplus.
- Cross-part exact tuples count T groups present in both parts once each. Cross-part candidate keys count K groups present in both parts once each, even if the parts carry different values. Neither count is a pairwise join count or a count of duplicate surplus rows.

Missing core fields include NULL or exact-empty timestamp, itemid, property or value. Unknown provenance includes NULL or any source_file other than the two accepted basenames. The grouping retains such rows; input controls flag them rather than silently filtering them. Distinct-item and distinct-property counts use non-NULL strings. Valid source input has no missing core fields. Grouping a NULL value still creates a value group, so it is not silently omitted from key reconciliation.

## Frozen 20-row report

The report has five columns: **check_order, check_name, actual, expected, status**. For valid input it contains **10 PASS controls and 10 INFO observations**. An INFO row has expected=NULL; this means no zero or other success target has been imposed, not a failed test. If any initial row-count, part-count, missingness or provenance control fails, the observations instead show BLOCKED, with their actual counts still visible. Such input must be resolved before interpreting those observations. A schema failure raises an explicit error.

| Order | Check name | Expected / role |
|---:|---|---|
| 1 | raw_rows | 20,275,902 |
| 2 | part1_rows | 10,999,999 |
| 3 | part2_rows | 9,275,903 |
| 4 | missing_core_rows | 0 |
| 5 | unknown_source_file_rows | 0 |
| 6 | distinct_items | NULL / INFO |
| 7 | distinct_property_names | NULL / INFO |
| 8 | distinct_item_property_pairs | NULL / INFO |
| 9 | candidate_keys | NULL / INFO |
| 10 | distinct_exact_tuples | NULL / INFO |
| 11 | exact_duplicate_surplus_rows | NULL / INFO |
| 12 | conflicting_candidate_keys | NULL / INFO |
| 13 | rows_in_conflicting_keys | NULL / INFO |
| 14 | cross_part_exact_tuples | NULL / INFO |
| 15 | cross_part_candidate_keys | NULL / INFO |
| 16 | part_rows_reconciled | Raw rows |
| 17 | tuple_rows_reconciled | Raw rows |
| 18 | key_rows_reconciled | Raw rows |
| 19 | exact_tuple_surplus_reconciled | Raw rows |
| 20 | key_value_groups_reconciled | Distinct exact tuples |

Rows 16–20 compare, respectively, the sum of the two part counts, summed tuple multiplicities, summed key multiplicities, distinct tuples plus exact surplus, and summed distinct-value-group counts across keys. These algebraic controls reconcile the report; they are not independent proof of source authenticity or correct business meaning. Duplicate and conflict counts remain observations regardless of their size. Distinct item/property/pair counts provide grain context, not guarantees of safe join keys.

## Bounded validation plan

The [validator](../validation/preflight_retailrocket_property_keys.py) reconstructs the raw input in one disposable private DuckDB database using only the frozen SQL56 import prefix. It does not rerun SQL56's four full comparisons or historical analysis suites. Fresh hashes and headers of the two source files must match the [independent standard-library source audit](../data/retailrocket_source_audit.json) and the [accepted SQL56 copy evidence](../data/retailrocket_properties_import_preflight.json). No other source CSV or learner database is opened. Both physical parts cover overlapping dates; they are not treated as separate date periods.

Small independent Python Counter fixtures will verify every output field for within-part and cross-part exact repetitions, multiple values at the same key, duplicates inside a conflict, shared keys with differing values, and exact-text distinctions. Invalid/missing input, an empty table and schema rejection are checked without broad historical suites. No full real-source Python Counter or row-level export is required or claimed. The real grouped audit will run once after implementation review.

The private preflight uses two threads, a 2GB DuckDB memory setting, an 8GB spill limit, a 12GiB task-directory budget and a 600-second timeout per phase. It requires 12GiB free disk initially and monitors a 2GiB reserve. Physical-memory availability is recorded. These controls do not guarantee total-process RAM use, and sampled disk observations do not measure a continuous peak. Private databases and spills are removed, and source/dependency and historical-preflight hashes must remain unchanged.

```powershell
python validation/preflight_retailrocket_property_keys.py --duckdb "E:/DuckDB/duckdb.exe" --output "data/retailrocket_property_keys_preflight.json"
```

Results will be appended after the bounded run and saved as [aggregate evidence](../data/retailrocket_property_keys_preflight.json). No real item identifiers, property names, raw values or keyed groups are published by this step. Preserving all source observations leaves future deduplication, conflict resolution, typed staging and as-of join decisions reviewable. Nothing here establishes a monetary amount, business event meaning, usable latest state or causal relationship.

## Executed results

The assistant's single real-source preflight completed on 3 November 2026 with **20 rows × 5 columns: 10 PASS controls and 10 INFO observations**, with no FAIL or BLOCKED rows. Learner SQL57 execution and acceptance remain pending. The original 7,022-byte method contract above is unchanged; its SHA-256 is `dd56b37a1ca2359634876f9985460ff7fdb19e40830a34616d32fa608944e5b0`.

| Observation | Actual | Status |
|---|---:|---|
| distinct_items | 417,053 | INFO |
| distinct_property_names | 1,104 | INFO |
| distinct_item_property_pairs | 12,003,814 | INFO |
| candidate_keys | 20,275,902 | INFO |
| distinct_exact_tuples | 20,275,902 | INFO |
| exact_duplicate_surplus_rows | 0 | INFO |
| conflicting_candidate_keys | 0 | INFO |
| rows_in_conflicting_keys | 0 | INFO |
| cross_part_exact_tuples | 0 | INFO |
| cross_part_candidate_keys | 0 | INFO |

All INFO expected cells remain NULL. The five observed zeros were not preset success targets. Each raw candidate key identifies one row in this supplied snapshot, and neither exact tuples nor candidate keys are shared across the two source parts. This does **not** establish uniqueness after type conversion, disjoint date windows, disjoint items/item-property pairs between files, or a general key guarantee for other snapshots. No row was removed and no deduplication or conflict policy was needed or applied by this audit.

All initial source controls matched 20,275,902 total rows, 10,999,999 part-one rows, 9,275,903 part-two rows, and zero missing-core or unknown-provenance rows. Every reconciliation returned 20,275,902 on both sides, including the summed key value groups versus distinct exact tuples. The full report is saved in the [aggregate preflight evidence](../data/retailrocket_property_keys_preflight.json), with fingerprint `55278e85394b3706bd57e61b9982ca31d1892d47a8426586bc6bf8836f2f8823`. The fingerprint uses ordered compact JSON arrays in the five-column order, each followed by LF; counts are integers and observation expectations are JSON null.

Three focused fixture families passed. Independent Python Counter/set calculations and explicit hand counts verified repetitions, same-key conflicts and cross-part distinctions. Additional tiny inputs verified unnormalized strings, NULL-valued groups, visible integrity failures with BLOCKED observations, the fixed empty-input report, and type/order rejection. An initial fixture caught DuckDB emitting promoted HUGEINT sums as JSON strings; casting only final report counts to BIGINT fixed serialization without changing raw identity, calculations or expected results, before the source run.

DuckDB 1.5.5 reconstructed the accepted raw table in **37.127 seconds** and completed the one grouped audit in **85.476 seconds**, for **122.603 seconds** total. Hashing and fixtures are excluded. The sampled peak private-directory size was **1,924,182,016 bytes**, approximately 1.92GB; the private database was 423,112,704 bytes before cleanup. These observations are not a performance benchmark or continuous peak measurement.

Both source hashes and metadata, all nine pinned code/evidence dependencies, and 55 historical preflight files remained unchanged. The private database and spills were removed. No learner database, other source CSV, SQL56 full-comparison rerun or historical suite was used; no real keyed groups or property values were exported or logged.

The next learner action is to run SQL57 and return the complete 20-row report, preserving visible expected=NULL cells and distinguishing INFO from PASS. Typed staging and later time-aware joins remain separate steps; observed raw-key uniqueness alone does not complete their validation.

## Learner screenshot acceptance — 3 November 2026

The learner screenshot shows **20 rows × 5 columns = 100 complete fields**: fifty integer values, ten explicit NULL expectations, twenty complete check names and twenty complete statuses. All five headers and the full exact_tuple_surplus_reconciled label are visible. There are **10 PASS controls and 10 INFO observations**, with no FAIL or BLOCKED rows and no visibility caveat.

The complete screenshot was independently transcribed before comparison with the frozen report. Numeric thousands separators were removed, and displayed [NULL] expectations were retained as JSON null; no label or value was reconstructed. Every field matches, with zero mismatches and the same report fingerprint shown above. The [learner acceptance record](../data/retailrocket_property_keys_learner_acceptance.json) contains the aggregate transcription, visibility counts and frozen fingerprints. INFO expectations remain NULL: the observed zeros are not success targets.

This later record establishes learner acceptance and supersedes the earlier learner-pending status and run request for current progress. The 7,022-byte method contract and the entire existing executed-results section are retained byte for byte as historical evidence. No learner database was opened, and no SQL, source audit, fixture or historical suite was rerun for this acceptance. SQL57, its validator, preflight and pinned prior evidence remain unchanged. No screenshot, real identifiers, property values or keyed groups are published, and learner conceptual understanding remains untested.

The accepted observations retain the raw-text and snapshot limits above. They do not establish uniqueness after type conversion, disjoint date/item coverage between parts, a valid current attribute state or safe event-time joins. Typed staging, further semantic checks and later time-aware joins remain separate work; no source observation was changed or removed by this acceptance.
