# M5 source-file audit

Completed on 27 October 2026. The learner supplied the three extracted M5 CSVs after reporting a completed download. The assistant scanned them read-only with Python 3.12.14. No persistent project database or analytical model was created. This is source-file verification, separate from the learner's upcoming DBeaver exercise.

## Verified inventory

| File | Bytes | Data rows, excluding header | Columns | Grain |
| --- | ---: | ---: | ---: | --- |
| calendar.csv | 103,469 | 1,969 | 14 | One calendar date |
| sales_train_evaluation.csv | 121,736,518 | 30,490 | 1,947 | One product/store series, with 1,941 daily unit columns |
| sell_prices.csv | 203,395,785 | 6,841,121 | 4 | One product/store/week |

The sales file contains 3,049 products, ten stores, three states, seven departments and three categories. Its 59,181,090 daily values are all present, parse as integers and are nonnegative. The control sum is 66,927,173 units; 40,241,819 cells are zero. These are reconciliation controls, not a forecast evaluation or evidence of stockouts.

Calendar dates are continuous from 2011-01-29 to 2016-06-19. Training sales stop at d_1941, **2016-05-22**. The calendar's final 28 days do not extend the training sales history. d_1913 maps to 2016-04-24, preserving the proposed final 28-day holdout.

## Quality results

All **33 explicitly recorded checks** passed. This count does not measure test coverage. Exact headers and CSV row widths were also enforced during parsing; a mismatch would stop the script.

- Calendar: unique dates/day IDs, continuous dates/day labels, valid weekday/month/year attributes, binary SNAP values and paired event-name/type missingness.
- Sales: unique series IDs and item/store keys; complete identifiers; consistent item-to-department/category and store-to-state mappings; no missing, invalid-integer or negative daily unit values.
- Prices: 6,841,121 unique item/store/week keys; no missing fields, invalid/nonpositive prices, unknown calendar weeks or item/store pairs absent from sales. Every sales pair has at least one price record. Prices range from 0.01 to 107.32.
- File integrity: SHA-256 values were identical before and after the scans.

Event fields intentionally contain blanks: event_name_1/event_type_1 each have 1,807; event_name_2/event_type_2 each have 1,964. Preserve these as no recorded event, rather than treating them as corrupt source rows.

An independent calendar scan confirmed counts, dates, mappings and missingness. An independent DuckDB v1.5.5 in-memory query confirmed price row count, key uniqueness, numeric validity and range. Neither verification created the learner's project database. Evidence: [primary audit](../data/m5_source_audit.json), [independent checks](../data/m5_independent_checks.json), [executed price SQL](../validation/price_source_check.sql).

## Reproduce

Requires Python 3.11 or later; no third-party Python packages. Tested with Python 3.12.14. Run from the repository root, replacing the source directory with the location of your immutable files:

```powershell
python scripts/audit_m5_sources.py --source-dir "D:/database/m5-forecasting-accuracy" --output "data/m5_source_audit.json"
```

The output contains hashes and aggregate diagnostics, not source records. The script returns a nonzero exit code for a failed check or parse failure. Calendar and sales expectations are specific to this selected M5 release; a changed release requires review instead of loosening checks blindly.

## Remaining checks and provenance limits

The local hashes identify this snapshot; no publisher-supplied checksum was available for comparison. The precise retrieval timestamp, download URL and original archive hash were not captured. The extracted files' historical modification timestamps are not the retrieval date. User-supplied files and their consistent schema do not independently establish the download channel or current redistribution rights. The canonical source remains the [M5 competition data page](https://www.kaggle.com/competitions/m5-forecasting-accuracy/data).

Day-level price coverage, particularly for positive sales, has not yet been checked. Some price history exists for each item/store pair, but that does not establish complete weekly coverage. Source-to-database reconciliation, raw-layer import, transformations, business metrics, model training and Power BI remain pending. Neither missing prices nor zero sales establishes stockouts.

The other two downloaded CSVs were observed in the directory but not audited or appended to sales. The validation file overlaps evaluation history; sample_submission is a competition output template.
