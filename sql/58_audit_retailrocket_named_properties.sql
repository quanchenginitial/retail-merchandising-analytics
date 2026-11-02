-- Read-only audit of exactly categoryid and available; other properties stay opaque.
-- Exact raw category-reference matching only. No event join, normalization or staging.
-- Semantic exceptions are INFO observations, never forced to zero.
WITH expected_counts AS (
    SELECT 20275902::BIGINT AS expected_rows,10999999::BIGINT AS expected_part1,
        9275903::BIGINT AS expected_part2,1669::BIGINT AS expected_reference_rows
), property_schema AS (
    SELECT COUNT(*)=5 AND COUNT(*) FILTER (WHERE data_type='VARCHAR')=5
        AND COUNT(*) FILTER (WHERE column_name IS DISTINCT FROM
            CASE ordinal_position WHEN 1 THEN 'timestamp' WHEN 2 THEN 'itemid'
                WHEN 3 THEN 'property' WHEN 4 THEN 'value' WHEN 5 THEN 'source_file' END)=0 AS valid_schema
    FROM information_schema.columns
    WHERE table_catalog=current_database() AND table_schema='rr_raw' AND table_name='item_properties'
), category_schema AS (
    SELECT COUNT(*)=2 AND COUNT(*) FILTER (WHERE data_type='VARCHAR')=2
        AND COUNT(*) FILTER (WHERE column_name IS DISTINCT FROM
            CASE ordinal_position WHEN 1 THEN 'categoryid' WHEN 2 THEN 'parentid' END)=0 AS valid_schema
    FROM information_schema.columns
    WHERE table_catalog=current_database() AND table_schema='rr_raw' AND table_name='category_tree'
), raw_stats AS (
    SELECT COUNT(*) AS raw_rows,
        COUNT(*) FILTER (WHERE source_file='item_properties_part1.csv') AS part1_rows,
        COUNT(*) FILTER (WHERE source_file='item_properties_part2.csv') AS part2_rows,
        COUNT(*) FILTER (WHERE source_file IS NULL OR source_file NOT IN
            ('item_properties_part1.csv','item_properties_part2.csv')) AS unknown_source_file_rows,
        COUNT(*) FILTER (WHERE property IS NULL OR property NOT IN ('categoryid','available')) AS other_property_rows
    FROM rr_raw.item_properties
), reference_groups AS (
    SELECT categoryid,COUNT(*) AS reference_group_rows
    FROM rr_raw.category_tree GROUP BY categoryid
), reference_stats AS (
    SELECT COALESCE(SUM(reference_group_rows),0) AS category_reference_rows,
        COALESCE(SUM(reference_group_rows-1),0) AS category_reference_duplicate_id_surplus,
        COALESCE(SUM(reference_group_rows) FILTER (WHERE categoryid IS NULL OR categoryid=''),0) AS category_reference_missing_ids
    FROM reference_groups
), named_rows AS MATERIALIZED (
    SELECT timestamp,itemid,property,value
    FROM rr_raw.item_properties WHERE property IN ('categoryid','available')
), named_stats AS (
    SELECT COUNT(*) FILTER (WHERE property='categoryid') AS categoryid_rows,
        COUNT(DISTINCT itemid) FILTER (WHERE property='categoryid') AS categoryid_items,
        COUNT(*) FILTER (WHERE property='available') AS available_rows,
        COUNT(DISTINCT itemid) FILTER (WHERE property='available') AS available_items,
        COUNT(*) FILTER (WHERE property='available' AND value='0') AS available_zero_rows,
        COUNT(*) FILTER (WHERE property='available' AND value='1') AS available_one_rows,
        COUNT(*) FILTER (WHERE property='available' AND (value IS NULL OR value NOT IN ('0','1'))) AS available_other_rows,
        COUNT(*) FILTER (WHERE property='categoryid' AND (value IS NULL
            OR NOT regexp_full_match(value,'[0-9]+') OR TRY_CAST(value AS BIGINT) IS NULL)) AS category_invalid_value_rows,
        COUNT(*) FILTER (WHERE timestamp IS NULL OR timestamp='' OR itemid IS NULL OR itemid='') AS named_missing_identity_rows,
        COUNT(*) FILTER (WHERE (timestamp IS NOT NULL AND timestamp<>'' AND
                (NOT regexp_full_match(timestamp,'[0-9]+') OR TRY_CAST(timestamp AS BIGINT) IS NULL))
            OR (itemid IS NOT NULL AND itemid<>'' AND
                (NOT regexp_full_match(itemid,'[0-9]+') OR TRY_CAST(itemid AS BIGINT) IS NULL))) AS named_invalid_identifier_or_timestamp_rows
    FROM named_rows
), category_match_stats AS (
    SELECT COUNT(*) FILTER (WHERE EXISTS (
        SELECT 1 FROM rr_raw.category_tree c WHERE c.categoryid=n.value
    )) AS category_matched_exact_rows,
        COUNT(*) FILTER (WHERE NOT EXISTS (
        SELECT 1 FROM rr_raw.category_tree c WHERE c.categoryid=n.value
    )) AS category_unmatched_exact_rows
    FROM named_rows n WHERE n.property='categoryid'
), metrics AS MATERIALIZED (
    SELECT r.*,c.*,n.*,m.*,e.*,
        r.raw_rows=e.expected_rows AND r.part1_rows=e.expected_part1 AND r.part2_rows=e.expected_part2
            AND r.unknown_source_file_rows=0 AND c.category_reference_rows=e.expected_reference_rows
            AND c.category_reference_duplicate_id_surplus=0 AND c.category_reference_missing_ids=0 AS valid_input
    FROM raw_stats r CROSS JOIN reference_stats c CROSS JOIN named_stats n
        CROSS JOIN category_match_stats m CROSS JOIN expected_counts e
), report AS (
    SELECT 1 AS check_order,'raw_rows' AS check_name,raw_rows AS actual,expected_rows AS expected FROM metrics
    UNION ALL SELECT 2,'part1_rows',part1_rows,expected_part1 FROM metrics
    UNION ALL SELECT 3,'part2_rows',part2_rows,expected_part2 FROM metrics
    UNION ALL SELECT 4,'unknown_source_file_rows',unknown_source_file_rows,0 FROM metrics
    UNION ALL SELECT 5,'category_reference_rows',category_reference_rows,expected_reference_rows FROM metrics
    UNION ALL SELECT 6,'category_reference_duplicate_id_surplus',category_reference_duplicate_id_surplus,0 FROM metrics
    UNION ALL SELECT 7,'category_reference_missing_ids',category_reference_missing_ids,0 FROM metrics
    UNION ALL SELECT 8,'categoryid_rows',categoryid_rows,NULL::BIGINT FROM metrics
    UNION ALL SELECT 9,'categoryid_items',categoryid_items,NULL::BIGINT FROM metrics
    UNION ALL SELECT 10,'available_rows',available_rows,NULL::BIGINT FROM metrics
    UNION ALL SELECT 11,'available_items',available_items,NULL::BIGINT FROM metrics
    UNION ALL SELECT 12,'other_property_rows',other_property_rows,NULL::BIGINT FROM metrics
    UNION ALL SELECT 13,'available_zero_rows',available_zero_rows,NULL::BIGINT FROM metrics
    UNION ALL SELECT 14,'available_one_rows',available_one_rows,NULL::BIGINT FROM metrics
    UNION ALL SELECT 15,'available_other_rows',available_other_rows,NULL::BIGINT FROM metrics
    UNION ALL SELECT 16,'category_invalid_value_rows',category_invalid_value_rows,NULL::BIGINT FROM metrics
    UNION ALL SELECT 17,'category_unmatched_exact_rows',category_unmatched_exact_rows,NULL::BIGINT FROM metrics
    UNION ALL SELECT 18,'named_missing_identity_rows',named_missing_identity_rows,NULL::BIGINT FROM metrics
    UNION ALL SELECT 19,'named_invalid_identifier_or_timestamp_rows',named_invalid_identifier_or_timestamp_rows,NULL::BIGINT FROM metrics
    UNION ALL SELECT 20,'property_partition_reconciled',categoryid_rows+available_rows+other_property_rows,raw_rows FROM metrics
    UNION ALL SELECT 21,'availability_partition_reconciled',available_zero_rows+available_one_rows+available_other_rows,available_rows FROM metrics
    UNION ALL SELECT 22,'category_match_partition_reconciled',category_matched_exact_rows+category_unmatched_exact_rows,categoryid_rows FROM metrics
)
SELECT r.check_order,r.check_name,r.actual::BIGINT AS actual,r.expected::BIGINT AS expected,
    CASE WHEN NOT (p.valid_schema AND c.valid_schema) THEN error('SQL58 requires the accepted five and two VARCHAR columns in source order')
         WHEN r.expected IS NULL THEN CASE WHEN m.valid_input THEN 'INFO' ELSE 'BLOCKED' END
         WHEN r.actual=r.expected THEN 'PASS' ELSE 'FAIL' END AS status
FROM property_schema p CROSS JOIN category_schema c CROSS JOIN metrics m LEFT JOIN report r ON true
ORDER BY r.check_order;
