# Retailrocket exact-unmatched category cohort and numeric diagnostics

This SQL59 contract was frozen on 3 November 2026 before computing new cohort outcomes. Accepted [SQL58 evidence](../data/retailrocket_named_properties_preflight.json) found **167 exact-unmatched category-property records among 788,214 categoryid records**. The 167 is a record count, not a count of different items, category values or affected events. SQL59 characterizes that fixed cohort and tests whether a strictly defined numeric interpretation would find reference candidates. It does not decide that any interpretation is a correction.

## Cohort and identity contract

[SQL59](../sql/59_audit_retailrocket_unmatched_categories.sql) reads only **rr_raw.item_properties** and **rr_raw.category_tree** with their accepted five and two VARCHAR columns in source order. It selects exactly property='categoryid' and retains every record for which raw value has no exact-text reference match under EXISTS. NULL values cannot match NULL reference IDs. Reference duplicates cannot multiply the cohort, and their surplus is checked separately.

Item, raw category-value and raw timestamp observations count distinct non-NULL original strings within the cohort. They are not counts of events, validated categories or calendar dates. Both part counts retain raw record multiplicity and source_file provenance. No item or timestamp key is normalized; no raw identifier, category value or row history is published. Affected-item history analysis is deferred.

## Numeric interpretation is diagnostic only

Eligibility requires ASCII digits only and a successful nonnegative signed BIGINT conversion. NULL, empty text, signs, spaces, decimal/scientific notation, non-ASCII digits and out-of-range values are ineligible. No trimming is allowed. Leading zeros are eligible, so '007' and '7' have the same diagnostic integer while remaining different original strings.

Eligible reference IDs are grouped by that integer, counting **distinct raw reference spellings**. More than one spelling creates an ambiguous normalized ID. Two copies of the same raw reference ID do not create numeric ambiguity, although they fail the separate raw duplicate control. Reference numeric-ineligible rows are observations; eligible reference rows equal total reference rows minus that count. This diagnostic never creates a normalized reference table or a new key guarantee.

Eligible unmatched cohort records are partitioned into:

1. Exactly one distinct raw reference spelling with the same diagnostic integer.
2. Multiple raw reference spellings with that integer: ambiguous.
3. No reference spelling with that integer.

A one-row-per-integer reference summary prevents row multiplication. Ineligible cohort records remain in a separate bucket. Every target record stays exact-unmatched throughout: neither unique nor ambiguous numeric candidacy changes the accepted baseline or authorizes an update, coercion or repair. A numeric candidate need not represent the intended category. Absence of a candidate does not establish why a reference is missing.

Raw reference duplicate surplus is sum(n-1) over raw categoryid groups, including a NULL group. A lone NULL is missing but not a duplicate; repeated NULLs can affect both controls. Missing reference IDs are NULL or exact-empty strings. Unknown source_file includes NULL and any value outside the two accepted property basenames.

## Frozen report

The report has **22 rows × 5 columns**: check_order, check_name, actual, expected, status. Valid baseline input gives **10 PASS controls and 12 INFO observations**. New diagnostic counts have expected=NULL and no zero or other success threshold. Failed baseline controls leave their actual values visible and mark observations BLOCKED; a wrong raw schema raises an error.

| Order | Check name | Expected / role |
|---:|---|---|
| 1 | raw_rows | 20,275,902 |
| 2 | categoryid_rows | 788,214 |
| 3 | exact_unmatched_rows | 167 |
| 4 | category_reference_rows | 1,669 |
| 5 | reference_duplicate_id_surplus | 0 |
| 6 | reference_missing_ids | 0 |
| 7 | unknown_source_file_rows | 0 |
| 8 | unmatched_items | NULL / INFO |
| 9 | unmatched_raw_category_values | NULL / INFO |
| 10 | unmatched_raw_timestamps | NULL / INFO |
| 11 | unmatched_part1_rows | NULL / INFO |
| 12 | unmatched_part2_rows | NULL / INFO |
| 13 | reference_numeric_ineligible_rows | NULL / INFO |
| 14 | reference_ambiguous_normalized_ids | NULL / INFO |
| 15 | unmatched_numeric_eligible_rows | NULL / INFO |
| 16 | unmatched_numeric_ineligible_rows | NULL / INFO |
| 17 | unmatched_numeric_unique_reference_rows | NULL / INFO |
| 18 | unmatched_numeric_ambiguous_reference_rows | NULL / INFO |
| 19 | unmatched_numeric_no_reference_rows | NULL / INFO |
| 20 | unmatched_part_rows_reconciled | Exact-unmatched rows |
| 21 | unmatched_numeric_eligibility_reconciled | Exact-unmatched rows |
| 22 | unmatched_numeric_candidate_partition_reconciled | Numeric-eligible cohort rows |

The final controls reconcile the two cohort part counts, eligible+ineligible cohort records, and unique+ambiguous+no-reference candidate buckets. They are arithmetic consistency checks, not evidence of source authenticity, intended category meaning or business impact.

## Bounded validation contract

The [validator](../validation/preflight_retailrocket_unmatched_categories.py) reconstructs only the two raw tables using frozen SQL55/56 import prefixes in a disposable private DuckDB database. It pins the three source files, accepted copy evidence and SQL58's 167-record baseline. It does not rerun SQL58, SQL57 grouping, earlier full comparisons or other historical suites, and it opens no event/M5 source or learner database.

Independent tiny Python set/Counter fixtures check every aggregate field: exact cohort membership, leading zeros, ineligible text/overflow/NULLs, unique/ambiguous/missing numeric candidates, exact reference duplicates without false ambiguity, preserved multiplicity, zero-size cohorts, invalid baselines and schema guards. No full real-source Python Counter or row-level export is used or claimed. The real audit is run once after review.

Private execution uses two threads, a 2GB DuckDB memory setting, an 8GB spill limit, a 12GiB task-directory budget and a 600-second timeout per phase. It requires 12GiB free disk initially and monitors a 2GiB reserve. Physical-memory availability is recorded; memory settings are not a total-process cap, and sampled disk observations are not continuous peaks. Temporary databases/spills must be removed and source, code/evidence and historical-preflight hashes preserved.

```powershell
python validation/preflight_retailrocket_unmatched_categories.py --duckdb "E:/DuckDB/duckdb.exe" --output "data/retailrocket_unmatched_categories_preflight.json"
```

Measured results will be appended and saved in [aggregate evidence](../data/retailrocket_unmatched_categories_preflight.json). No transformation is persisted. Typed staging, numeric reference policy, item/timestamp key normalization, event-time joins, source-cause claims and business impact remain separate work.

## Executed results

The assistant's single source preflight completed on 3 November 2026 with **22 rows × 5 columns: 10 PASS controls and 12 INFO observations**, and no FAIL or BLOCKED rows. Learner execution and acceptance remain pending. The frozen 7,145-byte method prefix above is unchanged, with SHA-256 `9be6f7027aaaa81a126103a740470c8c4781ae180ebf9df5f493a2fa0484d9d4`.

| Observation | Actual | Status |
|---|---:|---|
| unmatched_items | 137 | INFO |
| unmatched_raw_category_values | 30 | INFO |
| unmatched_raw_timestamps | 7 | INFO |
| unmatched_part1_rows | 92 | INFO |
| unmatched_part2_rows | 75 | INFO |
| reference_numeric_ineligible_rows | 0 | INFO |
| reference_ambiguous_normalized_ids | 0 | INFO |
| unmatched_numeric_eligible_rows | 167 | INFO |
| unmatched_numeric_ineligible_rows | 0 | INFO |
| unmatched_numeric_unique_reference_rows | 0 | INFO |
| unmatched_numeric_ambiguous_reference_rows | 0 | INFO |
| unmatched_numeric_no_reference_rows | 167 | INFO |

The accepted exact-unmatched baseline remains **167 records**. Those records cover 137 distinct raw item identifiers, 30 distinct raw category values and seven distinct raw timestamps; the two source parts contribute 92 and 75 records. These counts have different grains and are not event-impact measures.

All 1,669 reference rows meet the specified numeric eligibility rule, and no diagnostic integer corresponds to multiple raw reference spellings. All 167 cohort records are also eligible, but **none has any reference candidate under this numeric interpretation**. The three candidate buckets reconcile as 0 unique + 0 ambiguous + 167 absent = 167 eligible records. This test therefore supplies no numeric-recoding resolution for the cohort. It does not identify the cause of the missing references or establish that the source values are erroneous. All original observations remain retained.

Every INFO expected cell remains NULL; observed zeros were not imposed as success targets. The [saved aggregate report](../data/retailrocket_unmatched_categories_preflight.json) has fingerprint `67e062794f95028503399c7b822dff408eeb1af1ff78ac3c47f6d3f0e517089f`: ordered compact JSON arrays in output-column order, each followed by LF, with integer counts and JSON null observation expectations. No real category values, item IDs or individual histories are published.

Three focused fixture families passed. Independent Python sets/Counters and hand counts verified all numeric-candidate buckets, leading zeros, whitespace, overflow, non-ASCII digits, NULLs and duplicate cohort occurrences. Exact reference duplicates failed raw integrity without falsely creating multiple numeric candidates. Zero-cohort, invalid-baseline and schema fixtures preserved the documented report or raised the intended error.

DuckDB 1.5.5 reconstructed the two raw tables in **37.766 seconds** and ran SQL59 once in **2.298 seconds**, for **40.064 seconds** total excluding hashes and fixtures. The sampled private-directory peak and final database size were both **423,899,136 bytes**. These observations are not a performance benchmark or continuous peak guarantee. The private database and spills were removed.

All three source hashes and metadata, 14 pinned code/evidence dependencies and 57 historical preflight files remained unchanged. No learner database, event/M5 source, prior full-comparison rerun, SQL57 grouping or SQL58 audit rerun was used. The next learner action is to run SQL59 and return the complete report with INFO distinct from PASS. Decisions about unmatched-reference handling and typed staging remain separate, explicit work.
