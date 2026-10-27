-- Purpose: execute all three daily-sales dimension joins and verify complete,
-- one-to-one matches without losing or multiplying observations or units.
-- Read-only: no table/view creation, price join, or sales-value calculation.
-- Accepted source sales and dimension semantics are prerequisites.
WITH product_health AS MATERIALIZED (
    SELECT COUNT(*) AS row_count,COUNT(*)-COUNT(DISTINCT item_id) AS key_errors,
        COUNT(*) FILTER (WHERE NULLIF(TRIM(item_id),'') IS NULL
            OR NULLIF(TRIM(dept_id),'') IS NULL OR NULLIF(TRIM(cat_id),'') IS NULL) AS missing_rows
    FROM core.m5_product
), store_health AS MATERIALIZED (
    SELECT COUNT(*) AS row_count,COUNT(*)-COUNT(DISTINCT store_id) AS key_errors,
        COUNT(*) FILTER (WHERE NULLIF(TRIM(store_id),'') IS NULL
            OR NULLIF(TRIM(state_id),'') IS NULL) AS missing_rows
    FROM core.m5_store
), calendar_health AS MATERIALIZED (
    SELECT COUNT(*) AS row_count,COUNT(*)-COUNT(DISTINCT d) AS key_errors,
        COUNT(*) FILTER (WHERE NULLIF(TRIM(d),'') IS NULL OR "date" IS NULL
            OR wm_yr_wk IS NULL OR day_number IS NULL) AS missing_rows
    FROM core.m5_calendar
), guarded_product AS MATERIALIZED (
    SELECT CASE WHEN h.key_errors=0 AND h.missing_rows=0 THEN p.item_id
           ELSE error('Product dimension has duplicate/blank keys or missing required attributes') END AS item_id,
           p.dept_id,p.cat_id
    FROM core.m5_product p CROSS JOIN product_health h
), guarded_store AS MATERIALIZED (
    SELECT CASE WHEN h.key_errors=0 AND h.missing_rows=0 THEN s.store_id
           ELSE error('Store dimension has duplicate/blank keys or missing required attributes') END AS store_id,
           s.state_id
    FROM core.m5_store s CROSS JOIN store_health h
), guarded_calendar AS MATERIALIZED (
    SELECT CASE WHEN h.key_errors=0 AND h.missing_rows=0 THEN c.d
           ELSE error('Calendar dimension has duplicate/blank keys or missing required attributes') END AS d,
           c."date",c.wm_yr_wk,c.day_number
    FROM core.m5_calendar c CROSS JOIN calendar_health h
), base_by_store AS MATERIALIZED (
    SELECT store_id,COUNT(*) AS row_count,COALESCE(SUM(units),0) AS units,
        COUNT(*) FILTER (WHERE units=0) AS zero_rows,
        COUNT(*) FILTER (WHERE NULLIF(TRIM(item_id),'') IS NULL
            OR NULLIF(TRIM(store_id),'') IS NULL OR NULLIF(TRIM(d),'') IS NULL
            OR units IS NULL) AS missing_core_rows,
        COUNT(*) FILTER (WHERE units<0) AS negative_units_rows
    FROM stg.m5_sales_daily GROUP BY store_id
), joined_by_store AS MATERIALIZED (
    SELECT s.store_id,COUNT(*) AS row_count,COALESCE(SUM(s.units),0) AS units,
        COUNT(*) FILTER (WHERE s.units=0) AS zero_rows,
        COUNT(*) FILTER (WHERE p.item_id IS NULL) AS missing_product_rows,
        COUNT(*) FILTER (WHERE t.store_id IS NULL) AS missing_store_rows,
        COUNT(*) FILTER (WHERE c.d IS NULL) AS missing_calendar_rows,
        COUNT(*) FILTER (WHERE c.d IS NOT NULL AND NOT COALESCE(
            regexp_full_match(s.d,'d_[1-9][0-9]*') AND c.day_number BETWEEN 1 AND 1941
            AND c.day_number=TRY_CAST(SUBSTR(s.d,3) AS INTEGER)
            AND c.day_number=date_diff('day',DATE '2011-01-29',c."date")+1,false)) AS invalid_joined_day_rows,
        MIN(c."date") AS first_sales_date,MAX(c."date") AS last_sales_date
    FROM stg.m5_sales_daily s
    LEFT JOIN guarded_product p ON s.item_id=p.item_id
    LEFT JOIN guarded_store t ON s.store_id=t.store_id
    LEFT JOIN guarded_calendar c ON s.d=c.d
    GROUP BY s.store_id
), base_totals AS (
    SELECT COALESCE(SUM(row_count),0) AS row_count,COALESCE(SUM(units),0) AS units,
        COALESCE(SUM(zero_rows),0) AS zero_rows,
        COALESCE(SUM(missing_core_rows),0) AS missing_core_rows,
        COALESCE(SUM(negative_units_rows),0) AS negative_units_rows
    FROM base_by_store
), joined_totals AS (
    SELECT COALESCE(SUM(row_count),0) AS row_count,COALESCE(SUM(units),0) AS units,
        COALESCE(SUM(zero_rows),0) AS zero_rows,
        COALESCE(SUM(missing_product_rows),0) AS missing_product_rows,
        COALESCE(SUM(missing_store_rows),0) AS missing_store_rows,
        COALESCE(SUM(missing_calendar_rows),0) AS missing_calendar_rows,
        COALESCE(SUM(invalid_joined_day_rows),0) AS invalid_joined_day_rows,
        MIN(first_sales_date) AS first_sales_date,MAX(last_sales_date) AS last_sales_date
    FROM joined_by_store
), store_errors AS (
    SELECT COUNT(*) AS error_count
    FROM base_by_store b FULL OUTER JOIN joined_by_store j ON b.store_id=j.store_id
    WHERE b.store_id IS NULL OR j.store_id IS NULL
       OR b.row_count IS DISTINCT FROM j.row_count OR b.units IS DISTINCT FROM j.units
       OR b.zero_rows IS DISTINCT FROM j.zero_rows
), checks AS (
    SELECT 1 AS check_order,'product_rows' AS check_name,row_count::VARCHAR AS actual,'3049' AS expected FROM product_health
    UNION ALL SELECT 2,'store_rows',row_count::VARCHAR,'10' FROM store_health
    UNION ALL SELECT 3,'calendar_rows',row_count::VARCHAR,'1969' FROM calendar_health
    UNION ALL SELECT 4,'base_rows',row_count::VARCHAR,'59181090' FROM base_totals
    UNION ALL SELECT 5,'joined_rows',row_count::VARCHAR,'59181090' FROM joined_totals
    UNION ALL SELECT 6,'row_count_difference',(j.row_count-b.row_count)::VARCHAR,'0' FROM base_totals b CROSS JOIN joined_totals j
    UNION ALL SELECT 7,'base_units',units::VARCHAR,'66927173' FROM base_totals
    UNION ALL SELECT 8,'joined_units',units::VARCHAR,'66927173' FROM joined_totals
    UNION ALL SELECT 9,'units_difference',(j.units-b.units)::VARCHAR,'0' FROM base_totals b CROSS JOIN joined_totals j
    UNION ALL SELECT 10,'base_zero_rows',zero_rows::VARCHAR,'40241819' FROM base_totals
    UNION ALL SELECT 11,'joined_zero_rows',zero_rows::VARCHAR,'40241819' FROM joined_totals
    UNION ALL SELECT 12,'missing_product_rows',missing_product_rows::VARCHAR,'0' FROM joined_totals
    UNION ALL SELECT 13,'missing_store_rows',missing_store_rows::VARCHAR,'0' FROM joined_totals
    UNION ALL SELECT 14,'missing_calendar_rows',missing_calendar_rows::VARCHAR,'0' FROM joined_totals
    UNION ALL SELECT 15,'source_missing_core_rows',missing_core_rows::VARCHAR,'0' FROM base_totals
    UNION ALL SELECT 16,'source_negative_units_rows',negative_units_rows::VARCHAR,'0' FROM base_totals
    UNION ALL SELECT 17,'invalid_joined_day_rows',invalid_joined_day_rows::VARCHAR,'0' FROM joined_totals
    UNION ALL SELECT 18,'first_sales_date',first_sales_date::VARCHAR,'2011-01-29' FROM joined_totals
    UNION ALL SELECT 19,'last_sales_date',last_sales_date::VARCHAR,'2016-05-22' FROM joined_totals
    UNION ALL SELECT 20,'store_control_mismatches',error_count::VARCHAR,'0' FROM store_errors
)
SELECT check_order,check_name,actual,expected,
    CASE WHEN actual=expected THEN 'PASS' ELSE 'FAIL' END AS status
FROM checks ORDER BY check_order;
