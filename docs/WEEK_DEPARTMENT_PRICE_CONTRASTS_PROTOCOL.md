# Week and department price contrasts protocol

Fixed on 2026-11-02 before computing new jointly grouped outcomes. This exploratory comparison was chosen after SQL48 learner acceptance, with all seven department rows PASS. Preserve SQL44–48 and their frozen protocols/evidence. This step completes the planned descriptive price-association sequence before any separately specified anomaly work; no anomaly is calculated here.

## Question and unchanged scope

Within each merchandise department, compare UP and DOWN price transitions with UNCHANGED price transitions observed in the same current-endpoint calendar week. Weight the unchanged reference by the target direction's weekly transition counts, so each target direction is compared against its own calendar distribution. These references are broad contemporaneous groups, not the same products/stores or matched causal controls.

Use the same 365,880 accepted observations: 30,490 item/store pairs, twelve complete Saturday–Friday weeks 11601–11612, 2016-01-30–2016-04-22. Keep all 335,390 immediate transitions, with current endpoints 11602–11612, 2016-02-06–2016-04-22. Keep all zero sales, missing price endpoints and empty categories. Department pair controls remain FOODS_1 2,160; FOODS_2 3,980; FOODS_3 8,230; HOBBIES_1 4,160; HOBBIES_2 1,490; HOUSEHOLD_1 5,320; HOUSEHOLD_2 5,150.

Obtain previous week, exact DECIMAL(18,2) price and integer units over each complete twelve-week item/store sequence before excluding its first week. Never bridge missing prices, filter zeros before LAG, carry prices forward, borrow another pair's endpoint or use an outside week. Price direction is UP, DOWN or UNCHANGED from exact cents; an absent endpoint is MISSING_ENDPOINT. Signed unit_change is current units minus previous units. A missing-price endpoint must have zero units under the accepted input contract, but its priced opposite endpoint can have positive units. No individual growth percentage or elasticity is calculated.

## Exact support and weighting rules

For a department, target direction UP or DOWN, and current week, let nD and SD be the target transition count and summed signed unit change. Let nU and SU be the corresponding UNCHANGED count and signed sum. The week is comparable exactly when nD > 0 and nU > 0. This criterion uses support only, never outcome size, direction, significance or a minimum count threshold.

Across comparable weeks E, define N = sum(nD):

- direction_transitions is the sum of nD across all eleven weeks.
- comparable_transitions is N; unsupported_transitions is direction_transitions minus N. Retain unsupported target transitions in the report instead of silently dropping them.
- comparable_weeks counts weeks in E, including exact-zero gaps.
- weighted_direction_mean_change = sum(SD) / N over E.
- weighted_unchanged_mean_change = sum(nD × SU / nU) / N over E.
- mean_change_gap = sum((SD × nU − SU × nD) / nU) / N over E. This equals the target-count-weighted mean of same-week, same-department differences, calculated before rounding.
- positive_gap_weeks and negative_gap_weeks count comparable weeks whose exact integer cross-product SD × nU − SU × nD is respectively positive or negative. Exact ties equal comparable_weeks minus those two counts. Do not classify signs from displayed or floating-point means.

If N = 0, all three displayed means/gap are NULL, comparable_transitions/comparable_weeks/sign counts are zero, and unsupported_transitions equals direction_transitions. Empty target directions remain displayed.

Round each of the three final means/gap independently to six decimal places, half away from zero. Canonical rounded zero is 0.000000. Never average rounded cell means, subtract already rounded displayed means, or average medians. The displayed gap can differ by 0.000001 from subtracting the displayed means. A tiny nonzero exact week gap can count as positive/negative even when a displayed rounded value is zero. The independent reference accumulates fractions exactly and rounds with integer quotient/remainder arithmetic; final comparisons are exact, with no coarse tolerance.

## Frozen fourteen-row, twelve-column output

Return exactly fourteen rows, ordered by dept_id and then UP, DOWN, without a TOTAL row. Exact columns:

`dept_id, price_direction, direction_transitions, comparable_transitions, unsupported_transitions, comparable_weeks, weighted_direction_mean_change, weighted_unchanged_mean_change, mean_change_gap, positive_gap_weeks, negative_gap_weeks, check_status`.

Retain all four directions internally. The full internal grid has 7 departments × 11 current weeks × 4 directions = 308 cells, including empty cells. Its sixteen-field validation projection is `dept_id, retail_week, week_start, series_count` followed by the accepted SQL46 twelve-field schema. It retains cell counts, distinct pairs, endpoint sums, signed differences, means, medians and all three sales-direction percentages. Missing transitions remain in this grid and all full-population reconciliations even though the final contrasts concern only UP and DOWN relative to UNCHANGED.

PASS certifies accepted input integrity, immediate adjacency, department/week support and arithmetic reconciliations. It does not establish a price effect.

## Integrity and interpretation

SQL49 is self-contained, read-only and creates no table. Preserve accepted input/transition guards, exact source mappings and department roster controls, complete grid and calendar checks, staging-price agreement and pooled SQL23 reconciliation. Each department/week must contain exactly its series_count transitions across four directions; all 308 cells sum to 335,390. Anchor validation independently of output rows so invalid/empty inputs cannot silently return no rows.

This joint calendar-week/department comparison does not balance product/store identity, baseline demand, availability, promotion exposure or other conditions. The unchanged reference may contain different products and stores. Broad grouping can leave substantial composition differences. Repeated adjacent observations share endpoints and are not independent. Treat mean gaps and week-sign counts as descriptive patterns only, without causal, elasticity, significance, promotion-mechanism or anomaly claims. An absent unchanged group is unsupported comparison, not evidence of no association.

## Bounded independent preflight

Use original read-only sales/calendar/price CSVs and unchanged source-reference helpers. Reconstruct only the accepted 84-day sales projection and twelve-week prices through unchanged SQL09/23/44 in one containment-checked private database under ignored repository tmp. Never open the learner's persistent database, build the full historical daily fact or rerun historical forecasting/guard suites. Configure two DuckDB threads and a 2GB limit; this is not a total-process memory guarantee.

Compare all 365,880 weekly input rows across twelve fields and the accepted SQL44 fingerprint. Independently derive source department/week membership and every transition, then compare all 308 internal cells across sixteen fields and all fourteen displayed rows across twelve fields. Use exact Fraction accumulators for contrasts and exact integer cross-products for signs; retain the established Decimal helper for ordinary cell summaries. Verify the displayed final rounding exactly.

Re-evaluate unchanged SQL45–48 and compare every field with accepted evidence. Independently recompute full-window SQL46 statistics, SQL47 weekly margins and SQL48 department margins from the same source transitions, including exact sums, distinct pair sets and medians. Never reconstruct medians by averaging group medians. Focus synthetic checks on unequal target support, unsupported target weeks, absent target groups, exact ties and tiny nonzero signs, signed rounding boundaries, and retention of zero/missing endpoints; preserve intended invalid-input rejection without broad historical suites.

Verify original-source/dependency/historical-evidence hashes and all seven input snapshots before/after queries, then remove temporary exports, spills and databases. Pin this protocol before new outcomes. Publish only aggregate reports and fingerprints, without real item/store identifiers, row-level records, raw files, screenshots or databases. Assistant preflight and learner SQL49 execution remain separate states.
