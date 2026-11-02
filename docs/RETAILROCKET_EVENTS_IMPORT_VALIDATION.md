# Retailrocket events: first raw import

[SQL54](../sql/54_import_retailrocket_events.sql) imports the audited events file into **rr_raw.events**, isolated from the existing M5 tables. The assistant's bounded preflight passed all **18 checks across five report columns**. Learner execution and screenshot acceptance remain pending. This step establishes a faithful raw copy; it does not define sessions, orders, conversion, RF segments or a deduplication policy.

## Source and import contract

The input is `D:/database/retailrocket/events.csv`: **94,237,913 bytes**, with SHA-256 `3745aa83238b1e6d44d8fda209807899f420084398f94ddf745f3cbcfecbf9e7`. The [streaming source audit](../data/retailrocket_source_audit.json) independently checked the complete CSV's structure and field syntax. The separate [source checks](../data/retailrocket_independent_checks.json) establish observed duplicate multiplicities. These are fingerprints of the supplied local snapshot, not publisher-certified checksums.

The table has exactly five VARCHAR columns in source order: **timestamp, visitorid, event, itemid, transactionid**. The reader specifies its delimiter, quoting, encoding and columns; strict parsing is enabled, ignored errors and missing-column padding are disabled. All observations and strings are retained, including duplicate rows, leading zeros and whitespace. Only the exact empty transactionid field becomes SQL NULL. Required-field empty strings remain available to the missingness checks; no trimming or imputation is applied. Numeric checks inspect text without converting stored values. Raw timestamps remain their original millisecond strings.

The script uses plain CREATE TABLE. If rr_raw.events already exists, import stops rather than replacing or appending to it. Only schema creation is repeatable. A learner who already created the table should run the clearly marked checks query on its own; do not automatically drop a table or rerun only the loading statement.

## Frozen report

The learner report has **18 rows × 5 columns**: check_order, check_name, actual, expected, status. The successful assistant report is below; the machine record stores both actual and expected integer values.

| Check | Actual = expected | Status |
| --- | ---: | --- |
| row_count | 2,756,101 | PASS |
| column_count | 5 | PASS |
| varchar_column_count | 5 | PASS |
| column_sequence_errors | 0 | PASS |
| missing_required_rows | 0 | PASS |
| invalid_timestamp_rows | 0 | PASS |
| invalid_visitorid_rows | 0 | PASS |
| invalid_itemid_rows | 0 | PASS |
| invalid_transactionid_rows | 0 | PASS |
| unexpected_event_rows | 0 | PASS |
| view_event_rows | 2,664,312 | PASS |
| addtocart_event_rows | 69,332 | PASS |
| transaction_event_rows | 22,457 | PASS |
| transactions_missing_id | 0 | PASS |
| null_transactionid_rows | 2,733,644 | PASS |
| source_rows_absent_from_table | 0 | PASS |
| table_rows_absent_from_source | 0 | PASS |
| duplicate_surplus_rows_preserved | 460 | PASS |

The event counts sum to all 2,756,101 rows. Every transaction event has an identifier; the 2,733,644 nontransaction observations have an empty identifier in the source, represented by NULL in the raw table. A transaction event is not automatically a unique or validated order, and a visitor identifier is not a verified person.

Duplicate surplus means total rows minus distinct full five-field tuples. The **460 surplus rows are intentionally retained**; their presence is not an automatic import defect. Both source-to-table and table-to-source comparisons use EXCEPT ALL across every field, so multiplicity and NULL-bearing rows are checked. A set-only comparison could miss lost duplicates. No source row order is promised by a relational table.

## Preflight actually executed

The [validator](../validation/preflight_retailrocket_events_import.py) used DuckDB 1.5.5 in an isolated in-memory database, with two threads, a configured 2GB database memory limit and spills confined to an ignored temporary directory. It opened no learner database, executed no M5 queries or historical analysis suites, and loaded no property or category tables. The single source import plus its checks took **7.558 seconds**; this excludes hashes and synthetic fixtures and is not a performance benchmark or total-process memory guarantee.

Three focused synthetic cases passed:

1. Exact duplicate, optional NULL and leading-zero text preservation; existing-table reimport rejection; deletion of one duplicate produces the intended failed multiplicity checks.
2. Whitespace and required empty strings remain stored unchanged while the appropriate required-field, numeric, event-type and transaction-completeness checks fail.
3. An extra CSV field is rejected by strict parsing rather than skipped.

The real input's size, exact header and hash match the accepted source audit. All 18 report values reconcile to the fixed audit counts and independent duplicate count, and the full five-field source/table multiset comparison finds zero differences in both directions. Source, code and supporting audit hashes were checked again after execution; existing preflight files remained unchanged. Temporary fixture databases, synthetic CSVs and spills were removed. No real source records or identifiers were exported or logged; captured source-error diagnostics are withheld because parsers can quote field contents.

See the [aggregate preflight evidence](../data/retailrocket_events_import_preflight.json) for exact code/dependency hashes, focused cases, timing and preservation checks. Its ordered report fingerprint is `33da069bbaabe2936c14f08dce19a1eacf6322bc79a2d11cd001b3f06ec3bafb`: compact JSON arrays in the five-column order, followed by LF, with integer counts/order and string labels/status.

## Acceptance boundary

PASS means the first raw import and these specified checks agree with the audited source. It does not establish that every recorded event is a distinct real action, that identifiers define reliable order baskets, or that an anonymous visitor is a person. Duplicates require a later explicit policy before behavioral metrics; they are preserved now so that policy remains reviewable.

The next learner action is to run SQL54 in the existing retail_merchandising DBeaver connection and return the complete 18-row, five-column report with every status visible. Typed staging, duplicate handling, event/transaction semantics, time-aware attribute joins and behavioral analysis remain subsequent work. Retailrocket and M5 identifiers remain separate.
