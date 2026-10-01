-- 02_verify_load.sql
-- Quick checks after loading (MySQL). Expected results are in the comments.

-- Total rows (expect 315648)
SELECT COUNT(*) FROM energy_reading;

-- Date range (expect 2019-01-01 00:00 to 2021-12-31 23:55)
SELECT MIN(reading_time), MAX(reading_time) FROM energy_reading;

-- Readings per day should always be 288 (expect 0 rows returned)
SELECT DATE(reading_time) AS day, COUNT(*)
FROM energy_reading
GROUP BY day
HAVING COUNT(*) <> 288;

-- Rows per season (joins to the lookup table)
SELECT s.season_name, COUNT(*)
FROM energy_reading e
JOIN season s ON e.season_id = s.season_id
GROUP BY s.season_name
ORDER BY s.season_name;
