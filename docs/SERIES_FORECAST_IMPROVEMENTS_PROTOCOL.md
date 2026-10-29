# Fixed protocol: paired coverage of development forecast improvements

## Purpose and fixed contract

[SQL36](../sql/36_compare_development_forecast_errors.sql) established lower aggregate MAE and macro RMSSE for WEEKDAY4 in all three development windows. [SQL37](../sql/37_compare_series_forecast_improvements.sql) asks how widely the improvement is distributed across the same products: how many series improve, tie or worsen, and what the average and median paired differences are. This is a descriptive follow-up to observed development scores, not an independently held-out confirmatory test or a final model-selection rule.

This contract is recorded before inspecting the new paired summaries. Keep the existing [evaluation plan](EVALUATION_PLAN.md), three development windows, fixed FOODS_1 / CA_1 roster of 216 product-store series, 28-day horizons, forecast definitions and RMSSE scaling unchanged. The final holdout remains unscored. Both candidates are validated against their historical construction rules before their persisted values are evaluated.

SQL37 is read-only. It reuses SQL36's source, candidate and scoring checks and pairs the two models by origin, item and store. There must be one SNAIVE7 and one WEEKDAY4 diagnostic for each pair, with the same actual total, 28 evaluation positions and identical training-scale eligibility. All 648 origin/series pairs must be retained. Do not restrict this comparison to high-volume products, positive outcomes or a favorable subset.

## Exact win, tie and loss classification

For MAE, compare each model's sum of absolute error quarter-units. Both models have 28 positions, so their per-series MAE denominator is the same: 4 × 28 = 112. WEEKDAY4 wins when its exact integer sum is smaller, ties when equal, and loses when larger. All 216 series are compared, including zero outcomes and zero predictions.

For RMSSE, compare the exact sum of squared error quarter-units (squared-error sixteenths) only for series with a valid positive training scale. The scale and 28-day denominator are identical between the two candidates, and the square root is monotone, so comparing these integer sums gives the same ordering as comparing full-precision RMSSE. Undefined scales remain excluded from this metric and are explicitly counted. The same series still participates in MAE. Never replace undefined RMSSE with zero.

Classify exact equality as a tie. Do not classify from rounded MAE/RMSSE values, displayed differences or a floating-point tolerance. A tiny true improvement can display as a zero difference after rounding while still being a win. Comparisons measure each whole 28-day series, not daily win frequency.

## Paired differences and aggregation

Define delta = WEEKDAY4 metric minus SNAIVE7 metric for the same origin/series. Negative values favor WEEKDAY4 and positive values favor SNAIVE7. MAE differences have units of units per product-store day; RMSSE differences are dimensionless. Neither is a percentage or a relative improvement ratio.

Calculate the unweighted mean and conventional median of these paired deltas over the metric's compared cohort. For an even number of pairs, the median is the average of the two central differences after sorting; for an odd number it is the central difference. The median of paired differences is not generally the difference between the two models' separate medians. A majority of wins need not imply a better mean because the magnitudes can differ.

For MAE, retain exact integer quarter-error differences and rational denominators through final six-place rounding. For RMSSE, calculate differences from the unrounded individual roots, then take their mean and median. Independent high-precision references check the floating calculations. Win/tie/loss counts remain exact regardless of floating display precision.

Win percentage is 100 × WEEKDAY4 wins / compared series, displayed to four decimals. Ties remain in this denominator. Excluded RMSSE series do not. If no series is eligible, compared/win/tie/loss counts are zero, excluded equals 216, and win percentage, mean delta and median delta are NULL. This is a valid coverage result, not a score of zero.

## Six-row report

The 12 ordered columns are `origin`, `metric`, `total_series`, `compared_series`, `excluded_series`, `weekday4_wins`, `ties`, `snaive7_wins`, `weekday4_win_pct`, `mean_delta`, `median_delta`, and `check_status`.

Return DEVELOPMENT_1, DEVELOPMENT_2 and DEVELOPMENT_3 in that order, with MAE then RMSSE within each origin. No TOTAL row pools the repeated observations of the same products across origins. For every row:

- total_series = 216;
- compared_series + excluded_series = total_series;
- weekday4_wins + ties + snaive7_wins = compared_series;
- MAE has zero exclusions; RMSSE coverage matches SQL36's valid/undefined counts.

PASS confirms source, saved forecast, pairing, eligibility and aggregation checks. It does not establish a universally superior model, significance, forecast improvement on the final holdout, inventory savings or deployment benefit. Series share a store and dates, and products reappear across origins; these counts are not independent experimental trials. No p-value or confidence claim is attached to win percentages.

