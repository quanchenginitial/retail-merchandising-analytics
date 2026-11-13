-- Diagnose visitor-ID concentration for the same twelve exploratory pair cases.
-- Repeated visitor IDs are observed identifiers, not verified people or independent evidence.
WITH parameters AS (
    SELECT 22323::BIGINT AS expected_memberships,17672::BIGINT AS expected_baskets,
        15029::BIGINT AS expected_single_baskets,2643::BIGINT AS expected_multi_baskets,31::BIGINT AS expected_max_items,
        10757::BIGINT AS expected_pair_occurrences,9688::BIGINT AS expected_distinct_pairs,
        8785::BIGINT AS expected_pairs_seen_once,903::BIGINT AS expected_pairs_seen_2plus,39::BIGINT AS expected_max_pair_baskets,
        5::BIGINT AS min_pair_baskets,12::BIGINT AS expected_selected_pairs,110::BIGINT AS expected_selected_pair_occurrences
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
), selected_pairs AS MATERIALIZED (
    -- At equal n_ab and fixed N, smaller n_a*n_b means larger unrounded lift.
    SELECT ROW_NUMBER() OVER (ORDER BY m.n_ab DESC,m.n_a*m.n_b ASC,m.item_a ASC,m.item_b ASC) AS case_rank,m.*
    FROM pair_metrics m CROSS JOIN parameters p WHERE m.n_ab>=p.min_pair_baskets
), selected_health AS (
    SELECT COUNT(*) AS selected_pairs,COALESCE(SUM(n_ab),0)::BIGINT AS selected_pair_occurrences FROM selected_pairs
), selected_gate AS (
    SELECT s.selected_pairs=p.expected_selected_pairs AND s.selected_pair_occurrences=p.expected_selected_pair_occurrences AS valid_selection
    FROM selected_health s CROSS JOIN parameters p
), selected_visitor_groups AS MATERIALIZED (
    SELECT s.case_rank,s.item_a,s.item_b,a.visitorid,COUNT(*)::BIGINT AS pair_baskets
    FROM selected_pairs s JOIN eligible_keys a ON a.itemid=s.item_a
    JOIN eligible_keys b ON b.itemid=s.item_b AND a.visitorid=b.visitorid AND a.transactionid=b.transactionid
    GROUP BY s.case_rank,s.item_a,s.item_b,a.visitorid
), visitor_summaries AS MATERIALIZED (
    SELECT case_rank,COUNT(*)::BIGINT AS distinct_visitor_ids,
        COUNT(*) FILTER (WHERE pair_baskets>=2)::BIGINT AS repeat_visitor_ids,
        MAX(pair_baskets)::BIGINT AS max_baskets_one_visitor,
        SUM(pair_baskets)::BIGINT AS reconciled_pair_baskets,
        COALESCE(SUM(pair_baskets) FILTER (WHERE pair_baskets>=2),0)::BIGINT AS repeat_visitor_baskets
    FROM selected_visitor_groups GROUP BY case_rank
), concentration_health AS (
    SELECT COUNT(*) AS cases_checked,COALESCE(SUM(v.reconciled_pair_baskets),0)::BIGINT AS reconciled_pair_baskets,
        COUNT(*) FILTER (WHERE NOT COALESCE(v.reconciled_pair_baskets=s.n_ab
            AND v.distinct_visitor_ids>=1 AND v.distinct_visitor_ids<=s.n_ab
            AND v.repeat_visitor_ids>=0 AND v.repeat_visitor_ids<=v.distinct_visitor_ids
            AND v.max_baskets_one_visitor>=1 AND v.max_baskets_one_visitor<=s.n_ab
            AND v.repeat_visitor_baskets>=0 AND v.repeat_visitor_baskets<=s.n_ab,false)) AS invalid_cases
    FROM selected_pairs s LEFT JOIN visitor_summaries v USING (case_rank)
), concentration_gate AS (
    SELECT h.cases_checked=p.expected_selected_pairs AND h.reconciled_pair_baskets=p.expected_selected_pair_occurrences
        AND h.invalid_cases=0 AS valid_concentration
    FROM concentration_health h CROSS JOIN parameters p
), case_slots AS (
    SELECT UNNEST(range(1,expected_selected_pairs+1)) AS case_rank FROM parameters
)
SELECT printf('PAIR_%02d',c.case_rank) AS case_label,
    CASE WHEN a.valid_input AND g.valid_metrics AND s.valid_selection AND h.valid_concentration THEN m.n_ab END AS n_ab,
    CASE WHEN a.valid_input AND g.valid_metrics AND s.valid_selection AND h.valid_concentration THEN v.distinct_visitor_ids END AS distinct_visitor_ids,
    CASE WHEN a.valid_input AND g.valid_metrics AND s.valid_selection AND h.valid_concentration THEN v.repeat_visitor_ids END AS repeat_visitor_ids,
    CASE WHEN a.valid_input AND g.valid_metrics AND s.valid_selection AND h.valid_concentration THEN v.max_baskets_one_visitor END AS max_baskets_one_visitor,
    CASE WHEN a.valid_input AND g.valid_metrics AND s.valid_selection AND h.valid_concentration THEN ROUND(100.0*v.max_baskets_one_visitor/m.n_ab,6) END AS top_visitor_share_pct,
    CASE WHEN a.valid_input AND g.valid_metrics AND s.valid_selection AND h.valid_concentration THEN ROUND(100.0*v.repeat_visitor_baskets/m.n_ab,6) END AS repeat_visitor_basket_share_pct,
    CASE WHEN NOT a.valid_input THEN 'BLOCKED'
        WHEN NOT g.valid_metrics OR NOT s.valid_selection OR NOT h.valid_concentration THEN 'FAIL' ELSE 'PASS' END AS check_status
FROM case_slots c LEFT JOIN selected_pairs m USING (case_rank) LEFT JOIN visitor_summaries v USING (case_rank)
CROSS JOIN admission a CROSS JOIN metric_gate g CROSS JOIN selected_gate s CROSS JOIN concentration_gate h ORDER BY c.case_rank;
