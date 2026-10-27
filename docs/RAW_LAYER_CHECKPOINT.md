# M5 raw-layer acceptance checkpoint

Completed by learner evidence on 27 October 2026. DBeaver screenshots confirm all three raw imports and 47 detailed audit checks: 17 for calendar, 15 for sales and 15 for prices. Each current-CSV comparison returned zero differences in both directions, retaining duplicate multiplicities. The assistant reviewed the displayed results; it did not directly open the learner's persistent database.

| Accepted raw table | Stored rows | Columns | Detailed audit |
| --- | ---: | ---: | ---: |
| raw.m5_calendar | 1,969 | 14 VARCHAR | 17/17 PASS |
| raw.m5_sales_wide | 30,490 | 1,947 VARCHAR | 15/15 PASS |
| raw.m5_prices | 6,841,121 | 4 VARCHAR | 15/15 PASS |

The wide sales table represents 59,181,090 daily cells across 3,049 products and 10 stores. All cells are valid nonnegative integers, with 40,241,819 zeros and total units of 66,927,173. They are daily item/store observations, not individual transactions. The calendar spans 2011-01-29 through 2016-06-19; the sales evaluation training file ends at d_1941 (2016-05-22).

Price diagnostics found 6,841,121 finite positive numeric values, ranging from 0.01 to 107.32, with no duplicate item/store/week keys. All price pairs occur in the sales table, all price weeks occur in the calendar, and each sales pair has at least one price row. These checks do not establish price coverage for every daily sale.

## Evidence chain

- [Original source-file audit](M5_SOURCE_AUDIT.md) and [registered hashes](../data/m5_source_audit.json).
- [Calendar audit](CALENDAR_VALIDATION.md) and [learner result transcription](../data/calendar_learner_acceptance.json).
- [Sales audit](SALES_AUDIT_VALIDATION.md) and [learner result transcription](../data/sales_audit_learner_acceptance.json).
- [Price audit](PRICE_AUDIT_VALIDATION.md) and [learner result transcription](../data/price_audit_learner_acceptance.json).

Assistant preflights, their small fault fixtures and learner executions are recorded separately. The screenshot transcriptions do not recompute file hashes. Raw source files, database files and learner screenshots remain outside GitHub.

## Next stage

[Typed calendar staging](CALENDAR_STAGING_VALIDATION.md) is prepared and independently checked, but awaits learner execution. The project has not yet built the sales long table, typed prices, core dimensions, analytical marts, forecasts or Power BI pages. Business conclusions and sales-value measures must wait for those models and their validation, including daily price coverage. This checkpoint establishes a validated raw foundation rather than an analytical outcome.
