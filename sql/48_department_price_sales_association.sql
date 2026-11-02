-- Purpose: describe merchandise department composition of the accepted price-sales association.
-- Read-only; same 30,490 pairs, twelve input weeks, and all 335,390 immediate transitions.
-- Seven rows x twelve fields; internally retain all seven departments x four price directions.
-- series_count is distinct item/store support, not a sum of direction-specific pair counts.
-- Descriptive across all eleven current weeks; no joint week/department adjustment or causal control.
WITH parameters AS (
    SELECT 3049 AS expected_items,10 AS expected_stores,12 AS expected_weeks,84 AS expected_days,
        3536539 AS expected_units,DATE '2016-01-30' AS start_date,DATE '2016-04-22' AS end_date
), department_mapping(dept_id,cat_id) AS (
    VALUES ('FOODS_1','FOODS'),('FOODS_2','FOODS'),('FOODS_3','FOODS'),
        ('HOUSEHOLD_1','HOUSEHOLD'),('HOUSEHOLD_2','HOUSEHOLD'),('HOBBIES_1','HOBBIES'),('HOBBIES_2','HOBBIES')
), required_schema(table_schema,table_name,column_name,data_type) AS (
    VALUES ('core','m5_product','item_id','VARCHAR'),('core','m5_product','dept_id','VARCHAR'),
        ('core','m5_product','cat_id','VARCHAR'),('core','m5_store','store_id','VARCHAR'),
        ('core','m5_store','state_id','VARCHAR'),('core','m5_calendar','d','VARCHAR'),
        ('core','m5_calendar','date','DATE'),('core','m5_calendar','wm_yr_wk','INTEGER'),
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
), weekly_schema(column_name,data_type,ordinal_position) AS (
    VALUES ('item_id','VARCHAR',1),('store_id','VARCHAR',2),('dept_id','VARCHAR',3),('cat_id','VARCHAR',4),
        ('state_id','VARCHAR',5),('wm_yr_wk','INTEGER',6),('week_start','DATE',7),('week_end','DATE',8),
        ('units','HUGEINT',9),('source_daily_rows','BIGINT',10),('sell_price','DECIMAL(18,2)',11),('has_price','BOOLEAN',12)
), actual_weekly_schema AS (
    SELECT column_name,data_type,ordinal_position FROM information_schema.columns
    WHERE table_catalog=current_database() AND table_schema='mart' AND table_name='m5_item_store_weekly_prices_12w'
), weekly_schema_errors AS (
    SELECT COUNT(*) AS errors FROM weekly_schema e FULL OUTER JOIN actual_weekly_schema a USING (column_name)
    WHERE e.column_name IS NULL OR a.column_name IS NULL OR e.data_type IS DISTINCT FROM a.data_type
        OR e.ordinal_position IS DISTINCT FROM a.ordinal_position
), weekly AS MATERIALIZED (
    SELECT item_id,store_id,dept_id,cat_id,state_id,wm_yr_wk,week_start,week_end,units,
        source_daily_rows,sell_price,has_price FROM mart.m5_item_store_weekly_prices_12w
), series_coverage AS (
    SELECT item_id,store_id,COUNT(*) AS rows,COUNT(DISTINCT wm_yr_wk) AS weeks
    FROM weekly GROUP BY item_id,store_id
), weekly_health AS (
    SELECT COUNT(*) AS rows,COUNT(DISTINCT (w.item_id,w.store_id,w.wm_yr_wk)) AS keys,
        COALESCE(SUM(w.units),0) AS units,COALESCE(SUM(w.source_daily_rows),0) AS daily_rows,
        COUNT(*) FILTER (WHERE p.item_id IS NULL OR s.store_id IS NULL OR c.wm_yr_wk IS NULL
            OR w.dept_id IS DISTINCT FROM p.dept_id OR w.cat_id IS DISTINCT FROM p.cat_id
            OR w.state_id IS DISTINCT FROM s.state_id
            OR w.week_start IS DISTINCT FROM c.week_start OR w.week_end IS DISTINCT FROM c.week_end
            OR w.units IS NULL OR w.units<0 OR w.source_daily_rows IS DISTINCT FROM 7
            OR w.has_price IS NULL OR w.has_price IS DISTINCT FROM (w.sell_price IS NOT NULL)
            OR (w.sell_price IS NOT NULL AND w.sell_price<=0)
            OR (w.units>0 AND w.sell_price IS NULL)) AS invalid_rows
    FROM weekly w LEFT JOIN core.m5_product p ON w.item_id=p.item_id
    LEFT JOIN core.m5_store s ON w.store_id=s.store_id
    LEFT JOIN selected_weeks c ON w.wm_yr_wk=c.wm_yr_wk
), relevant_prices AS MATERIALIZED (
    SELECT store_id,item_id,wm_yr_wk,sell_price FROM stg.m5_prices
    WHERE wm_yr_wk BETWEEN 11601 AND 11612 OR wm_yr_wk IS NULL
), price_health AS (
    SELECT COUNT(*)-COUNT(DISTINCT (p.item_id,p.store_id,p.wm_yr_wk)) AS key_errors,
        COUNT(*) FILTER (WHERE i.item_id IS NULL OR s.store_id IS NULL OR p.wm_yr_wk IS NULL
            OR p.sell_price IS NULL OR p.sell_price<=0) AS invalid_rows
    FROM relevant_prices p LEFT JOIN core.m5_product i ON p.item_id=i.item_id
    LEFT JOIN core.m5_store s ON p.store_id=s.store_id
), price_join_health AS (
    SELECT COUNT(*) AS rows,COUNT(*) FILTER (WHERE w.sell_price IS DISTINCT FROM p.sell_price
        OR w.has_price IS DISTINCT FROM (p.wm_yr_wk IS NOT NULL)) AS errors
    FROM weekly w LEFT JOIN relevant_prices p
        ON w.item_id=p.item_id AND w.store_id=p.store_id AND w.wm_yr_wk=p.wm_yr_wk
), pooled_expected AS (
    SELECT item_id,dept_id,cat_id,wm_yr_wk,week_start,week_end,SUM(units) AS units,
        CAST(SUM(source_daily_rows) AS BIGINT) AS source_daily_rows
    FROM weekly GROUP BY item_id,dept_id,cat_id,wm_yr_wk,week_start,week_end
), pooled_expected_only AS (
    SELECT * FROM pooled_expected EXCEPT ALL SELECT * FROM mart.m5_product_weekly_12w
), pooled_actual_only AS (
    SELECT * FROM mart.m5_product_weekly_12w EXCEPT ALL SELECT * FROM pooled_expected
), input_health AS (
    SELECT se.errors=0 AND ps.errors=0 AND ws.errors=0 AND ts.errors=0 AND dh.passed AND ch.passed
        AND (SELECT COUNT(*) FROM actual_price_schema)=4 AND (SELECT COUNT(*) FROM actual_pooled_schema)=8
        AND (SELECT COUNT(*) FROM actual_weekly_schema)=12
        AND (SELECT COUNT(*) FROM series_coverage)=cfg.expected_items*cfg.expected_stores
        AND NOT EXISTS (SELECT 1 FROM series_coverage WHERE rows<>cfg.expected_weeks OR weeks<>cfg.expected_weeks)
        AND w.rows=cfg.expected_items*cfg.expected_stores*cfg.expected_weeks AND w.keys=w.rows
        AND w.invalid_rows=0 AND w.units=cfg.expected_units
        AND w.daily_rows=cfg.expected_items*cfg.expected_stores*cfg.expected_days
        AND p.key_errors=0 AND p.invalid_rows=0 AND j.rows=w.rows AND j.errors=0
        AND (SELECT COUNT(*) FROM mart.m5_product_weekly_12w)=cfg.expected_items*cfg.expected_weeks
        AND (SELECT COUNT(DISTINCT (item_id,wm_yr_wk)) FROM mart.m5_product_weekly_12w)=cfg.expected_items*cfg.expected_weeks
        AND NOT EXISTS (SELECT 1 FROM pooled_expected_only) AND NOT EXISTS (SELECT 1 FROM pooled_actual_only) AS passed
    FROM parameters cfg CROSS JOIN required_schema_errors se CROSS JOIN price_schema_errors ps
    CROSS JOIN pooled_schema_errors ws CROSS JOIN weekly_schema_errors ts CROSS JOIN dimension_health dh
    CROSS JOIN calendar_health ch CROSS JOIN weekly_health w CROSS JOIN price_health p CROSS JOIN price_join_health j
), lagged AS MATERIALIZED (
    -- Preserve missing-price and zero-sales rows before obtaining every previous endpoint.
    SELECT *,LAG(wm_yr_wk) OVER series_window AS previous_week,
        LAG(sell_price) OVER series_window AS previous_price,
        LAG(units) OVER series_window AS previous_units
    FROM weekly WINDOW series_window AS (PARTITION BY item_id,store_id ORDER BY wm_yr_wk)
), transitions AS MATERIALIZED (
    SELECT *,units-previous_units AS unit_change,
        CASE WHEN sell_price IS NULL OR previous_price IS NULL THEN 'MISSING_ENDPOINT'
             WHEN sell_price>previous_price THEN 'UP'
             WHEN sell_price<previous_price THEN 'DOWN' ELSE 'UNCHANGED' END AS price_direction
    FROM lagged WHERE wm_yr_wk BETWEEN 11602 AND 11612
), transition_health AS (
    SELECT (SELECT COUNT(*) FROM lagged WHERE wm_yr_wk=11601)=cfg.expected_items*cfg.expected_stores
        AND NOT EXISTS (SELECT 1 FROM lagged WHERE wm_yr_wk=11601
            AND (previous_week IS NOT NULL OR previous_price IS NOT NULL OR previous_units IS NOT NULL))
        AND (SELECT COUNT(*) FROM transitions)=cfg.expected_items*cfg.expected_stores*(cfg.expected_weeks-1)
        AND NOT EXISTS (SELECT 1 FROM transitions WHERE previous_week IS DISTINCT FROM wm_yr_wk-1
            OR previous_units IS NULL OR previous_units<0 OR unit_change IS NULL
            OR unit_change IS DISTINCT FROM units-previous_units
            OR (price_direction='MISSING_ENDPOINT') IS DISTINCT FROM
                (sell_price IS NULL OR previous_price IS NULL)) AS passed
    FROM parameters cfg
), expected_department_series(dept_id,expected_series) AS (
    VALUES ('FOODS_1',2160),('FOODS_2',3980),('FOODS_3',8230),('HOBBIES_1',4160),
        ('HOBBIES_2',1490),('HOUSEHOLD_1',5320),('HOUSEHOLD_2',5150)
), department_roster AS (
    SELECT dept_id,COUNT(DISTINCT (item_id,store_id)) AS series_count FROM weekly GROUP BY dept_id
), departments AS (
    SELECT e.dept_id,e.expected_series,COALESCE(r.series_count,0) AS series_count
    FROM expected_department_series e LEFT JOIN department_roster r USING (dept_id)
), categories(sort_order,price_direction) AS (
    VALUES (1,'UP'),(2,'DOWN'),(3,'UNCHANGED'),(4,'MISSING_ENDPOINT')
), aggregates AS MATERIALIZED (
    SELECT dept_id,price_direction,
        COUNT(*) AS transitions,COUNT(DISTINCT (item_id,store_id)) AS distinct_pairs,
        SUM(previous_units) AS previous_units,SUM(units) AS current_units,SUM(unit_change) AS unit_difference,
        CAST(ROUND(AVG(unit_change),6) AS DECIMAL(24,6)) AS mean_unit_change,
        CAST(ROUND(MEDIAN(unit_change),6) AS DECIMAL(24,6)) AS median_unit_change,
        COUNT(*) FILTER (WHERE unit_change>0) AS sales_up,
        COUNT(*) FILTER (WHERE unit_change<0) AS sales_down,
        COUNT(*) FILTER (WHERE unit_change=0) AS sales_unchanged
    FROM transitions GROUP BY dept_id,price_direction
), cells AS MATERIALIZED (
    -- All seven departments and all four directions remain represented, even when empty.
    SELECT d.dept_id,d.series_count,c.sort_order,c.price_direction,COALESCE(a.transitions,0) AS transitions,
        COALESCE(a.distinct_pairs,0) AS distinct_pairs,COALESCE(a.previous_units,0) AS previous_units,
        COALESCE(a.current_units,0) AS current_units,COALESCE(a.unit_difference,0) AS unit_difference,
        a.mean_unit_change,a.median_unit_change,
        CAST(ROUND(100.0*a.sales_up/NULLIF(a.transitions,0),4) AS DECIMAL(9,4)) AS sales_up_pct,
        CAST(ROUND(100.0*a.sales_down/NULLIF(a.transitions,0),4) AS DECIMAL(9,4)) AS sales_down_pct,
        CAST(ROUND(100.0*a.sales_unchanged/NULLIF(a.transitions,0),4) AS DECIMAL(9,4)) AS sales_unchanged_pct,
        COALESCE(a.sales_up,0) AS sales_up,COALESCE(a.sales_down,0) AS sales_down,
        COALESCE(a.sales_unchanged,0) AS sales_unchanged
    FROM departments d CROSS JOIN categories c LEFT JOIN aggregates a
        ON a.dept_id=d.dept_id AND a.price_direction=c.price_direction
), report AS MATERIALIZED (
    SELECT dept_id,series_count,
        MAX(transitions) FILTER (WHERE price_direction='UP') AS price_up_transitions,
        MAX(mean_unit_change) FILTER (WHERE price_direction='UP') AS price_up_mean_unit_change,
        MAX(transitions) FILTER (WHERE price_direction='DOWN') AS price_down_transitions,
        MAX(mean_unit_change) FILTER (WHERE price_direction='DOWN') AS price_down_mean_unit_change,
        MAX(transitions) FILTER (WHERE price_direction='UNCHANGED') AS unchanged_transitions,
        MAX(mean_unit_change) FILTER (WHERE price_direction='UNCHANGED') AS unchanged_mean_unit_change,
        MAX(transitions) FILTER (WHERE price_direction='MISSING_ENDPOINT') AS missing_endpoint_transitions,
        SUM(transitions) AS total_transitions,SUM(unit_difference) AS total_unit_difference
    FROM cells GROUP BY dept_id,series_count
), report_health AS (
    SELECT (SELECT COUNT(*) FROM departments)=7 AND (SELECT COUNT(*) FROM department_roster)=7
        AND NOT EXISTS (SELECT 1 FROM departments WHERE series_count<>expected_series)
        AND (SELECT SUM(series_count) FROM departments)=cfg.expected_items*cfg.expected_stores
        AND (SELECT COUNT(*) FROM cells)=28 AND (SELECT COUNT(*) FROM report)=7
        AND NOT EXISTS (SELECT 1 FROM cells WHERE transitions<>sales_up+sales_down+sales_unchanged
            OR unit_difference<>current_units-previous_units OR distinct_pairs>transitions
            OR distinct_pairs>series_count OR transitions>series_count*(cfg.expected_weeks-1)
            OR (transitions=0 AND (distinct_pairs<>0 OR previous_units<>0 OR current_units<>0 OR unit_difference<>0
                OR mean_unit_change IS NOT NULL OR median_unit_change IS NOT NULL
                OR sales_up_pct IS NOT NULL OR sales_down_pct IS NOT NULL OR sales_unchanged_pct IS NOT NULL))
            OR (transitions>0 AND (distinct_pairs=0 OR mean_unit_change IS NULL OR median_unit_change IS NULL
                OR sales_up_pct IS NULL OR sales_down_pct IS NULL OR sales_unchanged_pct IS NULL)))
        AND NOT EXISTS (SELECT 1 FROM report WHERE total_transitions<>series_count*(cfg.expected_weeks-1)
            OR total_transitions<>price_up_transitions+price_down_transitions+unchanged_transitions+missing_endpoint_transitions)
        AND (SELECT SUM(total_transitions) FROM report)=cfg.expected_items*cfg.expected_stores*(cfg.expected_weeks-1)
        AND (SELECT SUM(total_unit_difference) FROM report)=(SELECT SUM(unit_change) FROM transitions)
        AS passed
    FROM parameters cfg
)
SELECT r.dept_id,r.series_count,r.price_up_transitions,r.price_up_mean_unit_change,
    r.price_down_transitions,r.price_down_mean_unit_change,r.unchanged_transitions,r.unchanged_mean_unit_change,
    r.missing_endpoint_transitions,r.total_transitions,r.total_unit_difference,
    CASE WHEN COALESCE(i.passed AND t.passed AND h.passed,false) THEN 'PASS'
         ELSE error('Department price-sales association blocked: accepted input integrity, adjacent sequence, department roster or report partition failed')
    END AS check_status
FROM input_health i CROSS JOIN transition_health t CROSS JOIN report_health h
LEFT JOIN report r ON true
ORDER BY r.dept_id;
