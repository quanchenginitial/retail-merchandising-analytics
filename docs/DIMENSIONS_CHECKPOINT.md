# M5 dimension acceptance checkpoint

Completed from learner screenshots on 27 October 2026. Product, store and calendar dimensions have each passed their own acceptance checks. The assistant transcribed the displayed results; it did not directly open the learner's persistent database.

| Accepted dimension | Grain | Rows | Fields | Learner checks |
| --- | --- | ---: | ---: | ---: |
| core.m5_product | One product | 3,049 | 3 | 15/15 PASS |
| core.m5_store | One store | 10 | 2 | 13/13 PASS |
| core.m5_calendar | One source day/date | 1,969 | 15 | 17/17 PASS |

Products retain their original department/category codes, with seven departments and three categories. Stores retain their source state codes: CA has four stores, TX three and WI three. The calendar retains all 14 typed source fields and adds INTEGER day_number, with exact original-field reconciliation and unique day/date keys. Uniqueness is checked by acceptance queries; no physical PRIMARY KEY constraints have been declared.

The calendar spans 2011-01-29 through 2016-06-19. The observed sales snapshot ends on d_1941, 2016-05-22, leaving 28 subsequent calendar dates. These dates do not represent observed zero sales. Source retail-week and weekday definitions remain unchanged.

## Evidence chain

- [Staging checkpoint](STAGING_LAYER_CHECKPOINT.md).
- [Product acceptance](../data/product_dimension_learner_acceptance.json) and [method](PRODUCT_DIMENSION_VALIDATION.md).
- [Store acceptance](../data/store_dimension_learner_acceptance.json) and [method](STORE_DIMENSION_VALIDATION.md).
- [Calendar acceptance](../data/calendar_dimension_learner_acceptance.json) and [method](CALENDAR_DIMENSION_VALIDATION.md).

Assistant preflights and learner executions remain separate records. Source files, databases and learner screenshots are not published.

## Next acceptance boundary

At this checkpoint, the three dimensions are individually validated. Their small source-key checks do not yet establish a completed full join to daily sales. The next action executes the product, store and calendar joins against all 59,181,090 sales observations, checks every match and compares row counts, units, zero rows and store controls before and after the joins.

Daily price coverage, a persisted joined fact table, analytical results, forecasts and Power BI remain later work. Follow [the current step](FIRST_STEP_ZH.md) and [progress checklist](../PROJECT_CHECKLIST.md).
