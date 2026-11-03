-- Run once in the existing retail_merchandising connection.
-- Only known category-reference rows are staged; unmatched property rows stay raw.
-- Exact text roundtrip is required; no trimming, recoding, merging or invented keys.
CREATE SCHEMA IF NOT EXISTS rr_stg;

CREATE TABLE rr_stg.category_tree AS
WITH expected_counts AS (
    SELECT 1669::BIGINT AS expected_rows,25::BIGINT AS expected_null_parents
), raw_schema AS (
    SELECT CASE WHEN COUNT(*)=2 AND COUNT(*) FILTER (WHERE data_type='VARCHAR')=2
        AND COUNT(*) FILTER (WHERE column_name IS DISTINCT FROM
            CASE ordinal_position WHEN 1 THEN 'categoryid' WHEN 2 THEN 'parentid' END)=0
        THEN 0 ELSE 1 END AS raw_schema_mismatch
    FROM information_schema.columns
    WHERE table_catalog=current_database() AND table_schema='rr_raw' AND table_name='category_tree'
), source_rows AS MATERIALIZED (
    SELECT categoryid,parentid FROM rr_raw.category_tree
), source_health AS (
    SELECT COUNT(*) AS raw_rows,
        COUNT(*) FILTER (WHERE parentid IS NULL) AS raw_null_parents,
        COUNT(*) FILTER (WHERE NOT COALESCE(
            regexp_full_match(categoryid,'[0-9]+')
            AND TRY_CAST(categoryid AS BIGINT) IS NOT NULL
            AND CAST(TRY_CAST(categoryid AS BIGINT) AS VARCHAR)=categoryid
            AND (parentid IS NULL OR (
                regexp_full_match(parentid,'[0-9]+')
                AND TRY_CAST(parentid AS BIGINT) IS NOT NULL
                AND CAST(TRY_CAST(parentid AS BIGINT) AS VARCHAR)=parentid)),false)) AS raw_value_contract_violations,
        COUNT(*)-COUNT(DISTINCT categoryid) AS raw_duplicate_keys,
        COUNT(*) FILTER (WHERE categoryid=parentid) AS raw_self_parents
    FROM source_rows
), source_orphans AS (
    SELECT COUNT(*) AS raw_orphan_parents FROM source_rows child
    WHERE child.parentid IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM source_rows parent WHERE parent.categoryid=child.parentid
    )
), numeric_key_groups AS (
    SELECT TRY_CAST(categoryid AS BIGINT) AS numeric_id,COUNT(DISTINCT categoryid) AS raw_spellings
    FROM source_rows WHERE TRY_CAST(categoryid AS BIGINT) IS NOT NULL
    GROUP BY TRY_CAST(categoryid AS BIGINT)
), source_collisions AS (
    SELECT COUNT(*) FILTER (WHERE raw_spellings>1) AS numeric_key_collisions FROM numeric_key_groups
), input_guard AS (
    SELECT s.*,h.*,o.*,c.*,e.*,
        s.raw_schema_mismatch=0 AND h.raw_rows=e.expected_rows
            AND h.raw_null_parents=e.expected_null_parents
            AND h.raw_value_contract_violations=0 AND h.raw_duplicate_keys=0
            AND h.raw_self_parents=0 AND o.raw_orphan_parents=0
            AND c.numeric_key_collisions=0 AS valid_input
    FROM raw_schema s CROSS JOIN source_health h CROSS JOIN source_orphans o
        CROSS JOIN source_collisions c CROSS JOIN expected_counts e
)
SELECT CASE WHEN g.valid_input THEN CAST(r.categoryid AS BIGINT)
            ELSE error('SQL60 raw category contract failed; destination was not created') END AS categoryid,
       CASE WHEN g.valid_input THEN CAST(r.parentid AS BIGINT)
            ELSE error('SQL60 raw category contract failed; destination was not created') END AS parentid
FROM input_guard g LEFT JOIN source_rows r ON true;

-- CHECKS: if rr_stg.category_tree already exists, run only the query below.
-- NULL parents remain root candidates; cycles, depth and root paths are deferred.
WITH expected_counts AS (
    SELECT 1669::BIGINT AS expected_rows,25::BIGINT AS expected_null_parents
), raw_schema AS (
    SELECT CASE WHEN COUNT(*)=2 AND COUNT(*) FILTER (WHERE data_type='VARCHAR')=2
        AND COUNT(*) FILTER (WHERE column_name IS DISTINCT FROM
            CASE ordinal_position WHEN 1 THEN 'categoryid' WHEN 2 THEN 'parentid' END)=0
        THEN 0 ELSE 1 END AS raw_schema_mismatch
    FROM information_schema.columns
    WHERE table_catalog=current_database() AND table_schema='rr_raw' AND table_name='category_tree'
), source_rows AS MATERIALIZED (
    SELECT categoryid,parentid FROM rr_raw.category_tree
), source_health AS (
    SELECT COUNT(*) AS raw_rows,
        COUNT(*) FILTER (WHERE parentid IS NULL) AS raw_null_parents,
        COUNT(*) FILTER (WHERE NOT COALESCE(
            regexp_full_match(categoryid,'[0-9]+')
            AND TRY_CAST(categoryid AS BIGINT) IS NOT NULL
            AND CAST(TRY_CAST(categoryid AS BIGINT) AS VARCHAR)=categoryid
            AND (parentid IS NULL OR (
                regexp_full_match(parentid,'[0-9]+')
                AND TRY_CAST(parentid AS BIGINT) IS NOT NULL
                AND CAST(TRY_CAST(parentid AS BIGINT) AS VARCHAR)=parentid)),false)) AS raw_value_contract_violations,
        COUNT(*)-COUNT(DISTINCT categoryid) AS raw_duplicate_keys,
        COUNT(*) FILTER (WHERE categoryid=parentid) AS raw_self_parents
    FROM source_rows
), source_orphans AS (
    SELECT COUNT(*) AS raw_orphan_parents FROM source_rows child
    WHERE child.parentid IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM source_rows parent WHERE parent.categoryid=child.parentid
    )
), numeric_key_groups AS (
    SELECT TRY_CAST(categoryid AS BIGINT) AS numeric_id,COUNT(DISTINCT categoryid) AS raw_spellings
    FROM source_rows WHERE TRY_CAST(categoryid AS BIGINT) IS NOT NULL
    GROUP BY TRY_CAST(categoryid AS BIGINT)
), source_collisions AS (
    SELECT COUNT(*) FILTER (WHERE raw_spellings>1) AS numeric_key_collisions FROM numeric_key_groups
), input_guard AS (
    SELECT s.*,h.*,o.*,c.*,e.*,
        s.raw_schema_mismatch=0 AND h.raw_rows=e.expected_rows
            AND h.raw_null_parents=e.expected_null_parents
            AND h.raw_value_contract_violations=0 AND h.raw_duplicate_keys=0
            AND h.raw_self_parents=0 AND o.raw_orphan_parents=0
            AND c.numeric_key_collisions=0 AS valid_input
    FROM raw_schema s CROSS JOIN source_health h CROSS JOIN source_orphans o
        CROSS JOIN source_collisions c CROSS JOIN expected_counts e
), expected_schema(column_name,data_type,ordinal_position) AS (
    VALUES ('categoryid','BIGINT',1),('parentid','BIGINT',2)
), staging_columns AS (
    SELECT column_name,data_type,ordinal_position FROM information_schema.columns
    WHERE table_catalog=current_database() AND table_schema='rr_stg' AND table_name='category_tree'
), column_stats AS (
    SELECT COUNT(*) AS column_count,COUNT(*) FILTER (WHERE data_type='BIGINT') AS bigint_column_count
    FROM staging_columns
), schema_stats AS (
    SELECT COUNT(*) FILTER (WHERE e.column_name IS DISTINCT FROM s.column_name
        OR e.data_type IS DISTINCT FROM s.data_type) AS schema_mismatch_count
    FROM expected_schema e FULL OUTER JOIN staging_columns s USING (ordinal_position)
), staging_stats AS (
    SELECT COUNT(*) AS staging_rows,COUNT(DISTINCT categoryid) AS distinct_categoryids,
        COUNT(*) FILTER (WHERE categoryid IS NULL) AS missing_categoryids,
        COUNT(*)-COUNT(DISTINCT categoryid) AS duplicate_key_surplus,
        COUNT(*) FILTER (WHERE parentid IS NULL) AS null_parent_rows,
        COUNT(*) FILTER (WHERE categoryid=parentid) AS self_parent_rows
    FROM rr_stg.category_tree
), staging_orphans AS (
    SELECT COUNT(*) AS orphan_parent_rows FROM rr_stg.category_tree child
    WHERE child.parentid IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM rr_stg.category_tree parent WHERE parent.categoryid=child.parentid
    )
), raw_only AS (
    SELECT categoryid,parentid FROM source_rows
    EXCEPT ALL SELECT CAST(categoryid AS VARCHAR),CAST(parentid AS VARCHAR) FROM rr_stg.category_tree
), staging_only AS (
    SELECT CAST(categoryid AS VARCHAR),CAST(parentid AS VARCHAR) FROM rr_stg.category_tree
    EXCEPT ALL SELECT categoryid,parentid FROM source_rows
), raw_roots_only AS (
    SELECT categoryid FROM source_rows WHERE parentid IS NULL
    EXCEPT SELECT CAST(categoryid AS VARCHAR) FROM rr_stg.category_tree WHERE parentid IS NULL
), staging_roots_only AS (
    SELECT CAST(categoryid AS VARCHAR) AS categoryid FROM rr_stg.category_tree WHERE parentid IS NULL
    EXCEPT SELECT categoryid FROM source_rows WHERE parentid IS NULL
), report AS (
    SELECT 1 AS check_order,'staging_rows' AS check_name,s.staging_rows AS actual,e.expected_rows AS expected FROM staging_stats s CROSS JOIN expected_counts e
    UNION ALL SELECT 2,'column_count',column_count,2 FROM column_stats
    UNION ALL SELECT 3,'bigint_column_count',bigint_column_count,2 FROM column_stats
    UNION ALL SELECT 4,'schema_mismatch_count',schema_mismatch_count,0 FROM schema_stats
    UNION ALL SELECT 5,'distinct_categoryids',s.distinct_categoryids,e.expected_rows FROM staging_stats s CROSS JOIN expected_counts e
    UNION ALL SELECT 6,'missing_categoryids',missing_categoryids,0 FROM staging_stats
    UNION ALL SELECT 7,'duplicate_key_surplus',duplicate_key_surplus,0 FROM staging_stats
    UNION ALL SELECT 8,'null_parent_rows',s.null_parent_rows,e.expected_null_parents FROM staging_stats s CROSS JOIN expected_counts e
    UNION ALL SELECT 9,'self_parent_rows',self_parent_rows,0 FROM staging_stats
    UNION ALL SELECT 10,'orphan_parent_rows',orphan_parent_rows,0 FROM staging_orphans
    UNION ALL SELECT 11,'raw_rows',raw_rows,expected_rows FROM input_guard
    UNION ALL SELECT 12,'raw_value_contract_violations',raw_value_contract_violations,0 FROM input_guard
    UNION ALL SELECT 13,'raw_only_rows',COUNT(*),0 FROM raw_only
    UNION ALL SELECT 14,'staging_only_rows',COUNT(*),0 FROM staging_only
    UNION ALL SELECT 15,'raw_null_parent_rows',raw_null_parents,expected_null_parents FROM input_guard
    UNION ALL SELECT 16,'root_set_difference',(SELECT COUNT(*) FROM raw_roots_only)+(SELECT COUNT(*) FROM staging_roots_only),0
    UNION ALL SELECT 17,'numeric_key_collisions',numeric_key_collisions,0 FROM input_guard
    UNION ALL SELECT 18,'raw_schema_mismatch',raw_schema_mismatch,0 FROM input_guard
)
SELECT check_order,check_name,actual::BIGINT AS actual,expected::BIGINT AS expected,
    CASE WHEN actual=expected THEN 'PASS' ELSE 'FAIL' END AS status
FROM report ORDER BY check_order;
