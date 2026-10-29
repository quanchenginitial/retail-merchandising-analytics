-- Purpose: compare the two saved baseline candidates on the three prespecified development origins only.
-- Read-only: validate all saved fields for both candidates, then score their persisted development predictions.
-- Error = forecast - actual. MAE/bias give equal weight to all 216*28 positions per origin/model.
-- RMSSE uses first positive training day s and squared successive differences from s+1 through T.
-- No positive history, fewer than two retained days or zero scale gives NULL, never epsilon.
-- Macro RMSSE is the mean of individual valid-series RMSSE values; undefined series remain in MAE/bias.
-- Integer quarters and HUGEINT squares preserve exact error diagnostics; DOUBLE is used only for RMSSE roots.
-- Final-holdout candidates may be validated from training inputs, but final-holdout actuals are not read or scored.
-- No sales weighting, official WRMSSE, MAPE, accuracy claim or final model selection is implied.
WITH parameters AS (
    SELECT 3049 AS expected_products,10 AS expected_stores,1969 AS expected_calendar_days,
        216 AS expected_scope_series,1913 AS maximum_training_day,
        'FOODS_1'::VARCHAR AS frozen_department,'CA_1'::VARCHAR AS frozen_store,
        '6cabe9ae29616ce129fdf89fb02fec1cffd31ccb8194c4694b8bdf0ed85e622f'::VARCHAR AS frozen_membership_sha256,
        DATE '2011-01-29' AS first_date
), origins(origin_order,origin,train_end_day) AS (
    VALUES (1,'DEVELOPMENT_1',1829),(2,'DEVELOPMENT_2',1857),
        (3,'DEVELOPMENT_3',1885),(4,'FINAL_HOLDOUT',1913)
), required_schema(table_schema,table_name,column_name,data_type) AS (
    VALUES ('core','m5_product','item_id','VARCHAR'),('core','m5_product','dept_id','VARCHAR'),
        ('core','m5_product','cat_id','VARCHAR'),('core','m5_store','store_id','VARCHAR'),
        ('core','m5_store','state_id','VARCHAR'),('core','m5_calendar','d','VARCHAR'),
        ('core','m5_calendar','date','DATE'),('core','m5_calendar','day_number','INTEGER'),
        ('core','m5_calendar','wm_yr_wk','INTEGER'),('mart','m5_sales_daily','item_id','VARCHAR'),
        ('mart','m5_sales_daily','store_id','VARCHAR'),('mart','m5_sales_daily','d','VARCHAR'),
        ('mart','m5_sales_daily','date','DATE'),('mart','m5_sales_daily','wm_yr_wk','INTEGER'),
        ('mart','m5_sales_daily','units','INTEGER'),('raw','m5_sales_wide','item_id','VARCHAR'),
        ('raw','m5_sales_wide','dept_id','VARCHAR'),('raw','m5_sales_wide','cat_id','VARCHAR'),
        ('raw','m5_sales_wide','store_id','VARCHAR'),('raw','m5_sales_wide','state_id','VARCHAR')
), actual_schema AS (
    SELECT c.table_schema,c.table_name,c.column_name,c.data_type
    FROM information_schema.columns c
    WHERE c.table_catalog=current_database() AND (
        (c.table_schema='core' AND c.table_name IN ('m5_product','m5_store'))
        OR EXISTS (SELECT 1 FROM required_schema r WHERE r.table_schema=c.table_schema
            AND r.table_name=c.table_name AND r.column_name=c.column_name))
), schema_errors AS (
    SELECT COUNT(*) AS errors FROM required_schema r FULL OUTER JOIN actual_schema a
        USING(table_schema,table_name,column_name)
    WHERE r.column_name IS NULL OR a.column_name IS NULL OR r.data_type IS DISTINCT FROM a.data_type
), products AS MATERIALIZED (
    SELECT item_id,dept_id,cat_id FROM core.m5_product
), stores AS MATERIALIZED (
    SELECT store_id,state_id FROM core.m5_store
), raw_mapping AS MATERIALIZED (
    -- Metadata projection only: no raw day-unit columns enter the scope rule.
    SELECT item_id,dept_id,cat_id,store_id,state_id FROM raw.m5_sales_wide
), raw_products AS (
    SELECT DISTINCT item_id,dept_id,cat_id FROM raw_mapping
), raw_stores AS (
    SELECT DISTINCT store_id,state_id FROM raw_mapping
), product_source_only AS (
    SELECT * FROM raw_products EXCEPT ALL SELECT * FROM products
), product_dimension_only AS (
    SELECT * FROM products EXCEPT ALL SELECT * FROM raw_products
), store_source_only AS (
    SELECT * FROM raw_stores EXCEPT ALL SELECT * FROM stores
), store_dimension_only AS (
    SELECT * FROM stores EXCEPT ALL SELECT * FROM raw_stores
), dimension_health AS (
    SELECT (SELECT errors FROM schema_errors)=0
        AND (SELECT COUNT(*) FROM products)=p.expected_products
        AND (SELECT COUNT(DISTINCT item_id) FROM products)=p.expected_products
        AND (SELECT COUNT(*) FROM stores)=p.expected_stores
        AND (SELECT COUNT(DISTINCT store_id) FROM stores)=p.expected_stores
        AND NOT EXISTS (SELECT 1 FROM products WHERE NOT COALESCE(
            regexp_full_match(item_id,'[A-Z0-9_]+') AND regexp_full_match(dept_id,'[A-Z0-9_]+')
            AND regexp_full_match(cat_id,'[A-Z0-9_]+'),false))
        AND NOT EXISTS (SELECT 1 FROM stores WHERE NOT COALESCE(
            regexp_full_match(store_id,'[A-Z0-9_]+') AND regexp_full_match(state_id,'[A-Z0-9_]+'),false))
        AND NOT EXISTS (SELECT dept_id FROM products GROUP BY dept_id HAVING COUNT(DISTINCT cat_id)<>1)
        AND NOT EXISTS (SELECT 1 FROM product_source_only) AND NOT EXISTS (SELECT 1 FROM product_dimension_only)
        AND NOT EXISTS (SELECT 1 FROM store_source_only) AND NOT EXISTS (SELECT 1 FROM store_dimension_only) AS passed
    FROM parameters p
), selected_scope AS (
    SELECT (SELECT MIN(dept_id) FROM products) AS dept_id,(SELECT MIN(store_id) FROM stores) AS store_id
), selected_series AS MATERIALIZED (
    SELECT p.item_id,s.store_id FROM products p CROSS JOIN selected_scope s WHERE p.dept_id=s.dept_id
), selected_source_pairs AS (
    SELECT r.item_id,r.store_id,COUNT(*) AS source_rows
    FROM raw_mapping r JOIN selected_series s USING(item_id,store_id) GROUP BY r.item_id,r.store_id
), membership AS (
    SELECT COUNT(*) AS series_count,
        sha256(string_agg(item_id||'|'||store_id,chr(10) ORDER BY item_id,store_id)) AS membership_sha256
    FROM selected_series
), scope_health AS (
    SELECT d.passed AND s.dept_id=p.frozen_department AND s.store_id=p.frozen_store
        AND m.series_count=p.expected_scope_series AND m.membership_sha256=p.frozen_membership_sha256
        AND (SELECT COUNT(*) FROM selected_source_pairs)=m.series_count
        AND NOT EXISTS (SELECT 1 FROM selected_source_pairs WHERE source_rows<>1) AS passed
    FROM dimension_health d CROSS JOIN selected_scope s CROSS JOIN parameters p CROSS JOIN membership m
), calendar AS MATERIALIZED (
    SELECT d,date,day_number,wm_yr_wk FROM core.m5_calendar
), calendar_health AS (
    SELECT COUNT(*)=p.expected_calendar_days AND COUNT(DISTINCT d)=p.expected_calendar_days
        AND COUNT(DISTINCT date)=p.expected_calendar_days AND COUNT(DISTINCT day_number)=p.expected_calendar_days
        AND COUNT(*) FILTER (WHERE day_number IS NULL OR day_number NOT BETWEEN 1 AND p.expected_calendar_days
            OR d IS DISTINCT FROM 'd_'||CAST(day_number AS VARCHAR)
            OR date IS DISTINCT FROM p.first_date+TRY_CAST(day_number AS INTEGER)-1 OR wm_yr_wk IS NULL)=0 AS passed
    FROM calendar CROSS JOIN parameters p GROUP BY p.expected_calendar_days
), training_calendar AS MATERIALIZED (
    SELECT c.* FROM calendar c CROSS JOIN parameters p WHERE c.day_number BETWEEN 1 AND p.maximum_training_day
), training_key_health AS (
    -- Keys/dates only: an extra malformed training-period record must not disappear at the calendar join.
    -- Canonical future keys remain outside training even if their dates or units are deliberately altered.
    SELECT COUNT(*) FILTER (WHERE f.date BETWEEN p.first_date AND p.first_date+p.maximum_training_day-1
        AND NOT COALESCE(regexp_full_match(f.d,'d_[1-9][0-9]*')
            AND TRY_CAST(SUBSTR(f.d,3) AS INTEGER)>0,false))=0 AS passed
    FROM mart.m5_sales_daily f JOIN selected_series s USING(item_id,store_id) CROSS JOIN parameters p
), selected_training AS MATERIALIZED (
    -- Joining canonical training keys bounds the unit projection before the origin rollups.
    -- Dates and retail weeks are then checked against those same calendar keys.
    SELECT f.item_id,f.store_id,f.d,f.date,f.wm_yr_wk,f.units,c.day_number,
        c.date AS expected_date,c.wm_yr_wk AS expected_week
    FROM mart.m5_sales_daily f JOIN selected_series s USING(item_id,store_id)
    JOIN training_calendar c ON f.d=c.d CROSS JOIN parameters p
    WHERE regexp_full_match(f.d,'d_[1-9][0-9]*')
        AND TRY_CAST(SUBSTR(f.d,3) AS INTEGER) BETWEEN 1 AND p.maximum_training_day
), training_health AS (
    SELECT COUNT(*)=p.expected_scope_series*p.maximum_training_day
        AND COUNT(*) FILTER (WHERE units IS NULL OR units<0
            OR date IS DISTINCT FROM expected_date OR wm_yr_wk IS DISTINCT FROM expected_week)=0 AS passed
    FROM selected_training CROSS JOIN parameters p GROUP BY p.expected_scope_series,p.maximum_training_day
), series_origin_coverage AS MATERIALIZED (
    SELECT o.origin_order,o.train_end_day,s.item_id,s.store_id,COUNT(f.d) AS training_rows,
        COUNT(DISTINCT f.d) AS distinct_days,COUNT(DISTINCT f.date) AS distinct_dates,
        MIN(f.day_number) AS first_day,MAX(f.day_number) AS last_day,
        COUNT(f.d) FILTER (WHERE f.day_number>o.train_end_day-7) AS last7_rows,
        COUNT(f.d) FILTER (WHERE f.day_number>o.train_end_day-28) AS last28_rows
    FROM selected_series s CROSS JOIN origins o
    LEFT JOIN selected_training f ON f.item_id=s.item_id AND f.store_id=s.store_id AND f.day_number<=o.train_end_day
    GROUP BY o.origin_order,o.train_end_day,s.item_id,s.store_id
), origin_calendar AS (
    SELECT o.origin_order,MAX(c.date) FILTER (WHERE c.day_number=o.train_end_day) AS train_end,
        MIN(c.date) FILTER (WHERE c.day_number>o.train_end_day) AS forecast_start,
        MAX(c.date) FILTER (WHERE c.day_number>o.train_end_day) AS forecast_end,
        COUNT(*) FILTER (WHERE c.day_number>o.train_end_day) AS forecast_calendar_days
    FROM origins o LEFT JOIN calendar c ON c.day_number BETWEEN o.train_end_day AND o.train_end_day+28
    GROUP BY o.origin_order
), origin_training AS (
    SELECT origin_order,COUNT(*) AS series_count,SUM(training_rows) AS training_rows,
        SUM(last7_rows) AS last7_rows,SUM(last28_rows) AS last28_rows
    FROM series_origin_coverage GROUP BY origin_order
), audit_health AS (
    SELECT s.passed AND COALESCE((SELECT passed FROM calendar_health),false)
        AND COALESCE((SELECT passed FROM training_key_health),false)
        AND COALESCE((SELECT passed FROM training_health),false)
        AND (SELECT COUNT(*) FROM series_origin_coverage)=4*p.expected_scope_series
        AND NOT EXISTS (SELECT 1 FROM series_origin_coverage WHERE training_rows<>train_end_day
            OR distinct_days<>train_end_day OR distinct_dates<>train_end_day
            OR first_day IS DISTINCT FROM 1 OR last_day IS DISTINCT FROM train_end_day
            OR last7_rows<>7 OR last28_rows<>28)
        AND NOT EXISTS (SELECT 1 FROM origins o JOIN origin_calendar c USING(origin_order)
            WHERE c.forecast_calendar_days<>28 OR c.train_end IS DISTINCT FROM p.first_date+o.train_end_day-1
                OR c.forecast_start IS DISTINCT FROM p.first_date+o.train_end_day
                OR c.forecast_end IS DISTINCT FROM p.first_date+o.train_end_day+27) AS passed
    FROM scope_health s CROSS JOIN parameters p
)
, s7_forecast_inputs AS MATERIALIZED (
    SELECT o.origin,o.train_end_day,t.item_id,t.store_id,t.day_number,t.units
    FROM origins o JOIN selected_training t ON t.day_number BETWEEN o.train_end_day-6 AND o.train_end_day
), s7_forecast_grid AS MATERIALIZED (
    SELECT 'SNAIVE7'::VARCHAR AS model,o.origin,s.dept_id,k.item_id,k.store_id,o.train_end_day,
        p.first_date+o.train_end_day-1 AS train_end,CAST(h AS INTEGER) AS horizon_day,
        o.train_end_day+CAST(h AS INTEGER) AS forecast_day,
        o.train_end_day-6+CAST((h-1)%7 AS INTEGER) AS source_day
    FROM selected_series k CROSS JOIN origins o CROSS JOIN selected_scope s
    CROSS JOIN parameters p CROSS JOIN range(1,29) horizons(h)
), s7_expected_forecasts AS MATERIALIZED (
    SELECT g.model,g.origin,g.dept_id,g.item_id,g.store_id,g.train_end_day,g.train_end,g.horizon_day,
        g.forecast_day,c.date AS forecast_date,g.source_day,t.date AS source_date,t.units AS predicted_units
    FROM s7_forecast_grid g LEFT JOIN selected_training t
        ON t.item_id=g.item_id AND t.store_id=g.store_id AND t.day_number=g.source_day
    LEFT JOIN calendar c ON c.day_number=g.forecast_day
), s7_last7_totals AS (
    SELECT origin,COUNT(*) AS source_rows,SUM(units) AS last7_units FROM s7_forecast_inputs GROUP BY origin
), s7_expected_forecast_totals AS (
    SELECT origin,COUNT(DISTINCT (item_id,store_id)) AS series_count,COUNT(*) AS forecast_rows,
        MIN(forecast_date) AS forecast_start,MAX(forecast_date) AS forecast_end,
        SUM(predicted_units) AS predicted_units,COUNT(*) FILTER (WHERE predicted_units=0) AS zero_forecast_rows
    FROM s7_expected_forecasts GROUP BY origin
), s7_generation_health AS (
    SELECT ah.passed AND (SELECT COUNT(*) FROM s7_expected_forecasts)=4*p.expected_scope_series*28
        AND (SELECT COUNT(DISTINCT (model,origin,item_id,store_id,horizon_day)) FROM s7_expected_forecasts)=4*p.expected_scope_series*28
        AND NOT EXISTS (SELECT 1 FROM s7_expected_forecasts
            WHERE predicted_units IS NULL OR predicted_units<0 OR horizon_day NOT BETWEEN 1 AND 28
                OR source_day NOT BETWEEN train_end_day-6 AND train_end_day
                OR source_date IS DISTINCT FROM p.first_date+source_day-1 OR source_date>train_end
                OR forecast_day IS DISTINCT FROM train_end_day+horizon_day
                OR forecast_date IS DISTINCT FROM p.first_date+forecast_day-1 OR forecast_date<=train_end)
        AND NOT EXISTS (SELECT 1 FROM origins o LEFT JOIN s7_expected_forecast_totals f USING(origin)
            LEFT JOIN s7_last7_totals l USING(origin)
            WHERE f.series_count IS DISTINCT FROM CAST(p.expected_scope_series AS BIGINT)
                OR f.forecast_rows IS DISTINCT FROM CAST(p.expected_scope_series*28 AS BIGINT)
                OR l.source_rows IS DISTINCT FROM CAST(p.expected_scope_series*7 AS BIGINT)
                OR f.predicted_units IS DISTINCT FROM 4*l.last7_units) AS passed
    FROM audit_health ah CROSS JOIN parameters p
)
, s7_forecast_schema(column_name,data_type,ordinal_position) AS (
    VALUES ('model','VARCHAR',1),('origin','VARCHAR',2),('dept_id','VARCHAR',3),('item_id','VARCHAR',4),
        ('store_id','VARCHAR',5),('train_end_day','INTEGER',6),('train_end','DATE',7),('horizon_day','INTEGER',8),
        ('forecast_day','INTEGER',9),('forecast_date','DATE',10),('source_day','INTEGER',11),
        ('source_date','DATE',12),('predicted_units','INTEGER',13)
), s7_forecast_actual_schema AS (
    SELECT column_name,data_type,ordinal_position FROM information_schema.columns
    WHERE table_catalog=current_database() AND table_schema='mart' AND table_name='m5_forecast_snaive7_28d'
), s7_forecast_schema_errors AS (
    SELECT COUNT(*) AS errors FROM s7_forecast_schema e FULL OUTER JOIN s7_forecast_actual_schema a USING(column_name)
    WHERE e.column_name IS NULL OR a.column_name IS NULL OR e.data_type IS DISTINCT FROM a.data_type
        OR e.ordinal_position IS DISTINCT FROM a.ordinal_position
), s7_actual_forecasts AS MATERIALIZED (
    SELECT model,origin,dept_id,item_id,store_id,train_end_day,train_end,horizon_day,
        forecast_day,forecast_date,source_day,source_date,predicted_units FROM mart.m5_forecast_snaive7_28d
), s7_expected_only AS (
    SELECT * FROM s7_expected_forecasts EXCEPT ALL SELECT * FROM s7_actual_forecasts
), s7_actual_only AS (
    SELECT * FROM s7_actual_forecasts EXCEPT ALL SELECT * FROM s7_expected_forecasts
), s7_forecast_validation_health AS (
    SELECT g.passed AND se.errors=0 AND (SELECT COUNT(*) FROM s7_forecast_actual_schema)=13
        AND (SELECT COUNT(*) FROM s7_actual_forecasts)=4*p.expected_scope_series*28
        AND (SELECT COUNT(DISTINCT (model,origin,item_id,store_id,horizon_day)) FROM s7_actual_forecasts)=4*p.expected_scope_series*28
        AND NOT EXISTS (SELECT 1 FROM s7_expected_only) AND NOT EXISTS (SELECT 1 FROM s7_actual_only) AS passed
    FROM s7_generation_health g CROSS JOIN s7_forecast_schema_errors se CROSS JOIN parameters p
)
, w4_weekday_source_grid AS MATERIALIZED (
    SELECT o.origin,o.train_end_day,s.item_id,s.store_id,CAST(r AS INTEGER) AS weekday_offset,
        o.train_end_day-27+CAST(r AS INTEGER)+7*CAST(k AS INTEGER) AS source_day
    FROM selected_series s CROSS JOIN origins o CROSS JOIN range(0,7) offsets(r) CROSS JOIN range(0,4) observations(k)
), w4_weekday_means AS MATERIALIZED (
    SELECT g.origin,g.train_end_day,g.item_id,g.store_id,g.weekday_offset,
        MIN(g.source_day) AS source_first_day,MAX(g.source_day) AS source_last_day,
        COUNT(t.d) AS source_observations,CAST(SUM(CAST(t.units AS BIGINT)) AS BIGINT) AS source_units_sum,
        CAST(CAST(SUM(CAST(t.units AS BIGINT)) AS DECIMAL(18,0))*CAST('0.25' AS DECIMAL(3,2)) AS DECIMAL(18,2)) AS predicted_units
    FROM w4_weekday_source_grid g LEFT JOIN selected_training t
        ON t.item_id=g.item_id AND t.store_id=g.store_id AND t.day_number=g.source_day
    GROUP BY g.origin,g.train_end_day,g.item_id,g.store_id,g.weekday_offset
), w4_forecast_grid AS MATERIALIZED (
    SELECT 'WEEKDAY4'::VARCHAR AS model,o.origin,s.dept_id,k.item_id,k.store_id,o.train_end_day,
        p.first_date+o.train_end_day-1 AS train_end,CAST(h AS INTEGER) AS horizon_day,
        o.train_end_day+CAST(h AS INTEGER) AS forecast_day,CAST((h-1)%7 AS INTEGER) AS weekday_offset
    FROM selected_series k CROSS JOIN origins o CROSS JOIN selected_scope s
    CROSS JOIN parameters p CROSS JOIN range(1,29) horizons(h)
), w4_expected_forecasts AS MATERIALIZED (
    SELECT g.model,g.origin,g.dept_id,g.item_id,g.store_id,g.train_end_day,g.train_end,g.horizon_day,
        g.forecast_day,c.date AS forecast_date,w.source_first_day,w.source_last_day,
        w.source_observations,w.source_units_sum,w.predicted_units
    FROM w4_forecast_grid g LEFT JOIN w4_weekday_means w
        ON w.origin=g.origin AND w.item_id=g.item_id AND w.store_id=g.store_id AND w.weekday_offset=g.weekday_offset
    LEFT JOIN calendar c ON c.day_number=g.forecast_day
), w4_last28_totals AS (
    SELECT o.origin,COUNT(*) AS source_rows,SUM(t.units) AS last28_units
    FROM origins o JOIN selected_training t ON t.day_number BETWEEN o.train_end_day-27 AND o.train_end_day
    GROUP BY o.origin
), w4_expected_forecast_totals AS (
    SELECT origin,COUNT(DISTINCT (item_id,store_id)) AS series_count,COUNT(*) AS forecast_rows,
        MIN(forecast_date) AS forecast_start,MAX(forecast_date) AS forecast_end,SUM(predicted_units) AS predicted_units,
        COUNT(*) FILTER (WHERE predicted_units=0) AS zero_forecast_rows,
        COUNT(*) FILTER (WHERE predicted_units<>TRUNC(predicted_units)) AS fractional_forecast_rows
    FROM w4_expected_forecasts GROUP BY origin
), w4_generation_health AS (
    SELECT ah.passed AND (SELECT COUNT(*) FROM w4_weekday_means)=4*p.expected_scope_series*7
        AND (SELECT COUNT(*) FROM w4_expected_forecasts)=4*p.expected_scope_series*28
        AND (SELECT COUNT(DISTINCT (model,origin,item_id,store_id,horizon_day)) FROM w4_expected_forecasts)=4*p.expected_scope_series*28
        AND NOT EXISTS (SELECT 1 FROM w4_expected_forecasts
            WHERE predicted_units IS NULL OR predicted_units<0 OR source_observations IS DISTINCT FROM 4::BIGINT
                OR source_units_sum IS NULL OR source_units_sum NOT BETWEEN 0 AND 4::BIGINT*2147483647
                OR predicted_units*4 IS DISTINCT FROM CAST(source_units_sum AS DECIMAL(20,2))
                OR horizon_day NOT BETWEEN 1 AND 28
                OR source_first_day IS DISTINCT FROM train_end_day-27+(horizon_day-1)%7
                OR source_last_day IS DISTINCT FROM train_end_day-6+(horizon_day-1)%7
                OR source_last_day-source_first_day<>21 OR source_last_day>train_end_day
                OR forecast_day IS DISTINCT FROM train_end_day+horizon_day
                OR forecast_date IS DISTINCT FROM p.first_date+forecast_day-1 OR forecast_date<=train_end)
        AND NOT EXISTS (SELECT 1 FROM origins o LEFT JOIN w4_expected_forecast_totals f USING(origin)
            LEFT JOIN w4_last28_totals l USING(origin)
            WHERE f.series_count IS DISTINCT FROM CAST(p.expected_scope_series AS BIGINT)
                OR f.forecast_rows IS DISTINCT FROM CAST(p.expected_scope_series*28 AS BIGINT)
                OR l.source_rows IS DISTINCT FROM CAST(p.expected_scope_series*28 AS BIGINT)
                OR f.predicted_units IS DISTINCT FROM CAST(l.last28_units AS DECIMAL(38,2))) AS passed
    FROM audit_health ah CROSS JOIN parameters p
)
, w4_forecast_schema(column_name,data_type,ordinal_position) AS (
    VALUES ('model','VARCHAR',1),('origin','VARCHAR',2),('dept_id','VARCHAR',3),('item_id','VARCHAR',4),
        ('store_id','VARCHAR',5),('train_end_day','INTEGER',6),('train_end','DATE',7),('horizon_day','INTEGER',8),
        ('forecast_day','INTEGER',9),('forecast_date','DATE',10),('source_first_day','INTEGER',11),
        ('source_last_day','INTEGER',12),('source_observations','BIGINT',13),('source_units_sum','BIGINT',14),
        ('predicted_units','DECIMAL(18,2)',15)
), w4_forecast_actual_schema AS (
    SELECT column_name,data_type,ordinal_position FROM information_schema.columns
    WHERE table_catalog=current_database() AND table_schema='mart' AND table_name='m5_forecast_weekday4_28d'
), w4_forecast_schema_errors AS (
    SELECT COUNT(*) AS errors FROM w4_forecast_schema e FULL OUTER JOIN w4_forecast_actual_schema a USING(column_name)
    WHERE e.column_name IS NULL OR a.column_name IS NULL OR e.data_type IS DISTINCT FROM a.data_type
        OR e.ordinal_position IS DISTINCT FROM a.ordinal_position
), w4_actual_forecasts AS MATERIALIZED (
    SELECT model,origin,dept_id,item_id,store_id,train_end_day,train_end,horizon_day,forecast_day,forecast_date,source_first_day,source_last_day,source_observations,source_units_sum,predicted_units FROM mart.m5_forecast_weekday4_28d
), w4_expected_only AS (
    SELECT * FROM w4_expected_forecasts EXCEPT ALL SELECT * FROM w4_actual_forecasts
), w4_actual_only AS (
    SELECT * FROM w4_actual_forecasts EXCEPT ALL SELECT * FROM w4_expected_forecasts
), w4_forecast_validation_health AS (
    SELECT g.passed AND se.errors=0 AND (SELECT COUNT(*) FROM w4_forecast_actual_schema)=15
        AND (SELECT COUNT(*) FROM w4_actual_forecasts)=4*p.expected_scope_series*28
        AND (SELECT COUNT(DISTINCT (model,origin,item_id,store_id,horizon_day)) FROM w4_actual_forecasts)=4*p.expected_scope_series*28
        AND NOT EXISTS (SELECT 1 FROM w4_expected_only) AND NOT EXISTS (SELECT 1 FROM w4_actual_only) AS passed
    FROM w4_generation_health g CROSS JOIN w4_forecast_schema_errors se CROSS JOIN parameters p
)
, candidate_health AS (
    SELECT s.passed AND w.passed AS passed FROM s7_forecast_validation_health s CROSS JOIN w4_forecast_validation_health w
), development_origins AS (
    SELECT * FROM origins WHERE origin_order<=3
), persisted_predictions AS MATERIALIZED (
    -- Score the validated saved rows, not replacements from the expected-value CTEs.
    SELECT f.origin,f.model,f.item_id,f.store_id,f.train_end_day,f.horizon_day,f.forecast_day,f.forecast_date,
        CAST(f.predicted_units AS BIGINT)*4 AS predicted_quarters
    FROM s7_actual_forecasts f JOIN development_origins o USING(origin)
    UNION ALL
    SELECT f.origin,f.model,f.item_id,f.store_id,f.train_end_day,f.horizon_day,f.forecast_day,f.forecast_date,
        CAST(f.predicted_units*4 AS BIGINT) AS predicted_quarters
    FROM w4_actual_forecasts f JOIN development_origins o USING(origin)
), joined_errors AS MATERIALIZED (
    SELECT p.*,t.units AS actual_units,
        CAST(p.predicted_quarters AS HUGEINT)-CAST(t.units AS HUGEINT)*4 AS error_quarters
    FROM persisted_predictions p LEFT JOIN selected_training t
        ON t.item_id=p.item_id AND t.store_id=p.store_id AND t.day_number=p.forecast_day
), scored_rows AS MATERIALIZED (
    SELECT origin,model,item_id,store_id,horizon_day,forecast_day,forecast_date,actual_units,predicted_quarters,
        error_quarters,abs(error_quarters) AS absolute_error_quarters,
        CAST(error_quarters AS HUGEINT)*CAST(error_quarters AS HUGEINT) AS squared_error_sixteenths
    FROM joined_errors
), training_lagged AS MATERIALIZED (
    SELECT item_id,store_id,day_number,CAST(units AS BIGINT) AS units,
        LAG(CAST(units AS BIGINT)) OVER(PARTITION BY item_id,store_id ORDER BY day_number) AS previous_units
    FROM selected_training
), training_first_positive AS MATERIALIZED (
    SELECT o.origin,o.train_end_day,s.item_id,s.store_id,
        MIN(t.day_number) FILTER(WHERE t.units>0) AS first_positive_day
    FROM development_origins o CROSS JOIN selected_series s
    LEFT JOIN selected_training t ON t.item_id=s.item_id AND t.store_id=s.store_id AND t.day_number<=o.train_end_day
    GROUP BY o.origin,o.train_end_day,s.item_id,s.store_id
), training_scales AS MATERIALIZED (
    -- Start differences strictly AFTER first positive s: do not include the initial zero-to-positive jump.
    -- Later zero days remain in the retained history. Count is T-s, not positive-day count.
    SELECT f.origin,f.train_end_day,f.item_id,f.store_id,f.first_positive_day,
        CASE WHEN f.first_positive_day IS NULL THEN NULL::BIGINT
             ELSE CAST(f.train_end_day-f.first_positive_day AS BIGINT) END AS scale_diff_count,
        COUNT(t.day_number) AS observed_scale_differences,
        CASE WHEN f.first_positive_day IS NULL THEN NULL::HUGEINT ELSE COALESCE(SUM(
            (CAST(t.units AS HUGEINT)-CAST(t.previous_units AS HUGEINT))
            *(CAST(t.units AS HUGEINT)-CAST(t.previous_units AS HUGEINT))),0) END AS training_sse
    FROM training_first_positive f LEFT JOIN training_lagged t
        ON t.item_id=f.item_id AND t.store_id=f.store_id
        AND t.day_number>f.first_positive_day AND t.day_number<=f.train_end_day
    GROUP BY f.origin,f.train_end_day,f.item_id,f.store_id,f.first_positive_day
), series_errors AS MATERIALIZED (
    SELECT origin,model,item_id,store_id,COUNT(*) AS evaluated_rows,SUM(actual_units) AS actual_units,
        SUM(CAST(predicted_quarters AS HUGEINT)) AS predicted_quarters,
        SUM(absolute_error_quarters) AS absolute_error_quarters,SUM(error_quarters) AS error_quarters,
        SUM(squared_error_sixteenths) AS squared_error_sixteenths
    FROM scored_rows GROUP BY origin,model,item_id,store_id
), diagnostic_status AS MATERIALIZED (
    SELECT e.origin,e.model,e.item_id,e.store_id,t.train_end_day,t.first_positive_day,t.scale_diff_count,t.training_sse,
        e.evaluated_rows,e.actual_units,e.predicted_quarters,e.absolute_error_quarters,e.error_quarters,e.squared_error_sixteenths,
        CASE WHEN t.first_positive_day IS NULL THEN 'no_positive_training'
             WHEN t.scale_diff_count<1 THEN 'insufficient_retained_history'
             WHEN t.training_sse=0 THEN 'zero_scale' ELSE 'VALID' END AS rmsse_status
    FROM series_errors e JOIN training_scales t USING(origin,item_id,store_id)
), series_diagnostics AS MATERIALIZED (
    SELECT d.*,CASE WHEN rmsse_status='VALID' THEN sqrt(
        (CAST(squared_error_sixteenths AS DOUBLE)*CAST(scale_diff_count AS DOUBLE))
        /(16.0*28.0*CAST(training_sse AS DOUBLE))) ELSE NULL::DOUBLE END AS rmsse
    FROM diagnostic_status d
), score_health AS (
    SELECT c.passed AND (SELECT COUNT(*) FROM persisted_predictions)=3*2*p.expected_scope_series*28
        AND (SELECT COUNT(*) FROM scored_rows)=3*2*p.expected_scope_series*28
        AND (SELECT COUNT(DISTINCT (origin,model,item_id,store_id,horizon_day)) FROM scored_rows)=3*2*p.expected_scope_series*28
        AND NOT EXISTS (SELECT 1 FROM scored_rows WHERE actual_units IS NULL OR actual_units<0
            OR predicted_quarters IS NULL OR forecast_day>p.maximum_training_day)
        AND (SELECT COUNT(*) FROM training_scales)=3*p.expected_scope_series
        AND NOT EXISTS (SELECT 1 FROM training_scales WHERE
            (first_positive_day IS NULL AND (scale_diff_count IS NOT NULL OR training_sse IS NOT NULL OR observed_scale_differences<>0))
            OR (first_positive_day IS NOT NULL AND (observed_scale_differences IS DISTINCT FROM scale_diff_count
                OR scale_diff_count<0 OR training_sse IS NULL OR training_sse<0)))
        AND (SELECT COUNT(*) FROM series_diagnostics)=3*2*p.expected_scope_series
        AND NOT EXISTS (SELECT 1 FROM series_diagnostics WHERE evaluated_rows<>28
            OR (rmsse_status='VALID' AND (rmsse IS NULL OR NOT isfinite(rmsse) OR rmsse<0))
            OR (rmsse_status<>'VALID' AND rmsse IS NOT NULL)) AS passed
    FROM candidate_health c CROSS JOIN parameters p
), report_totals AS MATERIALIZED (
    SELECT origin,model,COUNT(*) AS series_count,SUM(evaluated_rows) AS evaluated_rows,
        SUM(actual_units) AS actual_units,SUM(predicted_quarters) AS predicted_quarters,
        SUM(absolute_error_quarters) AS absolute_error_quarters,SUM(error_quarters) AS error_quarters,
        COUNT(*) FILTER(WHERE rmsse_status='VALID') AS rmsse_valid_series,
        COUNT(*) FILTER(WHERE rmsse_status<>'VALID') AS rmsse_undefined_series,
        AVG(rmsse) AS macro_rmsse
    FROM series_diagnostics GROUP BY origin,model
), rounded_report AS (
    SELECT r.*,
        -- Exact integer half-away-from-zero rounding of rational unit errors to six decimals.
        CAST(CAST((2*absolute_error_quarters*1000000+4*evaluated_rows)//(8*evaluated_rows)
            AS DECIMAL(20,0))*CAST('0.000001' AS DECIMAL(7,6)) AS DECIMAL(24,6)) AS mae,
        CAST(CAST((2*abs(error_quarters)*1000000+4*evaluated_rows)//(8*evaluated_rows)
            AS DECIMAL(20,0))*CAST('0.000001' AS DECIMAL(7,6))
            *CASE WHEN error_quarters<0 THEN -1 ELSE 1 END AS DECIMAL(24,6)) AS mean_error
    FROM report_totals r
)
-- REPORT: development aggregates only. No final-holdout actual, forecast errors or selection decision.
SELECT r.origin,r.model,r.series_count,r.evaluated_rows,r.actual_units,
    CAST(CAST(r.predicted_quarters AS DECIMAL(20,0))*CAST('0.25' AS DECIMAL(3,2)) AS DECIMAL(26,2)) AS predicted_units,
    r.mae,r.mean_error,r.rmsse_valid_series,r.rmsse_undefined_series,
    CAST(ROUND(r.macro_rmsse,6) AS DECIMAL(24,6)) AS macro_rmsse,
    CASE WHEN COALESCE(h.passed,false) THEN 'PASS'
         ELSE error('Development error comparison blocked: candidate, source, scoring keys or training scale failed') END AS check_status
FROM development_origins o CROSS JOIN (VALUES ('SNAIVE7'),('WEEKDAY4')) models(model)
CROSS JOIN score_health h LEFT JOIN rounded_report r ON r.origin=o.origin AND r.model=models.model
ORDER BY o.origin_order,models.model;
