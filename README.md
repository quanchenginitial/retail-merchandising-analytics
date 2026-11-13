# Retail Merchandising Analytics

A guided SQL, Python and Power BI portfolio project investigating product assortment, sales predictability and shopping behaviour using public datasets.

**Current step, 13 November 2026:** the learner accepted all 45 visible fields of [SQL81's nested association-metric profile](docs/RETAILROCKET_BASKET_ASSOCIATION_METRICS_VALIDATION.md), with five PASS rows and no NULLs; see the [acceptance](data/retailrocket_basket_association_metrics_learner_acceptance.json). Minimum co-occurrence counts 1, 2, 3, 5 and 10 retain 9,688, 903, 79, 12 and 1 pairs. Next, read-only [SQL82](sql/82_analyze_retailrocket_basket_pair_cases.sql) displays all twelve pairs observed in at least five candidate baskets, with both directional confidences shown separately. The threshold was chosen after the profile to keep the exploratory case set manageable, not as an optimal or validated cutoff. Snapshot-specific PAIR_01–PAIR_12 labels hide actual item IDs; A/B roles are local to each pair. All 17,672 candidate baskets remain in support and item marginals. Assistant preflight passed; learner execution of the twelve-row, nine-column report remains pending, normally with twelve PASS statuses. New proof compares the twelve selected ten-field metric rows and their report, reusing SQL81's full metric evidence. These cases establish no business recommendation, verified order or causal effect. RF segmentation, rule validation and Power BI remain incomplete. See the [current step](docs/FIRST_STEP_ZH.md).

**The Stage 5 baseline forecasting milestone was accepted on 30 October 2026.** The learner reproduced [SQL43](sql/43_evaluate_final_holdout_baselines.sql): both FINAL_HOLDOUT rows and all twelve fields, including both PASS values, match the assistant preflight. **WEEKDAY4 remains the globally selected baseline; SNAIVE7 is its fixed reference**, as [frozen before final scoring](docs/FINAL_HOLDOUT_BASELINE_PROTOCOL.md). Across 30,490 series in 25 April–22 May 2016, WEEKDAY4 has MAE 1.103654 and macro RMSSE 0.828159, versus 1.243972 and 0.997242: approximate error reductions of 11.28% and 16.96%, calculated from displayed metrics. Its aggregate forecast is still 48,138 units below actual sales. See the [accepted findings and limits](docs/STAGE05_BASELINE_FORECAST_FINDINGS.md) and [screenshot acceptance](docs/FINAL_HOLDOUT_BASELINES_VALIDATION.md). A tree model remains unimplemented; this exposed period cannot serve as a fresh final test. The overall portfolio remains incomplete.

The learner accepted SQL44 on 30 October 2026: all thirteen rows and twelve fields, including thirteen complete PASS values, match its frozen preflight. The accepted table retains 365,880 item/store/week positions, 2,561,160 daily positions and 3,536,539 units. Sixteen missing-price weekly positions all have zero sales. See the [acceptance record](data/item_store_weekly_prices_learner_acceptance.json).

The learner accepted [SQL45](sql/45_audit_price_variation.sql) on **2 November 2026**: all twelve rows and twelve fields, including twelve complete PASS values, match its frozen report. The [acceptance record](data/price_variation_learner_acceptance.json) retains 335,374 comparable transitions and 3,361 distinct pairs with a price change; distinct-pair totals are not sums of weekly pair counts.

The learner accepted [SQL46](sql/46_price_sales_association.sql) on **2 November 2026**: all five rows, twelve fields and five PASS values match its frozen report. See the [60-field acceptance record](data/price_sales_association_learner_acceptance.json). Both price-up and price-down groups have positive mean unit changes in this unadjusted comparison; this does not identify a price effect.

The learner accepted [SQL47](sql/47_weekly_price_sales_association.sql) on **2 November 2026**: all eleven rows, twelve fields and eleven PASS values match its frozen report. See the [132-field acceptance record](data/weekly_price_sales_association_learner_acceptance.json). Price-up means are positive in all eleven weeks; price-down means are positive in the first eight and negative in the last three. These are descriptive group patterns.

The learner accepted [SQL49](sql/49_week_department_price_contrasts.sql) on **2 November 2026**: all 168 values across fourteen rows and twelve fields, including fourteen PASS statuses, match the frozen report. All 3,796 price-change transitions have a same-week/department unchanged reference. This completes the descriptive price-association milestone through SQL49; see the [acceptance record](data/week_department_price_contrasts_learner_acceptance.json) and [findings](docs/STAGE06_PRICE_ASSOCIATION_FINDINGS.md). These comparisons do not identify causal price effects.

The learner accepted [SQL51 classification](docs/ANOMALY_CANDIDATES_VALIDATION.md) on **2 November 2026**, with all 60 values and five PASS statuses matching the frozen report. SUDDEN_ZERO / LARGE_INCREASE / LARGE_DECREASE contain 902 / 6,118 / 5,327 target positions: 12,347 of 243,920 targets, approximately 5.0619%, are review candidates. These are not verified anomalies or stockouts; distinct-series counts overlap across classes. See the [acceptance record](data/anomaly_candidates_learner_acceptance.json).

The learner accepted [SQL52 weekly triage](docs/WEEKLY_ANOMALY_TRIAGE_VALIDATION.md) on **2 November 2026**, with all 96 values and eight PASS statuses matching. Weekly candidate counts range from 1,393 to 1,691, or 4.5687%–5.5461% of each week’s targets; see the [acceptance](data/weekly_anomaly_triage_learner_acceptance.json).

The learner accepted SQL53 on 2 November 2026: all 432 visible values across 36 rows and twelve fields, including 36 complete PASS statuses, match the frozen private reference. See the [aggregate acceptance](data/anomaly_case_histories_learner_acceptance.json). Actual case rows and selection keys remain private; aliases are not proof of anonymization, and the three fixed lower-median examples are not a representative sample. Later observations are retrospective context only. The implemented Stage 6 descriptive price analysis, candidate screening and illustrative history review, with an investigation framework, are complete; external operational causes and detection performance remain unassessed. See [anomaly findings and investigation requirements](docs/STAGE06_ANOMALY_REVIEW_FINDINGS.md). Retailrocket intake and its next import step are tracked in [the current guide](docs/FIRST_STEP_ZH.md). The overall portfolio remains incomplete.

## Business purpose

Help a merchandising analyst decide which products need closer attention, where sales forecasts are unreliable, and which shopping behaviours merit investigation. The outputs will be decision tables and a Power BI report backed by reproducible SQL, transparent metrics and evaluated Python models.

This project extends an existing banking SQL/Power BI portfolio into product analysis. It adds SKU/store sales, assortment and forecasting work; the existing Olist delivery/customer project and UCI pipeline project retain their separate purposes. This is independent historical-data analysis, not work for IKEA, Walmart or the other data publishers.

## Selected data

| Module | Source | Documented scale | Planned purpose |
| --- | --- | --- | --- |
| A: merchandising core | [M5 / Walmart](https://github.com/Mcompetitions/M5-methods) | 3,049 products, 10 stores; 30,490 series × 1,941 training days = **59,181,090 daily cells** | Product/category mix, ABC/XYZ, sales forecasts, price associations and anomaly candidates |
| B: shopping behaviour | [Retailrocket, version 2](https://www.kaggle.com/datasets/retailrocket/ecommerce-dataset) | **2,756,101 events** and **20,275,902 item-property records** | Behavioural segments, cart-to-purchase proxy, co-purchase candidates and time-aware availability joins |
| C: optional experiment extension | [Criteo corrected uplift release](https://ailab.criteo.com/criteo-uplift-prediction-dataset/) | **13,979,592 user rows** | Randomized advertising-treatment analysis and uplift evaluation |

M5 dimensions and daily-cell counts are verified against local files. Retailrocket event and property row counts are now locally verified; Criteo counts remain publisher figures. M5 daily cells are not individual transaction lines. Retailrocket transaction events are not necessarily distinct orders. The three modules describe different businesses and populations: their IDs and monetary measures will never be joined or pooled.

The supplied M5 and Retailrocket files passed their recorded source audits; local hashes identify these snapshots without proving their download channels. The learner supplied four extracted Retailrocket files, while the original archive and exact retrieval timestamp remain unverified. Retailrocket contains 460 surplus duplicate parsed event rows, retained unchanged; event/order identity and deduplication policy remain separate work. Criteo's download could not be verified in this environment. [Dataset selection](docs/DATASET_SELECTION_ZH.md) records access, provenance, alternatives and limitations.

## Intended questions

1. Which products and categories contribute most to observed sales, and how stable are they?
2. How well can simple baselines forecast the next 28 days of recorded sales?
3. Which product/store changes warrant investigation after data-quality checks?
4. Which visitors behave similarly, and which items appear in the same recorded transaction?
5. Where does observed browsing or cart activity fail to lead to an observed purchase?
6. How should a randomized intervention be evaluated with uncertainty and guardrails?

The [question coverage matrix](docs/QUESTION_COVERAGE_ZH.md) distinguishes measurable questions, proxies and unavailable outcomes. Recorded sales are not unconstrained demand. Neither zero sales nor a missing weekly price proves a stockout. The selected core has no unit costs, inventory ledger, refunds or randomized product changes.

## Working method

Briefly explain the step's purpose and intended analytical use → learner performs one small action → inspect actual evidence → update the checklist → publish the completed checkpoint to GitHub. Assistant preparation and learner completion are recorded separately. Each new instruction starts with that purpose summary.

Planned stack: DuckDB SQL in DBeaver, Python for auditing and evaluation, Power BI for reporting, and GitHub for versioned checkpoints. The schemas will separate raw, typed staging and module-specific marts. [Architecture and metrics](docs/ARCHITECTURE_AND_METRICS.md) defines grains, joins and proposed measures; [evaluation design](docs/EVALUATION_PLAN.md) defines future-information controls and validation gates.

## Start here

- [中文学习路线](docs/ROADMAP_ZH.md)
- [第一步操作](docs/FIRST_STEP_ZH.md)
- [数据集比较与选择](docs/DATASET_SELECTION_ZH.md)
- [业务问题覆盖范围](docs/QUESTION_COVERAGE_ZH.md)
- [进度与完成证据](PROJECT_CHECKLIST.md)
- [来源登记](data/source_registry.json)

## Repository policy

Commit reviewed code, source references, metric definitions, aggregate findings and validation evidence at each completed stage. Keep raw data, row-level extracts, databases, credentials and large generated files outside Git. A published plan is not an executed analysis or a learner's completed exercise.

Each source retains its own terms. M5 is subject to competition rules; Retailrocket and Criteo state CC BY-NC-SA 4.0. This repository does not grant a replacement licence to source data. No source records or the personal career report are included.
