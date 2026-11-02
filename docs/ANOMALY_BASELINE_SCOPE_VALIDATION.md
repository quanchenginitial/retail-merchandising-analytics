# Anomaly-screening baseline scope audit

## Purpose and state

The descriptive price-association milestone through SQL49 is learner-accepted on **2 November 2026**, with all 168 final report values and fourteen PASS statuses matching. Its [findings](STAGE06_PRICE_ASSOCIATION_FINDINGS.md) identify descriptive patterns and data gaps without claiming price effects. The next task prepares a retrospective anomaly-candidate screen.

[SQL50](../sql/50_audit_anomaly_baseline_scope.sql) audits coverage and past-only weekly baselines. **Assistant preflight passed; the learner screenshot was accepted on 2 November 2026 with all 96 displayed values and eight complete PASS statuses matching the frozen report.** No anomaly scores, labels, candidate counts or detection accuracy are produced. Future SQL51 rules are fixed in the [screening protocol](ANOMALY_SCREENING_PROTOCOL.md) but are not implemented by this query.

## Fixed time and observation contract

Reuse all 365,880 accepted item/store/week positions from twelve complete weeks **30 January–22 April 2016**. The first four weeks, 11601–11604, provide initial history. The eight target weeks, **11605–11612 / 27 February–22 April 2016**, contain **30,490 pairs × 8 = 243,920 target positions**. All zeros and missing-price positions remain eligible for coverage; price is context rather than a filter.

For each target and the same item/store, take exactly the four immediately preceding actual weeks. The target's own units and later units do not enter its baseline. Define S as the integer sum of those four observations and baseline_units = S × 0.25, with exact quarter-unit arithmetic and two displayed decimals. Retain the number of positive history weeks and first/last history week as validation features. Previously unusual or later flagged observations are not removed from subsequent rolling windows.

The private feature projection retains the accepted twelve weekly fields followed by history_rows, history_units, positive_history_weeks, first_history_week, last_history_week and baseline_units: **18 fields per target**. Every target must have history_rows=4, first_history_week=current_week−4 and last_history_week=current_week−1. The self-contained read-only query inherits the accepted weekly-input integrity checks and rejects invalid/empty scope rather than silently showing success.

## Eight-row report

Return eight chronological rows, twelve columns and no TOTAL row. Each row has series_count=scored_rows=30,490. Here scored_rows means screening-target positions; no anomaly scoring has occurred. history_rows=121,960 counts four referenced weeks for each pair. These historical observations are reused across target windows, so their counts are not new transactions.

baseline_units is the sum of individual four-week averages, equivalently the sum of history_units divided by four. It has a one-week units scale, as does observed_units. Neither an aggregate match nor a zero-sales count establishes normality or a stockout. zero_baseline_rows means all four preceding observed unit counts sum to zero. priced_target_rows and missing_price_target_rows partition the complete target population.

## Future screen and limitations

The protocol fixes inclusive, mutually exclusive candidate rules in priority order. With current units y and S equal to the preceding-four-week sum: SUDDEN_ZERO requires y=0, all four history weeks positive and S≥28. Otherwise LARGE_INCREASE requires 4y≥2S and 4y−S≥28; otherwise LARGE_DECREASE requires 8y≤S and S−4y≥28; otherwise NONE. The seven-unit weekly floor is an explicit one-unit-per-day heuristic, not an optimal or industry-validated threshold. A zero baseline can produce LARGE_INCREASE at y≥7, described as activity after four zero weeks, never percentage growth.

This is a retrospective, unlabelled screening exercise on a previously explored historical window. The past-only baseline prevents within-query look-ahead but does not turn the analysis into a new prospective test. It does not replace or retune the accepted forecasting milestone. Seasonal events, trends, changing availability and the small history window can all produce candidates without a data error. Candidate review, source investigation, human labels and evaluation remain future work; no true-anomaly, stockout, causal or accuracy claim is made.

## Independent preflight

The [validator](../validation/preflight_anomaly_baseline_scope.py) uses original read-only sales/calendar/price files in a private bounded 84-day reconstruction. It never opens the learner's persistent database or reruns the historical forecast pipeline. Original-source sliding four-week slices independently construct every target's history and baseline; source weekly rows and the accepted input fingerprint are also checked.

The run passed **2 focused cases**, matched **365,880 weekly rows × 12 fields**, **36,588 pooled rows × 8 fields**, **365,864 staged prices × 4 fields**, all **243,920 target rows × 18 fields**, and the **8×12 report**. Seven input snapshots, source/dependency fingerprints and **48 historical preflights** remained unchanged; private files were removed. See [machine evidence](../data/anomaly_baseline_scope_preflight.json) for executed cases, feature fingerprints and timings.

Report SHA256: `15020474ebc9f0555091e86fa78d3c743fcfa4ec4b9258528727b03c097edb20`. Canonical output uses fixed-field-order compact JSON row arrays followed by LF, integer counts/sums, week/date/status strings and fixed-two-place baseline strings. Only aggregates and fingerprints are published, with no item/store feature rows, raw sources, screenshots or databases.

## Measured assistant report

| Week | Week start | Series | Target rows | History observations | Baseline units | Observed units | Zero observed rows | Zero baseline rows | Priced targets | Missing-price targets | Status |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 11605 | 2016-02-27 | 30490 | 30490 | 121960 | 294200.25 | 291839 | 6040 | 2451 | 30490 | 0 | PASS |
| 11606 | 2016-03-05 | 30490 | 30490 | 121960 | 294276.50 | 304015 | 5942 | 2491 | 30490 | 0 | PASS |
| 11607 | 2016-03-12 | 30490 | 30490 | 121960 | 293928.00 | 297551 | 5737 | 2330 | 30490 | 0 | PASS |
| 11608 | 2016-03-19 | 30490 | 30490 | 121960 | 293496.00 | 281241 | 5772 | 2273 | 30490 | 0 | PASS |
| 11609 | 2016-03-26 | 30490 | 30490 | 121960 | 293661.50 | 282697 | 5529 | 2178 | 30490 | 0 | PASS |
| 11610 | 2016-04-02 | 30490 | 30490 | 121960 | 291376.00 | 309668 | 5116 | 2046 | 30490 | 0 | PASS |
| 11611 | 2016-04-09 | 30490 | 30490 | 121960 | 292789.25 | 306203 | 5102 | 1933 | 30490 | 0 | PASS |
| 11612 | 2016-04-16 | 30490 | 30490 | 121960 | 294952.25 | 286524 | 4998 | 1819 | 30490 | 0 | PASS |

Every report value matched the independent reference during preflight. The learner screenshot subsequently matched all fields on **2 November 2026**.

## Learner screenshot acceptance — 2 November 2026

All **8 rows × 12 fields = 96 values** and eight complete PASS statuses are visible and match the frozen report: 64 integer values, eight baseline values, sixteen week/date values and eight statuses. Only displayed thousands separators and omitted baseline trailing zeros were normalized; baseline_units retains two decimal places. The ordered row-array/LF hash is unchanged: `15020474ebc9f0555091e86fa78d3c743fcfa4ec4b9258528727b03c097edb20`. See the [aggregate learner acceptance](../data/anomaly_baseline_scope_learner_acceptance.json).

Each displayed week has 30,490 target positions and 121,960 referenced history observations. Across eight weeks, this is **243,920 item/store/week targets** and **975,680 history references**; neither count represents anomaly flags or independent transactions. All target positions have a recorded price in these eight report weeks. The displayed current units sum to 2,359,738; zero-current and zero-baseline counts sum to 44,236 and 17,521 target positions respectively. These counts do not establish abnormality, lost sales or stockouts.

This acceptance compares the visible aggregate report; it is not a direct audit of the learner database or a new row-level check of all prior-week features. The historical preflight above independently established the exact four-prior-actual-week histories and baselines. No learner database was opened and no SQL, preflight, fixture or historical analysis was rerun for screenshot acceptance. The original preflight JSON retains its historical pending status; the new record establishes subsequent learner acceptance. SQL50, its validator, the screening protocol and preflight remain unchanged. No screenshot, individual targets or raw sources are published.

SQL50 has not produced anomaly scores, flags or candidate counts. SQL51 candidate classification and investigation remain subsequent work; the full Stage 6 and overall portfolio are incomplete. See the [current Chinese guide](FIRST_STEP_ZH.md).
