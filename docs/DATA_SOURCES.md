# Data provenance and acquisition contract

Source review: 27 October 2026. This file records research, not completed ingestion. Machine-readable selection metadata is in [source_registry.json](../data/source_registry.json); source counts must be independently measured after acquisition.

## M5 core

Original source: [M5 competition organisers](https://github.com/Mcompetitions/M5-methods), [Kaggle data](https://www.kaggle.com/competitions/m5-forecasting-accuracy/data), [competitor guide](https://github.com/Mcompetitions/M5-methods/blob/master/M5-Competitors-Guide.pdf). The organiser repository links its own Drive dataset folder, recorded in the registry. Kaggle identifies the licence as Subject to Competition Rules; the complete current rule text and data download remain unverified here. Review [rules](https://www.kaggle.com/competitions/m5-forecasting-accuracy/rules) before acquisition.

Select `sales_train_evaluation.csv`, `calendar.csv` and `sell_prices.csv`. Store immutable originals under `data/raw/m5/`. The overlapping `sales_train_validation.csv` must not be appended. Expected sales identifiers are id, item_id, dept_id, cat_id, store_id and state_id, followed by d_1 through d_1941. Calendar joins use d; weekly prices use item_id, store_id and wm_yr_wk. Verify all keys before joining.

Documented coverage is 3,049 products across ten stores and three US states. The training file's 30,490 series × 1,941 days implies 59,181,090 cells; these are daily observations rather than transaction lines. Unit sales begin on 2011-01-29. Derived training end is 2016-05-22 and must be checked against the downloaded calendar. Weekly average prices support a value proxy, not exact recognized revenue. Inventory, costs and customers are absent from the documented schema.

## Retailrocket behaviour

Source: [Retailrocket's Kaggle release](https://www.kaggle.com/datasets/retailrocket/ecommerce-dataset), fixed version 2. The official metadata endpoint and versioned ZIP URL are recorded in the registry. Licence: [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/). Attribute Retailrocket and preserve applicable source terms for shared adaptations; no raw records are distributed here.

The publisher documents 2,756,101 events over about 4.5 months and 20,275,902 item-property change records. Events contain timestamp, visitorid, event, itemid and transactionid. Meaningful disclosed properties include categoryid and available; other values cannot be assumed to represent money. Property joins must use values known at event time. A recorded transaction event is not necessarily a unique order, and an anonymous visitor identifier is not a verified person.

Metadata and a four-byte range request confirmed an accessible ZIP signature without downloading the complete archive. This does not validate its contents, row counts, checksums or analytical suitability after cleaning. Record those in stage 1/behaviour-module audit when the files are acquired.

## Optional extensions

- [Criteo corrected uplift data](https://ailab.criteo.com/criteo-uplift-prediction-dataset/): use the 13,979,592-row corrected release, not the old 25,309,483-row release affected by published leakage. CC BY-NC-SA 4.0. The publisher's linked download domain failed DNS resolution during research. Advertising-treatment data is an independent method exercise, not a product-feature test. Nonuniform sampling prevents recovering the original advertiser incrementality.
- [dunnhumby Complete Journey](https://www.dunnhumby.com/source-files/): original two-year/2,500-household description. Download and exact data terms remain pending. The [completejourney package](https://bradleyboehmke.github.io/completejourney/) is a distinct maintained distribution of a one-year/2,469-household 84.51° release. Its package metadata states CC0; retain the distribution chain and verify files before use. Do not mix releases or assume identical monetary conventions.
- [Google GA4 sample](https://developers.google.com/analytics/bigquery/web-ecommerce-demo-dataset): obfuscated events from 2020-11-01 to 2021-01-31. Access requires a BigQuery-enabled project; no query has run. Placeholder values and limited internal consistency constrain business interpretation. The documentation's licence footer is not evidence of a separate data licence.

## Acquisition evidence required

For every actual source file record: canonical source page, version, retrieval timestamp with timezone, local relative path, size, SHA-256, archive membership, parsing settings, columns, observed rows, date coverage, key checks and missing-value patterns. Preserve archive hashes separately from extracted-file hashes. Stop and investigate unexpected schema or count changes rather than silently substituting another release.

GitHub receives source references, checks and reviewed aggregate results. Raw files, personal source documents, user-level extracts, databases, tokens and signed temporary download URLs remain excluded. No project-wide data licence is inferred from the repository's visibility.
