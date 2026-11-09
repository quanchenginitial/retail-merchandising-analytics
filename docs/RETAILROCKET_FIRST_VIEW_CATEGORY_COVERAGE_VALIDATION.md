# Retailrocket category coverage at eligible first view

This SQL73 contract was frozen on 9 November 2026 before fixtures or source execution. Before building a category-segmented funnel, it asks whether each pair in the accepted seven-day-eligible cohort has a usable category observation at its first observed view, and whether that category exists in the supplied static reference. Temporal and reference gaps remain visible rather than being silently dropped.

## Readsets, cohort and classification

SQL73 is read-only. It reads ten fields from rr_mart.events_enriched: the original timestamp/visitorid/event/itemid/transactionid fields and categoryid_value, categoryid_from_ms, categoryid_to_ms, categoryid_source_file, categoryid_coverage. It reads only categoryid from rr_core.dim_category, not parent/root/depth. Required names/types are checked without asserting the full seventeen-column fact or four-column dimension schema. Availability and stored UTC fields are outside scope.

The cohort is unchanged from SQL72: each visitor-item pair's earliest observed view plus 604800000 milliseconds must be <= MAX(timestamp) over all event types. The accepted endpoint is 1442545187788 ms (2015-09-18T02:59:47.788000Z), giving cutoff 1441940387788 ms (2015-09-11T02:59:47.788000Z). The resulting eligible population must be **2,042,310 pairs**. Seven elapsed days is the chosen rule; first observed is not necessarily first-ever, and the global log boundary does not prove continuous capture or complete individual exposure.

For each eligible pair, all view occurrences tied at that pair's earliest timestamp are inspected. They must have exactly one distinct **NULL-aware five-field category tuple** (value/from/to/source_file/coverage). Only after that consistency check may DISTINCT collapse identical snapshots. No arbitrary ROW_NUMBER, MIN value, LIMIT or tie selection is used. A conflict blocks the entire output rather than assigning a potentially misleading category. Original source duplicate surplus 460 remains preserved; collapsing identical first-view occurrences defines one snapshot per pair, not source deduplication.

The fixed output is **five rows × four columns**: coverage_status, eligible_pairs, share_of_eligible_pairs_pct, check_status. Row order is MAPPED, UNKNOWN_REFERENCE, BEFORE_FIRST, NO_HISTORY, TOTAL.

| Status | Meaning |
|---|---|
| MAPPED | The first-view snapshot is temporally MATCHED and its safely parsed category ID exists in the supplied reference. |
| UNKNOWN_REFERENCE | A valid temporally matched category value is absent from the reference. |
| BEFORE_FIRST | Category history exists for the item but begins after this view; no future value is filled backwards. |
| NO_HISTORY | No supplied category history exists for the item. |
| TOTAL | All eligible pairs; the sum of the preceding four mutually exclusive populations. |

MATCHED values must be digit text that safely fits BIGINT; only the lookup key is cast. Original text, including leading-zero spellings, and provenance remain unchanged. Malformed values are invalid inputs, not UNKNOWN_REFERENCE. The historical 167 unresolved **property observations** are not pair counts and are never substituted for this result. Zero UNKNOWN_REFERENCE or another empty status is allowed. Shares use the eligible pair denominator and four-place DECIMAL output; zero eligible denominators produce NULL shares, including TOTAL. DuckDB CLI JSON preserves DECIMAL values as four-place strings.

Mapping to a known static ID does not establish historical reference validity, a human-readable product category, current inventory or freshness. Category history follows the accepted latest-observation-at/before-event and [from,to) convention. A final NULL endpoint is the last supplied observation, not proof that its state remains true indefinitely. This step does not choose a staleness cutoff, repair unknown IDs, infer a category for missing history, or calculate category-level conversion.

## Admission and output safety

Admission checks the accepted 2,756,101 event occurrences, their type counts (2,664,312 view, 69,332 addtocart, 22,457 transaction), duplicate surplus 460, valid original identifiers/event/transaction rules and timestamps within 0–253402300799999. The actual all-event endpoint must match the frozen accepted endpoint. The ten-field category readset has exact required types. MATCHED rows require valid values and provenance, start <= event timestamp, and event < finite end with end > start; finite bounds must be supported. BEFORE_FIRST/NO_HISTORY require all four match fields to remain NULL. Unknown statuses or malformed fields invalidate admission.

The reference must contain 1,669 unique nonnegative non-NULL BIGINT IDs, preventing row multiplication. Its hierarchy is not revalidated. Eligible cohort count, tied-first-view tuple consistency, one snapshot per eligible pair, and the exhaustive four-way classification are checked before release. Invalid prerequisites or any eligible-pair first-view conflict yield all five labels with pair counts/shares NULL and every status BLOCKED. Missing referenced columns/tables may fail SQL binding. On healthy data all five rows are PASS, including zero-count statuses.

## Independent bounded four-source preflight

The validator reads events.csv, category_tree.csv and both item_properties CSVs. Both property files are scanned completely, but only categoryid observations are retained; availability and opaque properties are not reconstructed. Selected source keys must be canonically typed, values retain their original digit text, and item/timestamp keys must be unique. Category-only interval endpoints are derived from the next observation within each item, preserving all observations and source-file provenance. The reference is a disposable **ID-only projection** from category_tree.csv, independently checked against all 1,669 source IDs; no root/depth traversal is rebuilt.

The private fact is a **ten-field category-only stand-in**, built from frozen SQL54/63 event creation prefixes and one category ASOF LEFT JOIN. It is not a rebuild or re-verification of SQL69's seventeen-column fact. It preserves original event occurrences and derives the category snapshot under the accepted observation convention. Full SQL69, SQL62 hierarchy and previous full audit suites are not rerun. No learner database is opened.

Python independently sorts category observations numerically by item/time in chunks of at most 50,000, derives interval ends by lookahead, and sorts events by (itemid,visitorid,timestamp,event,transactionid with NULL before nonnegative IDs). This ordering permits only the current item's category history (explicit cap 50,000 observations), one current pair's first-view snapshot, and the small reference-ID set to be retained. Binary search selects the latest start <= event time and verifies finite boundaries. Remaining category history is drained and reconciled even for items with no events. No all-item history dictionary or all-pair dictionary is used.

Every original event occurrence's **complete ten-field readset** must match a direct private SQL stream, including original fields, category value/bounds/provenance/status, NULLs and duplicates. The same independent source fold identifies first views and eligible pairs, verifies snapshot consistency, resolves reference membership and reconstructs the complete five-by-four report using Decimal half-up shares. This verifies the new readset rather than trusting a repeated SQL join as its own reference.

The four real CLI phases are frozen before execution:

1. Category-only guarded import/interval construction plus ID-only reference projection: two threads, 1GB memory, 2GB spill, 120 seconds.
2. Frozen SQL54/63 event creation prefixes plus category-only ten-field enrichment: two threads, **2GB memory and 4GB spill**, 120 seconds.
3. Read-only SQL73 report: two threads, 1GB memory, 2GB spill, 120 seconds.
4. Direct read-only ten-field source comparison: two threads, 1GB memory, 2GB spill, 120 seconds.

At least **8GB free space** and a **7GB private-directory budget** are required. The larger enrichment-phase allowance is declared in advance, not evidence of a diagnosed failure. Post-phase directory sizes are not continuous peaks. Source sorting is timed separately. All four source hashes/metadata, pinned dependencies and **71 historical preflight files** must remain unchanged; the database byte hash must be identical across the read-only phases.

Focused fixtures cover all four statuses, safe numeric reference lookup without rewriting original text, zero unknown-reference populations, zero eligible cohorts, category history changes before/after first view, exact starts/ends, missing history, duplicate first-view occurrences and conflicting tied snapshots. Invalid reference IDs/counts/types, malformed category fields, future or expired matches, wrong cohort/endpoint and conflicting source observation keys must block rather than be silently selected. No additional hierarchy, availability, session or conversion analysis is introduced.

Private databases, source chunks and spills are removed. Real identifiers/history records are processed privately and never logged or uploaded. Public artifacts contain aggregate results, methods, code and hashes only. Endpoint/cutoff UTC labels are derived by integer epoch arithmetic; stored UTC fields are not read.

```powershell
python validation/preflight_retailrocket_first_view_category_coverage.py --duckdb "E:/DuckDB/duckdb.exe" --output "data/retailrocket_first_view_category_coverage_preflight.json"
```

Measured results will be appended and saved in the aggregate preflight evidence. Learner SQL73 execution follows the assistant preflight. The result establishes category coverage and static-reference membership under the stated temporal/cohort contract, not validated category-specific business outcomes.

## Executed results

The assistant preflight completed on 2026-11-09T10:38:43.822826+00:00 with DuckDB v1.5.5 (Variegata) d8cdaa33fd. This was one bounded real-source attempt with the four declared CLI phases. All five output rows passed and the independent Python report, including four-place Decimal shares, matched exactly.

| coverage_status | eligible_pairs | share_of_eligible_pairs_pct | check_status |
|---|---:|---:|---|
| MAPPED | 1527206 | 74.7784 | PASS |
| UNKNOWN_REFERENCE | 0 | 0.0000 | PASS |
| BEFORE_FIRST | 304405 | 14.9049 | PASS |
| NO_HISTORY | 210699 | 10.3167 | PASS |
| TOTAL | 2042310 | 100.0000 | PASS |

The unchanged cohort contains 2,042,310 eligible visitor-item pairs. At their earliest observed view, 1,527,206 pairs (74.7784%) have an eligible category observation whose numeric ID is present in the static reference. The remaining 515,104 pairs (25.2216%) comprise 304,405 BEFORE_FIRST and 210,699 NO_HISTORY pairs. Their missing assignment was retained rather than filled from later observations. UNKNOWN_REFERENCE is zero **within this cohort's earliest-view snapshots**; this does not erase the previously documented 167 unresolved category observations elsewhere in the property history.

These coverage results establish the denominator available for a later category-level analysis. They do not yet establish category-level funnel results, and excluding the unmatched quarter would change the population being described. Static membership and a last-recorded temporal match do not establish category freshness or continuous event capture.

The independent source proof compared every one of 2,756,101 event occurrences across all ten queried fields. All 460 duplicate surplus occurrences were preserved. It independently evaluated 2,132,127 viewed pairs, the same 2,042,310 eligible pairs and 2,042,360 eligible earliest-view occurrences; tied snapshots were consistent. Only one pair state was held at a time. The maximum observed current-item category history was 18 rows, below the declared 50,000-row cap.

Both property CSVs were scanned completely (20,275,902 rows); only 788,214 category observations were retained: 426,305 from part 1 and 361,909 from part 2. All selected history was drained and reconciled, including items without events. It formed 417,053 item histories, 371,161 finite intervals and 417,053 open tails; 345,542 consecutive equal-value links were retained. All 1,669 reference IDs matched the independently read CSV ID set exactly. No reference hierarchy, availability history or stored UTC field was rebuilt or reverified.

The global all-event endpoint remained 1442545187788 ms (2015-09-18T02:59:47.788000Z); the seven-day eligibility cutoff remained 1441940387788 ms (2015-09-11T02:59:47.788000Z). The window is an analysis convention, not an optimized horizon; the first observed view is subject to the dataset's left boundary.

Four focused fixture families passed, including 17 invalid-admission cases, full ten-field synthetic comparison, exact temporal boundaries, original digit spelling retained during numeric lookup, tied-snapshot conflicts, zero unknown-reference and zero eligible cohorts. A conflicting private category key was rejected before interval/ASOF construction, and the history cap aborted rather than filtering records.

Measured CLI durations were 3.404 seconds for category-only history/reference construction, 7.111 seconds for event/category enrichment, 3.313 seconds for SQL73 and 28.074 seconds for the complete independent stream. Python category and event scan/sorts took 18.858 and 24.633 seconds respectively. These timings exclude hashing and fixtures. Only enrichment used the predeclared 2GB memory/4GB spill allowance; other CLI phases used 1GB/2GB, all with two threads and 120-second limits.

The private database was 117,452,800 bytes before cleanup; the largest observed post-phase private directory was 264,262,494 bytes, below the 7GB budget. Post-phase observations are not continuous memory/disk peaks. Its byte hash was unchanged across the read-only report and stream. All four source hashes/metadata, pinned dependencies and 71 historical preflight evidence files remained unchanged. Private databases, spools and spills were removed; no learner database was opened and no real source identifiers or histories were logged or uploaded.

Report fingerprint: `ce37f37a9e45af0159a52b9cac78cb4853ada26af1e2b8ab252379034da59d50`. Script SHA-256: `a8701a98b0e33a613b9a6f7cbfd6f24df783a790baac38f90b70dc90bb3997f5`. Validator SHA-256: `8d9c8b034e7ed04a7d351b5ed2e0b404ed9a96364b000f7fee0304b35aa72f3e`. The original 9,951-byte method prefix remains unchanged (`f95f39277b2a7c61a5612ea70a7902ca3836991c64dfbc75b396fc5ec602c00e`). Aggregate evidence: [retailrocket_first_view_category_coverage_preflight.json](../data/retailrocket_first_view_category_coverage_preflight.json).

Assistant preflight is complete. Learner SQL73 execution and screenshot acceptance remain pending.

## Learner screenshot acceptance — 9 November 2026

The learner supplied the SQL73 DBeaver coverage result on 9 November 2026 (Australia/Sydney). All **five rows × four columns, twenty fields** and all headers are fully visible and match the prior measured result. All five rows are **PASS**. No labels or values were cropped or reconstructed. See the [learner acceptance record](../data/retailrocket_first_view_category_coverage_learner_acceptance.json).

The twenty fields comprise **five integer pair counts, five percentages, five complete coverage labels and five statuses**. The displayed UNKNOWN_REFERENCE share **0** and TOTAL share **100** are retained in the visual transcription and normalized exactly with Decimal to **0.0000** and **100.0000** for the frozen report contract. Integer thousands separators are removed without changing values. The normalized report fingerprint is `ce37f37a9e45af0159a52b9cac78cb4853ada26af1e2b8ab252379034da59d50`.

The accepted cohort remains **2,042,310 seven-day-eligible visitor/item pairs**. Its mutually exclusive coverage counts are **1,527,206 MAPPED (74.7784%)**, **0 UNKNOWN_REFERENCE (0.0000%)**, **304,405 BEFORE_FIRST (14.9049%)** and **210,699 NO_HISTORY (10.3167%)**. These four states reconcile to TOTAL and no unknown state is dropped. MAPPED means the recorded category at first observed view has a numeric ID present in the static reference; it does not establish freshness, historical business truth, a human-readable category name or category-specific conversion performance.

The zero UNKNOWN_REFERENCE count applies only to these eligible pairs' first-view attribution. It neither repairs nor contradicts the earlier **167 unmatched source property observations**, which are measured at a different grain and scope. Tied first-view attribution continues to require NULL-aware agreement of all five category fields across all view occurrences at an eligible pair's earliest view timestamp. No future category value is filled backward.

All **14,941 prior method bytes**, including the **9,951-byte frozen prefix** and executed-results appendix, remain preserved byte for byte. Frozen SQL73, validator, preflight and **24 pinned dependencies** are unchanged. Historical learner-pending statements remain as written; this appendix records current acceptance. No source CSV, learner database, SQL preflight or fixture was opened or rerun for acceptance, and no screenshot or row-level identifiers were copied into the repository. No fresh verification of availability/UTC fields, the full seventeen-field fact, category hierarchy or learner conceptual understanding is claimed.
