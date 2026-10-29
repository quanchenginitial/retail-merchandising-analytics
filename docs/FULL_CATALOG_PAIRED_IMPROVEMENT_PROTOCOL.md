# Fixed protocol: full-catalog paired forecast improvement

## Question and fixed scope

The learner has accepted SQL39's six full-catalog development-error rows. WEEKDAY4 has lower overall MAE and macro RMSSE in all three development windows, with signed mean error closer to zero. [SQL40](../sql/40_compare_full_catalog_paired_improvement.sql) asks how many individual product-store series improve, tie or worsen under this same comparison. An overall average does not establish the breadth of improvement.

Freeze this protocol before computing the new full-catalog paired results. Retain the earlier [pilot paired protocol](SERIES_FORECAST_IMPROVEMENTS_PROTOCOL.md), [full-catalog error protocol](FULL_CATALOG_DEVELOPMENT_ERRORS_PROTOCOL.md) and [evaluation plan](EVALUATION_PLAN.md). Do not change either model, the released retrospective roster, metric definitions, windows or eligibility rules in response to the results. Both methods remain candidates; this is not per-series model selection or final selection.

Use all **30,490 product-store series**, all 3,049 products and ten stores. Do not filter on outcomes, sales positivity, April ABC/XYZ labels, RMSSE eligibility or product performance. Use only the three accepted development windows:

| Origin | Training cutoff | Scored dates |
| --- | --- | --- |
| DEVELOPMENT_1 | d_1829 / 2016-01-31 | 2016-02-01–2016-02-28 |
| DEVELOPMENT_2 | d_1857 / 2016-02-28 | 2016-02-29–2016-03-27 |
| DEVELOPMENT_3 | d_1885 / 2016-03-27 | 2016-03-28–2016-04-24 |

Each model/origin has 853,720 forecast positions. Pair the two model diagnostics on origin, item_id and store_id, producing **91,470 pairs** from **182,940 model-specific diagnostics**. Each pair shares the same 28 actual observations and origin-specific historical scale. Missing, duplicate or mismatched counterparts must fail rather than disappear in an inner join.

No final-holdout actual quantities from d_1914–d_1941 are inspected or scored. The saved final-origin forecasts may be checked against their historical construction values. No future price or retrospective segmentation enters model construction or comparison.

## Exact comparison and eligibility

Reuse SQL39's validated CTE prefix without modifying its source, saved-candidate, history or scoring rules. Score the persisted forecasts, retaining exact WEEKDAY4 quarter-unit predictions. Check complete history d_1–d_1913 (58,327,370 observations), all source maps/calendar fields and all saved full-catalog candidate keys and construction values. Every origin's RMSSE scale still stops at that origin's training cutoff.

For MAE, compare the exact integer sums of absolute error quarters, since every series has the same 28-day denominator. Define each paired difference as `(WEEKDAY4 absolute-error quarters − SNAIVE7 absolute-error quarters) / 112`. A negative difference is a WEEKDAY4 win, zero is a tie and a positive difference is a SNAIVE7 win. Include all 30,490 series at every origin, regardless of RMSSE eligibility.

For RMSSE, both models must have identical first-positive training day, retained difference count, training squared-difference sum and eligibility status. Eligibility comes solely from common training history. When that scale is positive and defined, compare the two exact squared-error sums in sixteenths: their ordering also orders RMSSE. Never classify winners or ties from rounded or floating display values.

Keep the first-positive-day scale from SQL39: exclude the initial zero-to-first-positive jump, retain later zeros and divide the successive-difference squared sum by T−s. No positive training value, fewer than two retained observations or a zero scale leaves both RMSSE values and their paired difference undefined. Do not replace them with zero or an epsilon. They remain in MAE and in the RMSSE excluded count.

The accepted SQL39 coverage controls are 30,480 RMSSE-valid and ten undefined series in DEVELOPMENT_1, and 30,490 valid with none undefined in DEVELOPMENT_2/3. The first-window undefined reason is no positive training quantity before its cutoff, established by independent source preflight. These counts must reconcile; they are not filters selected to improve the score.

For valid RMSSE pairs, the difference is WEEKDAY4 RMSSE minus SNAIVE7 RMSSE. SQL uses the stable difference-of-squares identity to avoid subtracting nearly equal floating roots: `(SSE_W − SSE_S) × scale_count / (16 × 28 × training_SSE × (RMSSE_W + RMSSE_S))`. Two perfect forecasts give an explicit zero difference. Independently verify using direct subtraction of 70-digit Decimal roots, not by copying that SQL identity. Apply the inherited absolute/relative numeric tolerances and compare NULL eligibility exactly.

## Report and interpretation

Return six rows, chronologically by development origin, MAE then RMSSE, with the same twelve fields as SQL37: `origin`, `metric`, `total_series`, `compared_series`, `excluded_series`, `weekday4_wins`, `ties`, `snaive7_wins`, `weekday4_win_pct`, `mean_delta`, `median_delta`, `check_status`.

Use these identities for each row:

- total_series = 30,490;
- compared_series + excluded_series = total_series;
- weekday4_wins + ties + snaive7_wins = compared_series;
- weekday4_win_pct = 100 × weekday4_wins / compared_series; ties remain in the denominator.

The mean and median summarize the individual **paired differences** among the metric's eligible series. The median is not the difference of the two models' medians. For an even number of observations, average the two central paired differences. Calculate before rounding, with exact rational arithmetic for MAE and win percentage. Display percentages to four decimals and differences to six decimals. A zero-eligible RMSSE cohort returns zero win/tie/loss counts and NULL percentage/mean/median, without inventing a performance value.

Reconcile mean paired differences with the difference of the corresponding full-precision SQL39 aggregate scores over the identical cohort, rather than requiring rounded report arithmetic to match exactly. There is no pooled TOTAL row. Do not weight by sales, prices, revenue or group size beyond one vote per eligible series.

PASS confirms engineering and cohort integrity. The win percentage is not forecast accuracy, a percentage error reduction or a statistical significance level. A negative mean or median does not imply that every series improves. Products and stores recur across windows, so these are descriptive repeated comparisons rather than independent trials. Subgroup analysis, any later selection rule and final-holdout evaluation remain separate stages. Do not choose a hindsight winner for each series or claim inventory/revenue benefits.

## Independent verification and preservation

Use read-only original CSVs and a private temporary DuckDB database under ignored repository tmp. Never open or modify the learner's persistent database. Pin earlier SQL, validators, source hashes, accepted reports, fixed protocols and this file before the full run.

Reuse packed histories and direct stream comparisons from SQL39: all 58,327,370 indexed history triples, the full 30,490-row index/item/store map, the independently verified calendar, separate fact date/week mapping checks, and all 6,829,760 saved forecasts across fourteen fields. This is a three-field direct history stream with separate complete map/calendar checks, not a six-field history CSV comparison.

Execute one guarded scoring/export query that includes the literal six-row SQL40 report, all 91,470 paired rows across seventeen fields, all 182,940 model diagnostics across sixteen fields, unrounded paired aggregates and the SQL39 report reconstructed from the same diagnostics. Compare exact integer/key/status fields directly; verify roots, paired RMSSE differences and unrounded aggregates with Decimal references. Distinguish fourteen exact paired fields plus three numeric fields, and fifteen exact diagnostic fields plus one numeric field. Do not re-export or claim a new direct comparison of the unchanged 5,122,320 daily error rows: their accepted SQL39 lineage remains recorded, while this step directly checks complete series diagnostics and pairs.

Reconcile accepted SQL38 candidate report/fingerprint, accepted SQL39 aggregate report and the overlapping 216-series SQL37 paired report. Only one origin's paired reference needs buffering; avoid millions of Python dictionaries. Focused fixtures cover multi-store pairing, undefined/all-undefined eligibility, two perfect roots, exact winner classification despite rounded ties, paired-median logic and damaged/missing candidates. Do not rerun unrelated frozen suites without new concerns.

Verify that original files, relevant database inputs, saved candidates and historical evidence remain unchanged, then remove private databases and detailed exports. Publish only aggregate results, coverage, execution provenance and fingerprints. Keep real product identifiers, individual paired rows, errors, quantity arrays, screenshots and databases private. Assistant preflight and learner screenshot acceptance are separate evidence scopes.
