# SQL84: UTC month coverage of frozen pair cases

## Purpose and frozen scope

SQL83 examined visitor-ID concentration. SQL84 shows in which observed UTC months the same twelve selected pair cases appear. It preserves the accepted SQL82 full-snapshot selection n_ab>=5 and deterministic case order. The pairs were selected using the whole observation window; this report is not independent temporal validation, a train/test experiment, evidence of growth, seasonality, monthly lift or comparable monthly conversion rates.

The original event observation window spans May 3 to September 18, 2015 in UTC. May and September are partial months and month lengths/exposure differ. Monthly counts describe historical coverage, not equal-duration opportunities. No original item or visitor IDs or individual events are published; case labels are snapshot-specific and not a guarantee of anonymization.

The read-only analytical query reads four BIGINT fields from accepted `rr_mart.transaction_basket_items`: `visitorid,transactionid,itemid,first_timestamp_ms`. It does not read last_timestamp_ms, source_event_rows, properties, category reference or the enriched event fact. The assistant does not open the learner database. Binary pair membership and the composite visitor/transaction basket key remain unchanged. The accepted population is 22,323 memberships in 17,672 candidate baskets, including 15,029 singleton baskets, with 2,643 multi-item baskets and maximum size 31.

## Whole-basket time convention

Compute MIN(first_timestamp_ms) across every membership of each composite basket before joining selected pair appearances. This includes unselected or third items in that basket. Convert the integer epoch milliseconds with make_timestamp_ms to a timezone-naive TIMESTAMP interpreted under the same UTC convention as accepted SQL64, then extract year and month. There is no floating seconds conversion or session-timezone-dependent TIMESTAMPTZ conversion. Independent Python uses integer UTC datetime arithmetic.

If the pair's two items first appear just after June 1 but another basket member first appears just before June 1, the whole basket is assigned to May. This is deliberate attribution to the earliest recorded event in a candidate basket, not proof of a confirmed order date or simultaneous purchase. Membership timestamps spanning months are not by themselves invalid. No item is removed to obtain a preferred anchor.

## Report and controls

Return twelve rows and nine columns in this order: `case_label,n_ab,may_baskets,jun_baskets,jul_baskets,aug_baskets,sep_baskets,top_month_share_pct,check_status`. Labels and n_ab remain in accepted SQL82 order. The five monthly integer counts include explicit zeros. Top-month share is the largest of those five counts divided by that case's n_ab, times 100, displayed to six decimal places. Ties need only MAX; no winning month label is selected. The denominator is never the selected-set total 110.

Required schema now includes the fourth BIGINT timestamp field. All four required values must be non-NULL, keys remain nonnegative and unique, and every first_timestamp_ms must lie within the accepted source event timestamp bounds [1430622004384,1442545187788]. Invalid time input is blocked before the materialized admitted membership/pair join and before timestamp conversion. The timestamp bound is a source-identity/scope control; it is not a requirement that all memberships start at either bound. Missing required columns can fail SQL binding.

Retain accepted pair population and complete selection controls: 9,688 observed pairs, 10,757 appearances, 8,785 pairs appearing once, 903 at least twice and maximum frequency 39; selected set 12 pairs and 110 appearances, without LIMIT. Compute an anchor for every accepted basket, require exact millisecond roundtrip, year 2015 and month 5 through 9. Unknown/out-of-window anchors are not silently filtered away.

For each selected pair, join its binary item memberships on both basket-key fields and attach the whole-basket anchor. Scaffold all five months for all cases. All five counts must sum to the frozen n_ab per case and 110 overall; every case must have five nonnegative cells. This detects missing or multiplying pair appearances. A valid descriptive monthly distribution may PASS regardless of concentration. Invalid admission returns the twelve labels with NULL measurements and BLOCKED; post-admission population, selection or coverage reconciliation failure returns masked FAIL. PASS does not establish independent validation or commercial usefulness.

## Narrow independent proof

Reuse SQL79's accepted original-five-field and membership proofs, SQL81's metric proof, SQL82's selected-case proof and SQL83's contributor proof. Do not rerun SQL54, SQL63, SQL79, SQL80, SQL81, SQL82, SQL83, full historical suites or a full event external sort. Parse events.csv once in canonical source order with the pinned existing helper, reconstruct all six-field memberships and require their ordered canonical hash to match accepted SQL79. Load a small private six-column copy and verify its complete ordered readback. Source identity hash scans are separate reads from the single canonical parse; source timestamps are necessarily processed during reconstruction.

Independent Python first groups all memberships by the full basket key, obtains the minimum first timestamp and derives its UTC year/month using integer arithmetic. Only then does it test selected pair membership and accumulate a Counter. Build the complete private scaffold in case-rank and month-number order. The exact newly compared SQL stream is sixty rows by three integer fields: `case_rank,month_number,pair_baskets`, including zero cells. All cells are compared, totals must reconcile to each frozen n_ab and 110 overall, and monthly counts/labels/status in the twelve-by-nine public report match exactly. Top-month percentage is compared to an independent Fraction reference within 0.5e-6 plus 1e-12 absolute tolerance of the six-decimal display. The actual SQL report has its own exact digest.

Only three real CLI phases are permitted: private six-field load/readback, read-only monthly case report, and read-only full sixty-cell month stream from the same query CTEs. No full or selected metric-formula stream, visitor-group stream, original-event full proof or broad old suite is repeated. The assistant creates no persistent raw-ID mapping.

The focused fixture must place selected pair members just after a UTC month boundary and an unselected third member one millisecond before it, proving the whole-basket minimum. Include additional boundary observations and an empty month to prove the scaffold and partition. NULL, out-of-bound and wrong-type timestamps must visibly block/mask measurements; an intentionally inconsistent monthly count must fail the coverage reconciliation. No unrelated mathematical, category or property suite is rerun.

Keep the existing 100,000 caps on transaction occurrences, pair occurrences and distinct pair keys without filtering, and a fixed 60-cell real month stream. Each CLI phase uses two threads, 1GB memory, 2GB maximum spill and a 120-second timeout. Require 8GB available workspace space and a private-directory budget of 7GB, recording after-phase size rather than claiming a continuous peak. Pin dependencies and all historical preflight files, require source identity unchanged, check the private database bytes across both read-only phases and remove temporary memberships CSV, database and spills. Freeze this method before fixtures and the single source attempt, then append measured results without modifying the prefix.

## Executed results

Assistant SQL84 preflight passed at 2026-11-13T05:21:32.833968+00:00 using v1.5.5 (Variegata) d8cdaa33fd. One real-source attempt completed the three declared CLI phases. All twelve rows of the nine-column monthly report returned PASS, with no FAIL or BLOCKED rows. Learner execution and screenshot acceptance remain pending.

| case_label | n_ab | may_baskets | jun_baskets | jul_baskets | aug_baskets | sep_baskets | top_month_share_pct | check_status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| PAIR_01 | 39 | 0 | 0 | 35 | 2 | 2 | 89.743590 | PASS |
| PAIR_02 | 9 | 0 | 0 | 4 | 3 | 2 | 44.444444 | PASS |
| PAIR_03 | 8 | 2 | 1 | 2 | 1 | 2 | 25.000000 | PASS |
| PAIR_04 | 8 | 1 | 2 | 1 | 3 | 1 | 37.500000 | PASS |
| PAIR_05 | 8 | 0 | 0 | 1 | 4 | 3 | 50.000000 | PASS |
| PAIR_06 | 7 | 2 | 4 | 0 | 1 | 0 | 57.142857 | PASS |
| PAIR_07 | 6 | 3 | 0 | 2 | 1 | 0 | 50.000000 | PASS |
| PAIR_08 | 5 | 0 | 1 | 4 | 0 | 0 | 80.000000 | PASS |
| PAIR_09 | 5 | 5 | 0 | 0 | 0 | 0 | 100.000000 | PASS |
| PAIR_10 | 5 | 0 | 0 | 4 | 1 | 0 | 80.000000 | PASS |
| PAIR_11 | 5 | 2 | 0 | 0 | 1 | 2 | 40.000000 | PASS |
| PAIR_12 | 5 | 0 | 1 | 0 | 1 | 3 | 60.000000 | PASS |

All twelve labels and n_ab values retain accepted SQL82 order. The five monthly counts reconcile to each case's n_ab and 110 selected pair appearances overall. The complete sixty-cell scaffold contains 24 explicit zero cells. Top-month share uses the individual case denominator and requires no choice of a winning month when tied. The same candidate basket may contain multiple selected pairs, so 110 must not be described as unique covered baskets.

All 17,672 composite baskets received anchors from MIN(first_timestamp_ms) over their entire membership sets before selected pair attribution. Every anchor was within the accepted 2015 May–September partition, with integer millisecond roundtrip. This is the earliest recorded member event convention, not verified order or purchase timing. May and September are partial observed months, durations differ, and the cases were chosen from the full observation snapshot. Counts therefore describe coverage and are not independent temporal validation, growth estimates, monthly rates or monthly lift.

One canonical events.csv parse reconstructed all 22,323 six-field memberships. Fingerprint `99c7d679d858b3d1335dfafa22aa48b5e842d03336af5c85330e96853c59fca5` matched accepted SQL79 and the complete private six-field readback. Source-byte identity hashing used separate reads. Prior original-five-field, metric, selected-case and contributor proofs were reused; SQL54/63/79/80/81/82/83 and historical full suites were not rerun. The current query's analytical readset is exactly four fields: three membership keys plus first_timestamp_ms. Source timestamp processing during input reconstruction is separate from this analytical readset; stored last timestamps and occurrence weights are not queried.

The new private comparison covered every one of the sixty case-by-month cells across three integer fields in case-rank/month order, including zero cells, with exact agreement to the independent whole-basket-minimum Counter. No metric-formula or visitor-group stream was repeated. Public labels, n_ab values, monthly counts and statuses matched exactly; top-month percentage displays matched Fraction references within 5.00001e-07 absolute tolerance. The actual returned report has its own exact digest.

Two focused fixture families passed. A third member one millisecond before June 1 anchored the whole basket in May despite selected pair members at June 1; additional UTC boundaries yielded monthly counts [1,2,1,0,1], including a zero August cell and top-month share 40%. NULL, out-of-source-bound and non-BIGINT first timestamps returned BLOCKED with measurements masked. Deliberately inflating observed monthly counts returned FAIL with measurements masked. These tests do not treat legitimate cross-month membership timestamps as invalid.

The canonical source parse/reconstruction took 16.362 seconds and the independent whole-basket month reference 0.205 seconds. CLI phases took 0.262 seconds for private load/readback, 0.159 seconds for the monthly report and 0.144 seconds for the exact sixty-cell stream. Each phase used two threads, 1GB memory and 2GB maximum spill and completed within 120 seconds. The largest private directory observed after a phase was 1,922,839 bytes, below 7GB, without claiming a continuous peak measurement.

Source identity, pinned dependencies and all 82 historical preflight artifacts remained unchanged. Private database byte hashes matched across both read-only phases. Temporary membership CSV, databases and spills were removed, and no persistent identifier map was created. The learner database, property data, category reference and enriched fact were not accessed. Public evidence contains case labels, aggregate month counts and proof fingerprints, without raw item/visitor IDs or individual event rows.

Report SHA-256: `c15fb0f32ba48eea7cfd98da093a14a675d182eaac6a4560c4c66f5bb4d48b55`. Script SHA-256: `fc60d6ec367bdf7090d88e4089f3c8a90ae3a390e0285364d949360e25a00d7c`. Validator SHA-256: `1c3f5aa42f383623eea645cd075bed281039b318835947409adda45c1bc14c7d`. The frozen 7,671-byte method prefix remains unchanged at `183d6844786826de601c5fd5cc86ee23e4870bf256adcb484cf7bfc1a7ebf1f9`.

## Learner acceptance — 13 November 2026

The learner supplied a DBeaver screenshot showing all twelve rows, nine column headers and 108 result fields of SQL84. These comprise twelve case labels, seventy-two integer counts, twelve percentage displays and twelve PASS labels. No INFO, FAIL, BLOCKED or NULL cells appear. All sixty month counts are visible, including twenty-four explicit numeric zeroes. UI row numbers are excluded.

This screenshot contains no thousands separators. Eight percentages display integer-looking values, one displays 37.5 and one displays 89.74359; those ten cells normalize to six-decimal notation without changing values. The other two percentages already display six decimals. Every field and the case order matches the frozen preflight exactly. No label, hidden precision or missing value was inferred. Acceptance concerns the rounded report rather than direct observation of unrounded calculations. No learner database, source parsing, SQL, private proof stream or fixture was rerun.

| case_label | n_ab | may_baskets | jun_baskets | jul_baskets | aug_baskets | sep_baskets | top_month_share_pct | check_status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| PAIR_01 | 39 | 0 | 0 | 35 | 2 | 2 | 89.743590 | PASS |
| PAIR_02 | 9 | 0 | 0 | 4 | 3 | 2 | 44.444444 | PASS |
| PAIR_03 | 8 | 2 | 1 | 2 | 1 | 2 | 25.000000 | PASS |
| PAIR_04 | 8 | 1 | 2 | 1 | 3 | 1 | 37.500000 | PASS |
| PAIR_05 | 8 | 0 | 0 | 1 | 4 | 3 | 50.000000 | PASS |
| PAIR_06 | 7 | 2 | 4 | 0 | 1 | 0 | 57.142857 | PASS |
| PAIR_07 | 6 | 3 | 0 | 2 | 1 | 0 | 50.000000 | PASS |
| PAIR_08 | 5 | 0 | 1 | 4 | 0 | 0 | 80.000000 | PASS |
| PAIR_09 | 5 | 5 | 0 | 0 | 0 | 0 | 100.000000 | PASS |
| PAIR_10 | 5 | 0 | 0 | 4 | 1 | 0 | 80.000000 | PASS |
| PAIR_11 | 5 | 2 | 0 | 0 | 1 | 2 | 40.000000 | PASS |
| PAIR_12 | 5 | 0 | 1 | 0 | 1 | 3 | 60.000000 | PASS |

The current screenshot's shortened top_month_share_pct displays normalize as follows.

| case_label | displayed | normalized six-decimal value |
| --- | --- | --- |
| PAIR_01 | 89.74359 | 89.743590 |
| PAIR_03 | 25 | 25.000000 |
| PAIR_04 | 37.5 | 37.500000 |
| PAIR_05 | 50 | 50.000000 |
| PAIR_07 | 50 | 50.000000 |
| PAIR_08 | 80 | 80.000000 |
| PAIR_09 | 100 | 100.000000 |
| PAIR_10 | 80 | 80.000000 |
| PAIR_11 | 40 | 40.000000 |
| PAIR_12 | 60 | 60.000000 |

The same twelve case labels and n_ab values retain the frozen SQL82 order. Each case's five monthly counts reconcile to its n_ab; its maximum-month share divides by that n_ab, not the cross-case sum of 110. PAIR_01 has 35 of its 39 paired baskets in July, whereas PAIR_09 has all five in May. Concentration alone does not fail a check or prove a data problem.

Basket month uses the earliest observed timestamp across all members of the candidate basket, not just the selected pair. This observation is not a confirmed order or payment time. The cases were selected using the same full snapshot, and the overall UTC observation window of 3 May to 18 September 2015 includes incomplete boundary months and unequal exposure. These retrospective counts are not monthly growth, comparable monthly rates or independent temporal validation.

The exact comparison of sixty private case/month/count cells, all 17,672 whole-basket anchors, accepted-input fingerprints and fixture behaviour remains supported by frozen assistant evidence. The screenshot does not independently establish those private calculations. The [machine-readable learner acceptance](../data/retailrocket_pair_month_coverage_learner_acceptance.json) retains raw display strings, normalized values and all ten formatting normalizations. Its report SHA-256 is `c15fb0f32ba48eea7cfd98da093a14a675d182eaac6a4560c4c66f5bb4d48b55`, matching the actual returned SQL report.

The prior 13,055-byte method and executed-results document remains byte-for-byte intact at SHA-256 `40cc5259b82605efd0444c06e8cea7b3d2a50f8840dd9ed7e77c2d6ba361f6de`; its frozen 7,671-byte prefix remains `183d6844786826de601c5fd5cc86ee23e4870bf256adcb484cf7bfc1a7ebf1f9`. This UTF-8 appendix records learner acceptance without rewriting earlier pending statements. No raw events, memberships or visitor/item/transaction identifiers are published, and no permanent case mapping is created.
