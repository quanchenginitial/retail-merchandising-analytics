# Retailrocket transaction and candidate-basket grain audit

## Frozen method before execution

SQL78 begins the shopping-basket module by checking whether transaction identifiers, visitor/transaction groups and item observations have compatible grains. It is a read-only diagnostic query against the five accepted fields of rr_stg.events: timestamp, visitorid, event, itemid and transactionid. Required types are BIGINT for the four numeric fields and VARCHAR for event. Extra unqueried columns are allowed. No category, availability, UTC-derived field, time cohort, amount, price or source from another dataset is used.

This step measures candidate groups; it does not declare a verified business order key or build a basket table. A candidate basket is the ordered key (visitorid, transactionid) over transaction event records. A transaction identifier may occur with different visitors or at multiple timestamps. Both possibilities are reported, not assumed absent. Distinct visitor IDs are not verified people, and this snapshot cannot establish cross-device identity, cancellations, completed payments, or capture completeness.

All original event occurrences and transaction occurrences are preserved. An exact transaction duplicate means equality of all five original typed fields. A repeated basket-item key means more than one transaction event for (visitorid, transactionid, itemid). Repeat surplus is transaction event rows minus distinct basket-item keys. Nonexact repeat surplus is transaction event rows minus exact transaction duplicate surplus minus distinct basket-item keys; equivalently, distinct transaction five-tuples minus distinct basket-item keys. This diagnostic separates exact repeats from additional observed timestamps for the same candidate basket-item. Neither repeated records nor their surplus estimate purchased quantity. This audit does not decide whether records are instrumentation duplicates, repeated actions or business line items and does not delete any rows.

## Report and checks

The result has twenty-one rows and five columns: check_order, check_name, actual, expected and status. All actual and non-NULL expected values are integers. The thirteen newly measured diagnostics use NULL expected and INFO; a nonzero diagnostic is not automatically a validation failure. Eight stable source/integrity controls use PASS on equality, with FAIL reserved for a reconciliation mismatch after valid source admission.

| Order | Check | Expected/status meaning |
| --- | --- | --- |
| 1 | source_event_rows | 2,756,101 / PASS |
| 2 | required_schema_mismatch | 0 / PASS |
| 3 | invalid_event_rows | 0 / PASS |
| 4 | source_duplicate_surplus | 460 / PASS; duplicates preserved |
| 5 | transaction_event_rows | 22,457 / PASS |
| 6 | distinct_transaction_ids | INFO |
| 7 | visitor_transaction_pairs | INFO; candidate basket count |
| 8 | transaction_ids_multiple_visitors | INFO |
| 9 | transaction_ids_multiple_timestamps | INFO |
| 10 | visitor_transaction_pairs_multiple_timestamps | INFO |
| 11 | transaction_exact_duplicate_surplus | INFO |
| 12 | distinct_basket_item_pairs | INFO |
| 13 | repeated_basket_item_pairs | INFO; count of repeated keys |
| 14 | repeat_basket_item_surplus_rows | INFO; additional event occurrences beyond one per key |
| 15 | nonexact_repeat_surplus_rows | INFO; additional distinct five-tuples beyond one per key |
| 16 | single_item_baskets | INFO; one distinct item, irrespective of event repetitions |
| 17 | multi_item_baskets | INFO; at least two distinct items |
| 18 | max_distinct_items_per_basket | INFO; NULL if there are no transaction groups |
| 19 | basket_partition_difference | single + multi - candidate basket count = 0 / PASS |
| 20 | transaction_row_reconciliation_difference | summed candidate-basket event rows - transaction event rows = 0 / PASS |
| 21 | basket_item_reconciliation_difference | summed candidate-basket distinct-item counts - distinct basket-item keys = 0 / PASS |

Source admission also requires 2,664,312 view and 69,332 addtocart records, all required fields except nontransaction transactionid present, nonnegative numeric IDs, supported nonnegative epoch milliseconds, only the three known event labels, and transactionid present exactly for transaction events. These are the accepted source controls, not newly inferred targets. If required types, values or global source counts fail, all twenty-one labels remain, every actual value is NULL and every status is BLOCKED; static expected controls remain visible, while INFO expectations remain NULL. Missing required tables/columns may fail binding. A valid nonempty fixture population with no transaction events yields zero transaction diagnostics, NULL maximum basket size, thirteen INFO and eight PASS controls. Source admission requires at least one overall event.

No rate, association support/confidence/lift, recommendation effect, statistical significance, monetary value or business improvement is produced. Observed candidate-key agreement would support a subsequent explicit basket definition for this snapshot, not prove that identifier semantics hold in every system or future dataset.

## Bounded independent event-only validation

Only events.csv is read. Its hash, size and metadata must match the existing source audit before and after validation. Existing SQL54 and SQL63 creation prefixes are reused unchanged in a disposable private database to reconstruct rr_raw.events and rr_stg.events; their historical check blocks and old validator main functions are not rerun. No learner database is opened. Existing SQL70 sorting/parsing helpers are reused only for canonical original-field parsing and a bounded external sort, not its UTC output or identifier-set analysis.

Python sorts all source event occurrences in 50,000-row chunks and independently compares the complete 2,756,101 by five-field typed occurrence stream to a read-only sorted SQL projection, including NULLs and duplicate multiplicities. It keeps only transaction tuples for independent diagnostic calculations, with a declared cap of 100,000 retained transaction occurrences; exceeding the cap aborts rather than sampling. Each temporary diagnostic map/set is bounded by that capped population. No global nontransaction visitor/item map, property history or all-pair funnel state is constructed. Independent counters derive all thirteen diagnostics and three reconciliation differences, then compare the complete twenty-one-row report exactly.

Three real CLI phases are fixed in advance: (1) the frozen event import/staging creation prefixes; (2) read-only SQL78; (3) read-only five-field comparison and independent transaction aggregation. Each uses two threads, 1GB memory, 2GB maximum spill and a 120-second timeout. Minimum free space is 8GB, and the private-directory budget is 7GB. Python source scan/sort is separately timed. Directory observations after phases are not continuous peak measurements. The method is frozen before focused fixtures and the one real-source attempt.

Focused fixtures cover a transaction ID shared by different visitors, multiple timestamps within and across candidate baskets, exact duplicate occurrences versus a repeated item at a different timestamp, single/multi-item groups, zero transaction groups, extra unqueried columns, invalid required types/values/counts, and the transaction-retention cap. They verify that diagnostics do not cause automatic deduplication or failure and that invalid admission suppresses all actual metrics. No historical full suites are rerun.

The original source and pinned dependencies must remain unchanged, all seventy-six historical preflight files must remain unchanged, and private database bytes must be identical before and after read-only query/comparison phases. Temporary databases, sorted spools and spills are removed. Public artifacts contain only code, fixed method, aggregate checks and hashes; no actual source event records or visitor/item/transaction identifiers are published or logged. Property files, category_tree.csv, UTC-derived fields, hierarchy and the full enriched fact remain outside this step's verification scope.

```powershell
python validation/preflight_retailrocket_transaction_basket_grain.py --duckdb "E:/DuckDB/duckdb.exe" --output "data/retailrocket_transaction_basket_grain_preflight.json"
```

Measured results will be appended after validation. Assistant preparation and learner execution are recorded separately.

## Executed results

Assistant SQL78 preflight passed at 2026-11-13T02:59:28.861730+00:00 using v1.5.5 (Variegata) d8cdaa33fd. One real-source attempt completed the three declared CLI phases. The twenty-one-row, five-column report contains eight PASS controls and thirteen INFO diagnostics, with no FAIL or BLOCKED rows. Learner execution and screenshot acceptance remain pending.

| check_order | check_name | actual | expected | status |
| --- | --- | --- | --- | --- |
| 1 | source_event_rows | 2756101 | 2756101 | PASS |
| 2 | required_schema_mismatch | 0 | 0 | PASS |
| 3 | invalid_event_rows | 0 | 0 | PASS |
| 4 | source_duplicate_surplus | 460 | 460 | PASS |
| 5 | transaction_event_rows | 22457 | 22457 | PASS |
| 6 | distinct_transaction_ids | 17672 | NULL | INFO |
| 7 | visitor_transaction_pairs | 17672 | NULL | INFO |
| 8 | transaction_ids_multiple_visitors | 0 | NULL | INFO |
| 9 | transaction_ids_multiple_timestamps | 1788 | NULL | INFO |
| 10 | visitor_transaction_pairs_multiple_timestamps | 1788 | NULL | INFO |
| 11 | transaction_exact_duplicate_surplus | 0 | NULL | INFO |
| 12 | distinct_basket_item_pairs | 22323 | NULL | INFO |
| 13 | repeated_basket_item_pairs | 123 | NULL | INFO |
| 14 | repeat_basket_item_surplus_rows | 134 | NULL | INFO |
| 15 | nonexact_repeat_surplus_rows | 134 | NULL | INFO |
| 16 | single_item_baskets | 15029 | NULL | INFO |
| 17 | multi_item_baskets | 2643 | NULL | INFO |
| 18 | max_distinct_items_per_basket | 31 | NULL | INFO |
| 19 | basket_partition_difference | 0 | 0 | PASS |
| 20 | transaction_row_reconciliation_difference | 0 | 0 | PASS |
| 21 | basket_item_reconciliation_difference | 0 | 0 | PASS |

The report retains all 22,457 transaction event occurrences. It observes 17,672 distinct transaction IDs and 17,672 visitor/transaction candidate groups. Transaction IDs occurring with multiple visitors number 0; IDs observed at multiple timestamps number 1,788; candidate groups with multiple timestamps number 1,788. These describe this supplied snapshot and do not verify business order semantics.

Exact duplicate surplus within transaction events is 0. There are 22,323 distinct candidate-basket/item memberships and 123 repeated membership keys. The 134 repeat surplus rows comprise 0 exact repeats and 134 additional distinct observations of existing memberships. These counts are not quantities and no records were deleted. Candidate groups split into 15,029 single-item and 2,643 multi-item groups; the largest has 31 distinct observed items. All three reconciliation differences are zero.

The independent Python source proof compared every one of 2,756,101 original event occurrences across all five queried fields, including NULL transaction IDs and 460 exact duplicate surplus occurrences. It retained only the 22,457 transaction tuples, below the declared 100,000 cap, and independently reconstructed every reported diagnostic and reconciliation. The source split remained 2,664,312 view, 69,332 addtocart and 22,457 transaction occurrences, with 2,733,644 NULL transaction IDs. Only events.csv was read; no property, category-reference, UTC-derived or enriched-fact proof was performed.

Five focused fixture families passed: cross-visitor ID reuse and multiple timestamps with exact/nonexact repeats and single/multi-item groups; extra unqueried columns; seven invalid value/type/count cases that block all actuals while preserving static expectations; transaction-retention-cap rejection; and a valid nonempty population without transactions that retains zero counts and a NULL maximum. Synthetic testing identified DuckDB HUGEINT aggregate JSON serialization as strings; SQL78 explicitly casts admitted actual counts to BIGINT to honor the frozen integer output contract. This correction occurred before the one real-source attempt and did not change the metric definitions.

Measured CLI times were 4.864 seconds for the frozen event import/staging creation prefixes, 0.763 seconds for read-only SQL78, and 14.014 seconds for the complete five-field comparison and independent diagnostic aggregation. Python source scan/sort took 24.093 seconds. All three CLI phases used two threads with 1GB memory/2GB maximum spill and completed inside 120 seconds.

The events.csv hash and metadata, pinned dependencies and all 76 historical preflight artifacts were unchanged. Private database hashes matched before and after both read-only phases. The largest private directory observed after a phase was 162,804,399 bytes, below the 7GB budget; this is not a continuously measured peak. Temporary databases, sorted comparison spools and spills were removed. No learner database was opened, no source records or visitor/item/transaction IDs were published, and no earlier full validation suite was rerun.

The audit supports a subsequent explicit definition of candidate basket membership. It does not establish purchased units, monetary value, meaningful product complements, recommendation uplift or verified order completion. INFO records measurements rather than automatic data failure. Any subsequent basket transformation must preserve the distinction between source occurrences and one membership per candidate basket/item.

Report SHA-256: `a5661f430bd2f8f348a31cc658eb37272f9d0ca77788b2c0c1c262cf96f08301`. Script SHA-256: `48523dd99e2d09fc346bad03dd63a24194870c7c8b82eb48499acd8ba6c71a67`. Validator SHA-256: `304c7fec80cdf1cae98439d9c8f486109716c977a8cb9482db4d1ee8eee865de`. The original 8,477-byte method prefix remains unchanged at `9076cbdb7f345602552be4c30408d59c122c5cd1840ba48d1fbe29889d32d788`.
