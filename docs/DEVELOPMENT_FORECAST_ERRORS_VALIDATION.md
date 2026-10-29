# Development comparison of the two forecast baselines

## Purpose and scope

[SQL36](../sql/36_compare_development_forecast_errors.sql) makes the first direct error comparison between the accepted SNAIVE7 and WEEKDAY4 candidates. It answers how their predicted units compare with recorded units on the three fixed development windows. It is a read-only query. On 29 October 2026 (Australia/Sydney), the learner accepted all six rows and twelve displayed fields; their canonical report fingerprint matches the historical assistant preflight exactly. The [evaluation plan](EVALUATION_PLAN.md) specifies metrics, temporal boundaries and aggregation before computing these results.

The population remains all 216 product-store series in FOODS_1 / CA_1. Both models are scored on the same dates and records, including zeros. This is a fixed retrospective slice from the released catalog, not evidence of performance across all 30,490 M5 series or of the active assortment known at every historical origin.

| Development origin | Training ends | Scored 28-day period |
| --- | --- | --- |
| DEVELOPMENT_1 | 2016-01-31 / d_1829 | 2016-02-01–2016-02-28 |
| DEVELOPMENT_2 | 2016-02-28 / d_1857 | 2016-02-29–2016-03-27 |
| DEVELOPMENT_3 | 2016-03-27 / d_1885 | 2016-03-28–2016-04-24 |

There are 6,048 positions per model/origin, 18,144 distinct actual product-store days, 36,288 model-specific error rows and 1,296 model/origin/series diagnostics. Each error row is an observed daily unit count paired with a forecast, not a transaction. Missing actual records must fail validation rather than being imputed as zero.

## Score the saved candidates

The query checks the frozen scope and the complete schema, keys and values of the two saved forecast tables against their origin-available historical construction rules. It then evaluates the persisted candidate values. Reconstructing expected values is an integrity check, not permission to substitute them for corrupted saved forecasts.

SNAIVE7 repeats the last observed seven-day pattern. WEEKDAY4 repeats the seven means from the previous four observations of each weekday. WEEKDAY4's exact quarter-unit values are retained during scoring; they are not rounded to integers. Both models keep all 216 series and all 28 horizons.

## Metrics and aggregation

Let error = forecast minus actual for one daily position.

| Report metric | Definition and interpretation |
| --- | --- |
| mae | Sum of absolute errors divided by 6,048 positions. Lower is better. Units: average absolute unit error per product-store day. |
| mean_error | Sum of signed errors divided by 6,048. Positive means overprediction, negative means underprediction. Opposite errors can cancel, so a value near zero does not imply accurate predictions. |
| macro_rmsse | Calculate RMSSE separately for each eligible series, then take the unweighted arithmetic mean. Lower is better under the same scope and scale rule; it is dimensionless, not a percentage. |

MAE and mean error include every series. Every series has 28 scored positions, so position-level averages also equal unweighted averages of the corresponding series metrics. No revenue or sales-volume weights are applied. The RMSSE eligibility cohort is determined by training data alone and must be identical between the two models at the same origin.

For a series, let T be the training cutoff and s the first day at or before T with strictly positive units. Retain the full sequence from s through T, including subsequent zeros:

```text
training_scale = sum((units[t] - units[t-1])^2, t=s+1..T) / (T-s)
evaluation_MSE = sum(error[h]^2, h=1..28) / 28
series_RMSSE = sqrt(evaluation_MSE / training_scale)
macro_RMSSE = mean(series_RMSSE over series with a defined training scale)
```

The leading-zero-to-first-positive jump is excluded. Later zero-sales days are retained. No positive training observation, fewer than two retained observations, or zero scale makes RMSSE undefined. It remains NULL even if the forecast error happens to be zero. Do not substitute an epsilon or zero. Valid/undefined counts and aggregate status diagnostics make this eligibility visible; those series still contribute to MAE and signed error.

The macro score is a mean of individual square roots, not a square root of a mean ratio. It is not official M5 WRMSSE. A score of one is tied to the historical scaling rule and does not establish a victory over the out-of-sample SNAIVE7 candidate. Compare the two candidates' measured development errors directly.

## Numeric integrity

Quarter-unit forecasts allow exact integer error numerators: q = four times forecast minus four times actual. Absolute and signed error sums use quarters; squared-error sums use sixteenths. Promote operands before multiplication so valid large INTEGER units cannot overflow a narrow squared-error type. Training differences and their squared sums are accumulated exactly in sufficiently wide integers.

Use unrounded diagnostics to calculate metrics. Six-decimal formatting is applied only to final report values; independent checks compare full-precision metrics and exact integer diagnostics separately. Display rounding cannot decide a near tie.

## The six-row report

The 12 columns are `origin`, `model`, `series_count`, `evaluated_rows`, `actual_units`, `predicted_units`, `mae`, `mean_error`, `rmsse_valid_series`, `rmsse_undefined_series`, `macro_rmsse`, and `check_status`.

Each origin has two rows in SNAIVE7 then WEEKDAY4 order. Series count is 216 and evaluated rows are 6,048 per row. The actual total must be the same between the two models at that origin. RMSSE valid plus undefined counts must equal 216; a zero-valid cohort produces NULL macro RMSSE, not a failed data audit or a numeric zero score. There is no TOTAL row pooling origins.

PASS confirms input, forecast and evaluation checks. It is not a performance grade. Compare MAE and macro RMSSE across the two rows for each origin, and use mean error to understand underprediction or overprediction. A single smaller value does not establish general superiority.

## Final-holdout boundary

The final forecast period, 2016-04-25–2016-05-22 (d_1914–d_1941), remains unscored. Saved final-origin candidate rows can be validated against their historical inputs without reading final actuals. SQL36 never uses final-holdout unit values in errors or scale estimates. Earlier development dates may become training history at later origins; scales and predictions still respect their individual cutoffs.

Earlier engineering reconciliation included full-snapshot totals, so this is not a claim of wholly unseen data. No final method is selected by this query. The first comparison is development evidence for the fixed slice; subsequent model decisions and broader-scope evaluation remain separate work.

## Independent verification and execution

The [runner](../validation/preflight_development_forecast_errors.py) and [preflight evidence](../data/development_forecast_errors_preflight.json) use read-only original CSV files and private temporary databases under ignored `tmp/`. The learner's persistent database is never opened. Detailed rows and product identifiers remain private; public output contains aggregate results, coverage diagnostics and fingerprints.

The executed assistant preflight matched all **413,208 training observations across six fields**, both complete candidates (**24,192 × 13 SNAIVE7 fields and 24,192 × 15 WEEKDAY4 fields**), **36,288 scored rows across 12 fields**, **1,296 series diagnostics across 16 fields**, and all six displayed rows across 12 fields. Exact integer fields and status labels agreed; floating RMSSE values were compared to a 70-digit Decimal reference using absolute tolerance 1e-10 plus relative tolerance 1e-13. Maximum absolute deviations were about 3.35e-16 for individual RMSSE and 3.73e-16 for the macro score. Both candidate fingerprints matched their accepted evidence.

All **20 targeted cases** passed: 12 valid metric/isolation cases and eight deliberate rejections. They cover the excluded initial jump and retained later zeros, three undefined-scale reasons, mean-of-roots aggregation, signed-error cancellation, very large squared integers, origin-specific scales, changed/absent final outcomes, and damaged saved forecasts or development observations. Inputs and saved forecasts remained unchanged during both valid and rejected comparisons. The two original source files used by this step, dependent scripts/helpers, accepted candidate evidence and historical preflight records remained unchanged, and private temporary files were removed. The evaluation-plan hash was captured before tests and verified unchanged on completion.

The executed aggregate results below were first independently checked by the assistant and are now **also accepted from the learner screenshot**. These two evidence scopes remain separate: the screenshot confirms displayed aggregates; the preflight reconciles detailed source, forecast and scoring records. Each row has 216 series, 6,048 evaluated positions, 216 defined RMSSE scores, zero undefined scores and PASS status.

| Origin | Model | Actual units | Predicted units | MAE | Mean error | Macro RMSSE |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| DEVELOPMENT_1 | SNAIVE7 | 8,891 | 8,268.00 | 1.516700 | -0.103009 | 0.937803 |
| DEVELOPMENT_1 | WEEKDAY4 | 8,891 | 8,336.00 | 1.358714 | -0.091766 | 0.807044 |
| DEVELOPMENT_2 | SNAIVE7 | 9,456 | 8,112.00 | 1.384590 | -0.222222 | 0.880599 |
| DEVELOPMENT_2 | WEEKDAY4 | 9,456 | 8,891.00 | 1.298446 | -0.093419 | 0.772624 |
| DEVELOPMENT_3 | SNAIVE7 | 8,017 | 11,368.00 | 1.644676 | 0.554067 | 0.986653 |
| DEVELOPMENT_3 | WEEKDAY4 | 8,017 | 9,456.00 | 1.225116 | 0.237930 | 0.722085 |

WEEKDAY4 has lower MAE and macro RMSSE in each of these three development windows. Both methods underpredict in aggregate in the first two windows and overpredict in the third. This is descriptive evidence for the fixed slice, not a significance test, final model selection, final-holdout score or operational benefit. Detailed error and series rows remain private; the public JSON includes aggregate RMSSE-status coverage and fingerprints.

Run the complete SQL36 file in the existing `retail_merchandising` connection. It can be repeated as a read-only check; it creates no table and leaves both saved candidates and analytical input tables unchanged. The six-row screenshot acceptance is recorded below and remains separate from the assistant's detailed preflight evidence.

## Learner acceptance — 29 October 2026

The [learner acceptance record](../data/development_forecast_errors_learner_acceptance.json) contains all six aggregate rows and twelve displayed fields in origin/model order. Predicted totals shown without decimal places are normalized to two-decimal strings; metric values retain six decimals, including omitted display zeros such as `1.5167` → `1.516700`. Counts and actual units remain integers. The SQL36 runner's canonicalization reproduces report SHA-256 `46388fd2f259920a7ce05d0fc6b0ededad3588f6c100ce0e464c3a738622d9f7`, exactly matching historical preflight.

Each row shows 216 series, 6,048 evaluated positions, 216 valid RMSSE series and zero undefined series. Those 36,288 model-specific positions correspond to 18,144 distinct actual product-store days because both models score the same observations. The scope identifiers come from the earlier accepted scope audit, not extra fields in this screenshot. No direct learner-database read occurred. The screenshot accepts the displayed report; detailed source comparisons, candidate reconstruction, per-row errors, per-series diagnostics, 20 targeted cases and read-only/cleanup checks remain separate assistant evidence. No individual product identifiers, detailed vectors or screenshot are saved publicly.

Assistant interpretation remains limited to these three development windows: WEEKDAY4 has lower average MAE and macro RMSSE, while both models underpredict in aggregate in the first two windows and overpredict in the third. An average advantage does not tell us how many individual series improve. This acceptance does not establish final model choice, final-holdout performance, statistical significance, operational benefit or independently tested learner understanding.

## Next paired comparison

[SQL37](../sql/37_compare_series_forecast_improvements.sql) will compare the two models for each series at each development origin and summarize wins, exact ties, losses and metric deltas in six origin/metric rows. For MAE, compare exact summed absolute errors in quarter units. For RMSSE, compare exact summed squared errors in sixteenths on the common valid training-scale cohort; equal positive scales and equal 28-day denominators preserve this ordering. Do not decide ties from rounded displayed metrics. Delta is WEEKDAY4 minus SNAIVE7, so a negative value favors WEEKDAY4. Report excluded/undefined RMSSE series explicitly; final-holdout actuals and final selection remain outside this step.

See the [paired-series comparison method](SERIES_FORECAST_IMPROVEMENTS_VALIDATION.md) for the next step.
