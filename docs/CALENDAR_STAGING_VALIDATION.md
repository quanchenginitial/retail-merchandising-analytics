# Calendar typed staging acceptance and preflight

27 October 2026. The learner has completed the [raw-layer checkpoint](RAW_LAYER_CHECKPOINT.md). The learner has now executed [08_stage_calendar.sql](../sql/08_stage_calendar.sql) and supplied a screenshot showing all 13 checks with status PASS. The [learner transcription](../data/calendar_staging_learner_acceptance.json) records schema, row count, dates, NULL preservation and zero round-trip differences. This accepts stg.m5_calendar from screenshot evidence, not a new direct database read.

## Transformation contract

The table keeps the same 14 field names and order: date becomes DATE; wm_yr_wk, wday, month, year and three SNAP flags become INTEGER; weekday, d and the four event fields remain VARCHAR. Event NULLs are preserved. All 1,969 source dates remain, including the calendar dates after the sales training endpoint. No new daily sales observations are created. The source week identifier is cast, not recomputed as a Gregorian week.

Ordinary CREATE TABLE AS SELECT creates the table in one statement, without replacing an existing table. CAST errors stop creation instead of silently introducing NULLs. Some SQL casts can normalise or round convertible text, so the subsequent round-trip comparison is also required. This staging table does not yet enforce primary keys or NOT NULL constraints; core dimension design remains a separate step.

## Acceptance checks

The 13-row result verifies row and column counts; each column's exact name, data type and ordinal position; unique dates/day IDs; required values; full date range; binary SNAP values; expected event NULL counts; and two-way full-record reconciliation. The actual schema is restricted to the current database and target staging table and compared against all 14 expected columns, so missing, extra or mistyped columns fail.

Reconciliation casts the typed fields back to VARCHAR and compares all 14 values against raw.m5_calendar with EXCEPT ALL in both directions. It preserves duplicate multiplicities and NULLs without repeating the forward typed projection. This proves a lossless round trip for this source snapshot's canonical text representation; it is not a general text-normalisation policy. Other valid source formats such as zero-padded integers would require an explicit policy rather than bypassing the difference checks. The comparison uses the current raw table, not a fresh CSV read or snapshot hash.

## Independent assistant verification

[Preflight runner](../validation/preflight_calendar_staging.py) imports the calendar into a disposable :memory: database and executes the unchanged staging script in DuckDB v1.5.5. All 13 checks passed. Raw setup plus staging and checks took 0.659 seconds in this run. The input SHA-256 matched the [recorded source audit](../data/m5_source_audit.json) and was unchanged afterward. The [preflight evidence](../data/calendar_staging_preflight.json) records all results and the SQL fingerprint. No learner database was opened.

To reproduce from the repository root:

```powershell
python validation/preflight_calendar_staging.py --duckdb "E:/DuckDB/duckdb.exe" --output "data/calendar_staging_preflight.json"
```

The production staging SQL reads only database tables; the preflight runner and raw calendar import contain the local CSV path. Adjust those source paths when reproducing elsewhere. For an existing staging table, execute only the VALIDATION query. Follow [the current step](FIRST_STEP_ZH.md) for the learner action. Sales/price typing, core dimensions and daily sales-price coverage remain pending.
