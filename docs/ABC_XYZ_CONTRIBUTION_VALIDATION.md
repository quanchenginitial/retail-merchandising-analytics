# ABC × XYZ cell contribution: recorded units and product shares

29 October 2026. The learner's SQL27 screenshot has accepted all five product-count matrix rows with both observation windows. SQL28 adds descriptive recorded-unit contribution to that accepted combination. It is a single read-only query; no classifications or tables are updated. See [combined snapshot acceptance](PRODUCT_ABC_XYZ_VALIDATION.md) and [SQL28](../sql/28_abc_xyz_contribution.sql).

## Purpose and frozen membership

Compare each cell's share of products with its share of historical recorded units. Product count alone does not establish how much volume a cell contributes. Membership remains the accepted global, all-ten-store ABC × XYZ combination. ABC uses 80%/95% cumulative recorded-unit cutoffs over 2016-01-26–2016-04-24 (90 days); XYZ uses population CV cutoffs 0.5/1.0 over 2016-01-30–2016-04-22 (84 days, twelve complete weeks). Zero-sales labels remain independent for the two windows.

Both unit measures use this same fixed set of combined labels. Do not recompute ABC over 84 days or XYZ over 90 days. The windows are nested and differ in length and coverage, not consecutive periods; differences are not growth, decline, causal effects or forecasting performance. Units are not revenue, profit, inventory turns or unconstrained demand.

## Complete cells and display order

Build the Cartesian product of ABC {A,B,C,ZERO_SALES} and XYZ {X,Y,Z,ZERO_SALES}. Retain all sixteen cells, including empty cells, then append TOTAL as the seventeenth row. Sort in the fixed class order above, not by an outcome-dependent unit ranking.

Internally group on separate abc_class and xyz_class columns. Only at display time concatenate them into `segment`, such as `A × X` or `C × ZERO_SALES`, with ABC first. The separator prevents confusion between the independent zero-sales labels. TOTAL is a rollup rather than an additional product group.

## Ten-column metric contract

| Column | Definition |
| --- | --- |
| segment | Displayed ABC × XYZ combination, or TOTAL |
| sku_count | Number of unique products in the combination; keys are checked before aggregation |
| sku_share_pct | sku_count / all 3,049 products × 100; include zero-sales products |
| units_90d | Sum of the combination's recorded units in the 90-day window |
| unit_share_90d_pct | units_90d / all 3,767,196 recorded 90-day units × 100 |
| units_84d | Sum of the same combination's recorded units in the 84-day window |
| unit_share_84d_pct | units_84d / all 3,536,539 recorded 84-day units × 100 |
| abc_window | 2016-01-26..2016-04-24 |
| xyz_window | 2016-01-30..2016-04-22 |
| check_status | PASS only after source, cell, total and margin checks succeed |

Counts and units reconcile as integers before percentages are calculated. Display percentages as DECIMAL(12,4), rounded only at the final step. Rounded cell shares need not add to exactly 100%; never change a cell to absorb a rounding residual. TOTAL uses the unrounded totals. An empty cell has zero products and units. When the corresponding overall denominator is positive its share is zero; if all units in a window are zero, every unit share in that window, including TOTAL, is NULL. A positive product count with zero units is a real zero-sales group, distinct from an empty cell.

The two historical unit shares have different denominators, even though the source product set is unchanged. A cell with unit share above SKU share has above-universe average recorded units per product in that window. This is not evidence of higher prices, margin, efficient inventory or a preferred operating policy.

## Validation and provenance

Reuse SQL27's validated combined snapshot path: recheck the accepted weekly records and XYZ metrics/classes, ABC schema/ranks/cumulative values/classes, equal unique product sets and mappings, both date windows, the nonnegative six-day bridge, exact copied values across all twenty-two fields and both baseline margins. Source-to-daily equality relies on accepted SQL21/23; the learner query does not scan the large daily fact or raw CSVs.

The contribution layer checks exactly sixteen distinct class pairs. Their counts and both unit totals must reproduce the combined snapshot totals. Reconcile both counts and both window units separately by ABC row and XYZ column, with missing classes normalized to zero. Each cell must satisfy units_90d >= units_84d >= 0, and an empty cell cannot contain units. The overall 90-day minus 84-day difference must equal the saved excluded-six-day total. A failed guard raises an error rather than emitting PASS.

All source tables remain unchanged. The current output is not saved as another database table; its query, definitions and aggregate validation evidence form the reproducible checkpoint. Product-level source extracts and original CSVs are not published.

## Independent preflight and results

Assistant preflight passed; learner SQL28 execution remains pending. The numerical comparison below omits only the two repeated display-window columns: every actual report row includes ABC `2016-01-26..2016-04-24` and XYZ `2016-01-30..2016-04-22`.

| 组合 | 商品数 | 商品占比 % | 90 天销量 | 90 天销量占比 % | 84 天销量 | 84 天销量占比 % | 状态 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| A × X | 1082 | 35.4870 | 2892612 | 76.7842 | 2717788 | 76.8488 | PASS |
| A × Y | 38 | 1.2463 | 100661 | 2.6720 | 95885 | 2.7113 | PASS |
| A × Z | 15 | 0.4920 | 20626 | 0.5475 | 18907 | 0.5346 | PASS |
| A × ZERO_SALES | 0 | 0.0000 | 0 | 0.0000 | 0 | 0.0000 | PASS |
| B × X | 903 | 29.6163 | 528762 | 14.0360 | 496107 | 14.0280 | PASS |
| B × Y | 44 | 1.4431 | 23401 | 0.6212 | 22056 | 0.6237 | PASS |
| B × Z | 21 | 0.6888 | 13015 | 0.3455 | 11062 | 0.3128 | PASS |
| B × ZERO_SALES | 0 | 0.0000 | 0 | 0.0000 | 0 | 0.0000 | PASS |
| C × X | 760 | 24.9262 | 160754 | 4.2672 | 150665 | 4.2602 | PASS |
| C × Y | 85 | 2.7878 | 13764 | 0.3654 | 12920 | 0.3653 | PASS |
| C × Z | 94 | 3.0830 | 13589 | 0.3607 | 11149 | 0.3153 | PASS |
| C × ZERO_SALES | 3 | 0.0984 | 12 | 0.0003 | 0 | 0.0000 | PASS |
| ZERO_SALES × X | 0 | 0.0000 | 0 | 0.0000 | 0 | 0.0000 | PASS |
| ZERO_SALES × Y | 0 | 0.0000 | 0 | 0.0000 | 0 | 0.0000 | PASS |
| ZERO_SALES × Z | 0 | 0.0000 | 0 | 0.0000 | 0 | 0.0000 | PASS |
| ZERO_SALES × ZERO_SALES | 4 | 0.1312 | 0 | 0.0000 | 0 | 0.0000 | PASS |
| TOTAL | 3049 | 100.0000 | 3767196 | 100.0000 | 3536539 | 100.0000 | PASS |

A × X has 35.4870% of products and 76.7842% of 90-day units (76.8488% of 84-day units). C × X has 24.9262% of products but 4.2672% of 90-day units. These are descriptive quantity-contribution differences under the fixed membership, not economic-value rankings or changes between periods. Five cells are empty and remain visible. C × ZERO_SALES contains three products with 12 units in 90 days and zero in 84 days; ZERO_SALES × ZERO_SALES contains four products with zero in both windows.

The [runner](../validation/preflight_abc_xyz_contribution.py) reads only registered sales/calendar CSVs, verifies their hashes before and after, and creates a private 90-day fixture before executing actual SQL21, SQL23, SQL24, SQL25, SQL27 and read-only SQL28. It does not open the learner database or rebuild full-history facts. Independently aggregate original wide day arrays into each product's 90-day total, twelve weekly vectors and excluded-six-day total. Independent Python crossing-prefix endpoints determine ABC; centered Fraction population CV squared determines XYZ. The existing 70-digit Decimal reference validates floating metrics with the declared tolerance, while copied snapshot fields must match exactly.

Verify all **3,049 products and 22 combined fields**, all 3,049 displayed-membership/unit records, all **16 integer cells**, and all **17 report rows**, including Decimal half-up four-place percentages and both windows. Reconcile count and both unit measures along each ABC and XYZ margin. The independently rebuilt count matrix also matches the learner's accepted SQL27 screenshot. Source controls remain 3,049 products, 3,767,196 units in 90 days, 3,536,539 in 84 days and 230,657 in the excluded six days.

All **18 targeted cases** passed. Five valid cases cover mixed labels and denominators, an all-zero universe (both unit-share columns NULL), positive 90-day sales with an entirely zero 84-day window (only 84-day shares NULL), constant sales with empty classes, and accepted numerical variation preserved exactly. Thirteen rejection cases cover empty/missing/duplicate combined products, copied floating values, bridge and window drift, equal-unit label swaps preserving count/unit margins, incorrect combined schema, duplicate ABC keys, incorrect ABC or XYZ source labels, missing weekly observations and a nonfinite source metric.

Before/after fingerprints match for all five input tables: ABC, weekly sales, variability metrics, XYZ and the combined snapshot. Both CSVs and all 26 pre-existing preflight records remain unchanged. The private databases were removed. DuckDB v1.5.5 used two threads and a 2GB memory limit. SQL28 report, integer-cell and membership CLI queries took 0.495, 0.144 and 0.145 seconds respectively; these exclude Python comparison and file hashing and are not performance guarantees. Machine-readable hashes, error bounds, complete report columns and fixture names are in [the preflight evidence](../data/abc_xyz_contribution_preflight.json).

## Interpretation and next step

Inspect contribution together with the accepted variability label; do not prioritize a cell solely because it contains many products. After learner acceptance, inspect representative product records within selected cells and explain their historical quantities, zero weeks and relative variation. Any subsequent operational recommendation must respect the short observation window, smoothing from store pooling and unavailable cost, inventory and lead-time data.
