# Stage 6: accepted descriptive price-association findings

The **descriptive price-association milestone is accepted on 2 November 2026**, following learner acceptance of SQL44–49. SQL49's fourteen rows and twelve fields match the independent report, with every row PASS. Price changes are uncommon in this window, and their associations with recorded unit changes differ across weeks and departments. The results support further investigation; they do not identify a causal response to price. The anomaly component of Stage 6 and the overall project remain incomplete. See the [SQL49 validation record](WEEK_DEPARTMENT_PRICE_CONTRASTS_VALIDATION.md) and [frozen report](../data/week_department_price_contrasts_preflight.json).

## Business question and scope

How do recorded weekly unit changes differ when a product's price at the same store rises, falls or remains unchanged, and how much do calendar timing and department composition matter to that description?

The analysis uses public historical M5 Walmart data as a personal retail learning project. It is not employer work or an IKEA operating result. The fixed scope contains **3,049 products × 10 stores = 30,490 item/store series**, twelve complete Saturday–Friday weeks from **30 January to 22 April 2016**, and **365,880 weekly positions**. The 84-day input contains 2,561,160 daily cells and 3,536,539 recorded units. Eleven adjacent comparisons per series produce **335,390 transitions**, whose current endpoints run from 6 February to 22 April. See the [input protocol](ITEM_STORE_WEEKLY_PRICES_PROTOCOL.md) and [input evidence](../data/item_store_weekly_prices_preflight.json).

Unit change means **current-week units minus previous-week units**. Every zero-sales position remains included. Previous observations are obtained over the complete sequence before excluding the first week; missing prices are never bridged or treated as unchanged. Comparisons use exact recorded cents. No individual percentage-growth division is performed when previous units are zero.

## Price variation is limited

Of 335,390 transitions, **335,374 have both price endpoints** and 16 have a missing endpoint. There are **2,060 UP**, **1,736 DOWN** and **331,578 UNCHANGED** transitions. The **3,796 price changes represent approximately 1.13% of the 335,374 price-comparable transitions**; the sixteen missing-endpoint transitions are outside that denominator and remain separately accounted for.

UP transitions involve 2,014 distinct item/store pairs and DOWN transitions involve 1,711. Those sets overlap: their counts must not be added to describe unique changed pairs. The accepted distinct count for at least one price change is **3,361 pairs**. Repeated changes by one pair are separate transitions. These are support counts, not counts of independent experiments. Sources: [variation protocol](PRICE_VARIATION_PROTOCOL.md), [SQL45 evidence](../data/price_variation_preflight.json), and [SQL46 evidence](../data/price_sales_association_preflight.json).

## Aggregate results need calendar and department context

| Price direction | Transitions | Mean unit change per transition | Median unit change |
| --- | ---: | ---: | ---: |
| UP | 2,060 | +3.194660 | 1 |
| DOWN | 1,736 | +1.667051 | 1 |
| UNCHANGED | 331,578 | −0.043842 | 0 |

Both price-change groups have positive aggregate mean unit changes. This does not establish that either raising or lowering prices increases demand. The groups differ in product/store mix, initial sales levels and calendar exposure, and the unchanged-price group is a descriptive reference. The sixteen missing-endpoint transitions remain in full-population reconciliation; their observed endpoint sums are zero previous units and 52 current units, with the positive units at priced endpoints. See the [association protocol](PRICE_SALES_ASSOCIATION_PROTOCOL.md) and [SQL46 report](../data/price_sales_association_preflight.json).

The [weekly breakdown](../data/weekly_price_sales_association_preflight.json) shows positive UP-group means in all eleven current weeks. DOWN-group means are positive in the first eight weeks and negative in the final three, starting **2, 9 and 16 April 2016**. The [department breakdown](../data/department_price_sales_association_preflight.json) also varies: FOODS_1 has negative UP and DOWN means (−0.229167 and −0.800000), while FOODS_3 has positive means for both (+3.663102 and +3.790826). Neither a pooled average nor a calendar-only or department-only summary fully describes these differences. Methods were fixed in the [weekly](WEEKLY_PRICE_SALES_ASSOCIATION_PROTOCOL.md) and [department](DEPARTMENT_PRICE_SALES_ASSOCIATION_PROTOCOL.md) protocols before their respective outcomes were calculated.

## Same-week, same-department contrasts

SQL49 compares each department's UP or DOWN group with UNCHANGED observations from the same weeks. A week is eligible only when both groups have observations. The unchanged reference is weighted by the target direction's weekly transition counts. The reported gap is the weighted target mean minus the weighted reference mean, calculated before rounding. All **3,796 target transitions have comparison support** in this dataset; none is unsupported.

| Department and direction | Target transitions | Comparable weeks | Mean-change gap | Weeks with positive gap |
| --- | ---: | ---: | ---: | ---: |
| FOODS_1 UP | 48 | 10 | −0.531370 | 8 of 10 |
| FOODS_1 DOWN | 85 | 10 | −1.376188 | 9 of 10 |
| FOODS_3 UP | 1,309 | 11 | +3.406734 | 11 of 11 |
| FOODS_3 DOWN | 545 | 11 | +3.318254 | 10 of 11 |
| HOBBIES_2 UP | 12 | 6 | +1.952318 | 6 of 6 |
| HOBBIES_2 DOWN | 4 | 4 | +0.736261 | 2 of 4 |

FOODS_1 illustrates why **frequency and weighted magnitude answer different questions**. Most comparable weeks have positive gaps, yet the transition-weighted overall gaps are negative. A week-sign count gives each supported week one vote; the mean gap incorporates transition counts and gap magnitudes. The observed discrepancy is not an arithmetic contradiction, and the week counts are not a statistical significance test.

FOODS_3 provides much more price-change support than HOBBIES_2. The latter's positive gaps rest on only twelve UP and four DOWN transitions; these small groups cannot support a broad pricing conclusion. Raw unit changes also depend on product sales levels and unit definitions: one additional unit is not economically comparable across products with different pack sizes, prices or baseline volumes.

The unchanged observations may be reused for UP and DOWN, and each direction applies different target weights. Their gaps therefore do not form a direct UP-versus-DOWN treatment comparison. A negative gap means a lower average unit change than that weighted reference; it does not itself prove an absolute sales decline, lost sales or financial loss. Each displayed mean and gap is rounded independently, so displayed subtraction can differ by 0.000001. Sources: [contrast protocol](WEEK_DEPARTMENT_PRICE_CONTRASTS_PROTOCOL.md) and [complete SQL49 evidence](../data/week_department_price_contrasts_preflight.json).

## Investigation priorities and additional data

These findings identify questions to investigate, without recommending a price change or claiming savings:

- **FOODS_1:** inspect which supported observations, transition weights and gap magnitudes explain negative aggregate gaps alongside mostly positive week signs. Check exposure and availability before attributing the pattern to pricing.
- **FOODS_3:** examine why recorded units increase in both price directions and why the same-week/department gaps remain positive. Review product/store composition and contemporaneous promotions or availability changes.
- **HOBBIES_2:** obtain more price-change observations and broader time coverage before relying on the small supported groups.

Useful additional records include promotion and display exposure, advertising/coupon activity, actual transaction prices and discounts, price-change timing within the week, store traffic or customer exposure, stock-on-hand and stockout duration, replenishment, assortment availability, product pack/unit definitions, and product cost/margin. These would help distinguish possible mechanisms and assess economic relevance. They do not exist in this completed analysis as validated explanatory variables. A future causal or pricing decision study would need a separately specified identification and evaluation design.

## Evidence, sequencing and milestone boundary

SQL45 first established price variation; SQL46 described aggregate unit changes; SQL47 examined calendar weeks; SQL48 examined departments; SQL49 compared within department/week using target-count weights. The later follow-ups were **selected after observing earlier results**. Each step's protocol was fixed before its new outcomes were computed; the complete exploratory sequence was not prospectively specified before SQL45.

Independent preflight checked all 365,880 weekly rows across twelve fields against the original sources. SQL49 additionally checked all 308 department/week/direction cells and fourteen final contrast rows, with exact rational arithmetic for contrast verification and unrounded integer signs. Earlier accepted reports, source fingerprints and scoped inputs reconciled. Learner screenshot acceptance documents execution and visible results; it remains separate from the assistant's independent source comparisons and does not certify conceptual understanding. Public evidence contains aggregates and fingerprints, without redistributing real item/store detail or screenshots.

The analyses estimate **descriptive association only**. Same-week/department grouping does not balance individual products, stores, baseline demand, promotions or availability. Adjacent comparisons overlap, and no causal price effect, elasticity, significance result, sales-loss estimate or realised business benefit is established. The accepted forecast method and final evaluation remain frozen and unchanged; this work does not retune them. See the [accepted forecasting findings](STAGE05_BASELINE_FORECAST_FINDINGS.md).

This closes the accepted price-association milestone; its findings remain unchanged. The [anomaly screening protocol](ANOMALY_SCREENING_PROTOCOL.md) fixes the separate retrospective scope and candidate rules. The learner accepted [SQL50 baseline scope](ANOMALY_BASELINE_SCOPE_VALIDATION.md) on 2 November 2026 with all 96 visible values and eight PASS statuses matching. [SQL51 classification](ANOMALY_CANDIDATES_VALIDATION.md) under those unchanged rules has passed assistant preflight; learner execution and acceptance remain pending. Candidate investigation and detection-performance evaluation, the full Stage 6 and the overall project remain incomplete.

## Portfolio-ready summary

Developed a reproducible SQL analysis of public M5 retail data covering 30,490 product-store series and 335,390 adjacent weekly comparisons. Audited exact price support, retained zero sales and missing endpoints, and examined unit changes by price direction, calendar week and department. Validated results against independent source-based Python calculations, including exact rational checks for weighted within-week/department contrasts. Documented sparse price variation, uneven subgroup support and differing calendar/product composition, with explicit limits on causal interpretation and a practical plan for additional promotion, exposure and availability data.
