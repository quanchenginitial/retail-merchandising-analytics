-- Purpose: inspect twelve-week histories for three deterministic illustrative median-gap cases.
-- Read-only; selection uses all target positions in each frozen candidate class, with exact tie breaks.
-- CASE aliases are labels, not anonymisation. Display contains private case histories; do not publish its rows.
-- LATER observations are retrospective context and never enter the selected target's prior-only baseline.
-- Full 36 x 12 report; no real item/store identifier column is returned.
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
), history AS MATERIALIZED (
    -- Build prior-only frames over the complete twelve-week sequence before choosing targets.
    SELECT *,COUNT(*) OVER prior_four AS history_rows,SUM(units) OVER prior_four AS history_units,
        COUNT(*) FILTER (WHERE units>0) OVER prior_four AS positive_history_weeks,
        MIN(wm_yr_wk) OVER prior_four AS first_history_week,MAX(wm_yr_wk) OVER prior_four AS last_history_week
    FROM weekly WINDOW prior_four AS (
        PARTITION BY item_id,store_id ORDER BY wm_yr_wk ROWS BETWEEN 4 PRECEDING AND 1 PRECEDING)
), features AS MATERIALIZED (
    SELECT *,CAST(history_units*CAST(0.25 AS DECIMAL(3,2)) AS DECIMAL(24,2)) AS baseline_units
    FROM history WHERE wm_yr_wk BETWEEN 11605 AND 11612
), target_coverage AS (
    SELECT item_id,store_id,COUNT(*) AS rows,COUNT(DISTINCT wm_yr_wk) AS weeks
    FROM features GROUP BY item_id,store_id
), history_health AS (
    SELECT (SELECT COUNT(*) FROM history)=cfg.expected_items*cfg.expected_stores*cfg.expected_weeks
        AND (SELECT COUNT(*) FROM features)=cfg.expected_items*cfg.expected_stores*(cfg.expected_weeks-4)
        AND (SELECT COUNT(DISTINCT (item_id,store_id,wm_yr_wk)) FROM features)=
            cfg.expected_items*cfg.expected_stores*(cfg.expected_weeks-4)
        AND (SELECT COUNT(*) FROM target_coverage)=cfg.expected_items*cfg.expected_stores
        AND NOT EXISTS (SELECT 1 FROM target_coverage WHERE rows<>cfg.expected_weeks-4 OR weeks<>cfg.expected_weeks-4)
        AND NOT EXISTS (SELECT 1 FROM features WHERE history_rows<>4 OR history_units IS NULL OR history_units<0
            OR positive_history_weeks NOT BETWEEN 0 AND 4
            OR first_history_week IS DISTINCT FROM wm_yr_wk-4 OR last_history_week IS DISTINCT FROM wm_yr_wk-1
            OR baseline_units IS NULL OR baseline_units*4 IS DISTINCT FROM history_units
            OR (history_units=0) IS DISTINCT FROM (positive_history_weeks=0)) AS passed
    FROM parameters cfg
), classified AS MATERIALIZED (
    SELECT *,4*units-history_units AS unit_difference_x4,
        CASE WHEN units=0 AND positive_history_weeks=4 AND history_units>=28 THEN 'SUDDEN_ZERO'
             WHEN 4*units>=2*history_units AND 4*units-history_units>=28 THEN 'LARGE_INCREASE'
             WHEN 8*units<=history_units AND history_units-4*units>=28 THEN 'LARGE_DECREASE'
             ELSE 'NONE' END AS candidate_class
    FROM features
), case_plan(case_order,case_id,selected_class) AS (
    VALUES (1,'CASE_1','SUDDEN_ZERO'),(2,'CASE_2','LARGE_INCREASE'),(3,'CASE_3','LARGE_DECREASE')
), ranked_candidates AS MATERIALIZED (
    SELECT *,COUNT(*) OVER (PARTITION BY candidate_class) AS pool_rows,
        ROW_NUMBER() OVER (PARTITION BY candidate_class
            ORDER BY ABS(unit_difference_x4),item_id,store_id,wm_yr_wk) AS selection_rank
    FROM classified WHERE candidate_class IN ('SUDDEN_ZERO','LARGE_INCREASE','LARGE_DECREASE')
), selected_cases AS MATERIALIZED (
    SELECT p.case_order,p.case_id,p.selected_class,r.item_id,r.store_id,r.wm_yr_wk AS selected_week,
        r.unit_difference_x4 AS selected_difference_x4,r.pool_rows,r.selection_rank
    FROM case_plan p LEFT JOIN ranked_candidates r
        ON r.candidate_class=p.selected_class AND r.selection_rank=(r.pool_rows+1)//2
), case_history AS MATERIALIZED (
    SELECT s.case_order,s.case_id,s.selected_class,s.item_id,s.store_id,s.selected_week,
        s.selected_difference_x4,s.pool_rows,s.selection_rank,w.wm_yr_wk,w.week_start,
        w.wm_yr_wk-s.selected_week AS relative_week,w.units,c.baseline_units AS rolling_baseline_units,
        c.history_units AS own_history_units,
        CASE WHEN w.wm_yr_wk<11605 THEN 'WARMUP' ELSE c.candidate_class END AS screen_class,
        CASE WHEN w.wm_yr_wk-s.selected_week<-4 THEN 'EARLIER'
             WHEN w.wm_yr_wk-s.selected_week BETWEEN -4 AND -1 THEN 'BASELINE'
             WHEN w.wm_yr_wk=s.selected_week THEN 'TARGET' ELSE 'LATER' END AS context_role,
        w.sell_price,w.has_price
    FROM selected_cases s JOIN weekly w ON w.item_id=s.item_id AND w.store_id=s.store_id
    LEFT JOIN classified c ON c.item_id=w.item_id AND c.store_id=w.store_id AND c.wm_yr_wk=w.wm_yr_wk
), case_coverage AS (
    SELECT case_id,selected_class,COUNT(*) AS context_rows,COUNT(DISTINCT wm_yr_wk) AS weeks,
        MIN(wm_yr_wk) AS first_week,MAX(wm_yr_wk) AS last_week,
        COUNT(*) FILTER (WHERE context_role='BASELINE') AS baseline_rows,
        COUNT(*) FILTER (WHERE context_role='TARGET') AS target_rows,
        COUNT(*) FILTER (WHERE screen_class='WARMUP') AS warmup_rows,
        COUNT(*) FILTER (WHERE wm_yr_wk>=11605) AS eligible_rows,
        SUM(units) FILTER (WHERE context_role='BASELINE') AS baseline_role_units,
        MAX(rolling_baseline_units) FILTER (WHERE context_role='TARGET') AS target_baseline,
        MAX(units) FILTER (WHERE context_role='TARGET') AS target_units,
        MAX(screen_class) FILTER (WHERE context_role='TARGET') AS target_class,
        MAX(selected_difference_x4) AS selected_difference_x4
    FROM case_history GROUP BY case_id,selected_class
), selection_health AS (
    SELECT (SELECT COUNT(*) FROM case_plan)=3
        AND (SELECT COUNT(DISTINCT candidate_class) FROM ranked_candidates)=3
        AND (SELECT COUNT(*) FROM selected_cases)=3
        AND (SELECT COUNT(DISTINCT case_id) FROM selected_cases)=3
        AND (SELECT COUNT(DISTINCT (item_id,store_id,selected_week)) FROM selected_cases)=3
        AND NOT EXISTS (SELECT 1 FROM selected_cases WHERE item_id IS NULL OR store_id IS NULL
            OR selected_week IS NULL OR selected_week NOT BETWEEN 11605 AND 11612
            OR pool_rows IS NULL OR pool_rows<=0 OR selection_rank IS DISTINCT FROM (pool_rows+1)//2)
        AND NOT EXISTS (SELECT 1 FROM selected_cases s LEFT JOIN classified c
            ON c.item_id=s.item_id AND c.store_id=s.store_id AND c.wm_yr_wk=s.selected_week
            WHERE c.candidate_class IS DISTINCT FROM s.selected_class
                OR c.unit_difference_x4 IS DISTINCT FROM s.selected_difference_x4) AS passed
), report_health AS (
    SELECT (SELECT COUNT(*) FROM case_history)=36 AND (SELECT COUNT(*) FROM case_coverage)=3
        AND NOT EXISTS (SELECT 1 FROM case_coverage WHERE context_rows<>12 OR weeks<>12
            OR first_week<>11601 OR last_week<>11612 OR baseline_rows<>4 OR target_rows<>1
            OR warmup_rows<>4 OR eligible_rows<>8 OR target_class IS DISTINCT FROM selected_class
            OR target_baseline*4 IS DISTINCT FROM baseline_role_units
            OR selected_difference_x4 IS DISTINCT FROM 4*target_units-baseline_role_units)
        AND NOT EXISTS (SELECT 1 FROM case_history WHERE
            (wm_yr_wk<11605 AND (rolling_baseline_units IS NOT NULL OR screen_class<>'WARMUP'))
            OR (wm_yr_wk>=11605 AND (rolling_baseline_units IS NULL OR screen_class IS NULL
                OR screen_class NOT IN ('SUDDEN_ZERO','LARGE_INCREASE','LARGE_DECREASE','NONE')
                OR rolling_baseline_units*4 IS DISTINCT FROM own_history_units))
            OR has_price IS DISTINCT FROM (sell_price IS NOT NULL)) AS passed
)
SELECT r.case_id,r.selected_class,CAST(r.wm_yr_wk AS VARCHAR) AS retail_week,r.week_start,
    r.relative_week,r.units,r.rolling_baseline_units,r.screen_class,r.context_role,r.sell_price,r.has_price,
    CASE WHEN COALESCE(i.passed AND h.passed AND s.passed AND c.passed,false) THEN 'PASS'
         ELSE error('Anomaly case histories blocked: accepted inputs, history, nonempty class selection or context coverage failed')
    END AS check_status
FROM input_health i CROSS JOIN history_health h CROSS JOIN selection_health s CROSS JOIN report_health c
LEFT JOIN case_history r ON true
ORDER BY r.case_order,r.wm_yr_wk;
