-- Build once: one observed candidate-basket/item membership with source occurrence counts and time bounds.
-- These are not purchased quantities, verified orders or basket-level dates. Source events stay unchanged.
CREATE SCHEMA IF NOT EXISTS rr_mart;
CREATE TABLE rr_mart.transaction_basket_items AS
WITH parameters AS (
    SELECT 2756101::BIGINT AS expected_rows,2664312::BIGINT AS expected_views,
        69332::BIGINT AS expected_carts,22457::BIGINT AS expected_transactions,
        460::BIGINT AS expected_duplicate_surplus,253402300799999::BIGINT AS max_supported_ms,
        22323::BIGINT AS expected_memberships,17672::BIGINT AS expected_baskets,
        123::BIGINT AS expected_repeated_memberships,134::BIGINT AS expected_repeat_surplus,
        15029::BIGINT AS expected_single_baskets,2643::BIGINT AS expected_multi_baskets,31::BIGINT AS expected_max_items
), source_schema AS (
    SELECT CASE WHEN COUNT(*)=5 AND COUNT(*) FILTER (WHERE
        (column_name IN ('timestamp','visitorid','itemid','transactionid') AND data_type='BIGINT')
        OR (column_name='event' AND data_type='VARCHAR'))=5 THEN 0 ELSE 1 END AS schema_mismatch
    FROM information_schema.columns WHERE table_catalog=current_database()
        AND table_schema='rr_stg' AND table_name='events'
        AND column_name IN ('timestamp','visitorid','event','itemid','transactionid')
), source_rows AS MATERIALIZED (
    SELECT TRY_CAST(timestamp AS BIGINT) AS timestamp,TRY_CAST(visitorid AS BIGINT) AS visitorid,
        CAST(event AS VARCHAR) AS event,TRY_CAST(itemid AS BIGINT) AS itemid,
        TRY_CAST(transactionid AS BIGINT) AS transactionid,e.transactionid IS NOT NULL AS original_transaction_present
    FROM rr_stg.events e
), source_health AS (
    SELECT COUNT(*) AS rows,COUNT(*) FILTER (WHERE event='view') AS views,
        COUNT(*) FILTER (WHERE event='addtocart') AS carts,COUNT(*) FILTER (WHERE event='transaction') AS transactions,
        COUNT(*)-COUNT(DISTINCT (timestamp,visitorid,event,itemid,transactionid)) AS duplicate_surplus,
        COUNT(*) FILTER (WHERE NOT COALESCE(timestamp BETWEEN 0 AND p.max_supported_ms AND visitorid>=0 AND itemid>=0
            AND event IN ('view','addtocart','transaction')
            AND ((event='transaction' AND original_transaction_present AND transactionid>=0)
                OR (event<>'transaction' AND NOT original_transaction_present)),false)) AS invalid_rows
    FROM source_rows CROSS JOIN parameters p
), source_memberships AS MATERIALIZED (
    SELECT visitorid,transactionid,itemid,MIN(timestamp)::BIGINT AS first_timestamp_ms,
        MAX(timestamp)::BIGINT AS last_timestamp_ms,COUNT(*)::BIGINT AS source_event_rows
    FROM source_rows WHERE event='transaction' GROUP BY visitorid,transactionid,itemid
), source_membership_health AS (
    SELECT COUNT(*) AS memberships,COUNT(DISTINCT (visitorid,transactionid)) AS baskets,
        COUNT(*) FILTER (WHERE source_event_rows>1) AS repeated_memberships,
        COALESCE(SUM(source_event_rows),0)::BIGINT AS source_events,
        COALESCE(SUM(source_event_rows-1),0)::BIGINT AS repeat_surplus FROM source_memberships
), source_baskets AS (
    SELECT visitorid,transactionid,COUNT(*) AS items FROM source_memberships GROUP BY visitorid,transactionid
), source_basket_health AS (
    SELECT COUNT(*) FILTER (WHERE items=1) AS single_baskets,COUNT(*) FILTER (WHERE items>1) AS multi_baskets,
        MAX(items) AS max_items FROM source_baskets
), input_guard AS MATERIALIZED (
    SELECT COALESCE(s.schema_mismatch=0 AND h.rows=p.expected_rows AND h.rows>0
        AND h.views=p.expected_views AND h.carts=p.expected_carts AND h.transactions=p.expected_transactions
        AND h.duplicate_surplus=p.expected_duplicate_surplus AND h.invalid_rows=0
        AND m.memberships=p.expected_memberships AND m.baskets=p.expected_baskets
        AND m.source_events=p.expected_transactions AND m.repeated_memberships=p.expected_repeated_memberships
        AND m.repeat_surplus=p.expected_repeat_surplus AND b.single_baskets=p.expected_single_baskets
        AND b.multi_baskets=p.expected_multi_baskets AND b.max_items IS NOT DISTINCT FROM NULLIF(p.expected_max_items,0),false) AS valid_input
    FROM source_schema s CROSS JOIN source_health h CROSS JOIN source_membership_health m
        CROSS JOIN source_basket_health b CROSS JOIN parameters p
)
SELECT CASE WHEN g.valid_input THEN CAST(m.visitorid AS BIGINT) ELSE error('SQL79 source contract failed; destination was not created') END AS visitorid,
       CASE WHEN g.valid_input THEN CAST(m.transactionid AS BIGINT) ELSE error('SQL79 source contract failed; destination was not created') END AS transactionid,
       CASE WHEN g.valid_input THEN CAST(m.itemid AS BIGINT) ELSE error('SQL79 source contract failed; destination was not created') END AS itemid,
       CASE WHEN g.valid_input THEN CAST(m.first_timestamp_ms AS BIGINT) ELSE error('SQL79 source contract failed; destination was not created') END AS first_timestamp_ms,
       CASE WHEN g.valid_input THEN CAST(m.last_timestamp_ms AS BIGINT) ELSE error('SQL79 source contract failed; destination was not created') END AS last_timestamp_ms,
       CASE WHEN g.valid_input THEN CAST(m.source_event_rows AS BIGINT) ELSE error('SQL79 source contract failed; destination was not created') END AS source_event_rows
FROM input_guard g LEFT JOIN source_memberships m ON true
WHERE NOT g.valid_input OR m.itemid IS NOT NULL;

-- CHECKS: if rr_mart.transaction_basket_items already exists, run only the query below.
WITH parameters AS (
    SELECT 2756101::BIGINT AS expected_rows,2664312::BIGINT AS expected_views,
        69332::BIGINT AS expected_carts,22457::BIGINT AS expected_transactions,
        460::BIGINT AS expected_duplicate_surplus,253402300799999::BIGINT AS max_supported_ms,
        22323::BIGINT AS expected_memberships,17672::BIGINT AS expected_baskets,
        123::BIGINT AS expected_repeated_memberships,134::BIGINT AS expected_repeat_surplus,
        15029::BIGINT AS expected_single_baskets,2643::BIGINT AS expected_multi_baskets,31::BIGINT AS expected_max_items
), source_schema AS (
    SELECT CASE WHEN COUNT(*)=5 AND COUNT(*) FILTER (WHERE
        (column_name IN ('timestamp','visitorid','itemid','transactionid') AND data_type='BIGINT')
        OR (column_name='event' AND data_type='VARCHAR'))=5 THEN 0 ELSE 1 END AS schema_mismatch
    FROM information_schema.columns WHERE table_catalog=current_database()
        AND table_schema='rr_stg' AND table_name='events'
        AND column_name IN ('timestamp','visitorid','event','itemid','transactionid')
), source_rows AS MATERIALIZED (
    SELECT TRY_CAST(timestamp AS BIGINT) AS timestamp,TRY_CAST(visitorid AS BIGINT) AS visitorid,
        CAST(event AS VARCHAR) AS event,TRY_CAST(itemid AS BIGINT) AS itemid,
        TRY_CAST(transactionid AS BIGINT) AS transactionid,e.transactionid IS NOT NULL AS original_transaction_present
    FROM rr_stg.events e
), source_health AS (
    SELECT COUNT(*) AS rows,COUNT(*) FILTER (WHERE event='view') AS views,
        COUNT(*) FILTER (WHERE event='addtocart') AS carts,COUNT(*) FILTER (WHERE event='transaction') AS transactions,
        COUNT(*)-COUNT(DISTINCT (timestamp,visitorid,event,itemid,transactionid)) AS duplicate_surplus,
        COUNT(*) FILTER (WHERE NOT COALESCE(timestamp BETWEEN 0 AND p.max_supported_ms AND visitorid>=0 AND itemid>=0
            AND event IN ('view','addtocart','transaction')
            AND ((event='transaction' AND original_transaction_present AND transactionid>=0)
                OR (event<>'transaction' AND NOT original_transaction_present)),false)) AS invalid_rows
    FROM source_rows CROSS JOIN parameters p
), source_memberships AS MATERIALIZED (
    SELECT visitorid,transactionid,itemid,MIN(timestamp)::BIGINT AS first_timestamp_ms,
        MAX(timestamp)::BIGINT AS last_timestamp_ms,COUNT(*)::BIGINT AS source_event_rows
    FROM source_rows WHERE event='transaction' GROUP BY visitorid,transactionid,itemid
), source_membership_health AS (
    SELECT COUNT(*) AS memberships,COUNT(DISTINCT (visitorid,transactionid)) AS baskets,
        COUNT(*) FILTER (WHERE source_event_rows>1) AS repeated_memberships,
        COALESCE(SUM(source_event_rows),0)::BIGINT AS source_events,
        COALESCE(SUM(source_event_rows-1),0)::BIGINT AS repeat_surplus FROM source_memberships
), source_baskets AS (
    SELECT visitorid,transactionid,COUNT(*) AS items FROM source_memberships GROUP BY visitorid,transactionid
), source_basket_health AS (
    SELECT COUNT(*) FILTER (WHERE items=1) AS single_baskets,COUNT(*) FILTER (WHERE items>1) AS multi_baskets,
        MAX(items) AS max_items FROM source_baskets
), input_guard AS MATERIALIZED (
    SELECT COALESCE(s.schema_mismatch=0 AND h.rows=p.expected_rows AND h.rows>0
        AND h.views=p.expected_views AND h.carts=p.expected_carts AND h.transactions=p.expected_transactions
        AND h.duplicate_surplus=p.expected_duplicate_surplus AND h.invalid_rows=0
        AND m.memberships=p.expected_memberships AND m.baskets=p.expected_baskets
        AND m.source_events=p.expected_transactions AND m.repeated_memberships=p.expected_repeated_memberships
        AND m.repeat_surplus=p.expected_repeat_surplus AND b.single_baskets=p.expected_single_baskets
        AND b.multi_baskets=p.expected_multi_baskets AND b.max_items IS NOT DISTINCT FROM NULLIF(p.expected_max_items,0),false) AS valid_input
    FROM source_schema s CROSS JOIN source_health h CROSS JOIN source_membership_health m
        CROSS JOIN source_basket_health b CROSS JOIN parameters p
), membership_schema AS (
    SELECT COUNT(*) AS column_count,CASE WHEN COUNT(*)=6 AND COUNT(*) FILTER (WHERE data_type='BIGINT'
        AND column_name=CASE ordinal_position WHEN 1 THEN 'visitorid' WHEN 2 THEN 'transactionid' WHEN 3 THEN 'itemid'
            WHEN 4 THEN 'first_timestamp_ms' WHEN 5 THEN 'last_timestamp_ms' WHEN 6 THEN 'source_event_rows' END)=6
        THEN 0 ELSE 1 END AS schema_mismatch
    FROM information_schema.columns WHERE table_catalog=current_database()
        AND table_schema='rr_mart' AND table_name='transaction_basket_items'
), membership_rows AS MATERIALIZED (
    SELECT TRY_CAST(visitorid AS BIGINT) AS visitorid,TRY_CAST(transactionid AS BIGINT) AS transactionid,
        TRY_CAST(itemid AS BIGINT) AS itemid,TRY_CAST(first_timestamp_ms AS BIGINT) AS first_timestamp_ms,
        TRY_CAST(last_timestamp_ms AS BIGINT) AS last_timestamp_ms,TRY_CAST(source_event_rows AS BIGINT) AS source_event_rows
    FROM rr_mart.transaction_basket_items
), membership_health AS (
    SELECT COUNT(*) AS rows,COUNT(*)-COUNT(DISTINCT (visitorid,transactionid,itemid)) AS duplicate_keys,
        COUNT(DISTINCT (visitorid,transactionid)) AS baskets,
        COUNT(*) FILTER (WHERE NOT COALESCE(visitorid>=0 AND transactionid>=0 AND itemid>=0
            AND first_timestamp_ms BETWEEN 0 AND p.max_supported_ms AND last_timestamp_ms BETWEEN first_timestamp_ms AND p.max_supported_ms
            AND source_event_rows>0,false)) AS invalid_rows,
        COALESCE(SUM(source_event_rows),0)::BIGINT AS source_events,
        COUNT(*) FILTER (WHERE source_event_rows>1) AS repeated_memberships,
        COALESCE(SUM(source_event_rows-1),0)::BIGINT AS repeat_surplus
    FROM membership_rows CROSS JOIN parameters p
), member_baskets AS (
    SELECT visitorid,transactionid,COUNT(DISTINCT itemid) AS items FROM membership_rows GROUP BY visitorid,transactionid
), basket_health AS (
    SELECT COUNT(*) FILTER (WHERE items=1) AS single_baskets,COUNT(*) FILTER (WHERE items>1) AS multi_baskets,
        MAX(items) AS max_items FROM member_baskets
), source_only AS (
    SELECT * FROM source_memberships EXCEPT ALL SELECT * FROM membership_rows
), membership_only AS (
    SELECT * FROM membership_rows EXCEPT ALL SELECT * FROM source_memberships
), checks AS (
    SELECT 1 AS check_order,'source_event_rows' AS check_name,h.rows AS actual,p.expected_rows AS expected FROM source_health h CROSS JOIN parameters p
    UNION ALL SELECT 2,'source_schema_mismatch',s.schema_mismatch,0 FROM source_schema s
    UNION ALL SELECT 3,'source_invalid_event_rows',h.invalid_rows,0 FROM source_health h
    UNION ALL SELECT 4,'source_duplicate_surplus',h.duplicate_surplus,p.expected_duplicate_surplus FROM source_health h CROSS JOIN parameters p
    UNION ALL SELECT 5,'source_transaction_rows',h.transactions,p.expected_transactions FROM source_health h CROSS JOIN parameters p
    UNION ALL SELECT 6,'source_contract_violations',CASE WHEN g.valid_input THEN 0 ELSE 1 END,0 FROM input_guard g
    UNION ALL SELECT 7,'membership_rows',h.rows,p.expected_memberships FROM membership_health h CROSS JOIN parameters p
    UNION ALL SELECT 8,'column_count',s.column_count,6 FROM membership_schema s
    UNION ALL SELECT 9,'schema_mismatch',s.schema_mismatch,0 FROM membership_schema s
    UNION ALL SELECT 10,'missing_or_invalid_rows',h.invalid_rows,0 FROM membership_health h
    UNION ALL SELECT 11,'duplicate_key_surplus',h.duplicate_keys,0 FROM membership_health h
    UNION ALL SELECT 12,'candidate_baskets',h.baskets,p.expected_baskets FROM membership_health h CROSS JOIN parameters p
    UNION ALL SELECT 13,'source_event_rows_sum',h.source_events,p.expected_transactions FROM membership_health h CROSS JOIN parameters p
    UNION ALL SELECT 14,'repeated_memberships',h.repeated_memberships,p.expected_repeated_memberships FROM membership_health h CROSS JOIN parameters p
    UNION ALL SELECT 15,'repeat_surplus_rows',h.repeat_surplus,p.expected_repeat_surplus FROM membership_health h CROSS JOIN parameters p
    UNION ALL SELECT 16,'single_item_baskets',h.single_baskets,p.expected_single_baskets FROM basket_health h CROSS JOIN parameters p
    UNION ALL SELECT 17,'multi_item_baskets',h.multi_baskets,p.expected_multi_baskets FROM basket_health h CROSS JOIN parameters p
    UNION ALL SELECT 18,'max_distinct_items_per_basket',h.max_items,NULLIF(p.expected_max_items,0) FROM basket_health h CROSS JOIN parameters p
    UNION ALL SELECT 19,'source_only_memberships',COUNT(*),0 FROM source_only
    UNION ALL SELECT 20,'table_only_memberships',COUNT(*),0 FROM membership_only
    UNION ALL SELECT 21,'basket_partition_difference',b.single_baskets+b.multi_baskets-h.baskets,0 FROM basket_health b CROSS JOIN membership_health h
)
SELECT check_order,check_name,CAST(actual AS BIGINT) AS actual,expected,
    CASE WHEN actual IS NOT DISTINCT FROM expected THEN 'PASS' ELSE 'FAIL' END AS status
FROM checks ORDER BY check_order;
