# Category contribution: fixed-window method and acceptance

28 October 2026. The learner screenshot confirms all four result rows from [18_category_contribution.sql](../sql/18_category_contribution.sql) have check_status=PASS and numerically match the independent preflight results. This first business-analysis query after daily fact acceptance is accepted for the fixed window below. The [screenshot transcription](../data/category_contribution_learner_acceptance.json) records the displayed output separately from assistant preflight evidence; the assistant did not directly open the learner database.

## Question, scope and interpretation

Which categories contribute most to recorded units and estimated sales value during **2016-01-26–2016-04-24**, inclusive? This fixed 90-day window contains 2,744,100 item/store/day observations, all 3,049 source products and all 10 stores. It ends before the final 28-day forecasting holdout and aligns with the planned 90-day ABC window. Historical full-snapshot engineering controls are a different scope; do not compare this subset to the full 66,927,173 units or USD 191,577,546.04.

FOODS, HOBBIES and HOUSEHOLD are source category codes. SKU count is the distinct item count across stores, including products with zero sales; it does not establish active listing or availability. Units count source pieces, not equivalent physical volume or consumer utility across categories. Value means the accepted weekly-price-based USD proxy, not verified transaction revenue or profit. A higher value share than unit share describes product/price mix; it does not prove better margins or causal pricing power.

Both share denominators use all three categories under the same fixed date/store scope. Exact decimal values are summed before percentages are computed and rounded to four places for display. Zero denominators produce NULL; rounded category shares need not sum to exactly 100.0000. TOTAL is calculated from the pre-join source aggregates, not from already-rounded category percentages. Price-row coverage includes zero-sales days; positive-price completeness is required by the guards.

## Query checks and dependencies

Aggregate the accepted daily fact by item/store first. Each series must have 90 rows and all 90 unique dates, checked with a bounded bitmap. This detects a missing date replaced by a duplicate even when the row count is unchanged. Required values, canonical date/day mapping, positive-price validity, has_price and the zero-quantity/value convention are checked within the selected window.

Join the small accepted product/store dimensions to those aggregates, then summarize by category. Check dimension key counts and uniqueness, known category labels, complete product/store matches and unchanged row/unit/value totals. Missing mappings cannot silently disappear through an INNER JOIN. Any guard failure stops the query with an error; the output is not presented as a usable partial report. PASS means these data/aggregation checks passed, not that business performance is good.

SQL18 depends on the accepted SQL12/13/17 source mappings and values. It does not repeat their per-row raw-to-core/fact reconciliation, independently validate the fact's stored weekly prices against the price table, or detect every possible valid-looking upstream modification. Rerun the relevant upstream checks after source/fact edits. The assistant preflight below separately compares report aggregates against source-based calculations.

## Independent verification

The [runner](../validation/preflight_category_contribution.py) builds prerequisite objects in its own temporary on-disk database under ignored tmp, using two threads and a 2GB DuckDB memory limit. It never opens the learner database. All three source hashes must match the registry and remain unchanged. The temporary database and spills are removed. Recorded closed-file size is not a peak resource measurement.

An independent reference uses staging sales, staging calendar, staging prices and product/category mappings projected from raw sales. It does not use the fact's stored dates, flags or amounts. It multiplies integer units by integer price cents, sums in integer cents, and checks that no positive units lack prices. Python Decimal independently calculates the expected category shares and price coverage. All four report rows must match this reference, including category order, distinct SKU counts, unit totals, exact monetary totals, shares and coverage.

Sixteen targeted cases cover hand-calculated category totals, cross-store SKU de-duplication, missing-price zeros, inclusive boundary dates and excluded adjacent days, zero denominators, duplicate/missing mappings, invalid category/store keys, missing and duplicate dates, missing prices on positive units, invalid flags/prices/units/values and the zero-unit value policy. These cases test plausible aggregation failures rather than business outcomes.

## Accepted learner results and independent preflight

The learner's four displayed rows match the table below. Trailing zeros are normalized to two decimal places for money and four for percentages; this changes formatting only. Independently, the assistant preflight matched all four rows to its source-based reference. The preflight query took 4.349 seconds after rebuilding prerequisites; this is an environment-specific observation, not a runtime promise. All 16 targeted cases passed. Source hashes were unchanged and the private database was removed. These resource and source-hash observations belong to the assistant preflight, not the learner screenshot.

| Category | Source SKUs | Units | Unit share % | Estimated value USD | Value share % | Priced daily rows % |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| FOODS | 1437 | 2511345 | 66.6635 | 6694817.06 | 56.5109 | 99.9969 |
| HOUSEHOLD | 1047 | 905325 | 24.0318 | 3607297.50 | 30.4492 | 99.9877 |
| HOBBIES | 565 | 350526 | 9.3047 | 1544831.42 | 13.0399 | 100.0000 |
| TOTAL | 3049 | 3767196 | 100.0000 | 11846945.98 | 100.0000 | 99.9943 |

The independent preflight reference identifies 156 unpriced daily rows, all with zero units (40 FOODS, 116 HOUSEHOLD). This explains why the accepted daily-row price coverage is slightly below 100% while every positive unit is priced. The exact missing-row counts are reference evidence, not additional fields displayed in the learner result. Category monetary totals add exactly to USD 11,846,945.98.

## Business reading of the accepted output

The following is the assistant's interpretation of the accepted query results for this fixed historical window:

- FOODS contributes the most recorded units and estimated value: 66.6635% of units and 56.5109% of the value proxy. It is the largest category by these two measures within this scope.
- HOUSEHOLD contributes 24.0318% of units and 30.4492% of estimated value; HOBBIES contributes 9.3047% and 13.0399%, respectively. Their higher value shares than unit shares describe a higher estimated value per recorded unit relative to the overall mix. This is not evidence of higher margins, causal pricing power or superior business performance.
- Across all three categories, the window records 3,767,196 units and an estimated USD 11,846,945.98. These describe the specified 90 days, not full-history totals, verified transaction revenue or profit. The included SKU counts and missing-price zeros do not establish active assortment, inventory availability or stockouts.

See [learner acceptance evidence](../data/category_contribution_learner_acceptance.json), [machine-readable preflight evidence](../data/category_contribution_preflight.json) and [current learner instructions](FIRST_STEP_ZH.md). Learner execution and the displayed category results are now accepted. This query does not yet deliver ABC/XYZ classes, forecast scores, stockout diagnoses or recommendations to alter the assortment.
