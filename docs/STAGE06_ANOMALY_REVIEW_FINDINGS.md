# Stage 6: candidate screening and investigation findings

The implemented descriptive price-association, fixed-rule candidate screening and illustrative history-review milestone, together with its investigation framework, is complete. SQL50–53 have learner acceptance. SQL53's complete 36-row report matches its independently verified reference. The interpretation below is supplied by the assistant, not an independent test of learner understanding. Operational causes and detection performance remain **unassessed**. This milestone does not complete the overall portfolio.

The accepted [price-association findings](STAGE06_PRICE_ASSOCIATION_FINDINGS.md) remain unchanged. The anomaly work provides a reproducible way to identify recorded sales changes for investigation, with no claim that the rules identify true anomalies, stockouts or unconstrained demand.

## Accepted aggregate findings

[SQL50](ANOMALY_BASELINE_SCOPE_VALIDATION.md) retains **243,920 item/store/week target positions**: eight target weeks for each of 30,490 series. Every target uses its own four preceding actual weekly observations; zeros and previously flagged observations remain in the baseline. The first four input weeks supply warm-up history. See the [scope acceptance](../data/anomaly_baseline_scope_learner_acceptance.json).

The frozen [SQL51 rules](ANOMALY_SCREENING_PROTOCOL.md) assign exactly one class to each target, in priority order:

| Class | Target positions | Interpretation |
| --- | ---: | --- |
| SUDDEN_ZERO | 902 | Zero current units after four positive history weeks, meeting the baseline floor |
| LARGE_INCREASE | 6,118 | Increase meeting both the relative and absolute thresholds |
| LARGE_DECREASE | 5,327 | Decrease meeting both thresholds after the priority rule |
| NONE | 231,573 | None of the fixed rules triggered |
| TOTAL | 243,920 | Complete target population |

The three candidate classes contain **12,347 positions, approximately 5.0619% of all targets**. This is a screening workload, not an estimated prevalence of genuine anomalies. Target counts are additive across these exclusive classes; distinct item/store counts are not additive across classes or weeks because a series can recur. See the [classification method](ANOMALY_CANDIDATES_VALIDATION.md) and [acceptance](../data/anomaly_candidates_learner_acceptance.json).

[SQL52](WEEKLY_ANOMALY_TRIAGE_VALIDATION.md) reports **1,393–1,691 candidate positions per week**, or **4.5687%–5.5461%** of each week's 30,490 targets. This describes review workload within the observed window. The weekly report preserves the same rules and reconciles to the accepted class totals; it does not supply a cause for variation. See the [weekly acceptance](../data/weekly_anomaly_triage_learner_acceptance.json).

## What the history review establishes

The frozen [SQL53 protocol](ANOMALY_CASE_HISTORIES_PROTOCOL.md) selects one illustrative lower-median absolute-gap target from each complete candidate pool, using deterministic tie-breaks. It keeps all twelve input weeks for each selected pair: **three cases × twelve weeks = 36 rows, with twelve fields**. Each case has four BASELINE-role rows, one TARGET, four warm-up rows and eight eligible rows. The [independent method](ANOMALY_CASE_HISTORIES_VALIDATION.md) verifies selection, coverage and every displayed value against source-derived references. The [learner acceptance](../data/anomaly_case_histories_learner_acceptance.json) confirms all **432 displayed fields and 36 complete PASS statuses**, with zero mismatches and no visibility caveat; visual agreement does not independently re-audit the full source or candidate pools.

These are illustrative cases, not a representative sample. Public findings contain aggregate coverage and interpretation principles only; selected keys, detailed histories and screenshots are excluded. Aliases are reading labels, not anonymization guarantees.

The following lessons apply to the method without making a case-specific operational diagnosis:

- **NONE is not verified normality.** A four-week reference adapts during sustained low or zero sales, so a continuing condition can cease to trigger even without recovery.
- **A rise from a depressed reference needs context.** An increase flag can follow a low baseline without showing a return to a previous level or normal demand.
- **Class priority matters.** SUDDEN_ZERO requires four positive prior weeks. A zero following an earlier zero can instead qualify as LARGE_DECREASE or NONE.
- **Window boundaries limit interpretation.** A target at the end of the observed window has no subsequent observations. This right censoring prevents conclusions about persistence or reversal.
- **Recorded price is not inventory evidence.** A weekly price, even if unchanged, establishes neither availability nor the absence of promotions. Zero recorded sales establish neither zero demand nor a stockout.

## Investigation framework

| Hypothesis to investigate | Evidence needed | Next action |
| --- | --- | --- |
| Availability or assortment changed | Inventory movements, ranging status, replenishment and availability records | Check whether the product was offered and available before assigning a stockout or delisting explanation |
| Demand or exposure changed | Promotion exposure, merchandising changes, relevant calendar context and comparable observations | Align timing and scope; investigate alternative explanations before attributing an effect |
| Records are missing, delayed or duplicated | Transaction records, ingestion logs, reconciliation totals and correction history | Trace the recording path and reconcile discrepancies before changing data |

These are investigation routes, not confirmed explanations or recommended commercial interventions. Inventory, exposure and transaction evidence are absent from the accepted sales/price analysis. Detection performance would additionally require independently reviewed labels, including non-candidates, and a defined evaluation population; three selected histories cannot estimate precision or recall.

## Completion boundary and next module

The delivered analysis now connects price descriptions, candidate rules, weekly review workload, reproducible history inspection and an actionable evidence checklist. No further default department/store split or diagnostic SQL is required to close this implemented milestone. Operational verification, prospective usefulness and detection performance remain separate work; no causal effect, lost-sales estimate or financial benefit has been established.

The next project module is independent Retailrocket onboarding: audit its sources, observation coverage and event/user/transaction grains before defining behavioral metrics. Keep its records separate from M5. A learner explanation of why a rule triggers, why NONE does not prove normality and what external evidence would distinguish causes can check understanding without another data query.
