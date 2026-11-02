# Adjacent-week price and sales association protocol

Fixed on 2026-11-02 before computing new sales-change outcomes. SQL45 learner execution is accepted with all twelve rows PASS. Its accepted support counts, source window, pair roster and missing-price rules are retained. SQL45 and its frozen protocol/evidence remain unchanged.

## Question and scope

Describe how adjacent weekly unit changes differ among price-up, price-down and unchanged-price transitions. Retain missing-price-endpoint transitions separately and show TOTAL. This is an initial descriptive association, without a causal effect, elasticity, regression, significance test, promotion identification or anomaly claim.

Use all 365,880 accepted SQL44 item/store/week positions: 30,490 pairs, twelve complete Saturday–Friday weeks 11601–11612, 2016-01-30–2016-04-22, 2,561,160 daily cells and 3,536,539 units. The 335,390 transitions have current endpoints in weeks 11602–11612, 2016-02-06–2016-04-22. No window, group, exclusion or statistic is selected after viewing outcomes. Historical forecasting periods are not revisited.

## Fixed transition rule

Within each item/store pair, order the entire twelve-week sequence and obtain the immediately preceding week, exact DECIMAL(18,2) price and integer units before excluding the first week. Never filter zero sales or missing prices before obtaining previous values, bridge a missing endpoint, carry prices forward, borrow another store's observation or use an outside week.

Classify exact current price greater than previous as UP, lower as DOWN, equal as UNCHANGED. If either price is absent, classify MISSING_ENDPOINT. Define signed unit_change = current units minus previous units for every transition, including missing-price transitions. All zero-to-positive, positive-to-zero and zero-to-zero observations participate. No individual percentage growth is calculated, so previous zero units require no exclusion or division.

## Fixed report contract

Return exactly five rows, ordered UP, DOWN, UNCHANGED, MISSING_ENDPOINT, TOTAL, and exactly twelve columns:

`price_direction, transitions, distinct_pairs, previous_units, current_units, unit_difference, mean_unit_change, median_unit_change, sales_up_pct, sales_down_pct, sales_unchanged_pct, check_status`.

- transitions counts all observations in the group; distinct_pairs counts unique item/store pairs represented in it. TOTAL distinct_pairs is calculated over all transitions and is not the sum of group distinct counts.
- previous_units and current_units sum the respective endpoints; unit_difference sums their signed differences and equals current_units minus previous_units. Endpoint sums cover eleven endpoints each and are not the original twelve-week unit total.
- mean_unit_change is the arithmetic average signed difference per transition. median_unit_change is the usual sorted middle value, averaging the middle two values for an even count. Both round to six decimal places, half away from zero; the independent Decimal reference uses ROUND_HALF_UP.
- sales_up_pct, sales_down_pct and sales_unchanged_pct are 100 times the counts of positive, negative and zero unit changes divided by all transitions in that row. Round each independently to four decimal places. Rounding may make their displayed sum differ from 100 by at most 0.0001 percentage points.
- Display empty categories with zero counts and unit sums, and NULL mean, median and percentages. TOTAL statistics are recomputed from all transitions, not averages of category means/medians/percentages.
- PASS certifies accepted-input integrity, adjacent sequence and report partition/reconciliation; it does not establish a price effect.

## Integrity and interpretation

SQL46 is self-contained and read-only. Mechanically reuse the accepted SQL45 input-integrity prefix: exact schemas, full pair/week grid, calendar, source metadata mappings, nonnegative integer units, accepted control totals, exact scoped staging-price reconciliation, and all-field pooled SQL23 reconciliation. Add previous-unit and difference checks to the adjacent-sequence guard. Count every category including empty groups; reconcile group transition counts and unit sums to TOTAL, and ensure each sales-direction partition equals its group count. The independent preflight also reruns unchanged SQL45 on the identical private input and compares all twelve rows/fields to its published accepted evidence before validating SQL46.

The unchanged-price group is a descriptive comparison, not a causal control. Groups can have unequal item/store mix, baseline sales, calendar exposure and sizes. A pair can enter several categories. Adjacent transitions overlap in endpoints and repeated observations are not independent. Timing, seasonality, promotions, availability and other unmeasured factors can affect both prices and sales. Neither direction, mean differences nor percentages identify a response to price or an elasticity. No inferential uncertainty or claim of statistical significance is produced.

## Bounded independent preflight

Use original read-only CSVs and the unchanged SQL44 csv/Decimal source-reference helpers. Build only the 84-day sales projection, calendar/dimensions and twelve-week prices through unchanged SQL09/23/44 in one containment-checked, ignored repository tmp database. Never open the learner's persistent database, materialize the full historical daily fact or rerun forecasting. Use two DuckDB threads and a configured 2GB limit; this is not a total-process memory cap.

Compare every one of the 365,880 weekly input rows across twelve fields to independently derived original-source values and its accepted SQL44 fingerprint. Independently iterate every immediate transition from source weekly units and Decimal prices; compare all five report rows and every field. Counts and unit sums compare as exact integers. Means/medians compare to independently rounded fixed-six-place Decimal strings and percentages to fixed-four-place strings; SQL casts rounded values to corresponding decimals, so the final comparison is exact with no coarse tolerance.

Focused synthetic cases cover zero-to-positive, positive-to-zero, both-zero, signed mean/median and percentage rounding, missing first/internal endpoints without bridging, distinct-pair nonadditivity, store separation and empty groups. Do not repeat the historical construction guard suites. Verify relevant source, dependency and historical-evidence hashes, read-only input snapshots, and temporary cleanup. Freeze this protocol hash before new outcomes; pin SQL and validator hashes in evidence. Publish aggregates and fingerprints only, with no real identifiers, row-level exports, raw CSVs, screenshots or databases. Assistant preflight and learner execution are separate states.
