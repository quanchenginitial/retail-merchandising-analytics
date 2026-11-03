-- Run once in the existing retail_merchandising connection.
-- Persist only the verified known-reference category/root/depth mapping.
-- Root depth is zero; this is not a time-varying category history.
CREATE SCHEMA IF NOT EXISTS rr_core;

CREATE TABLE rr_core.dim_category AS
WITH RECURSIVE expected_counts AS (
    SELECT 1669::BIGINT AS expected_rows,25::BIGINT AS expected_roots,5::BIGINT AS expected_max_depth
), source_schema AS (
    SELECT CASE WHEN COUNT(*)=2 AND COUNT(*) FILTER (WHERE data_type='BIGINT')=2
        AND COUNT(*) FILTER (WHERE column_name IS DISTINCT FROM
            CASE ordinal_position WHEN 1 THEN 'categoryid' WHEN 2 THEN 'parentid' END)=0
        THEN 0 ELSE 1 END AS source_schema_mismatch
    FROM information_schema.columns
    WHERE table_catalog=current_database() AND table_schema='rr_stg' AND table_name='category_tree'
), source_rows AS MATERIALIZED (
    SELECT categoryid,parentid FROM rr_stg.category_tree
), source_health AS (
    SELECT COUNT(*) AS source_rows,COUNT(*) FILTER (WHERE categoryid IS NULL) AS missing_ids,
        COUNT(categoryid)-COUNT(DISTINCT categoryid) AS duplicate_ids,
        COUNT(*) FILTER (WHERE categoryid<0 OR parentid<0) AS negative_ids,
        COUNT(*) FILTER (WHERE parentid IS NULL) AS source_roots,
        COUNT(*) FILTER (WHERE categoryid=parentid) AS self_parents
    FROM source_rows
), source_orphans AS (
    SELECT COUNT(*) AS orphan_parents FROM source_rows child
    WHERE child.parentid IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM source_rows parent WHERE parent.categoryid=child.parentid
    )
), admission AS MATERIALIZED (
    SELECT s.*,h.*,o.*,e.*,
        s.source_schema_mismatch=0 AND h.source_rows=e.expected_rows AND h.source_rows>0
            AND h.missing_ids=0 AND h.duplicate_ids=0 AND h.negative_ids=0
            AND o.orphan_parents=0 AS admitted
    FROM source_schema s CROSS JOIN source_health h CROSS JOIN source_orphans o
        CROSS JOIN expected_counts e
), nodes AS MATERIALIZED (
    SELECT r.* FROM source_rows r CROSS JOIN admission a WHERE a.admitted
), rooted_walk(categoryid,parentid,root_categoryid,depth) AS (
    SELECT categoryid,parentid,categoryid AS root_categoryid,0::BIGINT AS depth
    FROM nodes WHERE parentid IS NULL
    UNION ALL
    SELECT child.categoryid,child.parentid,parent.root_categoryid,parent.depth+1
    FROM rooted_walk parent JOIN nodes child ON child.parentid=parent.categoryid
        CROSS JOIN admission a
    WHERE parent.depth<a.source_rows-1
), traversal_stats AS (
    SELECT COUNT(*) AS mapping_rows,COUNT(DISTINCT categoryid) AS reached_categories,
        COUNT(*)-COUNT(DISTINCT categoryid) AS repeated_rows,MAX(depth) AS source_max_depth
    FROM rooted_walk
), boundary_stats AS (
    SELECT COUNT(*) AS depth_limit_child_edges
    FROM rooted_walk parent JOIN nodes child ON child.parentid=parent.categoryid
        CROSS JOIN admission a
    WHERE parent.depth=a.source_rows-1
), input_guard AS MATERIALIZED (
    SELECT a.*,t.*,b.*,
        COALESCE(a.admitted AND a.source_roots=a.expected_roots AND a.self_parents=0
            AND t.mapping_rows=a.source_rows AND t.reached_categories=a.source_rows
            AND t.repeated_rows=0 AND b.depth_limit_child_edges=0
            AND t.source_max_depth=a.expected_max_depth,false) AS valid_input
    FROM admission a CROSS JOIN traversal_stats t CROSS JOIN boundary_stats b
)
SELECT CASE WHEN g.valid_input THEN w.categoryid
            ELSE error('SQL62 source hierarchy contract failed; destination was not created') END::BIGINT AS categoryid,
       CASE WHEN g.valid_input THEN w.parentid
            ELSE error('SQL62 source hierarchy contract failed; destination was not created') END::BIGINT AS parentid,
       CASE WHEN g.valid_input THEN w.root_categoryid
            ELSE error('SQL62 source hierarchy contract failed; destination was not created') END::BIGINT AS root_categoryid,
       CASE WHEN g.valid_input THEN w.depth
            ELSE error('SQL62 source hierarchy contract failed; destination was not created') END::BIGINT AS depth
FROM input_guard g LEFT JOIN rooted_walk w ON true;

-- CHECKS: if rr_core.dim_category already exists, run only the query below.
WITH RECURSIVE expected_counts AS (
    SELECT 1669::BIGINT AS expected_rows,25::BIGINT AS expected_roots,5::BIGINT AS expected_max_depth
), source_schema AS (
    SELECT CASE WHEN COUNT(*)=2 AND COUNT(*) FILTER (WHERE data_type='BIGINT')=2
        AND COUNT(*) FILTER (WHERE column_name IS DISTINCT FROM
            CASE ordinal_position WHEN 1 THEN 'categoryid' WHEN 2 THEN 'parentid' END)=0
        THEN 0 ELSE 1 END AS source_schema_mismatch
    FROM information_schema.columns
    WHERE table_catalog=current_database() AND table_schema='rr_stg' AND table_name='category_tree'
), source_rows AS MATERIALIZED (
    SELECT categoryid,parentid FROM rr_stg.category_tree
), source_health AS (
    SELECT COUNT(*) AS source_rows,COUNT(*) FILTER (WHERE categoryid IS NULL) AS missing_ids,
        COUNT(categoryid)-COUNT(DISTINCT categoryid) AS duplicate_ids,
        COUNT(*) FILTER (WHERE categoryid<0 OR parentid<0) AS negative_ids,
        COUNT(*) FILTER (WHERE parentid IS NULL) AS source_roots,
        COUNT(*) FILTER (WHERE categoryid=parentid) AS self_parents
    FROM source_rows
), source_orphans AS (
    SELECT COUNT(*) AS orphan_parents FROM source_rows child
    WHERE child.parentid IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM source_rows parent WHERE parent.categoryid=child.parentid
    )
), admission AS MATERIALIZED (
    SELECT s.*,h.*,o.*,e.*,
        s.source_schema_mismatch=0 AND h.source_rows=e.expected_rows AND h.source_rows>0
            AND h.missing_ids=0 AND h.duplicate_ids=0 AND h.negative_ids=0
            AND o.orphan_parents=0 AS admitted
    FROM source_schema s CROSS JOIN source_health h CROSS JOIN source_orphans o
        CROSS JOIN expected_counts e
), nodes AS MATERIALIZED (
    SELECT r.* FROM source_rows r CROSS JOIN admission a WHERE a.admitted
), rooted_walk(categoryid,parentid,root_categoryid,depth) AS (
    SELECT categoryid,parentid,categoryid AS root_categoryid,0::BIGINT AS depth
    FROM nodes WHERE parentid IS NULL
    UNION ALL
    SELECT child.categoryid,child.parentid,parent.root_categoryid,parent.depth+1
    FROM rooted_walk parent JOIN nodes child ON child.parentid=parent.categoryid
        CROSS JOIN admission a
    WHERE parent.depth<a.source_rows-1
), traversal_stats AS (
    SELECT COUNT(*) AS mapping_rows,COUNT(DISTINCT categoryid) AS reached_categories,
        COUNT(*)-COUNT(DISTINCT categoryid) AS repeated_rows,MAX(depth) AS source_max_depth
    FROM rooted_walk
), boundary_stats AS (
    SELECT COUNT(*) AS depth_limit_child_edges
    FROM rooted_walk parent JOIN nodes child ON child.parentid=parent.categoryid
        CROSS JOIN admission a
    WHERE parent.depth=a.source_rows-1
), input_guard AS MATERIALIZED (
    SELECT a.*,t.*,b.*,
        COALESCE(a.admitted AND a.source_roots=a.expected_roots AND a.self_parents=0
            AND t.mapping_rows=a.source_rows AND t.reached_categories=a.source_rows
            AND t.repeated_rows=0 AND b.depth_limit_child_edges=0
            AND t.source_max_depth=a.expected_max_depth,false) AS valid_input
    FROM admission a CROSS JOIN traversal_stats t CROSS JOIN boundary_stats b
), expected_schema(column_name,data_type,ordinal_position) AS (
    VALUES ('categoryid','BIGINT',1),('parentid','BIGINT',2),('root_categoryid','BIGINT',3),('depth','BIGINT',4)
), dimension_columns AS (
    SELECT column_name,data_type,ordinal_position FROM information_schema.columns
    WHERE table_catalog=current_database() AND table_schema='rr_core' AND table_name='dim_category'
), schema_stats AS (
    SELECT COUNT(*) FILTER (WHERE e.column_name IS DISTINCT FROM d.column_name
        OR e.data_type IS DISTINCT FROM d.data_type) AS schema_mismatch_count
    FROM expected_schema e FULL OUTER JOIN dimension_columns d USING (ordinal_position)
), dimension_stats AS (
    SELECT COUNT(*) AS dimension_rows,COUNT(DISTINCT categoryid) AS distinct_categoryids,
        COUNT(*) FILTER (WHERE categoryid IS NULL OR root_categoryid IS NULL OR depth IS NULL) AS missing_required_rows,
        COUNT(categoryid)-COUNT(DISTINCT categoryid) AS duplicate_key_surplus,
        COUNT(*) FILTER (WHERE parentid IS NULL) AS null_parent_rows,
        COUNT(DISTINCT root_categoryid) AS distinct_root_ids,
        COUNT(*) FILTER (WHERE parentid IS NULL AND
            (categoryid IS DISTINCT FROM root_categoryid OR depth IS DISTINCT FROM 0)) AS root_identity_errors,
        COUNT(*) FILTER (WHERE depth<0) AS negative_depth_rows,MAX(depth) AS max_depth
    FROM rr_core.dim_category
), root_reference AS (
    SELECT COUNT(*) AS root_reference_errors FROM rr_core.dim_category d
    WHERE NOT EXISTS (
        SELECT 1 FROM rr_core.dim_category r WHERE r.categoryid=d.root_categoryid AND r.parentid IS NULL
    )
), parent_reference AS (
    SELECT COUNT(*) AS parent_mapping_errors FROM rr_core.dim_category d
    WHERE d.parentid IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM rr_core.dim_category p WHERE p.categoryid=d.parentid
    )
), parent_consistency AS (
    SELECT COUNT(*) AS parent_root_depth_errors FROM rr_core.dim_category d
    WHERE d.parentid IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM rr_core.dim_category p WHERE p.categoryid=d.parentid
            AND p.root_categoryid=d.root_categoryid
            AND d.depth::HUGEINT=p.depth::HUGEINT+1
    )
), source_only AS (
    SELECT categoryid,parentid FROM source_rows
    EXCEPT ALL SELECT categoryid,parentid FROM rr_core.dim_category
), dimension_only AS (
    SELECT categoryid,parentid FROM rr_core.dim_category
    EXCEPT ALL SELECT categoryid,parentid FROM source_rows
), expected_mapping_only AS (
    SELECT categoryid,parentid,root_categoryid,depth FROM rooted_walk
    EXCEPT ALL SELECT categoryid,parentid,root_categoryid,depth FROM rr_core.dim_category
), dimension_mapping_only AS (
    SELECT categoryid,parentid,root_categoryid,depth FROM rr_core.dim_category
    EXCEPT ALL SELECT categoryid,parentid,root_categoryid,depth FROM rooted_walk
), report AS (
    SELECT 1 AS check_order,'dimension_rows' AS check_name,d.dimension_rows AS actual,e.expected_rows AS expected FROM dimension_stats d CROSS JOIN expected_counts e
    UNION ALL SELECT 2,'column_count',COUNT(*),4 FROM dimension_columns
    UNION ALL SELECT 3,'schema_mismatch_count',schema_mismatch_count,0 FROM schema_stats
    UNION ALL SELECT 4,'distinct_categoryids',d.distinct_categoryids,e.expected_rows FROM dimension_stats d CROSS JOIN expected_counts e
    UNION ALL SELECT 5,'missing_required_rows',missing_required_rows,0 FROM dimension_stats
    UNION ALL SELECT 6,'duplicate_key_surplus',duplicate_key_surplus,0 FROM dimension_stats
    UNION ALL SELECT 7,'null_parent_rows',d.null_parent_rows,e.expected_roots FROM dimension_stats d CROSS JOIN expected_counts e
    UNION ALL SELECT 8,'distinct_root_ids',d.distinct_root_ids,e.expected_roots FROM dimension_stats d CROSS JOIN expected_counts e
    UNION ALL SELECT 9,'root_identity_errors',root_identity_errors,0 FROM dimension_stats
    UNION ALL SELECT 10,'root_reference_errors',root_reference_errors,0 FROM root_reference
    UNION ALL SELECT 11,'parent_mapping_errors',parent_mapping_errors,0 FROM parent_reference
    UNION ALL SELECT 12,'parent_root_depth_errors',parent_root_depth_errors,0 FROM parent_consistency
    UNION ALL SELECT 13,'negative_depth_rows',negative_depth_rows,0 FROM dimension_stats
    UNION ALL SELECT 14,'max_depth',d.max_depth,e.expected_max_depth FROM dimension_stats d CROSS JOIN expected_counts e
    UNION ALL SELECT 15,'source_only_rows',COUNT(*),0 FROM source_only
    UNION ALL SELECT 16,'dimension_only_rows',COUNT(*),0 FROM dimension_only
    UNION ALL SELECT 17,'expected_mapping_only_rows',COUNT(*),0 FROM expected_mapping_only
    UNION ALL SELECT 18,'dimension_mapping_only_rows',COUNT(*),0 FROM dimension_mapping_only
    UNION ALL SELECT 19,'source_contract_violations',CASE WHEN valid_input THEN 0 ELSE 1 END,0 FROM input_guard
    UNION ALL SELECT 20,'source_rows',source_rows,expected_rows FROM input_guard
)
SELECT check_order,check_name,actual::BIGINT AS actual,expected::BIGINT AS expected,
    CASE WHEN actual=expected THEN 'PASS' ELSE 'FAIL' END AS status
FROM report ORDER BY check_order;
