-- Run once in the retail_merchandising DBeaver connection.
-- Grain: one store / item / source week. Preserve all four fields as VARCHAR.
-- Existing tables are not replaced. No sales or calendar joins are performed.
-- Price numeric validity and full source reconciliation are a later step.
CREATE SCHEMA IF NOT EXISTS raw;

CREATE TABLE raw.m5_prices AS
SELECT *
FROM read_csv(
    'D:/database/m5-forecasting-accuracy/sell_prices.csv',
    header = true,
    all_varchar = true
);

-- BASIC CHECKS: if the table already exists, run only the query below.
WITH column_stats AS (
    SELECT
        COUNT(*) AS column_count,
        COUNT(*) FILTER (WHERE data_type = 'VARCHAR') AS varchar_column_count,
        COUNT(*) FILTER (WHERE column_name IN
            ('store_id', 'item_id', 'wm_yr_wk', 'sell_price')) AS expected_column_names,
        COUNT(*) FILTER (WHERE column_name IS DISTINCT FROM
            CASE ordinal_position WHEN 1 THEN 'store_id' WHEN 2 THEN 'item_id'
                 WHEN 3 THEN 'wm_yr_wk' WHEN 4 THEN 'sell_price' END
        ) AS column_sequence_errors
    FROM information_schema.columns
    WHERE table_catalog = current_database()
      AND table_schema = 'raw' AND table_name = 'm5_prices'
), row_stats AS (
    SELECT
        COUNT(*) AS row_count,
        COUNT(DISTINCT (store_id, item_id, wm_yr_wk)) AS distinct_item_store_week_keys,
        COUNT(*) - COUNT(DISTINCT (store_id, item_id, wm_yr_wk)) AS duplicate_key_rows,
        COUNT(DISTINCT (store_id, item_id)) AS distinct_item_store_pairs,
        COUNT(DISTINCT item_id) AS distinct_items,
        COUNT(DISTINCT store_id) AS distinct_stores,
        COUNT(DISTINCT wm_yr_wk) AS distinct_weeks,
        COUNT(*) FILTER (WHERE
            NULLIF(TRIM(store_id), '') IS NULL OR NULLIF(TRIM(item_id), '') IS NULL OR
            NULLIF(TRIM(wm_yr_wk), '') IS NULL OR NULLIF(TRIM(sell_price), '') IS NULL
        ) AS missing_required_rows
    FROM raw.m5_prices
), checks AS (
    SELECT 1 AS check_order, 'row_count' AS check_name, row_count AS actual, 6841121 AS expected FROM row_stats
    UNION ALL SELECT 2, 'column_count', column_count, 4 FROM column_stats
    UNION ALL SELECT 3, 'varchar_column_count', varchar_column_count, 4 FROM column_stats
    UNION ALL SELECT 4, 'expected_column_names', expected_column_names, 4 FROM column_stats
    UNION ALL SELECT 5, 'column_sequence_errors', column_sequence_errors, 0 FROM column_stats
    UNION ALL SELECT 6, 'distinct_item_store_week_keys', distinct_item_store_week_keys, 6841121 FROM row_stats
    UNION ALL SELECT 7, 'duplicate_key_rows', duplicate_key_rows, 0 FROM row_stats
    UNION ALL SELECT 8, 'missing_required_rows', missing_required_rows, 0 FROM row_stats
    UNION ALL SELECT 9, 'distinct_item_store_pairs', distinct_item_store_pairs, 30490 FROM row_stats
    UNION ALL SELECT 10, 'distinct_items', distinct_items, 3049 FROM row_stats
    UNION ALL SELECT 11, 'distinct_stores', distinct_stores, 10 FROM row_stats
    UNION ALL SELECT 12, 'distinct_weeks', distinct_weeks, 282 FROM row_stats
)
SELECT check_order, check_name, actual, expected,
       CASE WHEN actual = expected THEN 'PASS' ELSE 'FAIL' END AS status
FROM checks ORDER BY check_order;
