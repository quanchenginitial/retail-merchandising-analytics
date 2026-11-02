# Department price-direction and sales-change breakdown

## Purpose and evidence boundary

The learner accepted all **11 rows × 12 fields** of SQL47 on **2 November 2026**, including all eleven PASS values. See the [132-field acceptance record](../data/weekly_price_sales_association_learner_acceptance.json). Price-up means were positive in all eleven weeks; price-down means were positive in the first eight and negative in the final three. Those observations remain descriptive.

The next [SQL48](../sql/48_department_price_sales_association.sql) groups the same transitions by seven merchandise departments to inspect composition. This follow-up was chosen after the observed SQL47 results; its [own protocol](DEPARTMENT_PRICE_SALES_ASSOCIATION_PROTOCOL.md) was fixed before computing the new department outcomes. **Assistant preflight has passed; learner SQL48 execution and acceptance remain pending.**

## Fixed scope and definitions

Retain all **365,880 item/store/week positions**, **30,490 item/store pairs**, twelve complete weeks **30 January–22 April 2016**, and all **335,390 adjacent transitions**. Obtain previous observations across the full twelve-week sequence, then exclude only the first week, which supplies the initial endpoint. Exact cent prices determine UP, DOWN and UNCHANGED when both endpoints exist; otherwise use MISSING_ENDPOINT. Preserve zero-to-zero, zero-to-positive and positive-to-zero transitions without a percentage-growth denominator or price imputation.

Signed unit change is current units minus previous units. Within each department, the report presents all-window direction counts and arithmetic mean signed changes. Means display six decimal places using the established half-away-from-zero rule; empty groups have count zero and NULL mean. Department names remain source codes; their finer business meaning is not invented.

`series_count` is the number of distinct item/store pairs in the department, not the number of distinct products or the sum of distinct pairs from each price direction. A pair can change direction across weeks. Every pair contributes eleven transitions, so each department's total_transitions equals series_count × 11. Department pair counts sum to 30,490. All four price directions remain present in the internal seven-by-four grid of **28 cells**, even if empty. The compact seven-row report shows missing-endpoint counts, and its total unit differences include their outcomes.

Report counts and signed sums are additive across departments. Recover global group means from exact difference sums divided by transition counts; never take a simple average of department means or aggregate displayed medians. The accepted SQL46 full-window report and SQL47 weekly report remain unchanged.

## Interpretation limits

This is a separate departmental breakdown over all eleven transition weeks, **not a joint within-week/department adjustment**. Timing differences found in SQL47 can still contribute to departmental means. Products, stores, sales levels and availability also differ within departments. Changes measured in units do not normalize for baseline demand. UNCHANGED is a descriptive comparison, not a causal control, and repeated adjacent comparisons share endpoints. No price elasticity, promotion lift, significance claim, causal effect, margin or inventory benefit is estimated.

## Independent preflight

The [validator](../validation/preflight_department_price_sales_association.py) uses the original read-only CSVs and a private, bounded temporary database containing the relevant 84-day sales projection and twelve price weeks. It never opens the learner's persistent database or reruns the historical forecasting pipeline. It compares the source-derived weekly input, pooled weekly product data and staged prices; independently computes department membership and every transition; checks all 28 internal cells and all seven displayed rows; and reconciles unchanged SQL45, SQL46 and SQL47 outputs with their frozen evidence.

The completed run recorded **3 passed focused cases**. It matched **365,880 weekly input rows × 12 fields**, **36,588 pooled rows × 8 fields**, **365,864 staged prices × 4 fields**, **28 internal cells × 14 fields**, and the **7×12 report**. The seven input snapshots and source/dependency hashes remained unchanged; **46 historical preflights** were preserved and private files removed. See [machine evidence](../data/department_price_sales_association_preflight.json) for executed case names and detailed reconciliations.

Displayed-report SHA256: `3d7de6c2e4287f68bd7e2e1016a95b5c22bd1f38cf27864536d1d6a4e97687c7`. Canonical report fingerprints use fixed-field-order compact JSON arrays followed by LF, integer counts/sums and fixed-six-place strings for the three displayed means (or NULL for an empty group).

## Measured assistant report

| Department | Item/store pairs | Up count | Up mean change | Down count | Down mean change | Unchanged count | Unchanged mean change | Missing endpoints | Total count | Total unit difference | Status |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| FOODS_1 | 2160 | 48 | -0.229167 | 85 | -0.800000 | 23627 | -0.033436 | 0 | 23760 | -869 | PASS |
| FOODS_2 | 3980 | 287 | 3.128920 | 281 | -0.405694 | 43212 | -0.106498 | 0 | 43780 | -3818 | PASS |
| FOODS_3 | 8230 | 1309 | 3.663102 | 545 | 3.790826 | 88672 | -0.009383 | 4 | 90530 | 6039 | PASS |
| HOBBIES_1 | 4160 | 140 | 1.085714 | 91 | 1.857143 | 45529 | -0.034418 | 0 | 45760 | -1246 | PASS |
| HOBBIES_2 | 1490 | 12 | 1.750000 | 4 | 0.750000 | 16374 | -0.022841 | 0 | 16390 | -350 | PASS |
| HOUSEHOLD_1 | 5320 | 200 | 3.320000 | 321 | 0.214953 | 57987 | -0.124873 | 12 | 58520 | -6466 | PASS |
| HOUSEHOLD_2 | 5150 | 64 | 0.968750 | 409 | 1.880196 | 56177 | 0.015469 | 0 | 56650 | 1700 | PASS |

Every displayed field matches the independent reference. Public evidence contains aggregates and fingerprints only, without real SKU identifiers, individual transitions, screenshots, raw data or databases. Learner reproduction is pending.

Read each mean alongside its sample count. The seven rows are all source departments, not a subset chosen by the direction or magnitude of the results. Run SQL48 and return seven rows and twelve fields including check_status. See the [Chinese current-step guide](FIRST_STEP_ZH.md).
