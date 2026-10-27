-- Purpose: one product row with its source department/category codes,
-- supporting later category rollups without multiplying daily sales rows.
-- Run once after sales staging reconciliation passes. Source tables stay unchanged.
-- This CTAS validates key uniqueness; it does not declare a physical PRIMARY KEY.
CREATE SCHEMA IF NOT EXISTS core;

CREATE TABLE core.m5_product AS
WITH source_products AS MATERIALIZED (
    SELECT DISTINCT item_id,dept_id,cat_id FROM raw.m5_sales_wide
), invalid_values AS (
    SELECT * FROM source_products
    WHERE NULLIF(TRIM(item_id),'') IS NULL OR NULLIF(TRIM(dept_id),'') IS NULL
       OR NULLIF(TRIM(cat_id),'') IS NULL
), item_conflicts AS (
    SELECT item_id FROM source_products GROUP BY item_id HAVING COUNT(*)>1
), department_conflicts AS (
    SELECT dept_id FROM source_products GROUP BY dept_id HAVING COUNT(DISTINCT cat_id)>1
)
SELECT CASE WHEN NOT EXISTS (SELECT 1 FROM invalid_values)
                  AND NOT EXISTS (SELECT 1 FROM item_conflicts)
                  AND NOT EXISTS (SELECT 1 FROM department_conflicts)
            THEN item_id ELSE error('Product mapping must have nonblank codes, one department/category per item and one category per department')
       END AS item_id,
       dept_id,cat_id
FROM source_products;

-- VALIDATION: if core.m5_product already exists, run only the query below.
WITH expected_schema(column_name,data_type,ordinal_position) AS (
    VALUES ('item_id','VARCHAR',1),('dept_id','VARCHAR',2),('cat_id','VARCHAR',3)
), actual_schema AS (
    SELECT column_name,data_type,ordinal_position FROM information_schema.columns
    WHERE table_catalog=current_database() AND table_schema='core' AND table_name='m5_product'
), schema_errors AS (
    SELECT COUNT(*) AS error_count
    FROM expected_schema e FULL OUTER JOIN actual_schema a USING (column_name)
    WHERE e.column_name IS NULL OR a.column_name IS NULL
       OR e.data_type IS DISTINCT FROM a.data_type
       OR e.ordinal_position IS DISTINCT FROM a.ordinal_position
), source_products AS MATERIALIZED (
    SELECT DISTINCT item_id,dept_id,cat_id FROM raw.m5_sales_wide
), source_quality AS (
    SELECT COUNT(*) FILTER (WHERE NULLIF(TRIM(item_id),'') IS NULL
        OR NULLIF(TRIM(dept_id),'') IS NULL OR NULLIF(TRIM(cat_id),'') IS NULL) AS missing_rows
    FROM raw.m5_sales_wide
), source_item_conflicts AS (
    SELECT item_id FROM source_products GROUP BY item_id HAVING COUNT(*)>1
), source_department_conflicts AS (
    SELECT dept_id FROM source_products GROUP BY dept_id HAVING COUNT(DISTINCT cat_id)>1
), dimension_department_conflicts AS (
    SELECT dept_id FROM core.m5_product GROUP BY dept_id HAVING COUNT(DISTINCT cat_id)>1
), dimension_stats AS (
    SELECT COUNT(*) AS product_rows,COUNT(DISTINCT item_id) AS distinct_items,
        COUNT(*)-COUNT(DISTINCT item_id) AS duplicate_or_null_item_rows,
        COUNT(*) FILTER (WHERE NULLIF(TRIM(item_id),'') IS NULL
            OR NULLIF(TRIM(dept_id),'') IS NULL OR NULLIF(TRIM(cat_id),'') IS NULL) AS missing_rows,
        COUNT(DISTINCT dept_id) AS distinct_departments,COUNT(DISTINCT cat_id) AS distinct_categories
    FROM core.m5_product
), raw_only AS (
    SELECT item_id,dept_id,cat_id FROM source_products
    EXCEPT ALL SELECT item_id,dept_id,cat_id FROM core.m5_product
), dimension_only AS (
    SELECT item_id,dept_id,cat_id FROM core.m5_product
    EXCEPT ALL SELECT item_id,dept_id,cat_id FROM source_products
), source_keys AS (
    SELECT DISTINCT item_id FROM source_products
), key_join_errors AS (
    SELECT s.item_id FROM source_keys s LEFT JOIN core.m5_product p ON s.item_id=p.item_id
    GROUP BY s.item_id HAVING COUNT(p.item_id)<>1
), checks AS (
    SELECT 1 AS check_order,'product_rows' AS check_name,product_rows::VARCHAR AS actual,'3049' AS expected FROM dimension_stats
    UNION ALL SELECT 2,'column_count',COUNT(*)::VARCHAR,'3' FROM actual_schema
    UNION ALL SELECT 3,'schema_mismatch_count',error_count::VARCHAR,'0' FROM schema_errors
    UNION ALL SELECT 4,'distinct_items',distinct_items::VARCHAR,'3049' FROM dimension_stats
    UNION ALL SELECT 5,'duplicate_or_null_item_rows',duplicate_or_null_item_rows::VARCHAR,'0' FROM dimension_stats
    UNION ALL SELECT 6,'missing_required_rows',missing_rows::VARCHAR,'0' FROM dimension_stats
    UNION ALL SELECT 7,'distinct_departments',distinct_departments::VARCHAR,'7' FROM dimension_stats
    UNION ALL SELECT 8,'distinct_categories',distinct_categories::VARCHAR,'3' FROM dimension_stats
    UNION ALL SELECT 9,'raw_missing_required_rows',missing_rows::VARCHAR,'0' FROM source_quality
    UNION ALL SELECT 10,'raw_item_mapping_conflicts',COUNT(*)::VARCHAR,'0' FROM source_item_conflicts
    UNION ALL SELECT 11,'raw_department_mapping_conflicts',COUNT(*)::VARCHAR,'0' FROM source_department_conflicts
    UNION ALL SELECT 12,'dimension_department_conflicts',COUNT(*)::VARCHAR,'0' FROM dimension_department_conflicts
    UNION ALL SELECT 13,'raw_only_product_rows',COUNT(*)::VARCHAR,'0' FROM raw_only
    UNION ALL SELECT 14,'dimension_only_product_rows',COUNT(*)::VARCHAR,'0' FROM dimension_only
    UNION ALL SELECT 15,'source_key_join_errors',COUNT(*)::VARCHAR,'0' FROM key_join_errors
)
SELECT check_order,check_name,actual,expected,
    CASE WHEN actual=expected THEN 'PASS' ELSE 'FAIL' END AS status
FROM checks ORDER BY check_order;
