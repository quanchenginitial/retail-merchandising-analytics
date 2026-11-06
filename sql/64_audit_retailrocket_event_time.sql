-- Read-only audit of integer Unix milliseconds in rr_stg.events.
-- Converted TIMESTAMP values use an explicit UTC convention, not a local business timezone.
-- All observations and duplicates remain unchanged; no session or order inference.
WITH expected_counts AS (
    SELECT 2756101::BIGINT AS expected_rows,
        1430622004384::BIGINT AS expected_min_ms,1442545187788::BIGINT AS expected_max_ms,
        '2015-05-03T03:00:04.384000Z'::VARCHAR AS expected_first_utc,
        '2015-09-18T02:59:47.788000Z'::VARCHAR AS expected_last_utc,
        139::BIGINT AS expected_dates,253402300799999::BIGINT AS max_supported_ms
), expected_schema(column_name,data_type,ordinal_position) AS (
    VALUES ('timestamp','BIGINT',1),('visitorid','BIGINT',2),('event','VARCHAR',3),
        ('itemid','BIGINT',4),('transactionid','BIGINT',5)
), source_schema AS (
    SELECT column_name,data_type,ordinal_position FROM information_schema.columns
    WHERE table_catalog=current_database() AND table_schema='rr_stg' AND table_name='events'
), schema_stats AS (
    SELECT COUNT(*) FILTER (WHERE e.column_name IS DISTINCT FROM s.column_name
        OR e.data_type IS DISTINCT FROM s.data_type) AS schema_mismatch
    FROM expected_schema e FULL OUTER JOIN source_schema s USING (ordinal_position)
), source_rows AS MATERIALIZED (
    SELECT timestamp AS original_timestamp,TRY_CAST(timestamp AS BIGINT) AS timestamp_ms
    FROM rr_stg.events
), source_health AS (
    SELECT COUNT(*) AS event_rows,
        COUNT(*) FILTER (WHERE original_timestamp IS NULL) AS missing_timestamp_rows,
        COUNT(*) FILTER (WHERE timestamp_ms<0) AS negative_timestamp_rows,
        COUNT(*) FILTER (WHERE original_timestamp IS NOT NULL
            AND (timestamp_ms IS NULL OR timestamp_ms>e.max_supported_ms)) AS unsupported_epoch_ms_rows
    FROM source_rows CROSS JOIN expected_counts e
), admission AS MATERIALIZED (
    SELECT s.*,h.*,e.*,COALESCE(s.schema_mismatch=0 AND h.event_rows=e.expected_rows
        AND h.event_rows>0 AND h.missing_timestamp_rows=0 AND h.negative_timestamp_rows=0
        AND h.unsupported_epoch_ms_rows=0,false) AS admitted
    FROM schema_stats s CROSS JOIN source_health h CROSS JOIN expected_counts e
), converted AS MATERIALIZED (
    SELECT r.timestamp_ms,
        CASE WHEN a.admitted THEN make_timestamp_ms(r.timestamp_ms) END AS event_ts
    FROM source_rows r CROSS JOIN admission a
), conversion_health AS (
    SELECT COUNT(*) FILTER (WHERE event_ts IS NOT NULL) AS converted_rows,
        COUNT(*) FILTER (WHERE event_ts IS NULL) AS conversion_null_rows,
        COUNT(*) FILTER (WHERE epoch_ms(event_ts) IS DISTINCT FROM timestamp_ms) AS roundtrip_error_rows,
        COUNT(*) FILTER (WHERE epoch_ms(CAST(CAST(event_ts AS DATE) AS TIMESTAMP))
            IS DISTINCT FROM (timestamp_ms // 86400000::BIGINT)*86400000::BIGINT) AS date_partition_error_rows,
        MIN(timestamp_ms) AS min_timestamp_ms,MAX(timestamp_ms) AS max_timestamp_ms,
        MIN(event_ts) AS first_timestamp,MAX(event_ts) AS last_timestamp,
        COUNT(DISTINCT CAST(event_ts AS DATE)) AS distinct_utc_dates,
        COUNT(*) FILTER (WHERE timestamp_ms % 1000<>0) AS subsecond_event_rows
    FROM converted
), daily_counts AS (
    SELECT CAST(event_ts AS DATE) AS utc_date,COUNT(*) AS event_rows
    FROM converted WHERE event_ts IS NOT NULL GROUP BY CAST(event_ts AS DATE)
), date_summary AS (
    SELECT COALESCE(SUM(d.event_rows),0)::BIGINT AS daily_total_rows,
        COALESCE(SUM(d.event_rows) FILTER (WHERE d.utc_date=CAST(h.first_timestamp AS DATE)),0)::BIGINT AS first_date_event_rows,
        COALESCE(SUM(d.event_rows) FILTER (WHERE d.utc_date=CAST(h.last_timestamp AS DATE)),0)::BIGINT AS last_date_event_rows
    FROM daily_counts d CROSS JOIN conversion_health h
), metrics AS MATERIALIZED (
    SELECT a.*,h.*,d.*,a.admitted AND h.converted_rows=a.event_rows AND h.conversion_null_rows=0
        AND h.roundtrip_error_rows=0 AND h.date_partition_error_rows=0 AS conversion_valid
    FROM admission a CROSS JOIN conversion_health h CROSS JOIN date_summary d
), final_metrics AS (
    SELECT *,conversion_valid AND min_timestamp_ms=expected_min_ms AND max_timestamp_ms=expected_max_ms
        AND strftime(first_timestamp,'%Y-%m-%dT%H:%M:%S.%fZ')=expected_first_utc
        AND strftime(last_timestamp,'%Y-%m-%dT%H:%M:%S.%fZ')=expected_last_utc
        AND distinct_utc_dates=expected_dates AND daily_total_rows=event_rows AS all_controls_valid
    FROM metrics
), report AS (
    SELECT 1 AS check_order,'event_rows' AS check_name,event_rows::VARCHAR AS actual,expected_rows::VARCHAR AS expected FROM final_metrics
    UNION ALL SELECT 2,'schema_mismatch',schema_mismatch::VARCHAR,'0' FROM final_metrics
    UNION ALL SELECT 3,'missing_timestamp_rows',missing_timestamp_rows::VARCHAR,'0' FROM final_metrics
    UNION ALL SELECT 4,'negative_timestamp_rows',negative_timestamp_rows::VARCHAR,'0' FROM final_metrics
    UNION ALL SELECT 5,'unsupported_epoch_ms_rows',unsupported_epoch_ms_rows::VARCHAR,'0' FROM final_metrics
    UNION ALL SELECT 6,'converted_rows',CASE WHEN admitted THEN converted_rows::VARCHAR END,expected_rows::VARCHAR FROM final_metrics
    UNION ALL SELECT 7,'conversion_null_rows',CASE WHEN admitted THEN conversion_null_rows::VARCHAR END,'0' FROM final_metrics
    UNION ALL SELECT 8,'roundtrip_error_rows',CASE WHEN admitted THEN roundtrip_error_rows::VARCHAR END,'0' FROM final_metrics
    UNION ALL SELECT 9,'date_partition_error_rows',CASE WHEN admitted THEN date_partition_error_rows::VARCHAR END,'0' FROM final_metrics
    UNION ALL SELECT 10,'min_timestamp_ms',CASE WHEN conversion_valid THEN min_timestamp_ms::VARCHAR END,expected_min_ms::VARCHAR FROM final_metrics
    UNION ALL SELECT 11,'max_timestamp_ms',CASE WHEN conversion_valid THEN max_timestamp_ms::VARCHAR END,expected_max_ms::VARCHAR FROM final_metrics
    UNION ALL SELECT 12,'first_utc_timestamp',CASE WHEN conversion_valid THEN strftime(first_timestamp,'%Y-%m-%dT%H:%M:%S.%fZ') END,expected_first_utc FROM final_metrics
    UNION ALL SELECT 13,'last_utc_timestamp',CASE WHEN conversion_valid THEN strftime(last_timestamp,'%Y-%m-%dT%H:%M:%S.%fZ') END,expected_last_utc FROM final_metrics
    UNION ALL SELECT 14,'distinct_utc_dates',CASE WHEN conversion_valid THEN distinct_utc_dates::VARCHAR END,expected_dates::VARCHAR FROM final_metrics
    UNION ALL SELECT 15,'daily_rows_difference',CASE WHEN conversion_valid THEN (daily_total_rows-event_rows)::VARCHAR END,'0' FROM final_metrics
    UNION ALL SELECT 16,'first_date_event_rows',CASE WHEN all_controls_valid THEN first_date_event_rows::VARCHAR END,NULL::VARCHAR FROM final_metrics
    UNION ALL SELECT 17,'last_date_event_rows',CASE WHEN all_controls_valid THEN last_date_event_rows::VARCHAR END,NULL::VARCHAR FROM final_metrics
    UNION ALL SELECT 18,'subsecond_event_rows',CASE WHEN all_controls_valid THEN subsecond_event_rows::VARCHAR END,NULL::VARCHAR FROM final_metrics
)
SELECT check_order,check_name,actual,expected,
    CASE WHEN actual IS NULL THEN 'BLOCKED' WHEN expected IS NULL THEN 'INFO'
         WHEN actual=expected THEN 'PASS' ELSE 'FAIL' END AS status
FROM report ORDER BY check_order;
