# Product dimension: purpose and validation

27 October 2026. The learner screenshot confirms all 15 checks from [12_build_product_dimension.sql](../sql/12_build_product_dimension.sql) passed: 3,049 unique products, seven departments and three categories, with zero schema, missing-value, mapping, source-difference or source-key join errors. core.m5_product is accepted. The [screenshot transcription](../data/product_dimension_learner_acceptance.json) is separate from the assistant preflight below; follow [the current step](FIRST_STEP_ZH.md) for subsequent work.

## Purpose and table contract

The product dimension provides one item_id row with its source dept_id and cat_id. This classifies products for later category totals, product contribution and variability analysis. Sales observations remain in the daily table; subsequent joins use item_id. Store and date dimensions are separate later steps.

All three fields remain VARCHAR, preserving original codes exactly, including any leading zeros. No product names, descriptions, brands, costs or inferred labels are invented. The current source contains 3,049 products, seven departments and three categories. These counts are snapshot acceptance controls, not universal business rules.

The source wide table repeats product attributes across stores. Identical item/department/category triples collapse to one row. Conflicting triples for one item cause creation to fail, as do NULL, empty or space-only required codes and departments mapped to more than one category. The script never chooses an arbitrary MIN/MAX mapping to hide a conflict. A single guarded CREATE TABLE AS SELECT creates the target; it does not overwrite an existing table.

Uniqueness is validated by queries rather than enforced by a declared PRIMARY KEY. Future joins must continue to check uniqueness and coverage if data changes. An empty source can produce an empty target, but it fails the required product counts and cannot be accepted.

## Acceptance checks

All 15 checks must pass: 3,049 rows and distinct items, three VARCHAR columns in the declared order, seven departments and three categories; zero duplicate/null item surplus, missing required values, source mapping conflicts, target department conflicts, source-only or dimension-only triples and source-key join errors.

The reconciliation compares the distinct source triples to all target rows using EXCEPT ALL in both directions. This preserves target duplicate multiplicity and detects a changed classification even if total row count stays constant. The relevant multiset behaviour is documented in [DuckDB set operations](https://duckdb.org/docs/1.5/sql/query_syntax/setops).

Each distinct source item key must join to exactly one dimension row. This checks the small source key set; it is not an executed join of all 59,181,090 daily sales rows and does not establish end-to-end sales join preservation. Extra dimension items are caught by the reverse reconciliation.

## Independent execution

The [preflight runner](../validation/preflight_product_dimension.py) used a private in-memory DuckDB, never the learner database. It read every sales CSV row but stored only the three required code columns, without rebuilding the daily table. The source hash matched the registered snapshot before the run and stayed unchanged afterward.

With DuckDB v1.5.5, two threads and memory_limit=512MB, projection import, dimension creation and 15 checks took 4.488 seconds. All checks passed. This is a single-run measurement; the memory setting is not a measured total-process limit and is not applied to the learner connection. [Preflight evidence](../data/product_dimension_preflight.json) records hashes, settings and results.

Twelve targeted cases passed. The valid fixture retains leading-zero item codes and collapses identical repeated triples. Five source cases reject conflicting item mappings, a department with two categories, NULL category, empty item code and a space-only department. Five post-creation cases detect an extra duplicate row, changed mapping with unchanged row count, missing product, extra product and reordered columns. The final case verifies that empty-source creation fails acceptance. Fixture cardinality expectations are adjusted to two products/departments/categories; validation logic is unchanged.

To reproduce from the repository root:

```powershell
python validation/preflight_product_dimension.py --duckdb "E:/DuckDB/duckdb.exe" --output "data/product_dimension_preflight.json"
```

The runner uses the current local CSV path. The learner SQL reads named tables only. When core.m5_product already exists, execute only the query after VALIDATION. Learner acceptance is recorded above; follow [the current step](FIRST_STEP_ZH.md) for the next action.
