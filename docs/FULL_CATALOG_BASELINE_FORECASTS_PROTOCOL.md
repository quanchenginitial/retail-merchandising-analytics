# Fixed protocol: expand both baselines to the full released catalog

## Development decision and next question

The accepted pilot covers 216 product-store series in FOODS_1 / CA_1. SQL36 shows lower MAE and macro RMSSE for WEEKDAY4 in all three development windows. SQL37 shows negative mean and median paired differences in all six metric/window groups, with MAE win shares of 54.1667%, 50.0000% and 67.5926%, and RMSSE win shares of 72.6852%, 65.7407% and 80.5556%. DEVELOPMENT_2 MAE is exactly half wins, not a strict majority.

Record WEEKDAY4 as the **preferred development baseline within this pilot**. This is a documented judgment from observed development evidence, not a previously registered selection test, a final model choice, or proof of improvement for every product. Preserve SNAIVE7 as the comparison method. Do not construct a hindsight oracle that selects a different method for each product from its scored future errors.

The next question is whether the same reproducible forecasting process works across the full catalog. [SQL38](../sql/38_build_full_catalog_baseline_forecasts.sql) expands both unchanged formulas to all 3,049 products at all ten stores: **30,490 series**, seven departments, three categories and three states. The broader roster is defined by the accepted metadata and complete item/store combinations, not by observed forecast performance, ABC/XYZ classes, positive sales or availability of a favorable RMSSE scale. This remains a retrospective roster from the released M5 catalog, not a historical active-assortment reconstruction.

Wider development scoring and any subsequent model extensions must precede final selection. No tree model, full-catalog accuracy gain, official WRMSSE, final-holdout score or operational benefit is established by this construction step. The original [evaluation plan](EVALUATION_PLAN.md) remains unchanged.

## Temporal inputs

Keep the four established origins and 28-day horizons unchanged:

| Origin | Training cutoff | Required recent input | Prediction period |
| --- | --- | --- | --- |
| DEVELOPMENT_1 | d_1829 / 2016-01-31 | d_1802–d_1829 / 2016-01-04–2016-01-31 | 2016-02-01–2016-02-28 |
| DEVELOPMENT_2 | d_1857 / 2016-02-28 | d_1830–d_1857 / 2016-02-01–2016-02-28 | 2016-02-29–2016-03-27 |
| DEVELOPMENT_3 | d_1885 / 2016-03-27 | d_1858–d_1885 / 2016-02-29–2016-03-27 | 2016-03-28–2016-04-24 |
| FINAL_HOLDOUT | d_1913 / 2016-04-24 | d_1886–d_1913 / 2016-03-28–2016-04-24 | 2016-04-25–2016-05-22 |

Both formulas use only recent history. Validate the four nonoverlapping 28-day input windows, totaling **112 days and 3,414,880 input rows**. Every origin has 853,720 last-28-day observations and 213,430 last-seven-day observations. Missing, duplicated, negative, invalid or misdated input rows must fail, not be silently removed or imputed. Keep zero sales. Verify canonical day identifiers, date/week mapping and declared types.

This is a recent-input construction audit, not a new full-history audit or a validation of future outcome availability. Full-history training scales are needed later for RMSSE. Do not use dates or quantities after an individual origin in that origin's forecast, and never read final-holdout actual quantities d_1914–d_1941. Calendar dates for the horizon can be checked without reading those actuals.

## Candidate formulas and saved table

For cutoff T and horizon h=1,...,28, let r=(h-1) modulo seven.

- SNAIVE7 predicts observed units at T-6+r. Source first and last day both equal that day; source observations equal one and source sum equals those observed units. Repeat the seven values four times.
- WEEKDAY4 averages units at T-27+r, T-20+r, T-13+r and T-6+r, including zeros. Source first/last day span these four observations; count equals four. Accumulate the source sum as a sufficiently wide integer and multiply exactly by decimal 0.25. Repeat the seven quarter-unit means four times.

Retain all horizons and all series. No target outcomes enter forecasts during the 28-day horizon. Do not round WEEKDAY4 predictions to integers, introduce extra smoothing or change the formulas during expansion.

Create a new table `mart.m5_forecast_baselines_all_28d`, preserving both pilot tables. Use CREATE TABLE without OR REPLACE: an existing full-catalog table must not be overwritten. Put the reusable saved-table validation after the script's `-- VALIDATION:` marker.

The ordered 14 fields are `model` VARCHAR, `origin` VARCHAR, `item_id` VARCHAR, `store_id` VARCHAR, `train_end_day` INTEGER, `train_end` DATE, `horizon_day` INTEGER, `forecast_day` INTEGER, `forecast_date` DATE, `source_first_day` INTEGER, `source_last_day` INTEGER, `source_observations` BIGINT, `source_units_sum` BIGINT, and `predicted_units` DECIMAL(18,2). The logical key is model/origin/item/store/horizon. Validate values and types; do not describe logical checks as declared physical primary keys.

There must be **853,720 rows per origin/model**, **3,414,880 per model**, and **6,829,760 overall**. The overlap with the accepted pilot must reproduce its predictions and source mappings for 24,192 rows per model. Pilot tables remain unchanged. Source/catalog integrity, input-window completeness and candidate values must be checked before accepting the output.

## Eight-row report

Return four origins in chronological order, each SNAIVE7 then WEEKDAY4. The 12 ordered columns are `origin`, `model`, `series_count`, `forecast_rows`, `forecast_start`, `forecast_end`, `input_days`, `input_units`, `predicted_units`, `zero_forecast_rows`, `fractional_forecast_rows`, and `check_status`.

Every row reports 30,490 series and 853,720 forecasts. For SNAIVE7, input_days is seven, input_units is the last-seven-day total, and predicted_units equals four times input_units. For WEEKDAY4, input_days is 28, input_units is the last-28-day total, and predicted_units equals input_units. These are necessary construction identities, not accuracy metrics. SNAIVE7 has zero fractional forecast rows; WEEKDAY4 retains exact quarters. Zero/fractional counts refer to forecast positions, not distinct products, customers or orders.

PASS is an engineering verification status. This step computes no wider-scope forecast errors and makes no final model selection. Both unscored final-origin candidates remain frozen outputs from information available through 2016-04-24.

## Independent verification boundaries

The assistant's preflight uses read-only original CSV files and private temporary databases under ignored `tmp/`, never the learner's persistent database. Stream comparisons of all 6,829,760 saved rows across 14 fields against independently generated source-based references; do not load millions of row dictionaries into memory. Check the required recent-input rows, accepted pilot overlap, exact summary fields, and preserved sources/candidates/history. Publish only aggregates and fingerprints. Detailed forecasts, product identifiers, snapshots, databases and raw data remain private.

Focused tests should address new full-roster coverage and resource/numeric risks, missing or duplicated recent inputs, quarter means including zeros, origin boundaries, damaged saved output and preserved pilot parity. Existing accepted tests need not be repeated without a new concern. Freeze this document before computing full-catalog construction results, and record assistant preflight separately from learner execution.
