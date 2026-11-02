# Price direction and adjacent weekly sales: descriptive comparison

## Purpose and status

The learner accepted all **12 rows × 12 fields** of SQL45 on **2 November 2026**, including all twelve PASS values. Its [acceptance record](../data/price_variation_learner_acceptance.json) matches the frozen report: 335,390 potential transitions, 335,374 comparable, 16 with a missing price endpoint, 2,060 price increases, 1,736 decreases and 331,578 unchanged. The 3,796 price changes involve 3,361 distinct item/store pairs.

[SQL46](../sql/46_price_sales_association.sql) describes adjacent sales changes by those price-direction groups. Its [protocol](PRICE_SALES_ASSOCIATION_PROTOCOL.md) was fixed before computing new group sales outcomes. **Assistant preflight passed; the learner accepted all five report rows and twelve fields on 2 November 2026.** Screenshot acceptance is recorded separately below. This is an initial unadjusted comparison, not a causal estimate or an elasticity model. Previously accepted forecasts and decisions remain fixed.

## Fixed observation and metrics

Retain every accepted item/store/week input for the same twelve complete weeks, **30 January–22 April 2016**. Compute previous-week price and units within each pair on the full ordered sequence before excluding the first week from transition rows. There are eleven comparisons per pair and 335,390 transitions. Current endpoints run **6 February–22 April 2016**. Exact-cent prices classify UP, DOWN and UNCHANGED only when both endpoints are present; missing endpoints form a separate group. No missing-price fill, gap bridging or positive-sales selection is used.

For each transition, **unit change = current units − previous units**. Counts and unit sums are exact integers; means and medians are signed differences measured in units per transition, displayed to six decimal places. Sales-up/down/unchanged percentages use every transition in that group as their denominator, including zero-to-zero observations, and display four decimal places. They describe the frequency of a sign of change, not percentage growth in sales. A zero baseline never causes division by zero because no individual sales-growth ratio is computed.

Each group receives one row even when empty: count and sums are zero, mean/median/percentages are NULL. TOTAL uses the full transition population. Distinct pair counts are independently deduplicated within each group and TOTAL; they cannot be added across groups. Means, medians and percentages are likewise computed from their underlying transition observations, not by unweighted averaging of group summaries. Independently rounded sign percentages can differ slightly from a displayed sum of 100%; the underlying integer sign counts must partition exactly.

Adjacent transitions share endpoints. Their previous/current unit sums are sums of comparison endpoints, not additional transactions or the twelve-week sales total. The accepted weekly controls provide a useful reconciliation: TOTAL previous units = 3,536,539 − 286,524 = **3,250,015**, current units = 3,536,539 − 291,534 = **3,245,005**, and their difference = **−5,010**. Intermediate weeks cancel in this difference. Across groups, transition counts, previous/current units and signed unit differences add to TOTAL; distinct pairs and distributional summaries do not.

## Verification and evidence

The query retains accepted weekly-input checks; independent preflight reconciles its price-direction counts to SQL45. It reads the established weekly mart and related inputs, without creating a new analysis table or rebuilding the daily fact. The [independent validator](../validation/preflight_price_sales_association.py) uses a bounded private database and original read-only CSVs, reconstructing only the relevant 84-day sales projection and twelve price weeks. The learner's persistent database is never opened, and historical forecasting computations and fixture suites are not rerun.

An original-source Python reference checks complete weekly inputs, then derives previous/current quantities, signed changes, distribution summaries and group membership independently of SQL46 output. Focused synthetic cases cover zero-to-positive, positive-to-zero and zero-to-zero changes, negative values and even-sample medians, missing endpoints, empty groups and distinct-pair overlap. Actual executed cases, precision rules, compared records, input preservation and cleanup are documented in [machine evidence](../data/price_sales_association_preflight.json). Assistant full-data verification remains separate from learner screenshot acceptance.

The completed preflight matched **365,880 weekly rows × 12 fields**, all **36,588 pooled rows × 8 fields** and **365,864 staged prices × 4 fields** against the original-source reference. SQL44's weekly fingerprint, the complete accepted SQL45 report and its inherited input-check prefix matched. All **3 focused cases** passed, and SQL46's five rows/twelve fields match the independent report exactly after declared display normalization. All seven input snapshots, source and dependency hashes, and 44 historical preflights remained unchanged; private files were removed. Report SHA256: `3847090d8a225e57ac78af9346538f1352741689198b68fd65b9ac95f5263562`. Canonical rows use compact JSON arrays plus LF, integer counts/sums, fixed-six-place mean/median strings and fixed-four-place percentage strings.

## Measured assistant report

| Price direction | Transitions | Distinct pairs | Previous units | Current units | Difference | Mean change | Median change | Sales up % | Sales down % | Sales unchanged % | Status |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| UP | 2060 | 2014 | 19448 | 26029 | 6581 | 3.194660 | 1.000000 | 64.8058 | 27.3301 | 7.8641 | PASS |
| DOWN | 1736 | 1711 | 12246 | 15140 | 2894 | 1.667051 | 1.000000 | 70.1037 | 22.0622 | 7.8341 | PASS |
| UNCHANGED | 331578 | 30490 | 3218321 | 3203784 | -14537 | -0.043842 | 0.000000 | 39.1353 | 39.4697 | 21.3950 | PASS |
| MISSING_ENDPOINT | 16 | 8 | 0 | 52 | 52 | 3.250000 | 1.000000 | 50.0000 | 0.0000 | 50.0000 | PASS |
| TOTAL | 335390 | 30490 | 3250015 | 3245005 | -5010 | -0.014938 | 0.000000 | 39.4538 | 39.3032 | 21.2430 | PASS |

In this unadjusted report, both price-up and price-down groups have positive average sales changes (**3.194660** and **1.667051** units per transition), with medians of **1.000000** and **1.000000**. The unchanged-price group has a mean of **-0.043842** and median **0.000000**. These simultaneous patterns do not identify the effect of either price direction; they motivate a later check of calendar exposure and product/store composition. The missing-endpoint group has **52** net units of change, demonstrating why missing price coverage must not be conflated with zero sales at both endpoints. The learner's accepted screenshot reproduces every value in this report.

The report's canonical fingerprint and implementation/source fingerprints are recorded in the machine evidence. Published materials contain aggregate results and fingerprints only; no real SKU identifiers, individual transitions, price vectors, screenshots or databases are included.

## Learner acceptance — 2026-11-02

The learner's DBeaver screenshot shows **all five rows and twelve fields, including five complete PASS values**. All **60 displayed values** match the frozen preflight after removing thousands separators and restoring omitted trailing zeros: means/medians retain six decimals, percentages four decimals, and counts/unit sums remain integers. The [learner acceptance record](../data/price_sales_association_learner_acceptance.json) reproduces report SHA256 `3847090d8a225e57ac78af9346538f1352741689198b68fd65b9ac95f5263562` using the ordered twelve-field row arrays, compact JSON and one LF per row.

Displayed transition counts and endpoint sums add to TOTAL, and current minus previous units equals the signed unit difference in each row. TOTAL has **335,390 transitions**, **30,490 distinct pairs**, previous units **3,250,015**, current units **3,245,005** and difference **−5,010**. Distinct-pair totals, medians and sign distributions cannot be reconstructed by summing group summaries. The MISSING_ENDPOINT row retains **16 transitions across eight pairs**, with zero previous units and **52 current units**; its 50/0/50 percentages describe sales directions, not sales growth rates.

This is screenshot-based acceptance of the aggregate report. The assistant did not open the learner's database or rerun SQL/full-data preflight for acceptance. Independent original-source medians, sign counts, distinct-pair sets, complete input checks and focused tests remain the separate historical assistant evidence above. Frozen SQL, validator, protocol and preflight remain unchanged; no screenshot or individual pair/transition record is published.

## Interpretation and next step

Compare sample coverage, mean, median and sign frequencies together. The unchanged-price group is a descriptive reference, not a randomized or matched causal control. Different groups can contain different products, stores and weeks, with different sales levels and concurrent calendar or availability conditions. Price changes can themselves respond to sales conditions. Overlapping transitions and repeated pairs are not independent experiments. Neither a group average nor its difference from another group establishes a price effect, documented promotion lift, profit, stockout or elasticity.

The accepted pattern can now guide an appropriate calendar/category breakdown or another declared descriptive robustness check; such later choices must not be portrayed as prespecified by this initial report. See [the Chinese current-step guide](FIRST_STEP_ZH.md) for the next single action.
