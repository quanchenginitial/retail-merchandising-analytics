-- Descriptive R x F matrix for transaction-recorded visitor IDs at the frozen global event endpoint.
-- Cell basket counts sum each member visitor's full-window frequency, not baskets in that recency interval.
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
), eligible_baskets AS MATERIALIZED (
    SELECT b.visitorid,b.transactionid FROM basket_sizes b CROSS JOIN admission a WHERE a.valid_input
), visitor_frequency AS MATERIALIZED (
    SELECT visitorid,COUNT(*)::BIGINT AS basket_count FROM eligible_baskets GROUP BY visitorid
), visitor_last_transaction AS MATERIALIZED (
    SELECT visitorid,MAX(last_timestamp_ms)::BIGINT AS last_transaction_ms FROM eligible_memberships GROUP BY visitorid
), visitor_measures AS MATERIALIZED (
    SELECT f.visitorid,f.basket_count,t.last_transaction_ms,
        (p.reference_timestamp_ms-t.last_transaction_ms)::BIGINT AS recency_ms
    FROM visitor_frequency f JOIN visitor_last_transaction t USING (visitorid) CROSS JOIN parameters p
), recency_bands AS (
    SELECT * FROM (VALUES (1,'R_LT_7D',0::BIGINT,604800000::BIGINT),
        (2,'R_7_TO_LT_30D',604800000::BIGINT,2592000000::BIGINT),
        (3,'R_30_TO_LT_60D',2592000000::BIGINT,5184000000::BIGINT),
        (4,'R_GE_60D',5184000000::BIGINT,NULL::BIGINT)) t(r_order,recency_band,min_ms,max_ms)
), frequency_bands AS (
    SELECT * FROM (VALUES (1,'F_1',1::BIGINT,1::BIGINT),(2,'F_2',2::BIGINT,2::BIGINT),
        (3,'F_3_4',3::BIGINT,4::BIGINT),(4,'F_5_PLUS',5::BIGINT,NULL::BIGINT))
        t(f_order,frequency_band,min_baskets,max_baskets)
), visitor_rf AS MATERIALIZED (
    SELECT v.*,r.r_order,r.recency_band,f.f_order,f.frequency_band
    FROM visitor_measures v JOIN recency_bands r ON v.recency_ms>=r.min_ms AND (r.max_ms IS NULL OR v.recency_ms<r.max_ms)
    JOIN frequency_bands f ON v.basket_count>=f.min_baskets AND (f.max_baskets IS NULL OR v.basket_count<=f.max_baskets)
), rf_health AS (
    SELECT COUNT(*)::BIGINT AS visitor_ids,COALESCE(SUM(basket_count),0)::BIGINT AS candidate_baskets,
        COUNT(*) FILTER (WHERE NOT COALESCE(basket_count>=1 AND basket_count<=p.expected_baskets
            AND recency_ms>=0 AND recency_ms<=p.reference_timestamp_ms-p.source_min_timestamp_ms
            AND last_transaction_ms+recency_ms=p.reference_timestamp_ms,false)) AS invalid_measures
    FROM visitor_measures CROSS JOIN parameters p
), assignment_health AS (
    SELECT COUNT(*) AS assignment_errors FROM (
        SELECT v.visitorid FROM visitor_measures v LEFT JOIN visitor_rf r USING (visitorid)
        GROUP BY v.visitorid HAVING COUNT(r.visitorid)<>1
    ) errors
), matrix_summary AS MATERIALIZED (
    SELECT r.r_order,r.recency_band,f.f_order,f.frequency_band,COUNT(v.visitorid)::BIGINT AS visitor_ids,
        COALESCE(SUM(v.basket_count),0)::BIGINT AS candidate_baskets
    FROM recency_bands r CROSS JOIN frequency_bands f LEFT JOIN visitor_rf v
        ON v.recency_band=r.recency_band AND v.frequency_band=f.frequency_band
    GROUP BY r.r_order,r.recency_band,f.f_order,f.frequency_band
), matrix_health AS (
    SELECT COUNT(*) AS cells,SUM(visitor_ids)::BIGINT AS visitor_ids,SUM(candidate_baskets)::BIGINT AS candidate_baskets,
        COUNT(*) FILTER (WHERE NOT COALESCE(visitor_ids>=0 AND candidate_baskets>=visitor_ids
            AND (visitor_ids>0 OR candidate_baskets=0),false)) AS invalid_cells FROM matrix_summary
), direct_marginals AS MATERIALIZED (
    SELECT 'R' AS dimension,r.recency_band AS band,COUNT(v.visitorid)::BIGINT AS visitor_ids,
        COALESCE(SUM(v.basket_count),0)::BIGINT AS candidate_baskets
    FROM recency_bands r LEFT JOIN visitor_measures v ON v.recency_ms>=r.min_ms AND (r.max_ms IS NULL OR v.recency_ms<r.max_ms)
    GROUP BY r.recency_band
    UNION ALL
    SELECT 'F',f.frequency_band,COUNT(v.visitorid)::BIGINT,COALESCE(SUM(v.basket_count),0)::BIGINT
    FROM frequency_bands f LEFT JOIN visitor_measures v ON v.basket_count>=f.min_baskets AND (f.max_baskets IS NULL OR v.basket_count<=f.max_baskets)
    GROUP BY f.frequency_band
), matrix_marginals AS MATERIALIZED (
    SELECT 'R' AS dimension,recency_band AS band,SUM(visitor_ids)::BIGINT AS visitor_ids,SUM(candidate_baskets)::BIGINT AS candidate_baskets
    FROM matrix_summary GROUP BY recency_band
    UNION ALL SELECT 'F',frequency_band,SUM(visitor_ids)::BIGINT,SUM(candidate_baskets)::BIGINT FROM matrix_summary GROUP BY frequency_band
), marginal_health AS (
    SELECT (SELECT COUNT(*) FROM (SELECT * FROM direct_marginals EXCEPT ALL SELECT * FROM matrix_marginals) d)
        +(SELECT COUNT(*) FROM (SELECT * FROM matrix_marginals EXCEPT ALL SELECT * FROM direct_marginals) d) AS differences
), rf_gate AS (
    SELECT COALESCE(h.visitor_ids=p.expected_visitor_ids AND h.candidate_baskets=p.expected_baskets AND h.invalid_measures=0
        AND a.assignment_errors=0 AND m.cells=16 AND m.visitor_ids=h.visitor_ids AND m.candidate_baskets=h.candidate_baskets
        AND m.invalid_cells=0 AND g.differences=0,false) AS valid_rf
    FROM rf_health h CROSS JOIN assignment_health a CROSS JOIN matrix_health m CROSS JOIN marginal_health g CROSS JOIN parameters p
), report_rows AS (
    SELECT * FROM matrix_summary
    UNION ALL SELECT 5,'TOTAL',5,'TOTAL',visitor_ids,candidate_baskets FROM rf_health
)
SELECT r.recency_band,r.frequency_band,
    CASE WHEN a.valid_input AND g.valid_rf THEN r.visitor_ids END AS visitor_ids,
    CASE WHEN a.valid_input AND g.valid_rf THEN ROUND(100.0*r.visitor_ids/NULLIF(h.visitor_ids,0),6) END AS visitor_share_pct,
    CASE WHEN a.valid_input AND g.valid_rf THEN r.candidate_baskets END AS candidate_baskets,
    CASE WHEN a.valid_input AND g.valid_rf THEN ROUND(100.0*r.candidate_baskets/NULLIF(h.candidate_baskets,0),6) END AS basket_share_pct,
    CASE WHEN NOT a.valid_input THEN 'BLOCKED' WHEN NOT g.valid_rf THEN 'FAIL' ELSE 'PASS' END AS check_status
FROM report_rows r CROSS JOIN admission a CROSS JOIN rf_gate g CROSS JOIN rf_health h ORDER BY r.r_order,r.f_order;
