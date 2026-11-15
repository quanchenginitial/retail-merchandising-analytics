# SQL90: ordered RF summary selection and CSV verification

## Purpose and scope

Prepare one learner export of the accepted rr_bi.rf_segment_summary table for later BI use. SQL90 is only a read-only SELECT of its seven columns, ordered by reference_timestamp_ms,recency_order,frequency_order. It neither rebuilds the table nor recalculates RF measures. It selects all sixteen cells without a TOTAL row, percentages, Top-k measures or original identifiers.

Column order is reference_timestamp_ms,recency_order,recency_band,frequency_order,frequency_band,visitor_ids,candidate_baskets. Five numeric fields are nonnegative integers; the two band fields are labels. The fixed reference remains 1442545187788. Counts still sum to 11,719 transaction-recorded IDs and 17,672 full-window candidate baskets. Their business interpretation is unchanged from accepted SQL89.

## Learner export contract

The learner executes SQL90 in DBeaver and exports the actual result grid to D:/database/retailrocket/rf_segment_summary.csv. Use all seven columns and sixteen rows, UTF-8 encoding, a comma delimiter, one header row with the column names as shown, and plain integers without thousands separators, decimal notation or row numbers. Standard CSV quoting is allowed. UTF-8 BOM is accepted and recorded; it changes the byte hash but not the typed semantic hash. The export is a new local file. If the suggested filename exists, use a different filename rather than overwriting it.

No assistant-created CSV from stored proof is supplied as a learner export. Assistant preparation and the user's actual exported file are separate evidence. The latter remains pending until the user supplies the file location and its contents are checked.

## Read-only CSV verifier

The small validator accepts --csv pointing to an existing learner-exported file. It reads no database or original event/property data, writes no files, and prints a JSON result. It pins the accepted SQL89 aggregate preflight and learner acceptance, then checks the file against the accepted sixteen typed aggregate rows.

Require an exact seven-column header, exactly sixteen data rows, no blank/TOTAL/row-number rows, canonical nonnegative integer text, exact labels and row order, a constant reference, sixteen unique RF keys and both additive totals. UTF-8 decoding is strict and a leading UTF-8 BOM is explicitly recorded. A 1 MiB bound prevents an accidentally selected large source file from being read in full. A changed file size or modification time during the check is rejected.

Record SHA-256 of the exact CSV bytes and SHA-256 of typed rows serialized as compact JSON arrays, in file order with LF after each row and no header. Thus a BOM, permitted CSV quoting or line-ending difference may change file bytes while preserving semantics. Neither floating-point parsing, trimming nor guessed formatting repairs are used. Failures produce a nonzero exit code and a concise diagnostic; the file is not modified.

## Assistant preparation proof

Use only the already accepted SQL89 sixteen-row aggregate evidence. Load those aggregate values into a tiny temporary DuckDB table with the accepted seven types; execute SQL90 exactly once in read-only mode and compare all returned column names, types, values, order and semantic hash to the accepted proof. Check temporary database bytes unchanged across the read-only selection and remove the temporary database afterward. Do not open the learner database, parse events.csv, call earlier analytical SQL, rebuild RF/rank streams or rerun historical suites.

Minimal in-memory serialization checks cover a plain UTF-8 CSV, the equivalent BOM form, and rejection of a formatted integer and an extra TOTAL row. These temporary in-memory test strings are synthetic verifier fixtures, not a delivered file or evidence of learner export. No CSV is written during preparation.

Freeze this method before the small preparation run and append observed results afterward. The preparation JSON records exactly what was tested and keeps learner_export_received=false and learner_export_validated=false. Power BI import, relationships, measures, visuals and interaction tests remain future work.

## Observed assistant preparation — 2026-11-15

The single small preparation run passed in 0.625 seconds. It loaded only the sixteen accepted SQL89 aggregate rows into a temporary seven-column typed table, then ran SQL90 once with DuckDB's read-only flag. All 112 data values, column names, five BIGINT/two VARCHAR types and row order matched. The additive counts were 11,719 IDs and 17,672 candidate baskets, with fixed reference 1442545187788. No original data, learner database, earlier analytical SQL or historical test suite was used.

The four in-memory serialization cases passed: canonical UTF-8, a BOM form with the same semantic hash and different byte hash, rejection of a formatted integer, and rejection of an extra TOTAL row. No CSV file was created or delivered. These are assistant verifier fixtures, not a learner export.

The preparation used two DuckDB CLI phases, with two threads, a 128 MB memory setting and a 30-second limit per phase. Loading took 0.485 seconds; the read-only schema and SQL90 selection phase took 0.125 seconds. Temporary database SHA-256 was 7c755e99dbbc54efc8f6dc73c5156496574125e5297f5522b51e1af55cf71c5b both before and after selection. The temporary database and its files were removed. Dependencies did not change during the run.

The full ordered aggregate semantic SHA-256 is cbcc0bc2cb3daf2ee510ae138b8091e3fd29277a34ea34ef25b348fcff0ff33e, identical to accepted SQL89. The frozen method preceding this appendix is 4,193 bytes with SHA-256 c42bda0113fa06c10fd24e5c13678d22e9bcd6a6a017c14389fa74d75ce170d7. The temporary preparation harness had SHA-256 c1be050f64839f7b11c060b09f3591d3acbebe404cd19524c9b48360acf6f1b4; it loaded aggregate literals into the isolated table, checked the four memory fixtures, compared the readonly output against the accepted rows, and wrote only the preparation JSON. It is not an additional public deliverable.

The reusable check for the actual learner file, from the repository directory, is:

```text
python validation/validate_retailrocket_rf_bi_export.py --csv "D:/database/retailrocket/rf_segment_summary.csv"
```

Use the actual new filename if a different name was chosen. This command reads the supplied CSV, prints PASS/FAIL plus byte and semantic fingerprints, and does not modify it. It has not been run against a learner export in this preparation step. No actual learner CSV byte hash exists in the evidence yet: learner_export_received=false and learner_export_validated=false. SQL90 is ready for the learner's export; CSV validation and subsequent Power BI work remain pending.
