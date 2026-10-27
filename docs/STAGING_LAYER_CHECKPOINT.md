# M5 staging-layer acceptance checkpoint

Completed from learner screenshots on 27 October 2026. The latest screenshot passes all 15 daily sales reconciliation checks: 59,181,090 compared cells, zero mismatching series and zero mismatching cells, with complete unique daily keys and matching source/target series sets. The assistant transcribed the displayed results; it did not open the learner's persistent database.

| Accepted table | Rows | Fields | Learner evidence |
| --- | ---: | --- | --- |
| stg.m5_calendar | 1,969 | 14 typed calendar fields | 13/13 checks; lossless text round-trip to raw |
| stg.m5_prices | 6,841,121 | Item/store codes, INTEGER week, DECIMAL(18,2) price | 13/13 checks; exact canonical value equality to raw |
| stg.m5_sales_daily | 59,181,090 | Item/store/day codes and INTEGER units | 14/14 reshape checks plus 15/15 exact cell reconciliation |

The raw layer preserves original imported values and remains available for tracing transformations. Sales reshaping preserves 40,241,819 zero-sales rows and 66,927,173 total units. Each of the 30,490 item/store series has exactly one row for every source day d_1 through d_1941. These are daily observations, not individual purchase transactions. Zero recorded sales do not establish stockouts or unconstrained demand.

## Evidence chain

- [Raw-layer checkpoint](RAW_LAYER_CHECKPOINT.md).
- [Calendar staging acceptance](../data/calendar_staging_learner_acceptance.json).
- [Price staging acceptance](../data/price_staging_learner_acceptance.json).
- [Sales reshape acceptance](../data/sales_daily_learner_acceptance.json).
- [Exact daily value acceptance](../data/sales_reconciliation_learner_acceptance.json) and [method](SALES_RECONCILIATION_VALIDATION.md).

Assistant preflights and learner execution evidence are separate. Screenshots do not independently recompute source-file hashes. Raw files, user screenshots and databases remain outside GitHub.

## Next stage

At this checkpoint, core dimensions, analytical marts, daily price coverage, forecasts and Power BI pages have not yet been accepted. The next small action builds a one-row-per-product mapping from item_id to dept_id and cat_id, providing the classification needed for later product/category analysis. Full sales joins must still check unmatched rows, multiplicity, unchanged units and price coverage before publishing analytical measures.

Follow [the current step](FIRST_STEP_ZH.md) and [progress checklist](../PROJECT_CHECKLIST.md) for subsequent work. Every learner action starts with a brief explanation of its purpose and intended analytical use.
