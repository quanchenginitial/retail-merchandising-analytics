# Core calendar: purpose and validation

27 October 2026. The learner screenshot confirms all 17 checks from [14_build_calendar_dimension.sql](../sql/14_build_calendar_dimension.sql) passed: 1,969 unique days/dates, 15 correctly typed fields, exact preservation of the original 14 fields and valid derived day numbers. core.m5_calendar is accepted. The [screenshot transcription](../data/calendar_dimension_learner_acceptance.json) is separate from the assistant preflight below. Product, store and calendar acceptance is summarised in the [dimension checkpoint](DIMENSIONS_CHECKPOINT.md).

## Why a core calendar

The accepted staging calendar preserves typed source fields. The core calendar provides the analytical day/date/week lookup, retaining those 14 fields in their existing order and appending INTEGER day_number. This numeric day order supports chronological sorting and explicit observation-window checks without sorting labels such as d_10 and d_2 alphabetically. Later sales and price joins can use d and the original wm_yr_wk, respectively. The core table has 15 columns.

All 1,969 dates are retained, from 2011-01-29 through 2016-06-19. The accepted sales snapshot covers d_1 through d_1941, ending on 2016-05-22. The remaining 28 calendar dates have no observed sales in that snapshot. They remain available for future-horizon alignment; the script does not generate or zero-fill sales for them. The snapshot endpoint is not a substitute for the earlier cutoffs required by rolling model evaluation.

The source wm_yr_wk and wday definitions are preserved, not replaced with ISO weeks or another weekday numbering convention. Event names/types, legitimate event NULLs and all SNAP fields are copied exactly. This step relies on the previously accepted source-field semantics; it adds day-key and derived-number checks, not a new event or SNAP interpretation.

## Creation and acceptance contract

Creation rejects missing required core fields, duplicate d or date keys, noncanonical labels, out-of-range day numbers and incorrect day/date relationships. The mapping uses date_diff from 2011-01-29 plus one, avoiding date arithmetic based on an arbitrary malformed day suffix. Event fields may remain NULL. Ordinary CREATE TABLE AS SELECT does not replace an existing table. Empty-source creation can produce an empty target, but it fails acceptance.

All 17 checks must pass together: 1,969 rows and distinct dates/day labels/day numbers, the exact 15-column schema, zero missing core values or invalid mappings, the expected date range and 282 source retail weeks, and a 1,941/28 partition around the accepted sales snapshot endpoint. Together, unique valid day numbers, their 1..1969 range and the expected count establish complete day coverage.

The original 14 fields are compared with staging by two-way EXCEPT ALL. This detects duplicate, missing and changed rows, including lost event values or altered NULLs. The derived day_number is independently checked against both the d suffix and actual date; matching the original 14 fields alone cannot prove that the added field is correct.

Each distinct staging day key must join to exactly one core row. This is a small calendar-key check, not a join to all daily sales or a proof of daily price coverage. The observed_sales_days and post_observation_days checks count calendar rows using the accepted d_1941 boundary; the script does not rescan sales to infer those dates. Uniqueness is validated rather than enforced by a declared PRIMARY KEY. Subsequent full joins must independently preserve sales rows and units.

## Independent execution

The [runner](../validation/preflight_calendar_dimension.py) imported calendar.csv into raw, reproduced accepted calendar staging and ran the unchanged core script in private in-memory DuckDB databases. It never opened the learner database. The source SHA-256 matched the registered snapshot before execution and remained unchanged after the baseline and all fixtures.

With DuckDB v1.5.5, two threads and memory_limit=512MB, raw/staging/core creation and 17 checks took 0.309 seconds. All checks passed. This one-run timing and configured memory limit are not a guarantee or a measured ceiling on total process memory; the learner connection settings are unchanged. [Preflight evidence](../data/calendar_dimension_preflight.json) records hashes, results and settings.

Thirteen fault cases passed, each starting from the small full-calendar fixture. Creation rejects a duplicated source day/date, noncanonical day label, out-of-range label, NULL day and swapped day labels with unchanged counts. Validation detects an incorrect derived number even when the original 14 fields still match, changed event text, removal of an existing event value, truncation of the final 28 dates, a missing interior day, a duplicate target row and reordered columns. Empty-source creation fails acceptance. These mutations only affect private fixture databases.

To reproduce from the repository root:

```powershell
python validation/preflight_calendar_dimension.py --duckdb "E:/DuckDB/duckdb.exe" --output "data/calendar_dimension_preflight.json"
```

The import setup uses the current local CSV path. The learner SQL reads existing named tables. When core.m5_calendar already exists, run only the query after VALIDATION. Learner acceptance is recorded above; follow [the current step](FIRST_STEP_ZH.md) for the next action.
