# Calendar import and validation checkpoint

27 October 2026. The learner's DBeaver screenshot confirms database retail_merchandising, 1,969 calendar rows, 14 columns, 14 VARCHAR columns, 1,969 distinct day IDs and dates from 2011-01-29 through 2016-06-19. The earlier connection screenshot confirmed DuckDB v1.5.5. Physical file path and full source equality were not established by these screenshots.

## Detailed audit accepted from learner evidence

The subsequent learner screenshot shows all 17 audit rows with status PASS. In particular, source_only_rows and table_only_rows are both zero. Source/table counts are both 1,969, distinct weeks are 282, event_1_nulls is 1,807 and event_2_nulls is 1,964. All other error counts are zero. The [screenshot transcription](../data/calendar_learner_acceptance.json) records these displayed results without publishing the screenshot itself. This is learner-provided execution evidence, not a new direct inspection of the persistent database.

[03_audit_calendar.sql](../sql/03_audit_calendar.sql) is one read-only query. Its 17 output rows cover source/table counts, missing core values, invalid or duplicate dates and IDs, exact day/date mapping, calendar attributes, source week-code shape/count, SNAP values, paired event missingness, expected event NULL counts and two-way full-row reconciliation.

Source reconciliation uses EXCEPT ALL across all 14 canonical columns in both directions. It preserves duplicate multiplicities and treats corresponding NULLs consistently. The query compares against the current CSV; it does not recompute the historical snapshot hash. Week codes are M5 source codes, not reconstructed Gregorian week numbers.

## Independent assistant verification

The unchanged source passed all 17 checks in an in-memory DuckDB v1.5.5 database. Five synthetic mutations were each applied to a fresh disposable table and detected: one duplicate row, one removed row, a NULL SNAP value, an invalid date and a changed non-null event name. The event-name test preserves row count and missingness, exercising the need for full-value reconciliation. These are engineering fixtures, not business anomalies or learner results.

[Verification evidence](../data/calendar_audit_preflight.json) records the baseline results, expected fault diagnostics and SQL fingerprint. [Test runner](../validation/test_calendar_audit.py) uses only Python's standard library and an installed DuckDB CLI:

```powershell
python validation/test_calendar_audit.py --duckdb "E:/DuckDB/duckdb.exe" --output "data/calendar_audit_preflight.json"
```

The SQL files currently reference the learner's existing M5 source directory. Adjust source paths when reproducing elsewhere. Every test database is :memory:; no learner database or raw file is changed. Six passing cases do not imply exhaustive test coverage.

The learner's detailed calendar check is now accepted. The next step is [sales raw import and basic checks](../sql/04_import_sales.sql). Sales and prices have not yet been imported into the learner database as part of this workflow.
