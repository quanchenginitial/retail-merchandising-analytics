# Fixed protocol: full-catalog development forecast errors

## Purpose and unchanged comparison

SQL38 has an accepted eight-row construction report for both full-catalog candidates. [SQL39](../sql/39_compare_full_catalog_development_errors.sql) evaluates their development errors over the same **30,490 product-store series**, all 3,049 products and ten stores. Its question is whether the pilot development comparison holds across the released catalog. WEEKDAY4 remains the preferred development baseline only within the earlier pilot until broader evidence is available. Both candidates remain in this comparison.

Freeze this protocol before computing the new full-catalog metrics. Keep the existing [evaluation plan](EVALUATION_PLAN.md), [catalog construction protocol](FULL_CATALOG_BASELINE_FORECASTS_PROTOCOL.md), two model formulas and roster unchanged. The roster is retrospective and unfiltered by sales, forecast errors, ABC/XYZ labels or RMSSE eligibility. This is a descriptive development comparison, not final selection, an independent experiment or a deployment outcome.

## Windows and observation counts

| Origin | Training cutoff | Scored horizon | Full training positions |
| --- | --- | --- | ---: |
| DEVELOPMENT_1 | d_1829 / 2016-01-31 | d_1830–d_1857 / 2016-02-01–2016-02-28 | 55,766,210 |
| DEVELOPMENT_2 | d_1857 / 2016-02-28 | d_1858–d_1885 / 2016-02-29–2016-03-27 | 56,619,930 |
| DEVELOPMENT_3 | d_1885 / 2016-03-27 | d_1886–d_1913 / 2016-03-28–2016-04-24 | 57,473,650 |

Each origin/model has **30,490 × 28 = 853,720 scored positions**. Both models together produce **5,122,320 model-specific errors** from **2,561,160 distinct actual product-store days**. There are **182,940 model/origin/series diagnostics**, using 91,470 series/origin training scales.

The bounded full-history source projection contains all **58,327,370 observations from d_1 through d_1913**. It includes the three development target windows and earlier history; every scale still stops at its own training cutoff. Earlier development outcomes legitimately enter later origins' training histories. The d_1914–d_1941 final-holdout actual quantities remain excluded. Saved final-origin forecast integrity may be checked against its historical construction rules without scoring final outcomes.

Full-history input validation is new here: SQL38 proved the recent 112-day inputs needed to build forecasts, not the earlier history required to calculate RMSSE scales. Every series must have each canonical day d_1–d_1913 exactly once, valid nonnegative INTEGER units and matching date/week fields. Unknown or null item/store keys, missing days, duplicate days and invalid mappings must fail rather than be dropped or imputed.

## Score persisted forecasts and preserve exact arithmetic

Use the accepted `mart.m5_forecast_baselines_all_28d` values after checking their schema, complete key coverage and full construction values. Expected-value reconstruction is a validation step, not a replacement for damaged saved forecasts. This read-only query creates no new table and changes no inputs or candidates.

Keep each WEEKDAY4 quarter-unit prediction. Define daily error as forecast minus actual. Express the error numerator in quarter units; absolute and signed sums stay exact integers, and squared numerators are in sixteenths. Promote integer operands to a sufficiently wide type before multiplication. MAE and signed mean error use every daily position, including zeros, and are rounded only for the displayed report.

MAE = sum of absolute daily errors / 853,720, in units per product-store day. Mean error = sum of signed daily errors / 853,720; positive means overprediction, negative underprediction. Because each series has exactly 28 positions, these also equal the unweighted averages of the corresponding series metrics. No sales-volume or revenue weights are applied.

## Training-only RMSSE and coverage

For each series at cutoff T, find its first strictly positive training day s at or before T. Retain the sequence from s through T, including later zeros. Training scale is the sum of squared consecutive differences from s+1 through T divided by T-s. The leading-zero-to-first-positive jump is excluded. Compute each series' 28-day mean squared forecast error and divide by this scale before taking the square root.

No positive training value, fewer than two retained training observations, or a zero training scale leaves RMSSE undefined, even when the forecast happens to be perfect. Keep NULL; do not substitute zero or an epsilon. Every such series still contributes to MAE and signed mean error. Report the valid/undefined counts and aggregate status-group MAE/bias so exclusions remain visible. Eligibility must be identical across both models at an origin because it depends only on common training history.

Macro RMSSE is the unweighted arithmetic mean of individually calculated valid series RMSSE values. It is not a root of averaged ratios, a pooled score, a percentage, a sales-weighted average or official M5 WRMSSE. A zero-valid cohort returns NULL macro RMSSE and can still pass integrity checks. RMSSE=1 does not by itself establish superiority to the measured out-of-sample SNAIVE7 candidate.

## Six-row output and interpretation

Return three development origins in chronological order, each SNAIVE7 then WEEKDAY4, with these 12 fields: `origin`, `model`, `series_count`, `evaluated_rows`, `actual_units`, `predicted_units`, `mae`, `mean_error`, `rmsse_valid_series`, `rmsse_undefined_series`, `macro_rmsse`, `check_status`.

Every row has series_count 30,490 and evaluated_rows 853,720. Valid plus undefined RMSSE counts equal 30,490; both models share the same actual total and eligibility cohort at each origin. Predicted totals retain two decimal places. Error metrics display six decimals, computed from unrounded values. No TOTAL row pools origins.

PASS verifies input, candidate, scoring and metric integrity; it is not a favorable performance grade. Lower MAE or macro RMSSE supports a development comparison under this fixed scope. Near-zero bias can reflect cancellation. Global averages do not establish uniform category/store or product improvements. The same products and stores recur across windows, so no significance or independent-trial claim follows from these six descriptive results. Final selection, wider subgroup analysis and final-holdout evaluation remain separate work.

## Efficient independent verification

Use private temporary DuckDB databases and read-only original files; never open the learner's persistent database. A single per-series lag and cutoff-conditional aggregates can derive the three scales without expanding every training day into three origin rows. Avoid millions of Python row dictionaries; packed quantity arrays and streamed comparisons keep memory bounded.

Independently assign deterministic indices to the sorted complete item/store roster. Directly compare all **58,327,370 (series_index, day_number, units) triples**, the entire **30,490-row index/item/store mapping**, and the independently verified calendar fields. Separately prove that every stored fact date and week agrees with that calendar. State these as three direct history fields plus complete mapping/calendar checks; do not claim a six-field history CSV comparison. Unknown or null keys must fail before an inner join could discard them.

Stream-check the saved 6,829,760 forecasts across 14 fields, the 5,122,320 scored rows and 182,940 series diagnostics against independent original-source calculations. Use high-precision Decimal references for roots and macro averages, exact integer comparisons for error and scale numerators, and explicit tolerances for floating values. Reconcile the accepted SQL38 construction summary and the overlapping pilot SQL36 development aggregates. Preserve sources, saved forecasts, earlier evidence and this protocol, then clean temporary detail files.

Publish only aggregate rows, RMSSE-status coverage and fingerprints. Keep product identifiers, quantity/error arrays, individual diagnostics and database files private. Focused fixtures address newly introduced multi-store history attribution, cutoff-specific scale eligibility, malformed full-history records and saved forecast damage; do not rerun unrelated frozen suites without a new concern. Assistant preflight and learner screenshot acceptance remain distinct evidence scopes.
