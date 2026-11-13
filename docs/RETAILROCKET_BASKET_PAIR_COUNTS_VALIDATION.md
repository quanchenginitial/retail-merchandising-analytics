# Retailrocket unordered basket-pair count diagnostic

## Frozen method before execution

SQL80 counts observed unordered item co-occurrences before calculating association metrics. Its read-only input is the accepted rr_mart.transaction_basket_items table, but its required readset is only visitorid, transactionid and itemid, all BIGINT. The membership timestamps and source_event_rows are unqueried. Repeated source-event occurrences must not multiply a membership's pair contribution; occurrence counts are not quantities.

The population is all 17,672 candidate baskets defined by (visitorid, transactionid), containing 22,323 unique basket/item memberships. All 15,029 single-item baskets remain in this population and contribute zero pairs; 2,643 multi-item baskets contribute pairs. The largest contains 31 distinct items. This population is not the category-1613 subset or seven-day funnel cohort and does not require a prior view/cart event. Candidate baskets are analytical groupings of observed transaction records, not verified paid orders or real-person identities.

For each candidate basket, an unordered pair is represented once with numeric item_a < item_b. The self-join requires equality of both visitorid and transactionid, so the same transaction identifier in different visitor groups cannot create cross-group pairs. No self-pair or reversed duplicate is admitted. A three-item basket contributes three pairs. The same unordered item pair occurring in two different baskets contributes two pair occurrences but one distinct item pair with basket_count=2. Basket_count is binary basket presence for each pair, not click count, item quantity or summed source_event_rows.

## Fifteen-row report

The output columns are check_order, check_name, actual, expected and status. Ten controls use PASS on equality; five first-observed pair diagnostics use INFO with NULL expected. INFO does not mean failure. All displayed non-NULL counts are BIGINT. A valid population containing only singleton baskets has zero pair counts and a NULL max_baskets_per_pair.

| Order | Check | Expected/status |
| --- | --- | --- |
| 1 | membership_rows | 22,323 / PASS |
| 2 | required_key_schema_mismatch | 0 / PASS |
| 3 | invalid_key_rows | 0 / PASS |
| 4 | duplicate_membership_keys | 0 / PASS |
| 5 | candidate_baskets | 17,672 / PASS |
| 6 | single_item_baskets | 15,029 / PASS |
| 7 | multi_item_baskets | 2,643 / PASS |
| 8 | max_items_per_basket | 31 / PASS |
| 9 | pair_occurrences | INFO; sum of basket_count over distinct unordered item pairs |
| 10 | distinct_item_pairs | INFO |
| 11 | pairs_seen_once | INFO; basket_count=1 |
| 12 | pairs_seen_2plus | INFO; basket_count>=2 |
| 13 | max_baskets_per_pair | INFO; NULL if there are no pairs |
| 14 | pair_occurrence_reconciliation_difference | observed pair occurrences minus sum n*(n-1)/2 over every basket = 0 / PASS |
| 15 | pair_frequency_partition_difference | pairs_seen_once + pairs_seen_2plus - distinct_item_pairs = 0 / PASS |

Before the self-join, admission checks the three required field types, non-NULL nonnegative keys, no duplicate membership key, the fixed membership/basket/single/multi counts, and maximum basket size. The admitted key relation is materialized only from valid input. Invalid admission yields all fifteen labels with actual=NULL and status=BLOCKED; fixed expected controls stay visible and INFO expectations stay NULL. A missing required table or column may fail binding. Empty input is not admitted. Additional unqueried columns are allowed. With valid input, reconciliation differences produce FAIL if they differ from zero.

The independent combinatorial invariant includes every basket, including singleton zeros. Later support denominators must retain all eligible candidate baskets rather than silently switching to the multi-item subset. This step publishes neither item-pair identifiers nor support, confidence, lift, rankings, minimum-support rules, recommendations, validation-period performance or causal effects. Frequent co-occurrence can reflect popular items or other shared factors and is not proof of complementarity or recommendation benefit.

## Narrow independent validation

The accepted SQL79 full five-field source proof and six-field membership mapping remain pinned dependencies. This step does not rerun SQL54, SQL63, SQL79, prior full suites, the 2,756,101-row sorted source comparison, or property/category/UTC/enriched-fact work.

Instead, events.csv is canonically parsed once in source order, with accepted header/value rules, source event counts and a 100,000 transaction-occurrence retention cap. Its hash and metadata must match the accepted source snapshots before and after. The retained transaction records reconstruct the six membership fields through the pinned SQL79 Python aggregation helper. The canonical sorted six-field membership SHA-256 must equal the accepted SQL79 independent membership-stream SHA-256. This is a scoped input reconstruction check against prior evidence, not a claim that SQL80 reads or revalidates all original source fields or its unused timestamp/count columns.

The small reconstructed membership CSV is loaded into a disposable six-field DuckDB table, with exact six-field readback checked inside the load phase. SQL80 itself reads only three keys. Independent Python groups the reconstructed memberships by both visitorid and transactionid, enumerates numeric unordered combinations once per basket, and counts basket appearances for each pair. The complete SQL pair aggregation stream is compared to this reference in numeric pair order, along with the entire fifteen-row report. Input baskets and keys are bounded by the transaction cap; total pair occurrences and distinct pair keys each have a 100,000 cap, with exceeding a cap causing failure rather than sampling. The accepted maximum size of 31 and population controls bound the self-join before it runs.

Three real CLI phases are declared: (1) private six-field CSV load and exact small input readback; (2) read-only SQL80; (3) read-only complete pair aggregation stream and reference comparison. Each uses two threads, 1GB memory, 2GB maximum spill and a 120-second timeout. Minimum free disk is 8GB; the private-directory budget is 7GB. The one source scan and independent Python reconstruction are timed separately. Observed post-phase directory sizes are not continuous peak measurements. This method is frozen before focused fixtures and one real-source attempt.

Focused fixtures cover numeric item ordering (2 versus 10), a three-item basket, singleton zeros, one pair in two different baskets, shared transaction IDs across different visitors, repeated source observations and changes to unqueried source_event_rows having no pair weight, invalid duplicate/NULL keys, and a valid singleton-only population. No historical full test suite is rerun.

The event source, pinned dependencies and all seventy-eight historical preflight artifacts must remain unchanged. Private database bytes must match before and after read-only phases. Temporary databases, membership CSVs and spills are removed; the learner database is never opened. Public evidence contains aggregate counts, code and hashes only, with no actual visitor/item/transaction IDs or item-pair list. SQL79 remains the evidence for the accepted stored six-field model; SQL80 adds a key-only co-occurrence diagnostic.

```powershell
python validation/preflight_retailrocket_basket_pair_counts.py --duckdb "E:/DuckDB/duckdb.exe" --output "data/retailrocket_basket_pair_counts_preflight.json"
```

Measured results will be appended after validation. Learner execution remains separate from assistant preparation.

## Executed results

Assistant SQL80 preflight passed at 2026-11-13T03:58:56.720430+00:00 using v1.5.5 (Variegata) d8cdaa33fd. One real-source attempt completed the three declared CLI phases. The fifteen-row, five-column report contains ten PASS controls and five INFO diagnostics, with zero FAIL or BLOCKED rows. Learner execution and screenshot acceptance remain pending.

| check_order | check_name | actual | expected | status |
| --- | --- | --- | --- | --- |
| 1 | membership_rows | 22323 | 22323 | PASS |
| 2 | required_key_schema_mismatch | 0 | 0 | PASS |
| 3 | invalid_key_rows | 0 | 0 | PASS |
| 4 | duplicate_membership_keys | 0 | 0 | PASS |
| 5 | candidate_baskets | 17672 | 17672 | PASS |
| 6 | single_item_baskets | 15029 | 15029 | PASS |
| 7 | multi_item_baskets | 2643 | 2643 | PASS |
| 8 | max_items_per_basket | 31 | 31 | PASS |
| 9 | pair_occurrences | 10757 | NULL | INFO |
| 10 | distinct_item_pairs | 9688 | NULL | INFO |
| 11 | pairs_seen_once | 8785 | NULL | INFO |
| 12 | pairs_seen_2plus | 903 | NULL | INFO |
| 13 | max_baskets_per_pair | 39 | NULL | INFO |
| 14 | pair_occurrence_reconciliation_difference | 0 | 0 | PASS |
| 15 | pair_frequency_partition_difference | 0 | 0 | PASS |

The population retains 17,672 candidate baskets and 22,323 item memberships. The 15,029 singleton baskets contribute zero pairs while remaining in the population; 2,643 multi-item baskets contribute 10,757 unordered basket-pair occurrences. These reduce to 9,688 distinct item pairs: 8,785 occur in one basket and 903 in at least two baskets. The largest observed pair frequency is 39 baskets. Both the sum-of-choose-two invariant and frequency partition difference are zero. Counts describe this supplied snapshot; pair identities and a ranking are not published.

One canonical events.csv parse reconstructed the accepted 22,323 six-field membership tuples from 22,457 transaction occurrences. The canonical reconstruction SHA-256 exactly matched accepted SQL79's independent membership-stream fingerprint: `99c7d679d858b3d1335dfafa22aa48b5e842d03336af5c85330e96853c59fca5`. The small private six-field table readback matched the same fingerprint. This reuses SQL79's accepted complete original five-field proof; it does not repeat the 2,756,101-row sorted source comparison, SQL54/63/79 or historical full suites. SQL80 queries only the three key columns, so unused timestamps and source_event_rows are not part of its analytical readset.

Independent Python combinations grouped by both basket-key fields and numeric item ordering matched every one of the 9,688 three-field SQL pair aggregates. Both total pair occurrences and distinct pair keys stayed below the declared 100,000 caps. The complete fifteen-row report matched the independent reference, including all INFO expectations and the singleton-inclusive denominator controls. No source-event occurrence weighting was used.

Three focused fixture families passed. Numeric item IDs 2 and 10, a three-item basket, a singleton, shared transaction identifiers across different visitors and one pair appearing in two baskets produced five pair occurrences and four distinct pairs; changing unqueried source_event_rows did not change the result. Five invalid key/type/expected-control cases blocked all actuals before the self-join while retaining static expectations. A valid singleton-only population preserved its basket count, emitted zero pairs and retained a NULL maximum pair frequency.

Measured CLI times were 0.427 seconds for private input load/readback, 0.234 seconds for read-only SQL80 and 0.294 seconds for the complete pair stream. The single Python source scan and membership reconstruction took 28.824 seconds; the independent pair reference took 0.07 seconds. Each CLI phase used two threads, 1GB memory/2GB maximum spill and completed within 120 seconds. The largest private directory observed after a phase was 1,922,839 bytes, below the 7GB budget; this was not a continuous peak measurement.

Source hashes/metadata, pinned dependencies and all 78 historical preflight artifacts remained unchanged. Private database hashes matched before and after both read-only phases. Temporary databases, membership CSV and spills were removed. No learner database was opened and no actual source IDs, item-pair list or individual records were published. Property files, category reference, UTC-derived fields and the enriched fact remained outside scope.

This diagnostic establishes reproducible binary pair counts over candidate baskets. It does not calculate support, confidence or lift, identify meaningful complements, establish recommendation effectiveness or validate business order semantics. Subsequent association metrics must retain all eligible candidate baskets as their population and address sparse co-occurrences separately.

Report SHA-256: `fcf64ac290ecfab36fd5b617de0638f7d08b331a3a084c4f6731fc7b706c4a03`. Script SHA-256: `f6858e4074798d1786dff4cee147d9049fb901519de1d17c07058afebf49c2f4`. Validator SHA-256: `12b7e52450c483aba2ea6b788f5a1f5c88d62a18f40ad2b43c3da9cb09e1c486`. The original 7,702-byte method prefix remains unchanged at `069c296001badd3789a4a652e368af6805eaf65b8497932622bcb8be7d8d9b86`.
