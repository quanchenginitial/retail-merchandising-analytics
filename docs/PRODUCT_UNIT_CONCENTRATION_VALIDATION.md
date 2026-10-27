# Product-unit concentration: ranking and threshold validation

28 October 2026. The learner's DBeaver screenshot confirms all eight output rows from [20_product_unit_concentration.sql](../sql/20_product_unit_concentration.sql) have `check_status=PASS` and numerically match the independent assistant preflight. The ranking and cumulative-contribution result is accepted. This read-only step prepares the evidence for later ABC classification; no ABC labels are produced here. The [learner acceptance record](../data/product_unit_concentration_learner_acceptance.json) transcribes the screenshot and is separate from the assistant's private-database checks; no direct read of the learner database was performed.

## Question and fixed scope

How concentrated are recorded units across products, and how many products are required to reach 80% or 95% of the window's units? Use **2016-01-26–2016-04-24 inclusive**, all 10 stores and the same 3,049 source products. Aggregate each item across stores before ranking; a SKU present in several stores remains one product. Retain products with zero recorded units in the product universe.

The prior accepted department totals provide 3,767,196 units and 3,049 products as controls. This query ranks **units**, not estimated value, margin or profit. Cross-category pieces do not represent equal volume, utility or economic value. Concentration does not establish availability, service importance, latent demand or an assortment removal decision. The analysis does not assume that 20% of products actually contribute 80% of units.

## Ranking and overlapping observations

Sort positive-unit SKUs by units descending and item_id ascending. Compute cumulative units with an explicit ROWS frame. Equal-unit products may be split by a target boundary; the identifier tie-break makes the outcome reproducible, not economically different.

| Segment | Definition |
| --- | --- |
| TOP_10 / TOP_50 / TOP_100 | First min(N, positive SKU count) products in that ranking |
| REACH_80_PCT / REACH_95_PCT | Smallest positive-SKU prefix meeting or exceeding the stated percentage of all units |
| ALL_POSITIVE | All products with strictly positive window units |
| ZERO_SALES | All products with zero window units |
| ALL_PRODUCTS | The entire observed source product universe |

These rows overlap and must not be added. Only ALL_POSITIVE plus ZERO_SALES partitions the entire universe. SKU-share denominators always include all source SKUs; unit-share denominators are the window's total units. Percentages are rounded to four places for display.

Threshold membership uses exact HUGEINT comparisons: cumulative_units × 100 >= total_units × 80 or 95. Include the last SKU that first reaches/crosses the target, so the actual share may exceed 80%/95%. Both targets can be reached by the same SKU. Do not select members from rounded percentages. If total units are zero, both REACH rows have NULL count/units/shares and N/A status; other unit shares are also NULL because their denominator is zero. Valid data checks can still pass in that scenario.

## Query checks and accepted dependencies

The selected item/store series must each contain exactly 90 rows with all 90 dates, using a bounded bitmap to detect duplicate/missing date substitutions. Required identifiers, canonical day/date mapping and nonnegative INTEGER units are checked. Product/store key uniqueness, known department/category pairs, full membership and unchanged row/unit totals prevent silent join loss or duplication. Product totals must preserve the series totals. Invalid data stop the report with an error; PASS refers to these checks, not business performance.

This is intentionally a units-only query. It does not require price availability, recalculate monetary values or re-audit every previously accepted raw-to-fact value. It relies on prior source/fact acceptance. After upstream edits, rerun the relevant acceptance scripts. The independent source test below verifies the actual baseline used to prepare this script.

## Independent evidence

The [runner](../validation/preflight_product_unit_concentration.py) rebuilds prerequisites in a private temporary on-disk database under ignored tmp, with two threads and a 2GB DuckDB memory limit. It never opens the learner database. Input hashes must match the registry and remain unchanged; database/spills are removed after verification. Closed-file size is not a peak-resource measurement.

The independent reference aggregates staging sales through staging calendar and the product hierarchy projected from raw sales. It compares **every SKU's identity, hierarchy and unit total** to the production query's product totals, not merely overall sums. It then independently sorts in Python and checks every positive SKU's identifier, rank and cumulative units. Python also reconstructs all eight segments and their Decimal display percentages. Source SKU totals must roll up exactly to the learner-accepted department SKU counts and units. These checks can expose redistribution between products even when department totals are unchanged. Only summary counts and department rollups are published; no SKU-level extract is committed.

Fourteen focused cases cover exact 80%/95% boundaries, overshoot by a crossing SKU, one SKU crossing both targets, equal-unit ties and rowwise cumulative sums, different top-N prefixes, fewer than ten positive products, zero-sales products, entirely zero sales, inclusive window boundaries, duplicate/orphan products, duplicate/missing dates, negative/NULL units and missing store mappings. No repeated forecast or financial validation is implied.

## Accepted learner results and independent preflight

The learner screenshot reproduces all eight rows below, including all PASS statuses. Thousands separators are omitted and percentage values are padded to four decimal places in the machine-readable acceptance record; this normalization preserves the displayed numeric values.

Separately, the assistant preflight compared all 3,049 product totals/mappings and 3,045 positive ranks/cumulative totals with the independent reference and found zero discrepancies. SKU counts and units rolled up exactly to the accepted department result. Fourteen targeted cases passed; input hashes were unchanged and the private database was removed. Report execution took 1.117 seconds after rebuilding prerequisites in the assistant's environment. These independent checks and timings are assistant evidence, not measurements established by the learner screenshot.

| Segment | SKUs | SKU share % | Units | Unit share % | Status |
| --- | ---: | ---: | ---: | ---: | --- |
| TOP_10 | 10 | 0.3280 | 247361 | 6.5662 | PASS |
| TOP_50 | 50 | 1.6399 | 667622 | 17.7220 | PASS |
| TOP_100 | 100 | 3.2798 | 984906 | 26.1443 | PASS |
| REACH_80_PCT | 1135 | 37.2253 | 3013899 | 80.0038 | PASS |
| REACH_95_PCT | 2103 | 68.9734 | 3579077 | 95.0064 | PASS |
| ALL_POSITIVE | 3045 | 99.8688 | 3767196 | 100.0000 | PASS |
| ZERO_SALES | 4 | 0.1312 | 0 | 0.0000 | PASS |
| ALL_PRODUCTS | 3049 | 100.0000 | 3767196 | 100.0000 | PASS |

## Business reading of the accepted output

The following interpretation is supplied by the assistant. The first 10 SKUs contribute 6.5662% of recorded units, the first 50 contribute 17.7220%, and the first 100 contribute 26.1443%. The top 100 are 3.2798% of the product universe, so their recorded unit contribution is disproportionately large relative to their count. This remains a comparison of pieces across heterogeneous products, not a measure of value, margin or service importance.

Reaching 80% requires 1,135 SKUs, or 37.2253% of all source products. Reaching 95% requires 2,103, or 68.9734%. The actual cumulative unit shares are 80.0038% and 95.0064% because each threshold includes its crossing SKU. This evidence does not support a literal assumption that 20% of products account for 80% of this window's units. The overlapping TOP and REACH rows describe different prefixes of the same ranking and must not be summed.

Four products have zero recorded units across all 10 stores during this 90-day window. They remain in the 3,049-product denominator. Their zero sales alone do not establish delisting, stockout, latent demand or a reason to remove them from the assortment. The 3,045 positive-sales products account for all 3,767,196 units. No ABC assignments, revenue/profit concentration, inventory decision or causal result has yet been established.

See the [learner acceptance record](../data/product_unit_concentration_learner_acceptance.json), [machine-readable preflight](../data/product_unit_concentration_preflight.json) and [current learner instructions](FIRST_STEP_ZH.md). Execution and displayed results are accepted; define mutually exclusive ABC bands and their boundary/zero-sales policy in a separate step, followed by threshold sensitivity checks.
