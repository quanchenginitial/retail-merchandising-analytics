-- Read-only. Run after 06's 12 basic checks and calendar/sales audits pass.
-- DOUBLE is used only for finite-number, sign and range diagnostics, not money sums.
-- Exact reconciliation compares all four original VARCHAR fields, not parsed prices.
-- Pair/week existence is NOT daily sales-price coverage. No quantities are joined.
WITH source_rows AS MATERIALIZED (
    SELECT store_id, item_id, wm_yr_wk, sell_price FROM read_csv(
        'D:/database/m5-forecasting-accuracy/sell_prices.csv',
        header = true, all_varchar = true
    )
), raw_rows AS NOT MATERIALIZED (
    SELECT store_id, item_id, wm_yr_wk, sell_price FROM raw.m5_prices
), typed_rows AS NOT MATERIALIZED (
    SELECT *, TRY_CAST(sell_price AS DOUBLE) AS numeric_price,
           NULLIF(TRIM(sell_price), '') IS NULL AS missing_price
    FROM raw_rows
), stats AS (
    SELECT
        COUNT(*) AS table_rows,
        COUNT(*) FILTER (WHERE
            NULLIF(TRIM(store_id), '') IS NULL OR NULLIF(TRIM(item_id), '') IS NULL OR
            NULLIF(TRIM(wm_yr_wk), '') IS NULL OR missing_price
        ) AS missing_required_rows,
        COUNT(*) - COUNT(DISTINCT (store_id, item_id, wm_yr_wk)) AS duplicate_key_rows,
        COUNT(*) FILTER (WHERE isfinite(numeric_price)) AS valid_numeric_price_rows,
        COUNT(*) FILTER (WHERE NOT missing_price
            AND NOT COALESCE(isfinite(numeric_price), false)) AS invalid_price_rows,
        COUNT(*) FILTER (WHERE isfinite(numeric_price) AND numeric_price <= 0) AS nonpositive_price_rows,
        MIN(numeric_price) FILTER (WHERE isfinite(numeric_price)) AS minimum_price,
        MAX(numeric_price) FILTER (WHERE isfinite(numeric_price)) AS maximum_price,
        COUNT(*) FILTER (WHERE NOT COALESCE(
            regexp_full_match(wm_yr_wk, '[0-9]{5}'), false)) AS invalid_week_code_rows
    FROM typed_rows
), sales_pairs AS MATERIALIZED (
    SELECT DISTINCT store_id, item_id FROM raw.m5_sales_wide
), calendar_weeks AS MATERIALIZED (
    SELECT DISTINCT wm_yr_wk FROM raw.m5_calendar
), price_pairs AS (
    SELECT DISTINCT store_id, item_id FROM raw_rows
), unknown_weeks AS (
    SELECT COUNT(*) AS row_count FROM raw_rows p
    WHERE NOT EXISTS (SELECT 1 FROM calendar_weeks c WHERE c.wm_yr_wk = p.wm_yr_wk)
), orphan_pairs AS (
    SELECT COUNT(*) AS row_count FROM raw_rows p
    WHERE NOT EXISTS (SELECT 1 FROM sales_pairs s
                      WHERE s.store_id = p.store_id AND s.item_id = p.item_id)
), pairs_without_prices AS (
    SELECT COUNT(*) AS pair_count FROM sales_pairs s
    WHERE NOT EXISTS (SELECT 1 FROM price_pairs p
                      WHERE p.store_id = s.store_id AND p.item_id = s.item_id)
), source_only AS (
    SELECT * FROM source_rows EXCEPT ALL SELECT * FROM raw_rows
), table_only AS (
    SELECT * FROM raw_rows EXCEPT ALL SELECT * FROM source_rows
), checks AS (
    SELECT 1 AS check_order, 'source_rows' AS check_name, COUNT(*)::VARCHAR AS actual, '6841121' AS expected FROM source_rows
    UNION ALL SELECT 2, 'table_rows', table_rows::VARCHAR, '6841121' FROM stats
    UNION ALL SELECT 3, 'missing_required_rows', missing_required_rows::VARCHAR, '0' FROM stats
    UNION ALL SELECT 4, 'duplicate_key_rows', duplicate_key_rows::VARCHAR, '0' FROM stats
    UNION ALL SELECT 5, 'valid_numeric_price_rows', valid_numeric_price_rows::VARCHAR, '6841121' FROM stats
    UNION ALL SELECT 6, 'invalid_price_rows', invalid_price_rows::VARCHAR, '0' FROM stats
    UNION ALL SELECT 7, 'nonpositive_price_rows', nonpositive_price_rows::VARCHAR, '0' FROM stats
    UNION ALL SELECT 8, 'minimum_price', minimum_price::VARCHAR, (0.01::DOUBLE)::VARCHAR FROM stats
    UNION ALL SELECT 9, 'maximum_price', maximum_price::VARCHAR, (107.32::DOUBLE)::VARCHAR FROM stats
    UNION ALL SELECT 10, 'invalid_week_code_rows', invalid_week_code_rows::VARCHAR, '0' FROM stats
    UNION ALL SELECT 11, 'unknown_calendar_week_rows', row_count::VARCHAR, '0' FROM unknown_weeks
    UNION ALL SELECT 12, 'orphan_item_store_rows', row_count::VARCHAR, '0' FROM orphan_pairs
    UNION ALL SELECT 13, 'sales_pairs_without_any_price', pair_count::VARCHAR, '0' FROM pairs_without_prices
    UNION ALL SELECT 14, 'source_only_rows', COUNT(*)::VARCHAR, '0' FROM source_only
    UNION ALL SELECT 15, 'table_only_rows', COUNT(*)::VARCHAR, '0' FROM table_only
)
SELECT check_order, check_name, actual, expected,
       CASE WHEN actual = expected THEN 'PASS' ELSE 'FAIL' END AS status
FROM checks ORDER BY check_order;
