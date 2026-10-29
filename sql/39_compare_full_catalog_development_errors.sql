-- Read-only development errors for all 30,490 released-catalog series and both saved candidates.
-- The exact SQL38 validation prefix reconciles all 6,829,760 saved candidate rows first.
-- Full canonical d_1..d_1913 history is audited; final holdout actual values never enter.
-- One narrow LAG plus per-series conditional aggregates computes the three origin-local RMSSE scales.
-- All series contribute to MAE and signed error; macro RMSSE averages only defined individual roots.
-- No sales weighting, epsilon scales, final-holdout scoring or final model selection.
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
, catalog_series AS MATERIALIZED (
    SELECT CAST(ROW_NUMBER() OVER(ORDER BY item_id,store_id) AS INTEGER) AS series_index,item_id,store_id
    FROM selected_series
), full_calendar AS (
    SELECT d,date,day_number,wm_yr_wk FROM calendar CROSS JOIN parameters p
    WHERE day_number BETWEEN 1 AND p.last_input_day
), full_key_health AS (
    -- Read keys/dates, never future units. Malformed extra training-period records must not vanish at joins.
    SELECT COUNT(*) FILTER (WHERE f.date BETWEEN p.first_date AND p.first_date+p.last_input_day-1
        AND NOT COALESCE(regexp_full_match(f.d,'d_[1-9][0-9]*')
            AND TRY_CAST(SUBSTR(f.d,3) AS INTEGER)>0,false))=0 AS passed
    FROM mart.m5_sales_daily f CROSS JOIN parameters p
), full_history AS MATERIALIZED (
    -- LEFT roster join retains unknown/null item/store keys so the NULL-index audit rejects them.
    -- Independently bound the canonical fact key even if a calendar mapping is corrupted.
    SELECT s.series_index,c.day_number,f.units,
        f.date IS NOT DISTINCT FROM c.date AND f.wm_yr_wk IS NOT DISTINCT FROM c.wm_yr_wk AS mapping_valid
    FROM mart.m5_sales_daily f JOIN full_calendar c ON f.d=c.d
    LEFT JOIN catalog_series s USING(item_id,store_id) CROSS JOIN parameters p
    WHERE regexp_full_match(f.d,'d_[1-9][0-9]*')
        AND TRY_CAST(SUBSTR(f.d,3) AS INTEGER) BETWEEN 1 AND p.last_input_day
), history_coverage AS MATERIALIZED (
    SELECT series_index,COUNT(*) AS history_rows,COUNT(DISTINCT day_number) AS distinct_days,
        MIN(day_number) AS first_day,MAX(day_number) AS last_day,
        COUNT(*) FILTER(WHERE series_index IS NULL OR units IS NULL OR units<0 OR NOT mapping_valid) AS invalid_rows
    FROM full_history GROUP BY series_index
), history_health AS (
    SELECT COALESCE((SELECT passed FROM full_key_health),false)
        AND (SELECT COUNT(*) FROM history_coverage)=p.expected_scope_series
        AND NOT EXISTS (SELECT 1 FROM history_coverage WHERE series_index IS NULL OR history_rows<>p.last_input_day
            OR distinct_days<>p.last_input_day OR first_day<>1 OR last_day<>p.last_input_day OR invalid_rows<>0)
        AND (SELECT COUNT(*) FROM full_history)=CAST(p.expected_scope_series AS BIGINT)*p.last_input_day AS passed
    FROM parameters p
), development_origins AS (
    SELECT * FROM origins WHERE origin_order<=3
), persisted_predictions AS MATERIALIZED (
    -- Score the validated persisted candidates; never replace their values with expected forecasts.
    SELECT f.origin,f.model,f.item_id,f.store_id,s.series_index,f.train_end_day,
        f.horizon_day,f.forecast_day,f.forecast_date,CAST(f.predicted_units*4 AS BIGINT) AS predicted_quarters
    FROM saved_forecasts f JOIN development_origins o USING(origin)
    JOIN catalog_series s USING(item_id,store_id)
), joined_errors AS (
    SELECT p.*,t.units AS actual_units,
        CAST(p.predicted_quarters AS HUGEINT)-CAST(t.units AS HUGEINT)*4 AS error_quarters
    FROM persisted_predictions p LEFT JOIN full_history t
        ON t.series_index=p.series_index AND t.day_number=p.forecast_day
), scored_rows AS MATERIALIZED (
    SELECT origin,model,item_id,store_id,horizon_day,forecast_day,forecast_date,actual_units,predicted_quarters,
        error_quarters,abs(error_quarters) AS absolute_error_quarters,
        CAST(error_quarters AS HUGEINT)*CAST(error_quarters AS HUGEINT) AS squared_error_sixteenths
    FROM joined_errors
), global_first_positive AS (
    SELECT series_index,MIN(day_number) FILTER(WHERE units>0) AS first_positive_day
    FROM full_history GROUP BY series_index
), training_lagged AS (
    SELECT series_index,day_number,CAST(units AS HUGEINT)
        -CAST(LAG(units) OVER(PARTITION BY series_index ORDER BY day_number) AS HUGEINT) AS difference
    FROM full_history
), scale_wide AS MATERIALIZED (
    -- One per-series aggregation, not an origin x full-history expansion.
    -- Strictly day>s excludes the initial zero-to-positive jump and retains later zero days.
    SELECT t.series_index,MIN(f.first_positive_day) AS first_positive_day,
        COUNT(*) FILTER(WHERE t.day_number>f.first_positive_day AND t.day_number<=1829) AS count_1,
        COUNT(*) FILTER(WHERE t.day_number>f.first_positive_day AND t.day_number<=1857) AS count_2,
        COUNT(*) FILTER(WHERE t.day_number>f.first_positive_day AND t.day_number<=1885) AS count_3,
        COALESCE(SUM(difference*difference) FILTER(WHERE t.day_number>f.first_positive_day AND t.day_number<=1829),0) AS sse_1,
        COALESCE(SUM(difference*difference) FILTER(WHERE t.day_number>f.first_positive_day AND t.day_number<=1857),0) AS sse_2,
        COALESCE(SUM(difference*difference) FILTER(WHERE t.day_number>f.first_positive_day AND t.day_number<=1885),0) AS sse_3
    FROM training_lagged t JOIN global_first_positive f USING(series_index) GROUP BY t.series_index
), training_scales AS MATERIALIZED (
    SELECT o.origin,o.train_end_day,s.item_id,s.store_id,
        CASE WHEN w.first_positive_day<=o.train_end_day THEN w.first_positive_day ELSE NULL::INTEGER END AS first_positive_day,
        CASE WHEN w.first_positive_day<=o.train_end_day THEN CAST(o.train_end_day-w.first_positive_day AS BIGINT)
            ELSE NULL::BIGINT END AS scale_diff_count,
        CASE o.origin_order WHEN 1 THEN w.count_1 WHEN 2 THEN w.count_2 ELSE w.count_3 END AS observed_scale_differences,
        CASE WHEN w.first_positive_day<=o.train_end_day THEN
            CASE o.origin_order WHEN 1 THEN w.sse_1 WHEN 2 THEN w.sse_2 ELSE w.sse_3 END
            ELSE NULL::HUGEINT END AS training_sse
    FROM scale_wide w JOIN catalog_series s USING(series_index) CROSS JOIN development_origins o
), candidate_health AS (
    SELECT v.passed AND h.passed AS passed FROM validation_health v CROSS JOIN history_health h
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
            OR predicted_quarters IS NULL OR forecast_day>p.last_input_day)
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
         ELSE error('Full catalog development comparison blocked: candidate, source, scoring keys or training scale failed') END AS check_status
FROM development_origins o CROSS JOIN (VALUES ('SNAIVE7'),('WEEKDAY4')) models(model)
CROSS JOIN score_health h LEFT JOIN rounded_report r ON r.origin=o.origin AND r.model=models.model
ORDER BY o.origin_order,models.model;
