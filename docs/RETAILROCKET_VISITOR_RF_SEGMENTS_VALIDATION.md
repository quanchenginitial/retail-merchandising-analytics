# SQL87: descriptive transaction-visitor R x F matrix

## Purpose and population

Combine the accepted frequency and recency definitions into one descriptive cross-classification. The source population remains all 22,323 accepted basket-item memberships, 17,672 composite candidate baskets and 11,719 transaction-recorded visitor IDs. No pair, category, product, funnel or recent-basket filter applies. Browsing-only/non-transaction IDs and F_0 are absent; this is not an all-visitor population.

Read only four BIGINT fields from rr_mart.transaction_basket_items: visitorid,transactionid,itemid,last_timestamp_ms. Preserve the existing membership table. The assistant uses a private copy and does not open the learner database. First timestamps, source-event occurrence weights, properties and enriched-event fields are not queried.

## Frozen visitor measures

F is the count of distinct full (visitorid,transactionid) basket keys for each visitor ID across the entire accepted window. Multiple item memberships never increase basket frequency. Shared transaction identifiers under different visitor IDs remain separate composite baskets.

R is 1442545187788 minus MAX(last_timestamp_ms) across all memberships for that visitor ID. The fixed reference is the global observed event endpoint 2015-09-18T02:59:47.788000Z, as accepted by SQL64/70/86, rather than today or the earlier latest transaction time. Source lower bound remains 1430622004384. A day is exactly 86,400,000 milliseconds; use exact integer elapsed times and explicit BIGINT boundaries before classification. No display rounding or calendar-date truncation determines a band.

R bands in order: R_LT_7D [0,604800000), R_7_TO_LT_30D [604800000,2592000000), R_30_TO_LT_60D [2592000000,5184000000), R_GE_60D [5184000000,infinity). F bands in order: F_1 = 1, F_2 = 2, F_3_4 = 3 through 4, F_5_PLUS >= 5. These remain the descriptive boundaries from SQL85/86; they are not optimized scores.

## Dense report and meaning

Return exactly seventeen rows and seven columns: recency_band,frequency_band,visitor_ids,visitor_share_pct,candidate_baskets,basket_share_pct,check_status. Show all sixteen R-major/F-minor combinations, including empty cells with zero counts and zero shares, then TOTAL/TOTAL. There are no subtotals or additional median/maximum columns.

Visitor shares divide by all 11,719 transaction-recorded IDs; basket shares divide by all 17,672 candidate baskets. Round both shares to six decimal places only for display. Each cell's candidate_baskets is SUM(F) for IDs assigned to that R/F cell. It includes those IDs' baskets across the full observed window, not only baskets within the recency interval. Segment labels classify IDs at the fixed endpoint; they do not relabel basket dates.

This step completes a descriptive R/F cross-tabulation, not validated lifetime-value, churn, loyalty or customer-response segmentation, and not RFM because no monetary measure is available. A visitor ID is not a verified person or customer; candidate baskets are not proven paid orders. The finite, partially observed window and unequal identifier tenure/exposure constrain interpretation. No retention or causal effect is estimated.

## Controls and failure behavior

Require four BIGINT readset fields, non-NULL/nonnegative unique three-field membership keys, and non-NULL last timestamps inside the accepted source bounds. Retain accepted controls: 22,323 memberships, 17,672 composite baskets, 15,029 singleton baskets, 2,643 multi-item baskets and maximum basket size 31. Invalid source admission prevents records entering derived R/F calculations; missing required columns may fail SQL binding.

Require 11,719 per-visitor measures with positive valid frequencies summing to 17,672, nonnegative bounded recency, and exact last_timestamp plus recency equal to the reference. Each visitor must join exactly one R/F cell. All sixteen cells must partition the visitor and basket totals with nonnegative counts and zero basket totals for empty cells. Matrix R and F marginals must equal directly aggregated visitor measures in both directions using multiset comparison. Concentration or particular cell counts are not preset business success tests.

Invalid admission preserves the seventeen labels with NULL measurements and BLOCKED. Post-admission measure, assignment, partition or marginal failures preserve labels with NULL measurements and FAIL. Normal empty cells contain zeros and PASS.

## Bounded independent proof

Pin accepted SQL85/86 report evidence and their latest learner acceptances, including the fixed SQL86 endpoint provenance. Reuse SQL79's original-five-field proof and canonical six-field membership fingerprint. Parse events.csv once in canonical source order with the existing bounded helper, reconstruct all six-field memberships, and match the accepted fingerprint. Source-byte identity hashing reads bytes separately. Load only the small private six-column copy and compare its complete ordered readback. Source timestamps are processed during reconstruction; analytical readset remains the four declared fields.

Independent Python constructs a set of complete composite basket keys for each visitor and MAX of membership last timestamps, then computes the fixed-reference integer recency and both labels. Compare the entire private SQL visitor stream in numeric visitor order: 11,719 rows by six fields visitorid,basket_count,last_transaction_ms,recency_ms,recency_band,frequency_band. Four integer fields and two labels must match exactly. The independent matrix is built directly from those independent visitor records. Compare report labels, counts and statuses exactly; compare six-decimal percentages to Fraction references within 0.5e-6 plus 1e-12 absolute tolerance. Hash the actual returned report separately. Publish no original identifiers or visitor records.

Independently sum new matrix rows to R/F marginals. Compare F visitor and basket counts to accepted SQL85 aggregate rows and R visitor counts to accepted SQL86 aggregate rows, without rerunning either old query or private stream. SQL86 did not report baskets by R, so those new basket marginals are checked against direct new visitor aggregation, not invented prior evidence.

Only three real CLI phases: private six-field load/readback, read-only matrix query, and complete read-only six-field visitor R/F stream from the same CTEs. No previous frequency, recency, pair, contributor or month result streams or full historical suites are repeated. Focused synthetic cases cover F boundaries 1,2,3,4,5, R boundaries and +/-1ms, composite baskets, additional item memberships with the latest timestamp, zero-cell scaffolding, NULL/future/wrong-type blocking and deliberately overlapping R or F intervals failing assignment/partition checks. Do not add unrelated historical suites.

Retain 100,000 transaction-occurrence and visitor-result caps without filtering. Each CLI phase uses two threads, 1GB memory, 2GB maximum spill and a 120-second timeout. Require 8GB free workspace and a 7GB private-directory budget, measuring size after phases rather than claiming a continuous peak. Require source/dependency identity, 85 historical preflight files unchanged, private database bytes unchanged across read-only phases, and cleanup of temporary CSV/database/spills. Freeze this method before fixtures and the single real attempt; append results without changing this prefix.

## Executed results

Assistant SQL87 preflight passed at 2026-11-13T07:15:10.973728+00:00 using v1.5.5 (Variegata) d8cdaa33fd. One real-source attempt completed all three declared CLI phases. The seventeen-row, seven-column R/F matrix returned seventeen PASS statuses and no FAIL or BLOCKED rows. Learner execution and screenshot acceptance remain pending.

| recency_band | frequency_band | visitor_ids | visitor_share_pct | candidate_baskets | basket_share_pct | check_status |
| --- | --- | --- | --- | --- | --- | --- |
| R_LT_7D | F_1 | 413 | 3.524191 | 413 | 2.337030 | PASS |
| R_LT_7D | F_2 | 29 | 0.247461 | 58 | 0.328203 | PASS |
| R_LT_7D | F_3_4 | 15 | 0.127997 | 48 | 0.271616 | PASS |
| R_LT_7D | F_5_PLUS | 19 | 0.162130 | 1517 | 8.584201 | PASS |
| R_7_TO_LT_30D | F_1 | 1711 | 14.600222 | 1711 | 9.681983 | PASS |
| R_7_TO_LT_30D | F_2 | 119 | 1.015445 | 238 | 1.346763 | PASS |
| R_7_TO_LT_30D | F_3_4 | 30 | 0.255995 | 99 | 0.560208 | PASS |
| R_7_TO_LT_30D | F_5_PLUS | 24 | 0.204796 | 402 | 2.274785 | PASS |
| R_30_TO_LT_60D | F_1 | 2366 | 20.189436 | 2366 | 13.388411 | PASS |
| R_30_TO_LT_60D | F_2 | 176 | 1.501835 | 352 | 1.991852 | PASS |
| R_30_TO_LT_60D | F_3_4 | 42 | 0.358392 | 136 | 0.769579 | PASS |
| R_30_TO_LT_60D | F_5_PLUS | 25 | 0.213329 | 916 | 5.183341 | PASS |
| R_GE_60D | F_1 | 6166 | 52.615411 | 6166 | 34.891354 | PASS |
| R_GE_60D | F_2 | 424 | 3.618056 | 848 | 4.798551 | PASS |
| R_GE_60D | F_3_4 | 90 | 0.767984 | 292 | 1.652331 | PASS |
| R_GE_60D | F_5_PLUS | 70 | 0.597321 | 2110 | 11.939792 | PASS |
| TOTAL | TOTAL | 11719 | 100.000000 | 17672 | 100.000000 | PASS |

All sixteen cells reconcile to 11,719 transaction-recorded visitor IDs and 17,672 candidate baskets. Visitor and basket shares use their separate global denominators. Each cell sums the full-window frequency of its assigned visitor IDs; those baskets are not restricted to that cell's recency interval. The frozen reference remains 1442545187788 Unix milliseconds, 2015-09-18T02:59:47.788000Z, with exact integer-millisecond R bands and the accepted F bands.

New matrix F marginals matched accepted SQL85 visitor and basket counts, and new matrix R visitor marginals matched accepted SQL86 counts. Both preflight and learner-acceptance aggregate artifacts were compared. R basket marginals were reconciled against the new direct visitor aggregation; no claim was made that SQL86 had already reported them. Neither old query nor its private stream was executed again.

One canonical events.csv parse reconstructed all 22,323 six-field memberships. Fingerprint `99c7d679d858b3d1335dfafa22aa48b5e842d03336af5c85330e96853c59fca5` matched accepted SQL79 and the complete private six-field readback. Separate source-byte hash scans checked identity. Original-five-field proof and accepted endpoint provenance were reused; SQL54/63/64/70/79/80/81/82/83/84/85/86 and full historical suites were not rerun. Reconstruction processed source timestamps, while the analytical query read only the three membership keys and last_timestamp_ms.

The new independent reference constructed complete composite basket-key sets per visitor and took MAX of all membership last timestamps. It derived exact R and F labels, then built the matrix directly. All 11,719 private rows across six fields matched in numeric visitor order: four integer fields and two labels were exact. Public labels, counts and statuses matched exactly, and six-decimal shares matched independent Fraction references within 5.00001e-07 absolute tolerance. No individual IDs or visitor records are published. Actual returned report values have their own exact digest.

One focused synthetic fixture family passed. Thirty-one memberships in thirty composite baskets produced ten visitor IDs with frequencies spanning 1,2,3,4,5 and recencies at 7/30/60-day boundaries and one millisecond on either side. Shared transaction IDs across visitors and an additional membership with a later last timestamp preserved the correct basket and recency grain. Seven empty cells remained visible with zero counts and shares. NULL, future and wrong-type timestamps returned masked BLOCKED; deliberately overlapping R and F rules separately returned masked FAIL. No unrelated previous suite was repeated.

The canonical source parse/reconstruction took 16.866 seconds and the independent set/MAX R/F reference 0.087 seconds. CLI phases took 0.266 seconds for private input load/readback, 0.16 seconds for the matrix and 0.204 seconds for the complete exact R/F stream. Each used two threads, 1GB memory, 2GB maximum spill and completed within 120 seconds. The largest private directory observed after a phase was 1,922,839 bytes, below 7GB, without claiming a continuous peak.

Source identity, pinned dependencies and all 85 historical preflight artifacts remained unchanged. Private database byte hashes matched across read-only phases; temporary CSV, database and spills were removed. The learner database, properties, category reference and enriched fact were not opened. The result is a descriptive R/F cross-tabulation of transaction-recorded identifiers with finite-window and unequal-exposure limitations. It does not establish monetary RFM, lifetime value, churn, retention, loyalty, verified people/orders or validated customer-response segments.

Report SHA-256: `390d6ae85a24500168443d351f1b1f12fec4a8a090b1176126b58567c63537c4`. Script SHA-256: `59ef1d7dfd6140fcae4b8bd98347d2f9e3d12f94b863698c1b7847130fa0a68f`. Validator SHA-256: `54e07f76b204cd6e3af31994c09d6708255b0ae6ed8dbf7a475915bcd504c287`. The frozen 7,441-byte method prefix remains unchanged at `383cdaf6ed6e0555445eff9e65a53db334933022de4b8500c8ab0293d0f7f350`.
