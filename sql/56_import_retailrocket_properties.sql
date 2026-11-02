-- Run once in the existing retail_merchandising DBeaver connection.
-- Two physical parts of one raw attribute log; their date ranges overlap.
-- Four exact source strings plus source_file provenance; no deduplication or joins.
-- Existing rr_raw.item_properties is never replaced or appended to.
CREATE SCHEMA IF NOT EXISTS rr_raw;

CREATE TABLE rr_raw.item_properties AS
SELECT timestamp,itemid,property,value,'item_properties_part1.csv'::VARCHAR AS source_file
FROM read_csv(
    'D:/database/retailrocket/item_properties_part1.csv',
    header=true, auto_detect=false,
    columns={'timestamp':'VARCHAR','itemid':'VARCHAR','property':'VARCHAR','value':'VARCHAR'},
    delim=',', quote='"', escape='"', encoding='utf-8',
    nullstr='', force_not_null=['timestamp','itemid','property','value'],
    strict_mode=true, ignore_errors=false, null_padding=false
)
UNION ALL
SELECT timestamp,itemid,property,value,'item_properties_part2.csv'::VARCHAR AS source_file
FROM read_csv(
    'D:/database/retailrocket/item_properties_part2.csv',
    header=true, auto_detect=false,
    columns={'timestamp':'VARCHAR','itemid':'VARCHAR','property':'VARCHAR','value':'VARCHAR'},
    delim=',', quote='"', escape='"', encoding='utf-8',
    nullstr='', force_not_null=['timestamp','itemid','property','value'],
    strict_mode=true, ignore_errors=false, null_padding=false
);

-- CHECKS: if the raw table already exists, run everything below this marker.
-- This replaceable TEMP table holds aggregate checks only, for this session.
-- Four separate statements below limit each exact comparison to one part/direction.
CREATE OR REPLACE TEMP TABLE rr_properties_import_checks AS
WITH expected_counts AS (
    SELECT 20275902 AS expected_rows,10999999 AS expected_part1,9275903 AS expected_part2
), column_stats AS (
    SELECT COUNT(*) AS columns,COUNT(*) FILTER (WHERE data_type='VARCHAR') AS varchar_columns,
        COUNT(*) FILTER (WHERE column_name IS DISTINCT FROM
            CASE ordinal_position WHEN 1 THEN 'timestamp' WHEN 2 THEN 'itemid'
                WHEN 3 THEN 'property' WHEN 4 THEN 'value' WHEN 5 THEN 'source_file' END) AS sequence_errors
    FROM information_schema.columns
    WHERE table_catalog=current_database() AND table_schema='rr_raw' AND table_name='item_properties'
), row_stats AS (
    SELECT COUNT(*) AS rows,
        COUNT(*) FILTER (WHERE source_file='item_properties_part1.csv') AS part1_rows,
        COUNT(*) FILTER (WHERE source_file='item_properties_part2.csv') AS part2_rows,
        COUNT(*) FILTER (WHERE timestamp IS NULL OR timestamp='' OR itemid IS NULL OR itemid=''
            OR property IS NULL OR property='' OR value IS NULL OR value='') AS missing_required,
        COUNT(*) FILTER (WHERE timestamp IS NOT NULL AND
            (NOT regexp_full_match(timestamp,'[0-9]+') OR TRY_CAST(timestamp AS BIGINT) IS NULL)) AS invalid_timestamp,
        COUNT(*) FILTER (WHERE itemid IS NOT NULL AND
            (NOT regexp_full_match(itemid,'[0-9]+') OR TRY_CAST(itemid AS BIGINT) IS NULL)) AS invalid_itemid,
        COUNT(*) FILTER (WHERE source_file IS NULL OR source_file NOT IN
            ('item_properties_part1.csv','item_properties_part2.csv')) AS unknown_source_files
    FROM rr_raw.item_properties
)
SELECT 1 AS check_order,'row_count' AS check_name,r.rows AS actual,e.expected_rows::BIGINT AS expected FROM row_stats r CROSS JOIN expected_counts e
UNION ALL SELECT 2,'part1_row_count',r.part1_rows,e.expected_part1 FROM row_stats r CROSS JOIN expected_counts e
UNION ALL SELECT 3,'part2_row_count',r.part2_rows,e.expected_part2 FROM row_stats r CROSS JOIN expected_counts e
UNION ALL SELECT 4,'column_count',columns,5 FROM column_stats
UNION ALL SELECT 5,'varchar_column_count',varchar_columns,5 FROM column_stats
UNION ALL SELECT 6,'column_sequence_errors',sequence_errors,0 FROM column_stats
UNION ALL SELECT 7,'missing_required_rows',missing_required,0 FROM row_stats
UNION ALL SELECT 8,'invalid_timestamp_rows',invalid_timestamp,0 FROM row_stats
UNION ALL SELECT 9,'invalid_itemid_rows',invalid_itemid,0 FROM row_stats
UNION ALL SELECT 10,'unknown_source_file_rows',unknown_source_files,0 FROM row_stats;

-- PART 1: source observations missing from the table, including multiplicity.
INSERT INTO rr_properties_import_checks
SELECT 11,'part1_source_rows_absent_from_table',COUNT(*),0
FROM (
    SELECT timestamp,itemid,property,value,'item_properties_part1.csv'::VARCHAR AS source_file
    FROM read_csv(
        'D:/database/retailrocket/item_properties_part1.csv',
        header=true, auto_detect=false,
        columns={'timestamp':'VARCHAR','itemid':'VARCHAR','property':'VARCHAR','value':'VARCHAR'},
        delim=',', quote='"', escape='"', encoding='utf-8',
        nullstr='', force_not_null=['timestamp','itemid','property','value'],
        strict_mode=true, ignore_errors=false, null_padding=false
    )
    EXCEPT ALL
    SELECT timestamp,itemid,property,value,source_file FROM rr_raw.item_properties
    WHERE source_file='item_properties_part1.csv'
) differences;

-- PART 1: table observations absent from that source part.
INSERT INTO rr_properties_import_checks
SELECT 12,'part1_table_rows_absent_from_source',COUNT(*),0
FROM (
    SELECT timestamp,itemid,property,value,source_file FROM rr_raw.item_properties
    WHERE source_file='item_properties_part1.csv'
    EXCEPT ALL
    SELECT timestamp,itemid,property,value,'item_properties_part1.csv'::VARCHAR AS source_file
    FROM read_csv(
        'D:/database/retailrocket/item_properties_part1.csv',
        header=true, auto_detect=false,
        columns={'timestamp':'VARCHAR','itemid':'VARCHAR','property':'VARCHAR','value':'VARCHAR'},
        delim=',', quote='"', escape='"', encoding='utf-8',
        nullstr='', force_not_null=['timestamp','itemid','property','value'],
        strict_mode=true, ignore_errors=false, null_padding=false
    )
) differences;

-- PART 2: source observations missing from the table, including multiplicity.
INSERT INTO rr_properties_import_checks
SELECT 13,'part2_source_rows_absent_from_table',COUNT(*),0
FROM (
    SELECT timestamp,itemid,property,value,'item_properties_part2.csv'::VARCHAR AS source_file
    FROM read_csv(
        'D:/database/retailrocket/item_properties_part2.csv',
        header=true, auto_detect=false,
        columns={'timestamp':'VARCHAR','itemid':'VARCHAR','property':'VARCHAR','value':'VARCHAR'},
        delim=',', quote='"', escape='"', encoding='utf-8',
        nullstr='', force_not_null=['timestamp','itemid','property','value'],
        strict_mode=true, ignore_errors=false, null_padding=false
    )
    EXCEPT ALL
    SELECT timestamp,itemid,property,value,source_file FROM rr_raw.item_properties
    WHERE source_file='item_properties_part2.csv'
) differences;

-- PART 2: table observations absent from that source part.
INSERT INTO rr_properties_import_checks
SELECT 14,'part2_table_rows_absent_from_source',COUNT(*),0
FROM (
    SELECT timestamp,itemid,property,value,source_file FROM rr_raw.item_properties
    WHERE source_file='item_properties_part2.csv'
    EXCEPT ALL
    SELECT timestamp,itemid,property,value,'item_properties_part2.csv'::VARCHAR AS source_file
    FROM read_csv(
        'D:/database/retailrocket/item_properties_part2.csv',
        header=true, auto_detect=false,
        columns={'timestamp':'VARCHAR','itemid':'VARCHAR','property':'VARCHAR','value':'VARCHAR'},
        delim=',', quote='"', escape='"', encoding='utf-8',
        nullstr='', force_not_null=['timestamp','itemid','property','value'],
        strict_mode=true, ignore_errors=false, null_padding=false
    )
) differences;

SELECT check_order,check_name,actual,expected,
    CASE WHEN actual=expected THEN 'PASS' ELSE 'FAIL' END AS status
FROM rr_properties_import_checks ORDER BY check_order;

