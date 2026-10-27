-- Purpose: measure daily-row and unit-weighted price coverage before estimating sales value.
-- Read-only. Match the exact item/store/source-week; no filling, interpolation or zero prices.
-- Checks 1-12 validate mechanics, 13-14 gate complete positive-sales value coverage,
-- and 15-23 are observed coverage metrics (INFO; undefined percentages are N/A).
WITH price_health AS MATERIALIZED (
    SELECT COUNT(*) AS row_count,
        COUNT(*)-COUNT(DISTINCT (store_id,item_id,wm_yr_wk)) AS key_errors,
        COUNT(*) FILTER (WHERE NULLIF(TRIM(store_id),'') IS NULL
            OR NULLIF(TRIM(item_id),'') IS NULL OR wm_yr_wk IS NULL OR wm_yr_wk<=0
            OR sell_price IS NULL OR NOT isfinite(sell_price) OR sell_price<=0) AS invalid_rows
    FROM stg.m5_prices
), calendar_health AS MATERIALIZED (
    SELECT COUNT(*)-COUNT(DISTINCT d) AS key_errors,
        COUNT(*) FILTER (WHERE NULLIF(TRIM(d),'') IS NULL OR wm_yr_wk IS NULL) AS missing_rows
    FROM core.m5_calendar
), guarded_prices AS MATERIALIZED (
    SELECT p.store_id,p.item_id,
        CASE WHEN h.key_errors=0 AND h.invalid_rows=0 THEN p.wm_yr_wk
             ELSE error('Price table has duplicate/blank keys or nonfinite/nonpositive/missing prices') END AS wm_yr_wk
    FROM stg.m5_prices p CROSS JOIN price_health h
), guarded_calendar AS MATERIALIZED (
    SELECT CASE WHEN h.key_errors=0 AND h.missing_rows=0 THEN c.d
             ELSE error('Calendar has duplicate/blank day keys or missing weeks') END AS d,c.wm_yr_wk
    FROM core.m5_calendar c CROSS JOIN calendar_health h
), base_by_store AS MATERIALIZED (
    SELECT store_id,COUNT(*) AS row_count,COALESCE(SUM(units),0) AS units,
        COUNT(*) FILTER (WHERE units=0) AS zero_rows
    FROM stg.m5_sales_daily GROUP BY store_id
), joined_by_store AS MATERIALIZED (
    SELECT s.store_id,COUNT(*) AS row_count,COALESCE(SUM(s.units),0) AS units,
        COUNT(*) FILTER (WHERE s.units=0) AS zero_rows,
        COUNT(*) FILTER (WHERE c.d IS NULL) AS missing_calendar_rows,
        COUNT(*) FILTER (WHERE NULLIF(TRIM(s.item_id),'') IS NULL
            OR NULLIF(TRIM(s.store_id),'') IS NULL OR s.units IS NULL OR s.units<0
            OR NOT COALESCE(regexp_full_match(s.d,'d_[1-9][0-9]*')
                AND TRY_CAST(SUBSTR(s.d,3) AS INTEGER) BETWEEN 1 AND 1941,false)) AS invalid_sales_rows,
        COUNT(*) FILTER (WHERE p.wm_yr_wk IS NOT NULL) AS priced_daily_rows,
        COUNT(*) FILTER (WHERE p.wm_yr_wk IS NULL) AS missing_price_daily_rows,
        COUNT(*) FILTER (WHERE p.wm_yr_wk IS NULL AND s.units=0) AS missing_price_zero_rows,
        COUNT(*) FILTER (WHERE s.units>0) AS positive_sales_rows,
        COUNT(*) FILTER (WHERE p.wm_yr_wk IS NOT NULL AND s.units>0) AS priced_positive_rows,
        COUNT(*) FILTER (WHERE p.wm_yr_wk IS NULL AND s.units>0) AS missing_price_positive_rows,
        COALESCE(SUM(s.units) FILTER (WHERE p.wm_yr_wk IS NULL AND s.units>0),0) AS missing_price_units,
        COALESCE(SUM(s.units) FILTER (WHERE p.wm_yr_wk IS NOT NULL),0) AS priced_units
    FROM stg.m5_sales_daily s
    LEFT JOIN guarded_calendar c ON s.d=c.d
    LEFT JOIN guarded_prices p
        ON s.item_id=p.item_id AND s.store_id=p.store_id AND c.wm_yr_wk=p.wm_yr_wk
    GROUP BY s.store_id
), base_totals AS (
    SELECT COALESCE(SUM(row_count),0) AS row_count,COALESCE(SUM(units),0) AS units,
        COALESCE(SUM(zero_rows),0) AS zero_rows FROM base_by_store
), totals AS (
    SELECT COALESCE(SUM(row_count),0) AS row_count,COALESCE(SUM(units),0) AS units,
        COALESCE(SUM(zero_rows),0) AS zero_rows,
        COALESCE(SUM(missing_calendar_rows),0) AS missing_calendar_rows,
        COALESCE(SUM(invalid_sales_rows),0) AS invalid_sales_rows,
        COALESCE(SUM(priced_daily_rows),0) AS priced_daily_rows,
        COALESCE(SUM(missing_price_daily_rows),0) AS missing_price_daily_rows,
        COALESCE(SUM(missing_price_zero_rows),0) AS missing_price_zero_rows,
        COALESCE(SUM(positive_sales_rows),0) AS positive_sales_rows,
        COALESCE(SUM(priced_positive_rows),0) AS priced_positive_rows,
        COALESCE(SUM(missing_price_positive_rows),0) AS missing_price_positive_rows,
        COALESCE(SUM(missing_price_units),0) AS missing_price_units,
        COALESCE(SUM(priced_units),0) AS priced_units
    FROM joined_by_store
), store_errors AS (
    SELECT COUNT(*) AS error_count
    FROM base_by_store b FULL OUTER JOIN joined_by_store j ON b.store_id=j.store_id
    WHERE b.store_id IS NULL OR j.store_id IS NULL OR b.row_count IS DISTINCT FROM j.row_count
       OR b.units IS DISTINCT FROM j.units OR b.zero_rows IS DISTINCT FROM j.zero_rows
), checks AS (
    SELECT 1 AS check_order,'price_rows' AS check_name,row_count::VARCHAR AS actual,'6841121' AS expected FROM price_health
    UNION ALL SELECT 2,'base_rows',row_count::VARCHAR,'59181090' FROM base_totals
    UNION ALL SELECT 3,'joined_rows',row_count::VARCHAR,'59181090' FROM totals
    UNION ALL SELECT 4,'row_count_difference',(t.row_count-b.row_count)::VARCHAR,'0' FROM base_totals b CROSS JOIN totals t
    UNION ALL SELECT 5,'base_units',units::VARCHAR,'66927173' FROM base_totals
    UNION ALL SELECT 6,'joined_units',units::VARCHAR,'66927173' FROM totals
    UNION ALL SELECT 7,'units_difference',(t.units-b.units)::VARCHAR,'0' FROM base_totals b CROSS JOIN totals t
    UNION ALL SELECT 8,'base_zero_rows',zero_rows::VARCHAR,'40241819' FROM base_totals
    UNION ALL SELECT 9,'joined_zero_rows',zero_rows::VARCHAR,'40241819' FROM totals
    UNION ALL SELECT 10,'missing_calendar_rows',missing_calendar_rows::VARCHAR,'0' FROM totals
    UNION ALL SELECT 11,'invalid_sales_rows',invalid_sales_rows::VARCHAR,'0' FROM totals
    UNION ALL SELECT 12,'store_control_mismatches',error_count::VARCHAR,'0' FROM store_errors
    UNION ALL SELECT 13,'missing_price_positive_rows',missing_price_positive_rows::VARCHAR,'0' FROM totals
    UNION ALL SELECT 14,'missing_price_units',missing_price_units::VARCHAR,'0' FROM totals
    UNION ALL SELECT 15,'priced_daily_rows',priced_daily_rows::VARCHAR,'observed' FROM totals
    UNION ALL SELECT 16,'missing_price_daily_rows',missing_price_daily_rows::VARCHAR,'observed' FROM totals
    UNION ALL SELECT 17,'missing_price_zero_rows',missing_price_zero_rows::VARCHAR,'observed' FROM totals
    UNION ALL SELECT 18,'positive_sales_rows',positive_sales_rows::VARCHAR,'observed' FROM totals
    UNION ALL SELECT 19,'priced_positive_rows',priced_positive_rows::VARCHAR,'observed' FROM totals
    UNION ALL SELECT 20,'priced_units',priced_units::VARCHAR,'observed' FROM totals
    UNION ALL SELECT 21,'daily_row_coverage_pct',CAST(ROUND(100.0*priced_daily_rows/NULLIF(row_count,0),4) AS DECIMAL(9,4))::VARCHAR,'observed' FROM totals
    UNION ALL SELECT 22,'positive_row_coverage_pct',CAST(ROUND(100.0*priced_positive_rows/NULLIF(positive_sales_rows,0),4) AS DECIMAL(9,4))::VARCHAR,'observed' FROM totals
    UNION ALL SELECT 23,'units_coverage_pct',CAST(ROUND(100.0*priced_units/NULLIF(units,0),4) AS DECIMAL(9,4))::VARCHAR,'observed' FROM totals
)
SELECT check_order,check_name,actual,expected,
    CASE WHEN check_order>=13 AND EXISTS (
            SELECT 1 FROM checks prerequisites WHERE prerequisites.check_order<=12
                AND prerequisites.actual IS DISTINCT FROM prerequisites.expected) THEN 'INCOMPLETE'
         WHEN check_order>=15 AND actual IS NULL THEN 'N/A'
         WHEN check_order>=15 THEN 'INFO'
         WHEN actual=expected THEN 'PASS' ELSE 'FAIL' END AS status
FROM checks ORDER BY check_order;
