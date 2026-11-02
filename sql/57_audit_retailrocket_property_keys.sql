-- Read-only raw-key audit after SQL56. Do not reread source CSVs or mutate rows.
-- INFO observations have no target; exact repetitions/conflicts are not forced to zero.
-- Raw string identity only: no trimming, casts, deduplication or latest-state selection.
WITH expected_counts AS (
    SELECT 20275902::BIGINT AS expected_rows,10999999::BIGINT AS expected_part1,9275903::BIGINT AS expected_part2
), schema_health AS (
    SELECT COUNT(*)=5 AND COUNT(*) FILTER (WHERE data_type='VARCHAR')=5
        AND COUNT(*) FILTER (WHERE column_name IS DISTINCT FROM
            CASE ordinal_position WHEN 1 THEN 'timestamp' WHEN 2 THEN 'itemid'
                WHEN 3 THEN 'property' WHEN 4 THEN 'value' WHEN 5 THEN 'source_file' END)=0 AS valid_schema
    FROM information_schema.columns
    WHERE table_catalog=current_database() AND table_schema='rr_raw' AND table_name='item_properties'
), row_stats AS MATERIALIZED (
    SELECT COUNT(*) AS raw_rows,
        COUNT(*) FILTER (WHERE source_file='item_properties_part1.csv') AS part1_rows,
        COUNT(*) FILTER (WHERE source_file='item_properties_part2.csv') AS part2_rows,
        COUNT(*) FILTER (WHERE timestamp IS NULL OR timestamp='' OR itemid IS NULL OR itemid=''
            OR property IS NULL OR property='' OR value IS NULL OR value='') AS missing_core_rows,
        COUNT(*) FILTER (WHERE source_file IS NULL OR source_file NOT IN
            ('item_properties_part1.csv','item_properties_part2.csv')) AS unknown_source_file_rows
    FROM rr_raw.item_properties
), tuple_groups AS MATERIALIZED (
    SELECT itemid,property,timestamp,value,COUNT(*) AS tuple_rows,
        BOOL_OR(source_file='item_properties_part1.csv') AS in_part1,
        BOOL_OR(source_file='item_properties_part2.csv') AS in_part2
    FROM rr_raw.item_properties
    GROUP BY itemid,property,timestamp,value
), key_groups AS MATERIALIZED (
    SELECT itemid,property,timestamp,COUNT(*) AS value_groups,SUM(tuple_rows) AS key_rows,
        BOOL_OR(in_part1) AS in_part1,BOOL_OR(in_part2) AS in_part2
    FROM tuple_groups
    GROUP BY itemid,property,timestamp
), tuple_stats AS (
    SELECT COUNT(*) AS distinct_exact_tuples,
        COALESCE(SUM(tuple_rows),0) AS tuple_rows,
        COALESCE(SUM(tuple_rows-1),0) AS exact_duplicate_surplus_rows,
        COUNT(*) FILTER (WHERE in_part1 AND in_part2) AS cross_part_exact_tuples
    FROM tuple_groups
), key_stats AS (
    SELECT COUNT(DISTINCT itemid) AS distinct_items,
        COUNT(DISTINCT property) AS distinct_property_names,
        COUNT(DISTINCT (itemid,property)) AS distinct_item_property_pairs,
        COUNT(*) AS candidate_keys,
        COUNT(*) FILTER (WHERE value_groups>1) AS conflicting_candidate_keys,
        COALESCE(SUM(key_rows) FILTER (WHERE value_groups>1),0) AS rows_in_conflicting_keys,
        COUNT(*) FILTER (WHERE in_part1 AND in_part2) AS cross_part_candidate_keys,
        COALESCE(SUM(key_rows),0) AS key_rows,
        COALESCE(SUM(value_groups),0) AS key_value_groups
    FROM key_groups
), metrics AS MATERIALIZED (
    SELECT r.*,t.*,k.*,e.*,
        r.raw_rows=e.expected_rows AND r.part1_rows=e.expected_part1 AND r.part2_rows=e.expected_part2
            AND r.missing_core_rows=0 AND r.unknown_source_file_rows=0 AS valid_input
    FROM row_stats r CROSS JOIN tuple_stats t CROSS JOIN key_stats k CROSS JOIN expected_counts e
), report AS (
    SELECT 1 AS check_order,'raw_rows' AS check_name,raw_rows AS actual,expected_rows AS expected FROM metrics
    UNION ALL SELECT 2,'part1_rows',part1_rows,expected_part1 FROM metrics
    UNION ALL SELECT 3,'part2_rows',part2_rows,expected_part2 FROM metrics
    UNION ALL SELECT 4,'missing_core_rows',missing_core_rows,0 FROM metrics
    UNION ALL SELECT 5,'unknown_source_file_rows',unknown_source_file_rows,0 FROM metrics
    UNION ALL SELECT 6,'distinct_items',distinct_items,NULL::BIGINT FROM metrics
    UNION ALL SELECT 7,'distinct_property_names',distinct_property_names,NULL::BIGINT FROM metrics
    UNION ALL SELECT 8,'distinct_item_property_pairs',distinct_item_property_pairs,NULL::BIGINT FROM metrics
    UNION ALL SELECT 9,'candidate_keys',candidate_keys,NULL::BIGINT FROM metrics
    UNION ALL SELECT 10,'distinct_exact_tuples',distinct_exact_tuples,NULL::BIGINT FROM metrics
    UNION ALL SELECT 11,'exact_duplicate_surplus_rows',exact_duplicate_surplus_rows,NULL::BIGINT FROM metrics
    UNION ALL SELECT 12,'conflicting_candidate_keys',conflicting_candidate_keys,NULL::BIGINT FROM metrics
    UNION ALL SELECT 13,'rows_in_conflicting_keys',rows_in_conflicting_keys,NULL::BIGINT FROM metrics
    UNION ALL SELECT 14,'cross_part_exact_tuples',cross_part_exact_tuples,NULL::BIGINT FROM metrics
    UNION ALL SELECT 15,'cross_part_candidate_keys',cross_part_candidate_keys,NULL::BIGINT FROM metrics
    UNION ALL SELECT 16,'part_rows_reconciled',part1_rows+part2_rows,raw_rows FROM metrics
    UNION ALL SELECT 17,'tuple_rows_reconciled',tuple_rows,raw_rows FROM metrics
    UNION ALL SELECT 18,'key_rows_reconciled',key_rows,raw_rows FROM metrics
    UNION ALL SELECT 19,'exact_tuple_surplus_reconciled',distinct_exact_tuples+exact_duplicate_surplus_rows,raw_rows FROM metrics
    UNION ALL SELECT 20,'key_value_groups_reconciled',key_value_groups,distinct_exact_tuples FROM metrics
)
SELECT r.check_order,r.check_name,r.actual::BIGINT AS actual,r.expected::BIGINT AS expected,
    CASE WHEN NOT s.valid_schema THEN error('SQL57 requires the accepted five VARCHAR columns in source order')
         WHEN r.expected IS NULL THEN CASE WHEN m.valid_input THEN 'INFO' ELSE 'BLOCKED' END
         WHEN r.actual=r.expected THEN 'PASS' ELSE 'FAIL' END AS status
FROM schema_health s CROSS JOIN metrics m LEFT JOIN report r ON true
ORDER BY r.check_order;
