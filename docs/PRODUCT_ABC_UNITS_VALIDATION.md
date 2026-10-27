# Product ABC by units: baseline table and validation

28 October 2026. [21_build_product_abc_units.sql](../sql/21_build_product_abc_units.sql) turns the accepted concentration ranking into mutually exclusive product labels. Assistant preflight is separate from learner execution, which remains pending. This step creates an 80%/95% baseline; threshold sensitivity is subsequent work.

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

## Assistant baseline observations — awaiting learner confirmation

All 3,049 stored product rows matched all nine independently derived fields. The five summary rows passed; A matched the accepted 80% prefix, A+B the 95% prefix, and positive/zero/all-product totals matched SQL20. Twenty-one targeted cases passed. Creation took 1.465 seconds and validation 1.040 seconds after rebuilding prerequisites in this environment. Source hashes were unchanged and temporary databases were removed.

| Class | SKUs | SKU share % | Units | Unit share % | First rank | Last rank | Status |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| A | 1135 | 37.2253 | 3013899 | 80.0038 | 1 | 1135 | PASS |
| B | 968 | 31.7481 | 565178 | 15.0026 | 1136 | 2103 | PASS |
| C | 942 | 30.8954 | 188119 | 4.9936 | 2104 | 3045 | PASS |
| ZERO_SALES | 4 | 0.1312 | 0 | 0.0000 | NULL | NULL | PASS |
| TOTAL | 3049 | 100.0000 | 3767196 | 100.0000 | 1 | 3045 | PASS |

These are assistant baseline observations, not learner acceptance or evidence that 80/95 is the best operating policy. A contains 37.2253% of source products and 80.0038% of units. B and C are the non-overlapping remainder of positive products; zero-sales items stay separate.

After the full-source run, one non-executable comment was clarified from “exact percentages” to “rounded displayed percentages.” The preflight record retains the original execution hash and delivered-script hash, verifies unchanged executable SQL, and records a successful rerun of all 21 fixtures on the delivered script.

See [machine-readable preflight](../data/product_abc_units_preflight.json) and [current learner instructions](FIRST_STEP_ZH.md). After baseline acceptance, compare reasonable alternative thresholds and boundary memberships before considering the ABC module complete. XYZ, forecasts, profit and inventory policy remain outside this step.
