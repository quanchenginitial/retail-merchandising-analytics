-- Read-only investigation of SQL58's exact-unmatched category-property cohort.
-- Numeric interpretation is a diagnostic only; raw values and matches never change.
-- INFO values are observations, not zero-target success requirements.
WITH expected_counts AS (
    SELECT 20275902::BIGINT AS expected_rows,788214::BIGINT AS expected_category_rows,
        167::BIGINT AS expected_unmatched_rows,1669::BIGINT AS expected_reference_rows
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
    SELECT COUNT(*) AS raw_rows,COUNT(*) FILTER (WHERE property='categoryid') AS categoryid_rows,
        COUNT(*) FILTER (WHERE source_file IS NULL OR source_file NOT IN
            ('item_properties_part1.csv','item_properties_part2.csv')) AS unknown_source_file_rows
    FROM rr_raw.item_properties
), reference_groups AS MATERIALIZED (
    SELECT categoryid,COUNT(*) AS reference_group_rows,
        CASE WHEN regexp_full_match(categoryid,'[0-9]+') AND TRY_CAST(categoryid AS BIGINT) IS NOT NULL
            THEN TRY_CAST(categoryid AS BIGINT) END AS numeric_id
    FROM rr_raw.category_tree GROUP BY categoryid
), reference_stats AS (
    SELECT COALESCE(SUM(reference_group_rows),0) AS category_reference_rows,
        COALESCE(SUM(reference_group_rows-1),0) AS reference_duplicate_id_surplus,
        COALESCE(SUM(reference_group_rows) FILTER (WHERE categoryid IS NULL OR categoryid=''),0) AS reference_missing_ids,
        COALESCE(SUM(reference_group_rows) FILTER (WHERE numeric_id IS NULL),0) AS reference_numeric_ineligible_rows
    FROM reference_groups
), numeric_reference AS MATERIALIZED (
    -- reference_groups already has one row per distinct raw spelling.
    SELECT numeric_id,COUNT(*) AS raw_reference_spellings
    FROM reference_groups WHERE numeric_id IS NOT NULL GROUP BY numeric_id
), numeric_reference_stats AS (
    SELECT COUNT(*) FILTER (WHERE raw_reference_spellings>1) AS reference_ambiguous_normalized_ids
    FROM numeric_reference
), unmatched AS MATERIALIZED (
    SELECT p.timestamp,p.itemid,p.value,p.source_file,
        CASE WHEN regexp_full_match(p.value,'[0-9]+') AND TRY_CAST(p.value AS BIGINT) IS NOT NULL
            THEN TRY_CAST(p.value AS BIGINT) END AS numeric_id
    FROM rr_raw.item_properties p
    WHERE p.property='categoryid' AND NOT EXISTS (
        SELECT 1 FROM rr_raw.category_tree c WHERE c.categoryid=p.value
    )
), cohort_stats AS (
    SELECT COUNT(*) AS exact_unmatched_rows,COUNT(DISTINCT u.itemid) AS unmatched_items,
        COUNT(DISTINCT u.value) AS unmatched_raw_category_values,
        COUNT(DISTINCT u.timestamp) AS unmatched_raw_timestamps,
        COUNT(*) FILTER (WHERE u.source_file='item_properties_part1.csv') AS unmatched_part1_rows,
        COUNT(*) FILTER (WHERE u.source_file='item_properties_part2.csv') AS unmatched_part2_rows,
        COUNT(*) FILTER (WHERE u.numeric_id IS NOT NULL) AS unmatched_numeric_eligible_rows,
        COUNT(*) FILTER (WHERE u.numeric_id IS NULL) AS unmatched_numeric_ineligible_rows,
        COUNT(*) FILTER (WHERE u.numeric_id IS NOT NULL AND n.raw_reference_spellings=1) AS unmatched_numeric_unique_reference_rows,
        COUNT(*) FILTER (WHERE u.numeric_id IS NOT NULL AND n.raw_reference_spellings>1) AS unmatched_numeric_ambiguous_reference_rows,
        COUNT(*) FILTER (WHERE u.numeric_id IS NOT NULL AND n.raw_reference_spellings IS NULL) AS unmatched_numeric_no_reference_rows
    FROM unmatched u LEFT JOIN numeric_reference n ON u.numeric_id=n.numeric_id
), metrics AS MATERIALIZED (
    SELECT r.*,c.*,n.*,u.*,e.*,
        r.raw_rows=e.expected_rows AND r.categoryid_rows=e.expected_category_rows
            AND u.exact_unmatched_rows=e.expected_unmatched_rows
            AND c.category_reference_rows=e.expected_reference_rows
            AND c.reference_duplicate_id_surplus=0 AND c.reference_missing_ids=0
            AND r.unknown_source_file_rows=0 AS valid_input
    FROM raw_stats r CROSS JOIN reference_stats c CROSS JOIN numeric_reference_stats n
        CROSS JOIN cohort_stats u CROSS JOIN expected_counts e
), report AS (
    SELECT 1 AS check_order,'raw_rows' AS check_name,raw_rows AS actual,expected_rows AS expected FROM metrics
    UNION ALL SELECT 2,'categoryid_rows',categoryid_rows,expected_category_rows FROM metrics
    UNION ALL SELECT 3,'exact_unmatched_rows',exact_unmatched_rows,expected_unmatched_rows FROM metrics
    UNION ALL SELECT 4,'category_reference_rows',category_reference_rows,expected_reference_rows FROM metrics
    UNION ALL SELECT 5,'reference_duplicate_id_surplus',reference_duplicate_id_surplus,0 FROM metrics
    UNION ALL SELECT 6,'reference_missing_ids',reference_missing_ids,0 FROM metrics
    UNION ALL SELECT 7,'unknown_source_file_rows',unknown_source_file_rows,0 FROM metrics
    UNION ALL SELECT 8,'unmatched_items',unmatched_items,NULL::BIGINT FROM metrics
    UNION ALL SELECT 9,'unmatched_raw_category_values',unmatched_raw_category_values,NULL::BIGINT FROM metrics
    UNION ALL SELECT 10,'unmatched_raw_timestamps',unmatched_raw_timestamps,NULL::BIGINT FROM metrics
    UNION ALL SELECT 11,'unmatched_part1_rows',unmatched_part1_rows,NULL::BIGINT FROM metrics
    UNION ALL SELECT 12,'unmatched_part2_rows',unmatched_part2_rows,NULL::BIGINT FROM metrics
    UNION ALL SELECT 13,'reference_numeric_ineligible_rows',reference_numeric_ineligible_rows,NULL::BIGINT FROM metrics
    UNION ALL SELECT 14,'reference_ambiguous_normalized_ids',reference_ambiguous_normalized_ids,NULL::BIGINT FROM metrics
    UNION ALL SELECT 15,'unmatched_numeric_eligible_rows',unmatched_numeric_eligible_rows,NULL::BIGINT FROM metrics
    UNION ALL SELECT 16,'unmatched_numeric_ineligible_rows',unmatched_numeric_ineligible_rows,NULL::BIGINT FROM metrics
    UNION ALL SELECT 17,'unmatched_numeric_unique_reference_rows',unmatched_numeric_unique_reference_rows,NULL::BIGINT FROM metrics
    UNION ALL SELECT 18,'unmatched_numeric_ambiguous_reference_rows',unmatched_numeric_ambiguous_reference_rows,NULL::BIGINT FROM metrics
    UNION ALL SELECT 19,'unmatched_numeric_no_reference_rows',unmatched_numeric_no_reference_rows,NULL::BIGINT FROM metrics
    UNION ALL SELECT 20,'unmatched_part_rows_reconciled',unmatched_part1_rows+unmatched_part2_rows,exact_unmatched_rows FROM metrics
    UNION ALL SELECT 21,'unmatched_numeric_eligibility_reconciled',unmatched_numeric_eligible_rows+unmatched_numeric_ineligible_rows,exact_unmatched_rows FROM metrics
    UNION ALL SELECT 22,'unmatched_numeric_candidate_partition_reconciled',unmatched_numeric_unique_reference_rows+unmatched_numeric_ambiguous_reference_rows+unmatched_numeric_no_reference_rows,unmatched_numeric_eligible_rows FROM metrics
)
SELECT r.check_order,r.check_name,r.actual::BIGINT AS actual,r.expected::BIGINT AS expected,
    CASE WHEN NOT (p.valid_schema AND c.valid_schema) THEN error('SQL59 requires the accepted five and two VARCHAR columns in source order')
         WHEN r.expected IS NULL THEN CASE WHEN m.valid_input THEN 'INFO' ELSE 'BLOCKED' END
         WHEN r.actual=r.expected THEN 'PASS' ELSE 'FAIL' END AS status
FROM property_schema p CROSS JOIN category_schema c CROSS JOIN metrics m LEFT JOIN report r ON true
ORDER BY r.check_order;
