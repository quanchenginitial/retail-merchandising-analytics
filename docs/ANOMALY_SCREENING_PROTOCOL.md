# Retrospective unit-change screening protocol

Fixed on 2026-11-02 before computing new rolling-baseline outcomes or screening candidates. The descriptive price-association milestone through SQL49 is learner accepted. This is a separate retrospective screening branch. SQL50 implements only the baseline scope and coverage audit below; the future SQL51 flag rules are fixed here but are not implemented or evaluated by SQL50.

## Scope and purpose

Use the accepted 30,490 item/store series and all twelve complete Saturday–Friday weeks 11601–11612, 2016-01-30–2016-04-22: 365,880 weekly positions, including zero sales and missing prices. Preserve original item/department/category/store/state mappings and all accepted input totals. The historical forecast choice and evaluation remain frozen and unchanged.

Weeks 11601–11604 form a four-week warm-up, ending 2016-02-26. Screenable target weeks are 11605–11612, 2016-02-27–2016-04-22: eight weeks × 30,490 pairs = **243,920 target positions**. This is an exploratory, label-free retrospective screen of recorded unit changes. It is not a new forecasting evaluation, a validated true-anomaly detector, or proof of stockout, lost demand, promotion or price causality.

## Fixed rolling baseline

Within each item/store pair, order the complete twelve-week sequence and use exactly its four immediately preceding **actual recorded** weekly unit values for each target. In SQL, the frame is `ROWS BETWEEN 4 PRECEDING AND 1 PRECEDING`, evaluated before filtering to target weeks. Do not include the current week or future weeks, skip zero observations, substitute a forecast, bridge missing weeks, borrow another pair, or import data outside this fixed window.

Let y be current units, S the sum of the four prior actual weeks, and μ = S / 4 their mean. Each target must have exactly four observations, with first/last history week identifiers equal to target week minus four/minus one. Retain all four actual history values even if a prior observation is later flagged by the screen. Zero history values remain valid observations. The baseline is exactly representable in quarter units and displayed with two decimals, without floating-point approximation.

Prices and their missingness remain context only. They do not filter the roster, define the rolling window or enter the baseline/flag arithmetic. Missing prices stay NULL under the accepted input contract.

## SQL50 scope-only report

Return eight rows ordered by current week, with no TOTAL row and exactly twelve columns:

`retail_week, week_start, series_count, scored_rows, history_rows, baseline_units, observed_units, zero_observed_rows, zero_baseline_rows, priced_target_rows, missing_price_target_rows, check_status`.

- retail_week identifies weeks 11605–11612; week_start is the current week's Saturday.
- series_count counts distinct item/store pairs in that week; scored_rows counts screening target positions. Both must be 30,490. The name scored_rows does not mean a score or flag has been calculated.
- history_rows sums the prior-observation count across targets: exactly 121,960 per week, or four per target. Rolling windows overlap; these repeated history observations are not new transactions.
- baseline_units sums the per-target means μ; equivalently, it is the summed S values divided by four. Display exact quarter-unit totals as fixed-two-place values. It is not a forecast accuracy measure or an additional sales total.
- observed_units sums current actual target units as an integer. zero_observed_rows counts targets with y = 0. zero_baseline_rows counts targets with S = 0, equivalently μ = 0 under nonnegative accepted units.
- priced_target_rows and missing_price_target_rows partition all target positions; neither group is excluded.
- PASS certifies accepted inputs, complete prior-only history, exact baseline arithmetic and report partitions. SQL50 returns no flags, candidate counts, anomaly scores or performance claims.

The private validation projection contains eighteen fields: the accepted SQL44 twelve fields in their original order (`item_id, store_id, dept_id, cat_id, state_id, wm_yr_wk, week_start, week_end, units, source_daily_rows, sell_price, has_price`), followed by `history_rows, history_units, positive_history_weeks, first_history_week, last_history_week, baseline_units`. Here history_units is S and positive_history_weeks counts positive actual units among the four prior observations. These features are verified at every target, but no row-level detail is published.

## Frozen future SQL51 rules — not evaluated by SQL50

For each supported target, apply these mutually exclusive labels in the stated priority order, with inclusive boundaries and exact integer arithmetic:

1. **SUDDEN_ZERO:** y = 0, all four prior actual weekly unit values are positive, and S ≥ 28.
2. Otherwise **LARGE_INCREASE:** 4y ≥ 2S and 4y − S ≥ 28.
3. Otherwise **LARGE_DECREASE:** 8y ≤ S and S − 4y ≥ 28.
4. Otherwise **NONE**.

The increase rule means current units are at least twice the prior-four mean and at least seven units above it. The decrease rule means current units are at most half the prior-four mean and at least seven units below it. The seven-unit weekly absolute floor corresponds to one unit per day. It is an explicit investigation heuristic, not an industry standard, an optimised threshold or a validated materiality level across products. No outcome-dependent threshold tuning is permitted under this frozen protocol; any later alternatives must be labelled exploratory and separately recorded.

When S = 0, the increase rule can qualify only if y ≥ 7. Describe this as activity after four zero weeks, not percentage growth from zero. If y = 0 but one or more prior weeks are zero, the first rule cannot apply; the separate decrease condition may still qualify. Priority prevents a SUDDEN_ZERO observation also being counted as LARGE_DECREASE. No candidate count for these rules is calculated in SQL50.

## Interpretation and follow-up

Any later flag is a request for review of recorded units, not a verified event. Baseline sales, product units, seasonality, promotions, availability and reporting can differ across products and stores. Repeated targets and histories are dependent. Without external labels and operational records, neither detection accuracy nor precision/recall, true anomaly frequency, stockout incidence, causal mechanisms or financial benefit can be established. Future review would require exposure/promotion, inventory/stockout, replenishment and transaction context.

## Independent preflight and preservation

SQL50 is self-contained and read-only, with the accepted SQL48 input-integrity prefix through input_health preserved. Check all schemas, pair/week coverage, calendar boundaries, integer nonnegative units, source metadata, exact scoped staging prices, pooled SQL23 agreement and established totals. Add prior-history and target-grid checks, anchored independently of output rows so empty inputs cannot silently suppress errors.

Use original read-only CSVs and unchanged SQL44 csv/Decimal helpers. Build only the 84-day sales projection and twelve-week prices through unchanged SQL09/23/44 in one containment-checked ignored repository tmp database, with two DuckDB threads and a configured 2GB limit. This limit is not a total-process memory guarantee. Never open the learner's persistent database or reconstruct the full historical daily fact; do not rerun forecasting or historical guard suites.

Independently compare all 365,880 accepted weekly rows across twelve fields and their frozen fingerprint. Derive each target's history from direct original-source four-week slices; compare all 243,920 target features across eighteen fields and every eight-row/twelve-field report value. Verify exact quarter-unit formatting, zero histories/current units, inclusion of actual zeros/missing prices, and exclusion of current/future units using focused fixtures, plus an intended empty-calendar rejection. Do not execute future flag rules during scope validation.

Preserve all accepted SQL45–49 SQL/protocol/evidence fingerprints and the historical preflight files. The accepted weekly-input fingerprint and exact original-source comparison establish this branch's input; price-description queries need not be rerun. Verify seven scoped input snapshots and original-source/dependency hashes before/after SQL50, then remove private exports, spills and databases. Public evidence contains aggregate controls and fingerprints only, without real item/store identifiers, row-level features, raw files, screenshots or databases. Assistant preflight and learner SQL50 execution remain separate states; the anomaly module and overall project remain incomplete.
