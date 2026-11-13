# SQL81: candidate-basket association metrics

## Purpose and frozen scope

SQL80 established the count of binary unordered item pairs. SQL81 computes support, both directional confidences and lift, then shows how their distributions change across five diagnostic co-occurrence thresholds. This is a read-only query, not a new stored table or a recommendation system. No item-pair identities are published in the report or evidence.

Input is the accepted `rr_mart.transaction_basket_items` relation. The analytical readset is only `visitorid`, `transactionid`, `itemid`, each BIGINT. The timestamp bounds and `source_event_rows` are not queried. Membership is binary: repeated source event occurrences do not weight a basket, marginal or pair. Candidate basket identity uses both visitor and transaction identifiers. These groups are not independently verified paid orders.

The population remains all 17,672 candidate baskets, including 15,029 singleton baskets. Item marginals count each item once in every basket containing it, including singletons. The accepted 22,323 memberships, 2,643 multi-item baskets and maximum size 31 are input controls. Unordered pairs use numeric `item_a < item_b` and both basket-key fields in the join. Accepted SQL80 pair controls are 10,757 occurrences, 9,688 distinct pairs, 8,785 seen once, 903 seen at least twice, and maximum frequency 39.

## Definitions and output

For a pair, let `n_ab` be its basket count, `n_a` and `n_b` the respective item basket counts, and `N` the full candidate-basket count. The private reusable ten-column metric relation is ordered as `item_a,item_b,n_ab,n_a,n_b,n_baskets,support,confidence_a_to_b,confidence_b_to_a,lift`.

- Support is `n_ab / N`.
- Confidence A to B is `n_ab / n_a`; confidence B to A is `n_ab / n_b`.
- Lift is `N * n_ab / (n_a * n_b)`, calculated without rounding intermediate ratios.

Lift above one describes observed co-occurrence relative to the product of the observed marginals. It does not demonstrate causality, product complementarity, statistical significance, recommendation effectiveness, quantity or revenue.

One five-row, nine-column report is returned:

| Column | Meaning |
| --- | --- |
| min_pair_baskets | Minimum observed co-occurrences: 1, 2, 3, 5 or 10 |
| retained_pairs | Distinct unordered pairs meeting the threshold |
| retained_pair_pct | Retained pairs divided by all 9,688 observed distinct pairs, times 100 |
| retained_pair_occurrences | Sum of n_ab for retained pairs; not a count of unique covered baskets |
| median_support_pct | Equal-pair median support, times 100; denominator remains all 17,672 baskets |
| median_directional_confidence_pct | Median of both confidence directions for every retained pair, equally weighted, times 100 |
| median_lift | Equal-pair median lift |
| max_lift | Maximum lift among retained pairs |
| check_status | PASS, BLOCKED or FAIL according to the controls below |

The five threshold rows are nested, not disjoint and never summed; there is no TOTAL row. Thresholds are diagnostics, not an optimal rule selection. Numeric item ordering has no business direction: both confidences are pooled, so arbitrary identifier order does not determine the median. None of the distribution summaries are basket-frequency weighted. Counts are integers; all percentage and lift summaries are rounded to six decimal places only for display. A qualifying-empty threshold retains zero pair and occurrence counts, zero retained percentage when the overall pair population is nonempty, and NULL metric summaries.

## Admission and calculation controls

Before the self-join, the materialized admitted key set requires BIGINT types, nonnegative and non-NULL keys, unique three-field memberships, and all accepted input population counts. Invalid admission returns five threshold labels with every other measured field NULL and status BLOCKED. A missing required column can instead fail SQL binding. Additional unqueried columns are allowed.

After pair aggregation, the accepted SQL80 pair counts are checked before results are displayed. The choose-two total across all baskets must reconcile to pair occurrences; frequency bins must reconcile to distinct pairs. Item marginal counts must sum to memberships, and the metric join must retain every pair. Every metric must satisfy `0 < n_ab <= min(n_a,n_b) <= N`; support and both confidences must lie in (0,1], and lift must be positive and finite. A post-admission control failure masks the measured outputs and returns FAIL. PASS certifies these computational controls, not that the discovered associations are commercially useful.

## Independent bounded proof

The proof reuses SQL79's accepted original-five-field occurrence comparison and SQL80's accepted counts. It does not rerun SQL54, SQL63, SQL79, SQL80, their past suites or a full event external sort. It parses events.csv once in canonical source order, preserves transaction occurrences, reconstructs the six-field membership tuples using the pinned existing helper, and requires their canonical sorted hash to equal SQL79's accepted full membership-stream fingerprint. Source bytes and metadata must also match the recorded source audit. This is explicitly not a fresh complete original-five-field stream comparison.

Independent Python enumerates numeric unordered item combinations within both basket-key fields, counts item marginals over all memberships and calculates the four metrics using exact Fraction arithmetic. All six integer fields of each private ten-column metric row must match exactly. Four unrounded floating metrics must match the independent rational reference with absolute and relative tolerances of 1e-12. Exact integer cross-products also verify the rational identities. The independently computed equal-weight medians and maxima validate the report; six-decimal displays may differ from mathematically exact values by at most 0.5e-6 plus a 1e-12 float allowance. The actual returned report has its own exact digest, without pretending a rounded boundary has infinite precision.

Only three real DuckDB CLI phases are allowed: (1) load the small private six-column membership CSV and compare its entire ordered readback, (2) execute the read-only SQL81 profile, (3) stream all ten columns of every pair metric from the same public query CTEs for independent comparison. The learner database is never opened. Property files, category reference, enriched event table and UTC-derived fields remain outside scope. Original source identifiers and individual metric rows are neither printed nor included in public artifacts.

Transaction occurrences, pair occurrences and distinct pair keys are each capped at 100,000 without filtering. Each CLI phase uses two threads, 1GB memory, 2GB maximum spill and a 120-second timeout. Require 8GB available workspace space and a private-directory budget of 7GB. Record observed private-directory size after phases, not a claimed continuous peak. Pin dependencies and all historical preflight files, check source identity before and after, require the private database bytes unchanged across the two read-only phases, and remove private database, membership CSV and spills.

Focused fixtures add only the new mathematical and control boundaries: known asymmetric marginals with singleton baskets, equal-pair rather than occurrence-weighted distributions, empty higher-threshold rows with NULL summaries, ignored source-event weights, invalid admission, and a failing accepted pair-control expectation. No broad historical suite is repeated. Freeze this document before fixtures and the single real-source attempt, then append measured results without changing the prefix.

## Executed results

Assistant SQL81 preflight passed at 2026-11-13T04:17:05.227003+00:00 using v1.5.5 (Variegata) d8cdaa33fd. One real-source attempt completed all three declared CLI phases. The five-row, nine-column report contains five PASS rows and no FAIL or BLOCKED rows. Learner execution and screenshot acceptance remain pending.

| min_pair_baskets | retained_pairs | retained_pair_pct | retained_pair_occurrences | median_support_pct | median_directional_confidence_pct | median_lift | max_lift | check_status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 9688 | 100.000000 | 10757 | 0.005659 | 60.000000 | 5890.666667 | 17672.000000 | PASS |
| 2 | 903 | 9.320809 | 1972 | 0.011317 | 66.666667 | 4418.000000 | 8836.000000 | PASS |
| 3 | 79 | 0.815442 | 324 | 0.016976 | 75.000000 | 1325.400000 | 5890.666667 | PASS |
| 5 | 12 | 0.123865 | 110 | 0.036781 | 46.195652 | 264.091482 | 2524.571429 | PASS |
| 10 | 1 | 0.010322 | 39 | 0.220688 | 64.528986 | 166.475362 | 166.475362 | PASS |

All thresholds use the same 17,672 candidate baskets for support and item marginals, including 15,029 singleton baskets. Retained-pair percentages instead use the 9,688 observed distinct pairs as their denominator. Rows are cumulative threshold diagnostics and must not be added. Retained occurrences count pair appearances, not uniquely covered baskets. These summaries do not select an optimal threshold or establish commercial recommendation value.

One canonical events.csv parse reconstructed 22,323 six-field memberships from 22,457 transaction event occurrences. Its hash `99c7d679d858b3d1335dfafa22aa48b5e842d03336af5c85330e96853c59fca5` matched the accepted SQL79 full membership-stream fingerprint and the complete private six-field readback. SQL79's original-five-field occurrence proof was reused; SQL54, SQL63, SQL79, SQL80 and full historical suites were not rerun. Source identity hashes also read file bytes, separately from the single parse. The SQL analytical readset remains the three membership keys.

Independent Python verified all 9,688 ten-column pair metric rows. Six integer fields matched exactly; four unrounded metrics matched exact Fraction references under absolute and relative tolerances of 1e-12. Maximum observed absolute metric error was 0.0. Rational identities were checked using integer-derived fractions. The actual returned report's integer fields matched exactly; independent rational medians/maxima matched the six-decimal displays within 5.00001e-07 absolute tolerance. The report digest records the actual SQL output, not an assertion that rounded floating values are mathematically exact.

Two focused fixture families passed. The known five-basket example includes two singleton baskets, asymmetric marginals and pairs occurring two times and once: it verifies support median 30%, pooled directional confidence median 175/3%, and equal-pair lift median 25/24, with individual lifts 5/6 and 5/4. Empty higher thresholds return zero counts and NULL metric summaries. Changing unused source-event weights leaves the report unchanged. Duplicate or empty input returns BLOCKED with measured fields masked; a wrong accepted pair-count expectation returns FAIL with measured fields masked. No broad previous test suite was repeated.

The source parse/reconstruction took 17.088 seconds and the independent metric reference 0.245 seconds. CLI times were 0.259 seconds for the private input load/readback, 0.153 seconds for the read-only profile and 0.283 seconds for the complete metric stream. Every phase used two threads, 1GB memory and 2GB maximum spill and completed within 120 seconds. The largest observed private-directory size after a phase was 1,922,839 bytes, below 7GB; no continuous peak was claimed.

Source identity, pinned dependency hashes and all 79 historical preflight files remained unchanged. Private database hashes matched before and after both read-only phases. All private membership CSV, database and spill files were removed. No learner database, property files, category reference or enriched fact was opened. Public evidence contains aggregate summaries and fingerprints only, without source IDs or a pair list. The results describe observed binary association, not quantities, revenue, verified paid orders or causal effects.

Report SHA-256: `a0bc66720b6b0e15ab2086308851949b1e6e9c8f99a8d3086ae7e25a20d5bdf1`. Script SHA-256: `d0c2600a49becb4f09de5f52a2e56dca4804c035b4c1eff0a9206cde13be0ecd`. Validator SHA-256: `e81b8c908fb4475b201afa5fbbc80714a3f4eb16f02be1334e2f2a8a8d3f3dcf`. The original 7,695-byte method prefix remains unchanged at `3f825703a4ef994189cd071c1f877fc43576ff3ae618b757fa9a376ac4dd4ea1`.

## Learner acceptance — 13 November 2026

The learner supplied a DBeaver screenshot showing all five rows, nine column headers and forty-five result fields of the SQL81 nested threshold profile. The visible fields comprise fifteen integer-count values, twenty-five decimal-metric displays and five PASS labels. Six metric cells look like integers because the interface omits trailing zeroes, but remain metric fields; one further metric cell displays a single decimal. UI row numbers are excluded. All five statuses are PASS, with no INFO, FAIL, BLOCKED or NULL cells.

Thousands separators were removed and seven shortened metric displays were restored to the report's six-decimal notation without changing their values. Every displayed report value matches the frozen preflight exactly. This is acceptance of the rounded report: it does not claim the screenshot reveals unrounded metrics or mathematically exact floating-point calculations. No cropped fields, labels or hidden values were inferred. The assistant did not open the learner database or rerun SQL, source parsing, membership reconstruction, metric streams or fixtures for this acceptance.

| min_pair_baskets | retained_pairs | retained_pair_pct | retained_pair_occurrences | median_support_pct | median_directional_confidence_pct | median_lift | max_lift | check_status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 9688 | 100.000000 | 10757 | 0.005659 | 60.000000 | 5890.666667 | 17672.000000 | PASS |
| 2 | 903 | 9.320809 | 1972 | 0.011317 | 66.666667 | 4418.000000 | 8836.000000 | PASS |
| 3 | 79 | 0.815442 | 324 | 0.016976 | 75.000000 | 1325.400000 | 5890.666667 | PASS |
| 5 | 12 | 0.123865 | 110 | 0.036781 | 46.195652 | 264.091482 | 2524.571429 | PASS |
| 10 | 1 | 0.010322 | 39 | 0.220688 | 64.528986 | 166.475362 | 166.475362 | PASS |

The seven shortened displays normalize as follows; comma removal is independent of precision normalization.

| min_pair_baskets | field | displayed | normalized six-decimal value |
| --- | --- | --- | --- |
| 1 | retained_pair_pct | 100 | 100.000000 |
| 1 | median_directional_confidence_pct | 60 | 60.000000 |
| 1 | max_lift | 17,672 | 17672.000000 |
| 2 | median_lift | 4,418 | 4418.000000 |
| 2 | max_lift | 8,836 | 8836.000000 |
| 3 | median_directional_confidence_pct | 75 | 75.000000 |
| 3 | median_lift | 1,325.4 | 1325.400000 |

The accepted nested minimum-count thresholds 1, 2, 3, 5 and 10 retain 9,688, 903, 79, 12 and 1 distinct pairs. They share the same 17,672 candidate-basket denominator for support and item marginals, while retained_pair_pct uses all 9,688 observed distinct pairs. Single-item candidates remain in the population. Each retained pair contributes its two directional confidences once to the pooled median; support and confidence are percentages, and lift is dimensionless. Retained pair occurrences sum appearances across pairs, not uniquely covered baskets. Rows overlap and must not be added.

This profile supports discussion of sparse co-occurrence and count thresholds; it does not establish an optimal cutoff, validated rule ranking, commercial recommendation benefit or causal effect. Candidate baskets remain a diagnostic grouping rather than verified orders or simultaneous purchases. The full unrounded ten-field metric comparison, accepted-input fingerprints and fixture behaviour remain supported by the frozen assistant evidence rather than new direct checks of the learner environment.

The [machine-readable learner acceptance](../data/retailrocket_basket_association_metrics_learner_acceptance.json) records the raw displayed strings, normalized values and seven precision normalizations. Its report SHA-256 is `a0bc66720b6b0e15ab2086308851949b1e6e9c8f99a8d3086ae7e25a20d5bdf1`, matching the actual SQL report fingerprint. The prior 12,389-byte method and executed-results document remains byte-for-byte intact at SHA-256 `98dacdfbe2752aa698b6eeae89d95bfe76b4c0c3821fd5be955d3b8858c2de30`; its frozen 7,695-byte prefix remains `3f825703a4ef994189cd071c1f877fc43576ff3ae618b757fa9a376ac4dd4ea1`. This UTF-8 appendix records learner acceptance without rewriting earlier pending statements. No raw events, memberships, item-pair lists or visitor/item/transaction identifiers are published.
