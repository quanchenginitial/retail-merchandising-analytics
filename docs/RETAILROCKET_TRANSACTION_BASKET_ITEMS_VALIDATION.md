# Retailrocket candidate basket-item membership build

## Frozen method before execution

SQL79 turns the accepted SQL78 transaction-grain diagnostics into a reusable candidate basket-item membership table. It reads the original five typed fields of rr_stg.events only and creates rr_mart.transaction_basket_items. This step does not mine associations, estimate quantities/revenue, validate business orders or infer dates from transaction IDs.

The candidate basket key is (visitorid, transactionid), and membership adds itemid. The destination has exactly six BIGINT columns, in order: visitorid, transactionid, itemid, first_timestamp_ms, last_timestamp_ms, source_event_rows. Each transaction event contributes to the source_event_rows count of its membership. first_timestamp_ms and last_timestamp_ms are the minimum and maximum observed event times for that particular basket-item key, not basket-level dates, confirmed order boundaries or an observation of actual purchasing duration. Repeated item observations are summarized with their occurrence counts and time bounds; no original rr_stg.events records are changed or deleted. No actual visitor/item/transaction identifiers are published.

The accepted source has 2,756,101 events, including 2,664,312 views, 69,332 addtocart and 22,457 transaction records, with 460 exact duplicate surplus occurrences overall. SQL78 measured 22,323 distinct candidate-basket/item memberships, 17,672 candidate baskets, 123 repeated membership keys and 134 additional observations beyond one per membership. Candidate baskets split into 15,029 single-item and 2,643 multi-item groups, with at most 31 distinct items. These are fixed construction controls now supported by SQL78 learner acceptance, not newly predicted results. SQL78 found no exact transaction duplicate surplus, but the transformation retains exact duplicates in source_event_rows if they occur in a valid synthetic population; it never equates observation counts with purchased units.

## Guarded creation and audit

CREATE SCHEMA IF NOT EXISTS is allowed for rr_mart. Destination creation uses plain CREATE TABLE AS, without OR REPLACE or IF NOT EXISTS. An existing destination causes failure and is not overwritten. The source guard checks the five required field types, known labels, nonnegative supported epoch milliseconds/IDs, transactionid present exactly for transaction records, accepted source counts and duplicate surplus, and all accepted grouped membership/basket controls. Extra unqueried source columns are allowed.

The guarded SELECT begins from a single guard row LEFT JOINed to grouped memberships. Its WHERE keeps an invalid guard even if there are no source rows or no transaction groups, and CASE error() prevents a destination from being created. A valid empty transaction subset in focused fixtures can produce an empty table; the real snapshot expects 22,457 transaction records. Missing required tables/columns may fail binding. The CREATE TABLE statement is atomic: invalid inputs must leave no destination table. A schema may exist after the failure, but no partial membership relation may remain. Rerunning the full script against an existing destination must fail without changing source or destination data. To recheck a completed build, run only the marked CHECKS query.

The audit has twenty-one rows and five columns: check_order, check_name, actual, expected and status. All production checks are expected to PASS. Actual and expected counts are BIGINT; the empty-transaction fixture uses NULL for maximum size, with NULL-aware equality. FAIL means a check differs; the audit does not suppress measured discrepancies. Successful reporting does not prove business order semantics.

| Order | Check | Expected |
| --- | --- | --- |
| 1 | source_event_rows | 2,756,101 |
| 2 | source_schema_mismatch | 0 |
| 3 | source_invalid_event_rows | 0 |
| 4 | source_duplicate_surplus | 460 |
| 5 | source_transaction_rows | 22,457 |
| 6 | source_contract_violations | 0 |
| 7 | membership_rows | 22,323 |
| 8 | column_count | 6 |
| 9 | schema_mismatch | 0 |
| 10 | missing_or_invalid_rows | 0 |
| 11 | duplicate_key_surplus | 0 |
| 12 | candidate_baskets | 17,672 |
| 13 | source_event_rows_sum | 22,457 |
| 14 | repeated_memberships | 123 |
| 15 | repeat_surplus_rows | 134 |
| 16 | single_item_baskets | 15,029 |
| 17 | multi_item_baskets | 2,643 |
| 18 | max_distinct_items_per_basket | 31 |
| 19 | source_only_memberships | 0 |
| 20 | table_only_memberships | 0 |
| 21 | basket_partition_difference | 0 |

The two directional EXCEPT ALL checks compare all six fields, not just keys. They detect absent/extra memberships, changed occurrence counts and changed first/last item timestamps. Structural checks additionally require unique membership keys, non-NULL nonnegative IDs, positive source_event_rows, supported timestamps with first <= last, exactly six columns in the declared order and BIGINT types. Summed occurrence counts must restore the original transaction total. Basket counts use distinct membership item IDs and do not multiply by repeated observations.

## Independent bounded event-only proof

Only events.csv is read. Its hash, size and metadata remain unchanged and match the accepted source snapshots. Frozen SQL54/63 creation prefixes reconstruct a private raw/staging source; historical audit blocks and old validator main functions are not rerun. SQL78 sorting/parsing/transaction-fold helpers are reused without executing its earlier full suite. The accepted SQL78 code, evidence, screenshot acceptance and method are pinned as dependencies. The learner database is never opened.

Python externally sorts all original events in 50,000-row chunks, independently matches every original five-field occurrence including NULLs and duplicate multiplicities, and retains only transaction tuples up to a declared 100,000-occurrence cap. From those tuples, a separate key-to-aggregate mapping computes the minimum timestamp, maximum timestamp and occurrence count per (visitorid, transactionid, itemid). Its maximum number of keys is bounded by the retained transaction cap. All 22,323 six-field membership tuples are independently compared in deterministic key order. This verifies the complete source-to-membership mapping, not a sample or aggregate-only reconciliation. No property file, category reference, enriched fact, stored UTC field, all-pair funnel map or association metric is rebuilt.

Four real CLI phases are fixed in advance: (1) frozen event import/staging creation; (2) SQL79 guarded membership creation and audit; (3) read-only complete five-field source comparison and transaction retention; (4) read-only complete six-field membership comparison. Each phase uses two threads, 1GB memory, 2GB maximum spill and a 120-second timeout. Minimum free disk is 8GB; the private-directory budget is 7GB. Python source scan/sort is separately timed. Post-phase directory size observations are not continuous peak measurements. This method is frozen before focused fixtures and the single real-source attempt.

Focused fixtures cover repeated and exact-duplicate source occurrences, a transaction ID shared by visitors, item-specific timestamp ranges, single/multi-item baskets, invalid empty/no-transaction sources leaving no destination, invalid fields or expected controls preventing creation, an existing destination remaining unchanged, valid no-transaction membership emptiness, extra unqueried source columns, and audit detection of occurrence/time-bound corruption. They reuse no historical full fixture suite.

Private source five-field fingerprints must match before and after SQL79; private database bytes must match before and after the two read-only comparison phases. All seventy-seven historical preflight artifacts, pinned dependencies and the event source must remain unchanged. Temporary databases, comparison spools and spills are removed. Public evidence contains only code, hashes and aggregate checks, not source records or identifiers. Original event occurrences and candidate memberships remain separate layers. This is a reusable analytical membership model, not a verified order-line or quantity table.

```powershell
python validation/preflight_retailrocket_transaction_basket_items.py --duckdb "E:/DuckDB/duckdb.exe" --output "data/retailrocket_transaction_basket_items_preflight.json"
```

Measured results will be appended after validation. Assistant preparation and learner execution are recorded separately.

## Executed results

Assistant SQL79 preflight passed at 2026-11-13T03:26:17.491759+00:00 using v1.5.5 (Variegata) d8cdaa33fd. One real-source attempt completed the four declared CLI phases. The twenty-one-row, five-column report contains twenty-one PASS checks, zero INFO and zero FAIL rows. Learner execution and screenshot acceptance remain pending.

| check_order | check_name | actual | expected | status |
| --- | --- | --- | --- | --- |
| 1 | source_event_rows | 2756101 | 2756101 | PASS |
| 2 | source_schema_mismatch | 0 | 0 | PASS |
| 3 | source_invalid_event_rows | 0 | 0 | PASS |
| 4 | source_duplicate_surplus | 460 | 460 | PASS |
| 5 | source_transaction_rows | 22457 | 22457 | PASS |
| 6 | source_contract_violations | 0 | 0 | PASS |
| 7 | membership_rows | 22323 | 22323 | PASS |
| 8 | column_count | 6 | 6 | PASS |
| 9 | schema_mismatch | 0 | 0 | PASS |
| 10 | missing_or_invalid_rows | 0 | 0 | PASS |
| 11 | duplicate_key_surplus | 0 | 0 | PASS |
| 12 | candidate_baskets | 17672 | 17672 | PASS |
| 13 | source_event_rows_sum | 22457 | 22457 | PASS |
| 14 | repeated_memberships | 123 | 123 | PASS |
| 15 | repeat_surplus_rows | 134 | 134 | PASS |
| 16 | single_item_baskets | 15029 | 15029 | PASS |
| 17 | multi_item_baskets | 2643 | 2643 | PASS |
| 18 | max_distinct_items_per_basket | 31 | 31 | PASS |
| 19 | source_only_memberships | 0 | 0 | PASS |
| 20 | table_only_memberships | 0 | 0 | PASS |
| 21 | basket_partition_difference | 0 | 0 | PASS |

The private destination contains 22,323 unique (visitorid, transactionid, itemid) memberships across 17,672 candidate baskets. Summing source_event_rows restores all 22,457 original transaction observations. There are 123 memberships with repeated observations and 134 observations beyond one per membership. The candidate baskets remain 15,029 single-item and 2,643 multi-item groups, with at most 31 distinct observed items. Both directional complete six-field differences are zero. All destination fields are BIGINT in the declared order; required values, key uniqueness, positive occurrence counts and valid first/last item-specific time bounds passed.

Independent Python comparison matched all 2,756,101 original event occurrences across five fields, including 460 exact duplicate surplus occurrences and nullable transaction IDs, then matched every one of the 22,323 six-field membership tuples. A bounded mapping independently computed each item membership's minimum timestamp, maximum timestamp and original occurrence count from the 22,457 retained transaction records. The transaction population and membership-key count remained below the declared 100,000 cap. This was a complete source-to-membership comparison, not a sample or aggregate-only check.

Source count/xor/sum fingerprints before and after membership creation matched. Those aggregate fingerprints alone are not exact identity proof; preservation is additionally supported by the unchanged source-only SQL operations, frozen reconstruction prefixes and complete after-build comparison to events.csv. Source occurrences were not deleted or rewritten. Private database hashes before and after the two read-only comparison phases matched.

Five focused fixture families passed. The mapping fixture preserved an exact repeated transaction occurrence and an additional timestamp for the same item, retained separate visitor/transaction groups even when transaction IDs collided, preserved different item-specific time ranges, and accepted an extra unqueried source column. Repeating creation with an existing destination failed while source fingerprints and all membership tuples remained unchanged. Three corruption cases changing occurrence count, first timestamp or last timestamp were detected by full six-field audit differences. Five invalid-creation cases, including empty source and a missing transaction population, left no destination table. A separately admitted nonempty source with zero transactions produced a typed empty membership table and a NULL maximum basket size. No earlier full fixture suite was rerun.

Measured CLI times were 6.541 seconds for frozen source creation, 1.832 seconds for SQL79 creation/audit, 37.536 seconds for the complete source stream and 0.4 seconds for the complete membership stream. Python event scan/sort took 36.786 seconds. Every CLI phase used two threads, 1GB memory/2GB maximum spill and completed within 120 seconds. The largest private directory observed after a phase was 162,542,255 bytes, below the 7GB budget; this is not a continuously observed peak.

The events.csv hash, size and modification metadata matched the accepted source snapshots and remained unchanged. Pinned dependencies and all 77 historical preflight artifacts were unchanged. Temporary databases, comparison spools and spills were removed. No learner database was opened; no property/category/UTC/enriched-fact reconstruction or association analysis was performed, and no actual source records or identifiers were published.

This table makes one observed item membership per candidate basket reusable without confusing repeated event observations with item quantity. Its time bounds remain specific to the basket-item membership. It does not establish actual completed orders, units purchased, revenue, product complementarity, recommendation effectiveness or business uplift.

Report SHA-256: `8cb3cf875bc4e83d55c671a84a6fe48fcdf1ef8521461e3be5497028eb0e026a`. Script SHA-256: `80fb5a9bf484a9b9e313e4421d9420b30051269044afa2335c3cb6c21e531846`. Validator SHA-256: `1a6605b07dd2bcf0719fac0773c739da4bd4a23327b78c4b0f380d32fa605eab`. The original 8,503-byte frozen method prefix remains unchanged at `b5b50226a110b37ab801dc20f8fccfc355c8df11629ac6425fc8401e2067d8dd`.
