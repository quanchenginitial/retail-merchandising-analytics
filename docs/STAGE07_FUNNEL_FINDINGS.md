# Retailrocket seven day shopping path findings

Accepted through SQL77 on 13 November 2026 (Australia/Sydney).

The defined browsing-to-cart-to-transaction analysis is complete through its exploratory category follow-up. It provides a reproducible shortlist for investigation: category 1613 has a comparatively low recorded cart-to-transaction rate, but the available data do not establish a checkout fault or an inventory cause. Basket analysis, behavioural RF segmentation and Power BI remain separate work.

## Business question and measurement

The question is where observed shopping paths fail to reach a later recorded stage, and which categories warrant closer examination. The log contains 2,756,101 events across 139 represented UTC dates, from 3 May to 18 September 2015. The 22,457 transaction events contain 17,672 distinct transaction IDs; event rows are therefore not interchangeable with orders. See the [accepted event overview](RETAILROCKET_EVENT_OVERVIEW_VALIDATION.md).

The funnel counts distinct visitor-item pairs. It anchors each pair to its first observed view and requires a strictly later cart followed by a strictly later transaction within the same inclusive seven-day window. Same-millisecond events do not establish stage order. Of 2,132,127 viewed pairs, 89,817 are excluded because their first view leaves less than seven days before the log endpoint. The remaining 2,042,310 are eligible. First observed does not mean first ever, and the endpoint does not establish uninterrupted event capture. See the [seven-day definition and acceptance](RETAILROCKET_7DAY_VISITOR_ITEM_FUNNEL_VALIDATION.md).

## Global path and category coverage

| Measure | Accepted result | Denominator |
| --- | ---: | --- |
| Qualified cart pairs | 43,147 | 2,042,310 eligible pairs |
| Cart rate | 2.1127% | Eligible pairs |
| Qualified transaction pairs | 15,520 | The same eligible pairs |
| Full-path transaction rate | 0.7599% | Eligible pairs |
| Cart-to-transaction rate | 35.9701% | Qualified cart pairs |

These rates describe the recorded path, not unique people, all purchases or a verified abandonment rate. Missing a qualifying stage can reflect the chosen horizon or event coverage as well as behaviour.

First-view category history maps 1,527,206 eligible pairs (74.7784%) to the supplied category reference. Another 304,405 eligible pairs have first views before their item's first category observation, and 210,699 eligible pairs have no category history. These groups remain in the totals rather than being imputed or dropped. Zero unknown reference matches in this cohort does not remove the 167 unmatched category observations found elsewhere in the source. See the [coverage audit](RETAILROCKET_FIRST_VIEW_CATEGORY_COVERAGE_VALIDATION.md).

## Category 1613 as an investigation candidate

Among the ten categories selected by eligible-pair volume, anonymous category 1613 has 25,105 eligible pairs, 483 qualified carts and 76 qualified transactions. Its cart-to-transaction rate is 15.7350%, compared with 35.9701% for the overall cohort. The overall cohort is descriptive context, not a matched control. The category was selected after inspecting these results, so subsequent comparisons are exploratory. See the [category comparison](RETAILROCKET_CATEGORY_7DAY_FUNNEL_VALIDATION.md).

The early and late first-view cohorts, split at 1 July 2015 UTC, have rates of 12.3134% (33/268) and 20.0000% (43/215) for this category. These unequal-duration cohorts preserve each pair's original seven-day window; they do not identify a trend, seasonality or a causal improvement. See the [time comparison](RETAILROCKET_CATEGORY_FUNNEL_TIME_COHORTS_VALIDATION.md).

Of 1,161 represented items, 151 have a qualifying cart and 98 of those have no qualifying transaction in this cohort. Thirty-five items in the 5–19 cart band account for 54.4513% of carts. The pooled transaction/cart rate is 15.7350%, while the equal-item mean among cart-positive items is 14.6612%. This distinction makes weighting explicit; sparse item counts do not justify labelling products as failures. See the [item concentration analysis](RETAILROCKET_CATEGORY_ITEM_CART_CONCENTRATION_VALIDATION.md).

## Availability at first view

Both category and availability are fixed using their latest supplied observations at or before the first view. Later updates do not reassign a pair, and future records never fill an earlier unknown state.

| First-view availability history | Eligible pairs | Cart pairs | Transaction pairs | Cart / eligible | Transaction / cart |
| --- | ---: | ---: | ---: | ---: | ---: |
| Recorded 1 | 16,994 | 419 | 64 | 2.4656% | 15.2745% |
| Recorded 0 | 7,005 | 56 | 12 | 0.7994% | 21.4286% |
| View before first history record | 1,106 | 8 | 0 | 0.7233% | 0.0000% |
| No history | 0 | 0 | 0 | NULL | NULL |
| Total | 25,105 | 483 | 76 | 1.9239% | 15.7350% |

Recorded 1 has a higher cart/eligible rate but a lower transaction/cart rate than recorded 0. The latter comparison conditions on different groups of carting pairs and uses only 56 carts in the recorded-0 group. It cannot establish that one state causes better or worse outcomes. These are historical observations, not verified live inventory, customer exposure or state throughout follow-up. Zero NO_HISTORY in this selected category does not imply complete availability coverage globally. See the [availability definition, validation and learner acceptance](RETAILROCKET_CATEGORY_AVAILABILITY_FUNNEL_VALIDATION.md).

## Operational follow-up and portfolio output

The actionable output is an investigation brief with explicit denominators and coverage, not a forecast of recoverable revenue. In a live business, a follow-up would reconcile stage logging, inspect category 1613's product and traffic mix, and obtain contemporaneous availability, pricing, delivery and checkout evidence. Any proposed intervention would need its own evaluation before claiming improved conversion.

The accepted SQL, source reconciliation, aggregate tables and these findings complete the defined funnel milestone. The next task audits transaction identity and repeated item observations before constructing candidate baskets. Co-purchase relationships will require their own support, confidence, lift and later-period checks; no recommendation uplift has yet been measured.
