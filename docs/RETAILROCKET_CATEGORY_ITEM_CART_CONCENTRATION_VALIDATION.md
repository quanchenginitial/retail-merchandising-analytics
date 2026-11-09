# Retailrocket category 1613 item cart-volume concentration

This SQL76 contract is frozen on 9 November 2026 before fixtures or source execution. It examines how qualified cart pairs are distributed across items within first-view category 1613, and compares a pooled cart-to-transaction rate with the arithmetic mean of positive-cart item rates. Category 1613 was chosen after observing earlier aggregate results, so this is exploratory diagnosis, not independent confirmation or a preselected hypothesis test.

## Scope, item universe and bands

The query is read-only and global over the accepted seven-day-eligible visitor-item cohort. It reads the same original five event fields and five category snapshot fields from rr_mart.events_enriched as SQL74/75, plus only categoryid from rr_core.dim_category. Availability, stored UTC fields, reference hierarchy and sessions are outside the readset. No item time-cohort split, ranking or top-item list is introduced.

The population remains first observed view +604800000 milliseconds <= the all-event endpoint 1442545187788 ms (2015-09-18T02:59:47.788000Z). The eligible first-view cutoff is 1441940387788 ms (2015-09-11T02:59:47.788000Z). A qualifying cart is strictly after that first view and within its inclusive seven-day deadline. A qualifying transaction is strictly after that cart and within the same deadline; the clock never restarts at cart. Same-millisecond ties do not prove order. Incomplete follow-up pairs are excluded before outcomes.

Category attribution is fixed at the earliest observed view. All eligible first-view ties must have the same NULL-aware value/from/to/provenance/coverage tuple. Safe numeric membership resolves the original category value against the static reference without changing its text. Later category changes do not reassign the pair. The selected item universe comprises items with at least one eligible pair whose fixed first-view category is MAPPED category 1613. Pairs for the same item assigned to another first-view category do not enter its target-category counts.

For each selected item, eligible_pairs, cart_pairs and transaction_pairs count binary qualified pair stages, not raw event repetitions or orders. Source duplicate surplus 460 is preserved. Each item is assigned once by its total qualified cart-pair count across this entire target-category cohort: ZERO_CART = 0; CART_01_04 = 1 through 4; CART_05_19 = 5 through 19; CART_20_PLUS = at least 20. These thresholds are explicit exploratory choices, not universal or optimized cutoffs. TOTAL combines every selected item. There is no ranking buffer or public item identifier.

The target counts must reconcile to accepted SQL74 category 1613: 25,105 eligible pairs, 483 cart pairs and 76 transaction pairs. The sum of its accepted SQL75 EARLY/LATE category rows must confirm the same counts. SQL76 does not introduce cohort outputs or use the period split to assign bands. Whole-source flow and coverage controls remain unchanged from SQL72/73.

## Five-row, ten-column report

The fixed row order is ZERO_CART, CART_01_04, CART_05_19, CART_20_PLUS and TOTAL. Columns are cart_volume_band, item_count, eligible_pairs, cart_pairs, transaction_pairs, cart_share_pct, weighted_cart_to_transaction_rate_pct, mean_item_cart_to_transaction_rate_pct, zero_transaction_cart_items and check_status. Empty bands remain visible.

item_count is the number of selected items in that band. cart_share_pct is 100*band_cart_pairs/category_cart_pairs. The weighted cart-to-transaction rate is 100*SUM(item_transaction_pairs)/SUM(item_cart_pairs), so items with more qualifying carts receive more weight. The mean item rate is 100*AVG(item_transaction_pairs/item_cart_pairs) over cart-positive items only; each such item receives equal weight. SQL computes item ratios without prior rounding, averages them, and only then rounds the displayed percentage to four places.

TOTAL's mean is computed directly over all positive-cart items, not by averaging the four displayed band means. Equivalently, valid band means would need weights equal to their positive-cart item counts, not their total item counts or cart volumes. ZERO_CART items do not enter any mean-rate denominator. zero_transaction_cart_items counts items with cart_pairs>0 and transaction_pairs=0 in this specific eligible cohort/window; it does not mean items that have never sold.

When the denominator is zero, the relevant rate remains NULL. Thus ZERO_CART has NULL weighted and mean rates and, when category carts are positive, a 0.0000 cart share. Empty positive-cart bands also have NULL rates. With no category carts, every cart share and all rates are NULL, including TOTAL. With a positive denominator and zero qualifying transactions, the rate is 0.0000. Four-place DECIMAL output is preserved as four-place JSON strings in evidence.

Exact item and pair counts reconcile from the four disjoint bands to TOTAL. Nested counts require eligible >= carts >= transactions; zero-transaction cart items cannot exceed positive-cart items, which cannot exceed item_count. The mean is NULL exactly when no positive-cart items exist. Rounded displayed cart shares need not sum literally to 100.0000; only unrounded count reconciliation is tested.

The inherited source/schema/temporal/reference/first-view/cohort controls remain active, followed by target-category parent-count reconciliation and band partitions. Invalid admission or reconciliation yields all five fixed labels with every count/rate metric NULL and BLOCKED status. Missing required tables/columns can fail binding. No per-item diagnostic row or real item/visitor/transaction identifier is published. The selected category ID 1613 is aggregate context in code/method/evidence, not a report column.

## Interpretation boundaries

Pooled and item-mean rates answer different questions. Their difference alone does not prove that a problem is widespread or confined to a few items. Item rates based on one or a few carts are sparse and unstable; zero observed qualifying transactions is not proof of failure, stockout, lost sales or zero lifetime purchases. Cart-share and item-count distributions describe concentration under this chosen population, not best/worst products or causal drivers.

The seven-day horizon and target category were not optimized or independently validated here. First observed view is subject to the left data boundary, the global endpoint is not proof of continuous capture, and last-recorded category assignment is not verified freshness or business truth. Product/traffic mix, price, availability, exposures and measurement gaps can affect the results. No causal intervention, significance test, forecast, seasonality claim or business uplift is estimated.

## Independent bounded source proof

Reusable SQL74/73 helpers are imported without running their main functions or prior full suites. The four sources are events.csv, category_tree.csv and both item_properties CSVs. Both property files are scanned completely, retaining only 788,214 category observations. Category-only interval construction preserves original values/provenance, rejects conflicting keys and uses the accepted latest-past observation convention. The private ID-only reference must equal all 1,669 independently parsed source IDs. The full SQL69 fact and SQL62 hierarchy are not rebuilt; availability history is not reconstructed and stored UTC fields are not read.

Four private CLI phases retain the frozen resource limits: (1) category-only import/intervals plus complete ID-only reference projection: two threads, 1GB memory, 2GB spill, 120 seconds; (2) frozen SQL54/63 event creation prefixes plus category-only ten-field enrichment: two threads, 2GB memory, 4GB spill, 120 seconds; (3) read-only SQL76 report: two threads, 1GB/2GB, 120 seconds; (4) complete read-only ten-field source comparison with independent item/band folding: two threads, 1GB/2GB, 120 seconds. At least 8GB free space and a 7GB private-directory budget are required. Post-phase directory observations are not continuous peaks; source scans/sorts are timed separately.

Python independently sorts category observations numerically by item/time and events by item/visitor/time/event/transaction in chunks of at most 50,000 rows. It retains one current item's category history (cap 50,000), one current pair's first-view/category/cart/transaction state, one current item's selected-pair counters, four band aggregates and global control counts. When an item closes, its band and aggregates are finalized and its identifier/counters are discarded. No all-item aggregate map, all-pair map, item-ranking heap or list of selected items is retained.

All 2,756,101 original event occurrences are compared across the complete ten-field readset, including original fields, category bounds/value/provenance/status, NULLs and duplicate multiplicity. All selected history is drained even for items without events. The independent fold selects category-1613 pairs from their first-view snapshot, computes each item's complete counts, assigns the volume band and accumulates exact Fraction sums of unrounded item transaction/cart ratios. Decimal arithmetic then independently rounds shares, pooled rates and means to four places. TOTAL combines exact fraction sums and positive-cart item counts; it never averages rounded band means.

Focused fixtures cover band edges 0,1,4,5,19,20; unequal item cart volumes with different pooled and mean rates; correct TOTAL mean; zero-transaction positive-cart items; zero-cart/no-selected-item cases; fixed first-view category despite later changes; same-item pairs attributed elsewhere; strict timing, shared deadline and duplicate preservation. Parent-target count failure and inconsistent first-view snapshots block all metrics. No historical full fixture suite is rerun.

All four source hashes/metadata, pinned code/accepted evidence/methods and 74 historical preflight files must remain unchanged. Private database bytes must be unchanged across read-only phases. Databases, source spools and spills are removed. No learner database is opened and no real item, visitor, transaction or raw history records are published or logged. Only aggregate counts/rates and target category context are retained.

```powershell
python validation/preflight_retailrocket_category_item_cart_concentration.py --duckdb "E:/DuckDB/duckdb.exe" --output "data/retailrocket_category_item_cart_concentration_preflight.json"
```

Measured results will be appended after the bounded preflight. Learner SQL76 execution and screenshot acceptance follow assistant validation.

## Executed results

The assistant preflight completed on 2026-11-09T11:35:36.500692+00:00 with DuckDB v1.5.5 (Variegata) d8cdaa33fd. One bounded real-source attempt completed the four declared CLI phases. All five rows passed. Every count, NULL, share, pooled rate and item-mean rate matched the independent source fold and Fraction/Decimal reference.

All share and rate columns below are percentages. The report contains no item identifiers or category-ID column; category 1613 is the fixed aggregate analysis context.

| cart_volume_band | item_count | eligible_pairs | cart_pairs | transaction_pairs | cart_share_pct | weighted_cart_to_transaction_rate_pct | mean_item_cart_to_transaction_rate_pct | zero_transaction_cart_items | check_status |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| ZERO_CART | 1010 | 9047 | 0 | 0 | 0.0000 | NULL | NULL | 0 | PASS |
| CART_01_04 | 116 | 8298 | 220 | 30 | 45.5487 | 13.6364 | 13.8649 | 88 | PASS |
| CART_05_19 | 35 | 7760 | 263 | 46 | 54.4513 | 17.4905 | 17.3003 | 10 | PASS |
| CART_20_PLUS | 0 | 0 | 0 | 0 | 0.0000 | NULL | NULL | 0 | PASS |
| TOTAL | 1161 | 25105 | 483 | 76 | 100.0000 | 15.7350 | 14.6612 | 98 | PASS |

The target universe contains 1,161 items and reconciles exactly to 25,105 eligible pairs, 483 qualified cart pairs and 76 qualified transaction pairs in accepted SQL74 and the combined category-1613 rows of SQL75. Of those items, 151 have at least one qualifying cart; 1,010 have none in this specific first-view-category, seven-day ordered-path definition. ZERO_CART does not mean no lifetime sales or no raw cart events outside this definition.

The 116 items with one to four qualified carts contribute 220 carts (45.5487%). The 35 items with five to nineteen carts contribute 263 (54.4513%). No selected item has twenty or more qualified carts. This describes the chosen volume distribution, while the coarse bands do not identify individual concentration within a band or establish which items cause the category-level rate.

The pooled cart-to-transaction rate is 15.7350%; the equal-weight mean across all 151 positive-cart items is 14.6612%. The low-volume band has pooled/mean rates of 13.6364% / 13.8649%; the five-to-nineteen band has 17.4905% / 17.3003%. TOTAL's item mean comes from the exact sum of all positive-cart item ratios divided by 151, not an average of the displayed band means. Their difference alone does not prove a widespread problem or isolate a small set of causal drivers.

There are 98 positive-cart items with zero qualifying transaction pairs: 88 in the one-to-four-cart band and 10 in the five-to-nineteen band. Those counts are highly dependent on sparse denominators and the defined observation window. They do not establish that these items never sold, caused lost sales, were unavailable or should be removed. Category 1613 was selected after its earlier aggregate rates were observed; the present result is exploratory diagnosis, not independent confirmation or statistical evidence of a business failure.

The independent proof compared all 2,756,101 event occurrences across the complete ten-field readset, retaining all 460 duplicate surplus occurrences. It fully drained 788,214 selected category observations and independently matched the complete set of 1,669 reference IDs. Whole-source eligible/cart/transaction counts and first-view coverage remain unchanged. Per-item counters admitted only pairs whose fixed first-view category was 1613, even where later snapshots changed or the same item had other-category pairs.

At most 18 category observations were held for the current item, with one current pair state, one current item counter and four band aggregates. Selected item identifiers were discarded when their aggregates closed; no all-item aggregate map, selected-item list or ranking heap was retained. Exact Fraction sums of item transaction/cart ratios supplied the independent mean reference. No real item, visitor, transaction or raw history records were published or logged.

Three focused fixture families passed, including five blocked-admission cases. The unequal-volume fixture covered cart-count edges 0, 1, 4, 5, 19 and 20, yielding selected counts [51,49,14], pooled rate 28.5714% and item mean 39.0526%. It also verified direct TOTAL mean aggregation, zero-transaction cart items, fixed category attribution, same-item non-target exclusion, strict timing, shared deadlines, duplicates and zero/no-target populations. Incorrect target parent counts/selector or conflicting first-view snapshots produced five NULL/BLOCKED rows. No historical full fixture suite or previous full analysis suite was rerun.

Measured CLI phases took 3.17 seconds for category-only history/reference construction, 6.863 seconds for event/category enrichment, 5.921 seconds for SQL76, and 28.252 seconds for the complete independent stream/item fold. Python category/event scan-sorts took 17.941 / 23.508 seconds. Hashing and fixtures are excluded. Only enrichment used the declared 2GB memory/4GB spill allowance; other phases used 1GB/2GB, all with two threads and 120-second limits.

The private database was 119,025,664 bytes before cleanup; the largest observed post-phase private directory was 265,835,358 bytes, below the 7GB budget. These observations are not continuous peaks. Database bytes were unchanged across read-only phases. All four source hashes/metadata, pinned dependencies and 74 historical preflight files remained unchanged. Private databases, source spools and spills were removed. No learner database was opened. Both property CSVs were scanned, but availability history was not reconstructed; stored UTC fields were not read, and full SQL69 reconstruction and SQL62 hierarchy were not rerun. Prior artifacts were read only to pin dependencies.

Report fingerprint: `66dc73eec2f5edbaf0e5369e39dcae9f289e246c3a7100e2d1a260839961bfcb`. Script SHA-256: `1ccdecabfe3f2ed017d686c24e70e0e47ccaca2b55e45960b0f473da055245b8`. Validator SHA-256: `6c414d9c5bb83d1882374bf9b4f0e8416b0f498e9d7cbca738c947da38b52896`. The original 10,635-byte frozen prefix remains unchanged (`66cdc63127de43a55421f280d1a69fd52bcc809b59861303fd02cb92290446fd`). Aggregate evidence: [retailrocket_category_item_cart_concentration_preflight.json](../data/retailrocket_category_item_cart_concentration_preflight.json).

Assistant preflight is complete. Learner SQL76 execution and screenshot acceptance remain pending.

## Learner screenshot acceptance — 9 November 2026

The learner supplied the SQL76 DBeaver report on 9 November 2026 (Australia/Sydney). All **five rows, ten column headers and fifty result fields** are fully visible, with **five PASS statuses** and no hidden or contract-resolved labels. See the [learner acceptance record](../data/retailrocket_category_item_cart_concentration_learner_acceptance.json).

The visible fields comprise **25 integer counts, 11 non-null percentage values, four genuine NULL rates, five complete band labels and five statuses**. The displayed cart-share values 0, 0 and 100, plus the TOTAL weighted rate 15.735, are preserved literally before exact normalization to 0.0000, 0.0000, 100.0000 and 15.7350. All other displayed percentage strings already show four places. The complete normalized report matches the assistant evidence with fingerprint `66dc73eec2f5edbaf0e5369e39dcae9f289e246c3a7100e2d1a260839961bfcb`.

The accepted TOTAL is **1,161 items, 25,105 eligible pairs, 483 cart pairs and 76 transaction pairs**. **1,010 items have no qualifying carts**, while 151 have positive carts. Among the positive-cart items, **98 have no qualifying transaction** under this particular first-view-category cohort, strict event order and seven-day deadline. The pooled cart-to-transaction rate is **15.7350%**; the equal-weight mean of unrounded positive-cart item ratios is **14.6612%**. CART_01_04 contains 116 items and 220 cart pairs (45.5487% of carts); CART_05_19 contains 35 items and 263 cart pairs (54.4513%). CART_20_PLUS is empty: its zero counts and two NULL rates are valid and retained. Counts reconcile exactly from the four disjoint bands to the category TOTAL.

Category 1613 was selected after its earlier aggregate rate was observed, so this remains exploratory follow-up rather than independent confirmation. Pooled and item-mean rates answer different questions, and their difference alone does not establish how broadly a problem occurs or what caused it. Sparse denominators remain uncertain. Zero qualifying transactions is specific to this cohort/window/path and does not mean a product has never sold. The thresholds are not proven optimal, and no causal or intervention result is claimed.

All **17,071 prior method bytes**, including the **10,635-byte frozen prefix** and the existing executed-results appendix, are preserved exactly. The pre-append method SHA-256 is `1e14e857cdeace42943ce08699d110d0f366992b2d2dffd9a067d368c8451340`. This operation appends explicit UTF-8 bytes without decoding/re-encoding or rewriting any prior content. Frozen SQL76, validator, preflight and all **38 pinned dependencies** remain unchanged. Historical pending statements remain as written; current learner acceptance is recorded here.

No source CSV, learner database, SQL preflight or fixture was opened or rerun for acceptance. No screenshot, raw event, visitor/item/transaction identifier or category-history detail was copied into the repository. Only the five aggregate band rows are recorded. This acceptance does not reverify unqueried availability, stored UTC-derived fact fields, the full production fact, reference hierarchy or learner conceptual understanding.
