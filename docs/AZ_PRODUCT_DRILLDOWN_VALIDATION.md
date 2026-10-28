# Complete A × Z product drilldown

29 October 2026. SQL28's seventeen contribution rows have been accepted from the learner's screenshot. [SQL29](../sql/29_az_product_drilldown.sql) exposes the complete A × Z cohort for local inspection. It is a single read-only query. Assistant preflight passed; learner execution of SQL29 remains pending and is separate evidence.

## Purpose and scope

Inspect recorded units, weekly variability and intermittent-sales indicators underlying the accepted combination. A × Z denotes the cumulative-volume A group together with high relative weekly variability. This does not establish a stockout, cause, forecast error or replenishment quantity.

The cell contains fifteen products and contributes 20,626 of 3,767,196 units (0.5475%) in the ABC window, and 18,907 of 3,536,539 units (0.5346%) in the XYZ window. A × X carries most recorded volume in this dataset. The drilldown reviews one complete cell; it is not an optimized operating priority or a representative sample of all products.

Retain both frozen windows: ABC 2016-01-26..2016-04-24 (90 days), and XYZ 2016-01-30..2016-04-22 (84 days, twelve complete Saturday–Friday weeks). Both pool the same ten stores. Their nested-window unit difference is not a change between successive periods.

## Ten-column output contract

| Column | Contract |
| --- | --- |
| segment | A × Z |
| item_id | Unique product identifier; local result only |
| units_90d | Accepted combined snapshot's 90-day units |
| units_84d | Same product's 84-day units |
| cv_weekly | Population standard deviation / mean of all twelve weekly observations, including zero weeks; six display decimals |
| zero_sales_weeks | Number of zero-unit weeks after pooling stores |
| mean_positive_gap_weeks | Mean difference of adjacent positive-week indices; NULL with fewer than two positive weeks; six display decimals |
| abc_window | 2016-01-26..2016-04-24 |
| xyz_window | 2016-01-30..2016-04-22 |
| check_status | PASS after validation; EMPTY only for a valid empty cohort |

Return every accepted A × Z product. Order by units_90d DESC, item_id ASC; do not apply Top-N, sample or append TOTAL. Select accepted exact labels rather than rounded displayed CV. Values just above 1 can display as 1.000000 while correctly remaining Z. No stored metric or label changes.

Positive-week indices 2, 5, 6 imply gaps 3 and 1 and a mean of 2 weeks. This is not the number of zero weeks, 12 / positive_weeks, lead time or a prescription for ordering frequency. Leading and trailing gaps to unobserved positive weeks are not measured. The short window and pooling across stores constrain interpretation.

## Validation path and empty outputs

Reuse SQL27's validation prefix: check weekly completeness and metrics, exact XYZ labels, ABC ranks and cumulative labels, schemas, windows, unique equal product sets, mappings, every copied combined field, nonnegative six-day bridges and source margins. Copied floating fields must match the accepted inputs exactly; recomputation retains its declared numerical tolerance. Source-to-daily equality relies on accepted SQL21/23 provenance rather than rescanning the large daily fact in the learner query.

Filter combined_actual to A and Z. Check distinct product count and both integer totals against combined_expected. Start the output from a singleton health/total row, then left join the cohort: an invalid source cannot silently return zero rows and bypass the guard. Source failure raises an error. A valid empty cohort emits one EMPTY sentinel with item_id and every product metric NULL, while retaining segment and dates. It is not a fictitious zero-sales product. The current accepted dataset expects fifteen PASS rows.

## Independent evidence and publication

The [preflight runner](../validation/preflight_az_product_drilldown.py) and [machine-readable evidence](../data/az_product_drilldown_preflight.json) record independent verification. Original sales/calendar CSVs are read-only inputs. A private temporary database reconstructs the required 90-day slice and executes prerequisites before SQL29; the learner's persistent database is never opened.

Independently derived totals, weekly vectors, ABC crossing-prefix labels and exact XYZ labels provide the reference. Compare the complete cohort and every output column, deterministic order, displayed rounding, NULL behavior and both windows. Reconcile fifteen products and 20,626 / 18,907 units to the accepted SQL28 cell. Preserve before/after fingerprints of five input tables, source hashes and historical preflight records.

Real product identifiers, product-level rows, CSV extracts and screenshots are excluded from public evidence. Public records retain aggregate controls, test results and SHA-256 fingerprints. Future learner screenshot acceptance remains distinct from this assistant-run preflight.

## Preflight results

All 3,049 products across 22 combined fields matched the independent reference. All fifteen A × Z result rows across ten columns matched, including order and both windows. The cohort's totals matched the accepted SQL28 cell: 20,626 units over 90 days and 18,907 over 84 days, with 1,719 units in the excluded six days.

| Aggregate observation | Result |
| --- | ---: |
| Displayed weekly CV range | 1.000271–1.601705 |
| Zero-sales weeks per product | 0–6 |
| Zero-unit product/week observations across this cohort | 49 |
| Displayed mean positive-week gap range | 1.000000–2.200000 weeks |
| Products with NULL positive-week gap | 0 |

These are cohort aggregates, not a product-level extract. The 49 observations are product/week cells, not 49 distinct products or calendar weeks. At least one product has no zero-sales weeks despite belonging to Z: relative variability is not synonymous with intermittent sales. Actual causal explanations require a closer look at time patterns and further evidence.

All eighteen targeted cases passed. Six valid cases cover NULL/non-NULL gaps, tied units with reversed source order, valid empty cohorts from positive and all-zero sources, exact Z classification despite a displayed CV of 1.000000, and allowed source-metric numerical variation. Twelve rejection cases cover invalid empty sources, an empty combined snapshot, duplicate products, deletion of the whole cohort, incorrect labels, copied floating-value drift, wrong windows/schema, incorrect source ABC ranks or XYZ labels, missing weekly observations and nonfinite metrics. The real cohort has no tied 90-day unit values; tie behavior is established by the synthetic fixture.

All five input snapshots, both original CSV hashes and all 27 historical preflight records remained unchanged; temporary databases were removed. DuckDB v1.5.5 used two threads and a 2GB memory limit. The SQL29 CLI query took 0.385 seconds in this run, excluding Python reference comparison and hashing; this is not a performance guarantee. Ordered membership and canonical detail SHA-256 hashes match the independent reference and are recorded in the public aggregate evidence.
