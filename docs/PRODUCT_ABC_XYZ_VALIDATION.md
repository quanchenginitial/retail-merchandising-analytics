# Product ABC × XYZ combination: construction and validation

29 October 2026 (Australia/Sydney). The learner's DBeaver screenshot confirms all five SQL27 matrix rows have `check_status=PASS` and numerically match the independent assistant preflight; both full date ranges are visible on every row. The combined snapshot and displayed product-count matrix are accepted. The [learner acceptance record](../data/product_abc_xyz_learner_acceptance.json) transcribes the screenshot; no direct read of the learner database was performed. SQL27 retains both declared ABC and XYZ windows and their accepted baseline labels. Cell-level unit contribution and drill-down remain subsequent work. See [XYZ sensitivity acceptance](XYZ_THRESHOLD_SENSITIVITY_VALIDATION.md) and [SQL27](../sql/27_build_product_abc_xyz.sql).

## Purpose and fixed definitions

ABC describes recorded-unit contribution over 2016-01-26–2016-04-24 (90 days), pooled across all ten stores. Rank positive units descending with item_id ascending ties; include the crossing SKU in the earlier cumulative band, using 80%/95% cutoffs. Zero-total products have ZERO_SALES with NULL rank and cumulative units. This is not value or profit ABC.

XYZ describes population CV over 2016-01-30–2016-04-22 (84 days), the twelve complete retail weeks contained within the ABC window, also pooling all ten stores. Keep the accepted thresholds X<=0.5, Y<=1 and Z>1 for positive total units, using exact integer weekly moments. Zero-total products remain ZERO_SALES with NULL CV. Passing sensitivity checks did not select new thresholds or optimize these labels.

The joined classes intentionally refer to different windows. Store both date pairs and display both ranges in the report. No final forecasting holdout date is included. A combination such as AX means membership in both declared descriptive groups, not an automatic inventory or forecasting policy.

## Snapshot fields

`mart.m5_product_abc_xyz` has 3,049 rows and 22 columns. Copy all nine ABC fields and all fifteen XYZ fields, sharing the three identical product identifiers and adding one window-bridge field. No source snapshot is overwritten, and no physical primary key is declared; key uniqueness is explicitly validated.

| Fields | Type | Contract |
| --- | --- | --- |
| item_id, dept_id, cat_id | VARCHAR | Identical source keys and hierarchy in both baselines |
| abc_window_start, abc_window_end | DATE | 2016-01-26 and 2016-04-24 |
| xyz_window_start, xyz_window_end | DATE | 2016-01-30 and 2016-04-22 |
| units_90d, units_84d | HUGEINT | Separate observed-unit totals from ABC and XYZ |
| excluded_six_day_units | HUGEINT | units_90d minus units_84d, required nonnegative |
| abc_sku_rank | BIGINT | Original positive-unit rank; NULL for ABC zero sales |
| abc_cumulative_units | HUGEINT | Original cumulative units; NULL for ABC zero sales |
| abc_class, xyz_class | VARCHAR | Original baseline labels, ZERO_SALES preserved independently |
| week_count | BIGINT | Twelve complete observed weeks |
| mean_weekly_units, stddev_weekly_units, cv_weekly | DOUBLE | Original unrounded population metrics; zero-sales CV remains NULL |
| zero_sales_weeks, positive_weeks | BIGINT | Original counts, summing to twelve |
| zero_week_share, mean_positive_gap_weeks | DOUBLE | Original ratio and conditional within-window positive gap; preserve NULL definitions |

The stored order is specified by SQL27's schema contract. All floating values are copied directly. Thus target-to-source snapshot reconciliation is exact, including floating values and NULLs; source XYZ metrics are separately rechecked against weekly recomputation with the previously declared numerical tolerance.

## Window bridge and zero groups

The 84-day window is a strict subset of the 90-day window. The six excluded dates are 2016-01-26–29 and 2016-04-23–24. For each product, 90-day units must be at least 84-day units; their difference is saved as excluded_six_day_units. This difference comes from accepted snapshots in the learner query. Independent preflight separately sums the six original CSV day columns to verify it for every product.

ZERO_SALES in ABC implies ZERO_SALES in XYZ. The reverse does not hold: a product can sell only in those six excluded dates. Consequently four 90-day zero products and seven 84-day zero products can both be valid. Keep a ZERO_SALES ABC row and a distinct ZERO_SALES XYZ column, rather than filtering out or relabelling these products. This distinction does not establish availability, launch, discontinuation or stockout status.

## Validation contract

Recheck XYZ using the same weekly and metric guards as SQL25: complete twelve-week keys/dates, schema, product hierarchy and uniqueness, numeric metrics and their NULL conditions, and exact baseline labels and copied fields. Recheck ABC's nine-column schema, complete unique products, date window, nonnegative bounded units, product mapping, deterministic ranks/cumulative values and labels. ABC source equality relies on accepted SQL21; weekly-to-daily provenance relies on accepted SQL23. This learner query does not rescan the large daily fact.

Compare source item-key multisets in both directions before accepting the join. Require identical item/dept/category mappings, expected join cardinality and nonnegative per-product bridge. The create guard also rejects empty sources; CREATE TABLE never overwrites an existing target. If the table exists, run only the complete query below `-- VALIDATION:`.

Validate target schema, 3,049 unique item keys, and bidirectional EXCEPT ALL equality across all 22 fields. Check the bridge again. Reconcile ABC row margins to their original counts and 90-day units, and XYZ column margins to original counts and 84-day units. Exact product-field reconciliation catches wrong assignments even if aggregate margins remain unchanged. Invalid data raises an error rather than printing PASS.

## Five-row matrix report

Nine columns: abc_class, x_skus, y_skus, z_skus, zero_xyz_skus, total_skus, abc_window, xyz_window, check_status. Always show A, B, C, ZERO_SALES and TOTAL; empty cells are zero. Each row's four XYZ counts add to its total. The four ABC row totals reconcile to 1,135/968/942/4, the column totals to 2,745/167/130/7, and the grand total to 3,049. TOTAL repeats column marginals; it is not another product group.

Display ABC `2016-01-26..2016-04-24` and XYZ `2016-01-30..2016-04-22` on every report row. This first combined output reports counts only. Do not infer a cell's unit share, sales value, profit or inventory needs from its product count.

## Accepted learner results and independent preflight

The learner screenshot reproduces the five rows below, including all PASS statuses, zero cells, margins and both observation-window strings. The acceptance record omits thousands separators, preserves counts as integers and retains the displayed date ranges. The original-CSV comparisons, 22-field checks, targeted cases, hashes and timings below remain separate assistant preflight evidence; the screenshot does not independently establish those checks.

| ABC | X 商品 | Y 商品 | Z 商品 | 全零 XYZ 商品 | 行合计 | ABC 窗口 | XYZ 窗口 | 状态 |
| --- | ---: | ---: | ---: | ---: | ---: | --- | --- | --- |
| A | 1082 | 38 | 15 | 0 | 1135 | 2016-01-26..2016-04-24 | 2016-01-30..2016-04-22 | PASS |
| B | 903 | 44 | 21 | 0 | 968 | 2016-01-26..2016-04-24 | 2016-01-30..2016-04-22 | PASS |
| C | 760 | 85 | 94 | 3 | 942 | 2016-01-26..2016-04-24 | 2016-01-30..2016-04-22 | PASS |
| ZERO_SALES | 0 | 0 | 0 | 4 | 4 | 2016-01-26..2016-04-24 | 2016-01-30..2016-04-22 | PASS |
| TOTAL | 2745 | 167 | 130 | 7 | 3049 | 2016-01-26..2016-04-24 | 2016-01-30..2016-04-22 | PASS |

Separately, the assistant's original-CSV preflight reproduced **3,767,196 units in 90 days = 3,536,539 units in 84 days + 230,657 units in the excluded six days**, with zero per-product bridge mismatches. Three products have positive 90-day units but zero 84-day units; all are C × ZERO_SALES and together sold 12 units on the six excluded dates. This twelve-unit subtotal is distinct from the full-universe six-day total. The screenshot confirms three C × ZERO_SALES products and four products zero in both classifications, explaining the XYZ-zero column total of seven. It does not display those products' unit totals or independently verify the per-product six-day bridge.

The [runner](../validation/preflight_product_abc_xyz.py) reads the registered sales/calendar CSVs without modification, projects only the 90-day window into a private database, and executes the actual SQL21, SQL23, SQL24, SQL25 and SQL27. No learner database is opened and no full-history fact is rebuilt. Independently sum original wide arrays for all 90 days, the twelve seven-day vectors and the six excluded days. Python uses crossing-prefix endpoints for ABC, exact centered Fraction population CV squared for XYZ, and 70-digit Decimal metric references. These reference methods differ from SQL's prior-cumulative ABC expression and raw-moment CV-square expression.

All **3,049 product rows and 22 fields** match their independent source references, using the established tolerance for the five recomputed floating metrics. Separately, all copied source fields including DOUBLE values match the pre-combination snapshots exactly. Every product's six-day bridge matches the original six columns. ABC and XYZ summaries reproduce the accepted learner reports; the matrix and its count/unit margins reconcile to both baselines.

All **20 targeted cases** passed: four valid cases, ten source-build rejections and six target-validation rejections. The mixed valid case includes an A-class product with all-zero 84-day sales. The other three valid cases cover an all-zero universe with NULL rank/CV, empty cells under constant sales, and accepted numerical variation copied exactly. Rejected inputs cover empty/duplicate ABC keys, missing XYZ products, mismatched hierarchy, wrong ABC rank/class/window, missing weekly observations, altered XYZ snapshot floats and an internally consistent ABC snapshot whose units are below its nested 84-day units. Target corruption cases include floating-value drift, bridge/date errors, duplicate rows, schema change and equal-unit product label swaps preserving matrix count and unit margins. Rejected builds leave no target table.

Before/after fingerprints match for all four input tables: ABC, weekly sales, variability metrics and XYZ. Sales and calendar source hashes, scripts, reference helpers and historical ABC preflight remain unchanged. Private databases were removed. The run used DuckDB v1.5.5, two threads and a 2GB memory limit. Build and validation CLI timings were 0.442 and 0.511 seconds, excluding Python reference work and file hashing; they are not a performance guarantee. Exact hashes, floating errors and fixture names are in [the preflight record](../data/product_abc_xyz_preflight.json). No product-level extract or original CSV is published.

## Interpretation and next step

The following interpretation is supplied by the assistant. The matrix combines contribution and observed relative variability while preserving lineage back to each source product. A × X contains 1,082 products; that count alone does not establish its share of recorded units. The three C × ZERO_SALES products are a valid result of using nested observation windows, not products to discard from the join.

The next planned step compares cell-level recorded-unit contribution, keeping the 90-day and 84-day totals and share denominators separate and showing both windows. Its results and learner execution are pending; monetary contribution is outside that step. A cell can contain few products yet substantial historical units, so counts and unit contribution must be examined separately before product-level inspection.

Short-window CV and store pooling limit interpretation; low CV is not a demonstrated forecasting result. Keep recorded sales separate from unconstrained demand and observed zero sales separate from availability. Actual replenishment decisions require inventory, lead-time, service-level and cost evidence beyond this count matrix.
