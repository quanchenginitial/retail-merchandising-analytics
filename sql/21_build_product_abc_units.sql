-- Purpose: persist one mutually exclusive units-based ABC label per source product.

-- Fixed 2016-01-26..2016-04-24, all 10 stores combined. This is not value/profit ABC.

-- Positive units DESC, item_id ASC. The crossing SKU stays in the earlier band:

-- prior cumulative units <80% => A; otherwise <95% => B; remaining positives => C.

-- Zero-unit products are ZERO_SALES with NULL rank/cumulative units.

-- Run once; no existing table is overwritten. Rounded displayed percentages never decide membership.

CREATE SCHEMA IF NOT EXISTS mart;

CREATE TABLE mart.m5_product_abc_90d AS

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

), assignments AS MATERIALIZED (

    SELECT p.item_id,p.dept_id,p.cat_id,cfg.start_date AS window_start,cfg.end_date AS window_end,

        p.units,r.sku_rank,r.cumulative_units,

        CASE WHEN NOT COALESCE(h.passed,false)

                  THEN error('ABC build blocked: check accepted units, complete 90-day keys and product/store mappings')

             WHEN p.units=0 THEN 'ZERO_SALES'

             WHEN (r.cumulative_units-p.units)*100<b.units*80 THEN 'A'

             WHEN (r.cumulative_units-p.units)*100<b.units*95 THEN 'B'

             ELSE 'C' END AS abc_class

    FROM health h LEFT JOIN product_totals p ON true LEFT JOIN ranked r USING (item_id)

    CROSS JOIN base_totals b CROSS JOIN parameters cfg

)

SELECT item_id,dept_id,cat_id,window_start,window_end,units,sku_rank,cumulative_units,abc_class FROM assignments;



-- VALIDATION: if mart.m5_product_abc_90d exists, run only the query below.

-- Recompute expected rows from the accepted daily fact, not from the ABC table.

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

), assignments AS MATERIALIZED (

    SELECT p.item_id,p.dept_id,p.cat_id,cfg.start_date AS window_start,cfg.end_date AS window_end,

        p.units,r.sku_rank,r.cumulative_units,

        CASE WHEN NOT COALESCE(h.passed,false)

                  THEN error('ABC build blocked: check accepted units, complete 90-day keys and product/store mappings')

             WHEN p.units=0 THEN 'ZERO_SALES'

             WHEN (r.cumulative_units-p.units)*100<b.units*80 THEN 'A'

             WHEN (r.cumulative_units-p.units)*100<b.units*95 THEN 'B'

             ELSE 'C' END AS abc_class

    FROM health h LEFT JOIN product_totals p ON true LEFT JOIN ranked r USING (item_id)

    CROSS JOIN base_totals b CROSS JOIN parameters cfg

), expected_schema(column_name,data_type,ordinal_position) AS (

    VALUES ('item_id','VARCHAR',1),('dept_id','VARCHAR',2),('cat_id','VARCHAR',3),

        ('window_start','DATE',4),('window_end','DATE',5),('units','HUGEINT',6),

        ('sku_rank','BIGINT',7),('cumulative_units','HUGEINT',8),('abc_class','VARCHAR',9)

), actual_schema AS (

    SELECT column_name,data_type,ordinal_position FROM information_schema.columns

    WHERE table_catalog=current_database() AND table_schema='mart' AND table_name='m5_product_abc_90d'

), schema_errors AS (

    SELECT COUNT(*) AS errors FROM expected_schema e FULL OUTER JOIN actual_schema a USING (column_name)

    WHERE e.column_name IS NULL OR a.column_name IS NULL OR e.data_type IS DISTINCT FROM a.data_type

        OR e.ordinal_position IS DISTINCT FROM a.ordinal_position

), expected_only AS (

    SELECT item_id,dept_id,cat_id,window_start,window_end,units,sku_rank,cumulative_units,abc_class FROM assignments

    EXCEPT ALL SELECT item_id,dept_id,cat_id,window_start,window_end,units,sku_rank,cumulative_units,abc_class FROM mart.m5_product_abc_90d

), actual_only AS (

    SELECT item_id,dept_id,cat_id,window_start,window_end,units,sku_rank,cumulative_units,abc_class FROM mart.m5_product_abc_90d

    EXCEPT ALL SELECT item_id,dept_id,cat_id,window_start,window_end,units,sku_rank,cumulative_units,abc_class FROM assignments

), actual_health AS (

    SELECT COUNT(*) AS rows,COUNT(DISTINCT item_id) AS items,

        COUNT(*) FILTER (WHERE NULLIF(TRIM(item_id),'') IS NULL) AS missing_items,

        COALESCE(SUM(units),0) AS units

    FROM mart.m5_product_abc_90d

), validation AS (

    SELECT COALESCE(h.passed,false) AND a.rows=cfg.expected_items AND a.items=cfg.expected_items

        AND a.missing_items=0 AND a.units=b.units AND e.errors=0

        AND (SELECT COUNT(*) FROM actual_schema)=9

        AND (SELECT COUNT(*) FROM expected_only)=0 AND (SELECT COUNT(*) FROM actual_only)=0 AS passed

    FROM actual_health a CROSS JOIN parameters cfg CROSS JOIN schema_errors e

    CROSS JOIN health h CROSS JOIN base_totals b

), class_order(display_order,abc_class) AS (

    VALUES (1,'A'),(2,'B'),(3,'C'),(4,'ZERO_SALES')

), summaries AS (

    SELECT c.display_order,c.abc_class,COUNT(a.item_id) AS sku_count,

        COALESCE(SUM(a.units),0) AS units,MIN(a.sku_rank) AS first_rank,MAX(a.sku_rank) AS last_rank

    FROM class_order c LEFT JOIN mart.m5_product_abc_90d a USING (abc_class)

    GROUP BY c.display_order,c.abc_class

    UNION ALL

    SELECT 5,'TOTAL',COUNT(*),COALESCE(SUM(units),0),MIN(sku_rank),MAX(sku_rank)

    FROM mart.m5_product_abc_90d

)

SELECT s.abc_class,s.sku_count,

    CAST(ROUND(100.0*s.sku_count/NULLIF(a.items,0),4) AS DECIMAL(9,4)) AS sku_share_pct,

    s.units,CAST(ROUND(100.0*s.units/NULLIF(a.units,0),4) AS DECIMAL(9,4)) AS unit_share_pct,

    s.first_rank,s.last_rank,

    CASE WHEN COALESCE(v.passed,false) THEN 'PASS'

         ELSE error('ABC validation failed: schema, keys or stored rows differ from the independently recomputed daily-fact result')

    END AS check_status

FROM summaries s CROSS JOIN actual_health a CROSS JOIN validation v

ORDER BY s.display_order;

