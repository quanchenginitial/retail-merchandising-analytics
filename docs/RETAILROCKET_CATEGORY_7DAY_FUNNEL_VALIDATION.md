# Retailrocket first-view category seven-day funnel

This SQL74 contract is frozen on 9 November 2026 before fixtures and source execution. It compares the ordered seven-day visitor-item funnel across categories assigned at the first observed view, while retaining every unmatched population. The top ten categories are selected by cohort size rather than by their outcome rates.

## Population and attribution

The read-only query uses the same ten fields of rr_mart.events_enriched as SQL73: timestamp, visitorid, event, itemid, transactionid, categoryid_value, categoryid_from_ms, categoryid_to_ms, categoryid_source_file and categoryid_coverage. It reads only categoryid from rr_core.dim_category. Availability, stored UTC fields, parent/root/depth, sessions and hierarchy rebuilding remain outside scope. Required readset names/types are checked without asserting the full seventeen-column fact schema.

Each visitor-item pair is anchored at its earliest observed view. It is eligible only if that timestamp plus 604800000 milliseconds is <= the maximum timestamp across all event types. The frozen endpoint is 1442545187788 ms (2015-09-18T02:59:47.788000Z), and the cutoff is 1441940387788 ms (2015-09-11T02:59:47.788000Z). The cohort must contain 2,042,310 eligible pairs. Seven elapsed days is a chosen analysis window, not an optimized horizon; first observed is not necessarily first-ever, and the global log boundary does not establish continuous capture or complete exposure.

For each eligible pair, every view occurrence tied at the earliest timestamp must have one identical NULL-aware five-field category tuple. Identical snapshots are collapsed only after the consistency check. The assigned first-view category stays fixed through the later funnel, even if the item's category changes before cart or transaction. Source duplicates remain preserved; one binary stage count per pair does not mean source deduplication.

MAPPED means the latest category observation at or before the first view has a safely parsed numeric ID present in the static reference. Original value text and provenance are retained; leading-zero text may map numerically without being rewritten. UNKNOWN_REFERENCE retains valid matched values absent from the reference; BEFORE_FIRST retains views before the item's first category observation; NO_HISTORY retains items with no supplied category history. No future value is filled backward. Last-recorded category assignment and static membership do not establish freshness, historical business truth, inventory state, or human-readable category labels.

The cart stage is the earliest addtocart strictly after the first view and no later than first-view+7 days. The transaction stage is the earliest transaction strictly after that qualifying cart and no later than the same first-view+7-day deadline. The clock does not restart at the cart. Same-millisecond ties do not establish order; later valid subsequences can still qualify. Earlier carts/transactions and transactions that skip a qualifying cart do not advance the chain. Recent pairs lacking seven days of potential follow-up are excluded before outcomes, even if they have already transacted.

## Report and reconciliation

The nine columns are segment, categoryid, eligible_pairs, cart_pairs, transaction_pairs, cart_rate_pct, transaction_rate_pct, cart_to_transaction_rate_pct and check_status.

Mapped category groups are ranked by eligible_pairs descending, with numeric categoryid ascending for ties. The first min(10,n) observed mapped groups appear as TOP_CATEGORY with their opaque numeric IDs. The remaining mapped groups are aggregated as OTHER_MAPPED. UNKNOWN_REFERENCE, BEFORE_FIRST, NO_HISTORY and TOTAL always appear, including zero counts. The production result has 15 rows; a healthy synthetic population with fewer mapped groups has min(10,n)+5 rows. No category names are inferred from numeric IDs.

The three rates are respectively 100*cart_pairs/eligible_pairs, 100*transaction_pairs/eligible_pairs and 100*transaction_pairs/cart_pairs. Every row uses its own denominator. Zero denominators yield NULL; a positive denominator with zero successes yields 0.0000. Four-place DECIMAL output is independently checked using Decimal half-up arithmetic; the CLI serializes these values as four-place JSON strings. Percentages are not additive and are never averaged to derive OTHER_MAPPED or TOTAL. Those rates are recomputed from summed binary pair counts.

Every eligible pair belongs to exactly one non-TOTAL row. These rows' eligible/cart/transaction counts must reconcile with TOTAL. All row counts must satisfy eligible >= cart >= transaction. The source-wide totals must agree with accepted SQL72: 2,042,310 eligible pairs, 43,147 qualifying carts and 15,520 qualifying transactions. First-view attribution totals must agree with accepted SQL73: 1,527,206 MAPPED, 0 UNKNOWN_REFERENCE, 304,405 BEFORE_FIRST and 210,699 NO_HISTORY. These are reconciliation controls rather than new inferred category outcomes.

The inherited admission checks include accepted event/type counts, duplicate surplus 460, original field validity and supported timestamps, the frozen global endpoint, exact ten-field types, temporal match/value/provenance validity, and 1,669 unique nonnegative non-NULL reference IDs. Eligible first-view tuple consistency and fixed cohort size are checked before outcomes. Invalid source, reference, cohort or outcome reconciliation produces only five aggregate placeholder rows (OTHER_MAPPED, the three unknown buckets and TOTAL), all categoryid NULL and all metrics NULL/BLOCKED. No top-category IDs or ranks are released from unadmitted data. Missing required tables/columns can fail SQL binding.

The rates describe observed ordered visitor-item paths, not people, orders, sessions or causal conversion effects. The top-ten selection favors larger cohorts and is not a performance leaderboard. Different traffic mix, exposure, price, availability and observation gaps can affect comparisons. Unmatched categories remain visible so the 25.2216% without first-view assignment are not silently excluded. This step establishes comparative descriptive outputs, not a causal intervention or estimated business uplift.

## Independent source validation and resource bounds

The validator imports reusable SQL73 source/format utilities but does not execute SQL73's main function or any previous full audit suite. The four sources are events.csv, category_tree.csv and both item_properties CSVs. Both property files are scanned completely, retaining only 788,214 categoryid observations; availability and opaque properties are not reconstructed. Category-only intervals are derived from next observations, preserving original values and provenance; duplicate/conflicting item/time keys abort before ASOF construction. The ID-only reference projection must exactly equal the independently parsed set of all 1,669 IDs. No full SQL62 hierarchy or SQL69 seventeen-field reconstruction is run.

A disposable ten-field category-only fact is built from frozen SQL54/63 event creation prefixes and the accepted category ASOF convention. Python independently sorts selected category observations numerically by item/time and events by item/visitor/time/event/transaction, in chunks of at most 50,000 rows. Only the current item's category history (cap 50,000), one current pair's first-view/category/cart/transaction state and a bounded category aggregate dictionary are retained. The dictionary contains at most 1,669 known IDs plus the three unmatched groups. No all-item histories or all-pair dictionary is used. Remaining category observations are drained even for items with no events.

Every one of the 2,756,101 original event occurrences is independently compared across the entire ten-field readset, including NULLs, original identifiers, category value/bounds/provenance/status and duplicate multiplicity. The same independent stream folds each pair's strict time-ordered chain, assigns it to its first-view category and aggregates eligible/cart/transaction counts. Independent population ranking and count aggregation recreate TOP_CATEGORY, OTHER_MAPPED, all unmatched groups and TOTAL, then recompute all rates. The existing SQL73 method is evidence for its accepted scope, not a substitute for the new source-derived category-funnel truth.

Four real CLI phases are declared before execution:

1. Category-only guarded import/interval construction plus complete ID-only reference projection: two threads, 1GB memory, 2GB spill, 120 seconds.
2. Frozen SQL54/63 event creation prefixes plus category-only ten-field enrichment: two threads, 2GB memory, 4GB spill, 120 seconds.
3. Read-only SQL74 report: two threads, 1GB memory, 2GB spill, 120 seconds.
4. Direct read-only ten-field source comparison and independent category-funnel fold: two threads, 1GB memory, 2GB spill, 120 seconds.

Admission requires at least 8GB free space and a 7GB private-directory budget. Post-phase directory observations are not continuous peaks. Source scan/sort time is reported separately. All four source hashes/metadata, pinned code/method/accepted-evidence dependencies and 72 historical preflight files must remain unchanged. The private database byte hash must be unchanged across the read-only report and stream. Private databases, spools and spills are removed; no learner database is opened and real visitor/item/transaction identifiers and raw event/category-history records are not logged or published. Anonymous category reference IDs are intentionally published only as aggregate TOP_CATEGORY labels.

Focused fixtures verify fixed first-view attribution despite later category changes, strict ordering and same-millisecond exclusion, the shared inclusive deadline and +1ms exclusion, incomplete-pair exclusion, all unmatched buckets, repeated first-view occurrences, safe original-text membership, top-N population ranking with numeric tie breaks, OTHER_MAPPED count aggregation, zero unknown and zero eligible cohorts, and NULL/zero rate behavior. Invalid admission and reconciliation block every metric and suppress top-category IDs. Existing source key and buffer-cap guards remain in force without expanding into a new foundation audit suite.

```powershell
python validation/preflight_retailrocket_category_7day_funnel.py --duckdb "E:/DuckDB/duckdb.exe" --output "data/retailrocket_category_7day_funnel_preflight.json"
```

Measured results will be appended after the bounded source preflight. Learner SQL74 execution and screenshot acceptance follow assistant validation.

## Executed results

The assistant preflight completed on 2026-11-09T10:54:22.912872+00:00 with DuckDB v1.5.5 (Variegata) d8cdaa33fd. One bounded real-source attempt completed the four declared CLI phases. All 15 output rows passed. The complete independent source-derived category-funnel report matched the SQL result, including rank order, every count, all NULLs and every four-place rate.

All three rate columns below are percentages. Category codes are anonymous aggregate labels; NULL in categoryid denotes an aggregate or unmatched bucket.

| segment | categoryid | eligible_pairs | cart_pairs | transaction_pairs | cart_rate_pct | transaction_rate_pct | cart_to_transaction_rate_pct | check_status |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| TOP_CATEGORY | 1051 | 47963 | 871 | 309 | 1.8160 | 0.6442 | 35.4765 | PASS |
| TOP_CATEGORY | 1483 | 41284 | 614 | 241 | 1.4873 | 0.5838 | 39.2508 | PASS |
| TOP_CATEGORY | 959 | 32525 | 869 | 320 | 2.6718 | 0.9839 | 36.8239 | PASS |
| TOP_CATEGORY | 342 | 30463 | 479 | 133 | 1.5724 | 0.4366 | 27.7662 | PASS |
| TOP_CATEGORY | 1613 | 25105 | 483 | 76 | 1.9239 | 0.3027 | 15.7350 | PASS |
| TOP_CATEGORY | 683 | 20147 | 488 | 134 | 2.4222 | 0.6651 | 27.4590 | PASS |
| TOP_CATEGORY | 5 | 19706 | 321 | 128 | 1.6289 | 0.6495 | 39.8754 | PASS |
| TOP_CATEGORY | 1279 | 18175 | 309 | 58 | 1.7001 | 0.3191 | 18.7702 | PASS |
| TOP_CATEGORY | 196 | 17225 | 413 | 180 | 2.3977 | 1.0450 | 43.5835 | PASS |
| TOP_CATEGORY | 646 | 16672 | 272 | 57 | 1.6315 | 0.3419 | 20.9559 | PASS |
| OTHER_MAPPED | NULL | 1257941 | 29692 | 10826 | 2.3604 | 0.8606 | 36.4610 | PASS |
| UNKNOWN_REFERENCE | NULL | 0 | 0 | 0 | NULL | NULL | NULL | PASS |
| BEFORE_FIRST | NULL | 304405 | 7626 | 2790 | 2.5052 | 0.9165 | 36.5854 | PASS |
| NO_HISTORY | NULL | 210699 | 710 | 268 | 0.3370 | 0.1272 | 37.7465 | PASS |
| TOTAL | NULL | 2042310 | 43147 | 15520 | 2.1127 | 0.7599 | 35.9701 | PASS |

The eligible cohort remains 2,042,310 pairs, with 43,147 qualifying carts and 15,520 qualifying transactions. The overall rates remain 2.1127%, 0.7599% and 35.9701%, reconciling exactly with SQL72. First-view coverage remains 1,527,206 MAPPED, 0 UNKNOWN_REFERENCE, 304,405 BEFORE_FIRST and 210,699 NO_HISTORY, reconciling exactly with SQL73.

There are 1,136 observed mapped category groups. The displayed ten were selected by eligible cohort size, not by their rates; OTHER_MAPPED combines the remaining 1,126 groups. The ten displayed groups contain 269,265 eligible pairs, 5,119 carts and 1,636 transactions. Together with OTHER_MAPPED they account for 1,527,206 mapped pairs, 34,811 carts and 12,462 transactions. All non-TOTAL counts reconcile to TOTAL; aggregate rates were recomputed from counts rather than summed or averaged.

The groups show descriptive differences worth investigating. For example, anonymous category 1613 has a 1.9239% cart rate and a 15.7350% cart-to-transaction rate; this identifies a potential later-stage diagnostic question but does not explain its cause. NO_HISTORY has a 0.1272% observed transaction rate compared with 0.9165% for BEFORE_FIRST. These unmatched populations remain in the report rather than disappearing from the denominator. Missing history is not established as the cause of the rate difference, and the report does not control product/traffic mix, price, availability or exposure.

UNKNOWN_REFERENCE remains an explicit zero-count row with NULL rates. This applies only to eligible first-view snapshots and does not imply that all property observations have valid reference mappings. The 25.2216% without an assigned first-view category remain represented by BEFORE_FIRST and NO_HISTORY. First-view attribution stays fixed for every path even if later event snapshots have a different category.

The independent proof compared all 2,756,101 event occurrences across the complete ten-field readset, retaining all 460 duplicate surplus occurrences. It independently folded 2,145,179 observed visitor-item pairs, 2,132,127 viewed pairs and 2,042,310 eligible pairs. All 788,214 selected category observations were drained and reconciled, including items with no events. Every one of the 1,669 reference IDs matched the independently parsed CSV ID set.

The fold held one pair state and at most 18 current-item category observations. Its maximum category aggregate dictionary contained 1,138 groups, below the 1,672-group bound; the zero-count UNKNOWN_REFERENCE group is emitted explicitly. Anonymous category IDs appear only as grouped report labels. No real visitor/item/transaction identifiers or raw event/category-history rows were published.

Three focused fixture families passed, including 14 invalid-admission cases. The synthetic top-two fixture verified numeric tie order, first-view attribution despite later category changes, inclusive seven-day boundaries, same-millisecond exclusions and no cart-clock reset. Its OTHER_MAPPED counts were [3,2,1] and overall counts [10,8,6]. Zero eligible, zero unknown-reference and empty OTHER_MAPPED cases retained the required rows and undefined-rate NULLs. Failed admission suppressed top-category IDs and returned only five NULL/BLOCKED aggregate placeholders.

The actual endpoint remains 1442545187788 ms (2015-09-18T02:59:47.788000Z) and the first-view eligibility cutoff remains 1441940387788 ms (2015-09-11T02:59:47.788000Z). The observation boundary is not proof of continuous capture; the seven-day rule is chosen rather than optimized.

CLI phase durations were 9.188 seconds for category-only history/reference construction, 9.964 seconds for event/category enrichment, 7.98 seconds for SQL74, and 41.164 seconds for the complete independent stream/fold. Python category and event scan/sorts took 24.386 and 33.026 seconds. Timings exclude hashing and fixtures. Only enrichment used the declared 2GB memory/4GB spill allowance; other CLI phases used 1GB/2GB, all with two threads and 120-second limits.

The private database was 118,501,376 bytes before cleanup. The largest observed post-phase private directory was 265,311,070 bytes, below the 7GB budget; these observations are not continuous peaks. The database byte hash was unchanged across the read-only report and stream. All four source hashes/metadata, pinned dependencies and 72 historical preflight files remained unchanged. Private databases, spools and spills were removed. No learner database was opened. Availability history and the SQL62 hierarchy were not rebuilt, stored UTC fields were not read, and the full SQL69 reconstruction and prior audit suites were not rerun. Their code and accepted evidence were read only to pin dependencies.

Report fingerprint: `b368ec2c3132e2ddafa3773d45402a33b003e8f508aea35367039e8efb10cbd9`. Script SHA-256: `b013cf0c7c887d687b5551d74d3d785e3bd0b08d320651bf7f314926c5b789da`. Validator SHA-256: `a4e51ee60f6417c9e3cb272c71bb053c7278b426d5940b59dec106829570546b`. The original 10,599-byte method prefix remains unchanged (`02fd845c6842d8f2d21211ea502df7baef6c2b29f5520f5cd2c8fa38558387a3`). Aggregate evidence: [retailrocket_category_7day_funnel_preflight.json](../data/retailrocket_category_7day_funnel_preflight.json).

Assistant preflight is complete. Learner SQL74 execution and screenshot acceptance remain pending.

## Learner screenshot acceptance — 9 November 2026

The learner supplied the SQL74 DBeaver result on 9 November 2026 (Australia/Sydney). All **fifteen rows × nine columns, 135 fields** and all headers are fully visible and match the prior measured result. All fifteen rows are **PASS**. No labels or values were cropped or reconstructed. See the [learner acceptance record](../data/retailrocket_category_7day_funnel_learner_acceptance.json).

Visibility comprises **45 integer counts, 10 non-null aggregate category IDs, 42 non-null decimal rates, 8 genuine NULL cells, 15 segment labels and 15 statuses**. The eight NULLs are five aggregate-row category IDs and three UNKNOWN_REFERENCE rates. Six displayed rate strings omit a trailing zero: category 1051 cart rate **1.816**, category 1613 cart-to-transaction **15.735**, category 683 cart-to-transaction **27.459**, category 196 transaction rate **1.045**, OTHER_MAPPED cart-to-transaction **36.461**, and NO_HISTORY cart rate **0.337**. The visual transcription preserves them exactly; Decimal normalization adds the final zero solely to match the frozen four-place report contract. The normalized fingerprint is `b368ec2c3132e2ddafa3773d45402a33b003e8f508aea35367039e8efb10cbd9`.

The accepted non-total counts reconcile to **2,042,310 eligible pairs, 43,147 cart pairs and 15,520 transaction pairs**. TOTAL rates remain **2.1127%**, **0.7599%** and **35.9701%**, using total counts rather than adding group percentages. All mapped and unknown eligible counts reconcile to SQL73. Category remains fixed at first observed view, while later events must obey strict stage order and the same inclusive seven-day deadline.

The ten displayed categories were selected by eligible-pair volume, not conversion performance. OTHER_MAPPED aggregates all remaining mapped categories, and all three unknown buckets remain present. The zero-count UNKNOWN_REFERENCE bucket correctly has three NULL rates. These are descriptive segment results: anonymous category codes do not reveal business names, and unknown coverage does not prove the customer-facing website lacked classification. Differences cannot be attributed causally to category identity.

All **17,864 prior method bytes**, including the **10,599-byte frozen prefix** and executed-results appendix, are preserved byte for byte. Frozen SQL74, validator, preflight and **29 pinned dependencies** remain unchanged. Historical learner-pending statements remain intact; this appendix records current acceptance. No source CSV, learner database, preflight or fixture was opened or rerun for acceptance. The record publishes grouped anonymous category codes with aggregates; it does not copy the screenshot, raw events, visitor/item/transaction identifiers or category-history details into the repository. No fresh verification of availability/UTC fields, the full production fact, category hierarchy or learner conceptual understanding is claimed.
