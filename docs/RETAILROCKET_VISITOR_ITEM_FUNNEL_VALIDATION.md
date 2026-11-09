# Retailrocket chronological visitor-item pair funnel

This SQL71 contract was frozen on 9 November 2026 before fixtures or source execution. The business question is: among observed visitor-item pairs with a view, how many later show a cart addition and then a later transaction event for the same pair? The result describes ordered progression in the supplied log. It does not define session conversion, person-level conversion, validated orders, causal effects or a fixed follow-up window.

## Cohort and strict chronological stages

[SQL71](../sql/71_analyze_retailrocket_visitor_item_funnel.sql) reads only timestamp BIGINT, visitorid BIGINT, event VARCHAR, itemid BIGINT and transactionid BIGINT from accepted rr_mart.events_enriched. It validates those five required names/types without asserting their positions or the full seventeen-column schema. It does not read either UTC field or any category/availability field.

The population is the complete supplied event observation. The cohort contains each distinct (visitorid,itemid) pair with at least one observed view. For each such pair:

1. first_view_ms is its earliest observed view timestamp.
2. first_cart_after_view_ms is its earliest addtocart timestamp **strictly greater** than first_view_ms.
3. first_transaction_after_cart_ms is its earliest transaction timestamp **strictly greater** than the qualifying cart timestamp.

A pair enters each nested stage at most once. Repeated views, carts, transactions and duplicate records do not create multiple pair entries. All original source occurrences, including accepted duplicate surplus 460, remain preserved; defining a distinct-pair cohort is not source-data deduplication. Same-millisecond events cannot establish order and never advance a stage through a tie. Earlier out-of-order activity does not prevent a later valid subsequence. A transaction with no qualifying earlier cart is excluded from the third stage, even if it follows a view. Pairs with no observed view never enter the cohort.

The algorithm uses minima after each preceding qualifying stage, not independent minima for all event types and not an unordered intersection of event sets. It therefore respects ordering for the same visitor-item pair. One visitor's other items and another visitor's events cannot complete that pair's chain.

The window is the full available observation, without session breaks or an expiry threshold. A qualifying sequence can span days or separate visits. Pairs first viewed near the observation end have less follow-up time, and earlier/later events may be unobserved. Excluded no-view paths and incomplete sequences must not be interpreted as proven abandonment. These boundary and unequal-follow-up limitations prevent treating the displayed shares as standardized conversion estimates.

## Three-row report and admission

The output is exactly **three rows × five columns**, ordered VIEW, VIEW_THEN_CART, VIEW_THEN_CART_THEN_TRANSACTION:

| Field | Definition |
|---|---|
| stage | The nested chronological stage label. |
| visitor_item_pairs | Distinct pairs reaching that stage within the observed log. |
| share_of_view_pairs_pct | Stage pair count divided by the viewed-pair cohort; four-place DECIMAL percentage. |
| step_rate_pct | Stage pair count divided by the immediately preceding stage; VIEW has NULL. |
| check_status | PASS for admitted sources and nonnegative nested counts; BLOCKED for invalid source admission; otherwise FAIL. |

For a positive viewed-pair cohort, VIEW's share is 100.0000. Any zero denominator yields NULL, never a fabricated zero or 100. A valid synthetic source with no views has all three pair counts zero and all shares/rates NULL. A viewed cohort with zero qualifying carts has a 0.0000 second-stage step rate and a NULL third-stage conditional rate. Percentages describe the stated pair population and observed ordering only. DuckDB CLI JSON serializes DECIMAL values as four-place strings; evidence preserves these strings and genuine NULLs.

Source admission requires the frozen 2,756,101 occurrences (2,664,312 view, 69,332 addtocart, 22,457 transaction), nonempty input, the five required field types, exact duplicate surplus 460, valid event labels and transaction-nullability rules, nonnegative identifiers and supported integer milliseconds from 0 through 253402300799999. Required fields are not imputed. If admission fails, all three metric columns are NULL for every stage and all statuses are BLOCKED. Missing required columns/tables may instead fail SQL binding. The learner query is entirely read-only and changes no session settings.

The three counts must satisfy viewed pairs >= qualifying cart pairs >= qualifying transaction pairs >= 0. No visitor identity is equated with a person and no transaction row or identifier is equated with a validated order. No event-row shares from SQL70 are used as funnel denominators.

## Independent event-only validation

The validator reads **events.csv only**. In a private database it executes only frozen SQL54/63 creation prefixes and creates a disposable five-column rr_mart.events_enriched projection. This stand-in validates SQL71's original-five-field readset; it does not recreate or reverify SQL69's seventeen-column enriched fact, its UTC derivation or its ten property fields. Those remain dependent on accepted earlier evidence. SQL69, SQL70 and previous full audit suites are not rerun. Neither property CSV nor the category CSV is read.

Python independently validates and types every original event record and sorts numeric keys by (visitorid,itemid,timestamp,event,transactionid with NULL before nonnegative IDs) in chunks of at most 50,000 rows. The merged stream is processed with only the current pair's first qualifying view/cart/transaction timestamps and counters. It never keeps an all-pair dictionary or an all-event list. Strict greater-than comparisons prevent same-time sort order from inventing a sequence. At each pair boundary, its nested stage flags are counted once. Earlier out-of-order activity is ignored until a valid chain exists; later valid events can still advance it.

A direct private read-only stream of all five fields must match every original source occurrence in that same numeric order. Exact duplicate multiplicity is independently counted from adjacent complete event tuples. Pair statistics are calculated while comparing the source stream. Independent Decimal arithmetic with four-place half-up rounding and explicit zero-denominator NULLs reconstructs all fifteen report cells. Report shares do not rely on SQL's pair outputs.

Focused synthetic fixtures cover strict same-millisecond exclusion, a later valid subsequence, carts/transactions before views, skipped-cart transactions, repeated events, one visitor across several items, several visitors, numeric ordering across chunks, no qualifying carts and a valid no-view cohort. Invalid source counts/schema/keys/event/transaction/time rules must block all metrics. Extra unqueried columns are allowed; a missing required column may produce a binding error. No additional property, session or window analysis is included.

The real preflight has three CLI phases: frozen event prefixes plus the disposable five-field projection; one read-only SQL71 report; one direct read-only five-field source comparison. Each uses two threads, 1GB memory, 2GB spill and a 120-second timeout. At least 6GB free workspace space and a 5GB private-directory budget are required. Python sort chunks are capped at 50,000 occurrences and funnel state is one pair at a time. These limits are bounds, not measured process-memory peaks.

The private database hash must remain unchanged across read-only report and stream. Fresh event-source hash/metadata, pinned dependencies and all 69 historical preflight files must remain unchanged. Private event chunks, database and spills are removed; real identifiers are processed privately and are not logged or uploaded. No learner database is opened. Public outputs contain aggregate evidence only.

```powershell
python validation/preflight_retailrocket_visitor_item_funnel.py --duckdb "E:/DuckDB/duckdb.exe" --output "data/retailrocket_visitor_item_funnel_preflight.json"
```

Measured results will be appended and saved in [aggregate evidence](../data/retailrocket_visitor_item_funnel_preflight.json). Learner SQL71 execution follows the assistant preflight. The funnel describes observed chronological pairs under this contract, with the stated identity, observation-window and follow-up limitations.

## Executed results

The assistant's single event-only SQL71 preflight completed on 9 November 2026. The read-only report returned **three rows × five columns, all three PASS**, with no FAIL or BLOCKED rows. Learner SQL71 execution remains pending. The preceding 8,553-byte frozen method prefix is unchanged, with SHA-256 `df835a679be19c19e2169a031328f4da27cf26cf0b26130e286a24ea1ec1ec2b`.

| Stage | Visitor-item pairs | Share of viewed pairs % | Conditional step rate % | Status |
|---|---:|---:|---:|---|
| VIEW | 2,132,127 | 100.0000 | NULL | PASS |
| VIEW_THEN_CART | 45,804 | 2.1483 | 2.1483 | PASS |
| VIEW_THEN_CART_THEN_TRANSACTION | 16,695 | 0.7830 | 36.4488 | PASS |

The observed viewed-pair cohort contains **2,132,127 pairs**. Of these, **45,804 (2.1483%)** have a strictly later cart addition; **16,695 (0.7830% of viewed pairs)** also have a transaction strictly later than that qualifying cart. Among qualifying cart pairs, **36.4488%** reach the third stage. These denominators are distinct pairs under the stated chronological rule, not the event-record shares reported in SQL70.

The independent source stream contained **2,145,179 observed pairs**, including **13,052 without an observed view**, which are outside this cohort. Each included pair is counted at most once per nested stage. All **2,756,101 original event occurrences**, including **460 exact duplicate surplus occurrences**, remain preserved in source verification. These observed chains are not session-level, fixed-window, person-level or validated-order conversion measures. Earlier/later unobserved events, missing event paths and unequal follow-up prevent interpreting incomplete chains as proven abandonment or causal loss.

Independent Python validation matched **all 2,756,101 occurrences × five original fields** in numeric pair/time order, then matched every count, Decimal percentage and NULL in the three-row report. Only **one pair's progression state** was held at a time; no all-pair dictionary or all-event list was constructed. Its source-derived sequence independently applied strict timestamp comparisons and counted pair stages at group boundaries. The nested counts reconcile as 2,132,127 >= 45,804 >= 16,695.

All **three fixture families** passed. A 24-event fixture across eight numeric sort chunks independently produced stage counts **[5,3,2]**, testing same-millisecond exclusions, later valid subsequences, earlier out-of-order activity, skipped-cart transactions, repeated records and separation across visitor/item pairs. An extra unqueried column remained outside admission. **Eleven invalid-source subcases** blocked all metrics or produced the documented missing-column binding error. **Two zero-denominator subcases** verified that valid no-view cohorts have zero counts and all NULL rates, while a viewed cohort with no qualifying carts has a NULL third-stage conditional rate. Fixture and real read-only database hashes remained unchanged.

Only **events.csv** was read. Frozen SQL54/63 creation prefixes built a disposable original-five-field projection for SQL71's readset. The production seventeen-column fact, its UTC fields and its category/availability fields were not rebuilt or reverified. Accepted earlier evidence remains their basis. SQL69, SQL70 and earlier full audit suites were not rerun. Neither property CSV nor the category CSV was read, and no learner database was opened.

Independent event selection and pair-key sorting took **25.172 seconds**. The three CLI phases took **5.995 seconds** for event-prefix reconstruction plus projection, **1.758 seconds** for SQL71, and **14.623 seconds** for the full five-field comparison and independent funnel fold. Each stayed within two threads, 1GB memory, 2GB spill and 120 seconds. Timings exclude hashing and fixtures and are not performance benchmarks.

The preflight created **56 private event chunks**, totalling **96,993,967 bytes**. The database measured **90,714,112 bytes** before cleanup; the largest post-phase private-directory observation was **187,708,079 bytes**, not a continuous peak. All private databases, chunks and spills were removed. Event-source hash/metadata, **16 pinned dependencies**, and **69 historical preflight files** remained unchanged. Real identifiers were processed privately without logging or uploading.

The [aggregate evidence](../data/retailrocket_visitor_item_funnel_preflight.json) records report fingerprint `08299a5dc9c79b8e862f8a4e1363b2f3beba5dd3033ca794113134f049382cb1`. DECIMAL shares/rates are preserved as four-place JSON strings, while the base step rate remains genuine NULL. The report establishes this observed chronological pair funnel and its explicit observation/identity limitations; it introduces no session definition, expiry window, order validation, monetary claim or causal interpretation.

## Learner screenshot acceptance — 9 November 2026

The learner supplied the SQL71 DBeaver result on 9 November 2026 (Australia/Sydney). All **three rows × five columns, fifteen fields**, including complete stage names and the first-row NULL step rate, are fully visible and match the prior result. All three rows are **PASS**. No labels or values were cropped or reconstructed. See the [learner acceptance record](../data/retailrocket_visitor_item_funnel_learner_acceptance.json).

The visible fields comprise **three integer pair counts, five non-null percentage cells, one NULL step-rate cell, three stage labels and three statuses**. The screenshot's VIEW share **100** and final share **0.783** are retained in the visual transcription and normalized exactly with Decimal to **100.0000** and **0.7830** for the frozen four-place report contract. The first-row [NULL] remains genuine JSON null. The normalized report fingerprint is `08299a5dc9c79b8e862f8a4e1363b2f3beba5dd3033ca794113134f049382cb1`.

The accepted report has **2,132,127 viewed visitor/item pairs**, **45,804 pairs with a strictly later qualifying cart**, and **16,695 pairs with a transaction strictly after that cart**. These represent **2.1483%** and **0.7830%** of the viewed cohort at the latter two stages; **36.4488%** of qualifying-cart pairs reach the final stage. Counts are binary per pair within nested stages, so repeated events do not inflate pair counts and source records are not deleted. Same-millisecond events do not prove stage order.

The report covers the full observed period. Pairs have unequal follow-up, observation boundaries can truncate earlier or later events, and paths with no observed view are excluded. Failure to observe a later stage is not proof of abandonment. Pair progression is not a person, session, validated-order, fixed-window or causal conversion measure.

All **13,397 prior method bytes**, including the **8,553-byte frozen contract** and executed-results appendix, are preserved byte for byte. Frozen SQL71, validator, preflight and sixteen pinned dependencies remain unchanged. Historical learner-pending statements remain as written; this appendix records current learner acceptance. No source CSV, database, preflight or fixture was opened or rerun for acceptance, and no screenshot or row-level identifiers were copied into the repository. This screenshot does not reverify SQL69/70 or the fact's unqueried UTC/property fields, and does not establish learner conceptual understanding.
