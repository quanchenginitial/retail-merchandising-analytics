-- Read-only audit. Run after the 14 basic checks in 04_import_sales.sql pass.
-- No persistent long table is created; raw values are never changed.
-- INCLUDE NULLS prevents missing cells from disappearing during inspection.
-- Integer syntax is checked before casting, so decimals cannot round into units.
-- Full JSON records preserve field names, text, NULLs and duplicate multiplicity.
-- Reconciliation compares the current CSV, not a recomputed historical hash.
WITH source_rows AS NOT MATERIALIZED (
    SELECT * FROM read_csv(
        'D:/database/m5-forecasting-accuracy/sales_train_evaluation.csv',
        header = true, all_varchar = true
    )
), raw_rows AS NOT MATERIALIZED (
    SELECT * FROM raw.m5_sales_wide
), source_records AS MATERIALIZED (
    SELECT to_json(source_rows)::VARCHAR AS full_record FROM source_rows
), table_records AS MATERIALIZED (
    SELECT to_json(raw_rows)::VARCHAR AS full_record FROM raw_rows
), source_only AS (
    SELECT full_record FROM source_records
    EXCEPT ALL
    SELECT full_record FROM table_records
), table_only AS (
    SELECT full_record FROM table_records
    EXCEPT ALL
    SELECT full_record FROM source_records
), sales_cells AS NOT MATERIALIZED (
    SELECT units_text
    FROM raw_rows
    UNPIVOT INCLUDE NULLS (
        units_text FOR day_id IN (COLUMNS('^d_[1-9][0-9]*$'))
    )
), typed_cells AS NOT MATERIALIZED (
    SELECT
        NULLIF(TRIM(units_text), '') IS NULL AS is_missing,
        CASE WHEN regexp_full_match(units_text, '-?[0-9]+')
             THEN TRY_CAST(units_text AS BIGINT) END AS units
    FROM sales_cells
), cell_stats AS (
    SELECT
        COUNT(*) AS daily_cells,
        COUNT(*) FILTER (WHERE is_missing) AS missing_sales_cells,
        COUNT(*) FILTER (WHERE NOT is_missing AND units IS NULL) AS invalid_integer_sales_cells,
        COUNT(*) FILTER (WHERE units < 0) AS negative_sales_cells,
        COUNT(units) AS valid_integer_sales_cells,
        COUNT(*) FILTER (WHERE units = 0) AS zero_sales_cells,
        COALESCE(SUM(units), 0) AS total_units,
        MAX(units) AS max_daily_units
    FROM typed_cells
), identifier_stats AS (
    SELECT COUNT(*) FILTER (
        WHERE id IS DISTINCT FROM item_id || '_' || store_id || '_evaluation'
    ) AS id_label_mismatches
    FROM raw_rows
), product_conflicts AS (
    SELECT item_id FROM raw_rows GROUP BY item_id
    HAVING COUNT(DISTINCT (dept_id, cat_id)) > 1
), store_conflicts AS (
    SELECT store_id FROM raw_rows GROUP BY store_id
    HAVING COUNT(DISTINCT state_id) > 1
), checks AS (
    SELECT 1 AS check_order, 'source_rows' AS check_name, COUNT(*) AS actual, 30490 AS expected FROM source_records
    UNION ALL SELECT 2, 'table_rows', COUNT(*), 30490 FROM table_records
    UNION ALL SELECT 3, 'daily_cells', daily_cells, 59181090 FROM cell_stats
    UNION ALL SELECT 4, 'missing_sales_cells', missing_sales_cells, 0 FROM cell_stats
    UNION ALL SELECT 5, 'invalid_integer_sales_cells', invalid_integer_sales_cells, 0 FROM cell_stats
    UNION ALL SELECT 6, 'negative_sales_cells', negative_sales_cells, 0 FROM cell_stats
    UNION ALL SELECT 7, 'valid_integer_sales_cells', valid_integer_sales_cells, 59181090 FROM cell_stats
    UNION ALL SELECT 8, 'zero_sales_cells', zero_sales_cells, 40241819 FROM cell_stats
    UNION ALL SELECT 9, 'total_units', total_units, 66927173 FROM cell_stats
    UNION ALL SELECT 10, 'max_daily_units', max_daily_units, 763 FROM cell_stats
    UNION ALL SELECT 11, 'id_label_mismatches', id_label_mismatches, 0 FROM identifier_stats
    UNION ALL SELECT 12, 'inconsistent_product_mapping_keys', COUNT(*), 0 FROM product_conflicts
    UNION ALL SELECT 13, 'inconsistent_store_mapping_keys', COUNT(*), 0 FROM store_conflicts
    UNION ALL SELECT 14, 'source_only_rows', COUNT(*), 0 FROM source_only
    UNION ALL SELECT 15, 'table_only_rows', COUNT(*), 0 FROM table_only
)
SELECT check_order, check_name, actual, expected,
       CASE WHEN actual = expected THEN 'PASS' ELSE 'FAIL' END AS status
FROM checks ORDER BY check_order;
