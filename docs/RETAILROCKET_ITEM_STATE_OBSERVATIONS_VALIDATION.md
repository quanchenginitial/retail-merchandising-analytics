# Retailrocket named item-state observations staging

This SQL65 contract was frozen on 6 November 2026 before executing the new stage. It builds on the accepted [raw property import](../data/retailrocket_properties_import_learner_acceptance.json), [candidate-key audit](../data/retailrocket_property_keys_learner_acceptance.json) and [named-property audit](../data/retailrocket_named_properties_learner_acceptance.json). This step prepares explicitly named category and availability observations for later temporal modelling.

## Scope and fixed transformation

[SQL65](../sql/65_stage_retailrocket_item_state_observations.sql) creates **rr_stg.item_state_observations** from **rr_raw.item_properties**. The five columns, in order, are timestamp BIGINT, itemid BIGINT, property VARCHAR, value VARCHAR and source_file VARCHAR. Selection is exactly property IN ('categoryid','available'), without trimming or recoding.

The selected subset contains **2,291,853 observations**: **788,214 categoryid** records and **1,503,639 available** records. The other **17,984,049** records remain in the raw table with opaque property meanings. This is an intentional subset of the **20,275,902** raw observations, not a claim that the whole property log has been typed or interpreted. The complement is raw row count minus the exact selected count, so even NULL or unrecognised property labels remain in the exhaustive raw complement rather than disappearing from its reconciliation.

Selected timestamp and itemid strings must be ASCII digits fitting a nonnegative signed BIGINT and roundtrip back to exactly the original VARCHAR spelling. The rule rejects missing values, spaces, signs, decimals, overflow and even isolated leading-zero key spellings. Exact roundtrip establishes injectivity separately for both fields; numeric aliases are not silently merged. No date or timezone conversion occurs here.

The **value column stays VARCHAR**. Category values follow the already observed SQL58 rule: ASCII digits fitting BIGINT, with no additional canonical-spelling requirement because they are not cast for storage. A category value such as '001' must remain exactly '001'. Availability values remain the literal strings '0' or '1'. Unknown category reference values are retained as observations; the prior **167 unmatched category records** are preserved by complete selected-row equality, without a new category lookup, a new unmatched-count claim or an invented repair. No category CSV or event table participates in this stage.

The candidate key is **(itemid, property, timestamp)**. It excludes value and source_file. The earlier raw-key audit found this key unique across the whole supplied log, so the selected subset must also be unique. The creation guard freshly checks selected raw key uniqueness, and the report checks typed key uniqueness. A duplicate key is rejected whether it repeats the same value, carries conflicting values or spans both physical source parts. No row is chosen or deduplicated. These are validated conditions at execution, not declared database primary-key constraints.

## Guard and preservation

Creation requires the exact five-VARCHAR raw schema/order, total rows **20,275,902**, part counts **10,999,999** and **9,275,903**, valid source_file tags, the named/complement counts, nonempty selected input, valid selected key/value strings and unique selected candidate keys. The source parts are provenance labels, not separate products or successive non-overlapping periods.

Plain CREATE TABLE prevents replacement of an existing target. The singleton guard is LEFT JOINed to the selected records, and every output field uses a guarded CASE. Invalid or empty selected input therefore raises an error in the atomic CREATE TABLE AS instead of leaving an empty or partial target. CREATE SCHEMA IF NOT EXISTS may still leave an empty schema after a failed creation; no whole-script rollback is claimed.

If the table already exists, run only the query after **-- CHECKS: if rr_stg.item_state_observations already exists, run only the query below.** The checks cast the two typed keys back to VARCHAR and compare all five fields against the exact selected raw multiset using EXCEPT ALL in both directions. This detects value changes, source-part changes, missing records and extra occurrences even when overall counts are unchanged. The raw table is never updated, filtered in place or replaced.

## Frozen 22-row report

Output is **22 rows × 5 columns**: check_order, check_name, actual, expected and status. Order/count fields are integers; the two INFO expectations are NULL. Valid input produces **20 PASS controls and 2 INFO observations**. INFO values are displayed only if every control passes; otherwise their actual values are NULL and status is BLOCKED.

| Order | Check | Expected |
|---:|---|---:|
| 1 | raw_rows | 20,275,902 |
| 2 | raw_part1_rows | 10,999,999 |
| 3 | raw_part2_rows | 9,275,903 |
| 4 | raw_schema_mismatch | 0 |
| 5 | raw_unknown_source_rows | 0 |
| 6 | staging_rows | 2,291,853 |
| 7 | staging_schema_mismatch | 0 |
| 8 | categoryid_rows | 788,214 |
| 9 | available_rows | 1,503,639 |
| 10 | other_property_rows | 17,984,049 |
| 11 | missing_required_rows | 0 |
| 12 | negative_numeric_rows | 0 |
| 13 | value_rule_violations | 0 |
| 14 | unexpected_property_rows | 0 |
| 15 | unknown_source_file_rows | 0 |
| 16 | candidate_key_surplus | 0 |
| 17 | raw_key_value_violations | 0 |
| 18 | raw_only_rows | 0 |
| 19 | staging_only_rows | 0 |
| 20 | source_contract_violations | 0 |
| 21 | selected_part1_rows | NULL; INFO |
| 22 | selected_part2_rows | NULL; INFO |

raw_key_value_violations counts selected raw records failing at least one key or value rule, not a sum of overlapping errors. candidate_key_surplus is selected row count minus distinct candidate keys; it covers duplicate or conflicting keys without separately classifying their causes. raw_schema_mismatch and source_contract_violations are 0/1 indicators; staging_schema_mismatch counts mismatched column/type positions. The selected per-part counts are new descriptive observations and are not assigned expected values in advance. Together they reconcile to the staged subset after all controls pass.

## Independent bounded preflight

The [validator](../validation/preflight_retailrocket_item_state_observations.py) reads only item_properties_part1.csv and item_properties_part2.csv among real inputs. It reconstructs all raw observations using only the frozen SQL56 import prefix, then executes SQL65 once. It does not rerun SQL56's full comparisons, SQL57–59 audits, or any event/M5 analysis, and it never opens the learner database.

Python scans both CSVs independently, verifies full per-part counts, and selects only the two exact property names. It validates selected key/value rules and writes sorted chunks of at most 50,000 complete selected tuples inside a private temporary directory. The other raw properties are counted as the complement and are never added to those comparison chunks. A bounded heap merge is compared tuple by tuple against two private read-only CLI streams: the selected raw records and the typed target projected back to the same five text fields. Both streams sort those text expressions in the same field order. This is complete selected multiset equality including source_file and original value spelling, not a sample or digest-only check. No giant Python tuple Counter is created for real records.

Python independently computes the report's source/subset/part counts and checks exact full-row preservation. The sorted tuple's first three fields are timestamp, itemid and property, a reordering of the candidate key. Counting adjacent equal three-field keys therefore independently checks candidate-key surplus without retaining a large set. Both streams must have zero key surplus, consistent with the prior accepted full-log key baseline. The raw and staged stream counts and selected part counts must agree with the independent CSV selection. Raw opaque records are reconstructed by the frozen import prefix and retained; this preflight does not repeat full opaque-value comparisons.

Fixtures cover retained category values '001' and an unknown numeric reference, exact availability strings, opaque records excluded from the stage but preserved raw, text sorting of numeric keys with different lengths, same-count value/provenance mutations, duplicate and conflicting candidate keys across source parts, guarded empty/invalid selected inputs, populated wrong raw schema/order, and a changed existing target protected from a second CREATE. Invalid creation must leave no target and retain raw fixture records. INFO observations must block if any control fails.

The fixed plan has four real CLI phases: full raw prefix reconstruction; SQL65 creation/checks; selected raw comparison stream; selected staged comparison stream. Each uses two threads, 1GB memory, a 2GB spill limit and a 120-second timeout, with a watchdog on streaming phases. At least 6GB of workspace free space is required, and the private directory budget is 5GB. Python's source sort has a 50,000-tuple chunk cap. These settings do not guarantee a total-process memory cap; directory observations are not continuous peaks.

The source files total **893,245,656 bytes**. Their frozen hashes and metadata are checked before and after. Code/evidence dependencies and all earlier preflight files must remain unchanged. Private sorted chunks contain selected source records temporarily and are removed together with the database and spills. No identifiers, source records or unknown-category histories enter public artifacts or logs. Only aggregate evidence, hashes and resource observations are retained.

```powershell
python validation/preflight_retailrocket_item_state_observations.py --duckdb "E:/DuckDB/duckdb.exe" --output "data/retailrocket_item_state_observations_preflight.json"
```

Measured results will be appended and saved in [aggregate evidence](../data/retailrocket_item_state_observations_preflight.json). This stage stores observations, not effective-date intervals or current product states. Historical validity, latest-known property selection, event-time joins and missing-reference handling remain separate steps. Availability is not an exact inventory quantity, and no conversion, sales amount or causal effect is inferred here.

## Executed results

The assistant's isolated SQL65 staging and checks completed on 6 November 2026: **22 rows × 5 columns, with 20 PASS controls and 2 INFO observations**. There are no FAIL or BLOCKED rows. Learner SQL65 execution and screenshot acceptance remain pending. The frozen 10,388-byte method prefix remains unchanged, with SHA-256 `b83200620a8734c1da2e8b0948886bd937e5007591afaad7109709fa345c4836`.

The full raw log contains **20,275,902 observations**. The new table contains only **2,291,853 named observations**: **788,214 categoryid** and **1,503,639 available** records. The remaining **17,984,049 observations** stay in the raw table as the intentionally opaque complement. The two newly measured INFO values are **1,243,692 selected records from part 1** and **1,048,161 from part 2**; together they reconcile exactly to the staged subset. Their expected cells are NULL.

Independent Python selection and both private read-only streams matched all **2,291,853 selected occurrences across all five fields**, including exact value spelling and source-file provenance. The raw and typed streams each had **zero candidate-key surplus**; the complete report matched the independent reference. This proves preservation of the selected records, including the previously observed cohort of **167 unmatched category-reference observations**, without looking up, repairing or recounting that cohort. The other raw properties were reconstructed with the frozen SQL56 prefix and counted, but their full values were not compared again in this selected-scope preflight.

All **three fixture families** passed. The valid fixture preserved category VALUE spellings such as '001' and a numeric value with a long zero prefix, retained an unknown numeric reference, counted an opaque NULL-property record in the complement, and checked actual sorted raw and staged streams. **Twenty invalid-input subcases** rejected creation atomically and left raw fixtures unchanged, including empty input, canonical-key violations, invalid values, wrong counts, wrong populated schema/order, and duplicate or conflicting candidate keys across parts. Same-count value and provenance changes were detected by complete tuple comparisons and blocked both INFO values. A second CREATE preserved an existing changed target.

The independent two-source scan, selection and external sort took **37.272 seconds**. Full raw prefix reconstruction and SQL65 staging/checks took **36.609** and **27.180 seconds**, respectively. The read-only raw and staged comparisons took **15.091** and **12.725 seconds**. These timings exclude hashing and fixture work and are not performance benchmarks. The fixed four CLI phases used two threads, 1GB memory, a 2GB spill limit and a 120-second limit per phase.

Python created **46 private sorted chunks** containing only selected source tuples, totalling **139,673,953 bytes**. The private database was **441,724,928 bytes** before cleanup; the largest post-phase private-directory observation was **581,398,881 bytes**, not a continuously measured peak. Every temporary database, spill and selected-record chunk was removed. No source records or identifiers entered public artifacts or logs.

Both property CSV hashes and metadata, **12 pinned code/evidence dependencies**, and **63 historical preflight files** remained unchanged. The learner database, other source CSVs and old full audit suites were not opened or rerun. The [aggregate evidence](../data/retailrocket_item_state_observations_preflight.json) records report fingerprint `d51af897958e1cefe8cf4e31d2fc259fe4d44327e2eb2f67d49338ebfcf6db56` and the independent count, tuple, candidate-key, resource and cleanup checks.

SQL65 establishes a typed observation history for the two named properties. It does not establish effective-date intervals, current product states, event-time associations, deduplication, repaired category references, exact inventory quantities, conversion rates or monetary outcomes. The next action remains the learner's SQL65 execution and screenshot review.

## Learner screenshot acceptance — 9 November 2026

The learner supplied the SQL65 DBeaver result on 9 November 2026 (Australia/Sydney). All **22 rows × 5 columns, 110 fields** are completely visible and match the assistant preflight: **20 PASS controls and 2 INFO observations**, with all twenty-two check names complete and both NULL expectations visible. There are no cropped or reconstructed labels. See the [learner acceptance record](../data/retailrocket_item_state_observations_learner_acceptance.json).

The visibility accounting is **22 integer row orders + 42 integer actual/expected values + 2 NULL expectations + 22 complete labels + 22 statuses = 110 fields**. Thousands separators are removed for JSON integer storage; the two displayed [NULL] values remain JSON null. The complete ordered report fingerprint is `d51af897958e1cefe8cf4e31d2fc259fe4d44327e2eb2f67d49338ebfcf6db56`.

The accepted snapshot contains **2,291,853 named observations**, comprising **788,214 categoryid** and **1,503,639 available** rows. The raw total remains **20,275,902**, including the **17,984,049** deliberately unselected opaque observations. The selected source-part counts are **1,243,692** and **1,048,161**; their expected values remain NULL and their statuses INFO. Schema, key/value contract, required-field, candidate-key and both full selected-row reconciliation controls pass.

Only timestamp and itemid are typed as BIGINT; property, value and source_file remain original text. The accepted complete selected-row equality preserves the earlier **167 unmatched category-property observations**, without another reference lookup, unmatched-count computation or repair. Each selected row is a historical property observation, not a distinct product, current-state snapshot or inventory quantity.

No source CSV, learner database, SQL preflight or fixture was opened or rerun for this acceptance. No screenshot, source identifiers or property histories were copied to the public repository. Frozen SQL, validator, preflight and dependencies remain unchanged. All **14,451 prior method bytes**, including the **10,388-byte frozen contract prefix** and prior historical learner-pending statements, are preserved byte for byte; this appended record establishes current learner acceptance.

SQL65 establishes the checked typed observation history for the two named properties. Property timestamp conversion and UTC interpretation, historical validity intervals, event-time associations and behaviour metrics remain subsequent work. This screenshot establishes no exact inventory, conversion, monetary or causal outcome, and does not test learner conceptual understanding.
