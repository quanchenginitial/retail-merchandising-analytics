# SQL85: observed visitor purchase-frequency baseline

## Purpose and population

This step begins the frequency component of an RF analysis. It describes how many observed candidate baskets belong to each transaction visitor ID during the supplied observation window. Recency, combined RF scores, segments and retention/loyalty interpretation are not implemented here. Identifiers are not verified people, candidate baskets are not independently verified paid orders, and observed-window frequency is not lifetime customer purchase frequency.

Use all accepted `rr_mart.transaction_basket_items` memberships, with no selected-pair, funnel, category or item filter. The population has 22,323 binary item memberships in 17,672 composite `(visitorid,transactionid)` baskets. Every purchasing identifier has at least one such basket; there is no F_0 band and the denominator is not every browsing visitor in events.csv. The expected 11,719 transaction visitor IDs are supported by the accepted transaction row of SQL70's event overview, in both `data/retailrocket_event_overview_preflight.json` and its learner-acceptance file. SQL70 is the overview step; SQL69 built the enriched event table.

The analytical readset is only three BIGINT keys: `visitorid,transactionid,itemid`. No timestamp, source-event occurrence count, product attribute or enriched-event field is queried. First deduplicate the full composite basket keys, then count baskets per visitor. Several item memberships in one basket contribute only one unit of frequency. The same transaction identifier under different visitor IDs remains distinct baskets. Original memberships and source occurrences remain unchanged.

## Five-row, seven-column report

Columns are `frequency_band,visitor_ids,visitor_share_pct,candidate_baskets,basket_share_pct,max_baskets_per_visitor,check_status`. Rows appear in this fixed order:

| Band | Observed baskets per visitor ID |
| --- | --- |
| F_1 | Exactly 1 |
| F_2 | Exactly 2 |
| F_3_4 | 3 or 4 |
| F_5_PLUS | At least 5 |
| TOTAL | All transaction visitor IDs |

These four descriptive bands are disjoint and exhaustive; their visitor and basket counts sum to TOTAL. They are not optimized behavioral segments. Visitor share divides a band's IDs by 11,719; basket share divides its baskets by 17,672. Do not interchange the denominators. Counts and maximum frequency are integers; percentages are rounded to six decimal places for display. An empty band remains visible with zero IDs/baskets/shares and NULL maximum. TOTAL's maximum is the largest observed frequency, not the sum of band maxima. Rounded band shares may differ very slightly from 100 due only to display precision; exact count partitions are the controls.

The source observations cover May 3 to September 18, 2015, with varying exposure by identifier. This frequency distribution alone cannot identify lifetime loyalty, churn, retention, unique customers or causal effects. The next recency step remains separate.

## Controls and failure behavior

Require the three BIGINT keys, no NULL or negative keys, unique `(visitorid,transactionid,itemid)` memberships, and the accepted source population controls: 22,323 rows, 17,672 baskets, 15,029 singleton baskets, 2,643 multi-item baskets and maximum size 31. Materialize admitted whole-basket keys only after these controls. Missing required columns can fail SQL binding; additional unqueried columns are allowed.

Every frequency must be positive and no larger than the entire basket population. The number of visitor-frequency rows must be 11,719 and their basket counts must sum to 17,672. The four band rows must partition these same two totals, with valid empty-band NULL maxima and nonnegative counts. The TOTAL row uses independently aggregated visitor frequencies. A particular frequency distribution is not expected in advance; valid arithmetic may PASS regardless of concentration.

Invalid source admission returns the five band labels with masked measurements and BLOCKED. A post-admission frequency or band-partition failure returns the labels with masked FAIL. PASS certifies the stated input and reconciliation controls, not customer value, loyalty or readiness of a completed RF segmentation.

## Independent bounded proof

Reuse the accepted SQL79 complete original-five-field and six-field membership proofs. The prior accepted analysis artifacts, including SQL84, supply progress/dependency provenance; their metric, contributor or monthly streams are not rerun. Pin accepted SQL70 overview evidence explicitly to support the 11,719 visitor-ID control. Do not run SQL54, SQL63, SQL70, SQL79 through SQL84, full historical suites or a full event external sort.

Parse events.csv once in canonical source order with the pinned helper, retain transaction occurrences within the existing cap, and reconstruct the ordered six-field membership tuples. Their canonical hash must match accepted SQL79's full membership fingerprint. Load only that small private six-column input and compare every row of its ordered readback. Source-byte identity hashes perform separate reads from the single canonical parse. Source timestamps are processed for reconstruction but are not part of SQL85's analytical readset.

Independent Python takes the unique composite basket-key set and counts each key once toward its visitor ID. Compare the complete private SQL frequency stream, sorted by visitorid, against that Counter: 11,719 rows by two exact integer fields, `visitorid,basket_count`. No private IDs are logged or published. Compute the four band summaries and TOTAL independently, compare all labels, integer counts, maxima and statuses exactly, and compare displayed six-decimal percentages with Fraction references within 0.5e-6 plus 1e-12 absolute floating allowance. The actual returned report receives its own exact digest.

Only three real CLI phases are permitted: private six-field load/readback, read-only frequency report, and read-only complete two-field visitor-frequency stream from the same query CTEs. No pair selection, full or selected metric stream, visitor-concentration stream or monthly scaffold is rebuilt as part of the new proof. The learner database, property files, category reference and enriched fact remain outside scope.

Focused fixtures cover frequencies 1, 2, 3, 4 and 5, multi-item baskets and shared transaction IDs under different visitors, then a small input with empty bands. They must establish whole-basket counting, both denominators, boundary classification and NULL empty maxima. Invalid key admission must visibly BLOCK, and an intentionally overlapping band boundary must FAIL partition reconciliation. No unrelated previous test suite is rerun.

Retain the existing 100,000 transaction-occurrence cap and add a 100,000 visitor-frequency-row cap, without filtering. Each CLI phase uses two threads, 1GB memory, 2GB maximum spill and a 120-second timeout. Require 8GB free workspace and a private-directory budget of 7GB; record after-phase size rather than claiming a continuous peak. Pin dependencies and all historical preflight files, verify source identity before/after, require unchanged private database bytes across read-only phases, and remove private memberships CSV, database and spills. Freeze this document before fixtures and the single source attempt, then append measured results without changing the prefix.

## Executed results

Assistant SQL85 preflight passed at 2026-11-13T06:28:04.545322+00:00 using v1.5.5 (Variegata) d8cdaa33fd. One real-source attempt completed all three declared CLI phases. The five-row, seven-column frequency report returned five PASS statuses and no FAIL or BLOCKED rows. Learner execution and screenshot acceptance remain pending.

| frequency_band | visitor_ids | visitor_share_pct | candidate_baskets | basket_share_pct | max_baskets_per_visitor | check_status |
| --- | --- | --- | --- | --- | --- | --- |
| F_1 | 10656 | 90.929260 | 10656 | 60.298778 | 1 | PASS |
| F_2 | 748 | 6.382797 | 1496 | 8.465369 | 2 | PASS |
| F_3_4 | 177 | 1.510368 | 575 | 3.253735 | 4 | PASS |
| F_5_PLUS | 138 | 1.177575 | 4945 | 27.982119 | 502 | PASS |
| TOTAL | 11719 | 100.000000 | 17672 | 100.000000 | 502 | PASS |

The four disjoint bands reconcile to all 11,719 transaction-recorded visitor IDs and all 17,672 candidate baskets. Visitor and basket shares use their respective separate denominators. The expected visitor count is explicitly confirmed by accepted SQL70's transaction overview in both preflight and learner evidence. This is not a distribution over all 1,407,580 event visitor IDs and has no F_0/non-transaction population. Frequency is observed in the finite supplied window, with unequal exposure by identifier; it does not establish lifetime loyalty, unique people, verified paid orders, retention or completed RF segmentation. Recency and combined scores remain pending.

One canonical events.csv parse reconstructed all 22,323 six-field memberships. Fingerprint `99c7d679d858b3d1335dfafa22aa48b5e842d03336af5c85330e96853c59fca5` matched accepted SQL79 and the complete private six-field readback. Separate source-byte hash scans also checked identity. Original-five-field proof was reused, while SQL54/63/70/79/80/81/82/83/84 and historical full suites were not rerun. Source timestamps were processed for reconstruction, but SQL85 queried only the three membership keys and no stored timestamps or occurrence weights.

The independent reference directly counted unique composite basket keys, then visitor IDs, without invoking pair, concentration or monthly calculations. All 11,719 private frequency rows across two integer fields matched exactly, in numeric visitor order. Their basket counts sum to 17,672. Public band labels, counts, maximums, NULL handling and statuses matched exactly; six-decimal shares matched independent Fraction references within 5.00001e-07 absolute tolerance. The actual returned report receives its own exact digest; no raw visitor IDs or individual frequency rows are published.

Two focused fixture families passed. Thirty-one item memberships in fifteen composite baskets produced five visitor frequencies 1,2,3,4,5, despite multi-item baskets, shared transaction identifiers across visitors and unused occurrence weights of seven. The boundary bands partitioned both visitor and basket totals. A separate input preserved three empty bands with zero counts/shares and NULL maxima. A NULL key returned BLOCKED and masked measurements; an overlapping band boundary returned FAIL and masked measurements. No unrelated previous test suite was repeated.

The canonical source parse/reconstruction took 32.968 seconds and the independent whole-basket frequency reference 0.06 seconds. CLI phases took 0.455 seconds for private input load/readback, 0.228 seconds for the frequency report and 0.291 seconds for the exact complete frequency stream. Each used two threads, 1GB memory and 2GB maximum spill and completed within 120 seconds. The largest private directory observed after a phase was 1,922,839 bytes, below 7GB, without claiming a continuously measured peak.

Source identity, pinned dependencies and all 83 historical preflight artifacts remained unchanged. Private database byte hashes matched across both read-only phases. Temporary membership CSV, database and spills were removed. The learner database, properties, category reference and enriched fact were not opened. Public artifacts contain only aggregate band results and proof fingerprints, without original source IDs or event records.

Report SHA-256: `4fe01bb6ca60f917757c289b0ac7569d5a1831769d16525a6dd3bcde9d6f07f8`. Script SHA-256: `ca02d51d5d5aa59b375fe1bb6ad1343247c3fdd58439e07082990c6771c72c4e`. Validator SHA-256: `048ec0032a5b9335707cbee8c4283cf867c394f14b591540c2dee0fe26386c6f`. The frozen 7,394-byte method prefix remains unchanged at `d97211d2c9684c014ee483b98459e01c44adc5707e7bc047f30b530a6c8b5727`.

## Learner acceptance — 13 November 2026

The learner supplied a DBeaver screenshot showing all five rows, seven column headers and 35 result fields of SQL85. These comprise five band labels, fifteen integer counts, ten percentage displays and five PASS labels. No INFO, FAIL, BLOCKED or NULL cells appear. Maximum frequency is one of the three integer-count columns; UI row numbers are excluded.

Six comma-formatted integer counts normalize by removing their thousands separators. F_1 visitor_share_pct displays 90.92926, and both TOTAL shares display 100; these three shortened percentages normalize to six decimals without changing values. The other seven percentage values already show six decimals. The two integer-looking TOTAL shares retain percentage semantics. Every field and band order matches the frozen preflight exactly; no hidden field, precision or label was inferred. Acceptance concerns the rounded returned report. The assistant did not open the learner database or rerun SQL, source parsing, private frequency streams or fixtures.

| frequency_band | visitor_ids | visitor_share_pct | candidate_baskets | basket_share_pct | max_baskets_per_visitor | check_status |
| --- | --- | --- | --- | --- | --- | --- |
| F_1 | 10656 | 90.929260 | 10656 | 60.298778 | 1 | PASS |
| F_2 | 748 | 6.382797 | 1496 | 8.465369 | 2 | PASS |
| F_3_4 | 177 | 1.510368 | 575 | 3.253735 | 4 | PASS |
| F_5_PLUS | 138 | 1.177575 | 4945 | 27.982119 | 502 | PASS |
| TOTAL | 11719 | 100.000000 | 17672 | 100.000000 | 502 | PASS |

| frequency_band | field | displayed | normalized six-decimal value |
| --- | --- | --- | --- |
| F_1 | visitor_share_pct | 90.92926 | 90.929260 |
| TOTAL | visitor_share_pct | 100 | 100.000000 |
| TOTAL | basket_share_pct | 100 | 100.000000 |

The four disjoint frequency bands reconcile to 11,719 transaction-recorded visitor IDs and 17,672 candidate baskets. Their shares use these separate denominators; TOTAL must not be added again to the bands. Frequency counts distinct composite candidate baskets, not item memberships, repeated events or purchased quantities. The population excludes F=0 and IDs without a recorded transaction; it is not the entire set of event visitor IDs.

F_1 contains 10,656 recorded IDs. F_5_PLUS contains 138 IDs and 4,945 candidate baskets, with a maximum frequency of 502. These are finite-window descriptive counts, not loyalty, customer-value or verified-person classifications. Candidate baskets are not verified paid orders. Recency and combined RF analysis remain unfinished. No empty band appears in this screenshot; zero-band NULL maxima remain supported by the frozen fixture evidence rather than direct observation here.

The exact comparison of all 11,719 private visitor/frequency rows across two integer fields, accepted-input fingerprints and fixture behaviour remains supported by the frozen assistant preflight. The [machine-readable learner acceptance](../data/retailrocket_visitor_purchase_frequency_learner_acceptance.json) retains raw displayed strings, normalized values, all three percentage normalizations and all six comma-formatted count normalizations. Its report SHA-256 is `4fe01bb6ca60f917757c289b0ac7569d5a1831769d16525a6dd3bcde9d6f07f8`, matching the returned SQL report fingerprint.

The prior 11,943-byte method and executed-results document remains byte-for-byte intact at SHA-256 `e91ac98fdd3a6d45aaf94ea98dbcf65c6d215fee329fd91a3bc78a8d8f0221fc`; its frozen 7,394-byte prefix remains `d97211d2c9684c014ee483b98459e01c44adc5707e7bc047f30b530a6c8b5727`. This UTF-8 appendix records learner acceptance without rewriting earlier pending statements. No raw source records, memberships or visitor/item/transaction identifiers are published.
