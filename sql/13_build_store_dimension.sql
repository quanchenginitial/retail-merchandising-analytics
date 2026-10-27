-- Purpose: one source store/state mapping per store for later regional analysis.
-- Run once after product-dimension acceptance. Source tables stay unchanged.
-- Uniqueness is checked here; this CTAS does not declare a physical PRIMARY KEY.
CREATE SCHEMA IF NOT EXISTS core;

CREATE TABLE core.m5_store AS
WITH source_stores AS MATERIALIZED (
    SELECT DISTINCT store_id,state_id FROM raw.m5_sales_wide
), invalid_values AS (
    SELECT * FROM source_stores
    WHERE NULLIF(TRIM(store_id),'') IS NULL OR NULLIF(TRIM(state_id),'') IS NULL
), store_conflicts AS (
    SELECT store_id FROM source_stores GROUP BY store_id HAVING COUNT(*)>1
)
SELECT CASE WHEN NOT EXISTS (SELECT 1 FROM invalid_values)
                  AND NOT EXISTS (SELECT 1 FROM store_conflicts)
            THEN store_id ELSE error('Store mapping must have nonblank codes and exactly one state per store')
       END AS store_id,
       state_id
FROM source_stores;

-- VALIDATION: if core.m5_store already exists, run only the query below.
WITH expected_schema(column_name,data_type,ordinal_position) AS (
    VALUES ('store_id','VARCHAR',1),('state_id','VARCHAR',2)
), actual_schema AS (
    SELECT column_name,data_type,ordinal_position FROM information_schema.columns
    WHERE table_catalog=current_database() AND table_schema='core' AND table_name='m5_store'
), schema_errors AS (
    SELECT COUNT(*) AS error_count
    FROM expected_schema e FULL OUTER JOIN actual_schema a USING (column_name)
    WHERE e.column_name IS NULL OR a.column_name IS NULL
       OR e.data_type IS DISTINCT FROM a.data_type
       OR e.ordinal_position IS DISTINCT FROM a.ordinal_position
), source_stores AS MATERIALIZED (
    SELECT DISTINCT store_id,state_id FROM raw.m5_sales_wide
), source_quality AS (
    SELECT COUNT(*) FILTER (WHERE NULLIF(TRIM(store_id),'') IS NULL
        OR NULLIF(TRIM(state_id),'') IS NULL) AS missing_rows FROM raw.m5_sales_wide
), source_store_conflicts AS (
    SELECT store_id FROM source_stores GROUP BY store_id HAVING COUNT(*)>1
), dimension_stats AS (
    SELECT COUNT(*) AS store_rows,COUNT(DISTINCT store_id) AS distinct_stores,
        COUNT(*)-COUNT(DISTINCT store_id) AS duplicate_or_null_store_rows,
        COUNT(*) FILTER (WHERE NULLIF(TRIM(store_id),'') IS NULL
            OR NULLIF(TRIM(state_id),'') IS NULL) AS missing_rows,
        COUNT(DISTINCT state_id) AS distinct_states FROM core.m5_store
), raw_only AS (
    SELECT store_id,state_id FROM source_stores
    EXCEPT ALL SELECT store_id,state_id FROM core.m5_store
), dimension_only AS (
    SELECT store_id,state_id FROM core.m5_store
    EXCEPT ALL SELECT store_id,state_id FROM source_stores
), source_keys AS (
    SELECT DISTINCT store_id FROM source_stores
), key_join_errors AS (
    SELECT s.store_id FROM source_keys s LEFT JOIN core.m5_store d ON s.store_id=d.store_id
    GROUP BY s.store_id HAVING COUNT(d.store_id)<>1
), expected_state_counts(state_id,store_count) AS (
    VALUES ('CA',4),('TX',3),('WI',3)
), actual_state_counts AS (
    SELECT state_id,COUNT(*) AS store_count FROM core.m5_store GROUP BY state_id
), state_count_errors AS (
    SELECT COUNT(*) AS error_count
    FROM expected_state_counts e FULL OUTER JOIN actual_state_counts a ON e.state_id=a.state_id
    WHERE e.state_id IS NULL OR a.state_id IS NULL OR e.store_count IS DISTINCT FROM a.store_count
), checks AS (
    SELECT 1 AS check_order,'store_rows' AS check_name,store_rows::VARCHAR AS actual,'10' AS expected FROM dimension_stats
    UNION ALL SELECT 2,'column_count',COUNT(*)::VARCHAR,'2' FROM actual_schema
    UNION ALL SELECT 3,'schema_mismatch_count',error_count::VARCHAR,'0' FROM schema_errors
    UNION ALL SELECT 4,'distinct_stores',distinct_stores::VARCHAR,'10' FROM dimension_stats
    UNION ALL SELECT 5,'duplicate_or_null_store_rows',duplicate_or_null_store_rows::VARCHAR,'0' FROM dimension_stats
    UNION ALL SELECT 6,'missing_required_rows',missing_rows::VARCHAR,'0' FROM dimension_stats
    UNION ALL SELECT 7,'distinct_states',distinct_states::VARCHAR,'3' FROM dimension_stats
    UNION ALL SELECT 8,'raw_missing_required_rows',missing_rows::VARCHAR,'0' FROM source_quality
    UNION ALL SELECT 9,'raw_store_mapping_conflicts',COUNT(*)::VARCHAR,'0' FROM source_store_conflicts
    UNION ALL SELECT 10,'raw_only_store_rows',COUNT(*)::VARCHAR,'0' FROM raw_only
    UNION ALL SELECT 11,'dimension_only_store_rows',COUNT(*)::VARCHAR,'0' FROM dimension_only
    UNION ALL SELECT 12,'source_key_join_errors',COUNT(*)::VARCHAR,'0' FROM key_join_errors
    UNION ALL SELECT 13,'state_store_count_mismatches',error_count::VARCHAR,'0' FROM state_count_errors
)
SELECT check_order,check_name,actual,expected,
    CASE WHEN actual=expected THEN 'PASS' ELSE 'FAIL' END AS status
FROM checks ORDER BY check_order;
