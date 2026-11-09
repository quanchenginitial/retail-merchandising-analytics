# Retailrocket enriched event fact

This SQL69 contract was frozen on 9 November 2026 before fixtures or source execution. It builds a reusable event fact after accepted SQL68 temporal-coverage evidence, with the same lookup policy and two explicit UTC fields. It supports later daily behaviour analysis; it does not yet define sessions, funnels or conversion rates.

## Table and interpretation

[SQL69](../sql/69_build_retailrocket_events_enriched.sql) creates **rr_mart.events_enriched** once. The first fifteen fields retain SQL68's private comparison order; two UTC columns are appended:

| Order | Field | Type |
|---:|---|---|
| 1 | timestamp | BIGINT |
| 2 | visitorid | BIGINT |
| 3 | event | VARCHAR |
| 4 | itemid | BIGINT |
| 5 | transactionid | BIGINT |
| 6 | categoryid_value | VARCHAR |
| 7 | categoryid_from_ms | BIGINT |
| 8 | categoryid_to_ms | BIGINT |
| 9 | categoryid_source_file | VARCHAR |
| 10 | categoryid_coverage | VARCHAR |
| 11 | available_value | VARCHAR |
| 12 | available_from_ms | BIGINT |
| 13 | available_to_ms | BIGINT |
| 14 | available_source_file | VARCHAR |
| 15 | available_coverage | VARCHAR |
| 16 | event_timestamp_utc | TIMESTAMP |
| 17 | event_date_utc | DATE |

Every one of the 2,756,101 original event occurrences is retained, including 460 exact duplicate surplus occurrences. No invented unique event ID, row deduplication or transaction/session consolidation is introduced. transactionid remains NULL for nontransaction events. Each property's value, boundaries and source_file are nullable when its coverage is BEFORE_FIRST or NO_HISTORY; a MATCHED observation may have a NULL final endpoint. The table has no asserted unique event key.

For each item and property independently, the greatest recorded observed_from_ms at or before the event is selected, subject to the accepted [from,to) convention. Exact next-start events select the next observation. BEFORE_FIRST means history exists but begins later; NO_HISTORY means no supplied history exists for that item/property. Neither case receives a future value or a fabricated zero. Two ASOF LEFT JOINs preserve the left occurrences, consistent with DuckDB's [ASOF documentation](https://duckdb.org/docs/1.5/guides/sql_features/asof_join). Complete unique interval keys and adjacent endpoint chains are checked before lookup; ASOF alone does not establish these conditions.

MATCHED means a technical association to an observation, not verified real-world state. An open-tail match is the last recorded observation with no later supplied boundary; it establishes neither unlimited freshness nor inventory truth. No expiry cutoff is introduced. Category values and provenance remain original text, including leading-zero category spellings, and no category-tree reference check or repair occurs. A temporally matched category may still be unresolved in the category tree. Open-tail counts are subsets of MATCHED, not extra mutually exclusive classes.

event_timestamp_utc is make_timestamp_ms(timestamp), a TIMESTAMP interpreted explicitly as UTC; event_date_utc is its DATE. Milliseconds are preserved without floating-point epoch conversion or connection-timezone-dependent timestamptz casts. The source integer remains present. The conservative supported source range is 0–253402300799999 milliseconds. These columns make later daily grouping reproducible without claiming all boundary dates were completely observed.

## Construction and checks

The accepted SQL68 source and guarded-join design is reused: exact ordered input schemas; frozen nonempty populations; valid keys, times, event names and transaction nullability; original event duplicate surplus; interval property/value/provenance rules; unique interval candidate keys; exact LEAD endpoint chain; property counts; preserved join rows and valid, exhaustive coverage. The frozen inputs are rr_stg.events and rr_core.item_state_intervals. No raw CSV or category tree is read by learner SQL69.

The plain CREATE TABLE deliberately fails if the target exists. A singleton admission guard LEFT JOINs the expected rows and raises an error on any invalid source/lookup contract, including empty input, so failed admission cannot silently create an empty target. The accepted sources are never edited. Reruns use only the marked CHECKS query; no DROP, REPLACE or overwrite is provided.

The check query reconstructs the accepted expected enrichment, derives UTC fields, and compares every one of its seventeen fields with the persisted fact using EXCEPT ALL in both directions. This preserves multiplicity and proves all original event fields, observation fields, status and UTC fields together; a separate redundant five-field comparison is unnecessary. The exact seventeen-column ordered schema is checked. Invalid fact rows include missing/invalid event fields, invalid match values/provenance/status/boundaries, inconsistent unmatched nullable fields, and missing UTC fields. Exact timestamp roundtrip and date derivation have explicit controls. Duplicate surplus counts original five-field event tuples, not artificial row identifiers.

Source controls 1–11 are direct diagnostics; control 12 also includes all inherited lookup invariants. If source admission fails, controls 13–20 and all INFO values are NULL/BLOCKED. INFO values are counted from the persisted fact and released only after every control passes. Full multiset equality and invalid-row checks also prevent false coverage from being accepted. Missing referenced table/column structures may fail at SQL binding rather than returning a diagnostic report.

The report has 28 rows and five columns (check_order, check_name, actual, expected, status): twenty PASS controls and eight INFO observations on healthy data. actual/expected are integer counts or NULL. The schema and source-contract checks are 0/1 flags; differences count occurrence surplus, preserving duplicates.

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
| 13 | fact_rows | 2756101 |
| 14 | fact_schema_mismatch | 0 |
| 15 | invalid_fact_rows | 0 |
| 16 | fact_duplicate_surplus | 460 |
| 17 | expected_only_rows | 0 |
| 18 | fact_only_rows | 0 |
| 19 | timestamp_roundtrip_errors | 0 |
| 20 | utc_date_errors | 0 |
| 21 | categoryid_matched_rows | NULL; INFO |
| 22 | categoryid_before_first_rows | NULL; INFO |
| 23 | categoryid_no_history_rows | NULL; INFO |
| 24 | categoryid_open_tail_match_rows | NULL; INFO |
| 25 | available_matched_rows | NULL; INFO |
| 26 | available_before_first_rows | NULL; INFO |
| 27 | available_no_history_rows | NULL; INFO |
| 28 | available_open_tail_match_rows | NULL; INFO |

## Independent bounded validation

The validator reuses SQL68's independent three-CSV matcher. It reads all original event occurrences and selects only categoryid/available observations from both property CSVs, externally sorts numeric keys in chunks of at most 50,000 rows, derives interval boundaries by source lookahead, and binary-searches the two histories for each current event item. Only current-item histories are buffered, with a 50,000-row cap that aborts rather than filters if exceeded. Remaining property history is drained and reconciled, including items unused by events. Event sorting includes numeric item/time/visitor and transaction NULL-before-nonnegative ordering; exact duplicates remain separate occurrences.

The expected seventeen-field rows add UTC text and date derived independently from an aware UTC epoch plus integer Python timedelta(milliseconds=...). The private target stream formats its TIMESTAMP as six fractional digits with an explicit Z convention and its DATE as ISO date. Every field of all 2,756,101 rows must match; explicit __NULL__ markers preserve nullable transaction and observation fields. This comparison reads the persisted fact directly, rather than another SQL join result. Independently accumulated source/match counts reconstruct the entire report.

Focused synthetic fixtures cover numeric ordering across chunks, all coverage classes, zero and exact next-start boundaries, one-property histories, open tails, retained duplicate events, NULL/zero transaction IDs, millisecond precision and UTC date crossing. Existing-target creation must fail without altering its contents. Invalid source/schema/key/chain inputs must fail atomically without a fact table. Same-count fact mutations in original fields, property provenance, coverage, UTC timestamp/date, plus a target schema mutation must be detected; INFO must block. Checks-only execution is read-only. The prior broad validation suites are not rerun.

One bounded real-source preflight uses four CLI phases: frozen SQL56/65/67 property/interval creation prefixes; frozen SQL54/63 event creation prefixes; SQL69 creation plus checks once; and the direct read-only seventeen-field target stream. Two threads, 1GB memory, 2GB spill and a 120-second timeout apply to each phase. At least 6GB free space and a 5GB private-directory budget are required; post-phase size observations are not continuous peak measurements. Source chunk sorting is timed separately. The database byte hash before and after the final read-only stream must remain identical.

Fresh hashes and metadata for all three source CSVs, pinned dependency hashes and all 67 historical preflight files must remain unchanged. Private source chunks contain records temporarily and are removed together with the private database and spills. No learner database or category CSV is opened. Real source identifiers and histories are processed only during private validation and are not uploaded or logged. Public artifacts contain aggregate evidence only. This preflight verifies reproducible materialization, not inventory, freshness, reference validity, conversion, monetary or causal outcomes.

```powershell
python validation/preflight_retailrocket_events_enriched.py --duckdb "E:/DuckDB/duckdb.exe" --output "data/retailrocket_events_enriched_preflight.json"
```

Measured results will be appended after the frozen contract and saved in [aggregate evidence](../data/retailrocket_events_enriched_preflight.json). Learner SQL69 execution follows the assistant preflight.

## Pre-recovery resource amendment

The first bounded real-source attempt completed both creation-prefix reconstruction phases but returned a nonzero CLI exit during SQL69 creation/checks. It did not reach the 120-second timeout. Its error category was discarded by the original privacy-preserving harness, so the cause is unknown; no out-of-memory diagnosis is claimed. No result evidence was issued. Its private database, source chunks and spills were automatically removed, and no learner database was opened.

Before any recovery execution, one recovery attempt is authorized with SQL69 semantics unchanged. Only the creation/check phase receives a bounded allowance of **2GB memory and 4GB spill**, still with two threads and a 120-second timeout. Reconstruction and the final read-only stream retain **1GB memory, 2GB spill and 120 seconds**. Admission becomes **8GB free space and a 7GB private-directory budget**. This allowance addresses a plausible wide-comparison resource demand without asserting the unknown cause.

The harness now reports only a whitelisted error category and whether a private construction-complete marker was reached; row-bearing stderr remains withheld. If the recovery fails, its owned private reconstruction directory may be retained temporarily for targeted inspection/reuse rather than another raw-source reconstruction. It must be cleaned before recovery work ends. Successful execution cleans it automatically. Evidence will disclose both the initial unknown failure and the recovery, separate attempt counters and the enlarged phase settings; it will not claim single-attempt or first-pass success.

The preceding 10,590-byte frozen contract is preserved exactly (SHA-256 429c848a03ae1e3f1c965e6af8741c22582683b1bcd6f2f761ea2fb18676c644). This amendment changes resource/error handling, not the 17-field schema, matching policy, exact multiset checks or independent source comparison.

## Executed results

The assistant's isolated SQL69 recovery preflight completed on 9 November 2026. It created **rr_mart.events_enriched with 2,756,101 rows and 17 columns** and returned **28 report rows: 20 PASS controls and 8 INFO observations**, with no FAIL or BLOCKED rows. Learner SQL69 execution remains pending. The original 10,590-byte frozen contract and the pre-recovery amendment are preserved; their combined 12,517-byte prefix has SHA-256 `4ef7c43f3a4b8069c4cccb846fc159b54d65cf7a6766deda1da2cf3ca04ff689`.

There were **two real-source attempts**, not a first-pass success. The initial attempt completed property and event reconstruction, then encountered an unknown non-timeout CLI failure during creation/checks under 1GB memory and 2GB spill. Its row-bearing diagnostics were withheld and the category was not retained, so its cause cannot be established. Its private files were cleaned and no success evidence was issued. The approved recovery left SQL69 unchanged and used 2GB memory/4GB spill only for creation/checks. The construction-complete marker was reached and the full report passed. Other recovery phases retained 1GB memory/2GB spill; all four phases retained the 120-second limit. The resource change is not evidence that the original failure was caused by memory pressure.

All **2,756,101 original event occurrences**, including **460 exact duplicate surplus occurrences**, remain in the fact. The full seventeen-field expected-only and fact-only multiset differences are both zero. Exact ordered schema, valid fact fields, source interval chains and lookup contracts pass. UTC timestamp roundtrip and date errors are zero. The two appended UTC fields preserve the source millisecond timestamp and support explicit UTC daily grouping.

| Property | MATCHED | BEFORE_FIRST | NO_HISTORY | Open-tail matches, included in MATCHED |
|---|---:|---:|---:|---:|
| categoryid | 2,099,173 | 401,343 | 255,585 | 1,924,845 |
| available | 2,224,316 | 276,200 | 255,585 | 1,127,773 |

Each property's first three classes reconcile to the full event population. Open-tail counts are subsets, not a fourth class. Unmatched values remain NULL without backward fill. MATCHED and its retained provenance establish the stated last-recorded observation association, not verified inventory, freshness or category-reference validity.

The independent Python process read all three source CSVs, selected **2,291,853 named observations** from **20,275,902 property rows**, derived their interval boundaries, and independently matched all events. The complete direct persisted-fact stream of **2,756,101 rows × 17 fields** matched exactly, including original event values, duplicate multiplicity, original category/availability text and provenance, coverage, nullable ends, and independently derived UTC timestamp/date. Every source property interval was reconciled, including histories unused by events. The current-event-item history buffer maximum was **36 rows**, within its 50,000-row cap. This is the measured maximum for the event items buffered during this run.

All **four focused fixture families** passed: persisted-field/numeric-order/coverage-boundary/duplicate/UTC precision and date-crossing cases; existing-target rejection without change; **six same-count content, coverage, provenance, UTC or schema mutations** detected with INFO blocked; and **fourteen invalid-input cases** rejected atomically without a target, with checks-only dependencies blocked. Existing-target and read-only fixture hashes remained unchanged. The final real database hash before and after the direct read-only comparison also remained identical.

Successful-recovery property selection/sorting and event sorting took **31.431** and **27.814 seconds**. Property reconstruction took **38.990 seconds**, event reconstruction **16.338 seconds**, SQL69 creation/checks **60.314 seconds**, and the complete direct comparison **71.345 seconds**. These measurements exclude the initial failed attempt, hashing and fixtures, and are not performance benchmarks.

The recovery used **46 property chunks** totalling **139,673,953 bytes** and **56 event chunks** totalling **96,993,967 bytes**. The database measured **537,669,632 bytes** before cleanup; the largest post-phase private-directory observation was **774,337,552 bytes**, not a continuous peak. All private databases, source chunks and spills from both attempts are removed; no recovery directory remains.

Fresh hashes and metadata of all **three source files**, **25 pinned dependencies**, and all **67 historical preflight files** remained unchanged during the successful recovery. No learner database or category CSV was opened. Real identifiers and histories were processed only in private validation and were neither uploaded nor logged. The [aggregate evidence](../data/retailrocket_events_enriched_preflight.json) records the attempt/resource disclosure, complete comparison, cleanup, and report fingerprint `780838696b74c8d9ad107214609d4dc0735aebabaeff307938e60893e02e5c2f`.

The materialized fact is ready for learner reproduction and later daily behaviour analysis. This step does not yet define sessions, visitor conversion denominators, order consolidation, inventory quantities, category-reference repair, monetary outcomes or causality.

## Learner screenshot acceptance — 9 November 2026

The learner supplied the SQL69 DBeaver result on 9 November 2026 (Australia/Sydney). All **28 rows × 5 columns, 140 fields** are completely visible and match: **20 PASS controls**, **8 INFO observations**, all twenty-eight complete check labels and all eight displayed NULL expectations. No labels or values were cropped or reconstructed. See the [learner acceptance record](../data/retailrocket_events_enriched_learner_acceptance.json).

The visibility accounting is **28 integer row orders + 48 integer actual/expected values + 8 NULL expectations + 28 complete labels + 28 statuses = 140 fields**. Thousands separators are removed for JSON integer storage; displayed [NULL] expectations remain JSON null. The complete ordered report fingerprint is `780838696b74c8d9ad107214609d4dc0735aebabaeff307938e60893e02e5c2f`. This fully visible SQL69 screenshot does not alter the separate five-label visibility caveat recorded for the earlier SQL68 screenshot.

The accepted fact snapshot retains **2,756,101 event occurrences** and **460 exact duplicate-surplus occurrences** under the **17-field schema contract**. Fact row/schema/content controls, both complete expected/fact reconciliation directions, timestamp roundtrip and UTC date checks pass. The original event fields and accepted property-match fields remain preserved alongside the appended UTC timestamp and date.

The eight INFO values remain unchanged: category **2,099,173 MATCHED**, **401,343 BEFORE_FIRST**, **255,585 NO_HISTORY**, and **1,924,845 open-tail matches**; availability **2,224,316 MATCHED**, **276,200 BEFORE_FIRST**, **255,585 NO_HISTORY**, and **1,127,773 open-tail matches**. Each property's three coverage classes reconcile to the entire fact population. Open-tail values are matched subsets, not additional exclusive classes. Their NULL expectations remain descriptive report cells, not missing verification.

All **17,825 prior method bytes** are preserved byte for byte, including the **original 10,590-byte frozen contract**, the pre-recovery amendment within the **12,517-byte amended prefix**, and the full executed-results account. That history still records **two assistant source attempts**: an initial unknown non-timeout CLI failure followed by the approved successful recovery. Its unknown cause, resource distinction and cleanup record are not rewritten or relabelled as first-pass success. The current learner screenshot is separate evidence; no assistant source attempt was made for this acceptance.

No source CSV, learner database, SQL preflight or fixture was opened or rerun for acceptance. No screenshot, event identifiers or event/property histories were copied to the repository. Frozen SQL, validator, preflight and dependencies remain unchanged. Historical learner-pending statements remain intact; this appended record establishes current learner acceptance.

The table provides a preserved event-level input for later descriptive analysis. It adds no invented event identifier, deduplication policy, future backfill, freshness cutoff, category-reference repair, session/order definition, conversion rate, inventory quantity or monetary/causal outcome. UTC remains the explicit analysis convention rather than an established retailer-local business day. The screenshot verifies the displayed aggregate reproduction, not fresh direct database inspection or learner conceptual understanding.
