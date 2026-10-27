# Department contribution: hierarchy and denominator checks

28 October 2026. The learner screenshot confirms all eight result rows from [19_department_contribution.sql](../sql/19_department_contribution.sql) have check_status=PASS and numerically match the independent preflight results. The seven-department report and TOTAL row are accepted for the fixed window below. The [screenshot transcription](../data/department_contribution_learner_acceptance.json) records learner execution separately from assistant preflight; the assistant did not directly open the learner database.

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

## Accepted learner results and independent preflight

The learner's eight displayed rows match the table below, including the expected NULL within-category share on TOTAL. Money is normalized to two decimal places and percentages to four; padding trailing zeros changes formatting only. Independently, the assistant preflight matched all eight rows to its department reference and rolled them up to the learner-accepted SQL18 category SKU counts, units and exact amounts. TOTAL remains 3,049 products, 3,767,196 units and USD 11,846,945.98. All 14 targeted cases passed. Preflight execution took 2.955 seconds after rebuilding prerequisites; this is not a performance guarantee. Source hashes remained unchanged and the private database was removed. These runtime and hash observations belong to the assistant preflight, not the learner screenshot.

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

The percentages above describe different denominators even on the same row. For example, the accepted FOODS_3 result is 34.4263% of overall estimated value and 60.9198% of FOODS value. TOTAL has no parent category, so its NULL within-category share is intentional and is not a failed check.

## Business reading of the accepted output

The following is the assistant's interpretation of the accepted results for this fixed historical window:

- FOODS_3 accounts for 60.9198% of estimated FOODS value and 34.4263% of the overall value proxy. It is the largest value contributor within FOODS, with 823 source SKUs compared with 398 in FOODS_2 and 216 in FOODS_1.
- HOUSEHOLD_1 accounts for 76.2764% of estimated HOUSEHOLD value. It contains 532 source SKUs, compared with 515 in HOUSEHOLD_2.
- HOBBIES_1 accounts for 95.4242% of estimated HOBBIES value. It contains 416 source SKUs, compared with 149 in HOBBIES_2.

These leading departments also contain more recorded SKU IDs than their siblings. Their absolute contributions combine assortment size, product mix, recorded quantities and weekly prices; this report does not isolate the effect of any one factor. Higher contribution does not establish higher per-SKU productivity, profitability or a causal benefit from carrying more SKUs. The source codes do not reveal the departments' specific product types, and the counts do not establish active inventory.

See [learner acceptance evidence](../data/department_contribution_learner_acceptance.json), [machine-readable preflight](../data/department_contribution_preflight.json) and [current learner step](FIRST_STEP_ZH.md). Learner execution and the displayed department results are now accepted. No ABC/XYZ labels, forecast errors, inventory diagnosis or assortment intervention is delivered by this step.
