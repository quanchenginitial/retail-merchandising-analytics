# Retailrocket seven-day visitor-item pair funnel

This SQL72 contract was frozen on 9 November 2026 before fixtures or source execution. It asks how many observed visitor-item pairs progress from view to cart to transaction within a uniform **seven elapsed days after their first observed view**, while explicitly excluding pairs lacking that potential follow-up before the log ends. Seven days is a chosen analysis definition, not an optimized or validated optimal horizon.

## Anchored window and cohort

[SQL72](../sql/72_analyze_retailrocket_7day_visitor_item_funnel.sql) reads only timestamp BIGINT, visitorid BIGINT, event VARCHAR, itemid BIGINT and transactionid BIGINT from accepted rr_mart.events_enriched. The required five names/types are checked; column positions and the full seventeen-column schema are not asserted. Neither stored UTC fields nor category/availability fields are read.

For every distinct (visitorid,itemid) pair with at least one observed view, first_view_ms is its earliest view timestamp in the supplied log. This is **first observed**, not necessarily first-ever: history before the log's left edge is unknown. The fixed deadline is first_view_ms + **604800000 integer milliseconds**, exactly 7×24 hours. It is not seven local calendar dates and is never restarted at the cart stage.

The actual observation end is MAX(timestamp) across **all event types**, independently of viewed-pair membership. Admission requires that value to match the accepted **1442545187788 ms = 2015-09-18T02:59:47.788000Z**. The eligibility cutoff is therefore **1441940387788 ms = 2015-09-11T02:59:47.788000Z**. A viewed pair is eligible precisely when its deadline is <= the actual observation end, equivalently first_view_ms <= cutoff. Equality is included. The global log boundary allows a potential seven-day follow-up interval; it does not prove continuous event capture, visitor presence, product exposure or complete observation for that individual pair.

Eligibility is determined before outcomes. A recent pair with a visible cart and transaction is still excluded if its deadline lies beyond the log end. This prevents retaining only early successes from incompletely followed pairs. The excluded cohort is visible in the output. No-view paths are outside the viewed-pair population.

For eligible pairs only:

1. The qualifying cart is the earliest addtocart strictly after first_view_ms and <= deadline_ms.
2. The qualifying transaction is the earliest transaction strictly after the qualifying cart and <= the **same first-view-anchored deadline_ms**.

An event at the exact deadline may qualify; one millisecond later cannot. A transaction tied with its qualifying cart cannot establish order. A cart tied with first view cannot advance the chain. Earlier out-of-order activity does not prevent a later valid chain within the window. A transaction without an earlier qualifying cart remains outside the third stage. Each pair enters each nested stage at most once, while all original event occurrences and accepted duplicate surplus 460 remain preserved. Distinct-pair counting is a cohort definition, not source deduplication.

## Five-row report and admission

The output is exactly **five rows × five columns**:

| Stage | Pair population | Share/rate denominator |
|---|---|---|
| VIEWED_ALL | All pairs with an observed view. | Both rate columns NULL; cohort diagnostic. |
| EXCLUDED_INCOMPLETE_7D | Viewed pairs whose deadline is after log end. | Both rate columns NULL; cohort diagnostic. |
| ELIGIBLE_VIEW_7D | Viewed pairs with complete potential seven-day follow-up. | Eligible share 100.0000 when positive; base step rate NULL. |
| VIEW_THEN_CART_7D | Eligible pairs with a qualifying cart. | Share and step rate use eligible viewed pairs. |
| VIEW_CART_TRANSACTION_7D | Eligible pairs with a qualifying cart then qualifying transaction. | Share uses eligible viewed pairs; step rate uses qualifying cart pairs. |

The column order is **stage, visitor_item_pairs, share_of_eligible_pairs_pct, step_rate_pct, check_status**. All zero denominators yield NULL. Thus a valid source with no eligible viewed cohort has zero nested counts and NULL nested rates. VIEWED_ALL = EXCLUDED_INCOMPLETE_7D + ELIGIBLE_VIEW_7D is a disjoint partition; the latter three stage counts are nested and **not additive**. They must satisfy eligible >= cart >= transaction >= 0. Do not sum the five report rows.

Percentages are four-place DECIMAL values; DuckDB CLI JSON preserves them as four-place strings and genuine NULLs. These are seven-day observed progression shares for visitor-item identifiers, not person-level conversion, session conversion, validated-order counts or causal effects. Missing paths do not establish abandonment. Comparisons with SQL71's unrestricted observation-window results require respecting the changed cohort and window; no improvement or causal impact is inferred here.

Source admission requires 2,756,101 records (2,664,312 view, 69,332 addtocart, 22,457 transaction), nonempty input, the five required field types, exact duplicate surplus 460, nonnegative valid identifiers, valid event/transaction-nullability rules, supported integer milliseconds from 0 through 253402300799999, and the actual all-event maximum equal to the frozen accepted endpoint. Deadlines are computed as BIGINT; the supported range plus seven days remains safely below the BIGINT limit. Invalid source admission returns all five fixed labels with all three metric columns NULL and every status BLOCKED. Missing required columns/tables may fail SQL binding. The query is entirely read-only and changes no session settings.

## Independent event-only preflight

The validator reads **events.csv only**. It executes frozen SQL54/63 creation prefixes in a private database and creates a disposable original-five-field rr_mart.events_enriched projection. This stand-in verifies SQL72's readset, not the seventeen-column production fact, its UTC fields or its property associations. Accepted earlier evidence remains their basis. SQL69, SQL70, SQL71 and all earlier full audit suites are not rerun; neither property CSV nor the category CSV is read.

Python independently types and validates every source event. Its first source scan measures the maximum timestamp across every type and compares it with accepted SQL64/SQL70 endpoint evidence and the frozen expected endpoint. It sorts numeric keys (visitorid,itemid,timestamp,event,transactionid with NULL before nonnegative IDs) in chunks of at most 50,000 records. During merged streaming, only the current pair's first observed view, deadline, eligibility and qualifying cart/transaction state is retained; there is no all-pair dictionary or all-event list. The global endpoint is known before the pair fold. Each pair contributes once to the all/excluded/eligible partition and, if eligible, its nested stage flags. Strict ordering and the shared inclusive deadline are implemented independently of SQL.

A direct read-only five-field projection stream must match every source occurrence in the same numeric order, including duplicate multiplicity. Independent pair counts and Decimal half-up arithmetic reconstruct all twenty-five report cells, including diagnostic and undefined NULL rates. The endpoint and eligibility cutoff are recorded both numerically and as UTC text derived from integer epoch arithmetic for interpretation; no stored UTC field is read.

Focused synthetic fixtures cover exact eligibility/deadline equality, one-millisecond-late exclusions, recent incomplete pairs excluded despite an already visible chain, an endpoint supplied by a non-view event, same-millisecond stage ties, earlier out-of-order activity, zero eligible or zero cart populations and retained source duplicates. A transaction shortly after a late cart but after the original view deadline must fail, so a restarted cart window cannot slip in. Incorrect expected endpoint, counts/schema/keys/event/time rules must block every metric. Extra unqueried columns remain outside schema scope; a missing required field may bind-fail.

The real preflight has three CLI phases: frozen event prefixes plus disposable five-field projection; one read-only SQL72 report; one direct read-only five-field comparison. Each uses two threads, 1GB memory, 2GB spill and a 120-second timeout. At least 6GB free space and a 5GB private-directory budget are required. Sort chunks have at most 50,000 records and pair state is bounded to one pair. Limits are bounds, not measured process-memory peaks.

The private database hash must remain unchanged across both read-only phases. Fresh event-source hash/metadata, pinned dependencies and all 70 historical preflight files must remain unchanged. Private source chunks, database and spills are removed. Real identifiers are processed privately and are not logged or uploaded; no learner database is opened. Public outputs contain aggregate evidence only.

```powershell
python validation/preflight_retailrocket_7day_visitor_item_funnel.py --duckdb "E:/DuckDB/duckdb.exe" --output "data/retailrocket_7day_visitor_item_funnel_preflight.json"
```

Measured results will be appended and saved in [aggregate evidence](../data/retailrocket_7day_visitor_item_funnel_preflight.json). Learner SQL72 execution follows the assistant preflight. The cohort and window are explicit analysis choices with the stated left-edge, capture and identity limitations.

## Executed results

The assistant's single event-only SQL72 preflight completed on 9 November 2026. The read-only report returned **five rows × five columns, all five PASS**, with no FAIL or BLOCKED rows. Learner SQL72 execution remains pending. The preceding 9,445-byte frozen method prefix is unchanged, with SHA-256 `dced516c84c1e0f0191a1e8271369fac276ceb68685ba11b6f5a055ac1bb685e`.

| Stage | Visitor-item pairs | Share of eligible pairs % | Conditional step rate % | Status |
|---|---:|---:|---:|---|
| VIEWED_ALL | 2,132,127 | NULL | NULL | PASS |
| EXCLUDED_INCOMPLETE_7D | 89,817 | NULL | NULL | PASS |
| ELIGIBLE_VIEW_7D | 2,042,310 | 100.0000 | NULL | PASS |
| VIEW_THEN_CART_7D | 43,147 | 2.1127 | 2.1127 | PASS |
| VIEW_CART_TRANSACTION_7D | 15,520 | 0.7599 | 35.9701 | PASS |

The cohort partition reconciles exactly: **2,132,127 viewed pairs = 89,817 excluded pairs + 2,042,310 eligible pairs**. The excluded pairs lack the full potential seven-day interval before the global log end, regardless of whether an early successful chain is visible. The last three stages are nested and must not be added together or to the diagnostic rows.

Within the eligible viewed-pair cohort, **43,147 pairs (2.1127%)** have a qualifying cart and **15,520 pairs (0.7599%)** have a qualifying cart followed by a qualifying transaction. Among qualifying cart pairs, **35.9701%** reach the transaction stage. Both later stages must occur by the same first-view deadline; the cart does not restart the clock. These are observed seven-day same-pair progression shares, not person/session/order or causal conversion measures. SQL71 used a different window and cohort, so differences between the two reports cannot be attributed to a business improvement or deterioration.

The independently measured all-event observation end is **1442545187788 ms**, or **2015-09-18T02:59:47.788000Z**, matching the frozen accepted endpoint. Subtracting **604800000 ms** gives the inclusive first-view eligibility cutoff **1441940387788 ms**, or **2015-09-11T02:59:47.788000Z**. An exactly equal first view is eligible. The boundary establishes potential follow-up only; continuous capture and complete individual exposure are not proven. Seven elapsed days remains the chosen rule, and earlier unobserved history means first observed view is not necessarily first-ever view.

Independent Python validation matched **all 2,756,101 original occurrences × five fields**, preserving **460 exact duplicate surplus occurrences**. It measured the source endpoint before the pair fold and verified it again over the complete stream. Its one-pair-at-a-time state independently reproduced the cohort partition, nested counts, Decimal percentages and every NULL in the twenty-five report cells. There were **2,145,179 observed pairs**, including **13,052 without an observed view** that remain outside the viewed-pair cohort. No all-pair dictionary or all-event list was built.

All **three fixture families** passed. The 28-event boundary fixture across ten numeric sort chunks independently produced **[8,1,7,5,3]** for the five rows. It covered exact eligibility/deadline equality, one-millisecond-late carts or transactions, a late cart whose transaction exceeds the original view deadline, strict timestamp ties, earlier out-of-order activity, incomplete pairs excluded despite visible early successes, and an all-event endpoint supplied by non-view records. **Twelve invalid subcases**, including an incorrect expected endpoint, blocked all metrics or produced the documented missing-column binding error. **Two zero-denominator subcases** verified zero eligible and zero qualifying-cart populations. Extra unqueried fields remained outside schema scope, and read-only fixture database hashes stayed unchanged.

Only **events.csv** was read. Frozen SQL54/63 prefixes and a disposable original-five-field projection supported SQL72's readset validation; SQL69, SQL70, SQL71 and prior full audit suites were not rerun. No stored UTC field was queried. Neither property CSV nor the category CSV was read, and no learner database was opened. The full seventeen-column production fact and its other twelve fields were not rebuilt or reverified. Integer epoch arithmetic was used only to express the measured endpoint/cutoff as UTC text in this evidence.

Source selection and numeric pair-key sorting took **24.481 seconds**. The three CLI phases took **5.443 seconds** for event-prefix reconstruction plus projection, **1.734 seconds** for SQL72, and **15.032 seconds** for the complete five-field comparison and independent windowed fold. Each stayed within two threads, 1GB memory, 2GB spill and 120 seconds. Timings exclude hashing and fixtures and are not performance benchmarks.

The run created **56 private event chunks**, totalling **96,993,967 bytes**. The database measured **91,238,400 bytes** before cleanup; the largest post-phase directory observation was **188,232,367 bytes**, not a continuous peak. All private databases, chunks and spills were removed. The database hash remained unchanged across the read-only query/stream, and fresh event-source hash/metadata, **20 pinned dependencies** and **70 historical preflight files** remained unchanged. Real identifiers were processed privately without logging or uploading.

The [aggregate evidence](../data/retailrocket_7day_visitor_item_funnel_preflight.json) records report fingerprint `2c3f6c2e2565f21d67419c0be4b09df9a48ebf4e9937b9fa09ca14b83e5d90a6`. The first two diagnostic rows have genuine NULL rates, and the eligible base has a NULL step rate. DECIMAL values retain their exact four-place JSON serialization. The result establishes the chosen seven-day observed pair funnel and its explicit observation/identity limitations; it does not establish abandonment, continuous collection, validated orders, an optimal horizon or causality.
