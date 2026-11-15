# SQL89: materialized additive R/F summary for later BI use

## Purpose and table contract

Materialize the accepted R/F cell counts into a small, typed source for a later BI model. This is source preparation, not a completed Power BI model, measure set or dashboard. Read the accepted rr_mart.transaction_basket_items four-field BIGINT projection visitorid,transactionid,itemid,last_timestamp_ms. Preserve the accepted 22,323 memberships, 17,672 composite candidate baskets and 11,719 transaction-recorded IDs. Do not open the learner database during assistant preparation.

Create rr_bi.rf_segment_summary exactly once, using CREATE SCHEMA IF NOT EXISTS followed by CREATE TABLE AS. There is no OR REPLACE, drop, overwrite, insert or update of the destination. An existing destination must cause creation to fail and remain unchanged. The table contains exactly sixteen dense R-major/F-minor cells, including any zero cells, and seven columns in this exact order:

| Column | Type | Meaning |
| --- | --- | --- |
| reference_timestamp_ms | BIGINT | Constant 1442545187788 ms, the accepted global observed event endpoint |
| recency_order | BIGINT | R sort position 1 through 4 |
| recency_band | VARCHAR | Accepted R label |
| frequency_order | BIGINT | F sort position 1 through 4 |
| frequency_band | VARCHAR | Accepted F label |
| visitor_ids | BIGINT | Number of transaction-recorded IDs in this disjoint cell |
| candidate_baskets | BIGINT | Sum of those IDs' full-observation-window F |

The key is (reference_timestamp_ms,recency_order,frequency_order). There is no TOTAL row, stored percentage, Top1/Top5 measure or original visitor/item/transaction identifier. The two count measures are additive across the disjoint cells in this single snapshot. Explicit sort orders avoid alphabetic label ordering. Future multiple snapshots must not be summed as unique people; current reference is constant. Ratios and nonadditive concentration measures require separately defined BI measures later.

## Preserved definitions and creation guard

F counts full distinct (visitorid,transactionid) candidate keys per ID, not item memberships or repeated event weights. R is 1442545187788 minus MAX(last_timestamp_ms) across every membership for that ID. The reference is 2015-09-18T02:59:47.788000Z, not today or the earlier latest transaction time; source lower bound remains 1430622004384. Preserve R intervals [0,7),[7,30),[30,60),[60,infinity) elapsed 24-hour days, using exact integer milliseconds. Preserve F intervals 1,2,3-4,5+. No threshold, population or selected-pair restriction changes.

Reuse SQL87 source admission, RF assignment, sixteen-cell partition and direct-marginal controls. The source requires four BIGINT fields, valid unique nonnegative/non-NULL membership keys, bounded non-NULL timestamps, and the accepted basket counts including 15,029 singleton/2,643 multi-item candidates and maximum 31 items. The dense matrix always has sixteen scaffold rows, even when invalid input supplies no eligible records. Every destination expression is protected by an explicit error branch when either source or RF contract fails. Invalid input, including an empty source, must fail the CREATE before a destination is created; it must not silently produce an empty table. Missing required source columns may fail binding. The rr_bi schema may exist after a rejected build; the destination table must not.

## Audit after creation

Return exactly twenty audit rows by five columns check_order,check_name,actual,expected,status. actual and expected are canonical integer text; check_order is numeric. The audit checks: summary_rows=16, column_count=7, schema_mismatch=0, distinct_rf_keys=16, missing_required_rows=0, negative_count_rows=0, invalid_band_order_rows=0, reference_mismatch_rows=0, distinct_recency_orders=4, distinct_frequency_orders=4, visitor_ids_total=11719, candidate_baskets_total=17672, total_label_rows=0, duplicate_key_surplus=0, source_membership_rows=22323, source_contract_violations=0, source_rf_contract_violations=0, expected_only_rows=0, summary_only_rows=0, cell_count_inconsistency_rows=0.

Validate exact types and ordinal positions, all sixteen unique keys, label-to-order mappings, constant reference and nonnegative required counts. The audit projects the five numeric target fields through TRY_CAST to BIGINT and labels through CAST to VARCHAR while separately checking the strict physical schema; malformed numeric values become NULL instead of bypassing validation. Compare all seven fields to freshly derived guarded source rows in both directions with EXCEPT ALL. The F bands also imply basket-count bounds, including zero baskets for empty cells. All twenty checks normally PASS. Counts/types or comparison violations FAIL; if source/RF contracts are invalid, the two source-to-target comparison checks are BLOCKED rather than presented as an accepted reconstruction. Missing required source or target columns can fail binding. An existing target is checked by running only the read-only query after the CHECKS marker, never by deleting or replacing it.

## Bounded independent proof

Pin accepted SQL88 progress evidence and latest learner acceptance, and reuse accepted SQL87 RF fingerprints/cell counts and fixed endpoint provenance. Parse events.csv once in canonical order with the bounded helper, reconstruct and match SQL79's accepted full six-field membership fingerprint, then load/read back the small private six-field input. Source byte-identity hashes are separate reads. Do not repeat earlier original-five-field comparisons, RF/ranked streams, old SQL analyses or full historical suites.

Python independently builds composite-key sets and MAX last timestamps per ID, computes exact R/F labels and matches the accepted six-field SQL87 RF fingerprint. Derive only the new sixteen aggregate rows with fixed reference and sort fields, and compare their ID/basket counts to accepted SQL87 cell artifacts. No rank, Top-k or further business drilldown is computed. Independently compare the complete materialized destination in reference/R/F order: sixteen rows by seven fields, five integers and two labels, exactly. Hash the actual audit report and full new table readback. Only aggregate rows and fingerprints may be published.

Run one integrated new fixture family before the single real attempt. Cover successful seven-column typed creation with sixteen cells including zeros and no TOTAL, complete readback, a rejected second creation that leaves the target unchanged, invalid nonempty and empty source rejection that leaves no target, a targeted count corruption detected by the read-only audit, and a wrong physical count type reported as a schema failure. No earlier RF boundary or concentration tests are repeated. Any fixture failure stops before parsing the real source.

Only three real CLI phases: load/readback accepted input; build destination and return its twenty-row audit; read the new sixteen-row table in read-only mode. The build intentionally changes the private database. Verify database bytes remain unchanged only between the completed build and the final read-only table proof. Require two threads, 1GB memory, 2GB spill and 120 seconds per CLI phase, 8GB free workspace and a 7GB private-directory budget checked after phases. Retain existing 100,000 transaction-occurrence/visitor bounds without filtering. Verify source/dependency identity and 87 historical preflight files unchanged; clean temporary CSV/database/spills. Freeze this method before the single integrated attempt and append execution results without altering this prefix.

## Interpretation and current scope

The table represents the same descriptive RF snapshot already accepted. Candidate baskets are not verified paid orders, and IDs are not verified people; observation length differs between IDs. Full-window basket sums are not restricted to the R interval. No monetary RFM, lifetime value, churn, loyalty, fraud or causal business effect is inferred. Power BI relationships, measures, visual interactions and dashboard validation remain future work.

## Executed results

Assistant preflight completed on 15 November 2026 (Australia/Sydney). Learner SQL89 creation remains pending. Evidence: [aggregate preflight and table readback](../data/retailrocket_rf_bi_summary_preflight.json); [SQL](../sql/89_build_retailrocket_rf_bi_summary.sql); [validator](../validation/preflight_retailrocket_rf_bi_summary.py).

An initial integrated attempt stopped at the first synthetic build/audit with an ambiguous reference_timestamp_ms binder error, before any source CSV parse. An empty in-memory schema diagnostic confirmed the ambiguity; the target column was qualified. The corrected integrated attempt passed the new build/audit fixture family, including five build-safety and audit subcases, before the single real-source parse. A duplicate creation was rejected with the existing target unchanged. Invalid nonempty and empty sources left no target. Target count corruption and a wrong physical count type were detected by the appropriate read-only audit failures. The successful fixture preserved sixteen cells, including twelve zeros, with exactly the seven required column types and no TOTAL row. There were two integrated attempts in total, one successful real-data attempt, and no old analysis suites were repeated.

The real private build produced rr_bi.rf_segment_summary with sixteen rows and seven columns, all five integer fields and two labels matching the independent Python reference exactly. All twenty audit checks passed:

| check_order | check_name | actual | expected | status |
| --- | --- | --- | --- | --- |
| 1 | summary_rows | 16 | 16 | PASS |
| 2 | column_count | 7 | 7 | PASS |
| 3 | schema_mismatch | 0 | 0 | PASS |
| 4 | distinct_rf_keys | 16 | 16 | PASS |
| 5 | missing_required_rows | 0 | 0 | PASS |
| 6 | negative_count_rows | 0 | 0 | PASS |
| 7 | invalid_band_order_rows | 0 | 0 | PASS |
| 8 | reference_mismatch_rows | 0 | 0 | PASS |
| 9 | distinct_recency_orders | 4 | 4 | PASS |
| 10 | distinct_frequency_orders | 4 | 4 | PASS |
| 11 | visitor_ids_total | 11719 | 11719 | PASS |
| 12 | candidate_baskets_total | 17672 | 17672 | PASS |
| 13 | total_label_rows | 0 | 0 | PASS |
| 14 | duplicate_key_surplus | 0 | 0 | PASS |
| 15 | source_membership_rows | 22323 | 22323 | PASS |
| 16 | source_contract_violations | 0 | 0 | PASS |
| 17 | source_rf_contract_violations | 0 | 0 | PASS |
| 18 | expected_only_rows | 0 | 0 | PASS |
| 19 | summary_only_rows | 0 | 0 | PASS |
| 20 | cell_count_inconsistency_rows | 0 | 0 | PASS |

The materialized table sums to 11,719 transaction-recorded IDs and 17,672 candidate baskets. It preserves the accepted SQL87 sixteen cell counts and fixed reference, with no TOTAL, percentages, Top-k measures or original identifiers. No empty cells occur in this snapshot; the synthetic test covers that behavior. The complete aggregate rows are included in the preflight evidence. Power BI model/dashboard development has not been performed in this step.

### Measured execution and reproducibility

- Source canonical parse/reconstruction: 19.186 seconds; independent summary reference: 0.091 seconds.
- Three real CLI phases: input load/readback 0.295 seconds; guarded build and audit 0.236 seconds; read-only complete target table 0.125 seconds.
- The private database intentionally changed when the new table was built. Its bytes were unchanged during the final read-only table comparison. No claim is made that construction left the database unchanged.
- Source/dependency identities and all 87 earlier preflight files remained unchanged. The learner database was not opened. Temporary membership CSV, databases and spills were removed; original identifiers were not uploaded or logged.
- Largest private directory observed after a phase: 2184983 bytes; this is not a continuous peak. Limits remained two threads, 1GB memory, 2GB spill and 120 seconds per CLI phase.
- Query SHA-256: df40c28e490128b7305266c933c15b6831e2ed4e865abcb01ecc4e09a2d20190.
- Validator SHA-256: 28dbd5356176fbcb4caab93f1aac0dfc6edb09e27d4979edc612d5c4865f04f0.
- Returned twenty-row audit SHA-256: 589bab3d4d6a36eb2a799e30a377c615e247aaab1f3e6be217ff6f14d0d64a0a.
- Complete sixteen-row, seven-field target SHA-256: cbcc0bc2cb3daf2ee510ae138b8091e3fd29277a34ea34ef25b348fcff0ff33e.
- Reused SQL87 six-field RF fingerprint: 06f415d38ff0a711b430a46c92884071b3babc203466cdd5071a8ab73dc73050.
- Reconstructed membership fingerprint: 99c7d679d858b3d1335dfafa22aa48b5e842d03336af5c85330e96853c59fca5.
- Frozen method prefix: 8109 bytes, SHA-256 ddc3ba182a31aa544ddfe9f344240eefa380ea26fc31df94231274afdbf18451; unchanged before this append.

The proof computes only the new aggregate table and its build/audit behavior. It does not rerun old SQL, RF/rank result streams, boundary/concentration suites or business drilldowns. Ratios, nonadditive concentration measures, relationships and visual interaction validation remain separate BI work.
