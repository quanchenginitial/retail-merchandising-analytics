# Stage 5: accepted baseline forecasting findings

Accepted on **30 October 2026**. The learner reproduced the two-baseline final report with all **two rows × twelve fields** visible and both statuses PASS. The [acceptance record](../data/final_holdout_baselines_learner_acceptance.json) matches the independent [assistant preflight](../data/final_holdout_baselines_preflight.json); full private data comparisons remain assistant evidence, separate from screenshot acceptance.

## Scope and frozen decision

The work progressed from a 216-series pilot to all **30,490 product-store series**, retaining zeros and both unchanged methods. Three 28-day development windows covered **1 February–28 February**, **29 February–27 March** and **28 March–24 April 2016**. Full-catalog, paired-series, department and store comparisons informed the choice; aggregate gains did not imply every series improved. See the [development](FULL_CATALOG_DEVELOPMENT_ERRORS_VALIDATION.md), [paired](FULL_CATALOG_PAIRED_IMPROVEMENT_VALIDATION.md), [department](DEPARTMENT_FORECAST_ERRORS_VALIDATION.md) and [store](STORE_FORECAST_ERRORS_VALIDATION.md) records.

**WEEKDAY4 was selected globally among the two implemented baselines before final scoring; SNAIVE7 remains the fixed reference.** The [protocol](FINAL_HOLDOUT_BASELINE_PROTOCOL.md) was [published before final-target access](https://github.com/quanchenginitial/retail-merchandising-analytics/commit/6d270efb8c06bc06632f6e3a400066cb11e3d626). Final training and RMSSE scales end at **24 April 2016 (d1913)**. The fixed final evaluation covers **25 April–22 May 2016 (d1914–d1941)**, with **853,720 daily positions per model**. Earlier engineering inspected whole-snapshot totals, so this is not a claim that the raw final data were wholly unseen.

## Accepted final report

| Origin | Model | Series | Positions | Actual units | Predicted units | MAE | Mean error | Valid RMSSE | Undefined RMSSE | Macro RMSSE | Status |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| FINAL_HOLDOUT | SNAIVE7 | 30490 | 853720 | 1231764 | 1141116.00 | 1.243972 | -0.106180 | 30490 | 0 | 0.997242 | PASS |
| FINAL_HOLDOUT | WEEKDAY4 | 30490 | 853720 | 1231764 | 1183626.00 | 1.103654 | -0.056386 | 30490 | 0 | 0.828159 | PASS |

WEEKDAY4 reduces MAE by approximately **11.28%** and macro RMSSE by approximately **16.96%** relative to SNAIVE7. These estimates use the displayed six-decimal metrics and `(reference − selected) / reference × 100`; they are error reductions, not accuracy percentages. Macro RMSSE weights defined series equally and is not official M5 WRMSSE. PASS verifies integrity, independently of which method wins.

Both methods underpredict in aggregate. WEEKDAY4's total is **48,138 units** below the actual total, versus **90,648 units** for SNAIVE7; its absolute mean signed error is also smaller. These are exact differences of accepted aggregate totals, not estimates of stockouts or lost sales. One final period does not establish statistical significance, improvement for every product or date, future performance, inventory savings or deployed business benefit.

## Milestone and next step

The **Stage 5 baseline milestone is accepted**: time boundaries, two reproducible baselines, development comparisons and one frozen final evaluation are complete. A tree model remains unimplemented. Future model development needs untouched evaluation data for a new final test, or must explicitly label reuse as exploratory retrospective analysis; this exposed period cannot become a fresh test again. The overall portfolio, Power BI and behaviour modules remain incomplete.

The separate [descriptive price-association milestone](STAGE06_PRICE_ASSOCIATION_FINDINGS.md) remains accepted through SQL49. SQL50–53 screening and illustrative-history outputs are also learner-accepted as of 2 November 2026. SQL53 matches all 432 visible values and 36 PASS statuses; see the [aggregate acceptance](../data/anomaly_case_histories_learner_acceptance.json) and [anomaly review findings and investigation framework](STAGE06_ANOMALY_REVIEW_FINDINGS.md). Actual case trajectories remain private. This closes the implemented Stage 6 descriptive, screening and illustrative-review milestone; external operational causes and detection performance remain unassessed. Next is independent Retailrocket source intake, not completed behaviour analysis. The accepted forecast choice and all numerical findings are unchanged; the overall portfolio remains incomplete. See [the current step](FIRST_STEP_ZH.md).
