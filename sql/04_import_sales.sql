-- Run once in the retail_merchandising DBeaver connection.
-- Load only the evaluation training snapshot; do not append the validation file.
-- Preserve the source's wide layout and VARCHAR fields. No sales values are cast.
-- Existing tables are not replaced. This step does not prove full-value equality.
CREATE SCHEMA IF NOT EXISTS raw;

CREATE TABLE raw.m5_sales_wide AS
SELECT *
FROM read_csv(
    'D:/database/m5-forecasting-accuracy/sales_train_evaluation.csv',
    header = true,
    all_varchar = true
);

-- BASIC CHECKS: if the table already exists, run only the query below.
WITH column_stats AS (
    SELECT
        COUNT(*) AS column_count,
        COUNT(*) FILTER (WHERE data_type = 'VARCHAR') AS varchar_column_count,
        COUNT(*) FILTER (WHERE column_name IN
            ('id', 'item_id', 'dept_id', 'cat_id', 'store_id', 'state_id')) AS identifier_column_count,
        COUNT(*) FILTER (WHERE regexp_full_match(column_name, 'd_[1-9][0-9]*')) AS day_column_count,
        COUNT(*) FILTER (
            WHERE ordinal_position > 6
              AND column_name IS DISTINCT FROM 'd_' || CAST(ordinal_position - 6 AS VARCHAR)
        ) AS day_column_sequence_errors
    FROM information_schema.columns
    WHERE table_catalog = current_database()
      AND table_schema = 'raw' AND table_name = 'm5_sales_wide'
), row_stats AS (
    SELECT
        COUNT(*) AS row_count,
        COUNT(DISTINCT id) AS distinct_series_ids,
        COUNT(DISTINCT (item_id, store_id)) AS distinct_item_store_keys,
        COUNT(DISTINCT item_id) AS distinct_items,
        COUNT(DISTINCT store_id) AS distinct_stores,
        COUNT(DISTINCT state_id) AS distinct_states,
        COUNT(DISTINCT dept_id) AS distinct_departments,
        COUNT(DISTINCT cat_id) AS distinct_categories,
        COUNT(*) FILTER (WHERE
            NULLIF(TRIM(id), '') IS NULL OR NULLIF(TRIM(item_id), '') IS NULL OR
            NULLIF(TRIM(dept_id), '') IS NULL OR NULLIF(TRIM(cat_id), '') IS NULL OR
            NULLIF(TRIM(store_id), '') IS NULL OR NULLIF(TRIM(state_id), '') IS NULL
        ) AS missing_identifier_rows
    FROM raw.m5_sales_wide
), checks AS (
    SELECT 1 AS check_order, 'row_count' AS check_name, row_count AS actual, 30490 AS expected FROM row_stats
    UNION ALL SELECT 2, 'column_count', column_count, 1947 FROM column_stats
    UNION ALL SELECT 3, 'varchar_column_count', varchar_column_count, 1947 FROM column_stats
    UNION ALL SELECT 4, 'identifier_column_count', identifier_column_count, 6 FROM column_stats
    UNION ALL SELECT 5, 'day_column_count', day_column_count, 1941 FROM column_stats
    UNION ALL SELECT 6, 'day_column_sequence_errors', day_column_sequence_errors, 0 FROM column_stats
    UNION ALL SELECT 7, 'distinct_series_ids', distinct_series_ids, 30490 FROM row_stats
    UNION ALL SELECT 8, 'distinct_item_store_keys', distinct_item_store_keys, 30490 FROM row_stats
    UNION ALL SELECT 9, 'distinct_items', distinct_items, 3049 FROM row_stats
    UNION ALL SELECT 10, 'distinct_stores', distinct_stores, 10 FROM row_stats
    UNION ALL SELECT 11, 'distinct_states', distinct_states, 3 FROM row_stats
    UNION ALL SELECT 12, 'distinct_departments', distinct_departments, 7 FROM row_stats
    UNION ALL SELECT 13, 'distinct_categories', distinct_categories, 3 FROM row_stats
    UNION ALL SELECT 14, 'missing_identifier_rows', missing_identifier_rows, 0 FROM row_stats
)
SELECT check_order, check_name, actual, expected,
       CASE WHEN actual = expected THEN 'PASS' ELSE 'FAIL' END AS status
FROM checks
ORDER BY check_order;
