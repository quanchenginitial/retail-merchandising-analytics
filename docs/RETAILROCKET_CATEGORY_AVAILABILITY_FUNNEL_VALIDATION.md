# Retailrocket category 1613 funnel by first-view recorded availability

This SQL77 contract is frozen on 9 November 2026 before fixtures and source execution. It compares category-1613 seven-day ordered visitor-item paths across the availability observation assigned at the first observed view. Category 1613 was selected after earlier results, so this remains exploratory diagnosis, not independent hypothesis confirmation or a causal availability effect.

## Expanded readset and fixed first-view assignment

SQL77 is read-only. The readset expands from ten to fifteen fields in rr_mart.events_enriched: original timestamp, visitorid, event, itemid and transactionid; categoryid_value/from_ms/to_ms/source_file/coverage; and available_value/from_ms/to_ms/source_file/coverage. Only categoryid is read from rr_core.dim_category. Stored UTC columns and parent/root/depth remain outside scope; the full seventeen-field fact and full hierarchy are not reverified.

Both category and availability histories are reconstructed in the private proof. This step must not be described as category-only reconstruction or as avoiding availability data. Both item_properties CSVs are scanned completely and the two named properties are selected: 788,214 categoryid observations plus 1,503,639 available observations, totaling 2,291,853. Other opaque properties are not reconstructed. Category and availability observation times and boundaries are independent; one property's date must not be substituted for the other.

The eligible population is unchanged: a visitor-item pair's earliest observed view plus 604800000 milliseconds must be <= the all-event endpoint 1442545187788 ms (2015-09-18T02:59:47.788000Z). The eligible first-view cutoff is 1441940387788 ms (2015-09-11T02:59:47.788000Z). Qualifying cart time is strictly later than the view and within its inclusive seven-day deadline. Qualifying transaction time is strictly later than that cart and within the same original deadline; a cart does not restart the clock. Same-millisecond ties do not prove ordering. Incomplete-follow-up pairs are excluded before outcomes.

For every eligible pair, all view occurrences tied at its earliest timestamp must share one identical NULL-aware ten-attribute tuple comprising both five-field snapshots. Only after this combined consistency guard may identical snapshots collapse. This is an all-eligible first-view guard, not a target-only check. Original source duplicates remain preserved. The fixed first-view category selects MAPPED category 1613, and the fixed availability snapshot assigns its analysis group. Later changes in either property do not reassign the pair or its later path outcomes.

The target must reconcile to accepted category-1613 totals: 25,105 eligible pairs, 483 qualifying cart pairs and 76 qualifying transaction pairs. These are supported by SQL74, the combined SQL75 category rows and SQL76 TOTAL. Whole-source original/type/duplicate/cohort/flow controls and first-view category reference membership remain unchanged. The report neither time-splits pairs nor publishes per-item histories.

## Availability groups and interpretation

The fixed row order is RECORDED_1, RECORDED_0, BEFORE_FIRST, NO_HISTORY and TOTAL. RECORDED_1/0 mean that the latest supplied availability observation at or before the first view has canonical original value '1'/'0'. BEFORE_FIRST means the item has an availability history, but its first observation is later than the view; no future value is filled backward. NO_HISTORY means no supplied availability history exists for that item. Category coverage and availability coverage are distinct.

MATCHED availability requires exact value '0' or '1', valid source provenance, from <= event timestamp, and event timestamp < any finite to boundary with to > from. A NULL tail means no later observation was supplied; it is not proof of indefinite validity or freshness. BEFORE_FIRST/NO_HISTORY require all four matched-value/boundary/provenance fields to remain NULL. Invalid values or tuples block output rather than being turned into another group or imputed.

Recorded 0/1 describes a historical dataset observation under the accepted latest-past convention, not verified live stock, a physical inventory audit, current website availability or complete user exposure. A later transaction after a RECORDED_0 first view can be a legitimate descriptive path under this model; it does not prove a data error or stockout cause. Availability may change after the first view, and this step deliberately retains the original assignment. Missing-history groups remain visible rather than being silently discarded.

The global boundary is not proof of continuous event capture, first observed view is not necessarily first-ever, and seven days is a chosen analysis horizon. Product/traffic mix, prices, promotions, exposure, recording gaps and stale observations may affect rates. No stockout, lost-sales amount, treatment effect, significance result or business uplift is estimated.

## Five-row, nine-column output

Columns are availability_status, eligible_pairs, cart_pairs, transaction_pairs, eligible_share_pct, cart_rate_pct, transaction_rate_pct, cart_to_transaction_rate_pct and check_status. Counts are binary qualified pair stages, not raw event totals, people or orders. The four mutually exclusive groups sum to TOTAL in all three count columns, and every row satisfies eligible >= carts >= transactions.

eligible_share_pct uses the whole target-category eligible population as denominator. The three path rates use the row's eligible pairs, eligible pairs and cart pairs respectively. Percentages are multiplied by 100 and rounded to four places only for display; the independent Decimal reference checks all values. Undefined denominators produce NULL. An empty group has a zero share when the target population is positive, but NULL path rates. If the whole target population is empty, every share and path rate is NULL. Positive denominators with no successes yield 0.0000. Rounded group shares need not sum literally to 100.0000; exact count reconciliation governs admission.

Required fifteen-field types, original event rules/counts/duplicate surplus 460, supported timestamps, accepted endpoint, both properties' value/boundary/provenance/coverage contracts, 1,669 unique reference IDs, combined earliest-view tie consistency, global cohort/flow and target-parent counts must pass. Invalid admission or partition reconciliation yields five fixed labels with every numeric metric NULL and BLOCKED status. Missing required columns/tables may fail binding. No source identifiers or history rows are published; category 1613 appears only as aggregate target context.

## Independent bounded four-source proof

Reusable import/staging/interval/matching helpers from SQL65/67/68/69 and recent analysis are used as code references, without running old main functions or historical full checks. Both named histories are privately selected, canonically typed and checked for unique item/property/timestamp keys. Values and source filenames are preserved; interval ends are derived from the next observation within the same item/property. The complete ID-only reference projection must match all 1,669 independently parsed category_tree.csv IDs.

The disposable private fact contains fifteen fields: original five plus both five-field observation assignments. Two independent ASOF LEFT JOINs implement the accepted latest observation at or before each event, retaining unmatched rows and duplicate occurrences. Frozen SQL54/63 event creation prefixes are reused. SQL69's full seventeen-column build and its historical two-attempt evidence are not rerun or modified; no UTC fields or hierarchy traversal are added.

Python independently sorts both named properties numerically by item/property/time and events by item/visitor/time/event/transaction in at most 50,000-row chunks. It retains only the current item's two histories, with a combined cap of 50,000 observations across both properties, one current pair's first-view snapshots and qualifying path state, four availability-group counters and global control counts. It does not retain an all-item history map, all-pair map, item ranking or selected-item list. Each property's latest-past match and finite endpoint are independently checked; remaining named observations are fully drained even for items with no events.

Every original event occurrence is compared across all fifteen queried fields, including both properties' values/bounds/provenance/statuses, original fields, NULLs and duplicates. The independent pair fold fixes both snapshots at the first view, enforces the original shared deadline and target category, and reconstructs all five output rows and rates. Coverage classes are not inferred from another property, and neither source missingness nor recorded zero is converted into fabricated stock information.

Four real CLI phases are declared in advance: (1) guarded named-history/interval construction plus full ID-only reference projection, two threads, 1GB memory/2GB spill/120 seconds; (2) event creation prefixes plus fifteen-field enrichment with two ASOF joins, two threads, 2GB memory/4GB spill/120 seconds; (3) read-only SQL77, two threads, 1GB/2GB/120 seconds; (4) read-only complete fifteen-field source comparison and pair fold, two threads, 1GB/2GB/120 seconds. At least 8GB free space and a 7GB private-directory budget are required. Post-phase observations are not continuous peaks; source scan/sort time is reported separately.

Focused fixtures cover both recorded values, both missing-history statuses, different category/availability start times, exact observation boundaries, later availability changes without reassignment, canonical 0/1 validation, NULL-aware combined first-view conflicts, shared seven-day strict ordering, duplicates and empty denominators. Invalid source values/keys or target contracts block rather than silently selecting or imputing. No historical full fixture suite is rerun.

All four source hashes/metadata, pinned code/accepted evidence/methods and 75 historical preflight files must remain unchanged. Private database bytes must be unchanged across read-only phases. Databases, spools and spills are removed; no learner database is opened. Raw event/history records and real visitor/item/transaction identifiers are not published or logged. Scope flags explicitly record availability_history_reconstructed=true and category_only_history_reconstructed=false, while stored UTC/full17/hierarchy verification remains excluded.

```powershell
python validation/preflight_retailrocket_category_availability_funnel.py --duckdb "E:/DuckDB/duckdb.exe" --output "data/retailrocket_category_availability_funnel_preflight.json"
```

Measured results will be appended after the bounded preflight. Learner SQL77 execution and screenshot acceptance follow assistant validation.

## Executed results

Assistant SQL77 preflight passed at 2026-11-09T12:05:56.729273+00:00 using v1.5.5 (Variegata) d8cdaa33fd. This was one real-source attempt with the four declared CLI phases. The five-row, nine-column report contains five PASS rows and no blocked/failing rows. Learner execution and screenshot acceptance remain pending.

| availability_status | eligible_pairs | cart_pairs | transaction_pairs | eligible_share_pct | cart_rate_pct | transaction_rate_pct | cart_to_transaction_rate_pct | check_status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| RECORDED_1 | 16994 | 419 | 64 | 67.6917 | 2.4656 | 0.3766 | 15.2745 | PASS |
| RECORDED_0 | 7005 | 56 | 12 | 27.9028 | 0.7994 | 0.1713 | 21.4286 | PASS |
| BEFORE_FIRST | 1106 | 8 | 0 | 4.4055 | 0.7233 | 0.0000 | 0.0000 | PASS |
| NO_HISTORY | 0 | 0 | 0 | 0.0000 | NULL | NULL | NULL | PASS |
| TOTAL | 25105 | 483 | 76 | 100.0000 | 1.9239 | 0.3027 | 15.7350 | PASS |

The target partition is exactly 25,105 eligible visitor-item pairs, 483 qualifying cart pairs and 76 qualifying transaction pairs. These reconcile to accepted SQL74 category 1613, both SQL75 periods combined and SQL76 TOTAL. The four availability buckets partition each count column; rates use the frozen row-specific denominators and independently checked four-place Decimal rounding.

The independent source proof compared every one of 2,756,101 original event occurrences across all fifteen queried fields, preserving the 460 duplicate surplus occurrences, both properties' original values, nullable boundaries, provenance and coverage statuses. It separately reconstructed and fully drained 2,291,853 named observations (788,214 categoryid and 1,503,639 available) from both CSV parts. The interval fold counted 1,457,747 finite intervals and 834,106 open tails across 834,106 item-property histories. All 1,669 independently parsed reference IDs matched the private ID-only projection.

The source-derived global eligible cohort remained 2,042,310, with 43,147 qualifying cart pairs and 15,520 qualifying transaction pairs. First-view category coverage remained 1,527,206 MAPPED, zero UNKNOWN_REFERENCE, 304,405 BEFORE_FIRST and 210,699 NO_HISTORY. Combined category/availability attributes agreed across every eligible pair's tied first-view occurrences. Later property changes did not alter the pair's assigned group. The largest current-item combined history held 36 observations, below the combined 50,000-row cap; only one pair state and four target availability aggregates were retained.

Five focused fixture families passed: independently timed category/availability observations and both recorded/unknown classes with fixed first-view attribution; eight invalid report cases; combined-history-cap rejection; atomic named-key duplicate rejection; and zero-cart/empty-target denominator behavior. The 32-event fixture preserved its repeated first-view occurrence and produced target counts [7, 6, 5], with all fifteen fields independently matched. These tests did not run historical full audit suites.

Measured CLI times were 6.392 seconds for named histories plus reference IDs, 9.701 seconds for fifteen-field enrichment, 12.055 seconds for read-only SQL77, and 44.605 seconds for the independent full stream and pair fold. Python named-history scan/sort took 28.35 seconds and event scan/sort 24.247 seconds. Each CLI phase remained inside the declared 120-second limit with two threads. Only enrichment used 2GB memory/4GB spill; the other phases used 1GB/2GB.

All four source file hashes and metadata, pinned dependencies and 75 historical preflight artifacts were unchanged. Read-only database hashes matched before and after the report and stream. The largest private directory observed after a phase was 399,995,920 bytes, below the declared 7GB budget; this is an observed size, not a continuous peak. All temporary databases, comparison spools and spills were removed. No learner database was opened, and no raw event/history records or visitor/item/transaction identifiers were published. Availability history was reconstructed; stored UTC fields, the full seventeen-field fact and category hierarchy were not reverified.

Recorded 0/1 remains last-recorded historical context under the accepted observation rule, not proof of live stock or an availability-caused change in behavior. The target was chosen after prior results. These grouped counts support exploratory diagnosis; they do not establish inventory truth, significance, causal effects or business uplift.

Report SHA-256: `d42b1832f6a7f49024f41d6fb8ed35895ec518204066e53c055aca6d7f1c552e`. Script SHA-256: `60bda48dea5621a876aa319c378c7600528c9c2950154b51f76d99b21aef7466`. Validator SHA-256: `b1620dfee1606b319d668b5db11bb9558be89d3c9fbd3ec0362d67f8acb9327d`. The original 10,939-byte method prefix remains unchanged at `33311c7d9048a25a0f260b8c1ccef6d91bc8cbcf71d526dfd55dbf585c87f02c`.
