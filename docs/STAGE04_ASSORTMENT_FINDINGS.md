# Stage 4 checkpoint: assortment contribution and sales variability

Checkpoint date: 2026-10-29 (Australia/Sydney).

The descriptive assortment module is complete through learner acceptance of SQL32. It establishes which products contribute observed sales, how pooled weekly sales vary, and how to investigate one selected case. Forecast performance, causes of sales changes, inventory decisions, wider price analysis and Power BI remain later work. Screenshot acceptance records execution and displayed results; it is not an independent assessment of the learner's conceptual understanding.

## Scope and definitions

- M5 public historical Walmart data is a retail learning proxy, not IKEA internal data or an IKEA operating result.
- Universe: 3,049 products across 10 stores, three states, seven departments and three categories.
- Contribution and ABC window: 2016-01-26–2016-04-24, 90 days, 3,767,196 recorded units.
- Weekly variability and XYZ window: 2016-01-30–2016-04-22, 12 complete Saturday–Friday weeks, 84 days, 3,536,539 recorded units. The six excluded days contain 230,657 units. Each window retains its own denominator.
- ABC ranks pooled unit sales, not value or profit. The boundary-crossing product remains in the earlier class; zero-sales products are separate.
- XYZ uses population standard deviation divided by mean across all 12 weeks, including zero weeks. X has CV <= 0.5, Y has 0.5 < CV <= 1, and Z has CV > 1; all-zero series are separate. Exact classification precedes rounded display.
- Estimated sales value is observed units multiplied by the published weekly price. It is a sales-value proxy, not verified net revenue or margin.

## Findings and their practical use

| Accepted observation | Useful analytical implication | Limit |
| --- | --- | --- |
| FOODS contributes 66.6635% of 90-day units and 56.5109% of estimated sales value. HOUSEHOLD contributes 24.0318% of units and 30.4492% of value; HOBBIES contributes 9.3047% and 13.0399%. | Show both units and the value proxy when discussing category mix: their rankings and shares convey different information. | Neither measure identifies profit, shelf-space productivity or customer preference independent of availability. |
| Reaching 80% of units requires 1,135 products, 37.2253% of the universe; these contribute 80.0038%. A+B reaches 95.0064% with 2,103 products. | Use the observed concentration curve to size review groups. | The data do not support assuming that 20% of products produce 80% of units. |
| A × X contains 1,082 products, 35.4870% of products, and contributes 76.7842% of 90-day units. | This is the largest contribution segment and a useful monitoring group in this descriptive snapshot. | X means low pooled variation in this window, not proven forecastability or a validated replenishment policy. |
| A × Z contains 15 products and contributes 0.5475% of 90-day units. | These cases support focused investigation of why a high-contribution classification can coexist with variable weekly sales. | This small segment is not a representative sample of the full assortment and does not define the forecast evaluation population. |
| X contains 2,745 products and 95.1371% of 84-day units. The four tested XYZ threshold alternatives individually change labels for products carrying 0.2411%–2.6335% of units. | Report classification sensitivity alongside the chosen thresholds. | These are historical shares of reclassified products, not changes in sales, optimal thresholds, or evidence of stability across time. Store pooling may smooth variation. |
| Four products have zero units in 90 days; seven have zero units in the 84-day window. Three C × ZERO_SALES products have 12 units only in the six excluded days. | Keep zero-sales groups and reconcile differing windows before interpreting an apparent discrepancy. | Zero observed sales do not establish stockouts, discontinuation or lack of demand. |

Evidence: [category contribution](CATEGORY_CONTRIBUTION_VALIDATION.md), [department contribution](DEPARTMENT_CONTRIBUTION_VALIDATION.md), [concentration](PRODUCT_UNIT_CONCENTRATION_VALIDATION.md), [ABC](PRODUCT_ABC_UNITS_VALIDATION.md), [ABC sensitivity](ABC_THRESHOLD_SENSITIVITY_VALIDATION.md), [XYZ](PRODUCT_XYZ_VALIDATION.md), [XYZ sensitivity](XYZ_THRESHOLD_SENSITIVITY_VALIDATION.md), and [joint contribution](ABC_XYZ_CONTRIBUTION_VALIDATION.md).

## Selected-case investigation

The case was selected deterministically as the highest 90-day-unit product within A × Z, with an item-ID tie-break. It was not selected as a representative product or because of its price changes. Public evidence retains aggregate controls and ordered-result fingerprints; real product identifiers, store-detail rows, weekly vectors and screenshots are not redistributed.

1. The full 12-week trajectory contains 2,730 units: 62 in the first six weeks and 2,668 in the last six weeks. A high full-window CV can reflect a change in sales level, rather than repeated erratic demand around a stable level.
2. All ten stores record higher units in the later half. The increase totals 2,606 units; the largest store contributes 20.2774% of later-half units. The change is therefore not confined to one store, although its cause remains unknown.
3. All 120 store-week positions have a published weekly price. Across 110 same-store adjacent-week comparisons, there are two increases, one decrease and 107 unchanged prices. The first displayed week has no within-window comparison and retains NULL comparison fields.
4. In the learner's accepted SQL32 display, all stores have a published weekly price of USD 2.68 throughout the later six weeks. The observed later-half sales increase does not coincide with a broad reduction in this recorded weekly price. This does not rule out other discounts, promotions, changes in availability, reporting, seasonality or other drivers; none has been established here.

The last observation is read from the accepted display; its complete ordered report fingerprint was checked against the independent preflight. No weekly detail is republished. See [weekly trajectory](AZ_LEADING_PRODUCT_WEEKLY_VALIDATION.md), [store comparison](AZ_LEADING_PRODUCT_STORE_COMPARISON_VALIDATION.md), and [price context](AZ_LEADING_PRODUCT_PRICE_CONTEXT_VALIDATION.md). These checks close the descriptive case; they do not complete the planned broader price/anomaly module.

## Transition to forecasting

The next question is whether simple methods can predict the next 28 days of recorded unit sales. The next learner action is [SQL33: scope and time audit](../sql/33_forecast_scope_and_time_audit.sql), under the existing [evaluation plan](EVALUATION_PLAN.md). The learning slice is selected from product/store dimensions, independently of sales rankings, and includes all products in that department at that store, including zero-sales series.

Use three development origins and the fixed final origin. Do not carry the April ABC/XYZ labels backwards as features or scope filters at February/March forecast origins: they include observations unavailable at those origins. Recompute any such features separately from origin-available data if introduced later. Future recorded prices are excluded from the initial baselines.

The final 28 days remain reserved for forecast evaluation after method choices are frozen. Engineering reconciliation has already included full-snapshot totals, so this is not a claim of wholly unseen data. SQL33 checks training observations and forecast calendar dates; it produces neither predictions nor final-holdout outcomes or errors. Later steps will run the last-seven-day-pattern baseline and the previous-four-same-weekday baseline, then compare development errors before any final evaluation.
