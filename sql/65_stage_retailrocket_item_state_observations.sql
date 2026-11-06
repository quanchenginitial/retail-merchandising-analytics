-- Run once in the existing retail_merchandising connection.
-- Stage only exact categoryid/available observations; all other properties remain raw.
-- Preserve value and source_file text exactly, including unknown category references.
-- No validity intervals, latest-state selection, event joins, deduplication or key repair.
CREATE SCHEMA IF NOT EXISTS rr_stg;

CREATE TABLE rr_stg.item_state_observations AS
WITH expected_counts AS (
    SELECT 20275902::BIGINT AS expected_raw_rows,10999999::BIGINT AS expected_part1,
        9275903::BIGINT AS expected_part2,2291853::BIGINT AS expected_selected_rows,
        788214::BIGINT AS expected_category_rows,1503639::BIGINT AS expected_available_rows,
        17984049::BIGINT AS expected_other_rows
), raw_schema AS (
    SELECT CASE WHEN COUNT(*)=5 AND COUNT(*) FILTER (WHERE data_type='VARCHAR')=5
        AND COUNT(*) FILTER (WHERE column_name IS DISTINCT FROM
            CASE ordinal_position WHEN 1 THEN 'timestamp' WHEN 2 THEN 'itemid'
                WHEN 3 THEN 'property' WHEN 4 THEN 'value' WHEN 5 THEN 'source_file' END)=0
        THEN 0 ELSE 1 END AS raw_schema_mismatch
    FROM information_schema.columns
    WHERE table_catalog=current_database() AND table_schema='rr_raw' AND table_name='item_properties'
), raw_health AS (
    SELECT COUNT(*) AS raw_rows,
        COUNT(*) FILTER (WHERE CAST(source_file AS VARCHAR)='item_properties_part1.csv') AS raw_part1_rows,
        COUNT(*) FILTER (WHERE CAST(source_file AS VARCHAR)='item_properties_part2.csv') AS raw_part2_rows,
        COUNT(*) FILTER (WHERE source_file IS NULL OR CAST(source_file AS VARCHAR) NOT IN
            ('item_properties_part1.csv','item_properties_part2.csv')) AS raw_unknown_source_rows,
        COUNT(*)-COUNT(*) FILTER (WHERE CAST(property AS VARCHAR) IN ('categoryid','available')) AS other_property_rows
    FROM rr_raw.item_properties
), selected_rows AS MATERIALIZED (
    SELECT CAST(timestamp AS VARCHAR) AS timestamp,CAST(itemid AS VARCHAR) AS itemid,
        CAST(property AS VARCHAR) AS property,CAST(value AS VARCHAR) AS value,
        CAST(source_file AS VARCHAR) AS source_file
    FROM rr_raw.item_properties WHERE CAST(property AS VARCHAR) IN ('categoryid','available')
), selected_health AS (
    SELECT COUNT(*) AS selected_rows,
        COUNT(*) FILTER (WHERE property='categoryid') AS raw_category_rows,
        COUNT(*) FILTER (WHERE property='available') AS raw_available_rows,
        COUNT(*)-COUNT(DISTINCT (itemid,property,timestamp)) AS raw_candidate_key_surplus,
        COUNT(*) FILTER (WHERE NOT COALESCE(
            regexp_full_match(timestamp,'[0-9]+') AND TRY_CAST(timestamp AS BIGINT) IS NOT NULL
            AND CAST(TRY_CAST(timestamp AS BIGINT) AS VARCHAR)=timestamp
            AND regexp_full_match(itemid,'[0-9]+') AND TRY_CAST(itemid AS BIGINT) IS NOT NULL
            AND CAST(TRY_CAST(itemid AS BIGINT) AS VARCHAR)=itemid
            AND ((property='available' AND value IN ('0','1'))
                OR (property='categoryid' AND regexp_full_match(value,'[0-9]+')
                    AND TRY_CAST(value AS BIGINT) IS NOT NULL)),false)) AS raw_key_value_violations
    FROM selected_rows
), input_guard AS (
    SELECT s.*,r.*,n.*,e.*,COALESCE(s.raw_schema_mismatch=0
        AND r.raw_rows=e.expected_raw_rows AND r.raw_rows>0
        AND r.raw_part1_rows=e.expected_part1 AND r.raw_part2_rows=e.expected_part2
        AND r.raw_unknown_source_rows=0 AND r.other_property_rows=e.expected_other_rows
        AND n.selected_rows=e.expected_selected_rows AND n.selected_rows>0
        AND n.raw_category_rows=e.expected_category_rows AND n.raw_available_rows=e.expected_available_rows
        AND n.raw_candidate_key_surplus=0 AND n.raw_key_value_violations=0,false) AS valid_input
    FROM raw_schema s CROSS JOIN raw_health r CROSS JOIN selected_health n CROSS JOIN expected_counts e
)
SELECT CASE WHEN g.valid_input THEN CAST(r.timestamp AS BIGINT)
            ELSE error('SQL65 named property contract failed; destination was not created') END AS timestamp,
       CASE WHEN g.valid_input THEN CAST(r.itemid AS BIGINT)
            ELSE error('SQL65 named property contract failed; destination was not created') END AS itemid,
       CASE WHEN g.valid_input THEN CAST(r.property AS VARCHAR)
            ELSE error('SQL65 named property contract failed; destination was not created') END AS property,
       CASE WHEN g.valid_input THEN CAST(r.value AS VARCHAR)
            ELSE error('SQL65 named property contract failed; destination was not created') END AS value,
       CASE WHEN g.valid_input THEN CAST(r.source_file AS VARCHAR)
            ELSE error('SQL65 named property contract failed; destination was not created') END AS source_file
FROM input_guard g LEFT JOIN selected_rows r ON true;

-- CHECKS: if rr_stg.item_state_observations already exists, run only the query below.
WITH expected_counts AS (
    SELECT 20275902::BIGINT AS expected_raw_rows,10999999::BIGINT AS expected_part1,
        9275903::BIGINT AS expected_part2,2291853::BIGINT AS expected_selected_rows,
        788214::BIGINT AS expected_category_rows,1503639::BIGINT AS expected_available_rows,
        17984049::BIGINT AS expected_other_rows
), raw_schema AS (
    SELECT CASE WHEN COUNT(*)=5 AND COUNT(*) FILTER (WHERE data_type='VARCHAR')=5
        AND COUNT(*) FILTER (WHERE column_name IS DISTINCT FROM
            CASE ordinal_position WHEN 1 THEN 'timestamp' WHEN 2 THEN 'itemid'
                WHEN 3 THEN 'property' WHEN 4 THEN 'value' WHEN 5 THEN 'source_file' END)=0
        THEN 0 ELSE 1 END AS raw_schema_mismatch
    FROM information_schema.columns
    WHERE table_catalog=current_database() AND table_schema='rr_raw' AND table_name='item_properties'
), raw_health AS (
    SELECT COUNT(*) AS raw_rows,
        COUNT(*) FILTER (WHERE CAST(source_file AS VARCHAR)='item_properties_part1.csv') AS raw_part1_rows,
        COUNT(*) FILTER (WHERE CAST(source_file AS VARCHAR)='item_properties_part2.csv') AS raw_part2_rows,
        COUNT(*) FILTER (WHERE source_file IS NULL OR CAST(source_file AS VARCHAR) NOT IN
            ('item_properties_part1.csv','item_properties_part2.csv')) AS raw_unknown_source_rows,
        COUNT(*)-COUNT(*) FILTER (WHERE CAST(property AS VARCHAR) IN ('categoryid','available')) AS other_property_rows
    FROM rr_raw.item_properties
), selected_rows AS MATERIALIZED (
    SELECT CAST(timestamp AS VARCHAR) AS timestamp,CAST(itemid AS VARCHAR) AS itemid,
        CAST(property AS VARCHAR) AS property,CAST(value AS VARCHAR) AS value,
        CAST(source_file AS VARCHAR) AS source_file
    FROM rr_raw.item_properties WHERE CAST(property AS VARCHAR) IN ('categoryid','available')
), selected_health AS (
    SELECT COUNT(*) AS selected_rows,
        COUNT(*) FILTER (WHERE property='categoryid') AS raw_category_rows,
        COUNT(*) FILTER (WHERE property='available') AS raw_available_rows,
        COUNT(*)-COUNT(DISTINCT (itemid,property,timestamp)) AS raw_candidate_key_surplus,
        COUNT(*) FILTER (WHERE NOT COALESCE(
            regexp_full_match(timestamp,'[0-9]+') AND TRY_CAST(timestamp AS BIGINT) IS NOT NULL
            AND CAST(TRY_CAST(timestamp AS BIGINT) AS VARCHAR)=timestamp
            AND regexp_full_match(itemid,'[0-9]+') AND TRY_CAST(itemid AS BIGINT) IS NOT NULL
            AND CAST(TRY_CAST(itemid AS BIGINT) AS VARCHAR)=itemid
            AND ((property='available' AND value IN ('0','1'))
                OR (property='categoryid' AND regexp_full_match(value,'[0-9]+')
                    AND TRY_CAST(value AS BIGINT) IS NOT NULL)),false)) AS raw_key_value_violations
    FROM selected_rows
), input_guard AS (
    SELECT s.*,r.*,n.*,e.*,COALESCE(s.raw_schema_mismatch=0
        AND r.raw_rows=e.expected_raw_rows AND r.raw_rows>0
        AND r.raw_part1_rows=e.expected_part1 AND r.raw_part2_rows=e.expected_part2
        AND r.raw_unknown_source_rows=0 AND r.other_property_rows=e.expected_other_rows
        AND n.selected_rows=e.expected_selected_rows AND n.selected_rows>0
        AND n.raw_category_rows=e.expected_category_rows AND n.raw_available_rows=e.expected_available_rows
        AND n.raw_candidate_key_surplus=0 AND n.raw_key_value_violations=0,false) AS valid_input
    FROM raw_schema s CROSS JOIN raw_health r CROSS JOIN selected_health n CROSS JOIN expected_counts e
), expected_schema(column_name,data_type,ordinal_position) AS (
    VALUES ('timestamp','BIGINT',1),('itemid','BIGINT',2),('property','VARCHAR',3),
        ('value','VARCHAR',4),('source_file','VARCHAR',5)
), staging_columns AS (
    SELECT column_name,data_type,ordinal_position FROM information_schema.columns
    WHERE table_catalog=current_database() AND table_schema='rr_stg' AND table_name='item_state_observations'
), staging_schema AS (
    SELECT COUNT(*) FILTER (WHERE e.column_name IS DISTINCT FROM s.column_name
        OR e.data_type IS DISTINCT FROM s.data_type) AS staging_schema_mismatch
    FROM expected_schema e FULL OUTER JOIN staging_columns s USING (ordinal_position)
), staging_health AS (
    SELECT COUNT(*) AS staging_rows,
        COUNT(*) FILTER (WHERE property='categoryid') AS categoryid_rows,
        COUNT(*) FILTER (WHERE property='available') AS available_rows,
        COUNT(*) FILTER (WHERE timestamp IS NULL OR itemid IS NULL OR property IS NULL OR property=''
            OR value IS NULL OR value='' OR source_file IS NULL OR source_file='') AS missing_required_rows,
        COUNT(*) FILTER (WHERE timestamp<0 OR itemid<0) AS negative_numeric_rows,
        COUNT(*) FILTER (WHERE NOT COALESCE(
            (property='available' AND value IN ('0','1')) OR (property='categoryid'
            AND regexp_full_match(value,'[0-9]+') AND TRY_CAST(value AS BIGINT) IS NOT NULL),false)) AS value_rule_violations,
        COUNT(*) FILTER (WHERE property IS NULL OR property NOT IN ('categoryid','available')) AS unexpected_property_rows,
        COUNT(*) FILTER (WHERE source_file IS NULL OR source_file NOT IN
            ('item_properties_part1.csv','item_properties_part2.csv')) AS unknown_source_file_rows,
        COUNT(*)-COUNT(DISTINCT (itemid,property,timestamp)) AS candidate_key_surplus,
        COUNT(*) FILTER (WHERE source_file='item_properties_part1.csv') AS selected_part1_rows,
        COUNT(*) FILTER (WHERE source_file='item_properties_part2.csv') AS selected_part2_rows
    FROM rr_stg.item_state_observations
), raw_only AS (
    SELECT timestamp,itemid,property,value,source_file FROM selected_rows
    EXCEPT ALL SELECT CAST(timestamp AS VARCHAR),CAST(itemid AS VARCHAR),property,value,source_file
        FROM rr_stg.item_state_observations
), staging_only AS (
    SELECT CAST(timestamp AS VARCHAR),CAST(itemid AS VARCHAR),property,value,source_file
        FROM rr_stg.item_state_observations
    EXCEPT ALL SELECT timestamp,itemid,property,value,source_file FROM selected_rows
), comparison_counts AS (
    SELECT (SELECT COUNT(*) FROM raw_only) AS raw_only_rows,
        (SELECT COUNT(*) FROM staging_only) AS staging_only_rows
), metrics AS MATERIALIZED (
    SELECT g.*,s.*,h.*,c.* FROM input_guard g CROSS JOIN staging_schema s
        CROSS JOIN staging_health h CROSS JOIN comparison_counts c
), controls AS (
    SELECT 1 AS check_order,'raw_rows' AS check_name,raw_rows AS actual,expected_raw_rows AS expected FROM metrics
    UNION ALL SELECT 2,'raw_part1_rows',raw_part1_rows,expected_part1 FROM metrics
    UNION ALL SELECT 3,'raw_part2_rows',raw_part2_rows,expected_part2 FROM metrics
    UNION ALL SELECT 4,'raw_schema_mismatch',raw_schema_mismatch,0 FROM metrics
    UNION ALL SELECT 5,'raw_unknown_source_rows',raw_unknown_source_rows,0 FROM metrics
    UNION ALL SELECT 6,'staging_rows',staging_rows,expected_selected_rows FROM metrics
    UNION ALL SELECT 7,'staging_schema_mismatch',staging_schema_mismatch,0 FROM metrics
    UNION ALL SELECT 8,'categoryid_rows',categoryid_rows,expected_category_rows FROM metrics
    UNION ALL SELECT 9,'available_rows',available_rows,expected_available_rows FROM metrics
    UNION ALL SELECT 10,'other_property_rows',other_property_rows,expected_other_rows FROM metrics
    UNION ALL SELECT 11,'missing_required_rows',missing_required_rows,0 FROM metrics
    UNION ALL SELECT 12,'negative_numeric_rows',negative_numeric_rows,0 FROM metrics
    UNION ALL SELECT 13,'value_rule_violations',value_rule_violations,0 FROM metrics
    UNION ALL SELECT 14,'unexpected_property_rows',unexpected_property_rows,0 FROM metrics
    UNION ALL SELECT 15,'unknown_source_file_rows',unknown_source_file_rows,0 FROM metrics
    UNION ALL SELECT 16,'candidate_key_surplus',candidate_key_surplus,0 FROM metrics
    UNION ALL SELECT 17,'raw_key_value_violations',raw_key_value_violations,0 FROM metrics
    UNION ALL SELECT 18,'raw_only_rows',raw_only_rows,0 FROM metrics
    UNION ALL SELECT 19,'staging_only_rows',staging_only_rows,0 FROM metrics
    UNION ALL SELECT 20,'source_contract_violations',CASE WHEN valid_input THEN 0 ELSE 1 END,0 FROM metrics
), controls_status AS (
    SELECT COUNT(*)=20 AND COUNT(*) FILTER (WHERE actual IS DISTINCT FROM expected)=0 AS all_controls_valid
    FROM controls
), report AS (
    SELECT * FROM controls
    UNION ALL SELECT 21,'selected_part1_rows',CASE WHEN c.all_controls_valid THEN m.selected_part1_rows END,NULL::BIGINT
        FROM metrics m CROSS JOIN controls_status c
    UNION ALL SELECT 22,'selected_part2_rows',CASE WHEN c.all_controls_valid THEN m.selected_part2_rows END,NULL::BIGINT
        FROM metrics m CROSS JOIN controls_status c
)
SELECT check_order,check_name,actual::BIGINT AS actual,expected::BIGINT AS expected,
    CASE WHEN actual IS NULL THEN 'BLOCKED' WHEN expected IS NULL THEN 'INFO'
         WHEN actual=expected THEN 'PASS' ELSE 'FAIL' END AS status
FROM report ORDER BY check_order;
