-- Audit candidate transaction groups before defining shopping baskets.
-- Original occurrences are retained; repeated records are not item quantities.
WITH parameters AS (
    SELECT 2756101::BIGINT AS expected_rows,2664312::BIGINT AS expected_views,
        69332::BIGINT AS expected_carts,22457::BIGINT AS expected_transactions,
        460::BIGINT AS expected_duplicate_surplus,253402300799999::BIGINT AS max_supported_ms
), required_schema AS (
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
), health AS (
    SELECT COUNT(*) AS rows,COUNT(*) FILTER (WHERE event='view') AS views,
        COUNT(*) FILTER (WHERE event='addtocart') AS carts,COUNT(*) FILTER (WHERE event='transaction') AS transactions,
        COUNT(*)-COUNT(DISTINCT (timestamp,visitorid,event,itemid,transactionid)) AS duplicate_surplus,
        COUNT(*) FILTER (WHERE NOT COALESCE(timestamp BETWEEN 0 AND p.max_supported_ms AND visitorid>=0 AND itemid>=0
            AND event IN ('view','addtocart','transaction')
            AND ((event='transaction' AND original_transaction_present AND transactionid>=0)
                OR (event<>'transaction' AND NOT original_transaction_present)),false)) AS invalid_rows
    FROM source_rows CROSS JOIN parameters p
), admission AS (
    SELECT COALESCE(s.schema_mismatch=0 AND h.rows=p.expected_rows AND h.rows>0 AND h.views=p.expected_views
        AND h.carts=p.expected_carts AND h.transactions=p.expected_transactions
        AND h.duplicate_surplus=p.expected_duplicate_surplus AND h.invalid_rows=0,false) AS valid_input
    FROM health h CROSS JOIN required_schema s CROSS JOIN parameters p
), transactions AS MATERIALIZED (
    SELECT s.* FROM source_rows s CROSS JOIN admission a WHERE a.valid_input AND s.event='transaction'
), transaction_ids AS (
    SELECT transactionid,COUNT(DISTINCT visitorid) AS visitors,COUNT(DISTINCT timestamp) AS timestamps
    FROM transactions GROUP BY transactionid
), baskets AS (
    SELECT visitorid,transactionid,COUNT(*) AS event_rows,COUNT(DISTINCT itemid) AS distinct_items,
        COUNT(DISTINCT timestamp) AS timestamps
    FROM transactions GROUP BY visitorid,transactionid
), basket_items AS (
    SELECT visitorid,transactionid,itemid,COUNT(*) AS event_rows
    FROM transactions GROUP BY visitorid,transactionid,itemid
), transaction_totals AS (
    SELECT COUNT(*) AS event_rows,COUNT(DISTINCT (timestamp,visitorid,event,itemid,transactionid)) AS distinct_tuples FROM transactions
), id_totals AS (
    SELECT COUNT(*) AS ids,COUNT(*) FILTER (WHERE visitors>1) AS multi_visitor_ids,
        COUNT(*) FILTER (WHERE timestamps>1) AS multi_timestamp_ids FROM transaction_ids
), basket_totals AS (
    SELECT COUNT(*) AS baskets,COUNT(*) FILTER (WHERE timestamps>1) AS multi_timestamp_baskets,
        COUNT(*) FILTER (WHERE distinct_items=1) AS single_item_baskets,
        COUNT(*) FILTER (WHERE distinct_items>1) AS multi_item_baskets,MAX(distinct_items) AS max_distinct_items,
        COALESCE(SUM(event_rows),0) AS event_rows,COALESCE(SUM(distinct_items),0) AS item_memberships FROM baskets
), item_totals AS (
    SELECT COUNT(*) AS memberships,COUNT(*) FILTER (WHERE event_rows>1) AS repeated_keys FROM basket_items
), checks AS (
    SELECT 1 AS check_order,'source_event_rows' AS check_name,h.rows::BIGINT AS actual,p.expected_rows AS expected FROM health h CROSS JOIN parameters p
    UNION ALL SELECT 2,'required_schema_mismatch',s.schema_mismatch,0 FROM required_schema s
    UNION ALL SELECT 3,'invalid_event_rows',h.invalid_rows,0 FROM health h
    UNION ALL SELECT 4,'source_duplicate_surplus',h.duplicate_surplus,p.expected_duplicate_surplus FROM health h CROSS JOIN parameters p
    UNION ALL SELECT 5,'transaction_event_rows',h.transactions,p.expected_transactions FROM health h CROSS JOIN parameters p
    UNION ALL SELECT 6,'distinct_transaction_ids',t.ids,NULL FROM id_totals t
    UNION ALL SELECT 7,'visitor_transaction_pairs',b.baskets,NULL FROM basket_totals b
    UNION ALL SELECT 8,'transaction_ids_multiple_visitors',t.multi_visitor_ids,NULL FROM id_totals t
    UNION ALL SELECT 9,'transaction_ids_multiple_timestamps',t.multi_timestamp_ids,NULL FROM id_totals t
    UNION ALL SELECT 10,'visitor_transaction_pairs_multiple_timestamps',b.multi_timestamp_baskets,NULL FROM basket_totals b
    UNION ALL SELECT 11,'transaction_exact_duplicate_surplus',t.event_rows-t.distinct_tuples,NULL FROM transaction_totals t
    UNION ALL SELECT 12,'distinct_basket_item_pairs',i.memberships,NULL FROM item_totals i
    UNION ALL SELECT 13,'repeated_basket_item_pairs',i.repeated_keys,NULL FROM item_totals i
    UNION ALL SELECT 14,'repeat_basket_item_surplus_rows',t.event_rows-i.memberships,NULL FROM transaction_totals t CROSS JOIN item_totals i
    UNION ALL SELECT 15,'nonexact_repeat_surplus_rows',t.distinct_tuples-i.memberships,NULL FROM transaction_totals t CROSS JOIN item_totals i
    UNION ALL SELECT 16,'single_item_baskets',b.single_item_baskets,NULL FROM basket_totals b
    UNION ALL SELECT 17,'multi_item_baskets',b.multi_item_baskets,NULL FROM basket_totals b
    UNION ALL SELECT 18,'max_distinct_items_per_basket',b.max_distinct_items,NULL FROM basket_totals b
    UNION ALL SELECT 19,'basket_partition_difference',b.single_item_baskets+b.multi_item_baskets-b.baskets,0 FROM basket_totals b
    UNION ALL SELECT 20,'transaction_row_reconciliation_difference',b.event_rows-t.event_rows,0 FROM basket_totals b CROSS JOIN transaction_totals t
    UNION ALL SELECT 21,'basket_item_reconciliation_difference',b.item_memberships-i.memberships,0 FROM basket_totals b CROSS JOIN item_totals i
)
SELECT c.check_order,c.check_name,CASE WHEN a.valid_input THEN CAST(c.actual AS BIGINT) END AS actual,c.expected,
    CASE WHEN NOT a.valid_input THEN 'BLOCKED' WHEN c.expected IS NULL THEN 'INFO'
        WHEN c.actual=c.expected THEN 'PASS' ELSE 'FAIL' END AS status
FROM checks c CROSS JOIN admission a ORDER BY c.check_order;
