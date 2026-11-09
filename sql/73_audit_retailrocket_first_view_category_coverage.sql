-- Category coverage at first observed view for the accepted seven-day-eligible pair cohort.
-- Conflicting tied first-view snapshots block output; no arbitrary selection or backward fill.
WITH parameters AS (
    SELECT 2756101::BIGINT AS expected_rows,2664312::BIGINT AS expected_views,
        69332::BIGINT AS expected_carts,22457::BIGINT AS expected_transactions,
        460::BIGINT AS expected_duplicate_surplus,253402300799999::BIGINT AS max_supported_ms,
        604800000::BIGINT AS window_ms,1442545187788::BIGINT AS expected_observation_end_ms,
        2042310::BIGINT AS expected_eligible_pairs,1669::BIGINT AS expected_reference_ids
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
        AND rh.invalid_ids=0,false) AS valid_input,
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
    SELECT s.*,CASE WHEN s.categoryid_coverage='BEFORE_FIRST' THEN 'BEFORE_FIRST'
        WHEN s.categoryid_coverage='NO_HISTORY' THEN 'NO_HISTORY'
        WHEN s.categoryid_coverage='MATCHED' AND r.categoryid IS NOT NULL THEN 'MAPPED'
        WHEN s.categoryid_coverage='MATCHED' THEN 'UNKNOWN_REFERENCE' ELSE 'INVALID' END AS coverage_status
    FROM snapshots s LEFT JOIN reference_rows r ON TRY_CAST(s.categoryid_value AS BIGINT)=r.categoryid
), summary AS (
    SELECT COUNT(*) AS eligible_pairs,COUNT(DISTINCT (visitorid,itemid)) AS distinct_pairs,
        COUNT(*) FILTER (WHERE coverage_status IN ('MAPPED','UNKNOWN_REFERENCE','BEFORE_FIRST','NO_HISTORY')) AS classified_pairs
    FROM classified
), admission AS (
    SELECT g.valid_cohort AND s.eligible_pairs=g.expected_eligible_pairs AND s.distinct_pairs=g.expected_eligible_pairs
        AND s.classified_pairs=g.expected_eligible_pairs AS valid_input,g.expected_eligible_pairs FROM cohort_guard g CROSS JOIN summary s
), counts AS (
    SELECT coverage_status,COUNT(*) AS eligible_pairs FROM classified GROUP BY coverage_status
    UNION ALL SELECT 'TOTAL',COUNT(*) FROM classified
), labels(status_order,coverage_status) AS (VALUES (1,'MAPPED'),(2,'UNKNOWN_REFERENCE'),(3,'BEFORE_FIRST'),(4,'NO_HISTORY'),(5,'TOTAL'))
SELECT l.coverage_status,CASE WHEN a.valid_input THEN COALESCE(c.eligible_pairs,0) END AS eligible_pairs,
    CASE WHEN a.valid_input THEN CAST(ROUND(100.0*COALESCE(c.eligible_pairs,0)/NULLIF(a.expected_eligible_pairs,0),4) AS DECIMAL(9,4)) END AS share_of_eligible_pairs_pct,
    CASE WHEN a.valid_input THEN 'PASS' ELSE 'BLOCKED' END AS check_status
FROM labels l CROSS JOIN admission a LEFT JOIN counts c USING(coverage_status) ORDER BY l.status_order;
