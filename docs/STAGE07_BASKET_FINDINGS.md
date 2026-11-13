# Retailrocket basket analysis findings

Accepted through SQL84 on 13 November 2026 (Australia/Sydney).

This analysis asks which observed product combinations merit investigation for cross-selling, and whether apparent associations have enough recorded breadth to justify further validation. The completed descriptive basket milestone produces twelve inspectable cases with explicit sample sizes, directional association metrics, visitor-ID concentration and monthly coverage. It does not establish deployable recommendation rules or measured uplift.

## Establishing the basket grain

The 22,457 transaction-event rows are not 22,457 verified orders. The analysis uses `(visitorid, transactionid)` as a candidate basket key and retains one membership per basket and item. This produces 22,323 memberships across 17,672 candidate baskets, including 15,029 single-item baskets and 2,643 baskets with multiple items. Repeated observations remain auditable: 123 memberships have more than one source event, accounting for 134 additional event occurrences. Occurrence counts are not interpreted as purchased quantities. See the accepted [grain audit](RETAILROCKET_TRANSACTION_BASKET_GRAIN_VALIDATION.md) and [membership model](RETAILROCKET_TRANSACTION_BASKET_ITEMS_VALIDATION.md).

Each unordered item pair contributes once per candidate basket. All 17,672 baskets, including single-item baskets, remain in the support denominator and item marginal counts. The resulting 10,757 pair appearances represent 9,688 distinct item pairs; 8,785 pairs appear only once, while 903 appear at least twice. This sparse evidence makes raw association rankings vulnerable to very small samples. A basket can contribute several pairs, so summed pair appearances are not counts of distinct baskets. See the [pair-count reconciliation](RETAILROCKET_BASKET_PAIR_COUNTS_VALIDATION.md).

## Association strength requires direction and sample size

Support measures the share of all candidate baskets containing both items. Directional confidence divides joint occurrences by baskets containing the antecedent item; reversing the direction changes that denominator. Lift compares joint occurrence with the product of the two marginal rates. Large lift values can arise when the items themselves are rare and do not by themselves establish dependable recommendations.

The [threshold profile](RETAILROCKET_BASKET_ASSOCIATION_METRICS_VALIDATION.md) compares minimum joint counts of 1, 2, 3, 5 and 10. A threshold of five was chosen after inspecting this profile to obtain a manageable exploratory set: all twelve qualifying pairs, with 110 pair appearances, are retained. This is an inspection choice rather than an optimal cutoff or evidence that every selected case is reliable.

For example, PAIR_01 occurs in 39 baskets. Its A-to-B confidence is 42.391304%, while B-to-A confidence is 86.666667%; support is 0.220688% and lift is 166.475362. PAIR_09 occurs in only five baskets but has B-to-A confidence of 100% and lift of 1,039.529412. Its high metrics therefore need to be read alongside the small denominator. A and B indicate numeric item ordering within each pair, not causal direction; the case labels belong to this fixed snapshot. See the [twelve accepted cases](RETAILROCKET_BASKET_PAIR_CASES_VALIDATION.md).

## Concentration changes the interpretation

The follow-up distinguishes repeated contributions from the same recorded visitor ID and concentrations in the observed calendar months.

| Case | Paired baskets | Distinct visitor IDs | Largest ID contribution | Monthly coverage |
| --- | ---: | ---: | --- | --- |
| PAIR_01 | 39 | 36 | 2 baskets; 5.128205% | 35 in July, 2 in August and 2 in September |
| PAIR_09 | 5 | 2 | 4 baskets; 80.000000% | All 5 in May |

PAIR_01 has broader recorded ID coverage, but most of its joint appearances occur in July. PAIR_09 has both a small sample and a dominant contributing ID, with all appearances in one month. These observations temper interpretation of their association metrics without proving that either case is invalid. Visitor IDs are not verified people, and different IDs do not establish independent observations. The same ID may appear in several cases. See the accepted [visitor concentration](RETAILROCKET_PAIR_VISITOR_CONCENTRATION_VALIDATION.md) and [month coverage](RETAILROCKET_PAIR_MONTH_COVERAGE_VALIDATION.md) reports.

Month assignment uses the earliest observed timestamp across every membership in a candidate basket, rather than only the selected pair. It is not a verified order or payment timestamp. The overall UTC observation window is 3 May–18 September 2015, so boundary months are partial and month lengths differ. Cases were selected using the same full snapshot. Their monthly counts are retrospective descriptions, not comparable monthly conversion rates, growth measures or independent temporal validation.

## Operational follow-up and portfolio output

The deliverable is a reproducible investigation shortlist and its evidence trail. Before a live cross-sell decision, an operational team would need to reconcile candidate keys with order and line-item records, establish event deduplication and identity rules, and obtain product meanings, availability, prices, margins and existing recommendation exposure. Those inputs would distinguish commercially suitable combinations from relationships driven by logging, repeated activity or a temporary context.

A next validation would freeze candidate selection and evaluation criteria before observing a separate later period, then check recurrence and direction-specific performance with adequate sample sizes. A controlled recommendation experiment with suitable revenue, margin and customer-experience measures would be needed to estimate incremental value. No recommendation uplift, causal effect or independent validation is claimed here. Behavioural RF segmentation and Power BI remain separate unfinished project work.
