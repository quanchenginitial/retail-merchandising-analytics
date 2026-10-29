# Fixed protocol: store development forecast errors

## Question and fixed scope

SQL41's department comparison is learner accepted. WEEKDAY4 has lower MAE and macro RMSSE in all 21 department/window comparisons, but absolute signed bias improves in eleven and worsens in ten. [SQL42](../sql/42_compare_store_forecast_errors.sql) checks whether the same aggregate advantage holds within every store, and identifies store-level overprediction or underprediction. Do not infer store results from department averages.

Freeze this protocol before computing the new store summaries. Retain the [evaluation plan](EVALUATION_PLAN.md), [department contract](DEPARTMENT_FORECAST_ERRORS_PROTOCOL.md), [full-catalog error contract](FULL_CATALOG_DEVELOPMENT_ERRORS_PROTOCOL.md) and [paired contract](FULL_CATALOG_PAIRED_IMPROVEMENT_PROTOCOL.md). Keep both model formulas, all 30,490 product-store series and the three development windows unchanged. This is descriptive subgroup exploration after observed development results, not an independent confirmatory test or a new model-selection policy.

Include **all ten stores and all 3,049 products at every store**, with all seven departments represented. This is the fixed released retrospective roster, not a reconstruction of the assortment active at each historical origin. No store, department, positive-sales condition, outcome, ABC/XYZ label or RMSSE eligibility filter may remove series. Use only source store and state identifiers; state is context, not a pooled reporting level or an invented store location.

## Windows and report

| Origin | Training cutoff | Scored dates |
| --- | --- | --- |
| DEVELOPMENT_1 | d_1829 / 2016-01-31 | 2016-02-01–2016-02-28 |
| DEVELOPMENT_2 | d_1857 / 2016-02-28 | 2016-02-29–2016-03-27 |
| DEVELOPMENT_3 | d_1885 / 2016-03-27 | 2016-03-28–2016-04-24 |

Each series has the same 28 scored positions. There are **60 store/model/origin totals** and **30 paired store report rows**, ordered chronologically by origin then store_id. Every row must include all 3,049 series for its store (85,372 positions per model). No TOTAL, state aggregation or pooling across origins is added.

Return fifteen fields in order: `origin`, `store_id`, `state_id`, `series_count`, `rmsse_valid_series`, `rmsse_undefined_series`, `snaive7_mae`, `weekday4_mae`, `mae_delta`, `snaive7_mean_error`, `weekday4_mean_error`, `snaive7_macro_rmsse`, `weekday4_macro_rmsse`, `rmsse_delta`, `check_status`.

Each origin's store counts sum to 30,490. RMSSE coverage must match SQL39: 30,480 valid plus ten undefined in DEVELOPMENT_1, and 30,490 valid with none undefined in each later window. The allocation of those exclusions across stores is a new source-based result; do not infer it from the department allocation.

SQL42 does not read or score final-holdout actual quantities d_1914–d_1941. Saved final-origin forecasts can be validated against historical inputs. Earlier engineering audits included observed-day totals, so this analytical boundary does not mean the final period is wholly unseen. Earlier development outcomes may enter later origins' history; forecasts and RMSSE scales retain their own cutoffs.

## Store/state assignment and unchanged lineage

Reuse SQL41's entire validated CTE prefix without changing its source, candidate, scoring, paired or department rules. Assign every existing model diagnostic through the complete source-validated store-to-state mapping. Each store must have exactly one non-null state, consistent across all original product rows. Preserve every diagnostic key, quantity and scale status; missing, duplicate, null, unknown or inconsistently reassigned mappings must fail rather than drop or multiply observations.

Check the complete ten-store mapping, all 182,940 assigned model diagnostics, all 60 model totals and 30 paired store groups. Both models must share the same actual totals, 28 positions per series and eligibility cohort. A guaranteed health row must raise an error for an empty/damaged mapping instead of returning an empty apparent success.

Score saved candidates after validation, never substitute reconstructed values for damaged forecasts. SQL42 is read-only and creates no table. Preserve accepted predictions, prior reports and existing inputs.

## Metrics, differences and coverage

MAE uses the department-stage definition, now within a store: exact absolute-error quarter sum divided by `4 × 28 × series_count`. Mean error uses the signed quarter sum and the same denominator. Retain all series, zeros and exact quarter-unit predictions. These metrics are units per product-store day, not whole-store daily totals, percentages or accuracy rates. Positive mean error means overprediction and negative means underprediction; cancellation can hide substantial errors.

Compute `mae_delta = WEEKDAY4 MAE − SNAIVE7 MAE` using the unrounded integer numerator difference. Negative favors WEEKDAY4. For bias, compare direction and distance from zero separately; do not interpret a more negative mean error as automatically better.

RMSSE retains the original training-only first-positive-day scale. Exclude the leading zero-to-first-positive jump, retain later zeros, and keep undefined scales NULL when training has no positive quantity, insufficient retained history or zero scale. Both store/model macro RMSSE values are equal-weight means over the same valid series. An all-undefined store keeps MAE/bias and its explicit exclusion count, with NULL for both macro RMSSE values and their delta.

Compute store `rmsse_delta` by averaging the existing stable per-series paired RMSSE differences over the valid cohort. Reconcile it to the difference of the two unrounded store macro RMSSE values. Independently verify by direct subtraction of 70-digit Decimal roots under the inherited absolute/relative tolerances. Keep exact NULL, key, numerator and eligibility comparisons. This is not sales weighting, a pooled root or official M5 WRMSSE.

Display metrics and deltas to exactly six decimal places before any client display suppression of trailing zeros. Avoid output alias collisions that expose an unrounded internal field. Last-digit differences from subtracting the displayed rounded scores are expected; compute before rounding and never use those display differences as a validation reference.

## Reconciliation and interpretation

Store integer totals and coverage must exactly reconstruct SQL39's global controls. MAE and signed bias use **all-series counts** when reconstructing global means; macro RMSSE and its mean paired difference use **valid-series counts**. Base store sizes happen to be equal in this roster, but RMSSE valid counts can differ. Do not automatically average store means equally, use rounded means, or fill undefined groups with zero.

Retain the literal SQL39/40/41 reports and their accepted fingerprints. The store view changes the grouping level, not predictions, scored observations, formulas or department findings. The unchanged daily-scoring calculation still runs, but no new direct export/comparison of 5,122,320 daily-error rows is claimed.

Compare the two methods within each store/window. Store sales volumes and histories differ, so raw MAE alone is not a store-performance ranking. A favorable store average does not show that every product or department improves or provide a within-store win percentage. State labels do not identify geographic causes. Retain adverse and ambiguous outcomes alongside favorable ones.

PASS verifies engineering, assignment and metric controls. These repeated dependent development comparisons are descriptive, not significance tests or evidence of causal, inventory or revenue benefits. Do not pick hindsight methods or bias corrections for individual stores. Candidate development, final selection and final-holdout evaluation remain separate work.

## Independent verification and public evidence

Use original CSVs read-only and a private temporary DuckDB database under resolved ignored repository tmp; never open the learner's persistent database. Pin this protocol, prior code/validators, source hashes and accepted evidence before full-data execution. Keep earlier files immutable and remove private details/databases after preservation checks.

Retain complete source checks: 58,327,370 indexed history triples, independent index/item/store and product/department assignments, calendar and separate fact date/week mappings, and 6,829,760 saved forecasts across fourteen fields. Independently derive and check the complete store/state map from original metadata across products. This is a three-field history export with separate mapping/calendar checks, not a six-field history CSV comparison.

Use one guarded execution for the literal SQL42 report and all required store-assigned diagnostics, store model totals, unrounded store pair/weighted controls, plus preserved department/pair streams and literal SQL39/40/41 reports. Verify exact fields directly and floating roots, sums, means and deltas with independent Decimal references. Keep root-sum numerical deviations separate from per-series and mean-metric deviations. Reconcile original-source references, earlier full-catalog fingerprints and overlapping pilot evidence; avoid millions of Python dictionaries.

Use proportionate focused fixtures for store/state attribution, different valid-series counts with equal base store sizes, all-undefined stores, signed-bias cancellation, unrounded deltas, and damaged/missing/duplicate mappings. Do not rerun unrelated frozen suites. Publish only store/state-level aggregate results, coverage, provenance and fingerprints. Keep real product identifiers, individual diagnostics, quantity/error arrays, screenshots and databases private. Assistant preflight and learner screenshot acceptance remain distinct.
