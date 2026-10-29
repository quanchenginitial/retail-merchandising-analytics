# Evaluation and evidence plan

This is a prospective plan, not a results report. Freeze each module's rules after source audit and before inspecting its final evaluation outcomes.

## M5 forecasts

Forecast recorded unit sales for 28 days. Begin with one documented department/store slice for learning and then evaluate the agreed wider scope; record the exact series list and never describe a slice as a full-dataset model.

| Training through | Subsequent 28-day window | Purpose |
| --- | --- | --- |
| d_1829, 2016-01-31 | d_1830–d_1857, 2016-02-01–2016-02-28 | Development fold 1 |
| d_1857, 2016-02-28 | d_1858–d_1885, 2016-02-29–2016-03-27 | Development fold 2 |
| d_1885, 2016-03-27 | d_1886–d_1913, 2016-03-28–2016-04-24 | Development fold 3 |
| d_1913, 2016-04-24 | d_1914–d_1941, 2016-04-25–2016-05-22 | Final holdout, evaluate once after freezing |

The first merchandising analysis uses a fixed 90-day window ending at d_1913: 2016-01-26–2016-04-24 (d_1824–d_1913). Keep the final 28-day holdout out of category/ABC decisions that may affect forecast scope or model selection. Full-snapshot ingestion and engineering reconciliation have already included all observed days and overall totals; these are not forecast evaluations, and no holdout forecast errors have been inspected. Do not describe the final period as wholly unseen data.

Dates are derived from d_1 = 2011-01-29 and must be checked against calendar.csv. Do not train with test outcomes or use actual earlier days of the 28-day horizon as if they were known at its start. Lag/rolling features must be shifted and generated separately at each origin. Fit imputers, encoders and model choices using training/development data only. Historical future weekly prices are excluded unless an explicit forecast-time pricing assumption is justified; calendar events may be known in advance.

Baselines: repeat the last observed seven-day pattern across the horizon; compare the mean of the previous four observations of the same weekday. Add a tree model only after those baselines are reproducible. Evaluate MAE, mean signed error (forecast minus actual), and RMSSE with its training-only scale. Distinguish macro versus sales-weighted averages. Intermittent series make MAPE unsuitable as the primary score.

For each origin, let s be the first strictly positive training observation and T the last training day. Set scale = sum of squared successive differences from t = s+1 through T, divided by (T-s). RMSSE = sqrt(mean squared error over the 28 forecast days / scale). No positive training observation, fewer than two retained training observations or zero scale makes RMSSE undefined; never replace its denominator with an epsilon. Report affected series, coverage and MAE separately. This removes leading pre-sale zeros for scaling, not from the forecast outcome window. Any alternative seasonal scaling must have a different metric label.

Official M5 WRMSSE is a later optional implementation requiring the complete hierarchy, correct revenue weights, scaling and independent parity checks. A bottom-level RMSSE average must not be labelled official WRMSSE. Retain a simpler model if a more complex one does not improve robustly; no improvement target is promised.

### Initial learning-slice protocol (2026-10-29)

The initial scope is all products in the lexicographically first department at the lexicographically first store in the accepted dimensions: **FOODS_1 at CA_1**. Scope selection uses dimension identifiers, not unit sales, ABC/XYZ labels, price changes or forecast errors. Retain every product in that department, including all-zero training series. SQL33 verifies this scope and temporal coverage; its independent preflight records the exact ordered membership fingerprint without publishing the product list. This is a fixed retrospective benchmark roster from the released catalog, not a reconstruction of the assortment known to be active at each historical origin.

Each origin uses an expanding training window beginning at d_1. Keep the four origin/horizon boundaries above unchanged. [SQL33](../sql/33_forecast_scope_and_time_audit.sql) reads selected-scope sales only through d_1913 and uses calendar fields to establish forecast dates. Earlier development target dates legitimately become training history at later origins; each origin's input counts remain bounded by its own cutoff. The audit does not inspect final-holdout unit values (d_1914–d_1941), produce forecasts, compute target-period errors, or establish final-holdout observation coverage. Its audit is the preparation step, not a baseline evaluation.

The already accepted April ABC/XYZ labels include observations occurring after the earlier development origins. Do not use those labels as origin-known features, filters or tuning signals for February/March folds. If such features are introduced later, recompute them from each origin's training data. Descriptive April labels may only be used for clearly labelled retrospective reporting, not as evidence that the same grouping was available when earlier forecasts were issued.

Next, generate all 28 forecasts at each origin from the last seven observed days without updating from target outcomes; compare the previous-four-same-weekday mean under the same origins and scope. Model choice will use development results only. Final-holdout evaluation remains pending until choices are frozen. Neither a single slice nor successful data checks establish full-dataset forecasting ability.

### First candidate: weekly seasonal naive (SQL34)

Generate the first candidate under the frozen scope and all four origins using [SQL34](../sql/34_build_seasonal_naive_forecasts.sql). For training cutoff T and horizon h = 1,...,28, predict the observed units at day `T - 6 + ((h - 1) % 7)`. This repeats the final observed seven-day pattern four times, preserving the weekday alignment. Forecast every scoped series, including zero predictions. All 28 values are fixed using information available at the origin; never update weeks two through four with actual observations from the first forecast week.

Persist the candidate as `mart.m5_forecast_snaive7_28d` with model tag `SNAIVE7`, explicit origin, source day and target day. There are 216 × 28 = 6,048 predictions per origin and 24,192 across all four origins. The four origins have different information cutoffs even though they are constructed in one script. A later origin may legitimately use observations that were future outcomes at an earlier origin.

Generation and correctness checks do not evaluate accuracy. The final-origin baseline is an unscored candidate, not a declaration of the selected final model. Do not join final-holdout actuals or compute their errors during construction. Subsequent steps will compare development results under the same scope and metrics, document model choices, and only then evaluate the final holdout. No accuracy, improvement or business benefit is claimed by saving this baseline.

### Second candidate: four-observation weekday mean (SQL35)

Use [SQL35](../sql/35_build_weekday_mean_forecasts.sql) to construct the second prespecified baseline, model tag `WEEKDAY4`, in `mart.m5_forecast_weekday4_28d`. Scope, four origins and 28-day horizons remain identical to SNAIVE7. For each horizon h, set r = (h-1) modulo 7 and take the arithmetic mean of observed units at days `T-6+r`, `T-13+r`, `T-20+r` and `T-27+r`. All four observations, including zeros, receive equal weight. Use the final 28 calendar days including the cutoff; do not substitute complete M5 retail weeks.

The seven weekday means remain fixed for all four forecast weeks. Retain exact quarter-unit predictions as DECIMAL(18,2), with no rounding to integers. Store the integer sum of the four observations and their source-day boundaries so every mean can be reconstructed. Accumulate source units in a type that safely holds four maximum INTEGER values; calculate the mean with exact decimal arithmetic.

The predicted 28-day total equals the actual last-28-day total because each four-value mean is repeated four times. This is a necessary aggregate construction check, not proof of the individual mapping or predictive accuracy. Validate every saved field and source mapping separately. Preserve the SNAIVE7 candidate for subsequent comparison; do not choose a winner from output smoothness, zero counts or forecast totals. Development-error comparison and final model selection remain later steps, and final-holdout unit values remain excluded from construction.

### First development comparison: fixed aggregation contract (SQL36)

Before computing candidate errors, fix [SQL36](../sql/36_compare_development_forecast_errors.sql) to score SNAIVE7 and WEEKDAY4 on the three development origins only. Each model/origin has 216 series × 28 days = 6,048 prediction–actual pairs; there are 36,288 model-specific error rows and 1,296 model/origin/series diagnostics in total. The two models share 18,144 distinct development actual observations. Validate the saved candidates against their construction rules, then score their persisted values. A corrupted saved forecast must fail rather than being silently replaced with a reconstruction.

For each model and origin, report MAE and mean signed error across all 6,048 daily positions, with equal weight per position. All series have 28 positions, so these also equal the unweighted mean of series MAE/bias. Mean signed error is forecast minus actual: positive indicates overprediction and negative underprediction. These metrics are in units per product-store day, not percentages or sales-weighted metrics. Retain zero observations and zero forecasts; missing evaluation observations are errors, not zeros.

Compute each series' RMSSE using the first-positive training start and scale defined above, separately at its own origin. Include later zero-sales days after the first positive observation, but exclude the jump from a leading zero into that first positive observation. No positive training value, fewer than two retained training observations, or zero training scale leaves RMSSE undefined even when evaluation error is zero. Keep those series in MAE/bias; report valid/undefined RMSSE counts and aggregate status diagnostics with MAE/bias. Never fill undefined RMSSE with zero or epsilon.

The reported `macro_rmsse` is the arithmetic mean of individually computed RMSSE values over valid series. It is not the square root of an average of series ratios, a pooled ratio, a sales-weighted score, or official M5 WRMSSE. If no series has a defined RMSSE, the macro result is NULL. Both models use the same scale-eligibility cohort at each origin.

Preserve WEEKDAY4's quarter predictions throughout evaluation. Exact quarter-unit error numerators and squared-error sixteenths support reconciliation; perform integer products in a wide enough type before summing. Calculate metrics from unrounded values, displaying six decimals only at the final report. Interpret close displayed values using the full-precision evidence rather than treating display rounding as model selection.

SQL36 returns six rows, ordered by development origin and then SNAIVE7/WEEKDAY4, with no pooled TOTAL row. It is read-only and leaves both candidate tables unchanged. Final-origin candidate integrity may be checked without joining its outcomes; d_1914–d_1941 unit values remain excluded and no final-holdout forecast errors are calculated. This comparison supplies development evidence and does not itself select a final model or establish wider-scope performance.

## Behaviour and recommendation

Choose chronological training/development/holdout boundaries after observing only source coverage. Apply all feature construction to events known at the prediction cutoff. Define a complete outcome window and exclude/censor immature episodes consistently. Split or cluster evaluation by visitor as needed to avoid treating repeated events as independent people.

For purchase prediction, compare with a prevalence/simple behavioural baseline and report PR-AUC, calibration and a threshold-based decision table, not accuracy alone. A late transaction is an outcome, not a pre-cart predictor. For basket recommendations, compare with popularity and evaluate on later transactions; report candidate coverage and sparse-item exclusions. Offline recall/lift is not a measured recommendation intervention.

## Anomalies

Start with seasonal residuals or robust historical thresholds. Show the number of candidates and investigate missing source data, price-coverage changes and calendar effects first. Without independently reviewed anomaly labels, report candidates and case reviews rather than precision/recall. Build synthetic faults only as clearly labelled engineering tests; do not mix them with source rows or business findings.

## Experiment extension

Write a hypothetical product-feature protocol: eligibility, randomization unit, primary purchase outcome, cancellations/delivery/margin/performance guardrails, minimum meaningful change, observation window, power inputs, exclusions and stopping rule. Missing guardrail fields remain unavailable; no live experiment is claimed.

Use only corrected Criteo data if access is available. Audit treatment, outcomes, features and missingness; retain assigned treatment for an intention-to-treat style comparison in the released sample. Do not restrict the analysis to exposed users, purchasers or other post-treatment outcomes. The observed treatment ratio alone is not a prespecified randomization ratio, so do not invent a 50/50 sample-ratio-mismatch test. Nonuniform sampling limits reconstruction of the original experiment's population effects. Report uncertainty, sparse conversions and the published data transformation limits. Uplift model selection uses separate held-out data and is optional after the basic comparison is understood.

## Checkpoint evidence

Each completed stage retains input hashes, executable version, scope, checks, results and limitations. Data tests should address plausible failures: duplicate joins, missing prices with positive units, future property joins, invalid numeric casts, censored episodes and time leakage. Add CI only when these checks exist; a GitHub repository alone is not production DevOps evidence.

Final acceptance requires a clean reproducible run, source-to-mart reconciliation, independent calculation checks, honest model evaluation and Power BI numeric/filter verification. Uploaded files, user practice and business deployment have distinct completion states.
