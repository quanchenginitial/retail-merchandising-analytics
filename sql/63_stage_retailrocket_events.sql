-- Run once in the existing retail_merchandising connection.
-- Purpose: type event identifiers/timestamps while preserving every observation.
-- Original integer timestamps are retained; no date, timezone, session or order inference.
-- Repeated tuples stay repeated. No deduplication, trimming or identity normalization.
CREATE SCHEMA IF NOT EXISTS rr_stg;

CREATE TABLE rr_stg.events AS
WITH expected_counts AS (
    SELECT 2756101::BIGINT AS expected_rows,2664312::BIGINT AS expected_views,
        69332::BIGINT AS expected_carts,22457::BIGINT AS expected_transactions,
        2733644::BIGINT AS expected_null_ids,460::BIGINT AS expected_duplicate_surplus
), raw_schema AS (
    SELECT CASE WHEN COUNT(*)=5 AND COUNT(*) FILTER (WHERE data_type='VARCHAR')=5
        AND COUNT(*) FILTER (WHERE column_name IS DISTINCT FROM
            CASE ordinal_position WHEN 1 THEN 'timestamp' WHEN 2 THEN 'visitorid'
                WHEN 3 THEN 'event' WHEN 4 THEN 'itemid' WHEN 5 THEN 'transactionid' END)=0
        THEN 0 ELSE 1 END AS raw_schema_mismatch
    FROM information_schema.columns
    WHERE table_catalog=current_database() AND table_schema='rr_raw' AND table_name='events'
), source_rows AS MATERIALIZED (
    SELECT CAST(timestamp AS VARCHAR) AS timestamp,CAST(visitorid AS VARCHAR) AS visitorid,
        CAST(event AS VARCHAR) AS event,CAST(itemid AS VARCHAR) AS itemid,
        CAST(transactionid AS VARCHAR) AS transactionid
    FROM rr_raw.events
), source_health AS (
    SELECT COUNT(*) AS raw_rows,
        COUNT(*) FILTER (WHERE event='view') AS raw_views,
        COUNT(*) FILTER (WHERE event='addtocart') AS raw_carts,
        COUNT(*) FILTER (WHERE event='transaction') AS raw_transactions,
        COUNT(*) FILTER (WHERE transactionid IS NULL) AS raw_null_ids,
        COUNT(*)-COUNT(DISTINCT (timestamp,visitorid,event,itemid,transactionid)) AS raw_duplicate_surplus,
        COUNT(*) FILTER (WHERE NOT COALESCE(
            regexp_full_match(timestamp,'[0-9]+')
            AND TRY_CAST(timestamp AS BIGINT) IS NOT NULL
            AND CAST(TRY_CAST(timestamp AS BIGINT) AS VARCHAR)=timestamp
            AND regexp_full_match(visitorid,'[0-9]+')
            AND TRY_CAST(visitorid AS BIGINT) IS NOT NULL
            AND CAST(TRY_CAST(visitorid AS BIGINT) AS VARCHAR)=visitorid
            AND regexp_full_match(itemid,'[0-9]+')
            AND TRY_CAST(itemid AS BIGINT) IS NOT NULL
            AND CAST(TRY_CAST(itemid AS BIGINT) AS VARCHAR)=itemid
            AND (transactionid IS NULL OR (
                regexp_full_match(transactionid,'[0-9]+')
                AND TRY_CAST(transactionid AS BIGINT) IS NOT NULL
                AND CAST(TRY_CAST(transactionid AS BIGINT) AS VARCHAR)=transactionid))
            AND event IN ('view','addtocart','transaction')
            AND ((event='transaction' AND transactionid IS NOT NULL)
                OR (event<>'transaction' AND transactionid IS NULL)),false)) AS raw_value_violations
    FROM source_rows
), input_guard AS (
    SELECT s.*,h.*,e.*,COALESCE(s.raw_schema_mismatch=0
        AND h.raw_rows=e.expected_rows AND h.raw_rows>0
        AND h.raw_views=e.expected_views AND h.raw_carts=e.expected_carts
        AND h.raw_transactions=e.expected_transactions AND h.raw_null_ids=e.expected_null_ids
        AND h.raw_duplicate_surplus=e.expected_duplicate_surplus
        AND h.raw_value_violations=0,false) AS valid_input
    FROM raw_schema s CROSS JOIN source_health h CROSS JOIN expected_counts e
)
SELECT CASE WHEN g.valid_input THEN CAST(r.timestamp AS BIGINT)
            ELSE error('SQL63 raw event contract failed; destination was not created') END AS timestamp,
       CASE WHEN g.valid_input THEN CAST(r.visitorid AS BIGINT)
            ELSE error('SQL63 raw event contract failed; destination was not created') END AS visitorid,
       CASE WHEN g.valid_input THEN CAST(r.event AS VARCHAR)
            ELSE error('SQL63 raw event contract failed; destination was not created') END AS event,
       CASE WHEN g.valid_input THEN CAST(r.itemid AS BIGINT)
            ELSE error('SQL63 raw event contract failed; destination was not created') END AS itemid,
       CASE WHEN g.valid_input THEN CAST(r.transactionid AS BIGINT)
            ELSE error('SQL63 raw event contract failed; destination was not created') END AS transactionid
FROM input_guard g LEFT JOIN source_rows r ON true;

-- CHECKS: if rr_stg.events already exists, run only the query below.
WITH expected_counts AS (
    SELECT 2756101::BIGINT AS expected_rows,2664312::BIGINT AS expected_views,
        69332::BIGINT AS expected_carts,22457::BIGINT AS expected_transactions,
        2733644::BIGINT AS expected_null_ids,460::BIGINT AS expected_duplicate_surplus
), raw_schema AS (
    SELECT CASE WHEN COUNT(*)=5 AND COUNT(*) FILTER (WHERE data_type='VARCHAR')=5
        AND COUNT(*) FILTER (WHERE column_name IS DISTINCT FROM
            CASE ordinal_position WHEN 1 THEN 'timestamp' WHEN 2 THEN 'visitorid'
                WHEN 3 THEN 'event' WHEN 4 THEN 'itemid' WHEN 5 THEN 'transactionid' END)=0
        THEN 0 ELSE 1 END AS raw_schema_mismatch
    FROM information_schema.columns
    WHERE table_catalog=current_database() AND table_schema='rr_raw' AND table_name='events'
), source_rows AS MATERIALIZED (
    SELECT CAST(timestamp AS VARCHAR) AS timestamp,CAST(visitorid AS VARCHAR) AS visitorid,
        CAST(event AS VARCHAR) AS event,CAST(itemid AS VARCHAR) AS itemid,
        CAST(transactionid AS VARCHAR) AS transactionid
    FROM rr_raw.events
), source_health AS (
    SELECT COUNT(*) AS raw_rows,
        COUNT(*) FILTER (WHERE event='view') AS raw_views,
        COUNT(*) FILTER (WHERE event='addtocart') AS raw_carts,
        COUNT(*) FILTER (WHERE event='transaction') AS raw_transactions,
        COUNT(*) FILTER (WHERE transactionid IS NULL) AS raw_null_ids,
        COUNT(*)-COUNT(DISTINCT (timestamp,visitorid,event,itemid,transactionid)) AS raw_duplicate_surplus,
        COUNT(*) FILTER (WHERE NOT COALESCE(
            regexp_full_match(timestamp,'[0-9]+')
            AND TRY_CAST(timestamp AS BIGINT) IS NOT NULL
            AND CAST(TRY_CAST(timestamp AS BIGINT) AS VARCHAR)=timestamp
            AND regexp_full_match(visitorid,'[0-9]+')
            AND TRY_CAST(visitorid AS BIGINT) IS NOT NULL
            AND CAST(TRY_CAST(visitorid AS BIGINT) AS VARCHAR)=visitorid
            AND regexp_full_match(itemid,'[0-9]+')
            AND TRY_CAST(itemid AS BIGINT) IS NOT NULL
            AND CAST(TRY_CAST(itemid AS BIGINT) AS VARCHAR)=itemid
            AND (transactionid IS NULL OR (
                regexp_full_match(transactionid,'[0-9]+')
                AND TRY_CAST(transactionid AS BIGINT) IS NOT NULL
                AND CAST(TRY_CAST(transactionid AS BIGINT) AS VARCHAR)=transactionid))
            AND event IN ('view','addtocart','transaction')
            AND ((event='transaction' AND transactionid IS NOT NULL)
                OR (event<>'transaction' AND transactionid IS NULL)),false)) AS raw_value_violations
    FROM source_rows
), input_guard AS (
    SELECT s.*,h.*,e.*,COALESCE(s.raw_schema_mismatch=0
        AND h.raw_rows=e.expected_rows AND h.raw_rows>0
        AND h.raw_views=e.expected_views AND h.raw_carts=e.expected_carts
        AND h.raw_transactions=e.expected_transactions AND h.raw_null_ids=e.expected_null_ids
        AND h.raw_duplicate_surplus=e.expected_duplicate_surplus
        AND h.raw_value_violations=0,false) AS valid_input
    FROM raw_schema s CROSS JOIN source_health h CROSS JOIN expected_counts e
), expected_schema(column_name,data_type,ordinal_position) AS (
    VALUES ('timestamp','BIGINT',1),('visitorid','BIGINT',2),('event','VARCHAR',3),
        ('itemid','BIGINT',4),('transactionid','BIGINT',5)
), staging_columns AS (
    SELECT column_name,data_type,ordinal_position FROM information_schema.columns
    WHERE table_catalog=current_database() AND table_schema='rr_stg' AND table_name='events'
), schema_stats AS (
    SELECT COUNT(*) FILTER (WHERE e.column_name IS DISTINCT FROM s.column_name
        OR e.data_type IS DISTINCT FROM s.data_type) AS schema_mismatch_count
    FROM expected_schema e FULL OUTER JOIN staging_columns s USING (ordinal_position)
), staging_stats AS (
    SELECT COUNT(*) AS staging_rows,
        COUNT(*) FILTER (WHERE timestamp IS NULL OR visitorid IS NULL OR event IS NULL
            OR event='' OR itemid IS NULL) AS missing_required_rows,
        COUNT(*) FILTER (WHERE timestamp<0 OR visitorid<0 OR itemid<0 OR transactionid<0) AS negative_numeric_rows,
        COUNT(*) FILTER (WHERE event IS NULL OR event NOT IN ('view','addtocart','transaction')) AS unexpected_event_rows,
        COUNT(*) FILTER (WHERE (event='transaction' AND transactionid IS NULL)
            OR (event<>'transaction' AND transactionid IS NOT NULL)) AS event_id_mismatch_rows,
        COUNT(*) FILTER (WHERE event='view') AS view_rows,
        COUNT(*) FILTER (WHERE event='addtocart') AS addtocart_rows,
        COUNT(*) FILTER (WHERE event='transaction') AS transaction_rows,
        COUNT(*) FILTER (WHERE transactionid IS NULL) AS null_transactionid_rows,
        COUNT(*)-COUNT(DISTINCT (timestamp,visitorid,event,itemid,transactionid)) AS duplicate_surplus_rows
    FROM rr_stg.events
), raw_only AS (
    SELECT timestamp,visitorid,event,itemid,transactionid FROM source_rows
    EXCEPT ALL SELECT CAST(timestamp AS VARCHAR),CAST(visitorid AS VARCHAR),event,
        CAST(itemid AS VARCHAR),CAST(transactionid AS VARCHAR) FROM rr_stg.events
), staging_only AS (
    SELECT CAST(timestamp AS VARCHAR),CAST(visitorid AS VARCHAR),event,
        CAST(itemid AS VARCHAR),CAST(transactionid AS VARCHAR) FROM rr_stg.events
    EXCEPT ALL SELECT timestamp,visitorid,event,itemid,transactionid FROM source_rows
), report AS (
    SELECT 1 AS check_order,'staging_rows' AS check_name,s.staging_rows AS actual,e.expected_rows AS expected FROM staging_stats s CROSS JOIN expected_counts e
    UNION ALL SELECT 2,'column_count',COUNT(*),5 FROM staging_columns
    UNION ALL SELECT 3,'schema_mismatch_count',schema_mismatch_count,0 FROM schema_stats
    UNION ALL SELECT 4,'missing_required_rows',missing_required_rows,0 FROM staging_stats
    UNION ALL SELECT 5,'negative_numeric_rows',negative_numeric_rows,0 FROM staging_stats
    UNION ALL SELECT 6,'unexpected_event_rows',unexpected_event_rows,0 FROM staging_stats
    UNION ALL SELECT 7,'event_id_mismatch_rows',event_id_mismatch_rows,0 FROM staging_stats
    UNION ALL SELECT 8,'view_rows',s.view_rows,e.expected_views FROM staging_stats s CROSS JOIN expected_counts e
    UNION ALL SELECT 9,'addtocart_rows',s.addtocart_rows,e.expected_carts FROM staging_stats s CROSS JOIN expected_counts e
    UNION ALL SELECT 10,'transaction_rows',s.transaction_rows,e.expected_transactions FROM staging_stats s CROSS JOIN expected_counts e
    UNION ALL SELECT 11,'null_transactionid_rows',s.null_transactionid_rows,e.expected_null_ids FROM staging_stats s CROSS JOIN expected_counts e
    UNION ALL SELECT 12,'duplicate_surplus_rows',s.duplicate_surplus_rows,e.expected_duplicate_surplus FROM staging_stats s CROSS JOIN expected_counts e
    UNION ALL SELECT 13,'raw_rows',raw_rows,expected_rows FROM input_guard
    UNION ALL SELECT 14,'raw_value_violations',raw_value_violations,0 FROM input_guard
    UNION ALL SELECT 15,'raw_schema_mismatch',raw_schema_mismatch,0 FROM input_guard
    UNION ALL SELECT 16,'raw_duplicate_surplus',raw_duplicate_surplus,expected_duplicate_surplus FROM input_guard
    UNION ALL SELECT 17,'raw_only_rows',COUNT(*),0 FROM raw_only
    UNION ALL SELECT 18,'staging_only_rows',COUNT(*),0 FROM staging_only
    UNION ALL SELECT 19,'raw_null_transactionid_rows',raw_null_ids,expected_null_ids FROM input_guard
    UNION ALL SELECT 20,'source_contract_violations',CASE WHEN valid_input THEN 0 ELSE 1 END,0 FROM input_guard
)
SELECT check_order,check_name,actual::BIGINT AS actual,expected::BIGINT AS expected,
    CASE WHEN actual=expected THEN 'PASS' ELSE 'FAIL' END AS status
FROM report ORDER BY check_order;
