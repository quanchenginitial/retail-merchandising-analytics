-- Purpose: measure one-boundary-at-a-time ABC label sensitivity on the accepted snapshot.
-- Read-only. Same 2016-01-26..2016-04-24 global SKU unit ranking; no baseline edits.
-- Scenarios were fixed before observing outputs. They are illustrative, not optimized policies.
-- changed_unit_share_pct is the historical unit share of relabelled SKUs, not a sales change.
WITH parameters AS (
    SELECT 3049 AS expected_items,DATE '2016-01-26' AS start_date,DATE '2016-04-24' AS end_date
), scenarios(display_order,scenario,a_target,ab_target,allowed_from,allowed_to) AS (
    VALUES (1,'BASE_80_95',80,95,NULL,NULL),(2,'A75_95',75,95,'A','B'),
        (3,'A85_95',85,95,'B','A'),(4,'AB80_92',80,92,'B','C'),(5,'AB80_98',80,98,'C','B')
), expected_schema(column_name,data_type,ordinal_position) AS (
    VALUES ('item_id','VARCHAR',1),('dept_id','VARCHAR',2),('cat_id','VARCHAR',3),
        ('window_start','DATE',4),('window_end','DATE',5),('units','HUGEINT',6),
        ('sku_rank','BIGINT',7),('cumulative_units','HUGEINT',8),('abc_class','VARCHAR',9)
), actual_schema AS (
    SELECT column_name,data_type,ordinal_position FROM information_schema.columns
    WHERE table_catalog=current_database() AND table_schema='mart' AND table_name='m5_product_abc_90d'
), schema_errors AS (
    SELECT COUNT(*) AS errors FROM expected_schema e FULL OUTER JOIN actual_schema a USING (column_name)
    WHERE e.column_name IS NULL OR a.column_name IS NULL OR e.data_type IS DISTINCT FROM a.data_type
        OR e.ordinal_position IS DISTINCT FROM a.ordinal_position
), baseline AS MATERIALIZED (
    SELECT * FROM mart.m5_product_abc_90d
), totals AS (
    SELECT COUNT(*) AS rows,COUNT(DISTINCT item_id) AS items,COALESCE(SUM(units),0) AS units,
        COUNT(*) FILTER (WHERE units=0) AS zero_skus,
        COUNT(*) FILTER (WHERE NULLIF(TRIM(item_id),'') IS NULL OR units IS NULL OR units<0
            OR window_start IS DISTINCT FROM cfg.start_date OR window_end IS DISTINCT FROM cfg.end_date) AS invalid_rows
    FROM baseline CROSS JOIN parameters cfg
), product_health AS (
    SELECT COUNT(*) AS rows,COUNT(DISTINCT item_id) AS items FROM core.m5_product
), mapping_errors AS (
    SELECT COUNT(*) AS errors FROM baseline b LEFT JOIN core.m5_product p USING (item_id)
    WHERE p.item_id IS NULL OR b.dept_id IS NULL OR b.cat_id IS NULL
        OR b.dept_id IS DISTINCT FROM p.dept_id OR b.cat_id IS DISTINCT FROM p.cat_id
), ranked AS MATERIALIZED (
    SELECT item_id,ROW_NUMBER() OVER (ORDER BY units DESC,item_id ASC) AS expected_rank,
        SUM(units) OVER (ORDER BY units DESC,item_id ASC
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS expected_cumulative
    FROM baseline WHERE units>0
), recomputed AS MATERIALIZED (
    SELECT b.item_id,b.units,b.abc_class AS baseline_class,r.expected_rank,r.expected_cumulative,
        CASE WHEN b.units=0 THEN 'ZERO_SALES'
             WHEN (r.expected_cumulative-b.units)*100<t.units*80 THEN 'A'
             WHEN (r.expected_cumulative-b.units)*100<t.units*95 THEN 'B' ELSE 'C' END AS expected_class
    FROM baseline b LEFT JOIN ranked r USING (item_id) CROSS JOIN totals t
), baseline_errors AS (
    SELECT COUNT(*) AS errors FROM baseline b JOIN recomputed r USING (item_id)
    WHERE b.sku_rank IS DISTINCT FROM r.expected_rank
       OR b.cumulative_units IS DISTINCT FROM r.expected_cumulative
       OR b.abc_class IS DISTINCT FROM r.expected_class
), health AS (
    SELECT t.rows=cfg.expected_items AND t.items=cfg.expected_items AND t.invalid_rows=0
        AND ph.rows=cfg.expected_items AND ph.items=cfg.expected_items
        AND me.errors=0 AND be.errors=0 AND se.errors=0
        AND (SELECT COUNT(*) FROM actual_schema)=9
        AND NOT EXISTS (SELECT 1 FROM scenarios WHERE NOT COALESCE(0<a_target AND a_target<ab_target AND ab_target<100,false)) AS passed
    FROM totals t CROSS JOIN parameters cfg CROSS JOIN product_health ph CROSS JOIN mapping_errors me
    CROSS JOIN baseline_errors be CROSS JOIN schema_errors se
), scenario_assignments AS MATERIALIZED (
    SELECT s.scenario,r.item_id,r.units,r.baseline_class,
        CASE WHEN r.units=0 THEN 'ZERO_SALES'
             WHEN (r.expected_cumulative-r.units)*100<t.units*s.a_target THEN 'A'
             WHEN (r.expected_cumulative-r.units)*100<t.units*s.ab_target THEN 'B' ELSE 'C' END AS scenario_class
    FROM scenarios s CROSS JOIN recomputed r CROSS JOIN totals t
), summaries AS (
    SELECT s.display_order,s.scenario,COUNT(a.item_id) AS total_skus,COALESCE(SUM(a.units),0) AS total_units,
        COUNT(*) FILTER (WHERE a.scenario_class='A') AS a_skus,
        COUNT(*) FILTER (WHERE a.scenario_class='B') AS b_skus,
        COUNT(*) FILTER (WHERE a.scenario_class='C') AS c_skus,
        COUNT(*) FILTER (WHERE a.scenario_class='ZERO_SALES') AS zero_skus,
        COUNT(*) FILTER (WHERE a.item_id IS NOT NULL AND a.scenario_class IS DISTINCT FROM a.baseline_class) AS changed_skus,
        COALESCE(SUM(a.units) FILTER (WHERE a.scenario_class IS DISTINCT FROM a.baseline_class),0) AS changed_units,
        COUNT(*) FILTER (WHERE a.item_id IS NOT NULL AND a.scenario_class IS DISTINCT FROM a.baseline_class
            AND NOT COALESCE(a.baseline_class=s.allowed_from AND a.scenario_class=s.allowed_to,false)) AS direction_errors
    FROM scenarios s LEFT JOIN scenario_assignments a USING (scenario)
    GROUP BY s.display_order,s.scenario
)
-- REPORT: preflight also compares all scenario/item labels to independent source-based labels.
SELECT s.scenario,s.a_skus,s.b_skus,s.c_skus,s.zero_skus,s.changed_skus,
    CAST(ROUND(100.0*s.changed_skus/NULLIF(t.items,0),4) AS DECIMAL(9,4)) AS changed_sku_pct,
    CAST(ROUND(100.0*s.changed_units/NULLIF(t.units,0),4) AS DECIMAL(9,4)) AS changed_unit_share_pct,
    CASE WHEN COALESCE(h.passed,false) AND s.total_skus=t.items AND s.total_units=t.units
              AND s.a_skus+s.b_skus+s.c_skus+s.zero_skus=t.items AND s.zero_skus=t.zero_skus
              AND s.direction_errors=0 AND (s.scenario<>'BASE_80_95' OR s.changed_skus=0)
         THEN 'PASS' ELSE error('ABC sensitivity blocked: accepted snapshot schema, window, keys, mapping, ranks, labels or scenario invariants failed')
    END AS check_status
FROM summaries s CROSS JOIN totals t CROSS JOIN health h
ORDER BY s.display_order;
