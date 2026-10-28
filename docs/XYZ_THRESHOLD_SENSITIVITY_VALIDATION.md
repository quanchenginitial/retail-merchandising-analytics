# XYZ threshold sensitivity: fixed-window, read-only scenarios

28 October 2026. The learner's SQL25 screenshot has accepted all five baseline report rows. This step evaluates whether classification conclusions depend heavily on chosen CV cutoffs; it does not replace the baseline or estimate an intervention effect. See [baseline acceptance](PRODUCT_XYZ_VALIDATION.md) and [SQL26](../sql/26_xyz_threshold_sensitivity.sql).

## Frozen data and scenarios

Keep all 3,049 products, all ten stores pooled, and the 12 complete retail weeks from 2016-01-30 through 2016-04-22. Keep zero weeks, population rather than sample variance, and ZERO_SALES for products with total zero. No time or store scope changes, products removed, forecasting holdout observations used, or baseline records updated.

The five scenarios were declared before examining their results. Each alternative changes only one boundary by 0.1 in dimensionless CV units.

| Scenario | Inclusive X upper CV | Inclusive Y upper CV | Possible transition from baseline |
| --- | ---: | ---: | --- |
| BASE_050_100 | 0.5 | 1.0 | None |
| X040_Y100 | 0.4 | 1.0 | X to Y |
| X060_Y100 | 0.6 | 1.0 | Y to X |
| X050_Y090 | 0.5 | 0.9 | Y to Z |
| X050_Y110 | 0.5 | 1.1 | Z to Y |

A product with positive units is X at or below the first bound, Y above the first and at or below the second, otherwise Z. ZERO_SALES stays separate in every scenario. Both boundaries move by the same absolute 0.1, but this is 20% of the X baseline bound and 10% of the Y baseline bound. Counts describe local responses to these chosen adjustments; they do not establish sensitivity to equal relative changes or identify optimal thresholds.

## Exact arithmetic and input checks

SQL26 is one read-only query. It reads the accepted weekly, variability and XYZ tables plus core product mapping. It reuses SQL25's guards: weekly schema/keys/complete dates/70 contributing daily rows per product-week, product uniqueness/mapping, all 14 source metrics reconciled to recomputation, and all 15 baseline fields matched to the copied metric snapshot plus exact label. Source-to-daily provenance relies on accepted SQL23; this query does not scan the learner's large daily fact.

For twelve integer weekly observations, N=12*sum(x²)-sum(x)² and D=sum(x)². For positive totals, represent a threshold as k/10 and compare `100*N <= k*k*D`. First check X, then Y. Inclusive threshold membership is exact, unaffected by rounded display or DOUBLE tolerance. Weekly units are bounded before squaring at 7*expected_stores*2147483647; products have twelve weekly records, so these scenario multiplications safely fit HUGEINT. Zero-total products bypass division and are ZERO_SALES.

The accepted baseline is recomputed at 0.5/1.0 and compared before scenarios. Scenario thresholds must be non-NULL, positive and ordered. Every scenario must preserve the product set, total units and zero-sales count. A changed label must follow the one permitted direction; the baseline must change no labels. A failed guard raises an error. No scenario table is created, and the original XYZ table remains the accepted baseline.

## Report contract

Five rows and nine columns: scenario, x_skus, y_skus, z_skus, zero_skus, changed_skus, changed_sku_pct, changed_unit_share_pct, check_status.

- Group counts partition all 3,049 source products in every row.
- changed_skus counts products whose scenario label differs from their accepted baseline label.
- changed_sku_pct = changed_skus / all 3,049 products, including the seven zero-sales products, times 100.
- changed_unit_share_pct = historical 84-day units of the changed products / all 3,536,539 window units, times 100. It is not an increase/decrease in sales, a financial return, or an effect caused by reclassification.
- Shares display four decimal places. A zero unit denominator gives NULL, including the all-zero baseline fixture. Products with zero units still count in the SKU denominator and never change class.

## Independent preflight and current results

The assistant preflight passed; learner execution of SQL26 remains pending. These are the independently checked five report rows:

| 场景 | X 商品 | Y 商品 | Z 商品 | 全零商品 | 换组商品 | 换组商品占比 % | 涉及历史销量占比 % | 状态 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| BASE_050_100 | 2745 | 167 | 130 | 7 | 0 | 0.0000 | 0.0000 | PASS |
| X040_Y100 | 2581 | 331 | 130 | 7 | 164 | 5.3788 | 2.6335 | PASS |
| X060_Y100 | 2811 | 101 | 130 | 7 | 66 | 2.1646 | 1.3061 | PASS |
| X050_Y090 | 2745 | 152 | 145 | 7 | 15 | 0.4920 | 0.2411 | PASS |
| X050_Y110 | 2745 | 191 | 106 | 7 | 24 | 0.7871 | 0.5665 | PASS |

Lowering the X bound from 0.5 to 0.4 moves 164 products from X to Y, representing 5.3788% of products and 2.6335% of historical units. The four alternatives affect 0.2411%–2.6335% of window units individually. This describes the selected local adjustments; none changes recorded units or demonstrates improved forecasts. Do not add scenario effects as if they represented a single boundary change.

The [runner](../validation/preflight_xyz_threshold_sensitivity.py) reads only registered sales and calendar CSVs, verifies their hashes before and after, and builds a private 84-day fixture before executing the actual SQL23, SQL24 and SQL25. It then executes the unchanged read-only SQL26. Independently aggregate each original seven-column wide block to a weekly vector. Python Fraction computes centered population variance divided by mean squared exactly, rather than SQL's raw-moment expression, and compares rational squared thresholds. Reused 70-digit Decimal metric references verify the baseline's fifteen fields. Confirm all 36,588 weekly source rows/eight fields, the 3,049-product baseline/fifteen fields, all **15,245 product/scenario memberships**, and all five report rows. The baseline summary also matches learner SQL25 acceptance.

All **21 targeted cases** passed. A 20-product fixture contains CV exactly at each of 0.4, 0.5, 0.6, 0.9, 1.0 and 1.1, plus integer perturbations immediately below/above each boundary, one all-zero and one constant-positive vector. Other cases cover all-zero denominators, empty positive groups, supported arithmetic bounds, tolerated DOUBLE CV drift, missing/duplicate/invalid weekly keys, unsafe square inputs, changed or NaN metrics, duplicate mappings, missing/duplicate baseline products, swapped labels that preserve class counts and class units, copied-float drift, wrong dates/schema, misclassified zeros and a NULL scenario boundary. NULL thresholds are explicitly rejected rather than passing a nullable Boolean range expression.

Before/after row fingerprints match for the weekly, metric and XYZ input tables. No learner database or ABC table was opened. Temporary databases were removed, original sources remain unchanged, and only aggregate evidence is published. DuckDB v1.5.5 used two threads and a 2GB memory limit. SQL26's report query took 0.352 seconds in the private run; the separate membership query took 0.217 seconds. These CLI process timings exclude Python reference work and file hashing, and are not a performance guarantee. Full hashes, exact fixture names and comparison evidence are in [the preflight record](../data/xyz_threshold_sensitivity_preflight.json).

## Interpretation and next step

A changed count tells us how many products depend on that particular cutoff. Their historical unit share adds a volume perspective; it does not reflect profit or inventory risk. Unchanged labels within these five scenarios do not prove robustness to larger adjustments, alternative windows, seasonal changes or individual stores. Low CV is not validated forecast accuracy, and zero units do not prove stockout.

After learner acceptance, retain the declared 0.5/1.0 baseline for the next ABC × XYZ analysis rather than silently choosing the most convenient sensitivity outcome. Combined output must disclose ABC's 90-day window (2016-01-26–2016-04-24) and XYZ's 84-day window (2016-01-30–2016-04-22). Decisions about replenishment or inventory need additional data and validation.
