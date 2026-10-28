# Product XYZ baseline: construction and validation

28 October 2026. The learner's DBeaver screenshot confirms all five SQL25 report rows have `check_status=PASS` and numerically match the independent assistant preflight. The XYZ baseline and displayed validation results are accepted. The [learner acceptance record](../data/product_xyz_learner_acceptance.json) transcribes the screenshot; no direct read of the learner database was performed. See the preceding [variability acceptance](PRODUCT_VARIABILITY_VALIDATION.md), [SQL25](../sql/25_build_product_xyz.sql), [preflight evidence](../data/product_xyz_preflight.json) and [runner](../validation/preflight_product_xyz.py).

## Purpose and frozen scope

Translate validated relative weekly variability into reproducible product groups. Retain the 12 complete source retail weeks from 2016-01-30 through 2016-04-22, all ten stores pooled, including observed zero weeks. The separate accepted ABC snapshot covers 2016-01-26 through 2016-04-24; later combined outputs must show both windows. The final forecasting holdout remains outside this classification window.

For positive total units, X means population CV <= 0.5, Y means 0.5 < CV <= 1, and Z means CV > 1. Zero-total products are ZERO_SALES with NULL CV. These thresholds were declared in the architecture before SQL25 outcomes; they are provisional project choices, not universal or optimized operating policies. Sensitivity analysis is a subsequent step.

## Exact boundary contract

Use the 12 integer weekly units x, their sum S, sum of squares Q, and n=12. Population CV squared equals `(n*Q-S*S)/(S*S)` when S>0. Define N=n*Q-S*S and D=S*S. Assign ZERO_SALES first when S=0. Otherwise assign X if 4*N<=D, else Y if N<=D, otherwise Z. This is algebraically the same CV definition as SQL24. Exact 0.5 belongs to X and exact 1 belongs to Y; neither displayed rounding nor numerical tolerance expands a class boundary.

The SQL uses HUGEINT arithmetic and guards each weekly input before squaring at 0 through `7*expected_stores*2147483647`, reflecting the accepted INTEGER daily-unit type and 70 daily rows per product/week. With 12 weeks these bounds remain far inside HUGEINT capacity. This is an arithmetic/provenance bound, not a merchandising outlier threshold. An unsupported value raises an error.

SQL24 stores unrounded DOUBLE metrics; their numerical tolerance remains `1e-9 + 1e-9*abs(expected)`. The XYZ decision uses exact weekly integers, not that tolerance. A metric at the 0.5 boundary may be stored infinitesimally above 0.5 due to numerical variation while its exact class remains X. A dedicated test exercises that distinction.

## Table and validation

`mart.m5_product_xyz_12w` contains 3,049 unique products and 15 columns: all 14 fields of `mart.m5_product_variability_12w` in the same order, followed by VARCHAR `xyz_class`. It is a frozen descriptive snapshot, not a live view or physical primary-key declaration. Source metrics, weekly records and ABC are not modified. Existing targets are not overwritten; rerun only the query after `-- VALIDATION:` if already created.

Both create and validate recheck the eight-column weekly schema, twelve unique expected weeks and boundaries per product, 70 daily source rows, product hierarchy and mappings, and the 14-column metric table. Recompute all metrics from weekly records, reconcile nine discrete fields exactly and five floating fields with strict NULL/finite/range rules and the declared tolerance. Weekly-to-daily source equality relies on accepted SQL23, not a fresh scan of the learner daily table.

Then derive exact integer labels from the weekly observations. The new target is compared with the source metric snapshot plus expected label using bidirectional EXCEPT ALL across all 15 fields, including multiplicity. Copied floats must match exactly because no recalculation occurs in the target snapshot; the source-to-recomputed metric comparison separately uses tolerance. Empty or duplicate sources, mismatched metrics and incorrect classifications abort rather than produce PASS. The create guard is also evaluated on empty source input.

## Five-row report

X, Y, Z and ZERO_SALES partition all products; TOTAL is their reconciliation. Eight columns report class, SKU count/share, units/share, zero-sales product/week count, median CV and status. Empty groups remain visible with zero counts and NULL median CV. SKU-share denominator includes all 3,049 products. Unit shares use all 3,536,539 recorded units in this window; a zero denominator yields NULL. Percentages display four decimals and can have rounding residuals. Median CV is an equally weighted per-product Type7 quantile, excluding NULL, displayed to six decimals. TOTAL therefore uses the same defined-CV population as SQL24's POSITIVE_12W; it is not the CV of pooled product sales.

The learner screenshot reproduces the following five rows, including all PASS statuses and the intentional NULL median for ZERO_SALES. The acceptance record removes thousands separators, pads percentages to four decimals and median CV to six decimals, and retains NULL. This formatting normalization preserves the displayed values. Independent original-CSV comparisons, copied-field checks, 24 targeted cases, hashes and timings remain separate assistant preflight evidence; the screenshot does not independently establish those checks.

| 分组 | 商品数 | 商品占比 % | 销量 | 销量占比 % | 零销量商品周 | CV 中位数 | 状态 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| X | 2745 | 90.0295 | 3364560 | 95.1371 | 32 | 0.193941 | PASS |
| Y | 167 | 5.4772 | 130861 | 3.7003 | 218 | 0.654150 | PASS |
| Z | 130 | 4.2637 | 41118 | 1.1627 | 722 | 1.645851 | PASS |
| ZERO_SALES | 7 | 0.2296 | 0 | 0.0000 | 84 | NULL | PASS |
| TOTAL | 3049 | 100.0000 | 3536539 | 100.0000 | 1056 | 0.205417 | PASS |

## Independent verification

Read only the registered sales and calendar CSVs, with matching hashes before and after. Build a private 84-day daily fixture, then execute the actual SQL23, SQL24 and SQL25. Separately aggregate each original seven-column wide-sales block directly to a product/week vector. These reference vectors do not read the daily or weekly fact. Compare all 36,588 weekly records and eight fields, all 3,049 product records and 15 XYZ fields, and the five report rows. The three accepted SQL24 summaries also match the independent reference.

Python uses arbitrary-precision integer moments for exact labels, independently cross-checks classification with centered population variance/square root at 70 Decimal digits, and checks all metrics using the existing independent reference helpers. Every copied metric value is also compared exactly with the pre-XYZ snapshot. Both input tables have identical before/after row fingerprints. No learner database or ABC table is opened. Source files remain unchanged; temporary databases were removed. Two threads and a 2GB memory limit were used. CLI timings exclude hashing and Python reference work; see machine-readable evidence.

All **24 targeted cases** pass: exact and immediately adjacent threshold cases, zero/constant-only populations with empty groups, maximum supported arithmetic inputs, tolerated DOUBLE drift at an exact boundary, empty/missing/duplicate weekly or metric records, unsafe squaring input, invalid metric CV/SD/NULL/window/schema, duplicate dimension, and target missing/duplicate products, swapped labels with unchanged group counts, misclassified zero sales, changed copied floats/gaps and incorrect target schema. Fixtures execute the actual build and validation SQL with smaller product/store counts, and confirm rejected builds leave no target table.

## Interpretation and next step

The following interpretation is supplied by the assistant. Under the frozen thresholds, X contains 2,745 products (90.0295%) and 95.1371% of recorded units; Y contains 167 products and Z contains 130. The remaining seven ZERO_SALES products complete the 3,049-product universe. The four classes reconcile to 3,536,539 units and 1,056 zero-sales product/week observations. X itself contains 32 zero-sales product/weeks, so its relative-variation label does not mean every product sold in every week. TOTAL's median CV of 0.205417 reconciles to SQL24's defined-CV population.

Store pooling can smooth single-store fluctuations; twelve weeks offer limited evidence about longer periods. Low relative variation is not a forecast-accuracy measurement. ZERO_SALES identifies observed zero units, not availability, launch status or stockout. No cost or inventory evidence supports a direct reorder quantity, safety-stock or profit recommendation.

SQL26 is planned as a read-only threshold-sensitivity comparison against the accepted baseline: (X boundary, Y boundary) = (0.5, 1.0), (0.4, 1.0), (0.6, 1.0), (0.5, 0.9) and (0.5, 1.1). Each alternative changes one boundary, retains zero sales separately and uses exact integer comparisons. This next step has not been executed or accepted by the learner. Later ABC/XYZ combinations must continue to disclose their different observation windows.
