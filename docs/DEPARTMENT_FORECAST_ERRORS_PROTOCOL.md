# Fixed protocol: department development forecast errors

## Business question and fixed comparison

The learner has accepted SQL39's full-catalog aggregate errors and SQL40's paired improvement coverage. WEEKDAY4 has lower overall MAE and macro RMSSE in all three development windows, with a strict majority of eligible series improving, but ties and SNAIVE7 wins remain. [SQL41](../sql/41_compare_department_forecast_errors.sql) asks whether the aggregate advantage holds within each released product department, and whether each department is overpredicted or underpredicted.

Freeze this protocol before computing new department summaries. Retain the [evaluation plan](EVALUATION_PLAN.md), [full-catalog error contract](FULL_CATALOG_DEVELOPMENT_ERRORS_PROTOCOL.md), [paired contract](FULL_CATALOG_PAIRED_IMPROVEMENT_PROTOCOL.md), both baseline formulas and the complete 30,490-series roster. This is descriptive subgroup exploration following observed development results, not an independent confirmatory test, new model, per-department hindsight policy or final model selection.

Use **all seven released departments**, all 3,049 products and all ten stores. Department identifiers are anonymous dataset codes; do not invent their real-world product meanings. Use the accepted source-derived product-to-department mapping without outcome-dependent regrouping. No department, store, positive-sales condition, ABC/XYZ label or RMSSE eligibility filter may remove a series from the overall scope.

## Windows and output shape

| Origin | Training cutoff | Scored dates |
| --- | --- | --- |
| DEVELOPMENT_1 | d_1829 / 2016-01-31 | 2016-02-01–2016-02-28 |
| DEVELOPMENT_2 | d_1857 / 2016-02-28 | 2016-02-29–2016-03-27 |
| DEVELOPMENT_3 | d_1885 / 2016-03-27 | 2016-03-28–2016-04-24 |

Every series has the same 28 scored positions. Aggregate the existing 182,940 model/origin/series diagnostics into **42 department/model/origin totals**, then pair the two model totals to produce **21 report rows**, ordered by origin then dept_id. Return these fourteen fields:

`origin`, `dept_id`, `series_count`, `rmsse_valid_series`, `rmsse_undefined_series`, `snaive7_mae`, `weekday4_mae`, `mae_delta`, `snaive7_mean_error`, `weekday4_mean_error`, `snaive7_macro_rmsse`, `weekday4_macro_rmsse`, `rmsse_delta`, `check_status`.

All seven departments must appear once per origin. No pooled-origin or TOTAL row is added. Within each origin, department series counts sum to 30,490; valid and undefined counts sum to their accepted SQL39 controls. DEVELOPMENT_1 has 30,480 valid and ten undefined scales globally, and DEVELOPMENT_2/3 each have 30,490 valid with none undefined. The department allocation of those exclusions is a new result, not assumed from overall counts.

Final-holdout actual quantities d_1914–d_1941 remain uninspected and unscored. Validating the saved final-origin forecasts against historical construction values is allowed. Earlier development outcomes can enter later origins' history, but each forecast and training scale retains its own cutoff.

## Department assignment and preservation

Reuse SQL40's complete validated CTE prefix without changing source, candidate, scoring or pair calculations. LEFT-join diagnostics to the complete validated product dimension. Require exactly one non-null department assignment for every product and every diagnostic, consistent with original sales-file metadata across stores. Unknown, missing, null, duplicate or inconsistent mappings must fail rather than remove or multiply observations.

Check counts and keys before and after assignment, complete department/model/origin coverage, identical actual totals and eligibility across the paired models, and the fixed full-catalog membership. All ten stores contribute to every department's roster. Report counts are product-store series, not unique products; a product appears at ten stores in this released retrospective roster. This is not reconstructed historical active assortment.

The query is read-only, creates no table and preserves accepted forecasts and existing inputs. Score stored candidate values after validation; do not repair damaged candidates by substituting expected forecasts.

## Metrics and exact differences

For each department/model/origin, MAE is the sum of absolute error quarters divided by `4 × 28 × series_count`. Mean signed error is the signed quarter sum divided by the same denominator. Both use all series and days, including zero outcomes and undefined RMSSE series. Positive mean error means overprediction and negative means underprediction. It is an average per product-store day, not a department total or percentage; cancellation can hide opposing errors.

Keep quarter predictions and exact integer sums until final display. Set `mae_delta = WEEKDAY4 MAE − SNAIVE7 MAE` using the difference of unrounded integer numerators. Negative favors WEEKDAY4. Do not subtract displayed rounded scores or take differences of absolute biases.

Retain SQL39's first-positive-training-day RMSSE scale, with later zeros included and the leading zero-to-first-positive jump excluded. No positive training observation, insufficient retained history or zero scale leaves RMSSE undefined. Every department/model macro RMSSE is the equal-weight mean of its valid series roots. Both models must have the same valid cohort. Zero-valid departments have NULL for both macro RMSSE values and their delta, while retaining MAE/bias and explicit undefined counts.

Compute `rmsse_delta` as the equal-weight average of the accepted stable per-series paired RMSSE differences within the department. Reconcile it to the difference of the two unrounded department macro RMSSE values. Independently verify by direct subtraction of 70-digit Decimal roots. Use the inherited absolute/relative tolerances and exact NULL/status comparisons. These quantities are dimensionless, unweighted bottom-level metrics, not official WRMSSE.

Display all metric values and deltas to six decimals, rounded only at the end. Last-digit differences between the reported delta and arithmetic on the two displayed scores are expected when rounding occurs at different stages. Coverage counts and exact arithmetic controls must not depend on display precision.

## Reconciliation and interpretation

Check department integer totals, counts and all relevant keys against the accepted global SQL39 diagnostics. MAE and signed bias reconstruct the global values when weighted by department **series counts** (equivalently their 28-day position counts). Macro RMSSE reconstructs the global value when weighted by department **valid-series counts**. Never average the seven displayed department means equally, mix these denominators, use rounded display values for reconciliation, or treat undefined groups as zero-valued scores.

The report compares the two methods within each department and origin. Different department unit volumes can produce different absolute MAEs, so a larger MAE alone is not a ranking of model quality across departments. A lower department mean does not prove that every product or store in that department improves. Paired group win counts are not reported by SQL41; do not infer them from its mean delta. Sign reversals in mean error are descriptive evidence, not proof of a cause.

PASS verifies engineering, grouping and metric controls. These repeated, dependent development comparisons do not establish significance or a causal intervention effect. Keep all department results, including ties, deterioration and ambiguous outcomes. Later store analysis and any model-selection decision remain separate work; no final performance, inventory benefit or revenue gain is claimed.

## Independent preflight and public evidence

Use original CSVs read-only and a private temporary DuckDB database under resolved ignored repository tmp. Never open the learner's persistent database. Pin this file, earlier SQL/validators, source hashes and accepted evidence before full-data execution; preserve them afterward and remove private detail exports/databases.

Reuse direct source comparisons of all 58,327,370 indexed history triples, the complete index/item/store map, independently checked calendar and separate fact date/week mappings, and all 6,829,760 saved forecasts across fourteen fields. Directly verify original product/department assignment and each assigned model diagnostic. This remains three exported history fields plus separate mapping/calendar checks, not a six-field history CSV comparison.

Use one guarded execution to export the literal SQL41 report, all 182,940 model diagnostics with department assignment (seventeen fields: sixteen exact plus RMSSE), all 91,470 unchanged paired rows, the 42 department/model/origin internal totals and unrounded controls, and literal SQL39/40 reports from the same calculation. Independently reconstruct department metrics from original source quantities and metadata using exact integers and Decimal-70 roots. Preserve base diagnostic and paired fingerprints and reconcile the accepted SQL38/39/40 reports and overlapping pilot evidence. Do not export or claim a new direct comparison of the unchanged 5,122,320 daily-error rows.

Use focused fixtures for unequal group sizes and weighting, product/store attribution, all-undefined department scales, opposing signed biases, unrounded deltas and damaged/missing/duplicate department mappings. Do not repeat unrelated frozen suites without a new concern. State the exact executed scope and fixture counts in machine evidence.

Publish only department-level aggregates, coverage, source/protocol lineage and fingerprints. Keep real product identifiers, individual product-store rows, error/quantity arrays, screenshots and database files private. Assistant preflight and learner screenshot acceptance remain separate evidence scopes.
