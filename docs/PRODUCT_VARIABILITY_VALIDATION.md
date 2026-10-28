# Product weekly variability metrics: construction and validation

28 October 2026. The learner has accepted [SQL23's weekly observations](PRODUCT_WEEKLY_VALIDATION.md). SQL24 converts each product's 12-week vector into descriptive metrics. Assistant preflight is distinct from pending learner execution. No XYZ labels are assigned in this step.

## Purpose and scope

Describe product sales level, relative variability and zero-sales frequency before assigning variability classes. Use all 12 complete retail weeks from 2016-01-30 through 2016-04-22, pooled across all 10 stores. Every week, including an observed zero, contributes to the denominator. The separate 90-day ABC window remains unchanged and must remain visible in later combined outputs.

For weekly recorded units x[1] through x[12], the mean is sum(x)/12. Population standard deviation is sqrt(sum((x-mean)^2)/12); CV is population SD divided by mean when mean is positive, and NULL when mean is zero. This is a choice to describe the complete observed window, not to estimate a future-population standard deviation. The implementation uses DuckDB's documented `STDDEV_POP`; it does not use the sample-standard-deviation denominator of 11. [DuckDB 1.5 aggregate reference](https://duckdb.org/docs/1.5/sql/functions/aggregates#stddev_popx).

A constant positive series has zero SD and CV; an all-zero series has zero SD but undefined CV. Keeping the latter NULL prevents absence of recorded sales from being labelled perfect stability. CV is dimensionless, but can be large for small or intermittent quantities. A low CV is not a tested forecasting result. Pooling stores can smooth store-specific fluctuations; 12 observations do not establish long-run seasonality or stable future demand.

## Stored fields

`mart.m5_product_variability_12w` contains one row for every source product: 3,049 rows, 14 columns. Floating metrics are stored as unrounded DOUBLE values.

| Field | Type | Definition |
| --- | --- | --- |
| item_id | VARCHAR | Source item key |
| dept_id | VARCHAR | Source department |
| cat_id | VARCHAR | Source category |
| window_start | DATE | 2016-01-30 |
| window_end | DATE | 2016-04-22 |
| week_count | BIGINT | All 12 complete weekly observations |
| units | HUGEINT | Sum of the 12 weekly unit values |
| mean_weekly_units | DOUBLE | units / 12 |
| stddev_weekly_units | DOUBLE | Population SD of the 12 weekly values |
| cv_weekly | DOUBLE | SD / mean for positive mean; otherwise NULL |
| zero_sales_weeks | BIGINT | Count of zero-unit weeks |
| zero_week_share | DOUBLE | zero_sales_weeks / 12, a ratio from 0 to 1 |
| positive_weeks | BIGINT | Count of strictly positive-unit weeks |
| mean_positive_gap_weeks | DOUBLE | Mean distance between adjacent positive week positions; NULL with fewer than two positives |

For the gap metric, weekly positions 1–12 come from calendar-date distance, not subtraction of retail-week codes. If positive positions are t[1]...t[k], the average adjacent distance equals (t[k]-t[1])/(k-1) for k>=2. SQL uses this telescoping identity; the independent Python reference explicitly averages the adjacent differences. For positive observations only in weeks 1 and 12, the gap is 11; with a single positive week it is NULL.

This conditional, within-window gap omits unknown intervals before the first and after the last observed positive week. It is not 12/positive_weeks, does not fully characterize sales clustering, and is not an estimate of unconstrained demand-arrival intervals. Zero recorded units do not identify shelf availability or stockout.

## Validation contract

[SQL24](../sql/24_build_product_variability.sql) first checks the weekly table's eight-column schema, required product keys and hierarchy, exactly 12 unique expected week keys per product, matching week boundaries, nonnegative non-NULL units and 70 source daily rows per item/week. The source product dimension must remain unique and complete. This is a check of the accepted weekly snapshot's internal integrity; it does not re-scan the learner daily fact or raw files. Source equality relies on SQL23; revalidate SQL23 if its source is deliberately changed.

The create statement consumes the source and computed-metric guards, including the empty-source case, and never overwrites an existing table. Validation recalculates all metrics from the weekly snapshot and checks the target's exact 14-column schema and unique item keys. The nine identifier/date/count/unit fields are compared exactly in both directions with EXCEPT ALL, including multiplicity. Each of the five floating fields requires matching NULL conditions, finite values and appropriate ranges, then allows absolute error no greater than **1e-9 + 1e-9 × abs(expected)**. This tolerance accommodates numerical arithmetic; it is not a business threshold or a rule for XYZ membership.

Stored metrics are not rounded for validation. Non-finite values, changed integer fields and incorrect NULL values cannot be hidden by the floating tolerance. A failing guard raises an error rather than emitting a valid result. If the target exists, run only the complete query below `-- VALIDATION:`.

## Three-row report

The report has POSITIVE_12W, ZERO_12W and TOTAL, with eight columns: sales_group, sku_count, units, zero_sales_product_weeks, median_cv, p90_cv, max_cv and check_status. The first two groups partition source products by whether their 84-day units are positive. Counts/units/zero-sales-week counts add to TOTAL. Empty groups retain a row with count/units zero and NULL CV summaries.

CV summaries describe the equally weighted distribution of individual product CVs, not a CV of pooled product sales. `quantile_cont` uses linear interpolation at index (n-1)*p after removing NULL values; the report uses p=0.5 and p=0.9. Valid groups with no defined CV have NULL summaries. [DuckDB 1.5 quantile documentation](https://duckdb.org/docs/1.5/sql/functions/aggregates#quantile_contx-pos).

Only displayed CV summaries are rounded to six decimal places and represented as DECIMAL(12,6). TOTAL's CV summaries match POSITIVE_12W because all-zero products' undefined CV values are excluded, while those products remain in total counts. A percentile is not a share of sales and the maximum is not a forecast error.

## Independent preflight

The [runner](../validation/preflight_product_variability.py) uses private temporary databases under ignored tmp with two threads and a 2GB memory limit; it never opens the learner database. Only the original sales and calendar CSVs are read, with registered hashes checked before and after. A private window-only daily fixture supports the actual SQL23 weekly build. Its 13 summary rows must match the learner acceptance record before SQL24 runs. This is not a full historical price-bearing fact rebuild.

Independent weekly vectors come from summing each week's original seven wide CSV columns over stores. Python computes population metrics with high-precision arithmetic and cross-checks population SD against `statistics.pstdev`. It computes gap by adjacent positive positions and implements linear percentile interpolation on unrounded CVs. All 3,049 product rows and all 14 fields, including intentional NULLs, are compared with actual SQL24 output; floating comparisons use the documented tolerance. The three displayed report rows are also compared. The accepted input weekly rows must be unchanged before and after SQL24. Only aggregate findings are published, not product-level extracts.

All 22 targeted cases passed. A mixed vector fixture covers constant positive sales, all-zero sales, a single positive week with population CV sqrt(11), positive weeks 1 and 12 with gap 11, adjacent positives with gap 1, sparse sales, a near-constant series around one million and a trend. Additional cases cover all-zero/no-zero groups, empty/duplicate/missing weekly keys, invalid dates or source coverage, NULL/negative units, duplicate product mappings and schema problems. Target tests reject missing/duplicate products, incorrect CV NULL handling, NaN SD, infinite mean, altered positive-week gaps, offsetting zero/positive-week counts and unit redistribution between products that preserves the total.

All 3,049 stored rows matched the independent reference across all 14 fields, including all intentional NULLs, and all three six-decimal report rows matched. The input weekly table's 36,588 rows matched the independent wide-column reference and remained unchanged after SQL24. Both source-file hashes remained unchanged and the private database was removed.

The largest observed absolute floating discrepancy was approximately 1.67e-13, and the largest discrepancy divided by its allowed tolerance was approximately 1.51e-6. No tolerance was widened. Seven CVs were undefined; 17 positive-gap values were undefined (seven all-zero products and ten with only one positive week). The machine-readable record retains comparison counts and errors separately for all five floating metrics and the aggregate positive-week-count distribution.

Using two threads and a 2GB memory limit, the private source fixture took 5.801 seconds to prepare; SQL24 build/validation took 0.180/0.198 seconds. These are assistant DuckDB CLI timings, excluding Python references/comparisons and hashing, and are not performance promises for the learner environment.

## Assistant preflight result; learner confirmation pending

| Group | SKUs | Units | Zero-sales product/weeks | Median CV | P90 CV | Max CV | Status |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| POSITIVE_12W | 3042 | 3536539 | 972 | 0.205417 | 0.495779 | 3.316625 | PASS |
| ZERO_12W | 7 | 0 | 84 | NULL | NULL | NULL | PASS |
| TOTAL | 3049 | 3536539 | 1056 | 0.205417 | 0.495779 | 3.316625 | PASS |

These are descriptive measurements for the stated recorded-sales window. XYZ classification, threshold sensitivity, forecast evaluation and inventory policies remain subsequent work.

See the [machine-readable preflight](../data/product_variability_preflight.json) and [current learner instructions](FIRST_STEP_ZH.md).
