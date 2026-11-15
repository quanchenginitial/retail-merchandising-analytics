# Retailrocket RF analysis findings

Accepted through SQL88 on 15 November 2026 (Australia/Sydney).

This analysis asks how observed transaction activity differs by recency and frequency, and whether a group's basket contribution is shared broadly or concentrated in a few recorded identifiers. The completed descriptive RF milestone combines a 16-cell distribution with concentration measures. It provides an investigation baseline for behavioural segmentation; commercial targeting decisions require additional validation.

## Population and measurement

The population is 11,719 visitor IDs with recorded transaction events, represented by 22,323 item memberships across 17,672 candidate baskets. A basket uses the complete `(visitorid, transactionid)` key. Frequency F counts distinct candidate baskets per ID across the observation window, so additional items and repeated event observations do not increase F. Browsing-only IDs are outside this population. IDs are not verified people and candidate baskets are not verified paid orders. See the accepted [basket membership model](RETAILROCKET_TRANSACTION_BASKET_ITEMS_VALIDATION.md).

Recency R measures elapsed time from each ID's latest observed transaction to the fixed global event endpoint, **18 September 2015 at 02:59:47.788 UTC**. A day is 24 hours. The four R bands are under 7 days, 7 to under 30 days, 30 to under 60 days and at least 60 days; F bands are 1, 2, 3–4 and at least 5 baskets. These fixed descriptive ranges form 16 mutually exclusive groups. F always covers the full observed window, including when the ID's most recent transaction falls in the under-seven-day group.

## Frequency and recency reveal different distributions

Most transaction-recorded IDs appear in one candidate basket: **10,656 IDs, or 90.929260%**. The **138 IDs with at least five baskets** represent **1.177575%** of the population but contribute **4,945 baskets, or 27.982119%** of all baskets. This concentration makes frequency useful for describing observed activity without treating every ID as an equally large contributor. See the accepted [frequency results](../data/retailrocket_visitor_purchase_frequency_learner_acceptance.json).

At the fixed endpoint, **6,750 IDs, or 57.598771%**, have no observed transaction in the preceding 60 days. Across all transaction-recorded IDs, the median interval is **70.897344 days**. These are elapsed intervals in a finite log, rather than measured customer churn. Different IDs may have different observation lengths and opportunities to transact. See the accepted [recency results](../data/retailrocket_visitor_purchase_recency_learner_acceptance.json).

Combining R and F separates groups that either measure alone would merge. The under-seven-day, F5+ group contains **19 IDs and 1,517 candidate baskets**, accounting for **8.584201% of all baskets**. At the other end, **6,166 IDs, or 52.615411% of the population**, have one recorded basket and a recency of at least 60 days. The 1,517 baskets belong to the recent group's members across the whole observation window; they are not a seven-day sales total. See the accepted [RF matrix](../data/retailrocket_visitor_rf_segments_learner_acceptance.json).

## Group contribution needs a concentration check

Within the under-seven-day, F5+ group, just five IDs account for **79.960448%** of its baskets. Its apparent group contribution therefore includes substantial concentration in a small number of identifiers.

| Population | IDs | Full-window baskets | Largest ID contribution | Top five ID contribution |
| --- | ---: | ---: | --- | --- |
| R under 7 days and F at least 5 | 19 | 1,517 | 502 baskets; 33.091628% | 1,213 baskets; 79.960448% |
| All transaction-recorded IDs | 11,719 | 17,672 | 502 baskets; 2.840652% | 1,318 baskets; 7.458126% |

Each concentration percentage divides by the basket total in its own row. This differs from the RF matrix's 8.584201% contribution, which divides the recent group's 1,517 baskets by all 17,672 baskets. The global top five are ranked again across all IDs; their 1,318 baskets are not a sum of the top five from each group. Ranking uses F descending with ID ascending for reproducible ties. See the accepted [concentration results](../data/retailrocket_rf_basket_concentration_learner_acceptance.json).

This distinction supports a practical investigation: examine whether the activity behind a concentrated group is consistent with its identifier and basket definitions before using the group for commercial decisions. Concentration alone does not identify unusually valuable customers, fraud or automated activity. The analysis has no verified monetary measure and therefore remains RF rather than monetary RFM.

## Follow-up and portfolio scope

An operational follow-up would reconcile identifier and basket semantics with business records and inspect activity timing relative to each ID's observed exposure. A separate evaluation should freeze the grouping rules and success criteria before examining a later period. Any claim about incremental targeting value would require an appropriate intervention design and business outcomes.

The accepted output is a reproducible descriptive RF distribution and concentration assessment, alongside the separate [funnel](STAGE07_FUNNEL_FINDINGS.md) and [basket](STAGE07_BASKET_FINDINGS.md) findings. This completes the descriptive RF milestone. Power BI delivery, independent temporal validation and business-effect evaluation remain separate project work.
