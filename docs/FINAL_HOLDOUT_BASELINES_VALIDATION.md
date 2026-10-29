# Final evaluation of the frozen baseline choice

## Purpose and decision

The learner accepted SQL42's thirty store/window rows: fourteen substantive fields were visually matched, while the clipped PASS column is supported by the user's explicit confirmation. WEEKDAY4 has lower MAE and macro RMSSE in all thirty groups; absolute bias is smaller in twenty and larger in ten. These development results complete the global, paired, department and store comparisons.

[SQL43](../sql/43_evaluate_final_holdout_baselines.sql) evaluates the reserved final 28 days after the baseline decision has been fixed. **WEEKDAY4 is the one global selected baseline; SNAIVE7 is a fixed reference.** This choice is among the two implemented candidates, not a claim of optimality among all forecasting models. Do not change the choice after inspecting the final report, even if the reference wins.

The [protocol](FINAL_HOLDOUT_BASELINE_PROTOCOL.md) was published and read back exactly in [freeze commit 6d270ef](https://github.com/quanchenginitial/retail-merchandising-analytics/commit/6d270efb8c06bc06632f6e3a400066cb11e3d626), before the new final-target calculations. Protocol SHA256: `ad621241d935f9fe14d4ec491a527b332dfe8ff27b3439d11239eaa4f8212669`. This is a decision based on already observed development evidence, frozen before final scoring; it is not a claim that the selection rule preceded development results.

This is a baseline-only milestone. A tree/Python forecasting model has not been implemented. Future model development cannot use this now-exposed period as a fresh final test; it needs untouched evaluation data or explicit exploratory retrospective labelling. Earlier whole-snapshot engineering totals were observed, so the final data were not wholly unseen. Identical assistant verification and learner reproduction retain one fixed evaluation design.

## Fixed report

Training and all prediction inputs end at d1913, **2016-04-24**. Score d1914–d1941, **2016-04-25–2016-05-22**, across all **30,490 product-store series**. Each candidate has **853,720** positions. Keep zero outcomes and all products, stores and departments; do not use April ABC/XYZ filters or choose a different method per subgroup.

Return **two rows × twelve columns**, ordered SNAIVE7 then WEEKDAY4, both with origin FINAL_HOLDOUT:

| Field | Interpretation |
| --- | --- |
| origin / model | Reserved final period and unchanged saved candidate |
| series_count / evaluated_rows | 30,490 product-store series and 853,720 daily positions per model |
| actual_units / predicted_units | Shared observed total and each candidate's saved forecast total |
| mae | Mean absolute error, units per product-store day |
| mean_error | Mean forecast minus actual; negative means underprediction |
| rmsse_valid_series / rmsse_undefined_series | Shared training-scale coverage; exclusions remain in MAE/bias |
| macro_rmsse | Equal-weight mean of individually defined RMSSE values |
| check_status | Data and calculation integrity, independent of which model wins |

No pooled TOTAL or mixture with development scores is introduced. Macro RMSSE supplies the principal cross-series comparison; MAE, signed bias and eligibility provide complementary information. Neither MAE nor RMSSE is an accuracy percentage, and neither establishes an inventory or financial effect. A relative error reduction uses `(SNAIVE7 − WEEKDAY4) / SNAIVE7 × 100`; a zero reference makes that percentage undefined.

## Calculation and time boundaries

Score the persisted candidates, verifying their exact fourteen-field construction first. SNAIVE7 repeats the last seven training days; WEEKDAY4 repeats the four-observation same-weekday means with exact quarter-unit values. The already accepted final forecast totals are 1,141,116 and 1,183,626 units respectively. Those values come from training data; they are not final accuracy results.

Target quantities enter errors only, never saved predictions or scales. Preserve integer quarter-error numerators and squared-error sixteenths, widening before multiplication. MAE/bias include all positions; missing outcomes fail instead of becoming zeros. Display rounding to six decimals happens last.

Find each series' first positive training day and compute the unchanged nonseasonal RMSSE scale only through d1913. Exclude leading pre-sale zeros and the first-positive jump from the denominator, retain later zeros, and use the exact count of retained differences. No positive training observation, fewer than two retained observations or zero scale leaves RMSSE undefined. Keep those series in MAE/bias and status-group reporting; do not substitute epsilon or zero. Macro RMSSE is the mean of valid per-series roots, not a pooled root or official M5 WRMSSE. A completely undefined cohort has NULL macro RMSSE.

The complete SQL42 validated prefix remains intact. A separate final-target projection checks unique keys, exact per-series day coverage, valid units and calendar mappings. Balanced missing/duplicate records must fail even if overall row counts agree. The forecast/actual join must preserve all positions without multiplication. Final-target mutation tests must leave predictions, training scales and development controls unchanged.

## Independent verification

The [validator](../validation/preflight_final_holdout_baselines.py) uses original read-only CSVs and a private temporary database; it never opens the learner's persistent database. A public-freeze commit is required for real-data execution. Source-derived training and final-target arrays remain separate, and the final reference calculates the first-positive scale and error sums independently.

Compare 58,327,370 indexed training triples and complete mapping/calendar projections, all 6,829,760 saved candidate records across fourteen fields, and 853,720 final-target triples plus their date/week mappings. The new scoring streams contain 1,707,440 final error records across twelve fields and 60,980 final model/series diagnostics across sixteen fields, with status groups and the literal report. Integer fields, keys and NULL statuses match exactly; roots and means use Decimal precision 70 with the inherited absolute 1e-12 plus relative 1e-13 tolerance.

The same guarded execution preserves development diagnostic, pair, department and store fingerprints and literal SQL39/40/41/42 reports, as well as saved-candidate and overlapping pilot controls. This does not claim a new direct export of 5,122,320 development error rows. Keep sum deviations separate from per-series/mean deviations. Sources, relevant training/target projections, saved forecasts and historical dependencies must be unchanged after execution, and private exports/databases removed.

Focused fixtures cover hand calculations, fractional forecasts/zeros, target-only mutations and a selected-model loss that still passes integrity checks, undefined training scales, malformed/duplicate/missing targets and corrupted saved predictions. Public evidence contains aggregate results and fingerprints only, not individual product identifiers, target records or model errors.

The executed [machine record](../data/final_holdout_baselines_preflight.json) records **two rows × twelve columns, both PASS**, with **7 focused fixture families and 14 executed subcases passed**. Final targets, all 1,707,440 final error rows and 60,980 diagnostics match the independent reference under the exact/numeric contracts. The selected-model-loss fixture still returns PASS, confirming that integrity does not depend on performance ranking.

Historical training, complete mappings/calendar and saved candidates also passed their full comparisons. Literal SQL39/40/41/42 development reports and their diagnostic/pair/group fingerprints reproduce unchanged. Sources, relevant training/target projections, candidates and historical dependencies remain unchanged; temporary private files/databases were removed. **The learner subsequently accepted SQL43 on 2026-10-30**, as recorded separately below; the historical preflight record remains unchanged.

### Verified final-period report

The prepublished decision remains WEEKDAY4 selected and SNAIVE7 reference. The assistant preflight report below was reproduced in the learner's accepted screenshot on 2026-10-30; the final results do not change the frozen selection.

| Model | Series | Positions | Actual units | Predicted units | MAE | Mean error | Valid RMSSE | Undefined RMSSE | Macro RMSSE | Status |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| SNAIVE7 | 30490 | 853720 | 1231764 | 1141116.00 | 1.243972 | -0.106180 | 30490 | 0 | 0.997242 | PASS |
| WEEKDAY4 | 30490 | 853720 | 1231764 | 1183626.00 | 1.103654 | -0.056386 | 30490 | 0 | 0.828159 | PASS |

Both rows have origin FINAL_HOLDOUT. Ordered report SHA256: `3b4a0f10f18d5abf661a140abd3dbe7437301cefe87fc8dfa50e3da895a7fd2a`.

## Learner acceptance and interpretation — 2026-10-30

The learner supplied a DBeaver screenshot showing **both FINAL_HOLDOUT rows and all twelve field positions, including both complete PASS values**. All twenty-four values match the assistant preflight after removing displayed thousands separators, preserving prediction totals to two decimal places and restoring metrics to six decimal places. The [learner acceptance record](../data/final_holdout_baselines_learner_acceptance.json) reproduces the ordered report SHA256 `3b4a0f10f18d5abf661a140abd3dbe7437301cefe87fc8dfa50e3da895a7fd2a` with zero field mismatches.

This is screenshot-based acceptance of the displayed aggregate report. The assistant did not access the learner's database or rerun forecasts/final-target calculations for this acceptance. Complete private source, saved-candidate, error-row, diagnostic and fixture comparisons remain the separate historical preflight evidence described above. The frozen SQL43, protocol and preflight files remain unchanged; no screenshot, individual product identifiers, detailed errors or quantity vectors are published.

The selected WEEKDAY4 baseline has lower MAE (**1.103654 versus 1.243972**) and macro RMSSE (**0.828159 versus 0.997242**) than the fixed SNAIVE7 reference in this final period. Relative reductions are approximately **11.28% for MAE** and **16.96% for macro RMSSE**, calculated from the displayed six-decimal metrics; the retained evidence does not store the unrounded independent aggregate values needed to claim more precise percentages. These are error reductions, not accuracy percentages.

Both candidates underpredict in aggregate. WEEKDAY4's mean error of **-0.056386** is closer to zero than SNAIVE7's **-0.106180**. Actual minus predicted totals are exactly **48,138 units** and **90,648 units**, respectively, using the accepted aggregate totals. This does not identify individual stockouts or lost sales, and aggregate improvement does not establish that every series improved.

**WEEKDAY4 remains the one global selected baseline, as frozen before final evaluation.** This result confirms its advantage over the fixed reference for this one reserved period; it does not establish statistical significance, guarantee later performance or justify tuning on these outcomes. Future tree-model work needs untouched evaluation data or an explicitly exploratory retrospective evaluation: the exposed final period cannot become a fresh test again. Learner reproduction of the baseline final evaluation is complete; Power BI, price/anomaly work, behaviour analysis, tree modelling and the overall portfolio project remain separate work.
