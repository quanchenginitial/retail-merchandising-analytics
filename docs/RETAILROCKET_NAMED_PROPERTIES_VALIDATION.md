# Retailrocket disclosed-property values and exact category references

This SQL58 contract was frozen on 3 November 2026 before computing the named-property results. It follows accepted SQL57 and examines only the two disclosed property names, **categoryid** and **available**, ahead of a separate typed-staging design. The query does not build a timeline, select current/latest values, repair records or join events.

## Meaning and input boundaries

The [publisher description](https://www.kaggle.com/retailrocket/ecommerce-dataset/home) explains categoryid as the item's category identifier and available as an availability marker: 1 indicates available and 0 otherwise. Other property values are anonymized. This does not identify inventory quantity, verified stockouts, realized demand or a causal business effect. Counts here concern recorded property observations across the supplied history, not the number of unavailable products at a particular instant.

[SQL58](../sql/58_audit_retailrocket_named_properties.sql) reads only **rr_raw.item_properties** and **rr_raw.category_tree**. Schema guards require the accepted five and two VARCHAR columns in their original orders. Source-file counts and reference integrity controls remain visible. The query is read-only, uses no CSV reader and leaves every raw observation unchanged. All other property names remain opaque and retained.

Selection uses exactly property='categoryid' or property='available'. There is no case folding or whitespace trimming. The other-property bucket includes every remaining row, including a NULL property name, to preserve the complete input partition. Distinct-item counts within each named property count non-NULL raw itemid strings; they are not guaranteed counts of validated items.

## Diagnostic definitions

- Availability buckets are exact value='0', exact value='1', and everything else. The other bucket includes NULL, empty text, padded values and other literals; no value is filled with zero or silently recoded.
- A category value is invalid for the stated numeric-text diagnostic if it is NULL/empty, is not ASCII digits only, or cannot fit a nonnegative signed BIGINT. This tests syntax/range without changing the stored string. Leading zeros can pass this diagnostic.
- Category references use **exact raw-text EXISTS** against category_tree.categoryid. There is no numeric reference matching or normalization. For example, a property value '01' does not match a reference ID '1'. Every categoryid row is either exactly matched or unmatched, including malformed/missing values. Invalid-value and unmatched counts can therefore overlap and must not be added as disjoint populations.
- Reference duplicate surplus is sum(n-1) over groups of raw categoryid, including a NULL group. A single NULL is missing only; repeated NULLs can contribute to both missingness and duplicate surplus. Reference missingness counts NULL or exact-empty categoryid. EXISTS prevents duplicated reference rows from multiplying observations, while the separate duplicate control still fails.
- Named missing identity means NULL or exact-empty timestamp or itemid. Named invalid identifier/timestamp counts a row once if either **nonempty** field is not ASCII digits only or does not fit a nonnegative signed BIGINT. It excludes an empty offending field, but can overlap missingness when the other field is invalid. These checks do not convert timestamps to dates or validate typed-key uniqueness.

All semantic exceptions are observations, not zero-target tests. Availability, category-value, reference-match and identity diagnostics can overlap. Numeric-looking property values do not establish a monetary amount. Exact reference presence alone does not validate category hierarchy, historical taxonomy coverage or an as-of join.

## Frozen report

The report has **22 rows × 5 columns**: check_order, check_name, actual, expected, status. Valid baseline input yields **10 PASS controls and 12 INFO observations**. INFO expected=NULL means no success threshold was imposed. Malformed or unknown property values do not cause automatic deletion, repair or forced-zero PASS requirements. If a baseline source/reference control fails, observations instead display BLOCKED while their actual counts remain visible. Schema mismatch raises an explicit error.

| Order | Check name | Expected / role |
|---:|---|---|
| 1 | raw_rows | 20,275,902 |
| 2 | part1_rows | 10,999,999 |
| 3 | part2_rows | 9,275,903 |
| 4 | unknown_source_file_rows | 0 |
| 5 | category_reference_rows | 1,669 |
| 6 | category_reference_duplicate_id_surplus | 0 |
| 7 | category_reference_missing_ids | 0 |
| 8 | categoryid_rows | NULL / INFO |
| 9 | categoryid_items | NULL / INFO |
| 10 | available_rows | NULL / INFO |
| 11 | available_items | NULL / INFO |
| 12 | other_property_rows | NULL / INFO |
| 13 | available_zero_rows | NULL / INFO |
| 14 | available_one_rows | NULL / INFO |
| 15 | available_other_rows | NULL / INFO |
| 16 | category_invalid_value_rows | NULL / INFO |
| 17 | category_unmatched_exact_rows | NULL / INFO |
| 18 | named_missing_identity_rows | NULL / INFO |
| 19 | named_invalid_identifier_or_timestamp_rows | NULL / INFO |
| 20 | property_partition_reconciled | Raw rows |
| 21 | availability_partition_reconciled | Available rows |
| 22 | category_match_partition_reconciled | Categoryid rows |

Rows 20–22 reconcile categoryid+available+other to all rows, exact 0+exact 1+other to availability rows, and exact matched+unmatched to category rows. They are arithmetic controls, not independent evidence of business meaning or source authenticity. Parent IDs are retained in the reference but no recursive hierarchy checks are performed here.

## Bounded validation contract

The [validator](../validation/preflight_retailrocket_named_properties.py) reconstructs the inputs using only the frozen SQL56 property-import and SQL55 category-import prefixes in a disposable private database. It does not rerun their full comparisons or SQL57's key grouping. Fresh hashes and headers of the three CSVs must match the [source audit](../data/retailrocket_source_audit.json) and accepted copy evidence. No event/M5 CSV or learner database is opened.

Small independent Python Counter/set fixtures check every report field: exact availability buckets; malformed and unknown categories; leading-zero exact mismatches; missing/invalid identity overlap; opaque properties/NULL names; duplicated or missing reference IDs without row multiplication; and schema/empty-input behavior. Full-source Python Counters or row exports are not needed or claimed. Only aggregate results are public; item IDs, actual category values and raw records are not exported or logged.

The private run uses two threads, a 2GB DuckDB memory setting, an 8GB spill limit, a 12GiB task-directory budget and a 600-second timeout per phase. It requires 12GiB free workspace disk initially, monitors a 2GiB reserve and records physical-memory availability. Memory settings do not cap total-process RAM, and once-per-second disk samples are not continuous peak measurements. Temporary databases and spills must be removed, with frozen source/dependency and historical-preflight hashes unchanged.

```powershell
python validation/preflight_retailrocket_named_properties.py --duckdb "E:/DuckDB/duckdb.exe" --output "data/retailrocket_named_properties_preflight.json"
```

Measured results will be appended after the one reviewed real audit and saved in [aggregate evidence](../data/retailrocket_named_properties_preflight.json). Typed-key collision checks, numeric category normalization, staging, conflict policy, latest-state selection, event-time property coverage and RF/funnel/basket definitions remain separate work. This raw audit does not establish typed or as-of readiness.

## Executed results

The assistant's single real-source preflight completed on 3 November 2026: **22 rows × 5 columns, with 10 PASS controls and 12 INFO observations**, and no FAIL or BLOCKED rows. Learner SQL58 execution/acceptance remains pending. The original 7,818-byte method contract above is unchanged, with SHA-256 `b4fb0f9d84ad0fb628ff36788be01fe2f8c86b960363fcfdaa1795a5576cbc59`.

| Observation | Actual | Status |
|---|---:|---|
| categoryid_rows | 788,214 | INFO |
| categoryid_items | 417,053 | INFO |
| available_rows | 1,503,639 | INFO |
| available_items | 417,053 | INFO |
| other_property_rows | 17,984,049 | INFO |
| available_zero_rows | 863,086 | INFO |
| available_one_rows | 640,553 | INFO |
| available_other_rows | 0 | INFO |
| category_invalid_value_rows | 0 | INFO |
| category_unmatched_exact_rows | 167 | INFO |
| named_missing_identity_rows | 0 | INFO |
| named_invalid_identifier_or_timestamp_rows | 0 | INFO |

All observation expectations remain NULL. In particular, **167 category-property records have no exact raw-text category-reference match**. This is a count of attribute records, not distinct categories, items or affected events. The records have not been dropped, rewritten, normalized or assigned a guessed category. A zero invalid-format count does not imply that every reference matches. The cause and any appropriate handling remain follow-up work; this result does not establish malformed source data or a stockout.

Both disclosed properties have records for 417,053 distinct raw item identifiers. That historical presence is not a measure of coverage at event time. The available 0/1 buckets describe source attribute observations, not current item states, time-weighted availability, inventory quantities or verified operational causes. Other property records remain intact and opaque. This audit does not validate typed/canonical keys or perform an event join.

The initial controls matched 20,275,902 property rows, part counts 10,999,999 and 9,275,903, no unknown provenance, 1,669 reference rows and no duplicate/missing reference IDs. Partition checks reconcile all property rows, all 1,503,639 availability records and all 788,214 category records. They verify accounting identities, not that every category is resolved. The [full aggregate report](../data/retailrocket_named_properties_preflight.json) has fingerprint `6eb6961f3542f88cac1ea3f6974ab63301c09e13a253d5c477c9d363b51ecd34` (ordered compact JSON arrays, LF per row, integer counts and null observation expectations).

Three focused synthetic fixture families passed. Independent Python sets/Counters and hand-calculated counts checked exact membership, leading-zero mismatches, NULL/empty/other buckets, overlapping identity diagnostics, duplicated/missing reference IDs without multiplication, empty-input reports and schema rejection. Incompatible raw numeric types can fail DuckDB function binding before the explicit schema guard; the negative fixture accepts that specific binding rejection or the explicit guard error. No observed count target was changed to fit the source outcomes.

The private input reconstruction used only the frozen SQL55 and SQL56 import prefixes and took **37.331 seconds**; the single read-only SQL58 audit took **3.166 seconds**, for **40.497 seconds** total, excluding hashes and fixtures. The sampled private-directory peak and final database size were 423,374,848 and 423,374,848 bytes respectively. These measurements are not a benchmark or a continuous peak guarantee.

All three source hashes and metadata, 12 code/evidence dependency pins and 56 historical preflight files remained unchanged. Private database and spill files were removed. No learner database, event/M5 source, SQL55/56 full-comparison rerun or SQL57 key regrouping was used; no real item/category values or raw records were exported or logged.

The learner's next step is to run SQL58 and return the complete 22-row report, including the INFO rows. Exact-unmatched category references remain visible for investigation before downstream interpretation. Staging and event-time attribute linkage remain subsequent work.

## Learner screenshot acceptance — 3 November 2026

The screenshot shows all **22 rows × 5 columns = 110 field positions**, with **107 complete fields** directly visible: 54 integers, twelve explicit NULL expectations, nineteen complete check names and twenty-two complete statuses. All five headers are visible. The status split is **10 PASS controls and 12 INFO observations**, with no FAIL or BLOCKED rows.

Three check-name endings are cropped:

| Check order | Full label resolved from the frozen contract | Visibility |
| ---: | --- | --- |
| 6 | category_reference_duplicate_id_surplus | Prefix visible; ending cropped |
| 19 | named_invalid_identifier_or_timestamp_rows | Prefix visible; ending cropped |
| 22 | category_match_partition_reconciled | Prefix visible; ending cropped |

The complete order-21 label, availability_partition_reconciled, is visible, including its ending. No numeric, expected-NULL or status cell is cropped. Each of the three partial names agrees with a legible prefix and fixed row position, but its full text is supplied by the frozen contract; the screenshot does not show all 110 field values in full.

The screenshot was independently transcribed before comparison with the frozen report. Numeric thousands separators were removed, displayed [NULL] expectations were retained as JSON null, and only the three documented labels were resolved. The resulting full aggregate report matches the frozen fingerprint above with zero mismatches. The [learner acceptance record](../data/retailrocket_named_properties_learner_acceptance.json) separates visible transcription, partial-label evidence and complete resolved results. INFO rows remain observations rather than zero-target success checks.

This later record establishes learner acceptance and supersedes the earlier pending status and run request for current progress. The entire prior method, including its 7,818-byte frozen contract and executed-results section, is retained byte for byte. No learner database was opened, and no SQL, source audit, fixture or historical suite was rerun for acceptance. SQL58, its validator, preflight and pinned prior evidence remain unchanged. No screenshot, real item/category values or raw records are published, and learner conceptual understanding remains untested.

The accepted 167 exact-unmatched category-property records retain the interpretation limits above: they are not a count of distinct categories, items or affected events, and their cause is unverified. Availability observations do not establish current item states, inventory quantities or stockout causes. Typed staging, canonical references, further investigation and event-time attribute linkage remain separate work.
