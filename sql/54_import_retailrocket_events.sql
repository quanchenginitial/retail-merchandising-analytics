-- Run once in the existing retail_merchandising DBeaver connection.
-- Retailrocket remains separate from M5. Preserve every source observation.
-- All five raw fields stay VARCHAR; only exact-empty transactionid becomes NULL.
-- Existing rr_raw.events is never replaced: a second import must stop.
CREATE SCHEMA IF NOT EXISTS rr_raw;

CREATE TABLE rr_raw.events AS
SELECT timestamp,visitorid,event,itemid,transactionid
FROM read_csv(
    'D:/database/retailrocket/events.csv',
    header=true, auto_detect=false,
    columns={'timestamp':'VARCHAR','visitorid':'VARCHAR','event':'VARCHAR',
             'itemid':'VARCHAR','transactionid':'VARCHAR'},
    delim=',', quote='"', escape='"', encoding='utf-8',
    nullstr='', force_not_null=['timestamp','visitorid','event','itemid'],
    strict_mode=true, ignore_errors=false, null_padding=false
);

-- CHECKS: if the import already exists, run only the query below.
WITH expected_counts AS (
    SELECT 2756101 AS expected_rows,2664312 AS expected_views,
        69332 AS expected_carts,22457 AS expected_transactions,2733644 AS expected_null_transaction_ids
), source_rows AS MATERIALIZED (
    SELECT timestamp,visitorid,event,itemid,transactionid
    FROM read_csv(
        'D:/database/retailrocket/events.csv',
        header=true, auto_detect=false,
        columns={'timestamp':'VARCHAR','visitorid':'VARCHAR','event':'VARCHAR',
                 'itemid':'VARCHAR','transactionid':'VARCHAR'},
        delim=',', quote='"', escape='"', encoding='utf-8',
        nullstr='', force_not_null=['timestamp','visitorid','event','itemid'],
        strict_mode=true, ignore_errors=false, null_padding=false
    )
), column_stats AS (
    SELECT COUNT(*) AS columns,COUNT(*) FILTER (WHERE data_type='VARCHAR') AS varchar_columns,
        COUNT(*) FILTER (WHERE column_name IS DISTINCT FROM
            CASE ordinal_position WHEN 1 THEN 'timestamp' WHEN 2 THEN 'visitorid'
                WHEN 3 THEN 'event' WHEN 4 THEN 'itemid' WHEN 5 THEN 'transactionid' END) AS sequence_errors
    FROM information_schema.columns
    WHERE table_catalog=current_database() AND table_schema='rr_raw' AND table_name='events'
), row_stats AS (
    SELECT COUNT(*) AS rows,
        COUNT(*) FILTER (WHERE timestamp IS NULL OR timestamp='' OR visitorid IS NULL OR visitorid=''
            OR event IS NULL OR event='' OR itemid IS NULL OR itemid='') AS missing_required,
        COUNT(*) FILTER (WHERE timestamp IS NOT NULL AND
            (NOT regexp_full_match(timestamp,'[0-9]+') OR TRY_CAST(timestamp AS BIGINT) IS NULL)) AS invalid_timestamp,
        COUNT(*) FILTER (WHERE visitorid IS NOT NULL AND
            (NOT regexp_full_match(visitorid,'[0-9]+') OR TRY_CAST(visitorid AS BIGINT) IS NULL)) AS invalid_visitorid,
        COUNT(*) FILTER (WHERE itemid IS NOT NULL AND
            (NOT regexp_full_match(itemid,'[0-9]+') OR TRY_CAST(itemid AS BIGINT) IS NULL)) AS invalid_itemid,
        COUNT(*) FILTER (WHERE transactionid IS NOT NULL AND
            (NOT regexp_full_match(transactionid,'[0-9]+') OR TRY_CAST(transactionid AS BIGINT) IS NULL)) AS invalid_transactionid,
        COUNT(*) FILTER (WHERE event IS NULL OR event NOT IN ('view','addtocart','transaction')) AS unexpected_events,
        COUNT(*) FILTER (WHERE event='view') AS views,
        COUNT(*) FILTER (WHERE event='addtocart') AS carts,
        COUNT(*) FILTER (WHERE event='transaction') AS transactions,
        COUNT(*) FILTER (WHERE event='transaction' AND (transactionid IS NULL OR transactionid='')) AS missing_transaction_ids,
        COUNT(*) FILTER (WHERE transactionid IS NULL) AS null_transaction_ids,
        COUNT(*)-COUNT(DISTINCT (timestamp,visitorid,event,itemid,transactionid)) AS duplicate_surplus
    FROM rr_raw.events
), source_stats AS (
    SELECT COUNT(*)-COUNT(DISTINCT (timestamp,visitorid,event,itemid,transactionid)) AS duplicate_surplus
    FROM source_rows
), source_only AS (
    SELECT timestamp,visitorid,event,itemid,transactionid FROM source_rows
    EXCEPT ALL SELECT timestamp,visitorid,event,itemid,transactionid FROM rr_raw.events
), table_only AS (
    SELECT timestamp,visitorid,event,itemid,transactionid FROM rr_raw.events
    EXCEPT ALL SELECT timestamp,visitorid,event,itemid,transactionid FROM source_rows
), checks AS (
    SELECT 1 AS check_order,'row_count' AS check_name,r.rows AS actual,e.expected_rows AS expected FROM row_stats r CROSS JOIN expected_counts e
    UNION ALL SELECT 2,'column_count',columns,5 FROM column_stats
    UNION ALL SELECT 3,'varchar_column_count',varchar_columns,5 FROM column_stats
    UNION ALL SELECT 4,'column_sequence_errors',sequence_errors,0 FROM column_stats
    UNION ALL SELECT 5,'missing_required_rows',missing_required,0 FROM row_stats
    UNION ALL SELECT 6,'invalid_timestamp_rows',invalid_timestamp,0 FROM row_stats
    UNION ALL SELECT 7,'invalid_visitorid_rows',invalid_visitorid,0 FROM row_stats
    UNION ALL SELECT 8,'invalid_itemid_rows',invalid_itemid,0 FROM row_stats
    UNION ALL SELECT 9,'invalid_transactionid_rows',invalid_transactionid,0 FROM row_stats
    UNION ALL SELECT 10,'unexpected_event_rows',unexpected_events,0 FROM row_stats
    UNION ALL SELECT 11,'view_event_rows',r.views,e.expected_views FROM row_stats r CROSS JOIN expected_counts e
    UNION ALL SELECT 12,'addtocart_event_rows',r.carts,e.expected_carts FROM row_stats r CROSS JOIN expected_counts e
    UNION ALL SELECT 13,'transaction_event_rows',r.transactions,e.expected_transactions FROM row_stats r CROSS JOIN expected_counts e
    UNION ALL SELECT 14,'transactions_missing_id',missing_transaction_ids,0 FROM row_stats
    UNION ALL SELECT 15,'null_transactionid_rows',r.null_transaction_ids,e.expected_null_transaction_ids FROM row_stats r CROSS JOIN expected_counts e
    UNION ALL SELECT 16,'source_rows_absent_from_table',COUNT(*),0 FROM source_only
    UNION ALL SELECT 17,'table_rows_absent_from_source',COUNT(*),0 FROM table_only
    UNION ALL SELECT 18,'duplicate_surplus_rows_preserved',r.duplicate_surplus,s.duplicate_surplus FROM row_stats r CROSS JOIN source_stats s
)
SELECT check_order,check_name,actual,expected,
    CASE WHEN actual=expected THEN 'PASS' ELSE 'FAIL' END AS status
FROM checks ORDER BY check_order;
