-- Run in the learner's new retail_merchandising DBeaver connection.
-- This query reads connection information only; it does not create tables.
SELECT
    current_database() AS database_name,
    version() AS duckdb_version;
