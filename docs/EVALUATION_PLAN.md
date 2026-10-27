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

Dates are derived from d_1 = 2011-01-29 and must be checked against calendar.csv. Do not train with test outcomes or use actual earlier days of the 28-day horizon as if they were known at its start. Lag/rolling features must be shifted and generated separately at each origin. Fit imputers, encoders and model choices using training/development data only. Historical future weekly prices are excluded unless an explicit forecast-time pricing assumption is justified; calendar events may be known in advance.

Baselines: repeat the last observed seven-day pattern across the horizon; compare the mean of the previous four observations of the same weekday. Add a tree model only after those baselines are reproducible. Evaluate MAE, mean signed error (forecast minus actual), and RMSSE with its training-only scale. Distinguish macro versus sales-weighted averages. Intermittent series make MAPE unsuitable as the primary score.

For each origin, let s be the first strictly positive training observation and T the last training day. Set scale = sum of squared successive differences from t = s+1 through T, divided by (T-s). RMSSE = sqrt(mean squared error over the 28 forecast days / scale). No positive training observation, fewer than two retained training observations or zero scale makes RMSSE undefined; never replace its denominator with an epsilon. Report affected series, coverage and MAE separately. This removes leading pre-sale zeros for scaling, not from the forecast outcome window. Any alternative seasonal scaling must have a different metric label.

Official M5 WRMSSE is a later optional implementation requiring the complete hierarchy, correct revenue weights, scaling and independent parity checks. A bottom-level RMSSE average must not be labelled official WRMSSE. Retain a simpler model if a more complex one does not improve robustly; no improvement target is promised.

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
