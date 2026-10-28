# Weekly trajectory of the volume-leading A × Z product

29 October 2026. SQL29's complete fifteen-product drilldown is accepted from the learner screenshot, with canonical detail and ordered membership fingerprints matching independent preflight. [SQL30](../sql/30_az_leading_product_weekly.sql) now examines one deterministically selected case. Assistant preflight passed; learner execution remains pending.

## Purpose and selection

Restore temporal order to the variability summary: inspect which weeks carry recorded units and where zero-sales weeks occur. Select the first accepted A × Z product by units_90d DESC, item_id ASC. No actual product identifier is hardcoded. This selects the highest 90-day recorded-unit product within that cell; it does not select the greatest CV, establish a representative sample or optimize an intervention.

Keep the accepted ABC selection window 2016-01-26..2016-04-24 (90 days) and XYZ trajectory window 2016-01-30..2016-04-22 (84 days). The twelve complete Saturday–Friday weeks are 11601–11612 internally. Pool all ten stores, preserve zero weeks, sort by week_start then wm_yr_wk, and do not append TOTAL.

## Ten-column output contract

| Column | Definition |
| --- | --- |
| item_id | One selected product, repeated for every week; local output only |
| week_start | DATE beginning the complete retail week |
| week_end | DATE ending that week |
| units | Recorded units across all ten stores in that week |
| unit_share_84d_pct | Weekly units / selected product's accepted 84-day units × 100 |
| cumulative_unit_share_84d_pct | Chronological cumulative integer units / same product's 84-day units × 100 |
| zero_sales_week | BOOLEAN indicating units = 0 |
| abc_window | 2016-01-26..2016-04-24 |
| xyz_window | 2016-01-30..2016-04-22 |
| check_status | PASS after validation, or EMPTY for a valid empty source cohort |

Both shares use this product's 84-day unit denominator, not all-product units or its own 90-day units. Calculate cumulative integer units with an explicit ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW window before calculating and rounding shares to four decimal places. Do not accumulate rounded weekly shares. Displayed weekly percentages need not sum to precisely 100%; the last cumulative value must be 100% for a valid selected product. A Z product has positive 84-day units.

## Integrity and empty-cohort behavior

Reuse SQL29's validation prefix unchanged: source weekly completeness, metric and classification checks, schema and product-key controls, ABC ranks, both date windows, exact copied combined fields and full A × Z membership controls. Select independently from combined_actual and combined_expected and reconcile the selected twenty-two-field record in both directions.

Join the selected product to the accepted weekly observations. Require twelve distinct weeks, exact first/last boundaries, the expected zero-week count, positive total units matching the selected 84-day metric, and matching final cumulative units. Source guards cover all products and prevent missing, duplicate or invalid weekly observations from being silently accepted.

Start the result from a singleton health row and left join the selected observations. A valid empty A × Z cohort produces one EMPTY row with the seven product/week fields NULL and both windows retained. Invalid empty inputs raise an error. The learner's query is read-only and does not scan raw CSVs or the large daily fact table; source-to-fact equality relies on the accepted earlier stages.

## Independent verification and evidence

The [runner](../validation/preflight_az_leading_product_weekly.py) and [aggregate evidence](../data/az_leading_product_weekly_preflight.json) retain the independent preflight. Read registered sales/calendar CSVs into a private temporary database and execute prerequisites. Independent original-wide daily arrays define the 90-day totals, twelve weekly vectors, exact ABC crossing-prefix and XYZ labels. Reconstruct the accepted SQL29 detail fingerprint before selecting its first product; compare every actual SQL30 row and all ten fields, chronological order, weekly and cumulative shares, dates and NULL/boolean handling.

Keep screenshot evidence separate from assistant preflight: [SQL29 acceptance](../data/az_product_drilldown_learner_acceptance.json) establishes the learner's displayed result; the new runner independently checks source-derived trajectories. Preserve all five accepted input tables, source hashes and historical preflight records. The learner's persistent database is never opened.

Publish only aggregate controls, test outcomes and SHA-256 fingerprints of selection and ordered trajectories. Never publish real identifiers, twelve-week product rows, raw CSVs or screenshots. The displayed trajectory remains local.

## Preflight results

All 3,049 combined products across twenty-two fields matched independent source-derived references. Reconstructed SQL29 detail and membership fingerprints matched the learner acceptance exactly. The selected product and all twelve SQL30 rows across ten fields matched, including column names/order, dates, time order, booleans, integer units and both percentage columns. All eighteen targeted cases passed.

| Aggregate control | Observed value |
| --- | ---: |
| Selected product's 90-day units | 2,897 |
| Selected product's 84-day units / twelve-week sum | 2,730 |
| Units in the excluded six days | 167 |
| Positive / zero-sales weeks | 11 / 1 |
| Minimum / maximum weekly units | 0 / 552 |
| Mean weekly units | 227.5 |
| Maximum single-week share | 20.2198% |
| Highest three weeks combined | 1,580 units / 57.8755% |
| First six complete weeks combined | 62 units / 2.2711% |
| Last six complete weeks combined | 2,668 units / 97.7289% |
| Sum of displayed weekly shares | 100.0002% |
| Final cumulative share | 100.0000% |

The highest three weeks are ranked by units and need not be consecutive. Half-window figures describe chronological first/last six complete weeks, not the two ABC/XYZ windows. This series concentrates recorded units in the latter half; this observation alone does not identify a cause. The 100.0002% display sum is an expected consequence of individually rounding twelve percentages; no observation is adjusted to force the rounded sum to 100%. Cumulative shares use integer cumulative units and remain monotone, ending at exactly 100.0000%.

Seven valid fixtures cover reversed source order with zeros retained, selection by the defined 90-day ranking, tied selection with the item key as tiebreaker, four-place half-up rounding and integer cumulative sums, valid empty cohorts with positive and all-zero source universes, and exact Z labels near the display boundary. Eleven rejection cases cover invalid empty inputs, empty/duplicate combined snapshots, label or copied-float drift, wrong weekly schema, missing weeks, a duplicate/missing pair preserving total row count, incorrect dates and incorrect source ABC ranks or XYZ labels.

All five input tables, both original source hashes and 28 historical preflight records remained unchanged. Private temporary databases were removed. DuckDB v1.5.5 ran with two threads and a 2GB memory limit. SQL30 took 0.419 seconds in this CLI run, excluding Python comparison and hashing; this is not a performance guarantee. The public JSON records matching independent selection/trajectory fingerprints and aggregate evidence only.

## Interpretation limits

Describe when recorded sales concentrate and where zeros occur. CV alone has no time order: a permutation of weekly values preserves it. A trajectory adds temporal information but cannot independently establish stockouts, launch timing, promotions, seasonality or a cause. One case does not generalize to the entire cell. Pooling stores can hide store-specific patterns, and observed units do not measure unconstrained demand. Inventory, lead time, cost and further contextual evidence remain necessary for operating decisions.
