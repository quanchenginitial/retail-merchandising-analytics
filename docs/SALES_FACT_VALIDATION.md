# Daily sales fact: value contract and validation

27 October 2026. The learner has accepted daily price coverage. The current script, [17_build_sales_fact.sql](../sql/17_build_sales_fact.sql), creates `mart.m5_sales_daily`. Full-data preflight is assistant-only; learner execution and acceptance remain pending.

## Purpose and grain

Persist one row per item/store/observed day for subsequent product, category, store and time analysis. The table has nine columns: item_id, store_id, d, date, wm_yr_wk, units, sell_price, has_price and estimated_sales_value. Product/category and store/state attributes remain in the small accepted dimensions rather than being copied into every daily row. Retain all 59,181,090 observations, including zeros; do not manufacture sales for the calendar's final 28 dates.

Calendar supplies the date and source retail week. Price matches exactly item/store/week. Product and store keys must have one match. Full weekly price keys and calendar day/date keys are guarded before joins; invalid or duplicate price/calendar rows, including unused duplicates, stop execution. Source units must be nonnegative INTEGER values with canonical observed day IDs. These checks complement previously accepted source reconciliations; they are not a new audit of the original download.

## Monetary convention

- Zero units yield 0.00 estimated value, including on unpriced days. Missing sell_price remains NULL and has_price=false.
- Positive units require a matching weekly price. Otherwise creation stops rather than producing a partial headline total.
- Positive price times units is an estimated USD sales-value proxy. Published weekly prices do not establish transaction-level revenue, refunds, net sales, costs, margin or profit.
- Prices remain DECIMAL(18,2). Cast units to DECIMAL(20,0) before multiplication to force a DECIMAL(38,2) intermediate, then store DECIMAL(28,2). A narrower decimal operand can produce a narrower intermediate in DuckDB; an outer cast alone would not prevent intermediate overflow. SUM uses DECIMAL(38,2).

This is an explicit zero-quantity accounting convention, not a claim about why a price is missing, whether an item was available, or lost demand.

## Acceptance query

The final query returns 20 checks and one observed total. It verifies the exact nine-column schema, known row/unit/zero/price counts, missing/invalid fields, series sets and product/store references. For each of 30,490 series, a count of 1,941 plus a bounded day bitmap proves complete, unique day keys. The same proof is applied independently to staging. Ordered daily-unit lists then compare all 59,181,090 values exactly, detecting changes that leave overall totals unchanged. Unique accepted calendar dates plus exact calendar field matching establish the item/store/date grain; no physical primary key is declared.

Every fact row independently looks up the accepted calendar using d, then the price using that calendar's week. It does not trust the fact's week to obtain its expected price. NULL-safe comparisons check date/week, price, has_price and recomputed value. Thus a fact week and price changed together cannot validate each other. The final monetary total is INFO only if all 20 preceding checks pass; otherwise it is INCOMPLETE.

CTAS is followed by validation. Duplicate or missing source daily keys can therefore create an unaccepted table that fails the final checks. A successful CREATE alone never constitutes acceptance. The script never overwrites an existing fact; if it already exists, rerun only the section below `-- VALIDATION:`.

## Independent execution evidence

The [preflight runner](../validation/preflight_sales_fact.py) rebuilds prerequisite raw/staging/dimension objects in a private temporary on-disk DuckDB, then creates and validates the fact. It uses two threads and a 2GB DuckDB memory limit, with spill files under the same ignored temporary directory. It never opens the learner database. Source hashes must match the registry before execution and remain unchanged afterward. Database and spills are removed after the run. The recorded closed database size is not a peak disk or memory measurement.

The [machine-readable result](../data/sales_fact_preflight.json) records all outputs, engine version, script hash, timings and 25 targeted cases. Cases cover missing-price zeros, priced zeros, positive sales without prices, wrong-store prices, unused duplicate keys, invalid prices/types, missing/duplicate dimension matches, missing/duplicate calendar days, invalid units, tampered prices/flags/amounts, same-total daily sales shifts, duplicate-and-missing day pairs, and independently matched week/price discrepancies. Decimal tests verify 3 Ã— 0.10 = 0.30 and the full declared INTEGER Ã— DECIMAL(18,2) domain boundary without floating point or overflow.

Full source execution passed all 20 checks. Fact creation took 49.393 seconds and the full acceptance query 38.365 seconds after 79.594 seconds of prerequisite setup in this environment. All 59,181,090 rows and 66,927,173 units were retained. The observed total estimated sales value is **USD 191,577,546.04** over 2011-01-29 through 2016-05-22. It is an assistant-only preflight observation awaiting learner reproduction, not verified transaction revenue. All 25 targeted cases passed; source hashes remained unchanged and the temporary database was removed.

## Next acceptance

Follow the [current learner step](FIRST_STEP_ZH.md). Inspect the learner's 21-row result before recording fact completion. Historical preflight observations are not portfolio business findings or a learner execution record. Aggregate merchandising analysis starts only after fact acceptance.
