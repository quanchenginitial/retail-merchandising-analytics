# Retailrocket typed event staging

This SQL63 contract was frozen on 6 November 2026 before executing the new stage. The accepted [SQL54 raw event import](../data/retailrocket_events_import_learner_acceptance.json) preserves 2,756,101 observations in five VARCHAR fields, including 460 surplus exact duplicate occurrences. Its digit/range checks did not establish canonical integer spelling; this stage must establish that condition independently before conversion.

## Purpose and fixed transformation

[SQL63](../sql/63_stage_retailrocket_events.sql) creates **rr_stg.events** from **rr_raw.events**. Columns remain in their original order: timestamp BIGINT, visitorid BIGINT, event VARCHAR, itemid BIGINT, transactionid BIGINT. Only transactionid may be NULL. The original integer timestamp is retained; this step adds no date, timezone, session, order, customer or event identifier. An anonymous visitor ID is not a verified person, and a transaction record is not a validated unique order.

All non-NULL numeric strings must consist of ASCII digits, fit a nonnegative signed BIGINT, and convert back to the exact original VARCHAR spelling. This rejects even an isolated leading-zero value, whitespace, signs, decimals, non-ASCII digits and overflow. Raw NULLs in required fields and non-NULL empty transaction IDs are invalid. Exact roundtrip proves injectivity within each numeric field: two accepted spellings cannot collapse into one integer. No separate expensive numeric-alias grouping is needed, and no identity repair or recoding is performed.

The creation guard requires the exact five-column VARCHAR source schema and order; the accepted row, three-event, NULL-ID and duplicate-surplus counts; nonempty source; and zero value-contract violations. Event names remain exactly view, addtocart or transaction. Transaction IDs must be present exactly for transaction rows, which is a frozen condition of this observed snapshot, not a universal e-commerce rule. Raw type/order mismatches are rejected even when otherwise valid values could be cast. Raw values are projected to VARCHAR for diagnostics, while the actual schema is checked separately.

The accepted baselines are 2,664,312 view observations, 69,332 addtocart observations, 22,457 transaction observations, 2,733,644 NULL transaction IDs and 460 duplicate surplus occurrences. A surplus is total rows minus distinct complete five-field tuples, including NULL-bearing tuples. All repetitions remain present; these are not automatically classified as erroneous tracking or removed. No unique event key or database primary-key/NOT-NULL constraints are declared.

## Failure and rerun behavior

Plain CREATE TABLE protects an existing destination. A singleton aggregate guard is LEFT JOINed to the source; an empty source therefore still produces an error-bearing row. Each output column uses the guarded CASE, and invalid input fails the atomic CREATE TABLE AS statement without leaving an empty or partial target. The preceding CREATE SCHEMA IF NOT EXISTS may leave the schema, so whole-script rollback is not claimed.

If the table already exists, execute only the query after **-- CHECKS: if rr_stg.events already exists, run only the query below.** The checks inspect stored data without rebuilding it. Future appends, deduplication policy, sessions, transaction grouping, historical properties, event-time joins and behavioural metrics remain separate steps.

## Frozen 20-row report

The output has **20 rows and five columns**: check_order, check_name, actual, expected, status. All controls should PASS for the accepted snapshot.

| Order | Check | Expected |
|---:|---|---:|
| 1 | staging_rows | 2,756,101 |
| 2 | column_count | 5 |
| 3 | schema_mismatch_count | 0 |
| 4 | missing_required_rows | 0 |
| 5 | negative_numeric_rows | 0 |
| 6 | unexpected_event_rows | 0 |
| 7 | event_id_mismatch_rows | 0 |
| 8 | view_rows | 2,664,312 |
| 9 | addtocart_rows | 69,332 |
| 10 | transaction_rows | 22,457 |
| 11 | null_transactionid_rows | 2,733,644 |
| 12 | duplicate_surplus_rows | 460 |
| 13 | raw_rows | 2,756,101 |
| 14 | raw_value_violations | 0 |
| 15 | raw_schema_mismatch | 0 |
| 16 | raw_duplicate_surplus | 460 |
| 17 | raw_only_rows | 0 |
| 18 | staging_only_rows | 0 |
| 19 | raw_null_transactionid_rows | 2,733,644 |
| 20 | source_contract_violations | 0 |

raw_value_violations counts raw observations failing any field/event-ID condition, not a sum of overlapping errors. raw_schema_mismatch and source_contract_violations are 0/1 indicators. The two full multiset comparisons cast the staged integers back to their original VARCHAR representation and use EXCEPT ALL in both directions; they preserve all five fields, NULLs and duplicate multiplicities. A same-count tuple change must still fail these checks.

## Bounded independent validation

The [validator](../validation/preflight_retailrocket_events_staging.py) reconstructs rr_raw.events using only the frozen SQL54 import prefix, then runs SQL63 once in a private temporary DuckDB database. It reads only events.csv; the category, property and M5 sources, learner database and old full audit suites are excluded. Established file hash and metadata are compared before and after, and dependency hashes and all existing preflight evidence must remain unchanged.

Independent Python references test small synthetic records, complete typed tuples and full report values. Fixtures cover duplicate preservation and duplicate loss, a same-count changed tuple, a changed existing destination protected from a second CREATE, and invalid raw input including isolated leading zeros, numeric aliases, overflow, whitespace, NULL/empty required values, event-ID inconsistency, wrong counts, empty source and populated wrong schema/order. Rejected creation must leave no target and preserve source tuples. Synthetic fixtures use invented identifiers only.

For the real source, Python reads CSV independently, validates canonical spelling, and sorts chunks of at most 50,000 complete text tuples. It writes those chunks only inside the private temporary directory. A bounded heap merge produces the sorted original multiset. Separate private DuckDB CSV streams project the raw table and staged table into the same five VARCHAR fields, coalescing only NULL transaction IDs to the source's exact-empty representation, and sort those same text expressions. Python compares every tuple in order against the merged source, including repeated records and NULL/empty correspondence. This is a complete row-by-row comparison, not a sample or hash-only equality. Python independently derives event, NULL and duplicate counts and verifies the aggregate report.

Private source comparison chunks, database files and spills contain real records temporarily and are removed at completion; no row identifiers or histories are printed, saved in public evidence or uploaded. Evidence explicitly distinguishes these private temporary spools from public exports. Only aggregate checks, resource observations and file fingerprints are retained.

DuckDB uses two threads, a 1GB memory setting, a 2GB spill limit and a 120-second timeout for each CLI phase. One phase performs import, guarded staging and checks; two subsequent read-only phases stream the raw and staged comparisons. The source sorter caps chunk size at 50,000 tuples. Settings are not a total-process memory guarantee. Directory sizes are post-phase observations rather than continuous peaks. A watchdog bounds streaming phases even if stdout blocks. All private files stay under the repository tmp directory and are removed on completion.

```powershell
python validation/preflight_retailrocket_events_staging.py --duckdb "E:/DuckDB/duckdb.exe" --output "data/retailrocket_events_staging_preflight.json"
```

Measured outcomes will be appended and recorded in [aggregate evidence](../data/retailrocket_events_staging_preflight.json). This step prepares typed events for subsequent behaviour analysis; it does not itself establish conversion, sessions, order counts, customer identities or transaction value.

## Executed results

The assistant's isolated SQL63 preflight completed on 6 November 2026: **20 rows × 5 columns, all 20 PASS**. Learner execution and screenshot acceptance remain pending. The frozen 8,088-byte method prefix is unchanged, with SHA-256 `1eff15c9b102fa2196065f3065d61459e69efe110a0e021d2f4dc14f157641ed`.

The typed table retains **2,756,101 observations in five columns**: timestamp, visitorid, itemid and nullable transactionid are BIGINT; event remains VARCHAR in its original third position. All **2,664,312 view**, **69,332 addtocart**, **22,457 transaction** and **2,733,644 NULL transaction-ID** observations are preserved. Both raw and staged duplicate surplus counts remain **460**. Raw and staged full-five-field multiset differences, schema/value/required-field/negative-value/event-ID discrepancies and the source-contract indicator are zero. Every non-NULL numeric source string passed exact canonical roundtrip; no identity normalisation was needed.

The independent Python parser checked source spelling and aggregate counts. Its private external sort produced **56 chunks**, each with at most 50,000 tuples, totalling **96,993,967 bytes**. Two independent comparison streams each matched **2,756,101 complete five-field tuples**, including all duplicate occurrences and NULL/empty correspondence: the raw stream confirmed original observations remained unchanged, and the staged stream confirmed exact converted values. This was a complete ordered multiset comparison, not sampling or hash-only equality. Real comparison files existed only inside the private temporary directory and were removed; no identifiers or event histories entered public artifacts or logs.

All **three fixture families**, including **21 invalid-input rejection subcases**, passed. A seven-row fixture used four two-row-capacity chunks and independently checked lexical timestamp ordering with 10 before 2; both actual CLI comparison streams preserved this order, NULLs and duplicates. Canonical zero and maximum BIGINT were retained. An isolated leading-zero value and a numeric-alias pair were rejected. Populated wrong-type/order examples isolated schema refusal. A same-count changed staged tuple and a deleted duplicate occurrence failed the full comparisons; a second CREATE preserved the deliberately changed destination. Rejected creation left no target and preserved raw inputs.

One real CLI phase for the SQL54 import prefix, SQL63 creation and its checks took **17.159 seconds**. The independent source sort took **18.92 seconds**; the subsequent raw and staged streaming comparisons took **9.845** and **9.189 seconds**, respectively. These observations exclude hashing and fixture work and are not performance benchmarks. The private database was **65,286,144 bytes** before cleanup. The largest post-phase private-directory observation was **162,280,111 bytes**, not a continuously measured peak. The fixed 1GB memory setting, 2GB spill cap, two threads and 120-second per-CLI timeout were sufficient. All private databases, spills and comparison chunks were removed.

The event source hash and metadata, **8 pinned code/evidence dependencies**, and **61 historical preflight files** remained unchanged. Only events.csv was read among real input sources. The learner database, property/category/M5 sources and prior full audit suites were not opened or rerun. The public [aggregate evidence](../data/retailrocket_events_staging_preflight.json) has report fingerprint `df201fe6fcd54779af3b9abdcfd8fa1d0e9ab16dd1ce9d948ba4dc0757960fc0`.

The result establishes typed event observations with preserved source identity and multiplicity. It does not establish a deduplication policy, unique event key, UTC dates, sessions, validated orders/persons, event-time property associations, conversion rates or monetary metrics. Learner SQL63 execution remains the next step.

## Learner screenshot acceptance — 6 November 2026

The learner supplied the SQL63 DBeaver result on 6 November 2026 (Australia/Sydney). All **20 rows × 5 columns, 100 report fields** are fully visible and match: **60 integer values**, **20 complete check names** and **20 PASS statuses**. The five column headers are also complete. The long row-19 label raw_null_transactionid_rows is fully visible; no names or values were cropped, reconstructed or inferred. See the [learner acceptance record](../data/retailrocket_events_staging_learner_acceptance.json).

The accepted report confirms **2,756,101 staged observations and five correctly typed columns**. All **2,664,312 view**, **69,332 addtocart**, **22,457 transaction** and **2,733,644 NULL transaction-ID** observations are preserved. Both raw and staged duplicate surplus counts remain **460**. Schema, required-field, negative-value, event-ID, raw-value and source-contract controls pass; the two complete five-field multiset differences are zero. This verifies the observed snapshot's type conversion and preserved multiplicity rather than implementing a deduplication policy or declaring a unique event key.

The complete ordered report fingerprint is `df201fe6fcd54779af3b9abdcfd8fa1d0e9ab16dd1ce9d948ba4dc0757960fc0`, matching the separate assistant preflight. No source CSV, learner database, SQL preflight or fixture was reopened or rerun for acceptance. The screenshot was not copied to the repository, and no source identifiers or event histories were published. Frozen SQL, validator, preflight and dependencies are unchanged; every previous method byte, including historical learner-pending statements, is preserved. This append establishes the current learner-accepted status.

The original numeric timestamp remains an integer in this stage. Epoch-unit interpretation, UTC/date conversion, day-boundary validation and historical-property joins still require subsequent checks. Sessions, validated orders or people, conversion rates, monetary measures and duplicate-handling policy are not established by this acceptance. Screenshot evidence does not constitute a fresh direct inspection of the persistent database or a test of learner understanding.
