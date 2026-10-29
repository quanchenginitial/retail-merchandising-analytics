# Full-catalog paired forecast improvement coverage

## Purpose

SQL39's six development-error rows are learner accepted. WEEKDAY4 has lower overall MAE and macro RMSSE in all three windows, but an average does not tell us how widely the improvement is shared. [SQL40](../sql/40_compare_full_catalog_paired_improvement.sql) compares the two forecasts within each identical product-store series to count improvements, ties and deteriorations, then summarize their magnitudes.

The [fixed protocol](FULL_CATALOG_PAIRED_IMPROVEMENT_PROTOCOL.md) was written before the new paired summaries. This is a descriptive follow-up to the observed development scores. Keep the full released roster, both unchanged model formulas and the three development windows. No outcome-based subset, per-series hindsight model selection or final-holdout actual data enters this step.

## What is paired

There are 30,490 product-store series at each origin, three origins and **91,470 pairs**. Each pair contains two model diagnostics for the same 28 days, actual quantities and training history. SQL39's source, saved-candidate and score-validation CTEs are retained. A missing model, duplicate pair, different actual total or inconsistent scale must fail.

MAE compares every series, including zero outcomes and series without a valid RMSSE scale. RMSSE compares only pairs with the same defined positive training scale. First-window RMSSE coverage is 30,480 compared and ten excluded; later windows compare all 30,490. The first-window exclusion reason, established by independent source verification, is no positive training quantity before that cutoff. These ten series remain in MAE. Their absence from RMSSE is visible in the report.

For MAE, compare exact absolute-error quarter sums. For RMSSE, compare exact squared-error sums in sixteenths under the common positive scale. Never use rounded displayed scores or a floating-point tolerance to declare a tie. A small improvement may round to a displayed zero difference while remaining a win.

## Reading the output

The report has six rows: each development origin has an MAE row followed by an RMSSE row. It uses twelve fields:

| Field | Meaning |
| --- | --- |
| origin / metric | Development window and the metric being compared |
| total_series | All 30,490 product-store series |
| compared_series / excluded_series | Eligible and excluded pairs for that metric |
| weekday4_wins / ties / snaive7_wins | Exact comparison of each complete 28-day series |
| weekday4_win_pct | 100 × WEEKDAY4 wins / compared pairs; ties remain in the denominator |
| mean_delta | Equal-weight mean of paired metric differences |
| median_delta | Median of the paired differences, averaging both central differences for an even count |
| check_status | PASS when source, candidate, pairing and coverage checks pass |

Both differences use **WEEKDAY4 − SNAIVE7**. Negative favors WEEKDAY4; positive favors SNAIVE7. MAE differences are units per product-store day; RMSSE differences are dimensionless. Neither is a percentage reduction. The win percentage measures the share of eligible series that improve, not forecast accuracy or daily win frequency.

The median of paired differences is not the difference between separate model medians. A better mean can coexist with many losses, since changes have different magnitudes. No pooled TOTAL row mixes the repeated series across origins. Win/tie/loss counts sum to compared_series; compared plus excluded equals total_series. If a fixture has no RMSSE-eligible series, its percentage and differences stay NULL.

Mean paired differences reconcile to full-precision aggregate score differences on the same cohort. Rounded SQL39 display values may differ in the last decimal when subtracted. SQL keeps exact rational arithmetic for MAE and win percentage, and a stable difference-of-squares formula for RMSSE; an independent 70-digit Decimal reference directly subtracts the two roots.

## Independent verification

The [runner](../validation/preflight_full_catalog_paired_improvement.py) uses original CSVs read-only and an isolated temporary DuckDB database. It never opens the learner's database. Reused packed history arrays and streaming checks cover all 58,327,370 history triples, the separate index map/calendar and fact date/week mappings, and the 6,829,760 saved forecasts across fourteen fields.

One guarded calculation exports the literal SQL40 report, paired details, model diagnostics, unrounded paired aggregates and the reconstructed SQL39 report. Each of the 91,470 paired rows has fourteen exact key/integer/status fields plus three independently checked numeric fields. Each of the 182,940 diagnostics has fifteen exact fields plus its numeric RMSSE. The unchanged 5,122,320 daily errors are not directly exported and compared anew here; their SQL39 validation remains part of the immutable lineage.

The runner reconciles accepted SQL38 candidates, accepted SQL39 diagnostics/report and the overlapping pilot SQL37 paired report. Targeted fixtures exercise the new paired aggregation boundaries. Public evidence contains only aggregate results, coverage and fingerprints; private detailed rows and databases are removed after preservation checks.

The executed [machine evidence](../data/full_catalog_paired_improvement_preflight.json) records **six rows × twelve columns, all PASS**, and **8 focused fixtures passed** (6 valid scenarios and 2 rejected corruptions). All indexed history, mapping/calendar, saved-candidate, diagnostic and paired comparisons passed. Exact pair classifications match independent integer comparisons; roots, paired RMSSE differences and unrounded aggregates match the 70-digit Decimal reference within fixed tolerances. Mean paired differences also reconcile to full-precision development aggregate differences on the same cohort.

The SQL38 construction fingerprint, SQL39 diagnostics/report and overlapping SQL37 paired report reconcile. Original sources, saved candidates, relevant inputs and historical dependencies remain unchanged. Private temporary databases and detailed exports were removed. **Learner SQL40 execution remains pending.**

### Independently verified aggregate report

| Origin | Metric | Compared | Excluded | WEEKDAY4 wins | Ties | SNAIVE7 wins | WEEKDAY4 win % | Mean delta | Median delta |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| DEVELOPMENT_1 | MAE | 30490 | 0 | 16469 | 4216 | 9805 | 54.0144 | -0.131612 | -0.035714 |
| DEVELOPMENT_1 | RMSSE | 30480 | 10 | 21997 | 3552 | 4931 | 72.1686 | -0.154763 | -0.104405 |
| DEVELOPMENT_2 | MAE | 30490 | 0 | 16410 | 3484 | 10596 | 53.8209 | -0.127279 | -0.035714 |
| DEVELOPMENT_2 | RMSSE | 30490 | 0 | 22296 | 2823 | 5371 | 73.1256 | -0.159516 | -0.111300 |
| DEVELOPMENT_3 | MAE | 30490 | 0 | 17019 | 3178 | 10293 | 55.8183 | -0.158501 | -0.035714 |
| DEVELOPMENT_3 | RMSSE | 30490 | 0 | 23146 | 2540 | 4804 | 75.9134 | -0.175844 | -0.121692 |

Every row has total_series 30,490. The first RMSSE row excludes the ten source-confirmed no-positive-training series; the remaining rows have no exclusions. These are assistant development preflight results, awaiting learner screenshot acceptance.

WEEKDAY4 improves MAE for 53.8209%–55.8183% of series and RMSSE for 72.1686%–75.9134% of eligible series across the three windows. All six paired medians are negative. A strict majority improves for each metric/window, while many ties and SNAIVE7 wins remain; this supports further subgroup investigation rather than claiming uniform improvement or choosing a hindsight model per series.

Two display examples illustrate rounding: DEVELOPMENT_1 MAE mean_delta is −0.131612, whereas subtracting the displayed SQL39 MAEs gives −0.131611; DEVELOPMENT_2 RMSSE mean_delta is −0.159516, whereas subtracting displayed macro RMSSE values gives −0.159517. The exact MAE identity passes and the maximum full-precision RMSSE reconciliation difference is 7.9 × 10⁻¹⁵. These final-digit differences do not change wins or ties.

Ordered report SHA256: `2b0c2d245522ac25bc24993f156606334fa36a68f3cb70757127b8c596a0913d`.

## Learner execution and interpretation boundary

Open SQL40 in a new editor under the `retail_merchandising` DBeaver connection and execute the complete file. It is read-only, makes no new table and can be repeated. Full-history validation remains part of this query, so allow it to finish before running it again. Return all six rows and twelve columns, splitting wide screenshots if needed.

The same products/stores recur across windows and are not independent experimental trials. These descriptive counts do not establish significance, uniform improvement across categories or stores, final-holdout performance, inventory savings or deployed business benefits. Subgroup checks and eventual final selection remain separate work.
