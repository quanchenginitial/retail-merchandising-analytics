# SQL82: inspect selected candidate-basket pairs

## Purpose and frozen scope

SQL81 showed that increasingly strict co-occurrence thresholds retain sharply fewer pairs. SQL82 inspects every pair observed in at least five candidate baskets, a manageable exploratory set of 12 pairs. Five is not an optimized or validated decision threshold. There is no LIMIT, top-N truncation, new stored table or recommendation deployment.

Input remains the accepted `rr_mart.transaction_basket_items` relation. The analytical readset consists only of BIGINT `visitorid,transactionid,itemid`. Membership is binary and the basket key contains both visitor and transaction identifiers. `source_event_rows` and timestamp fields are not queried. The accepted 22,323 memberships form 17,672 candidate baskets, including 15,029 singletons; 2,643 baskets have multiple items and maximum size is 31. These candidate baskets are not independently verified paid orders.

All-basket item marginals and formulas are unchanged from accepted SQL81. For a pair with basket count n_ab and marginals n_a and n_b, support is n_ab/N, directional confidences are n_ab/n_a and n_ab/n_b, and lift is N*n_ab/(n_a*n_b), with N=17,672. Singleton baskets remain in both N and the marginals. All calculations use unrounded ratios before six-decimal display rounding. Lift describes association, not causal influence, product complementarity, recommendation performance, quantity or revenue.

## Case identity, ordering and output

The public report has 12 rows and these nine columns, in order: `case_label,n_ab,n_a,n_b,support_pct,confidence_a_to_b_pct,confidence_b_to_a_pct,lift,check_status`. Counts are integers; percentages and lift are displayed to six decimal places. Labels are PAIR_01 through PAIR_12. Item A and item B use internal numeric identifier order; A/B are local to each pair, not global product aliases or a causal direction.

All qualifying pairs are ordered by n_ab descending, unrounded lift descending, numeric item_a ascending and numeric item_b ascending. With fixed N and equal n_ab, lift descending is exactly equivalent to n_a*n_b ascending. The SQL uses that exact integer product to avoid floating-point tie ambiguity, followed by the numeric identifier tie-breakers. Given this fixed input fingerprint and query, case labels can be reconstructed from the internal `selected_pairs` CTE for later case drilldowns. Labels may change if input, threshold, scope or ordering changes. No persistent file of real-ID mappings is needed, and the label scheme is not a guarantee of anonymization.

The private selected relation retains real keys and the ten fields `item_a,item_b,n_ab,n_a,n_b,n_baskets,support,confidence_a_to_b,confidence_b_to_a,lift`. Neither raw identifiers nor individual event rows are published. The report contains case-level count/rate summaries. Twelve qualifying pairs and their 110 summed pair occurrences are controls established by SQL81. The 110 occurrences are not uniquely covered baskets and must not be described as 110 distinct orders.

## Controls and failure behavior

Before the self-join, reuse the accepted key schema, nonnegative/non-NULL/unique key and input population controls. The materialized admitted key set prevents invalid input from entering the pair join. After aggregation, retain SQL81's five accepted pair controls, choose-two reconciliation, marginal sum, row retention and metric bounds. The full accepted pair population is 9,688 pairs and 10,757 occurrences; 8,785 pairs occur once, 903 occur at least twice and maximum frequency is 39.

The selected relation contains all n_ab>=5 pairs without a LIMIT. Its complete count must be 12 and its summed occurrences 110. The fixed report slots are not a hidden truncation: if the actual selection has more or fewer rows, the selection gate fails and all measured fields are masked. Invalid source admission yields 12 case labels with NULL measured fields and BLOCKED status. Post-admission pair or selection control failure yields the labels with NULL measured fields and FAIL status. Missing required source columns may instead fail SQL binding. PASS certifies computational and population controls; it does not establish commercially useful recommendations.

## Bounded independent proof

Reuse SQL79's accepted complete original-five-field proof and SQL81's accepted full 9,688-by-ten metric proof. Do not rerun SQL54, SQL63, SQL79, SQL80, SQL81, previous full suites or a full event external sort. Parse events.csv once in canonical source order and reconstruct the six-field memberships through the pinned existing helper. Their canonical ordered hash must match the accepted SQL79 membership-stream fingerprint, and the small private six-column table must match the full reconstructed input on readback. Source identity hashing also reads file bytes, separately from the single canonical parse.

Independent Python reuses the pinned rational metric helper to enumerate pairs and all-basket marginals, then selects every n_ab>=5 pair and sorts with the same mathematically specified exact count-product order. The newly compared SQL metric stream contains only the selected 12 rows, not all 9,688 pairs. Compare the six integer fields exactly and four unrounded metrics against Fraction-derived references with absolute and relative tolerances of 1e-12. Compare the entire 12-by-nine case report in order: case labels/counts/status exactly, and six-decimal percentages/lift within 0.5e-6 plus a 1e-12 floating allowance of the independent rational value. The actual returned report receives its own exact digest.

Only three real CLI phases are allowed: load/readback the private six-field input, execute the read-only case report, and read the selected ten-field metric stream from the same public query CTEs in case-rank order. There is no persistent private ID mapping export. The learner database, properties, category reference, enriched event fact and UTC-derived fields remain outside scope.

Focused fixtures address new selection behavior only: more than 12 qualifying pairs to establish no LIMIT, exact threshold inclusion/exclusion, lift and numeric-key ties with deterministic labels, and complete selection matching. Include a singleton that changes a marginal and therefore the tie order. Invalid empty source must visibly BLOCK rather than return a misleading empty success, and an intentionally wrong selection control must FAIL with masked values. Prior full mathematical and admission suites are reused, not repeated.

Retain 100,000 caps for transaction occurrences, pair occurrences and distinct pair keys, with no filtering to satisfy a cap. Each CLI phase uses two threads, 1GB memory, 2GB maximum spill and a 120-second timeout. Require 8GB available workspace space and keep the private directory within 7GB. Record observed size after phases rather than a claimed continuous peak. Pin dependencies and all historical preflight files, compare source identity before and after, ensure private database bytes do not change across read-only phases, and remove the private membership CSV, database and spills. Freeze this method before fixtures and the single source attempt; append measured results without changing its prefix.

## Executed results

Assistant SQL82 preflight passed at 2026-11-13T04:48:45.986208+00:00 using v1.5.5 (Variegata) d8cdaa33fd. One real-source attempt completed the three declared CLI phases. All 12 rows of the nine-column case report returned PASS, with no FAIL or BLOCKED rows. Learner execution and screenshot acceptance remain pending.

| case_label | n_ab | n_a | n_b | support_pct | confidence_a_to_b_pct | confidence_b_to_a_pct | lift | check_status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| PAIR_01 | 39 | 92 | 45 | 0.220688 | 42.391304 | 86.666667 | 166.475362 | PASS |
| PAIR_02 | 9 | 13 | 133 | 0.050928 | 69.230769 | 6.766917 | 91.988433 | PASS |
| PAIR_03 | 8 | 8 | 133 | 0.045269 | 100.000000 | 6.015038 | 132.872180 | PASS |
| PAIR_04 | 8 | 11 | 133 | 0.045269 | 72.727273 | 6.015038 | 96.634313 | PASS |
| PAIR_05 | 8 | 19 | 133 | 0.045269 | 42.105263 | 6.015038 | 55.946181 | PASS |
| PAIR_06 | 7 | 18 | 19 | 0.039611 | 38.888889 | 36.842105 | 361.707602 | PASS |
| PAIR_07 | 6 | 7 | 12 | 0.033952 | 85.714286 | 50.000000 | 1262.285714 | PASS |
| PAIR_08 | 5 | 5 | 7 | 0.028293 | 100.000000 | 71.428571 | 2524.571429 | PASS |
| PAIR_09 | 5 | 17 | 5 | 0.028293 | 29.411765 | 100.000000 | 1039.529412 | PASS |
| PAIR_10 | 5 | 19 | 5 | 0.028293 | 26.315789 | 100.000000 | 930.105263 | PASS |
| PAIR_11 | 5 | 13 | 9 | 0.028293 | 38.461538 | 55.555556 | 755.213675 | PASS |
| PAIR_12 | 5 | 7 | 92 | 0.028293 | 71.428571 | 5.434783 | 137.204969 | PASS |

These are all 12 observed pairs meeting n_ab>=5, with 110 summed pair occurrences, not a truncated top-N list or 110 unique covered baskets. Support and marginals retain the full 17,672 candidate-basket population including singletons. Labels follow n_ab descending, exact n_a*n_b ascending, then numeric internal item keys; A/B are pair-local. The case mapping is reproducible for this frozen snapshot and query, may change under a different input or selection, and is not an anonymization guarantee. Five remains an exploratory threshold without a claim of optimality or validated recommendation value.

One canonical source parse reconstructed the accepted 22,323 six-field membership tuples. Hash `99c7d679d858b3d1335dfafa22aa48b5e842d03336af5c85330e96853c59fca5` matched SQL79's accepted full membership-stream fingerprint and the complete private six-field readback. Source byte identity hashing performed separate reads. Original-five-field proof and SQL81's full metric proof were reused, without rerunning SQL54/63/79/80/81, the full event sort or historical suites.

The current query computes its pair metric population and applies all accepted population and metric controls. The newly independently compared SQL metric stream was deliberately limited to the complete selected set: 12 rows by ten fields, in case-rank order. Six integer fields matched exactly and four unrounded metrics matched Fraction references within absolute and relative tolerances of 1e-12; maximum observed absolute error was 0.0. This does not claim a new full 9,688-row metric-stream comparison. All labels, counts and statuses in the ordered case report matched exactly; displayed percentages and lifts matched independent rational values within 5.00001e-07 absolute tolerance.

Two focused fixture families passed. A synthetic 80-basket input supplied 15 qualifying pairs plus one pair below the threshold; every qualifying pair was returned, establishing the absence of a hidden 12-row limit. Equal lifts followed numeric key ties, while a singleton changed one marginal and moved that pair after the exact ties. Empty source returned visible case labels with BLOCKED and masked measurements. An incorrect selection-total expectation returned FAIL with masked measurements. An initial fixture-only identifier collision was corrected before the real-source attempt; no real source execution was repeated.

The canonical source parse/reconstruction took 16.276 seconds and independent rational metric selection 0.155 seconds. CLI phases took 0.263 seconds for private input load/readback, 0.149 seconds for the case report and 0.143 seconds for the selected metric stream. Each phase used two threads, 1GB memory and 2GB maximum spill and completed within 120 seconds. The largest private directory observed after a phase was 1,922,839 bytes, below 7GB, without claiming a continuously measured peak.

Source identity and dependency hashes remained unchanged, as did all 80 historical preflight artifacts. Private database byte hashes matched across both read-only phases. Temporary membership CSV, databases and spills were removed; no persistent mapping file was created. No learner database, property files, category reference, enriched fact or UTC-derived fields were accessed. Public artifacts contain snapshot case labels and aggregate count/rate summaries, without raw source identifiers or event rows. The cases support exploratory inspection of observed association, not causal, quantity, revenue or verified-order claims.

Report SHA-256: `170c95058d3b06fcf2645ca04232bca95a007db6cbe5c64bcffb813c50c90b52`. Script SHA-256: `5067c4f85ab4a99ea995fa29ca009d0c15de9f06c40842ce72142015e5bff32f`. Validator SHA-256: `0ddaa9af909ca726e060035c14251e7f706376190d1c38684d21c85e872599fe`. The original 7,239-byte method prefix remains unchanged at `04726b98a1b9c16751148a842b3ec1208336cb282d3371da4ed032b065b0d28f`.

## Learner acceptance — 13 November 2026

The learner supplied a DBeaver screenshot showing all twelve rows, nine column headers and one hundred eight result fields of the SQL82 selected pair-case report. The visible fields comprise twelve case labels, thirty-six integer-count values, forty-eight decimal-metric displays and twelve PASS labels. Five confidence cells look like integers because the interface omits trailing zeroes, but remain metric fields; one lift cell displays five decimals. UI row numbers are excluded. All twelve statuses are PASS, with no INFO, FAIL, BLOCKED or NULL cells.

Thousands separators were removed and six shortened metric displays were restored to six-decimal notation without changing values. Every displayed report field and its case order matches the frozen preflight exactly. This accepts the rounded report rather than claiming direct observation or mathematical exactness of unrounded metrics. No labels, hidden fields or missing precision were inferred. The assistant did not open the learner database or rerun SQL, source parsing, input reconstruction, metric streams or fixtures for this acceptance.

| case_label | n_ab | n_a | n_b | support_pct | confidence_a_to_b_pct | confidence_b_to_a_pct | lift | check_status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| PAIR_01 | 39 | 92 | 45 | 0.220688 | 42.391304 | 86.666667 | 166.475362 | PASS |
| PAIR_02 | 9 | 13 | 133 | 0.050928 | 69.230769 | 6.766917 | 91.988433 | PASS |
| PAIR_03 | 8 | 8 | 133 | 0.045269 | 100.000000 | 6.015038 | 132.872180 | PASS |
| PAIR_04 | 8 | 11 | 133 | 0.045269 | 72.727273 | 6.015038 | 96.634313 | PASS |
| PAIR_05 | 8 | 19 | 133 | 0.045269 | 42.105263 | 6.015038 | 55.946181 | PASS |
| PAIR_06 | 7 | 18 | 19 | 0.039611 | 38.888889 | 36.842105 | 361.707602 | PASS |
| PAIR_07 | 6 | 7 | 12 | 0.033952 | 85.714286 | 50.000000 | 1262.285714 | PASS |
| PAIR_08 | 5 | 5 | 7 | 0.028293 | 100.000000 | 71.428571 | 2524.571429 | PASS |
| PAIR_09 | 5 | 17 | 5 | 0.028293 | 29.411765 | 100.000000 | 1039.529412 | PASS |
| PAIR_10 | 5 | 19 | 5 | 0.028293 | 26.315789 | 100.000000 | 930.105263 | PASS |
| PAIR_11 | 5 | 13 | 9 | 0.028293 | 38.461538 | 55.555556 | 755.213675 | PASS |
| PAIR_12 | 5 | 7 | 92 | 0.028293 | 71.428571 | 5.434783 | 137.204969 | PASS |

The six shortened displays normalize as follows; comma removal is independent of precision normalization.

| case_label | field | displayed | normalized six-decimal value |
| --- | --- | --- | --- |
| PAIR_03 | confidence_a_to_b_pct | 100 | 100.000000 |
| PAIR_03 | lift | 132.87218 | 132.872180 |
| PAIR_07 | confidence_b_to_a_pct | 50 | 50.000000 |
| PAIR_08 | confidence_a_to_b_pct | 100 | 100.000000 |
| PAIR_09 | confidence_b_to_a_pct | 100 | 100.000000 |
| PAIR_10 | confidence_b_to_a_pct | 100 | 100.000000 |

The accepted report contains all twelve pairs meeting n_ab≥5, with 110 summed pair occurrences; it is not a truncated top-N list, and 110 is not distinct basket coverage. The denominator remains all 17,672 candidate baskets, including singletons for support and item marginals. Each case displays its own two directional confidences, with percentages for support/confidence and dimensionless lift. Source-event counts are not weights.

PAIR_01–PAIR_12 are labels for this fixed snapshot and query. A/B reflect numeric roles within each pair and do not identify the same product across rows or establish causal direction. Labels can change under a refreshed input; they are not an anonymization guarantee or a business recommendation ranking. No permanent private mapping is created. The five-count threshold was chosen after the profile for a manageable exploratory set, not as an optimal cutoff or assurance that every case is reliable. High lift and inclusion do not prove verified orders, simultaneous purchases, complementarity or recommendation uplift.

The selected twelve-row, ten-field independent metric comparison, accepted-input fingerprints and fixture behaviour remain supported by frozen assistant evidence rather than new direct checks of the learner environment. No full 9,688-row metric-stream proof is repeated for acceptance.

The [machine-readable learner acceptance](../data/retailrocket_basket_pair_cases_learner_acceptance.json) records raw displayed strings, normalized values and all six precision normalizations. Its report SHA-256 is `170c95058d3b06fcf2645ca04232bca95a007db6cbe5c64bcffb813c50c90b52`, matching the actual SQL report fingerprint. The prior 12,629-byte method and executed-results document remains byte-for-byte intact at SHA-256 `a6e57e6f7fb48672f02269a2375f811f0f5c46d194e1fb01e4e6b84694eece94`; its frozen 7,239-byte prefix remains `04726b98a1b9c16751148a842b3ec1208336cb282d3371da4ed032b065b0d28f`. This UTF-8 appendix records learner acceptance without rewriting earlier pending statements. No raw events, memberships or visitor/item/transaction identifiers are published.
