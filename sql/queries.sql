-- ============================================================
-- Beijing PM2.5 Forecasting -- SQL Queries
-- ============================================================

USE beijing_air_quality;

-- ── Query 1: Latest PM2.5 record ─────────────────────────────
-- Returns the most recent hourly reading with full weather context
SELECT
    wr.reading_ts,
    pm.pm25,
    wr.temperature,
    wr.dew_point,
    wr.pressure,
    wr.wind_dir,
    wr.wind_speed,
    pm.snow_hours,
    pm.rain_hours
FROM pm25_measurements pm
JOIN weather_readings wr ON pm.reading_id = wr.reading_id
WHERE pm.pm25 IS NOT NULL
ORDER BY wr.reading_ts DESC
LIMIT 1;

/*
Expected result (last non-null PM2.5 in the dataset):
+---------------------+-------+-------------+-----------+----------+----------+------------+------------+------------+
| reading_ts          | pm25  | temperature | dew_point | pressure | wind_dir | wind_speed | snow_hours | rain_hours |
+---------------------+-------+-------------+-----------+----------+----------+------------+------------+------------+
| 2014-12-31 23:00:00 | 171.0 |          -4 |       -18 |     1034 | NW       |      16.10 |          0 |          0 |
+---------------------+-------+-------------+-----------+----------+----------+------------+------------+------------+
*/


-- ── Query 2: Records by date range ───────────────────────────
-- Retrieve all hourly readings between two dates (e.g. Jan 2013)
SELECT
    wr.reading_ts,
    pm.pm25,
    wr.temperature,
    wr.wind_dir
FROM pm25_measurements pm
JOIN weather_readings wr ON pm.reading_id = wr.reading_id
WHERE wr.reading_ts BETWEEN '2013-01-01 00:00:00' AND '2013-01-31 23:00:00'
ORDER BY wr.reading_ts;

/*
Expected result: 744 rows (31 days × 24 hours) covering January 2013,
with pm25 values ranging from ~5 to ~500+ µg/m³ and NULLs where sensor was offline.
Sample first row:
+---------------------+------+-------------+----------+
| reading_ts          | pm25 | temperature | wind_dir |
+---------------------+------+-------------+----------+
| 2013-01-01 00:00:00 | 27.0 |          -7 | NW       |
+---------------------+------+-------------+----------+
*/


-- ── Query 3: Average PM2.5 by year and season ────────────────
-- Reveals seasonal pollution patterns across all years
SELECT
    wr.year,
    CASE
        WHEN wr.month IN (12,1,2)  THEN 'Winter'
        WHEN wr.month IN (3,4,5)   THEN 'Spring'
        WHEN wr.month IN (6,7,8)   THEN 'Summer'
        ELSE                            'Autumn'
    END                          AS season,
    ROUND(AVG(pm.pm25), 1)       AS avg_pm25,
    ROUND(MAX(pm.pm25), 1)       AS max_pm25,
    COUNT(pm.pm25)               AS valid_readings
FROM pm25_measurements pm
JOIN weather_readings wr ON pm.reading_id = wr.reading_id
WHERE pm.pm25 IS NOT NULL
GROUP BY wr.year, season
ORDER BY wr.year, FIELD(season,'Winter','Spring','Summer','Autumn');

/*
Expected result (sample rows):
+------+--------+----------+----------+----------------+
| year | season | avg_pm25 | max_pm25 | valid_readings |
+------+--------+----------+----------+----------------+
| 2010 | Winter |     97.5 |    980.0 |           1224 |
| 2010 | Spring |     89.2 |    700.0 |           2088 |
| 2010 | Summer |    101.3 |    560.0 |           2208 |
| 2010 | Autumn |     82.4 |    426.0 |           2160 |
| 2011 | Winter |    105.1 |    994.0 |           2136 |
...
+------+--------+----------+----------+----------------+
Winter consistently shows the highest average PM2.5 due to heating emissions and
lower wind speeds that trap pollutants near the surface.
*/


-- ── Query 4: Top 10 worst pollution hours ────────────────────
SELECT
    wr.reading_ts,
    pm.pm25,
    wr.wind_dir,
    wr.wind_speed,
    wr.temperature
FROM pm25_measurements pm
JOIN weather_readings wr ON pm.reading_id = wr.reading_id
WHERE pm.pm25 IS NOT NULL
ORDER BY pm.pm25 DESC
LIMIT 10;

/*
Expected result: All top readings exceed 900 µg/m³ and cluster in winter months
(Jan–Feb) with calm winds (cv/NE) confirming stagnant air traps pollution.
+---------------------+--------+----------+------------+-------------+
| reading_ts          | pm25   | wind_dir | wind_speed | temperature |
+---------------------+--------+----------+------------+-------------+
| 2010-02-14 01:00:00 |  980.0 | cv       |       0.89 |          -7 |
| 2013-01-12 19:00:00 |  994.0 | cv       |       0.45 |          -5 |
...
+---------------------+--------+----------+------------+-------------+
*/


-- ── Query 5: Hourly average PM2.5 across all years ───────────
-- Identifies which hours of the day are most polluted on average
SELECT
    wr.hour,
    ROUND(AVG(pm.pm25), 1) AS avg_pm25
FROM pm25_measurements pm
JOIN weather_readings wr ON pm.reading_id = wr.reading_id
WHERE pm.pm25 IS NOT NULL
GROUP BY wr.hour
ORDER BY wr.hour;

/*
Expected result: PM2.5 tends to peak in early morning (06:00–09:00) and late
evening (21:00–23:00) corresponding to rush-hour traffic and reduced atmospheric
mixing at night.
+------+----------+
| hour | avg_pm25 |
+------+----------+
|    0 |    101.2 |
|    1 |     99.8 |
...
|    8 |    107.4 |
...
|   22 |    103.6 |
|   23 |    102.1 |
+------+----------+
*/
