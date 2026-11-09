-- Run once in the existing retail_merchandising connection.
-- Observation-based [from,to) convention: the next recorded observation ends this segment.
-- A NULL end means no later observation is recorded, not known unlimited freshness.
-- Preserve every value and source record; no backfill, deduplication or event join.
CREATE SCHEMA IF NOT EXISTS rr_core;

CREATE TABLE rr_core.item_state_intervals AS
WITH expected_counts AS (
    SELECT 2291853::BIGINT AS expected_rows,788214::BIGINT AS expected_category_rows,
        1503639::BIGINT AS expected_available_rows,253402300799999::BIGINT AS max_supported_ms
), source_schema AS (
    SELECT CASE WHEN COUNT(*)=5 AND COUNT(*) FILTER (WHERE
        column_name=CASE ordinal_position WHEN 1 THEN 'timestamp' WHEN 2 THEN 'itemid'
            WHEN 3 THEN 'property' WHEN 4 THEN 'value' WHEN 5 THEN 'source_file' END
        AND data_type=CASE WHEN ordinal_position IN (1,2) THEN 'BIGINT' ELSE 'VARCHAR' END)=5
        THEN 0 ELSE 1 END AS source_schema_mismatch
    FROM information_schema.columns
    WHERE table_catalog=current_database() AND table_schema='rr_stg' AND table_name='item_state_observations'
), source_rows AS MATERIALIZED (
    SELECT TRY_CAST(itemid AS BIGINT) AS itemid,CAST(property AS VARCHAR) AS property,
        CAST(value AS VARCHAR) AS value,TRY_CAST(timestamp AS BIGINT) AS observed_from_ms,
        CAST(source_file AS VARCHAR) AS source_file
    FROM rr_stg.item_state_observations
), source_health AS (
    SELECT COUNT(*) AS source_rows,
        COUNT(*) FILTER (WHERE property='categoryid') AS source_category_rows,
        COUNT(*) FILTER (WHERE property='available') AS source_available_rows,
        COUNT(DISTINCT (itemid,property)) AS source_pairs,
        COUNT(*)-COUNT(DISTINCT (itemid,property,observed_from_ms)) AS source_key_surplus,
        COUNT(*) FILTER (WHERE NOT COALESCE(itemid>=0 AND observed_from_ms BETWEEN 0 AND e.max_supported_ms
            AND ((property='available' AND value IN ('0','1')) OR (property='categoryid'
                AND regexp_full_match(value,'[0-9]+') AND TRY_CAST(value AS BIGINT) IS NOT NULL))
            AND source_file IN ('item_properties_part1.csv','item_properties_part2.csv'),false)) AS source_value_violations
    FROM source_rows CROSS JOIN expected_counts e
), admission AS MATERIALIZED (
    SELECT s.*,h.*,e.*,COALESCE(s.source_schema_mismatch=0 AND h.source_rows=e.expected_rows
        AND h.source_rows>0 AND h.source_category_rows=e.expected_category_rows
        AND h.source_available_rows=e.expected_available_rows AND h.source_key_surplus=0
        AND h.source_value_violations=0,false) AS valid_input
    FROM source_schema s CROSS JOIN source_health h CROSS JOIN expected_counts e
), expected_intervals AS MATERIALIZED (
    SELECT *,LEAD(observed_from_ms) OVER (PARTITION BY itemid,property ORDER BY observed_from_ms) AS observed_to_ms
    FROM source_rows
)
SELECT CASE WHEN a.valid_input THEN r.itemid ELSE error('SQL67 observation interval contract failed; target was not created') END AS itemid,
    CASE WHEN a.valid_input THEN r.property ELSE error('SQL67 observation interval contract failed; target was not created') END AS property,
    CASE WHEN a.valid_input THEN r.value ELSE error('SQL67 observation interval contract failed; target was not created') END AS value,
    CASE WHEN a.valid_input THEN r.observed_from_ms ELSE error('SQL67 observation interval contract failed; target was not created') END AS observed_from_ms,
    CASE WHEN a.valid_input THEN r.observed_to_ms ELSE error('SQL67 observation interval contract failed; target was not created') END AS observed_to_ms,
    CASE WHEN a.valid_input THEN r.source_file ELSE error('SQL67 observation interval contract failed; target was not created') END AS source_file
FROM admission a LEFT JOIN expected_intervals r ON true;

-- CHECKS: if rr_core.item_state_intervals already exists, run only the query below.
WITH expected_counts AS (
    SELECT 2291853::BIGINT AS expected_rows,788214::BIGINT AS expected_category_rows,
        1503639::BIGINT AS expected_available_rows,253402300799999::BIGINT AS max_supported_ms
), source_schema AS (
    SELECT CASE WHEN COUNT(*)=5 AND COUNT(*) FILTER (WHERE
        column_name=CASE ordinal_position WHEN 1 THEN 'timestamp' WHEN 2 THEN 'itemid'
            WHEN 3 THEN 'property' WHEN 4 THEN 'value' WHEN 5 THEN 'source_file' END
        AND data_type=CASE WHEN ordinal_position IN (1,2) THEN 'BIGINT' ELSE 'VARCHAR' END)=5
        THEN 0 ELSE 1 END AS source_schema_mismatch
    FROM information_schema.columns
    WHERE table_catalog=current_database() AND table_schema='rr_stg' AND table_name='item_state_observations'
), source_rows AS MATERIALIZED (
    SELECT TRY_CAST(itemid AS BIGINT) AS itemid,CAST(property AS VARCHAR) AS property,
        CAST(value AS VARCHAR) AS value,TRY_CAST(timestamp AS BIGINT) AS observed_from_ms,
        CAST(source_file AS VARCHAR) AS source_file
    FROM rr_stg.item_state_observations
), source_health AS (
    SELECT COUNT(*) AS source_rows,
        COUNT(*) FILTER (WHERE property='categoryid') AS source_category_rows,
        COUNT(*) FILTER (WHERE property='available') AS source_available_rows,
        COUNT(DISTINCT (itemid,property)) AS source_pairs,
        COUNT(*)-COUNT(DISTINCT (itemid,property,observed_from_ms)) AS source_key_surplus,
        COUNT(*) FILTER (WHERE NOT COALESCE(itemid>=0 AND observed_from_ms BETWEEN 0 AND e.max_supported_ms
            AND ((property='available' AND value IN ('0','1')) OR (property='categoryid'
                AND regexp_full_match(value,'[0-9]+') AND TRY_CAST(value AS BIGINT) IS NOT NULL))
            AND source_file IN ('item_properties_part1.csv','item_properties_part2.csv'),false)) AS source_value_violations
    FROM source_rows CROSS JOIN expected_counts e
), admission AS MATERIALIZED (
    SELECT s.*,h.*,e.*,COALESCE(s.source_schema_mismatch=0 AND h.source_rows=e.expected_rows
        AND h.source_rows>0 AND h.source_category_rows=e.expected_category_rows
        AND h.source_available_rows=e.expected_available_rows AND h.source_key_surplus=0
        AND h.source_value_violations=0,false) AS valid_input
    FROM source_schema s CROSS JOIN source_health h CROSS JOIN expected_counts e
), expected_intervals AS MATERIALIZED (
    SELECT *,LEAD(observed_from_ms) OVER (PARTITION BY itemid,property ORDER BY observed_from_ms) AS observed_to_ms
    FROM source_rows
), expected_schema(column_name,data_type,ordinal_position) AS (
    VALUES ('itemid','BIGINT',1),('property','VARCHAR',2),('value','VARCHAR',3),
        ('observed_from_ms','BIGINT',4),('observed_to_ms','BIGINT',5),('source_file','VARCHAR',6)
), interval_columns AS (
    SELECT column_name,data_type,ordinal_position FROM information_schema.columns
    WHERE table_catalog=current_database() AND table_schema='rr_core' AND table_name='item_state_intervals'
), interval_schema AS (
    SELECT COUNT(*) FILTER (WHERE e.column_name IS DISTINCT FROM i.column_name
        OR e.data_type IS DISTINCT FROM i.data_type) AS interval_schema_mismatch
    FROM expected_schema e FULL OUTER JOIN interval_columns i USING (ordinal_position)
), interval_rows AS MATERIALIZED (
    SELECT TRY_CAST(itemid AS BIGINT) AS itemid,CAST(property AS VARCHAR) AS property,
        CAST(value AS VARCHAR) AS value,TRY_CAST(observed_from_ms AS BIGINT) AS observed_from_ms,
        TRY_CAST(observed_to_ms AS BIGINT) AS observed_to_ms,CAST(source_file AS VARCHAR) AS source_file,
        i.observed_to_ms IS NOT NULL AS original_end_present
    FROM rr_core.item_state_intervals i
), interval_links AS MATERIALIZED (
    SELECT *,LEAD(value) OVER (PARTITION BY itemid,property ORDER BY observed_from_ms) AS next_value,
        LEAD(observed_from_ms) OVER (PARTITION BY itemid,property ORDER BY observed_from_ms) AS next_start,
        MAX(observed_from_ms) OVER (PARTITION BY itemid,property) AS last_start
    FROM interval_rows
), interval_health AS (
    SELECT COUNT(*) AS interval_rows,
        COUNT(*) FILTER (WHERE property='categoryid') AS categoryid_rows,
        COUNT(*) FILTER (WHERE property='available') AS available_rows,
        COUNT(*) FILTER (WHERE itemid IS NULL OR property IS NULL OR property='' OR value IS NULL OR value=''
            OR observed_from_ms IS NULL OR source_file IS NULL OR source_file='') AS missing_required_rows,
        COUNT(*) FILTER (WHERE observed_from_ms IS NULL OR observed_from_ms<0
            OR observed_from_ms>e.max_supported_ms) AS invalid_start_rows,
        COUNT(*) FILTER (WHERE original_end_present AND NOT COALESCE(observed_to_ms BETWEEN 0 AND e.max_supported_ms
            AND observed_to_ms>observed_from_ms,false)) AS invalid_end_rows,
        COUNT(*) FILTER (WHERE NOT COALESCE((property='available' AND value IN ('0','1'))
            OR (property='categoryid' AND regexp_full_match(value,'[0-9]+')
                AND TRY_CAST(value AS BIGINT) IS NOT NULL),false)) AS invalid_value_rows,
        COUNT(*) FILTER (WHERE source_file IS NULL OR source_file NOT IN
            ('item_properties_part1.csv','item_properties_part2.csv')) AS unknown_source_file_rows,
        COUNT(*)-COUNT(DISTINCT (itemid,property,observed_from_ms)) AS candidate_key_surplus,
        COUNT(DISTINCT (itemid,property)) AS item_property_pairs,
        COUNT(*) FILTER (WHERE observed_to_ms IS NOT NULL) AS finite_intervals,
        COUNT(*) FILTER (WHERE observed_to_ms IS NULL) AS open_intervals,
        COUNT(*) FILTER (WHERE observed_to_ms IS NULL AND observed_from_ms IS DISTINCT FROM last_start) AS open_end_position_errors,
        COUNT(*) FILTER (WHERE next_start IS NOT NULL AND value=next_value) AS unchanged_next_value_links
    FROM interval_links CROSS JOIN expected_counts e
), group_health AS (
    SELECT COUNT(*) FILTER (WHERE open_ends<>1) AS open_end_group_errors
    FROM (SELECT itemid,property,COUNT(*) FILTER (WHERE observed_to_ms IS NULL) AS open_ends
        FROM interval_rows GROUP BY itemid,property)
), source_only AS (
    SELECT itemid,property,value,observed_from_ms,source_file FROM source_rows
    EXCEPT ALL SELECT itemid,property,value,observed_from_ms,source_file FROM interval_rows
), interval_only AS (
    SELECT itemid,property,value,observed_from_ms,source_file FROM interval_rows
    EXCEPT ALL SELECT itemid,property,value,observed_from_ms,source_file FROM source_rows
), comparison_counts AS (
    SELECT (SELECT COUNT(*) FROM source_only) AS source_only_rows,
        (SELECT COUNT(*) FROM interval_only) AS interval_only_rows,
        (SELECT COUNT(*) FROM expected_intervals e LEFT JOIN interval_rows i
            ON e.itemid=i.itemid AND e.property=i.property AND e.observed_from_ms=i.observed_from_ms
            WHERE e.observed_to_ms IS DISTINCT FROM i.observed_to_ms) AS endpoint_mismatch_rows
), metrics AS MATERIALIZED (
    SELECT a.*,s.*,h.*,g.*,c.* FROM admission a CROSS JOIN interval_schema s CROSS JOIN interval_health h
        CROSS JOIN group_health g CROSS JOIN comparison_counts c
), controls AS (
    SELECT 1 AS check_order,'source_rows' AS check_name,source_rows AS actual,expected_rows AS expected FROM metrics
    UNION ALL SELECT 2,'source_schema_mismatch',source_schema_mismatch,0 FROM metrics
    UNION ALL SELECT 3,'source_contract_violations',CASE WHEN valid_input THEN 0 ELSE 1 END,0 FROM metrics
    UNION ALL SELECT 4,'interval_rows',interval_rows,expected_rows FROM metrics
    UNION ALL SELECT 5,'interval_schema_mismatch',interval_schema_mismatch,0 FROM metrics
    UNION ALL SELECT 6,'categoryid_rows',categoryid_rows,expected_category_rows FROM metrics
    UNION ALL SELECT 7,'available_rows',available_rows,expected_available_rows FROM metrics
    UNION ALL SELECT 8,'missing_required_rows',missing_required_rows,0 FROM metrics
    UNION ALL SELECT 9,'invalid_start_rows',invalid_start_rows,0 FROM metrics
    UNION ALL SELECT 10,'invalid_end_rows',invalid_end_rows,0 FROM metrics
    UNION ALL SELECT 11,'invalid_value_rows',invalid_value_rows,0 FROM metrics
    UNION ALL SELECT 12,'unknown_source_file_rows',unknown_source_file_rows,0 FROM metrics
    UNION ALL SELECT 13,'candidate_key_surplus',candidate_key_surplus,0 FROM metrics
    UNION ALL SELECT 14,'source_only_rows',source_only_rows,0 FROM metrics
    UNION ALL SELECT 15,'interval_only_rows',interval_only_rows,0 FROM metrics
    UNION ALL SELECT 16,'endpoint_mismatch_rows',endpoint_mismatch_rows,0 FROM metrics
    UNION ALL SELECT 17,'open_end_group_errors',open_end_group_errors,0 FROM metrics
    UNION ALL SELECT 18,'open_end_position_errors',open_end_position_errors,0 FROM metrics
    UNION ALL SELECT 19,'finite_link_count_difference',finite_intervals-(interval_rows-item_property_pairs),0 FROM metrics
    UNION ALL SELECT 20,'interval_pair_count_difference',item_property_pairs-source_pairs,0 FROM metrics
), controls_status AS (
    SELECT COUNT(*)=20 AND COUNT(*) FILTER (WHERE actual IS DISTINCT FROM expected)=0 AS all_controls_valid FROM controls
), report AS (
    SELECT * FROM controls
    UNION ALL SELECT 21,'item_property_pairs',CASE WHEN c.all_controls_valid THEN m.item_property_pairs END,NULL::BIGINT
        FROM metrics m CROSS JOIN controls_status c
    UNION ALL SELECT 22,'finite_intervals',CASE WHEN c.all_controls_valid THEN m.finite_intervals END,NULL::BIGINT
        FROM metrics m CROSS JOIN controls_status c
    UNION ALL SELECT 23,'open_intervals',CASE WHEN c.all_controls_valid THEN m.open_intervals END,NULL::BIGINT
        FROM metrics m CROSS JOIN controls_status c
    UNION ALL SELECT 24,'unchanged_next_value_links',CASE WHEN c.all_controls_valid THEN m.unchanged_next_value_links END,NULL::BIGINT
        FROM metrics m CROSS JOIN controls_status c
)
SELECT check_order,check_name,actual::BIGINT AS actual,expected::BIGINT AS expected,
    CASE WHEN actual IS NULL THEN 'BLOCKED' WHEN expected IS NULL THEN 'INFO'
         WHEN actual=expected THEN 'PASS' ELSE 'FAIL' END AS status
FROM report ORDER BY check_order;
