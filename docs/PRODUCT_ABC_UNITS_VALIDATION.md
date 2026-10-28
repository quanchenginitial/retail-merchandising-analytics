# Product ABC by units: baseline table and validation

28 October 2026. The learner's DBeaver screenshot confirms all five summary rows from [21_build_product_abc_units.sql](../sql/21_build_product_abc_units.sql) have `check_status=PASS` and numerically match the independent assistant preflight. The 80%/95% units-based ABC baseline is accepted; the subsequent [threshold comparison](ABC_THRESHOLD_SENSITIVITY_VALIDATION.md) has also been learner-accepted. The [learner acceptance record](../data/product_abc_units_learner_acceptance.json) transcribes the screenshot separately from assistant preflight evidence. No direct read of the learner database was performed.

## Business purpose and frozen scope

Persist one label per source product so later variability analysis can join by item_id without reconstructing label boundaries in each chart. The snapshot uses **2016-01-26–2016-04-24 inclusive**, pools all 10 stores and all categories into one product ranking, and retains all 3,049 source SKUs. It is units-based ABC, not monetary/profit ABC, store-specific ABC or a volatility class.

Positive SKU totals are sorted by units descending and item_id ascending. The identifier tie-break is deterministic but may separate equally selling products. It is not evidence that those products have different economic value.

## Mutually exclusive boundary rule

- ZERO_SALES: units=0, with NULL sku_rank and cumulative_units.
- A: the current SKU's prior cumulative units are strictly below 80% of total units.
- B: otherwise, prior cumulative units are strictly below 95%.
- C: all remaining positive-unit products.

Prior cumulative units means cumulative_units minus the current SKU's units. Membership uses exact integer comparisons, not displayed rounded percentages. The SKU that first reaches or crosses a threshold stays in the earlier band. A therefore reproduces the accepted REACH_80_PCT prefix; A+B reproduces REACH_95_PCT. If a single SKU contributes over 95%, it is A, B is empty, and remaining positives are C. With all-zero units, all source items are ZERO_SALES and all unit-share percentages are NULL.

A/B/C/ZERO_SALES partition the product universe and their counts/units can be summed to TOTAL. The report always retains five rows, including empty classes (count/units 0, rank bounds NULL). TOTAL rank bounds refer only to positive-unit ranks; zero-sales products have no rank. Thresholds are project conventions, not universal laws or demonstrated optimal operating policies. Labels alone do not justify inventory, removal or service decisions.

## Persisted table and validation

`mart.m5_product_abc_90d` has nine fields: item_id, dept_id and cat_id VARCHAR; window_start and window_end DATE; units and cumulative_units HUGEINT; sku_rank BIGINT; abc_class VARCHAR. The fixed dates make the analysis window explicit in each row. Key uniqueness is validated; no physical PRIMARY KEY is declared. This is a saved snapshot, not an automatic refresh.

Creation consumes the accepted 90-day unit/key/mapping guards in its actual abc_class output. It starts assignments from a single health row and LEFT JOINs products, so even an entirely empty selected source triggers rejection rather than creating a misleading empty table. Source data remain unchanged, and CREATE TABLE does not overwrite an existing snapshot.

The final query independently recomputes expected product totals, hierarchy, rank, cumulative units and labels from the current accepted daily fact. It checks all nine column names/types/order, row count and unique item keys. Bidirectional EXCEPT ALL compares every stored field and row multiplicity, including intentional NULLs. This detects wrong labels, stale values, altered dates/mappings, duplicate/missing products and changes that preserve overall totals. The summary reports PASS only if these checks pass. Its recalculation uses the same documented classification formula; the separate source/Python preflight below independently tests that formula and input path.

If the snapshot already exists, rerun only the section below `-- VALIDATION:`. A failed comparison means the current snapshot is not accepted; investigate the output before rebuilding. Successful table creation alone is not acceptance.

## Independent preflight and targeted tests

The [runner](../validation/preflight_product_abc_units.py) rebuilds prerequisites and the ABC table in its own temporary on-disk database under ignored tmp, with two threads and a 2GB DuckDB memory limit. It never opens the learner database. Original CSV hashes must match the source registry and remain unchanged; temporary databases/spills are removed after verification. Closed database size does not measure peak resources.

An independent reference aggregates staging sales using staging calendar and raw product hierarchy. Python then finds minimal 80%/95% prefix endpoints and labels ranks by those intervals, rather than copying the SQL prior-cumulative expression. Every one of the nine stored fields is compared for every source SKU. The five summary rows must match Python totals/percentages/rank bounds, and A, A+B, positive, zero and all-product totals must match the **learner-accepted SQL20** concentration record. No SKU-level extract is published.

Twenty-one targeted cases cover exact thresholds, overshoot, one SKU crossing both thresholds, equal-unit ties, all-zero and one-positive cases, date boundaries, wrong labels/ranks/cumulative values/NULL handling/windows/hierarchy, duplicate/missing rows, same-total redistribution and altered schema types. Invalid-input cases include empty source, negative units, duplicate/missing dates and duplicate product mappings; each build rejection also confirms that no ABC table was created.

## Accepted learner baseline and independent preflight

The learner screenshot reproduces all five rows below, including all PASS statuses, contiguous positive rank ranges and intentional NULL rank bounds for ZERO_SALES. Thousands separators are omitted and percentage values are padded to four decimal places in the machine-readable acceptance record; this normalization preserves the displayed numeric values.

Separately, the assistant preflight compared all 3,049 stored product rows with all nine independently derived fields and found no differences. Its five summary rows passed; A matched the accepted 80% prefix, A+B the 95% prefix, and positive/zero/all-product totals matched SQL20. Twenty-one targeted cases passed. Creation took 1.465 seconds and validation 1.040 seconds after rebuilding prerequisites in the assistant's environment. Source hashes were unchanged and temporary databases were removed. These independent checks and timings are assistant evidence, not measurements established by the learner screenshot.

| Class | SKUs | SKU share % | Units | Unit share % | First rank | Last rank | Status |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| A | 1135 | 37.2253 | 3013899 | 80.0038 | 1 | 1135 | PASS |
| B | 968 | 31.7481 | 565178 | 15.0026 | 1136 | 2103 | PASS |
| C | 942 | 30.8954 | 188119 | 4.9936 | 2104 | 3045 | PASS |
| ZERO_SALES | 4 | 0.1312 | 0 | 0.0000 | NULL | NULL | PASS |
| TOTAL | 3049 | 100.0000 | 3767196 | 100.0000 | 1 | 3045 | PASS |

## Business reading of the accepted baseline

The following interpretation is supplied by the assistant. A contains 1,135 products, or 37.2253% of source SKUs, and accounts for 80.0038% of recorded units. B adds 968 products and 15.0026% of units; C contains the remaining 942 positive-sales products and 4.9936% of units. Unlike the overlapping concentration rows in SQL20, these classes are mutually exclusive. Adding A and B reproduces the 2,103-product prefix that reaches 95.0064% of units.

The four zero-sales products remain a separate class with no positive-sales rank. TOTAL's ranks 1 through 3,045 therefore cover positive-sales products, while its count of 3,049 includes the four zero-sales products. Zero recorded units alone do not establish delisting or stockout.

These labels express global unit contribution across all 10 stores and categories in the fixed window. Pieces of different products are not economically equivalent, so A does not mean the most profitable products, nor does C imply low service importance or an assortment-removal decision. The accepted 80/95 baseline is a documented classification convention, not evidence that these thresholds are optimal. The subsequent five-scenario threshold comparison is now accepted. This establishes sensitivity to those specified boundaries, not stability across time or optimal policy.

After the full-source run, one non-executable comment was clarified from “exact percentages” to “rounded displayed percentages.” The preflight record retains the original execution hash and delivered-script hash, verifies unchanged executable SQL, and records a successful rerun of all 21 fixtures on the delivered script.

See the [learner acceptance record](../data/product_abc_units_learner_acceptance.json), [machine-readable preflight](../data/product_abc_units_preflight.json) and [current learner instructions](FIRST_STEP_ZH.md). Baseline execution and the subsequent five-scenario threshold comparison are accepted; see the linked sensitivity record for boundary memberships. Temporal stability has not been evaluated. XYZ, forecasts, profit and inventory policy remain outside this step.
