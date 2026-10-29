-- Purpose: preserve every item/store/week's recorded units and published weekly price.
-- Fixed retrospective scope: 11601..11612, 2016-01-30..2016-04-22, all 30,490 item/store series.
-- Missing prices remain NULL; observed zero-sales weeks remain present. Missing daily rows are errors.
-- Weekly price is joined only after aggregating units, on exact item/store/source-week keys.
-- Positive recorded sales require an observed price. No imputation, value proxy or price-change result.
-- Run the whole file once; existing tables are never overwritten and historical inputs stay unchanged.
CREATE SCHEMA IF NOT EXISTS mart;
CREATE TABLE mart.m5_item_store_weekly_prices_12w AS
WITH parameters AS (
    SELECT 3049 AS expected_items,10 AS expected_stores,12 AS expected_weeks,84 AS expected_days,
        DATE '2016-01-30' AS start_date,DATE '2016-04-22' AS end_date
), department_mapping(dept_id,cat_id) AS (
    VALUES ('FOODS_1','FOODS'),('FOODS_2','FOODS'),('FOODS_3','FOODS'),
        ('HOUSEHOLD_1','HOUSEHOLD'),('HOUSEHOLD_2','HOUSEHOLD'),('HOBBIES_1','HOBBIES'),('HOBBIES_2','HOBBIES')
), required_schema(table_schema,table_name,column_name,data_type) AS (
    VALUES ('core','m5_product','item_id','VARCHAR'),('core','m5_product','dept_id','VARCHAR'),
        ('core','m5_product','cat_id','VARCHAR'),('core','m5_store','store_id','VARCHAR'),
        ('core','m5_store','state_id','VARCHAR'),('core','m5_calendar','d','VARCHAR'),
        ('core','m5_calendar','date','DATE'),('core','m5_calendar','wm_yr_wk','INTEGER'),
        ('mart','m5_sales_daily','item_id','VARCHAR'),('mart','m5_sales_daily','store_id','VARCHAR'),
        ('mart','m5_sales_daily','d','VARCHAR'),('mart','m5_sales_daily','date','DATE'),
        ('mart','m5_sales_daily','wm_yr_wk','INTEGER'),('mart','m5_sales_daily','units','INTEGER'),
        ('raw','m5_sales_wide','item_id','VARCHAR'),('raw','m5_sales_wide','store_id','VARCHAR'),
        ('raw','m5_sales_wide','dept_id','VARCHAR'),('raw','m5_sales_wide','cat_id','VARCHAR'),
        ('raw','m5_sales_wide','state_id','VARCHAR')
), required_schema_errors AS (
    SELECT COUNT(*) AS errors FROM required_schema e LEFT JOIN information_schema.columns a
        ON a.table_catalog=current_database() AND e.table_schema=a.table_schema
        AND e.table_name=a.table_name AND e.column_name=a.column_name
    WHERE a.column_name IS NULL OR a.data_type IS DISTINCT FROM e.data_type
), price_schema(column_name,data_type,ordinal_position) AS (
    VALUES ('store_id','VARCHAR',1),('item_id','VARCHAR',2),
        ('wm_yr_wk','INTEGER',3),('sell_price','DECIMAL(18,2)',4)
), actual_price_schema AS (
    SELECT column_name,data_type,ordinal_position FROM information_schema.columns
    WHERE table_catalog=current_database() AND table_schema='stg' AND table_name='m5_prices'
), price_schema_errors AS (
    SELECT COUNT(*) AS errors FROM price_schema e FULL OUTER JOIN actual_price_schema a USING (column_name)
    WHERE e.column_name IS NULL OR a.column_name IS NULL OR e.data_type IS DISTINCT FROM a.data_type
        OR e.ordinal_position IS DISTINCT FROM a.ordinal_position
), pooled_schema(column_name,data_type,ordinal_position) AS (
    VALUES ('item_id','VARCHAR',1),('dept_id','VARCHAR',2),('cat_id','VARCHAR',3),('wm_yr_wk','INTEGER',4),
        ('week_start','DATE',5),('week_end','DATE',6),('units','HUGEINT',7),('source_daily_rows','BIGINT',8)
), actual_pooled_schema AS (
    SELECT column_name,data_type,ordinal_position FROM information_schema.columns
    WHERE table_catalog=current_database() AND table_schema='mart' AND table_name='m5_product_weekly_12w'
), pooled_schema_errors AS (
    SELECT COUNT(*) AS errors FROM pooled_schema e FULL OUTER JOIN actual_pooled_schema a USING (column_name)
    WHERE e.column_name IS NULL OR a.column_name IS NULL OR e.data_type IS DISTINCT FROM a.data_type
        OR e.ordinal_position IS DISTINCT FROM a.ordinal_position
), raw_products AS MATERIALIZED (
    SELECT DISTINCT item_id,dept_id,cat_id FROM raw.m5_sales_wide
), raw_stores AS MATERIALIZED (
    SELECT DISTINCT store_id,state_id FROM raw.m5_sales_wide
), raw_product_only AS (SELECT * FROM raw_products EXCEPT ALL SELECT * FROM core.m5_product),
core_product_only AS (SELECT * FROM core.m5_product EXCEPT ALL SELECT * FROM raw_products),
raw_store_only AS (SELECT * FROM raw_stores EXCEPT ALL SELECT * FROM core.m5_store),
core_store_only AS (SELECT * FROM core.m5_store EXCEPT ALL SELECT * FROM raw_stores),
dimension_health AS (
    SELECT (SELECT COUNT(*) FROM core.m5_product)=cfg.expected_items
        AND (SELECT COUNT(DISTINCT item_id) FROM core.m5_product)=cfg.expected_items
        AND NOT EXISTS (SELECT 1 FROM core.m5_product p LEFT JOIN department_mapping m
            ON p.dept_id=m.dept_id AND p.cat_id=m.cat_id
            WHERE NULLIF(TRIM(p.item_id),'') IS NULL OR m.dept_id IS NULL)
        AND (SELECT COUNT(*) FROM core.m5_store)=cfg.expected_stores
        AND (SELECT COUNT(DISTINCT store_id) FROM core.m5_store)=cfg.expected_stores
        AND NOT EXISTS (SELECT 1 FROM core.m5_store
            WHERE NULLIF(TRIM(store_id),'') IS NULL OR state_id IS NULL OR state_id NOT IN ('CA','TX','WI'))
        AND (SELECT COUNT(*) FROM raw.m5_sales_wide)=cfg.expected_items*cfg.expected_stores
        AND (SELECT COUNT(DISTINCT (item_id,store_id)) FROM raw.m5_sales_wide)=cfg.expected_items*cfg.expected_stores
        AND NOT EXISTS (SELECT 1 FROM raw_product_only) AND NOT EXISTS (SELECT 1 FROM core_product_only)
        AND NOT EXISTS (SELECT 1 FROM raw_store_only) AND NOT EXISTS (SELECT 1 FROM core_store_only) AS passed
    FROM parameters cfg
), week_catalog AS MATERIALIZED (
    -- Inspect whole source weeks before selection: clipping cannot make a partial week complete.
    SELECT wm_yr_wk,MIN(date) AS week_start,MAX(date) AS week_end,COUNT(*) AS calendar_rows,
        COUNT(DISTINCT date) AS dates,COUNT(DISTINCT d) AS day_keys
    FROM core.m5_calendar GROUP BY wm_yr_wk
), selected_weeks AS MATERIALIZED (
    SELECT * FROM week_catalog WHERE wm_yr_wk BETWEEN 11601 AND 11612
), selected_calendar AS MATERIALIZED (
    SELECT c.d,c.date,c.wm_yr_wk FROM core.m5_calendar c CROSS JOIN parameters cfg
    WHERE c.wm_yr_wk BETWEEN 11601 AND 11612 OR c.date BETWEEN cfg.start_date AND cfg.end_date
), calendar_health AS (
    SELECT (SELECT COUNT(*) FROM selected_weeks)=cfg.expected_weeks
        AND NOT EXISTS (SELECT 1 FROM selected_weeks
            WHERE calendar_rows<>7 OR dates<>7 OR day_keys<>7
                OR week_start IS DISTINCT FROM cfg.start_date+7*(wm_yr_wk-11601)
                OR week_end IS DISTINCT FROM cfg.start_date+7*(wm_yr_wk-11601)+6
                OR dayofweek(week_start)<>6 OR dayofweek(week_end)<>5)
        AND (SELECT COUNT(*) FROM selected_calendar)=cfg.expected_days
        AND (SELECT COUNT(DISTINCT d) FROM selected_calendar)=cfg.expected_days
        AND (SELECT COUNT(DISTINCT date) FROM selected_calendar)=cfg.expected_days
        AND NOT EXISTS (SELECT 1 FROM selected_calendar
            WHERE date IS NULL OR date NOT BETWEEN cfg.start_date AND cfg.end_date
                OR d IS DISTINCT FROM 'd_'||CAST(date_diff('day',DATE '2011-01-29',date)+1 AS VARCHAR)
                OR wm_yr_wk IS DISTINCT FROM 11601+date_diff('day',cfg.start_date,date)//7) AS passed
    FROM parameters cfg
), selected_daily AS MATERIALIZED (
    -- Other fact columns, including its historical daily price, are deliberately not inputs.
    SELECT f.item_id,f.store_id,f.d,f.date,f.wm_yr_wk,f.units
    FROM mart.m5_sales_daily f CROSS JOIN parameters cfg WHERE f.date BETWEEN cfg.start_date AND cfg.end_date
), daily_coverage AS MATERIALIZED (
    SELECT item_id,store_id,COUNT(*) AS rows,COUNT(DISTINCT d) AS days,COUNT(DISTINCT date) AS dates,
        MIN(date) AS first_date,MAX(date) AS last_date FROM selected_daily GROUP BY item_id,store_id
), daily_health AS (
    SELECT COUNT(*) AS rows,COALESCE(SUM(f.units),0) AS units,
        COUNT(*) FILTER (WHERE p.item_id IS NULL OR s.store_id IS NULL OR c.d IS NULL
            OR f.units IS NULL OR f.units<0
            OR f.d IS DISTINCT FROM 'd_'||CAST(date_diff('day',DATE '2011-01-29',f.date)+1 AS VARCHAR)) AS invalid_rows
    FROM selected_daily f LEFT JOIN core.m5_product p ON f.item_id=p.item_id
    LEFT JOIN core.m5_store s ON f.store_id=s.store_id
    LEFT JOIN selected_calendar c ON f.d=c.d AND f.date=c.date AND f.wm_yr_wk=c.wm_yr_wk
), weekly_units AS MATERIALIZED (
    SELECT item_id,store_id,wm_yr_wk,SUM(units) AS units,COUNT(*) AS source_daily_rows
    FROM selected_daily GROUP BY item_id,store_id,wm_yr_wk
), relevant_prices AS MATERIALIZED (
    -- All in-window records are checked, including unknown keys; NULL weeks cannot disappear.
    SELECT store_id,item_id,wm_yr_wk,sell_price FROM stg.m5_prices
    WHERE wm_yr_wk BETWEEN 11601 AND 11612 OR wm_yr_wk IS NULL
), price_health AS (
    SELECT COUNT(*) AS rows,COUNT(*)-COUNT(DISTINCT (p.item_id,p.store_id,p.wm_yr_wk)) AS key_errors,
        COUNT(*) FILTER (WHERE i.item_id IS NULL OR s.store_id IS NULL OR p.wm_yr_wk IS NULL
            OR p.sell_price IS NULL OR p.sell_price<=0) AS invalid_rows
    FROM relevant_prices p LEFT JOIN core.m5_product i ON p.item_id=i.item_id
    LEFT JOIN core.m5_store s ON p.store_id=s.store_id
), weekly_expected AS MATERIALIZED (
    SELECT i.item_id,s.store_id,i.dept_id,i.cat_id,s.state_id,w.wm_yr_wk,w.week_start,w.week_end,
        u.units,u.source_daily_rows,p.sell_price,p.wm_yr_wk IS NOT NULL AS has_price
    FROM core.m5_product i CROSS JOIN core.m5_store s CROSS JOIN selected_weeks w
    LEFT JOIN weekly_units u ON i.item_id=u.item_id AND s.store_id=u.store_id AND w.wm_yr_wk=u.wm_yr_wk
    LEFT JOIN relevant_prices p ON i.item_id=p.item_id AND s.store_id=p.store_id AND w.wm_yr_wk=p.wm_yr_wk
), grid_health AS (
    SELECT COUNT(*) AS rows,COALESCE(SUM(units),0) AS units,
        COALESCE(SUM(source_daily_rows),0) AS daily_rows,
        COUNT(*) FILTER (WHERE units IS NULL OR units<0 OR source_daily_rows IS DISTINCT FROM 7
            OR (units>0 AND NOT has_price) OR has_price IS DISTINCT FROM (sell_price IS NOT NULL)) AS invalid_rows
    FROM weekly_expected
), pooled_expected AS MATERIALIZED (
    SELECT item_id,dept_id,cat_id,wm_yr_wk,week_start,week_end,SUM(units) AS units,
        CAST(SUM(source_daily_rows) AS BIGINT) AS source_daily_rows
    FROM weekly_expected GROUP BY item_id,dept_id,cat_id,wm_yr_wk,week_start,week_end
), pooled_expected_only AS (
    SELECT * FROM pooled_expected EXCEPT ALL SELECT * FROM mart.m5_product_weekly_12w
), pooled_actual_only AS (
    SELECT * FROM mart.m5_product_weekly_12w EXCEPT ALL SELECT * FROM pooled_expected
), health AS (
    SELECT se.errors=0 AND ps.errors=0 AND ws.errors=0 AND dh.passed AND ch.passed
        AND (SELECT COUNT(*) FROM actual_price_schema)=4 AND (SELECT COUNT(*) FROM actual_pooled_schema)=8
        AND (SELECT COUNT(*) FROM daily_coverage)=cfg.expected_items*cfg.expected_stores
        AND NOT EXISTS (SELECT 1 FROM daily_coverage WHERE rows<>cfg.expected_days OR days<>cfg.expected_days
            OR dates<>cfg.expected_days OR first_date IS DISTINCT FROM cfg.start_date OR last_date IS DISTINCT FROM cfg.end_date)
        AND d.rows=cfg.expected_items*cfg.expected_stores*cfg.expected_days AND d.invalid_rows=0
        AND d.rows=(SELECT COUNT(*) FROM selected_daily)
        AND d.units=(SELECT COALESCE(SUM(units),0) FROM selected_daily)
        AND p.key_errors=0 AND p.invalid_rows=0
        AND g.rows=cfg.expected_items*cfg.expected_stores*cfg.expected_weeks
        AND g.daily_rows=d.rows AND g.units=d.units AND g.invalid_rows=0
        AND (SELECT COUNT(*) FROM mart.m5_product_weekly_12w)=cfg.expected_items*cfg.expected_weeks
        AND (SELECT COUNT(DISTINCT (item_id,wm_yr_wk)) FROM mart.m5_product_weekly_12w)=cfg.expected_items*cfg.expected_weeks
        AND NOT EXISTS (SELECT 1 FROM pooled_expected_only) AND NOT EXISTS (SELECT 1 FROM pooled_actual_only) AS passed
    FROM parameters cfg CROSS JOIN required_schema_errors se CROSS JOIN price_schema_errors ps
    CROSS JOIN pooled_schema_errors ws CROSS JOIN dimension_health dh CROSS JOIN calendar_health ch
    CROSS JOIN daily_health d CROSS JOIN price_health p CROSS JOIN grid_health g
)
SELECT w.item_id,w.store_id,w.dept_id,w.cat_id,w.state_id,w.wm_yr_wk,w.week_start,w.week_end,
    CASE WHEN NOT COALESCE(h.passed,false)
         THEN error('Item-store weekly build blocked: source completeness, calendar, mappings, prices or accepted product-week rollup failed')
         ELSE w.units END AS units,w.source_daily_rows,w.sell_price,w.has_price
FROM health h LEFT JOIN weekly_expected w ON true;

-- VALIDATION: if the target already exists, run only the complete query below.
-- Recompute every stored field, retain NULLs, and compare both directions including duplicate rows.
WITH parameters AS (
    SELECT 3049 AS expected_items,10 AS expected_stores,12 AS expected_weeks,84 AS expected_days,
        DATE '2016-01-30' AS start_date,DATE '2016-04-22' AS end_date
), department_mapping(dept_id,cat_id) AS (
    VALUES ('FOODS_1','FOODS'),('FOODS_2','FOODS'),('FOODS_3','FOODS'),
        ('HOUSEHOLD_1','HOUSEHOLD'),('HOUSEHOLD_2','HOUSEHOLD'),('HOBBIES_1','HOBBIES'),('HOBBIES_2','HOBBIES')
), required_schema(table_schema,table_name,column_name,data_type) AS (
    VALUES ('core','m5_product','item_id','VARCHAR'),('core','m5_product','dept_id','VARCHAR'),
        ('core','m5_product','cat_id','VARCHAR'),('core','m5_store','store_id','VARCHAR'),
        ('core','m5_store','state_id','VARCHAR'),('core','m5_calendar','d','VARCHAR'),
        ('core','m5_calendar','date','DATE'),('core','m5_calendar','wm_yr_wk','INTEGER'),
        ('mart','m5_sales_daily','item_id','VARCHAR'),('mart','m5_sales_daily','store_id','VARCHAR'),
        ('mart','m5_sales_daily','d','VARCHAR'),('mart','m5_sales_daily','date','DATE'),
        ('mart','m5_sales_daily','wm_yr_wk','INTEGER'),('mart','m5_sales_daily','units','INTEGER'),
        ('raw','m5_sales_wide','item_id','VARCHAR'),('raw','m5_sales_wide','store_id','VARCHAR'),
        ('raw','m5_sales_wide','dept_id','VARCHAR'),('raw','m5_sales_wide','cat_id','VARCHAR'),
        ('raw','m5_sales_wide','state_id','VARCHAR')
), required_schema_errors AS (
    SELECT COUNT(*) AS errors FROM required_schema e LEFT JOIN information_schema.columns a
        ON a.table_catalog=current_database() AND e.table_schema=a.table_schema
        AND e.table_name=a.table_name AND e.column_name=a.column_name
    WHERE a.column_name IS NULL OR a.data_type IS DISTINCT FROM e.data_type
), price_schema(column_name,data_type,ordinal_position) AS (
    VALUES ('store_id','VARCHAR',1),('item_id','VARCHAR',2),
        ('wm_yr_wk','INTEGER',3),('sell_price','DECIMAL(18,2)',4)
), actual_price_schema AS (
    SELECT column_name,data_type,ordinal_position FROM information_schema.columns
    WHERE table_catalog=current_database() AND table_schema='stg' AND table_name='m5_prices'
), price_schema_errors AS (
    SELECT COUNT(*) AS errors FROM price_schema e FULL OUTER JOIN actual_price_schema a USING (column_name)
    WHERE e.column_name IS NULL OR a.column_name IS NULL OR e.data_type IS DISTINCT FROM a.data_type
        OR e.ordinal_position IS DISTINCT FROM a.ordinal_position
), pooled_schema(column_name,data_type,ordinal_position) AS (
    VALUES ('item_id','VARCHAR',1),('dept_id','VARCHAR',2),('cat_id','VARCHAR',3),('wm_yr_wk','INTEGER',4),
        ('week_start','DATE',5),('week_end','DATE',6),('units','HUGEINT',7),('source_daily_rows','BIGINT',8)
), actual_pooled_schema AS (
    SELECT column_name,data_type,ordinal_position FROM information_schema.columns
    WHERE table_catalog=current_database() AND table_schema='mart' AND table_name='m5_product_weekly_12w'
), pooled_schema_errors AS (
    SELECT COUNT(*) AS errors FROM pooled_schema e FULL OUTER JOIN actual_pooled_schema a USING (column_name)
    WHERE e.column_name IS NULL OR a.column_name IS NULL OR e.data_type IS DISTINCT FROM a.data_type
        OR e.ordinal_position IS DISTINCT FROM a.ordinal_position
), raw_products AS MATERIALIZED (
    SELECT DISTINCT item_id,dept_id,cat_id FROM raw.m5_sales_wide
), raw_stores AS MATERIALIZED (
    SELECT DISTINCT store_id,state_id FROM raw.m5_sales_wide
), raw_product_only AS (SELECT * FROM raw_products EXCEPT ALL SELECT * FROM core.m5_product),
core_product_only AS (SELECT * FROM core.m5_product EXCEPT ALL SELECT * FROM raw_products),
raw_store_only AS (SELECT * FROM raw_stores EXCEPT ALL SELECT * FROM core.m5_store),
core_store_only AS (SELECT * FROM core.m5_store EXCEPT ALL SELECT * FROM raw_stores),
dimension_health AS (
    SELECT (SELECT COUNT(*) FROM core.m5_product)=cfg.expected_items
        AND (SELECT COUNT(DISTINCT item_id) FROM core.m5_product)=cfg.expected_items
        AND NOT EXISTS (SELECT 1 FROM core.m5_product p LEFT JOIN department_mapping m
            ON p.dept_id=m.dept_id AND p.cat_id=m.cat_id
            WHERE NULLIF(TRIM(p.item_id),'') IS NULL OR m.dept_id IS NULL)
        AND (SELECT COUNT(*) FROM core.m5_store)=cfg.expected_stores
        AND (SELECT COUNT(DISTINCT store_id) FROM core.m5_store)=cfg.expected_stores
        AND NOT EXISTS (SELECT 1 FROM core.m5_store
            WHERE NULLIF(TRIM(store_id),'') IS NULL OR state_id IS NULL OR state_id NOT IN ('CA','TX','WI'))
        AND (SELECT COUNT(*) FROM raw.m5_sales_wide)=cfg.expected_items*cfg.expected_stores
        AND (SELECT COUNT(DISTINCT (item_id,store_id)) FROM raw.m5_sales_wide)=cfg.expected_items*cfg.expected_stores
        AND NOT EXISTS (SELECT 1 FROM raw_product_only) AND NOT EXISTS (SELECT 1 FROM core_product_only)
        AND NOT EXISTS (SELECT 1 FROM raw_store_only) AND NOT EXISTS (SELECT 1 FROM core_store_only) AS passed
    FROM parameters cfg
), week_catalog AS MATERIALIZED (
    -- Inspect whole source weeks before selection: clipping cannot make a partial week complete.
    SELECT wm_yr_wk,MIN(date) AS week_start,MAX(date) AS week_end,COUNT(*) AS calendar_rows,
        COUNT(DISTINCT date) AS dates,COUNT(DISTINCT d) AS day_keys
    FROM core.m5_calendar GROUP BY wm_yr_wk
), selected_weeks AS MATERIALIZED (
    SELECT * FROM week_catalog WHERE wm_yr_wk BETWEEN 11601 AND 11612
), selected_calendar AS MATERIALIZED (
    SELECT c.d,c.date,c.wm_yr_wk FROM core.m5_calendar c CROSS JOIN parameters cfg
    WHERE c.wm_yr_wk BETWEEN 11601 AND 11612 OR c.date BETWEEN cfg.start_date AND cfg.end_date
), calendar_health AS (
    SELECT (SELECT COUNT(*) FROM selected_weeks)=cfg.expected_weeks
        AND NOT EXISTS (SELECT 1 FROM selected_weeks
            WHERE calendar_rows<>7 OR dates<>7 OR day_keys<>7
                OR week_start IS DISTINCT FROM cfg.start_date+7*(wm_yr_wk-11601)
                OR week_end IS DISTINCT FROM cfg.start_date+7*(wm_yr_wk-11601)+6
                OR dayofweek(week_start)<>6 OR dayofweek(week_end)<>5)
        AND (SELECT COUNT(*) FROM selected_calendar)=cfg.expected_days
        AND (SELECT COUNT(DISTINCT d) FROM selected_calendar)=cfg.expected_days
        AND (SELECT COUNT(DISTINCT date) FROM selected_calendar)=cfg.expected_days
        AND NOT EXISTS (SELECT 1 FROM selected_calendar
            WHERE date IS NULL OR date NOT BETWEEN cfg.start_date AND cfg.end_date
                OR d IS DISTINCT FROM 'd_'||CAST(date_diff('day',DATE '2011-01-29',date)+1 AS VARCHAR)
                OR wm_yr_wk IS DISTINCT FROM 11601+date_diff('day',cfg.start_date,date)//7) AS passed
    FROM parameters cfg
), selected_daily AS MATERIALIZED (
    -- Other fact columns, including its historical daily price, are deliberately not inputs.
    SELECT f.item_id,f.store_id,f.d,f.date,f.wm_yr_wk,f.units
    FROM mart.m5_sales_daily f CROSS JOIN parameters cfg WHERE f.date BETWEEN cfg.start_date AND cfg.end_date
), daily_coverage AS MATERIALIZED (
    SELECT item_id,store_id,COUNT(*) AS rows,COUNT(DISTINCT d) AS days,COUNT(DISTINCT date) AS dates,
        MIN(date) AS first_date,MAX(date) AS last_date FROM selected_daily GROUP BY item_id,store_id
), daily_health AS (
    SELECT COUNT(*) AS rows,COALESCE(SUM(f.units),0) AS units,
        COUNT(*) FILTER (WHERE p.item_id IS NULL OR s.store_id IS NULL OR c.d IS NULL
            OR f.units IS NULL OR f.units<0
            OR f.d IS DISTINCT FROM 'd_'||CAST(date_diff('day',DATE '2011-01-29',f.date)+1 AS VARCHAR)) AS invalid_rows
    FROM selected_daily f LEFT JOIN core.m5_product p ON f.item_id=p.item_id
    LEFT JOIN core.m5_store s ON f.store_id=s.store_id
    LEFT JOIN selected_calendar c ON f.d=c.d AND f.date=c.date AND f.wm_yr_wk=c.wm_yr_wk
), weekly_units AS MATERIALIZED (
    SELECT item_id,store_id,wm_yr_wk,SUM(units) AS units,COUNT(*) AS source_daily_rows
    FROM selected_daily GROUP BY item_id,store_id,wm_yr_wk
), relevant_prices AS MATERIALIZED (
    -- All in-window records are checked, including unknown keys; NULL weeks cannot disappear.
    SELECT store_id,item_id,wm_yr_wk,sell_price FROM stg.m5_prices
    WHERE wm_yr_wk BETWEEN 11601 AND 11612 OR wm_yr_wk IS NULL
), price_health AS (
    SELECT COUNT(*) AS rows,COUNT(*)-COUNT(DISTINCT (p.item_id,p.store_id,p.wm_yr_wk)) AS key_errors,
        COUNT(*) FILTER (WHERE i.item_id IS NULL OR s.store_id IS NULL OR p.wm_yr_wk IS NULL
            OR p.sell_price IS NULL OR p.sell_price<=0) AS invalid_rows
    FROM relevant_prices p LEFT JOIN core.m5_product i ON p.item_id=i.item_id
    LEFT JOIN core.m5_store s ON p.store_id=s.store_id
), weekly_expected AS MATERIALIZED (
    SELECT i.item_id,s.store_id,i.dept_id,i.cat_id,s.state_id,w.wm_yr_wk,w.week_start,w.week_end,
        u.units,u.source_daily_rows,p.sell_price,p.wm_yr_wk IS NOT NULL AS has_price
    FROM core.m5_product i CROSS JOIN core.m5_store s CROSS JOIN selected_weeks w
    LEFT JOIN weekly_units u ON i.item_id=u.item_id AND s.store_id=u.store_id AND w.wm_yr_wk=u.wm_yr_wk
    LEFT JOIN relevant_prices p ON i.item_id=p.item_id AND s.store_id=p.store_id AND w.wm_yr_wk=p.wm_yr_wk
), grid_health AS (
    SELECT COUNT(*) AS rows,COALESCE(SUM(units),0) AS units,
        COALESCE(SUM(source_daily_rows),0) AS daily_rows,
        COUNT(*) FILTER (WHERE units IS NULL OR units<0 OR source_daily_rows IS DISTINCT FROM 7
            OR (units>0 AND NOT has_price) OR has_price IS DISTINCT FROM (sell_price IS NOT NULL)) AS invalid_rows
    FROM weekly_expected
), pooled_expected AS MATERIALIZED (
    SELECT item_id,dept_id,cat_id,wm_yr_wk,week_start,week_end,SUM(units) AS units,
        CAST(SUM(source_daily_rows) AS BIGINT) AS source_daily_rows
    FROM weekly_expected GROUP BY item_id,dept_id,cat_id,wm_yr_wk,week_start,week_end
), pooled_expected_only AS (
    SELECT * FROM pooled_expected EXCEPT ALL SELECT * FROM mart.m5_product_weekly_12w
), pooled_actual_only AS (
    SELECT * FROM mart.m5_product_weekly_12w EXCEPT ALL SELECT * FROM pooled_expected
), health AS (
    SELECT se.errors=0 AND ps.errors=0 AND ws.errors=0 AND dh.passed AND ch.passed
        AND (SELECT COUNT(*) FROM actual_price_schema)=4 AND (SELECT COUNT(*) FROM actual_pooled_schema)=8
        AND (SELECT COUNT(*) FROM daily_coverage)=cfg.expected_items*cfg.expected_stores
        AND NOT EXISTS (SELECT 1 FROM daily_coverage WHERE rows<>cfg.expected_days OR days<>cfg.expected_days
            OR dates<>cfg.expected_days OR first_date IS DISTINCT FROM cfg.start_date OR last_date IS DISTINCT FROM cfg.end_date)
        AND d.rows=cfg.expected_items*cfg.expected_stores*cfg.expected_days AND d.invalid_rows=0
        AND d.rows=(SELECT COUNT(*) FROM selected_daily)
        AND d.units=(SELECT COALESCE(SUM(units),0) FROM selected_daily)
        AND p.key_errors=0 AND p.invalid_rows=0
        AND g.rows=cfg.expected_items*cfg.expected_stores*cfg.expected_weeks
        AND g.daily_rows=d.rows AND g.units=d.units AND g.invalid_rows=0
        AND (SELECT COUNT(*) FROM mart.m5_product_weekly_12w)=cfg.expected_items*cfg.expected_weeks
        AND (SELECT COUNT(DISTINCT (item_id,wm_yr_wk)) FROM mart.m5_product_weekly_12w)=cfg.expected_items*cfg.expected_weeks
        AND NOT EXISTS (SELECT 1 FROM pooled_expected_only) AND NOT EXISTS (SELECT 1 FROM pooled_actual_only) AS passed
    FROM parameters cfg CROSS JOIN required_schema_errors se CROSS JOIN price_schema_errors ps
    CROSS JOIN pooled_schema_errors ws CROSS JOIN dimension_health dh CROSS JOIN calendar_health ch
    CROSS JOIN daily_health d CROSS JOIN price_health p CROSS JOIN grid_health g
)
, expected_schema(column_name,data_type,ordinal_position) AS (
    VALUES ('item_id','VARCHAR',1),('store_id','VARCHAR',2),('dept_id','VARCHAR',3),('cat_id','VARCHAR',4),
        ('state_id','VARCHAR',5),('wm_yr_wk','INTEGER',6),('week_start','DATE',7),('week_end','DATE',8),
        ('units','HUGEINT',9),('source_daily_rows','BIGINT',10),('sell_price','DECIMAL(18,2)',11),('has_price','BOOLEAN',12)
), actual_schema AS (
    SELECT column_name,data_type,ordinal_position FROM information_schema.columns
    WHERE table_catalog=current_database() AND table_schema='mart' AND table_name='m5_item_store_weekly_prices_12w'
), schema_errors AS (
    SELECT COUNT(*) AS errors FROM expected_schema e FULL OUTER JOIN actual_schema a USING (column_name)
    WHERE e.column_name IS NULL OR a.column_name IS NULL OR e.data_type IS DISTINCT FROM a.data_type
        OR e.ordinal_position IS DISTINCT FROM a.ordinal_position
), actual AS MATERIALIZED (
    SELECT item_id,store_id,dept_id,cat_id,state_id,wm_yr_wk,week_start,week_end,
        units,source_daily_rows,sell_price,has_price FROM mart.m5_item_store_weekly_prices_12w
), expected_only AS (SELECT * FROM weekly_expected EXCEPT ALL SELECT * FROM actual),
actual_only AS (SELECT * FROM actual EXCEPT ALL SELECT * FROM weekly_expected),
series_coverage AS (
    SELECT item_id,store_id,COUNT(*) AS rows,COUNT(DISTINCT wm_yr_wk) AS weeks
    FROM actual GROUP BY item_id,store_id
), validation_health AS (
    SELECT h.passed AND se.errors=0 AND (SELECT COUNT(*) FROM actual_schema)=12
        AND (SELECT COUNT(*) FROM actual)=cfg.expected_items*cfg.expected_stores*cfg.expected_weeks
        AND (SELECT COUNT(*) FROM series_coverage)=cfg.expected_items*cfg.expected_stores
        AND NOT EXISTS (SELECT 1 FROM series_coverage WHERE rows<>cfg.expected_weeks OR weeks<>cfg.expected_weeks)
        AND NOT EXISTS (SELECT 1 FROM expected_only) AND NOT EXISTS (SELECT 1 FROM actual_only) AS passed
    FROM health h CROSS JOIN schema_errors se CROSS JOIN parameters cfg
), report AS (
    SELECT GROUPING(wm_yr_wk) AS is_total,
        CASE WHEN GROUPING(wm_yr_wk)=1 THEN 'TOTAL' ELSE CAST(wm_yr_wk AS VARCHAR) END AS retail_week,
        MIN(week_start) AS week_start,MAX(week_end) AS week_end,COUNT(*) AS series_week_rows,
        COALESCE(SUM(source_daily_rows),0) AS source_daily_rows,COALESCE(SUM(units),0) AS units,
        COUNT(*) FILTER (WHERE units=0) AS zero_sales_series_weeks,
        COUNT(*) FILTER (WHERE has_price) AS priced_series_weeks,
        COUNT(*) FILTER (WHERE NOT has_price) AS missing_price_series_weeks,
        COUNT(*) FILTER (WHERE NOT has_price AND units>0) AS missing_price_positive_sales_weeks,
        COALESCE(SUM(units) FILTER (WHERE has_price),0) AS priced_units
    FROM actual GROUP BY GROUPING SETS ((wm_yr_wk),())
)
SELECT r.retail_week,r.week_start,r.week_end,r.series_week_rows,r.source_daily_rows,r.units,
    r.zero_sales_series_weeks,r.priced_series_weeks,r.missing_price_series_weeks,
    r.missing_price_positive_sales_weeks,r.priced_units,
    CASE WHEN COALESCE(h.passed,false) THEN 'PASS'
         ELSE error('Item-store weekly validation blocked: source, schema, coverage or exact stored-row comparison failed')
    END AS check_status
FROM report r CROSS JOIN validation_health h ORDER BY r.is_total,r.week_start;

