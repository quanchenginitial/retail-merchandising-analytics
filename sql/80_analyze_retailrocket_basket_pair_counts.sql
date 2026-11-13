-- Count unordered observed item pairs before defining association metrics.
-- All candidate baskets remain in the population; singleton baskets contribute zero pairs.
WITH parameters AS (
    SELECT 22323::BIGINT AS expected_memberships,17672::BIGINT AS expected_baskets,
        15029::BIGINT AS expected_single_baskets,2643::BIGINT AS expected_multi_baskets,31::BIGINT AS expected_max_items
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
), pair_counts AS MATERIALIZED (
    SELECT a.itemid AS item_a,b.itemid AS item_b,COUNT(*)::BIGINT AS basket_count
    FROM eligible_keys a JOIN eligible_keys b ON a.visitorid=b.visitorid AND a.transactionid=b.transactionid AND a.itemid<b.itemid
    GROUP BY a.itemid,b.itemid
), pair_summary AS (
    SELECT COALESCE(SUM(basket_count),0)::BIGINT AS pair_occurrences,COUNT(*) AS distinct_pairs,
        COUNT(*) FILTER (WHERE basket_count=1) AS seen_once,COUNT(*) FILTER (WHERE basket_count>=2) AS seen_2plus,
        MAX(basket_count) AS max_baskets_per_pair FROM pair_counts
), checks AS (
    SELECT 1 AS check_order,'membership_rows' AS check_name,h.memberships AS actual,p.expected_memberships AS expected FROM source_health h CROSS JOIN parameters p
    UNION ALL SELECT 2,'required_key_schema_mismatch',s.schema_mismatch,0 FROM required_schema s
    UNION ALL SELECT 3,'invalid_key_rows',h.invalid_keys,0 FROM source_health h
    UNION ALL SELECT 4,'duplicate_membership_keys',h.duplicate_keys,0 FROM source_health h
    UNION ALL SELECT 5,'candidate_baskets',b.baskets,p.expected_baskets FROM basket_health b CROSS JOIN parameters p
    UNION ALL SELECT 6,'single_item_baskets',b.single_baskets,p.expected_single_baskets FROM basket_health b CROSS JOIN parameters p
    UNION ALL SELECT 7,'multi_item_baskets',b.multi_baskets,p.expected_multi_baskets FROM basket_health b CROSS JOIN parameters p
    UNION ALL SELECT 8,'max_items_per_basket',b.max_items,p.expected_max_items FROM basket_health b CROSS JOIN parameters p
    UNION ALL SELECT 9,'pair_occurrences',s.pair_occurrences,NULL FROM pair_summary s
    UNION ALL SELECT 10,'distinct_item_pairs',s.distinct_pairs,NULL FROM pair_summary s
    UNION ALL SELECT 11,'pairs_seen_once',s.seen_once,NULL FROM pair_summary s
    UNION ALL SELECT 12,'pairs_seen_2plus',s.seen_2plus,NULL FROM pair_summary s
    UNION ALL SELECT 13,'max_baskets_per_pair',s.max_baskets_per_pair,NULL FROM pair_summary s
    UNION ALL SELECT 14,'pair_occurrence_reconciliation_difference',s.pair_occurrences-b.combinatorial_pair_occurrences,0 FROM pair_summary s CROSS JOIN basket_health b
    UNION ALL SELECT 15,'pair_frequency_partition_difference',s.seen_once+s.seen_2plus-s.distinct_pairs,0 FROM pair_summary s
)
SELECT c.check_order,c.check_name,CASE WHEN a.valid_input THEN CAST(c.actual AS BIGINT) END AS actual,c.expected,
    CASE WHEN NOT a.valid_input THEN 'BLOCKED' WHEN c.expected IS NULL THEN 'INFO'
        WHEN c.actual=c.expected THEN 'PASS' ELSE 'FAIL' END AS status
FROM checks c CROSS JOIN admission a ORDER BY c.check_order;
