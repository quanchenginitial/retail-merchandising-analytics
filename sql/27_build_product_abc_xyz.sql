-- Purpose: combine contribution (90-day ABC) with variability (84-day XYZ) per product.
-- ABC: 2016-01-26..2016-04-24; XYZ: 2016-01-30..2016-04-22. Both pool all 10 stores.
-- Preserve both windows and all source fields; do not equate their zero-sales populations.
-- The six-day bridge is the difference of accepted snapshots, independently source-tested in preflight.
-- This step reports the count matrix; it does not infer inventory levels or prescribe replenishment.
-- First run: execute the complete file. Existing tables are never overwritten.
CREATE SCHEMA IF NOT EXISTS mart;
CREATE TABLE mart.m5_product_abc_xyz AS
WITH parameters AS (
    SELECT 3049 AS expected_items,10 AS expected_stores,12 AS expected_weeks,
        DATE '2016-01-30' AS start_date,DATE '2016-04-22' AS end_date,
        1e-9::DOUBLE AS absolute_tolerance,1e-9::DOUBLE AS relative_tolerance
), source_schema(column_name,data_type,ordinal_position) AS (
    VALUES ('item_id','VARCHAR',1),('dept_id','VARCHAR',2),('cat_id','VARCHAR',3),('wm_yr_wk','INTEGER',4),
        ('week_start','DATE',5),('week_end','DATE',6),('units','HUGEINT',7),('source_daily_rows','BIGINT',8)
), actual_source_schema AS (
    SELECT column_name,data_type,ordinal_position FROM information_schema.columns
    WHERE table_catalog=current_database() AND table_schema='mart' AND table_name='m5_product_weekly_12w'
), source_schema_errors AS (
    SELECT COUNT(*) AS errors FROM source_schema e FULL OUTER JOIN actual_source_schema a USING (column_name)
    WHERE e.column_name IS NULL OR a.column_name IS NULL OR e.data_type IS DISTINCT FROM a.data_type
        OR e.ordinal_position IS DISTINCT FROM a.ordinal_position
), department_mapping(dept_id,cat_id) AS (
    VALUES ('FOODS_1','FOODS'),('FOODS_2','FOODS'),('FOODS_3','FOODS'),
        ('HOUSEHOLD_1','HOUSEHOLD'),('HOUSEHOLD_2','HOUSEHOLD'),('HOBBIES_1','HOBBIES'),('HOBBIES_2','HOBBIES')
), product_health AS (
    SELECT COUNT(*) AS rows,COUNT(DISTINCT p.item_id) AS items,
        COUNT(*) FILTER (WHERE NULLIF(TRIM(p.item_id),'') IS NULL OR m.dept_id IS NULL) AS invalid_rows
    FROM core.m5_product p LEFT JOIN department_mapping m ON p.dept_id=m.dept_id AND p.cat_id=m.cat_id
), weekly AS MATERIALIZED (
    SELECT w.*,CAST(date_diff('day',cfg.start_date,w.week_start)//7+1 AS INTEGER) AS week_index
    FROM mart.m5_product_weekly_12w w CROSS JOIN parameters cfg
), source_health AS (
    SELECT COUNT(*) AS rows,COUNT(DISTINCT item_id) AS items,
        COUNT(*) FILTER (WHERE NULLIF(TRIM(item_id),'') IS NULL OR units IS NULL OR units<0
            OR wm_yr_wk IS NULL OR wm_yr_wk NOT BETWEEN 11601 AND 11612
            OR week_start IS DISTINCT FROM cfg.start_date+7*(wm_yr_wk-11601)
            OR week_end IS DISTINCT FROM cfg.start_date+7*(wm_yr_wk-11601)+6
            OR source_daily_rows IS DISTINCT FROM 7*cfg.expected_stores) AS invalid_rows
    FROM weekly CROSS JOIN parameters cfg
), item_coverage AS (
    SELECT item_id,COUNT(*) AS rows,COUNT(DISTINCT wm_yr_wk) AS weeks FROM weekly GROUP BY item_id
), joined AS MATERIALIZED (
    SELECT w.*,p.item_id AS matched_item,p.dept_id AS matched_department,p.cat_id AS matched_category
    FROM weekly w LEFT JOIN core.m5_product p USING (item_id)
), join_health AS (
    SELECT COUNT(*) AS rows,
        COUNT(*) FILTER (WHERE matched_item IS NULL OR dept_id IS DISTINCT FROM matched_department
            OR cat_id IS DISTINCT FROM matched_category) AS invalid_rows FROM joined
), stats AS MATERIALIZED (
    SELECT item_id,dept_id,cat_id,MIN(week_start) AS window_start,MAX(week_end) AS window_end,
        COUNT(*) AS week_count,SUM(units) AS units,
        AVG(CAST(units AS DOUBLE)) AS mean_weekly_units,STDDEV_POP(CAST(units AS DOUBLE)) AS stddev_weekly_units,
        COUNT(*) FILTER (WHERE units=0) AS zero_sales_weeks,COUNT(*) FILTER (WHERE units>0) AS positive_weeks,
        MIN(week_index) FILTER (WHERE units>0) AS first_positive_week,
        MAX(week_index) FILTER (WHERE units>0) AS last_positive_week
    FROM joined GROUP BY item_id,dept_id,cat_id
), expected AS MATERIALIZED (
    SELECT item_id,dept_id,cat_id,window_start,window_end,week_count,units,mean_weekly_units,stddev_weekly_units,
        CASE WHEN mean_weekly_units=0 THEN NULL ELSE stddev_weekly_units/mean_weekly_units END AS cv_weekly,
        zero_sales_weeks,CAST(zero_sales_weeks AS DOUBLE)/week_count AS zero_week_share,positive_weeks,
        CASE WHEN positive_weeks<2 THEN NULL
             ELSE CAST(last_positive_week-first_positive_week AS DOUBLE)/(positive_weeks-1) END AS mean_positive_gap_weeks
    FROM stats
), computed_health AS (
    SELECT COUNT(*) AS rows,
        COUNT(*) FILTER (WHERE NOT isfinite(mean_weekly_units) OR NOT isfinite(stddev_weekly_units)
            OR mean_weekly_units<0 OR stddev_weekly_units<0 OR NOT isfinite(zero_week_share)
            OR zero_week_share<0 OR zero_week_share>1
            OR (cv_weekly IS NOT NULL AND (NOT isfinite(cv_weekly) OR cv_weekly<0))
            OR (mean_positive_gap_weeks IS NOT NULL AND
                (NOT isfinite(mean_positive_gap_weeks) OR mean_positive_gap_weeks<1 OR mean_positive_gap_weeks>11))) AS invalid_rows
    FROM expected
), health AS (
    SELECT ph.rows=cfg.expected_items AND ph.items=cfg.expected_items AND ph.invalid_rows=0
        AND se.errors=0 AND (SELECT COUNT(*) FROM actual_source_schema)=8
        AND sh.rows=cfg.expected_items*cfg.expected_weeks AND sh.items=cfg.expected_items AND sh.invalid_rows=0
        AND NOT EXISTS (SELECT 1 FROM item_coverage WHERE rows<>cfg.expected_weeks OR weeks<>cfg.expected_weeks)
        AND jh.rows=sh.rows AND jh.invalid_rows=0 AND ch.rows=cfg.expected_items AND ch.invalid_rows=0 AS passed
    FROM parameters cfg CROSS JOIN product_health ph CROSS JOIN source_schema_errors se
    CROSS JOIN source_health sh CROSS JOIN join_health jh CROSS JOIN computed_health ch
), expected_schema(column_name,data_type,ordinal_position) AS (
    VALUES ('item_id','VARCHAR',1),('dept_id','VARCHAR',2),('cat_id','VARCHAR',3),
        ('window_start','DATE',4),('window_end','DATE',5),('week_count','BIGINT',6),('units','HUGEINT',7),
        ('mean_weekly_units','DOUBLE',8),('stddev_weekly_units','DOUBLE',9),('cv_weekly','DOUBLE',10),
        ('zero_sales_weeks','BIGINT',11),('zero_week_share','DOUBLE',12),('positive_weeks','BIGINT',13),
        ('mean_positive_gap_weeks','DOUBLE',14)
), actual_schema AS (
    SELECT column_name,data_type,ordinal_position FROM information_schema.columns
    WHERE table_catalog=current_database() AND table_schema='mart' AND table_name='m5_product_variability_12w'
), schema_errors AS (
    SELECT COUNT(*) AS errors FROM expected_schema e FULL OUTER JOIN actual_schema a USING (column_name)
    WHERE e.column_name IS NULL OR a.column_name IS NULL OR e.data_type IS DISTINCT FROM a.data_type
        OR e.ordinal_position IS DISTINCT FROM a.ordinal_position
), actual AS MATERIALIZED (
    SELECT item_id,dept_id,cat_id,window_start,window_end,week_count,units,mean_weekly_units,stddev_weekly_units,
        cv_weekly,zero_sales_weeks,zero_week_share,positive_weeks,mean_positive_gap_weeks
    FROM mart.m5_product_variability_12w
), exact_expected_only AS (
    SELECT item_id,dept_id,cat_id,window_start,window_end,week_count,units,zero_sales_weeks,positive_weeks FROM expected
    EXCEPT ALL
    SELECT item_id,dept_id,cat_id,window_start,window_end,week_count,units,zero_sales_weeks,positive_weeks FROM actual
), exact_actual_only AS (
    SELECT item_id,dept_id,cat_id,window_start,window_end,week_count,units,zero_sales_weeks,positive_weeks FROM actual
    EXCEPT ALL
    SELECT item_id,dept_id,cat_id,window_start,window_end,week_count,units,zero_sales_weeks,positive_weeks FROM expected
), float_errors AS (
    SELECT COUNT(*) AS errors FROM actual a JOIN expected e USING (item_id) CROSS JOIN parameters cfg
    CROSS JOIN LATERAL (VALUES (a.mean_weekly_units,e.mean_weekly_units),(a.stddev_weekly_units,e.stddev_weekly_units),
        (a.cv_weekly,e.cv_weekly),(a.zero_week_share,e.zero_week_share),(a.mean_positive_gap_weeks,e.mean_positive_gap_weeks)
    ) v(actual_value,expected_value)
    WHERE CASE WHEN v.expected_value IS NULL THEN v.actual_value IS NOT NULL
               WHEN v.actual_value IS NULL OR NOT isfinite(v.actual_value) OR NOT isfinite(v.expected_value) THEN true
               ELSE abs(v.actual_value-v.expected_value)>cfg.absolute_tolerance+cfg.relative_tolerance*abs(v.expected_value) END
), actual_health AS (
    SELECT COUNT(*) AS rows,COUNT(DISTINCT item_id) AS items,
        COUNT(*) FILTER (WHERE mean_weekly_units<0 OR stddev_weekly_units<0 OR cv_weekly<0
            OR zero_week_share<0 OR zero_week_share>1
            OR (mean_positive_gap_weeks IS NOT NULL AND (mean_positive_gap_weeks<1 OR mean_positive_gap_weeks>11))) AS range_errors
    FROM actual
), validation_health AS (
    SELECT h.passed AND se.errors=0 AND (SELECT COUNT(*) FROM actual_schema)=14
        AND ah.rows=cfg.expected_items AND ah.items=cfg.expected_items AND ah.range_errors=0 AND fe.errors=0
        AND NOT EXISTS (SELECT 1 FROM exact_expected_only) AND NOT EXISTS (SELECT 1 FROM exact_actual_only) AS passed
    FROM health h CROSS JOIN schema_errors se CROSS JOIN parameters cfg CROSS JOIN actual_health ah CROSS JOIN float_errors fe
)
, bounded_weekly AS MATERIALIZED (
    -- Upstream daily units are INTEGER and each product/week contains 7 * 10 daily rows.
    -- Bound before squaring: multiplication remains safely within HUGEINT at this grain.
    SELECT w.item_id,CASE WHEN w.units IS NULL OR w.units<0
            OR w.units>CAST(7 AS HUGEINT)*cfg.expected_stores*2147483647
        THEN error('XYZ blocked: weekly units outside supported nonnegative INTEGER-daily provenance')
        ELSE w.units END AS safe_units
    FROM weekly w CROSS JOIN parameters cfg
), exact_moments AS MATERIALIZED (
    SELECT item_id,COUNT(*) AS n,SUM(safe_units) AS total_units,
        SUM(safe_units*safe_units) AS sum_squared_units
    FROM bounded_weekly GROUP BY item_id
), squared_cv AS MATERIALIZED (
    SELECT item_id,total_units,n*sum_squared_units-total_units*total_units AS variance_numerator,
        total_units*total_units AS mean_denominator FROM exact_moments
), expected_xyz AS MATERIALIZED (
    -- For population CV: CV^2 = (n * sum(x^2) - sum(x)^2) / sum(x)^2.
    -- Inclusive rational boundaries use exact integers; no rounded or DOUBLE CV determines a label.
    SELECT a.*,CASE WHEN s.total_units=0 THEN 'ZERO_SALES'
        WHEN 4*s.variance_numerator<=s.mean_denominator THEN 'X'
        WHEN s.variance_numerator<=s.mean_denominator THEN 'Y'
        ELSE 'Z' END AS xyz_class
    FROM actual a JOIN squared_cv s USING (item_id)
), xyz_source_health AS (
    SELECT vh.passed AND (SELECT COUNT(*) FROM expected_xyz)=cfg.expected_items
        AND NOT EXISTS (SELECT 1 FROM squared_cv WHERE variance_numerator<0
            OR total_units<0 OR (total_units=0 AND variance_numerator<>0)) AS passed
    FROM validation_health vh CROSS JOIN parameters cfg
)
, xyz_schema AS (
    SELECT * FROM expected_schema
    UNION ALL SELECT 'xyz_class','VARCHAR',15
), actual_xyz_schema AS (
    SELECT column_name,data_type,ordinal_position FROM information_schema.columns
    WHERE table_catalog=current_database() AND table_schema='mart' AND table_name='m5_product_xyz_12w'
), xyz_schema_errors AS (
    SELECT COUNT(*) AS errors FROM xyz_schema e FULL OUTER JOIN actual_xyz_schema a USING (column_name)
    WHERE e.column_name IS NULL OR a.column_name IS NULL OR e.data_type IS DISTINCT FROM a.data_type
        OR e.ordinal_position IS DISTINCT FROM a.ordinal_position
), actual_xyz AS MATERIALIZED (
    SELECT item_id,dept_id,cat_id,window_start,window_end,week_count,units,mean_weekly_units,stddev_weekly_units,
        cv_weekly,zero_sales_weeks,zero_week_share,positive_weeks,mean_positive_gap_weeks,xyz_class
    FROM mart.m5_product_xyz_12w
), xyz_expected_only AS (
    SELECT * FROM expected_xyz EXCEPT ALL SELECT * FROM actual_xyz
), xyz_actual_only AS (
    SELECT * FROM actual_xyz EXCEPT ALL SELECT * FROM expected_xyz
), xyz_validation_health AS (
    -- All 15 snapshot fields match exactly: floats are copied, not recalculated in the target.
    -- The source metrics above are separately reconciled to recomputation using explicit tolerance.
    SELECT h.passed AND se.errors=0 AND (SELECT COUNT(*) FROM actual_xyz_schema)=15
        AND (SELECT COUNT(*) FROM actual_xyz)=cfg.expected_items
        AND (SELECT COUNT(DISTINCT item_id) FROM actual_xyz)=cfg.expected_items
        AND NOT EXISTS (SELECT 1 FROM xyz_expected_only)
        AND NOT EXISTS (SELECT 1 FROM xyz_actual_only) AS passed
    FROM xyz_source_health h CROSS JOIN xyz_schema_errors se CROSS JOIN parameters cfg
), abc_parameters AS (
    SELECT DATE '2016-01-26' AS start_date,DATE '2016-04-24' AS end_date
), abc_schema(column_name,data_type,ordinal_position) AS (
    VALUES ('item_id','VARCHAR',1),('dept_id','VARCHAR',2),('cat_id','VARCHAR',3),
        ('window_start','DATE',4),('window_end','DATE',5),('units','HUGEINT',6),
        ('sku_rank','BIGINT',7),('cumulative_units','HUGEINT',8),('abc_class','VARCHAR',9)
), abc_actual_schema AS (
    SELECT column_name,data_type,ordinal_position FROM information_schema.columns
    WHERE table_catalog=current_database() AND table_schema='mart' AND table_name='m5_product_abc_90d'
), abc_schema_errors AS (
    SELECT COUNT(*) AS errors FROM abc_schema e FULL OUTER JOIN abc_actual_schema a USING(column_name)
    WHERE e.column_name IS NULL OR a.column_name IS NULL OR e.data_type IS DISTINCT FROM a.data_type
        OR e.ordinal_position IS DISTINCT FROM a.ordinal_position
), abc_snapshot AS MATERIALIZED (
    SELECT item_id,dept_id,cat_id,window_start,window_end,units,sku_rank,cumulative_units,abc_class
    FROM mart.m5_product_abc_90d
), abc_totals AS (
    SELECT COUNT(*) AS rows,COUNT(DISTINCT item_id) AS items,COALESCE(SUM(units),0) AS units,
        COUNT(*) FILTER (WHERE NULLIF(TRIM(item_id),'') IS NULL OR units IS NULL OR units<0
            OR units>CAST(90 AS HUGEINT)*cfg.expected_stores*2147483647
            OR window_start IS DISTINCT FROM ap.start_date OR window_end IS DISTINCT FROM ap.end_date) AS invalid_rows
    FROM abc_snapshot CROSS JOIN abc_parameters ap CROSS JOIN parameters cfg
), abc_mapping_errors AS (
    SELECT COUNT(*) AS errors FROM abc_snapshot a LEFT JOIN core.m5_product p USING(item_id)
    WHERE p.item_id IS NULL OR a.dept_id IS DISTINCT FROM p.dept_id OR a.cat_id IS DISTINCT FROM p.cat_id
), abc_ranked AS MATERIALIZED (
    SELECT item_id,ROW_NUMBER() OVER(ORDER BY units DESC,item_id ASC) AS expected_rank,
        SUM(units) OVER(ORDER BY units DESC,item_id ASC ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS expected_cumulative
    FROM abc_snapshot WHERE units>0
), abc_recomputed AS MATERIALIZED (
    SELECT a.item_id,r.expected_rank,r.expected_cumulative,
        CASE WHEN a.units=0 THEN 'ZERO_SALES'
            WHEN (r.expected_cumulative-a.units)*100<t.units*80 THEN 'A'
            WHEN (r.expected_cumulative-a.units)*100<t.units*95 THEN 'B' ELSE 'C' END AS expected_class
    FROM abc_snapshot a LEFT JOIN abc_ranked r USING(item_id) CROSS JOIN abc_totals t
), abc_errors AS (
    SELECT COUNT(*) AS errors FROM abc_snapshot a JOIN abc_recomputed r USING(item_id)
    WHERE a.sku_rank IS DISTINCT FROM r.expected_rank OR a.cumulative_units IS DISTINCT FROM r.expected_cumulative
        OR a.abc_class IS DISTINCT FROM r.expected_class
), abc_health AS (
    SELECT t.rows=cfg.expected_items AND t.items=cfg.expected_items AND t.invalid_rows=0
        AND se.errors=0 AND (SELECT COUNT(*) FROM abc_actual_schema)=9 AND me.errors=0 AND e.errors=0 AS passed
    FROM abc_totals t CROSS JOIN parameters cfg CROSS JOIN abc_schema_errors se
    CROSS JOIN abc_mapping_errors me CROSS JOIN abc_errors e
), abc_only_keys AS (
    SELECT item_id FROM abc_snapshot EXCEPT ALL SELECT item_id FROM actual_xyz
), xyz_only_keys AS (
    SELECT item_id FROM actual_xyz EXCEPT ALL SELECT item_id FROM abc_snapshot
), combined_expected AS MATERIALIZED (
    SELECT a.item_id,a.dept_id,a.cat_id,
        a.window_start AS abc_window_start,a.window_end AS abc_window_end,
        x.window_start AS xyz_window_start,x.window_end AS xyz_window_end,
        a.units AS units_90d,x.units AS units_84d,a.units-x.units AS excluded_six_day_units,
        a.sku_rank AS abc_sku_rank,a.cumulative_units AS abc_cumulative_units,a.abc_class,x.xyz_class,
        x.week_count,x.mean_weekly_units,x.stddev_weekly_units,x.cv_weekly,x.zero_sales_weeks,x.zero_week_share,
        x.positive_weeks,x.mean_positive_gap_weeks
    FROM abc_snapshot a JOIN actual_xyz x USING(item_id)
), combined_input_health AS (
    SELECT xh.passed AND ah.passed
        AND NOT EXISTS (SELECT 1 FROM abc_only_keys) AND NOT EXISTS (SELECT 1 FROM xyz_only_keys)
        AND (SELECT COUNT(*) FROM combined_expected)=cfg.expected_items
        AND NOT EXISTS (SELECT 1 FROM abc_snapshot a JOIN actual_xyz x USING(item_id)
            WHERE a.dept_id IS DISTINCT FROM x.dept_id OR a.cat_id IS DISTINCT FROM x.cat_id
                OR a.units<x.units OR (a.units=0 AND x.xyz_class<>'ZERO_SALES')) AS passed
    FROM xyz_validation_health xh CROSS JOIN abc_health ah CROSS JOIN parameters cfg
)
SELECT e.item_id,
    e.dept_id,
    e.cat_id,
    e.abc_window_start,
    e.abc_window_end,
    e.xyz_window_start,
    e.xyz_window_end,
    CASE WHEN COALESCE(h.passed,false) THEN e.units_90d ELSE error('ABC XYZ build blocked: source snapshots or one-to-one product join failed') END AS units_90d,
    e.units_84d,
    e.excluded_six_day_units,
    e.abc_sku_rank,
    e.abc_cumulative_units,
    e.abc_class,
    e.xyz_class,
    e.week_count,
    e.mean_weekly_units,
    e.stddev_weekly_units,
    e.cv_weekly,
    e.zero_sales_weeks,
    e.zero_week_share,
    e.positive_weeks,
    e.mean_positive_gap_weeks
FROM combined_input_health h LEFT JOIN combined_expected e ON true;

-- VALIDATION: if the combined table exists, run only this complete query.
-- ABC source equality relies on accepted SQL21. XYZ weekly source equality relies on SQL23.
-- Recheck snapshot internals, exact copied fields, per-product bridge and both matrix margins.
WITH parameters AS (
    SELECT 3049 AS expected_items,10 AS expected_stores,12 AS expected_weeks,
        DATE '2016-01-30' AS start_date,DATE '2016-04-22' AS end_date,
        1e-9::DOUBLE AS absolute_tolerance,1e-9::DOUBLE AS relative_tolerance
), source_schema(column_name,data_type,ordinal_position) AS (
    VALUES ('item_id','VARCHAR',1),('dept_id','VARCHAR',2),('cat_id','VARCHAR',3),('wm_yr_wk','INTEGER',4),
        ('week_start','DATE',5),('week_end','DATE',6),('units','HUGEINT',7),('source_daily_rows','BIGINT',8)
), actual_source_schema AS (
    SELECT column_name,data_type,ordinal_position FROM information_schema.columns
    WHERE table_catalog=current_database() AND table_schema='mart' AND table_name='m5_product_weekly_12w'
), source_schema_errors AS (
    SELECT COUNT(*) AS errors FROM source_schema e FULL OUTER JOIN actual_source_schema a USING (column_name)
    WHERE e.column_name IS NULL OR a.column_name IS NULL OR e.data_type IS DISTINCT FROM a.data_type
        OR e.ordinal_position IS DISTINCT FROM a.ordinal_position
), department_mapping(dept_id,cat_id) AS (
    VALUES ('FOODS_1','FOODS'),('FOODS_2','FOODS'),('FOODS_3','FOODS'),
        ('HOUSEHOLD_1','HOUSEHOLD'),('HOUSEHOLD_2','HOUSEHOLD'),('HOBBIES_1','HOBBIES'),('HOBBIES_2','HOBBIES')
), product_health AS (
    SELECT COUNT(*) AS rows,COUNT(DISTINCT p.item_id) AS items,
        COUNT(*) FILTER (WHERE NULLIF(TRIM(p.item_id),'') IS NULL OR m.dept_id IS NULL) AS invalid_rows
    FROM core.m5_product p LEFT JOIN department_mapping m ON p.dept_id=m.dept_id AND p.cat_id=m.cat_id
), weekly AS MATERIALIZED (
    SELECT w.*,CAST(date_diff('day',cfg.start_date,w.week_start)//7+1 AS INTEGER) AS week_index
    FROM mart.m5_product_weekly_12w w CROSS JOIN parameters cfg
), source_health AS (
    SELECT COUNT(*) AS rows,COUNT(DISTINCT item_id) AS items,
        COUNT(*) FILTER (WHERE NULLIF(TRIM(item_id),'') IS NULL OR units IS NULL OR units<0
            OR wm_yr_wk IS NULL OR wm_yr_wk NOT BETWEEN 11601 AND 11612
            OR week_start IS DISTINCT FROM cfg.start_date+7*(wm_yr_wk-11601)
            OR week_end IS DISTINCT FROM cfg.start_date+7*(wm_yr_wk-11601)+6
            OR source_daily_rows IS DISTINCT FROM 7*cfg.expected_stores) AS invalid_rows
    FROM weekly CROSS JOIN parameters cfg
), item_coverage AS (
    SELECT item_id,COUNT(*) AS rows,COUNT(DISTINCT wm_yr_wk) AS weeks FROM weekly GROUP BY item_id
), joined AS MATERIALIZED (
    SELECT w.*,p.item_id AS matched_item,p.dept_id AS matched_department,p.cat_id AS matched_category
    FROM weekly w LEFT JOIN core.m5_product p USING (item_id)
), join_health AS (
    SELECT COUNT(*) AS rows,
        COUNT(*) FILTER (WHERE matched_item IS NULL OR dept_id IS DISTINCT FROM matched_department
            OR cat_id IS DISTINCT FROM matched_category) AS invalid_rows FROM joined
), stats AS MATERIALIZED (
    SELECT item_id,dept_id,cat_id,MIN(week_start) AS window_start,MAX(week_end) AS window_end,
        COUNT(*) AS week_count,SUM(units) AS units,
        AVG(CAST(units AS DOUBLE)) AS mean_weekly_units,STDDEV_POP(CAST(units AS DOUBLE)) AS stddev_weekly_units,
        COUNT(*) FILTER (WHERE units=0) AS zero_sales_weeks,COUNT(*) FILTER (WHERE units>0) AS positive_weeks,
        MIN(week_index) FILTER (WHERE units>0) AS first_positive_week,
        MAX(week_index) FILTER (WHERE units>0) AS last_positive_week
    FROM joined GROUP BY item_id,dept_id,cat_id
), expected AS MATERIALIZED (
    SELECT item_id,dept_id,cat_id,window_start,window_end,week_count,units,mean_weekly_units,stddev_weekly_units,
        CASE WHEN mean_weekly_units=0 THEN NULL ELSE stddev_weekly_units/mean_weekly_units END AS cv_weekly,
        zero_sales_weeks,CAST(zero_sales_weeks AS DOUBLE)/week_count AS zero_week_share,positive_weeks,
        CASE WHEN positive_weeks<2 THEN NULL
             ELSE CAST(last_positive_week-first_positive_week AS DOUBLE)/(positive_weeks-1) END AS mean_positive_gap_weeks
    FROM stats
), computed_health AS (
    SELECT COUNT(*) AS rows,
        COUNT(*) FILTER (WHERE NOT isfinite(mean_weekly_units) OR NOT isfinite(stddev_weekly_units)
            OR mean_weekly_units<0 OR stddev_weekly_units<0 OR NOT isfinite(zero_week_share)
            OR zero_week_share<0 OR zero_week_share>1
            OR (cv_weekly IS NOT NULL AND (NOT isfinite(cv_weekly) OR cv_weekly<0))
            OR (mean_positive_gap_weeks IS NOT NULL AND
                (NOT isfinite(mean_positive_gap_weeks) OR mean_positive_gap_weeks<1 OR mean_positive_gap_weeks>11))) AS invalid_rows
    FROM expected
), health AS (
    SELECT ph.rows=cfg.expected_items AND ph.items=cfg.expected_items AND ph.invalid_rows=0
        AND se.errors=0 AND (SELECT COUNT(*) FROM actual_source_schema)=8
        AND sh.rows=cfg.expected_items*cfg.expected_weeks AND sh.items=cfg.expected_items AND sh.invalid_rows=0
        AND NOT EXISTS (SELECT 1 FROM item_coverage WHERE rows<>cfg.expected_weeks OR weeks<>cfg.expected_weeks)
        AND jh.rows=sh.rows AND jh.invalid_rows=0 AND ch.rows=cfg.expected_items AND ch.invalid_rows=0 AS passed
    FROM parameters cfg CROSS JOIN product_health ph CROSS JOIN source_schema_errors se
    CROSS JOIN source_health sh CROSS JOIN join_health jh CROSS JOIN computed_health ch
), expected_schema(column_name,data_type,ordinal_position) AS (
    VALUES ('item_id','VARCHAR',1),('dept_id','VARCHAR',2),('cat_id','VARCHAR',3),
        ('window_start','DATE',4),('window_end','DATE',5),('week_count','BIGINT',6),('units','HUGEINT',7),
        ('mean_weekly_units','DOUBLE',8),('stddev_weekly_units','DOUBLE',9),('cv_weekly','DOUBLE',10),
        ('zero_sales_weeks','BIGINT',11),('zero_week_share','DOUBLE',12),('positive_weeks','BIGINT',13),
        ('mean_positive_gap_weeks','DOUBLE',14)
), actual_schema AS (
    SELECT column_name,data_type,ordinal_position FROM information_schema.columns
    WHERE table_catalog=current_database() AND table_schema='mart' AND table_name='m5_product_variability_12w'
), schema_errors AS (
    SELECT COUNT(*) AS errors FROM expected_schema e FULL OUTER JOIN actual_schema a USING (column_name)
    WHERE e.column_name IS NULL OR a.column_name IS NULL OR e.data_type IS DISTINCT FROM a.data_type
        OR e.ordinal_position IS DISTINCT FROM a.ordinal_position
), actual AS MATERIALIZED (
    SELECT item_id,dept_id,cat_id,window_start,window_end,week_count,units,mean_weekly_units,stddev_weekly_units,
        cv_weekly,zero_sales_weeks,zero_week_share,positive_weeks,mean_positive_gap_weeks
    FROM mart.m5_product_variability_12w
), exact_expected_only AS (
    SELECT item_id,dept_id,cat_id,window_start,window_end,week_count,units,zero_sales_weeks,positive_weeks FROM expected
    EXCEPT ALL
    SELECT item_id,dept_id,cat_id,window_start,window_end,week_count,units,zero_sales_weeks,positive_weeks FROM actual
), exact_actual_only AS (
    SELECT item_id,dept_id,cat_id,window_start,window_end,week_count,units,zero_sales_weeks,positive_weeks FROM actual
    EXCEPT ALL
    SELECT item_id,dept_id,cat_id,window_start,window_end,week_count,units,zero_sales_weeks,positive_weeks FROM expected
), float_errors AS (
    SELECT COUNT(*) AS errors FROM actual a JOIN expected e USING (item_id) CROSS JOIN parameters cfg
    CROSS JOIN LATERAL (VALUES (a.mean_weekly_units,e.mean_weekly_units),(a.stddev_weekly_units,e.stddev_weekly_units),
        (a.cv_weekly,e.cv_weekly),(a.zero_week_share,e.zero_week_share),(a.mean_positive_gap_weeks,e.mean_positive_gap_weeks)
    ) v(actual_value,expected_value)
    WHERE CASE WHEN v.expected_value IS NULL THEN v.actual_value IS NOT NULL
               WHEN v.actual_value IS NULL OR NOT isfinite(v.actual_value) OR NOT isfinite(v.expected_value) THEN true
               ELSE abs(v.actual_value-v.expected_value)>cfg.absolute_tolerance+cfg.relative_tolerance*abs(v.expected_value) END
), actual_health AS (
    SELECT COUNT(*) AS rows,COUNT(DISTINCT item_id) AS items,
        COUNT(*) FILTER (WHERE mean_weekly_units<0 OR stddev_weekly_units<0 OR cv_weekly<0
            OR zero_week_share<0 OR zero_week_share>1
            OR (mean_positive_gap_weeks IS NOT NULL AND (mean_positive_gap_weeks<1 OR mean_positive_gap_weeks>11))) AS range_errors
    FROM actual
), validation_health AS (
    SELECT h.passed AND se.errors=0 AND (SELECT COUNT(*) FROM actual_schema)=14
        AND ah.rows=cfg.expected_items AND ah.items=cfg.expected_items AND ah.range_errors=0 AND fe.errors=0
        AND NOT EXISTS (SELECT 1 FROM exact_expected_only) AND NOT EXISTS (SELECT 1 FROM exact_actual_only) AS passed
    FROM health h CROSS JOIN schema_errors se CROSS JOIN parameters cfg CROSS JOIN actual_health ah CROSS JOIN float_errors fe
)
, bounded_weekly AS MATERIALIZED (
    -- Upstream daily units are INTEGER and each product/week contains 7 * 10 daily rows.
    -- Bound before squaring: multiplication remains safely within HUGEINT at this grain.
    SELECT w.item_id,CASE WHEN w.units IS NULL OR w.units<0
            OR w.units>CAST(7 AS HUGEINT)*cfg.expected_stores*2147483647
        THEN error('XYZ blocked: weekly units outside supported nonnegative INTEGER-daily provenance')
        ELSE w.units END AS safe_units
    FROM weekly w CROSS JOIN parameters cfg
), exact_moments AS MATERIALIZED (
    SELECT item_id,COUNT(*) AS n,SUM(safe_units) AS total_units,
        SUM(safe_units*safe_units) AS sum_squared_units
    FROM bounded_weekly GROUP BY item_id
), squared_cv AS MATERIALIZED (
    SELECT item_id,total_units,n*sum_squared_units-total_units*total_units AS variance_numerator,
        total_units*total_units AS mean_denominator FROM exact_moments
), expected_xyz AS MATERIALIZED (
    -- For population CV: CV^2 = (n * sum(x^2) - sum(x)^2) / sum(x)^2.
    -- Inclusive rational boundaries use exact integers; no rounded or DOUBLE CV determines a label.
    SELECT a.*,CASE WHEN s.total_units=0 THEN 'ZERO_SALES'
        WHEN 4*s.variance_numerator<=s.mean_denominator THEN 'X'
        WHEN s.variance_numerator<=s.mean_denominator THEN 'Y'
        ELSE 'Z' END AS xyz_class
    FROM actual a JOIN squared_cv s USING (item_id)
), xyz_source_health AS (
    SELECT vh.passed AND (SELECT COUNT(*) FROM expected_xyz)=cfg.expected_items
        AND NOT EXISTS (SELECT 1 FROM squared_cv WHERE variance_numerator<0
            OR total_units<0 OR (total_units=0 AND variance_numerator<>0)) AS passed
    FROM validation_health vh CROSS JOIN parameters cfg
)
, xyz_schema AS (
    SELECT * FROM expected_schema
    UNION ALL SELECT 'xyz_class','VARCHAR',15
), actual_xyz_schema AS (
    SELECT column_name,data_type,ordinal_position FROM information_schema.columns
    WHERE table_catalog=current_database() AND table_schema='mart' AND table_name='m5_product_xyz_12w'
), xyz_schema_errors AS (
    SELECT COUNT(*) AS errors FROM xyz_schema e FULL OUTER JOIN actual_xyz_schema a USING (column_name)
    WHERE e.column_name IS NULL OR a.column_name IS NULL OR e.data_type IS DISTINCT FROM a.data_type
        OR e.ordinal_position IS DISTINCT FROM a.ordinal_position
), actual_xyz AS MATERIALIZED (
    SELECT item_id,dept_id,cat_id,window_start,window_end,week_count,units,mean_weekly_units,stddev_weekly_units,
        cv_weekly,zero_sales_weeks,zero_week_share,positive_weeks,mean_positive_gap_weeks,xyz_class
    FROM mart.m5_product_xyz_12w
), xyz_expected_only AS (
    SELECT * FROM expected_xyz EXCEPT ALL SELECT * FROM actual_xyz
), xyz_actual_only AS (
    SELECT * FROM actual_xyz EXCEPT ALL SELECT * FROM expected_xyz
), xyz_validation_health AS (
    -- All 15 snapshot fields match exactly: floats are copied, not recalculated in the target.
    -- The source metrics above are separately reconciled to recomputation using explicit tolerance.
    SELECT h.passed AND se.errors=0 AND (SELECT COUNT(*) FROM actual_xyz_schema)=15
        AND (SELECT COUNT(*) FROM actual_xyz)=cfg.expected_items
        AND (SELECT COUNT(DISTINCT item_id) FROM actual_xyz)=cfg.expected_items
        AND NOT EXISTS (SELECT 1 FROM xyz_expected_only)
        AND NOT EXISTS (SELECT 1 FROM xyz_actual_only) AS passed
    FROM xyz_source_health h CROSS JOIN xyz_schema_errors se CROSS JOIN parameters cfg
), abc_parameters AS (
    SELECT DATE '2016-01-26' AS start_date,DATE '2016-04-24' AS end_date
), abc_schema(column_name,data_type,ordinal_position) AS (
    VALUES ('item_id','VARCHAR',1),('dept_id','VARCHAR',2),('cat_id','VARCHAR',3),
        ('window_start','DATE',4),('window_end','DATE',5),('units','HUGEINT',6),
        ('sku_rank','BIGINT',7),('cumulative_units','HUGEINT',8),('abc_class','VARCHAR',9)
), abc_actual_schema AS (
    SELECT column_name,data_type,ordinal_position FROM information_schema.columns
    WHERE table_catalog=current_database() AND table_schema='mart' AND table_name='m5_product_abc_90d'
), abc_schema_errors AS (
    SELECT COUNT(*) AS errors FROM abc_schema e FULL OUTER JOIN abc_actual_schema a USING(column_name)
    WHERE e.column_name IS NULL OR a.column_name IS NULL OR e.data_type IS DISTINCT FROM a.data_type
        OR e.ordinal_position IS DISTINCT FROM a.ordinal_position
), abc_snapshot AS MATERIALIZED (
    SELECT item_id,dept_id,cat_id,window_start,window_end,units,sku_rank,cumulative_units,abc_class
    FROM mart.m5_product_abc_90d
), abc_totals AS (
    SELECT COUNT(*) AS rows,COUNT(DISTINCT item_id) AS items,COALESCE(SUM(units),0) AS units,
        COUNT(*) FILTER (WHERE NULLIF(TRIM(item_id),'') IS NULL OR units IS NULL OR units<0
            OR units>CAST(90 AS HUGEINT)*cfg.expected_stores*2147483647
            OR window_start IS DISTINCT FROM ap.start_date OR window_end IS DISTINCT FROM ap.end_date) AS invalid_rows
    FROM abc_snapshot CROSS JOIN abc_parameters ap CROSS JOIN parameters cfg
), abc_mapping_errors AS (
    SELECT COUNT(*) AS errors FROM abc_snapshot a LEFT JOIN core.m5_product p USING(item_id)
    WHERE p.item_id IS NULL OR a.dept_id IS DISTINCT FROM p.dept_id OR a.cat_id IS DISTINCT FROM p.cat_id
), abc_ranked AS MATERIALIZED (
    SELECT item_id,ROW_NUMBER() OVER(ORDER BY units DESC,item_id ASC) AS expected_rank,
        SUM(units) OVER(ORDER BY units DESC,item_id ASC ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS expected_cumulative
    FROM abc_snapshot WHERE units>0
), abc_recomputed AS MATERIALIZED (
    SELECT a.item_id,r.expected_rank,r.expected_cumulative,
        CASE WHEN a.units=0 THEN 'ZERO_SALES'
            WHEN (r.expected_cumulative-a.units)*100<t.units*80 THEN 'A'
            WHEN (r.expected_cumulative-a.units)*100<t.units*95 THEN 'B' ELSE 'C' END AS expected_class
    FROM abc_snapshot a LEFT JOIN abc_ranked r USING(item_id) CROSS JOIN abc_totals t
), abc_errors AS (
    SELECT COUNT(*) AS errors FROM abc_snapshot a JOIN abc_recomputed r USING(item_id)
    WHERE a.sku_rank IS DISTINCT FROM r.expected_rank OR a.cumulative_units IS DISTINCT FROM r.expected_cumulative
        OR a.abc_class IS DISTINCT FROM r.expected_class
), abc_health AS (
    SELECT t.rows=cfg.expected_items AND t.items=cfg.expected_items AND t.invalid_rows=0
        AND se.errors=0 AND (SELECT COUNT(*) FROM abc_actual_schema)=9 AND me.errors=0 AND e.errors=0 AS passed
    FROM abc_totals t CROSS JOIN parameters cfg CROSS JOIN abc_schema_errors se
    CROSS JOIN abc_mapping_errors me CROSS JOIN abc_errors e
), abc_only_keys AS (
    SELECT item_id FROM abc_snapshot EXCEPT ALL SELECT item_id FROM actual_xyz
), xyz_only_keys AS (
    SELECT item_id FROM actual_xyz EXCEPT ALL SELECT item_id FROM abc_snapshot
), combined_expected AS MATERIALIZED (
    SELECT a.item_id,a.dept_id,a.cat_id,
        a.window_start AS abc_window_start,a.window_end AS abc_window_end,
        x.window_start AS xyz_window_start,x.window_end AS xyz_window_end,
        a.units AS units_90d,x.units AS units_84d,a.units-x.units AS excluded_six_day_units,
        a.sku_rank AS abc_sku_rank,a.cumulative_units AS abc_cumulative_units,a.abc_class,x.xyz_class,
        x.week_count,x.mean_weekly_units,x.stddev_weekly_units,x.cv_weekly,x.zero_sales_weeks,x.zero_week_share,
        x.positive_weeks,x.mean_positive_gap_weeks
    FROM abc_snapshot a JOIN actual_xyz x USING(item_id)
), combined_input_health AS (
    SELECT xh.passed AND ah.passed
        AND NOT EXISTS (SELECT 1 FROM abc_only_keys) AND NOT EXISTS (SELECT 1 FROM xyz_only_keys)
        AND (SELECT COUNT(*) FROM combined_expected)=cfg.expected_items
        AND NOT EXISTS (SELECT 1 FROM abc_snapshot a JOIN actual_xyz x USING(item_id)
            WHERE a.dept_id IS DISTINCT FROM x.dept_id OR a.cat_id IS DISTINCT FROM x.cat_id
                OR a.units<x.units OR (a.units=0 AND x.xyz_class<>'ZERO_SALES')) AS passed
    FROM xyz_validation_health xh CROSS JOIN abc_health ah CROSS JOIN parameters cfg
)
, combined_schema(column_name,data_type,ordinal_position) AS (
    VALUES ('item_id','VARCHAR',1),
        ('dept_id','VARCHAR',2),
        ('cat_id','VARCHAR',3),
        ('abc_window_start','DATE',4),
        ('abc_window_end','DATE',5),
        ('xyz_window_start','DATE',6),
        ('xyz_window_end','DATE',7),
        ('units_90d','HUGEINT',8),
        ('units_84d','HUGEINT',9),
        ('excluded_six_day_units','HUGEINT',10),
        ('abc_sku_rank','BIGINT',11),
        ('abc_cumulative_units','HUGEINT',12),
        ('abc_class','VARCHAR',13),
        ('xyz_class','VARCHAR',14),
        ('week_count','BIGINT',15),
        ('mean_weekly_units','DOUBLE',16),
        ('stddev_weekly_units','DOUBLE',17),
        ('cv_weekly','DOUBLE',18),
        ('zero_sales_weeks','BIGINT',19),
        ('zero_week_share','DOUBLE',20),
        ('positive_weeks','BIGINT',21),
        ('mean_positive_gap_weeks','DOUBLE',22)
), combined_actual_schema AS (
    SELECT column_name,data_type,ordinal_position FROM information_schema.columns
    WHERE table_catalog=current_database() AND table_schema='mart' AND table_name='m5_product_abc_xyz'
), combined_schema_errors AS (
    SELECT COUNT(*) AS errors FROM combined_schema e FULL OUTER JOIN combined_actual_schema a USING(column_name)
    WHERE e.column_name IS NULL OR a.column_name IS NULL OR e.data_type IS DISTINCT FROM a.data_type
        OR e.ordinal_position IS DISTINCT FROM a.ordinal_position
), combined_actual AS MATERIALIZED (
    SELECT item_id,dept_id,cat_id,abc_window_start,abc_window_end,xyz_window_start,xyz_window_end,units_90d,units_84d,excluded_six_day_units,abc_sku_rank,abc_cumulative_units,abc_class,xyz_class,week_count,mean_weekly_units,stddev_weekly_units,cv_weekly,zero_sales_weeks,zero_week_share,positive_weeks,mean_positive_gap_weeks FROM mart.m5_product_abc_xyz
), combined_expected_only AS (
    SELECT * FROM combined_expected EXCEPT ALL SELECT * FROM combined_actual
), combined_actual_only AS (
    SELECT * FROM combined_actual EXCEPT ALL SELECT * FROM combined_expected
), abc_margin_expected AS (
    SELECT abc_class,COUNT(*) AS sku_count,SUM(units) AS units FROM abc_snapshot GROUP BY abc_class
), abc_margin_actual AS (
    SELECT abc_class,COUNT(*) AS sku_count,SUM(units_90d) AS units FROM combined_actual GROUP BY abc_class
), xyz_margin_expected AS (
    SELECT xyz_class,COUNT(*) AS sku_count,SUM(units) AS units FROM actual_xyz GROUP BY xyz_class
), xyz_margin_actual AS (
    SELECT xyz_class,COUNT(*) AS sku_count,SUM(units_84d) AS units FROM combined_actual GROUP BY xyz_class
), margin_errors AS (
    SELECT * FROM (SELECT * FROM abc_margin_expected EXCEPT ALL SELECT * FROM abc_margin_actual)
    UNION ALL SELECT * FROM (SELECT * FROM abc_margin_actual EXCEPT ALL SELECT * FROM abc_margin_expected)
    UNION ALL SELECT * FROM (SELECT * FROM xyz_margin_expected EXCEPT ALL SELECT * FROM xyz_margin_actual)
    UNION ALL SELECT * FROM (SELECT * FROM xyz_margin_actual EXCEPT ALL SELECT * FROM xyz_margin_expected)
), combined_validation_health AS (
    SELECT h.passed AND se.errors=0 AND (SELECT COUNT(*) FROM combined_actual_schema)=22
        AND (SELECT COUNT(*) FROM combined_actual)=cfg.expected_items
        AND (SELECT COUNT(DISTINCT item_id) FROM combined_actual)=cfg.expected_items
        AND NOT EXISTS (SELECT 1 FROM combined_expected_only) AND NOT EXISTS (SELECT 1 FROM combined_actual_only)
        AND NOT EXISTS (SELECT 1 FROM margin_errors)
        AND NOT EXISTS (SELECT 1 FROM combined_actual WHERE units_90d<units_84d
            OR excluded_six_day_units IS DISTINCT FROM units_90d-units_84d) AS passed
    FROM combined_input_health h CROSS JOIN combined_schema_errors se CROSS JOIN parameters cfg
), abc_groups(display_order,abc_class) AS (
    VALUES (1,'A'),(2,'B'),(3,'C'),(4,'ZERO_SALES'),(5,'TOTAL')
), matrix AS (
    SELECT g.display_order,g.abc_class,
        COUNT(a.item_id) FILTER(WHERE a.xyz_class='X') AS x_skus,
        COUNT(a.item_id) FILTER(WHERE a.xyz_class='Y') AS y_skus,
        COUNT(a.item_id) FILTER(WHERE a.xyz_class='Z') AS z_skus,
        COUNT(a.item_id) FILTER(WHERE a.xyz_class='ZERO_SALES') AS zero_xyz_skus,COUNT(a.item_id) AS total_skus
    FROM abc_groups g LEFT JOIN combined_actual a ON g.abc_class='TOTAL' OR g.abc_class=a.abc_class
    GROUP BY g.display_order,g.abc_class
)
SELECT m.abc_class,m.x_skus,m.y_skus,m.z_skus,m.zero_xyz_skus,m.total_skus,
    CAST(ap.start_date AS VARCHAR)||'..'||CAST(ap.end_date AS VARCHAR) AS abc_window,
    CAST(cfg.start_date AS VARCHAR)||'..'||CAST(cfg.end_date AS VARCHAR) AS xyz_window,
    CASE WHEN COALESCE(h.passed,false) AND m.x_skus+m.y_skus+m.z_skus+m.zero_xyz_skus=m.total_skus THEN 'PASS'
        ELSE error('ABC XYZ validation blocked: sources, combined fields, bridge or matrix margins failed') END AS check_status
FROM matrix m CROSS JOIN combined_validation_health h CROSS JOIN parameters cfg CROSS JOIN abc_parameters ap
ORDER BY m.display_order;
