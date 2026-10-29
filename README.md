# Retail Merchandising Analytics

A guided SQL, Python and Power BI portfolio project investigating product assortment, sales predictability and shopping behaviour using public datasets.

**Status: store results are accepted; the two-baseline final-holdout evaluation passed assistant verification.** SQL42's 30 rows match across fourteen visible substantive fields; the learner separately confirms all PASS values in the clipped status column ([acceptance](docs/STORE_FORECAST_ERRORS_VALIDATION.md)). The [frozen protocol](docs/FINAL_HOLDOUT_BASELINE_PROTOCOL.md) selects **WEEKDAY4 globally among the two implemented baselines**, retaining SNAIVE7 as a fixed reference, based on accepted development evidence. [SQL43](sql/43_evaluate_final_holdout_baselines.sql) scores their existing predictions for 25 April–22 May 2016, with all 30,490 series retained. Independent preflight passed seven test families/fourteen subcases and both twelve-field report rows. WEEKDAY4 has MAE 1.103654 and macro RMSSE 0.828159, versus SNAIVE7’s 1.243972 and 0.997242. Learner execution is pending. The [public protocol freeze](https://github.com/quanchenginitial/retail-merchandising-analytics/commit/6d270efb8c06bc06632f6e3a400066cb11e3d626) preceded final-target access. This is a baseline-only milestone. A tree model remains unimplemented; this holdout has now been evaluated, so future model development needs untouched evaluation data for a new final test. See [the current step](docs/FIRST_STEP_ZH.md), [final-holdout method](docs/FINAL_HOLDOUT_BASELINES_VALIDATION.md), [metric contract](docs/ARCHITECTURE_AND_METRICS.md) and [checkpoint history](PROJECT_CHECKLIST.md).

## Business purpose

Help a merchandising analyst decide which products need closer attention, where sales forecasts are unreliable, and which shopping behaviours merit investigation. The outputs will be decision tables and a Power BI report backed by reproducible SQL, transparent metrics and evaluated Python models.

This project extends an existing banking SQL/Power BI portfolio into product analysis. It adds SKU/store sales, assortment and forecasting work; the existing Olist delivery/customer project and UCI pipeline project retain their separate purposes. This is independent historical-data analysis, not work for IKEA, Walmart or the other data publishers.

## Selected data

| Module | Source | Documented scale | Planned purpose |
| --- | --- | --- | --- |
| A: merchandising core | [M5 / Walmart](https://github.com/Mcompetitions/M5-methods) | 3,049 products, 10 stores; 30,490 series × 1,941 training days = **59,181,090 daily cells** | Product/category mix, ABC/XYZ, sales forecasts, price associations and anomaly candidates |
| B: shopping behaviour | [Retailrocket, version 2](https://www.kaggle.com/datasets/retailrocket/ecommerce-dataset) | **2,756,101 events** and **20,275,902 item-property records** | Behavioural segments, cart-to-purchase proxy, co-purchase candidates and time-aware availability joins |
| C: optional experiment extension | [Criteo corrected uplift release](https://ailab.criteo.com/criteo-uplift-prediction-dataset/) | **13,979,592 user rows** | Randomized advertising-treatment analysis and uplift evaluation |

M5 dimensions and daily-cell counts are now verified against the local files. Retailrocket and Criteo counts remain publisher figures. M5 daily cells are not individual transaction lines. Retailrocket transaction events are not necessarily distinct orders. The three modules describe different businesses and populations: their IDs and monetary measures will never be joined or pooled.

The supplied M5 files passed the source-file audit; local hashes identify this snapshot without proving its download channel. Retailrocket metadata and a four-byte ZIP range request were verified; its full archive remains undownloaded. Criteo's download could not be verified in this environment. [Dataset selection](docs/DATASET_SELECTION_ZH.md) records access, provenance, alternatives and limitations.

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
