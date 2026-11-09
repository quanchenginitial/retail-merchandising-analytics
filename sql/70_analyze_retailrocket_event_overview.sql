-- Event-record overview: counts and shares are not visitor conversion rates.
-- Only seven accepted fact fields are read; the ten property fields are outside this query's scope.
WITH parameters AS (
    SELECT 2756101::BIGINT AS expected_rows,2664312::BIGINT AS expected_views,
        69332::BIGINT AS expected_carts,22457::BIGINT AS expected_transactions,
        460::BIGINT AS expected_duplicate_surplus,253402300799999::BIGINT AS max_supported_ms
), required_schema AS (
    SELECT CASE WHEN COUNT(*)=7 AND COUNT(*) FILTER (WHERE
        (column_name IN ('timestamp','visitorid','itemid','transactionid') AND data_type='BIGINT')
        OR (column_name='event' AND data_type='VARCHAR')
        OR (column_name='event_timestamp_utc' AND data_type='TIMESTAMP')
        OR (column_name='event_date_utc' AND data_type='DATE'))=7 THEN 0 ELSE 1 END AS schema_mismatch
    FROM information_schema.columns WHERE table_catalog=current_database()
        AND table_schema='rr_mart' AND table_name='events_enriched'
        AND column_name IN ('timestamp','visitorid','event','itemid','transactionid','event_timestamp_utc','event_date_utc')
), source_rows AS MATERIALIZED (
    SELECT TRY_CAST(timestamp AS BIGINT) AS timestamp,TRY_CAST(visitorid AS BIGINT) AS visitorid,
        CAST(event AS VARCHAR) AS event,TRY_CAST(itemid AS BIGINT) AS itemid,
        TRY_CAST(transactionid AS BIGINT) AS transactionid,f.transactionid IS NOT NULL AS original_transaction_present,
        TRY_CAST(event_timestamp_utc AS TIMESTAMP) AS event_timestamp_utc,TRY_CAST(event_date_utc AS DATE) AS event_date_utc
    FROM rr_mart.events_enriched f
), health AS (
    SELECT COUNT(*) AS rows,COUNT(*) FILTER (WHERE event='view') AS views,
        COUNT(*) FILTER (WHERE event='addtocart') AS carts,COUNT(*) FILTER (WHERE event='transaction') AS transactions,
        COUNT(*)-COUNT(DISTINCT (timestamp,visitorid,event,itemid,transactionid)) AS duplicate_surplus,
        COUNT(*) FILTER (WHERE NOT COALESCE(timestamp BETWEEN 0 AND p.max_supported_ms AND visitorid>=0 AND itemid>=0
            AND event IN ('view','addtocart','transaction')
            AND ((event='transaction' AND original_transaction_present AND transactionid>=0)
                OR (event<>'transaction' AND NOT original_transaction_present))
            AND event_timestamp_utc IS NOT NULL AND event_date_utc IS NOT NULL
            AND epoch_ms(event_timestamp_utc)=timestamp
            AND CASE WHEN timestamp BETWEEN 0 AND p.max_supported_ms THEN event_timestamp_utc=make_timestamp_ms(timestamp) ELSE false END
            AND event_date_utc=CAST(event_timestamp_utc AS DATE),false)) AS invalid_rows
    FROM source_rows CROSS JOIN parameters p
), admission AS (
    SELECT COALESCE(s.schema_mismatch=0 AND h.rows=p.expected_rows AND h.rows>0 AND h.views=p.expected_views
        AND h.carts=p.expected_carts AND h.transactions=p.expected_transactions
        AND h.duplicate_surplus=p.expected_duplicate_surplus AND h.invalid_rows=0,false) AS valid_input,p.*
    FROM health h CROSS JOIN required_schema s CROSS JOIN parameters p
), eligible AS (
    SELECT s.* FROM source_rows s CROSS JOIN admission a WHERE a.valid_input
), aggregates AS (
    SELECT CASE WHEN GROUPING(event)=1 THEN 'TOTAL' ELSE event END AS event_type,
        COUNT(*) AS event_rows,COUNT(DISTINCT visitorid) AS distinct_visitor_ids,
        COUNT(DISTINCT itemid) AS distinct_item_ids,COUNT(DISTINCT transactionid) AS distinct_transaction_ids,
        strftime(MIN(event_timestamp_utc),'%Y-%m-%dT%H:%M:%S.%fZ') AS first_event_utc,
        strftime(MAX(event_timestamp_utc),'%Y-%m-%dT%H:%M:%S.%fZ') AS last_event_utc,
        COUNT(DISTINCT event_date_utc) AS observed_utc_dates
    FROM eligible GROUP BY GROUPING SETS ((event),())
), labels(event_order,event_type) AS (VALUES (1,'view'),(2,'addtocart'),(3,'transaction'),(4,'TOTAL'))
SELECT l.event_type,
    CASE WHEN a.valid_input THEN g.event_rows END AS event_rows,
    CASE WHEN a.valid_input THEN CAST(ROUND(100.0*g.event_rows/a.expected_rows,4) AS DECIMAL(9,4)) END AS event_share_pct,
    CASE WHEN a.valid_input THEN g.distinct_visitor_ids END AS distinct_visitor_ids,
    CASE WHEN a.valid_input THEN g.distinct_item_ids END AS distinct_item_ids,
    CASE WHEN a.valid_input THEN g.distinct_transaction_ids END AS distinct_transaction_ids,
    CASE WHEN a.valid_input THEN g.first_event_utc END AS first_event_utc,
    CASE WHEN a.valid_input THEN g.last_event_utc END AS last_event_utc,
    CASE WHEN a.valid_input THEN g.observed_utc_dates END AS observed_utc_dates,
    CASE WHEN NOT a.valid_input THEN 'BLOCKED'
        WHEN g.event_rows=CASE l.event_type WHEN 'view' THEN a.expected_views WHEN 'addtocart' THEN a.expected_carts
            WHEN 'transaction' THEN a.expected_transactions ELSE a.expected_rows END THEN 'PASS' ELSE 'FAIL' END AS check_status
FROM labels l CROSS JOIN admission a LEFT JOIN aggregates g USING(event_type) ORDER BY l.event_order;
