-- Purpose: locate department contributions within each accepted category over the same 90-day window.
-- Read-only. Requires accepted SQL17 fact and dimensions. This is not a forecast or ABC result.
-- Inclusive dates: 2016-01-26..2016-04-24 (d_1824..d_1913); excludes final forecast holdout.
-- SKU count includes observed source products with zero sales, not proven active/listed stock.
-- Global shares use all categories; within_category_value_share_pct uses only the parent category.
-- TOTAL has no parent category, so its within-category share is NULL (not applicable).
-- Source department codes are anonymous; do not invent descriptive department names.
WITH parameters AS (
    SELECT DATE '2016-01-26' AS start_date,DATE '2016-04-24' AS end_date,
        3049 AS expected_items,10 AS expected_stores
), department_mapping(dept_id,cat_id) AS (
    VALUES ('FOODS_1','FOODS'),('FOODS_2','FOODS'),('FOODS_3','FOODS'),
        ('HOBBIES_1','HOBBIES'),('HOBBIES_2','HOBBIES'),
        ('HOUSEHOLD_1','HOUSEHOLD'),('HOUSEHOLD_2','HOUSEHOLD')
), product_health AS (
    SELECT COUNT(*) AS rows,COUNT(DISTINCT p.item_id) AS items,
        COUNT(*) FILTER (WHERE NULLIF(TRIM(p.item_id),'') IS NULL OR m.dept_id IS NULL) AS invalid_rows
    FROM core.m5_product p LEFT JOIN department_mapping m ON p.dept_id=m.dept_id AND p.cat_id=m.cat_id
), store_health AS (
    SELECT COUNT(*) AS rows,COUNT(DISTINCT store_id) AS stores,
        COUNT(*) FILTER (WHERE NULLIF(TRIM(store_id),'') IS NULL) AS invalid_rows
    FROM core.m5_store
), selected AS NOT MATERIALIZED (
    SELECT f.*,CAST(date_diff('day',p.start_date,f."date")+1 AS INTEGER) AS window_day
    FROM mart.m5_sales_daily f CROSS JOIN parameters p
    WHERE f."date" BETWEEN p.start_date AND p.end_date
), by_series AS MATERIALIZED (
    SELECT item_id,store_id,COUNT(*) AS daily_rows,
        bit_count(bitstring_agg(window_day,1,90)) AS covered_days,
        SUM(units) AS units,SUM(estimated_sales_value) AS estimated_sales_value,
        COUNT(*) FILTER (WHERE sell_price IS NOT NULL) AS priced_daily_rows,
        COUNT(*) FILTER (WHERE NULLIF(TRIM(item_id),'') IS NULL OR NULLIF(TRIM(store_id),'') IS NULL
            OR units IS NULL OR units<0 OR estimated_sales_value IS NULL
            OR has_price IS DISTINCT FROM (sell_price IS NOT NULL)
            OR (sell_price IS NOT NULL AND (NOT isfinite(sell_price) OR sell_price<=0))
            OR (units>0 AND sell_price IS NULL)
            OR d IS DISTINCT FROM 'd_'||CAST(date_diff('day',DATE '2011-01-29',"date")+1 AS VARCHAR)
            OR estimated_sales_value IS DISTINCT FROM CASE WHEN units=0 THEN CAST(0 AS DECIMAL(28,2))
                WHEN units>0 AND sell_price IS NOT NULL
                THEN CAST(CAST(units AS DECIMAL(20,0))*sell_price AS DECIMAL(28,2)) ELSE NULL END
        ) AS invalid_rows
    FROM selected GROUP BY item_id,store_id
), joined AS MATERIALIZED (
    SELECT b.*,p.cat_id,p.dept_id,s.store_id AS matched_store_id
    FROM by_series b LEFT JOIN core.m5_product p ON b.item_id=p.item_id
    LEFT JOIN core.m5_store s ON b.store_id=s.store_id
), base_totals AS (
    SELECT COUNT(*) AS series,COUNT(DISTINCT item_id) AS sku_count,
        COALESCE(SUM(daily_rows),0) AS daily_rows,COALESCE(SUM(units),0) AS units,
        COALESCE(SUM(estimated_sales_value),0) AS estimated_sales_value,
        COALESCE(SUM(priced_daily_rows),0) AS priced_daily_rows,
        COALESCE(SUM(invalid_rows),0) AS invalid_rows,
        COUNT(*) FILTER (WHERE daily_rows<>90 OR covered_days IS DISTINCT FROM 90) AS key_errors
    FROM by_series
), categories AS MATERIALIZED (
    SELECT cat_id AS category,COUNT(DISTINCT item_id) AS sku_count,
        SUM(daily_rows) AS daily_rows,SUM(units) AS units,
        SUM(estimated_sales_value) AS estimated_sales_value,SUM(priced_daily_rows) AS priced_daily_rows
    FROM joined GROUP BY cat_id
), departments AS MATERIALIZED (
    SELECT cat_id AS category,dept_id AS department,COUNT(DISTINCT item_id) AS sku_count,
        SUM(daily_rows) AS daily_rows,SUM(units) AS units,
        SUM(estimated_sales_value) AS estimated_sales_value
    FROM joined GROUP BY cat_id,dept_id
), department_category_totals AS (
    SELECT category,SUM(sku_count) AS sku_count,SUM(daily_rows) AS daily_rows,
        SUM(units) AS units,SUM(estimated_sales_value) AS estimated_sales_value
    FROM departments GROUP BY category
), hierarchy_errors AS (
    SELECT COUNT(*) AS errors FROM categories c FULL OUTER JOIN department_category_totals d USING (category)
    WHERE c.category IS NULL OR d.category IS NULL OR c.sku_count IS DISTINCT FROM d.sku_count
       OR c.daily_rows IS DISTINCT FROM d.daily_rows OR c.units IS DISTINCT FROM d.units
       OR c.estimated_sales_value IS DISTINCT FROM d.estimated_sales_value
), join_totals AS (
    SELECT COUNT(*) AS series,SUM(daily_rows) AS daily_rows,SUM(units) AS units,
        SUM(estimated_sales_value) AS estimated_sales_value,
        COUNT(*) FILTER (WHERE cat_id IS NULL OR dept_id IS NULL OR matched_store_id IS NULL) AS missing_dimensions
    FROM joined
), health AS (
    SELECT ph.rows=cfg.expected_items AND ph.items=cfg.expected_items AND ph.invalid_rows=0
        AND sh.rows=cfg.expected_stores AND sh.stores=cfg.expected_stores AND sh.invalid_rows=0
        AND b.series=cfg.expected_items*cfg.expected_stores AND b.sku_count=cfg.expected_items
        AND b.daily_rows=cfg.expected_items*cfg.expected_stores*90
        AND b.key_errors=0 AND b.invalid_rows=0 AND j.missing_dimensions=0
        AND b.series=j.series AND b.daily_rows=j.daily_rows AND b.units=j.units
        AND b.estimated_sales_value=j.estimated_sales_value
        AND (SELECT COUNT(*) FROM categories)=3 AND (SELECT COUNT(*) FROM departments)=7
        AND (SELECT errors FROM hierarchy_errors)=0 AS passed
    FROM base_totals b CROSS JOIN join_totals j CROSS JOIN product_health ph
    CROSS JOIN store_health sh CROSS JOIN parameters cfg
), report_rows AS (
    SELECT d.category,d.department,d.sku_count,d.units,d.estimated_sales_value,
        c.estimated_sales_value AS category_value,0 AS total_order
    FROM departments d JOIN categories c ON d.category=c.category
    UNION ALL
    SELECT 'TOTAL','TOTAL',sku_count,units,estimated_sales_value,NULL,1 FROM base_totals
)
SELECT r.category,r.department,r.sku_count,r.units,
    CAST(ROUND(100.0*r.units/NULLIF(b.units,0),4) AS DECIMAL(9,4)) AS unit_share_pct,
    r.estimated_sales_value AS estimated_sales_value_usd,
    CAST(ROUND(100.0*r.estimated_sales_value/NULLIF(b.estimated_sales_value,0),4) AS DECIMAL(9,4)) AS value_share_pct,
    CAST(ROUND(100.0*r.estimated_sales_value/NULLIF(r.category_value,0),4) AS DECIMAL(9,4)) AS within_category_value_share_pct,
    CASE WHEN COALESCE(h.passed,false) THEN 'PASS'
         ELSE error('Department report blocked: check accepted fact, 90-day keys, source hierarchy, prices and value policy')
    END AS check_status
FROM report_rows r CROSS JOIN base_totals b CROSS JOIN health h
ORDER BY r.total_order,r.category_value DESC,r.category,r.estimated_sales_value DESC,r.department;
