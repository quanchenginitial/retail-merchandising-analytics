-- Observed candidate-basket frequency per transaction visitor ID; no recency or lifetime-loyalty inference.
-- A basket is the full visitorid/transactionid key, regardless of its number of item memberships.
WITH parameters AS (
    SELECT 22323::BIGINT AS expected_memberships,17672::BIGINT AS expected_baskets,
        15029::BIGINT AS expected_single_baskets,2643::BIGINT AS expected_multi_baskets,31::BIGINT AS expected_max_items,
        11719::BIGINT AS expected_visitor_ids
), required_schema AS (
    SELECT CASE WHEN COUNT(*)=3 AND COUNT(*) FILTER (WHERE data_type='BIGINT')=3 THEN 0 ELSE 1 END AS schema_mismatch
    FROM information_schema.columns WHERE table_catalog=current_database()
        AND table_schema='rr_mart' AND table_name='transaction_basket_items'
        AND column_name IN ('visitorid','transactionid','itemid')
), source_keys AS MATERIALIZED (
    SELECT TRY_CAST(visitorid AS BIGINT) AS visitorid,TRY_CAST(transactionid AS BIGINT) AS transactionid,
        TRY_CAST(itemid AS BIGINT) AS itemid FROM rr_mart.transaction_basket_items
), source_health AS (
    SELECT COUNT(*) AS memberships,COUNT(*)-COUNT(DISTINCT (visitorid,transactionid,itemid)) AS duplicate_keys,
        COUNT(*) FILTER (WHERE NOT COALESCE(visitorid>=0 AND transactionid>=0 AND itemid>=0,false)) AS invalid_keys
    FROM source_keys
), basket_sizes AS MATERIALIZED (
    SELECT visitorid,transactionid,COUNT(*) AS items FROM source_keys GROUP BY visitorid,transactionid
), basket_health AS (
    SELECT COUNT(*) AS baskets,COUNT(*) FILTER (WHERE items=1) AS single_baskets,
        COUNT(*) FILTER (WHERE items>1) AS multi_baskets,MAX(items) AS max_items FROM basket_sizes
), admission AS (
    SELECT COALESCE(s.schema_mismatch=0 AND h.memberships=p.expected_memberships AND h.memberships>0
        AND h.invalid_keys=0 AND h.duplicate_keys=0 AND b.baskets=p.expected_baskets
        AND b.single_baskets=p.expected_single_baskets AND b.multi_baskets=p.expected_multi_baskets
        AND b.max_items=p.expected_max_items,false) AS valid_input
    FROM required_schema s CROSS JOIN source_health h CROSS JOIN basket_health b CROSS JOIN parameters p
), eligible_baskets AS MATERIALIZED (
    SELECT b.visitorid,b.transactionid FROM basket_sizes b CROSS JOIN admission a WHERE a.valid_input
), visitor_frequency AS MATERIALIZED (
    SELECT visitorid,COUNT(*)::BIGINT AS basket_count FROM eligible_baskets GROUP BY visitorid
), frequency_health AS (
    SELECT COUNT(*)::BIGINT AS visitor_ids,COALESCE(SUM(basket_count),0)::BIGINT AS candidate_baskets,
        MAX(basket_count)::BIGINT AS max_baskets_per_visitor,
        COUNT(*) FILTER (WHERE NOT COALESCE(basket_count>=1 AND basket_count<=p.expected_baskets,false)) AS invalid_frequencies
    FROM visitor_frequency CROSS JOIN parameters p
), bands AS (
    SELECT * FROM (VALUES (1,'F_1',1::BIGINT,1::BIGINT),(2,'F_2',2::BIGINT,2::BIGINT),
        (3,'F_3_4',3::BIGINT,4::BIGINT),(4,'F_5_PLUS',5::BIGINT,NULL::BIGINT))
        t(band_order,frequency_band,min_baskets,max_baskets)
), band_summary AS MATERIALIZED (
    SELECT b.band_order,b.frequency_band,COUNT(v.visitorid)::BIGINT AS visitor_ids,
        COALESCE(SUM(v.basket_count),0)::BIGINT AS candidate_baskets,MAX(v.basket_count)::BIGINT AS max_baskets_per_visitor
    FROM bands b LEFT JOIN visitor_frequency v ON v.basket_count>=b.min_baskets
        AND (b.max_baskets IS NULL OR v.basket_count<=b.max_baskets)
    GROUP BY b.band_order,b.frequency_band
), partition_health AS (
    SELECT COUNT(*) AS band_rows,SUM(visitor_ids)::BIGINT AS visitor_ids,SUM(candidate_baskets)::BIGINT AS candidate_baskets,
        COUNT(*) FILTER (WHERE NOT COALESCE(visitor_ids>=0 AND candidate_baskets>=0
            AND ((visitor_ids=0 AND candidate_baskets=0 AND max_baskets_per_visitor IS NULL)
                OR (visitor_ids>0 AND candidate_baskets>=visitor_ids AND max_baskets_per_visitor>=1)),false)) AS invalid_bands
    FROM band_summary
), frequency_gate AS (
    SELECT f.visitor_ids=p.expected_visitor_ids AND f.candidate_baskets=p.expected_baskets AND f.invalid_frequencies=0
        AND b.band_rows=4 AND b.visitor_ids=f.visitor_ids AND b.candidate_baskets=f.candidate_baskets AND b.invalid_bands=0 AS valid_frequency
    FROM frequency_health f CROSS JOIN partition_health b CROSS JOIN parameters p
), report_rows AS (
    SELECT * FROM band_summary
    UNION ALL SELECT 5,'TOTAL',visitor_ids,candidate_baskets,max_baskets_per_visitor FROM frequency_health
)
SELECT r.frequency_band,
    CASE WHEN a.valid_input AND g.valid_frequency THEN r.visitor_ids END AS visitor_ids,
    CASE WHEN a.valid_input AND g.valid_frequency THEN ROUND(100.0*r.visitor_ids/NULLIF(f.visitor_ids,0),6) END AS visitor_share_pct,
    CASE WHEN a.valid_input AND g.valid_frequency THEN r.candidate_baskets END AS candidate_baskets,
    CASE WHEN a.valid_input AND g.valid_frequency THEN ROUND(100.0*r.candidate_baskets/NULLIF(f.candidate_baskets,0),6) END AS basket_share_pct,
    CASE WHEN a.valid_input AND g.valid_frequency THEN r.max_baskets_per_visitor END AS max_baskets_per_visitor,
    CASE WHEN NOT a.valid_input THEN 'BLOCKED' WHEN NOT g.valid_frequency THEN 'FAIL' ELSE 'PASS' END AS check_status
FROM report_rows r CROSS JOIN admission a CROSS JOIN frequency_gate g CROSS JOIN frequency_health f ORDER BY r.band_order;
