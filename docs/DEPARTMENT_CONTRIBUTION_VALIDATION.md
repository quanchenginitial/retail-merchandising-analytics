# Department contribution: hierarchy and denominator checks

28 October 2026. [19_department_contribution.sql](../sql/19_department_contribution.sql) extends the learner-accepted category analysis to seven source departments. This is a read-only query; assistant preflight and learner acceptance remain separate. Department results are currently awaiting learner execution.

## Business question and scope

Where within each category does the observed contribution come from? Retain **2016-01-26–2016-04-24 inclusive**, all 10 stores and all 3,049 source products, including zero-sales products. The date window contains 2,744,100 daily observations and excludes the final forecast holdout. The category baseline is 3,767,196 units and USD 11,846,945.98 estimated value, as accepted from [SQL18 screenshot evidence](../data/category_contribution_learner_acceptance.json).

FOODS has FOODS_1, FOODS_2 and FOODS_3; HOBBIES has HOBBIES_1 and HOBBIES_2; HOUSEHOLD has HOUSEHOLD_1 and HOUSEHOLD_2. These are anonymous source codes. Do not infer that any department is a specific food type, hobby or household product group. Product counts refer to distinct source SKU IDs, not confirmed active listings, physical stock or consumer-equivalent units.

The output has seven department rows plus TOTAL and nine columns. Global unit share uses all-window units; global value share uses all-window estimated value. **Within-category value share uses only the department's parent category value.** TOTAL has no parent category, so its within-category percentage is NULL. Any zero monetary/unit denominator also produces NULL. Rounded shares need not sum to exactly 100.0000; acceptance compares exact amounts and independently calculated ratios.

Order category groups by category estimated value descending, then departments by their value descending, with codes breaking ties; TOTAL comes last. This is contribution ordering, not a profitability or recommendation ranking. Weekly-price-based value is still a proxy; neither margins, causal effects nor availability are established.

## Query validation and limits

Reuse the accepted SQL18 window, per-series 90-day bitmap/count guards, missing-value/price/flag/value-policy checks, key coverage and no-amplification controls. Add the seven valid department/category pairs as a source contract and require all seven departments. Aggregate facts by item/store before joining small product/store dimensions; count distinct item IDs within each department so cross-store products are not multiplied and zero-sales SKUs remain represented.

Group joined series independently at category and department levels. Summing department counts/units/value back to category must match the category aggregates. This in-query check proves hierarchy aggregation consistency; both sides use the same accepted joined input, so it is not an independent raw-source audit. Guard failures stop the query instead of returning a partial report. PASS means data and aggregation checks passed, not that a department performed well.

The query depends on previously accepted SQL12/13/17 mappings and source values. It does not re-certify every raw-to-core assignment or rejoin source prices for each fact row. Rerun upstream acceptance after modifying those inputs. The independent preflight below is a separate check of the actual source snapshot.

## Independent preflight

The [runner](../validation/preflight_department_contribution.py) builds prerequisites in its own temporary on-disk database under ignored tmp, with two threads and a 2GB DuckDB memory limit. It never opens the learner database. The three original CSV hashes are checked before and after execution; database/spills are removed after verification. Recorded closed database size is not peak disk or memory use.

The reference uses staging sales/calendar/prices and product/department/category mappings projected from raw sales. It independently sums integer price cents times integer units, not the fact's stored date, value or flag. Python Decimal verifies global and within-category shares, counts, exact amounts and deterministic order. Reference department totals are then rolled back up to the **learner-accepted SQL18 category counts, units and amounts**, and the TOTAL row is also compared. The acceptance-record hash is retained for traceability.

Fourteen targeted cases cover hand-calculated global versus parent denominators, cross-store SKU de-duplication, a completely zero-sales SKU, missing-price zeros, inclusive/excluded date boundaries, all-zero denominators, one zero-valued category alongside positive categories, wrong/unknown/NULL/missing department mappings, duplicate products, orphan items, duplicate/missing dates, positive units without a price and incorrect amounts. In particular, a zero-valued category has 0% global value share when the overall total is positive but NULL within-category share; TOTAL within-category share is always NULL.

## Assistant observations — awaiting learner confirmation

All eight report rows passed and matched the independent department reference. Department rollups matched all learner-accepted SQL18 category SKU counts, units and exact amounts; TOTAL remains 3,049 products, 3,767,196 units and USD 11,846,945.98. All 14 targeted cases passed. Report execution took 2.955 seconds after prerequisites were rebuilt in this environment; this is not a performance guarantee. Source hashes remained unchanged and the private database was removed.

| Category | Department | SKUs | Units | Global unit % | Estimated value USD | Global value % | Within-category value % |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| FOODS | FOODS_3 | 823 | 1722888 | 45.7340 | 4078467.22 | 34.4263 | 60.9198 |
| FOODS | FOODS_2 | 398 | 511688 | 13.5827 | 1836210.56 | 15.4994 | 27.4273 |
| FOODS | FOODS_1 | 216 | 276769 | 7.3468 | 780139.28 | 6.5852 | 11.6529 |
| HOUSEHOLD | HOUSEHOLD_1 | 532 | 726805 | 19.2930 | 2751516.58 | 23.2255 | 76.2764 |
| HOUSEHOLD | HOUSEHOLD_2 | 515 | 178520 | 4.7388 | 855780.92 | 7.2236 | 23.7236 |
| HOBBIES | HOBBIES_1 | 416 | 317010 | 8.4150 | 1474142.70 | 12.4432 | 95.4242 |
| HOBBIES | HOBBIES_2 | 149 | 33516 | 0.8897 | 70688.72 | 0.5967 | 4.5758 |
| TOTAL | TOTAL | 3049 | 3767196 | 100.0000 | 11846945.98 | 100.0000 | NULL |

The percentages above describe different denominators even on the same row. For example, the assistant observation for FOODS_3 is 34.4263% of overall estimated value and 60.9198% of FOODS value. This is not a per-SKU productivity or profitability comparison and is not yet a learner-accepted department finding.

See [machine-readable preflight](../data/department_contribution_preflight.json) and [current learner step](FIRST_STEP_ZH.md). Department findings become accepted analysis only after the learner result is reviewed. No ABC/XYZ labels, forecast errors, inventory diagnosis or assortment intervention is delivered by this step.
