# SQL86: observed transaction-visitor recency baseline

## Purpose and population

SQL85 established observed basket frequency. This separate R-only step measures elapsed time since each transaction-recorded visitor ID's latest recorded transaction event, at a frozen observation reference. It does not calculate combined RF scores, monetary value or customer segments, and does not identify churn, retention, loyalty or verified people/orders.

Use all 22,323 accepted basket-item memberships across 17,672 candidate baskets and 11,719 transaction-recorded visitor IDs. No pair, product, funnel or category restriction applies. Non-transaction and browsing-only visitor IDs are absent from this population; there is no F_0 population or all-visitor retention denominator. The finite source window and unequal exposure/tenure of identifiers constrain interpretation.

The analytical readset is four BIGINT fields from `rr_mart.transaction_basket_items`: `visitorid,transactionid,itemid,last_timestamp_ms`. The previously accepted membership table retains the last source transaction-event timestamp for each basket-item key. First timestamps, occurrence weights, properties, category reference and enriched-event columns are not queried. No learner database is opened by the assistant's preflight.

## Frozen reference and exact R definition

Reference timestamp is exactly 1442545187788 Unix milliseconds, corresponding to 2015-09-18T02:59:47.788000Z under the accepted UTC convention. This is the global observed event endpoint proven by accepted SQL64 and the TOTAL row of accepted SQL70. It is neither today's date nor a claimed collection cutoff; it is not replaced by the earlier latest transaction event (2015-09-18T02:43:12.017000Z).

For each visitor ID, take MAX(last_timestamp_ms) across all its accepted memberships and compute `recency_ms = reference_timestamp_ms - last_transaction_ms`. This uses the latest retained transaction-event observation across all items and baskets, not a basket's earliest timestamp, the first timestamp of a membership, an event-row count or a maximum limited to selected products. A membership with repeated source events contributes its accepted last timestamp. This is not proof of a completed order time.

All calculations and band boundaries use exact integer milliseconds. A day is exactly 86,400,000 milliseconds, rather than a calendar-date difference. Reference/source bounds are fixed, so session timezone and current clock do not determine R. The source lower timestamp bound is 1430622004384 milliseconds, from accepted SQL64.

## Report and intervals

Return five rows and seven columns: `recency_band,visitor_ids,visitor_share_pct,min_recency_days,median_recency_days,max_recency_days,check_status`.

| Band | Exact elapsed-time interval |
| --- | --- |
| R_LT_7D | 0 <= R < 7 days |
| R_7_TO_LT_30D | 7 <= R < 30 days |
| R_30_TO_LT_60D | 30 <= R < 60 days |
| R_GE_60D | R >= 60 days |
| TOTAL | All 11,719 transaction-recorded visitor IDs |

Boundary constants are explicit BIGINT milliseconds: 604800000, 2592000000 and 5184000000. Do not multiply 32-bit integer literals or classify after rounding. The four bands are disjoint descriptive intervals, not learned risk or value scores. Shares divide by all 11,719 IDs. Empty bands remain visible with zero IDs/share and NULL minimum, median and maximum days. TOTAL statistics are recomputed over all visitor recencies; its median is not an average of band medians.

Day summaries and visitor shares are rounded to six decimal places for display only. A raw elapsed time one millisecond below a boundary may display exactly 7.000000, 30.000000 or 60.000000 while correctly belonging to the lower interval. Classification always precedes display rounding. Even-size medians average the two central integer-millisecond values and may therefore include a half millisecond. The source's partial observation days and varying visitor tenure do not support interpreting these labels as established churn or retention states.

## Controls and failure behavior

Require the four BIGINT fields, non-NULL/nonnegative keys, unique three-field memberships and non-NULL last timestamps within [1430622004384,1442545187788]. Retain accepted membership/basket controls: 22,323 rows, 17,672 composite baskets, 15,029 singleton baskets, 2,643 multi-item baskets and maximum size 31. Invalid source rows do not enter the materialized recency calculation. Missing required columns may fail SQL binding.

The visitor-level result must have 11,719 rows. Every recency must be nonnegative, no larger than reference minus source lower bound, and reconcile exactly with its last timestamp to the frozen reference. Four band rows must partition the same 11,719 IDs. Nonempty band statistics satisfy 0 <= minimum <= median <= maximum; empty bands have three NULL statistics. The TOTAL statistics independently aggregate all visitor recencies.

Invalid source admission returns the five fixed labels with NULL measurements and BLOCKED. Post-admission recency or partition failures return masked FAIL. A particular distribution is not specified in advance; PASS verifies computational integrity rather than business validity of a churn/loyalty interpretation.

## Bounded independent proof

Pin both preflight and learner evidence for accepted SQL64's integer endpoint/UTC rendering and SQL70's global TOTAL endpoint. Pin accepted SQL85 progress while reusing SQL79's complete original-five-field and membership fingerprints. Do not run SQL54, SQL63, SQL64, SQL70, SQL79 through SQL85, full historical suites or a full event external sort.

Parse events.csv once in canonical source order with the existing bounded reconstruction helper. Require all six-field memberships to match the accepted SQL79 canonical fingerprint, then load only the small private six-column copy and compare its complete ordered readback. Source-byte identity hashing uses separate reads from the canonical parse. Source timestamps are processed in reconstruction; only the membership last timestamp enters the new analytical readset.

Independent Python finds each visitor's maximum of all membership last timestamps and subtracts it from the fixed integer reference. Compare the entire private SQL stream sorted by visitorid: 11,719 rows by three exact integer fields, `visitorid,last_transaction_ms,recency_ms`. Classify the independent raw milliseconds using the same specified half-open intervals. Compute minimum, exact Fraction median (including even central averages), maximum and shares independently; compare public labels, counts and NULLs exactly and six-decimal displays within 0.5e-6 plus 1e-12 absolute tolerance. Record the actual returned report's own exact digest. No visitor IDs or private rows are published.

Only three real CLI phases are permitted: private six-field load/readback, read-only R report and complete read-only three-field recency stream from the same query CTEs. No old F, pair, contributor or monthly result stream is repeated. This is R-only, not completed RF segmentation or a monetary analysis.

Focused fixtures cover exact 7/30/60-day boundaries and one millisecond on either side; a later timestamp in another membership must determine the visitor maximum, independently of its earlier first timestamp. Include both odd and even medians and a separate empty-band input. NULL, future/out-of-bound and wrong-type timestamps must visibly block, while an intentionally overlapping millisecond boundary must fail the partition. No unrelated previous suite is rerun.

Keep the 100,000 transaction-occurrence and 100,000 visitor-result caps without filtering. Each CLI phase uses two threads, 1GB memory, 2GB maximum spill and a 120-second timeout. Require 8GB free workspace and a 7GB private-directory budget, measuring after-phase size rather than claiming a continuous peak. Pin dependencies/historical preflights, require source identity unchanged, ensure private database bytes remain unchanged across read-only phases and remove temporary CSV/database/spills. Freeze this method before fixtures and the single source attempt, then append results without changing the prefix.

## Executed results

Assistant SQL86 preflight passed at 2026-11-13T06:46:27.133820+00:00 using v1.5.5 (Variegata) d8cdaa33fd. One real-source attempt completed all three declared CLI phases. The five-row, seven-column recency report returned five PASS statuses and no FAIL or BLOCKED rows. Learner execution and screenshot acceptance remain pending.

| recency_band | visitor_ids | visitor_share_pct | min_recency_days | median_recency_days | max_recency_days | check_status |
| --- | --- | --- | --- | --- | --- | --- |
| R_LT_7D | 476 | 4.061780 | 0.011525 | 3.485765 | 6.989986 | PASS |
| R_7_TO_LT_30D | 1884 | 16.076457 | 7.026333 | 18.295281 | 29.984544 | PASS |
| R_30_TO_LT_60D | 2609 | 22.262992 | 30.003754 | 46.491853 | 59.965966 | PASS |
| R_GE_60D | 6750 | 57.598771 | 60.003765 | 98.363966 | 137.980861 | PASS |
| TOTAL | 11719 | 100.000000 | 0.011525 | 70.897344 | 137.980861 | PASS |

The four disjoint intervals reconcile to all 11,719 transaction-recorded visitor IDs. Their common reference is 1442545187788 Unix milliseconds, or 2015-09-18T02:59:47.788000Z, confirmed independently in accepted SQL64 and SQL70 evidence. The global observed event endpoint stays fixed despite the earlier last transaction event, 2015-09-18T02:43:12.017000Z. It is neither today's date nor a confirmed collection cutoff. The day summaries use elapsed milliseconds divided by 86,400,000. Band membership uses exact raw-millisecond comparisons before six-decimal display rounding; the TOTAL median is recomputed directly across all IDs.

The population excludes browsing-only and other non-transaction IDs. These observed-window recencies do not establish unique people, verified paid orders, lifetime purchase history, churn, retention or loyalty. Unequal visitor exposure remains a limitation. The descriptive intervals are not optimized customer scores; combined RF segmentation and monetary analysis remain uncompleted.

One canonical events.csv parse reconstructed all 22,323 six-field memberships. Fingerprint `99c7d679d858b3d1335dfafa22aa48b5e842d03336af5c85330e96853c59fca5` matched accepted SQL79 and the complete private six-field readback. Separate source-byte hash scans also checked identity. Original-five-field proof was reused; SQL54/63/64/70/79/80/81/82/83/84/85 and full historical suites were not rerun. Source timestamps were processed during reconstruction. The analytical query read only the three membership keys and last_timestamp_ms, without first timestamps, occurrence weights, properties or enriched-event fields.

The new independent reference took MAX(last_timestamp_ms) for each visitor over all memberships and subtracted it from the fixed integer reference. All 11,719 private rows across three integer fields matched exactly in numeric visitor order: visitorid, last_transaction_ms and recency_ms. Public labels, counts, NULLs and statuses matched exactly. Six-decimal shares and day summaries matched independent Fraction references within 5.00001e-07 absolute tolerance; exact median references included even-size central averages. The actual returned report has its own exact digest. No earlier frequency, pair, contributor or monthly result stream was repeated, and no private visitor IDs or recency rows are published.

Two focused fixture families passed. A ten-visitor input covered exact 7/30/60-day boundaries and one millisecond on either side. A later last timestamp in an additional membership correctly determined the visitor's MAX, independently of that membership's much earlier first timestamp. Odd and even medians, including the direct TOTAL median, matched exact references. A separate input preserved three empty bands with zero counts/shares and NULL minimum, median and maximum. NULL, future and wrong-type timestamps each returned BLOCKED with masked measurements; an intentionally overlapping millisecond boundary returned FAIL with masked measurements. No unrelated previous test suite was repeated.

The canonical source parse/reconstruction took 31.529 seconds and the independent per-visitor recency reference 0.058 seconds. CLI phases took 0.384 seconds for private input load/readback, 0.208 seconds for the R report and 0.276 seconds for the exact complete recency stream. Each used two threads, 1GB memory and 2GB maximum spill and completed within 120 seconds. The largest private directory observed after a phase was 1,922,839 bytes, below 7GB, without claiming a continuously measured peak.

Source identity, pinned dependencies and all 84 historical preflight artifacts remained unchanged. Private database byte hashes matched across both read-only phases. Temporary membership CSV, database and spills were removed. The learner database, properties, category reference and enriched fact were not opened. Public artifacts contain aggregate band results and proof fingerprints, without original source IDs or event records.

Report SHA-256: `a9b438cd1c30b3b9df4d6e3d438f3ae08780fe0e5eec4b4f7daa8b4281fc42ee`. Script SHA-256: `c152b6af75534dd5078cabe79a8cfd53e4369e12058dd0a36ec78d8e97be122d`. Validator SHA-256: `958d9757afc737284514f3660c933826b6410ff7f546621a6e25285dcfd42205`. The frozen 8,175-byte method prefix remains unchanged at `338d01de50fe7c66ef27c4abc4d1b9ced7b194e6abac83d2ff4a0c3593940149`.

## Learner acceptance — 13 November 2026

The learner supplied the DBeaver screenshot identified as codex-clipboard-f1038136-7e6a-4f94-b425-c05295aa737c.png in this conversation. Direct inspection shows all five rows, seven column headers and 35 result fields of SQL86: five band labels, five integer visitor counts, twenty decimal metrics (five percentages and fifteen fractional-day statistics), and five PASS labels. No INFO, FAIL, BLOCKED or NULL cells appear. UI row numbers are excluded; no image editing or inference of hidden fields was used.

Four comma-formatted visitor counts normalize by removing thousands separators. R_LT_7D visitor_share_pct displays 4.06178, and TOTAL visitor_share_pct displays 100; these two percentages normalize to six decimals without changing values. The other eighteen decimal fields already show six places, including every day statistic. All displayed fractional values below one retain their visible leading zero. Every field and the band order matches the frozen preflight exactly. Acceptance concerns the rounded report rather than direct observation of underlying milliseconds. No learner database, SQL, source parsing, private recency stream or fixture was rerun.

| recency_band | visitor_ids | visitor_share_pct | min_recency_days | median_recency_days | max_recency_days | check_status |
| --- | --- | --- | --- | --- | --- | --- |
| R_LT_7D | 476 | 4.061780 | 0.011525 | 3.485765 | 6.989986 | PASS |
| R_7_TO_LT_30D | 1884 | 16.076457 | 7.026333 | 18.295281 | 29.984544 | PASS |
| R_30_TO_LT_60D | 2609 | 22.262992 | 30.003754 | 46.491853 | 59.965966 | PASS |
| R_GE_60D | 6750 | 57.598771 | 60.003765 | 98.363966 | 137.980861 | PASS |
| TOTAL | 11719 | 100.000000 | 0.011525 | 70.897344 | 137.980861 | PASS |

| recency_band | field | displayed | normalized six-decimal value |
| --- | --- | --- | --- |
| R_LT_7D | visitor_share_pct | 4.06178 | 4.061780 |
| TOTAL | visitor_share_pct | 100 | 100.000000 |

The four disjoint intervals reconcile to 11,719 transaction-recorded IDs. TOTAL is a separate summary, not an additional disjoint interval. The reference remains the accepted global observed event endpoint 1442545187788 ms, or 2015-09-18T02:59:47.788000Z. It is neither today's date nor the earlier latest-transaction endpoint. Recency subtracts the maximum last transaction timestamp across all memberships for each ID. Exact elapsed milliseconds determine the half-open bands; rounded fractional-day summaries do not reclassify an ID.

The population excludes non-transaction visitors. These finite-window observations do not establish churn, retention, loyalty, lifetime history, verified people or paid orders. Combined RF segmentation and monetary analysis remain unfinished. No empty band appears in this screenshot; zero-count bands with three NULL statistics remain supported by the frozen fixtures rather than direct observation here.

The complete exact comparison of 11,719 private ID/latest-transaction/elapsed-ms triples, endpoint provenance, accepted-input fingerprints and fixture behaviour remains supported by frozen assistant evidence. The [machine-readable learner acceptance](../data/retailrocket_visitor_purchase_recency_learner_acceptance.json) records the screenshot provenance, raw display strings, normalized values, two decimal normalizations and four separator normalizations. Its report SHA-256 is `a9b438cd1c30b3b9df4d6e3d438f3ae08780fe0e5eec4b4f7daa8b4281fc42ee`, matching the returned SQL report fingerprint.

The prior 13,450-byte method and executed-results document remains byte-for-byte intact at SHA-256 `00e814bdcf7546b0dbf6fb18f05fe5fc642720f8f7e9df9ae6b31cbc64201c15`; its frozen 8,175-byte prefix remains `338d01de50fe7c66ef27c4abc4d1b9ced7b194e6abac83d2ff4a0c3593940149`. This UTF-8 appendix records learner acceptance without rewriting earlier pending statements. No raw events, memberships or visitor/item/transaction identifiers are published.
