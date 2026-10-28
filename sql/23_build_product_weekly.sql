-- Purpose: prepare equal-length weekly product sales for later XYZ variability analysis.
-- Full source retail weeks inside the ABC window: 11601..11612, Saturday-Friday.
-- 2016-01-30..2016-04-22 (84 days); ABC remains 2016-01-26..2016-04-24 (90 days).
-- All 10 stores pooled; keep observed zero-sales weeks, never fill missing records with zero.
-- One row per item/week, 36,588 rows, 8 columns; no XYZ labels yet.
-- Run the whole file once. Existing tables are never overwritten.
CREATE SCHEMA IF NOT EXISTS mart;
CREATE TABLE mart.m5_product_weekly_12w AS
WITH parameters AS (
    SELECT 3049 AS expected_items,10 AS expected_stores,12 AS expected_weeks,84 AS expected_days,
        DATE '2016-01-26' AS abc_start,DATE '2016-04-24' AS abc_end,
        DATE '2016-01-30' AS start_date,DATE '2016-04-22' AS end_date
), department_mapping(dept_id,cat_id) AS (
    VALUES ('FOODS_1','FOODS'),('FOODS_2','FOODS'),('FOODS_3','FOODS'),
        ('HOUSEHOLD_1','HOUSEHOLD'),('HOUSEHOLD_2','HOUSEHOLD'),('HOBBIES_1','HOBBIES'),('HOBBIES_2','HOBBIES')
), product_health AS (
    SELECT COUNT(*) AS rows,COUNT(DISTINCT p.item_id) AS items,
        COUNT(*) FILTER (WHERE NULLIF(TRIM(p.item_id),'') IS NULL OR m.dept_id IS NULL) AS invalid_rows
    FROM core.m5_product p LEFT JOIN department_mapping m ON p.dept_id=m.dept_id AND p.cat_id=m.cat_id
), store_health AS (
    SELECT COUNT(*) AS rows,COUNT(DISTINCT store_id) AS stores,
        COUNT(*) FILTER (WHERE NULLIF(TRIM(store_id),'') IS NULL) AS invalid_rows FROM core.m5_store
), week_catalog AS MATERIALIZED (
    -- Group the complete calendar first, so clipped partial weeks cannot look complete.
    SELECT wm_yr_wk,MIN("date") AS week_start,MAX("date") AS week_end,COUNT(*) AS calendar_rows,
        COUNT(DISTINCT "date") AS distinct_dates,COUNT(DISTINCT d) AS distinct_days
    FROM core.m5_calendar GROUP BY wm_yr_wk
), selected_weeks AS MATERIALIZED (
    SELECT w.* FROM week_catalog w CROSS JOIN parameters cfg
    WHERE w.week_start>=cfg.abc_start AND w.week_end<=cfg.abc_end
), week_health AS (
    SELECT COUNT(*) AS weeks,MIN(week_start) AS first_date,MAX(week_end) AS last_date,
        COUNT(*) FILTER (WHERE calendar_rows<>7 OR distinct_dates<>7 OR distinct_days<>7
            OR date_diff('day',week_start,week_end)<>6 OR dayofweek(week_start)<>6 OR dayofweek(week_end)<>5
            OR wm_yr_wk IS DISTINCT FROM 11601+date_diff('day',cfg.start_date,week_start)//7) AS invalid_weeks
    FROM selected_weeks CROSS JOIN parameters cfg
), selected_calendar AS MATERIALIZED (
    SELECT c.d,c."date",c.wm_yr_wk FROM core.m5_calendar c JOIN selected_weeks w USING (wm_yr_wk)
), calendar_health AS (
    SELECT COUNT(*) AS rows,COUNT(DISTINCT d) AS day_keys,COUNT(DISTINCT "date") AS dates,
        COUNT(*) FILTER (WHERE d IS DISTINCT FROM 'd_'||CAST(date_diff('day',DATE '2011-01-29',"date")+1 AS VARCHAR)
            OR "date" IS NULL OR typeof("date")<>'DATE' OR typeof(wm_yr_wk)<>'INTEGER'
            OR wm_yr_wk IS DISTINCT FROM 11601+date_diff('day',cfg.start_date,"date")//7) AS invalid_rows
    FROM selected_calendar CROSS JOIN parameters cfg
), selected_fact AS MATERIALIZED (
    SELECT f.item_id,f.store_id,f.d,f."date",f.wm_yr_wk,f.units,
        CAST(date_diff('day',cfg.start_date,f."date")+1 AS INTEGER) AS window_day
    FROM mart.m5_sales_daily f CROSS JOIN parameters cfg
    WHERE f."date" BETWEEN cfg.start_date AND cfg.end_date
), by_series AS MATERIALIZED (
    SELECT item_id,store_id,COUNT(*) AS daily_rows,
        bit_count(bitstring_agg(window_day,1,84)) AS covered_days,SUM(units) AS units,
        COUNT(*) FILTER (WHERE NULLIF(TRIM(item_id),'') IS NULL OR NULLIF(TRIM(store_id),'') IS NULL
            OR units IS NULL OR units<0 OR typeof(units)<>'INTEGER' OR typeof("date")<>'DATE'
            OR d IS DISTINCT FROM 'd_'||CAST(date_diff('day',DATE '2011-01-29',"date")+1 AS VARCHAR)) AS invalid_rows
    FROM selected_fact GROUP BY item_id,store_id
), source_health AS (
    SELECT COUNT(*) AS series,COUNT(DISTINCT item_id) AS items,COUNT(DISTINCT store_id) AS stores,
        COALESCE(SUM(daily_rows),0) AS daily_rows,COALESCE(SUM(units),0) AS units,
        COALESCE(SUM(invalid_rows),0) AS invalid_rows,
        COUNT(*) FILTER (WHERE daily_rows<>84 OR covered_days IS DISTINCT FROM 84) AS key_errors
    FROM by_series
), joined AS MATERIALIZED (
    SELECT f.*,p.dept_id,p.cat_id,s.store_id AS matched_store,c.d AS calendar_day,c.wm_yr_wk AS calendar_week
    FROM selected_fact f LEFT JOIN core.m5_product p ON f.item_id=p.item_id
    LEFT JOIN core.m5_store s ON f.store_id=s.store_id
    LEFT JOIN selected_calendar c ON f.d=c.d AND f."date"=c."date" AND f.wm_yr_wk=c.wm_yr_wk
), join_health AS (
    SELECT COUNT(*) AS daily_rows,COALESCE(SUM(units),0) AS units,
        COUNT(*) FILTER (WHERE dept_id IS NULL OR cat_id IS NULL OR matched_store IS NULL OR calendar_day IS NULL) AS unmatched_rows
    FROM joined
), weekly_expected AS MATERIALIZED (
    SELECT item_id,dept_id,cat_id,calendar_week AS wm_yr_wk,
        MIN("date") AS week_start,MAX("date") AS week_end,SUM(units) AS units,COUNT(*) AS source_daily_rows
    FROM joined GROUP BY item_id,dept_id,cat_id,calendar_week
), weekly_health AS (
    SELECT COUNT(*) AS rows,COUNT(DISTINCT item_id) AS items,
        COUNT(*) FILTER (WHERE source_daily_rows<>7*cfg.expected_stores OR date_diff('day',week_start,week_end)<>6
            OR units IS NULL OR units<0 OR wm_yr_wk IS NULL) AS invalid_rows
    FROM weekly_expected CROSS JOIN parameters cfg
), health AS (
    SELECT ph.rows=cfg.expected_items AND ph.items=cfg.expected_items AND ph.invalid_rows=0
        AND sh.rows=cfg.expected_stores AND sh.stores=cfg.expected_stores AND sh.invalid_rows=0
        AND wh.weeks=cfg.expected_weeks AND wh.first_date=cfg.start_date AND wh.last_date=cfg.end_date AND wh.invalid_weeks=0
        AND ch.rows=cfg.expected_days AND ch.day_keys=cfg.expected_days AND ch.dates=cfg.expected_days AND ch.invalid_rows=0
        AND src.series=cfg.expected_items*cfg.expected_stores AND src.items=cfg.expected_items AND src.stores=cfg.expected_stores
        AND src.daily_rows=cfg.expected_items*cfg.expected_stores*cfg.expected_days AND src.invalid_rows=0 AND src.key_errors=0
        AND j.daily_rows=src.daily_rows AND j.units=src.units AND j.unmatched_rows=0
        AND w.rows=cfg.expected_items*cfg.expected_weeks AND w.items=cfg.expected_items AND w.invalid_rows=0 AS passed
    FROM parameters cfg CROSS JOIN product_health ph CROSS JOIN store_health sh CROSS JOIN week_health wh
    CROSS JOIN calendar_health ch CROSS JOIN source_health src CROSS JOIN join_health j CROSS JOIN weekly_health w
)
SELECT w.item_id,w.dept_id,w.cat_id,w.wm_yr_wk,w.week_start,w.week_end,
    CASE WHEN NOT COALESCE(h.passed,false)
         THEN error('Weekly build blocked: check full retail weeks, complete daily keys and dimension/calendar mappings')
         ELSE w.units END AS units,w.source_daily_rows
FROM health h LEFT JOIN weekly_expected w ON true;

-- VALIDATION: if the weekly table already exists, run only the complete query below.
-- Recompute every stored field from the accepted daily fact; do not overwrite the table.
WITH parameters AS (
    SELECT 3049 AS expected_items,10 AS expected_stores,12 AS expected_weeks,84 AS expected_days,
        DATE '2016-01-26' AS abc_start,DATE '2016-04-24' AS abc_end,
        DATE '2016-01-30' AS start_date,DATE '2016-04-22' AS end_date
), department_mapping(dept_id,cat_id) AS (
    VALUES ('FOODS_1','FOODS'),('FOODS_2','FOODS'),('FOODS_3','FOODS'),
        ('HOUSEHOLD_1','HOUSEHOLD'),('HOUSEHOLD_2','HOUSEHOLD'),('HOBBIES_1','HOBBIES'),('HOBBIES_2','HOBBIES')
), product_health AS (
    SELECT COUNT(*) AS rows,COUNT(DISTINCT p.item_id) AS items,
        COUNT(*) FILTER (WHERE NULLIF(TRIM(p.item_id),'') IS NULL OR m.dept_id IS NULL) AS invalid_rows
    FROM core.m5_product p LEFT JOIN department_mapping m ON p.dept_id=m.dept_id AND p.cat_id=m.cat_id
), store_health AS (
    SELECT COUNT(*) AS rows,COUNT(DISTINCT store_id) AS stores,
        COUNT(*) FILTER (WHERE NULLIF(TRIM(store_id),'') IS NULL) AS invalid_rows FROM core.m5_store
), week_catalog AS MATERIALIZED (
    -- Group the complete calendar first, so clipped partial weeks cannot look complete.
    SELECT wm_yr_wk,MIN("date") AS week_start,MAX("date") AS week_end,COUNT(*) AS calendar_rows,
        COUNT(DISTINCT "date") AS distinct_dates,COUNT(DISTINCT d) AS distinct_days
    FROM core.m5_calendar GROUP BY wm_yr_wk
), selected_weeks AS MATERIALIZED (
    SELECT w.* FROM week_catalog w CROSS JOIN parameters cfg
    WHERE w.week_start>=cfg.abc_start AND w.week_end<=cfg.abc_end
), week_health AS (
    SELECT COUNT(*) AS weeks,MIN(week_start) AS first_date,MAX(week_end) AS last_date,
        COUNT(*) FILTER (WHERE calendar_rows<>7 OR distinct_dates<>7 OR distinct_days<>7
            OR date_diff('day',week_start,week_end)<>6 OR dayofweek(week_start)<>6 OR dayofweek(week_end)<>5
            OR wm_yr_wk IS DISTINCT FROM 11601+date_diff('day',cfg.start_date,week_start)//7) AS invalid_weeks
    FROM selected_weeks CROSS JOIN parameters cfg
), selected_calendar AS MATERIALIZED (
    SELECT c.d,c."date",c.wm_yr_wk FROM core.m5_calendar c JOIN selected_weeks w USING (wm_yr_wk)
), calendar_health AS (
    SELECT COUNT(*) AS rows,COUNT(DISTINCT d) AS day_keys,COUNT(DISTINCT "date") AS dates,
        COUNT(*) FILTER (WHERE d IS DISTINCT FROM 'd_'||CAST(date_diff('day',DATE '2011-01-29',"date")+1 AS VARCHAR)
            OR "date" IS NULL OR typeof("date")<>'DATE' OR typeof(wm_yr_wk)<>'INTEGER'
            OR wm_yr_wk IS DISTINCT FROM 11601+date_diff('day',cfg.start_date,"date")//7) AS invalid_rows
    FROM selected_calendar CROSS JOIN parameters cfg
), selected_fact AS MATERIALIZED (
    SELECT f.item_id,f.store_id,f.d,f."date",f.wm_yr_wk,f.units,
        CAST(date_diff('day',cfg.start_date,f."date")+1 AS INTEGER) AS window_day
    FROM mart.m5_sales_daily f CROSS JOIN parameters cfg
    WHERE f."date" BETWEEN cfg.start_date AND cfg.end_date
), by_series AS MATERIALIZED (
    SELECT item_id,store_id,COUNT(*) AS daily_rows,
        bit_count(bitstring_agg(window_day,1,84)) AS covered_days,SUM(units) AS units,
        COUNT(*) FILTER (WHERE NULLIF(TRIM(item_id),'') IS NULL OR NULLIF(TRIM(store_id),'') IS NULL
            OR units IS NULL OR units<0 OR typeof(units)<>'INTEGER' OR typeof("date")<>'DATE'
            OR d IS DISTINCT FROM 'd_'||CAST(date_diff('day',DATE '2011-01-29',"date")+1 AS VARCHAR)) AS invalid_rows
    FROM selected_fact GROUP BY item_id,store_id
), source_health AS (
    SELECT COUNT(*) AS series,COUNT(DISTINCT item_id) AS items,COUNT(DISTINCT store_id) AS stores,
        COALESCE(SUM(daily_rows),0) AS daily_rows,COALESCE(SUM(units),0) AS units,
        COALESCE(SUM(invalid_rows),0) AS invalid_rows,
        COUNT(*) FILTER (WHERE daily_rows<>84 OR covered_days IS DISTINCT FROM 84) AS key_errors
    FROM by_series
), joined AS MATERIALIZED (
    SELECT f.*,p.dept_id,p.cat_id,s.store_id AS matched_store,c.d AS calendar_day,c.wm_yr_wk AS calendar_week
    FROM selected_fact f LEFT JOIN core.m5_product p ON f.item_id=p.item_id
    LEFT JOIN core.m5_store s ON f.store_id=s.store_id
    LEFT JOIN selected_calendar c ON f.d=c.d AND f."date"=c."date" AND f.wm_yr_wk=c.wm_yr_wk
), join_health AS (
    SELECT COUNT(*) AS daily_rows,COALESCE(SUM(units),0) AS units,
        COUNT(*) FILTER (WHERE dept_id IS NULL OR cat_id IS NULL OR matched_store IS NULL OR calendar_day IS NULL) AS unmatched_rows
    FROM joined
), weekly_expected AS MATERIALIZED (
    SELECT item_id,dept_id,cat_id,calendar_week AS wm_yr_wk,
        MIN("date") AS week_start,MAX("date") AS week_end,SUM(units) AS units,COUNT(*) AS source_daily_rows
    FROM joined GROUP BY item_id,dept_id,cat_id,calendar_week
), weekly_health AS (
    SELECT COUNT(*) AS rows,COUNT(DISTINCT item_id) AS items,
        COUNT(*) FILTER (WHERE source_daily_rows<>7*cfg.expected_stores OR date_diff('day',week_start,week_end)<>6
            OR units IS NULL OR units<0 OR wm_yr_wk IS NULL) AS invalid_rows
    FROM weekly_expected CROSS JOIN parameters cfg
), health AS (
    SELECT ph.rows=cfg.expected_items AND ph.items=cfg.expected_items AND ph.invalid_rows=0
        AND sh.rows=cfg.expected_stores AND sh.stores=cfg.expected_stores AND sh.invalid_rows=0
        AND wh.weeks=cfg.expected_weeks AND wh.first_date=cfg.start_date AND wh.last_date=cfg.end_date AND wh.invalid_weeks=0
        AND ch.rows=cfg.expected_days AND ch.day_keys=cfg.expected_days AND ch.dates=cfg.expected_days AND ch.invalid_rows=0
        AND src.series=cfg.expected_items*cfg.expected_stores AND src.items=cfg.expected_items AND src.stores=cfg.expected_stores
        AND src.daily_rows=cfg.expected_items*cfg.expected_stores*cfg.expected_days AND src.invalid_rows=0 AND src.key_errors=0
        AND j.daily_rows=src.daily_rows AND j.units=src.units AND j.unmatched_rows=0
        AND w.rows=cfg.expected_items*cfg.expected_weeks AND w.items=cfg.expected_items AND w.invalid_rows=0 AS passed
    FROM parameters cfg CROSS JOIN product_health ph CROSS JOIN store_health sh CROSS JOIN week_health wh
    CROSS JOIN calendar_health ch CROSS JOIN source_health src CROSS JOIN join_health j CROSS JOIN weekly_health w
), expected_schema(column_name,data_type,ordinal_position) AS (
    VALUES ('item_id','VARCHAR',1),('dept_id','VARCHAR',2),('cat_id','VARCHAR',3),('wm_yr_wk','INTEGER',4),
        ('week_start','DATE',5),('week_end','DATE',6),('units','HUGEINT',7),('source_daily_rows','BIGINT',8)
), actual_schema AS (
    SELECT column_name,data_type,ordinal_position FROM information_schema.columns
    WHERE table_catalog=current_database() AND table_schema='mart' AND table_name='m5_product_weekly_12w'
), schema_errors AS (
    SELECT COUNT(*) AS errors FROM expected_schema e FULL OUTER JOIN actual_schema a USING (column_name)
    WHERE e.column_name IS NULL OR a.column_name IS NULL OR e.data_type IS DISTINCT FROM a.data_type
        OR e.ordinal_position IS DISTINCT FROM a.ordinal_position
), actual AS MATERIALIZED (
    SELECT item_id,dept_id,cat_id,wm_yr_wk,week_start,week_end,units,source_daily_rows FROM mart.m5_product_weekly_12w
), expected_only AS (
    SELECT * FROM weekly_expected EXCEPT ALL SELECT * FROM actual
), actual_only AS (
    SELECT * FROM actual EXCEPT ALL SELECT * FROM weekly_expected
), item_coverage AS (
    SELECT item_id,COUNT(*) AS rows,COUNT(DISTINCT wm_yr_wk) AS weeks FROM actual GROUP BY item_id
), validation_health AS (
    SELECT h.passed AND se.errors=0 AND (SELECT COUNT(*) FROM actual_schema)=8
        AND (SELECT COUNT(*) FROM actual)=cfg.expected_items*cfg.expected_weeks
        AND (SELECT COUNT(*) FROM item_coverage)=cfg.expected_items
        AND NOT EXISTS (SELECT 1 FROM item_coverage WHERE rows<>cfg.expected_weeks OR weeks<>cfg.expected_weeks)
        AND NOT EXISTS (SELECT 1 FROM expected_only) AND NOT EXISTS (SELECT 1 FROM actual_only) AS passed
    FROM health h CROSS JOIN schema_errors se CROSS JOIN parameters cfg
), report AS (
    SELECT GROUPING(wm_yr_wk) AS is_total,
        CASE WHEN GROUPING(wm_yr_wk)=1 THEN 'TOTAL' ELSE CAST(wm_yr_wk AS VARCHAR) END AS retail_week,
        MIN(week_start) AS week_start,MAX(week_end) AS week_end,COUNT(*) AS product_week_rows,
        COALESCE(SUM(source_daily_rows),0) AS source_daily_rows,COALESCE(SUM(units),0) AS units,
        COUNT(*) FILTER (WHERE units=0) AS zero_sales_product_weeks
    FROM actual GROUP BY GROUPING SETS ((wm_yr_wk),())
)
SELECT r.retail_week,r.week_start,r.week_end,r.product_week_rows,r.source_daily_rows,r.units,r.zero_sales_product_weeks,
    CASE WHEN COALESCE(h.passed,false) THEN 'PASS'
         ELSE error('Weekly validation blocked: source completeness, schema, key coverage or exact stored-row comparison failed')
    END AS check_status
FROM report r CROSS JOIN validation_health h ORDER BY r.is_total,r.retail_week;
