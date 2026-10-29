# Forecast scope and time-boundary audit

## Purpose and status

[SQL33](../sql/33_forecast_scope_and_time_audit.sql) prepares the existing [28-day forecast protocol](EVALUATION_PLAN.md). Before generating predictions, it fixes the learning population and checks that each series has complete historical inputs at each origin. It is a read-only audit, not a forecast or an evaluation result. On 29 October 2026, the learner screenshot confirmed all four rows and thirteen columns PASS, with canonical report fingerprint matching historical preflight. [Learner acceptance](../data/forecast_scope_and_time_audit_learner_acceptance.json) records the four public aggregate rows; independent source verification remains separate in [preflight evidence](../data/forecast_scope_and_time_audit_preflight.json).

## Population fixed without sales-based selection

Select the lexicographically first department and first store from the accepted dimensions: **FOODS_1 / CA_1**, containing **216 product-store series**. Retain all scope members regardless of their observed units, including all-zero training series. The choice uses no ABC/XYZ label, case-study membership, price change or forecast error. It is a deliberately small learning slice and cannot stand in for full-dataset performance.

The scope is a retrospective benchmark roster from the released catalog; it is not evidence of which products were active or known at every historical origin. April ABC/XYZ labels cannot be used as origin-known features at the earlier development origins. Any future feature based on sales must be rebuilt using that origin's training data only.

The query checks product/store dimensions against the raw identifier projection, then enforces both the scope count and frozen exact membership. The membership hash is SHA-256 of UTF-8 `item_id|store_id` lines sorted by item then store, joined by LF without a trailing LF. Alphanumeric/underscore identifier constraints prevent separator ambiguity. The frozen hash is `6cabe9ae29616ce129fdf89fb02fec1cffd31ccb8194c4694b8bdf0ed85e622f`. A same-count member substitution must fail. Public files retain the scope names, count and fingerprint, not the product list.

## Expanding training windows

Every training window starts at d_1, 2011-01-29. The SQL returns one row per origin:

| Origin | Last training day | Training end | Forecast calendar dates | Training records |
| --- | --- | --- | --- | ---: |
| DEVELOPMENT_1 | d_1829 | 2016-01-31 | 2016-02-01–2016-02-28 | 395,064 |
| DEVELOPMENT_2 | d_1857 | 2016-02-28 | 2016-02-29–2016-03-27 | 401,112 |
| DEVELOPMENT_3 | d_1885 | 2016-03-27 | 2016-03-28–2016-04-24 | 407,160 |
| FINAL_HOLDOUT | d_1913 | 2016-04-24 | 2016-04-25–2016-05-22 | 413,208 |

Each row has 216 series, 1,512 records in the last seven training days, 6,048 in the last 28 training days, and 28 forecast calendar dates. These are record counts, not units. Training records overlap between origins and must not be summed as distinct observations. The complete unique training projection through d_1913 contains 413,208 rows.

The 13 output columns are `origin`, `dept_id`, `store_id`, `series_count`, `train_end_day`, `train_end`, `forecast_start`, `forecast_end`, `training_rows`, `last7_rows`, `last28_rows`, `forecast_calendar_days`, and `check_status`. They form an aggregate audit report with no product-level observations.

## Runtime checks and boundaries

- Check the complete product/store schemas and only the used fields of raw metadata, calendar and daily facts. This is not a new audit of unused price/value columns or all 59 million fact rows.
- Require unique, nonblank product and store keys; consistent department/category mapping; raw/dimension agreement; and exactly one raw series for every selected product/store pair.
- Validate the calendar's 1,969 unique day keys, dates and day numbers against d_1, with a nonnull retail-week mapping. Forecast dates are checked against the fixed origin boundaries.
- Project only selected-scope training units through d_1913. Verify integral, nonnegative, nonnull units, fact/calendar date and retail-week agreement, and complete unique day/date coverage separately for every series at every origin.
- Require complete last-seven-day and last-28-day input windows. Missing observations are errors, not zero sales. A missing day replaced by a duplicate must still fail even when total row counts are unchanged.
- Return four PASS rows only when the combined audit passes; invalid inputs block the result with an error. PASS establishes these data checks, not forecasting skill.

Calendar coverage establishes available date labels. It does **not** establish the presence, quality or values of final-holdout sales. Earlier development target dates become training history at later origins; each origin's coverage counts are still bounded by its own cutoff. Final-holdout unit values (d_1914–d_1941) are excluded from this audit. The SQL produces no target-unit aggregate, prediction, error, price feature or ABC/XYZ feature. Engineering audits have previously included full-snapshot totals, so the final period is reserved for forecasting evaluation rather than described as wholly unseen.

## Independent verification

The companion [runner](../validation/preflight_forecast_scope_and_time_audit.py) uses private temporary databases under the ignored `tmp/` directory and read-only original CSVs. It never connects to the learner's persistent database. Its CSV/Python reference independently selects and hashes membership, validates dates, parses selected training integers, and compares every selected training observation through private streamed CSV exports. The four expected report rows are derived separately from source calendar mappings and the complete series/day roster.

Executed results on DuckDB v1.5.5:

- **413,208 training rows × six fields** match the original CSV reference with zero field mismatches. The 3,049-product and 10-store dimensions, 30,490 raw metadata rows and 1,969 calendar projections also match their source reference.
- All **four report rows × 13 columns**, including field order and origin order, match. The canonical ordered report SHA-256 is `c1df269f32ca8f9e5e680780796a6b385e97c89303719d6ac33beb6209aa54b0`.
- **33 targeted cases passed:** five valid cases and 28 expected rejections. Valid cases include zero-only training series, shuffled metadata, absent final-holdout observations and altered final-holdout values. Rejections cover balanced missing/duplicate days, malformed extra training keys, invalid units, changed membership even at the same count, source/dimension disagreement and damaged calendar boundaries.
- Both used source-file hashes, historical preflights and five deterministic input projections remain unchanged. Private databases and row-level exports were removed. No actual source product identifiers, training vectors or final-holdout unit values are published.

The four-row audit took 1.153 seconds in this private run; source reconstruction and initial export took 14.598 seconds. These timings do not predict performance against the learner's full fact table. The evidence records exact timing scopes and excludes remaining Python comparisons and hashing. A separate read-only review found the implemented scope, boundaries and executed evidence consistent. The learner has now accepted the displayed four-row audit by screenshot; the source reconstruction and fixtures remain assistant evidence.

To reproduce the assistant preflight from the repository root on the documented local environment:

```powershell
& 'C:/Users/dell/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe' validation/preflight_forecast_scope_and_time_audit.py --duckdb 'E:/DuckDB/duckdb.exe' --output 'tmp/forecast_scope_and_time_audit_rerun.json'
```

The runner expects original files under `D:/database/m5-forecasting-accuracy` and verifies their hashes against the source registry. Adjust environment paths when reproducing elsewhere; keep rerun evidence separate from the published historical record. It tokenizes complete CSV records but only inspects selected training unit fields through d_1913, discarding final-holdout unit cells without conversion or evaluation.

## Learner acceptance

The four-row screenshot was transcribed with integer counts and ISO dates, preserving origin order and all thirteen columns. Its SHA-256 matches `c1df269f32ca8f9e5e680780796a6b385e97c89303719d6ac33beb6209aa54b0` exactly. Scope labels FOODS_1 / CA_1 and the four aggregate origins are safe to publish; no product identifiers, membership list, row-level observations or screenshot are saved.

The accepted report confirms 216 series per origin, 1,512 last-seven-day records, 6,048 last-28-day records and 28 forecast calendar dates. Expanding training counts overlap and are not summed. The screenshot establishes these displayed results and learner execution; it is not a separate direct audit of the learner database, every training value or target observation. Source comparisons, frozen-membership checks and final-holdout access boundaries remain the independently documented SQL/preflight evidence. This is an input/time audit, not a forecast-skill result or an independent test of the learner's conceptual understanding.

## Subsequent work

With the scope/time audit accepted, the next step is to generate the complete 28-day last-seven-day-pattern baseline at each origin without updating it with actual target outcomes. Compare the previous-four-same-weekday mean under the same scope and windows, then evaluate development MAE, signed error and training-scaled RMSSE under the evaluation plan. Freeze method choices before final-holdout evaluation. None of those forecast results is claimed by this preparation step.
