# Full-catalog development forecast error comparison

## Purpose and scope

The learner accepted SQL38's full-catalog construction report. [SQL39](../sql/39_compare_full_catalog_development_errors.sql) now compares SNAIVE7 and WEEKDAY4 against actual quantities over the three development windows, using all **30,490 product-store series**. It extends the same MAE, signed mean error and macro RMSSE definitions already used in the 216-series pilot. The [fixed protocol](FULL_CATALOG_DEVELOPMENT_ERRORS_PROTOCOL.md) freezes the comparison before new full-catalog scores are computed. On 29 October 2026 (Australia/Sydney), the learner accepted all six rows and twelve displayed fields; the canonical report fingerprint matches historical assistant preflight exactly.

WEEKDAY4's earlier advantage was a pilot finding. This broader comparison tests its descriptive performance on the released catalog; it does not assume the pilot conclusion generalizes. Both candidates remain fixed and saved. No per-product hindsight model selection, April ABC/XYZ feature, future price or final-holdout outcome enters the comparison.

## Why earlier history is needed

SQL38 verified the 112 recent days required to construct the two baseline methods. RMSSE needs a longer historical scale, so SQL39 also checks complete history from **d_1 through d_1913**, totaling **58,327,370 observations**. Each origin uses only its own training prefix for its scale. Data through d_1913 includes the three development outcome windows; the final outcome period d_1914–d_1941 remains excluded.

All series must have one valid record per canonical historical day, nonnegative INTEGER units and correct calendar mappings. Missing, duplicate or unknown keys must fail, not be removed by joins. Keep zero units. A series starting to sell later must not acquire an earlier origin's scale from later positive outcomes.

The source verification uses an exact, independently sorted mapping between each item/store pair and a numeric series index. It directly compares every **series index / day number / units** triple, the complete 30,490-row mapping and the independent calendar. Separate checks verify the stored dates and retail-week fields for all bounded fact rows. These are three direct history fields plus complete mapping/calendar checks, not a claimed six-field exported history comparison.

## Score the same observations fairly

Each model/origin has **853,720 positions** (30,490 series × 28 days). Across three origins and two models, there are **5,122,320 model-specific error rows**, sharing **2,561,160 actual product-store days**. The series-level diagnostics contain **182,940 rows**.

The query validates the complete saved full-catalog candidate schema, keys and construction values, then scores the persisted forecasts. WEEKDAY4 keeps exact quarter-unit predictions. Integer quarter errors and squared-error sixteenths support exact reconciliation; operands are widened before squaring. Missing actuals fail rather than becoming zeros.

| Metric | Interpretation |
| --- | --- |
| MAE | Average absolute forecast error per product-store day, across every series and day. Lower is better. |
| Mean error | Average forecast minus actual. Positive means overprediction and negative underprediction. Cancellation can make the average small despite substantial errors. |
| Macro RMSSE | Compute RMSSE separately using each series' own training scale, then average the valid scores equally. Lower is better under the same scope and scale definition; it is dimensionless. |

For RMSSE, start at the first positive training day s available by cutoff T. Scale the 28-day mean squared error by sum((y[t]−y[t−1])², t=s+1..T)/(T−s), then take the square root. Exclude the leading-zero-to-first-positive jump and retain all later zeros. No positive training value, fewer than two retained observations, or zero scale leaves RMSSE NULL, even for a perfect forecast.

Undefined-scale series still contribute to MAE and signed mean error. Report valid/undefined counts and aggregate status-group controls. Both models have the same eligibility cohort at each origin. Macro RMSSE is an unweighted mean of roots, not official M5 WRMSSE or a percentage; a value below one is not by itself a test against the out-of-sample SNAIVE7 result.

## Six-row output

The 12 columns are `origin`, `model`, `series_count`, `evaluated_rows`, `actual_units`, `predicted_units`, `mae`, `mean_error`, `rmsse_valid_series`, `rmsse_undefined_series`, `macro_rmsse`, and `check_status`.

Return DEVELOPMENT_1, DEVELOPMENT_2 and DEVELOPMENT_3, each SNAIVE7 then WEEKDAY4. Every row has 30,490 series and 853,720 evaluated positions. Both models share the same actual total at an origin. RMSSE valid plus undefined counts equal 30,490; an entirely undefined cohort has NULL macro RMSSE. No TOTAL row pools origins. Predicted totals display two decimals and error metrics six; calculate from unrounded quantities.

PASS confirms engineering and metric checks. Compare the two models within each development window, inspect bias direction and preserve the coverage context. Overall averages do not establish uniform improvements across categories, stores or individual products. These are repeated products and stores, not independent randomized trials.

## Independent verification and execution

The [runner](../validation/preflight_full_catalog_development_errors.py) uses read-only original CSVs and private temporary DuckDB databases under ignored `tmp/`. It never opens the learner's persistent database. Packed arrays and streamed comparisons bound memory; a single per-series lag with cutoff-conditional aggregation avoids tripling full history by joining every day to every origin.

The [machine evidence](../data/full_catalog_development_errors_preflight.json) records a successful assistant preflight: **6 rows × 12 columns, all PASS**, and **11 focused fixtures passed** (six valid scenarios and five rejected corruptions). Exact streamed comparisons cover all 58,327,370 indexed history triples, the 30,490-row index map, 6,829,760 saved 14-field forecasts, 5,122,320 scored rows, and 182,940 series diagnostics. All exact field comparisons match; individual and macro RMSSE values also agree with the independent 70-digit Decimal reference within the fixed tolerance. Calendar and fact mappings pass separately.

The full candidate construction report and fingerprint match accepted SQL38, and the overlapping 216-series pilot reproduces accepted SQL36. Original inputs, saved candidates, fixed protocols and historical evidence remain unchanged. The private database and detailed exports were removed after verification. Public outputs contain aggregate reports, status coverage and fingerprints only. **Learner SQL39 screenshot acceptance is now recorded separately below.**

### Independently verified aggregate report

| Origin | Model | Actual units | Predicted units | MAE | Mean error | RMSSE valid | RMSSE undefined | Macro RMSSE |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| DEVELOPMENT_1 | SNAIVE7 | 1175668 | 1064896.00 | 1.199449 | -0.129752 | 30480 | 10 | 0.939616 |
| DEVELOPMENT_1 | WEEKDAY4 | 1175668 | 1093558.00 | 1.067838 | -0.096179 | 30480 | 10 | 0.784853 |
| DEVELOPMENT_2 | SNAIVE7 | 1176067 | 1105772.00 | 1.210618 | -0.082340 | 30490 | 0 | 0.958631 |
| DEVELOPMENT_2 | WEEKDAY4 | 1176067 | 1175668.00 | 1.083339 | -0.000467 | 30490 | 0 | 0.799114 |
| DEVELOPMENT_3 | SNAIVE7 | 1183626 | 1149832.00 | 1.232355 | -0.039584 | 30490 | 0 | 0.975596 |
| DEVELOPMENT_3 | WEEKDAY4 | 1183626 | 1176067.00 | 1.073854 | -0.008854 | 30490 | 0 | 0.799752 |

Each row covers 30,490 series and 853,720 forecast positions. These development aggregates are now also accepted from the learner screenshot; detailed source and scoring audits remain separate assistant evidence. Aggregate status-group MAE and bias, including undefined-scale cases if any, remain in the machine evidence.

In DEVELOPMENT_1, ten series have no positive training quantities by the cutoff. Their RMSSE is undefined for both models; their 280 forecast positions remain in MAE and signed mean error (group MAE 0.639286, mean error −0.639286 for each model). All 30,490 series have defined scales in DEVELOPMENT_2 and DEVELOPMENT_3. This origin-specific coverage is expected from the source history, not a failed check. WEEKDAY4 has lower overall MAE and macro RMSSE in all three accepted development-window summaries, with signed mean error closer to zero. This does not establish improvement for every subgroup or settle final selection.

Ordered report SHA256: `e85b813c4467dd9cee33d18fd5de0f74598fa61fa8c142f5b55830b3aae512ac`.

Run the whole SQL39 file in a new editor under the `retail_merchandising` DBeaver connection. It is read-only and can be repeated; it creates no table and changes no saved forecasts. Full-history validation and scaling do more work than recent-input construction, so allow the script to finish before rerunning. Return all six rows including model, origin and check status; split wide screenshots if necessary.

Final-holdout actual quantities remain excluded, and no final model is selected here. Later subgroup interpretation and the single final evaluation must retain their own evidence and boundaries. No business deployment or inventory benefit is claimed by offline scores.

## Learner acceptance — 29 October 2026

The [learner acceptance record](../data/full_catalog_development_errors_learner_acceptance.json) transcribes all six rows and twelve displayed fields in origin/model order. Counts and actual units remain integers, predicted totals are normalized to two-decimal strings and metric values to six decimals. Restoring a trailing zero such as `-0.08234` → `-0.082340` changes formatting only. The SQL39 runner's canonicalization reproduces ordered report SHA-256 `e85b813c4467dd9cee33d18fd5de0f74598fa61fa8c142f5b55830b3aae512ac`.

Each row shows 30,490 series, 853,720 evaluated positions and PASS. The first origin displays 30,480 valid and ten undefined RMSSE series for both models; later origins display all 30,490 valid. The screenshot confirms these counts, while the `no_positive_training` reason and undefined-group MAE/bias are separate assistant preflight findings. Undefined series remain included in overall MAE and signed error. The 5,122,320 model-specific positions reuse 2,561,160 distinct actual product-store days rather than adding new sales observations.

This accepts the learner's aggregate comparison report, not a direct database read or independent inspection of all history, forecasts or per-series calculations. The three-field indexed history comparison and separate complete mappings/calendar checks, streamed candidate/error/diagnostic comparisons, high-precision RMSSE reference, 11 focused cases, pilot fingerprints, unchanged-source/candidate checks and cleanup remain historical assistant evidence. No product identifiers, detailed vectors or screenshot are saved publicly.

Assistant interpretation: WEEKDAY4 has lower average MAE and macro RMSSE in each full-catalog development window, while all six signed-error values show aggregate underprediction. The result does not establish uniform improvement within every category, store or product, statistical significance, final-holdout performance, final model choice or business benefit. It does not independently test the learner's conceptual understanding.

## Next paired coverage check

[SQL40](../sql/40_compare_full_catalog_paired_improvement.sql) will examine how many full-catalog series improve, tie or worsen under MAE and RMSSE at each development origin. It will use exact error numerators for win/tie decisions, preserve the first window's ten undefined RMSSE exclusions, and retain all 30,490 series for MAE. Mean/median delta is WEEKDAY4 minus SNAIVE7; negative values favor WEEKDAY4. This remains a descriptive development follow-up, with no final-holdout scoring or final selection.

See the [full-catalog paired method](FULL_CATALOG_PAIRED_IMPROVEMENT_VALIDATION.md) for the next step.
