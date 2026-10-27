# Store dimension: purpose and validation

27 October 2026. The learner has accepted core.m5_product with all 15 checks passed. The next action is [13_build_store_dimension.sql](../sql/13_build_store_dimension.sql), providing a consistent store-to-state mapping for later store and regional sales comparisons. Assistant preflight is complete; learner creation of core.m5_store remains pending.

## Table and transformation contract

core.m5_store has two VARCHAR columns, store_id and state_id, with one row per store. Identical source pairs repeated across products collapse to one pair. Store and state codes are retained exactly as supplied in raw.m5_sales_wide. State membership comes from state_id, not from parsing the store identifier. No city, address, store name, floor area or other unavailable attribute is invented.

The creation guard rejects NULL, empty and space-only codes, or a store mapped to more than one state. It does not impose the reverse restriction: a state can contain several stores. Conflicts are rejected rather than resolved by arbitrarily selecting MIN/MAX. Ordinary CREATE TABLE AS SELECT does not overwrite an existing target.

Key uniqueness is verified by the checks, not enforced by a declared PRIMARY KEY. If tables change later, uniqueness and coverage must be rechecked before joining. Empty-source creation can succeed, but the resulting empty table fails acceptance.

## Acceptance checks

All 13 checks must pass together: ten rows and distinct stores, two VARCHAR fields in the correct order, three states, and zero missing values, duplicate/null store surplus, source mapping conflicts, two-way source differences, source-key join errors or state-count mismatches.

The current source snapshot contains four stores with state_id CA, three with TX and three with WI. The preflight independently grouped distinct raw store/state pairs to verify these counts, recording them as source_state_store_counts. They are snapshot controls, not universal regional rules.

Two-way EXCEPT ALL compares distinct raw pairs with every target row, preserving target duplicate multiplicity. Thus swapping state assignments while preserving total store and state counts still fails exact reconciliation. Each distinct source store key must match exactly one dimension row; extra target stores are detected by the reverse comparison. This small key-set check does not execute or validate a full join to the 59,181,090-row sales table. That later join must separately preserve rows and units.

## Independent execution

The [runner](../validation/preflight_store_dimension.py) read every source CSV row but stored only store_id and state_id in private in-memory DuckDB databases. It never opened the learner database or rebuilt daily sales. The source SHA-256 matched the registered snapshot before execution and stayed unchanged afterward.

With DuckDB v1.5.5, two threads and memory_limit=512MB, projection loading, creation, validation and the independent state-count profile took 3.927 seconds. All 13 full-source checks passed. These are one-run settings and timing, not a measured total-process memory bound or runtime guarantee; they do not change the learner connection. See [preflight evidence](../data/store_dimension_preflight.json).

Eleven fixture cases passed: identical pairs collapse correctly; conflicting states, NULL state, empty store and space-only state reject creation; duplicate target row, swapped state assignments with unchanged counts, missing store, extra store/state and reordered columns fail validation; an empty source cannot pass acceptance. Only fixture cardinality and state-count expectations are adjusted for the small dataset. No fixture mutation touches user tables or source files.

To reproduce from the repository root:

```powershell
python validation/preflight_store_dimension.py --duckdb "E:/DuckDB/duckdb.exe" --output "data/store_dimension_preflight.json"
```

The runner uses the current local CSV path. The learner SQL reads existing named tables. When core.m5_store already exists, run only the query after VALIDATION. Follow [the current step](FIRST_STEP_ZH.md) and return the 13-row result for acceptance.
