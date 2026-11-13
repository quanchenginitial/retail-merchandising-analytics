-- Elapsed time since each transaction visitor ID's latest recorded transaction event.
-- Reference is the frozen global observed event endpoint, not today or the latest transaction time.
WITH parameters AS (
    SELECT 22323::BIGINT AS expected_memberships,17672::BIGINT AS expected_baskets,
        15029::BIGINT AS expected_single_baskets,2643::BIGINT AS expected_multi_baskets,31::BIGINT AS expected_max_items,
        11719::BIGINT AS expected_visitor_ids,1430622004384::BIGINT AS source_min_timestamp_ms,
        1442545187788::BIGINT AS reference_timestamp_ms,86400000::BIGINT AS day_ms
), required_schema AS (
    SELECT CASE WHEN COUNT(*)=4 AND COUNT(*) FILTER (WHERE data_type='BIGINT')=4 THEN 0 ELSE 1 END AS schema_mismatch
    FROM information_schema.columns WHERE table_catalog=current_database()
        AND table_schema='rr_mart' AND table_name='transaction_basket_items'
        AND column_name IN ('visitorid','transactionid','itemid','last_timestamp_ms')
), source_keys AS MATERIALIZED (
    SELECT TRY_CAST(visitorid AS BIGINT) AS visitorid,TRY_CAST(transactionid AS BIGINT) AS transactionid,
        TRY_CAST(itemid AS BIGINT) AS itemid,TRY_CAST(last_timestamp_ms AS BIGINT) AS last_timestamp_ms
    FROM rr_mart.transaction_basket_items
), source_health AS (
    SELECT COUNT(*) AS memberships,COUNT(*)-COUNT(DISTINCT (visitorid,transactionid,itemid)) AS duplicate_keys,
        COUNT(*) FILTER (WHERE NOT COALESCE(visitorid>=0 AND transactionid>=0 AND itemid>=0,false)) AS invalid_keys,
        COUNT(*) FILTER (WHERE NOT COALESCE(last_timestamp_ms BETWEEN p.source_min_timestamp_ms AND p.reference_timestamp_ms,false)) AS invalid_timestamps
    FROM source_keys CROSS JOIN parameters p
), basket_sizes AS MATERIALIZED (
    SELECT visitorid,transactionid,COUNT(*) AS items FROM source_keys GROUP BY visitorid,transactionid
), basket_health AS (
    SELECT COUNT(*) AS baskets,COUNT(*) FILTER (WHERE items=1) AS single_baskets,
        COUNT(*) FILTER (WHERE items>1) AS multi_baskets,MAX(items) AS max_items FROM basket_sizes
), admission AS (
    SELECT COALESCE(s.schema_mismatch=0 AND h.memberships=p.expected_memberships AND h.memberships>0
        AND h.invalid_keys=0 AND h.duplicate_keys=0 AND h.invalid_timestamps=0 AND b.baskets=p.expected_baskets
        AND b.single_baskets=p.expected_single_baskets AND b.multi_baskets=p.expected_multi_baskets
        AND b.max_items=p.expected_max_items,false) AS valid_input
    FROM required_schema s CROSS JOIN source_health h CROSS JOIN basket_health b CROSS JOIN parameters p
), eligible_memberships AS MATERIALIZED (
    SELECT k.* FROM source_keys k CROSS JOIN admission a WHERE a.valid_input
), visitor_last_transaction AS MATERIALIZED (
    SELECT visitorid,MAX(last_timestamp_ms)::BIGINT AS last_transaction_ms FROM eligible_memberships GROUP BY visitorid
), visitor_recency AS MATERIALIZED (
    SELECT v.visitorid,v.last_transaction_ms,(p.reference_timestamp_ms-v.last_transaction_ms)::BIGINT AS recency_ms
    FROM visitor_last_transaction v CROSS JOIN parameters p
), recency_health AS (
    SELECT COUNT(*)::BIGINT AS visitor_ids,MIN(recency_ms)::BIGINT AS min_recency_ms,
        MEDIAN(recency_ms) AS median_recency_ms,MAX(recency_ms)::BIGINT AS max_recency_ms,
        COUNT(*) FILTER (WHERE NOT COALESCE(recency_ms>=0 AND recency_ms<=p.reference_timestamp_ms-p.source_min_timestamp_ms
            AND last_transaction_ms+recency_ms=p.reference_timestamp_ms,false)) AS invalid_recencies
    FROM visitor_recency CROSS JOIN parameters p
), bands AS (
    SELECT * FROM (VALUES (1,'R_LT_7D',0::BIGINT,604800000::BIGINT),
        (2,'R_7_TO_LT_30D',604800000::BIGINT,2592000000::BIGINT),
        (3,'R_30_TO_LT_60D',2592000000::BIGINT,5184000000::BIGINT),
        (4,'R_GE_60D',5184000000::BIGINT,NULL::BIGINT)) t(band_order,recency_band,min_ms,max_ms)
), band_summary AS MATERIALIZED (
    SELECT b.band_order,b.recency_band,COUNT(v.visitorid)::BIGINT AS visitor_ids,
        MIN(v.recency_ms)::BIGINT AS min_recency_ms,MEDIAN(v.recency_ms) AS median_recency_ms,
        MAX(v.recency_ms)::BIGINT AS max_recency_ms
    FROM bands b LEFT JOIN visitor_recency v ON v.recency_ms>=b.min_ms AND (b.max_ms IS NULL OR v.recency_ms<b.max_ms)
    GROUP BY b.band_order,b.recency_band
), partition_health AS (
    SELECT COUNT(*) AS band_rows,SUM(visitor_ids)::BIGINT AS visitor_ids,
        COUNT(*) FILTER (WHERE NOT COALESCE(visitor_ids>=0
            AND ((visitor_ids=0 AND min_recency_ms IS NULL AND median_recency_ms IS NULL AND max_recency_ms IS NULL)
                OR (visitor_ids>0 AND min_recency_ms>=0 AND min_recency_ms<=median_recency_ms AND median_recency_ms<=max_recency_ms)),false)) AS invalid_bands
    FROM band_summary
), recency_gate AS (
    SELECT r.visitor_ids=p.expected_visitor_ids AND r.invalid_recencies=0 AND b.band_rows=4
        AND b.visitor_ids=r.visitor_ids AND b.invalid_bands=0 AS valid_recency
    FROM recency_health r CROSS JOIN partition_health b CROSS JOIN parameters p
), report_rows AS (
    SELECT * FROM band_summary
    UNION ALL SELECT 5,'TOTAL',visitor_ids,min_recency_ms,median_recency_ms,max_recency_ms FROM recency_health
)
SELECT r.recency_band,
    CASE WHEN a.valid_input AND g.valid_recency THEN r.visitor_ids END AS visitor_ids,
    CASE WHEN a.valid_input AND g.valid_recency THEN ROUND(100.0*r.visitor_ids/NULLIF(h.visitor_ids,0),6) END AS visitor_share_pct,
    CASE WHEN a.valid_input AND g.valid_recency THEN ROUND(r.min_recency_ms::DOUBLE/p.day_ms,6) END AS min_recency_days,
    CASE WHEN a.valid_input AND g.valid_recency THEN ROUND(r.median_recency_ms::DOUBLE/p.day_ms,6) END AS median_recency_days,
    CASE WHEN a.valid_input AND g.valid_recency THEN ROUND(r.max_recency_ms::DOUBLE/p.day_ms,6) END AS max_recency_days,
    CASE WHEN NOT a.valid_input THEN 'BLOCKED' WHEN NOT g.valid_recency THEN 'FAIL' ELSE 'PASS' END AS check_status
FROM report_rows r CROSS JOIN admission a CROSS JOIN recency_gate g CROSS JOIN recency_health h CROSS JOIN parameters p ORDER BY r.band_order;
