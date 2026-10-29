# Final holdout protocol for the two-baseline milestone

Frozen on 2026-10-29 before any final-holdout forecast errors are computed or inspected. This document records a decision based on already observed development evidence, not a selection rule registered before those development results. The original evaluation plan and historical protocols remain unchanged.

## Fixed decision and evidence

Select **WEEKDAY4 globally** among the two implemented baseline candidates. Retain **SNAIVE7 as a fixed reference**. Use the saved final-origin predictions in `mart.m5_forecast_baselines_all_28d`; do not refit, blend, round to integer units, correct bias, select a different model for particular products/stores/departments, or update forecasts using actual horizon days.

The accepted three development windows show lower full-catalog MAE and macro RMSSE for WEEKDAY4. The paired-series reports retain ties and SNAIVE7 wins, so the choice does not imply every series improves. All 21 department/window and all 30 store/window averages favor WEEKDAY4 on those two error measures; absolute bias improves in 11/21 department groups and 20/30 store groups. These repeated, dependent comparisons do not establish statistical significance, causal impact or deployed business benefit.

The decision is frozen independently of how the final comparison turns out. If WEEKDAY4 loses on the final period, retain and report that result and the original choice. Do not tune against this period and then describe the retuned result as a fresh final test. PASS checks data and calculation integrity, not whether the selected model wins.

This completes a **baseline-only forecasting milestone**, subject to actual execution and learner acceptance. Tree/Python forecasting remains an unimplemented extension. Once this holdout is inspected, subsequent model development needs genuinely untouched evaluation data for a new final test; otherwise it must be explicitly labelled exploratory retrospective comparison on an already exposed period. The historical plan's requirement for reproducible baselines is met; no tree model is claimed as completed.

Evidence available at freeze:

| Accepted report | Ordered report SHA256 |
| --- | --- |
| SQL39 full-catalog development errors | `e85b813c4467dd9cee33d18fd5de0f74598fa61fa8c142f5b55830b3aae512ac` |
| SQL40 paired-series development coverage | `2b0c2d245522ac25bc24993f156606334fa36a68f3cb70757127b8c596a0913d` |
| SQL41 department development errors | `7f5af82dce08cd2dc28c5bfdac8da4a35a3e804c1543abb5503ac102fd303a4c` |
| SQL42 store development errors | `e78a15f0d2dcf329c30346a3583b3198b3fe98e52751d9aeab57d269cfbab156` |

SQL42 learner acceptance SHA256 is `889e002b20167033c37eee53b9f0805599e2297c8aec6df87290dfee16cfbbde`. Fourteen substantive fields were visually matched for all thirty rows; the clipped status column is covered by the user's explicit all-PASS confirmation. It is not described as fully visible in the screenshot.

## Fixed scope and time

Keep the full retrospective released roster: **3,049 products × 10 stores = 30,490 product-store series**, all seven departments, three categories and three states. Retain zero-sales and undefined-scale series. No performance-based assortment or April ABC/XYZ filtering is allowed. This is not a reconstruction of historically active assortment.

The only scored origin is `FINAL_HOLDOUT`: training d1–d1913, ending **2016-04-24**; forecast d1914–d1941, **2016-04-25–2016-05-22**, exactly 28 days. Each model has **853,720** forecast–actual positions. Compare the **853,720 distinct final actual records** separately from **58,327,370 historical training records**. The two models share the same targets.

The final forecasts already exist and their construction remains fixed: SNAIVE7 repeats the last seven observed training days; WEEKDAY4 repeats the means of the last four observations of each weekday. Preserve exact quarter-unit values. All model inputs and RMSSE scales end at d1913. Target observations may enter the error calculations only. Prices, future prices, target-derived features and later calendar days d1942–d1969 do not enter predictions, training scales or scored target rows. Complete calendar integrity checks retain their previously accepted scope.

Earlier engineering reconciliation inspected the full released snapshot and totals. This is the first forecast-error evaluation of the reserved final period, not a claim that its data were wholly unseen. Repeating the identical frozen computation for assistant verification and learner reproduction is one evaluation design, not repeated model selection. A verified implementation defect must be documented and repaired without changing the decision or scope; report such reruns transparently.

## Fixed report and metrics

SQL43 is a read-only query with **2 rows × 12 columns**, ordered FINAL_HOLDOUT/SNAIVE7 and FINAL_HOLDOUT/WEEKDAY4. Use the same field contract as SQL39:

`origin, model, series_count, evaluated_rows, actual_units, predicted_units, mae, mean_error, rmsse_valid_series, rmsse_undefined_series, macro_rmsse, check_status`.

Each row retains 30,490 series and 853,720 positions. No TOTAL row or pooling with development scores is introduced. Interpret macro RMSSE as the principal cross-series comparison, alongside MAE, signed bias and eligibility; there is no retrospective numerical performance acceptance threshold or significance claim. Record the selected/reference roles in the documentation rather than changing the accepted metric columns.

MAE and signed mean error (forecast minus actual) equally weight every product-store-day position. Keep exact quarter-error integer numerators and squared-error sixteenths, using a sufficiently wide integer type before multiplication. Zero observations and predictions remain; missing observations are errors, not zeros. A negative bias means underprediction, not automatically better performance.

For each series use only d1–d1913 to find its first strictly positive observation s and compute scale = sum of squared successive differences from s+1 through T, divided by T−s, with T=1913. Exclude the leading-zero-to-first-positive jump but keep later zeros. No positive training observation, fewer than two retained observations, or zero scale makes RMSSE undefined even when final error is zero. Never fill with epsilon or zero. Keep those series in MAE/bias and report their status groups and coverage.

Macro RMSSE is the equal-weight mean of defined per-series RMSSE values, not a pooled root, revenue-weighted score or official M5 WRMSSE. Both models share the same eligibility. An empty valid cohort yields NULL macro RMSSE. Format metrics to six decimals only after computing unrounded values. Any reported relative reduction is `(reference − selected) / reference × 100`, with a zero reference explicitly undefined; it is an error reduction, not an accuracy percentage.

## Independent verification and preservation

Use only original read-only CSVs and a private temporary DuckDB database; never open or alter the learner's persistent database. Freeze/publish this protocol before reading final target quantities for the new evaluation. Pin protocol, SQL, validator, sources and historical dependencies. Preserve the exact SQL42 validated CTE prefix, with a separately bounded final-target projection and final-origin calculations, to retain historical guards and controls.

Independently reconstruct and compare all 58,327,370 indexed training triples, complete mappings/calendar and all 6,829,760 saved candidate rows across fourteen fields. Verify all 853,720 indexed final target triples and their date/week mappings. Check final target keys, exact 28-day coverage, unique model/series/day joins, valid nonnegative integer quantities, source relationships and no row multiplication or loss. Detect balanced missing/duplicate keys rather than relying on overall counts alone. A corrupted saved prediction must fail, not be silently replaced by a recalculation.

In one guarded execution compare **1,707,440 final error rows × 12 fields**, **60,980 final model/series diagnostics × 16 fields**, status-group aggregates and the literal two-row report against an independent reference. Reference quarter errors, integer sums and training-scale calculations are exact; use Decimal precision 70 for roots and means, with the inherited absolute tolerance 1e-12 plus relative tolerance 1e-13. Record root-sum deviations separately from root and mean deviations. No real product identifiers or individual error records are published.

Preserve accepted development diagnostics, paired/department/store controls and literal SQL39/40/41/42 reports in the same guarded calculation, together with accepted candidate and pilot fingerprints. Reuse validated references without rerunning historical fixture suites. Directly compared final errors are a new stream; do not describe this as a new export of the 5,122,320 development error rows.

Focused synthetic checks cover: hand-calculated fractional forecasts with zeros and multiple stores; final-target mutation affecting only errors, not saved predictions, training scales or development outputs (including a case where the selected model loses without failing integrity checks); undefined training scales even when targets become positive; balanced missing/duplicate target keys; invalid/null series or final day/date mappings; null/negative/noninteger target quantities; and damaged saved final forecasts. Record executed case/subcase counts honestly rather than treating this list as already passed.

After comparison, verify sources, training/target projections, saved candidates, earlier results and dependencies remain unchanged; remove private exports and temporary databases. Publish code, aggregate results and fingerprints only. Distinguish assistant preflight from learner execution and screenshot acceptance. A final-period score does not establish deployment, future performance, stockout detection, inventory saving or revenue improvement.
