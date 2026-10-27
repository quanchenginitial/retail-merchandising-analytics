-- Read-only: reconcile every daily value to its original raw wide-table cell.
-- Run after 10_stage_sales_daily.sql. No tables are created or changed.
-- Numeric day order matters: lexical order would put d_10 before d_2.
WITH raw_day_columns AS (
    SELECT column_name, ordinal_position,
        TRY_CAST(SUBSTR(column_name,3) AS INTEGER) AS day_number
    FROM information_schema.columns
    WHERE table_catalog=current_database() AND table_schema='raw'
      AND table_name='m5_sales_wide' AND starts_with(column_name,'d_')
), raw_shape AS (
    SELECT COUNT(*) AS day_columns,
        COUNT(*) FILTER (WHERE NOT COALESCE(
            regexp_full_match(column_name,'d_[1-9][0-9]*')
            AND day_number BETWEEN 1 AND 1941
            AND ordinal_position=day_number+6,false)) AS sequence_errors
    FROM raw_day_columns
), raw_lists AS MATERIALIZED (
    SELECT item_id, store_id,
        COUNT(*) OVER (PARTITION BY item_id,store_id) AS pair_rows,
        list_transform(list_value(*COLUMNS('^d_[1-9][0-9]*$')),
            lambda value: CASE WHEN regexp_full_match(value,'[0-9]+')
                AND TRY_CAST(value AS INTEGER)>=0 THEN CAST(value AS INTEGER)
                ELSE error('Raw daily sales must be nonnegative integers within INTEGER range') END
        ) AS expected_units
    FROM raw.m5_sales_wide
), raw_totals AS (
    SELECT COUNT(*) AS series_rows,
        COUNT(*) FILTER (WHERE pair_rows<>1 OR NULLIF(TRIM(item_id),'') IS NULL
            OR NULLIF(TRIM(store_id),'') IS NULL) AS key_error_rows
    FROM raw_lists
), numbered AS NOT MATERIALIZED (
    SELECT *, TRY_CAST(SUBSTR(d,3) AS INTEGER) AS day_number FROM stg.m5_sales_daily
), checked AS NOT MATERIALIZED (
    SELECT *, COALESCE(regexp_full_match(d,'d_[1-9][0-9]*')
        AND day_number BETWEEN 1 AND 1941,false) AS valid_day FROM numbered
), series_stats AS MATERIALIZED (
    SELECT item_id,store_id,COUNT(*) AS row_count,
        COUNT(*) FILTER (WHERE NULLIF(TRIM(item_id),'') IS NULL OR
            NULLIF(TRIM(store_id),'') IS NULL OR d IS NULL OR units IS NULL) AS missing_core_rows,
        COUNT(*) FILTER (WHERE NOT valid_day) AS invalid_day_rows,
        bit_count(bitstring_agg(CASE WHEN valid_day THEN day_number END,1,1941)) AS covered_days,
        list(units ORDER BY day_number) AS actual_units
    FROM checked GROUP BY item_id,store_id
), staging_totals AS (
    SELECT COALESCE(SUM(row_count),0) AS staging_rows,COUNT(*) AS series_count,
        COALESCE(SUM(missing_core_rows),0) AS missing_core_rows,
        COALESCE(SUM(invalid_day_rows),0) AS invalid_day_rows,
        COUNT(*) FILTER (WHERE row_count<>1941) AS row_count_errors,
        COUNT(*) FILTER (WHERE covered_days IS DISTINCT FROM 1941) AS coverage_errors
    FROM series_stats
), raw_only AS (
    SELECT item_id,store_id FROM raw_lists
    EXCEPT SELECT item_id,store_id FROM series_stats
), staging_only AS (
    SELECT item_id,store_id FROM series_stats
    EXCEPT SELECT item_id,store_id FROM raw_lists
), comparisons AS MATERIALIZED (
    SELECT r.item_id,r.store_id,
        r.expected_units IS DISTINCT FROM s.actual_units AS mismatched_series,
        CASE WHEN r.expected_units IS DISTINCT FROM s.actual_units
            THEN list_count(list_filter(range(1,1942),lambda n:
                list_extract(r.expected_units,n) IS DISTINCT FROM list_extract(s.actual_units,n)))
            ELSE 0 END AS mismatch_cells
    FROM raw_lists r JOIN series_stats s USING (item_id,store_id)
    CROSS JOIN raw_shape shape
    WHERE r.pair_rows=1 AND NULLIF(TRIM(r.item_id),'') IS NOT NULL
      AND NULLIF(TRIM(r.store_id),'') IS NOT NULL
      AND shape.day_columns=1941 AND shape.sequence_errors=0
      AND len(r.expected_units)=1941 AND s.row_count=1941
      AND s.covered_days=1941 AND s.invalid_day_rows=0 AND s.missing_core_rows=0
), comparison_totals AS (
    SELECT COUNT(*)*1941 AS compared_cells,
        COUNT(*) FILTER (WHERE mismatched_series) AS mismatch_series,
        COALESCE(SUM(mismatch_cells),0) AS mismatch_cells FROM comparisons
), checks AS (
    SELECT 1 AS check_order,'raw_series_rows' AS check_name,series_rows::VARCHAR AS actual,'30490' AS expected FROM raw_totals
    UNION ALL SELECT 2,'raw_day_columns',day_columns::VARCHAR,'1941' FROM raw_shape
    UNION ALL SELECT 3,'raw_day_sequence_errors',sequence_errors::VARCHAR,'0' FROM raw_shape
    UNION ALL SELECT 4,'raw_key_error_rows',key_error_rows::VARCHAR,'0' FROM raw_totals
    UNION ALL SELECT 5,'staging_rows',staging_rows::VARCHAR,'59181090' FROM staging_totals
    UNION ALL SELECT 6,'staging_series_count',series_count::VARCHAR,'30490' FROM staging_totals
    UNION ALL SELECT 7,'missing_core_rows',missing_core_rows::VARCHAR,'0' FROM staging_totals
    UNION ALL SELECT 8,'invalid_day_rows',invalid_day_rows::VARCHAR,'0' FROM staging_totals
    UNION ALL SELECT 9,'series_row_count_errors',row_count_errors::VARCHAR,'0' FROM staging_totals
    UNION ALL SELECT 10,'series_day_coverage_errors',coverage_errors::VARCHAR,'0' FROM staging_totals
    UNION ALL SELECT 11,'raw_only_series',COUNT(*)::VARCHAR,'0' FROM raw_only
    UNION ALL SELECT 12,'staging_only_series',COUNT(*)::VARCHAR,'0' FROM staging_only
    UNION ALL SELECT 13,'compared_cells',compared_cells::VARCHAR,'59181090' FROM comparison_totals
    UNION ALL SELECT 14,'value_mismatch_series',mismatch_series::VARCHAR,'0' FROM comparison_totals
    UNION ALL SELECT 15,'value_mismatch_cells',mismatch_cells::VARCHAR,'0' FROM comparison_totals
)
SELECT check_order,check_name,actual,expected,
    CASE WHEN check_order IN (14,15) AND EXISTS (
             SELECT 1 FROM checks prerequisites
             WHERE prerequisites.check_order<=13
               AND prerequisites.actual IS DISTINCT FROM prerequisites.expected)
         THEN 'INCOMPLETE' WHEN actual=expected THEN 'PASS' ELSE 'FAIL' END AS status
FROM checks ORDER BY check_order;
