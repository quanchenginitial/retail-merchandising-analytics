# Adjacent-week price variation protocol

Fixed on 2026-10-30 before computing new variation counts. SQL44 learner execution is accepted; its original twelve-week window, all-pair roster, price precision and missing-value rules remain unchanged.

## Question and boundaries

Determine how many adjacent weekly observations have usable prices and how much actual within-pair price variation is present before choosing a later association method. A pair means the same product at the same store. This is a price-data support audit: no sales-change association, elasticity, causal effect, promotion identification or anomaly label is calculated.

Use every accepted `mart.m5_item_store_weekly_prices_12w` row: 30,490 item/store pairs, twelve complete Saturday–Friday weeks 11601–11612, 2016-01-30–2016-04-22. Preserve all 365,880 positions, including zero-sales and missing-price observations. The accepted window contains 2,561,160 daily cells and 3,536,539 units. These previously established controls are not newly selected outcomes.

SQL45 is read-only and creates no table. Historical SQL, evidence, learner acceptance and source files remain unchanged. The observed final forecast period is not reused or retuned.

## Exact comparison rule

Order all twelve observations chronologically within each item/store pair. Compute the immediately preceding week and its price over that complete sequence, then exclude the first displayed week from the transition report. Never remove missing-price or zero-sales observations before calculating the previous observation, skip a price gap, carry prices forward, borrow another store's price, or import a week outside this interval.

There are eleven potential transitions per pair, hence 30,490 per transition week and 335,390 overall. A transition is comparable only when both current and immediately preceding prices exist. Compare the source DECIMAL(18,2) values directly: current greater than previous is up, lower is down, equal is unchanged. An absent endpoint is an uncomparable transition, not an unchanged price. A return to an earlier price is a new adjacent change: 1.00 → 0.90 → 1.00 has two changes for one distinct pair. Priced zero-sales observations participate fully.

The first week 11601 provides the in-window previous-price endpoint for week 11602 but is not itself a transition row. Report dates describe the current-week endpoint; TOTAL therefore spans 2016-02-06–2016-04-22. The underlying input still spans 2016-01-30–2016-04-22.

## Accepted-input integrity checks

Validate the exact twelve-column SQL44 schema, full product/store/week grid and unique keys, complete calendar week boundaries, nonnegative non-NULL integer-valued stored units, seven source daily rows, and product/department/category/store/state mappings against core dimensions and raw source metadata. Check full pair coverage and the accepted units/daily-cell totals.

Rejoin scoped staging prices by item/store/week and compare exact price and has_price values. Validate the four-column staging price schema and unique known keys with positive exact-cent prices for weeks 11601–11612 plus NULL week records; invalid present rows must fail, including invalid zero-sales prices. Other price weeks remain outside the new audit. Missing prices remain NULL and may accompany only zero units under the accepted coverage contract.

Roll the input table up across stores and compare all eight fields of the accepted 36,588-row `mart.m5_product_weekly_12w`, including its schema and key multiplicity. This read-only audit relies on the already accepted daily-to-weekly construction; it does not rebuild the historical daily fact or claim to recheck every current daily value. Independent preflight separately verifies the complete relevant weekly input against original CSVs.

Guard the empty, malformed or incomplete input before reporting success. Check that the full sequence has exactly one first week per pair, all subsequent previous-week keys are exactly the immediately preceding source week, and all transition partitions reconcile.

## Fixed report contract

Return twelve rows by twelve columns: current weeks 11602–11612 ordered by week_start, followed by TOTAL. Exact column order:

`retail_week, week_start, week_end, potential_transitions, comparable_transitions, missing_endpoint_transitions, price_up_transitions, price_down_transitions, unchanged_price_transitions, comparable_pairs, changed_pairs, check_status`.

For every row:

- Comparable plus missing-endpoint transitions equals potential transitions.
- Up plus down plus unchanged equals comparable transitions.
- Comparable_pairs counts distinct item/store pairs with at least one comparable transition represented by that row.
- Changed_pairs counts distinct item/store pairs with at least one up or down transition represented by that row.
- Changed_pairs is at most comparable_pairs, and comparable_pairs is at most the source pair roster.

Within one weekly row, comparable_pairs equals comparable_transitions and changed_pairs equals up plus down. TOTAL comparable_pairs and changed_pairs are distinct counts over all eleven transitions and are **not sums of weekly pair counts**. The six transition-count fields sum normally across weeks. No percentage, significance test or association result is added. PASS certifies the mechanics and accepted-input checks, not an effect of price on sales. Actual comparability and variation counts are measured after this protocol is fixed, without prescribing their values.

## Independent preflight and publication

Use original read-only sales/calendar/price CSVs, existing SQL44 source-reference helpers, and one private temporary database under containment-checked ignored repository tmp. Two DuckDB threads and a 2GB configured limit are settings, not a total-process memory guarantee. Never open the learner's persistent database or rerun the forecasting pipeline.

Reconstruct only the 84-day sales projection, small date/week calendar and dimensions, twelve-week prices, unchanged SQL23 dependency and unchanged SQL44 input. Reuse independent Python csv/Decimal source readers to derive expected weekly units/prices. Compare every one of the 365,880 input rows across twelve fields; then independently iterate eleven adjacent pairs for every series, preserving missing endpoints and exact prices, and compare every report field/order. The Python reference must derive pair membership and prices from original sources, not SQL45 output. Preserve relevant input snapshots and hashes before/after the read-only query, registered original hashes and relevant historical evidence. Remove private detail exports, spills and databases afterward.

Focused synthetic cases cover first-week exclusion, missing first/intermediate endpoints without bridging, exact-cent changes and equality, a return to an earlier price with nonadditive pair counts, zero-sales price changes, store separation, all-missing/all-unchanged states, reversed row order and malformed/incomplete accepted input. Record only actually executed cases and intended guard rejection behavior.

Pin this protocol, new SQL/validator and unchanged dependency hashes. Public evidence includes aggregate counts and fingerprints only; no real item/store rows, raw vectors, price extracts, screenshots or databases. Assistant preflight and learner execution remain separate states. After learner acceptance, counts may inform the next descriptive analysis; no method is retrospectively presented as prespecified by this audit.
