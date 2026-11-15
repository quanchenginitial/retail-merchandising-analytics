-- Build once: additive R/F cell counts for a later BI model; no TOTAL or stored percentages.
CREATE SCHEMA IF NOT EXISTS rr_bi;
CREATE TABLE rr_bi.rf_segment_summary AS
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
)
SELECT CASE WHEN a.valid_input AND g.valid_rf THEN CAST(p.reference_timestamp_ms AS BIGINT) ELSE error('SQL89 source/RF contract failed; destination was not created') END AS reference_timestamp_ms,
    CASE WHEN a.valid_input AND g.valid_rf THEN CAST(m.r_order AS BIGINT) ELSE error('SQL89 source/RF contract failed; destination was not created') END AS recency_order,
    CASE WHEN a.valid_input AND g.valid_rf THEN CAST(m.recency_band AS VARCHAR) ELSE error('SQL89 source/RF contract failed; destination was not created') END AS recency_band,
    CASE WHEN a.valid_input AND g.valid_rf THEN CAST(m.f_order AS BIGINT) ELSE error('SQL89 source/RF contract failed; destination was not created') END AS frequency_order,
    CASE WHEN a.valid_input AND g.valid_rf THEN CAST(m.frequency_band AS VARCHAR) ELSE error('SQL89 source/RF contract failed; destination was not created') END AS frequency_band,
    CASE WHEN a.valid_input AND g.valid_rf THEN CAST(m.visitor_ids AS BIGINT) ELSE error('SQL89 source/RF contract failed; destination was not created') END AS visitor_ids,
    CASE WHEN a.valid_input AND g.valid_rf THEN CAST(m.candidate_baskets AS BIGINT) ELSE error('SQL89 source/RF contract failed; destination was not created') END AS candidate_baskets
FROM matrix_summary m CROSS JOIN parameters p CROSS JOIN admission a CROSS JOIN rf_gate g;

-- CHECKS: if the target already exists, run only the read-only query below.
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
), expected_schema AS (
    SELECT * FROM (VALUES ('reference_timestamp_ms','BIGINT',1),('recency_order','BIGINT',2),('recency_band','VARCHAR',3),
        ('frequency_order','BIGINT',4),('frequency_band','VARCHAR',5),('visitor_ids','BIGINT',6),('candidate_baskets','BIGINT',7))
        t(column_name,data_type,ordinal_position)
), actual_schema AS (
    SELECT column_name,data_type,ordinal_position FROM information_schema.columns
    WHERE table_catalog=current_database() AND table_schema='rr_bi' AND table_name='rf_segment_summary'
), schema_health AS (
    SELECT COUNT(*) FILTER (WHERE e.data_type IS DISTINCT FROM a.data_type OR e.ordinal_position IS DISTINCT FROM a.ordinal_position) AS schema_mismatch
    FROM expected_schema e FULL OUTER JOIN actual_schema a USING (column_name)
), expected_rows AS MATERIALIZED (
    SELECT p.reference_timestamp_ms::BIGINT AS reference_timestamp_ms,m.r_order::BIGINT AS recency_order,m.recency_band::VARCHAR AS recency_band,
        m.f_order::BIGINT AS frequency_order,m.frequency_band::VARCHAR AS frequency_band,m.visitor_ids::BIGINT AS visitor_ids,
        m.candidate_baskets::BIGINT AS candidate_baskets
    FROM matrix_summary m CROSS JOIN parameters p CROSS JOIN admission a CROSS JOIN rf_gate g WHERE a.valid_input AND g.valid_rf
), summary_rows AS MATERIALIZED (
    SELECT TRY_CAST(reference_timestamp_ms AS BIGINT) AS reference_timestamp_ms,TRY_CAST(recency_order AS BIGINT) AS recency_order,
        CAST(recency_band AS VARCHAR) AS recency_band,TRY_CAST(frequency_order AS BIGINT) AS frequency_order,
        CAST(frequency_band AS VARCHAR) AS frequency_band,TRY_CAST(visitor_ids AS BIGINT) AS visitor_ids,
        TRY_CAST(candidate_baskets AS BIGINT) AS candidate_baskets
    FROM rr_bi.rf_segment_summary
), summary_health AS (
    SELECT COUNT(*) AS summary_rows,COUNT(DISTINCT (s.reference_timestamp_ms,recency_order,frequency_order)) AS distinct_rf_keys,
        COUNT(*)-COUNT(DISTINCT (s.reference_timestamp_ms,recency_order,frequency_order)) AS duplicate_key_surplus,
        COUNT(*) FILTER (WHERE s.reference_timestamp_ms IS NULL OR recency_order IS NULL OR recency_band IS NULL
            OR frequency_order IS NULL OR frequency_band IS NULL OR visitor_ids IS NULL OR candidate_baskets IS NULL) AS missing_required_rows,
        COUNT(*) FILTER (WHERE visitor_ids<0 OR candidate_baskets<0) AS negative_count_rows,
        COUNT(*) FILTER (WHERE NOT COALESCE(recency_order BETWEEN 1 AND 4 AND frequency_order BETWEEN 1 AND 4
            AND recency_band=CASE recency_order WHEN 1 THEN 'R_LT_7D' WHEN 2 THEN 'R_7_TO_LT_30D' WHEN 3 THEN 'R_30_TO_LT_60D' WHEN 4 THEN 'R_GE_60D' END
            AND frequency_band=CASE frequency_order WHEN 1 THEN 'F_1' WHEN 2 THEN 'F_2' WHEN 3 THEN 'F_3_4' WHEN 4 THEN 'F_5_PLUS' END,false)) AS invalid_band_order_rows,
        COUNT(*) FILTER (WHERE s.reference_timestamp_ms IS DISTINCT FROM p.reference_timestamp_ms) AS reference_mismatch_rows,
        COUNT(DISTINCT recency_order) AS distinct_recency_orders,COUNT(DISTINCT frequency_order) AS distinct_frequency_orders,
        COALESCE(SUM(visitor_ids),0)::BIGINT AS visitor_ids_total,COALESCE(SUM(candidate_baskets),0)::BIGINT AS candidate_baskets_total,
        COUNT(*) FILTER (WHERE recency_band='TOTAL' OR frequency_band='TOTAL') AS total_label_rows,
        COUNT(*) FILTER (WHERE NOT COALESCE(visitor_ids>=0 AND candidate_baskets>=visitor_ids AND (visitor_ids>0 OR candidate_baskets=0)
            AND CASE frequency_order WHEN 1 THEN candidate_baskets=visitor_ids WHEN 2 THEN candidate_baskets=2*visitor_ids
                WHEN 3 THEN candidate_baskets BETWEEN 3*visitor_ids AND 4*visitor_ids WHEN 4 THEN candidate_baskets>=5*visitor_ids ELSE false END,false)) AS cell_count_inconsistency_rows
    FROM summary_rows s CROSS JOIN parameters p
), differences AS (
    SELECT (SELECT COUNT(*) FROM (SELECT * FROM expected_rows EXCEPT ALL SELECT * FROM summary_rows) d) AS expected_only_rows,
        (SELECT COUNT(*) FROM (SELECT * FROM summary_rows EXCEPT ALL SELECT * FROM expected_rows) d) AS summary_only_rows
), checks AS (
    SELECT v.check_order,v.check_name,CAST(v.actual AS VARCHAR) AS actual,CAST(v.expected AS VARCHAR) AS expected
    FROM summary_health h CROSS JOIN parameters p CROSS JOIN schema_health s CROSS JOIN source_health src
    CROSS JOIN admission a CROSS JOIN rf_gate g CROSS JOIN differences d
    CROSS JOIN LATERAL (VALUES
        (1,'summary_rows',h.summary_rows,16),
        (2,'column_count',(SELECT COUNT(*) FROM actual_schema),7),
        (3,'schema_mismatch',s.schema_mismatch,0),
        (4,'distinct_rf_keys',h.distinct_rf_keys,16),
        (5,'missing_required_rows',h.missing_required_rows,0),
        (6,'negative_count_rows',h.negative_count_rows,0),
        (7,'invalid_band_order_rows',h.invalid_band_order_rows,0),
        (8,'reference_mismatch_rows',h.reference_mismatch_rows,0),
        (9,'distinct_recency_orders',h.distinct_recency_orders,4),
        (10,'distinct_frequency_orders',h.distinct_frequency_orders,4),
        (11,'visitor_ids_total',h.visitor_ids_total,p.expected_visitor_ids),
        (12,'candidate_baskets_total',h.candidate_baskets_total,p.expected_baskets),
        (13,'total_label_rows',h.total_label_rows,0),
        (14,'duplicate_key_surplus',h.duplicate_key_surplus,0),
        (15,'source_membership_rows',src.memberships,p.expected_memberships),
        (16,'source_contract_violations',CASE WHEN a.valid_input THEN 0 ELSE 1 END,0),
        (17,'source_rf_contract_violations',CASE WHEN g.valid_rf THEN 0 ELSE 1 END,0),
        (18,'expected_only_rows',d.expected_only_rows,0),
        (19,'summary_only_rows',d.summary_only_rows,0),
        (20,'cell_count_inconsistency_rows',h.cell_count_inconsistency_rows,0)
    ) v(check_order,check_name,actual,expected)
)
SELECT c.check_order,c.check_name,c.actual,c.expected,
    CASE WHEN c.check_order IN (18,19) AND NOT (a.valid_input AND g.valid_rf) THEN 'BLOCKED'
        WHEN c.actual=c.expected THEN 'PASS' ELSE 'FAIL' END AS status
FROM checks c CROSS JOIN admission a CROSS JOIN rf_gate g ORDER BY c.check_order;
