# Within-week and department price-group contrasts

## Purpose and evidence boundary

SQL48 was learner-accepted on **2 November 2026**: all seven rows, twelve field values per row and seven complete PASS values match its frozen report. The cropped final header is documented separately from the visible status values in the [84-field acceptance record](../data/department_price_sales_association_learner_acceptance.json). Both price-direction means were negative in FOODS_1 and positive in FOODS_3. SQL47 had already shown variation across weeks.

This [SQL49](../sql/49_week_department_price_contrasts.sql) follow-up was chosen after those results. Its [protocol](WEEK_DEPARTMENT_PRICE_CONTRASTS_PROTOCOL.md) was fixed before computing the new contrasts. It adds descriptive joint week/department context and is not a prespecified causal test. **Assistant preflight passed; the learner screenshot was accepted on 2 November 2026 with all 168 displayed values and fourteen complete PASS statuses matching the frozen report.**

## Population and eligibility

Retain the same 365,880 item/store/week inputs, 30,490 pairs, twelve complete weeks **30 January–22 April 2016** and all **335,390 adjacent transitions**. Each unit change is current units minus previous units for the same item/store pair. Price direction uses exact cents, with MISSING_ENDPOINT separate and no imputation. Compute previous endpoints over the full sequence before removing its initial week. All zero-sales observations remain.

The complete internal grid has **7 departments × 11 current weeks × 4 directions = 308 cells**, including empty cells and missing-price groups. In a given department and current week, a target direction (UP or DOWN) is eligible for a contrast only when both its transition count and the UNCHANGED count are positive. There is no outcome-based or minimum-volume filter. All target observations remain visible in direction_transitions; comparable_transitions counts eligible target observations, and unsupported_transitions records the rest. This use of comparable is distinct from SQL45's endpoint-price availability definition.

## Estimand and arithmetic

For an eligible department/week, let n_g and S_g be the target-direction count and sum of signed unit changes; n_u and S_u are the corresponding UNCHANGED quantities. The within-week contrast is S_g/n_g − S_u/n_u. For one department/direction, sum over its eligible weeks:

- Weighted target mean = Σ S_g / Σ n_g.
- Weighted unchanged reference = Σ (n_g × S_u/n_u) / Σ n_g.
- Mean change gap = Σ ((S_g × n_u − S_u × n_g)/n_u) / Σ n_g.

This uses target-transition weights for both sides. It is not an equal-weight average of weekly means or subtraction from SQL48's all-week unchanged mean. The gap is computed from unrounded inputs, not rounded displayed means. Each displayed mean and gap is independently rounded to six decimal places, half away from zero. Exact integer cross-products S_g × n_u − S_u × n_g determine weekly signs. Tied weeks equal comparable_weeks minus positive_gap_weeks minus negative_gap_weeks. If no eligible observations exist, all three displayed means/gap are NULL and comparable counts/weeks are zero.

The fixed report has **14 rows × 12 fields**, ordered by department and then UP/DOWN, without a TOTAL row. UP and DOWN can reuse unchanged observations, but have different target weights. Their reference groups must not be treated as disjoint samples; gaps are not additive or a direct treatment comparison. Missing-price observations remain in the complete input/cell reconciliation, although they cannot be assigned a known price direction for a contrast.

## Interpretation

A positive gap means the target group's average change exceeds its same-week/department reference under the stated weights. It does not necessarily mean the target group's sales increased. Likewise, a negative gap can occur when both groups grow but the reference grows more. Units are sold-unit counts, not growth percentages, margins or causal lift.

Week-sign counts treat each eligible week as one count; the aggregate contrast also depends on magnitudes and target-transition weights. A majority of positive-gap weeks therefore does not guarantee a positive weighted gap.

Stratifying by department and week does not balance item/store mix, baseline demand, availability or other conditions. The unchanged group is not a matched-SKU counterfactual. Repeated adjacent transitions overlap, and positive/negative week counts are descriptive rather than independent significance trials. No elasticity, causal effect, net promotion benefit, p-value, inventory improvement or business savings is estimated.

## Independent verification

The [validator](../validation/preflight_week_department_price_contrasts.py) reconstructs only the original 84-day sales projection and twelve price weeks in a private temporary database. It never opens the learner's persistent database or reruns historical forecasting/test suites. Original-source metadata, integer units and exact-cent prices independently reconstruct all transitions and group cells. A rational-number reference verifies weighted calculations and exact signs before final rounding.

The completed preflight passed **3 focused cases** and matched **365,880 weekly input rows × 12 fields**, **36,588 pooled rows × 8 fields**, **365,864 prices × 4 fields**, **308 internal cells × 16 fields**, and every field in the **14×12 report**. Accepted SQL45–48 reports and week/department margins reconcile. Seven scoped input snapshots, source/dependency hashes and **47 historical preflights** remained unchanged; private files were removed. See the [machine evidence](../data/week_department_price_contrasts_preflight.json) for executed cases, reference details and timings.

Displayed-report SHA256: `b85f3e28dc964a5261e843a3bc36da590b8fd1498fdc22c9ce91f65a0837f43e`. The canonical report uses ordered compact JSON arrays plus LF, integer counts and fixed-six-place strings for means/gaps, with NULL for empty eligibility. Public evidence contains aggregates and fingerprints, without real SKU identifiers, individual transitions, screenshots, raw files or databases.

## Measured assistant report

| Department | Direction | All direction transitions | Comparable transitions | Unsupported transitions | Comparable weeks | Weighted direction mean | Weighted unchanged mean | Mean change gap | Positive-gap weeks | Negative-gap weeks | Status |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| FOODS_1 | UP | 48 | 48 | 0 | 10 | -0.229167 | 0.302203 | -0.531370 | 8 | 2 | PASS |
| FOODS_1 | DOWN | 85 | 85 | 0 | 10 | -0.800000 | 0.576188 | -1.376188 | 9 | 1 | PASS |
| FOODS_2 | UP | 287 | 287 | 0 | 11 | 3.128920 | -0.025770 | 3.154690 | 8 | 3 | PASS |
| FOODS_2 | DOWN | 281 | 281 | 0 | 11 | -0.405694 | -0.297401 | -0.108293 | 5 | 6 | PASS |
| FOODS_3 | UP | 1309 | 1309 | 0 | 11 | 3.663102 | 0.256367 | 3.406734 | 11 | 0 | PASS |
| FOODS_3 | DOWN | 545 | 545 | 0 | 11 | 3.790826 | 0.472571 | 3.318254 | 10 | 1 | PASS |
| HOBBIES_1 | UP | 140 | 140 | 0 | 11 | 1.085714 | -0.020742 | 1.106456 | 7 | 4 | PASS |
| HOBBIES_1 | DOWN | 91 | 91 | 0 | 11 | 1.857143 | -0.017146 | 1.874288 | 9 | 2 | PASS |
| HOBBIES_2 | UP | 12 | 12 | 0 | 6 | 1.750000 | -0.202318 | 1.952318 | 6 | 0 | PASS |
| HOBBIES_2 | DOWN | 4 | 4 | 0 | 4 | 0.750000 | 0.013739 | 0.736261 | 2 | 2 | PASS |
| HOUSEHOLD_1 | UP | 200 | 200 | 0 | 11 | 3.320000 | -0.365139 | 3.685139 | 10 | 1 | PASS |
| HOUSEHOLD_1 | DOWN | 321 | 321 | 0 | 11 | 0.214953 | -0.196590 | 0.411543 | 9 | 2 | PASS |
| HOUSEHOLD_2 | UP | 64 | 64 | 0 | 11 | 0.968750 | -0.011996 | 0.980746 | 10 | 1 | PASS |
| HOUSEHOLD_2 | DOWN | 409 | 409 | 0 | 11 | 1.880196 | -0.020259 | 1.900455 | 11 | 0 | PASS |

All displayed fields matched the independent reference during preflight. The learner screenshot subsequently matched every field on **2 November 2026**. Read support counts and week coverage alongside each gap; the fourteen rows include all seven departments and both directions, without choosing groups by their outcomes.

## Learner screenshot acceptance — 2 November 2026

The learner's DBeaver screenshot shows all **14 rows × 12 fields = 168 values**, including fourteen complete PASS statuses. Independent visual transcription matches the frozen report in all 168 positions: 84 integer counts, 42 mean/gap values, 28 department/direction labels and fourteen statuses. Only displayed thousands separators and omitted trailing zeros were normalized; the two means and gap retain six decimal places. No gap was recalculated by subtracting printed means. The resulting ordered row-array/LF hash is the same `b85f3e28dc964a5261e843a3bc36da590b8fd1498fdc22c9ce91f65a0837f43e`. See the [aggregate learner acceptance](../data/week_department_price_contrasts_learner_acceptance.json).

The visible rows contain **3,796 target transitions: 2,060 UP and 1,736 DOWN**. All 3,796 are comparable and unsupported counts are zero in every row. Positive- and negative-gap week counts sum to comparable weeks in each row, so no tied weeks are displayed. FOODS_1's weighted gaps are **−0.531370 for UP** and **−1.376188 for DOWN**, despite positive gaps in **8/10** and **9/10** eligible weeks respectively. A count of weekly signs does not incorporate contrast magnitudes or target-transition weights. This remains descriptive evidence, without a causal interpretation.

This acceptance is a visual aggregate-report comparison, not a direct audit of the learner database or a new verification of all 308 internal cells, unrounded contrasts or exact weekly signs. No learner database was opened and no SQL, preflight, fixture or historical analysis was rerun for acceptance. The full-source comparisons and preservation checks above remain separate historical assistant evidence. The original preflight JSON retains its historical pending status; the new acceptance record establishes the subsequent learner result. SQL49, its validator, protocol and preflight are unchanged, and no screenshot or individual records are published.

The planned next task is to summarize the price-association findings and limitations, then begin the anomaly-candidate protocol. Those tasks, the full Stage 6 module and the overall portfolio remain incomplete; see the [current Chinese guide](FIRST_STEP_ZH.md).
