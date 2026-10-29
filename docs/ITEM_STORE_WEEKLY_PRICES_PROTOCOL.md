# Item-store weekly price and sales construction protocol

Fixed on 2026-10-30 before the new window-specific price summaries are inspected. This begins the descriptive price module after learner acceptance of the two-baseline final forecast report. Historical SQL, protocols, preflights and forecasting decisions remain unchanged.

## Business question and scope

Prepare observations for asking whether a price change for the **same product at the same store** coincides with a sales change. The accepted SQL23 table pools ten stores per product/week and cannot preserve store-specific prices. SQL44 therefore builds a separate item/store/week table. It does not yet calculate price changes, correlations, elasticity, promotion effects or anomaly labels.

Reuse the already fixed twelve complete Saturday–Friday retail weeks **11601–11612**, **2016-01-30–2016-04-22**, source day numbers **1828–1911**. Derive complete weeks from the full source calendar before selecting the interval; do not aggregate partial week fragments or borrow final-holdout days. This window supports short-period descriptive investigation, not annual seasonality or a causal effect. It is not a new forecast evaluation or a way to retune the exposed final period.

Retain the entire released retrospective roster: 3,049 products × ten stores = **30,490 pairs**, all seven departments and three categories/states, including zero-sales pairs and weeks. This is source coverage, not an active-assortment or in-stock roster. The output contains **365,880 item/store/week positions** from **2,561,160 daily records**, totaling **3,536,539 units**. These counts and units follow the accepted SQL23 window; its 1,056 zero-unit pooled product/weeks must not be reused as a store/week zero count. Price coverage and store/week zero counts are new observations and must be measured without prescribing their values.

## Inputs and stored grain

Read accepted `mart.m5_sales_daily` item/store/day/date/week/unit fields, the complete `core.m5_calendar`, `core.m5_product`, `core.m5_store`, source identifier mappings in `raw.m5_sales_wide`, selected `stg.m5_prices` rows, and the accepted `mart.m5_product_weekly_12w` table for reconciliation. Existing daily fact price/value fields are not inputs to this construction. The weekly staged price is joined directly on item_id, store_id and wm_yr_wk.

Create `mart.m5_item_store_weekly_prices_12w` with these exact twelve columns in order:

| Column | Type | Meaning |
| --- | --- | --- |
| item_id | VARCHAR | Source product identifier |
| store_id | VARCHAR | Source store identifier |
| dept_id | VARCHAR | Validated product department |
| cat_id | VARCHAR | Validated product category |
| state_id | VARCHAR | Validated store state code |
| wm_yr_wk | INTEGER | Complete source retail week |
| week_start | DATE | Saturday boundary |
| week_end | DATE | Friday boundary |
| units | HUGEINT | Sum of seven recorded daily quantities for this product/store |
| source_daily_rows | BIGINT | Exactly seven contributing daily records |
| sell_price | DECIMAL(18,2), nullable | Source weekly price, with NULL if its key is absent |
| has_price | BOOLEAN | True exactly when the valid source price key exists |

Each item/store/week key occurs once and every pair retains all twelve weeks. Keep zero units as observed; never manufacture missing daily records as zeros. Do not average prices across stores, borrow adjacent-week prices, fill price gaps, replace missing prices with zero, or calculate monetary revenue/profit in this step.

## Source and join checks

Validate complete product/store identifier mappings against the raw metadata and exact released pair roster. Check required keys, one-to-one product→department/category and store→state mappings, and dimension uniqueness before joining. Check the complete calendar's relevant contracts and the selected weeks' seven distinct consecutive dates/day keys, correct Saturday–Friday boundaries and 84-day coverage.

Each selected item/store series must have 84 unique daily positions; each selected pair/week must have seven. Check exact day/date/week relationships, known product/store keys and nonnegative, non-NULL integer units. A missing day replaced by a duplicate must fail even if row counts and quantities happen to agree. Joins must preserve source rows and units. Empty or incomplete sources must raise a guarded error rather than silently creating an empty target.

Price validation is explicitly scoped to the twelve selected week keys, plus malformed NULL week keys that cannot safely be classified outside the interval. Audit known nonempty item/store keys, unique item/store/week keys, a valid INTEGER week representation, and finite positive exact-cent DECIMAL(18,2) prices. Reject invalid present rows; an absent key is distinct from a present row with a NULL or invalid price. Other out-of-window price records are not newly re-audited. The source snapshot's earlier full-price audit remains separate historical evidence.

LEFT JOIN one valid weekly price per pair/week, preserving all 365,880 positions. Retain absent prices as NULL with has_price=false only for zero-unit weeks. A positive-unit week with no matching price blocks construction under the already accepted positive-sales coverage contract. Price presence or absence does not establish stock availability, product launch, delisting or promotion status.

## Stored-table checks and report

Use ordinary CREATE TABLE without replacing an existing object. Include a clearly marked `-- VALIDATION:` query that can be rerun independently. Recompute expected rows from current source projections, verify the exact stored schema/order/types and key coverage, and compare all twelve fields in both directions with EXCEPT ALL. Total-preserving redistribution of quantities, altered hierarchy/week fields, duplicate/missing rows or changed price/has_price pairs must fail. Validate price semantics even for zero-unit rows, rather than allowing a zero sales-value calculation to hide price corruption.

Roll the new table up over stores by item/week and compare all eight original SQL23 fields against `mart.m5_product_weekly_12w`, including its stored schema, multiplicity, hierarchy, boundaries, units and daily-row counts. Check all **36,588 product/week rows**, not only the overall total. The prior table and all other inputs must remain unchanged.

Return **thirteen rows × twelve columns**: twelve weekly rows ordered by actual week start, then TOTAL. Column order:

`retail_week, week_start, week_end, series_week_rows, source_daily_rows, units, zero_sales_series_weeks, priced_series_weeks, missing_price_series_weeks, missing_price_positive_sales_weeks, priced_units, check_status`.

Each week has 30,490 item/store/week observations and 213,430 daily records; TOTAL has 365,880 and 2,561,160 respectively. TOTAL spans the same 84 days. Weekly and total units must match the accepted SQL23 report. `priced_series_weeks + missing_price_series_weeks = series_week_rows`; missing-positive counts must be zero, and priced_units must equal units. Zero and missing counts describe weekly positions, not distinct products or stores. Preserve their observed values and all zero-sales weeks. PASS means construction and reconciliation succeeded, not that a price–sales relationship exists.

## Independent validation and publication

Use only original read-only CSVs and a private temporary DuckDB database under the repository's containment-checked ignored tmp directory. Never open or alter the learner's persistent database. Use two threads and a 2GB DuckDB limit as settings, not a guarantee of total process memory. Compare only the relevant 84-day sales and twelve-week price projections, complete small calendar and metadata; source file hashes identify the unchanged full files. Do not rebuild the forecasting pipeline or rerun historical fixture suites.

An independent Python csv/Decimal calculation groups the original seven wide daily columns for each pair/week and matches exact-cent prices by the full key. Compare every stored output row and all twelve fields with this reference, plus every report field and order. Reproduce the unchanged SQL23 table on the private 84-day input and compare all 36,588 original product/week rows independently, then verify the exact SQL44 rollup and the historical accepted weekly report. Preserve source projections and the prior product table before/after SQL44. Publish only aggregate reports, schema information and fingerprints; do not publish real SKU identifiers, private row extracts, screenshots or databases.

Focused test families cover valid zero/missing-price/boundary cases; daily completeness and mappings; calendar and dimension integrity; scoped price keys/types/coverage; exact stored rows and schema; rollup corruption; and rerun/nonoverwrite behavior. Use meaningful subcases for distinct failure modes and record actual executed counts, without padding or claiming historical suites were rerun. A rejected build must not leave a new target table. Report precise validation behavior for rejected stored-table checks.

Pin the fixed protocol, implementation, relevant historical evidence and source hashes. After verification, confirm sources, prior tables and relevant input projections remain unchanged; remove private databases, spills and detail exports. Distinguish assistant preflight from learner execution. After learner acceptance, the next analytical step can inspect how many same-series adjacent-week comparisons have usable prices and actual price variation before selecting an association method.
