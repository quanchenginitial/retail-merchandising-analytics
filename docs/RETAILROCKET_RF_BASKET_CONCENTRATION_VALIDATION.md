# SQL88: candidate-basket concentration within descriptive R/F cells

## Purpose and fixed input

Check whether a cell's basket contribution is spread across its transaction-recorded IDs or concentrated in very few IDs. Use the accepted SQL87 R/F classification without changing its population, cutoffs or reference. The four BIGINT analytical fields are visitorid,transactionid,itemid,last_timestamp_ms from rr_mart.transaction_basket_items. Keep all 22,323 memberships, 17,672 composite candidate baskets and 11,719 transaction-recorded IDs; browsing-only IDs and F_0 are excluded.

F counts distinct full (visitorid,transactionid) keys per ID, not item memberships or repeated source-event weights. R equals the fixed global observed endpoint 1442545187788 ms (2015-09-18T02:59:47.788000Z) minus each ID's MAX(last_timestamp_ms) across all memberships. Source lower bound remains 1430622004384. It is not today's date, a verified collection cutoff or the earlier latest transaction time. Use exact integer milliseconds before any display operation. R bands retain [0,7),[7,30),[30,60),[60,infinity) elapsed 24-hour days; F bands retain 1,2,3-4,5+.

## Concentration definition and output

Within each R/F cell, sort IDs by basket_count descending, then visitorid ascending to resolve ties deterministically. Use ROW_NUMBER, never a tie-preserving RANK for selecting the first five IDs. Top1 is the highest individual F. Top5 is the sum of F for the first min(5,n) IDs, where n is the cell's ID count. A cutoff tie selects exactly five IDs; their identity is not a claim of greater value than tied alternatives.

Return exactly seventeen rows by nine columns: recency_band,frequency_band,visitor_ids,candidate_baskets,top1_baskets,top1_share_pct,top5_baskets,top5_share_pct,check_status. Keep all sixteen R-major/F-minor cells and add TOTAL/TOTAL. Each cell's candidate_baskets is its members' full-observation-window F sum, not baskets occurring during its recency interval. Both concentration shares divide by that row's own candidate_baskets, unlike SQL87's all-population contribution percentages. Show six decimals after division. An empty cell has zero IDs, baskets and top counts but NULL shares because its denominator is zero. Any nonempty cell with five or fewer IDs has top5_share_pct=100; that is a size consequence rather than evidence of unusual concentration.

TOTAL ranks all 11,719 IDs globally again and uses 17,672 as its denominator. Its Top1/Top5 counts and shares are not sums or averages of the sixteen cell-level tops. No original ID or ranked record appears in the public report.

## Controls and failure behavior

Retain SQL87 source admission, per-ID exact assignment, matrix partition and direct R/F marginal checks. Require four BIGINT fields, nonnegative/non-NULL unique membership keys, and bounded non-NULL timestamps. Basket controls remain 15,029 single-item and 2,643 multi-item baskets, maximum 31 items. Invalid input cannot enter RF calculations. Missing required columns can fail binding.

Check that ranked identities preserve the classified visitor multiset in both directions, global ranks are distinct and contiguous from one through the ID count, and each nonempty cell's ranks are also distinct and contiguous. The seventeen report rows must satisfy Top1=max(F), 0<=Top1<=Top5<=row baskets, exactly min(1,n)/min(5,n) selected IDs, correct empty-cell behavior, and Top5=row baskets for n<=5. Check all RF and concentration gates before displaying measurements. Invalid admission yields BLOCKED and NULL measurements; post-admission failures yield FAIL and NULL measurements. Normal empty cells yield PASS with zero counts and NULL shares. Particular concentration values are discoveries, not preset success thresholds.

## Bounded independent proof

Pin the accepted SQL87 report and learner acceptance, fixed endpoint provenance, and immutable earlier dependencies. Reuse SQL79's complete original-five-field proof and accepted canonical six-field membership fingerprint. Read events.csv once in canonical source order with the existing bounded helper, reconstruct six-field memberships, and compare the accepted fingerprint. Identity hash reads of source bytes are separate from the one CSV parse. Load only the private small membership copy and compare its full ordered six-field readback. Do not open the learner database or read item-property files.

Independently construct Python composite-key sets and per-ID MAX of membership last timestamps, calculate exact R and F labels, and match the accepted SQL87 six-field RF fingerprint. This reuses accepted proof by fingerprint and does not run SQL87 or its old stream. Build new cell and global rankings with Python sorted(..., key=(-F,ID)), then compare the entire new SQL ranked stream in numeric visitor order: 11,719 rows by eight fields visitorid,basket_count,last_transaction_ms,recency_ms,recency_band,frequency_band,cell_rank,global_rank. All six integer fields and both labels match exactly. The new stream includes the RF values as part of the ranking proof; no separate old RF stream is repeated.

Independently calculate each Top1/Top5 report and compare labels, counts, NULLs and statuses exactly. Compare six-decimal shares to Fraction references within 0.5e-6 plus 1e-12 absolute tolerance. Match all cell and TOTAL ID/basket counts to accepted SQL87 aggregate artifacts. The independent global Top1/Top5 calculation must use all IDs, not sum cell tops. Hash the actual returned report and private complete stream without publishing records.

Use one integrated run after static review: run only new concentration fixtures, then the single real-data attempt if they pass. Fixtures cover a tie at the fifth cutoff, F_1 ties, nonempty cells with fewer than/exactly/more than five IDs, dense empty cells with NULL shares, global totals different from summed cell tops, invalid source blocking, and deliberately invalid ranking/top selection failing gates. Do not repeat earlier RF boundary suites or run the fixture stage twice without a change or failure.

Only three real CLI phases: private six-field load/readback, read-only report, and the new complete read-only eight-field ranked stream. Require two threads, 1GB memory, 2GB spill limit and a 120-second timeout per phase; cap retained transaction occurrences and ranked IDs at 100,000 without filtering. Require 8GB free workspace and a 7GB private-directory budget measured after phases, not a claimed continuous peak. Verify source/dependencies, 86 historical preflight files and private database bytes unchanged; clean temporary CSV/database/spills. Do not rerun old SQL/result streams or full historical suites. Freeze this method before the integrated attempt and append measured results without changing its prefix.

## Interpretation limits

Concentration is descriptive evidence for investigation. High frequency or a large share does not establish customer value, loyalty, churn, fraud, automation or a response to marketing. IDs are not verified people and candidate baskets are not verified paid orders. Unequal identifier exposure, the finite observation window and lack of monetary data remain. This is not monetary RFM, independent temporal validation or a measured business effect. Top1/Top5 were chosen to inspect concentration, not optimized or validated as operational thresholds.

## Executed results

Assistant preflight completed on 15 November 2026 (Australia/Sydney). The learner's SQL88 execution remains pending. Evidence: [aggregate preflight](../data/retailrocket_rf_basket_concentration_preflight.json); [query](../sql/88_analyze_retailrocket_rf_basket_concentration.sql); [validator](../validation/preflight_retailrocket_rf_basket_concentration.py).

One integrated run passed the new concentration fixture family and all three invalid-control subcases before parsing the real source. No earlier RF boundary tests were repeated. The single real attempt produced seventeen PASS rows with no FAIL/BLOCKED rows. The complete 11,719-row, eight-field ranked reference matched exactly, including all cell/global rank integers and both band labels. The accepted SQL87 six-field RF fingerprint and all cell/TOTAL visitor/basket counts matched without rerunning its query or old stream.

| recency_band | frequency_band | visitor_ids | candidate_baskets | top1_baskets | top1_share_pct | top5_baskets | top5_share_pct | check_status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| R_LT_7D | F_1 | 413 | 413 | 1 | 0.242131 | 5 | 1.210654 | PASS |
| R_LT_7D | F_2 | 29 | 58 | 2 | 3.448276 | 10 | 17.241379 | PASS |
| R_LT_7D | F_3_4 | 15 | 48 | 4 | 8.333333 | 18 | 37.500000 | PASS |
| R_LT_7D | F_5_PLUS | 19 | 1517 | 502 | 33.091628 | 1213 | 79.960448 | PASS |
| R_7_TO_LT_30D | F_1 | 1711 | 1711 | 1 | 0.058445 | 5 | 0.292227 | PASS |
| R_7_TO_LT_30D | F_2 | 119 | 238 | 2 | 0.840336 | 10 | 4.201681 | PASS |
| R_7_TO_LT_30D | F_3_4 | 30 | 99 | 4 | 4.040404 | 20 | 20.202020 | PASS |
| R_7_TO_LT_30D | F_5_PLUS | 24 | 402 | 85 | 21.144279 | 233 | 57.960199 | PASS |
| R_30_TO_LT_60D | F_1 | 2366 | 2366 | 1 | 0.042265 | 5 | 0.211327 | PASS |
| R_30_TO_LT_60D | F_2 | 176 | 352 | 2 | 0.568182 | 10 | 2.840909 | PASS |
| R_30_TO_LT_60D | F_3_4 | 42 | 136 | 4 | 2.941176 | 20 | 14.705882 | PASS |
| R_30_TO_LT_60D | F_5_PLUS | 25 | 916 | 148 | 16.157205 | 524 | 57.205240 | PASS |
| R_GE_60D | F_1 | 6166 | 6166 | 1 | 0.016218 | 5 | 0.081090 | PASS |
| R_GE_60D | F_2 | 424 | 848 | 2 | 0.235849 | 10 | 1.179245 | PASS |
| R_GE_60D | F_3_4 | 90 | 292 | 4 | 1.369863 | 20 | 6.849315 | PASS |
| R_GE_60D | F_5_PLUS | 70 | 2110 | 162 | 7.677725 | 639 | 30.284360 | PASS |
| TOTAL | TOTAL | 11719 | 17672 | 502 | 2.840652 | 1318 | 7.458126 | PASS |

The 16 cell totals reconcile to 11,719 IDs and 17,672 candidate baskets. All 16 observed cells are nonempty in this snapshot; the separate synthetic fixture verified 12 empty cells with zero counts and NULL shares. The TOTAL top counts above are independently computed from the global ranking. Their percentages use 17,672 baskets; other rows use their own candidate_baskets. A row's full-window basket totals must not be interpreted as transactions limited to its recency interval.

The top counts and shares describe concentration only. They do not classify identified people, verified orders, value, loyalty, churn, fraud or automation. No recommendation or marketing effect was evaluated.

### Measured execution and reproducibility

- Source canonical parse/reconstruction: 19.581 seconds; independent concentration reference: 0.104 seconds.
- Three real CLI phases: input load/readback 0.295 seconds; read-only report 0.220 seconds; complete ranked stream 0.233 seconds.
- Source/dependency identities and all 86 earlier preflight files remained unchanged; private database hashes matched across read-only phases. The learner database was not opened. Temporary membership CSV, databases and spills were removed; original identifiers and ranked records were not uploaded or logged.
- Largest private directory observed after a phase: 1922839 bytes. This is an after-phase observation, not a continuous peak. Limits stayed at two threads, 1GB memory, 2GB spill and 120 seconds per CLI phase.
- Query SHA-256: 166ea83ae11e71fdbea3271586b25adb5b07709ab804bbc0c4ad92f3122d128c.
- Validator SHA-256: 012108db92f29bf5fb6bd468fa68ad1186f2ce720e86278f3f63a0d241294d84.
- Returned report SHA-256: e8385fde4a98f505d7b0c12b3e4ca0d17d23a47527d13f696e64a2b5f6b66897.
- Complete private eight-field ranked stream SHA-256: 276e19dfa47a1894b6a5a3c9a1e6719cc2e438ca73368db4b76728c254bd5b39.
- Reused accepted six-field RF fingerprint: 06f415d38ff0a711b430a46c92884071b3babc203466cdd5071a8ab73dc73050.
- Reconstructed membership fingerprint: 99c7d679d858b3d1335dfafa22aa48b5e842d03336af5c85330e96853c59fca5.
- Frozen method prefix: 7369 bytes, SHA-256 0cce795a2e7d4dbbacd85b0b37ae518b415730bee0f6c818a4592cb14fad8ee7; unchanged before this append.

Times exclude separate byte-identity hash reads where the evidence says so. Earlier full suites, RF result streams and raw property files were not executed or read. No further source execution is required for publication of these artifacts.

## Learner screenshot acceptance — 15 November 2026

The learner supplied the SQL88 DBeaver result on 2026-11-15 (Australia/Sydney). All seventeen rows and 153 data fields are fully visible: 34 band labels, 68 integer counts, 34 percentages and 17 complete PASS values. No data cell is NULL or clipped. Eight column headers are fully visible; the final header is clipped after the visible prefix check_sta. Its complete name check_status comes from the frozen SQL88 output contract, not a fully visible screenshot header. The seventeen PASS values beneath it are visible. See [machine-readable acceptance](../data/retailrocket_rf_basket_concentration_learner_acceptance.json).

| recency_band | frequency_band | visitor_ids | candidate_baskets | top1_baskets | top1_share_pct | top5_baskets | top5_share_pct | check_status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| R_LT_7D | F_1 | 413 | 413 | 1 | 0.242131 | 5 | 1.210654 | PASS |
| R_LT_7D | F_2 | 29 | 58 | 2 | 3.448276 | 10 | 17.241379 | PASS |
| R_LT_7D | F_3_4 | 15 | 48 | 4 | 8.333333 | 18 | 37.500000 | PASS |
| R_LT_7D | F_5_PLUS | 19 | 1517 | 502 | 33.091628 | 1213 | 79.960448 | PASS |
| R_7_TO_LT_30D | F_1 | 1711 | 1711 | 1 | 0.058445 | 5 | 0.292227 | PASS |
| R_7_TO_LT_30D | F_2 | 119 | 238 | 2 | 0.840336 | 10 | 4.201681 | PASS |
| R_7_TO_LT_30D | F_3_4 | 30 | 99 | 4 | 4.040404 | 20 | 20.202020 | PASS |
| R_7_TO_LT_30D | F_5_PLUS | 24 | 402 | 85 | 21.144279 | 233 | 57.960199 | PASS |
| R_30_TO_LT_60D | F_1 | 2366 | 2366 | 1 | 0.042265 | 5 | 0.211327 | PASS |
| R_30_TO_LT_60D | F_2 | 176 | 352 | 2 | 0.568182 | 10 | 2.840909 | PASS |
| R_30_TO_LT_60D | F_3_4 | 42 | 136 | 4 | 2.941176 | 20 | 14.705882 | PASS |
| R_30_TO_LT_60D | F_5_PLUS | 25 | 916 | 148 | 16.157205 | 524 | 57.205240 | PASS |
| R_GE_60D | F_1 | 6166 | 6166 | 1 | 0.016218 | 5 | 0.081090 | PASS |
| R_GE_60D | F_2 | 424 | 848 | 2 | 0.235849 | 10 | 1.179245 | PASS |
| R_GE_60D | F_3_4 | 90 | 292 | 4 | 1.369863 | 20 | 6.849315 | PASS |
| R_GE_60D | F_5_PLUS | 70 | 2110 | 162 | 7.677725 | 639 | 30.284360 | PASS |
| TOTAL | TOTAL | 11719 | 17672 | 502 | 2.840652 | 1318 | 7.458126 | PASS |

Five top5_share_pct displays omit trailing zeros: 37.5, 20.20202, 57.20524, 0.08109 and 30.28436. One uses one decimal, four use five decimals, and the other twenty-nine percentage cells use six. Twelve integer fields contain thousands separators. Normalization changes display format only; no exact underlying division precision is claimed. DBeaver row numbers and header text are excluded from the 153-field data count.

The RF groups still partition 11,719 transaction-recorded IDs and 17,672 full-window candidate baskets. Concentration percentages use the current row's candidate_baskets. TOTAL recomputes the top one and five across all IDs: 502 and 1,318 baskets, respectively, representing 2.840652% and 7.458126%. These totals are not sums of the sixteen cell-top counts. R_LT_7D/F_5_PLUS has 19 IDs and 1,517 baskets; its top one contributes 502 (33.091628%) and its top five contribute 1,213 (79.960448%). This is evidence of concentrated recorded contribution within that group, not a fraud, bot, customer-value or loyalty classification.

The screenshot verifies returned aggregates and complete PASS values, not the hidden 11,719-by-eight ranked stream, deterministic tied-ID order, input reconstruction or synthetic cases. Frozen assistant evidence supports those checks. The source files, learner database, SQL and fixtures were not rerun for this acceptance. No screenshot or individual identifiers are published. Previous pending statements above remain unchanged as historical context; this appendix records learner acceptance of the descriptive concentration report. Independent temporal validation and targeting-effect evaluation remain separate work.

Accepted report SHA-256: `e8385fde4a98f505d7b0c12b3e4ca0d17d23a47527d13f696e64a2b5f6b66897`. The full prior 12,222-byte method/results document is preserved at `286536ed6bc15569dd3ba5dabfed4f8844f22ac34ecd9e8869e6b9b8dbf57017`. Its frozen 7,369-byte method prefix remains `0cce795a2e7d4dbbacd85b0b37ae518b415730bee0f6c818a4592cb14fad8ee7`.
