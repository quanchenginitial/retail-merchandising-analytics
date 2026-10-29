# Item-store weekly price and sales: construction and validation

## Purpose and scope

After the accepted [baseline forecasting milestone](STAGE05_BASELINE_FORECAST_FINDINGS.md), SQL44 prepares observations for descriptive price analysis. The question is whether price changes for the same product at the same store coincide with sales changes. The existing SQL23 product/week table pools ten stores, so it cannot preserve their individual prices.

The [fixed protocol](ITEM_STORE_WEEKLY_PRICES_PROTOCOL.md) uses the same twelve complete Saturday–Friday retail weeks as SQL23/XYZ: **11601–11612, 2016-01-30–2016-04-22**, source days 1828–1911. Keep all 3,049 products × ten stores × twelve weeks = **365,880 observations**, from **2,561,160 daily records** and **3,536,539 recorded units**. The released roster is retrospective source coverage, not verified active assortment or stock availability. No final-holdout days or price-driven window selection are introduced.

This step builds and reconciles the observation table. It does not yet calculate price changes, correlations, elasticity or promotion effects. Twelve weeks describe a short period; seasonality, supply conditions and other drivers will require separate consideration. The accepted forecast choice and results remain fixed.

## Stored table

[SQL44](../sql/44_build_item_store_weekly_prices.sql) creates `mart.m5_item_store_weekly_prices_12w`, one row per item_id/store_id/wm_yr_wk. Its twelve fields are:

| Fields | Types / meaning |
| --- | --- |
| item_id, store_id | VARCHAR source keys |
| dept_id, cat_id, state_id | VARCHAR attributes from validated product/store mappings |
| wm_yr_wk | INTEGER source retail-week key |
| week_start, week_end | DATE complete-week boundaries |
| units | HUGEINT sum of seven recorded daily quantities |
| source_daily_rows | BIGINT, exactly 7 for each stored observation |
| sell_price | Nullable DECIMAL(18,2), published weekly price for the exact key |
| has_price | BOOLEAN indicating a valid matching price record |

Use the unit/date/week fields of the accepted daily sales fact, the accepted core dimensions/calendar, raw identifier mappings and selected typed weekly prices. The daily fact's existing price and sales-value fields are not inputs. Keep zero-unit weeks. An absent price stays NULL with has_price=false; it is never filled from another store/week or replaced by zero. Under the accepted positive-sales coverage contract, a positive-unit week without a price blocks construction. An invalid present price record also blocks construction, even with zero units.

## Construction and reconciliation

Validate the full released pair roster and raw-to-core product/store mappings before joining. Derive complete retail weeks from the full calendar and verify all 84 distinct selected day positions. Each pair must contribute 84 unique dates and each weekly row seven; balanced duplicate/missing days must fail even when totals agree. Validate nonnegative integer units and exact source day/date/week relationships. Empty, incomplete or multiplying joins must fail visibly.

Scope weekly prices to 11601–11612, also checking malformed NULL week keys. Require unique known item/store/week keys and positive exact-cent typed prices. Out-of-window price records are not newly re-audited; earlier full-source price checks remain historical evidence. Join on all three keys with LEFT JOIN to preserve zero-unit and missing-price observations.

The independent validation section recomputes expected rows, checks exact stored column names/types/order and key coverage, and compares all twelve fields with EXCEPT ALL in both directions. This catches total-preserving reallocations, altered metadata or week boundaries, price/flag corruption, and duplicate/missing stored rows. The new table must also roll up to all **36,588 rows × eight fields** of `mart.m5_product_weekly_12w`, including hierarchy, boundaries, quantities and contributing row counts. The existing product table remains unchanged.

## Thirteen-row report

The report has twelve weekly rows followed by TOTAL, with twelve columns:

| Field | Meaning |
| --- | --- |
| retail_week / week_start / week_end | Week label and boundaries; TOTAL spans the 84-day window |
| series_week_rows | Item/store/week positions: 30,490 per week, 365,880 in TOTAL |
| source_daily_rows | Contributing daily positions: 213,430 per week, 2,561,160 in TOTAL |
| units | Recorded unit sum, matching the accepted SQL23 window |
| zero_sales_series_weeks | Weekly positions with zero recorded units |
| priced_series_weeks | Weekly positions with a valid matching price |
| missing_price_series_weeks | Weekly positions without a matching price |
| missing_price_positive_sales_weeks | Must be zero under the fixed coverage contract |
| priced_units | Units in priced positions; must equal units |
| check_status | Construction, source and exact reconciliation checks |

Priced plus missing positions must equal all positions. Zero and missing counts are observations, not distinct product/store counts. Do not copy SQL23's 1,056 zero pooled product/weeks into this new grain. Neither missing prices nor zero units establishes a stockout, delisting or absence of demand.

## Independent preflight

The [validator](../validation/preflight_item_store_weekly_prices.py) reads original CSVs and uses a private temporary database under ignored tmp; it never opens the learner's database. Its source projection includes only the 84 selected daily columns and twelve price weeks, with the complete calendar date/week projection and metadata. Registered source hashes identify the full unchanged files. No forecasting pipeline or historical fixture suite is rerun.

An independent Python csv/Decimal calculation groups each source pair's seven daily values for every selected week, matches prices on the full key and compares every new stored row across twelve fields. The unchanged SQL23 is reproduced in the private window fixture; all 36,588 original product/week rows are independently checked, then preserved while SQL44 builds and reconciles its rollup. All report values and row order are compared. Sources, relevant input projections, original weekly table, fixed protocol and historical evidence remain unchanged; private exports/databases are removed. No real product identifiers or individual weekly observations are published.

Focused tests address valid zero and missing-price cases, observation-window boundaries, daily/calendar/dimension integrity, scoped price validity, stored-table corruption, exact rollup and nonoverwrite behavior. Record actual executed families and subcases in the evidence; a PASS means the data model is consistent, not that price explains sales.

The executed [machine evidence](../data/item_store_weekly_prices_preflight.json) records **365,880 stored rows × twelve exact fields**, all matching the independent original-source reference, and **thirteen report rows × twelve fields, all PASS**. All **8 focused test families / 33 executed subcases** passed. The preflight compared all 2,561,160 selected daily rows across six fields, 365,864 scoped price rows across four fields, and all 36,588 original pooled rows across eight fields.

The exact item/week rollup and the historical SQL23 weekly controls matched. All seven relevant input snapshots, source hashes, the prior pooled table and historical preflight files stayed unchanged; private databases and detail exports were removed. Existing-target refusal and validation-only rerun behavior were verified. **Learner SQL44 execution remains pending.**

### Selected fields from the measured report

Every week retains 30,490 item/store observations and 213,430 daily records; the machine evidence contains all twelve report fields and dates. Missing-price positive-sales counts are zero and priced_units equals units in every row.

| Week | Units | Zero-sales positions | Priced positions | Missing-price positions | Status |
| --- | ---: | ---: | ---: | ---: | --- |
| 11601 | 291534 | 6378 | 30482 | 8 | PASS |
| 11602 | 305409 | 6333 | 30482 | 8 | PASS |
| 11603 | 299279 | 6262 | 30490 | 0 | PASS |
| 11604 | 280579 | 6329 | 30490 | 0 | PASS |
| 11605 | 291839 | 6040 | 30490 | 0 | PASS |
| 11606 | 304015 | 5942 | 30490 | 0 | PASS |
| 11607 | 297551 | 5737 | 30490 | 0 | PASS |
| 11608 | 281241 | 5772 | 30490 | 0 | PASS |
| 11609 | 282697 | 5529 | 30490 | 0 | PASS |
| 11610 | 309668 | 5116 | 30490 | 0 | PASS |
| 11611 | 306203 | 5102 | 30490 | 0 | PASS |
| 11612 | 286524 | 4998 | 30490 | 0 | PASS |
| TOTAL | 3536539 | 69538 | 365864 | 16 | PASS |

These are weekly positions, not unique products or evidence of stockouts. Table construction does not establish any price–sales association. Ordered report SHA256: `ecf14a9fdf423410c9118114ee6a0f0693c12ffeca1f1ae020b95a657efd3d18`.

## Learner action and next question

Run the entire SQL44 file once in a new editor under the retail_merchandising DBeaver connection. It creates a new analysis table and does not overwrite an existing object. If the target already exists, execute only the complete query after `-- VALIDATION:`; do not drop the table just to rerun the checks. Return all 13 report rows and twelve columns, including check_status.

After acceptance, investigate usable price coverage and actual price variation within each pair before choosing an association statistic. Do not interpret cross-product price differences as price response, or claim causal elasticity, inventory savings, profit or a live promotion effect from this construction.
