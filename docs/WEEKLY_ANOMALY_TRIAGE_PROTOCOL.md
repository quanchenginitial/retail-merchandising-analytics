# Weekly retrospective candidate triage protocol

Fixed on 2026-11-02 before computing new weekly candidate outcomes. SQL51's five-row candidate report is learner accepted. This is one weekly overview before separately specified representative-history review; no additional department/store cuts or case selection are performed here. Preserve the frozen [screening rules](ANOMALY_SCREENING_PROTOCOL.md) and [candidate contract](ANOMALY_CANDIDATES_PROTOCOL.md), including thresholds, label priority, input scope and rounding.

## Unchanged population and classifications

Use all 365,880 accepted weekly observations for 30,490 item/store pairs in weeks 11601–11612, 2016-01-30–2016-04-22. Classify the same 243,920 targets in weeks 11605–11612, 2016-02-27–2016-04-22, using each pair's four immediately preceding actual weekly observations. Keep actual zeros, previous flagged actual values, and missing-price context. No current/future observation enters a baseline; price does not filter or influence a flag.

Mechanically preserve the SQL51 prefix through classified, including all input/history guards and the exact inclusive priority rules: SUDDEN_ZERO, then LARGE_INCREASE, then LARGE_DECREASE, otherwise NONE. The unchanged integer difference is unit_difference_x4 = 4 × current units − prior-four unit sum. A candidate is any of the three labels other than NONE. These are heuristic review candidates, not verified anomalies or operational events.

## Frozen eight-row, twelve-column report

Return exactly eight chronological current-week rows, without TOTAL, with columns:

`retail_week, week_start, target_rows, sudden_zero_rows, large_increase_rows, large_decrease_rows, none_rows, candidate_rows, candidate_share_pct, upward_gap_units, downward_gap_units, check_status`.

- retail_week covers 11605–11612; week_start is the current week's Saturday.
- target_rows includes all 30,490 item/store target positions in that week, including NONE, zero sales and missing-price observations.
- The four class counts partition target_rows. candidate_rows equals sudden_zero_rows + large_increase_rows + large_decrease_rows; none_rows equals target_rows minus candidate_rows.
- candidate_share_pct is 100 × candidate_rows / target_rows. Round once to four decimal places, half away from zero, with all targets including NONE in the denominator.
- upward_gap_units is SUM(unit_difference_x4) / 4 over LARGE_INCREASE only.
- downward_gap_units is −SUM(unit_difference_x4) / 4 over SUDDEN_ZERO and LARGE_DECREASE only.
- Both gap columns are nonnegative exact quarter-unit sums, displayed to two decimal places. They describe differences from each target's own historical baseline, not money, lost sales, unmet demand or price effects.
- A zero-candidate week remains displayed with zero candidate count, 0.0000 share and 0.00 upward/downward gaps. All eight weeks remain present.
- PASS certifies accepted classifications, weekly allocation, coverage and aggregate reconciliation, not detection accuracy or a causal interpretation.

The difference upward_gap_units minus downward_gap_units is the net signed difference of the **three candidate classes only**. NONE observations are excluded from both gap columns, so this is not the net difference of all target observations. Gap sums are descriptive differences, not forecast errors from a new evaluation.

## Integrity and interpretation

SQL52 is self-contained, read-only and creates no table. Use a fixed eight-week scaffold and a guard-anchored final output so invalid or empty inputs cannot silently suppress errors. Every week's four counts must sum to 30,490 and its candidate count to the three selected classes. Across eight weeks, class counts and gap sums must reconcile exactly to accepted SQL51: upward to LARGE_INCREASE signed difference, downward to the negated combined SUDDEN_ZERO/LARGE_DECREASE signed difference.

Weekly concentration can help organise a review, but it cannot identify causes. Calendar conditions, product/store mix, baseline volume, availability, promotions and recording issues can all remain relevant. Adjacent targets share history and are not independent. Counts are candidate positions, not unique events or distinct series; do not sum them as independent incidents. A high count/share or large unit gap does not establish material financial impact. Later representative histories should follow a separately fixed deterministic selection from the full candidate classes, without choosing only the busiest weeks.

## Bounded independent preflight

Use original read-only CSVs and the unchanged SQL44/50/51 reference helpers. Rebuild only the accepted 84-day sales projection and twelve-week prices through unchanged SQL09/23/44 in one containment-checked ignored tmp database. Use two DuckDB threads and a configured 2GB limit, which is not a total-process cap. Never open the learner's persistent database, reconstruct the full historical daily fact or rerun forecasting and historical boundary-test suites.

Compare all 365,880 weekly rows across twelve fields with original-source values and the accepted fingerprint. Independently derive and compare all 243,920 twenty-field classifications, reproducing accepted SQL51 fingerprint `901d908b825f192b0dd1a7baabfe9ad38cdf96add65f7fa891b7aa15dea85e31` and the embedded eighteen-field SQL50 fingerprint `556c07cf090b18fc6d60c00770b524d2d71464d3aece8968c438fea0c558c38f`. Reconstruct the complete accepted SQL51 five-row report from source classifications, then independently bucket every target by current week and compare every eight-row/twelve-field SQL52 value/order. Reconcile weekly class/gap totals to SQL51 and weekly target counts to SQL50. No rerun of the older price-analysis or forecasting queries is needed.

Focused new fixtures cover allocation to separate weeks, an all-NONE week, the all-target share denominator, exact upward/downward quarter-unit sums, retained unpriced zeros and an intended empty-calendar rejection. Reuse already verified classification/rounding helpers without rerunning SQL51's boundary suite. Preserve all frozen code/protocol/evidence hashes, original-source hashes and historical preflight files; compare all seven scoped input snapshots before/after and remove private exports, spills and databases.

Publish only aggregate results and fingerprints, without real item/store identifiers, candidate histories, raw files, screenshots or databases. Assistant preflight and learner SQL52 execution remain separate states. Representative-history review and the overall project remain unfinished.
