# Weekly price and sales association protocol

Fixed on 2026-11-02 before computing new weekly group outcomes. SQL46 learner execution is accepted with all five rows PASS. Preserve its original price-direction definitions, window, pair roster, zero-sales inclusion, missing-price rules and descriptive scope. SQL45/46 and their frozen protocols/evidence remain unchanged.

## Question and fixed scope

Check whether the already observed aggregate price/sales association is concentrated in particular calendar weeks. Display the UP, DOWN and UNCHANGED price groups side by side within each week, with their support counts and mean signed unit changes. Missing-price-endpoint counts remain visible. This is a calendar breakdown, not a matched comparison, causal adjustment, elasticity, regression, significance test, promotion identification or anomaly claim.

Use all accepted 365,880 item/store/week positions: 30,490 pairs and twelve complete Saturday–Friday weeks 11601–11612, 2016-01-30–2016-04-22. Retain all 335,390 adjacent transitions. Current endpoints cover eleven weeks 11602–11612, 2016-02-06–2016-04-22, with 30,490 transitions per week. The first input week supplies the initial previous endpoint. Do not change the window, remove zero sales, retune historical forecasts or select weeks based on outcomes.

## Unchanged transition definitions

Within each item/store pair, obtain previous week, exact DECIMAL(18,2) price and integer units over the complete twelve-week sequence before excluding the first week. Never bridge missing prices, filter zero units before LAG, carry values forward, borrow another store's observation or import an outside week.

Current price greater than previous is UP, lower is DOWN, equal is UNCHANGED; either price absent is MISSING_ENDPOINT. Every transition has signed unit_change = current units minus previous units. Include zero-to-positive, positive-to-zero and zero-to-zero observations. A missing-price endpoint has zero units under the accepted coverage contract; its other priced endpoint may have positive units. No individual percentage growth is calculated.

## Frozen eleven-row, twelve-column report

Return one row per current-endpoint retail week, ordered chronologically, with exactly these columns:

`retail_week, week_start, price_up_transitions, price_up_mean_unit_change, price_down_transitions, price_down_mean_unit_change, unchanged_transitions, unchanged_mean_unit_change, missing_endpoint_transitions, total_transitions, total_unit_difference, check_status`.

- retail_week is the current endpoint's week identifier, 11602–11612; week_start is that week's Saturday. The week ends six days later.
- Each direction count includes all transitions classified in that direction in that week. The three displayed means are arithmetic averages of signed unit_change over all transitions in their corresponding week/direction group. Means round to six decimal places, half away from zero; the independent Decimal reference uses ROUND_HALF_UP.
- An empty direction group displays count zero and mean NULL. Empty categories remain represented internally; missing-price transitions are never silently included in UNCHANGED.
- missing_endpoint_transitions displays the fourth category's support. Its outcomes remain included in total_unit_difference and in all reconciliation checks. SQL46 retains the accepted full-window missing-endpoint statistics.
- total_transitions equals all four direction counts combined and must equal 30,490 for every week. total_unit_difference sums signed unit_change across all four groups, including missing endpoints and zero sales. It is an exact integer.
- No TOTAL row is added: SQL46 supplies the accepted full-window report. Summing weekly transition counts and unit differences must reconcile to SQL46. Group full-window means require transition weighting; they are never unweighted averages of weekly means. Full-window medians are recomputed from all underlying differences, never from weekly medians.
- PASS certifies accepted inputs, immediate adjacency and report reconciliations, not a causal relationship.

## Internal integrity and interpretation

SQL47 is self-contained, read-only and creates no table. Preserve the SQL46 accepted-input and adjacent-transition checks mechanically. These cover exact schemas, complete pair/week/calendar coverage, integer nonnegative units, source metadata mappings, original control totals, exact scoped staging prices and pooled SQL23 reconciliation.

Use a fixed internal grid of eleven current weeks by UP, DOWN, UNCHANGED and MISSING_ENDPOINT: 44 cells even when groups are empty. Aggregate exact previous/current units and signed differences, counts, means, medians and unit-direction counts; validate all cell partitions and each weekly total before presenting the compact report. Within one week, a pair can occur in only one price direction. Across weeks a pair can change directions and adjacent comparisons share endpoints.

Same-week display makes calendar concentration visible but does not make groups comparable in product/store mix, baseline demand, availability or promotions. UNCHANGED remains a descriptive comparison, not a causal control. Repeated adjacent observations are not independent. Positive or negative group means do not identify a response to price; no significance, confidence interval or elasticity is estimated. Report observable weekly patterns without selecting or excluding inconvenient weeks.

## Bounded independent preflight and publication

Use original read-only sales/calendar/price CSVs and unchanged SQL44 csv/Decimal source helpers. Reconstruct only the 84-day sales projection, calendar/dimensions and twelve-week prices through unchanged SQL09/23/44 in one private, containment-checked, ignored repository tmp database. Never open the learner's persistent database or construct the full historical daily fact. Configure two DuckDB threads and a 2GB memory limit; this is not a total-process memory guarantee.

Independently derive all weekly integer units and exact prices from original source files, compare every one of the 365,880 weekly rows across twelve fields, and match the accepted SQL44 fingerprint. Independently derive every adjacent transition and all 44 weekly direction cells, including distinct pairs, endpoint sums, differences, means, medians and all three sales-direction percentages using the SQL46 six/four-place Decimal rounding rules. Compare every internal cell field and every displayed report field/order exactly. Re-evaluate all five full-window SQL46 rows from underlying transitions, including medians and distinct pairs, and reconcile unchanged SQL46 execution to its accepted evidence. Match every weekly price-direction count to accepted SQL45 and reconcile weekly sums to the accepted SQL46 totals.

Focused fixtures cover changing week-level means, unequal group support and weighted aggregation; signed/half-unit medians and zero endpoints; and all-zero/empty week-direction groups with missing-price gaps and store separation. Reuse the already verified rounding helper/production expressions rather than repeat historical guard suites. Record only cases actually executed. Verify original-source, dependency and historical-evidence hashes and scoped input snapshots before/after the read-only query, then remove all private exports, spills and databases. Pin this protocol before computing new outcomes. Publish aggregates and fingerprints only, without real identifiers, row-level records, raw files, screenshots or databases. Assistant preflight and learner execution remain separate states.
