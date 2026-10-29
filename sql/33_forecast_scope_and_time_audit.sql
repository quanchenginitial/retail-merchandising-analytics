-- Purpose: freeze one retrospective benchmark slice and audit four forecast origins.
-- Select the lexicographically first department and store using dimensions only.
-- Frozen released-catalog scope: FOODS_1 / CA_1, all 216 products, including zero sales.
-- Membership SHA256: sorted item_id|store_id lines, LF separator, no trailing LF.
-- Full training starts at d_1. Read unit fields only for canonical d_1..d_1913 keys.
-- This query computes no forecast, target-unit total, forecast error, price or ABC/XYZ feature.
-- Calendar coverage is not proof of observed target sales or of origin-time active assortment.
-- Validate product/store schemas in full; calendar/daily/raw schemas only for fields used below.
-- Read-only. Four aggregate rows; no product identifiers or individual observations are returned.
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
SELECT o.origin,s.dept_id,s.store_id,t.series_count,o.train_end_day,c.train_end,c.forecast_start,c.forecast_end,
    t.training_rows,t.last7_rows,t.last28_rows,c.forecast_calendar_days,
    CASE WHEN COALESCE(h.passed,false) THEN 'PASS'
         ELSE error('Forecast scope/time audit blocked: schema, frozen membership, mapping, complete training keys or calendar failed') END AS check_status
FROM origins o CROSS JOIN selected_scope s CROSS JOIN audit_health h
LEFT JOIN origin_training t USING(origin_order) LEFT JOIN origin_calendar c USING(origin_order)
ORDER BY o.origin_order;
