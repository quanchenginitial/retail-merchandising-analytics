-- Read-only, bounded hierarchy audit of the accepted typed reference.
-- Root depth is zero. Cycle-affected nodes include feeders, not just cycle members.
-- No category IDs, paths or inferred mappings are returned.
WITH RECURSIVE expected_counts AS (
    SELECT 1669::BIGINT AS expected_rows,25::BIGINT AS expected_roots
), schema_stats AS (
    SELECT COUNT(*) AS column_count,
        CASE WHEN COUNT(*)=2 AND COUNT(*) FILTER (WHERE data_type='BIGINT')=2
            AND COUNT(*) FILTER (WHERE column_name IS DISTINCT FROM
                CASE ordinal_position WHEN 1 THEN 'categoryid' WHEN 2 THEN 'parentid' END)=0
            THEN 0 ELSE 1 END AS schema_mismatch
    FROM information_schema.columns
    WHERE table_catalog=current_database() AND table_schema='rr_stg' AND table_name='category_tree'
), source_rows AS MATERIALIZED (
    SELECT categoryid,parentid FROM rr_stg.category_tree
), source_health AS (
    SELECT COUNT(*) AS category_rows,COUNT(DISTINCT categoryid) AS distinct_categoryids,
        COUNT(*) FILTER (WHERE categoryid IS NULL) AS missing_categoryids,
        COUNT(categoryid)-COUNT(DISTINCT categoryid) AS duplicate_key_surplus,
        COUNT(*) FILTER (WHERE categoryid<0 OR parentid<0) AS negative_identifier_rows,
        COUNT(*) FILTER (WHERE parentid IS NULL) AS root_nodes,
        COUNT(*) FILTER (WHERE categoryid=parentid) AS self_parent_rows
    FROM source_rows
), source_orphans AS (
    SELECT COUNT(*) AS orphan_parent_rows FROM source_rows child
    WHERE child.parentid IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM source_rows parent WHERE parent.categoryid=child.parentid
    )
), admission AS MATERIALIZED (
    SELECT s.*,h.*,o.*,e.*,
        s.schema_mismatch=0 AND h.category_rows=e.expected_rows AND h.category_rows>0
            AND h.missing_categoryids=0 AND h.duplicate_key_surplus=0
            AND h.negative_identifier_rows=0 AND o.orphan_parent_rows=0 AS admitted
    FROM schema_stats s CROSS JOIN source_health h CROSS JOIN source_orphans o
        CROSS JOIN expected_counts e
), nodes AS MATERIALIZED (
    SELECT r.categoryid,r.parentid FROM source_rows r CROSS JOIN admission a WHERE a.admitted
), rooted_walk(categoryid,depth) AS (
    SELECT categoryid,0::BIGINT AS depth FROM nodes WHERE parentid IS NULL
    UNION ALL
    SELECT child.categoryid,parent.depth+1
    FROM rooted_walk parent JOIN nodes child ON child.parentid=parent.categoryid
        CROSS JOIN admission a
    WHERE parent.depth<a.category_rows-1
), traversal_stats AS (
    SELECT COUNT(DISTINCT categoryid) AS root_reachable_nodes,
        COUNT(*)-COUNT(DISTINCT categoryid) AS repeated_traversal_rows,
        MAX(depth) AS max_root_depth
    FROM rooted_walk
), boundary_stats AS (
    SELECT COUNT(*) AS depth_limit_child_edges
    FROM rooted_walk parent JOIN nodes child ON child.parentid=parent.categoryid
        CROSS JOIN admission a
    WHERE parent.depth=a.category_rows-1
), child_counts AS (
    SELECT parent.categoryid,COUNT(child.categoryid) AS direct_children
    FROM nodes parent LEFT JOIN nodes child ON child.parentid=parent.categoryid
    GROUP BY parent.categoryid
), shape_stats AS (
    SELECT COUNT(*) FILTER (WHERE direct_children=0) AS leaf_nodes,
        COUNT(*) FILTER (WHERE direct_children>1) AS branching_nodes,
        COALESCE(MAX(direct_children),0) AS max_children_per_node
    FROM child_counts
), metrics AS MATERIALIZED (
    SELECT a.*,t.*,b.*,s.*,
        a.admitted AND t.repeated_traversal_rows=0 AND b.depth_limit_child_edges=0 AS cycle_inference_valid,
        a.admitted AND a.root_nodes=a.expected_roots AND a.self_parent_rows=0
            AND t.root_reachable_nodes=a.category_rows AND t.repeated_traversal_rows=0
            AND b.depth_limit_child_edges=0 AS hierarchy_valid
    FROM admission a CROSS JOIN traversal_stats t CROSS JOIN boundary_stats b CROSS JOIN shape_stats s
), report AS (
    SELECT 1 AS check_order,'category_rows' AS check_name,category_rows AS actual,expected_rows AS expected FROM metrics
    UNION ALL SELECT 2,'column_count',column_count,2 FROM metrics
    UNION ALL SELECT 3,'schema_mismatch',schema_mismatch,0 FROM metrics
    UNION ALL SELECT 4,'distinct_categoryids',distinct_categoryids,expected_rows FROM metrics
    UNION ALL SELECT 5,'missing_categoryids',missing_categoryids,0 FROM metrics
    UNION ALL SELECT 6,'duplicate_key_surplus',duplicate_key_surplus,0 FROM metrics
    UNION ALL SELECT 7,'negative_identifier_rows',negative_identifier_rows,0 FROM metrics
    UNION ALL SELECT 8,'root_nodes',root_nodes,expected_roots FROM metrics
    UNION ALL SELECT 9,'self_parent_rows',self_parent_rows,0 FROM metrics
    UNION ALL SELECT 10,'orphan_parent_rows',orphan_parent_rows,0 FROM metrics
    UNION ALL SELECT 11,'root_reachable_nodes',CASE WHEN admitted THEN root_reachable_nodes END,expected_rows FROM metrics
    UNION ALL SELECT 12,'cycle_affected_nodes',CASE WHEN cycle_inference_valid THEN category_rows-root_reachable_nodes END,0 FROM metrics
    UNION ALL SELECT 13,'repeated_traversal_rows',CASE WHEN admitted THEN repeated_traversal_rows END,0 FROM metrics
    UNION ALL SELECT 14,'depth_limit_child_edges',CASE WHEN admitted THEN depth_limit_child_edges END,0 FROM metrics
    UNION ALL SELECT 15,'max_root_depth',CASE WHEN hierarchy_valid THEN max_root_depth END,NULL::BIGINT FROM metrics
    UNION ALL SELECT 16,'leaf_nodes',CASE WHEN hierarchy_valid THEN leaf_nodes END,NULL::BIGINT FROM metrics
    UNION ALL SELECT 17,'branching_nodes',CASE WHEN hierarchy_valid THEN branching_nodes END,NULL::BIGINT FROM metrics
    UNION ALL SELECT 18,'max_children_per_node',CASE WHEN hierarchy_valid THEN max_children_per_node END,NULL::BIGINT FROM metrics
)
SELECT check_order,check_name,actual::BIGINT AS actual,expected::BIGINT AS expected,
    CASE WHEN actual IS NULL THEN 'BLOCKED'
         WHEN expected IS NULL THEN 'INFO'
         WHEN actual=expected THEN 'PASS' ELSE 'FAIL' END AS status
FROM report ORDER BY check_order;
