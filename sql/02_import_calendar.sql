-- Run once in the retail_merchandising DBeaver connection.
-- CSV is read-only. Existing tables are not replaced.
-- All source fields remain VARCHAR; empty CSV fields become SQL NULL.
CREATE SCHEMA IF NOT EXISTS raw;

CREATE TABLE raw.m5_calendar AS
SELECT *
FROM read_csv(
    'D:/database/m5-forecasting-accuracy/calendar.csv',
    header = true,
    all_varchar = true
);

-- On a repeat visit, run only this verification query if the table exists.
SELECT
    current_database() AS database_name,
    COUNT(*) AS row_count,
    (SELECT COUNT(*) FROM information_schema.columns
     WHERE table_catalog = current_database()
       AND table_schema = 'raw' AND table_name = 'm5_calendar') AS column_count,
    (SELECT COUNT(*) FROM information_schema.columns
     WHERE table_catalog = current_database()
       AND table_schema = 'raw' AND table_name = 'm5_calendar'
       AND data_type = 'VARCHAR') AS varchar_column_count,
    COUNT(DISTINCT d) AS distinct_day_ids,
    MIN(TRY_CAST(date AS DATE)) AS first_date,
    MAX(TRY_CAST(date AS DATE)) AS last_date
FROM raw.m5_calendar;
