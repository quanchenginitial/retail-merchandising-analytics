# Store comparison for the accepted A × Z product case

29 October 2026. SQL30's twelve-week trajectory is accepted from the learner screenshot, with selected-product, ordered-trajectory and weekly-vector fingerprints matching preflight. [SQL31](../sql/31_az_leading_product_store_comparison.sql) compares the same selected product across every store. Assistant preflight passed; learner execution remains pending.

## Purpose and fixed scope

Locate the observed unit difference by store before generalizing from the pooled trajectory. Select exactly the same first accepted A × Z product by 90-day units DESC, item_id ASC; no actual identifier is hardcoded. Retain the original ABC selection window 2016-01-26..2016-04-24 and XYZ window 2016-01-30..2016-04-22.

Split the latter into equal forty-two-day halves: 2016-01-30..2016-03-11 (retail weeks 11601–11606), and 2016-03-12..2016-04-22 (11607–11612). These are two consecutive six-week blocks within the same accepted trajectory. They do not redefine ABC/XYZ or replace the original selection window.

## Eleven-column report

| Column | Definition |
| --- | --- |
| item_id | Same automatically selected product on every row |
| store_id | All ten accepted stores in ascending identifier order, followed by TOTAL |
| state_id | Exact source store/state mapping; NULL on TOTAL |
| units_first6w | Store units in the first forty-two-day window |
| units_last6w | Store units in the last forty-two-day window |
| unit_difference | units_last6w minus units_first6w; retain negative differences |
| late_unit_share_pct | Store last-window units / all-store last-window units × 100 |
| units_84d | Store first plus last window units |
| first6w_window | 2016-01-30..2016-03-11 |
| last6w_window | 2016-03-12..2016-04-22 |
| check_status | PASS after integrity and reconciliation checks; EMPTY only for a valid empty cohort |

The last-window share describes where the later volume was recorded; it is not a share of net change. Do not divide by the net difference or call this an increment-contribution percentage. Rounded shares display four decimals and need not sum precisely to 100%. TOTAL divides the unrounded last-window total by itself when positive. If the last-window total is zero, every share including TOTAL is NULL.

All ten stores are present, including true zero-unit stores. TOTAL is a rollup, never an eleventh store; its state is NULL because the rows span multiple states. The selected product identifier is retained locally so the analysis object remains explicit. Store ordering carries no performance ranking.

## Input scope and integrity

Reuse SQL30's complete validation prefix unchanged: accepted source weekly records, metrics, exact classifications, combined snapshot, deterministic product selection and twelve-week trajectory controls.

Validate the two-column core store schema, expected unique nonblank store count, and exact two-way equality to distinct store_id/state_id projected from the raw sales table. Never infer state from an identifier prefix. Reject the reserved TOTAL identifier to avoid ambiguity in the rollup. The raw projection reads existing database columns, not external CSVs in the learner query.

The daily fact has nine fields in the accepted project. This query validates and uses only six: item_id/store_id/d VARCHAR, date DATE, wm_yr_wk/units INTEGER. Price, price-presence and estimated-value fields do not participate; a private preflight may therefore use a six-column daily fixture.

For the selected product and accepted 84-day window, require exactly 840 daily rows: ten stores times 84 dates. Each store must have 84 distinct day IDs and dates, both exact endpoints, and forty-two observations in each half. Validate nonnegative non-NULL units, recognized store keys, exact d-to-date mapping from 2011-01-29, and exact retail-week assignment. Duplicate/missing days cannot compensate for each other.

Aggregate the selected daily slice into twelve weekly totals and reconcile both ways against the accepted trajectory before presenting store comparisons. Store totals must reconcile to both six-week totals and the selected product's 84-day total. Left joins preserve actual zero-sales stores, but missing coverage fails validation rather than being accepted as zero.

A singleton health row ensures that invalid empty inputs cannot bypass validation. A valid empty A × Z cohort yields one EMPTY sentinel with all eight product/store/numeric fields NULL and both comparison windows retained. Otherwise return ten stores and TOTAL. The query creates or changes no database objects.

## Independent verification and publication

The [runner](../validation/preflight_az_leading_product_store_comparison.py) uses registered original sales/calendar CSVs in a private temporary database; the learner database is never opened. [Aggregate evidence](../data/az_leading_product_store_comparison_preflight.json) records source hashes, method and tests.

Independently derive all product labels and the selected product from original wide arrays, reconstruct the accepted SQL30 fingerprints, then compare all 840 selected store/day cells against the original source. Compute each store's two half-window totals and every eleven-column output row independently, preserving dates, signed differences, percentages, NULLs, TOTAL and ordering.

Before/after fingerprints cover the five accepted analysis snapshots plus the relevant selected daily projection and store mappings. These checks do not claim to re-audit every cell in the full-history daily fact. Prior accepted source-to-fact evidence remains the basis for that broader lineage. Preserve original CSVs and all historical preflight records; remove the private temporary database after verification.

Publish aggregate controls and SHA-256 fingerprints only. Do not save real selected identifiers, store-level product results, daily rows or screenshots in public files. [SQL30 learner acceptance](../data/az_leading_product_weekly_learner_acceptance.json) remains distinct from the independent SQL31 preflight.

## Preflight results

All 3,049 combined products across twenty-two fields matched the independent original-source reference. The selected-product and accepted SQL30 trajectory/vector fingerprints were reproduced. Every selected daily record matched its original CSV cell: 840 rows across six fields, with 84 dates per store and 42 dates in each half. Store/state mappings and all twelve weekly totals matched. All eleven result rows across eleven fields, including column names/order and TOTAL placement, matched the independent reference. Twenty targeted cases passed.

| Aggregate result | Value |
| --- | ---: |
| Stores retained | 10 |
| First / last six-week units | 62 / 2,668 |
| Signed unit difference | +2,606 |
| Total 84-day units | 2,730 |
| Stores with increased / decreased / unchanged units | 10 / 0 / 0 |
| Stores with zero units in the first / last half | 6 / 0 |
| Range of store unit differences | +160 to +541 |
| Largest store share of last-half units | 20.2774% |
| Three largest stores' last-half units / share | 1,218 / 45.6522% |
| Sum of displayed store shares / TOTAL share | 99.9999% / 100.0000% |

All ten stores recorded higher units in the latter half, so the pooled difference spans the store set. This is an observed cross-store pattern, not evidence of a common cause. The three largest stores are ranked by last-half recorded units, not increment or profitability. The 99.9999% sum follows separate four-place rounding; TOTAL uses unrounded totals and is not adjusted to absorb rounding residuals. Do not add TOTAL to the ten-store amounts.

Six valid fixtures test real zero stores with negative differences and reversed source order, an entirely zero last-window denominator, half-up shares and separately computed TOTAL, two valid empty-cohort cases, and the presence of unused price/value columns. Fourteen rejection cases test invalid empty mappings, missing zero days, duplicate/missing zero days preserving counts and units, invalid day/date/week keys, orphan stores, conflicting or missing/duplicate mappings, NULL/negative units, and the required INTEGER units contract.

Before/after hashes match for the five complete analysis snapshots, the selected 840-row daily projection, the ten-row core mapping and ten-row distinct raw mapping. Both CSV hashes and all 29 historical preflight records remained unchanged; private databases were removed. These checks are scoped to those snapshots/projections and do not re-audit the full-history daily table. DuckDB v1.5.5 used two threads and a 2GB memory limit. SQL31 took 0.501 seconds in this private CLI run, excluding Python comparisons and hashing; this is not a performance guarantee. Public evidence contains aggregate controls and matching report fingerprints only.

## Interpretation limits

Compare observed units over equal lengths, and distinguish a broad store pattern from concentration in a few stores. These are historical recorded-sales differences for one selected product. They do not establish changes in unconstrained demand, inventory availability, launch timing, promotion effects or store performance. State labels support grouping but are not causal explanations. Operating recommendations still need stock, cost, lead-time and contextual evidence.
