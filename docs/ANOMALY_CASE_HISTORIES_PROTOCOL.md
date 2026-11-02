# Illustrative anomaly-candidate history review protocol

Fixed on 2026-11-02 before selecting cases or computing their displayed histories. SQL52's eight-row weekly triage report is learner accepted. This step reviews three individual historical examples, without further aggregate slicing or threshold tuning. Preserve the accepted SQL51 classifications and the complete SQL52 prefix through classified.

## Fixed selection from the full candidate pools

Choose one target position independently from each of SUDDEN_ZERO, LARGE_INCREASE and LARGE_DECREASE, using every target in that class across all eight target weeks. The accepted pools contain 902, 6,118 and 5,327 positions respectively. A position is an item/store/current-week observation, not a distinct series.

Within each class, sort by **absolute unit_difference_x4 ascending, item_id ascending, store_id ascending, wm_yr_wk ascending**. Select rank `(pool_rows + 1) // 2`, using one-based ranks: the lower middle position for even pools and the middle position for odd pools. The established pool counts imply ranks 451, 3,059 and 2,664. Use exact integer differences and the full tie-break tuple; do not select by a rounded mean, peak week, largest gap, price availability or subjective appearance.

Assign CASE_1 to SUDDEN_ZERO, CASE_2 to LARGE_INCREASE and CASE_3 to LARGE_DECREASE. The same item/store pair can be selected in different classes and receives a separate case alias each time. Do not deduplicate or reweight pairs. These are **three illustrative median-gap cases**, not a representative sample, estimated typical event, validated anomaly or causal explanation. If any class is absent, fail the fixed three-case contract explicitly; never omit a case or manufacture a NULL selection.

## Full twelve-week context and frozen output

For each selected pair, retain all twelve accepted weekly observations in 11601–11612, 2016-01-30–2016-04-22. Return exactly 36 rows ordered CASE_1, CASE_2, CASE_3 and then chronologically, with exactly twelve columns:

`case_id, selected_class, retail_week, week_start, relative_week, units, rolling_baseline_units, screen_class, context_role, sell_price, has_price, check_status`.

- case_id is the fixed alias; selected_class describes the selected TARGET position and remains constant throughout that case's twelve rows.
- retail_week and week_start describe the context row's own current week. relative_week equals context week identifier minus selected target week identifier.
- units is that context row's actual integer weekly sales.
- rolling_baseline_units is that context row's own accepted prior-four-actual-week mean, displayed to two decimal places. It is NULL in the first four input weeks 11601–11604, with screen_class = WARMUP. All eight eligible weeks use their own unchanged SQL51 baseline and classification, including NONE and other candidate classes.
- context_role is EARLIER when relative_week < −4, BASELINE at −4 through −1, TARGET at 0, and LATER above 0. Every case has exactly four BASELINE rows and one TARGET row. Its other seven rows can be split differently between EARLIER and LATER; a last-week target has no LATER rows. Do not fill context from outside the accepted window.
- The TARGET row's baseline equals the arithmetic mean of actual **units** in its four BASELINE-role rows. Do not average those rows' rolling_baseline_units: they describe different, earlier windows and can be NULL during warm-up.
- The TARGET screen_class must equal selected_class. A context row's class can differ, and actual observations remain in later baselines even when previously flagged.
- sell_price is the unchanged nullable recorded exact-cent price, displayed to two decimals when present; has_price is Boolean. Prices provide context only and do not influence case selection, baseline or class.
- PASS certifies accepted inputs, deterministic selection, full history coverage and exact field reconciliation. It does not establish a cause or verify an operational event.

LATER rows are explicitly retrospective context. They are not used in the selected target's ranking feature, baseline or classification and do not establish a prospective prediction. The complete class pools and their median-based selection are retrospective. All zero sales and missing-price positions remain included.

## Read-only integrity and independent validation

SQL53 is self-contained and read-only, with no learner-table mutation. Mechanically preserve the SQL52 input/history/classification prefix, including the frozen rules. Validate three nonempty pools and three unique case aliases, exact lower-median rank and selected target class, twelve unique weeks per case, four prior BASELINE-role rows, one TARGET, four warm-up rows and eight eligible rows. Keep guard-anchored output so invalid or missing input/selection cannot silently return an incomplete report.

Use original read-only CSVs and unchanged source/feature/classification helpers. Reconstruct only the fixed 84-day projection and twelve-week prices through unchanged SQL09/23/44 in one containment-checked ignored tmp database, with two DuckDB threads and a configured 2GB limit. The limit is not a total-process cap. Never open the learner's persistent database, rebuild the full historical daily fact, rerun historical forecasting/boundary suites, or select cases from SQL output.

Compare every one of the 365,880 accepted weekly rows across twelve fields; independently reproduce all 243,920 twenty-field classifications and accepted fingerprint `901d908b825f192b0dd1a7baabfe9ad38cdf96add65f7fa891b7aa15dea85e31`, including the accepted eighteen-field baseline fingerprint `556c07cf090b18fc6d60c00770b524d2d71464d3aece8968c438fea0c558c38f`. Independently sort original-source candidate tuples in Python, compare the three selected private keys/ranks exactly, and derive every 36-row/twelve-field context value directly from original weekly observations and accepted own-week features. Verify the selected TARGET baseline against its four displayed BASELINE-role unit values.

Focused synthetic cases cover odd/even lower-median selection, exact-gap tie-breaking, the same pair selected for different cases, early/late boundary targets with complete in-window context, warm-up NULL/WARMUP behavior, nullable prices, and explicit rejection when a candidate class or calendar is absent. Reuse accepted helper behavior without rerunning old rule suites.

## Privacy, retained reference and cleanup exception

Aliases are presentation labels, **not anonymisation**. Real selected item/store keys, gap features and all 36 context values stay private. Public evidence contains only fingerprints, exact comparison counts, report shape and three case summaries with case/class, candidate pool/rank, one selected case, twelve context rows, four BASELINE rows, one TARGET, four warm-up/eight eligible rows and PASS. Do not publish selected dates, units, prices, full result dictionaries, screenshots, candidate IDs or row-level features. Public SQL/code/protocol files remain reproducible without embedding selected outcomes.

After successful validation, intentionally retain exactly one private expected-report artifact at ignored `exports/private/sql53_case_history_reference.json`. Its JSON schema is `{ "output_columns": [...], "results": [36 ordered dictionaries] }`, using only the twelve displayed fields: integer units/relative week, two-decimal baseline/price strings or NULL, ISO dates, text labels and Boolean has_price. It contains no real item/store identifier fields but remains private because aliases do not remove the sensitivity of the histories. Record the private file's relative path and SHA-256 in public evidence for later screenshot acceptance.

This retained expected report is an explicit exception to deleting all private row-level artifacts. Verify containment, the repository's `exports/**` ignore rule and exclusion from the public artifact/release allowlist. Delete the disposable database, spills, actual-key selection exports, classified/input exports and temporary report files. State retained-reference and temporary-cleanup status separately; do not claim every private row-level file was deleted.

Preserve original-source hashes, all frozen code/protocol/evidence and historical preflights, and all seven scoped input snapshots. Assistant preflight and learner SQL53 execution/interpretation remain separate states. Subsequent discussion should inspect what the actual histories show, with promotion, availability, exposure and recording explanations remaining unverified; no stockout, lost-sales, pricing-causality or anomaly-accuracy claim follows from these examples.
