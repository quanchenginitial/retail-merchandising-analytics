-- Read-only UTC audit of the two named property observation histories.
-- Converted TIMESTAMP values use an explicit UTC convention, not a local business timezone.
-- Preserve every observation; no validity intervals, current-state selection or event join.
WITH expected_counts AS (
    SELECT 2291853::BIGINT AS expected_rows,788214::BIGINT AS expected_category_rows,
        1503639::BIGINT AS expected_available_rows,253402300799999::BIGINT AS max_supported_ms
), expected_schema(column_name,data_type,ordinal_position) AS (
    VALUES ('timestamp','BIGINT',1),('itemid','BIGINT',2),('property','VARCHAR',3),
        ('value','VARCHAR',4),('source_file','VARCHAR',5)
), source_schema AS (
    SELECT column_name,data_type,ordinal_position FROM information_schema.columns
    WHERE table_catalog=current_database() AND table_schema='rr_stg' AND table_name='item_state_observations'
), schema_stats AS (
    SELECT COUNT(*) FILTER (WHERE e.column_name IS DISTINCT FROM s.column_name
        OR e.data_type IS DISTINCT FROM s.data_type) AS schema_mismatch
    FROM expected_schema e FULL OUTER JOIN source_schema s USING (ordinal_position)
), source_rows AS MATERIALIZED (
    SELECT timestamp AS original_timestamp,TRY_CAST(timestamp AS BIGINT) AS timestamp_ms,
        CAST(property AS VARCHAR) AS property_name
    FROM rr_stg.item_state_observations
), source_health AS (
    SELECT COUNT(*) AS observation_rows,
        COUNT(*) FILTER (WHERE original_timestamp IS NULL) AS missing_timestamp_rows,
        COUNT(*) FILTER (WHERE timestamp_ms<0) AS negative_timestamp_rows,
        COUNT(*) FILTER (WHERE original_timestamp IS NOT NULL
            AND (timestamp_ms IS NULL OR timestamp_ms>e.max_supported_ms)) AS unsupported_epoch_ms_rows,
        COUNT(*) FILTER (WHERE property_name='categoryid') AS categoryid_rows,
        COUNT(*) FILTER (WHERE property_name='available') AS available_rows
    FROM source_rows CROSS JOIN expected_counts e
), admission AS MATERIALIZED (
    SELECT s.*,h.*,e.*,COALESCE(s.schema_mismatch=0 AND h.observation_rows=e.expected_rows
        AND h.observation_rows>0 AND h.missing_timestamp_rows=0 AND h.negative_timestamp_rows=0
        AND h.unsupported_epoch_ms_rows=0 AND h.categoryid_rows=e.expected_category_rows
        AND h.available_rows=e.expected_available_rows,false) AS admitted
    FROM schema_stats s CROSS JOIN source_health h CROSS JOIN expected_counts e
), converted AS MATERIALIZED (
    SELECT r.timestamp_ms,
        CASE WHEN a.admitted THEN make_timestamp_ms(r.timestamp_ms) END AS observation_ts
    FROM source_rows r CROSS JOIN admission a
), conversion_health AS (
    SELECT COUNT(*) FILTER (WHERE observation_ts IS NOT NULL) AS converted_rows,
        COUNT(*) FILTER (WHERE observation_ts IS NULL) AS conversion_null_rows,
        COUNT(*) FILTER (WHERE epoch_ms(observation_ts) IS DISTINCT FROM timestamp_ms) AS roundtrip_error_rows,
        COUNT(*) FILTER (WHERE epoch_ms(CAST(CAST(observation_ts AS DATE) AS TIMESTAMP))
            IS DISTINCT FROM (timestamp_ms // 86400000::BIGINT)*86400000::BIGINT) AS date_partition_error_rows,
        MIN(timestamp_ms) AS min_timestamp_ms,MAX(timestamp_ms) AS max_timestamp_ms,
        MIN(observation_ts) AS first_timestamp,MAX(observation_ts) AS last_timestamp,
        COUNT(DISTINCT CAST(observation_ts AS DATE)) AS distinct_utc_dates,
        COUNT(*) FILTER (WHERE timestamp_ms % 1000<>0) AS subsecond_observation_rows
    FROM converted
), daily_counts AS (
    SELECT CAST(observation_ts AS DATE) AS utc_date,COUNT(*) AS observation_rows
    FROM converted WHERE observation_ts IS NOT NULL GROUP BY CAST(observation_ts AS DATE)
), date_summary AS (
    SELECT COALESCE(SUM(d.observation_rows),0)::BIGINT AS daily_total_rows,
        COALESCE(SUM(d.observation_rows) FILTER (WHERE d.utc_date=CAST(h.first_timestamp AS DATE)),0)::BIGINT AS first_date_observation_rows,
        COALESCE(SUM(d.observation_rows) FILTER (WHERE d.utc_date=CAST(h.last_timestamp AS DATE)),0)::BIGINT AS last_date_observation_rows
    FROM daily_counts d CROSS JOIN conversion_health h
), metrics AS MATERIALIZED (
    SELECT a.*,h.*,d.*,a.admitted AND h.converted_rows=a.observation_rows AND h.conversion_null_rows=0
        AND h.roundtrip_error_rows=0 AND h.date_partition_error_rows=0 AS conversion_valid
    FROM admission a CROSS JOIN conversion_health h CROSS JOIN date_summary d
), final_metrics AS (
    SELECT *,conversion_valid AND daily_total_rows=observation_rows
        AND categoryid_rows=expected_category_rows AND available_rows=expected_available_rows AS all_controls_valid
    FROM metrics
), report AS (
    SELECT 1 AS check_order,'observation_rows' AS check_name,observation_rows::VARCHAR AS actual,expected_rows::VARCHAR AS expected FROM final_metrics
    UNION ALL SELECT 2,'schema_mismatch',schema_mismatch::VARCHAR,'0' FROM final_metrics
    UNION ALL SELECT 3,'missing_timestamp_rows',missing_timestamp_rows::VARCHAR,'0' FROM final_metrics
    UNION ALL SELECT 4,'negative_timestamp_rows',negative_timestamp_rows::VARCHAR,'0' FROM final_metrics
    UNION ALL SELECT 5,'unsupported_epoch_ms_rows',unsupported_epoch_ms_rows::VARCHAR,'0' FROM final_metrics
    UNION ALL SELECT 6,'converted_rows',CASE WHEN admitted THEN converted_rows::VARCHAR END,expected_rows::VARCHAR FROM final_metrics
    UNION ALL SELECT 7,'conversion_null_rows',CASE WHEN admitted THEN conversion_null_rows::VARCHAR END,'0' FROM final_metrics
    UNION ALL SELECT 8,'roundtrip_error_rows',CASE WHEN admitted THEN roundtrip_error_rows::VARCHAR END,'0' FROM final_metrics
    UNION ALL SELECT 9,'date_partition_error_rows',CASE WHEN admitted THEN date_partition_error_rows::VARCHAR END,'0' FROM final_metrics
    UNION ALL SELECT 10,'daily_rows_difference',CASE WHEN conversion_valid THEN (daily_total_rows-observation_rows)::VARCHAR END,'0' FROM final_metrics
    UNION ALL SELECT 11,'categoryid_rows',categoryid_rows::VARCHAR,expected_category_rows::VARCHAR FROM final_metrics
    UNION ALL SELECT 12,'available_rows',available_rows::VARCHAR,expected_available_rows::VARCHAR FROM final_metrics
    UNION ALL SELECT 13,'min_timestamp_ms',CASE WHEN all_controls_valid THEN min_timestamp_ms::VARCHAR END,NULL::VARCHAR FROM final_metrics
    UNION ALL SELECT 14,'max_timestamp_ms',CASE WHEN all_controls_valid THEN max_timestamp_ms::VARCHAR END,NULL::VARCHAR FROM final_metrics
    UNION ALL SELECT 15,'first_utc_timestamp',CASE WHEN all_controls_valid THEN strftime(first_timestamp,'%Y-%m-%dT%H:%M:%S.%fZ') END,NULL::VARCHAR FROM final_metrics
    UNION ALL SELECT 16,'last_utc_timestamp',CASE WHEN all_controls_valid THEN strftime(last_timestamp,'%Y-%m-%dT%H:%M:%S.%fZ') END,NULL::VARCHAR FROM final_metrics
    UNION ALL SELECT 17,'distinct_utc_dates',CASE WHEN all_controls_valid THEN distinct_utc_dates::VARCHAR END,NULL::VARCHAR FROM final_metrics
    UNION ALL SELECT 18,'first_date_observation_rows',CASE WHEN all_controls_valid THEN first_date_observation_rows::VARCHAR END,NULL::VARCHAR FROM final_metrics
    UNION ALL SELECT 19,'last_date_observation_rows',CASE WHEN all_controls_valid THEN last_date_observation_rows::VARCHAR END,NULL::VARCHAR FROM final_metrics
    UNION ALL SELECT 20,'subsecond_observation_rows',CASE WHEN all_controls_valid THEN subsecond_observation_rows::VARCHAR END,NULL::VARCHAR FROM final_metrics
)
SELECT check_order,check_name,actual,expected,
    CASE WHEN actual IS NULL THEN 'BLOCKED' WHEN expected IS NULL THEN 'INFO'
         WHEN actual=expected THEN 'PASS' ELSE 'FAIL' END AS status
FROM report ORDER BY check_order;
