# Department price and sales association protocol

Fixed on 2026-11-02 before computing new department-level sales-change outcomes. This exploratory breakdown was chosen after SQL47 learner acceptance, with all eleven weekly rows PASS. Preserve the accepted SQL44–47 window, pair roster, transition definitions, rounding and missing/zero rules; their frozen SQL, protocols and evidence remain unchanged.

## Question and scope

Describe how the aggregate price/sales association is distributed across the seven merchandise departments. Display each department's UP, DOWN and UNCHANGED price support and mean signed unit changes, with missing-price support and overall counts/difference. This is a broad product-composition breakdown, not a causal effect, elasticity, significance test, regression, promotion explanation or anomaly label.

Use all 365,880 accepted item/store/week positions: 30,490 pairs and twelve complete Saturday–Friday weeks 11601–11612, 2016-01-30–2016-04-22. Preserve all 335,390 immediate transitions with current endpoints in weeks 11602–11612, 2016-02-06–2016-04-22. The first input week supplies the previous endpoint. Retain all zero sales and missing endpoints. Do not change the window, filter groups based on outcomes or revisit the forecasting period.

The established department pair roster, ordered by dept_id, is FOODS_1 2,160; FOODS_2 3,980; FOODS_3 8,230; HOBBIES_1 4,160; HOBBIES_2 1,490; HOUSEHOLD_1 5,320; HOUSEHOLD_2 5,150. These source-metadata controls sum to 30,490 pairs. Every pair contributes eleven transitions.

## Unchanged transition and arithmetic definitions

Within each item/store pair, obtain previous week, exact DECIMAL(18,2) price and integer units over the complete twelve-week sequence before excluding the first week. Never filter zero/missing observations before LAG, bridge a missing endpoint, carry a price forward, borrow another store or use an outside week.

Current price greater than previous is UP, lower is DOWN, equal is UNCHANGED; either price absent is MISSING_ENDPOINT. Define signed unit_change = current units minus previous units for every transition. Include zero-to-positive, positive-to-zero and zero-to-zero observations. A missing-price endpoint has zero units under the accepted contract, while the other priced endpoint may have positive units. No individual sales-growth percentage is calculated.

## Frozen seven-row, twelve-column report

Return exactly seven rows ordered by dept_id, with no TOTAL row and exactly these columns:

`dept_id, series_count, price_up_transitions, price_up_mean_unit_change, price_down_transitions, price_down_mean_unit_change, unchanged_transitions, unchanged_mean_unit_change, missing_endpoint_transitions, total_transitions, total_unit_difference, check_status`.

- series_count counts distinct item/store pairs assigned to that department over the full accepted roster. It is not the sum of direction-specific pair counts; one pair may enter multiple directions across weeks.
- Each direction count includes every transition in the corresponding department/direction group across all eleven current weeks. The displayed means are averages of signed unit_change over all those transitions, including zero changes. Round means to six decimal places, half away from zero; the independent Decimal reference uses ROUND_HALF_UP.
- Empty groups retain count zero and mean NULL. MISSING_ENDPOINT remains a separate category and is never folded into UNCHANGED.
- total_transitions equals all four category counts and must equal eleven times the department's series_count. total_unit_difference sums signed changes across all four groups, including missing endpoints and zero sales, as an exact integer.
- Department counts and unit differences sum to accepted SQL46 totals. Recompute full-window group means from exact summed differences and counts; never average department means without transition weights. Recompute medians and distinct pair sets from underlying observations, never average group medians or sum overlapping pair counts.
- PASS certifies input integrity, immediate adjacency, department membership and report reconciliation. It does not establish a price effect.

## Internal checks and interpretation

SQL48 is self-contained, read-only and creates no table. Mechanically preserve accepted SQL46/47 input and transition guards: exact schemas, full pair/week coverage, calendar boundaries, nonnegative integer units, original control totals, source metadata and department/category/store/state mappings, exact staging-price reconciliation and pooled SQL23 agreement. Validate the fixed seven-department pair roster.

Maintain an internal grid of seven departments by four price directions: 28 cells including empty categories. Retain count, distinct pair support, previous/current unit sums, signed difference, mean, median and unit-direction counts/percentages. Check cell partitions, pair support and department transition totals before projecting the compact report. Anchor checks independently of output rows so an empty calendar/input cannot silently suppress the intended error.

Each department aggregates all eleven transition weeks. This is not a joint week-by-department adjustment. Department groups can still differ in products, stores, baseline demand, calendar exposure, promotions and availability. Within-department UP/DOWN/UNCHANGED comparisons remain descriptive, and UNCHANGED is not a causal control. Adjacent observations share endpoints and are not independent. The breakdown reveals broad composition; it does not remove timing or product/store confounding, identify elasticity or justify significance claims.

## Bounded independent preflight and publication

Use original read-only sales/calendar/price CSVs and unchanged SQL44 csv/Decimal helpers. Reconstruct only the 84-day sales projection, calendar/dimensions and twelve-week prices through unchanged SQL09/23/44 in one containment-checked private database under ignored repository tmp. Never open the learner's persistent database, construct the full historical daily fact or rerun historical guard/forecasting suites. Configure two DuckDB threads and a 2GB limit; the latter is not a total-process memory guarantee.

Compare every one of the 365,880 weekly input rows across twelve fields to original-source values and the accepted SQL44 fingerprint. Independently derive source department membership, pair sets and every adjacent unit/price transition. Compare all 28 internal department cells across fourteen fields and all seven displayed rows across twelve fields, including order. Use exact integers, independently sorted integer medians and fixed-six/four-place Decimal strings for mean/median/percentages. Reuse the already tested rounding helpers and mechanically identical production aggregation expressions.

Re-evaluate unchanged SQL45, SQL46 and SQL47 on the same private input and compare every field to their accepted evidence. Independently reconcile all full-window SQL46 statistics, including medians and pair support, and all weekly SQL47 rows; reconstruct global means from exact department sums/counts. Focus new fixtures on department membership, distinct-pair nonadditivity, empty department-direction groups and unequal group support requiring weighted aggregation, plus targeted rejection of wrong department mapping and empty calendar. Do not repeat broad historical suites.

Verify source/dependency/historical-evidence hashes and all seven scoped input snapshots before/after execution, then remove private exports, spills and databases. Pin this protocol before new department outcomes; record SQL/validator hashes and only actually executed checks. Publish aggregates and fingerprints only, without real identifiers, row-level records, raw files, screenshots or databases. Assistant preflight and learner SQL48 execution remain separate states.
