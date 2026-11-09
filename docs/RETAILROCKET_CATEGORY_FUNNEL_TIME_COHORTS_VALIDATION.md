# Retailrocket category funnel across two first-view UTC cohorts

This SQL75 contract is frozen on 9 November 2026 before fixtures and source execution. It splits the accepted seven-day category funnel into two fixed first-view UTC cohorts, preserving the same global category labels and every unmatched group. This is an exploratory descriptive comparison of two unequal calendar blocks, not predictive validation, a seasonality test, statistical proof, or a causal comparison.

## Fixed cohort and category definitions

SQL75 is read-only and uses the SQL74 readset: the original timestamp/visitorid/event/itemid/transactionid fields plus categoryid_value, categoryid_from_ms, categoryid_to_ms, categoryid_source_file and categoryid_coverage from rr_mart.events_enriched; only categoryid from rr_core.dim_category is referenced. Availability, stored UTC fields, parent/root/depth and sessions remain outside scope. The accepted seventeen-field fact and full reference hierarchy are not rebuilt or reverified.

The eligible population remains each visitor-item pair's earliest observed view plus 604800000 milliseconds <= the maximum timestamp over all event types. The endpoint is frozen at 1442545187788 ms (2015-09-18T02:59:47.788000Z), with eligible first-view cutoff 1441940387788 ms (2015-09-11T02:59:47.788000Z). Expected totals remain 2,042,310 eligible pairs, 43,147 qualifying carts and 15,520 qualifying transactions. Seven elapsed days is an analysis convention; first observed is not first-ever, and a global log boundary does not guarantee continuous capture or complete individual exposure.

The split is **1435708800000 ms = 2015-07-01T00:00:00.000000Z**, computed using integer UTC epoch arithmetic. EARLY contains pairs with first_view_ms strictly below this boundary; LATE contains first_view_ms at or above it. Only the first-view anchor determines the cohort. An EARLY pair's qualifying cart or transaction may occur after 1 July and remains EARLY. Follow-up is not truncated at the split, and events are not individually reassigned by their own dates.

First-view category attribution is unchanged: all eligible earliest-view ties must have an identical NULL-aware five-field category tuple before collapsing identical snapshots. That category stays fixed through the path, even if later category observations change. MAPPED uses safe numeric membership in the 1,669-ID static reference, retaining original value text/provenance. UNKNOWN_REFERENCE, BEFORE_FIRST and NO_HISTORY remain separate, without future filling or category repair. Last-recorded assignment and static membership do not establish freshness, inventory truth or readable category names.

Qualifying cart time is strictly after the first view and <= its seven-day deadline. Qualifying transaction time is strictly after that cart and <= the same original deadline; the cart never starts a new clock. Same-millisecond ties do not establish stage order. Recent pairs lacking potential seven-day follow-up are excluded before outcomes, including early successes. Source duplicate surplus 460 is retained; binary pair counts define analytic units rather than deduplicating source events.

## Fixed report labels and reconciliation

Output columns are cohort followed by SQL74's nine columns: segment, categoryid, eligible_pairs, cart_pairs, transaction_pairs, cart_rate_pct, transaction_rate_pct, cart_to_transaction_rate_pct and check_status. The production result contains 30 rows, EARLY's 15 rows followed by LATE's 15 rows.

TOP_CATEGORY labels are selected once using the entire eligible population, ranked by eligible-pair count descending and numeric category ID ascending. The same ten IDs and order are retained in both cohorts, including zero-count cohort/category cells. There is no within-cohort reranking and no outcome-based selection. This whole-period selection is suitable for an exploratory retrospective comparison, not evidence of out-of-time predictive validation.

The fixed SQL74 top IDs are 1051, 1483, 959, 342, 1613, 683, 5, 1279, 196 and 646. OTHER_MAPPED, UNKNOWN_REFERENCE, BEFORE_FIRST, NO_HISTORY and TOTAL appear after them in each cohort, including empty groups. Healthy synthetic reports have 2*(min(top_n,mapped-group-count)+5) rows, using the same global labels in both cohorts; zero eligible population produces ten aggregate/unknown rows.

Each row's cart rate is 100*cart_pairs/eligible_pairs, transaction rate is 100*transaction_pairs/eligible_pairs, and cart-to-transaction rate is 100*transaction_pairs/cart_pairs. Rates use local row denominators. Undefined rates remain NULL, while zero successes with positive denominator produce 0.0000. Four-place DECIMAL percentages are independently checked by Decimal half-up arithmetic and represented as four-place JSON strings. Rates are not additive or averaged across groups/cohorts; count sums determine combined rates.

The SQL contains an explicit frozen 15-row SQL74 count contract, including each TOP_CATEGORY, OTHER_MAPPED, every unmatched group and TOTAL. Global group counts and the sums of EARLY+LATE for each corresponding group must both match this contract exactly, not merely the grand total. Within each cohort, all non-TOTAL counts must sum to its TOTAL and eligible >= cart >= transaction must hold. The inherited overall-flow controls also reconcile SQL72 and coverage totals 1,527,206 MAPPED, 0 UNKNOWN_REFERENCE, 304,405 BEFORE_FIRST and 210,699 NO_HISTORY from SQL73.

Inherited admission requires exact queried field types, valid original event fields/timestamps, accepted source/type/duplicate counts, the accepted global endpoint, valid category temporal bounds/value/provenance, unique valid reference IDs, eligible first-view tie consistency and the fixed population. The split parameter must equal the frozen UTC boundary. Failure of admission or any count reconciliation returns only ten aggregate placeholders—five per cohort—with categoryid NULL, all count/rate metrics NULL and BLOCKED status. No TOP_CATEGORY ID or rank is released from invalid input. Missing required tables/columns can fail SQL binding.

Differences describe observed visitor-item paths, not people, orders, sessions or causal conversion effects. The two periods differ in duration and may differ in traffic/product mix, exposure, price, availability and recording coverage. The preserved unmatched groups make coverage changes visible rather than silently filtering them away. No significance test, treatment effect, optimized split or recurring seasonal pattern is claimed.

## Independent bounded validation

The validator imports reusable SQL74/SQL73 helper functions without running their main functions or prior full suites. It reads events.csv, category_tree.csv and both item_properties CSVs. Both property files are scanned completely but only the 788,214 category observations are retained. Typed category-only intervals preserve values/provenance and reject duplicate/conflicting item/time keys before ASOF. The ID-only private reference must equal all 1,669 independently parsed CSV IDs. No availability reconstruction, full SQL69 reconstruction or SQL62 hierarchy traversal is performed.

The four private CLI phases retain the existing bounds: (1) category-only import/intervals and complete reference-ID projection at two threads, 1GB memory, 2GB spill, 120 seconds; (2) frozen SQL54/63 event creation prefixes plus category-only ten-field enrichment at two threads, 2GB memory, 4GB spill, 120 seconds; (3) read-only SQL75 at two threads, 1GB/2GB, 120 seconds; (4) direct read-only ten-field source comparison and independent cohort/group fold at two threads, 1GB/2GB, 120 seconds. At least 8GB free space and a 7GB private-directory budget are required. Post-phase observations are not continuous peaks; source sorting is timed separately.

Python sorts category observations numerically by item/time and events by item/visitor/time/event/transaction in at most 50,000-row chunks. It retains one current item's history (cap 50,000), one current pair's anchor/category/cart/transaction state, and two eligible/cart/transaction counter cells per category group. The aggregate bound is 2*(1,669+3)=3,344 cells. There is no all-pair dictionary or all-item history map. All remaining category observations are drained even for items with no events.

The independent stream compares all ten queried fields for every original event occurrence, including NULLs and duplicates. Its source-derived first-view timestamp selects EARLY/LATE, while the same pair state derives strict seven-day outcomes without truncating them at the split. Global category counts select one fixed top list. Independent per-cohort counts/rates recreate all 30 report rows; every group's summed counts must equal the accepted SQL74 report, independently of the SQL's embedded contract.

Focused fixtures cover the exact UTC boundary, EARLY outcomes crossing into July, a globally top category absent from LATE while a locally largest LATE category remains OTHER_MAPPED, empty cohorts/groups, fixed first-view category changes, shared-deadline and same-millisecond behavior, unmatched groups, duplicates and NULL/zero rates. Incorrect split/global-group contracts must suppress top labels and block all metrics. Existing common source guards are reused without rerunning previous foundation audit suites or all historical fixtures.

All four source hashes/metadata, pinned code/accepted evidence/methods and 73 historical preflight files must remain unchanged. Database bytes must be unchanged across read-only phases; private databases, spools and spills are removed. No learner database is opened. Anonymous category IDs are intentionally published as aggregate labels; raw event/category-history records and visitor/item/transaction identifiers are not published or logged.

```powershell
python validation/preflight_retailrocket_category_funnel_time_cohorts.py --duckdb "E:/DuckDB/duckdb.exe" --output "data/retailrocket_category_funnel_time_cohorts_preflight.json"
```

Measured results will be appended after the bounded preflight. Learner SQL75 execution and screenshot acceptance follow assistant validation.

## Executed results

The assistant preflight completed on 2026-11-09T11:13:17.609252+00:00 with DuckDB v1.5.5 (Variegata) d8cdaa33fd. One bounded real-source attempt completed the four declared CLI phases. All 30 rows passed, and the complete independent source-derived report matched every label, count, NULL and four-place percentage. The combined counts for **every one of SQL74's 15 groups** matched its accepted report; this check was not limited to grand totals.

All three rate columns below are percentages. Category IDs are anonymous aggregate labels. The same global top-category order is retained in both cohorts.

| cohort | segment | categoryid | eligible_pairs | cart_pairs | transaction_pairs | cart_rate_pct | transaction_rate_pct | cart_to_transaction_rate_pct | check_status |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| EARLY | TOP_CATEGORY | 1051 | 14204 | 275 | 100 | 1.9361 | 0.7040 | 36.3636 | PASS |
| EARLY | TOP_CATEGORY | 1483 | 12192 | 147 | 48 | 1.2057 | 0.3937 | 32.6531 | PASS |
| EARLY | TOP_CATEGORY | 959 | 10121 | 278 | 96 | 2.7468 | 0.9485 | 34.5324 | PASS |
| EARLY | TOP_CATEGORY | 342 | 8231 | 163 | 48 | 1.9803 | 0.5832 | 29.4479 | PASS |
| EARLY | TOP_CATEGORY | 1613 | 14022 | 268 | 33 | 1.9113 | 0.2353 | 12.3134 | PASS |
| EARLY | TOP_CATEGORY | 683 | 10214 | 278 | 71 | 2.7218 | 0.6951 | 25.5396 | PASS |
| EARLY | TOP_CATEGORY | 5 | 4439 | 88 | 28 | 1.9824 | 0.6308 | 31.8182 | PASS |
| EARLY | TOP_CATEGORY | 1279 | 8125 | 121 | 28 | 1.4892 | 0.3446 | 23.1405 | PASS |
| EARLY | TOP_CATEGORY | 196 | 5413 | 128 | 59 | 2.3647 | 1.0900 | 46.0938 | PASS |
| EARLY | TOP_CATEGORY | 646 | 6951 | 155 | 28 | 2.2299 | 0.4028 | 18.0645 | PASS |
| EARLY | OTHER_MAPPED | NULL | 446790 | 11019 | 4000 | 2.4663 | 0.8953 | 36.3009 | PASS |
| EARLY | UNKNOWN_REFERENCE | NULL | 0 | 0 | 0 | NULL | NULL | NULL | PASS |
| EARLY | BEFORE_FIRST | NULL | 286243 | 7006 | 2539 | 2.4476 | 0.8870 | 36.2404 | PASS |
| EARLY | NO_HISTORY | NULL | 93994 | 290 | 105 | 0.3085 | 0.1117 | 36.2069 | PASS |
| EARLY | TOTAL | NULL | 920939 | 20216 | 7183 | 2.1952 | 0.7800 | 35.5313 | PASS |
| LATE | TOP_CATEGORY | 1051 | 33759 | 596 | 209 | 1.7655 | 0.6191 | 35.0671 | PASS |
| LATE | TOP_CATEGORY | 1483 | 29092 | 467 | 193 | 1.6053 | 0.6634 | 41.3276 | PASS |
| LATE | TOP_CATEGORY | 959 | 22404 | 591 | 224 | 2.6379 | 0.9998 | 37.9019 | PASS |
| LATE | TOP_CATEGORY | 342 | 22232 | 316 | 85 | 1.4214 | 0.3823 | 26.8987 | PASS |
| LATE | TOP_CATEGORY | 1613 | 11083 | 215 | 43 | 1.9399 | 0.3880 | 20.0000 | PASS |
| LATE | TOP_CATEGORY | 683 | 9933 | 210 | 63 | 2.1142 | 0.6342 | 30.0000 | PASS |
| LATE | TOP_CATEGORY | 5 | 15267 | 233 | 100 | 1.5262 | 0.6550 | 42.9185 | PASS |
| LATE | TOP_CATEGORY | 1279 | 10050 | 188 | 30 | 1.8706 | 0.2985 | 15.9574 | PASS |
| LATE | TOP_CATEGORY | 196 | 11812 | 285 | 121 | 2.4128 | 1.0244 | 42.4561 | PASS |
| LATE | TOP_CATEGORY | 646 | 9721 | 117 | 29 | 1.2036 | 0.2983 | 24.7863 | PASS |
| LATE | OTHER_MAPPED | NULL | 811151 | 18673 | 6826 | 2.3020 | 0.8415 | 36.5555 | PASS |
| LATE | UNKNOWN_REFERENCE | NULL | 0 | 0 | 0 | NULL | NULL | NULL | PASS |
| LATE | BEFORE_FIRST | NULL | 18162 | 620 | 251 | 3.4137 | 1.3820 | 40.4839 | PASS |
| LATE | NO_HISTORY | NULL | 116705 | 420 | 163 | 0.3599 | 0.1397 | 38.8095 | PASS |
| LATE | TOTAL | NULL | 1121371 | 22931 | 8337 | 2.0449 | 0.7435 | 36.3569 | PASS |

EARLY contains 920,939 eligible pairs, 20,216 qualifying carts and 7,183 qualifying transactions; LATE contains 1,121,371 pairs, 22,931 carts and 8,337 transactions. Their sums remain 2,042,310 / 43,147 / 15,520. Overall cart rates are 2.1952% and 2.0449%, transaction rates 0.7800% and 0.7435%, and cart-to-transaction rates 35.5313% and 36.3569% respectively. These are local cohort rates, not additive percentages.

The earlier descriptive pattern for category 1613 is visible in both blocks: cart-to-transaction rates are 12.3134% EARLY and 20.0000% LATE, compared with the respective overall rates of 35.5313% and 36.3569%. This supports a further diagnostic question; two unequal blocks do not establish statistical significance, seasonality, causation or a durable performance effect. The anonymous category code does not reveal the product type.

Category coverage differs substantially across these first-view cohorts. Mapped eligible pairs are 540,702 of 920,939 EARLY (58.7120%) and 986,504 of 1,121,371 LATE (87.9730%). BEFORE_FIRST contains 286,243 EARLY pairs but 18,162 LATE pairs. This reflects the relationship between first views and the supplied category observation history, not proof of business improvement or newly reliable capture. Keeping unmatched buckets visible prevents these different populations from silently disappearing. UNKNOWN_REFERENCE remains an explicit zero row in both cohorts, with NULL rates.

The split remains exactly 1435708800000 ms (2015-07-01T00:00:00.000000Z). It applies only to first observed view. Qualifying follow-up across the split stays attached to its original cohort and first-view+7-day deadline. The observation endpoint/cutoff remain 1442545187788 / 1441940387788 ms. Both period durations and their product/traffic/coverage mixes differ; counts cannot be interpreted as growth, and rate changes cannot be attributed solely to time.

The independent proof compared every one of 2,756,101 event occurrences across all ten queried fields, preserving all 460 duplicate surplus occurrences. It fully drained 788,214 category observations and independently verified all 1,669 reference IDs. It folded 2,145,179 observed pairs and 2,132,127 viewed pairs into the unchanged eligible cohort. Global first-view category coverage still reconciles to SQL73 and all category groups reconcile to SQL74.

The maximum current-item history contained 18 observations; only one current pair state was retained. There were 1,136 mapped category groups and a maximum of 1,138 aggregate groups including populated unmatched buckets. Their two-cohort storage used 2,276 counter cells, below the 3,344-cell limit. No all-pair or all-item history dictionary was retained. Only grouped anonymous category IDs are published; real visitor/item/transaction identifiers and raw event/category-history rows are not published or logged.

Three focused fixture families passed. They verify the exact split, cross-boundary EARLY follow-up, fixed global labels despite different local cohort ranking, empty cohorts/groups, zero eligible populations, strict stage timing, shared deadlines, first-view attribution and duplicates. Three invalid cases—wrong split, wrong per-group contract while the grand total remains unchanged, and conflicting earliest-view snapshots—each suppressed TOP_CATEGORY IDs and produced ten NULL/BLOCKED placeholders. No prior full suite or historical fixture suite was rerun.

Measured CLI phases took 9.213 seconds for category-only history/reference construction, 9.585 seconds for event/category enrichment, 14.875 seconds for SQL75, and 39.908 seconds for the complete independent stream/cohort fold. Python category/event scan-sorts took 20.981 / 28.78 seconds. Hashing and fixtures are excluded. Only enrichment used the declared 2GB memory/4GB spill allowance; other phases used 1GB/2GB, all with two threads and 120-second limits.

The private database was 118,239,232 bytes before cleanup, and the largest observed post-phase private directory was 265,048,926 bytes, below the 7GB budget. These measurements are not continuous peaks. Database bytes were unchanged across read-only phases. All four source hashes/metadata, pinned dependencies and 73 historical preflight evidence files remained unchanged. Private databases, spills and spools were removed. No learner database was opened. Both property CSVs were scanned but availability history was not reconstructed; stored UTC fields were not read, and the full SQL69 reconstruction and SQL62 hierarchy were not rerun. Prior code and accepted evidence were read only to pin dependencies, not to rerun their analyses.

Report fingerprint: `76a51f4c3c545a747fa3748fb6ecc18ebcf30b1777ab78ad10f8abe651d8c4fc`. Script SHA-256: `4abb202fc3d63650ca9f6dc36d2d1e74751d07fac057842c04e59dd747fafb2d`. Validator SHA-256: `b1ed5cb0612f53c9216a1b427a89a6c690ba7c214595883bb17fbf857b774ad9`. The original 10,179-byte frozen prefix remains unchanged (`37bc38da4693e6173afea477dedbca8090b53b4e2d981f1dc37587686dee8859`). Aggregate evidence: [retailrocket_category_funnel_time_cohorts_preflight.json](../data/retailrocket_category_funnel_time_cohorts_preflight.json).

Assistant preflight is complete. Learner SQL75 execution and screenshot acceptance remain pending.

## Learner screenshot acceptance — 9 November 2026

The learner supplied the SQL75 DBeaver report on 9 November 2026 (Australia/Sydney). All **thirty rows and ten column headers** are present, and all thirty statuses are **PASS**. Of **300 result-field positions**, **298 complete fields are directly visible**. The segment cells in rows **12 and 27** show only **UNKNOWN_REFEREN**; the full labels are not visually verified. They are uniquely resolved to **UNKNOWN_REFERENCE** from the frozen allowed labels, fixed position between OTHER_MAPPED and BEFORE_FIRST, matching cohort, and the visible NULL category ID, zero counts and NULL rates. See the [learner acceptance record](../data/retailrocket_category_funnel_time_cohorts_learner_acceptance.json). **This acceptance does not claim that all 300 fields are fully visible.**

Visibility comprises **90 integer counts, 20 non-null aggregate category IDs, 84 non-null rates, 16 genuine NULL cells, 30 cohort labels, 28 complete segment labels and 30 statuses**, totalling 298 complete fields. The remaining two labels are contract-resolved. The sixteen NULLs are ten category IDs and six rates; the cropped prefixes are preserved as strings in observed_rows and are not confused with database NULLs. Ten shortened decimal displays are retained literally before exact four-place Decimal normalization. The resolved report fingerprint is `76a51f4c3c545a747fa3748fb6ecc18ebcf30b1777ab78ad10f8abe651d8c4fc`.

The accepted EARLY total is **920,939 eligible pairs, 20,216 cart pairs and 7,183 transaction pairs**, with rates **2.1952%, 0.7800% and 35.5313%**. LATE totals **1,121,371, 22,931 and 8,337**, with rates **2.0449%, 0.7435% and 36.3569%**. The same global category codes/order are retained in both cohorts, and each corresponding group's counts reconcile to SQL74. Category attribution and cohort assignment remain fixed at first observed view; qualifying follow-up may cross 1 July within the same original seven-day deadline.

The first-view intervals have unequal duration and can differ in composition and capture coverage. Raw count differences do not establish growth; local rates must be read with their denominators. This descriptive comparison does not establish statistical significance, seasonality or causality. Unknown buckets remain history-coverage states rather than proof that the customer-facing website lacked classification.

All **18,836 prior method bytes**, including the **10,179-byte frozen prefix** and the final executed-results appendix, are preserved exactly. The accepted pre-append method SHA-256 is `31deabb1b06eecfec63301a94cdc25d28f1cf88bc7021c232c7dff6e824f70b8`. This operation appends explicit UTF-8 bytes and does not decode/re-encode or rewrite the prior content. Frozen SQL75, validator, preflight and **34 pinned dependencies** remain unchanged. Historical pending statements remain as written; current acceptance is appended with its label-visibility caveat.

No source CSV, learner database, SQL preflight or fixture was opened or rerun for acceptance. The record contains grouped anonymous category codes and aggregates; no screenshot, raw events, visitor/item/transaction identifiers or category-history details were copied into the repository. No fresh verification of availability, stored UTC-derived fact fields, the full production fact, category hierarchy or learner conceptual understanding is claimed.
