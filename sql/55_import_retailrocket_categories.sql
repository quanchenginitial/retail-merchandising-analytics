-- Run once in the existing retail_merchandising DBeaver connection.
-- Small, separate Retailrocket reference; no events, properties or M5 are joined.
-- Both fields remain VARCHAR; only exact-empty parentid becomes NULL.
-- Existing rr_raw.category_tree is never replaced or appended to.
CREATE SCHEMA IF NOT EXISTS rr_raw;

CREATE TABLE rr_raw.category_tree AS
SELECT categoryid,parentid
FROM read_csv(
    'D:/database/retailrocket/category_tree.csv',
    header=true, auto_detect=false,
    columns={'categoryid':'VARCHAR','parentid':'VARCHAR'},
    delim=',', quote='"', escape='"', encoding='utf-8',
    nullstr='', force_not_null=['categoryid'],
    strict_mode=true, ignore_errors=false, null_padding=false
);

-- CHECKS: if the table already exists, run only the query below.
-- NULL parents are root candidates. No recursive hierarchy validation is done.
WITH expected_counts AS (
    SELECT 1669 AS expected_rows,1669 AS expected_categories,25 AS expected_null_parents
), source_rows AS MATERIALIZED (
    SELECT categoryid,parentid
    FROM read_csv(
        'D:/database/retailrocket/category_tree.csv',
        header=true, auto_detect=false,
        columns={'categoryid':'VARCHAR','parentid':'VARCHAR'},
        delim=',', quote='"', escape='"', encoding='utf-8',
        nullstr='', force_not_null=['categoryid'],
        strict_mode=true, ignore_errors=false, null_padding=false
    )
), column_stats AS (
    SELECT COUNT(*) AS columns,COUNT(*) FILTER (WHERE data_type='VARCHAR') AS varchar_columns,
        COUNT(*) FILTER (WHERE column_name IS DISTINCT FROM
            CASE ordinal_position WHEN 1 THEN 'categoryid' WHEN 2 THEN 'parentid' END) AS sequence_errors
    FROM information_schema.columns
    WHERE table_catalog=current_database() AND table_schema='rr_raw' AND table_name='category_tree'
), row_stats AS (
    SELECT COUNT(*) AS rows,
        COUNT(*) FILTER (WHERE categoryid IS NULL OR categoryid='') AS missing_categoryid,
        COUNT(*) FILTER (WHERE categoryid IS NOT NULL AND
            (NOT regexp_full_match(categoryid,'[0-9]+') OR TRY_CAST(categoryid AS BIGINT) IS NULL)) AS invalid_categoryid,
        COUNT(*) FILTER (WHERE parentid IS NOT NULL AND
            (NOT regexp_full_match(parentid,'[0-9]+') OR TRY_CAST(parentid AS BIGINT) IS NULL)) AS invalid_parentid,
        COUNT(DISTINCT categoryid) AS categories,
        COUNT(*) FILTER (WHERE parentid IS NULL) AS null_parents,
        COUNT(*)-COUNT(DISTINCT categoryid) AS duplicate_categoryid_surplus,
        COUNT(*) FILTER (WHERE categoryid=parentid) AS self_parents,
        COUNT(*)-COUNT(DISTINCT (categoryid,parentid)) AS duplicate_surplus
    FROM rr_raw.category_tree
), parent_stats AS (
    SELECT COUNT(*) AS orphan_parents
    FROM rr_raw.category_tree child
    WHERE child.parentid IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM rr_raw.category_tree parent WHERE parent.categoryid=child.parentid
    )
), source_stats AS (
    SELECT COUNT(*)-COUNT(DISTINCT (categoryid,parentid)) AS duplicate_surplus FROM source_rows
), source_only AS (
    SELECT categoryid,parentid FROM source_rows
    EXCEPT ALL SELECT categoryid,parentid FROM rr_raw.category_tree
), table_only AS (
    SELECT categoryid,parentid FROM rr_raw.category_tree
    EXCEPT ALL SELECT categoryid,parentid FROM source_rows
), checks AS (
    SELECT 1 AS check_order,'row_count' AS check_name,r.rows AS actual,e.expected_rows AS expected FROM row_stats r CROSS JOIN expected_counts e
    UNION ALL SELECT 2,'column_count',columns,2 FROM column_stats
    UNION ALL SELECT 3,'varchar_column_count',varchar_columns,2 FROM column_stats
    UNION ALL SELECT 4,'column_sequence_errors',sequence_errors,0 FROM column_stats
    UNION ALL SELECT 5,'missing_categoryid_rows',missing_categoryid,0 FROM row_stats
    UNION ALL SELECT 6,'invalid_categoryid_rows',invalid_categoryid,0 FROM row_stats
    UNION ALL SELECT 7,'invalid_parentid_rows',invalid_parentid,0 FROM row_stats
    UNION ALL SELECT 8,'distinct_categoryids',r.categories,e.expected_categories FROM row_stats r CROSS JOIN expected_counts e
    UNION ALL SELECT 9,'null_parentid_rows',r.null_parents,e.expected_null_parents FROM row_stats r CROSS JOIN expected_counts e
    UNION ALL SELECT 10,'duplicate_categoryid_surplus_rows',duplicate_categoryid_surplus,0 FROM row_stats
    UNION ALL SELECT 11,'self_parent_rows',self_parents,0 FROM row_stats
    UNION ALL SELECT 12,'orphan_parent_rows',orphan_parents,0 FROM parent_stats
    UNION ALL SELECT 13,'source_rows_absent_from_table',COUNT(*),0 FROM source_only
    UNION ALL SELECT 14,'table_rows_absent_from_source',COUNT(*),0 FROM table_only
    UNION ALL SELECT 15,'duplicate_surplus_rows_preserved',r.duplicate_surplus,s.duplicate_surplus FROM row_stats r CROSS JOIN source_stats s
)
SELECT check_order,check_name,actual,expected,
    CASE WHEN actual=expected THEN 'PASS' ELSE 'FAIL' END AS status
FROM checks ORDER BY check_order;
