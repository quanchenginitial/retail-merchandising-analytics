-- Build unchanged SNAIVE7 and WEEKDAY4 candidates for the complete released catalog.
-- Frozen retrospective product x store roster; all zero-sales series and positions retained.
-- Only canonical d_1802..d_1913 unit fields enter this audit and construction.
-- This verifies recent input coverage, not full training history, RMSSE scales or target coverage.
-- No final target values, forecast errors, model selection, prices or ABC/XYZ features are used.
-- Source roster hashes: sorted UTF-8 pipe-separated fields joined with LF, no trailing LF.
-- All catalog schemas are checked for fields used; product/store schemas are checked in full.
-- Existing pilot tables are untouched. Run the full file once; later run only VALIDATION.
CREATE TABLE mart.m5_forecast_baselines_all_28d AS
WITH parameters AS (
    SELECT 3049 AS expected_products,10 AS expected_stores,1969 AS expected_calendar_days,
        30490 AS expected_scope_series,1802 AS first_input_day,1913 AS last_input_day,
        'dfa7ed458d1aa6d5afa80b9847aa1c0a98d98d06e7c3347acb9881bbb0584114' AS frozen_membership_sha256,
        'c36d6ca2fb1e0555b5a6f150832c1cd7648c7f0a76891ee8fbc88cae9dce6cbf' AS frozen_metadata_sha256,
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
), selected_series AS MATERIALIZED (
    SELECT p.item_id,s.store_id FROM products p CROSS JOIN stores s
), roster_health AS (
    SELECT d.passed
        AND (SELECT COUNT(*) FROM selected_series)=p.expected_scope_series
        AND (SELECT sha256(string_agg(item_id||'|'||store_id,chr(10) ORDER BY item_id,store_id))
             FROM selected_series)=p.frozen_membership_sha256
        AND (SELECT COUNT(*) FROM raw_mapping)=p.expected_scope_series
        AND (SELECT COUNT(DISTINCT (item_id,store_id)) FROM raw_mapping)=p.expected_scope_series
        AND NOT EXISTS (SELECT 1 FROM raw_mapping r
            LEFT JOIN products a USING(item_id) LEFT JOIN stores b USING(store_id)
            WHERE a.item_id IS NULL OR b.store_id IS NULL OR r.dept_id IS DISTINCT FROM a.dept_id
                OR r.cat_id IS DISTINCT FROM a.cat_id OR r.state_id IS DISTINCT FROM b.state_id)
        AND (SELECT sha256(string_agg(item_id||'|'||dept_id||'|'||cat_id||'|'||store_id||'|'||state_id,
            chr(10) ORDER BY item_id,dept_id,cat_id,store_id,state_id)) FROM raw_mapping)=p.frozen_metadata_sha256 AS passed
    FROM dimension_health d CROSS JOIN parameters p
), calendar AS MATERIALIZED (
    SELECT d,date,day_number,wm_yr_wk FROM core.m5_calendar
), calendar_health AS (
    SELECT COUNT(*)=p.expected_calendar_days AND COUNT(DISTINCT d)=p.expected_calendar_days
        AND COUNT(DISTINCT date)=p.expected_calendar_days AND COUNT(DISTINCT day_number)=p.expected_calendar_days
        AND COUNT(*) FILTER (WHERE day_number IS NULL OR day_number NOT BETWEEN 1 AND p.expected_calendar_days
            OR d IS DISTINCT FROM 'd_'||CAST(day_number AS VARCHAR)
            OR date IS DISTINCT FROM p.first_date+TRY_CAST(day_number AS INTEGER)-1 OR wm_yr_wk IS NULL)=0 AS passed
    FROM calendar CROSS JOIN parameters p GROUP BY p.expected_calendar_days
), input_calendar AS MATERIALIZED (
    SELECT c.*,o.origin_order,o.origin,o.train_end_day FROM calendar c
    JOIN origins o ON c.day_number BETWEEN o.train_end_day-27 AND o.train_end_day
), malformed_key_health AS (
    -- Keys/dates only. Canonical days outside the recent window never project unit values.
    SELECT COUNT(*) FILTER (WHERE f.date BETWEEN p.first_date+p.first_input_day-1 AND p.first_date+p.last_input_day-1
        AND NOT COALESCE(regexp_full_match(f.d,'d_[1-9][0-9]*')
            AND TRY_CAST(SUBSTR(f.d,3) AS INTEGER)>0,false))=0 AS passed
    FROM mart.m5_sales_daily f CROSS JOIN parameters p
), recent_inputs AS MATERIALIZED (
    SELECT f.item_id,f.store_id,f.d,f.date,f.wm_yr_wk,f.units,c.day_number,
        c.date AS expected_date,c.wm_yr_wk AS expected_week,c.origin_order,c.origin,c.train_end_day
    FROM mart.m5_sales_daily f JOIN input_calendar c ON f.d=c.d CROSS JOIN parameters p
    WHERE regexp_full_match(f.d,'d_[1-9][0-9]*')
        AND TRY_CAST(SUBSTR(f.d,3) AS INTEGER) BETWEEN p.first_input_day AND p.last_input_day
), input_health AS (
    SELECT COUNT(*)=p.expected_scope_series*112
        AND COUNT(*) FILTER (WHERE f.units IS NULL OR f.units<0 OR s.item_id IS NULL
            OR f.date IS DISTINCT FROM f.expected_date OR f.wm_yr_wk IS DISTINCT FROM f.expected_week)=0 AS passed
    FROM recent_inputs f LEFT JOIN selected_series s USING(item_id,store_id)
    CROSS JOIN parameters p GROUP BY p.expected_scope_series
), series_origin_coverage AS MATERIALIZED (
    SELECT o.origin_order,o.train_end_day,s.item_id,s.store_id,COUNT(f.d) AS input_rows,
        COUNT(DISTINCT f.d) AS distinct_days,MIN(f.day_number) AS first_day,MAX(f.day_number) AS last_day,
        COUNT(f.d) FILTER (WHERE f.day_number>o.train_end_day-7) AS last7_rows
    FROM selected_series s CROSS JOIN origins o
    LEFT JOIN recent_inputs f ON f.item_id=s.item_id AND f.store_id=s.store_id AND f.origin_order=o.origin_order
    GROUP BY o.origin_order,o.train_end_day,s.item_id,s.store_id
), origin_calendar AS (
    SELECT o.origin_order,MAX(c.date) FILTER (WHERE c.day_number=o.train_end_day) AS train_end,
        MIN(c.date) FILTER (WHERE c.day_number>o.train_end_day) AS forecast_start,
        MAX(c.date) FILTER (WHERE c.day_number>o.train_end_day) AS forecast_end,
        COUNT(*) FILTER (WHERE c.day_number>o.train_end_day) AS forecast_calendar_days
    FROM origins o LEFT JOIN calendar c ON c.day_number BETWEEN o.train_end_day AND o.train_end_day+28
    GROUP BY o.origin_order
), audit_health AS (
    SELECT r.passed AND COALESCE((SELECT passed FROM calendar_health),false)
        AND COALESCE((SELECT passed FROM malformed_key_health),false)
        AND COALESCE((SELECT passed FROM input_health),false)
        AND (SELECT COUNT(*) FROM input_calendar)=112
        AND (SELECT COUNT(*) FROM series_origin_coverage)=4*p.expected_scope_series
        AND NOT EXISTS (SELECT 1 FROM series_origin_coverage WHERE input_rows<>28 OR distinct_days<>28
            OR first_day IS DISTINCT FROM train_end_day-27 OR last_day IS DISTINCT FROM train_end_day OR last7_rows<>7)
        AND NOT EXISTS (SELECT 1 FROM origins o JOIN origin_calendar c USING(origin_order)
            WHERE c.forecast_calendar_days<>28 OR c.train_end IS DISTINCT FROM p.first_date+o.train_end_day-1
                OR c.forecast_start IS DISTINCT FROM p.first_date+o.train_end_day
                OR c.forecast_end IS DISTINCT FROM p.first_date+o.train_end_day+27) AS passed
    FROM roster_health r CROSS JOIN parameters p
), weekday_inputs AS MATERIALIZED (
    SELECT origin_order,origin,train_end_day,item_id,store_id,(day_number-(train_end_day-27))%7 AS weekday_offset,
        COUNT(*) AS observations,CAST(SUM(CAST(units AS BIGINT)) AS BIGINT) AS four_units,
        MAX(units) FILTER (WHERE day_number>train_end_day-7) AS last_units
    FROM recent_inputs GROUP BY origin_order,origin,train_end_day,item_id,store_id,weekday_offset
), patterns AS MATERIALIZED (
    SELECT 'SNAIVE7'::VARCHAR AS model,origin_order,origin,train_end_day,item_id,store_id,weekday_offset,
        train_end_day-6+weekday_offset AS source_first_day,train_end_day-6+weekday_offset AS source_last_day,
        1::BIGINT AS source_observations,CAST(last_units AS BIGINT) AS source_units_sum,
        CAST(last_units AS DECIMAL(18,2)) AS predicted_units FROM weekday_inputs
    UNION ALL
    SELECT 'WEEKDAY4',origin_order,origin,train_end_day,item_id,store_id,weekday_offset,
        train_end_day-27+weekday_offset,train_end_day-6+weekday_offset,observations,four_units,
        CAST(CAST(four_units AS DECIMAL(18,0))*CAST('0.25' AS DECIMAL(3,2)) AS DECIMAL(18,2)) FROM weekday_inputs
), expected_forecasts AS MATERIALIZED (
    SELECT w.model,w.origin,w.item_id,w.store_id,w.train_end_day,c.train_end,
        CAST(r.n*7+w.weekday_offset+1 AS INTEGER) AS horizon_day,
        CAST(w.train_end_day+r.n*7+w.weekday_offset+1 AS INTEGER) AS forecast_day,
        CAST(c.train_end+CAST(r.n*7+w.weekday_offset+1 AS INTEGER) AS DATE) AS forecast_date,
        w.source_first_day,w.source_last_day,w.source_observations,w.source_units_sum,w.predicted_units
    FROM patterns w CROSS JOIN range(0,4) r(n) JOIN origin_calendar c USING(origin_order)
), input_totals AS (
    SELECT origin,SUM(CAST(units AS BIGINT)) AS last28_units,
        SUM(CAST(units AS BIGINT)) FILTER (WHERE day_number>train_end_day-7) AS last7_units
    FROM recent_inputs GROUP BY origin
), generation_health AS (
    SELECT a.passed AND (SELECT COUNT(*) FROM weekday_inputs)=4*p.expected_scope_series*7
        AND NOT EXISTS (SELECT 1 FROM weekday_inputs WHERE observations<>4 OR last_units IS NULL)
        AND (SELECT COUNT(*) FROM patterns)=8*p.expected_scope_series*7
        AND NOT EXISTS (SELECT 1 FROM patterns WHERE source_units_sum IS NULL OR source_units_sum<0
            OR predicted_units IS NULL OR predicted_units<0 OR source_last_day>train_end_day
            OR source_first_day<train_end_day-27
            OR (model='SNAIVE7' AND (source_observations<>1 OR source_units_sum>2147483647
                OR predicted_units IS DISTINCT FROM CAST(source_units_sum AS DECIMAL(18,2))))
            OR (model='WEEKDAY4' AND (source_observations<>4 OR source_units_sum>4::BIGINT*2147483647
                OR predicted_units*4 IS DISTINCT FROM CAST(source_units_sum AS DECIMAL(20,2))))) AS passed
    FROM audit_health a CROSS JOIN parameters p
)
SELECT CASE WHEN COALESCE(h.passed,false) THEN f.model
            ELSE error('Full catalog baseline creation blocked: frozen roster, schema, recent inputs or source pattern failed') END AS model,
    f.origin,f.item_id,f.store_id,f.train_end_day,f.train_end,f.horizon_day,f.forecast_day,f.forecast_date,f.source_first_day,f.source_last_day,f.source_observations,f.source_units_sum,f.predicted_units
FROM generation_health h LEFT JOIN expected_forecasts f ON true;

-- VALIDATION: if mart.m5_forecast_baselines_all_28d exists, run only the query below.
-- Reconcile every saved field and row multiplicity, then summarize persisted predictions.
WITH parameters AS (
    SELECT 3049 AS expected_products,10 AS expected_stores,1969 AS expected_calendar_days,
        30490 AS expected_scope_series,1802 AS first_input_day,1913 AS last_input_day,
        'dfa7ed458d1aa6d5afa80b9847aa1c0a98d98d06e7c3347acb9881bbb0584114' AS frozen_membership_sha256,
        'c36d6ca2fb1e0555b5a6f150832c1cd7648c7f0a76891ee8fbc88cae9dce6cbf' AS frozen_metadata_sha256,
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
), selected_series AS MATERIALIZED (
    SELECT p.item_id,s.store_id FROM products p CROSS JOIN stores s
), roster_health AS (
    SELECT d.passed
        AND (SELECT COUNT(*) FROM selected_series)=p.expected_scope_series
        AND (SELECT sha256(string_agg(item_id||'|'||store_id,chr(10) ORDER BY item_id,store_id))
             FROM selected_series)=p.frozen_membership_sha256
        AND (SELECT COUNT(*) FROM raw_mapping)=p.expected_scope_series
        AND (SELECT COUNT(DISTINCT (item_id,store_id)) FROM raw_mapping)=p.expected_scope_series
        AND NOT EXISTS (SELECT 1 FROM raw_mapping r
            LEFT JOIN products a USING(item_id) LEFT JOIN stores b USING(store_id)
            WHERE a.item_id IS NULL OR b.store_id IS NULL OR r.dept_id IS DISTINCT FROM a.dept_id
                OR r.cat_id IS DISTINCT FROM a.cat_id OR r.state_id IS DISTINCT FROM b.state_id)
        AND (SELECT sha256(string_agg(item_id||'|'||dept_id||'|'||cat_id||'|'||store_id||'|'||state_id,
            chr(10) ORDER BY item_id,dept_id,cat_id,store_id,state_id)) FROM raw_mapping)=p.frozen_metadata_sha256 AS passed
    FROM dimension_health d CROSS JOIN parameters p
), calendar AS MATERIALIZED (
    SELECT d,date,day_number,wm_yr_wk FROM core.m5_calendar
), calendar_health AS (
    SELECT COUNT(*)=p.expected_calendar_days AND COUNT(DISTINCT d)=p.expected_calendar_days
        AND COUNT(DISTINCT date)=p.expected_calendar_days AND COUNT(DISTINCT day_number)=p.expected_calendar_days
        AND COUNT(*) FILTER (WHERE day_number IS NULL OR day_number NOT BETWEEN 1 AND p.expected_calendar_days
            OR d IS DISTINCT FROM 'd_'||CAST(day_number AS VARCHAR)
            OR date IS DISTINCT FROM p.first_date+TRY_CAST(day_number AS INTEGER)-1 OR wm_yr_wk IS NULL)=0 AS passed
    FROM calendar CROSS JOIN parameters p GROUP BY p.expected_calendar_days
), input_calendar AS MATERIALIZED (
    SELECT c.*,o.origin_order,o.origin,o.train_end_day FROM calendar c
    JOIN origins o ON c.day_number BETWEEN o.train_end_day-27 AND o.train_end_day
), malformed_key_health AS (
    -- Keys/dates only. Canonical days outside the recent window never project unit values.
    SELECT COUNT(*) FILTER (WHERE f.date BETWEEN p.first_date+p.first_input_day-1 AND p.first_date+p.last_input_day-1
        AND NOT COALESCE(regexp_full_match(f.d,'d_[1-9][0-9]*')
            AND TRY_CAST(SUBSTR(f.d,3) AS INTEGER)>0,false))=0 AS passed
    FROM mart.m5_sales_daily f CROSS JOIN parameters p
), recent_inputs AS MATERIALIZED (
    SELECT f.item_id,f.store_id,f.d,f.date,f.wm_yr_wk,f.units,c.day_number,
        c.date AS expected_date,c.wm_yr_wk AS expected_week,c.origin_order,c.origin,c.train_end_day
    FROM mart.m5_sales_daily f JOIN input_calendar c ON f.d=c.d CROSS JOIN parameters p
    WHERE regexp_full_match(f.d,'d_[1-9][0-9]*')
        AND TRY_CAST(SUBSTR(f.d,3) AS INTEGER) BETWEEN p.first_input_day AND p.last_input_day
), input_health AS (
    SELECT COUNT(*)=p.expected_scope_series*112
        AND COUNT(*) FILTER (WHERE f.units IS NULL OR f.units<0 OR s.item_id IS NULL
            OR f.date IS DISTINCT FROM f.expected_date OR f.wm_yr_wk IS DISTINCT FROM f.expected_week)=0 AS passed
    FROM recent_inputs f LEFT JOIN selected_series s USING(item_id,store_id)
    CROSS JOIN parameters p GROUP BY p.expected_scope_series
), series_origin_coverage AS MATERIALIZED (
    SELECT o.origin_order,o.train_end_day,s.item_id,s.store_id,COUNT(f.d) AS input_rows,
        COUNT(DISTINCT f.d) AS distinct_days,MIN(f.day_number) AS first_day,MAX(f.day_number) AS last_day,
        COUNT(f.d) FILTER (WHERE f.day_number>o.train_end_day-7) AS last7_rows
    FROM selected_series s CROSS JOIN origins o
    LEFT JOIN recent_inputs f ON f.item_id=s.item_id AND f.store_id=s.store_id AND f.origin_order=o.origin_order
    GROUP BY o.origin_order,o.train_end_day,s.item_id,s.store_id
), origin_calendar AS (
    SELECT o.origin_order,MAX(c.date) FILTER (WHERE c.day_number=o.train_end_day) AS train_end,
        MIN(c.date) FILTER (WHERE c.day_number>o.train_end_day) AS forecast_start,
        MAX(c.date) FILTER (WHERE c.day_number>o.train_end_day) AS forecast_end,
        COUNT(*) FILTER (WHERE c.day_number>o.train_end_day) AS forecast_calendar_days
    FROM origins o LEFT JOIN calendar c ON c.day_number BETWEEN o.train_end_day AND o.train_end_day+28
    GROUP BY o.origin_order
), audit_health AS (
    SELECT r.passed AND COALESCE((SELECT passed FROM calendar_health),false)
        AND COALESCE((SELECT passed FROM malformed_key_health),false)
        AND COALESCE((SELECT passed FROM input_health),false)
        AND (SELECT COUNT(*) FROM input_calendar)=112
        AND (SELECT COUNT(*) FROM series_origin_coverage)=4*p.expected_scope_series
        AND NOT EXISTS (SELECT 1 FROM series_origin_coverage WHERE input_rows<>28 OR distinct_days<>28
            OR first_day IS DISTINCT FROM train_end_day-27 OR last_day IS DISTINCT FROM train_end_day OR last7_rows<>7)
        AND NOT EXISTS (SELECT 1 FROM origins o JOIN origin_calendar c USING(origin_order)
            WHERE c.forecast_calendar_days<>28 OR c.train_end IS DISTINCT FROM p.first_date+o.train_end_day-1
                OR c.forecast_start IS DISTINCT FROM p.first_date+o.train_end_day
                OR c.forecast_end IS DISTINCT FROM p.first_date+o.train_end_day+27) AS passed
    FROM roster_health r CROSS JOIN parameters p
), weekday_inputs AS MATERIALIZED (
    SELECT origin_order,origin,train_end_day,item_id,store_id,(day_number-(train_end_day-27))%7 AS weekday_offset,
        COUNT(*) AS observations,CAST(SUM(CAST(units AS BIGINT)) AS BIGINT) AS four_units,
        MAX(units) FILTER (WHERE day_number>train_end_day-7) AS last_units
    FROM recent_inputs GROUP BY origin_order,origin,train_end_day,item_id,store_id,weekday_offset
), patterns AS MATERIALIZED (
    SELECT 'SNAIVE7'::VARCHAR AS model,origin_order,origin,train_end_day,item_id,store_id,weekday_offset,
        train_end_day-6+weekday_offset AS source_first_day,train_end_day-6+weekday_offset AS source_last_day,
        1::BIGINT AS source_observations,CAST(last_units AS BIGINT) AS source_units_sum,
        CAST(last_units AS DECIMAL(18,2)) AS predicted_units FROM weekday_inputs
    UNION ALL
    SELECT 'WEEKDAY4',origin_order,origin,train_end_day,item_id,store_id,weekday_offset,
        train_end_day-27+weekday_offset,train_end_day-6+weekday_offset,observations,four_units,
        CAST(CAST(four_units AS DECIMAL(18,0))*CAST('0.25' AS DECIMAL(3,2)) AS DECIMAL(18,2)) FROM weekday_inputs
), expected_forecasts AS MATERIALIZED (
    SELECT w.model,w.origin,w.item_id,w.store_id,w.train_end_day,c.train_end,
        CAST(r.n*7+w.weekday_offset+1 AS INTEGER) AS horizon_day,
        CAST(w.train_end_day+r.n*7+w.weekday_offset+1 AS INTEGER) AS forecast_day,
        CAST(c.train_end+CAST(r.n*7+w.weekday_offset+1 AS INTEGER) AS DATE) AS forecast_date,
        w.source_first_day,w.source_last_day,w.source_observations,w.source_units_sum,w.predicted_units
    FROM patterns w CROSS JOIN range(0,4) r(n) JOIN origin_calendar c USING(origin_order)
), input_totals AS (
    SELECT origin,SUM(CAST(units AS BIGINT)) AS last28_units,
        SUM(CAST(units AS BIGINT)) FILTER (WHERE day_number>train_end_day-7) AS last7_units
    FROM recent_inputs GROUP BY origin
), generation_health AS (
    SELECT a.passed AND (SELECT COUNT(*) FROM weekday_inputs)=4*p.expected_scope_series*7
        AND NOT EXISTS (SELECT 1 FROM weekday_inputs WHERE observations<>4 OR last_units IS NULL)
        AND (SELECT COUNT(*) FROM patterns)=8*p.expected_scope_series*7
        AND NOT EXISTS (SELECT 1 FROM patterns WHERE source_units_sum IS NULL OR source_units_sum<0
            OR predicted_units IS NULL OR predicted_units<0 OR source_last_day>train_end_day
            OR source_first_day<train_end_day-27
            OR (model='SNAIVE7' AND (source_observations<>1 OR source_units_sum>2147483647
                OR predicted_units IS DISTINCT FROM CAST(source_units_sum AS DECIMAL(18,2))))
            OR (model='WEEKDAY4' AND (source_observations<>4 OR source_units_sum>4::BIGINT*2147483647
                OR predicted_units*4 IS DISTINCT FROM CAST(source_units_sum AS DECIMAL(20,2))))) AS passed
    FROM audit_health a CROSS JOIN parameters p
), expected_saved_schema(column_name,data_type,ordinal_position) AS (
    VALUES ('model','VARCHAR',1),
        ('origin','VARCHAR',2),
        ('item_id','VARCHAR',3),
        ('store_id','VARCHAR',4),
        ('train_end_day','INTEGER',5),
        ('train_end','DATE',6),
        ('horizon_day','INTEGER',7),
        ('forecast_day','INTEGER',8),
        ('forecast_date','DATE',9),
        ('source_first_day','INTEGER',10),
        ('source_last_day','INTEGER',11),
        ('source_observations','BIGINT',12),
        ('source_units_sum','BIGINT',13),
        ('predicted_units','DECIMAL(18,2)',14)
), saved_schema AS (
    SELECT column_name,data_type,ordinal_position FROM information_schema.columns
    WHERE table_catalog=current_database() AND table_schema='mart' AND table_name='m5_forecast_baselines_all_28d'
), saved_schema_errors AS (
    SELECT COUNT(*) AS errors FROM expected_saved_schema e FULL OUTER JOIN saved_schema a USING(column_name)
    WHERE e.column_name IS NULL OR a.column_name IS NULL OR e.data_type IS DISTINCT FROM a.data_type
        OR e.ordinal_position IS DISTINCT FROM a.ordinal_position
), saved_forecasts AS MATERIALIZED (
    SELECT model,origin,item_id,store_id,train_end_day,train_end,horizon_day,forecast_day,forecast_date,source_first_day,source_last_day,source_observations,source_units_sum,predicted_units FROM mart.m5_forecast_baselines_all_28d
), missing_or_changed AS (
    SELECT * FROM expected_forecasts EXCEPT ALL SELECT * FROM saved_forecasts
), extra_or_changed AS (
    SELECT * FROM saved_forecasts EXCEPT ALL SELECT * FROM expected_forecasts
), saved_totals AS (
    SELECT origin,model,COUNT(DISTINCT (item_id,store_id)) AS series_count,COUNT(*) AS forecast_rows,
        MIN(forecast_date) AS forecast_start,MAX(forecast_date) AS forecast_end,
        SUM(predicted_units) AS predicted_units,COUNT(*) FILTER (WHERE predicted_units=0) AS zero_forecast_rows,
        COUNT(*) FILTER (WHERE predicted_units<>TRUNC(predicted_units)) AS fractional_forecast_rows
    FROM saved_forecasts GROUP BY origin,model
), validation_health AS (
    SELECT g.passed AND (SELECT errors FROM saved_schema_errors)=0
        AND (SELECT COUNT(*) FROM saved_forecasts)=8*p.expected_scope_series*28
        AND NOT EXISTS (SELECT 1 FROM missing_or_changed) AND NOT EXISTS (SELECT 1 FROM extra_or_changed)
        AND NOT EXISTS (SELECT 1 FROM origins o CROSS JOIN (VALUES ('SNAIVE7'),('WEEKDAY4')) m(model)
            LEFT JOIN saved_totals s ON s.origin=o.origin AND s.model=m.model LEFT JOIN input_totals i ON i.origin=o.origin
            WHERE s.series_count IS DISTINCT FROM CAST(p.expected_scope_series AS BIGINT)
                OR s.forecast_rows IS DISTINCT FROM CAST(p.expected_scope_series*28 AS BIGINT)
                OR s.predicted_units IS DISTINCT FROM CAST(CASE WHEN m.model='SNAIVE7' THEN i.last7_units*4
                    ELSE i.last28_units END AS DECIMAL(38,2))) AS passed
    FROM generation_health g CROSS JOIN parameters p
)
SELECT o.origin,m.model,s.series_count,s.forecast_rows,s.forecast_start,s.forecast_end,
    CASE WHEN m.model='SNAIVE7' THEN 7 ELSE 28 END AS input_days,
    CASE WHEN m.model='SNAIVE7' THEN i.last7_units ELSE i.last28_units END AS input_units,
    s.predicted_units,s.zero_forecast_rows,s.fractional_forecast_rows,
    CASE WHEN COALESCE(h.passed,false) THEN 'PASS'
        ELSE error('Full catalog baseline validation blocked: input, saved schema, key multiplicity or forecast value failed') END AS check_status
FROM origins o CROSS JOIN (VALUES ('SNAIVE7'),('WEEKDAY4')) m(model) CROSS JOIN validation_health h
LEFT JOIN saved_totals s ON s.origin=o.origin AND s.model=m.model LEFT JOIN input_totals i ON i.origin=o.origin
ORDER BY o.origin_order,m.model;
