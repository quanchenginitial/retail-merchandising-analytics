# Weekly price-direction and sales-change breakdown

## Purpose and evidence boundary

The learner accepted SQL46 on **2 November 2026**, with all five rows and twelve fields visible and PASS. The [acceptance record](../data/price_sales_association_learner_acceptance.json) matches its frozen report. In that aggregate description, both price-up and price-down groups have positive mean unit changes, while the unchanged group has a slightly negative mean. These are associations, not price effects.

[SQL47](../sql/47_weekly_price_sales_association.sql) splits the same observations by current endpoint week to examine timing concentration and whether the aggregate pattern recurs. This follow-up was chosen after seeing the accepted SQL46 result; it was not prespecified as part of the earlier report. Its [own protocol](WEEKLY_PRICE_SALES_ASSOCIATION_PROTOCOL.md) was fixed before new weekly sales outcomes were computed. **Assistant preflight has passed; learner SQL47 execution and acceptance remain pending.**

## Fixed scope and calculation

Use the same 365,880 item/store/week inputs, 30,490 pairs and twelve complete weeks **30 January–22 April 2016**. Derive all eleven immediate transitions within each pair, retaining zero-sales and missing-price observations. The first week supplies the initial previous endpoint. Current endpoint weeks **11602–11612**, **6 February–22 April 2016**, form eleven report rows. No new window, price threshold or positive-sales filter is introduced.

For each transition, signed unit change remains **current units minus previous units**. Price UP/DOWN/UNCHANGED uses exact cents only when both prices exist; MISSING_ENDPOINT is separate, without carrying forward or bridging gaps. Each of the eleven weeks has four internal price-direction groups, including empty groups. Thus **44 group cells** retain the full population even though the user-facing table pivots counts and means into eleven rows.

The report shows the three priced groups' counts and means side by side, plus missing-endpoint count, total count and the total signed unit difference including every group. Means use all transitions in that week/direction, including zero-to-zero changes, and display six decimal places under the established rounding rule. An empty group's count is zero and mean is NULL. Previous zero units never cause exclusion because no percentage sales-growth ratio is calculated.

Counts and signed differences add across weeks. Means must be reconstructed from underlying difference sums and transition counts, not a simple average of weekly means. Rounding printed means can introduce small reconstruction differences, so formal reconciliation uses exact internal integer sums. Distinct-pair counts, medians and sign frequencies are not newly displayed; the accepted SQL46 results for those metrics remain unchanged.

## Independent verification

The self-contained query retains the accepted input checks, full sequence and missing-value behavior. A [bounded validator](../validation/preflight_weekly_price_sales_association.py) reconstructs only the relevant original 84-day sales projection and twelve price weeks in a private temporary database. It never opens the learner's persistent database or reruns forecasting or historical test suites.

The independent original-source reference derives weekly units and exact prices, then every adjacent comparison and all weekly group cells. It compares the entire new report, reconciles weekly price-direction coverage to accepted SQL45, and reconciles the full-window outcome to accepted SQL46. Those checks retain missing-price sales changes and zeros, rather than assuming the small missing group has no units. The historical weekly input fingerprint and original source hashes identify unchanged inputs; complete record comparisons, executed focused cases, preservation and cleanup are recorded in [machine evidence](../data/weekly_price_sales_association_preflight.json).

The completed run matched **365,880 weekly input rows × 12 fields**, **36,588 pooled rows × 8 fields** and **365,864 staged prices × 4 fields** to original-source references. It also matched every **44 internal group cell × 14 fields** and the **11×12 displayed report**. The unchanged SQL45 12×12 and SQL46 5×12 reports remain identical to their accepted evidence. All **4 focused cases** passed, including a guard check that an empty calendar raises an explicit error instead of silently producing no rows. All seven input snapshots, source/dependency hashes and 45 historical preflights stayed unchanged; private files were removed. Internal-cell SHA256: `8eb073904d9418e2877cf398b93403532cba5d01b5cc16ba9794ed81a86785a9`. Displayed-report SHA256: `106928695f37931fab9c6ab6f153b736ccdf0bbc50cf0b6d563dbc373774ab7a`. Canonical hashes use ordered compact JSON arrays plus LF, integers for counts/sums and fixed-six-place strings for displayed means (or NULL for empty groups).

## Measured assistant report

| Week | Current week start | Up count | Up mean change | Down count | Down mean change | Unchanged count | Unchanged mean change | Missing endpoints | Total count | Total unit difference | Status |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 11602 | 2016-02-06 | 218 | 2.302752 | 418 | 1.320574 | 29846 | 0.429572 | 8 | 30490 | 13875 | PASS |
| 11603 | 2016-02-13 | 138 | 3.869565 | 177 | 3.180791 | 30167 | -0.241290 | 8 | 30490 | -6130 | PASS |
| 11604 | 2016-02-20 | 69 | 1.739130 | 101 | 2.990099 | 30320 | -0.630673 | 0 | 30490 | -18700 | PASS |
| 11605 | 2016-02-27 | 207 | 4.396135 | 164 | 2.530488 | 30119 | 0.329858 | 0 | 30490 | 11260 | PASS |
| 11606 | 2016-03-05 | 576 | 4.326389 | 265 | 2.143396 | 29649 | 0.307464 | 0 | 30490 | 12176 | PASS |
| 11607 | 2016-03-12 | 236 | 1.186441 | 198 | 1.414141 | 30056 | -0.233697 | 0 | 30490 | -6464 | PASS |
| 11608 | 2016-03-19 | 213 | 1.769953 | 83 | 2.734940 | 30194 | -0.560178 | 0 | 30490 | -16310 | PASS |
| 11609 | 2016-03-26 | 123 | 1.260163 | 119 | 1.991597 | 30248 | 0.035176 | 0 | 30490 | 1456 | PASS |
| 11610 | 2016-04-02 | 108 | 5.740741 | 84 | -2.392857 | 30298 | 0.876361 | 0 | 30490 | 26971 | PASS |
| 11611 | 2016-04-09 | 92 | 2.271739 | 64 | -0.203125 | 30334 | -0.120690 | 0 | 30490 | -3465 | PASS |
| 11612 | 2016-04-16 | 80 | 4.775000 | 63 | -0.571429 | 30347 | -0.659868 | 0 | 30490 | -19679 | PASS |

All eleven rows and twelve fields match the independent reference. Published evidence contains only aggregate reports and fingerprints, not real SKU identifiers, individual transitions, raw price vectors, screenshots or databases. Learner reproduction of this report remains pending.

## Interpretation and next learner step

Read each mean alongside its sample count, then compare the same price group across weeks. Weekly means based on very different counts should not receive equal weight in the aggregate. A concentrated pattern motivates investigation of timing and composition; it does not prove that calendar effects caused the earlier aggregate association. A consistent pattern also does not establish a price effect.

Same-week price groups can still contain different products, stores, baseline sales and availability conditions. Adjacent comparisons share endpoints and repeated pairs are not independent experiments. No matched control, causal estimate, elasticity, promotion lift, statistical significance or inventory benefit is produced. This step adds time context to the accepted description and does not alter forecast choices or previously accepted results.

Run the full SQL47 query in a new DBeaver editor connected to **retail_merchandising**, then return all **eleven rows and twelve columns**, including check_status. See [the Chinese current-step guide](FIRST_STEP_ZH.md).
