# Retrospective screening candidate report protocol

Fixed on 2026-11-02 before computing candidate classifications or counts. SQL50's eight-row baseline scope report is learner accepted. The rules were already fixed in [ANOMALY_SCREENING_PROTOCOL.md](ANOMALY_SCREENING_PROTOCOL.md), SHA-256 `dd2376b370d2350d51d49e20b7ba29254b0fc49215e3c58e79d2d7b4ed4c7b2d`; preserve that document unchanged. This protocol fixes SQL51's report and validation contract without retuning any threshold.

## Unchanged population and rules

Retain all 365,880 accepted weekly observations for 30,490 item/store pairs in weeks 11601–11612, 2016-01-30–2016-04-22. The first four weeks supply warm-up history. Classify all **243,920 targets** in weeks 11605–11612, 2016-02-27–2016-04-22. Each baseline uses exactly four immediately preceding actual weekly unit values, including zeros and any previously flagged actual observations. Exclude current/future observations and never borrow another pair's history. Prices remain context only, without filtering or affecting classification.

Let y be current units, S the prior-four actual unit sum, μ = S / 4, and positive_history_weeks the number of positive prior values. Apply these exact integer rules in order, with inclusive boundaries:

1. **SUDDEN_ZERO:** y = 0, positive_history_weeks = 4, and S ≥ 28.
2. Otherwise **LARGE_INCREASE:** 4y ≥ 2S and 4y − S ≥ 28.
3. Otherwise **LARGE_DECREASE:** 8y ≤ S and S − 4y ≥ 28.
4. Otherwise **NONE**.

SUDDEN_ZERO takes priority over the overlapping decrease condition. With S = 0, y = 6 is NONE and y = 7 qualifies as LARGE_INCREASE: activity after zero history, not percentage growth from zero. A zero current value with some prior zero values can qualify as LARGE_DECREASE when its independent conditions hold. The seven-unit weekly absolute floor and ratio conditions remain investigation heuristics, not validated operating standards or optimised thresholds.

Define signed `unit_difference_x4 = 4y − S` as an exact integer. The ordinary signed difference is y − μ = unit_difference_x4 / 4. Keep quarter units exactly; never round a baseline before classification. All targets receive exactly one label.

## Fixed five-row, twelve-column report

Return exactly five rows ordered SUDDEN_ZERO, LARGE_INCREASE, LARGE_DECREASE, NONE, TOTAL, with columns:

`candidate_class, target_rows, target_share_pct, distinct_series, baseline_units, observed_units, unit_difference, mean_unit_difference, zero_observed_rows, zero_baseline_rows, missing_price_rows, check_status`.

- target_rows counts all targets assigned to the class. The four class counts must sum to TOTAL = 243,920.
- target_share_pct is 100 × class target_rows / all target_rows, including NONE in the denominator. Round independently to four decimal places, half away from zero; TOTAL is 100.0000. Rounded class shares may sum to 100 ± 0.0002, so enforce the exact count partition instead of exact equality of rounded shares.
- distinct_series counts unique item/store pairs represented in that row. TOTAL is independently counted over all targets and must be 30,490. A pair may enter several classes across weeks, so class pair counts are not additive.
- baseline_units sums μ over the class; observed_units sums integer current units. unit_difference sums signed y − μ, equivalently SUM(unit_difference_x4) / 4, and equals observed_units minus baseline_units. Baseline and signed difference are exact quarter units formatted to two decimal places.
- mean_unit_difference is SUM(unit_difference_x4) / (4 × target_rows), rounded once to six decimal places, half away from zero. TOTAL is computed from all targets, not an unweighted average of class means. Canonical rounded zero is positive zero.
- zero_observed_rows counts y = 0; zero_baseline_rows counts S = 0; missing_price_rows counts absent current prices. Retain these positions in every class calculation.
- Empty classes remain visible with zero counts, shares and unit sums, but NULL mean_unit_difference. An empty overall population is invalid input, not a successful empty report.
- PASS certifies accepted inputs, prior-only history, exact rule application and aggregate partitions. It does not verify real anomalies or operational causes.

## Exact private classification contract

The private projection contains all eighteen frozen SQL50 fields in their original order, followed by `unit_difference_x4` and `candidate_class`: twenty fields per target. No private feature is selected from public aggregate outcomes. Compare all 243,920 rows and all twenty fields to independently derived original-source values; also reproduce the accepted eighteen-field SQL50 fingerprint exactly.

SQL51 is self-contained and read-only, with the accepted SQL50 input, history and target-coverage guard prefix mechanically preserved. Use a fixed five-row report scaffold and guard-anchored final output so an invalid empty input cannot suppress errors. Reconcile four class counts, sums and coverage fields to TOTAL; verify rule priority, all target keys and exactly one class per target. Prior classified values stay as actual baseline history; no iterative exclusion or forecast substitution occurs.

## Interpretation and publication

These are retrospective review candidates under fixed heuristic rules, not verified events. The class means mechanically reflect the selection rules; positive LARGE_INCREASE or negative LARGE_DECREASE means are not evidence of a causal effect or detection quality. Differences are from a prior-four-week descriptive baseline, not forecast errors from a new evaluation. Price context does not establish pricing causality. Zero observed units do not prove stockouts or lost demand.

Product units, baseline sales, seasonality, promotions, availability and reporting differ, and repeated target/history windows overlap. No precision, recall, statistical significance, true-anomaly rate, stockout count, savings or financial benefit can be established without independent labels and operational investigation. The full anomaly module and project remain incomplete until subsequent review and acceptance; the accepted forecasts and price-association findings remain unchanged.

## Bounded independent preflight

Use original read-only sales/calendar/price CSVs and unchanged SQL44/50 source helpers. Build only the fixed 84-day sales projection and twelve-week prices through unchanged SQL09/23/44 in one containment-checked private ignored tmp database, with two DuckDB threads and a configured 2GB limit. The configured limit is not a total-process memory guarantee. Never open the learner's persistent database, rebuild the full historical daily fact or rerun forecasting/historical guard suites.

Compare all 365,880 weekly input rows across twelve fields and their accepted fingerprint. Independently derive the four-prior-actual features from original-source slices, match all 243,920 eighteen-field rows and SQL50's feature fingerprint, then independently classify and compare all 243,920 twenty-field rows. Use exact Fraction comparisons against μ for the reference rules, independently checking SQL's integer inequalities. Compute exact quarter sums and Fraction-based final rounding; compare all five report rows and every field exactly. Execute unchanged SQL50 once and reconcile its entire eight-row/twelve-field report to accepted evidence.

Focused synthetic cases isolate inclusive ratio and absolute boundaries, S = 27 versus 28, SUDDEN_ZERO priority, prior-zero decreases, zero baseline y = 6 versus 7, quarter baselines, retained unpriced zero targets, empty categories, nonadditive series counts, and signed mean/share rounding. Keep an intended invalid-empty rejection. Record only executed checks and do not expand into old historical suites.

Preserve all accepted dependencies and historical preflight files, verify original-source hashes and seven scoped input snapshots before/after the read-only work, and remove private exports, spills and databases. Publish aggregate reports and fingerprints only, without real item/store identifiers, candidate IDs, row-level features, raw files or screenshots. Assistant preflight and learner SQL51 execution remain separate states.
