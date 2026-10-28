# Complete retail-week product sales: construction and validation

28 October 2026. The learner's DBeaver screenshot confirms all 13 SQL23 report rows have `check_status=PASS` and numerically match the assistant's independent preflight. The weekly table and displayed validation results are accepted. The [learner acceptance record](../data/product_weekly_learner_acceptance.json) transcribes the screenshot; no direct read of the learner database was performed. Following the accepted [ABC threshold sensitivity](ABC_THRESHOLD_SENSITIVITY_VALIDATION.md), this step prepares weekly observations for later variability analysis. It does not calculate CV or assign XYZ classes.

## Purpose, grain and observation window

Use equal observation durations before measuring variability. The source calendar's retail weeks run Saturday to Friday. Group the complete calendar by `wm_yr_wk` first, then select weeks wholly within the accepted ABC window of 2016-01-26–2016-04-24. Validate seven distinct consecutive dates and day keys per week, rather than treating clipped fragments as complete weeks.

The selected weeks are **11601–11612, 2016-01-30–2016-04-22**, a continuous 84-day interval. The first four ABC days (January 26–29) and final two (April 23–24) belong to partial weeks within the ABC window and are excluded from this weekly-series scope. No final-holdout dates are used to complete the last week. This choice was fixed from calendar coverage before examining variability outcomes.

The original 90-day ABC snapshot stays unchanged. Future ABC/XYZ combinations must display both windows. A product positive in 90 days can be zero over the 84-day subset; these are compatible observations. Zero units do not establish stockout or delisting. Pooling stores can smooth store-specific volatility; 12 weekly observations describe only this short global-product window, not long-run seasonality, unconstrained demand or forecast accuracy.

## Stored table and report

`mart.m5_product_weekly_12w` has one row per source item and selected retail week, with all 10 stores pooled. It contains **3,049 × 12 = 36,588 rows** and eight columns:

| Column | Type | Meaning |
| --- | --- | --- |
| item_id | VARCHAR | Source product key |
| dept_id | VARCHAR | Source department code |
| cat_id | VARCHAR | Source category code |
| wm_yr_wk | INTEGER | Source retail-week key |
| week_start | DATE | Saturday at the start of the complete week |
| week_end | DATE | Friday at the end of the complete week |
| units | HUGEINT | Sum of recorded daily units over all stores in the week |
| source_daily_rows | BIGINT | Number of contributing item/store/day rows; must equal 70 |

All observed zero-unit weeks are retained. Missing records are rejected, not imputed as zero. Keys are validated without declaring a physical PRIMARY KEY. This is a saved observation-window snapshot, not an automatic refresh.

The final report has 12 weekly rows plus TOTAL and eight columns. `product_week_rows` counts item/week records (3,049 per week, 36,588 in TOTAL), not unique products in TOTAL. `source_daily_rows` sums contributing daily rows (213,430 per week, 2,561,160 in TOTAL); its aggregate type is HUGEINT. `zero_sales_product_weeks` counts zero-unit item/week observations and may count an item in several weeks. `units` in TOTAL covers only the 84 days. The other report columns are retail_week, week_start, week_end and check_status.

## Build and validation guards

[SQL23](../sql/23_build_product_weekly.sql) checks source product and store uniqueness, required identifiers and department/category mappings. The complete-calendar week catalog must yield the 12 expected weeks and 84 unique dates/day keys with correct source day labels, retail-week mapping and Saturday–Friday boundaries.

For each item/store series, the selected daily fact must contain exactly 84 rows and all 84 date positions using a date bitmap. This catches a duplicated day replacing a missing day even if counts and sums agree. Units must be nonnegative, non-NULL INTEGER values. Exact daily `d`, `date` and `wm_yr_wk` matches to the calendar are required; dimension/calendar joins must preserve row counts and units and have no unmatched rows. Each derived product/week must contain seven days from all stores, with 70 source records.

The build consumes these guards in its output and raises an error even on empty sources; CREATE TABLE does not overwrite an existing object. The final validation separately recomputes all eight expected fields from the current daily fact and dimensions, checks exact stored column names/types/order and 12 unique weeks for every product, and compares both directions with EXCEPT ALL. Duplicate/missing rows or value changes preserving aggregate totals still fail. A PASS result requires both valid sources and exact stored-row equality. If the table exists, rerun only the complete query after `-- VALIDATION:`.

## Independent preflight

The [runner](../validation/preflight_product_weekly.py) uses its own temporary database under ignored tmp and never opens the learner database. It reads only the original sales and calendar CSVs, checking registered hashes before and after. Prices are not part of this units-only step.

A private daily fixture is built from the same 90-day source projection and the full calendar. The actual SQL21 establishes a private copy of the accepted ABC baseline, and actual SQL23 builds and validates the weekly table. This is a window-only fixture, not a full rebuild of the historical price-bearing fact.

The independent reference sums the seven original wide day columns belonging to each week, then aggregates over stores. It compares all 36,588 stored product/week rows and all eight fields, plus the 13 report rows. For every product it also checks the bridge **90-day units = 84-day units + excluded-six-day units**, and checks the 90-day ABC result against the learner-accepted baseline. The private ABC rows must remain identical before and after SQL23. No product-level extract is published.

All 20 targeted cases passed. Valid cases retain observed zero weeks, a product sold only on excluded boundary dates, all-zero data, and exclusion of adjacent/holdout dates. Build rejections cover empty source, a missing day replaced by a duplicate while counts stay unchanged, missing stores, wrong fact week/day mappings, duplicate calendar dates, nonconsecutive seven-date weeks, a clipped partial calendar week, negative units and duplicate product mappings. Each rejected build leaves no target table. Validation rejects altered stored week boundaries/counts/hierarchy, same-week total-preserving redistribution between products, duplicate/missing product-week rows and wrong units type.

All 36,588 product/week rows matched the independent wide-column reference across all eight fields; the 13 summary rows passed. Every product's 12-week key set and 90/84/six-day bridge matched. The private ABC baseline remained unchanged and matched the accepted 90-day result. Both original file hashes were unchanged, and private databases/spills were removed.

The preflight used two threads and a 2GB memory limit. Preparing its 90-day fixture took 7.997 seconds; SQL23 build and validation took 1.159 and 1.192 seconds. These are assistant DuckDB CLI execution timings, exclude Python comparisons/file hashing, and are not promises for the learner environment.

## Accepted learner results and independent preflight

The learner screenshot reproduces the 12 weekly rows and TOTAL below, including all PASS statuses. Thousands separators are omitted in the acceptance record, dates use YYYY-MM-DD, and integer counts retain their numeric values. The source-level row comparisons, targeted cases and timings above are separate assistant preflight evidence; the screenshot does not independently establish those checks.

| Retail week | Start | End | Product/week rows | Source daily rows | Units | Zero-unit product/weeks | Status |
| --- | --- | --- | ---: | ---: | ---: | ---: | --- |
| 11601 | 2016-01-30 | 2016-02-05 | 3049 | 213430 | 291534 | 92 | PASS |
| 11602 | 2016-02-06 | 2016-02-12 | 3049 | 213430 | 305409 | 102 | PASS |
| 11603 | 2016-02-13 | 2016-02-19 | 3049 | 213430 | 299279 | 105 | PASS |
| 11604 | 2016-02-20 | 2016-02-26 | 3049 | 213430 | 280579 | 96 | PASS |
| 11605 | 2016-02-27 | 2016-03-04 | 3049 | 213430 | 291839 | 104 | PASS |
| 11606 | 2016-03-05 | 2016-03-11 | 3049 | 213430 | 304015 | 100 | PASS |
| 11607 | 2016-03-12 | 2016-03-18 | 3049 | 213430 | 297551 | 84 | PASS |
| 11608 | 2016-03-19 | 2016-03-25 | 3049 | 213430 | 281241 | 94 | PASS |
| 11609 | 2016-03-26 | 2016-04-01 | 3049 | 213430 | 282697 | 73 | PASS |
| 11610 | 2016-04-02 | 2016-04-08 | 3049 | 213430 | 309668 | 69 | PASS |
| 11611 | 2016-04-09 | 2016-04-15 | 3049 | 213430 | 306203 | 72 | PASS |
| 11612 | 2016-04-16 | 2016-04-22 | 3049 | 213430 | 286524 | 65 | PASS |
| TOTAL | 2016-01-30 | 2016-04-22 | 36588 | 2561160 | 3536539 | 1056 | PASS |

The accepted TOTAL contains 36,588 product/week records, 2,561,160 contributing daily records, 3,536,539 units and 1,056 zero-unit product/week observations. The last count is not a count of distinct products: one product can contribute a zero observation in several weeks.

Separately, the assistant's independent original-CSV preflight established the window bridge **3,767,196 units over 90 days = 3,536,539 over 84 days + 230,657 on the six excluded days**. It also checked this identity for every source product with no differences. The screenshot displays the 84-day total, not the excluded-day total or the per-product bridge.

The assistant preflight additionally counted seven distinct products with zero units throughout the 84-day window, compared with four throughout the 90-day ABC window; the additional three sold only on the excluded dates. The seven-product count is not displayed in the learner screenshot and is not claimed as screenshot evidence. It differs from the displayed 1,056 zero-unit product/week observations. These findings neither change the stored 90-day ABC labels nor establish unavailable inventory.

The next step prepares per-product mean weekly units, population standard deviation, CV and zero-sales-week share from the 12 equal-length observations. Those variability metrics and XYZ labels are not completed by SQL23. No forecasting, inventory or causal performance result is claimed.

See the [learner acceptance record](../data/product_weekly_learner_acceptance.json), [machine-readable preflight](../data/product_weekly_preflight.json) and [current learner instructions](FIRST_STEP_ZH.md).
