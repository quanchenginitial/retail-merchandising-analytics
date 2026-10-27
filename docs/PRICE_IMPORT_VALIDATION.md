# Price raw import acceptance and preflight

27 October 2026. The learner has completed calendar and sales raw validation. The learner has now supplied a screenshot showing all 12 price import checks with status PASS. The [screenshot transcription](../data/price_import_learner_acceptance.json) records those displayed values. This accepts the raw import structure and keys; the subsequent [detailed price audit](PRICE_AUDIT_VALIDATION.md) has now also passed all 15 learner checks.

## Import and basic acceptance

[06_import_prices.sql](../sql/06_import_prices.sql) uses ordinary CREATE TABLE with read_csv(header=true, all_varchar=true). Existing tables are not replaced. Its four fields remain store_id, item_id, wm_yr_wk and sell_price, at one item/store/source-week per row. The BASIC CHECKS query can be rerun alone for an existing table.

The expected results are 6,841,121 rows and distinct item/store/week keys; four columns, all VARCHAR, with the expected names and order; zero excess duplicate-key rows and rows containing NULL/blank required values; 30,490 item/store pairs, 3,049 items, 10 stores and 282 weeks. Composite distinct counts use tuples, not concatenated strings. Column metadata is limited to the current database and the intended raw table.

No price conversion, positivity/range check, calendar/sales join or full-value reconciliation occurs in this step. Matching pair counts do not establish set equality or daily coverage. Price numeric validation, exact source reconciliation and later sales-date price coverage remain separate acceptance steps.

## Independent assistant verification

[Preflight runner](../validation/preflight_price_import.py) executed the full import and basic checks once in DuckDB v1.5.5 using :memory:. All 12 checks passed; import plus checks took 3.92 seconds in this run. The preflight used two threads, a DuckDB memory_limit setting of 2GB and a temporary spill directory under the ignored project tmp folder. This setting is not a bound on total process memory and does not change the learner's connection. Learner runtime can differ.

The source SHA-256 matched the [registered source audit](../data/m5_source_audit.json) before execution and remained unchanged afterward. The [preflight evidence](../data/price_import_preflight.json) includes the SQL fingerprint, source hash and all results. No learner database or raw file was changed, and no source rows are published.

To reproduce from the repository root:

```powershell
python validation/preflight_price_import.py --duckdb "E:/DuckDB/duckdb.exe" --output "data/price_import_preflight.json"
```

The SQL and runner reference the current local M5 source directory; adjust both when reproducing elsewhere. The learner has now executed the script and passed all 12 checks. The subsequent [detailed price audit](PRICE_AUDIT_VALIDATION.md) is also accepted; follow [the current step](FIRST_STEP_ZH.md) for typed calendar staging. Assistant preflight remains separate from learner evidence.
