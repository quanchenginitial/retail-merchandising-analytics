# Weekly triage of fixed-rule sales candidates

## Purpose and state

The learner accepted [SQL51](ANOMALY_CANDIDATES_VALIDATION.md) on **2 November 2026**, with all sixty visible fields and five PASS statuses matching its frozen report. Its three candidate classes contain 12,347 of 243,920 target positions, approximately 5.0619%. These are heuristic review positions, not independently verified events or unique products.

[SQL52](../sql/52_weekly_anomaly_triage.sql) provides one chronological overview of workload and unit-change magnitude before deterministic candidate-history review. **Assistant preflight has passed; learner SQL52 execution and acceptance remain pending.** This descriptive follow-up was chosen after seeing SQL51's global candidate counts, rather than being presented as a preregistered hypothesis test. The [weekly report protocol](WEEKLY_ANOMALY_TRIAGE_PROTOCOL.md) fixes its grouping and measures before computing these weekly outcomes. The original classification rules and thresholds remain unchanged.

## Fixed population and measures

Reuse the entire accepted classification: 30,490 item/store pairs × eight target weeks, 11605–11612, within the twelve-week input spanning 30 January–22 April 2016. The target window is **27 February–22 April 2016**. No pair, zero observation, missing-price context or candidate class is removed. Each baseline remains the same pair's four strictly preceding actual weeks; prior flagged observations remain in later actual histories.

Return **eight chronological rows and twelve columns, without TOTAL**. A fixed week scaffold retains even a week without candidates. Each target_rows is 30,490. The three candidate counts plus none_rows equal target_rows; candidate_rows is the sum of the three candidate classes. candidate_share_pct uses all weekly targets, including NONE, as its denominator and is rounded once to four decimals. Counts across eight weeks are additive target positions; they do not become distinct pairs or independent statistical trials.

Let delta4=4y−S, where y is current sales and S the sum of the four prior actual weeks. upward_gap_units is SUM(delta4)/4 only for LARGE_INCREASE. downward_gap_units is −SUM(delta4)/4 for SUDDEN_ZERO and LARGE_DECREASE together. Both are nonnegative exact quarter-unit sums, displayed to two decimals. No within-target or within-week rounding changes their arithmetic. Zero-candidate weeks show zero counts, zero share and zero gaps.

Across all weeks, class counts must equal SQL51's 902 / 6,118 / 5,327 / 231,573, and candidate_rows must sum to 12,347. The upward total equals SQL51's LARGE_INCREASE signed difference, **105,974.00 units**. The downward total is the negative sum of SUDDEN_ZERO and LARGE_DECREASE signed differences, **104,809.75 units**. Their net difference, **1,164.25**, excludes NONE's **9,894.00** signed units and therefore is not the all-target net difference of **11,058.25**.

These gaps describe departures from a four-week historical reference. They are not lost sales, incremental sales attributable to an intervention, price effects, financial amounts or independently estimated forecast errors. Candidate class direction is imposed by the rule; its gap sign is not evidence of classification quality. NONE remains unflagged, not verified normal. PASS validates the computational contract, not an operational cause.

## Independent validation actually executed

The [validator](../validation/preflight_weekly_anomaly_triage.py) uses original read-only CSVs and the existing independent source helpers in one bounded 84-day private reconstruction. It never opens the learner's persistent database or rebuilds the full historical daily fact. Previously accepted forecasting and price-analysis suites are not rerun.

All **365,880 weekly inputs × 12 fields**, **36,588 pooled rows × 8 fields**, and **365,864 staged prices × 4 fields** match original-source references. All **243,920 classified targets × 20 fields** match the independent reference and reproduce SQL51's frozen classification fingerprint; their eighteen baseline fields also reproduce SQL50's accepted fingerprint. Independent weekly buckets then verify all **8×12 report values** and reconcile their class counts and directional gaps to accepted SQL51 evidence.

The run passed **2 focused cases** covering the new weekly reporting behavior, with specific executed checks listed in [machine evidence](../data/weekly_anomaly_triage_preflight.json). Existing classification boundary tests are preserved as prior evidence instead of being rerun as a new suite. The frozen input/history/classification prefix and rules are preserved. Seven scoped input snapshots, original source and dependency fingerprints, and **50 historical preflights** remained unchanged. Private exports, spills and databases were removed.

Report SHA256: `02196fd34a1bfbd79a340b8df2b4afd8e715d231ee53f72e7cfc2f220a838aa1`. Canonical output is ordered compact JSON row arrays with one LF after each row: string week/date/status, integer counts, fixed-four-place share strings and fixed-two-place gap strings. Only aggregate results and fingerprints are published, with no real candidate identifiers or row-level features.

## Measured assistant report — learner reproduction pending

| Week | Week start | Targets | Sudden zero | Large increase | Large decrease | NONE | Candidates | Candidate % | Upward gap units | Downward gap units | Status |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 11605 | 2016-02-27 | 30490 | 165 | 724 | 608 | 28993 | 1497 | 4.9098 | 10725.50 | 14877.50 | PASS |
| 11606 | 2016-03-05 | 30490 | 103 | 849 | 636 | 28902 | 1588 | 5.2083 | 17618.50 | 13706.25 | PASS |
| 11607 | 2016-03-12 | 30490 | 133 | 809 | 593 | 28955 | 1535 | 5.0344 | 14928.00 | 11244.50 | PASS |
| 11608 | 2016-03-19 | 30490 | 106 | 735 | 850 | 28799 | 1691 | 5.5461 | 12251.50 | 14096.25 | PASS |
| 11609 | 2016-03-26 | 30490 | 74 | 607 | 822 | 28987 | 1503 | 4.9295 | 11181.75 | 13968.75 | PASS |
| 11610 | 2016-04-02 | 30490 | 161 | 924 | 516 | 28889 | 1601 | 5.2509 | 15765.00 | 12267.25 | PASS |
| 11611 | 2016-04-09 | 30490 | 103 | 847 | 589 | 28951 | 1539 | 5.0476 | 13953.75 | 12329.75 | PASS |
| 11612 | 2016-04-16 | 30490 | 57 | 623 | 713 | 29097 | 1393 | 4.5687 | 9550.00 | 12319.50 | PASS |

The report is an assistant reproducibility reference; learner screenshot acceptance remains separate. Execute the full SQL52 and return eight rows and twelve fields including check_status; see the [Chinese guide](FIRST_STEP_ZH.md).

## Follow-up boundary

After this overview, proceed directly to deterministic representative-history review across the complete candidate classes. Do not choose examples solely from a peak week observed here, and do not expand into department/store summary grids without a specific investigation question. Selection rules and any new public evidence contract must be explicit before new case outcomes are examined.

Weekly concentration can describe when review workload or recorded unit departures are larger, but it does not identify promotions, inventory failures, genuine demand shocks or source errors. Overlapping histories, repeated pairs, seasonality and changing availability limit interpretation. No independent labels establish precision/recall or true-anomaly prevalence. This previously explored historical window is not a new prospective forecasting test. Candidate-history review, operational verification, the full Stage 6 and the overall project remain incomplete.
