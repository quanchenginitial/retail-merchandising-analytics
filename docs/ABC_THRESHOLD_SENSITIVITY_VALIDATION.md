# ABC threshold sensitivity: method and accepted results

28 October 2026. The learner's DBeaver screenshot confirms all five SQL22 scenario rows have `check_status=PASS` and numerically match the independent assistant preflight. Execution and displayed threshold-sensitivity results are accepted. The comparison uses the accepted [SQL21 80/95 baseline](PRODUCT_ABC_UNITS_VALIDATION.md) without changing its saved labels. The [learner acceptance record](../data/abc_threshold_sensitivity_learner_acceptance.json) transcribes the screenshot separately from assistant preflight evidence; no direct read of the learner database was performed.

## Purpose and fixed design

Assess how much of the product classification changes when one cumulative unit boundary moves. All scenarios use the same 2016-01-26–2016-04-24 inclusive window, all 10 stores, all categories, and all 3,049 products. Positive products retain the units-descending, item_id-ascending ranking; crossing products remain in the earlier class. Zero-sales products remain separate.

The five scenarios were fixed before observing their results:

| Scenario | A cumulative target | A+B cumulative target | Permitted migration relative to BASE_80_95 |
| --- | ---: | ---: | --- |
| BASE_80_95 | 80% | 95% | None |
| A75_95 | 75% | 95% | A to B |
| A85_95 | 85% | 95% | B to A |
| AB80_92 | 80% | 92% | B to C |
| AB80_98 | 80% | 98% | C to B |

Only one boundary changes in each alternative. These illustrative thresholds are not optimized operating policies. Each scenario partitions the same universe, so counts and units are conserved. Scenario rows are alternatives and must not be summed together. The deterministic identifier tie-break may separate equally selling products; it does not establish a difference in their economic value.

## Query contract and interpretation

[SQL22](../sql/22_abc_threshold_sensitivity.sql) is one read-only query over the accepted nine-column ABC snapshot and the small product dimension. It returns five rows and nine columns: scenario, a_skus, b_skus, c_skus, zero_skus, changed_skus, changed_sku_pct, changed_unit_share_pct, check_status.

`changed_skus` counts products whose alternative label differs from their accepted baseline. `changed_sku_pct` divides that count by all 3,049 products, including zero-sales products. `changed_unit_share_pct` divides the historical units attached to those relabelled products by all 3,767,196 window units. It is not a sales increase/decrease, forecast error or causal effect of a policy. Percentages are rounded only for display; membership uses exact integer comparisons.

The query checks exact column names/types/order, row and unique-product counts, nonnegative non-NULL units, window dates, and matching hierarchy against the product dimension. It recomputes positive ranks, cumulative units and original 80/95 labels and compares them with the saved baseline. Each scenario must preserve total products/units and zero-sales products; changes must follow only the permitted direction, and the baseline must have no changes. Failure raises an error rather than returning a misleading PASS.

A scenario may legitimately have no changes. Empty A/B/C groups have zero counts. For all-zero synthetic inputs, changed_sku_pct is zero and changed_unit_share_pct is NULL because the volume denominator is zero; the quality checks can still pass.

This is an internal consistency check of an already accepted snapshot, not a new scan of the learner's daily fact or original files. Source equality relies on the preceding SQL21 acceptance. If inputs are intentionally changed, revalidate that baseline against its current fact before interpreting sensitivity. SQL22 never updates saved labels.

## Independent source preflight

The [runner](../validation/preflight_abc_threshold_sensitivity.py) uses its own temporary database under ignored tmp with two threads and a 2GB DuckDB memory limit. It does not open the learner database. It verifies registered hashes for the original sales and calendar CSVs before and after the run. Prices are irrelevant to this units-only comparison and are not read or rehashed in this step.

The preflight projects the original wide sales data to the 90 selected day columns and creates a private window-only daily fixture of 2,744,100 rows, plus source product/store dimensions. It executes the actual SQL21 build and validation on that fixture. This is deliberately a window-only validation setup, not a rebuild of all 59,181,090 historical daily rows or the nine-column price-bearing production fact.

A separate source reference sums the original wide row values, aggregates products, and uses a Python minimal-prefix endpoint algorithm to assign class intervals. It does not derive its reference labels from SQL22. The runner compares all nine stored baseline fields for all 3,049 products and checks the five baseline summary rows against the learner-accepted record. It then compares all 15,245 scenario/product assignments and the five scenario summaries with independent Python results. It verifies that the baseline rows are identical before and after SQL22. Only aggregate results are published; no product-level extract is committed.

All 26 targeted cases passed. Valid cases cover exact 75/80/85/92/95/98 boundaries, crossing products, equal-unit ties, a dominant product with no scenario changes, all-zero units, one positive product and no zero-sales products. Rejection cases cover empty/duplicate/missing items, NULL/negative units, wrong dates/ranks/cumulative values/labels/zero-sales NULLs, incorrect hierarchy, missing/duplicate dimension keys, altered schema, blank item IDs, same-total redistribution and a NULL scenario threshold. Each case also verifies that executing the query leaves the baseline unchanged.

The source preflight found zero mismatches across 3,049 baseline rows (all nine fields), 15,245 scenario/product assignments and all five summary rows. SQL21 summaries matched the learner acceptance record, and the baseline remained unchanged. Preparing the private window data took 6.131 seconds; SQL22's summary query took 0.147 seconds in the assistant environment. Both source hashes were unchanged and the temporary database was removed. These timings are not performance promises for the learner environment.

## Accepted learner results and independent preflight

The learner screenshot reproduces the five rows below, including all PASS statuses. The acceptance record omits thousands separators and pads percentages to four decimal places without changing their displayed numeric values. The source comparisons, targeted cases and timings above remain evidence from the assistant's independent preflight; the screenshot does not independently establish those checks.

| Scenario | A SKUs | B SKUs | C SKUs | Zero SKUs | Changed SKUs | Changed SKU % | Changed historical unit share % | Status |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| BASE_80_95 | 1135 | 968 | 942 | 4 | 0 | 0.0000 | 0.0000 | PASS |
| A75_95 | 941 | 1162 | 942 | 4 | 194 | 6.3627 | 4.9878 | PASS |
| A85_95 | 1375 | 728 | 942 | 4 | 240 | 7.8714 | 5.0062 | PASS |
| AB80_92 | 1135 | 695 | 1215 | 4 | 273 | 8.9538 | 2.9960 | PASS |
| AB80_98 | 1135 | 1360 | 550 | 4 | 392 | 12.8567 | 2.9961 | PASS |

## Business reading of the accepted comparison

The following interpretation is supplied by the assistant. Reducing the A boundary from 80% to 75% moves 194 products from A to B: 6.3627% of all source products, carrying 4.9878% of the window's historical units. Increasing it to 85% moves 240 products from B to A: 7.8714% of products, carrying 5.0062% of historical units. The different product counts reflect how the existing unit-ranked products sit around the two boundaries; the underlying sales observations have not changed.

Reducing the A+B boundary from 95% to 92% moves 273 products from B to C, while increasing it to 98% moves 392 products from C to B. These products account for 8.9538% and 12.8567% of all SKUs, respectively, and carry 2.9960% and 2.9961% of historical units. The four zero-sales products remain separate in every scenario. The baseline has zero label changes, as required for the comparison control.

The A-boundary alternatives move that target by five percentage points, whereas the A+B alternatives move it by three percentage points. Their change counts therefore do not directly establish which boundary is more sensitive under an equal-sized adjustment. These results describe dependence on the specified thresholds; they establish neither optimal thresholds nor a causal sales effect or stability across time. They do not determine inventory, service or assortment-removal policies.

The next preparation step is a product-level weekly-sales series pooled across all stores over 12 complete retail weeks. That step prepares comparable weekly observations for later variability analysis; it does not yet assign XYZ labels.

See the [learner acceptance record](../data/abc_threshold_sensitivity_learner_acceptance.json), [machine-readable preflight](../data/abc_threshold_sensitivity_preflight.json) and [current learner instructions](FIRST_STEP_ZH.md).
