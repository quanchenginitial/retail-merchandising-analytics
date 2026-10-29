# Four-observation weekday-mean forecasts

## Purpose and status

[SQL35](../sql/35_build_weekday_mean_forecasts.sql) creates the second prespecified 28-day unit-sales forecast baseline. For each weekday, it averages the last four observations of that weekday, retaining zeros. Using four observations reduces reliance on a single week's value; whether it predicts better must be tested later. This step constructs and checks forecasts, without computing errors or selecting a final model. On 29 October 2026 (Australia/Sydney), the learner accepted all four report rows and twelve displayed fields; the canonical report fingerprint matches the historical assistant preflight exactly.

The learner has accepted [SQL34's SNAIVE7 report](SEASONAL_NAIVE_FORECASTS_VALIDATION.md). WEEKDAY4 uses the same frozen FOODS_1 / CA_1 scope, all 216 series, and the four origins in the [evaluation plan](EVALUATION_PLAN.md). Both candidates are retained separately for a consistent later comparison. The released catalog is a fixed retrospective benchmark roster, not a reconstruction of historical active assortment.

## Exact forecast rule

For cutoff T, horizon h = 1,...,28, and r = (h-1) modulo 7:

```text
four source days = T-27+r, T-20+r, T-13+r, T-6+r
source_units_sum = sum of all four historical unit counts, including zeros
predicted_units = source_units_sum * 0.25
forecast_day = T+h
```

The four source dates are seven days apart and share the target weekday. They lie within T-27 through T, inclusive. These are the final 28 calendar days ending at the cutoff, not the complete Saturday–Friday retail weeks used by the earlier XYZ module. The same seven means repeat throughout the four-week horizon; actual outcomes from forecast week one never become inputs for forecast weeks two through four at that origin.

Illustrative example, not a source-data result: four historical Mondays have 0, 2, 5 and 6 units, from oldest to newest. SNAIVE7 uses the latest value, 6. WEEKDAY4 uses `(0+2+5+6)/4 = 3.25` for each of the next four Mondays. Zero is a valid observation and remains in the denominator. A missing observation must trigger a data error rather than silently reducing the denominator.

A fractional prediction is an estimated quantity, not a claim that a fraction of a unit was actually sold or a physical order recommendation. Preserve the exact quarters for later scoring; rounding now would alter the method and could introduce bias. Integer accumulation and exact decimal multiplication avoid floating-point approximation and overflow when summing four valid INTEGER observations.

## Saved table

`mart.m5_forecast_weekday4_28d` contains **24,192 rows**, 6,048 for each origin. Its validated logical key is `(model, origin, item_id, store_id, horizon_day)`; uniqueness is checked rather than declared as a physical primary key.

| Field | Type | Meaning |
| --- | --- | --- |
| model | VARCHAR | WEEKDAY4 |
| origin | VARCHAR | Development origin 1–3 or final-holdout origin |
| dept_id / item_id / store_id | VARCHAR | Frozen-scope identifiers |
| train_end_day | INTEGER | Origin's final permitted training day |
| train_end | DATE | Training cutoff date |
| horizon_day | INTEGER | Position 1–28 within the horizon |
| forecast_day | INTEGER | Target day number |
| forecast_date | DATE | Target date |
| source_first_day | INTEGER | Earliest of the four contributing days |
| source_last_day | INTEGER | Latest contributing day, 21 days after the earliest |
| source_observations | BIGINT | Exactly four observations |
| source_units_sum | BIGINT | Exact sum of the four nonnegative unit counts |
| predicted_units | DECIMAL(18,2) | Exact mean, in increments of 0.25 |

All 216 series and all 28 horizons remain, including zero predictions. The four source day numbers are `source_first_day + {0,7,14,21}`; together with the stored numerator they make the forecast traceable. Product-level predictions and source vectors remain local; public evidence contains aggregate controls and fingerprints.

## Reading the four-row report

The 12 columns are `origin`, `dept_id`, `store_id`, `series_count`, `forecast_rows`, `forecast_start`, `forecast_end`, `last28_units`, `predicted_units`, `zero_forecast_rows`, `fractional_forecast_rows`, and `check_status`.

- Each origin has 216 series and 6,048 forecast positions.
- `last28_units` sums the 6,048 historical observations from the final 28 calendar days including that origin's cutoff.
- `predicted_units` sums 6,048 future predictions. It must equal `last28_units`: each weekday's four-value mean repeats four times. This equality is only an aggregate check; source-day and saved-value checks establish the individual mapping.
- `zero_forecast_rows` counts forecast positions whose four historical inputs are all zero. `fractional_forecast_rows` counts non-integer predictions. Neither count represents a number of distinct products.
- PASS means the construction and integrity checks passed. It does not imply greater accuracy than SNAIVE7.

## Time boundaries and execution

The four training cutoffs remain d_1829, d_1857, d_1885 and d_1913. Their 28-day calendar horizons remain 2016-02-01–02-28, 2016-02-29–03-27, 2016-03-28–04-24 and 2016-04-25–05-22. Earlier development dates can become training history at later origins; every prediction is still bounded by its own origin. April ABC/XYZ labels and future prices are not forecast inputs.

The final-origin forecasts are an unscored candidate. Final-holdout unit values are not used in construction or validation, and no final model is selected. Full-snapshot engineering audits previously included overall totals, so this is not a claim that final data has never been seen.

On first execution, run the complete SQL35 file in the existing `retail_merchandising` connection. It creates one new table without replacing an existing table and then validates the saved result. On later checks, run only the section beginning `-- VALIDATION:`. Keep the SNAIVE7 table for subsequent comparison.

Construction and validation reuse the accepted SQL33 scope/time checks. They require complete historical inputs, four correctly spaced observations per weekday, exact schema and keys, and agreement of every saved field with a reconstruction from permitted source records. Corrupted inputs or saved forecasts block the report. Existing analytical inputs remain unchanged.

## Independent verification

The [preflight runner](../validation/preflight_weekday_mean_forecasts.py) and [machine evidence](../data/weekday_mean_forecasts_preflight.json) separate detailed assistant verification from the learner screenshot acceptance below. Original source files remain read-only; private temporary databases and detailed exports are kept under ignored `tmp/` and removed after verification. The learner's persistent database is never opened.

The independent reference uses original CSV training values and Python Decimal arithmetic. It splits each origin's final 28 observations into four seven-day blocks, averages corresponding columns and repeats the resulting seven values in four loops. This is separate from the SQL day-grid construction and decimal multiplication. It compares all source and saved fields rather than relying on aggregate equality. It also reconstructs and verifies the existing SNAIVE7 candidate against its accepted report and detailed-forecast fingerprints before checking that SQL35 leaves it unchanged.

## Executed assistant results

All four aggregate rows and all 12 report fields match the independent reference:

| Origin | Series | Forecast rows | Last-28-day actual units | Predicted 28-day units | Zero forecasts | Fractional forecasts |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| DEVELOPMENT_1 | 216 | 6,048 | 8,336 | 8,336.00 | 1,228 | 3,984 |
| DEVELOPMENT_2 | 216 | 6,048 | 8,891 | 8,891.00 | 1,168 | 3,956 |
| DEVELOPMENT_3 | 216 | 6,048 | 9,456 | 9,456.00 | 1,292 | 3,788 |
| FINAL_HOLDOUT | 216 | 6,048 | 8,017 | 8,017.00 | 1,228 | 3,828 |

Individual forecasts may be fractional even though each origin's predicted total is an integer. The repeated-mean construction recovers the integer historical total across the entire horizon. These totals are candidate outputs, not observed future sales or accuracy scores.

- **24,192 WEEKDAY4 rows × 15 fields** match the independent Decimal reference, with zero mismatches. Schema, field order, complete keys and exact quarter values are verified.
- **413,208 training rows × six fields** match original CSV values, together with source-backed product/store mappings and used calendar/raw metadata projections. Both SQL35 scope-validation prefixes are byte-identical to SQL33's accepted prefix.
- **24,192 SNAIVE7 rows × 13 fields** are independently reconstructed and matched. Its four-row learner-accepted report and full forecast fingerprint match, and the saved SNAIVE7 export remains identical before and after SQL35.
- **19 targeted cases passed:** six valid behaviors, four expected creation rejections and nine expected saved-table validation rejections. Coverage includes unequal weeks with zeros and fractional means, all-zero series, four maximum INTEGER observations, origin-local temporal isolation and final-holdout exclusion. Deliberate faults exercise missing inputs, wrong observation counts, altered source sums/bounds, altered quarter-valued predictions, total-preserving swaps, duplicate/missing keys and schema changes.
- Repeated creation cannot overwrite an existing WEEKDAY4 table. Validation is read-only for the saved forecasts. The five source projections, both original source-file hashes, reference helpers, acceptance evidence and historical preflight records remain unchanged. Private temporary databases and detailed exports were removed.
- A separate read-only review checked implementation, documentation and executed provenance and found no remaining material correction. Learner SQL35 execution and screenshot acceptance are now recorded separately below; the historical preflight JSON remains unchanged.

The ordered four-row report SHA-256 is `075094fbbc14290ad397c358c44ccc72d7f9309042f139f21601a05bb1d19b50`. The ordered WEEKDAY4 detail SHA-256 is `cc13454ee4ebd947cbe4ff2d45cb6b67a827f019dd843ea824117828ca31b49f`, matching the independent reference. Predicted-unit values are serialized as two-decimal strings; integer source counts and sums remain JSON integers. Detailed forecasts, source vectors and real product identifiers are not published.

To reproduce the assistant preflight from the repository root in the documented environment:

```powershell
& 'C:/Users/dell/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe' validation/preflight_weekday_mean_forecasts.py --duckdb 'E:/DuckDB/duckdb.exe' --output 'tmp/weekday_mean_forecasts_rerun.json'
```

The runner uses original CSVs under `D:/database/m5-forecasting-accuracy` and checks their source-registry hashes. Keep rerun evidence separate from the published historical record. Source rows are tokenized in full, but only selected training-unit cells through d_1913 are inspected or converted; final-holdout unit values are discarded without scoring. Timings and their measured scopes are retained in the machine evidence, not asserted as guarantees for the learner's full database.

## Learner acceptance — 29 October 2026

The [learner acceptance record](../data/weekday_mean_forecasts_learner_acceptance.json) transcribes all four aggregate screenshot rows, including the FOODS_1 / CA_1 scope labels, dates, counts, predicted totals and PASS statuses. Each row matches the table above. Displayed predicted totals such as `8336` are normalized to `"8336.00"`; source counts and historical units remain integers. Applying the SQL35 runner's canonicalization gives the same ordered report fingerprint, `075094fbbc14290ad397c358c44ccc72d7f9309042f139f21601a05bb1d19b50`.

This accepts the learner's displayed construction/validation result. It is not a direct read of the learner database or an independent inspection of all 24,192 stored predictions. The detailed source/forecast comparisons, 19 targeted cases, unchanged-input evidence and temporary-file cleanup remain assistant preflight evidence. No individual product identifiers, forecast vectors or screenshot are saved publicly.

Assistant interpretation: both prescribed baseline candidates are now constructed. WEEKDAY4's predicted totals equal its last-28-day input sums by arithmetic design; this does not show accuracy. Its nonzero fractional-position counts also show why integer-looking report totals must not be interpreted as integer rounding of each prediction. Zero and fractional counts describe forecast positions, not distinct products, future observed outcomes or physical orders. This acceptance does not independently test the learner's conceptual understanding.

## Next evaluation

[SQL36](../sql/36_compare_development_forecast_errors.sql) will compare the two fixed candidates on the three development windows in six read-only report rows. Include all 216 scoped series in MAE and signed mean error (prediction minus actual). Compute macro RMSSE as an unweighted mean over series with a defined training-only scale, starting at each series' first positive training observation; report undefined scales explicitly rather than setting them to zero. See the [development error comparison method](DEVELOPMENT_FORECAST_ERRORS_VALIDATION.md). Final-holdout actual values remain excluded, and no final selection follows from this construction acceptance. Forecast totals, smoothness and zero counts alone cannot establish which candidate is better; no accuracy improvement or business benefit is claimed by SQL35.
