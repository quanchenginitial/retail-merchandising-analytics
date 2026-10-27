# Proposed data model and metric contract

Stage 0 design. Tables and measures below have not been implemented. Audit source schemas before freezing types or business rules.

## Independent modules

`raw` retains imported source values; `stg` contains typed and audited records; module-specific marts support analysis. Namespace M5 and Retailrocket dimensions separately. Do not join cross-publisher IDs or sum their monetary/behavioural totals.

| Proposed object | Grain | Core rule |
| --- | --- | --- |
| `raw.m5_sales_wide` | One source item/store series | Only evaluation training file; do not append overlapping validation history |
| `stg.m5_sales_daily` | One item × store × source day | UNPIVOT d_1...d_1941; preserve zero units; reject invalid numeric conversion |
| `core.m5_product` | One item | Verify each item maps consistently to department/category |
| `core.m5_store` | One store | Verify each store maps consistently to state |
| `core.m5_calendar` | One source day | Unique d/date; map weekly identifier explicitly |
| `stg.m5_prices` | One item × store × week | Unique composite key; preserve missing prices as unknown |
| `mart.m5_sales_daily` | One item × store × date | Join calendar then LEFT JOIN prices; row count and units unchanged |
| `mart.m5_product_week` | One item × store × week | Aggregate only after daily reconciliation; distinguish missing price coverage |
| `stg.rr_events` | One source event row | Audit duplicates; no invented source event ID; retain an ingestion row identifier for traceability |
| `stg.rr_item_property_history` | One item × property × change time | Resolve equal-time conflicting values explicitly before as-of joining |
| `mart.rr_event_context` | One audited event | Latest known property at/before event time; never backfill from future |
| `mart.rr_basket_items` | One audited basket key × distinct item | Candidate key visitorid + transactionid, subject to reuse/collision audit; binary item presence |
| `mart.rr_cart_episodes` | One defined visitor/item cart episode | Event order, repeat-cart handling and complete purchase horizon required |

## Planned M5 metrics

- **Recorded units:** sum of observed nonnegative integer units. This measures realized recorded sales, not latent demand.
- **Estimated sales value (USD proxy):** sum of units × published weekly average sell_price for price-covered rows. Expose priced units and price coverage; if positive sales lack a price, headline complete-value totals stay unavailable instead of silently becoming partial totals. Do not call it net revenue, margin or customer spend.
- **Product share:** units (or covered value proxy) divided by the total under exactly the same date/store/category filters. State which measure is used.
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
