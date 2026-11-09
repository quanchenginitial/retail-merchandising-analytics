# Retailrocket event-to-observation temporal coverage audit

This SQL68 contract was frozen on 9 November 2026 before execution. It follows accepted [typed events](../data/retailrocket_events_staging_learner_acceptance.json) and [observation-based intervals](../data/retailrocket_item_state_intervals_learner_acceptance.json). The purpose is to measure whether each recorded event has an eligible earlier category and availability observation, preserving events without usable history rather than filling future values backwards.

## Matching policy and interpretation

[SQL68](../sql/68_audit_retailrocket_event_property_coverage.sql) reads **rr_stg.events** (2,756,101 occurrences) and **rr_core.item_state_intervals** (2,291,853 observations). It creates no persistent fact table and changes neither input. Each of the two properties is matched independently by itemid to the greatest observed_from_ms less than or equal to the event's timestamp. The accepted [from,to) convention then requires the event to be strictly before a finite observed_to_ms. An event exactly at the next start belongs to the next observation.

The query uses two ASOF LEFT JOINs with explicit equality and inequality predicates and explicitly projects both the event timestamp and property interval boundaries. DuckDB's [ASOF join documentation](https://duckdb.org/docs/1.5/guides/sql_features/asof_join) describes at-most-one right match per left row and preservation of unmatched left rows. The source interval key and complete adjacent endpoint chain are checked before admission; ASOF alone could hide duplicate keys, overlapping intervals or gaps, so those conditions must independently pass first.

For each property, coverage has three mutually exclusive statuses:

| Status | Meaning |
|---|---|
| MATCHED | An observation exists at or before the event and is assigned under the accepted interval convention. |
| BEFORE_FIRST | That item's property history exists, but its first recorded start is later than the event; no future value is filled backwards. |
| NO_HISTORY | No history for that item/property exists in the supplied selected history. This is not a claim that the product or real property did not exist. |

Any other unmatched case is classified INVALID and causes the coverage partition control to fail. For each property the three valid classes must sum to **2,756,101 event occurrences**. Open-tail matches are a **subset of MATCHED**, not a fourth class; they are never added again when reconciling coverage.

A match to a NULL final endpoint means the **last recorded observation** was selected because no later observation is present. It does not prove the property remained true, confirm inventory or establish freshness. No expiry age, global cutoff or backward fill is introduced. This step measures coverage of that explicitly stated lookup policy, not verified business-state accuracy. Real state changes, collection completeness and a later staleness policy remain separate questions.

All five original event fields and every occurrence are retained, including the accepted **460 exact duplicate surplus rows**. No visitor/session/order deduplication occurs. Category values and source-file provenance remain original text, including numeric-looking category spellings. No category-tree lookup or reference repair, M5 link, conversion measure, funnel or monetary interpretation is performed. A covered category value can still be an unmatched category reference; temporal coverage does not resolve that separate issue.

## Admission and frozen report

Admission requires exact ordered input schemas, nonempty frozen event/interval populations, the accepted full-five-field event duplicate surplus, valid event identifiers/time/event/transaction-nullability rules, and valid interval identifiers, property values, provenance and supported time ranges. The interval candidate key must be unique, the end of each interval must equal the next start within its item/property history, and the final end must be NULL. Frozen interval counts are **788,214 categoryid** and **1,503,639 available**. Numeric diagnostics use TRY_CAST while exact typed schema admission remains mandatory. The audit range remains 0–253402300799999 milliseconds.

Both event and interval inputs to the joins are gated to empty if any prerequisite fails. Controls 1–12 remain direct diagnostics; derived controls 13–20 and INFO rows 21–28 become NULL/BLOCKED. On admitted data, row preservation, future-match absence, finite-end boundary compliance and exhaustive coverage partitions are checked. INFO values are released only if **all twenty controls pass**.

The output has **28 rows × 5 columns**: check_order, check_name, actual, expected and status. Counts are integers; INFO expectations are NULL. Healthy data produces **20 PASS controls and 8 INFO observations**.

| Order | Check | Expected |
|---:|---|---:|
| 1 | event_rows | 2756101 |
| 2 | event_schema_mismatch | 0 |
| 3 | invalid_event_rows | 0 |
| 4 | event_duplicate_surplus | 460 |
| 5 | interval_rows | 2291853 |
| 6 | interval_schema_mismatch | 0 |
| 7 | invalid_interval_rows | 0 |
| 8 | interval_candidate_key_surplus | 0 |
| 9 | interval_chain_errors | 0 |
| 10 | categoryid_interval_rows | 788214 |
| 11 | available_interval_rows | 1503639 |
| 12 | source_contract_violations | 0 |
| 13 | categoryid_joined_rows | 2756101 |
| 14 | available_joined_rows | 2756101 |
| 15 | categoryid_future_match_rows | 0 |
| 16 | available_future_match_rows | 0 |
| 17 | categoryid_boundary_error_rows | 0 |
| 18 | available_boundary_error_rows | 0 |
| 19 | categoryid_coverage_partition_difference | 0 |
| 20 | available_coverage_partition_difference | 0 |
| 21 | categoryid_matched_rows | NULL; INFO |
| 22 | categoryid_before_first_rows | NULL; INFO |
| 23 | categoryid_no_history_rows | NULL; INFO |
| 24 | categoryid_open_tail_match_rows | NULL; INFO |
| 25 | available_matched_rows | NULL; INFO |
| 26 | available_before_first_rows | NULL; INFO |
| 27 | available_no_history_rows | NULL; INFO |
| 28 | available_open_tail_match_rows | NULL; INFO |

Schema mismatch and source_contract_violations are 0/1 indicators. Invalid row controls count records failing at least one relevant rule. The joined-row controls share the one-wide-row-per-event result of the two left joins, with separate property matches. Partition difference is valid-status count minus source event count, not a coverage percentage. Duplicate surplus is occurrence count minus distinct complete five-field event tuples; it is a preservation control, not a deduplication instruction.

## Independent bounded preflight

The [validator](../validation/preflight_retailrocket_event_property_coverage.py) reads only events.csv and the two property CSVs. Property sources use the accepted SQL67 numeric external-sort/lookahead helpers to derive intervals independently from original observations. Events are independently typed from source strings and sorted in chunks of at most 50,000 rows by **(itemid, timestamp, visitorid, event, transactionid with NULL ordered before nonnegative IDs)**. Every occurrence is retained. The sorted event stream also independently checks exact duplicate surplus by adjacent complete-row comparison.

For each current event item, Python retains only that item's two property histories and uses binary search to select the latest start at or before each event. It checks the finite endpoint and independently assigns MATCHED, BEFORE_FIRST or NO_HISTORY. The explicit current-item history budget is **50,000 rows**; exceeding it aborts rather than truncating or filtering source history. The observed maximum buffer size is recorded. No all-item history dictionary or event collection is built. Property rows outside current event items are streamed past; the remaining property iterator is drained so complete source counts and history construction are still reconciled.

One private read-only SQL stream contains **2,756,101 wide rows × 15 fields**: the five original event fields, followed for each property by value, matched start, matched end, source_file and coverage status. It is sorted by the same numeric event key. Explicit __NULL__ markers preserve transaction NULL and missing match fields; a matched NULL end is distinguished by its MATCHED status. Every field and every occurrence, including exact duplicates, must match Python's source-derived sequence. A second 5.5-million-row normalized join is unnecessary. Independent counts reconstruct the complete 28-row report and reconcile each three-way coverage partition; open-tail counts remain subsets.

The fixed four real CLI phases are: the frozen SQL56/65/67 creation prefixes for properties and intervals; the frozen SQL54/63 event creation prefixes; one read-only SQL68 report; and the read-only wide comparison stream. No earlier full audit suite is rerun. The database byte hash must stay identical across the read-only report and stream. Each CLI phase uses two threads, 1GB memory, a 2GB spill cap and a 120-second timeout, with a watchdog on the stream. At least 6GB workspace free space and a 5GB private directory budget are required. Python source chunks and the current-item buffer each have a 50,000-row cap. These are bounded settings, not a guarantee on total process memory; directory observations are not continuous peaks.

Focused synthetic fixtures cover unmatched items, one-property-only histories, events before the first observation, exact starts and ends, between-start assignment, matched open tails, preserved duplicate events, transaction NULLs and numeric ordering across chunks. Invalid input/schema/time/key/property-chain conditions must block derived metrics, and malformed overlap/gap/open-tail chains must not be hidden by ASOF. Existing source and fixture database bytes stay unchanged under read-only audits.

All three source file hashes and metadata, pinned code/evidence dependencies and historical preflight files are checked before and after. Private sorted chunks temporarily contain source records; they are removed with the database and spills. No learner database, category CSV or real identifiers/history records enter public artifacts or logs. Public outputs are aggregate evidence, method, code and hashes only.

```powershell
python validation/preflight_retailrocket_event_property_coverage.py --duckdb "E:/DuckDB/duckdb.exe" --output "data/retailrocket_event_property_coverage_preflight.json"
```

Measured results will be appended and saved in [aggregate evidence](../data/retailrocket_event_property_coverage_preflight.json). Learner execution follows the assistant preflight. This read-only step establishes technical matching coverage under the stated observation policy; it does not validate business-state truth, freshness, inventory, category-reference quality, conversion or causality.

## Executed results

The assistant's isolated SQL68 read-only audit completed on 9 November 2026: **28 rows × 5 columns, with 20 PASS controls and 8 INFO observations**. There are no FAIL or BLOCKED rows. Learner SQL68 execution and screenshot acceptance remain pending. The frozen 10,863-byte method prefix remains unchanged, with SHA-256 `8cb849837dafdaa7f403afd653d42413062e471f80464fddadc0be170295bd30`.

All **2,756,101 original event occurrences** were retained through both property lookups, including the accepted **460 exact duplicate surplus rows**. The **2,291,853 input intervals**, both schemas, event/interval rules, unique interval keys and complete adjacent endpoint chains passed admission. Future matches, finite-end boundary violations and both coverage partition differences are zero.

The eight INFO counts have NULL expectations:

| Property | MATCHED | BEFORE_FIRST | NO_HISTORY | Open-tail matches: subset of MATCHED |
|---|---:|---:|---:|---:|
| categoryid | 2,099,173 | 401,343 | 255,585 | 1,924,845 |
| available | 2,224,316 | 276,200 | 255,585 | 1,127,773 |

Each property's first three columns sum to **2,756,101 occurrences**. The open-tail column is already included in MATCHED and must not be added again. BEFORE_FIRST events retain missing values rather than borrowing future observations; NO_HISTORY refers only to absence from the supplied item/property history. MATCHED confirms a technical association under the stated last-observation and [from,to) convention, not state truth, freshness, inventory availability or category-reference validity. No expiry threshold was introduced.

The independent Python source process scanned all **20,275,902 property records**, retained **2,291,853 named observations**, and sorted all **2,756,101 event occurrences**. It reconstructed interval endpoints from numeric source ordering and performed separate category/availability binary searches using only the current event item's histories. The largest current-item history buffer observed was **36 rows**, within the explicit **50,000-row** cap. This is a maximum for the histories buffered for event items during this run, not an unmeasured maximum over all source items.

The complete private stream of **2,756,101 rows × 15 fields** matched the independent source-derived sequence exactly: all five original event fields plus each property's value, start, end, source_file and coverage status. Duplicate event occurrences were compared separately and remained present. NULL transaction IDs, unmatched fields and matched open endpoints were preserved using explicit markers. All remaining property intervals were drained and reconciled, including histories without event use. The complete 28-row report and all coverage counts matched the independent reference. The database hash before and after the read-only report and stream was identical.

All **three fixture families** passed. Twelve synthetic events, including an exact duplicate and NULL/zero transaction IDs, were compared across six event chunks and three property chunks. Synthetic cases verified no history, pre-first history, exact starts and ends, between-start selection, one-property-only histories and last-recorded open tails. A deliberately one-row history budget aborted without filtering. **Fourteen invalid-prerequisite subcases** blocked every derived metric and INFO value; they covered empty/wrong-count inputs, schema or value failures, duplicate interval keys, overlapping and gapped chains, and a closed final tail. Fixture database hashes remained unchanged under the read-only audits.

Independent property selection/sorting and event sorting took **31.957** and **26.984 seconds**. Property/interval and event prefix reconstruction took **38.467** and **14.561 seconds**. The read-only SQL68 report and complete wide comparison stream took **4.647** and **57.992 seconds**. These observations exclude hashing and fixtures and are not performance benchmarks. All four CLI phases stayed within the fixed two-thread, 1GB memory, 2GB spill and 120-second per-phase limits.

Python created **46 property chunks** totalling **139,673,953 bytes** and **56 event chunks** totalling **96,993,967 bytes**. These private files contained source records temporarily and were all removed. The database was **539,242,496 bytes** before cleanup; the largest post-phase directory observation was **775,910,416 bytes**, not a continuously measured peak. All temporary databases and spills were removed, and no real identifiers or histories entered public artifacts or logs.

All three source file hashes and metadata, **19 pinned code/evidence dependencies**, and **66 historical preflight files** remained unchanged. No learner database, category CSV or historical full comparison suite was opened or rerun. The [aggregate evidence](../data/retailrocket_event_property_coverage_preflight.json) records report fingerprint `e6be3ad761ce64b831686ffd2185d82454a623ee70e730bd7d344a3d42b20fbf` and the complete occurrence comparison, buffer limits, read-only hashes, source reconciliation and cleanup checks.

SQL68 establishes coverage of the two temporal lookups without creating a fact table. It does not resolve missing history, set an expiry policy, repair category references or infer conversion, inventory, monetary or causal outcomes. The next action remains learner execution of this read-only query and screenshot review.

## Learner screenshot acceptance — 9 November 2026

The learner supplied the SQL68 DBeaver result on 9 November 2026 (Australia/Sydney). All **28 rows**, numeric actual/expected values, **8 displayed NULL expectations**, **20 PASS statuses** and **8 INFO statuses** are visible and match. **Five check-name endings are cropped at orders 17, 19, 20, 24 and 28**; their full names are resolved from visible prefixes, row order and the frozen SQL/report contract. Rows 8 and 18 have complete visible labels. See the [learner acceptance record](../data/retailrocket_event_property_coverage_learner_acceptance.json).

The visibility accounting is **28 integer row orders + 48 integer actual/expected values + 8 NULL expectations + 23 complete labels + 28 statuses = 135 fully visible fields**, plus **5 contract-resolved labels**. The report contains 140 positions, but not all 140 fields are claimed as fully visible. The acceptance's observed_rows stores null in the five cropped check_name cells; these visibility placeholders are distinct from the eight database NULL expectations. Conservative legible prefixes and full contract-resolved labels are recorded separately. The complete reconciled report fingerprint is `e6be3ad761ce64b831686ffd2185d82454a623ee70e730bd7d344a3d42b20fbf`.

Both joins retain **2,756,101 event occurrences**, including the accepted **460 exact duplicate-surplus occurrences**. Category coverage is **2,099,173 MATCHED**, **401,343 BEFORE_FIRST** and **255,585 NO_HISTORY**. Availability coverage is **2,224,316 MATCHED**, **276,200 BEFORE_FIRST** and **255,585 NO_HISTORY**. Each property's three classes reconcile to the complete event population. **1,924,845 category matches** and **1,127,773 availability matches** use open-tail observations; these are subsets of MATCHED, not fourth mutually exclusive classes. Future-match, interval-boundary and coverage-partition controls pass with zero discrepancies.

The audit uses the last recorded observation starting at or before an event under the accepted [from,to) convention. It does not fill earlier events with future attribute values. No freshness or observation-age cutoff is applied, and an open-tail match does not prove that a real-world state remains valid or fresh. Matching a category-value observation does not validate its category-tree reference. Unknown or unmatched values are not recoded as unavailable or stockout conditions.

No source CSV, learner database, SQL preflight or fixture was opened or rerun for acceptance. No screenshot, event identifiers or event/property histories were copied to the repository. Frozen SQL, validator, preflight and dependencies remain unchanged. All **16,285 prior method bytes**, including the **10,863-byte frozen contract prefix** and historical learner-pending statements, are preserved byte for byte; this appended record establishes learner acceptance with the stated visibility caveat.

This read-only step creates no production event fact table and introduces no deduplication policy, category-reference repair, session/order definition, conversion rate, inventory quantity or monetary/causal outcome. The screenshot is evidence of the displayed aggregate reproduction, not fresh direct database inspection or a test of conceptual understanding.
