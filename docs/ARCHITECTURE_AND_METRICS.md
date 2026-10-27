# Proposed data model and metric contract

The M5 raw/staging tables, core dimensions, daily joins, price coverage and daily sales fact have all been accepted from learner screenshots as of 28 October 2026. The [model checkpoint](ANALYTICAL_MODEL_CHECKPOINT.md) records their scope. The fixed 90-day category contribution report has also been accepted. Department contribution is the current business-analysis step; ABC/XYZ, forecasts and Power BI are not yet accepted. Planned objects and methods below remain explicitly prospective where not covered by that checkpoint.

## Independent modules

`raw` retains imported source values; `stg` contains typed and audited records; module-specific marts support analysis. Namespace M5 and Retailrocket dimensions separately. Do not join cross-publisher IDs or sum their monetary/behavioural totals.

| Proposed object | Grain | Core rule |
| --- | --- | --- |
| `raw.m5_calendar` | One source day | Preserve source values; audited day/date mapping |
| `raw.m5_sales_wide` | One source item/store series | Only evaluation training file; do not append overlapping validation history |
| `raw.m5_prices` | One source item × store × week | Preserve four source VARCHAR fields; validate keys before typed joins |
| `stg.m5_calendar` | One source day | DATE plus seven INTEGER and six VARCHAR fields; retain all dates and event NULLs; lossless round-trip validation |
| `stg.m5_sales_daily` | One item × store × source day | Four columns: item_id/store_id/d VARCHAR and units INTEGER; retain zero units; verify complete day keys, then reconcile every value |
| `core.m5_product` | One item | Three source VARCHAR codes; unique item_id and exact source triple equality accepted in 15 checks; no declared physical PRIMARY KEY |
| `core.m5_store` | One store | Two source VARCHAR codes; exact mapping and unique store_id accepted in 13 checks; no state inferred from identifier prefix or physical PRIMARY KEY declared |
| `core.m5_calendar` | One source day | Original 14 fields plus INTEGER day_number, unique d/date and exact source equality accepted in 17 checks; all 1,969 dates retained, including 28 after sales observation |
| `stg.m5_prices` | One item × store × week | Guarded DECIMAL(18,2), INTEGER week, exact value-equivalence reconciliation; absent price rows remain unknown |
| `mart.m5_sales_daily` | One item × store × observed date | Nine fields: item_id/store_id/d VARCHAR, date DATE, wm_yr_wk/units INTEGER, sell_price DECIMAL(18,2), has_price BOOLEAN, estimated_sales_value DECIMAL(28,2). Exact calendar/week price joins; no future rows or declared physical PRIMARY KEY |
| `mart.m5_product_week` | One item × store × week | Aggregate only after daily reconciliation; distinguish missing price coverage |
| `stg.rr_events` | One source event row | Audit duplicates; no invented source event ID; retain an ingestion row identifier for traceability |
| `stg.rr_item_property_history` | One item × property × change time | Resolve equal-time conflicting values explicitly before as-of joining |
| `mart.rr_event_context` | One audited event | Latest known property at/before event time; never backfill from future |
| `mart.rr_basket_items` | One audited basket key × distinct item | Candidate key visitorid + transactionid, subject to reuse/collision audit; binary item presence |
| `mart.rr_cart_episodes` | One defined visitor/item cart episode | Event order, repeat-cart handling and complete purchase horizon required |

## M5 metric contract and planned extensions

- **Recorded units:** sum of observed nonnegative integer units. This measures realized recorded sales, not latent demand.
- **Estimated sales value (USD proxy):** when units=0, value=0.00 whether or not a price is present; when units>0, multiply by the matching published weekly average sell_price. Positive sales without a price abort this fact build. Preserve the absent price as NULL and has_price=false; never substitute a zero price. The zero-quantity convention describes recorded sales value only, not lost sales or demand. Expose daily-row, positive-row and unit-weighted coverage separately. Use DECIMAL(20,0) for the units operand so DuckDB evaluates the product as DECIMAL(38,2), then store DECIMAL(28,2); no floating-point multiplication or rounding of source cents. Do not call it verified transaction revenue, net revenue, margin or customer spend.
- **Category/department/product share:** units or estimated value divided by the all-category total under the same date/store scope. SQL18 fixes all 10 stores and 2016-01-26–2016-04-24 inclusive (90 days), before the final forecast holdout. Aggregate exact amounts before dividing; display percentages to four decimals. Zero denominator produces NULL, not zero or 100%. Rounded category shares may sum to 99.9999 or 100.0001. The SKU count includes all distinct source item IDs in the window, even with zero units; it is not an active-availability count. This window/cutoff also anchors the planned 90-day ABC exercise, but category contribution itself is not ABC classification. SQL19 adds seven source departments under the same window. Its global unit/value shares use all categories; within_category_value_share_pct divides each department value by its own category value. TOTAL has no parent category and its within-category share is NULL. Category denominators are calculated from category aggregates; department rollups must reproduce their unrounded counts/amounts. Anonymous source department codes are retained without invented subcategory descriptions.
- **ABC:** initial proposed bands A through 80% cumulative units, B through 95%, C remainder, over a fixed trailing 90-day window ending at the analysis cutoff. Sort deterministically by units then item ID. Report boundary-crossing convention and sensitivity; thresholds are project choices, not industry laws. Display non-selling SKUs separately.
- **XYZ:** variability classification using weekly units from a documented comparable observation window. CV is undefined at mean zero; keep that group separate. A provisional X ≤ 0.5, Y ≤ 1, Z > 1 classification needs sensitivity review. Also show zero-sales share and mean nonzero gap so CV does not hide intermittent sales. Availability is not known from zero units.
- **Price association:** compare within item/store over time and account for calendar patterns; no causal elasticity claim from raw correlations. Do not relabel all price reductions as documented promotions.
- **Anomaly candidate:** deviation from a historical, seasonally appropriate baseline, plus a record of data coverage. It is a triage flag, not a proven incident.

## Planned Retailrocket metrics

- **Visitors:** distinct anonymous visitorid within the stated eligible population/window; not verified people.
- **Behavioural RF:** recency and frequency of separately defined views, carts and recorded transactions. No monetary component without an interpretable monetary field.
- **Session:** proposed 30 minutes of inactivity boundary per visitor; a derived convention, not a supplied session ID. Validate ties and compare alternative thresholds.
- **Cart conversion proxy:** fraction of eligible deduplicated cart episodes with a later observed transaction for the same visitor/item within 24 hours. Same-time ambiguity is reported. Episodes in the final 24 hours are censored; lack of purchase does not prove abandonment. Audit repeated carts and pre-existing purchase events before freezing the denominator.
- **Co-purchase rules:** unique baskets containing both items / all eligible baskets for support; both / antecedent baskets for confidence; confidence / consequent prevalence for lift. Require minimum co-occurrence and assess later-period stability. Quantity and basket value are unavailable unless explicitly documented.
- **Availability coverage:** proportion with a known prior `available` value; separate known unavailable from unknown. Source observations are not a live inventory ledger.

## Join and reporting acceptance

Check key uniqueness, relationship cardinality, missing coverage, date continuity and exact before/after row counts. Reconcile units at series, store and overall levels; compare selected calculations independently. Do not collapse nulls to zero without a metric-specific reason.

Power BI should consume audited aggregates rather than importing all 59 million daily cells by default. Prototype store/category/day summaries, product/week summaries and forecast evaluation summaries; include drill-through only after size/performance checks. Planned pages: Merchandise Overview, Assortment and Variability, Forecast Quality, Shopping Behaviour, and optional Experiment Evidence. Unit, period, denominator and module must be visible.

Source field meanings: [M5 guide](https://github.com/Mcompetitions/M5-methods/blob/master/M5-Competitors-Guide.pdf), [Retailrocket publisher](https://www.kaggle.com/datasets/retailrocket/ecommerce-dataset). Thresholds, table names and episode definitions are proposed project decisions.
