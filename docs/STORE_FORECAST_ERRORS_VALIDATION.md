# Store development forecast error comparison

## Purpose and fixed scope

SQL41's department report is learner accepted. WEEKDAY4 has lower MAE and macro RMSSE in every department/window, while absolute signed bias improves in eleven and worsens in ten. [SQL42](../sql/42_compare_store_forecast_errors.sql) checks the corresponding store-level pattern using all ten stores and all 3,049 products at every store. Department findings do not determine store findings.

The [fixed protocol](STORE_FORECAST_ERRORS_PROTOCOL.md) precedes inspection of these new summaries. The same two baseline formulas, complete retrospective roster and three development windows are retained. No favorable store, sales-positive subset, ABC/XYZ label or RMSSE-eligibility filter changes the scope. State codes provide context only; no state-level or cross-origin pooling is introduced.

## Thirty rows and fifteen fields

Return **30 rows × 15 columns**, ordered by development origin and store_id. Each row pairs the two methods for one store over a 28-day window. Every store has 3,049 product-store series and 85,372 scored positions per model. The windows remain 2016-02-01–2016-02-28, 2016-02-29–2016-03-27 and 2016-03-28–2016-04-24. There is no TOTAL row.

| Fields | Meaning |
| --- | --- |
| origin / store_id / state_id | Development window, source store identifier and its source state code |
| series_count | All 3,049 product-store series at the store |
| rmsse_valid_series / rmsse_undefined_series | Shared RMSSE eligibility counts for both methods |
| snaive7_mae / weekday4_mae / mae_delta | Mean absolute error per product-store day and WEEKDAY4 minus SNAIVE7 |
| snaive7_mean_error / weekday4_mean_error | Mean forecast minus actual for each method |
| snaive7_macro_rmsse / weekday4_macro_rmsse / rmsse_delta | Mean valid-series RMSSE and paired difference |
| check_status | PASS when input, attribution, grouping and reconciliation controls pass |

Negative error **deltas** favor WEEKDAY4. Negative **mean_error** indicates underprediction, not automatically better performance. Near-zero bias can result from opposing errors canceling. MAE/bias are units per product-store day, not whole-store daily totals; neither delta nor RMSSE is an accuracy percentage.

All series remain in MAE and bias. RMSSE uses each origin's unchanged positive training-scale cohort. If a store has no valid scales, preserve its MAE/bias and explicit exclusions, with NULL for both macro RMSSE values and their delta. At the first origin, valid/undefined counts across stores must sum to 30,480/10; later windows sum to 30,490/0. The store allocation is determined by original metadata and scale diagnostics.

## Assignment and metric controls

SQL42 retains the validated SQL41 CTE prefix. Each existing diagnostic receives exactly one source-derived state through its store identifier. A store must have one consistent state across all original product records. Missing, null, duplicate or inconsistent mappings fail, and an empty map must raise a guarded error instead of returning an empty report. All original diagnostic keys, quantities, statuses and predictions are preserved.

MAE and mean error retain exact quarter-error integer sums through aggregation. MAE delta uses the unrounded numerator difference. Macro RMSSE is the equal-weight mean of valid per-series roots. RMSSE delta averages the existing stable paired root differences and separately reconciles to the difference of unrounded store macros. The independent reference subtracts 70-digit Decimal roots directly. Output is explicitly six-decimal numeric data before a client may hide trailing zeros.

Store integer totals reconstruct SQL39 exactly. Reconstruct MAE/bias using **all-series counts**, and RMSSE/delta using **valid-series counts**. The base store counts are equal here, but RMSSE eligibility may differ, so equal averaging of displayed store means is not the general reconciliation rule. Keep undefined groups NULL and reconcile before rounding. Literal SQL39/40/41 results and earlier diagnostic/pair fingerprints must remain unchanged.

## Independent preflight

The [runner](../validation/preflight_store_forecast_errors.py) reads original CSVs and uses a private temporary DuckDB database; it never opens the learner's persistent database. Complete source checks include 58,327,370 indexed history triples, the separate complete roster/department/calendar maps and fact date/week mappings, and all 6,829,760 saved forecasts across fourteen fields. Store/state assignment is independently derived from the original metadata across products.

One guarded execution exports the literal SQL42 report, every required store-assigned diagnostic, store model totals and unrounded controls, preserved department/pair streams and literal SQL39/40/41 reports. Exact key, integer and NULL/status fields are checked directly; numeric roots, sums, means and deltas use the independent Decimal reference under declared tolerances. Root-sum deviations are recorded separately from mean-metric and per-series deviations. No new direct export/comparison of the unchanged 5,122,320 daily-error rows is claimed.

The single assigned stream contains 182,940 rows and eighteen fields: the original sixteen model-diagnostic fields plus the observed department and state. Seventeen fields are exact and RMSSE is checked numerically. Projecting the observed department fields preserves SQL41's fingerprint without substituting reference metadata. The 60 store/model totals have fourteen fields (twelve exact, then RMSSE sum and macro RMSSE); 30 store-pair controls have six fields (origin, store, state, total/valid counts and unrounded mean paired RMSSE difference).

Targeted fixtures cover the new store/state attribution and store-level eligibility, bias and rounding boundaries. Sources, candidates, relevant inputs and historical evidence remain unchanged; private details/databases are removed after verification. Public evidence contains store/state aggregates and fingerprints, not individual product identifiers or diagnostics.

The executed [machine evidence](../data/store_forecast_errors_preflight.json) records **30 rows × 15 columns, all PASS**, and **8 focused fixtures passed** (three valid cases and five correctly rejected invalid cases). All 182,940 assigned diagnostics, 60 internal store/model totals and 30 store-pair controls match the independent source reference under the declared exact/numeric comparison rules. Store integer totals and the distinct all-series/valid-series weighted means reconcile to the accepted global reports.

All 58,327,370 history triples, complete source mappings/calendar and 6,829,760 saved candidates passed their checks. The literal SQL39/40/41 reports, earlier department/base diagnostic and pair fingerprints, SQL38 candidate/report controls and overlapping pilot evidence reproduce unchanged. Sources, saved candidates, relevant inputs and historical dependencies remain unchanged; private detail exports and databases were removed. **Learner SQL42 output was accepted on 29 October 2026:** the screenshot verifies all thirty rows across fourteen substantive fields, and the learner separately confirms all thirty PASS statuses because the final column is clipped. See the acceptance section below.

### Selected fields from the verified report

The machine evidence retains all fifteen fields. This table highlights store differences and bias; negative deltas favor WEEKDAY4, while negative bias means underprediction.

| Origin | Store | State | Series | Undefined RMSSE | MAE delta | SNAIVE7 bias | WEEKDAY4 bias | RMSSE delta |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| DEVELOPMENT_1 | CA_1 | CA | 3049 | 1 | -0.148357 | -0.099447 | -0.055627 | -0.152611 |
| DEVELOPMENT_1 | CA_2 | CA | 3049 | 2 | -0.166272 | -0.028920 | -0.030057 | -0.171436 |
| DEVELOPMENT_1 | CA_3 | CA | 3049 | 3 | -0.224886 | -0.081982 | -0.097280 | -0.159004 |
| DEVELOPMENT_1 | CA_4 | CA | 3049 | 1 | -0.106774 | 0.009488 | -0.005880 | -0.161308 |
| DEVELOPMENT_1 | TX_1 | TX | 3049 | 0 | -0.072858 | -0.138664 | -0.074989 | -0.135355 |
| DEVELOPMENT_1 | TX_2 | TX | 3049 | 0 | -0.115143 | -0.189711 | -0.143712 | -0.146657 |
| DEVELOPMENT_1 | TX_3 | TX | 3049 | 0 | -0.107764 | -0.123190 | -0.093942 | -0.147160 |
| DEVELOPMENT_1 | WI_1 | WI | 3049 | 1 | -0.145949 | -0.041641 | -0.057068 | -0.169239 |
| DEVELOPMENT_1 | WI_2 | WI | 3049 | 2 | -0.131677 | -0.384798 | -0.272993 | -0.156441 |
| DEVELOPMENT_1 | WI_3 | WI | 3049 | 0 | -0.096437 | -0.218655 | -0.130242 | -0.148445 |
| DEVELOPMENT_2 | CA_1 | CA | 3049 | 0 | -0.151144 | -0.066275 | -0.027972 | -0.153520 |
| DEVELOPMENT_2 | CA_2 | CA | 3049 | 0 | -0.156404 | 0.020510 | 0.028112 | -0.177001 |
| DEVELOPMENT_2 | CA_3 | CA | 3049 | 0 | -0.223727 | -0.057829 | -0.017031 | -0.160514 |
| DEVELOPMENT_2 | CA_4 | CA | 3049 | 0 | -0.104683 | -0.046713 | -0.040927 | -0.169085 |
| DEVELOPMENT_2 | TX_1 | TX | 3049 | 0 | -0.091072 | -0.096402 | -0.023099 | -0.144584 |
| DEVELOPMENT_2 | TX_2 | TX | 3049 | 0 | -0.126312 | -0.043059 | 0.017711 | -0.153572 |
| DEVELOPMENT_2 | TX_3 | TX | 3049 | 0 | -0.097315 | -0.102469 | 0.020253 | -0.155814 |
| DEVELOPMENT_2 | WI_1 | WI | 3049 | 0 | -0.139935 | -0.045987 | -0.003034 | -0.173446 |
| DEVELOPMENT_2 | WI_2 | WI | 3049 | 0 | -0.100314 | -0.240266 | 0.022900 | -0.158877 |
| DEVELOPMENT_2 | WI_3 | WI | 3049 | 0 | -0.081889 | -0.144907 | 0.018414 | -0.148750 |
| DEVELOPMENT_3 | CA_1 | CA | 3049 | 0 | -0.188674 | -0.024305 | -0.031732 | -0.172535 |
| DEVELOPMENT_3 | CA_2 | CA | 3049 | 0 | -0.207152 | 0.002589 | -0.113972 | -0.192030 |
| DEVELOPMENT_3 | CA_3 | CA | 3049 | 0 | -0.220101 | 0.035609 | 0.047006 | -0.166988 |
| DEVELOPMENT_3 | CA_4 | CA | 3049 | 0 | -0.125527 | -0.003338 | -0.015661 | -0.186035 |
| DEVELOPMENT_3 | TX_1 | TX | 3049 | 0 | -0.123794 | -0.001827 | -0.001335 | -0.175138 |
| DEVELOPMENT_3 | TX_2 | TX | 3049 | 0 | -0.160070 | 0.068805 | 0.071288 | -0.176169 |
| DEVELOPMENT_3 | TX_3 | TX | 3049 | 0 | -0.145229 | -0.006770 | 0.018765 | -0.172189 |
| DEVELOPMENT_3 | WI_1 | WI | 3049 | 0 | -0.180932 | -0.012897 | -0.009968 | -0.196863 |
| DEVELOPMENT_3 | WI_2 | WI | 3049 | 0 | -0.121363 | -0.310547 | -0.038561 | -0.161626 |
| DEVELOPMENT_3 | WI_3 | WI | 3049 | 0 | -0.112168 | -0.143162 | -0.014372 | -0.158867 |

These historical assistant preflight values now also match the learner's visible numeric report. Status acceptance uses the learner's explicit all-PASS confirmation; complete status text is not visible in the screenshot.

Ordered report SHA256: `e78a15f0d2dcf329c30346a3583b3198b3fe98e52751d9aeab57d269cfbab156`.

## Learner acceptance — 29 October 2026

The [learner acceptance record](../data/store_forecast_errors_learner_acceptance.json) records two distinct evidence sources. The assistant inspected the supplied screenshot and independently transcribed all **30 rows × 14 substantive fields**: three identifier/context fields, three counts and eight metric/delta fields per row. All **240 metric values and 90 count values**, identifiers, source state codes and ordering match the frozen preflight after removing thousands separators and restoring six-decimal trailing zeros.

The rightmost **check_status column is clipped**. The learner explicitly confirms that all thirty rows are PASS; those statuses are accepted from that statement, not inferred by completing partially visible text. The complete fifteen-field report fingerprint therefore combines screenshot-verified substantive values with learner-attested statuses. It must not be described as fifteen fully visible screenshot columns.

The canonical complete report SHA256 remains `e78a15f0d2dcf329c30346a3583b3198b3fe98e52751d9aeab57d269cfbab156`. The separate fingerprint for the fourteen visible fields, excluding check_status, is `5b678503c6248abb3c1516c52254e7e1c6356301ace4b8a68efd5bdecd218672`. The historical preflight record is unchanged.

This accepts the displayed store/window aggregates, paired differences and scale-eligibility counts. The screenshot does not independently prove the underlying source reconciliation, all diagnostic records, numeric controls or fixture outcomes; those remain the assistant's separate preflight evidence above. The learner database was not opened, and no screenshot, product identifier or individual diagnostic was copied into the repository. Conceptual understanding, final-holdout accuracy and final selection were not independently established by this acceptance.

## Repeat execution and interpretation

Run the complete SQL42 file in a new editor under the `retail_merchandising` DBeaver connection. It is read-only, creates no table and can be repeated. Full-history controls remain part of the query; wait for completion before rerunning. For any future verification, retain all 30 rows and fifteen fields, splitting screenshots while keeping origin/store identifiers readable; the current acceptance explicitly records the clipped status column and separate learner confirmation.

Compare methods within a store/window. Differences in unit volumes and histories mean raw MAE alone is not a store-performance ranking. A lower store mean does not establish improvement for every product or department or supply a within-store win percentage. State labels do not establish geographic causes. SQL42 does not read or score final-holdout actual quantities; earlier engineering totals do not make this a wholly unseen period. No significance, final model selection, bias correction, inventory saving or deployed business effect is claimed.
