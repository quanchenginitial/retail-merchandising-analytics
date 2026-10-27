-- Purpose: persist one analysis-ready row per item/store/observed day.
-- Keep missing prices NULL. Zero units have zero estimated sales value, even without price.
-- Positive units require an exact item/store/source-week price. This is a USD value proxy,
-- not transaction revenue, net sales, margin or profit. No imputation or future sales rows.
-- Run the complete file once. No existing table is overwritten; source tables stay unchanged.
CREATE SCHEMA IF NOT EXISTS mart;
CREATE TABLE mart.m5_sales_daily AS
WITH price_health AS MATERIALIZED (
    SELECT COUNT(*)-COUNT(DISTINCT (store_id,item_id,wm_yr_wk)) AS key_errors,
        COUNT(*) FILTER (WHERE NULLIF(TRIM(store_id),'') IS NULL
            OR NULLIF(TRIM(item_id),'') IS NULL OR wm_yr_wk IS NULL OR wm_yr_wk<=0
            OR typeof(sell_price)<>'DECIMAL(18,2)' OR sell_price IS NULL
            OR NOT isfinite(sell_price) OR sell_price<=0) AS invalid_rows
    FROM stg.m5_prices
), calendar_health AS MATERIALIZED (
    SELECT COUNT(*)-COUNT(DISTINCT d) AS key_errors,
        COUNT(*)-COUNT(DISTINCT "date") AS date_errors,
        COUNT(*) FILTER (WHERE wm_yr_wk IS NULL OR wm_yr_wk<=0 OR "date" IS NULL
            OR NOT COALESCE(regexp_full_match(d,'d_[1-9][0-9]*')
                AND day_number BETWEEN 1 AND 1969
                AND day_number=TRY_CAST(SUBSTR(d,3) AS INTEGER)
                AND day_number=date_diff('day',DATE '2011-01-29',"date")+1,false)) AS invalid_rows
    FROM core.m5_calendar
), guarded_prices AS MATERIALIZED (
    SELECT p.store_id,p.item_id,p.sell_price,
        CASE WHEN h.key_errors=0 AND h.invalid_rows=0 THEN p.wm_yr_wk
             ELSE error('Price table requires unique complete keys and positive DECIMAL(18,2) prices') END AS wm_yr_wk
    FROM stg.m5_prices p CROSS JOIN price_health h
), guarded_calendar AS MATERIALIZED (
    SELECT CASE WHEN h.key_errors=0 AND h.date_errors=0 AND h.invalid_rows=0 THEN c.d
             ELSE error('Calendar requires unique canonical day/date keys and valid source weeks') END AS d,
        c."date",c.wm_yr_wk
    FROM core.m5_calendar c CROSS JOIN calendar_health h
), product_keys AS MATERIALIZED (
    SELECT item_id,COUNT(*) AS matches FROM core.m5_product GROUP BY item_id
), store_keys AS MATERIALIZED (
    SELECT store_id,COUNT(*) AS matches FROM core.m5_store GROUP BY store_id
), enriched AS (
    SELECT s.item_id,s.store_id,s.d,c."date",c.wm_yr_wk,
        CASE WHEN NULLIF(TRIM(s.item_id),'') IS NOT NULL AND NULLIF(TRIM(s.store_id),'') IS NOT NULL
                  AND typeof(s.units)='INTEGER' AND s.units IS NOT NULL AND s.units>=0
                  AND COALESCE(regexp_full_match(s.d,'d_[1-9][0-9]*')
                      AND TRY_CAST(SUBSTR(s.d,3) AS INTEGER) BETWEEN 1 AND 1941,false)
                  AND c.d IS NOT NULL AND pk.matches=1 AND sk.matches=1
             THEN s.units ELSE error('Sales require valid identifiers, nonnegative INTEGER units and one matching product/store/calendar')
        END AS units,p.sell_price,p.wm_yr_wk IS NOT NULL AS has_price
    FROM stg.m5_sales_daily s
    LEFT JOIN guarded_calendar c ON s.d=c.d
    LEFT JOIN guarded_prices p ON s.item_id=p.item_id AND s.store_id=p.store_id AND c.wm_yr_wk=p.wm_yr_wk
    LEFT JOIN product_keys pk ON s.item_id=pk.item_id
    LEFT JOIN store_keys sk ON s.store_id=sk.store_id
)
SELECT item_id,store_id,d,"date",wm_yr_wk,units,sell_price,has_price,
    CASE WHEN units=0 THEN CAST(0 AS DECIMAL(28,2))
         WHEN has_price THEN CAST(CAST(units AS DECIMAL(20,0))*sell_price AS DECIMAL(28,2))
         ELSE error('Positive sales require an exact weekly price before value can be estimated')
    END AS estimated_sales_value
FROM enriched;

-- VALIDATION: if mart.m5_sales_daily already exists, run only the query below.
-- Two complete, ordered series lists compare every source daily units value exactly.
-- Prices are independently rejoined via calendar.d, never via the fact's own week field.
-- Row count plus a 1..1941 bitmap proves each item/store/day occurs exactly once.
WITH expected_schema(column_name,data_type,ordinal_position) AS (
    VALUES ('item_id','VARCHAR',1),('store_id','VARCHAR',2),('d','VARCHAR',3),
        ('date','DATE',4),('wm_yr_wk','INTEGER',5),('units','INTEGER',6),
        ('sell_price','DECIMAL(18,2)',7),('has_price','BOOLEAN',8),
        ('estimated_sales_value','DECIMAL(28,2)',9)
), actual_schema AS (
    SELECT column_name,data_type,ordinal_position FROM information_schema.columns
    WHERE table_catalog=current_database() AND table_schema='mart' AND table_name='m5_sales_daily'
), schema_errors AS (
    SELECT COUNT(*) AS error_count FROM expected_schema e FULL OUTER JOIN actual_schema a USING (column_name)
    WHERE e.column_name IS NULL OR a.column_name IS NULL OR e.data_type IS DISTINCT FROM a.data_type
       OR e.ordinal_position IS DISTINCT FROM a.ordinal_position
), price_health AS MATERIALIZED (
    SELECT COUNT(*)-COUNT(DISTINCT (store_id,item_id,wm_yr_wk)) AS key_errors,
        COUNT(*) FILTER (WHERE NULLIF(TRIM(store_id),'') IS NULL
            OR NULLIF(TRIM(item_id),'') IS NULL OR wm_yr_wk IS NULL OR wm_yr_wk<=0
            OR typeof(sell_price)<>'DECIMAL(18,2)' OR sell_price IS NULL
            OR NOT isfinite(sell_price) OR sell_price<=0) AS invalid_rows
    FROM stg.m5_prices
), calendar_health AS MATERIALIZED (
    SELECT COUNT(*)-COUNT(DISTINCT d) AS key_errors,
        COUNT(*)-COUNT(DISTINCT "date") AS date_errors,
        COUNT(*) FILTER (WHERE wm_yr_wk IS NULL OR wm_yr_wk<=0 OR "date" IS NULL
            OR NOT COALESCE(regexp_full_match(d,'d_[1-9][0-9]*')
                AND day_number BETWEEN 1 AND 1969
                AND day_number=TRY_CAST(SUBSTR(d,3) AS INTEGER)
                AND day_number=date_diff('day',DATE '2011-01-29',"date")+1,false)) AS invalid_rows
    FROM core.m5_calendar
), guarded_prices AS MATERIALIZED (
    SELECT p.store_id,p.item_id,p.sell_price,
        CASE WHEN h.key_errors=0 AND h.invalid_rows=0 THEN p.wm_yr_wk
             ELSE error('Price table requires unique complete keys and positive DECIMAL(18,2) prices') END AS wm_yr_wk
    FROM stg.m5_prices p CROSS JOIN price_health h
), guarded_calendar AS MATERIALIZED (
    SELECT CASE WHEN h.key_errors=0 AND h.date_errors=0 AND h.invalid_rows=0 THEN c.d
             ELSE error('Calendar requires unique canonical day/date keys and valid source weeks') END AS d,
        c."date",c.wm_yr_wk
    FROM core.m5_calendar c CROSS JOIN calendar_health h
), product_keys AS MATERIALIZED (
    SELECT item_id,COUNT(*) AS matches FROM core.m5_product GROUP BY item_id
), store_keys AS MATERIALIZED (
    SELECT store_id,COUNT(*) AS matches FROM core.m5_store GROUP BY store_id
), source_numbered AS NOT MATERIALIZED (
    SELECT *,TRY_CAST(SUBSTR(d,3) AS INTEGER) AS day_number,
        COALESCE(regexp_full_match(d,'d_[1-9][0-9]*')
            AND TRY_CAST(SUBSTR(d,3) AS INTEGER) BETWEEN 1 AND 1941,false) AS valid_day
    FROM stg.m5_sales_daily
), source_series AS MATERIALIZED (
    SELECT item_id,store_id,COUNT(*) AS row_count,
        COUNT(*) FILTER (WHERE NOT valid_day OR units IS NULL OR units<0 OR typeof(units)<>'INTEGER'
            OR NULLIF(TRIM(item_id),'') IS NULL OR NULLIF(TRIM(store_id),'') IS NULL) AS invalid_rows,
        bit_count(bitstring_agg(CASE WHEN valid_day THEN day_number END,1,1941)) AS covered_days,
        list(units ORDER BY day_number) AS daily_units
    FROM source_numbered GROUP BY item_id,store_id
), fact_numbered AS NOT MATERIALIZED (
    SELECT *,TRY_CAST(SUBSTR(d,3) AS INTEGER) AS day_number,
        COALESCE(regexp_full_match(d,'d_[1-9][0-9]*')
            AND TRY_CAST(SUBSTR(d,3) AS INTEGER) BETWEEN 1 AND 1941,false) AS valid_day
    FROM mart.m5_sales_daily
), fact_checked AS NOT MATERIALIZED (
    SELECT f.*,
        c.d IS NULL OR f."date" IS DISTINCT FROM c."date"
            OR f.wm_yr_wk IS DISTINCT FROM c.wm_yr_wk AS calendar_error,
        f.sell_price IS DISTINCT FROM p.sell_price AS price_error,
        f.has_price IS DISTINCT FROM (p.wm_yr_wk IS NOT NULL) AS flag_error,
        f.estimated_sales_value IS DISTINCT FROM
            CASE WHEN f.units=0 THEN CAST(0 AS DECIMAL(28,2))
                 WHEN f.units>0 AND p.wm_yr_wk IS NOT NULL
                 THEN CAST(CAST(TRY_CAST(f.units AS INTEGER) AS DECIMAL(20,0))*p.sell_price AS DECIMAL(28,2))
                 ELSE NULL END AS amount_error
    FROM fact_numbered f
    LEFT JOIN guarded_calendar c ON f.d=c.d
    LEFT JOIN guarded_prices p ON f.item_id=p.item_id AND f.store_id=p.store_id AND c.wm_yr_wk=p.wm_yr_wk
), fact_series AS MATERIALIZED (
    SELECT item_id,store_id,COUNT(*) AS row_count,SUM(units) AS total_units,
        COUNT(*) FILTER (WHERE units=0) AS zero_rows,
        COUNT(*) FILTER (WHERE sell_price IS NOT NULL) AS priced_rows,
        COUNT(*) FILTER (WHERE sell_price IS NULL AND units=0) AS missing_price_zero_rows,
        COUNT(*) FILTER (WHERE sell_price IS NULL AND units>0) AS missing_price_positive_rows,
        COUNT(*) FILTER (WHERE NULLIF(TRIM(item_id),'') IS NULL OR NULLIF(TRIM(store_id),'') IS NULL
            OR d IS NULL OR "date" IS NULL OR wm_yr_wk IS NULL OR units IS NULL
            OR has_price IS NULL OR estimated_sales_value IS NULL) AS missing_core_rows,
        COUNT(*) FILTER (WHERE NOT valid_day OR units<0 OR estimated_sales_value<0
            OR (sell_price IS NOT NULL AND (NOT isfinite(sell_price) OR sell_price<=0))) AS invalid_rows,
        bit_count(bitstring_agg(CASE WHEN valid_day THEN day_number END,1,1941)) AS covered_days,
        list(units ORDER BY day_number) AS daily_units,
        COUNT(*) FILTER (WHERE calendar_error) AS calendar_errors,
        COUNT(*) FILTER (WHERE price_error) AS price_errors,
        COUNT(*) FILTER (WHERE flag_error) AS flag_errors,
        COUNT(*) FILTER (WHERE amount_error) AS amount_errors,
        SUM(estimated_sales_value) AS estimated_sales_value
    FROM fact_checked GROUP BY item_id,store_id
), totals AS (
    SELECT COALESCE(SUM(row_count),0) AS row_count,COALESCE(SUM(total_units),0) AS total_units,
        COALESCE(SUM(zero_rows),0) AS zero_rows,COALESCE(SUM(priced_rows),0) AS priced_rows,
        COALESCE(SUM(missing_price_zero_rows),0) AS missing_price_zero_rows,
        COALESCE(SUM(missing_price_positive_rows),0) AS missing_price_positive_rows,
        COALESCE(SUM(missing_core_rows),0) AS missing_core_rows,COALESCE(SUM(invalid_rows),0) AS invalid_rows,
        COUNT(*) AS series_count,
        COUNT(*) FILTER (WHERE row_count<>1941 OR covered_days IS DISTINCT FROM 1941) AS key_coverage_errors,
        COALESCE(SUM(calendar_errors),0) AS calendar_errors,COALESCE(SUM(price_errors),0) AS price_errors,
        COALESCE(SUM(flag_errors),0) AS flag_errors,COALESCE(SUM(amount_errors),0) AS amount_errors,
        SUM(estimated_sales_value) AS estimated_sales_value
    FROM fact_series
), source_errors AS (
    SELECT COUNT(*) AS error_count FROM source_series
    WHERE row_count<>1941 OR covered_days IS DISTINCT FROM 1941 OR invalid_rows<>0
), source_only AS (
    SELECT item_id,store_id FROM source_series EXCEPT SELECT item_id,store_id FROM fact_series
), fact_only AS (
    SELECT item_id,store_id FROM fact_series EXCEPT SELECT item_id,store_id FROM source_series
), unit_errors AS (
    SELECT COUNT(*) AS error_count FROM source_series s JOIN fact_series f USING (item_id,store_id)
    WHERE s.daily_units IS DISTINCT FROM f.daily_units
), dimension_errors AS (
    SELECT COUNT(*) AS error_count FROM fact_series f
    LEFT JOIN product_keys p ON f.item_id=p.item_id LEFT JOIN store_keys s ON f.store_id=s.store_id
    WHERE p.matches IS DISTINCT FROM 1 OR s.matches IS DISTINCT FROM 1
), checks AS (
    SELECT 1 AS check_order,'fact_rows' AS check_name,row_count::VARCHAR AS actual,'59181090' AS expected FROM totals
    UNION ALL SELECT 2,'column_count',COUNT(*)::VARCHAR,'9' FROM actual_schema
    UNION ALL SELECT 3,'schema_mismatch_count',error_count::VARCHAR,'0' FROM schema_errors
    UNION ALL SELECT 4,'total_units',total_units::VARCHAR,'66927173' FROM totals
    UNION ALL SELECT 5,'zero_sales_rows',zero_rows::VARCHAR,'40241819' FROM totals
    UNION ALL SELECT 6,'priced_daily_rows',priced_rows::VARCHAR,'46881677' FROM totals
    UNION ALL SELECT 7,'missing_price_zero_rows',missing_price_zero_rows::VARCHAR,'12299413' FROM totals
    UNION ALL SELECT 8,'missing_price_positive_rows',missing_price_positive_rows::VARCHAR,'0' FROM totals
    UNION ALL SELECT 9,'missing_core_rows',missing_core_rows::VARCHAR,'0' FROM totals
    UNION ALL SELECT 10,'invalid_fact_rows',invalid_rows::VARCHAR,'0' FROM totals
    UNION ALL SELECT 11,'fact_series_count',series_count::VARCHAR,'30490' FROM totals
    UNION ALL SELECT 12,'fact_key_coverage_errors',key_coverage_errors::VARCHAR,'0' FROM totals
    UNION ALL SELECT 13,'source_key_coverage_errors',error_count::VARCHAR,'0' FROM source_errors
    UNION ALL SELECT 14,'series_set_difference_rows',((SELECT COUNT(*) FROM source_only)+(SELECT COUNT(*) FROM fact_only))::VARCHAR,'0'
    UNION ALL SELECT 15,'units_mismatch_series',error_count::VARCHAR,'0' FROM unit_errors
    UNION ALL SELECT 16,'dimension_key_errors',error_count::VARCHAR,'0' FROM dimension_errors
    UNION ALL SELECT 17,'calendar_field_mismatches',calendar_errors::VARCHAR,'0' FROM totals
    UNION ALL SELECT 18,'price_field_mismatches',price_errors::VARCHAR,'0' FROM totals
    UNION ALL SELECT 19,'coverage_flag_mismatches',flag_errors::VARCHAR,'0' FROM totals
    UNION ALL SELECT 20,'amount_mismatches',amount_errors::VARCHAR,'0' FROM totals
    UNION ALL SELECT 21,'total_estimated_sales_value',estimated_sales_value::VARCHAR,'observed' FROM totals
)
SELECT check_order,check_name,actual,expected,
    CASE WHEN check_order=21 AND EXISTS (SELECT 1 FROM checks c WHERE c.check_order<=20
             AND c.actual IS DISTINCT FROM c.expected) THEN 'INCOMPLETE'
         WHEN check_order=21 THEN 'INFO'
         WHEN actual=expected THEN 'PASS' ELSE 'FAIL' END AS status
FROM checks ORDER BY check_order;
