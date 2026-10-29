# Adjacent-week price variation: method and validation

## Purpose and status

SQL44 was learner-accepted on **30 October 2026**: all thirteen rows and twelve fields match its frozen report. See the [acceptance record](../data/item_store_weekly_prices_learner_acceptance.json). [SQL45](../sql/45_audit_price_variation.sql) now asks how many usable adjacent-week comparisons and actual price changes exist within the same item/store pair. This establishes data support before choosing a later price–sales association method.

The [protocol](PRICE_VARIATION_PROTOCOL.md) was fixed before computing these new variation counts. SQL45 is a read-only query. **Assistant preflight passed; learner SQL45 execution and screenshot acceptance remain pending.** Forecast selection and the accepted final report remain unchanged.

## Observation and comparison units

The input is the accepted `mart.m5_item_store_weekly_prices_12w`: 30,490 pairs × twelve complete retail weeks, **2016-01-30–2016-04-22**, or 365,880 positions. It includes zero-sales weeks and missing prices; it does not assert that every released pair was actively stocked.

Compute the previous observation with LAG across all twelve ordered records within each item/store. Only afterward exclude the first week from transition rows. Every pair therefore has eleven potential comparisons: **335,390** in total. A comparison uses the same pair in consecutive weeks, with both exact-cent prices present. Higher, lower and equal current prices form the up, down and unchanged classes. A missing price at either endpoint makes the comparison uncomparable; there is no gap bridging, price filling or positive-sales filter.

The first input week is the previous endpoint for the first comparison. Output dates refer to the current endpoint, so eleven weekly rows cover **2016-02-06–2016-04-22**; TOTAL spans those same dates. This is deliberate and does not drop the first week's input.

The first six count fields describe transitions and add across weeks. `comparable_pairs` counts distinct item/store pairs with at least one comparable transition; `changed_pairs` counts pairs with at least one up/down transition. **TOTAL pair counts are not sums of weekly pair counts.** A pair with prices 1.00 → 0.90 → 1.00 contributes two changes but only one changed pair.

## Integrity checks and independent preflight

The query checks the accepted weekly schema, complete grid, unique keys, calendar boundaries, source mappings, units and seven source daily rows per observation. Prices and coverage flags reconcile exactly to the typed staging price table on item/store/week. It checks the existing product/week rollup as well. Empty or malformed input must fail visibly; no new persistent table is created. SQL45 relies on SQL44's accepted daily-to-weekly construction and does not claim to re-audit every current daily fact value.

The [independent validator](../validation/preflight_price_variation.py) reconstructs only the relevant 84-day source projection and twelve price weeks in a private temporary database. Original CSVs are read-only and the learner's database is never opened. It reuses frozen source-reading helpers and the unchanged SQL23/SQL44 dependencies, without running the forecasting pipeline. Python csv/Decimal logic checks the weekly input against original sources, then independently traverses consecutive weeks and derives the aggregate report. The [machine evidence](../data/price_variation_preflight.json) records actual comparisons, targeted cases, fingerprints, unchanged inputs and cleanup.

Focused cases exercise missing endpoint behavior, first-week boundaries, zero-sales changes, equal prices across different stores, return-to-prior-price patterns, distinct pair totals, input order and invalid input rejection. The recorded cases belong to this audit; historical suites are not presented as rerun.

The completed run matched **365,880 weekly input rows × 12 fields**, **365,864 staged prices × 4 fields**, and **36,588 pooled rows × 8 fields** against the independent original-source reference. The weekly fingerprint also matches frozen SQL44 evidence. All twelve report rows and twelve fields match. All **9 focused cases** passed, comprising 4 valid scenarios and 5 intended guard rejections. All 7 input snapshots, original source hashes, code dependencies and 43 historical preflights remained unchanged; private files were removed. The learner's database was not accessed.

## Measured assistant report

The complete machine report contains twelve rows and twelve fields, including current-week start/end dates. This compact view omits only those two date columns.

| Current week | Potential | Comparable | Missing endpoint | Up | Down | Unchanged | Comparable pairs | Changed pairs | Status |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 11602 | 30490 | 30482 | 8 | 218 | 418 | 29846 | 30482 | 636 | PASS |
| 11603 | 30490 | 30482 | 8 | 138 | 177 | 30167 | 30482 | 315 | PASS |
| 11604 | 30490 | 30490 | 0 | 69 | 101 | 30320 | 30490 | 170 | PASS |
| 11605 | 30490 | 30490 | 0 | 207 | 164 | 30119 | 30490 | 371 | PASS |
| 11606 | 30490 | 30490 | 0 | 576 | 265 | 29649 | 30490 | 841 | PASS |
| 11607 | 30490 | 30490 | 0 | 236 | 198 | 30056 | 30490 | 434 | PASS |
| 11608 | 30490 | 30490 | 0 | 213 | 83 | 30194 | 30490 | 296 | PASS |
| 11609 | 30490 | 30490 | 0 | 123 | 119 | 30248 | 30490 | 242 | PASS |
| 11610 | 30490 | 30490 | 0 | 108 | 84 | 30298 | 30490 | 192 | PASS |
| 11611 | 30490 | 30490 | 0 | 92 | 64 | 30334 | 30490 | 156 | PASS |
| 11612 | 30490 | 30490 | 0 | 80 | 63 | 30347 | 30490 | 143 | PASS |
| TOTAL | 335390 | 335374 | 16 | 2060 | 1736 | 331578 | 30490 | 3361 | PASS |

Every row satisfies `comparable + missing endpoint = potential` and `up + down + unchanged = comparable`. Within a weekly row the pair and transition counts coincide where defined; TOTAL uses full-window distinct pair counts. There are **3,361 distinct item/store pairs** with at least one comparable price change, out of **30,490 pairs** with at least one comparable transition. These are combinations, not a count of unique products or stores.

The sixteen missing-price weekly positions accepted in SQL44 and SQL45's missing-endpoint transition count measure different things: one missing weekly position may affect an adjacent comparison on either side. Do not substitute one metric for the other, even if their measured totals happen to match.

Ordered report SHA256: `417d051dbcdd4c28eae74a72e692e1b5f33e73de36ba6d66f10542543a24880b`. Its canonical contract is the fixed field-order row arrays, compact JSON and one LF per row, with integer counts and string week/date/status values. Only aggregates and fingerprints are published; private per-pair records and screenshots are excluded.

## Interpretation and next learner step

Price variation is a necessary observation condition for within-pair comparisons, not evidence that a price change caused a sales change. Repeated overlapping weekly comparisons are not independent experiments. Calendar effects, availability and other unobserved drivers remain potential alternative explanations. A lower published price is not automatically a documented promotion. This short window supports descriptive investigation and does not establish elasticity, profit, inventory savings or stockouts.

Execute the entire SQL45 query in a new DBeaver editor connected to **retail_merchandising**, then return **twelve rows and twelve columns**, including check_status. See [the Chinese current-step guide](FIRST_STEP_ZH.md). After screenshot acceptance, these measured counts can guide the next descriptive analysis; this audit has not yet computed a price–sales relationship.
