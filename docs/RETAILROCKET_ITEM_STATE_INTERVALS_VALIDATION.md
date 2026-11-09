# Retailrocket observation-based item-state intervals

This SQL67 contract was frozen on 9 November 2026 before execution. It follows the accepted [named observation stage](../data/retailrocket_item_state_observations_learner_acceptance.json) and [observation time audit](../data/retailrocket_item_state_time_learner_acceptance.json). The purpose is to express how consecutive recorded observations will be assigned to a time range in later analyses, while preserving the underlying history.

## Meaning and grain

[SQL67](../sql/67_build_retailrocket_item_state_intervals.sql) creates **rr_core.item_state_intervals** from **rr_stg.item_state_observations**. It retains all **2,291,853 observations**: **788,214 categoryid** and **1,503,639 available** rows. There is no deduplication or collapse of consecutive equal values.

The ordered target columns are **itemid BIGINT**, **property VARCHAR**, **value VARCHAR**, **observed_from_ms BIGINT**, **observed_to_ms BIGINT or NULL**, and **source_file VARCHAR**. Each target row corresponds to one source observation. The candidate key is (itemid, property, observed_from_ms); this is an audited condition, not a declared database key constraint.

observed_from_ms is the original timestamp. observed_to_ms is the next timestamp within the same itemid/property history, computed by LEAD with numeric timestamp ordering. The assignment convention is **[observed_from_ms, observed_to_ms)**: include the start and exclude the next observation's start. An instant before the first observation has no match; the value is not filled backwards. At the exact next start, the next observation takes over under this convention.

The final row in each history has a NULL end, meaning **no later observation is recorded in the supplied selected history**. It does not prove unlimited freshness, actual continuous availability, a precisely timed business change or a known commercial validity period. No age cap or freshness policy is established here. These are observation-based intervals for analysis, not confirmed inventory periods. No global cutoff, synthetic end date, current-state selection, event join or event-impact count is introduced.

The missing final boundary is right-censored: the actual next update time is unknown. Different item/property histories may start or end on different dates despite the combined history's global date coverage. A later last-known-state event association must separately define its observation-window and staleness policy.

Property values and source_file provenance remain exact original text. Category values such as '001' are retained without numeric normalization. The earlier unmatched category-reference cohort is preserved through complete source projection equality; this step does not read the category tree, recount or repair that cohort. Availability remains a source 0/1 flag, not stock quantity. Equal consecutive original text values are counted descriptively but their rows are retained.

## Guard and construction

The source must have the exact five-column typed SQL65 schema/order, the frozen total and per-property counts, and nonempty input. Required keys and values must be present; itemid must be nonnegative, timestamp must lie in the already audited range 0–253402300799999, category values must be ASCII digits fitting BIGINT, availability values must be literal '0'/'1', and provenance must name one of the two accepted property files. The (itemid, property, timestamp) source key must be unique. No conflicting or duplicate source key is resolved automatically.

Diagnostics use TRY_CAST for numeric source fields, while exact schema admission remains mandatory. Plain CREATE TABLE protects an existing destination. A singleton guard LEFT JOINed to the expected interval rows, with guarded CASE in every output column, makes invalid or empty input fail atomic creation rather than leave an empty/partial target. CREATE SCHEMA IF NOT EXISTS can still create an empty schema; no whole-script rollback is claimed.

If the target already exists, retain it and run only the query after **-- CHECKS: if rr_core.item_state_intervals already exists, run only the query below.** That query changes no table. It checks schema, populations, non-NULL required fields, timestamp ranges, finite end > start, values, provenance and candidate-key uniqueness. The optional observed_to_ms is excluded from missing-required checks.

Both directions of EXCEPT ALL compare all five original source fields after timestamp is renamed to observed_from_ms, preserving values, provenance and occurrence multiplicities. A separate comparison requires each endpoint to equal the source-derived next observation timestamp. Together with key uniqueness these cover all six target fields. The report also requires one open tail per item/property, only at the maximum start, finite link count = rows minus histories, and the same source/target history count. No current event table is needed.

## Frozen 24-row report

Output has **24 rows × 5 columns**: check_order, check_name, actual, expected and status. Counts are integers; INFO expectations are NULL. Valid input produces **20 PASS controls and 4 INFO observations**. INFO actual values are released only if all twenty controls pass; otherwise those four rows have NULL actual and BLOCKED status.

| Order | Check | Expected |
|---:|---|---:|
| 1 | source_rows | 2291853 |
| 2 | source_schema_mismatch | 0 |
| 3 | source_contract_violations | 0 |
| 4 | interval_rows | 2291853 |
| 5 | interval_schema_mismatch | 0 |
| 6 | categoryid_rows | 788214 |
| 7 | available_rows | 1503639 |
| 8 | missing_required_rows | 0 |
| 9 | invalid_start_rows | 0 |
| 10 | invalid_end_rows | 0 |
| 11 | invalid_value_rows | 0 |
| 12 | unknown_source_file_rows | 0 |
| 13 | candidate_key_surplus | 0 |
| 14 | source_only_rows | 0 |
| 15 | interval_only_rows | 0 |
| 16 | endpoint_mismatch_rows | 0 |
| 17 | open_end_group_errors | 0 |
| 18 | open_end_position_errors | 0 |
| 19 | finite_link_count_difference | 0 |
| 20 | interval_pair_count_difference | 0 |
| 21 | item_property_pairs | NULL; INFO |
| 22 | finite_intervals | NULL; INFO |
| 23 | open_intervals | NULL; INFO |
| 24 | unchanged_next_value_links | NULL; INFO |

source_schema_mismatch and source_contract_violations are 0/1 indicators. interval_schema_mismatch counts mismatched or missing column/type positions. invalid_end_rows counts supplied non-NULL ends that cannot be represented in the supported range or do not exceed the start. unchanged_next_value_links counts adjacent finite links whose two original text values are exactly equal; numeric category aliases are not normalized for this count. The four INFO counts are measured without inventing new expected targets.

## Independent bounded preflight

The [validator](../validation/preflight_retailrocket_item_state_intervals.py) reads only the two property CSVs. Python scans all source records, selects exact categoryid/available rows and checks their accepted key/value rules. It retains at most 50,000 selected tuples per sorted chunk, using the numeric key **(int(itemid), property, int(timestamp))**. This prevents lexicographic errors for variable-length numeric identifiers or timestamps. Chunk tuples retain original property value and source-file provenance.

A bounded heap merge and one-record lookahead independently produce the expected six-field intervals: the next numeric timestamp within the same history is the current end, and the last end is None. This independent sequence is compared completely, record by record, with one read-only target stream ordered numerically by itemid, property and observed_from_ms. The stream uses an explicit __OPEN__ marker for NULL endpoints so zero is never confused with missing. Source counters, history counts, finite/open counts and exact equal-value link counts independently reconstruct the full report. No giant Python source Counter or per-item dictionary is built for real data.

The temporary database uses only the frozen SQL56 raw import prefix and SQL65 typed creation prefix before one SQL67 creation/check run. Previous full comparisons are not rerun. The fixed four real CLI phases are raw reconstruction, typed reconstruction, SQL67 construction/report, and the target comparison stream. Each uses two threads, 1GB memory, a 2GB spill cap and a 120-second timeout, with a watchdog on the stream. Python sorting uses 50,000-row chunks; workspace free space must be at least 6GB and the private directory budget is 5GB. Directory observations are not continuous peaks, and memory settings are not a total-process memory guarantee.

Focused fixtures cover numeric ordering across multiple chunks, original category text, repeated equal values, multiple histories and a single-observation open tail. Synthetic instant lookups verify before-first absence, inclusive first start, between-observation assignment and exclusive next-start ownership; this does not join real events. Mutated endpoints and same-count provenance changes must be detected and block INFO. Invalid source identity/time/value/schema/count or duplicate/conflicting keys must reject atomic creation and leave source records unchanged; an existing changed target must survive a second CREATE.

Source hashes and metadata are checked before and after. Pinned code/evidence dependencies and all historical preflight files must remain unchanged. Private sorted chunks temporarily contain selected source records and are removed together with the database and spills. Only aggregate evidence and hashes are published. No learner database, event/category CSV, source identifiers, source histories or raw record export enters public artifacts or logs.

```powershell
python validation/preflight_retailrocket_item_state_intervals.py --duckdb "E:/DuckDB/duckdb.exe" --output "data/retailrocket_item_state_intervals_preflight.json"
```

Measured results will be appended to this method and saved in [aggregate evidence](../data/retailrocket_item_state_intervals_preflight.json). The next action remains learner execution and review. Later use must separately decide missing-history handling, freshness assumptions and event-time association; this model itself establishes no causal, inventory or conversion outcome.

## Executed results

The assistant's isolated SQL67 construction and checks completed on 9 November 2026: **24 rows × 5 columns, with 20 PASS controls and 4 INFO observations**. There are no FAIL or BLOCKED rows. Learner SQL67 execution and screenshot acceptance remain pending. The frozen 10,286-byte method prefix remains unchanged, with SHA-256 `fd0918667f1e3b42648fd6e0e5be018a564cbd68b18ba62103e7d3bff3bfe060`.

The interval table retains all **2,291,853 selected observations**, comprising **788,214 categoryid** and **1,503,639 available** rows. Source and target schemas, required fields, timestamp ranges, finite endpoint ordering, value rules, provenance and candidate-key uniqueness passed. Both directions of the original five-field projection comparison contain zero differences, and every endpoint equals its source-derived next observation timestamp. Each history has exactly one open tail, only at its last observed start; finite-link and history counts reconcile.

The four INFO values have NULL expectations:

| Observation | Measured value |
|---|---:|
| Item/property histories | 834,106 |
| Finite intervals | 1,457,747 |
| Open final intervals | 834,106 |
| Adjacent links with equal original text values | 1,260,380 |

Finite and open intervals sum to **2,291,853**. Each open tail records an unknown next boundary in the supplied history. No global end, freshness allowance or confirmed business validity period is inferred. Equal-value adjacent observations remain separate; this step does not collapse states or normalize category values.

Python independently scanned both property CSVs and selected the two named properties, reconciling **20,275,902 raw records** and **2,291,853 selected records**. Numeric sorting by itemid, property and timestamp and bounded one-record lookahead reconstructed every endpoint. The complete ordered stream of **2,291,853 intervals × six fields** matched that independent source-derived sequence, including exact value text, source provenance and NULL endpoints. The complete 24-row report and all four INFO counts matched the independent reference. The target stream used an explicit __OPEN__ marker for missing endpoints; the private database hash was identical before and after that read-only comparison.

All **three fixture families** passed. Eight selected observations across four small numeric-sort chunks verified variable-length identifier/time ordering, original category text, two retained equal-value links, multiple histories, single/open tails and the complete six-field comparison. Synthetic instant probes verified no match before the first observation, inclusion at the first start, between-start assignment and ownership by the next observation at its exact start. These probes used synthetic instants only, without real event records. A nonadjacent finite endpoint and a same-count provenance mutation were detected and blocked all INFO values; a second CREATE preserved the existing changed target. **Thirteen invalid-source subcases** rejected creation atomically and retained source fixtures, covering empty/wrong-count input, missing or invalid identity/time/value/provenance, duplicate/conflicting keys and wrong typed schema/order.

The independent two-source selection and numeric external sort took **27.776 seconds**. Raw and typed prefix reconstruction took **24.435** and **10.256 seconds**. SQL67 construction/checks and the complete interval comparison stream took **12.717** and **9.861 seconds**. These timings exclude hashing and fixture work and are not performance benchmarks. All four CLI phases stayed within the fixed two-thread, 1GB memory, 2GB spill and 120-second per-phase limits.

Python created **46 private sorted chunks**, containing only selected source tuples and totalling **139,673,953 bytes**. The private database was **442,773,504 bytes** before cleanup; the largest post-phase directory observation was **582,447,457 bytes**, not a continuously measured peak. Every temporary database, spill and selected-record chunk was removed. No real source records or identifiers entered public artifacts or logs.

Both property source hashes and metadata, **12 pinned code/evidence dependencies**, and **65 historical preflight files** remained unchanged. No learner database, event/category CSV or historical full comparison suite was opened or rerun. The [aggregate evidence](../data/retailrocket_item_state_intervals_preflight.json) records report fingerprint `4f725b4f0e4ed343603dedd78345514814047836a63123358015deccc17f82ef`, independent source/history counts, six-field matching, mutation tests, resource observations and cleanup evidence.

SQL67 establishes an observation-based [from,to) assignment model. The unknown final boundary remains right-censored, and histories may have different starts and ends. Missing-history handling, staleness limits and real event association remain subsequent decisions. This step establishes no inventory quantity, confirmed availability duration, conversion rate, causality or monetary outcome. The next action remains learner execution and screenshot review.
