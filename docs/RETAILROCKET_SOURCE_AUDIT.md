# Retailrocket source-file audit

Completed on 2 November 2026 (Australia/Sydney). The learner reported downloading the four extracted files to `D:/database/retailrocket`. The assistant scanned every CSV record read-only with Python 3.12.14 using only the standard library. The scan and before/after hashes took 44.436 seconds. No source file was modified and no learner database was opened. This source audit is separate from the learner's upcoming raw-import exercise.

## Verified inventory

| File | Bytes | Data records, excluding header | Physical lines, including header | Columns |
|---|---:|---:|---:|---:|
| `events.csv` | 94,237,913 | 2,756,101 | 2,756,102 | 5 |
| `item_properties_part1.csv` | 484,315,749 | 10,999,999 | 11,000,000 | 4 |
| `item_properties_part2.csv` | 408,929,907 | 9,275,903 | 9,275,904 | 4 |
| `category_tree.csv` | 14,454 | 1,669 | 1,670 | 2 |

All four lengths match the [official version 2 file-list metadata](https://www.kaggle.com/api/v1/datasets/list/retailrocket/ecommerce-dataset?datasetVersionNumber=2) checked on 2 November 2026. Their total is 987,498,023 bytes. The two property parts contain 20,275,902 records together, matching the published combined count. This is a local measurement; matching length and record count do not prove publisher-certified byte identity.

The exact observed headers are:

- Events: `timestamp,visitorid,event,itemid,transactionid`.
- Both property parts: `timestamp,itemid,property,value`.
- Category tree: `categoryid,parentid`.

An event record describes one visitor/item interaction. A property record describes a property value for an item at a timestamp; the two parts belong to the same logical source. A category record supplies a category-to-parent relationship. These are different grains, and no join was performed by the Python audit.

## Parsing and field checks

All **38 explicitly recorded checks passed**. This is the number of recorded assertions, not a measure of complete test coverage. Every record passed strict UTF-8 decoding, strict CSV parsing, the exact header contract and the expected field count. No file has a UTF-8 BOM. There were no invalid nonempty identifier values or timestamps. Identifier checks require nonnegative ASCII integer text; timestamps are interpreted as integer Unix milliseconds within the representable UTC range.

Missingness means the exact empty string. Property names and values remain text: no trimming, numeric conversion, splitting, imputation or correction was applied. All property fields were nonempty. The audit does not require property names or values to be numeric.

| Event type | Records | Empty transaction identifiers |
|---|---:|---:|
| view | 2,664,312 | 2,664,312 |
| addtocart | 69,332 | 69,332 |
| transaction | 22,457 | 0 |

There are no unknown event types. All required event fields are present; the 2,733,644 empty transaction identifiers occur on nontransaction events and are retained as expected missing values. The category file has 25 empty parent identifiers and no empty category identifiers. Empty parents are root candidates, not generic parsing failures.

## Observed time coverage

| Source | Minimum UTC timestamp | Maximum UTC timestamp |
|---|---|---|
| Events | 2015-05-03 03:00:04.384 | 2015-09-18 02:59:47.788 |
| Property part 1 | 2015-05-10 03:00:00.000 | 2015-09-13 03:00:00.000 |
| Property part 2 | 2015-05-10 03:00:00.000 | 2015-09-13 03:00:00.000 |

These are UTC interpretations of the supplied integers, not evidence of the website's local timezone. The different source bounds do not establish event-level property coverage. A future time-aware join must use only values available at or before the event and retain unknown attributes when no prior record exists.

## Independent checks and retained duplicates

A separate DuckDB v1.5.5 in-memory audit verified events and category records without opening the learner database. It confirmed the event counts, missingness, time bounds and unchanged hashes. It also observed 1,407,580 distinct visitor identifiers, 235,061 distinct event item identifiers and 17,672 distinct nonempty transaction identifiers. Anonymous identifiers are not verified persons, and the 22,457 transaction-event rows and 17,672 identifiers are not interchangeable with a validated order count.

That independent audit found 458 duplicate groups across the five parsed event fields: 918 involved rows, giving 460 excess occurrences. All occurrences remain in the source. This finding establishes neither their cause nor an appropriate deletion policy; raw import must preserve multiplicity. The category checks found 1,669 unique category identifiers, no missing referenced parent identifiers and no self-parent rows. General cycle detection remains pending.

Evidence: [Python inventory and hashes](../data/retailrocket_source_audit.json), [independent event/category results](../data/retailrocket_independent_checks.json), and [executed independent SQL](../validation/retailrocket_source_check.sql). The independent checks do not constitute a second scan of the property files.

## Reproduce and preserve provenance

Requires Python 3.11 or later, with no third-party packages. From the repository root:

```powershell
python scripts/audit_retailrocket_sources.py --source-dir "D:/database/retailrocket" --output "data/retailrocket_source_audit.json"
```

The script streams the files, retains only aggregate diagnostics, rejects an output path inside the source directory, and returns a nonzero exit code for failed checks or parsing. Source SHA-256, length and modification metadata were unchanged before and after this run. The JSON records the script hash as well as each local file hash. The script does not access the network or invoke a database.

The observed hashes identify this local snapshot. No verified publisher checksum was available, and the original archive hash, exact acquisition time and download channel were not captured by this audit. Modification timestamps are not acquisition timestamps. Current version and license metadata remain documented in the [intake note](RETAILROCKET_INTAKE_ZH.md); the canonical source is the [Retailrocket dataset page](https://www.kaggle.com/datasets/retailrocket/ecommerce-dataset). Raw files and visitor-level records stay outside GitHub.

## Next bounded step and limits

The next learner step is to import only `events.csv` into a separate Retailrocket raw schema with all five fields preserved as text, retaining duplicates and expected empty transaction identifiers, then reconcile the import. This audit does not itself perform that import or constitute learner execution.

Property-key uniqueness, distinct property item count, property conflicts, category cycles, time-aware joins and coverage, session rules, RF segmentation, funnels and baskets remain unimplemented or unaudited. RF has no monetary component here because no transaction amount has been verified. M5 and Retailrocket retain separate business domains and identifiers; this intake does not change accepted M5 analyses or imply that the overall project is complete.
