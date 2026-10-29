# Paired coverage of development forecast improvements

## Purpose and fixed contract

[SQL36](../sql/36_compare_development_forecast_errors.sql) established lower aggregate MAE and macro RMSSE for WEEKDAY4 in all three development windows. [SQL37](../sql/37_compare_series_forecast_improvements.sql) asks how widely the improvement is distributed across the same products: how many series improve, tie or worsen, and what the average and median paired differences are. This is a descriptive follow-up to observed development scores, not an independently held-out confirmatory test or a final model-selection rule.

This contract is recorded before inspecting the new paired summaries. Keep the existing [evaluation plan](EVALUATION_PLAN.md), three development windows, fixed FOODS_1 / CA_1 roster of 216 product-store series, 28-day horizons, forecast definitions and RMSSE scaling unchanged. The final holdout remains unscored. Both candidates are validated against their historical construction rules before their persisted values are evaluated.

The separately saved [fixed protocol](SERIES_FORECAST_IMPROVEMENTS_PROTOCOL.md) is the exact document pinned before execution and checked unchanged. This method page also records the executed verification and findings below. On 29 October 2026 (Australia/Sydney), the learner accepted all six rows and twelve displayed fields; the canonical report fingerprint matches historical assistant preflight.

SQL37 is read-only. It reuses SQL36's source, candidate and scoring checks and pairs the two models by origin, item and store. There must be one SNAIVE7 and one WEEKDAY4 diagnostic for each pair, with the same actual total, 28 evaluation positions and identical training-scale eligibility. All 648 origin/series pairs must be retained. Do not restrict this comparison to high-volume products, positive outcomes or a favorable subset.

## Exact win, tie and loss classification

For MAE, compare each model's sum of absolute error quarter-units. Both models have 28 positions, so their per-series MAE denominator is the same: 4 × 28 = 112. WEEKDAY4 wins when its exact integer sum is smaller, ties when equal, and loses when larger. All 216 series are compared, including zero outcomes and zero predictions.

For RMSSE, compare the exact sum of squared error quarter-units (squared-error sixteenths) only for series with a valid positive training scale. The scale and 28-day denominator are identical between the two candidates, and the square root is monotone, so comparing these integer sums gives the same ordering as comparing full-precision RMSSE. Undefined scales remain excluded from this metric and are explicitly counted. The same series still participates in MAE. Never replace undefined RMSSE with zero.

Classify exact equality as a tie. Do not classify from rounded MAE/RMSSE values, displayed differences or a floating-point tolerance. A tiny true improvement can display as a zero difference after rounding while still being a win. Comparisons measure each whole 28-day series, not daily win frequency.

## Paired differences and aggregation

Define delta = WEEKDAY4 metric minus SNAIVE7 metric for the same origin/series. Negative values favor WEEKDAY4 and positive values favor SNAIVE7. MAE differences have units of units per product-store day; RMSSE differences are dimensionless. Neither is a percentage or a relative improvement ratio.

Calculate the unweighted mean and conventional median of these paired deltas over the metric's compared cohort. For an even number of pairs, the median is the average of the two central differences after sorting; for an odd number it is the central difference. The median of paired differences is not generally the difference between the two models' separate medians. A majority of wins need not imply a better mean because the magnitudes can differ.

For MAE, retain exact integer quarter-error differences and rational denominators through final six-place rounding. For RMSSE, calculate differences from the unrounded individual roots, then take their mean and median. Independent high-precision references check the floating calculations. Win/tie/loss counts remain exact regardless of floating display precision.

The SQL implements the RMSSE difference with an algebraically equivalent difference-of-squares identity: scale the exact integer squared-error difference and divide by the sum of the two roots, with an explicit zero when both squared errors are zero. This reduces cancellation for nearly equal roots without changing the metric or its exact winner labels. The independent reference subtracts the roots at 70-digit Decimal precision.

Win percentage is 100 × WEEKDAY4 wins / compared series, displayed to four decimals. Ties remain in this denominator. Excluded RMSSE series do not. If no series is eligible, compared/win/tie/loss counts are zero, excluded equals 216, and win percentage, mean delta and median delta are NULL. This is a valid coverage result, not a score of zero.

## Six-row report

The 12 ordered columns are `origin`, `metric`, `total_series`, `compared_series`, `excluded_series`, `weekday4_wins`, `ties`, `snaive7_wins`, `weekday4_win_pct`, `mean_delta`, `median_delta`, and `check_status`.

Return DEVELOPMENT_1, DEVELOPMENT_2 and DEVELOPMENT_3 in that order, with MAE then RMSSE within each origin. No TOTAL row pools the repeated observations of the same products across origins. For every row:

- total_series = 216;
- compared_series + excluded_series = total_series;
- weekday4_wins + ties + snaive7_wins = compared_series;
- MAE has zero exclusions; RMSSE coverage matches SQL36's valid/undefined counts.

PASS confirms source, saved forecast, pairing, eligibility and aggregation checks. It does not establish a universally superior model, significance, forecast improvement on the final holdout, inventory savings or deployment benefit. Series share a store and dates, and products reappear across origins; these counts are not independent experimental trials. No p-value or confidence claim is attached to win percentages.

## Independent verification and execution

The [runner](../validation/preflight_series_forecast_improvements.py) uses read-only original CSVs and private temporary DuckDB databases under ignored `tmp/`. It never opens the learner's persistent database. It verifies the accepted SQL36 aggregate fingerprint, original scoped inputs, both saved candidates, all paired diagnostics and the six new summary rows against independent references. Detailed product rows remain private; public evidence contains aggregate summaries, coverage and fingerprints only.

The executed assistant preflight matched **413,208 training records across six fields**, the complete SNAIVE7 candidate (**24,192 × 13 fields**), the complete WEEKDAY4 candidate (**24,192 × 15 fields**), **648 paired series records across 17 fields**, and all **six report rows across 12 columns**. Exact integer fields, eligibility and winner labels agreed. Roots and deltas agreed with the 70-digit reference under an absolute tolerance of 1e-12 plus relative tolerance of 1e-13. Maximum absolute deviations were approximately 3.35e-16 for paired roots/deltas and 1.26e-16 for RMSSE mean/median deltas.

The accepted SQL36 six-row report was reproduced, and reconstructed error/scale reference fingerprints matched the frozen earlier evidence. This step compared all 648 paired records directly; it did not rerun the earlier 20-case SQL36 suite. The **10 new focused cases** passed: eight valid cases for wins/ties/losses, odd/even medians, a true RMSSE win displayed as zero delta, undefined and all-zero RMSSE cohorts, and changed/absent final outcomes; two expected rejections covered a missing saved candidate and a damaged final-origin candidate. Validating final-origin forecast integrity still uses historical inputs only and does not score final actuals.

Original source files, dependent code and historical evidence remained unchanged. Seven relevant input/candidate projections were unchanged across execution, temporary files were removed, and no learner database was accessed. Detailed products and vectors remain private.

## Executed assistant preflight results

The following results were independently checked by the assistant and are **also accepted from the learner screenshot**. The screenshot confirms displayed aggregate values; detailed paired-record verification remains separate assistant evidence. Each row has 216 total and compared series, zero exclusions and PASS status.

| Origin | Metric | WEEKDAY4 wins | Ties | SNAIVE7 wins | WEEKDAY4 win % | Mean delta | Median delta |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| DEVELOPMENT_1 | MAE | 117 | 23 | 76 | 54.1667 | -0.157986 | -0.035714 |
| DEVELOPMENT_1 | RMSSE | 157 | 20 | 39 | 72.6852 | -0.130759 | -0.081459 |
| DEVELOPMENT_2 | MAE | 108 | 14 | 94 | 50.0000 | -0.086144 | -0.008929 |
| DEVELOPMENT_2 | RMSSE | 142 | 11 | 63 | 65.7407 | -0.107975 | -0.079134 |
| DEVELOPMENT_3 | MAE | 146 | 27 | 43 | 67.5926 | -0.419560 | -0.187500 |
| DEVELOPMENT_3 | RMSSE | 174 | 24 | 18 | 80.5556 | -0.264568 | -0.170819 |

Both mean and median differences favor WEEKDAY4 in each metric/window, but the coverage varies. In DEVELOPMENT_2, exactly half of the products improve on MAE: 108 wins, 14 ties and 94 losses. Do not describe that as a strict majority. RMSSE wins cover more than half in all three windows. A product can improve in one metric while worsening in another because absolute and squared errors penalize deviations differently. These descriptive counts do not justify selecting a model separately for each product using its observed future errors, and they do not establish final-holdout performance or deployment benefit.

Run the whole SQL37 file in the existing `retail_merchandising` DBeaver connection and return all six rows including `check_status`. The query can be repeated and leaves inputs and candidate tables unchanged.

## Learner acceptance — 29 October 2026

The [learner acceptance record](../data/series_forecast_improvements_learner_acceptance.json) contains all six aggregate rows in development-origin order, with MAE then RMSSE. Every displayed field matches the table and coverage controls above. Counts remain integers, win percentages are normalized to four decimals and deltas to six: `50` → `50.0000`, `-0.41956` → `-0.419560`, and `-0.1875` → `-0.187500`. This changes formatting only. Applying the SQL37 runner's canonicalization reproduces ordered report SHA-256 `94187c0f06928611b8cf15ebf50c32fc1280233d6088daf6e3585df970a1ee41`.

Each row shows 216 total/compared series, zero exclusions and PASS. The three origins contain 648 origin/series pairs; the MAE and RMSSE rows summarize those same pairs and must not be added as distinct products. Scope identifiers are inherited from the preceding accepted audit rather than extra screenshot fields. No direct learner-database read occurred. Source and candidate reconstruction, all 648 paired records across 17 fields, exact winner/eligibility checks, high-precision delta comparisons, 10 targeted cases, input/protocol immutability and cleanup remain historical assistant preflight evidence. The screenshot does not independently inspect private pair-level calculations. Individual product identifiers, paired diagnostics, vectors and screenshot are not published.

Assistant interpretation: all six average and median deltas are negative, favoring WEEKDAY4 under the defined metrics, but coverage varies. In the second development window, MAE improves for exactly half the series, with 108 wins, 14 ties and 94 losses; it is not a strict majority. This does not establish daily accuracy, statistical significance, universal superiority, final-holdout performance or a final model choice. It also does not independently test the learner's conceptual understanding. Wider-scope work remains to be specified under the existing evaluation plan; no new result is claimed here.
