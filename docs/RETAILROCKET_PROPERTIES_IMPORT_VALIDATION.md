# Retailrocket properties: raw import with source provenance

[SQL56](../sql/56_import_retailrocket_properties.sql) imports the two audited item-property CSVs into **rr_raw.item_properties** with UNION ALL. On 2 November 2026, the assistant's single bounded source preflight passed all **14 checks across five report columns**. Learner execution and acceptance remain pending. The output/report contract below was fixed before the import preflight. This step preserves a raw attribute log; it does not infer property meaning, deduplicate records, resolve conflicts, choose the latest state or join other modules.

## Source and storage contract

| File | Bytes | Expected records | Observed local SHA-256 |
|---|---:|---:|---|
| item_properties_part1.csv | 484,315,749 | 10,999,999 | 30aad5aeca58b2dc27dcc73e1708565f5818e45adb3eb57401f91e87355b0b81 |
| item_properties_part2.csv | 408,929,907 | 9,275,903 | d5e7d1a91dc40f522aeb596b267e6c87d8aed689a7192d12369cfb165eb987e5 |

Both files are under `D:/database/retailrocket`. The [frozen standard-library source audit](../data/retailrocket_source_audit.json) previously scanned every record, verified headers, UTF-8/CSV widths, required fields and timestamp/item syntax, and established these local fingerprints. No publisher-certified checksum was available. Both parts span **2015-05-10 03:00:00 UTC through 2015-09-13 03:00:00 UTC**; the physical split is not a nonoverlapping date partition.

The table has five VARCHAR columns, in order: **timestamp, itemid, property, value, source_file**. The first four preserve exact source text, including whitespace, leading zeros, literal NULL-looking words and empty strings. Each branch appends its fixed source basename as source_file. All four source columns use force_not_null, so exact-empty raw strings remain visible to quality checks. No trimming, stored numeric casting, value interpretation or imputation occurs. Numeric checks inspect only timestamp and itemid; property and value remain arbitrary text.

Explicit readers use strict CSV parsing, with ignored errors and padding disabled. UNION ALL preserves all observations and duplicates within and across the parts. Plain CREATE TABLE protects an existing raw table from replacement or appending. If it already exists, run the entire marked checks section only; do not automatically drop it.

## Frozen report and sequential comparisons

The report has **14 rows × 5 columns**: check_order, check_name, actual, expected, status. Every actual value matched the following expectation and every status was PASS in the assistant preflight.

| Check | Expected |
|---|---:|
| row_count | 20,275,902 |
| part1_row_count | 10,999,999 |
| part2_row_count | 9,275,903 |
| column_count | 5 |
| varchar_column_count | 5 |
| column_sequence_errors | 0 |
| missing_required_rows | 0 |
| invalid_timestamp_rows | 0 |
| invalid_itemid_rows | 0 |
| unknown_source_file_rows | 0 |
| part1_source_rows_absent_from_table | 0 |
| part1_table_rows_absent_from_source | 0 |
| part2_source_rows_absent_from_table | 0 |
| part2_table_rows_absent_from_source | 0 |

A replaceable session-only TEMP helper holds these aggregate checks. It does not replace the raw table. The four EXCEPT ALL comparisons execute as separate statements: one part and direction at a time, across all five columns. This preserves multiplicity and provenance while avoiding simultaneous comparisons of the entire 20-million-row input. Unknown/NULL provenance is separately checked so an incorrectly tagged row cannot escape the per-part comparisons. The entire checks section rebuilds its temporary aggregate helper when rerun.

Zero differences establish faithful copying, including duplicate occurrences; this report deliberately does not require zero duplicate or conflicting property keys. Copy fidelity is separate from later semantic auditing. Raw text equality also does not prove that an item has a reliable attribute at a particular event time.

## Bounded preflight contract

The [validator](../validation/preflight_retailrocket_properties_import.py) uses only the two property CSVs, frozen source evidence and temporary databases under the ignored repository tmp directory. It never opens the learner database or rereads M5, events or category CSVs. The preflight pins both source hashes before and after, checks exact headers, and compares complete imported/source multisets with the four production EXCEPT ALL statements. The independently executed Python source audit supplies the full-source parsing/count evidence; this preflight does not build a 20-million-row Python Counter or claim an independent Python tuple comparison.

Small synthetic cases verify duplicate/overlapping records, leading zeros, NULL-looking literals, multivalue text and spaces, provenance attribution, missing/invalid fields retained but flagged, missing source parts, existing-table protection and strict malformed-width rejection. Private synthetic Counter comparisons test string and multiplicity preservation; no real identifiers or property values are exported or logged.

Before running, the validator checks available workspace disk and records physical-memory availability. Private runs use two DuckDB threads, a 2GB database memory setting, an 8GB spill limit, a 12GiB private-directory disk budget and a 600-second timeout per phase. At least 12GiB free workspace disk is required at start, with a 2GiB free-space reserve monitored during execution. These are preflight controls, not a guarantee of total-process memory usage. Learner SQL does not change session memory settings; its comparisons remain sequential.

```powershell
python validation/preflight_retailrocket_properties_import.py --duckdb "E:/DuckDB/duckdb.exe" --output "data/retailrocket_properties_import_preflight.json"
```

## Executed result and preservation

DuckDB 1.5.5 imported **20,275,902 records** in **24.720 seconds**. The sequential checks took **196.008 seconds**, for **220.728 seconds** across the two private CLI executions. This timing excludes hashes and fixtures and is not a benchmark. Both source-to-table and table-to-source comparisons returned zero difference rows for each part, across all five raw/provenance fields.

All three focused fixture cases passed. The sampled peak private-directory size was **1,489,874,944 bytes**, approximately 1.49GB; the observations were taken once per second and are not a continuous peak measurement. The private database and spill files were removed after verification. Both property source hashes and metadata, all 14 pinned code/evidence dependencies and 54 historical preflight files remained unchanged. No other source CSV, learner database or historical test suite was opened or rerun.

The [aggregate preflight evidence](../data/retailrocket_properties_import_preflight.json) records the complete 14-row report, code/source fingerprints, resource observations, fixture results and preservation checks. Its report fingerprint is `8fc152f44f1fe524f3a5fcc8ce727c955114574ab4e2c1277f6587c37ac0b150`: ordered compact JSON arrays in output-column order, each followed by LF, with integer counts/order and string labels/status. No real property records or identifiers were exported or logged.

The next learner action is to run SQL56 and return the complete 14-row, five-column report with every status visible. Property semantics, conflicts, time-aware coverage/joins, event staging and RF/funnel/basket definitions are subsequent work. No monetary amount is established by arbitrary numeric-looking property values, and Retailrocket remains separate from M5.
