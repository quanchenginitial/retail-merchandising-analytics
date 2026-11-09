# Retailrocket named property observation time audit

This SQL66 contract was frozen on 9 November 2026 before execution. It follows accepted [SQL65 named observations](../data/retailrocket_item_state_observations_learner_acceptance.json). The purpose is to establish an exact UTC analysis convention for the retained categoryid and available histories before later temporal modelling.

## Scope and interpretation

[SQL66](../sql/66_audit_retailrocket_item_state_time.sql) is a read-only query of **rr_stg.item_state_observations**. The expected five-column schema is timestamp BIGINT, itemid BIGINT, property VARCHAR, value VARCHAR and source_file VARCHAR, in that order. It reads all **2,291,853 selected observations**, including **788,214 categoryid** and **1,503,639 available** records. It creates no table or datetime column and changes no setting. Other opaque properties, event records and category references do not participate.

The original timestamp is an integer count of Unix milliseconds. As in the accepted [event-time audit](RETAILROCKET_EVENT_TIME_VALIDATION.md), make_timestamp_ms converts the integer directly and epoch_ms must recover it exactly. UTC date partitioning must agree with timestamp_ms // 86400000, using integer day starts rather than floating-point seconds. The SQL TIMESTAMP value remains timezone-naive and is interpreted by the stated UTC convention. Text uses YYYY-MM-DDTHH:MM:SS.ffffffZ, preserving the exact milliseconds with trailing microsecond zeros. The Z suffix expresses that convention; it does not identify the retailer's local timezone or turn the SQL value into TIMESTAMPTZ.

The conservative supported range is **0 through 253402300799999 milliseconds**, the shared Python/DuckDB audit interval from the epoch through the last millisecond of year 9999. This is not DuckDB's full timestamp range. CASE guards prevent unsupported values from reaching make_timestamp_ms. TRY_CAST permits diagnostic counts for a populated wrong-type timestamp column while exact schema admission still fails.

This selected population's extrema and represented dates are **new descriptive observations**. They are not assigned expected values from the full property log or from events. Global selected-history date coverage does not establish each property's or each item's coverage, a complete collection period, state validity, update frequency or an effective-from boundary. Property observations must not automatically be interpreted as precisely timed business changes.

## Admission and report

Admission requires nonempty input, the exact expected row count and schema, no missing/negative/unsupported timestamps, and both frozen property counts. Controls 1–5 and 11–12 remain direct diagnostics. If admission fails, derived controls 6–10 and all INFO rows have NULL actual values and BLOCKED status. Conversion coverage, NULLs, integer recovery and date partitioning are controls 6–9; daily reconciliation at control 10 additionally requires these conversion checks to pass. Every INFO value requires all twelve controls to pass.

The output has **20 rows × 5 columns**: check_order INTEGER, check_name VARCHAR, actual VARCHAR or NULL, expected VARCHAR or NULL, and status VARCHAR. Counts share text columns with UTC timestamps. Healthy input produces **12 PASS controls and 8 INFO observations**. The eight INFO expected cells are NULL; descriptive values are not failures or newly fitted pass targets.

| Order | Check | Expected |
|---:|---|---|
| 1 | observation_rows | 2291853 |
| 2 | schema_mismatch | 0 |
| 3 | missing_timestamp_rows | 0 |
| 4 | negative_timestamp_rows | 0 |
| 5 | unsupported_epoch_ms_rows | 0 |
| 6 | converted_rows | 2291853 |
| 7 | conversion_null_rows | 0 |
| 8 | roundtrip_error_rows | 0 |
| 9 | date_partition_error_rows | 0 |
| 10 | daily_rows_difference | 0 |
| 11 | categoryid_rows | 788214 |
| 12 | available_rows | 1503639 |
| 13 | min_timestamp_ms | NULL; INFO |
| 14 | max_timestamp_ms | NULL; INFO |
| 15 | first_utc_timestamp | NULL; INFO |
| 16 | last_utc_timestamp | NULL; INFO |
| 17 | distinct_utc_dates | NULL; INFO |
| 18 | first_date_observation_rows | NULL; INFO |
| 19 | last_date_observation_rows | NULL; INFO |
| 20 | subsecond_observation_rows | NULL; INFO |

unsupported_epoch_ms_rows counts non-NULL timestamps unparseable as BIGINT or exceeding the upper audit limit; negative timestamps have their own control. schema_mismatch counts mismatched or absent name/type positions. Boundary-date counts count all selected occurrences on their earliest/latest represented UTC dates. subsecond_observation_rows counts occurrences with timestamp_ms % 1000 <> 0, not distinct timestamps. All original observations remain intact.

## Independent bounded preflight

The [validator](../validation/preflight_retailrocket_item_state_time.py) reuses the frozen SQL64 integer Python datetime reference: an aware UTC epoch plus timedelta(milliseconds=integer), with exact integer timedelta recovery. It independently scans both property CSVs, selects only exact categoryid/available names and folds every selected timestamp into bounded date counters. Full raw per-part and selected per-property counts are independently reconciled. No source identifiers or property values are exported or logged.

The source audit reads only item_properties_part1.csv and item_properties_part2.csv. An isolated database reconstructs the raw table using only the frozen SQL56 import prefix, then the selected typed table using only the frozen SQL65 creation prefix. It does not rerun prior full checks or selected multiset comparisons. Source-to-stage value and provenance preservation rely on accepted SQL65 and unchanged prefixes. SQL66 runs once with a read-only database connection, followed by one private read-only four-field stream: original timestamp, converted UTC text, date and recovered integer. Python verifies every streamed conversion and compares the complete date partition and timestamp aggregates to its independent selected-source fold. The resulting twenty-row report must also match the independent reference.

The private database byte hash must remain unchanged across the read-only report and stream. Both source hashes and metadata, pinned code/evidence dependencies and all prior preflight files must remain unchanged. No learner database, event CSV, category CSV, source-row comparison chunks or persistent record export is used. The temporary database and spills are removed; public evidence contains only aggregate results, hashes and resource observations.

Fixtures cover epoch zero, millisecond fractions, duplicate occurrences, midnight boundaries, leap day and the shared upper limit. Reports and per-occurrence conversions must agree under UTC and Australia/Sydney session settings without SQL66 changing the session. Invalid input count, empty input, NULL/negative/unsupported timestamps and populated wrong schema/type/order must block derived controls safely. Incorrect categoryid or available counts must also block conversion and every INFO value, including when the total observation count still matches. Read-only fixture database hashes must stay unchanged.

The fixed plan has four real CLI phases: full raw prefix reconstruction; selected typed prefix reconstruction; the read-only SQL66 report; the read-only conversion stream. Each uses two threads, 1GB memory, a 2GB spill limit and a 120-second timeout, with a watchdog on the stream. At least 6GB workspace free space is required; the private directory budget is 5GB. Resource settings do not guarantee a total-process memory cap. Directory sizes are post-phase observations rather than continuous peaks. The independent Python two-file fold is timed separately and keeps date counters, not a full row collection.

```powershell
python validation/preflight_retailrocket_item_state_time.py --duckdb "E:/DuckDB/duckdb.exe" --output "data/retailrocket_item_state_time_preflight.json"
```

Measured results will be appended and recorded in [aggregate evidence](../data/retailrocket_item_state_time_preflight.json). This audit does not establish effective-date intervals, latest-known state, event-time matches, inventory quantities, conversion rates or causal effects. The next work will use the checked time convention while explicitly defining historical-state assumptions.

## Executed results

The assistant's isolated SQL66 audit completed on 9 November 2026: **20 rows × 5 columns, with 12 PASS controls and 8 INFO observations**. There are no FAIL or BLOCKED rows. Learner SQL66 execution and screenshot acceptance remain pending. The frozen 8,346-byte method prefix remains unchanged, with SHA-256 `19cfe93e4e12226be16c057190d1b1b9c3cc54c8c0be49b0db74fc1dca4f6c98`.

All **2,291,853 named-property observations** converted successfully: **788,214 categoryid** and **1,503,639 available** occurrences. Missing, negative or unsupported timestamps, conversion NULLs, millisecond roundtrip differences, date partition errors and daily reconciliation differences are all zero. The table's schema and the independently selected per-property populations match the accepted stage.

The eight new INFO observations have NULL expectations:

| Observation | Measured value |
|---|---|
| Minimum timestamp milliseconds | 1431226800000 |
| Maximum timestamp milliseconds | 1442113200000 |
| First UTC timestamp | 2015-05-10T03:00:00.000000Z |
| Last UTC timestamp | 2015-09-13T03:00:00.000000Z |
| Distinct represented UTC dates | 18 |
| First-date observations | 446,582 |
| Last-date observations | 93,764 |
| Observations with nonzero millisecond remainder | 0 |

These measurements describe the combined selected history. They do not establish per-property or per-item date coverage, a complete collection period, the retailer's local business timezone, update cadence, exact business change times or validity intervals. None was borrowed from the full property log or event bounds and retrospectively made a pass target.

The independent Python scan examined both source files, reconciled **20,275,902 raw records** and selected **2,291,853 observations**. The source part counts remain **10,999,999** and **9,275,903**, with selected part counts **1,243,692** and **1,048,161**. Python's aware UTC epoch and integer timedelta arithmetic matched every one of the **2,291,853 streamed occurrences across four fields**. The full date partition, extrema, subsecond count and twenty-row report agree with the independent selected-source fold. Source-to-stage value/provenance preservation relies on accepted SQL65 and unchanged reconstruction prefixes; this audit does not repeat the earlier full five-field multiset comparisons.

All **three fixture families** passed. A ten-occurrence precision, midnight, leap-day, duplicate and upper-bound fixture produced identical reports and conversions under UTC and Australia/Sydney sessions. **Nine invalid-prerequisite subcases** safely blocked derived metrics. **Three property-count mismatch subcases**, including a changed category/availability mix with unchanged total count, blocked conversion and all eight INFO values. The private database byte hashes remained identical throughout each read-only fixture audit and the real audit/stream.

The independent two-source fold took **22.012 seconds**. Full raw and selected typed prefix reconstruction took **24.043** and **10.368 seconds**. The read-only SQL66 report and per-occurrence stream took **0.296** and **17.890 seconds**. These observations exclude hashing and fixture work and are not performance benchmarks. The four CLI phases stayed within the fixed two-thread, 1GB memory, 2GB spill and 120-second per-phase limits.

The private database was **442,773,504 bytes** before cleanup; the largest post-phase private directory observation was **442,773,504 bytes**, not a continuous peak. Every temporary database and spill was removed. No per-observation comparison files or source-record exports were created. The database hash before and after the read-only real work is identical.

Both property source hashes and metadata, **13 pinned code/evidence dependencies**, and **64 historical preflight files** remained unchanged. No learner database, event/category CSV or historical full comparison suite was opened or rerun. The [aggregate evidence](../data/retailrocket_item_state_time_preflight.json) records report fingerprint `4212b9cdd85528fc56905cb6fb1574940bb70f8891b9ad0c474c2ca30520d7fa` and date-partition fingerprint `caf271d84a26b0ab3b1e30e0600c0bf9aed6e06b17c8a817881210baeadcdb36`.

SQL66 establishes a checked time interpretation for the selected observation history. It does not create effective intervals, choose latest-known states, associate events, repair category references or establish inventory, conversion or monetary outcomes. The next action remains the learner's read-only SQL66 execution and screenshot review.

## Learner screenshot acceptance — 9 November 2026

The learner supplied the SQL66 DBeaver result on 9 November 2026 (Australia/Sydney). All **20 rows × 5 columns, 100 fields** are completely visible and match: **12 PASS controls and 8 INFO observations**, all twenty complete labels, both full UTC strings and all eight NULL expectations. No labels or values were cropped or reconstructed. See the [learner acceptance record](../data/retailrocket_item_state_time_learner_acceptance.json).

The visibility accounting is **20 INTEGER row orders + 30 digit-only VARCHAR actual/expected values + 2 UTC timestamp strings + 8 NULL expectations + 20 labels + 20 statuses = 100 fields**. The acceptance retains numeric-looking actual/expected cells as strings, both timestamps with all six fractional digits and Z suffix, and displayed [NULL] expectations as JSON null. The complete ordered report fingerprint is `4212b9cdd85528fc56905cb6fb1574940bb70f8891b9ad0c474c2ca30520d7fa`.

The accepted report confirms lossless conversion of **2,291,853 selected observations**, including **788,214 categoryid** and **1,503,639 available** rows. Missing/negative/unsupported timestamps, conversion NULLs, millisecond roundtrip, date-partition and daily-reconciliation discrepancies are zero. The INFO endpoints are **1431226800000–1442113200000 milliseconds**, rendered as **2015-05-10T03:00:00.000000Z–2015-09-13T03:00:00.000000Z**. The combined history has **18 represented UTC dates**, **446,582 observations on the first date**, **93,764 on the last date**, and **0 observations with a nonzero millisecond remainder**. All eight INFO expectations remain NULL.

These values describe the combined selected history, not per-item or per-property coverage, continuous collection, complete catalogue snapshots, a fixed update cadence or exact real-world state-change times. UTC is the stated analysis convention, not evidence of the retailer's local timezone. The prior 167 unmatched category-property observations remain unresolved; this audit performs no reference lookup or repair.

No source CSV, learner database, SQL preflight or fixture was opened or rerun for acceptance. No screenshot, source identifiers or property histories were copied to the repository. Frozen SQL, validator, preflight and dependencies remain unchanged. All **12,914 prior method bytes**, including the **8,346-byte frozen contract prefix** and historical learner-pending statements, are preserved byte for byte; this appended record establishes current learner acceptance.

This read-only audit creates no persistent interval table, real-world validity claim, latest-state selection, event association, inventory estimate, conversion rate or monetary outcome. Screenshot evidence remains separate from direct database inspection and does not test conceptual understanding. Subsequent historical-state work must state its observation-based assumptions explicitly.
