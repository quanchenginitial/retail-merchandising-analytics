-- Build once: every original event occurrence plus independently matched property history and UTC fields.
-- Last recorded observations do not establish freshness, inventory or category-reference validity.
CREATE SCHEMA IF NOT EXISTS rr_mart;
CREATE TABLE rr_mart.events_enriched AS
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
-- Guarded last-observation lookup inherited from accepted SQL68.
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
), source_controls AS (
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
), source_controls_status AS (
    SELECT COUNT(*)=20 AND COUNT(*) FILTER (WHERE actual IS DISTINCT FROM expected)=0 AS all_controls_valid FROM source_controls
)
SELECT
    CASE WHEN g.all_controls_valid THEN c.timestamp ELSE error('SQL69 source contract failed; no fact table created') END::BIGINT AS timestamp,
    CASE WHEN g.all_controls_valid THEN c.visitorid ELSE error('SQL69 source contract failed; no fact table created') END::BIGINT AS visitorid,
    CASE WHEN g.all_controls_valid THEN c.event ELSE error('SQL69 source contract failed; no fact table created') END::VARCHAR AS event,
    CASE WHEN g.all_controls_valid THEN c.itemid ELSE error('SQL69 source contract failed; no fact table created') END::BIGINT AS itemid,
    CASE WHEN g.all_controls_valid THEN c.transactionid ELSE error('SQL69 source contract failed; no fact table created') END::BIGINT AS transactionid,
    CASE WHEN g.all_controls_valid THEN c.categoryid_value ELSE error('SQL69 source contract failed; no fact table created') END::VARCHAR AS categoryid_value,
    CASE WHEN g.all_controls_valid THEN c.categoryid_from_ms ELSE error('SQL69 source contract failed; no fact table created') END::BIGINT AS categoryid_from_ms,
    CASE WHEN g.all_controls_valid THEN c.categoryid_to_ms ELSE error('SQL69 source contract failed; no fact table created') END::BIGINT AS categoryid_to_ms,
    CASE WHEN g.all_controls_valid THEN c.categoryid_source_file ELSE error('SQL69 source contract failed; no fact table created') END::VARCHAR AS categoryid_source_file,
    CASE WHEN g.all_controls_valid THEN c.categoryid_coverage ELSE error('SQL69 source contract failed; no fact table created') END::VARCHAR AS categoryid_coverage,
    CASE WHEN g.all_controls_valid THEN c.available_value ELSE error('SQL69 source contract failed; no fact table created') END::VARCHAR AS available_value,
    CASE WHEN g.all_controls_valid THEN c.available_from_ms ELSE error('SQL69 source contract failed; no fact table created') END::BIGINT AS available_from_ms,
    CASE WHEN g.all_controls_valid THEN c.available_to_ms ELSE error('SQL69 source contract failed; no fact table created') END::BIGINT AS available_to_ms,
    CASE WHEN g.all_controls_valid THEN c.available_source_file ELSE error('SQL69 source contract failed; no fact table created') END::VARCHAR AS available_source_file,
    CASE WHEN g.all_controls_valid THEN c.available_coverage ELSE error('SQL69 source contract failed; no fact table created') END::VARCHAR AS available_coverage,
    CASE WHEN g.all_controls_valid THEN make_timestamp_ms(c.timestamp) ELSE error('SQL69 source contract failed; no fact table created') END::TIMESTAMP AS event_timestamp_utc,
    CASE WHEN g.all_controls_valid THEN CAST(make_timestamp_ms(c.timestamp) AS DATE) ELSE error('SQL69 source contract failed; no fact table created') END::DATE AS event_date_utc
FROM source_controls_status g LEFT JOIN classified c ON g.all_controls_valid;

-- CHECKS: if rr_mart.events_enriched already exists, run only the query below.
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
-- Guarded last-observation lookup inherited from accepted SQL68.
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
), source_controls AS (
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
), source_controls_status AS (
    SELECT COUNT(*)=20 AND COUNT(*) FILTER (WHERE actual IS DISTINCT FROM expected)=0 AS all_controls_valid FROM source_controls
), expected_fact AS MATERIALIZED (
    SELECT c.timestamp AS timestamp,
        c.visitorid AS visitorid,
        c.event AS event,
        c.itemid AS itemid,
        c.transactionid AS transactionid,
        c.categoryid_value AS categoryid_value,
        c.categoryid_from_ms AS categoryid_from_ms,
        c.categoryid_to_ms AS categoryid_to_ms,
        c.categoryid_source_file AS categoryid_source_file,
        c.categoryid_coverage AS categoryid_coverage,
        c.available_value AS available_value,
        c.available_from_ms AS available_from_ms,
        c.available_to_ms AS available_to_ms,
        c.available_source_file AS available_source_file,
        c.available_coverage AS available_coverage,
        make_timestamp_ms(c.timestamp) AS event_timestamp_utc,
        CAST(make_timestamp_ms(c.timestamp) AS DATE) AS event_date_utc
    FROM classified c
), fact_schema AS (
    SELECT CASE WHEN COUNT(*)=17 AND COUNT(*) FILTER (WHERE
        column_name=CASE ordinal_position WHEN 1 THEN 'timestamp' WHEN 2 THEN 'visitorid' WHEN 3 THEN 'event' WHEN 4 THEN 'itemid' WHEN 5 THEN 'transactionid' WHEN 6 THEN 'categoryid_value' WHEN 7 THEN 'categoryid_from_ms' WHEN 8 THEN 'categoryid_to_ms' WHEN 9 THEN 'categoryid_source_file' WHEN 10 THEN 'categoryid_coverage' WHEN 11 THEN 'available_value' WHEN 12 THEN 'available_from_ms' WHEN 13 THEN 'available_to_ms' WHEN 14 THEN 'available_source_file' WHEN 15 THEN 'available_coverage' WHEN 16 THEN 'event_timestamp_utc' WHEN 17 THEN 'event_date_utc' END
        AND data_type=CASE ordinal_position WHEN 1 THEN 'BIGINT' WHEN 2 THEN 'BIGINT' WHEN 3 THEN 'VARCHAR' WHEN 4 THEN 'BIGINT' WHEN 5 THEN 'BIGINT' WHEN 6 THEN 'VARCHAR' WHEN 7 THEN 'BIGINT' WHEN 8 THEN 'BIGINT' WHEN 9 THEN 'VARCHAR' WHEN 10 THEN 'VARCHAR' WHEN 11 THEN 'VARCHAR' WHEN 12 THEN 'BIGINT' WHEN 13 THEN 'BIGINT' WHEN 14 THEN 'VARCHAR' WHEN 15 THEN 'VARCHAR' WHEN 16 THEN 'TIMESTAMP' WHEN 17 THEN 'DATE' END)=17 THEN 0 ELSE 1 END AS fact_schema_mismatch
    FROM information_schema.columns WHERE table_catalog=current_database() AND table_schema='rr_mart' AND table_name='events_enriched'
), fact_rows AS MATERIALIZED (
    SELECT TRY_CAST(f.timestamp AS BIGINT) AS timestamp,
        TRY_CAST(f.visitorid AS BIGINT) AS visitorid,
        CAST(f.event AS VARCHAR) AS event,
        TRY_CAST(f.itemid AS BIGINT) AS itemid,
        TRY_CAST(f.transactionid AS BIGINT) AS transactionid,
        CAST(f.categoryid_value AS VARCHAR) AS categoryid_value,
        TRY_CAST(f.categoryid_from_ms AS BIGINT) AS categoryid_from_ms,
        TRY_CAST(f.categoryid_to_ms AS BIGINT) AS categoryid_to_ms,
        CAST(f.categoryid_source_file AS VARCHAR) AS categoryid_source_file,
        CAST(f.categoryid_coverage AS VARCHAR) AS categoryid_coverage,
        CAST(f.available_value AS VARCHAR) AS available_value,
        TRY_CAST(f.available_from_ms AS BIGINT) AS available_from_ms,
        TRY_CAST(f.available_to_ms AS BIGINT) AS available_to_ms,
        CAST(f.available_source_file AS VARCHAR) AS available_source_file,
        CAST(f.available_coverage AS VARCHAR) AS available_coverage,
        TRY_CAST(f.event_timestamp_utc AS TIMESTAMP) AS event_timestamp_utc,
        TRY_CAST(f.event_date_utc AS DATE) AS event_date_utc,
        f.transactionid IS NOT NULL AS original_transaction_present,
        f.categoryid_to_ms IS NOT NULL AS original_category_end_present,
        f.available_to_ms IS NOT NULL AS original_available_end_present
    FROM rr_mart.events_enriched f
), fact_health AS (
    SELECT COUNT(*) AS fact_rows,
        COUNT(*) FILTER (WHERE NOT COALESCE(timestamp BETWEEN 0 AND p.max_supported_ms AND visitorid>=0 AND itemid>=0 AND event IN ('view','addtocart','transaction')
            AND ((event='transaction' AND original_transaction_present AND transactionid>=0) OR (event<>'transaction' AND NOT original_transaction_present))
            AND event_timestamp_utc IS NOT NULL AND event_date_utc IS NOT NULL
            AND ((categoryid_coverage='MATCHED' AND (regexp_full_match(categoryid_value,'[0-9]+') AND TRY_CAST(categoryid_value AS BIGINT) IS NOT NULL) AND categoryid_from_ms BETWEEN 0 AND p.max_supported_ms AND categoryid_from_ms<=timestamp AND (NOT original_category_end_present OR (categoryid_to_ms BETWEEN 0 AND p.max_supported_ms AND categoryid_to_ms>categoryid_from_ms AND timestamp<categoryid_to_ms)) AND categoryid_source_file IN ('item_properties_part1.csv','item_properties_part2.csv')) OR (categoryid_coverage IN ('BEFORE_FIRST','NO_HISTORY') AND categoryid_value IS NULL AND categoryid_from_ms IS NULL AND categoryid_to_ms IS NULL AND NOT original_category_end_present AND categoryid_source_file IS NULL))
            AND ((available_coverage='MATCHED' AND (available_value IN ('0','1')) AND available_from_ms BETWEEN 0 AND p.max_supported_ms AND available_from_ms<=timestamp AND (NOT original_available_end_present OR (available_to_ms BETWEEN 0 AND p.max_supported_ms AND available_to_ms>available_from_ms AND timestamp<available_to_ms)) AND available_source_file IN ('item_properties_part1.csv','item_properties_part2.csv')) OR (available_coverage IN ('BEFORE_FIRST','NO_HISTORY') AND available_value IS NULL AND available_from_ms IS NULL AND available_to_ms IS NULL AND NOT original_available_end_present AND available_source_file IS NULL)),false)) AS invalid_fact_rows,
        COUNT(*)-COUNT(DISTINCT (timestamp,visitorid,event,itemid,transactionid)) AS fact_duplicate_surplus,
        COUNT(*) FILTER (WHERE epoch_ms(event_timestamp_utc) IS DISTINCT FROM timestamp) AS timestamp_roundtrip_errors,
        COUNT(*) FILTER (WHERE event_date_utc IS DISTINCT FROM CAST(event_timestamp_utc AS DATE)) AS utc_date_errors,
        COUNT(*) FILTER (WHERE categoryid_coverage='MATCHED') AS categoryid_matched_rows,
        COUNT(*) FILTER (WHERE categoryid_coverage='BEFORE_FIRST') AS categoryid_before_first_rows,
        COUNT(*) FILTER (WHERE categoryid_coverage='NO_HISTORY') AS categoryid_no_history_rows,
        COUNT(*) FILTER (WHERE available_coverage='MATCHED') AS available_matched_rows,
        COUNT(*) FILTER (WHERE available_coverage='BEFORE_FIRST') AS available_before_first_rows,
        COUNT(*) FILTER (WHERE available_coverage='NO_HISTORY') AS available_no_history_rows,
        COUNT(*) FILTER (WHERE categoryid_coverage='MATCHED' AND categoryid_to_ms IS NULL) AS categoryid_open_tail_match_rows,
        COUNT(*) FILTER (WHERE available_coverage='MATCHED' AND available_to_ms IS NULL) AS available_open_tail_match_rows
    FROM fact_rows CROSS JOIN expected_counts p
), differences AS (
    SELECT (SELECT COUNT(*) FROM (SELECT timestamp,visitorid,event,itemid,transactionid,categoryid_value,categoryid_from_ms,categoryid_to_ms,categoryid_source_file,categoryid_coverage,available_value,available_from_ms,available_to_ms,available_source_file,available_coverage,event_timestamp_utc,event_date_utc FROM expected_fact EXCEPT ALL SELECT timestamp,visitorid,event,itemid,transactionid,categoryid_value,categoryid_from_ms,categoryid_to_ms,categoryid_source_file,categoryid_coverage,available_value,available_from_ms,available_to_ms,available_source_file,available_coverage,event_timestamp_utc,event_date_utc FROM fact_rows)) AS expected_only_rows,
        (SELECT COUNT(*) FROM (SELECT timestamp,visitorid,event,itemid,transactionid,categoryid_value,categoryid_from_ms,categoryid_to_ms,categoryid_source_file,categoryid_coverage,available_value,available_from_ms,available_to_ms,available_source_file,available_coverage,event_timestamp_utc,event_date_utc FROM fact_rows EXCEPT ALL SELECT timestamp,visitorid,event,itemid,transactionid,categoryid_value,categoryid_from_ms,categoryid_to_ms,categoryid_source_file,categoryid_coverage,available_value,available_from_ms,available_to_ms,available_source_file,available_coverage,event_timestamp_utc,event_date_utc FROM expected_fact)) AS fact_only_rows
), fact_metrics AS MATERIALIZED (
    SELECT h.*,s.*,d.*,p.expected_event_rows,p.expected_duplicate_surplus,g.all_controls_valid AS valid_source
    FROM fact_health h CROSS JOIN fact_schema s CROSS JOIN differences d CROSS JOIN expected_counts p CROSS JOIN source_controls_status g
), controls AS (
    SELECT check_order,check_name,actual,expected FROM source_controls WHERE check_order<12
    UNION ALL SELECT 12,'source_contract_violations',CASE WHEN all_controls_valid THEN 0 ELSE 1 END,0 FROM source_controls_status
    UNION ALL SELECT 13,'fact_rows',CASE WHEN valid_source THEN fact_rows END,expected_event_rows FROM fact_metrics
    UNION ALL SELECT 14,'fact_schema_mismatch',CASE WHEN valid_source THEN fact_schema_mismatch END,0 FROM fact_metrics
    UNION ALL SELECT 15,'invalid_fact_rows',CASE WHEN valid_source THEN invalid_fact_rows END,0 FROM fact_metrics
    UNION ALL SELECT 16,'fact_duplicate_surplus',CASE WHEN valid_source THEN fact_duplicate_surplus END,expected_duplicate_surplus FROM fact_metrics
    UNION ALL SELECT 17,'expected_only_rows',CASE WHEN valid_source THEN expected_only_rows END,0 FROM fact_metrics
    UNION ALL SELECT 18,'fact_only_rows',CASE WHEN valid_source THEN fact_only_rows END,0 FROM fact_metrics
    UNION ALL SELECT 19,'timestamp_roundtrip_errors',CASE WHEN valid_source THEN timestamp_roundtrip_errors END,0 FROM fact_metrics
    UNION ALL SELECT 20,'utc_date_errors',CASE WHEN valid_source THEN utc_date_errors END,0 FROM fact_metrics
), controls_status AS (
    SELECT COUNT(*)=20 AND COUNT(*) FILTER (WHERE actual IS DISTINCT FROM expected)=0 AS all_controls_valid FROM controls
), report AS (
    SELECT * FROM controls
    UNION ALL SELECT 21,'categoryid_matched_rows',CASE WHEN c.all_controls_valid THEN f.categoryid_matched_rows END,NULL::BIGINT FROM fact_metrics f CROSS JOIN controls_status c
    UNION ALL SELECT 22,'categoryid_before_first_rows',CASE WHEN c.all_controls_valid THEN f.categoryid_before_first_rows END,NULL::BIGINT FROM fact_metrics f CROSS JOIN controls_status c
    UNION ALL SELECT 23,'categoryid_no_history_rows',CASE WHEN c.all_controls_valid THEN f.categoryid_no_history_rows END,NULL::BIGINT FROM fact_metrics f CROSS JOIN controls_status c
    UNION ALL SELECT 24,'categoryid_open_tail_match_rows',CASE WHEN c.all_controls_valid THEN f.categoryid_open_tail_match_rows END,NULL::BIGINT FROM fact_metrics f CROSS JOIN controls_status c
    UNION ALL SELECT 25,'available_matched_rows',CASE WHEN c.all_controls_valid THEN f.available_matched_rows END,NULL::BIGINT FROM fact_metrics f CROSS JOIN controls_status c
    UNION ALL SELECT 26,'available_before_first_rows',CASE WHEN c.all_controls_valid THEN f.available_before_first_rows END,NULL::BIGINT FROM fact_metrics f CROSS JOIN controls_status c
    UNION ALL SELECT 27,'available_no_history_rows',CASE WHEN c.all_controls_valid THEN f.available_no_history_rows END,NULL::BIGINT FROM fact_metrics f CROSS JOIN controls_status c
    UNION ALL SELECT 28,'available_open_tail_match_rows',CASE WHEN c.all_controls_valid THEN f.available_open_tail_match_rows END,NULL::BIGINT FROM fact_metrics f CROSS JOIN controls_status c
)
SELECT check_order,check_name,actual::BIGINT AS actual,expected::BIGINT AS expected,
    CASE WHEN actual IS NULL THEN 'BLOCKED' WHEN expected IS NULL THEN 'INFO' WHEN actual=expected THEN 'PASS' ELSE 'FAIL' END AS status
FROM report ORDER BY check_order;
