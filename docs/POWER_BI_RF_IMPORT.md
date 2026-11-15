# Power BI RF CSV import and type checkpoint

Updated: 15 November 2026 (Australia/Sydney).

The actual learner export at D:/database/retailrocket/rf_segment_summary.csv is accepted: 830 bytes, UTF-8 without BOM, with all 16 rows and seven fields matching the accepted aggregate table. Counts remain 11,719 visitor IDs and 17,672 candidate baskets. See the [file acceptance](../data/retailrocket_rf_bi_export_file_acceptance.json). The learner confirmed that Power BI Desktop is installed and opens. Power BI import has not yet been observed or accepted.

## One manual checkpoint

1. Open a **new blank report** in Power BI Desktop.
2. Choose **Home → Get data → Text/CSV**, then open D:/database/retailrocket/rf_segment_summary.csv.
3. In the preview, choose **65001: Unicode (UTF-8)** for file origin and **Comma** for delimiter. Select **Transform Data** to open Power Query Editor. Microsoft documents the Text/CSV connector, encoding/delimiter settings and Transform Data route in its [connector guide](https://learn.microsoft.com/en-us/power-query/connectors/text-csv).
4. Set the query name to **rf_segment_summary**. Confirm exactly **16 data rows and seven columns**, with the names and order below. The first CSV line supplies the headers; it is not a seventeenth data row. There is no TOTAL row.
5. Use each column's data-type control to set the five numeric columns to **Whole Number** and the two band columns to **Text**. Check every header's type icon; do not rely solely on automatic inference. Whole Number is Power Query's 64-bit integer type, Int64.Type. See Microsoft's [data-type reference](https://learn.microsoft.com/en-us/power-query/data-types).

| Column, in order | Power Query type |
| --- | --- |
| reference_timestamp_ms | Whole Number (Int64) |
| recency_order | Whole Number (Int64) |
| recency_band | Text |
| frequency_order | Whole Number (Int64) |
| frequency_band | Text |
| visitor_ids | Whole Number (Int64) |
| candidate_baskets | Whole Number (Int64) |

Keep reference_timestamp_ms as the numeric value **1442545187788** in every row. It is the fixed historical reference in milliseconds, not today's date. Keep the source values and row order unchanged; this checkpoint adds no date conversion, filters, grouping, label sorting, DAX, relationships or visuals.

## Evidence and stopping point

Stay in **Power Query Editor**. Send a screenshot showing the query name, all 16 rows, all seven complete headers and type icons, plus **Applied Steps**. Two screenshots are acceptable if one cannot show everything legibly.

Stop before **Close & Apply** and saving the report. A screenshot review will determine the next step. This guide does not claim that the query has been loaded into a model, a report has been saved, or a dashboard has been built. No native Power BI actions were executed by the assistant for this preparation.
