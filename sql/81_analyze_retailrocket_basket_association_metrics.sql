-- Summarize binary co-occurrence metrics over every candidate basket, including singletons.
-- Threshold rows are nested diagnostics, not additive groups or selected recommendations.
WITH parameters AS (
    SELECT 22323::BIGINT AS expected_memberships,17672::BIGINT AS expected_baskets,
        15029::BIGINT AS expected_single_baskets,2643::BIGINT AS expected_multi_baskets,31::BIGINT AS expected_max_items,
        10757::BIGINT AS expected_pair_occurrences,9688::BIGINT AS expected_distinct_pairs,
        8785::BIGINT AS expected_pairs_seen_once,903::BIGINT AS expected_pairs_seen_2plus,39::BIGINT AS expected_max_pair_baskets
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
        COUNT(*) FILTER (WHERE items>1) AS multi_baskets,MAX(items) AS max_items,
        COALESCE(SUM(items*(items-1)//2),0)::BIGINT AS combinatorial_pair_occurrences FROM basket_sizes
), admission AS (
    SELECT COALESCE(s.schema_mismatch=0 AND h.memberships=p.expected_memberships AND h.memberships>0
        AND h.invalid_keys=0 AND h.duplicate_keys=0 AND b.baskets=p.expected_baskets
        AND b.single_baskets=p.expected_single_baskets AND b.multi_baskets=p.expected_multi_baskets
        AND b.max_items=p.expected_max_items,false) AS valid_input
    FROM required_schema s CROSS JOIN source_health h CROSS JOIN basket_health b CROSS JOIN parameters p
), eligible_keys AS MATERIALIZED (
    SELECT k.* FROM source_keys k CROSS JOIN admission a WHERE a.valid_input
), item_marginals AS MATERIALIZED (
    SELECT itemid,COUNT(*)::BIGINT AS item_baskets FROM eligible_keys GROUP BY itemid
), pair_counts AS MATERIALIZED (
    SELECT a.itemid AS item_a,b.itemid AS item_b,COUNT(*)::BIGINT AS n_ab
    FROM eligible_keys a JOIN eligible_keys b ON a.visitorid=b.visitorid AND a.transactionid=b.transactionid AND a.itemid<b.itemid
    GROUP BY a.itemid,b.itemid
), pair_summary AS (
    SELECT COALESCE(SUM(n_ab),0)::BIGINT AS pair_occurrences,COUNT(*) AS distinct_pairs,
        COUNT(*) FILTER (WHERE n_ab=1) AS seen_once,COUNT(*) FILTER (WHERE n_ab>=2) AS seen_2plus,
        MAX(n_ab) AS max_pair_baskets FROM pair_counts
), pair_metrics AS MATERIALIZED (
    SELECT p.item_a,p.item_b,p.n_ab,a.item_baskets AS n_a,b.item_baskets AS n_b,h.baskets::BIGINT AS n_baskets,
        p.n_ab::DOUBLE/h.baskets AS support,
        p.n_ab::DOUBLE/a.item_baskets AS confidence_a_to_b,
        p.n_ab::DOUBLE/b.item_baskets AS confidence_b_to_a,
        (p.n_ab::DOUBLE*h.baskets)/(a.item_baskets::DOUBLE*b.item_baskets) AS lift
    FROM pair_counts p JOIN item_marginals a ON p.item_a=a.itemid JOIN item_marginals b ON p.item_b=b.itemid
    CROSS JOIN basket_health h
), metric_health AS (
    SELECT COUNT(*) AS metric_rows,COUNT(*) FILTER (WHERE NOT COALESCE(
        item_a<item_b AND n_ab>0 AND n_ab<=n_a AND n_ab<=n_b AND n_a<=n_baskets AND n_b<=n_baskets
        AND support>0 AND support<=1 AND confidence_a_to_b>0 AND confidence_a_to_b<=1
        AND confidence_b_to_a>0 AND confidence_b_to_a<=1 AND lift>0 AND isfinite(lift),false)) AS invalid_metric_rows
    FROM pair_metrics
), metric_gate AS (
    SELECT COALESCE(s.pair_occurrences=p.expected_pair_occurrences AND s.distinct_pairs=p.expected_distinct_pairs
        AND s.seen_once=p.expected_pairs_seen_once AND s.seen_2plus=p.expected_pairs_seen_2plus
        AND (s.max_pair_baskets IS NOT DISTINCT FROM p.expected_max_pair_baskets)
        AND s.pair_occurrences=b.combinatorial_pair_occurrences AND s.seen_once+s.seen_2plus=s.distinct_pairs
        AND m.metric_rows=s.distinct_pairs AND m.invalid_metric_rows=0
        AND (SELECT COALESCE(SUM(item_baskets),0) FROM item_marginals)=h.memberships,false) AS valid_metrics
    FROM pair_summary s CROSS JOIN parameters p CROSS JOIN basket_health b CROSS JOIN source_health h CROSS JOIN metric_health m
), thresholds AS (
    SELECT * FROM (VALUES (1::BIGINT),(2::BIGINT),(3::BIGINT),(5::BIGINT),(10::BIGINT)) t(min_pair_baskets)
), directional_confidences AS (
    SELECT n_ab,confidence_a_to_b AS confidence FROM pair_metrics
    UNION ALL SELECT n_ab,confidence_b_to_a FROM pair_metrics
), confidence_profile AS (
    SELECT t.min_pair_baskets,MEDIAN(d.confidence) AS median_confidence
    FROM thresholds t LEFT JOIN directional_confidences d ON d.n_ab>=t.min_pair_baskets GROUP BY t.min_pair_baskets
), threshold_profile AS (
    SELECT t.min_pair_baskets,COUNT(m.n_ab)::BIGINT AS retained_pairs,COALESCE(SUM(m.n_ab),0)::BIGINT AS retained_pair_occurrences,
        MEDIAN(m.support) AS median_support,MEDIAN(m.lift) AS median_lift,MAX(m.lift) AS max_lift
    FROM thresholds t LEFT JOIN pair_metrics m ON m.n_ab>=t.min_pair_baskets GROUP BY t.min_pair_baskets
)
SELECT t.min_pair_baskets,
    CASE WHEN a.valid_input AND g.valid_metrics THEN t.retained_pairs END AS retained_pairs,
    CASE WHEN a.valid_input AND g.valid_metrics THEN ROUND(100.0*t.retained_pairs/NULLIF(s.distinct_pairs,0),6) END AS retained_pair_pct,
    CASE WHEN a.valid_input AND g.valid_metrics THEN t.retained_pair_occurrences END AS retained_pair_occurrences,
    CASE WHEN a.valid_input AND g.valid_metrics THEN ROUND(100.0*t.median_support,6) END AS median_support_pct,
    CASE WHEN a.valid_input AND g.valid_metrics THEN ROUND(100.0*c.median_confidence,6) END AS median_directional_confidence_pct,
    CASE WHEN a.valid_input AND g.valid_metrics THEN ROUND(t.median_lift,6) END AS median_lift,
    CASE WHEN a.valid_input AND g.valid_metrics THEN ROUND(t.max_lift,6) END AS max_lift,
    CASE WHEN NOT a.valid_input THEN 'BLOCKED' WHEN NOT g.valid_metrics THEN 'FAIL' ELSE 'PASS' END AS check_status
FROM threshold_profile t JOIN confidence_profile c USING (min_pair_baskets)
CROSS JOIN admission a CROSS JOIN metric_gate g CROSS JOIN pair_summary s ORDER BY t.min_pair_baskets;
