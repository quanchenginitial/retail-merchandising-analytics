-- Independently executed by the assistant in DuckDB v1.5.5 :memory:.
-- Change only the source path to reproduce against your local snapshot.
-- Reads the CSV directly; no persistent project table is created.
SELECT
    count(*) AS rows,
    count(DISTINCT (store_id, item_id, wm_yr_wk)) AS distinct_composite_keys,
    count(*) - count(DISTINCT (store_id, item_id, wm_yr_wk)) AS duplicate_composite_rows,
    count(*) FILTER (WHERE store_id IS NULL OR item_id IS NULL OR wm_yr_wk IS NULL) AS null_key_rows,
    min(try_cast(sell_price AS DECIMAL(18,6))) AS min_price,
    max(try_cast(sell_price AS DECIMAL(18,6))) AS max_price,
    count(*) FILTER (WHERE sell_price IS NULL) AS null_price_rows,
    count(*) FILTER (WHERE sell_price IS NOT NULL AND try_cast(sell_price AS DECIMAL(18,6)) IS NULL) AS invalid_price_rows,
    count(*) FILTER (WHERE try_cast(sell_price AS DECIMAL(18,6)) = 0) AS zero_price_rows,
    count(*) FILTER (WHERE try_cast(sell_price AS DECIMAL(18,6)) <= 0) AS nonpositive_price_rows
FROM read_csv('D:/database/m5-forecasting-accuracy/sell_prices.csv', header=true, all_varchar=true);
