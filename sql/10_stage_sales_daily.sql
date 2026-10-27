-- Run once after the raw sales audit passes. Preserve every zero-sales day.
-- Four-column staging grain: item_id / store_id / d, with INTEGER units.
-- Product/category/state attributes stay in raw for later dimension creation.
-- No calendar or price join occurs. Full cell-value reconciliation is the next step.
CREATE SCHEMA IF NOT EXISTS stg;

CREATE TABLE stg.m5_sales_daily AS
SELECT item_id, store_id, d,
    CASE WHEN regexp_full_match(units_text, '[0-9]+')
              AND TRY_CAST(units_text AS INTEGER) >= 0
         THEN CAST(units_text AS INTEGER)
         ELSE error('Raw daily sales must be nonnegative integers within INTEGER range')
    END AS units
FROM raw.m5_sales_wide
UNPIVOT INCLUDE NULLS (
    units_text FOR d IN (COLUMNS('^d_[1-9][0-9]*$'))
);

-- VALIDATION: if the staging table already exists, run only the query below.
WITH expected_schema(column_name, data_type, ordinal_position) AS (
    VALUES ('item_id','VARCHAR',1), ('store_id','VARCHAR',2),
           ('d','VARCHAR',3), ('units','INTEGER',4)
), actual_schema AS (
    SELECT column_name, data_type, ordinal_position
    FROM information_schema.columns
    WHERE table_catalog = current_database()
      AND table_schema = 'stg' AND table_name = 'm5_sales_daily'
), schema_errors AS (
    SELECT COUNT(*) AS error_count
    FROM expected_schema e FULL OUTER JOIN actual_schema a ON e.column_name = a.column_name
    WHERE e.column_name IS NULL OR a.column_name IS NULL
       OR e.data_type IS DISTINCT FROM a.data_type
       OR e.ordinal_position IS DISTINCT FROM a.ordinal_position
), numbered AS NOT MATERIALIZED (
    SELECT *, TRY_CAST(SUBSTR(d,3) AS INTEGER) AS day_number FROM stg.m5_sales_daily
), checked AS NOT MATERIALIZED (
    SELECT *, COALESCE(regexp_full_match(d,'d_[1-9][0-9]*')
              AND day_number BETWEEN 1 AND 1941, false) AS valid_day
    FROM numbered
), series_stats AS MATERIALIZED (
    SELECT item_id, store_id, COUNT(*) AS row_count,
        COUNT(*) FILTER (WHERE NULLIF(TRIM(item_id),'') IS NULL OR
            NULLIF(TRIM(store_id),'') IS NULL OR d IS NULL OR units IS NULL) AS missing_core_rows,
        COUNT(*) FILTER (WHERE units < 0) AS negative_sales_rows,
        COUNT(*) FILTER (WHERE units = 0) AS zero_sales_rows,
        SUM(units) AS total_units, MAX(units) AS max_daily_units,
        COUNT(*) FILTER (WHERE NOT valid_day) AS invalid_day_rows,
        bit_count(bitstring_agg(CASE WHEN valid_day THEN day_number END,1,1941)) AS covered_days
    FROM checked GROUP BY item_id,store_id
), totals AS (
    SELECT COALESCE(SUM(row_count),0) AS staging_rows,
        COALESCE(SUM(missing_core_rows),0) AS missing_core_rows,
        COALESCE(SUM(negative_sales_rows),0) AS negative_sales_rows,
        COALESCE(SUM(zero_sales_rows),0) AS zero_sales_rows,
        COALESCE(SUM(total_units),0) AS total_units, MAX(max_daily_units) AS max_daily_units,
        COUNT(*) AS series_count,
        COUNT(*) FILTER (WHERE row_count <> 1941) AS series_row_count_errors,
        COUNT(*) FILTER (WHERE covered_days IS DISTINCT FROM 1941) AS series_day_coverage_errors,
        COALESCE(SUM(invalid_day_rows),0) AS invalid_day_rows
    FROM series_stats
), raw_pairs AS (
    SELECT DISTINCT item_id,store_id FROM raw.m5_sales_wide
), missing_series AS (
    SELECT * FROM raw_pairs EXCEPT SELECT item_id,store_id FROM series_stats
), extra_series AS (
    SELECT item_id,store_id FROM series_stats EXCEPT SELECT * FROM raw_pairs
), expected_store_totals(store_id,total_units) AS (
    VALUES ('CA_1',7832248), ('CA_2',5818395), ('CA_3',11363540), ('CA_4',4182534),
           ('TX_1',5692823), ('TX_2',7329642), ('TX_3',6205940),
           ('WI_1',5261506), ('WI_2',6697988), ('WI_3',6542557)
), actual_store_totals AS (
    SELECT store_id,SUM(total_units) AS total_units FROM series_stats GROUP BY store_id
), store_errors AS (
    SELECT COUNT(*) AS error_count
    FROM expected_store_totals e FULL OUTER JOIN actual_store_totals a ON e.store_id=a.store_id
    WHERE e.store_id IS NULL OR a.store_id IS NULL OR e.total_units IS DISTINCT FROM a.total_units
), checks AS (
    SELECT 1 AS check_order, 'staging_rows' AS check_name, staging_rows::VARCHAR AS actual, '59181090' AS expected FROM totals
    UNION ALL SELECT 2, 'column_count', COUNT(*)::VARCHAR, '4' FROM actual_schema
    UNION ALL SELECT 3, 'schema_mismatch_count', error_count::VARCHAR, '0' FROM schema_errors
    UNION ALL SELECT 4, 'missing_core_rows', missing_core_rows::VARCHAR, '0' FROM totals
    UNION ALL SELECT 5, 'negative_sales_rows', negative_sales_rows::VARCHAR, '0' FROM totals
    UNION ALL SELECT 6, 'zero_sales_rows', zero_sales_rows::VARCHAR, '40241819' FROM totals
    UNION ALL SELECT 7, 'total_units', total_units::VARCHAR, '66927173' FROM totals
    UNION ALL SELECT 8, 'max_daily_units', max_daily_units::VARCHAR, '763' FROM totals
    UNION ALL SELECT 9, 'series_count', series_count::VARCHAR, '30490' FROM totals
    UNION ALL SELECT 10, 'series_row_count_errors', series_row_count_errors::VARCHAR, '0' FROM totals
    UNION ALL SELECT 11, 'series_day_coverage_errors', series_day_coverage_errors::VARCHAR, '0' FROM totals
    UNION ALL SELECT 12, 'invalid_day_rows', invalid_day_rows::VARCHAR, '0' FROM totals
    UNION ALL SELECT 13, 'series_set_difference_rows',
        ((SELECT COUNT(*) FROM missing_series)+(SELECT COUNT(*) FROM extra_series))::VARCHAR, '0'
    UNION ALL SELECT 14, 'store_total_mismatches', error_count::VARCHAR, '0' FROM store_errors
)
SELECT check_order,check_name,actual,expected,
       CASE WHEN actual=expected THEN 'PASS' ELSE 'FAIL' END AS status
FROM checks ORDER BY check_order;
