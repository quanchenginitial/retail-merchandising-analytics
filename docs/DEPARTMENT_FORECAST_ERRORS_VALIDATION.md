# Department development forecast error comparison

## Purpose and scope

SQL40's full-catalog paired report is learner accepted. WEEKDAY4 improves a majority of series in each metric/window, while many ties and SNAIVE7 wins remain. [SQL41](../sql/41_compare_department_forecast_errors.sql) checks whether each department shares the aggregate improvement and whether its forecasts tend to be too high or too low.

This is a descriptive follow-up using all seven source-defined departments, all ten stores and the same 30,490 product-store series. The [fixed protocol](DEPARTMENT_FORECAST_ERRORS_PROTOCOL.md) is recorded before inspecting department results. No favorable subgroup is selected, and no final model or department-specific forecasting policy is chosen. Department labels are anonymous codes; do not attach invented real-world product meanings to them. On 29 October 2026 (Australia/Sydney), the learner accepted all 21 report rows and fourteen field positions; the canonical report fingerprint matches historical assistant preflight.

## One row per department and development window

Return **21 rows × 14 columns**, ordered by development origin and department. Every row pairs SNAIVE7 and WEEKDAY4 for one department over the same 28 days. The three windows remain 2016-02-01–2016-02-28, 2016-02-29–2016-03-27 and 2016-03-28–2016-04-24. Each origin contains all seven departments; there is no TOTAL row or pooling across origins.

| Fields | Interpretation |
| --- | --- |
| origin / dept_id | Development window and source department code |
| series_count | Product-store series in this department; not unique products |
| rmsse_valid_series / rmsse_undefined_series | Shared eligible/undefined RMSSE counts for both methods |
| snaive7_mae / weekday4_mae / mae_delta | Each model's mean absolute error and WEEKDAY4 minus SNAIVE7 |
| snaive7_mean_error / weekday4_mean_error | Mean forecast minus actual for each method |
| snaive7_macro_rmsse / weekday4_macro_rmsse / rmsse_delta | Each model's mean valid-series RMSSE and paired difference |
| check_status | PASS when source, grouping and metric checks succeed |

Negative **mae_delta or rmsse_delta** favors WEEKDAY4. A negative **mean_error** means underprediction; it does not by itself mean better performance. Near-zero bias can contain offsetting over- and underpredictions. MAE/bias are units per product-store day; RMSSE is dimensionless. None is a forecast-accuracy percentage.

All series participate in MAE and bias. RMSSE uses the common positive training-scale cohort, with the unchanged first-positive-day definition. If a department has no valid scales, keep both macro RMSSE values and their delta NULL while retaining MAE/bias. Across departments, first-window coverage must sum to 30,480 valid plus ten undefined; later windows each have all 30,490 valid. Department allocation is determined by source metadata and the actual scale diagnostics.

## How the grouping is checked

SQL41 keeps SQL40's validated CTE prefix unchanged. It assigns each existing model diagnostic to exactly one department through the source-validated product dimension. The assignment must retain all 182,940 model diagnostics, their keys, quantities and eligibility; absent, duplicate, null or inconsistent mappings fail. The result contains 42 department/model/origin totals and 21 paired department rows.

MAE and signed error retain exact integer quarter sums through final rounding. MAE delta uses the unrounded numerator difference. Macro RMSSE averages the defined individual series roots equally. RMSSE delta averages the stable existing paired root differences and is separately reconciled with the difference of unrounded department macros. Independent high-precision calculation directly subtracts Decimal roots. Display six decimals only after aggregation.

Department totals reconcile to the accepted SQL39 global totals: use **all-series counts** for MAE/bias and **valid-series counts** for macro RMSSE. Equal averaging of seven department means is incorrect when department sizes differ. Do not substitute zero for an undefined mean or reconcile using rounded display values. The accepted SQL40 global paired report and diagnostic/pair fingerprints must also reproduce unchanged.

## Independent verification

The [runner](../validation/preflight_department_forecast_errors.py) uses original CSVs read-only and a private temporary database, never the learner's persistent database. Source checks cover all 58,327,370 indexed history triples, the separate complete roster map/calendar and fact date/week mappings, and all 6,829,760 saved forecasts across fourteen fields. Department assignment is independently derived from original product metadata across stores.

One guarded calculation exports the literal SQL41 report, all 182,940 department-assigned diagnostics (sixteen exact fields plus RMSSE), 91,470 unchanged paired rows, the 42 internal department/model/origin totals and full-precision controls, plus the literal SQL39/40 reports. Integer keys, sums and coverage are exact; floating roots, means and deltas use independent 70-digit Decimal references under the declared tolerances. The unchanged 5,122,320 daily error rows are not exported and compared anew; their earlier validation remains recorded.

The 42 internal model totals have thirteen fields: eleven exact origin/department/model identifiers, counts and integer quantity/error sums, followed by RMSSE sum and macro RMSSE. Both numeric fields stay NULL for a zero-valid group. The 21 department-pair controls have five fields: origin, department, series count, valid count and unrounded mean paired RMSSE difference. These internal controls support denominator-specific reconciliation; the learner report remains 21 rows and fourteen columns.

Focused fixtures cover new assignment, weighting, NULL-scale, bias and rounding behavior. Sources, candidates, inputs and historical evidence must remain unchanged, and private details/databases are removed after the run. Public outputs contain department aggregates and fingerprints, not individual product identifiers or model diagnostics.

The executed [machine evidence](../data/department_forecast_errors_preflight.json) records **21 rows × 14 columns, all PASS**, and **8 focused fixtures passed**. All 182,940 assigned diagnostics, 91,470 preserved pairs, 42 internal model totals and 21 department-pair controls match the independent source reference under the declared exact/numeric comparison rules. Department integer totals and the distinct all-series/valid-series weighted means reconcile to the accepted global reports.

Original history, complete mappings/calendar and saved candidates also passed their full checks. SQL38/39/40 reports, base diagnostic and pair fingerprints, and overlapping pilot evidence reproduce unchanged. Sources, saved candidates, relevant inputs and historical dependencies remain unchanged; private detail exports and databases were removed. **Learner SQL41 screenshot acceptance is now recorded separately below.**

### Selected fields from the verified report

The machine evidence retains all fourteen fields. This table highlights departmental differences and bias; negative deltas favor WEEKDAY4, while negative bias means underprediction.

| Origin | Department | Series | Undefined RMSSE | MAE delta | SNAIVE7 bias | WEEKDAY4 bias | RMSSE delta |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| DEVELOPMENT_1 | FOODS_1 | 2160 | 0 | -0.159979 | -0.008399 | 0.046081 | -0.162523 |
| DEVELOPMENT_1 | FOODS_2 | 3980 | 0 | -0.133296 | -0.170002 | -0.002028 | -0.154338 |
| DEVELOPMENT_1 | FOODS_3 | 8230 | 2 | -0.167885 | -0.333288 | -0.234278 | -0.137125 |
| DEVELOPMENT_1 | HOBBIES_1 | 4160 | 0 | -0.132568 | 0.011976 | -0.024588 | -0.168019 |
| DEVELOPMENT_1 | HOBBIES_2 | 1490 | 0 | -0.042414 | 0.010618 | -0.025551 | -0.170074 |
| DEVELOPMENT_1 | HOUSEHOLD_1 | 5320 | 8 | -0.179437 | -0.065199 | -0.133882 | -0.167950 |
| DEVELOPMENT_1 | HOUSEHOLD_2 | 5150 | 0 | -0.036075 | -0.046061 | -0.047233 | -0.151280 |
| DEVELOPMENT_2 | FOODS_1 | 2160 | 0 | -0.095271 | -0.130456 | -0.034755 | -0.129503 |
| DEVELOPMENT_2 | FOODS_2 | 3980 | 0 | -0.114299 | -0.239869 | -0.017857 | -0.145425 |
| DEVELOPMENT_2 | FOODS_3 | 8230 | 0 | -0.186077 | -0.178233 | -0.026805 | -0.142559 |
| DEVELOPMENT_2 | HOBBIES_1 | 4160 | 0 | -0.112384 | 0.012783 | 0.028245 | -0.180454 |
| DEVELOPMENT_2 | HOBBIES_2 | 1490 | 0 | -0.016131 | -0.001918 | 0.006352 | -0.155154 |
| DEVELOPMENT_2 | HOUSEHOLD_1 | 5320 | 0 | -0.180233 | 0.015454 | 0.042602 | -0.179506 |
| DEVELOPMENT_2 | HOUSEHOLD_2 | 5150 | 0 | -0.046262 | 0.011699 | -0.000215 | -0.173793 |
| DEVELOPMENT_3 | FOODS_1 | 2160 | 0 | -0.341377 | 0.360301 | 0.124223 | -0.235380 |
| DEVELOPMENT_3 | FOODS_2 | 3980 | 0 | -0.168624 | -0.231954 | -0.034727 | -0.180628 |
| DEVELOPMENT_3 | FOODS_3 | 8230 | 0 | -0.232954 | -0.020023 | -0.015857 | -0.162146 |
| DEVELOPMENT_3 | HOBBIES_1 | 4160 | 0 | -0.102039 | -0.069059 | -0.036581 | -0.173284 |
| DEVELOPMENT_3 | HOBBIES_2 | 1490 | 0 | -0.028559 | -0.007430 | -0.013854 | -0.169378 |
| DEVELOPMENT_3 | HOUSEHOLD_1 | 5320 | 0 | -0.149047 | -0.099288 | 0.001289 | -0.163381 |
| DEVELOPMENT_3 | HOUSEHOLD_2 | 5150 | 0 | -0.047965 | -0.013717 | -0.020118 | -0.185879 |

These development aggregates are also accepted from the learner screenshot; detailed source and assigned-diagnostic comparisons remain separate assistant evidence.

WEEKDAY4 has lower MAE and macro RMSSE in all 21 department/window comparisons. Its absolute mean signed error is closer to zero in eleven comparisons and farther from zero in ten; lower average error magnitude does not imply uniformly improved bias. For example, DEVELOPMENT_1 HOUSEHOLD_1 MAE falls from 1.326101 to 1.146664, while mean error changes from −0.065199 to −0.133882, indicating greater average underprediction. These descriptive results support examining bias alongside error magnitude, not applying an untested bias correction or selecting a different method retrospectively for each department.

The first-window ten undefined RMSSE scales are assigned to FOODS_3 (two) and HOUSEHOLD_1 (eight); every other department/window has zero exclusions. These are sequence counts, not claims about missing department data or inventory availability.

Ordered report SHA256: `7f5af82dce08cd2dc28c5bfdac8da4a35a3e804c1543abb5503ac102fd303a4c`.

## Learner action and interpretation

Execute the full SQL41 file in a new editor under the `retail_merchandising` DBeaver connection. It is read-only and creates no table. Full-history checks remain part of this query, so wait for completion before repeating it. Return all 21 rows and fourteen columns; split screenshots if necessary while keeping each row identifiable by origin and department.

Compare methods within a department/window. Departments differ in unit volumes, so a larger absolute MAE alone does not rank forecasting quality across departments. A favorable department average does not prove that every store or product improves, nor does it give a department-specific win percentage. Store comparisons and subsequent selection remain separate work. SQL41 does not read or score final-holdout actual quantities. Earlier full-snapshot engineering audits included observed-day totals; this is an analytical-step boundary, not a claim that the period is wholly unseen. No significance, causality or deployed business benefit is claimed.

## Learner acceptance — 29 October 2026

The [learner acceptance record](../data/department_forecast_errors_learner_acceptance.json) transcribes all 21 rows and fourteen field positions after visual inspection of the supplied screenshot. Counts have their thousands separators removed and metrics/deltas are normalized to six-decimal strings, restoring omitted trailing zeros. Applying the SQL41 column contract, `six(Decimal)` formatting and canonical JSON hash reproduces `7f5af82dce08cd2dc28c5bfdac8da4a35a3e804c1543abb5503ac102fd303a4c`.

The screenshot's final column header is truncated. Its position is identified as `check_status` from the accepted SQL41 fourteen-column contract, and all 21 PASS values are visible; this is not a claim that the complete final header text appears in the image. Origin/department order, all counts and all eight metric fields per row match historical preflight. The visible first-window undefined allocation is FOODS_3 two and HOUSEHOLD_1 eight; other department/windows show zero. Counts are product-store series, not unique products. The underlying no-positive-training reason remains prior source-verification evidence.

This accepts the displayed aggregate results, not a direct learner-database read or an independent inspection of every private calculation. Source history and mappings, assigned diagnostics, preserved pairs, internal department totals and controls, high-precision reconciliation, eight focused cases, immutable dependencies and cleanup remain separate assistant preflight evidence. No new direct daily-error export is attributed to this step. Product identifiers, individual diagnostic rows, vectors and screenshot are not published.

Assistant interpretation remains unchanged: WEEKDAY4 has lower MAE and macro RMSSE in all 21 department/windows, but absolute mean signed error is closer to zero in eleven and farther in ten. A department average does not prove every product/store improves or provide a department win percentage. No final-holdout score, significance, final model choice, causal mechanism or business benefit is established. Conceptual understanding has not been independently tested.

## Next store comparison

[SQL42](../sql/42_compare_store_forecast_errors.sql) will compare all ten stores across the same three development windows, retaining every one of the 3,049 products at each store. The 30-row, fifteen-column report will show both candidates' metrics, differences and eligibility with source state identifiers as context. Follow the [store method](STORE_FORECAST_ERRORS_VALIDATION.md); no store findings or undefined-scale allocation are inferred from department averages. Final-holdout actuals and final selection remain excluded.
