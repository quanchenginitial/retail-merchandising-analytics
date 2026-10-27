-- Run once after the raw price audit. No raw values are changed.
-- Verified snapshot: prices have at most two fractional digits.
-- Additional trailing zeros are exact; nonzero precision beyond cents is rejected.
-- Guard every conversion before CAST, which would otherwise be able to round.
CREATE SCHEMA IF NOT EXISTS stg;

CREATE TABLE stg.m5_prices AS
SELECT store_id, item_id,
    CASE WHEN regexp_full_match(wm_yr_wk, '[1-9][0-9]{4}')
         THEN CAST(wm_yr_wk AS INTEGER)
         ELSE error('Raw week is outside the verified five-digit code contract')
    END AS wm_yr_wk,
    CASE WHEN regexp_full_match(sell_price, '[0-9]+([.][0-9]{1,2}0*)?')
              AND TRY_CAST(sell_price AS DECIMAL(18,2)) > 0
         THEN CAST(sell_price AS DECIMAL(18,2))
         ELSE error('Raw price is outside the verified positive exact-cent contract')
    END AS sell_price
FROM raw.m5_prices;

-- VALIDATION: if the staging table already exists, run only the query below.
WITH expected_schema(column_name, data_type, ordinal_position) AS (
    VALUES ('store_id','VARCHAR',1), ('item_id','VARCHAR',2),
           ('wm_yr_wk','INTEGER',3), ('sell_price','DECIMAL(18,2)',4)
), actual_schema AS (
    SELECT column_name, data_type, ordinal_position
    FROM information_schema.columns
    WHERE table_catalog = current_database()
      AND table_schema = 'stg' AND table_name = 'm5_prices'
), schema_errors AS (
    SELECT COUNT(*) AS error_count
    FROM expected_schema e FULL OUTER JOIN actual_schema a ON e.column_name = a.column_name
    WHERE e.column_name IS NULL OR a.column_name IS NULL
       OR e.data_type IS DISTINCT FROM a.data_type
       OR e.ordinal_position IS DISTINCT FROM a.ordinal_position
), raw_contract AS (
    SELECT COUNT(*) FILTER (WHERE NOT COALESCE(
        regexp_full_match(wm_yr_wk, '[1-9][0-9]{4}') AND
        regexp_full_match(sell_price, '[0-9]+([.][0-9]{1,2}0*)?') AND
        TRY_CAST(sell_price AS DECIMAL(18,2)) > 0, false)) AS violation_rows
    FROM raw.m5_prices
), both_sides AS NOT MATERIALIZED (
    SELECT 'raw' AS side, store_id, item_id, wm_yr_wk, sell_price AS price_text
    FROM raw.m5_prices
    UNION ALL
    SELECT 'staging', store_id, item_id, CAST(wm_yr_wk AS VARCHAR), CAST(sell_price AS VARCHAR)
    FROM stg.m5_prices
), canonical AS MATERIALIZED (
    -- Text-only normalisation: integer leading zeros and fractional trailing zeros.
    -- No price cast/rounding is used to build the raw comparison value.
    SELECT side, store_id, item_id, wm_yr_wk,
        COALESCE(NULLIF(LTRIM(split_part(price_text,'.',1),'0'),''),'0') ||
        CASE WHEN RTRIM(split_part(price_text,'.',2),'0') = '' THEN ''
             ELSE '.' || RTRIM(split_part(price_text,'.',2),'0') END AS canonical_price
    FROM both_sides
), raw_only AS (
    SELECT store_id, item_id, wm_yr_wk, canonical_price FROM canonical WHERE side='raw'
    EXCEPT ALL
    SELECT store_id, item_id, wm_yr_wk, canonical_price FROM canonical WHERE side='staging'
), staging_only AS (
    SELECT store_id, item_id, wm_yr_wk, canonical_price FROM canonical WHERE side='staging'
    EXCEPT ALL
    SELECT store_id, item_id, wm_yr_wk, canonical_price FROM canonical WHERE side='raw'
), stats AS (
    SELECT COUNT(*) AS staging_rows,
        COUNT(DISTINCT (store_id,item_id,wm_yr_wk)) AS distinct_item_store_week_keys,
        COUNT(*) FILTER (WHERE NULLIF(TRIM(store_id),'') IS NULL OR
            NULLIF(TRIM(item_id),'') IS NULL OR wm_yr_wk IS NULL OR sell_price IS NULL
        ) AS missing_core_rows,
        COUNT(*) FILTER (WHERE sell_price <= 0) AS nonpositive_price_rows,
        MIN(sell_price) AS minimum_price, MAX(sell_price) AS maximum_price,
        COUNT(DISTINCT (store_id,item_id)) AS distinct_item_store_pairs,
        COUNT(DISTINCT wm_yr_wk) AS distinct_weeks
    FROM stg.m5_prices
), checks AS (
    SELECT 1 AS check_order, 'staging_rows' AS check_name, staging_rows::VARCHAR AS actual, '6841121' AS expected FROM stats
    UNION ALL SELECT 2, 'column_count', COUNT(*)::VARCHAR, '4' FROM actual_schema
    UNION ALL SELECT 3, 'schema_mismatch_count', error_count::VARCHAR, '0' FROM schema_errors
    UNION ALL SELECT 4, 'distinct_item_store_week_keys', distinct_item_store_week_keys::VARCHAR, '6841121' FROM stats
    UNION ALL SELECT 5, 'missing_core_rows', missing_core_rows::VARCHAR, '0' FROM stats
    UNION ALL SELECT 6, 'nonpositive_price_rows', nonpositive_price_rows::VARCHAR, '0' FROM stats
    UNION ALL SELECT 7, 'minimum_price', minimum_price::VARCHAR, '0.01' FROM stats
    UNION ALL SELECT 8, 'maximum_price', maximum_price::VARCHAR, '107.32' FROM stats
    UNION ALL SELECT 9, 'distinct_item_store_pairs', distinct_item_store_pairs::VARCHAR, '30490' FROM stats
    UNION ALL SELECT 10, 'distinct_weeks', distinct_weeks::VARCHAR, '282' FROM stats
    UNION ALL SELECT 11, 'raw_contract_violation_rows', violation_rows::VARCHAR, '0' FROM raw_contract
    UNION ALL SELECT 12, 'raw_canonical_only_rows', COUNT(*)::VARCHAR, '0' FROM raw_only
    UNION ALL SELECT 13, 'staging_canonical_only_rows', COUNT(*)::VARCHAR, '0' FROM staging_only
)
SELECT check_order, check_name, actual, expected,
       CASE WHEN actual = expected THEN 'PASS' ELSE 'FAIL' END AS status
FROM checks ORDER BY check_order;
