# Retailrocket event timestamp and UTC audit

This SQL64 contract was frozen on 6 November 2026 before executing the audit. [SQL63 typed events](../data/retailrocket_events_staging_learner_acceptance.json) has been accepted. The new step reads **rr_stg.events** without creating or changing any table and prepares a consistent time basis for later daily behaviour analysis.

## Interpretation and exact conversion

The original timestamp column remains a BIGINT count of Unix milliseconds. SQL64 converts it in a query to TIMESTAMP with make_timestamp_ms and verifies exact integer recovery with epoch_ms. No floating-point seconds or division is used. DuckDB documents both operations in its [version 1.5 timestamp functions](https://duckdb.org/docs/1.5/sql/functions/timestamp).

The derived TIMESTAMP is timezone-naive and is interpreted under an explicit **UTC convention**, consistent with DuckDB's distinction between [timestamp types](https://duckdb.org/docs/1.5/sql/data_types/timestamp). Its report text uses YYYY-MM-DDTHH:MM:SS.ffffffZ, where six fractional digits retain the exact millisecond value with trailing microsecond zeros. Appending Z documents this chosen interpretation; it does not change the SQL value into TIMESTAMPTZ or establish the shop's or visitor's local timezone. The query does not change the connection timezone. No daily local-business pattern, session boundary or geographical inference follows from this conversion.

The supported audit range is **0 through 253402300799999 milliseconds**, corresponding to 1970-01-01 through the last millisecond of year 9999. This is a conservative range shared with the independent Python datetime reference, not DuckDB's complete representable timestamp range. Negative values, missing timestamps and values outside this range block conversion. No unsupported BIGINT is passed to make_timestamp_ms. Diagnostics use TRY_CAST so a populated wrong-type column can be reported without an unsafe numeric conversion; the exact five-field typed schema must still pass before any timestamp interpretation is admitted.

The independently recorded prior bounds are **1430622004384** and **1442545187788**, corresponding to **2015-05-03T03:00:04.384000Z** and **2015-09-18T02:59:47.788000Z**, with **139 distinct UTC dates**. These are frozen controls from the [earlier independent source audit](../data/retailrocket_independent_checks.json), not newly discovered expected values selected after this run.

## Admission, dependent controls and observations

The audit first checks the accepted 2,756,101-row count, nonempty input, exact five-column schema/order, missing timestamps, negative timestamps and the supported conversion range. The accepted schema remains timestamp BIGINT, visitorid BIGINT, event VARCHAR, itemid BIGINT, transactionid BIGINT. It does not re-audit unrelated identifier semantics or deduplicate observations.

Conversion is inside a CASE guarded by those prerequisites. If any prerequisite fails, dependent rows 6–18 have NULL actual values and BLOCKED status rather than misleading zero errors or healthy date summaries. Rows 6–9 inspect conversion coverage, NULL results, integer roundtrip and date partitioning. Rows 10–15 require these conversion controls to pass. Finally, INFO rows 16–18 require **all fifteen controls**, including the frozen bounds and date count, to pass. Expected values remain visible for blocked controls; INFO expectations remain NULL.

UTC date partitioning is checked against the exact integer quotient timestamp_ms // 86400000. The epoch of each converted date's midnight must equal that quotient multiplied by 86400000; this avoids floating-point boundary errors. The counts grouped by UTC date must reconcile to all source observations. Every occurrence remains present, including the 460 duplicate surplus records preserved by SQL63.

## Frozen 18-row report

The output has **18 rows × 5 columns**: check_order INTEGER, check_name VARCHAR, actual VARCHAR or NULL, expected VARCHAR or NULL, status VARCHAR. Counts are represented as decimal strings because timestamp text shares the same actual/expected columns. A valid snapshot produces **15 PASS controls and 3 INFO observations**; INFO is descriptive and is not a failed check.

| Order | Check | Expected |
|---:|---|---|
| 1 | event_rows | 2756101 |
| 2 | schema_mismatch | 0 |
| 3 | missing_timestamp_rows | 0 |
| 4 | negative_timestamp_rows | 0 |
| 5 | unsupported_epoch_ms_rows | 0 |
| 6 | converted_rows | 2756101 |
| 7 | conversion_null_rows | 0 |
| 8 | roundtrip_error_rows | 0 |
| 9 | date_partition_error_rows | 0 |
| 10 | min_timestamp_ms | 1430622004384 |
| 11 | max_timestamp_ms | 1442545187788 |
| 12 | first_utc_timestamp | 2015-05-03T03:00:04.384000Z |
| 13 | last_utc_timestamp | 2015-09-18T02:59:47.788000Z |
| 14 | distinct_utc_dates | 139 |
| 15 | daily_rows_difference | 0 |
| 16 | first_date_event_rows | NULL; INFO |
| 17 | last_date_event_rows | NULL; INFO |
| 18 | subsecond_event_rows | NULL; INFO |

unsupported_epoch_ms_rows counts non-NULL values that cannot be parsed as BIGINT or exceed the supported upper bound; negative values have their own control. schema_mismatch counts mismatched or absent column/type positions. first_date_event_rows and last_date_event_rows count observations on the earliest and latest UTC dates. subsecond_event_rows counts original millisecond values not divisible by 1000; it does not count unique timestamps. None of these counts defines sessions, orders, people or conversions.

## Independent bounded validation

The [validator](../validation/preflight_retailrocket_event_time.py) reconstructs the raw and typed event tables using only the frozen SQL54 import prefix and SQL63 creation prefix, without their previous full checks. SQL64 then runs once in an isolated database opened read-only. One further private read-only stream emits each staged timestamp with its converted text, date and roundtrip integer. Python validates every occurrence using an aware UTC epoch plus timedelta(milliseconds=integer), with integer timedelta arithmetic for recovery. No floating-point fromtimestamp or timestamp method is used.

An independent streaming CSV fold computes the complete timestamp bounds, UTC date counts, subsecond count and boundary-date counts directly from events.csv. Those aggregates and the private per-occurrence stage stream must agree, and Python reconstructs the full eighteen-row report independently. No per-event timestamp exports or sorted row files are needed; only bounded date counters and the current record are held. The private database's byte hash is checked before and after the read-only audit and stream. Source file hash/metadata, pinned dependencies and all prior preflight files must remain unchanged.

Small fixtures cover exact millisecond fractions, duplicate occurrences, midnight transitions, epoch zero, the shared upper boundary, and invariance under UTC versus Australia/Sydney session settings. The Python upper-date partition check uses integer day starts plus 86400000, avoiding an attempted year-10000 datetime. Empty input, wrong counts, NULL/negative/unsupported timestamps and populated wrong schema/type fixtures must report blocked dependent metrics without unsafe conversion. Validly converted data with changed expected bounds or date counts must show failed controls and blocked INFO observations.

The fixed resource plan uses two DuckDB threads, 1GB memory, a 2GB spill cap and 120 seconds per CLI phase, with a watchdog on the private stream. Reconstruction, the read-only report and the read-only stream are distinct phases. Settings are not a total-process memory guarantee, and directory sizes are observations rather than continuous peaks. All private databases and spills live under repository tmp and are removed. Other real source CSVs, learner databases and old full audit suites are excluded. Only aggregate evidence, hashes and timing observations are retained publicly.

```powershell
python validation/preflight_retailrocket_event_time.py --duckdb "E:/DuckDB/duckdb.exe" --output "data/retailrocket_event_time_preflight.json"
```

Measured results will be appended and saved in [aggregate evidence](../data/retailrocket_event_time_preflight.json). The observed timestamp range starts and ends within UTC dates: those boundary dates must not be assumed to contain complete observation days. Event extrema do not establish the exact collection start/end, and an absence outside the extract is not evidence of no behaviour. Even 139 represented dates does not prove uninterrupted tracking. Later daily metrics must retain this observation-window limitation; sessionisation, property validity and event-time associations remain separate steps.

## Executed results

The assistant's isolated SQL64 audit completed on 6 November 2026: **18 rows × 5 columns, with 15 PASS controls and 3 INFO observations**. There are no FAIL or BLOCKED rows. Learner execution and screenshot acceptance remain pending. The frozen 8,758-byte method prefix remains unchanged, with SHA-256 `75e3f3d48f9d3b295ff7543c6234c1a16cfc6906c03129fa04559eb25f3e39a3`.

All **2,756,101 event occurrences** converted successfully. Missing, negative or unsupported timestamps, conversion NULLs, millisecond roundtrip differences, date partition errors and daily count differences are zero. The exact bounds remain **1430622004384–1442545187788 milliseconds**, rendered as **2015-05-03T03:00:04.384000Z–2015-09-18T02:59:47.788000Z**, and all **139 UTC dates** match the frozen prior controls. These values describe the observed event timestamps under the stated UTC convention.

The three new descriptive observations are **13,683 events on the first UTC date**, **1,528 on the last UTC date**, and **2,753,264 occurrences with a nonzero millisecond remainder**. Their expected cells are NULL and their status is INFO. These are event-occurrence counts, not unique timestamps, visitors, orders or complete-day activity. Boundary dates still must not be treated as complete collection days; the exact recording start/end and local business timezone remain unknown.

The independent Python source fold and private read-only stream agreed on the complete date-count partition, timestamp bounds and subsecond totals. Python checked **2,756,101 streamed occurrences across four fields** using an aware UTC epoch, integer timedelta arithmetic and exact date boundaries. This validates each streamed conversion; source-to-stage preservation continues to rely on the accepted SQL63 transformation and unchanged reconstruction prefixes, not a newly repeated full-five-field source comparison. The private database byte hash was identical before and after SQL64 plus the stream. No table was changed and no event comparison row files were created or retained.

All **three fixture families** passed: a ten-occurrence precision/midnight/leap-day/duplicate/upper-bound fixture gave the same report and per-occurrence conversions under UTC and Australia/Sydney; **nine invalid-prerequisite subcases** blocked all dependent rows safely; and **three changed-control subcases** blocked every INFO value when an otherwise valid conversion no longer matched the frozen minimum, maximum or date count. Private database hashes remained unchanged throughout the read-only fixture checks.

The independent source fold took **16.159 seconds**. The prefix-only reconstruction, read-only SQL64 report and read-only per-occurrence stream took **4.766**, **0.317** and **31.445 seconds**, respectively. These observations exclude hashing and fixture work and are not performance benchmarks. The private database was **65,548,288 bytes** before cleanup; the largest post-phase directory observation was **65,548,288 bytes**, not a continuously measured peak. The fixed two-thread, 1GB memory, 2GB spill and 120-second phase limits were sufficient. All private databases and spills were removed.

The event CSV hash and metadata, **11 pinned code/evidence dependencies**, and **62 historical preflight files** remained unchanged. No learner database, other real source CSV or prior full audit suite was opened or rerun. The public [aggregate evidence](../data/retailrocket_event_time_preflight.json) has report fingerprint `5293a6a3aedeb9b74821fc20cd6b9dd6d6e0b8555a8bf3d12d71045f26cb70c0` and documents the separate reconstruction, audit and stream phases.

SQL64 establishes a checked UTC analysis convention and exact observed date partitions. It does not establish sessions, validated orders or people, deduplication policy, historical property associations, conversion rates or transaction value. The next action remains the learner's read-only SQL64 execution and screenshot review.
