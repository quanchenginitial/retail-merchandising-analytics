-- Purpose: measure product-unit concentration before assigning any ABC labels.
-- Read-only. Fixed 2016-01-26..2016-04-24 inclusive; all 10 stores combined per SKU.
-- Top N includes positive-unit SKUs only; SKU-share denominator includes zero-sales SKUs.
-- Segments overlap: do not sum their counts/units. Units, not monetary value, drive ranking.
-- Thresholds use exact integer comparisons and include the first SKU reaching/crossing them.
-- Equal units are ordered by item_id; this is a deterministic tie-break, not a business distinction.
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
    SELECT f.item_id,f.store_id,f.d,f."date",f.units,
        CAST(date_diff('day',p.start_date,f."date")+1 AS INTEGER) AS window_day
    FROM mart.m5_sales_daily f CROSS JOIN parameters p
    WHERE f."date" BETWEEN p.start_date AND p.end_date
), by_series AS MATERIALIZED (
    SELECT item_id,store_id,COUNT(*) AS daily_rows,
        bit_count(bitstring_agg(window_day,1,90)) AS covered_days,SUM(units) AS units,
        COUNT(*) FILTER (WHERE NULLIF(TRIM(item_id),'') IS NULL OR NULLIF(TRIM(store_id),'') IS NULL
            OR units IS NULL OR units<0 OR typeof(units)<>'INTEGER'
            OR d IS DISTINCT FROM 'd_'||CAST(date_diff('day',DATE '2011-01-29',"date")+1 AS VARCHAR)
        ) AS invalid_rows
    FROM selected GROUP BY item_id,store_id
), base_totals AS (
    SELECT COUNT(*) AS series,COUNT(DISTINCT item_id) AS sku_count,
        COALESCE(SUM(daily_rows),0) AS daily_rows,COALESCE(SUM(units),0) AS units,
        COALESCE(SUM(invalid_rows),0) AS invalid_rows,
        COUNT(*) FILTER (WHERE daily_rows<>90 OR covered_days IS DISTINCT FROM 90) AS key_errors
    FROM by_series
), joined AS MATERIALIZED (
    SELECT b.*,p.cat_id,p.dept_id,s.store_id AS matched_store_id
    FROM by_series b LEFT JOIN core.m5_product p ON b.item_id=p.item_id
    LEFT JOIN core.m5_store s ON b.store_id=s.store_id
), join_totals AS (
    SELECT COUNT(*) AS series,SUM(daily_rows) AS daily_rows,SUM(units) AS units,
        COUNT(*) FILTER (WHERE cat_id IS NULL OR dept_id IS NULL OR matched_store_id IS NULL) AS missing_dimensions
    FROM joined
), product_totals AS MATERIALIZED (
    SELECT item_id,cat_id,dept_id,SUM(units) AS units FROM joined GROUP BY item_id,cat_id,dept_id
), ranked AS MATERIALIZED (
    SELECT *,ROW_NUMBER() OVER (ORDER BY units DESC,item_id ASC) AS sku_rank,
        SUM(units) OVER (ORDER BY units DESC,item_id ASC
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS cumulative_units
    FROM product_totals WHERE units>0
), thresholds AS (
    SELECT MIN(sku_rank) FILTER (WHERE r.cumulative_units*100>=b.units*80) AS reach80_rank,
        MIN(sku_rank) FILTER (WHERE r.cumulative_units*100>=b.units*95) AS reach95_rank
    FROM ranked r CROSS JOIN base_totals b
), health AS (
    SELECT ph.rows=cfg.expected_items AND ph.items=cfg.expected_items AND ph.invalid_rows=0
        AND sh.rows=cfg.expected_stores AND sh.stores=cfg.expected_stores AND sh.invalid_rows=0
        AND b.series=cfg.expected_items*cfg.expected_stores AND b.sku_count=cfg.expected_items
        AND b.daily_rows=cfg.expected_items*cfg.expected_stores*90
        AND b.key_errors=0 AND b.invalid_rows=0 AND j.missing_dimensions=0
        AND b.series=j.series AND b.daily_rows=j.daily_rows AND b.units=j.units
        AND (SELECT COUNT(*) FROM product_totals)=cfg.expected_items
        AND (SELECT SUM(units) FROM product_totals)=b.units AS passed
    FROM base_totals b CROSS JOIN join_totals j CROSS JOIN product_health ph
    CROSS JOIN store_health sh CROSS JOIN parameters cfg
), definitions AS (
    SELECT 1 AS display_order,'TOP_10' AS segment,'PREFIX' AS kind,10::BIGINT AS cutoff_rank
    UNION ALL SELECT 2,'TOP_50','PREFIX',50
    UNION ALL SELECT 3,'TOP_100','PREFIX',100
    UNION ALL SELECT 4,'REACH_80_PCT','PREFIX',reach80_rank FROM thresholds
    UNION ALL SELECT 5,'REACH_95_PCT','PREFIX',reach95_rank FROM thresholds
    UNION ALL SELECT 6,'ALL_POSITIVE','POSITIVE',NULL
    UNION ALL SELECT 7,'ZERO_SALES','ZERO',NULL
    UNION ALL SELECT 8,'ALL_PRODUCTS','ALL',NULL
), products_with_rank AS (
    SELECT p.*,r.sku_rank FROM product_totals p LEFT JOIN ranked r USING (item_id)
), segments AS (
    SELECT s.display_order,s.segment,COUNT(p.item_id) AS sku_count,COALESCE(SUM(p.units),0) AS units
    FROM definitions s LEFT JOIN products_with_rank p ON
        CASE s.kind WHEN 'PREFIX' THEN p.sku_rank<=s.cutoff_rank WHEN 'POSITIVE' THEN p.units>0
            WHEN 'ZERO' THEN p.units=0 WHEN 'ALL' THEN true END
    GROUP BY s.display_order,s.segment
), observations AS (
    SELECT s.*,s.segment IN ('REACH_80_PCT','REACH_95_PCT') AND b.units=0 AS undefined_threshold
    FROM segments s CROSS JOIN base_totals b
)
-- REPORT: preflight also inspects the CTE product totals/ranks for exact source comparisons.
SELECT o.segment,CASE WHEN undefined_threshold THEN NULL ELSE o.sku_count END AS sku_count,
    CASE WHEN undefined_threshold THEN NULL ELSE
        CAST(ROUND(100.0*o.sku_count/NULLIF(b.sku_count,0),4) AS DECIMAL(9,4)) END AS sku_share_pct,
    CASE WHEN undefined_threshold THEN NULL ELSE o.units END AS units,
    CAST(ROUND(100.0*o.units/NULLIF(b.units,0),4) AS DECIMAL(9,4)) AS unit_share_pct,
    CASE WHEN NOT COALESCE(h.passed,false)
              THEN error('Product concentration blocked: check accepted units, complete 90-day keys and product/store mappings')
         WHEN undefined_threshold THEN 'N/A' ELSE 'PASS' END AS check_status
FROM observations o CROSS JOIN base_totals b CROSS JOIN health h
ORDER BY o.display_order;
