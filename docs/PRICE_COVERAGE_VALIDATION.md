# Daily price coverage: method, observations and learner acceptance

27 October 2026. The learner-supplied DBeaver screenshot for [16_audit_price_coverage.sql](../sql/16_audit_price_coverage.sql) shows all 23 result rows: 14 PASS and 9 INFO. Every displayed value matches the earlier independent preflight. Daily price coverage is accepted on screenshot evidence; no direct read of the learner database was performed. The [learner acceptance record](../data/price_coverage_learner_acceptance.json) preserves the transcribed results separately from assistant execution evidence.

## Purpose and matching rule

A weekly price can be used only for the same item_id, store_id and source wm_yr_wk. The query first maps sales d to the accepted calendar week, then LEFT JOINs the price key. Multiple days in the same week may correctly share one price row. Prices from another store or another week are never borrowed or filled forward/backward. Missing prices remain missing; no monetary value is calculated here.

Before joining, the full price table is checked for duplicate or missing composite keys and finite positive prices. A MATERIALIZED guard retains only the three keys needed for coverage, avoiding carrying price amounts into every daily result. Duplicate keys, including unused ones, and invalid prices cause an error before acceptance. Calendar keys/weeks are similarly guarded. Coverage uses the matched non-NULL price week as its marker, rather than treating an invalid price value as an ordinary missing lookup.

Independent base/join aggregates check rows, units, zero-sales rows and store-level preservation. Missing calendar matches and invalid source sales are reported separately. The script relies on earlier accepted source values, calendar semantics and product/store joins; it does not redo their full source reconciliations.

## Reading the 23 result rows

- Rows 1â€“12: mechanical checks, expected PASS. These establish valid inputs and unchanged rows/units/zeros at overall and store levels.
- Rows 13â€“14: positive-sales price-coverage gates. Zero unpriced positive-sales rows and zero unpriced units are required before claiming a complete estimated sales-value proxy. A nonzero result blocks that completeness claim; it does not automatically prove the source is wrong or prevent unit-based analysis.
- Rows 15â€“23: observed counts and percentages, marked INFO. A zero denominator gives NULL with status N/A, never a fabricated 100%.

If any of rows 1â€“12 fails, rows 13â€“23 show INCOMPLETE. In particular, a missing calendar match must not be interpreted as confirmed missing price coverage for a valid week. An invalid price/calendar guard stops the query instead of returning the grid.

Daily row coverage counts all observed item/store/day cells, including zeros. Positive-row coverage counts only rows with units greater than zero. Unit coverage weights by the number of units sold. These denominators answer different questions and are reported separately.

## Full-source observations â€” confirmed by learner screenshot

All 12 mechanical checks and both positive-sales coverage gates passed. Base and joined totals remain 59,181,090 rows, 66,927,173 units and 40,241,819 zero-sales rows. Calendar misses, invalid sales and store-control differences are zero.

| Observed metric | Independent result and learner screenshot |
| --- | ---: |
| Priced daily rows | 46,881,677 |
| Missing-price daily rows | 12,299,413 |
| Missing-price rows with zero sales | 12,299,413 |
| Positive-sales rows | 18,939,271 |
| Priced positive-sales rows | 18,939,271 |
| Missing-price positive-sales rows | 0 |
| Missing-price units | 0 |
| Priced units | 66,927,173 |
| Daily row coverage | 79.2173% |
| Positive-row coverage | 100.0000% |
| Unit coverage | 100.0000% |

The observed missing prices all coincide with zero recorded sales. This check does not determine why prices are absent and does not identify stockouts, launch dates, delistings or unconstrained demand. It does not convert absent prices to zero. The learner has now confirmed this coverage result. The next [fact-table step](SALES_FACT_VALIDATION.md) explicitly assigns zero value to zero units while preserving missing prices as NULL. Weekly prices still support an estimated sales-value proxy, not verified transaction revenue, profit or margin.

## Independent execution and tests

The [runner](../validation/preflight_price_coverage.py) reproduced raw calendar/sales/prices, the corresponding staging tables and core calendar in its own temporary on-disk DuckDB under the ignored repository tmp directory. It never opened the learner database. The original three file hashes matched the source registry and remained unchanged.

With DuckDB v1.5.5, two threads, memory_limit=2GB and a spill directory inside the temporary folder, setup took 77.43 seconds and the full coverage audit took 12.739 seconds. The private directory was checked for workspace containment and removed after execution. These are one-run timings and configured limits, not a runtime guarantee or measurement of total process memory. Learner connection settings are not changed. [Preflight evidence](../data/price_coverage_preflight.json) records hashes, results, settings and cleanup.

The preflight file remains an unchanged historical assistant-only record. Its original statement that learner execution was pending describes the time of that run; the separate learner acceptance record above establishes the subsequently accepted screenshot result.

Fifteen targeted cases passed: shared same-week prices with zero-sales gaps; positive unpriced sales; refusal to borrow another store's or adjacent week's price; duplicate unused price keys; NULL, zero, negative and nonfinite prices; empty keys or NULL price weeks; duplicate or missing calendar days; NULL sales units; and all-zero sales with undefined positive-row/unit coverage. Fixture controls describe each small synthetic input; coverage logic is unchanged. Positive unpriced sales yield failed coverage gates while preserving valid mechanical checks; invalid mechanics make all coverage outputs INCOMPLETE.

To reproduce from the repository root:

```powershell
python validation/preflight_price_coverage.py --duckdb "E:/DuckDB/duckdb.exe" --output "data/price_coverage_preflight.json"
```

The setup uses current local CSV paths. The learner query reads named tables and can be rerun safely. This coverage step is complete; follow [the current step](FIRST_STEP_ZH.md) for the next learner action. No joined fact table or monetary total was created by the coverage audit.
