# Fixed-rule anomaly candidate classification

## Purpose and state

The learner accepted [SQL50's baseline scope](ANOMALY_BASELINE_SCOPE_VALIDATION.md) on **2 November 2026**: all 96 visible values and eight PASS statuses match frozen evidence. [SQL51](../sql/51_screen_anomaly_candidates.sql) now applies the already-fixed rules to identify retrospective review candidates. **Assistant preflight has passed; learner SQL51 execution and acceptance remain pending.** Candidate investigation and detection-performance evaluation are not complete.

The original [screening protocol](ANOMALY_SCREENING_PROTOCOL.md) was published before this classification work and remains unchanged. The separate [candidate report protocol](ANOMALY_CANDIDATES_PROTOCOL.md) fixes output, rounding and validation. Neither thresholds nor scope were selected from the resulting candidate counts.

## Observation and classification contract

Use the accepted twelve-week input, 30 January–22 April 2016, containing 365,880 item/store/week observations. The first four weeks supply initial history. Classify all **243,920 target positions** across 30,490 pairs in eight weeks, **27 February–22 April 2016**. For every target, use exactly its own pair's four immediately preceding actual weeks. Retain zero history, missing-price observations and actual prior values even if those values also qualify as candidates. Current/future values, other pairs and forecast substitutions do not enter the baseline.

Let y denote current units, S the integer sum of the prior four weeks, and μ=S/4. Apply these inclusive rules in priority order:

1. SUDDEN_ZERO: y=0, all four prior weeks are positive, and S≥28.
2. Otherwise LARGE_INCREASE: 4y≥2S and 4y−S≥28.
3. Otherwise LARGE_DECREASE: 8y≤S and S−4y≥28.
4. Otherwise NONE.

Each target receives exactly one class. SUDDEN_ZERO takes precedence over the overlapping decrease rule. Relative and absolute conditions must both hold. With S=0, current y=6 is NONE and y=7 is LARGE_INCREASE; this is activity after zero history, not a percentage increase from zero. Current zero with some prior zero weeks may satisfy LARGE_DECREASE without satisfying SUDDEN_ZERO. The seven-unit weekly floor is an explicit heuristic, not an industry standard or an optimised operating threshold.

Keep signed `unit_difference_x4=4y−S` as an exact integer. Divide by four only for ordinary-unit differences; all baseline and difference sums remain exact quarter units. A classification never uses a rounded baseline or a price filter.

## Five-row report and interpretation

Rows are ordered SUDDEN_ZERO, LARGE_INCREASE, LARGE_DECREASE, NONE and TOTAL. target_rows counts item/store/week positions, not independent events or unique products. Its share denominator is **all 243,920 targets, including NONE**. Four class counts partition TOTAL exactly. Percentages are rounded independently to four decimals, so displayed class shares may sum to 100 ± 0.0002 percentage points; TOTAL is independently 100.0000.

distinct_series is the number of different item/store pairs in that row. A pair can enter multiple classes across different weeks, so these counts are not additive; TOTAL is independently 30,490. baseline_units sums the four-week means, observed_units sums current sales, and unit_difference is observed_units minus baseline_units. These are unit counts or unit differences, not dollars, lost sales or estimated business benefits. mean_unit_difference is the signed total difference divided by this row's target_rows, rounded once to six decimals, half away from zero. TOTAL is computed over all targets, not by averaging class means. Empty categories remain visible with zero counts/sums/shares and NULL means.

zero_observed_rows, zero_baseline_rows and missing_price_rows are retained coverage descriptors. NONE means the fixed rules did not trigger, not verified normality. PASS checks data and computational consistency, not whether an operational anomaly occurred. The sign of a selected candidate group's mean is partly imposed by its rule and is not independent evidence of detection quality.

## Independent validation actually executed

The [validator](../validation/preflight_anomaly_candidates.py) reconstructs only the fixed 84-day window from original read-only sales/calendar/price files in an ignored private database. It does not open the learner's persistent database, rebuild the complete daily fact, rerun forecasting, or alter accepted historical evidence. The unchanged SQL09/23/44 setup creates the bounded inputs.

Original-source weekly slices independently derive all four-week histories. A Fraction-based reference classifies against μ and checks SQL's integer inequalities, priority and exact signed differences. All **365,880 weekly rows × 12 fields**, **36,588 pooled product/week rows × 8 fields**, and **365,864 scoped price rows × 4 fields** match the reference. All **243,920 baseline feature rows × 18 fields** reproduce SQL50's accepted feature fingerprint; all **243,920 classified rows × 20 fields** match the independent source reference exactly. The two added fields are unit_difference_x4 and candidate_class. The unchanged SQL50 eight-row/twelve-field report is also reproduced and reconciled.

The run passed **4 focused cases**. The [machine evidence](../data/anomaly_candidates_preflight.json) records the executed boundary, priority, zero-history, missing-price, empty-group and rounding checks, plus the intended invalid-empty rejection. All five report rows and twelve fields match the independently aggregated reference. Seven input snapshots, source/dependency fingerprints and **49 historical preflights** remained unchanged; private exports and databases were removed after validation.

Only aggregate results and fingerprints are published. The private twenty-field classification and its real item/store identifiers are not included in the repository. Report SHA256: `530ad26f7eb84ce5521bbdc522a712a22fbce3f1cb37042d4cb97233f164c550`. Canonical rows are compact JSON arrays in fixed column order followed by LF: integers for counts and observed units, fixed two-place strings for baseline/difference, four-place shares, six-place means (or null), and string labels/statuses. Canonical rounded zero is positive zero.

## Measured assistant report — learner reproduction pending

| Class | Target rows | Share % | Distinct pairs | Baseline units | Observed units | Signed difference | Mean signed difference | Zero observed | Zero baseline | Missing price | Status |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| SUDDEN_ZERO | 902 | 0.3698 | 898 | 18576.50 | 0 | -18576.50 | -20.594789 | 902 | 0 | 0 | PASS |
| LARGE_INCREASE | 6118 | 2.5082 | 4636 | 50705.00 | 156679 | 105974.00 | 17.321674 | 0 | 421 | 0 | PASS |
| LARGE_DECREASE | 5327 | 2.1839 | 3983 | 124220.25 | 37987 | -86233.25 | -16.187958 | 623 | 0 | 0 | PASS |
| NONE | 231573 | 94.9381 | 30488 | 2155178.00 | 2165072 | 9894.00 | 0.042725 | 42711 | 17100 | 0 | PASS |
| TOTAL | 243920 | 100.0000 | 30490 | 2348679.75 | 2359738 | 11058.25 | 0.045336 | 44236 | 17521 | 0 | PASS |

This is a reproducibility reference, not an accepted learner result or a claim of true-anomaly prevalence. The group totals reconcile to the SQL50 target population and sales/baseline totals.

## Next review and limits

Run the full SQL51 in the learner's retail_merchandising connection and submit its five-row/twelve-column result, including check_status; see the [Chinese guide](FIRST_STEP_ZH.md). After acceptance, inspect representative candidates' histories and available calendar/price context before choosing further operational evidence to request.

The historical window has already been explored; past-only baseline construction prevents within-query look-ahead but does not create a new prospective test. Four-week averages need not represent normal demand. Seasonality, trends, changing availability, promotions and reporting can all produce flagged changes. Zero sales alone do not prove stockouts. No independent human labels, inventory or availability evidence establish precision, recall, true-anomaly counts, causal effects or financial benefits. The accepted forecasting and price-association milestones remain unchanged; candidate investigation, the full Stage 6 and the overall portfolio remain incomplete.
