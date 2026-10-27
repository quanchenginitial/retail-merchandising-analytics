-- Run once after all raw calendar checks pass. The raw table is unchanged.
-- This staging table keeps the 14 source fields and all 1,969 calendar dates.
-- CAST fails on conversion errors instead of silently replacing them with NULL.
-- Existing tables are not replaced. Core dimension keys are a later step.
CREATE SCHEMA IF NOT EXISTS stg;

CREATE TABLE stg.m5_calendar AS
SELECT
    CAST("date" AS DATE) AS "date",
    CAST(wm_yr_wk AS INTEGER) AS wm_yr_wk,
    weekday,
    CAST(wday AS INTEGER) AS wday,
    CAST(month AS INTEGER) AS month,
    CAST(year AS INTEGER) AS year,
    d,
    event_name_1, event_type_1, event_name_2, event_type_2,
    CAST(snap_CA AS INTEGER) AS snap_CA,
    CAST(snap_TX AS INTEGER) AS snap_TX,
    CAST(snap_WI AS INTEGER) AS snap_WI
FROM raw.m5_calendar;

-- VALIDATION: if the staging table already exists, run only the query below.
WITH expected_schema(column_name, data_type, ordinal_position) AS (
    VALUES ('date','DATE',1), ('wm_yr_wk','INTEGER',2), ('weekday','VARCHAR',3),
           ('wday','INTEGER',4), ('month','INTEGER',5), ('year','INTEGER',6),
           ('d','VARCHAR',7), ('event_name_1','VARCHAR',8), ('event_type_1','VARCHAR',9),
           ('event_name_2','VARCHAR',10), ('event_type_2','VARCHAR',11),
           ('snap_CA','INTEGER',12), ('snap_TX','INTEGER',13), ('snap_WI','INTEGER',14)
), actual_schema AS (
    SELECT column_name, data_type, ordinal_position
    FROM information_schema.columns
    WHERE table_catalog = current_database()
      AND table_schema = 'stg' AND table_name = 'm5_calendar'
), schema_errors AS (
    SELECT COUNT(*) AS error_count
    FROM expected_schema e FULL OUTER JOIN actual_schema a ON e.column_name = a.column_name
    WHERE e.column_name IS NULL OR a.column_name IS NULL
       OR e.data_type IS DISTINCT FROM a.data_type
       OR e.ordinal_position IS DISTINCT FROM a.ordinal_position
), raw_rows AS (
    SELECT "date", wm_yr_wk, weekday, wday, month, year, d,
           event_name_1, event_type_1, event_name_2, event_type_2, snap_CA, snap_TX, snap_WI
    FROM raw.m5_calendar
), staging_as_text AS (
    SELECT CAST("date" AS VARCHAR) AS "date", CAST(wm_yr_wk AS VARCHAR) AS wm_yr_wk,
           weekday, CAST(wday AS VARCHAR) AS wday, CAST(month AS VARCHAR) AS month,
           CAST(year AS VARCHAR) AS year, d,
           event_name_1, event_type_1, event_name_2, event_type_2,
           CAST(snap_CA AS VARCHAR) AS snap_CA, CAST(snap_TX AS VARCHAR) AS snap_TX,
           CAST(snap_WI AS VARCHAR) AS snap_WI
    FROM stg.m5_calendar
), raw_only AS (
    SELECT * FROM raw_rows EXCEPT ALL SELECT * FROM staging_as_text
), staging_only AS (
    SELECT * FROM staging_as_text EXCEPT ALL SELECT * FROM raw_rows
), stats AS (
    SELECT COUNT(*) AS staging_rows,
           COUNT(DISTINCT "date") AS distinct_dates,
           COUNT(DISTINCT d) AS distinct_day_ids,
           COUNT(*) FILTER (WHERE "date" IS NULL OR wm_yr_wk IS NULL OR
               NULLIF(TRIM(weekday),'') IS NULL OR wday IS NULL OR month IS NULL OR year IS NULL OR
               NULLIF(TRIM(d),'') IS NULL OR snap_CA IS NULL OR snap_TX IS NULL OR snap_WI IS NULL
           ) AS missing_core_rows,
           MIN("date") AS first_date, MAX("date") AS last_date,
           COUNT(*) FILTER (WHERE snap_CA IS NULL OR snap_CA NOT IN (0,1) OR
               snap_TX IS NULL OR snap_TX NOT IN (0,1) OR snap_WI IS NULL OR snap_WI NOT IN (0,1)
           ) AS invalid_snap_rows,
           COUNT(*) FILTER (WHERE event_name_1 IS NULL) AS event_1_nulls,
           COUNT(*) FILTER (WHERE event_name_2 IS NULL) AS event_2_nulls
    FROM stg.m5_calendar
), checks AS (
    SELECT 1 AS check_order, 'staging_rows' AS check_name, staging_rows::VARCHAR AS actual, '1969' AS expected FROM stats
    UNION ALL SELECT 2, 'column_count', COUNT(*)::VARCHAR, '14' FROM actual_schema
    UNION ALL SELECT 3, 'schema_mismatch_count', error_count::VARCHAR, '0' FROM schema_errors
    UNION ALL SELECT 4, 'distinct_dates', distinct_dates::VARCHAR, '1969' FROM stats
    UNION ALL SELECT 5, 'distinct_day_ids', distinct_day_ids::VARCHAR, '1969' FROM stats
    UNION ALL SELECT 6, 'missing_core_rows', missing_core_rows::VARCHAR, '0' FROM stats
    UNION ALL SELECT 7, 'first_date', first_date::VARCHAR, '2011-01-29' FROM stats
    UNION ALL SELECT 8, 'last_date', last_date::VARCHAR, '2016-06-19' FROM stats
    UNION ALL SELECT 9, 'invalid_snap_rows', invalid_snap_rows::VARCHAR, '0' FROM stats
    UNION ALL SELECT 10, 'event_1_nulls', event_1_nulls::VARCHAR, '1807' FROM stats
    UNION ALL SELECT 11, 'event_2_nulls', event_2_nulls::VARCHAR, '1964' FROM stats
    UNION ALL SELECT 12, 'raw_only_rows', COUNT(*)::VARCHAR, '0' FROM raw_only
    UNION ALL SELECT 13, 'staging_only_rows', COUNT(*)::VARCHAR, '0' FROM staging_only
)
SELECT check_order, check_name, actual, expected,
       CASE WHEN actual = expected THEN 'PASS' ELSE 'FAIL' END AS status
FROM checks ORDER BY check_order;
