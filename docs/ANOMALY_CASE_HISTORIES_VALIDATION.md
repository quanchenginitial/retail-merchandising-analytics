# Deterministic illustrative candidate histories

## Purpose and state

The learner accepted [SQL52](WEEKLY_ANOMALY_TRIAGE_VALIDATION.md) on **2 November 2026**: all 96 visible values and eight PASS statuses match its frozen report. [SQL53](../sql/53_review_anomaly_case_histories.sql) moves directly from that overview to three concrete twelve-week histories. **Assistant preflight passed; learner screenshot reproduction was accepted on 2 November 2026 after all 432 visible fields and thirty-six complete PASS statuses matched the frozen private reference.** Operational cause verification and detection-performance evaluation remain incomplete.

The [case protocol](ANOMALY_CASE_HISTORIES_PROTOCOL.md) fixes selection, context and publication before examining new selected-case outcomes. This choice follows previously observed aggregate results; it is not a preregistered population hypothesis test, random sample or new prospective forecast evaluation. Original classification thresholds and all accepted source observations remain unchanged.

## Selection contract

Use all 243,920 target positions from the frozen eight-week classification. In each of the three candidate classes, order by **ABS(unit_difference_x4) ascending, item_id ascending, store_id ascending, wm_yr_wk ascending**. Select rank `(class_count + 1) // 2`, the lower middle observation for an even count. SUDDEN_ZERO, LARGE_INCREASE and LARGE_DECREASE have 902 / 6,118 / 5,327 positions, so ranks are 451 / 3,059 / 2,664.

The unit of selection is an item/store/week target. Repeated pairs across weeks remain in the pool; a pair selected for two classes stays as two distinct case roles. No peak-week, department, store, price-availability or follow-up-outcome filter is applied. Empty classes fail the fixed three-case contract instead of silently omitting or inventing a case. CASE_1 / CASE_2 / CASE_3 map to the three classes in that order. They are reading labels, not anonymization guarantees.

These are illustrative cases near the middle of each class's **absolute unit-gap** ordering. They are not median relative changes, typical products or a representative population sample. Tie-breaks make selection reproducible; they do not remove selection bias. The class-pool ordering is retrospective over all eight weeks; each target's own baseline and gap use only its current/prior observations, but selection from the full pool is not an online decision at that target date.

## Thirty-six-row local report

For each selected pair, show all twelve accepted weeks, 30 January–22 April 2016, in chronological order: **3 cases × 12 weeks = 36 rows, 12 columns, no TOTAL**. Selected class is constant within the case, but screen_class belongs to each displayed row's own week. In weeks 11601–11604, rolling_baseline_units is NULL and screen_class is WARMUP; in weeks 11605–11612, use the same four-prior-actual-week baseline and class already accepted in SQL51.

relative_week is displayed week minus the selected target week. context_role is EARLIER below −4, BASELINE from −4 through −1, TARGET at zero, and LATER above zero. Every case has exactly four BASELINE rows and one TARGET row. The TARGET's baseline equals the average units over its four BASELINE rows. Baselines on other eligible rows use their own preceding windows, not the selected target's window.

The original zero values and missing-price context are retained. sell_price remains an exact two-place amount or NULL; has_price preserves its original boolean. Prices do not determine case membership. Later observations are explicitly retrospective context and never enter the selected target's baseline or classification. A last-week target has no later rows; no extra window, artificial padding or source borrowing is introduced. PASS checks the computational contract, not an operational explanation.

## Independent preflight actually executed

The [validator](../validation/preflight_anomaly_case_histories.py) reconstructs only the fixed 84-day window from original read-only CSVs in a private temporary database. It does not open the learner's persistent database, rebuild the entire daily fact, rerun forecast comparisons or repeat historical classification-boundary suites.

All **365,880 weekly input rows × 12 fields**, **36,588 pooled rows × 8 fields**, and **365,864 scoped prices × 4 fields** match original-source references. All **243,920 classified targets × 20 fields** match and reproduce SQL51's accepted classification fingerprint; the embedded eighteen baseline fields also reproduce SQL50's fingerprint. Independent sorting of original-source classified targets establishes the selected keys and ranks. All **36 context rows × 12 fields** then match their source-derived reference, including dates, role boundaries, own-row baseline eligibility, labels, prices and booleans.

The run passed **4 focused cases**, listed precisely in [machine evidence](../data/anomaly_case_histories_preflight.json), and preserved all frozen source/dependency fingerprints, seven scoped input snapshots and **51 historical preflights**. Temporary databases, spills and intermediate row/key exports were removed. A deliberately retained local report reference is described separately below; it is not claimed to have been deleted.

## Publication and retained local reference

The public evidence contains only selection/coverage aggregates, validation status and fingerprints. It does **not** publish the 36 actual history rows, selected source keys, case-level sales or prices. The expected displayed report is retained only at the ignored local path `exports/private/sql53_case_history_reference.json` for subsequent learner screenshot comparison. It is excluded from the public release allowlist. Its file fingerprint is recorded in machine evidence; temporary working files remain separate.

Canonical report SHA256: `ab5ee45befcb93eb0b260b3f3881829bd71568975ac20a9d4f3af871a42241b0`. Canonical rows are ordered compact JSON arrays with LF: string case/class/week/date/role/status values, integer relative weeks and units, fixed-two-place baseline and price strings or null, and boolean has_price. This fingerprint validates agreement; it does not itself publish the detailed reference or establish an underlying business cause.

## Public coverage summary — learner reproduction accepted

| Case | Selected class | Pool positions | Selected rank | Cases | Context rows | Baseline rows | Target rows | Warm-up rows | Eligible rows | Status |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| CASE_1 | SUDDEN_ZERO | 902 | 451 | 1 | 12 | 4 | 1 | 4 | 8 | PASS |
| CASE_2 | LARGE_INCREASE | 6118 | 3059 | 1 | 12 | 4 | 1 | 4 | 8 | PASS |
| CASE_3 | LARGE_DECREASE | 5327 | 2664 | 1 | 12 | 4 | 1 | 4 | 8 | PASS |

The table above remains aggregate coverage evidence; the learner's detailed 36-row output is not published. The screenshot now matches the private reference in every field. See the [aggregate acceptance record](../data/anomaly_case_histories_learner_acceptance.json) and the [current Chinese guide](FIRST_STEP_ZH.md).

## Learner screenshot acceptance — 2 November 2026

The screenshot shows **36 rows × 12 columns = 432 visible fields**, all twelve headers and thirty-six complete PASS statuses, with no visibility caveat. Each case contributes twelve rows and 144 verified fields, including four BASELINE rows, one TARGET row, four WARMUP rows and eight eligible rows. Checked price boxes were transcribed as true, displayed NULLs as null, and omitted decimal trailing zeros restored to two places.

The complete screenshot was independently transcribed before comparison with the private expected report. All 432 fields match, with zero mismatches and the same canonical report fingerprint shown above. The separate normalized transcription is retained only at the ignored local path exports/private/sql53_case_histories_learner_transcription.json. Its fingerprint and the unchanged original-reference fingerprint appear in the public acceptance record; neither file belongs to the public release. Actual case values, selected weeks, source keys and screenshots remain excluded from public documentation.

This is visual reproduction acceptance, not a new source-data or learner-database audit, a new full-pool selection check, or an independent assessment of conceptual understanding. No learner database was opened and no SQL, source preflight, fixture or historical analysis was rerun. The earlier source checks and temporary-file cleanup remain separate historical evidence; retaining the expected report and learner transcription is deliberate. SQL53, its validator, both frozen protocols, preflight and prior acceptance evidence remain unchanged. The original preflight retains its historical learner-pending state; this later record establishes learner acceptance.

## Interpretation limits and next action

First reproduce the selected target's mean and rule from its four marked history weeks, then describe the surrounding actual pattern without assuming its cause. A temporary zero, sustained rise or later recovery can suggest questions, but none confirms inventory availability, stockouts, a promotion effect, latent demand or a data-entry error. Independent inventory, assortment, promotion, replenishment or transaction records are needed to distinguish explanations.

Selection on observed gap size and overlapping histories preclude population-level performance claims from three cases. No precision/recall, true-anomaly rate, causal effect, lost-sales estimate or financial benefit follows. The previously explored historical window remains retrospective. Learner case reproduction is accepted; learner conceptual understanding remains untested. The assistant interpretation and investigation framework are now documented in [Stage 6 anomaly review findings](STAGE06_ANOMALY_REVIEW_FINDINGS.md). The implemented Stage 6 descriptive, screening and illustrative review scope is complete. Operational causes and detection performance remain unassessed, and the overall portfolio remains incomplete. The next step is an independent Retailrocket intake.
