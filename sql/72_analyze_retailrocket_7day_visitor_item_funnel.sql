-- Seven elapsed days from each first observed view; both later stages share the same deadline.
-- Exclude incomplete follow-up before evaluating outcomes; log end does not prove continuous capture.
-- Strict timestamp inequalities exclude same-millisecond ties from evidence of ordering.
WITH parameters AS (
    SELECT 2756101::BIGINT AS expected_rows,2664312::BIGINT AS expected_views,
        69332::BIGINT AS expected_carts,22457::BIGINT AS expected_transactions,
        460::BIGINT AS expected_duplicate_surplus,253402300799999::BIGINT AS max_supported_ms,
        604800000::BIGINT AS window_ms,1442545187788::BIGINT AS expected_observation_end_ms
), required_schema AS (
    SELECT CASE WHEN COUNT(*)=5 AND COUNT(*) FILTER (WHERE
        (column_name IN ('timestamp','visitorid','itemid','transactionid') AND data_type='BIGINT')
        OR (column_name='event' AND data_type='VARCHAR'))=5 THEN 0 ELSE 1 END AS schema_mismatch
    FROM information_schema.columns WHERE table_catalog=current_database()
        AND table_schema='rr_mart' AND table_name='events_enriched'
        AND column_name IN ('timestamp','visitorid','event','itemid','transactionid')
), source_rows AS MATERIALIZED (
    SELECT TRY_CAST(timestamp AS BIGINT) AS timestamp,TRY_CAST(visitorid AS BIGINT) AS visitorid,
        CAST(event AS VARCHAR) AS event,TRY_CAST(itemid AS BIGINT) AS itemid,
        TRY_CAST(transactionid AS BIGINT) AS transactionid,f.transactionid IS NOT NULL AS original_transaction_present
    FROM rr_mart.events_enriched f
), health AS (
    SELECT COUNT(*) AS rows,MAX(timestamp) AS observation_end_ms,COUNT(*) FILTER (WHERE event='view') AS views,
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
        AND h.duplicate_surplus=p.expected_duplicate_surplus AND h.invalid_rows=0
        AND h.observation_end_ms=p.expected_observation_end_ms,false) AS valid_input,
        h.observation_end_ms,p.window_ms
    FROM health h CROSS JOIN required_schema s CROSS JOIN parameters p
), eligible AS MATERIALIZED (
    SELECT s.timestamp,s.visitorid,s.event,s.itemid,s.transactionid FROM source_rows s CROSS JOIN admission a WHERE a.valid_input
), viewed_pairs AS MATERIALIZED (
    SELECT e.visitorid,e.itemid,MIN(e.timestamp) AS first_view_ms,MIN(e.timestamp)+a.window_ms AS deadline_ms,
        MIN(e.timestamp)+a.window_ms<=a.observation_end_ms AS complete_followup
    FROM eligible e CROSS JOIN admission a WHERE e.event='view'
    GROUP BY e.visitorid,e.itemid,a.window_ms,a.observation_end_ms
), cohort AS (
    SELECT COUNT(*) AS viewed_all_pairs,COUNT(*) FILTER (WHERE NOT complete_followup) AS excluded_pairs,
        COUNT(*) FILTER (WHERE complete_followup) AS cohort_eligible_pairs FROM viewed_pairs
), eligible_view_pairs AS (
    SELECT * FROM viewed_pairs WHERE complete_followup
), cart_pairs AS MATERIALIZED (
    SELECT v.visitorid,v.itemid,v.first_view_ms,v.deadline_ms,MIN(e.timestamp) AS first_cart_after_view_ms
    FROM eligible_view_pairs v LEFT JOIN eligible e ON e.visitorid=v.visitorid AND e.itemid=v.itemid
        AND e.event='addtocart' AND e.timestamp>v.first_view_ms AND e.timestamp<=v.deadline_ms
    GROUP BY v.visitorid,v.itemid,v.first_view_ms,v.deadline_ms
), completed_pairs AS (
    SELECT c.visitorid,c.itemid,c.first_view_ms,c.deadline_ms,c.first_cart_after_view_ms,MIN(e.timestamp) AS first_transaction_after_cart_ms
    FROM cart_pairs c LEFT JOIN eligible e ON e.visitorid=c.visitorid AND e.itemid=c.itemid
        AND e.event='transaction' AND e.timestamp>c.first_cart_after_view_ms AND e.timestamp<=c.deadline_ms
    GROUP BY c.visitorid,c.itemid,c.first_view_ms,c.deadline_ms,c.first_cart_after_view_ms
), funnel AS (
    SELECT COUNT(*) AS view_pairs,COUNT(*) FILTER (WHERE first_cart_after_view_ms IS NOT NULL) AS cart_pairs,
        COUNT(*) FILTER (WHERE first_transaction_after_cart_ms IS NOT NULL) AS transaction_pairs
    FROM completed_pairs
), labels(stage_order,stage) AS (VALUES (1,'VIEWED_ALL'),(2,'EXCLUDED_INCOMPLETE_7D'),(3,'ELIGIBLE_VIEW_7D'),
    (4,'VIEW_THEN_CART_7D'),(5,'VIEW_CART_TRANSACTION_7D')),
stage_counts AS (
    SELECT l.*,f.*,c.*,a.valid_input,
        CASE l.stage_order WHEN 1 THEN c.viewed_all_pairs WHEN 2 THEN c.excluded_pairs
            WHEN 3 THEN f.view_pairs WHEN 4 THEN f.cart_pairs ELSE f.transaction_pairs END AS pair_count,
        CASE l.stage_order WHEN 4 THEN f.view_pairs WHEN 5 THEN f.cart_pairs END AS previous_pair_count
    FROM labels l CROSS JOIN funnel f CROSS JOIN cohort c CROSS JOIN admission a
)
SELECT stage,CASE WHEN valid_input THEN pair_count END AS visitor_item_pairs,
    CASE WHEN valid_input AND stage_order>=3 THEN CAST(ROUND(100.0*pair_count/NULLIF(view_pairs,0),4) AS DECIMAL(9,4)) END AS share_of_eligible_pairs_pct,
    CASE WHEN valid_input THEN CAST(ROUND(100.0*pair_count/NULLIF(previous_pair_count,0),4) AS DECIMAL(9,4)) END AS step_rate_pct,
    CASE WHEN NOT valid_input THEN 'BLOCKED'
        WHEN viewed_all_pairs=excluded_pairs+cohort_eligible_pairs AND view_pairs=cohort_eligible_pairs
            AND view_pairs>=cart_pairs AND cart_pairs>=transaction_pairs AND transaction_pairs>=0 THEN 'PASS' ELSE 'FAIL' END AS check_status
FROM stage_counts ORDER BY stage_order;
