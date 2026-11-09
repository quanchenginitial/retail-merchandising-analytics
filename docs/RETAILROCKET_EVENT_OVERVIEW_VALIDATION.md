# Retailrocket event-record business overview

This SQL70 contract was frozen on 9 November 2026 before fixtures or source execution. After accepted SQL69 materialization, the purpose is to establish the volume, identifier reach and recorded time coverage of views, cart additions and transaction events. These descriptive counts establish denominators for later analysis without prematurely defining a funnel or conversion rate.

## Readset and output

[SQL70](../sql/70_analyze_retailrocket_event_overview.sql) is read-only and queries rr_mart.events_enriched using only seven fields: timestamp BIGINT, visitorid BIGINT, event VARCHAR, itemid BIGINT, transactionid BIGINT, event_timestamp_utc TIMESTAMP and event_date_utc DATE. It validates those seven required names and types without asserting their positions or requiring a seven-column full table. The accepted production fact has seventeen columns; the ten category/availability fields are outside this query's readset and are not read or revalidated.

The output is exactly **four rows × ten columns**. Row order is view, addtocart, transaction, TOTAL. All four statuses must be PASS on admitted data.

| Field | Definition |
|---|---|
| event_type | Recorded event label or TOTAL. |
| event_rows | Original event occurrences, including accepted exact duplicates. |
| event_share_pct | That type's share of all event occurrences, rounded to four decimal places; TOTAL is 100.0000. |
| distinct_visitor_ids | Distinct supplied visitor identifiers within the row's population. |
| distinct_item_ids | Distinct supplied item identifiers within the row's population. |
| distinct_transaction_ids | Distinct non-NULL transaction identifiers; view/cart rows are zero under the accepted event rules. |
| first_event_utc | Minimum recorded UTC event timestamp, formatted with six fractional digits and Z. |
| last_event_utc | Maximum recorded UTC event timestamp in the same format. |
| observed_utc_dates | Distinct dates with at least one event in that row's population. |
| check_status | PASS when admission and the row's accepted event count hold; otherwise BLOCKED or FAIL. |

TOTAL distinct identifiers, date counts and extrema are recomputed directly over all source occurrences using grouping sets. They are never obtained by summing distinct counts or date counts from the three event types. The same visitor/item/date can appear in several types. Rounded type shares need not sum to exactly 100.0000; displayed rounding is not a conservation test.

Event share is a share of records, **not visitor conversion**. A visitor ID is not proof of a unique person, transaction rows are not consolidated orders, and distinct transaction IDs are not asserted to be validated orders. Transaction events may contain item-level rows. No deduplication, sessionization, visitor funnel, order consolidation, inventory or monetary conclusion is introduced. The accepted 460 duplicate surplus occurrences are retained. First/last timestamps and represented UTC dates do not prove complete collection on boundary days or uninterrupted collection.

## Admission and invalid inputs

The frozen event population is 2,756,101 rows: 2,664,312 view, 69,332 addtocart and 22,457 transaction records. Admission requires those counts, a nonempty population, exact required field types, accepted duplicate surplus 460, nonnegative valid identifiers, supported integer milliseconds (0–253402300799999), valid event names and transaction-nullability rules. UTC timestamp roundtrip, exact equality to the safely range-guarded make_timestamp_ms(original integer), and date derivation must agree for every row. Exact timestamp equality rejects sub-millisecond corruption that an integer-millisecond roundtrip alone could truncate. Counts of original-five-field tuples establish duplicate surplus; no artificial event identifier is created.

If admission fails, the query still returns the four fixed labels, but every metric is NULL and all four check_status values are BLOCKED. Gated inputs prevent invalid records from producing a plausible business overview. A missing referenced column/table may instead fail during SQL binding. An admitted row whose expected type count is not met is FAIL. SQL70 changes neither input nor session settings.

## Scope-aware independent preflight

The validator reads **events.csv only**. It reuses the frozen SQL54 and SQL63 creation prefixes in a private database, then creates a disposable seven-field rr_mart.events_enriched projection from their original five typed event fields plus make_timestamp_ms(timestamp) and its DATE. The projection is a validation stand-in for SQL70's exact readset, **not a recreation or re-verification of SQL69's seventeen-column fact**. Accepted SQL69 evidence remains the basis for the ten unqueried property fields. No property CSV or category CSV is read; the SQL69 build and earlier full audit suites are not rerun.

Python independently validates and types every original event record, sorts numeric event keys in chunks of at most 50,000 rows, and preserves every occurrence. Per-type and TOTAL statistics use separate identifier/date sets and min/max integer timestamps; TOTAL is accumulated directly from each event. Identifier sets are bounded by the admitted source population and an explicit total entry budget; no all-event list is held. Percentage display is calculated independently with Decimal and four-place half-up rounding. The SQL field is DECIMAL(9,4); DuckDB CLI JSON serializes these values as four-place strings, which the evidence preserves exactly. UTC values are independently derived from an aware UTC epoch plus integer timedelta(milliseconds=...), without float seconds.

A direct private read-only seven-field stream from the projection must match every sorted source occurrence, including duplicate records, NULL/zero transaction IDs, millisecond precision and UTC dates. The full four-by-ten report must match the independent source aggregation. This proves SQL70's readset and overview, while preserving the explicit dependency on accepted SQL69 for the remaining fields.

Focused fixtures test all three event labels, repeated visitors/items/dates across labels (TOTAL distinct counts must be recomputed), transaction NULLs/zero IDs, duplicate occurrences, numeric sorting across chunks, UTC millisecond/date boundaries and rounded record shares. Invalid counts/schema/event rules/UTC fields, including a one-microsecond timestamp mutation, must block all metrics. Extra unqueried columns are allowed and deliberately excluded from admission; missing required columns can produce binding errors.

The real preflight has **three CLI phases**: frozen SQL54/63 prefixes plus the disposable seven-field projection; one read-only SQL70 report; one direct read-only seven-field comparison. Each uses two threads, 1GB memory, 2GB spill and a 120-second timeout. At least 6GB free workspace space and a 5GB private-directory budget are required. Python sort chunks have at most 50,000 events and aggregate identifier sets have at most 4,000,000 entries across type/TOTAL sets; exceeding a bound aborts rather than filters data. Settings are bounds, not measured memory peaks.

The private database hash must remain unchanged across both read-only phases. The event CSV's fresh hash/metadata, pinned dependencies and all 68 historical preflight artifacts must remain unchanged. Private event chunks, database and spills are removed. Real identifiers are processed privately but not logged or uploaded. No learner database or property/category CSV is opened. Public outputs contain only aggregate results, code, methods and evidence.

```powershell
python validation/preflight_retailrocket_event_overview.py --duckdb "E:/DuckDB/duckdb.exe" --output "data/retailrocket_event_overview_preflight.json"
```

Measured results will be appended and saved in [aggregate evidence](../data/retailrocket_event_overview_preflight.json). Learner SQL70 execution follows this assistant preflight. No conversion, validated-order, person-level, causal or monetary claim is made by this overview.

## Executed results

The assistant's single event-only SQL70 preflight completed on 9 November 2026. The read-only overview returned **four rows × ten columns, all four PASS**, with no FAIL or BLOCKED rows. Learner SQL70 execution remains pending. The preceding 8,108-byte frozen method prefix is unchanged, with SHA-256 `e9676f52d45e3446a27d76c0f1d2eaae9d237ca8342a68411ac96046390074bf`.

| Event type | Event rows | Record share % | Distinct visitor IDs | Distinct item IDs | Distinct transaction IDs |
|---|---:|---:|---:|---:|---:|
| view | 2,664,312 | 96.6696 | 1,404,179 | 234,838 | 0 |
| addtocart | 69,332 | 2.5156 | 37,722 | 23,903 | 0 |
| transaction | 22,457 | 0.8148 | 11,719 | 12,025 | 17,672 |
| TOTAL | 2,756,101 | 100.0000 | 1,407,580 | 235,061 | 17,672 |

| Event type | First recorded UTC event | Last recorded UTC event | Represented UTC dates |
|---|---|---|---:|
| view | 2015-05-03T03:00:11.289000Z | 2015-09-18T02:59:47.788000Z | 139 |
| addtocart | 2015-05-03T03:00:04.384000Z | 2015-09-18T02:50:49.834000Z | 139 |
| transaction | 2015-05-03T03:27:21.391000Z | 2015-09-18T02:43:12.017000Z | 139 |
| TOTAL | 2015-05-03T03:00:04.384000Z | 2015-09-18T02:59:47.788000Z | 139 |

Views account for **96.6696% of event records**, cart additions **2.5156%**, and transaction events **0.8148%**. These are record shares, not visitor conversion rates. The **22,457 transaction records** contain **17,672 distinct transaction identifiers**; this establishes the distinction between event rows and identifiers without validating either as an order count. TOTAL visitor/item/date distincts were recomputed directly over the full population, rather than summing across event types. Visitor IDs are not asserted to be distinct people. All **460 accepted duplicate surplus occurrences** remain included.

All three event types have observations on **139 UTC dates**. Their extrema differ, and the collection's first/last dates are partial timestamp boundaries; represented dates do not establish complete or uninterrupted collection. These findings provide the scale and denominators needed for later behaviour analysis, while session, order and conversion definitions remain separate work.

Independent Python validation matched the complete **2,756,101 occurrences × seven fields**: all five original event fields plus the exact UTC timestamp and date. It also matched every field of the four-row overview, including independently rounded Decimal shares and directly accumulated TOTAL distinct sets. The identifier-set accumulator held **3,402,371 entries** across its type/TOTAL sets, within the **4,000,000-entry** budget. No all-event list was held. All nullable transaction IDs and original duplicate multiplicities were preserved.

This was deliberately a **seven-field readset preflight**. Only events.csv was read. Frozen SQL54/63 prefixes and accepted integer UTC derivation created a disposable seven-column validation projection; the production seventeen-column SQL69 fact was not rebuilt or fully reverified. Its ten category/availability fields remain supported by accepted SQL69 evidence. Neither property CSV, category CSV nor learner database was opened, and no previous full audit suite was rerun.

All **three fixture families** passed. Nine synthetic event occurrences across five sort chunks verified repeated identifiers/dates across event types, direct TOTAL distincts, retained duplicates, transaction NULL/zero IDs, UTC boundaries and Decimal record shares. An extra unqueried column was accepted without a full-schema claim. **Twelve invalid subcases** covered empty/wrong-count input, duplicate-count mismatch, invalid identifiers/event/transaction rules, missing or inconsistent UTC values, a one-microsecond timestamp change, a required-field type change and a missing required column. Invalid admitted structures blocked every metric; the missing column produced the documented binding failure. The read-only fixture and real database hashes remained unchanged.

Source selection and numeric chunk sorting took **27.189 seconds**. The three real CLI phases took **7.270 seconds** for event-prefix reconstruction plus the disposable projection, **2.513 seconds** for SQL70, and **45.495 seconds** for the complete independent stream comparison. Each stayed within two threads, 1GB memory, 2GB spill and 120 seconds. Timings exclude hashing and fixtures and are not performance benchmarks.

The preflight created **56 private event chunks**, totalling **96,993,967 bytes**. The private database measured **104,607,744 bytes** before cleanup, and the largest post-phase directory observation was **201,601,711 bytes**, not a continuous peak. All private database, chunk and spill files were removed. The event CSV hash and metadata, **13 pinned dependencies**, and **68 historical preflight files** remained unchanged. Real identifiers were processed privately but were not logged or uploaded.

The [aggregate evidence](../data/retailrocket_event_overview_preflight.json) records report fingerprint `ed621a3b2b89aed8c428d34fc010c57e08ae0ee598ef112aa8c117b11d70aff7`. SQL share values remain DECIMAL(9,4); their four-place JSON strings preserve the CLI's exact serialization. This overview supports subsequent business analysis without claiming visitor conversion, validated orders, inventory, monetary effects or causality.
