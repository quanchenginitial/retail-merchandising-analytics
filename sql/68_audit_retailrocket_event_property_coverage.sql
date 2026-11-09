-- Read-only event-to-observation coverage audit; no persistent join table.
-- Each property uses the last observation at/before the event, never a future value.
-- A matched NULL tail means last recorded observation, not confirmed freshness.
-- Preserve all original event occurrences, including exact duplicates.
WITH expected_counts AS (
    SELECT 2756101::BIGINT AS expected_event_rows,460::BIGINT AS expected_duplicate_surplus,
        2291853::BIGINT AS expected_interval_rows,788214::BIGINT AS expected_category_rows,
        1503639::BIGINT AS expected_available_rows,253402300799999::BIGINT AS max_supported_ms
), event_schema AS (
    SELECT CASE WHEN COUNT(*)=5 AND COUNT(*) FILTER (WHERE
        column_name=CASE ordinal_position WHEN 1 THEN 'timestamp' WHEN 2 THEN 'visitorid' WHEN 3 THEN 'event'
            WHEN 4 THEN 'itemid' WHEN 5 THEN 'transactionid' END
        AND data_type=CASE WHEN ordinal_position=3 THEN 'VARCHAR' ELSE 'BIGINT' END)=5 THEN 0 ELSE 1 END AS event_schema_mismatch
    FROM information_schema.columns
    WHERE table_catalog=current_database() AND table_schema='rr_stg' AND table_name='events'
), interval_schema AS (
    SELECT CASE WHEN COUNT(*)=6 AND COUNT(*) FILTER (WHERE
        column_name=CASE ordinal_position WHEN 1 THEN 'itemid' WHEN 2 THEN 'property' WHEN 3 THEN 'value'
            WHEN 4 THEN 'observed_from_ms' WHEN 5 THEN 'observed_to_ms' WHEN 6 THEN 'source_file' END
        AND data_type=CASE WHEN ordinal_position IN (1,4,5) THEN 'BIGINT' ELSE 'VARCHAR' END)=6 THEN 0 ELSE 1 END AS interval_schema_mismatch
    FROM information_schema.columns
    WHERE table_catalog=current_database() AND table_schema='rr_core' AND table_name='item_state_intervals'
), event_rows AS MATERIALIZED (
    SELECT TRY_CAST(timestamp AS BIGINT) AS timestamp,TRY_CAST(visitorid AS BIGINT) AS visitorid,
        CAST(event AS VARCHAR) AS event,TRY_CAST(itemid AS BIGINT) AS itemid,
        TRY_CAST(transactionid AS BIGINT) AS transactionid,e.transactionid IS NOT NULL AS original_transaction_present
    FROM rr_stg.events e
), interval_rows AS MATERIALIZED (
    SELECT TRY_CAST(itemid AS BIGINT) AS itemid,CAST(property AS VARCHAR) AS property,CAST(value AS VARCHAR) AS value,
        TRY_CAST(observed_from_ms AS BIGINT) AS observed_from_ms,TRY_CAST(observed_to_ms AS BIGINT) AS observed_to_ms,
        CAST(source_file AS VARCHAR) AS source_file,i.observed_to_ms IS NOT NULL AS original_end_present
    FROM rr_core.item_state_intervals i
), event_health AS (
    SELECT COUNT(*) AS event_rows,
        COUNT(*) FILTER (WHERE NOT COALESCE(timestamp BETWEEN 0 AND e.max_supported_ms AND visitorid>=0 AND itemid>=0
            AND event IN ('view','addtocart','transaction')
            AND ((event='transaction' AND original_transaction_present AND transactionid>=0)
                OR (event<>'transaction' AND NOT original_transaction_present)),false)) AS invalid_event_rows,
        COUNT(*)-COUNT(DISTINCT (timestamp,visitorid,event,itemid,transactionid)) AS event_duplicate_surplus
    FROM event_rows CROSS JOIN expected_counts e
), interval_links AS MATERIALIZED (
    SELECT *,LEAD(observed_from_ms) OVER (PARTITION BY itemid,property ORDER BY observed_from_ms) AS expected_next_start
    FROM interval_rows
), interval_health AS (
    SELECT COUNT(*) AS interval_rows,
        COUNT(*) FILTER (WHERE NOT COALESCE(itemid>=0 AND observed_from_ms BETWEEN 0 AND e.max_supported_ms
            AND (NOT original_end_present OR (observed_to_ms BETWEEN 0 AND e.max_supported_ms AND observed_to_ms>observed_from_ms))
            AND ((property='available' AND value IN ('0','1')) OR (property='categoryid' AND regexp_full_match(value,'[0-9]+')
                AND TRY_CAST(value AS BIGINT) IS NOT NULL))
            AND source_file IN ('item_properties_part1.csv','item_properties_part2.csv'),false)) AS invalid_interval_rows,
        COUNT(*)-COUNT(DISTINCT (itemid,property,observed_from_ms)) AS interval_candidate_key_surplus,
        COUNT(*) FILTER (WHERE observed_to_ms IS DISTINCT FROM expected_next_start) AS interval_chain_errors,
        COUNT(*) FILTER (WHERE property='categoryid') AS categoryid_interval_rows,
        COUNT(*) FILTER (WHERE property='available') AS available_interval_rows
    FROM interval_links CROSS JOIN expected_counts e
), admission AS MATERIALIZED (
    SELECT e.*,i.*,es.*,s.*,p.*,COALESCE(es.event_schema_mismatch=0 AND s.interval_schema_mismatch=0
        AND e.event_rows=p.expected_event_rows AND e.event_rows>0 AND e.invalid_event_rows=0
        AND e.event_duplicate_surplus=p.expected_duplicate_surplus AND i.interval_rows=p.expected_interval_rows AND i.interval_rows>0
        AND i.invalid_interval_rows=0 AND i.interval_candidate_key_surplus=0 AND i.interval_chain_errors=0
        AND i.categoryid_interval_rows=p.expected_category_rows AND i.available_interval_rows=p.expected_available_rows,false) AS valid_input
    FROM event_health e CROSS JOIN interval_health i CROSS JOIN event_schema es CROSS JOIN interval_schema s CROSS JOIN expected_counts p
), eligible_events AS MATERIALIZED (
    SELECT e.timestamp,e.visitorid,e.event,e.itemid,e.transactionid FROM event_rows e CROSS JOIN admission a WHERE a.valid_input
), category_intervals AS (
    SELECT i.itemid,i.value,i.observed_from_ms,i.observed_to_ms,i.source_file
    FROM interval_rows i CROSS JOIN admission a WHERE a.valid_input AND i.property='categoryid'
), available_intervals AS (
    SELECT i.itemid,i.value,i.observed_from_ms,i.observed_to_ms,i.source_file
    FROM interval_rows i CROSS JOIN admission a WHERE a.valid_input AND i.property='available'
), first_observations AS (
    SELECT i.itemid,MIN(i.observed_from_ms) FILTER (WHERE i.property='categoryid') AS first_category_ms,
        MIN(i.observed_from_ms) FILTER (WHERE i.property='available') AS first_available_ms
    FROM interval_rows i CROSS JOIN admission a WHERE a.valid_input GROUP BY i.itemid
), joined AS MATERIALIZED (
    SELECT e.timestamp,e.visitorid,e.event,e.itemid,e.transactionid,
        c.value AS categoryid_value,c.observed_from_ms AS categoryid_from_ms,c.observed_to_ms AS categoryid_to_ms,
        c.source_file AS categoryid_source_file,a.value AS available_value,a.observed_from_ms AS available_from_ms,
        a.observed_to_ms AS available_to_ms,a.source_file AS available_source_file,h.first_category_ms,h.first_available_ms
    FROM eligible_events e LEFT JOIN first_observations h ON e.itemid=h.itemid
    ASOF LEFT JOIN category_intervals c ON e.itemid=c.itemid AND e.timestamp>=c.observed_from_ms
    ASOF LEFT JOIN available_intervals a ON e.itemid=a.itemid AND e.timestamp>=a.observed_from_ms
), classified AS MATERIALIZED (
    SELECT *,CASE WHEN categoryid_from_ms IS NOT NULL THEN 'MATCHED' WHEN first_category_ms IS NULL THEN 'NO_HISTORY'
        WHEN timestamp<first_category_ms THEN 'BEFORE_FIRST' ELSE 'INVALID' END AS categoryid_coverage,
        CASE WHEN available_from_ms IS NOT NULL THEN 'MATCHED' WHEN first_available_ms IS NULL THEN 'NO_HISTORY'
        WHEN timestamp<first_available_ms THEN 'BEFORE_FIRST' ELSE 'INVALID' END AS available_coverage
    FROM joined
)
-- REPORT: the validator reuses the guarded prefix above for its private occurrence stream.
, match_health AS (
    SELECT COUNT(*) AS joined_rows,
        COUNT(*) FILTER (WHERE categoryid_from_ms>timestamp) AS categoryid_future_match_rows,
        COUNT(*) FILTER (WHERE available_from_ms>timestamp) AS available_future_match_rows,
        COUNT(*) FILTER (WHERE categoryid_from_ms IS NOT NULL AND categoryid_to_ms IS NOT NULL AND timestamp>=categoryid_to_ms) AS categoryid_boundary_error_rows,
        COUNT(*) FILTER (WHERE available_from_ms IS NOT NULL AND available_to_ms IS NOT NULL AND timestamp>=available_to_ms) AS available_boundary_error_rows,
        COUNT(*) FILTER (WHERE categoryid_coverage='MATCHED') AS categoryid_matched_rows,
        COUNT(*) FILTER (WHERE categoryid_coverage='BEFORE_FIRST') AS categoryid_before_first_rows,
        COUNT(*) FILTER (WHERE categoryid_coverage='NO_HISTORY') AS categoryid_no_history_rows,
        COUNT(*) FILTER (WHERE categoryid_coverage='MATCHED' AND categoryid_to_ms IS NULL) AS categoryid_open_tail_match_rows,
        COUNT(*) FILTER (WHERE available_coverage='MATCHED') AS available_matched_rows,
        COUNT(*) FILTER (WHERE available_coverage='BEFORE_FIRST') AS available_before_first_rows,
        COUNT(*) FILTER (WHERE available_coverage='NO_HISTORY') AS available_no_history_rows,
        COUNT(*) FILTER (WHERE available_coverage='MATCHED' AND available_to_ms IS NULL) AS available_open_tail_match_rows
    FROM classified
), metrics AS MATERIALIZED (
    SELECT a.*,h.* FROM admission a CROSS JOIN match_health h
), controls AS (
    SELECT 1 AS check_order,'event_rows' AS check_name,event_rows AS actual,expected_event_rows AS expected FROM metrics
    UNION ALL SELECT 2,'event_schema_mismatch',event_schema_mismatch,0 FROM metrics
    UNION ALL SELECT 3,'invalid_event_rows',invalid_event_rows,0 FROM metrics
    UNION ALL SELECT 4,'event_duplicate_surplus',event_duplicate_surplus,expected_duplicate_surplus FROM metrics
    UNION ALL SELECT 5,'interval_rows',interval_rows,expected_interval_rows FROM metrics
    UNION ALL SELECT 6,'interval_schema_mismatch',interval_schema_mismatch,0 FROM metrics
    UNION ALL SELECT 7,'invalid_interval_rows',invalid_interval_rows,0 FROM metrics
    UNION ALL SELECT 8,'interval_candidate_key_surplus',interval_candidate_key_surplus,0 FROM metrics
    UNION ALL SELECT 9,'interval_chain_errors',interval_chain_errors,0 FROM metrics
    UNION ALL SELECT 10,'categoryid_interval_rows',categoryid_interval_rows,expected_category_rows FROM metrics
    UNION ALL SELECT 11,'available_interval_rows',available_interval_rows,expected_available_rows FROM metrics
    UNION ALL SELECT 12,'source_contract_violations',CASE WHEN valid_input THEN 0 ELSE 1 END,0 FROM metrics
    UNION ALL SELECT 13,'categoryid_joined_rows',CASE WHEN valid_input THEN joined_rows END,expected_event_rows FROM metrics
    UNION ALL SELECT 14,'available_joined_rows',CASE WHEN valid_input THEN joined_rows END,expected_event_rows FROM metrics
    UNION ALL SELECT 15,'categoryid_future_match_rows',CASE WHEN valid_input THEN categoryid_future_match_rows END,0 FROM metrics
    UNION ALL SELECT 16,'available_future_match_rows',CASE WHEN valid_input THEN available_future_match_rows END,0 FROM metrics
    UNION ALL SELECT 17,'categoryid_boundary_error_rows',CASE WHEN valid_input THEN categoryid_boundary_error_rows END,0 FROM metrics
    UNION ALL SELECT 18,'available_boundary_error_rows',CASE WHEN valid_input THEN available_boundary_error_rows END,0 FROM metrics
    UNION ALL SELECT 19,'categoryid_coverage_partition_difference',CASE WHEN valid_input THEN categoryid_matched_rows+categoryid_before_first_rows+categoryid_no_history_rows-event_rows END,0 FROM metrics
    UNION ALL SELECT 20,'available_coverage_partition_difference',CASE WHEN valid_input THEN available_matched_rows+available_before_first_rows+available_no_history_rows-event_rows END,0 FROM metrics
), controls_status AS (
    SELECT COUNT(*)=20 AND COUNT(*) FILTER (WHERE actual IS DISTINCT FROM expected)=0 AS all_controls_valid FROM controls
), report AS (
    SELECT * FROM controls
    UNION ALL SELECT 21,'categoryid_matched_rows',CASE WHEN c.all_controls_valid THEN m.categoryid_matched_rows END,NULL::BIGINT FROM metrics m CROSS JOIN controls_status c
    UNION ALL SELECT 22,'categoryid_before_first_rows',CASE WHEN c.all_controls_valid THEN m.categoryid_before_first_rows END,NULL::BIGINT FROM metrics m CROSS JOIN controls_status c
    UNION ALL SELECT 23,'categoryid_no_history_rows',CASE WHEN c.all_controls_valid THEN m.categoryid_no_history_rows END,NULL::BIGINT FROM metrics m CROSS JOIN controls_status c
    UNION ALL SELECT 24,'categoryid_open_tail_match_rows',CASE WHEN c.all_controls_valid THEN m.categoryid_open_tail_match_rows END,NULL::BIGINT FROM metrics m CROSS JOIN controls_status c
    UNION ALL SELECT 25,'available_matched_rows',CASE WHEN c.all_controls_valid THEN m.available_matched_rows END,NULL::BIGINT FROM metrics m CROSS JOIN controls_status c
    UNION ALL SELECT 26,'available_before_first_rows',CASE WHEN c.all_controls_valid THEN m.available_before_first_rows END,NULL::BIGINT FROM metrics m CROSS JOIN controls_status c
    UNION ALL SELECT 27,'available_no_history_rows',CASE WHEN c.all_controls_valid THEN m.available_no_history_rows END,NULL::BIGINT FROM metrics m CROSS JOIN controls_status c
    UNION ALL SELECT 28,'available_open_tail_match_rows',CASE WHEN c.all_controls_valid THEN m.available_open_tail_match_rows END,NULL::BIGINT FROM metrics m CROSS JOIN controls_status c
)
SELECT check_order,check_name,actual::BIGINT AS actual,expected::BIGINT AS expected,
    CASE WHEN actual IS NULL THEN 'BLOCKED' WHEN expected IS NULL THEN 'INFO'
         WHEN actual=expected THEN 'PASS' ELSE 'FAIL' END AS status
FROM report ORDER BY check_order;
