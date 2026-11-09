-- Two fixed first-view UTC cohorts; retain the global SQL74 category labels in both.
-- Outcomes keep their original seven-day deadline, including follow-up crossing 1 July.
WITH parameters AS (
    SELECT 2756101::BIGINT AS expected_rows,2664312::BIGINT AS expected_views,
        69332::BIGINT AS expected_carts,22457::BIGINT AS expected_transactions,
        460::BIGINT AS expected_duplicate_surplus,253402300799999::BIGINT AS max_supported_ms,
        604800000::BIGINT AS window_ms,1442545187788::BIGINT AS expected_observation_end_ms,
        2042310::BIGINT AS expected_eligible_pairs,1669::BIGINT AS expected_reference_ids,
        1527206::BIGINT AS expected_mapped_pairs,0::BIGINT AS expected_unknown_reference_pairs,
        304405::BIGINT AS expected_before_first_pairs,210699::BIGINT AS expected_no_history_pairs,
        43147::BIGINT AS expected_cart_pairs,15520::BIGINT AS expected_transaction_pairs,10::BIGINT AS top_n,1435708800000::BIGINT AS cohort_boundary_ms
), expected_global(segment,categoryid,eligible_pairs,cart_pairs,transaction_pairs) AS (VALUES
    -- EXPECTED SQL74 COUNTS BEGIN
('TOP_CATEGORY',1051,47963,871,309),
    ('TOP_CATEGORY',1483,41284,614,241),
    ('TOP_CATEGORY',959,32525,869,320),
    ('TOP_CATEGORY',342,30463,479,133),
    ('TOP_CATEGORY',1613,25105,483,76),
    ('TOP_CATEGORY',683,20147,488,134),
    ('TOP_CATEGORY',5,19706,321,128),
    ('TOP_CATEGORY',1279,18175,309,58),
    ('TOP_CATEGORY',196,17225,413,180),
    ('TOP_CATEGORY',646,16672,272,57),
    ('OTHER_MAPPED',NULL::BIGINT,1257941,29692,10826),
    ('UNKNOWN_REFERENCE',NULL::BIGINT,0,0,0),
    ('BEFORE_FIRST',NULL::BIGINT,304405,7626,2790),
    ('NO_HISTORY',NULL::BIGINT,210699,710,268),
    ('TOTAL',NULL::BIGINT,2042310,43147,15520)
-- EXPECTED SQL74 COUNTS END
), required_schema AS (
    SELECT CASE WHEN COUNT(*)=10 AND COUNT(*) FILTER (WHERE
        (column_name IN ('timestamp','visitorid','itemid','transactionid') AND data_type='BIGINT')
        OR (column_name IN ('event','categoryid_value','categoryid_source_file','categoryid_coverage') AND data_type='VARCHAR')
        OR (column_name IN ('categoryid_from_ms','categoryid_to_ms') AND data_type='BIGINT'))=10 THEN 0 ELSE 1 END AS schema_mismatch
    FROM information_schema.columns WHERE table_catalog=current_database()
        AND table_schema='rr_mart' AND table_name='events_enriched'
        AND column_name IN ('timestamp','visitorid','event','itemid','transactionid','categoryid_value','categoryid_from_ms','categoryid_to_ms','categoryid_source_file','categoryid_coverage')
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
        CAST(categoryid_coverage AS VARCHAR) AS categoryid_coverage,f.categoryid_to_ms IS NOT NULL AS original_category_end_present
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
                AND categoryid_to_ms IS NULL AND NOT original_category_end_present AND categoryid_source_file IS NULL),false)) AS invalid_category_rows
    FROM source_rows CROSS JOIN parameters p
), source_admission AS (
    SELECT COALESCE(s.schema_mismatch=0 AND h.rows=p.expected_rows AND h.rows>0 AND h.views=p.expected_views
        AND h.carts=p.expected_carts AND h.transactions=p.expected_transactions
        AND h.duplicate_surplus=p.expected_duplicate_surplus AND h.invalid_rows=0
        AND h.observation_end_ms=p.expected_observation_end_ms AND h.invalid_category_rows=0
        AND rs.schema_mismatch=0 AND rh.reference_rows=p.expected_reference_ids AND rh.distinct_ids=p.expected_reference_ids
        AND rh.invalid_ids=0 AND p.top_n>0 AND p.cohort_boundary_ms=1435708800000,false) AS valid_input,
        h.observation_end_ms,p.window_ms,p.expected_eligible_pairs
    FROM health h CROSS JOIN required_schema s CROSS JOIN parameters p CROSS JOIN reference_schema rs CROSS JOIN reference_health rh
), eligible AS MATERIALIZED (
    SELECT s.* FROM source_rows s CROSS JOIN source_admission a WHERE a.valid_input
), viewed_pairs AS (
    SELECT visitorid,itemid,MIN(timestamp) AS first_view_ms FROM eligible WHERE event='view' GROUP BY visitorid,itemid
), eligible_pairs AS MATERIALIZED (
    SELECT v.* FROM viewed_pairs v CROSS JOIN source_admission a WHERE v.first_view_ms+a.window_ms<=a.observation_end_ms
), first_view_rows AS MATERIALIZED (
    SELECT p.visitorid,p.itemid,p.first_view_ms,e.categoryid_value,e.categoryid_from_ms,e.categoryid_to_ms,e.categoryid_source_file,e.categoryid_coverage
    FROM eligible_pairs p JOIN eligible e ON e.visitorid=p.visitorid AND e.itemid=p.itemid AND e.timestamp=p.first_view_ms AND e.event='view'
), consistency AS (
    SELECT visitorid,itemid,COUNT(DISTINCT (categoryid_value,categoryid_from_ms,categoryid_to_ms,categoryid_source_file,categoryid_coverage)) AS attribute_tuples
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
    SELECT c.visitorid,c.itemid,c.categoryid,c.coverage_status,c.first_view_ms,t.cart_ms,MIN(e.timestamp) AS transaction_ms
    FROM classified c JOIN cart_times t USING(visitorid,itemid) CROSS JOIN parameters p LEFT JOIN eligible e
        ON e.visitorid=c.visitorid AND e.itemid=c.itemid AND e.event='transaction'
        AND e.timestamp>t.cart_ms AND e.timestamp<=c.first_view_ms+p.window_ms
    GROUP BY c.visitorid,c.itemid,c.categoryid,c.coverage_status,c.first_view_ms,t.cart_ms
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
), groups AS MATERIALIZED (
    SELECT coverage_status,categoryid,COUNT(*) AS eligible_pairs,COUNT(cart_ms) AS cart_pairs,COUNT(transaction_ms) AS transaction_pairs
    FROM outcomes CROSS JOIN base_admission a WHERE a.valid_input GROUP BY coverage_status,categoryid
), ranked AS (
    SELECT *,ROW_NUMBER() OVER (ORDER BY eligible_pairs DESC,categoryid ASC) AS population_rank FROM groups WHERE coverage_status='MAPPED'
), remaining AS (
    SELECT COALESCE(SUM(eligible_pairs),0)::BIGINT AS eligible_pairs,COALESCE(SUM(cart_pairs),0)::BIGINT AS cart_pairs,
        COALESCE(SUM(transaction_pairs),0)::BIGINT AS transaction_pairs FROM ranked CROSS JOIN parameters p WHERE population_rank>p.top_n
), unknown_labels(segment_order,segment) AS (VALUES (2,'UNKNOWN_REFERENCE'),(3,'BEFORE_FIRST'),(4,'NO_HISTORY')),
global_report AS (
    SELECT 0 AS segment_order,population_rank AS within_order,'TOP_CATEGORY' AS segment,categoryid,eligible_pairs,cart_pairs,transaction_pairs
    FROM ranked CROSS JOIN parameters p WHERE population_rank<=p.top_n
    UNION ALL SELECT 1,0,'OTHER_MAPPED',NULL::BIGINT,eligible_pairs,cart_pairs,transaction_pairs FROM remaining
    UNION ALL SELECT l.segment_order,0,l.segment,NULL::BIGINT,COALESCE(g.eligible_pairs,0),COALESCE(g.cart_pairs,0),COALESCE(g.transaction_pairs,0)
    FROM unknown_labels l LEFT JOIN groups g ON l.segment=g.coverage_status
    UNION ALL SELECT 5,0,'TOTAL',NULL::BIGINT,eligible_pairs,cart_pairs,transaction_pairs FROM summary
), global_contract AS (
    SELECT (SELECT COUNT(*) FROM (SELECT segment,categoryid,eligible_pairs,cart_pairs,transaction_pairs FROM global_report
        EXCEPT ALL SELECT * FROM expected_global))=0
    AND (SELECT COUNT(*) FROM (SELECT * FROM expected_global
        EXCEPT ALL SELECT segment,categoryid,eligible_pairs,cart_pairs,transaction_pairs FROM global_report))=0 AS valid_global
), admission AS (
    SELECT a.valid_input AND c.valid_global AS valid_input FROM base_admission a CROSS JOIN global_contract c
), cohorts(cohort_order,cohort) AS (VALUES (0,'EARLY'),(1,'LATE')),
labels AS (
    SELECT segment_order,within_order,segment,categoryid FROM global_report CROSS JOIN admission a
    WHERE a.valid_input OR segment<>'TOP_CATEGORY'
), assigned AS MATERIALIZED (
    SELECT o.visitorid,o.itemid,o.cart_ms,o.transaction_ms,
        CASE WHEN o.first_view_ms<p.cohort_boundary_ms THEN 'EARLY' ELSE 'LATE' END AS cohort,
        CASE WHEN o.coverage_status='MAPPED' AND r.population_rank<=p.top_n THEN 'TOP_CATEGORY'
            WHEN o.coverage_status='MAPPED' THEN 'OTHER_MAPPED' ELSE o.coverage_status END AS segment,
        CASE WHEN o.coverage_status='MAPPED' AND r.population_rank<=p.top_n THEN o.categoryid END AS categoryid
    FROM outcomes o CROSS JOIN parameters p CROSS JOIN admission a
    LEFT JOIN ranked r ON o.coverage_status='MAPPED' AND o.categoryid=r.categoryid WHERE a.valid_input
), period_counts AS (
    SELECT cohort,segment,categoryid,COUNT(*) AS eligible_pairs,COUNT(cart_ms) AS cart_pairs,COUNT(transaction_ms) AS transaction_pairs
    FROM assigned GROUP BY cohort,segment,categoryid
    UNION ALL SELECT c.cohort,'TOTAL',NULL::BIGINT,COUNT(a.visitorid),COUNT(a.cart_ms),COUNT(a.transaction_ms)
    FROM cohorts c LEFT JOIN assigned a ON c.cohort=a.cohort GROUP BY c.cohort
), report AS MATERIALIZED (
    SELECT c.cohort_order,c.cohort,l.segment_order,l.within_order,l.segment,l.categoryid,
        COALESCE(p.eligible_pairs,0) AS eligible_pairs,COALESCE(p.cart_pairs,0) AS cart_pairs,COALESCE(p.transaction_pairs,0) AS transaction_pairs
    FROM cohorts c CROSS JOIN labels l LEFT JOIN period_counts p
        ON c.cohort=p.cohort AND l.segment=p.segment AND l.categoryid IS NOT DISTINCT FROM p.categoryid
), period_health AS (
    SELECT cohort,SUM(eligible_pairs) FILTER (WHERE segment<>'TOTAL')=MAX(eligible_pairs) FILTER (WHERE segment='TOTAL')
        AND SUM(cart_pairs) FILTER (WHERE segment<>'TOTAL')=MAX(cart_pairs) FILTER (WHERE segment='TOTAL')
        AND SUM(transaction_pairs) FILTER (WHERE segment<>'TOTAL')=MAX(transaction_pairs) FILTER (WHERE segment='TOTAL')
        AND COUNT(*)=(SELECT COUNT(*) FROM labels)
        AND COUNT(*) FILTER (WHERE eligible_pairs<cart_pairs OR cart_pairs<transaction_pairs)=0 AS valid_period
    FROM report GROUP BY cohort
), across_periods AS (
    SELECT segment,categoryid,SUM(eligible_pairs)::BIGINT AS eligible_pairs,SUM(cart_pairs)::BIGINT AS cart_pairs,SUM(transaction_pairs)::BIGINT AS transaction_pairs
    FROM report GROUP BY segment,categoryid
), report_reconciliation AS (
    SELECT (SELECT COUNT(*) FROM period_health)=2 AND (SELECT COUNT(*) FROM period_health WHERE NOT valid_period)=0
        AND (SELECT COUNT(*) FROM (SELECT * FROM across_periods EXCEPT ALL SELECT * FROM expected_global))=0
        AND (SELECT COUNT(*) FROM (SELECT * FROM expected_global EXCEPT ALL SELECT * FROM across_periods))=0 AS valid_report
)
SELECT r.cohort,r.segment,r.categoryid,
    CASE WHEN a.valid_input AND v.valid_report THEN r.eligible_pairs END AS eligible_pairs,
    CASE WHEN a.valid_input AND v.valid_report THEN r.cart_pairs END AS cart_pairs,
    CASE WHEN a.valid_input AND v.valid_report THEN r.transaction_pairs END AS transaction_pairs,
    CASE WHEN a.valid_input AND v.valid_report THEN CAST(ROUND(100.0*r.cart_pairs/NULLIF(r.eligible_pairs,0),4) AS DECIMAL(9,4)) END AS cart_rate_pct,
    CASE WHEN a.valid_input AND v.valid_report THEN CAST(ROUND(100.0*r.transaction_pairs/NULLIF(r.eligible_pairs,0),4) AS DECIMAL(9,4)) END AS transaction_rate_pct,
    CASE WHEN a.valid_input AND v.valid_report THEN CAST(ROUND(100.0*r.transaction_pairs/NULLIF(r.cart_pairs,0),4) AS DECIMAL(9,4)) END AS cart_to_transaction_rate_pct,
    CASE WHEN a.valid_input AND v.valid_report THEN 'PASS' ELSE 'BLOCKED' END AS check_status
FROM report r CROSS JOIN admission a CROSS JOIN report_reconciliation v
WHERE (a.valid_input AND v.valid_report) OR r.segment<>'TOP_CATEGORY'
ORDER BY r.cohort_order,r.segment_order,r.within_order;
