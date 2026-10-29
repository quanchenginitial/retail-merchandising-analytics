# Weekly seasonal-naive forecast construction

## Purpose and status

[SQL34](../sql/34_build_seasonal_naive_forecasts.sql) creates the first reproducible 28-day unit-sales forecast candidate. It repeats each series' last observed seven days over the next four weeks. This provides a simple reference against which later methods can be compared. Correct construction does not establish accuracy; no forecast errors are computed in this step. Learner execution remains pending.

The [evaluation plan](EVALUATION_PLAN.md) fixes scope, origins and later evaluation rules. [SQL33's accepted scope audit](FORECAST_SCOPE_AND_TIME_AUDIT_VALIDATION.md) establishes FOODS_1 at CA_1, with all 216 product-store series retained. The scope is a retrospective released-catalog benchmark, not an inferred list of products active at each origin. April ABC/XYZ labels and weekly prices are not inputs to this model.

## Forecast rule

For cutoff day T and horizon h from 1 through 28:

```text
source_day = T - 6 + ((h - 1) % 7)
forecast_day = T + h
predicted_units = observed_units[source_day]
```

The source day always lies in T-6 through T, inclusive. These are the last seven calendar days ending at the cutoff, not the previous complete Saturday–Friday M5 retail week used in the earlier XYZ module. Each of these seven observations is used exactly four times per series and origin. Source and forecast dates have the same weekday. For example, if the final observed Monday has three units, each of the next four Mondays receives a forecast of three units. This is an illustrative example, not a source-data result.

All 28 predictions are made at the origin. For horizon 8, use the same historical input as horizon 1; do not read the actual units from horizon 1. This is a fixed-origin, multi-step forecast rather than a daily update with newly observed outcomes. Nonnegative integers and zeros are preserved exactly. A missing input is an error, not a zero forecast.

## Saved table

The script creates `mart.m5_forecast_snaive7_28d` without replacing an existing table. Its validated logical key is `(model, origin, item_id, store_id, horizon_day)`; validated uniqueness does not imply a declared physical primary key.

| Field | Type | Meaning |
| --- | --- | --- |
| model | VARCHAR | Fixed candidate tag SNAIVE7 |
| origin | VARCHAR | DEVELOPMENT_1, DEVELOPMENT_2, DEVELOPMENT_3 or FINAL_HOLDOUT |
| dept_id / item_id / store_id | VARCHAR | Frozen-scope identifiers |
| train_end_day | INTEGER | Last day allowed as training information |
| train_end | DATE | Date of that cutoff |
| horizon_day | INTEGER | Forecast position 1–28 |
| forecast_day | INTEGER | Target day number T+h |
| forecast_date | DATE | Target date |
| source_day | INTEGER | Historical day used by this prediction |
| source_date | DATE | Historical source date |
| predicted_units | INTEGER | Copied historical unit count, including zero |

There are **6,048 rows per origin** and **24,192 rows in total**. Each origin contains all 216 series and every one of its 28 target dates. These are forecast positions, not observed transactions or distinct products. Product-level predictions stay in the local database; public evidence retains only aggregates and fingerprints.

## Origins and information available

| Origin | Training cutoff | Forecast dates |
| --- | --- | --- |
| DEVELOPMENT_1 | d_1829 / 2016-01-31 | 2016-02-01–2016-02-28 |
| DEVELOPMENT_2 | d_1857 / 2016-02-28 | 2016-02-29–2016-03-27 |
| DEVELOPMENT_3 | d_1885 / 2016-03-27 | 2016-03-28–2016-04-24 |
| FINAL_HOLDOUT | d_1913 / 2016-04-24 | 2016-04-25–2016-05-22 |

Earlier development outcome dates legitimately become training history at later origins. Each individual forecast still uses only its own origin's information. Final-holdout unit values are excluded from construction and validation; future calendar dates supply labels only. Earlier full-snapshot engineering audits saw aggregate totals, so this is not a claim of wholly unseen final data.

The FINAL_HOLDOUT rows are forecasts from this candidate, not a declaration that it is the selected final model. Generating them without their actual outcomes does not evaluate the holdout. Method selection and final scoring remain later work.

## Reading the four-row report

The report has 11 fields: `origin`, `dept_id`, `store_id`, `series_count`, `forecast_rows`, `forecast_start`, `forecast_end`, `last7_units`, `predicted_units`, `zero_forecast_rows`, and `check_status`.

Each row describes one origin. `last7_units` sums the 1,512 historical input observations across 216 series and the last seven days including the cutoff. `predicted_units` sums that origin's 6,048 predictions; it must equal four times `last7_units`. This is a necessary aggregate check; verifying each repeated value requires the separate source-day and saved-field comparisons. It does not establish predictive accuracy. `zero_forecast_rows` counts zero-valued forecast positions, not unique zero-sales products. Every series remains present regardless of its sales.

## Execution and verification boundary

For the first learner execution, run the whole file in the existing `retail_merchandising` connection. It creates one new forecast table and returns its validation summary. Existing source, dimension and merchandising tables remain inputs. To recheck an already-created table, run only the section beginning `-- VALIDATION:`; do not rerun creation or delete the table merely to obtain the report again.

Both construction and validation recheck the frozen SQL33 scope and training-time contract. Saved predictions must have the exact schema, complete unique keys, correct dates and source-day mapping, and values matching the permitted historical inputs. An invalid input or corrupted saved forecast blocks the report. A successful output means the implemented construction checks passed; it does not mean the predictions are accurate.

Independent assistant verification is recorded in [the preflight evidence](../data/seasonal_naive_forecasts_preflight.json) and implemented by [the preflight runner](../validation/preflight_seasonal_naive_forecasts.py). It uses only original read-only source files and private temporary databases under ignored `tmp/`, never the learner's persistent database. The Python reference extracts each origin's seven-element historical slice and repeats it in four loops, independently of the SQL modulo expression. The reconstructed SQL33 report also matches the learner's accepted scope-report fingerprint. Learner SQL34 screenshot acceptance remains pending.

## Executed assistant results

All four aggregate rows and their 11 fields match the independent reference:

| Origin | Series | Forecast rows | Last-seven-day actual units | Predicted 28-day units | Zero-valued forecast rows |
| --- | ---: | ---: | ---: | ---: | ---: |
| DEVELOPMENT_1 | 216 | 6,048 | 2,067 | 8,268 | 3,208 |
| DEVELOPMENT_2 | 216 | 6,048 | 2,028 | 8,112 | 3,336 |
| DEVELOPMENT_3 | 216 | 6,048 | 2,842 | 11,368 | 2,972 |
| FINAL_HOLDOUT | 216 | 6,048 | 2,202 | 8,808 | 2,956 |

These predicted totals are model outputs, not observed future sales or accuracy scores. The zero counts describe prediction positions and should not be interpreted as a measured number of future stockouts.

- **24,192 saved forecast rows × 13 fields** match the independent Python reference, with zero mismatches. The exact schema/order and unique logical keys pass.
- **413,208 historical training rows × six fields**, all product/store mappings and the used raw metadata/calendar projections match original CSV references. Both SQL34 validation prefixes match SQL33's accepted prefix byte for byte.
- **19 targeted cases passed:** six valid behavior cases, five expected creation rejections and eight expected saved-table validation rejections. Tests cover distinct weekly patterns and zeros, all-zero series, altered or absent final-holdout outcomes, and origin-specific future-data isolation. Deliberate stored-table faults include duplicate/missing keys and value swaps that preserve the aggregate total, ensuring totals alone cannot conceal incorrect predictions.
- Re-executing creation cannot overwrite an existing forecast table. Validation leaves the saved forecasts unchanged. The five input projections, both source-file hashes, reference helpers, acceptance evidence and historical preflight records remain unchanged; all private temporary databases and detailed exports were removed.
- A separate read-only review checked logic, provenance and the executed evidence and found no remaining material correction. No learner database was accessed.

The ordered four-row report SHA-256 is `ad3c5000fd81a327e400cf32fddf57b3ba41bf59bddd73bb4e4de175229ac9ce`. The ordered detailed-forecast SHA-256 is `ba27d6983331c204021881bf048cc9ff24af867096fade669a49e05f7b47fb4e`, matching the independent reference. Detailed predictions and real product identifiers remain private; fingerprint serialization is specified in the machine evidence.

On DuckDB v1.5.5, private forecast creation took 1.412 seconds and saved-table validation took 1.392 seconds. Source reconstruction and initial export took 16.000 seconds. These measured scopes exclude remaining Python comparisons and hashing and do not guarantee timing against the learner's full fact table.

To reproduce the assistant preflight from the repository root in the documented environment:

```powershell
& 'C:/Users/dell/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe' validation/preflight_seasonal_naive_forecasts.py --duckdb 'E:/DuckDB/duckdb.exe' --output 'tmp/seasonal_naive_forecasts_rerun.json'
```

The original CSV location remains `D:/database/m5-forecasting-accuracy`; hashes are checked against the source registry. Keep rerun evidence under `tmp/` so published historical evidence remains unchanged. Source CSV records are tokenized in full, but only selected training-unit cells through d_1913 are inspected or converted; final-holdout unit values are discarded without scoring.

## Limitations and next comparison

Repeating one week preserves a weekly pattern, but does not explicitly model trends, holidays or promotions. A zero input produces zero predictions for that weekday even if future recorded sales are positive. These are properties to evaluate on development windows, not reasons to remove difficult series in advance.

After this output is accepted, continue under the evaluation plan with the previous-four-same-weekday baseline and development-only error comparisons. Report MAE, signed error and training-scaled RMSSE with their defined zero-scale handling before any final evaluation. No accuracy score or model improvement is asserted here.
