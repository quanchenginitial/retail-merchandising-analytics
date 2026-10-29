# Weekly price context for the accepted A × Z product case

29 October 2026. SQL31's eleven-row store comparison is accepted from the learner screenshot, with the canonical report fingerprint matching independent preflight. [SQL32](../sql/32_az_leading_product_price_context.sql) adds published weekly price context for the same product. Assistant preflight passed; learner execution remains pending.

## Purpose and frozen scope

Inspect price observations alongside the recorded-unit trajectory to develop evidence-based questions. Selection remains the accepted first A × Z product by units_90d DESC, item_id ASC over 2016-01-26..2016-04-24. Display all twelve complete weeks of 2016-01-30..2016-04-22, with all ten stores present in the underlying 120-position grid.

Use the dataset's published store/item/week sell_price. Do not replace it with a sales-weighted realized price, infer transaction-level prices, or interpret descriptive associations as price elasticity, promotion attribution or a causal effect. Selection and classification remain unchanged.

## Twelve-column report

| Column | Definition |
| --- | --- |
| item_id | Same automatically selected product; local result only |
| week_start / week_end | Complete displayed retail week's DATE boundaries |
| units | Pooled recorded units, reconciled to the accepted weekly trajectory |
| priced_stores | Number of stores with an observed valid price this week |
| missing_price_stores | Number without a price; priced plus missing must equal ten |
| min_price_usd / max_price_usd | Minimum/maximum observed price across stores this week; NULL if no store has a price |
| comparable_stores | Stores with prices in both this week and the immediately preceding displayed week |
| price_up_stores | Comparable stores whose price increased |
| price_down_stores | Comparable stores whose price decreased |
| check_status | PASS after checks; EMPTY only for a valid empty cohort |

The first displayed week's comparable/up/down counts are NULL because there is no preceding week inside this analysis window. No outside-window price is imported to create a baseline. Thereafter count comparisons only when both current and immediately previous prices for the same store are non-NULL. An absent intermediate price breaks comparability: do not carry forward or skip gaps. If there are no comparable stores, all three comparison counts are zero; that does not establish unchanged prices. Unchanged comparable stores equal comparable minus up minus down.

All prices retain DECIMAL(18,2) precision, and directions compare the decimals directly. Store counts are not sales weights. Both zero-sales and positive-sales stores participate in price summaries when they have valid prices. No TOTAL row is appended to the twelve-week report.

## Validation and missing observations

Reuse SQL31's validation prefix unchanged, including accepted baseline classifications, selected product, complete selected daily records, raw/core store mappings and twelve-week reconciliation. Validate the four-column staging price schema in order: store_id VARCHAR, item_id VARCHAR, wm_yr_wk INTEGER, sell_price DECIMAL(18,2).

Inspect price records for the selected product in weeks 11601–11612; include a NULL-week selected-product record in validation so it is rejected. Require unique store/week keys, known stores, non-NULL positive prices and valid weeks for this scope. This does not re-audit every price row for all products or outside the window.

Construct every selected week crossed with every accepted store, attach seven-day unit totals and left join prices. Price absence remains NULL. Reject a positive-unit store/week with no price; permit absence for a zero-unit store/week. Verify exactly 120 grid positions for the current selection, no missing store/week unit totals, complete weekly output, priced-plus-missing counts and reconciliation of units to the accepted trajectory.

Compute LAG over the complete store/week grid so an absent price stays in the sequence. Compare same-store adjacent DECIMAL values only. Check count bounds and first-week NULL semantics before reporting PASS. A valid empty A × Z cohort yields one EMPTY sentinel with all eleven product/week/price fields NULL; invalid schema or in-scope input state still fails. The query is read-only.

## Independent verification and publication

The [runner](../validation/preflight_az_leading_product_price_context.py) and [aggregate evidence](../data/az_leading_product_price_context_preflight.json) record verification in a private temporary database. The learner's persistent database is never opened.

Original sales/calendar data independently establish all product labels, selected product, store/day values and the accepted store report fingerprint. Independently read relevant original sell_prices.csv observations, enforce the accepted source text contract and positive exact cents, then compare them against a separately staged DuckDB price projection. Build an independent 120-position grid and twelve-row report; compare every output column, order, NULL, coverage and same-store direction.

Verify registered hashes of all three original CSVs before/after, preserve historical preflight records, and compare the five complete analytical snapshots plus the relevant daily/store/price projections before/after the query. These scoped checks do not claim full-history fact/price-table equality. Remove the private temporary database after verification.

Publish aggregates and SHA-256 fingerprints only. Real item/store identifiers, store prices, weekly rows, raw arrays and screenshots are not published. Keep [SQL31 learner acceptance](../data/az_leading_product_store_comparison_learner_acceptance.json) distinct from new assistant preflight.

## Preflight results

All 3,049 combined products across twenty-two fields matched independent references, as did 840 selected daily rows across six fields and the accepted store-report fingerprint. All 120 relevant original price rows across four fields matched the independently staged projection at exact cent precision. The independent reference covers all 120 store/week positions and every field of the twelve-row, twelve-column output, including chronological order, price extrema, counts and first-week NULLs. The evidence distinguishes grid positions covered from the directly compared source price/daily rows and final report fields.

| Aggregate control | Result |
| --- | ---: |
| Displayed weeks / pooled units | 12 / 2,730 |
| Priced / missing-price store-weeks | 120 / 0 |
| Observed price range over all selected stores and weeks | USD 2.00–2.68 |
| Comparable same-store adjacent-week transitions | 110 |
| Price increases / decreases / unchanged transitions | 2 / 1 / 107 |
| First-week comparable/up/down fields | NULL / NULL / NULL |

The 110 transitions represent ten stores each compared across eleven adjacent-week pairs, not 110 distinct stores. The whole-window price range combines observations across stores and time; it is not a claim that every store moved from USD 2.00 to USD 2.68. Most observed adjacent-week prices were unchanged, but this descriptive count cannot quantify how much of the sales pattern is attributable to price.

All 36 targeted cases passed: eight valid cases and twenty-eight expected rejections. Valid cases cover exact-cent changes and equal prices, reverse input ordering, missing-price gaps and returns, an entirely unpriced zero-sales week, first-week NULL behavior with missing prices, valid empty cohorts, unused daily price fields and out-of-scope records. Rejection cases cover malformed price schema, duplicate/null/orphan/nonpositive price keys or values, missing positive-sales prices, invalid empty mappings, and retained daily completeness, store-mapping and upstream snapshot guards.

The five full analysis snapshots and four relevant projections (selected daily rows, core mapping, distinct raw mapping, selected prices) remained unchanged. All three registered CSV hashes and all 30 historical preflight records remained unchanged; private databases were removed. DuckDB v1.5.5 used two threads and a 2GB memory limit. SQL32 took 0.528 seconds in the private CLI run; the separate Python stream of the original price CSV took 9.150 seconds. These timings exclude other Python comparisons and hashing and are not performance guarantees. Public evidence contains aggregate controls and matching fingerprints only.

## Interpretation limits

A movement in the cross-store min/max range may reflect changed price coverage or store composition; same-store adjacent comparisons provide more specific descriptive evidence. An unchanged weekly price does not rule out unobserved transaction-level discounts or non-price factors. A lower price is not itself a documented promotion, and missing price is not proof of inventory unavailability. A short selected-product case cannot identify causal demand response or justify replenishment quantities.
