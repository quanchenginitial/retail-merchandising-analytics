# SQL83: visitor-ID concentration within selected pair cases

## Purpose and frozen scope

SQL82 exposed the twelve pairs observed in at least five candidate baskets. SQL83 asks whether each pair's observed co-occurrences are spread across visitor identifiers or concentrated in a few identifiers. This is descriptive evidence about the source snapshot, not a test of statistical independence or a causal explanation. A visitor ID is not a verified person; multiple baskets or IDs must not be assumed independent.

The query is read-only and uses only BIGINT `visitorid,transactionid,itemid` from accepted `rr_mart.transaction_basket_items`. Basket identity remains the composite visitor and transaction key, and binary item membership remains unweighted by source event repetitions. No timestamp, date, property, category, event row, quantity or revenue field is read. The learner database is never opened by the assistant's preflight.

Reconstruct the exact SQL82 selection and ordering: all n_ab>=5 pairs, no LIMIT, n_ab descending, exact n_a*n_b ascending (equivalent to unrounded lift descending at fixed N and equal n_ab), then numeric item keys. Retain PAIR_01 through PAIR_12 in that order. The labels are snapshot-specific, A/B are pair-local numeric item order, and no raw item or visitor identifiers are published. No persistent private identifier map is created. The population remains all 17,672 candidate baskets including 15,029 singleton baskets; the selected set has 12 pairs and 110 summed pair appearances, not 110 uniquely covered baskets or verified paid orders.

## Eight-column report and definitions

The output has twelve rows and these columns:

| Column | Meaning |
| --- | --- |
| case_label | Unchanged snapshot-specific SQL82 label |
| n_ab | Number of candidate baskets containing both items |
| distinct_visitor_ids | Number of visitor IDs contributing at least one such basket |
| repeat_visitor_ids | Number of contributing visitor IDs with at least two such baskets |
| max_baskets_one_visitor | Largest per-ID paired-basket count; no winning ID is disclosed |
| top_visitor_share_pct | Maximum per-ID paired-basket count divided by this case's n_ab, times 100 |
| repeat_visitor_basket_share_pct | All paired baskets contributed by IDs with at least two divided by this case's n_ab, times 100 |
| check_status | Computational controls: PASS, BLOCKED or FAIL |

Every percentage uses its own case's n_ab as denominator, never 110. The repeat-share numerator includes all baskets of repeat contributors, not merely their extra baskets beyond the first. A visitor-count pattern of [3,1,1] has one repeat ID, maximum three, top share 60% and repeat share 60%; [2,2,1] has two repeat IDs, maximum two, top share 40% and repeat share 80%. Tied maximums use MAX only; the query does not choose a top visitor identity. Counts are integers and percentages are rounded to six decimal places for display.

Concentration can motivate further examination of evidence quality or generalizability, but does not establish unique-person reach, independent observations, causality or recommendation effectiveness. Any concentration value within the correct arithmetic may PASS; high concentration is not itself a failed data-quality check.

## Controls and failure behavior

Retain the accepted SQL82 source key/type/nonnegative/non-NULL/uniqueness controls and its exact membership, basket, pair-population and selection controls. Invalid source admission is blocked before the materialized pair join. Candidate-basket membership controls are 22,323 rows, 17,672 baskets, 15,029 singletons, 2,643 multi-item baskets and maximum size 31. Pair population controls remain 9,688 pairs and 10,757 appearances, with 8,785 occurring once, 903 at least twice and maximum frequency 39. The selected relation must remain complete at 12 pairs and 110 appearances.

For each selected pair, join both items on both visitorid and transactionid, then group paired baskets by visitorid. The private relation is `case_rank,item_a,item_b,visitorid,pair_baskets`. Counts must sum back to the original n_ab per case and to 110 overall. Every case must have at least one contributor and no more contributors than baskets; repeat IDs cannot exceed distinct IDs; maximum per-ID count is between one and n_ab; repeat-contributor basket counts are between zero and n_ab. These controls detect missing or multiplying paired-basket joins. All twelve cases must have summaries.

Fixed case slots preserve the twelve labels when input fails. Invalid admission returns NULL measurements and BLOCKED. A pair, selection or concentration reconciliation failure masks measurements and returns FAIL. Missing required columns may instead fail SQL binding. PASS means the stated controls hold; concentration findings are not required to equal a preconceived result.

## Bounded independent proof

Reuse the accepted SQL79 full original-five-field proof, SQL81 full metric proof and SQL82 case-selection proof. Do not rerun SQL54, SQL63, SQL79, SQL80, SQL81, SQL82, full past suites or a full event external sort. Parse events.csv once in canonical source order using the pinned helper, reconstruct its six-field membership tuples and require their canonical fingerprint to equal SQL79's accepted complete membership fingerprint. Load only that small private six-column copy and compare its entire ordered readback. Source identity hashing also reads file bytes separately from the one parse.

Independent Python uses the pinned SQL82 selection helper to reconstruct the same case keys and order. It then groups binary items by the full basket key and counts each selected pair once for its contributing visitor ID. Compare every row of the private selected pair-by-visitor stream in case-rank and numeric visitor order, exactly across all five integer fields. There can be no more than 110 groups, since each contributes at least one of the 110 selected pair appearances. The new proof does not compare the full 9,688-row metric stream or reverify the selected four metric formulas; prior metric proofs are reused.

Independently calculate each case's distinct and repeat IDs, maximum count, repeat-contributor basket numerator and two rational percentages. Compare all twelve report rows in original case order: labels, integer counts and statuses exactly; six-decimal percentage displays within 0.5e-6 plus 1e-12 absolute floating allowance. The actual returned report receives its own exact digest. Neither public evidence nor logs contain raw identifiers or private group tuples.

Only three real CLI phases are permitted: private six-field load/readback, read-only twelve-case concentration report, and read-only complete selected visitor-group stream derived from the same query CTEs. The narrow fixture uses patterns [3,1,1] and [2,2,1], including shared transaction identifiers under different visitor IDs. It verifies repeated versus unique contributors, tied maxima, complete repeat-share numerators, and the composite basket key. Test visible empty-source BLOCKED behavior and a deliberately inconsistent paired-basket group stream producing masked FAIL. No unrelated previous suite is repeated.

Keep existing caps of 100,000 transaction occurrences, pair occurrences and distinct pair keys, with no filtering. Add a 110-group cap to the real selected visitor stream. Each CLI phase uses two threads, 1GB memory, 2GB maximum spill and a 120-second timeout. Require 8GB available workspace space and keep the private directory within 7GB; record after-phase observations, not a claimed continuous peak. Pin dependencies and all historical preflight files, check source identity before/after, require unchanged private database bytes across read-only phases and remove the private CSV, database and spills. Freeze this method before fixtures and the single real attempt, then append measurements without changing its prefix.

## Executed results

Assistant SQL83 preflight passed at 2026-11-13T05:05:24.089618+00:00 using v1.5.5 (Variegata) d8cdaa33fd. One real-source attempt completed all three CLI phases. The twelve-row, eight-column report returned twelve PASS statuses and no FAIL or BLOCKED rows. Learner execution and screenshot acceptance remain pending.

| case_label | n_ab | distinct_visitor_ids | repeat_visitor_ids | max_baskets_one_visitor | top_visitor_share_pct | repeat_visitor_basket_share_pct | check_status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| PAIR_01 | 39 | 36 | 3 | 2 | 5.128205 | 15.384615 | PASS |
| PAIR_02 | 9 | 9 | 0 | 1 | 11.111111 | 0.000000 | PASS |
| PAIR_03 | 8 | 7 | 1 | 2 | 25.000000 | 25.000000 | PASS |
| PAIR_04 | 8 | 8 | 0 | 1 | 12.500000 | 0.000000 | PASS |
| PAIR_05 | 8 | 8 | 0 | 1 | 12.500000 | 0.000000 | PASS |
| PAIR_06 | 7 | 7 | 0 | 1 | 14.285714 | 0.000000 | PASS |
| PAIR_07 | 6 | 6 | 0 | 1 | 16.666667 | 0.000000 | PASS |
| PAIR_08 | 5 | 4 | 1 | 2 | 40.000000 | 40.000000 | PASS |
| PAIR_09 | 5 | 2 | 1 | 4 | 80.000000 | 80.000000 | PASS |
| PAIR_10 | 5 | 3 | 1 | 3 | 60.000000 | 60.000000 | PASS |
| PAIR_11 | 5 | 3 | 2 | 2 | 40.000000 | 80.000000 | PASS |
| PAIR_12 | 5 | 5 | 0 | 1 | 20.000000 | 0.000000 | PASS |

The twelve labels and n_ab values remain in the accepted SQL82 order. Every case's contributor counts reconcile to that case's n_ab, and all selected pair appearances reconcile to 110. Each percentage uses the corresponding case count, never 110. Repeat-contributor share includes all paired baskets from IDs contributing at least twice, not only the excess beyond one. Case-by-ID counts must not be summed and described as distinct people across the whole selection. The results describe recorded identifier concentration and do not establish unique-person reach, independence or causal significance; high concentration does not itself fail a check.

One canonical events.csv parse reconstructed the accepted 22,323 six-field memberships. Fingerprint `99c7d679d858b3d1335dfafa22aa48b5e842d03336af5c85330e96853c59fca5` matched SQL79's accepted full membership fingerprint and the complete private input readback. Separate source-byte hashes also verified identity. Prior original-five-field, full metric and case-selection proofs were reused; SQL54/63/79/80/81/82 and full historical suites were not rerun.

The new private SQL comparison covered all 98 selected pair-by-visitor groups across five integer fields, with exact tuple/order agreement to the independent Counter. Their basket counts sum to 110. The group count is not a global distinct-visitor count. No new full 9,688-row or selected four-formula metric stream was compared. All public labels, counts and statuses matched exactly; two six-decimal percentages per case matched independent Fraction references within 5.00001e-07 absolute tolerance. Actual SQL output is preserved in the report digest.

Two focused fixture families passed. Contributor patterns [3,1,1] and [2,2,1] produced maximum shares 60% and 40%, and complete repeat-contributor shares 60% and 80%. Shared transaction identifiers under different visitors remained distinct baskets. Tied maxima required no visitor identity selection. Empty source returned the existing labels with BLOCKED and masked measurements. Intentionally adding one to each private per-ID group count produced inconsistent totals and FAIL with masked measurements. No unrelated prior suite was repeated.

The canonical source parse/reconstruction took 16.249 seconds and the independent selected visitor reference 0.172 seconds. CLI phases took 0.262 seconds for private input load/readback, 0.154 seconds for the read-only concentration report and 0.143 seconds for the exact selected group stream. Each used two threads, 1GB memory and 2GB maximum spill and finished within 120 seconds. The largest private directory observed after a phase was 1,922,839 bytes, below 7GB; this is not a continuous peak measurement.

Source snapshots and pinned dependencies remained unchanged, together with all 81 historical preflight artifacts. Private database hashes matched across the read-only phases. All temporary membership CSV, databases and spills were removed, and no persistent ID map was created. The analytical query did not read stored timestamp fields; source timestamps were processed only in the bounded membership reconstruction. The learner database, property data, category reference and enriched fact were not accessed. Public evidence contains only case labels, aggregate count/share summaries and proof fingerprints, without raw item or visitor IDs or event records.

Report SHA-256: `877cab7cb6760152fb92062a524eccf1d51f188e286f0e7aa67415625ae3e544`. Script SHA-256: `8760fcc7d9ee3797f983444c8c315f7eaf3c7f988c91ebbd00230deb8bd1e022`. Validator SHA-256: `8012ecdde69cbffd052128ce958ab38390462d9e22fe9119de72f5fe445f3df4`. The frozen 7,917-byte method prefix remains unchanged at `360fed85d5889b51e4dfbff841de05e96e5376ad3a7fd66cf6dacb50d139cd94`.

## Learner acceptance — 13 November 2026

The learner supplied a DBeaver screenshot showing all twelve rows, eight column headers and ninety-six result fields of SQL83. The visible fields comprise twelve case labels, forty-eight integer-count values, twenty-four percentage displays and twelve PASS labels. Seventeen percentages display integer-looking values, two display one decimal and five display six decimals; percentage columns retain their metric semantics. UI row numbers are excluded. All twelve statuses are PASS, with no INFO, FAIL, BLOCKED or NULL cells.

This screenshot contains no thousands separators. Nineteen shortened percentage displays were restored to six-decimal notation without changing values; displayed zeroes remain numeric zeroes. Every field and its case order matches the frozen preflight exactly. Acceptance concerns the rounded report, not direct observation or mathematical exactness of unrounded calculations. No label, hidden field or missing precision was inferred. The assistant did not open the learner database or rerun SQL, source parsing, input reconstruction, contributor streams or fixtures for this acceptance.

| case_label | n_ab | distinct_visitor_ids | repeat_visitor_ids | max_baskets_one_visitor | top_visitor_share_pct | repeat_visitor_basket_share_pct | check_status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| PAIR_01 | 39 | 36 | 3 | 2 | 5.128205 | 15.384615 | PASS |
| PAIR_02 | 9 | 9 | 0 | 1 | 11.111111 | 0.000000 | PASS |
| PAIR_03 | 8 | 7 | 1 | 2 | 25.000000 | 25.000000 | PASS |
| PAIR_04 | 8 | 8 | 0 | 1 | 12.500000 | 0.000000 | PASS |
| PAIR_05 | 8 | 8 | 0 | 1 | 12.500000 | 0.000000 | PASS |
| PAIR_06 | 7 | 7 | 0 | 1 | 14.285714 | 0.000000 | PASS |
| PAIR_07 | 6 | 6 | 0 | 1 | 16.666667 | 0.000000 | PASS |
| PAIR_08 | 5 | 4 | 1 | 2 | 40.000000 | 40.000000 | PASS |
| PAIR_09 | 5 | 2 | 1 | 4 | 80.000000 | 80.000000 | PASS |
| PAIR_10 | 5 | 3 | 1 | 3 | 60.000000 | 60.000000 | PASS |
| PAIR_11 | 5 | 3 | 2 | 2 | 40.000000 | 80.000000 | PASS |
| PAIR_12 | 5 | 5 | 0 | 1 | 20.000000 | 0.000000 | PASS |

The current screenshot's nineteen shortened displays normalize as follows.

| case_label | field | displayed | normalized six-decimal value |
| --- | --- | --- | --- |
| PAIR_02 | repeat_visitor_basket_share_pct | 0 | 0.000000 |
| PAIR_03 | top_visitor_share_pct | 25 | 25.000000 |
| PAIR_03 | repeat_visitor_basket_share_pct | 25 | 25.000000 |
| PAIR_04 | top_visitor_share_pct | 12.5 | 12.500000 |
| PAIR_04 | repeat_visitor_basket_share_pct | 0 | 0.000000 |
| PAIR_05 | top_visitor_share_pct | 12.5 | 12.500000 |
| PAIR_05 | repeat_visitor_basket_share_pct | 0 | 0.000000 |
| PAIR_06 | repeat_visitor_basket_share_pct | 0 | 0.000000 |
| PAIR_07 | repeat_visitor_basket_share_pct | 0 | 0.000000 |
| PAIR_08 | top_visitor_share_pct | 40 | 40.000000 |
| PAIR_08 | repeat_visitor_basket_share_pct | 40 | 40.000000 |
| PAIR_09 | top_visitor_share_pct | 80 | 80.000000 |
| PAIR_09 | repeat_visitor_basket_share_pct | 80 | 80.000000 |
| PAIR_10 | top_visitor_share_pct | 60 | 60.000000 |
| PAIR_10 | repeat_visitor_basket_share_pct | 60 | 60.000000 |
| PAIR_11 | top_visitor_share_pct | 40 | 40.000000 |
| PAIR_11 | repeat_visitor_basket_share_pct | 80 | 80.000000 |
| PAIR_12 | top_visitor_share_pct | 20 | 20.000000 |
| PAIR_12 | repeat_visitor_basket_share_pct | 0 | 0.000000 |

The twelve labels and n_ab values retain the SQL82 case order. Both percentages divide by each case's n_ab, not the cross-case sum of 110. Repeat contributors have at least two paired baskets within the case; repeat-contributor share includes their entire contribution, not only the excess above the first. For example, PAIR_01 records 39 paired baskets across 36 visitor IDs with maximum contribution two, whereas PAIR_09 records five baskets across two IDs with maximum contribution four. These observations describe concentration in recorded identifiers and do not verify distinct people or independent observations. Cross-case ID counts cannot be summed as globally distinct people. High concentration alone neither fails a control nor proves a data error.

The exact comparison of 98 private pair-by-visitor groups across five integer fields, accepted-input fingerprints and fixture behaviour remains supported by frozen assistant evidence rather than new direct checks of the learner environment. No old metric-formula proof or date/time analysis is rerun for acceptance. No persistent mapping is created, and snapshot case labels are not permanent product aliases.

The [machine-readable learner acceptance](../data/retailrocket_pair_visitor_concentration_learner_acceptance.json) records raw displayed strings, normalized values and all nineteen precision normalizations. Its report SHA-256 is `877cab7cb6760152fb92062a524eccf1d51f188e286f0e7aa67415625ae3e544`, matching the actual SQL report fingerprint. The prior 12,939-byte method and executed-results document remains byte-for-byte intact at SHA-256 `d7efad1d15beef0997a7d617752ce1c84c9e01b1a265511298da60a5a881af5e`; its frozen 7,917-byte prefix remains `360fed85d5889b51e4dfbff841de05e96e5376ad3a7fd66cf6dacb50d139cd94`. This UTF-8 appendix records learner acceptance without rewriting earlier pending statements. No raw events, memberships or visitor/item/transaction identifiers are published.
