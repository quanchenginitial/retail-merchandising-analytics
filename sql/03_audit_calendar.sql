-- Read-only audit of the learner's imported calendar.
-- Run as one statement in retail_merchandising. No tables are changed.
-- EXCEPT ALL compares all 14 fields, including NULLs and duplicate multiplicity.
WITH source_rows AS (
    SELECT * FROM read_csv(
        'D:/database/m5-forecasting-accuracy/calendar.csv',
        header = true, all_varchar = true
    )
), raw_rows AS (
    SELECT date, wm_yr_wk, weekday, wday, month, year, d,
           event_name_1, event_type_1, event_name_2, event_type_2,
           snap_CA, snap_TX, snap_WI
    FROM raw.m5_calendar
), typed AS (
    SELECT *, TRY_CAST(date AS DATE) AS parsed_date,
           TRY_CAST(SUBSTR(d, 3) AS INTEGER) AS day_number
    FROM raw_rows
), source_only AS (
    SELECT * FROM source_rows EXCEPT ALL SELECT * FROM raw_rows
), table_only AS (
    SELECT * FROM raw_rows EXCEPT ALL SELECT * FROM source_rows
), stats AS (
    SELECT
        COUNT(*) AS row_count,
        COUNT(*) FILTER (WHERE
            NULLIF(TRIM(date), '') IS NULL OR
            NULLIF(TRIM(wm_yr_wk), '') IS NULL OR
            NULLIF(TRIM(weekday), '') IS NULL OR
            NULLIF(TRIM(wday), '') IS NULL OR
            NULLIF(TRIM(month), '') IS NULL OR
            NULLIF(TRIM(year), '') IS NULL OR
            NULLIF(TRIM(d), '') IS NULL OR
            NULLIF(TRIM(snap_CA), '') IS NULL OR
            NULLIF(TRIM(snap_TX), '') IS NULL OR
            NULLIF(TRIM(snap_WI), '') IS NULL
        ) AS missing_core_rows,
        COUNT(*) FILTER (WHERE parsed_date IS NULL) AS invalid_dates,
        COUNT(date) - COUNT(DISTINCT date) AS duplicate_dates,
        COUNT(d) - COUNT(DISTINCT d) AS duplicate_day_ids,
        COUNT(*) FILTER (WHERE
            parsed_date IS NULL OR day_number IS NULL OR
            regexp_full_match(COALESCE(d, ''), 'd_[1-9][0-9]*') IS NOT TRUE OR
            day_number NOT BETWEEN 1 AND 1969 OR
            date_diff('day', DATE '2011-01-29', parsed_date)
                IS DISTINCT FROM (day_number - 1)
        ) AS day_date_mapping_errors,
        COUNT(*) FILTER (WHERE
            parsed_date IS NULL OR
            weekday IS DISTINCT FROM strftime(parsed_date, '%A') OR
            TRY_CAST(month AS INTEGER) IS DISTINCT FROM date_part('month', parsed_date) OR
            TRY_CAST(year AS INTEGER) IS DISTINCT FROM date_part('year', parsed_date) OR
            TRY_CAST(wday AS INTEGER) IS DISTINCT FROM
                ((date_part('isodow', parsed_date) + 1) % 7 + 1)
        ) AS calendar_attribute_errors,
        COUNT(*) FILTER (WHERE
            regexp_full_match(COALESCE(wm_yr_wk, ''), '[0-9]{5}') IS NOT TRUE
        ) AS invalid_week_codes,
        COUNT(DISTINCT wm_yr_wk) AS distinct_weeks,
        COUNT(*) FILTER (WHERE
            COALESCE(snap_CA, '') NOT IN ('0', '1') OR
            COALESCE(snap_TX, '') NOT IN ('0', '1') OR
            COALESCE(snap_WI, '') NOT IN ('0', '1')
        ) AS invalid_snap_rows,
        COUNT(*) FILTER (WHERE (event_name_1 IS NULL) <> (event_type_1 IS NULL))
            AS event_1_pair_errors,
        COUNT(*) FILTER (WHERE (event_name_2 IS NULL) <> (event_type_2 IS NULL))
            AS event_2_pair_errors,
        COUNT(*) FILTER (WHERE event_name_1 IS NULL) AS event_1_nulls,
        COUNT(*) FILTER (WHERE event_name_2 IS NULL) AS event_2_nulls
    FROM typed
), checks AS (
    SELECT 1 AS check_order, 'source_rows' AS check_name,
           (SELECT COUNT(*) FROM source_rows) AS actual, 1969 AS expected
    UNION ALL SELECT 2, 'table_rows', row_count, 1969 FROM stats
    UNION ALL SELECT 3, 'missing_core_rows', missing_core_rows, 0 FROM stats
    UNION ALL SELECT 4, 'invalid_dates', invalid_dates, 0 FROM stats
    UNION ALL SELECT 5, 'duplicate_dates', duplicate_dates, 0 FROM stats
    UNION ALL SELECT 6, 'duplicate_day_ids', duplicate_day_ids, 0 FROM stats
    UNION ALL SELECT 7, 'day_date_mapping_errors', day_date_mapping_errors, 0 FROM stats
    UNION ALL SELECT 8, 'calendar_attribute_errors', calendar_attribute_errors, 0 FROM stats
    UNION ALL SELECT 9, 'invalid_week_codes', invalid_week_codes, 0 FROM stats
    UNION ALL SELECT 10, 'distinct_weeks', distinct_weeks, 282 FROM stats
    UNION ALL SELECT 11, 'invalid_snap_rows', invalid_snap_rows, 0 FROM stats
    UNION ALL SELECT 12, 'event_1_pair_errors', event_1_pair_errors, 0 FROM stats
    UNION ALL SELECT 13, 'event_2_pair_errors', event_2_pair_errors, 0 FROM stats
    UNION ALL SELECT 14, 'event_1_nulls', event_1_nulls, 1807 FROM stats
    UNION ALL SELECT 15, 'event_2_nulls', event_2_nulls, 1964 FROM stats
    UNION ALL SELECT 16, 'source_only_rows', (SELECT COUNT(*) FROM source_only), 0
    UNION ALL SELECT 17, 'table_only_rows', (SELECT COUNT(*) FROM table_only), 0
)
SELECT check_order, check_name, actual, expected,
       CASE WHEN actual = expected THEN 'PASS' ELSE 'FAIL' END AS status
FROM checks
ORDER BY check_order;
