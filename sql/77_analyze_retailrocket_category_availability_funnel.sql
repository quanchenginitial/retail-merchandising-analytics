-- Category 1613 seven-day paths by availability recorded at the first observed view.
-- Recorded values describe historical observations, not verified stock or causality.
WITH parameters AS (
    SELECT 2756101::BIGINT AS expected_rows,2664312::BIGINT AS expected_views,
        69332::BIGINT AS expected_carts,22457::BIGINT AS expected_transactions,
        460::BIGINT AS expected_duplicate_surplus,253402300799999::BIGINT AS max_supported_ms,
        604800000::BIGINT AS window_ms,1442545187788::BIGINT AS expected_observation_end_ms,
        2042310::BIGINT AS expected_eligible_pairs,1669::BIGINT AS expected_reference_ids,
        1527206::BIGINT AS expected_mapped_pairs,0::BIGINT AS expected_unknown_reference_pairs,
        304405::BIGINT AS expected_before_first_pairs,210699::BIGINT AS expected_no_history_pairs,
        43147::BIGINT AS expected_cart_pairs,15520::BIGINT AS expected_transaction_pairs,1613::BIGINT AS target_categoryid,25105::BIGINT AS expected_target_pairs,
        483::BIGINT AS expected_target_carts,76::BIGINT AS expected_target_transactions
), required_schema AS (
    SELECT CASE WHEN COUNT(*)=15 AND COUNT(*) FILTER (WHERE
        (column_name IN ('timestamp','visitorid','itemid','transactionid') AND data_type='BIGINT')
        OR (column_name IN ('event','categoryid_value','categoryid_source_file','categoryid_coverage','available_value','available_source_file','available_coverage') AND data_type='VARCHAR')
        OR (column_name IN ('categoryid_from_ms','categoryid_to_ms','available_from_ms','available_to_ms') AND data_type='BIGINT'))=15 THEN 0 ELSE 1 END AS schema_mismatch
    FROM information_schema.columns WHERE table_catalog=current_database()
        AND table_schema='rr_mart' AND table_name='events_enriched'
        AND column_name IN ('timestamp','visitorid','event','itemid','transactionid','categoryid_value','categoryid_from_ms','categoryid_to_ms','categoryid_source_file','categoryid_coverage','available_value','available_from_ms','available_to_ms','available_source_file','available_coverage')
) , reference_schema AS (
    SELECT CASE WHEN COUNT(*)=1 AND COUNT(*) FILTER (WHERE data_type='BIGINT')=1 THEN 0 ELSE 1 END AS schema_mismatch
    FROM information_schema.columns WHERE table_catalog=current_database() AND table_schema='rr_core' AND table_name='dim_category' AND column_name='categoryid'
), reference_rows AS MATERIALIZED (
    SELECT TRY_CAST(categoryid AS BIGINT) AS categoryid FROM rr_core.dim_category
), reference_health AS (
    SELECT COUNT(*) AS reference_rows,COUNT(DISTINCT categoryid) AS distinct_ids,
        COUNT(*) FILTER (WHERE categoryid IS NULL OR categoryid<0) AS invalid_ids FROM reference_rows
), source_rows AS MATERIALIZED (
    SELECT TRY_CAST(timestamp AS BIGINT) AS timestamp,TRY_CAST(visitorid AS BIGINT) AS visitorid,
        CAST(event AS VARCHAR) AS event,TRY_CAST(itemid AS BIGINT) AS itemid,
        TRY_CAST(transactionid AS BIGINT) AS transactionid,f.transactionid IS NOT NULL AS original_transaction_present,
        CAST(categoryid_value AS VARCHAR) AS categoryid_value,TRY_CAST(categoryid_from_ms AS BIGINT) AS categoryid_from_ms,
        TRY_CAST(categoryid_to_ms AS BIGINT) AS categoryid_to_ms,CAST(categoryid_source_file AS VARCHAR) AS categoryid_source_file,
        CAST(categoryid_coverage AS VARCHAR) AS categoryid_coverage,f.categoryid_to_ms IS NOT NULL AS original_category_end_present,
        CAST(available_value AS VARCHAR) AS available_value,TRY_CAST(available_from_ms AS BIGINT) AS available_from_ms,
        TRY_CAST(available_to_ms AS BIGINT) AS available_to_ms,CAST(available_source_file AS VARCHAR) AS available_source_file,
        CAST(available_coverage AS VARCHAR) AS available_coverage,f.available_to_ms IS NOT NULL AS original_available_end_present
    FROM rr_mart.events_enriched f
), health AS (
    SELECT COUNT(*) AS rows,MAX(timestamp) AS observation_end_ms,COUNT(*) FILTER (WHERE event='view') AS views,
        COUNT(*) FILTER (WHERE event='addtocart') AS carts,COUNT(*) FILTER (WHERE event='transaction') AS transactions,
        COUNT(*)-COUNT(DISTINCT (timestamp,visitorid,event,itemid,transactionid)) AS duplicate_surplus,
        COUNT(*) FILTER (WHERE NOT COALESCE(timestamp BETWEEN 0 AND p.max_supported_ms AND visitorid>=0 AND itemid>=0
            AND event IN ('view','addtocart','transaction')
            AND ((event='transaction' AND original_transaction_present AND transactionid>=0)
                OR (event<>'transaction' AND NOT original_transaction_present)),false)) AS invalid_rows,
        COUNT(*) FILTER (WHERE NOT COALESCE(
            (categoryid_coverage='MATCHED' AND regexp_full_match(categoryid_value,'[0-9]+') AND TRY_CAST(categoryid_value AS BIGINT) IS NOT NULL
                AND categoryid_from_ms BETWEEN 0 AND p.max_supported_ms AND categoryid_from_ms<=timestamp
                AND (NOT original_category_end_present OR (categoryid_to_ms BETWEEN 0 AND p.max_supported_ms
                    AND categoryid_to_ms>categoryid_from_ms AND timestamp<categoryid_to_ms))
                AND categoryid_source_file IN ('item_properties_part1.csv','item_properties_part2.csv'))
            OR (categoryid_coverage IN ('BEFORE_FIRST','NO_HISTORY') AND categoryid_value IS NULL AND categoryid_from_ms IS NULL
                AND categoryid_to_ms IS NULL AND NOT original_category_end_present AND categoryid_source_file IS NULL),false)) AS invalid_category_rows,
        COUNT(*) FILTER (WHERE NOT COALESCE(
            (available_coverage='MATCHED' AND available_value IN ('0','1')
                AND available_from_ms BETWEEN 0 AND p.max_supported_ms AND available_from_ms<=timestamp
                AND (NOT original_available_end_present OR (available_to_ms BETWEEN 0 AND p.max_supported_ms
                    AND available_to_ms>available_from_ms AND timestamp<available_to_ms))
                AND available_source_file IN ('item_properties_part1.csv','item_properties_part2.csv'))
            OR (available_coverage IN ('BEFORE_FIRST','NO_HISTORY') AND available_value IS NULL AND available_from_ms IS NULL
                AND available_to_ms IS NULL AND NOT original_available_end_present AND available_source_file IS NULL),false)) AS invalid_available_rows
    FROM source_rows CROSS JOIN parameters p
), source_admission AS (
    SELECT COALESCE(s.schema_mismatch=0 AND h.rows=p.expected_rows AND h.rows>0 AND h.views=p.expected_views
        AND h.carts=p.expected_carts AND h.transactions=p.expected_transactions
        AND h.duplicate_surplus=p.expected_duplicate_surplus AND h.invalid_rows=0
        AND h.observation_end_ms=p.expected_observation_end_ms AND h.invalid_category_rows=0 AND h.invalid_available_rows=0
        AND rs.schema_mismatch=0 AND rh.reference_rows=p.expected_reference_ids AND rh.distinct_ids=p.expected_reference_ids
        AND rh.invalid_ids=0 AND p.target_categoryid=1613,false) AS valid_input,
        h.observation_end_ms,p.window_ms,p.expected_eligible_pairs
    FROM health h CROSS JOIN required_schema s CROSS JOIN parameters p CROSS JOIN reference_schema rs CROSS JOIN reference_health rh
), eligible AS MATERIALIZED (
    SELECT s.* FROM source_rows s CROSS JOIN source_admission a WHERE a.valid_input
), viewed_pairs AS (
    SELECT visitorid,itemid,MIN(timestamp) AS first_view_ms FROM eligible WHERE event='view' GROUP BY visitorid,itemid
), eligible_pairs AS MATERIALIZED (
    SELECT v.* FROM viewed_pairs v CROSS JOIN source_admission a WHERE v.first_view_ms+a.window_ms<=a.observation_end_ms
), first_view_rows AS MATERIALIZED (
    SELECT p.visitorid,p.itemid,p.first_view_ms,e.categoryid_value,e.categoryid_from_ms,e.categoryid_to_ms,e.categoryid_source_file,e.categoryid_coverage,
        e.available_value,e.available_from_ms,e.available_to_ms,e.available_source_file,e.available_coverage
    FROM eligible_pairs p JOIN eligible e ON e.visitorid=p.visitorid AND e.itemid=p.itemid AND e.timestamp=p.first_view_ms AND e.event='view'
), consistency AS (
    SELECT visitorid,itemid,COUNT(DISTINCT (categoryid_value,categoryid_from_ms,categoryid_to_ms,categoryid_source_file,categoryid_coverage,
        available_value,available_from_ms,available_to_ms,available_source_file,available_coverage)) AS attribute_tuples
    FROM first_view_rows GROUP BY visitorid,itemid
), cohort_guard AS (
    SELECT a.valid_input AND (SELECT COUNT(*) FROM eligible_pairs)=a.expected_eligible_pairs
        AND (SELECT COUNT(*) FROM consistency)=a.expected_eligible_pairs
        AND (SELECT COUNT(*) FROM consistency WHERE attribute_tuples<>1)=0 AS valid_cohort,a.expected_eligible_pairs
    FROM source_admission a
), snapshots AS MATERIALIZED (
    SELECT DISTINCT f.* FROM first_view_rows f CROSS JOIN cohort_guard g WHERE g.valid_cohort
), classified AS (
    SELECT s.*,r.categoryid,CASE WHEN s.categoryid_coverage='BEFORE_FIRST' THEN 'BEFORE_FIRST'
        WHEN s.categoryid_coverage='NO_HISTORY' THEN 'NO_HISTORY'
        WHEN s.categoryid_coverage='MATCHED' AND r.categoryid IS NOT NULL THEN 'MAPPED'
        WHEN s.categoryid_coverage='MATCHED' THEN 'UNKNOWN_REFERENCE' ELSE 'INVALID' END AS coverage_status
    FROM snapshots s LEFT JOIN reference_rows r ON TRY_CAST(s.categoryid_value AS BIGINT)=r.categoryid
), cart_times AS MATERIALIZED (
    SELECT c.visitorid,c.itemid,MIN(e.timestamp) AS cart_ms
    FROM classified c CROSS JOIN parameters p LEFT JOIN eligible e
        ON e.visitorid=c.visitorid AND e.itemid=c.itemid AND e.event='addtocart'
        AND e.timestamp>c.first_view_ms AND e.timestamp<=c.first_view_ms+p.window_ms
    GROUP BY c.visitorid,c.itemid
), outcomes AS MATERIALIZED (
    SELECT c.visitorid,c.itemid,c.categoryid,c.coverage_status,c.first_view_ms,t.cart_ms,c.available_value,c.available_from_ms,c.available_to_ms,c.available_source_file,c.available_coverage,MIN(e.timestamp) AS transaction_ms
    FROM classified c JOIN cart_times t USING(visitorid,itemid) CROSS JOIN parameters p LEFT JOIN eligible e
        ON e.visitorid=c.visitorid AND e.itemid=c.itemid AND e.event='transaction'
        AND e.timestamp>t.cart_ms AND e.timestamp<=c.first_view_ms+p.window_ms
    GROUP BY c.visitorid,c.itemid,c.categoryid,c.coverage_status,c.first_view_ms,t.cart_ms,
        c.available_value,c.available_from_ms,c.available_to_ms,c.available_source_file,c.available_coverage
), summary AS (
    SELECT COUNT(*) AS eligible_pairs,COUNT(DISTINCT (visitorid,itemid)) AS distinct_pairs,
        COUNT(*) FILTER (WHERE coverage_status='MAPPED') AS mapped_pairs,
        COUNT(*) FILTER (WHERE coverage_status='UNKNOWN_REFERENCE') AS unknown_reference_pairs,
        COUNT(*) FILTER (WHERE coverage_status='BEFORE_FIRST') AS before_first_pairs,
        COUNT(*) FILTER (WHERE coverage_status='NO_HISTORY') AS no_history_pairs,
        COUNT(cart_ms) AS cart_pairs,COUNT(transaction_ms) AS transaction_pairs,
        COUNT(*) FILTER (WHERE (cart_ms IS NOT NULL AND NOT (cart_ms>first_view_ms AND cart_ms<=first_view_ms+p.window_ms))
            OR (transaction_ms IS NOT NULL AND (cart_ms IS NULL OR NOT (transaction_ms>cart_ms AND transaction_ms<=first_view_ms+p.window_ms)))) AS invalid_flow_pairs
    FROM outcomes CROSS JOIN parameters p
), base_admission AS (
    SELECT COALESCE(g.valid_cohort AND s.eligible_pairs=p.expected_eligible_pairs AND s.distinct_pairs=p.expected_eligible_pairs
        AND s.mapped_pairs=p.expected_mapped_pairs AND s.unknown_reference_pairs=p.expected_unknown_reference_pairs
        AND s.before_first_pairs=p.expected_before_first_pairs AND s.no_history_pairs=p.expected_no_history_pairs
        AND s.mapped_pairs+s.unknown_reference_pairs+s.before_first_pairs+s.no_history_pairs=s.eligible_pairs
        AND s.cart_pairs=p.expected_cart_pairs AND s.transaction_pairs=p.expected_transaction_pairs
        AND s.eligible_pairs>=s.cart_pairs AND s.cart_pairs>=s.transaction_pairs AND s.invalid_flow_pairs=0,false) AS valid_input
    FROM summary s CROSS JOIN parameters p CROSS JOIN cohort_guard g
), target_pairs AS MATERIALIZED (
    SELECT o.*,CASE WHEN o.available_coverage='MATCHED' AND o.available_value='1' THEN 'RECORDED_1'
        WHEN o.available_coverage='MATCHED' AND o.available_value='0' THEN 'RECORDED_0'
        WHEN o.available_coverage='BEFORE_FIRST' THEN 'BEFORE_FIRST'
        WHEN o.available_coverage='NO_HISTORY' THEN 'NO_HISTORY' ELSE 'INVALID' END AS availability_status
    FROM outcomes o CROSS JOIN parameters p CROSS JOIN base_admission a
    WHERE a.valid_input AND o.coverage_status='MAPPED' AND o.categoryid=p.target_categoryid
), target_health AS (
    SELECT COUNT(*) AS eligible_pairs,COUNT(DISTINCT (visitorid,itemid)) AS distinct_pairs,
        COUNT(cart_ms) AS cart_pairs,COUNT(transaction_ms) AS transaction_pairs,
        COUNT(*) FILTER (WHERE availability_status IN ('RECORDED_1','RECORDED_0','BEFORE_FIRST','NO_HISTORY')) AS classified_pairs
    FROM target_pairs
), admission AS (
    SELECT a.valid_input AND h.eligible_pairs=p.expected_target_pairs AND h.distinct_pairs=p.expected_target_pairs
        AND h.classified_pairs=p.expected_target_pairs AND h.cart_pairs=p.expected_target_carts
        AND h.transaction_pairs=p.expected_target_transactions AND h.eligible_pairs>=h.cart_pairs AND h.cart_pairs>=h.transaction_pairs AS valid_input
    FROM target_health h CROSS JOIN parameters p CROSS JOIN base_admission a
), groups AS (
    SELECT availability_status,COUNT(*) AS eligible_pairs,COUNT(cart_ms) AS cart_pairs,COUNT(transaction_ms) AS transaction_pairs
    FROM target_pairs GROUP BY availability_status
    UNION ALL SELECT 'TOTAL',COUNT(*),COUNT(cart_ms),COUNT(transaction_ms) FROM target_pairs
), labels(status_order,availability_status) AS (VALUES (1,'RECORDED_1'),(2,'RECORDED_0'),(3,'BEFORE_FIRST'),(4,'NO_HISTORY'),(5,'TOTAL')),
report AS (
    SELECT l.status_order,l.availability_status,COALESCE(g.eligible_pairs,0) AS eligible_pairs,
        COALESCE(g.cart_pairs,0) AS cart_pairs,COALESCE(g.transaction_pairs,0) AS transaction_pairs
    FROM labels l LEFT JOIN groups g USING(availability_status)
), report_health AS (
    SELECT SUM(eligible_pairs) FILTER (WHERE availability_status<>'TOTAL')=MAX(eligible_pairs) FILTER (WHERE availability_status='TOTAL')
        AND SUM(cart_pairs) FILTER (WHERE availability_status<>'TOTAL')=MAX(cart_pairs) FILTER (WHERE availability_status='TOTAL')
        AND SUM(transaction_pairs) FILTER (WHERE availability_status<>'TOTAL')=MAX(transaction_pairs) FILTER (WHERE availability_status='TOTAL')
        AND COUNT(*) FILTER (WHERE eligible_pairs<cart_pairs OR cart_pairs<transaction_pairs)=0 AS valid_report FROM report
)
SELECT r.availability_status,
    CASE WHEN a.valid_input AND v.valid_report THEN r.eligible_pairs END AS eligible_pairs,
    CASE WHEN a.valid_input AND v.valid_report THEN r.cart_pairs END AS cart_pairs,
    CASE WHEN a.valid_input AND v.valid_report THEN r.transaction_pairs END AS transaction_pairs,
    CASE WHEN a.valid_input AND v.valid_report THEN CAST(ROUND(100.0*r.eligible_pairs/NULLIF(h.eligible_pairs,0),4) AS DECIMAL(9,4)) END AS eligible_share_pct,
    CASE WHEN a.valid_input AND v.valid_report THEN CAST(ROUND(100.0*r.cart_pairs/NULLIF(r.eligible_pairs,0),4) AS DECIMAL(9,4)) END AS cart_rate_pct,
    CASE WHEN a.valid_input AND v.valid_report THEN CAST(ROUND(100.0*r.transaction_pairs/NULLIF(r.eligible_pairs,0),4) AS DECIMAL(9,4)) END AS transaction_rate_pct,
    CASE WHEN a.valid_input AND v.valid_report THEN CAST(ROUND(100.0*r.transaction_pairs/NULLIF(r.cart_pairs,0),4) AS DECIMAL(9,4)) END AS cart_to_transaction_rate_pct,
    CASE WHEN a.valid_input AND v.valid_report THEN 'PASS' ELSE 'BLOCKED' END AS check_status
FROM report r CROSS JOIN admission a CROSS JOIN report_health v CROSS JOIN target_health h ORDER BY r.status_order;
