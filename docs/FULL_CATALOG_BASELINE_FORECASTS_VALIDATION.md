# Full-catalog baseline forecast construction

## Purpose and decision boundary

The pilot now has accepted construction, development error and paired-coverage results. WEEKDAY4 is the preferred development baseline in that pilot, because average MAE and macro RMSSE are lower in all three windows and the paired mean/median differences are negative. Its MAE win coverage is not universal: the second window has exactly 108 improvements among 216 series. Preserve SNAIVE7 as the reference candidate.

[SQL38](../sql/38_build_full_catalog_baseline_forecasts.sql) now builds both unchanged formulas over the full released catalog. This is an expansion of scope and forecast construction, not another accuracy comparison or final selection. The [fixed protocol](FULL_CATALOG_BASELINE_FORECASTS_PROTOCOL.md) records the broader roster, temporal bounds, table schema and output contract before the new construction results are inspected. The earlier [evaluation plan](EVALUATION_PLAN.md) remains unchanged. On 29 October 2026 (Australia/Sydney), the learner accepted all eight rows and twelve displayed fields; the canonical report fingerprint matches the historical assistant preflight exactly.

## From a pilot to all item/store combinations

The population is all **3,049 products × 10 stores = 30,490 product-store series**, across seven departments, three categories and three states. A product sold at ten stores contributes ten distinct series. All combinations, including zero histories, remain included. The roster is not filtered by pilot performance, April ABC/XYZ labels or forecast outcomes. It is a retrospective released-catalog benchmark, not proof that every item was actively ranged at every historical date.

The build validates the product and store dimensions, raw metadata mappings, complete unique item/store combinations and calendar mapping. This full-roster guard adds a scope check before the broader calculation. It does not assume that a few global row counts alone establish complete pair coverage.

The four origins and 28-day horizons are the same as the pilot. Each formula requires no more than the final 28 training days. Four consecutive, nonoverlapping source windows cover **d_1802–d_1913**, or **2016-01-04–2016-04-24**. They contain **3,414,880 required daily input rows**. Every origin has 853,720 last-28-day positions and 213,430 last-seven-day positions. The logical filter limits quantities used in the calculation; it does not guarantee that the database engine physically reads only those rows or imply a fixed runtime.

Missing or duplicated input positions, invalid values, broken identifiers or mismatched date/week mappings must fail. Zero units remain valid inputs. This is a recent-history construction check; full-history training scales and wider evaluation outcomes are separate later checks. No final-holdout actual quantities enter this step.

## Formulas, output and preservation

SNAIVE7 repeats each series' final seven observed daily values four times. WEEKDAY4 averages the previous four occurrences of each weekday, including zeros, then repeats those seven means four times. All 28 forecasts are fixed at their origin. WEEKDAY4 keeps exact quarter-unit values, and SNAIVE7's whole-unit predictions use the same decimal storage type in the combined table.

The new table is `mart.m5_forecast_baselines_all_28d`. It has the 14 fields specified in the [protocol](FULL_CATALOG_BASELINE_FORECASTS_PROTOCOL.md), with model/origin/item/store/horizon as its logical key. It records source-day boundaries, observation count and source-unit sum so each forecast can be traced to the historical input rule.

There are **853,720 forecasts per model/origin**, **3,414,880 per model** and **6,829,760 across both models and all four origins**. Forecast positions are not observed sales transactions or units sold. SQL38 never reads or modifies either pilot table; it validates the new table against the recent source observations. The assistant independently checks pilot overlap and preservation during the private preflight described below. Do not overwrite the new table on a repeat run: use the saved-table validation section instead.

## Eight-row report

The 12 columns are `origin`, `model`, `series_count`, `forecast_rows`, `forecast_start`, `forecast_end`, `input_days`, `input_units`, `predicted_units`, `zero_forecast_rows`, `fractional_forecast_rows`, and `check_status`.

The four origins each show SNAIVE7 followed by WEEKDAY4. Every row has 30,490 series and 853,720 predictions. Input days are seven for SNAIVE7 and 28 for WEEKDAY4; input units sum those respective recent observations across all series. SNAIVE7's total prediction is four times its input total, while WEEKDAY4's total equals its 28-day input total. These arithmetic identities are construction controls, not performance results.

SNAIVE7 has no fractional predictions. WEEKDAY4 may have fractional positions because the mean of four integers can end in .25, .50 or .75. The zero and fractional columns count forecast positions, not distinct products or future realized outcomes. PASS confirms engineering checks.

## Independent verification and learner execution

The [runner](../validation/preflight_full_catalog_baseline_forecasts.py) uses read-only original sales and calendar CSVs with private temporary databases under ignored `tmp/`. The learner's persistent database is never opened. Independently computed references use bounded input storage and streaming comparisons so millions of forecasts need not become Python row dictionaries. Public [evidence](../data/full_catalog_baseline_forecasts_preflight.json) contains only aggregate results and fingerprints.

The full-catalog reference uses only the 112 recent days. Separately, the preflight reconstructs the accepted 216-series pilot using its original d_1–d_1913 historical inputs, verifies its complete original 13/15-field tables and accepted fingerprints, and maps its 24,192 rows per model to the common 14-field format for overlap comparison. This additional bounded pilot reconstruction is not a full-catalog history audit. The preservation checks apply to the privately reconstructed tables; no direct inspection of the learner's pilot tables is claimed.

The assistant preflight passed. All **3,414,880 required recent input rows across six fields** and **6,829,760 forecasts across 14 fields** matched the independent reference exactly. Streaming fingerprints were computed separately for observed and expected records, using canonical TAB-separated field strings with LF row endings, ISO dates and two-decimal predictions. Every field was compared before hashing; matching totals alone were not treated as a row-level audit.

Both privately reconstructed pilot tables matched their original 13/15-field references and accepted report/forecast fingerprints. The **24,192-row overlap per model across all 14 common fields** matched the full-catalog output. The pilot's **413,208 historical rows across six fields** were independently reconciled. Sources, pinned repository dependencies, relevant input projections, pilot tables and the saved full forecast table remained unchanged across validation. Private databases and detailed exports were removed.

All **13 focused cases** passed: five valid cases covered multiple products/stores with distinct histories, zeros and quarter means, maximum INTEGER inputs, origin isolation and removal of final-outcome records. Five creation rejections covered balanced missing/duplicate catalog pairs or recent days, negative units, date mapping corruption and empty recent input. Three saved-table rejections covered a total-preserving forecast swap, a balanced missing/duplicate output key and an incorrect decimal schema. The full run and fixtures used private databases with two threads and a 2 GB memory limit. Execution timings in the machine evidence describe that environment and do not predict the learner's runtime.

## Executed assistant construction results

All eight rows below passed, each with **30,490 series and 853,720 forecast positions**. These construction controls are **also accepted from the learner screenshot**. Detailed recent-input, forecast and pilot comparisons remain separate assistant preflight evidence.

| Origin | Model | Input days | Input units | Predicted units | Zero forecasts | Fractional forecasts |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| DEVELOPMENT_1 | SNAIVE7 | 7 | 266,224 | 1,064,896.00 | 508,680 | 0 |
| DEVELOPMENT_1 | WEEKDAY4 | 28 | 1,093,558 | 1,093,558.00 | 260,184 | 496,156 |
| DEVELOPMENT_2 | SNAIVE7 | 7 | 276,443 | 1,105,772.00 | 501,080 | 0 |
| DEVELOPMENT_2 | WEEKDAY4 | 28 | 1,175,668 | 1,175,668.00 | 236,616 | 513,980 |
| DEVELOPMENT_3 | SNAIVE7 | 7 | 287,458 | 1,149,832.00 | 492,984 | 0 |
| DEVELOPMENT_3 | WEEKDAY4 | 28 | 1,176,067 | 1,176,067.00 | 225,628 | 523,544 |
| FINAL_HOLDOUT | SNAIVE7 | 7 | 285,279 | 1,141,116.00 | 480,928 | 0 |
| FINAL_HOLDOUT | WEEKDAY4 | 28 | 1,183,626 | 1,183,626.00 | 212,108 | 535,464 |

The ordered report fingerprint is `8adf6723be729be1311415ef1379929c18d1637cd7316568b6278c654ea76587`. The complete canonical forecast stream fingerprint is `c090772d39f9a8cc324a2f707cda3d519a73efc7b58c7c804bf4b68f8101c38e`. The forecast counts and totals do not establish whether WEEKDAY4's pilot advantage persists in the broader scope; that requires wider development scoring.

For a first run, copy the whole SQL38 file into a new editor under the `retail_merchandising` DBeaver connection and execute the script. It creates the broader table and returns eight summary rows. If the table already exists after a successful build, run only the part after `-- VALIDATION:`. Keep any error for diagnosis rather than deleting accepted tables. Return all eight rows including model, origin and check status.

The final-origin rows are unscored candidates generated through 2016-04-24. Wider development evaluation follows this construction step. Final selection and the one final-holdout evaluation remain future work; no full-catalog accuracy, inventory benefit or completed forecasting stage is claimed here.

## Learner acceptance — 29 October 2026

The [learner acceptance record](../data/full_catalog_baseline_forecasts_learner_acceptance.json) transcribes all eight rows and twelve displayed fields in origin/model order. Counts and input units remain integers; integer-looking displayed predicted totals are normalized to two-decimal strings and dates to ISO format. Applying the SQL38 runner's canonicalization reproduces ordered report SHA-256 `8adf6723be729be1311415ef1379929c18d1637cd7316568b6278c654ea76587`.

Every row displays 30,490 series, 853,720 forecast positions and PASS. Summing the reported positions gives 6,829,760 across both models and four origins, or 3,414,880 per model. These are forecast positions, not distinct products or sales units. Input-total identities, zero counts and fractional counts match the table above. The separate product/store/department/category/state counts come from accepted metadata audits, not extra screenshot fields.

This accepts the learner's displayed construction and saved-table validation summary. It is not a direct database read or an independent inspection of all persisted predictions. The full recent-input and forecast comparisons, pilot history and original-table reconstructions, mapped overlap, 13 focused cases, preservation checks and cleanup remain historical assistant evidence. SQL38 does not read or audit the original pilot tables; their overlap and preservation were checked separately in the private preflight. Individual product identifiers, forecasts, vectors and screenshot are not published.

Assistant interpretation: the same two transparent formulas have a verified construction summary across the full released catalog. The pilot's WEEKDAY4 preference does not establish superiority in this broader scope. No wider forecast errors, full-history RMSSE scales, final-holdout scores, final model choice or inventory benefit are established by this step. Wider development scoring remains next under the unchanged evaluation plan. This screenshot acceptance does not independently test the learner's conceptual understanding.
