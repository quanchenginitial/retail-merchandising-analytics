-- Purpose: a unique day/date/retail-week lookup for sales trends and later price joins.
-- Keep all 14 accepted source fields and all 1,969 dates; append INTEGER day_number.
-- The last 28 dates have no observed sales in this snapshot. Never create zero sales for them.
-- Source wm_yr_wk and wday retain their original meaning; no ISO-week substitution.
-- Key uniqueness is validated, not enforced by a declared PRIMARY KEY.
CREATE SCHEMA IF NOT EXISTS core;

CREATE TABLE core.m5_calendar AS
WITH source_days AS MATERIALIZED (
    SELECT *,TRY_CAST(SUBSTR(d,3) AS INTEGER) AS day_number FROM stg.m5_calendar
), invalid_days AS (
    SELECT * FROM source_days
    WHERE "date" IS NULL OR wm_yr_wk IS NULL OR NULLIF(TRIM(weekday),'') IS NULL
       OR wday IS NULL OR month IS NULL OR year IS NULL
       OR snap_CA IS NULL OR snap_TX IS NULL OR snap_WI IS NULL
       OR NOT COALESCE(regexp_full_match(d,'d_[1-9][0-9]*')
           AND day_number BETWEEN 1 AND 1969
           AND day_number=date_diff('day',DATE '2011-01-29',"date")+1,false)
), duplicate_days AS (
    SELECT d FROM source_days GROUP BY d HAVING COUNT(*)>1
), duplicate_dates AS (
    SELECT "date" FROM source_days GROUP BY "date" HAVING COUNT(*)>1
)
SELECT "date",wm_yr_wk,weekday,wday,month,year,
    CASE WHEN NOT EXISTS (SELECT 1 FROM invalid_days)
              AND NOT EXISTS (SELECT 1 FROM duplicate_days)
              AND NOT EXISTS (SELECT 1 FROM duplicate_dates)
         THEN d ELSE error('Calendar requires complete core fields, unique day/date keys and canonical d_1..d_1969 date mapping')
    END AS d,
    event_name_1,event_type_1,event_name_2,event_type_2,snap_CA,snap_TX,snap_WI,day_number
FROM source_days;

-- VALIDATION: if core.m5_calendar already exists, run only the query below.
WITH expected_schema(column_name,data_type,ordinal_position) AS (
    VALUES ('date','DATE',1),('wm_yr_wk','INTEGER',2),('weekday','VARCHAR',3),
           ('wday','INTEGER',4),('month','INTEGER',5),('year','INTEGER',6),
           ('d','VARCHAR',7),('event_name_1','VARCHAR',8),('event_type_1','VARCHAR',9),
           ('event_name_2','VARCHAR',10),('event_type_2','VARCHAR',11),
           ('snap_CA','INTEGER',12),('snap_TX','INTEGER',13),('snap_WI','INTEGER',14),
           ('day_number','INTEGER',15)
), actual_schema AS (
    SELECT column_name,data_type,ordinal_position FROM information_schema.columns
    WHERE table_catalog=current_database() AND table_schema='core' AND table_name='m5_calendar'
), schema_errors AS (
    SELECT COUNT(*) AS error_count
    FROM expected_schema e FULL OUTER JOIN actual_schema a USING (column_name)
    WHERE e.column_name IS NULL OR a.column_name IS NULL
       OR e.data_type IS DISTINCT FROM a.data_type
       OR e.ordinal_position IS DISTINCT FROM a.ordinal_position
), dimension_stats AS (
    SELECT COUNT(*) AS calendar_rows,COUNT(DISTINCT "date") AS distinct_dates,
        COUNT(DISTINCT d) AS distinct_day_ids,COUNT(DISTINCT day_number) AS distinct_day_numbers,
        COUNT(*) FILTER (WHERE "date" IS NULL OR wm_yr_wk IS NULL
            OR NULLIF(TRIM(weekday),'') IS NULL OR wday IS NULL OR month IS NULL OR year IS NULL
            OR NULLIF(TRIM(d),'') IS NULL OR snap_CA IS NULL OR snap_TX IS NULL OR snap_WI IS NULL
            OR day_number IS NULL) AS missing_core_rows,
        COUNT(*) FILTER (WHERE NOT COALESCE(regexp_full_match(d,'d_[1-9][0-9]*')
            AND day_number BETWEEN 1 AND 1969
            AND day_number=TRY_CAST(SUBSTR(d,3) AS INTEGER)
            AND day_number=date_diff('day',DATE '2011-01-29',"date")+1,false)) AS invalid_day_mapping_rows,
        MIN("date") AS first_date,MAX("date") AS last_date,
        COUNT(DISTINCT wm_yr_wk) AS distinct_weeks,
        COUNT(*) FILTER (WHERE day_number BETWEEN 1 AND 1941) AS observed_sales_days,
        COUNT(*) FILTER (WHERE day_number BETWEEN 1942 AND 1969) AS post_observation_days,
        MAX("date") FILTER (WHERE day_number BETWEEN 1 AND 1941) AS observed_last_date
    FROM core.m5_calendar
), staging_rows AS (
    SELECT "date",wm_yr_wk,weekday,wday,month,year,d,
        event_name_1,event_type_1,event_name_2,event_type_2,snap_CA,snap_TX,snap_WI
    FROM stg.m5_calendar
), core_source_fields AS (
    SELECT "date",wm_yr_wk,weekday,wday,month,year,d,
        event_name_1,event_type_1,event_name_2,event_type_2,snap_CA,snap_TX,snap_WI
    FROM core.m5_calendar
), stg_only AS (
    SELECT * FROM staging_rows EXCEPT ALL SELECT * FROM core_source_fields
), core_only AS (
    SELECT * FROM core_source_fields EXCEPT ALL SELECT * FROM staging_rows
), source_keys AS (
    SELECT DISTINCT d FROM stg.m5_calendar
), key_join_errors AS (
    SELECT s.d FROM source_keys s LEFT JOIN core.m5_calendar c ON s.d=c.d
    GROUP BY s.d HAVING COUNT(c.d)<>1
), checks AS (
    SELECT 1 AS check_order,'calendar_rows' AS check_name,calendar_rows::VARCHAR AS actual,'1969' AS expected FROM dimension_stats
    UNION ALL SELECT 2,'column_count',COUNT(*)::VARCHAR,'15' FROM actual_schema
    UNION ALL SELECT 3,'schema_mismatch_count',error_count::VARCHAR,'0' FROM schema_errors
    UNION ALL SELECT 4,'distinct_dates',distinct_dates::VARCHAR,'1969' FROM dimension_stats
    UNION ALL SELECT 5,'distinct_day_ids',distinct_day_ids::VARCHAR,'1969' FROM dimension_stats
    UNION ALL SELECT 6,'distinct_day_numbers',distinct_day_numbers::VARCHAR,'1969' FROM dimension_stats
    UNION ALL SELECT 7,'missing_core_rows',missing_core_rows::VARCHAR,'0' FROM dimension_stats
    UNION ALL SELECT 8,'invalid_day_mapping_rows',invalid_day_mapping_rows::VARCHAR,'0' FROM dimension_stats
    UNION ALL SELECT 9,'first_date',first_date::VARCHAR,'2011-01-29' FROM dimension_stats
    UNION ALL SELECT 10,'last_date',last_date::VARCHAR,'2016-06-19' FROM dimension_stats
    UNION ALL SELECT 11,'distinct_weeks',distinct_weeks::VARCHAR,'282' FROM dimension_stats
    UNION ALL SELECT 12,'observed_sales_days',observed_sales_days::VARCHAR,'1941' FROM dimension_stats
    UNION ALL SELECT 13,'post_observation_days',post_observation_days::VARCHAR,'28' FROM dimension_stats
    UNION ALL SELECT 14,'observed_last_date',observed_last_date::VARCHAR,'2016-05-22' FROM dimension_stats
    UNION ALL SELECT 15,'stg_only_rows',COUNT(*)::VARCHAR,'0' FROM stg_only
    UNION ALL SELECT 16,'core_only_rows',COUNT(*)::VARCHAR,'0' FROM core_only
    UNION ALL SELECT 17,'source_key_join_errors',COUNT(*)::VARCHAR,'0' FROM key_join_errors
)
SELECT check_order,check_name,actual,expected,
    CASE WHEN actual=expected THEN 'PASS' ELSE 'FAIL' END AS status
FROM checks ORDER BY check_order;
