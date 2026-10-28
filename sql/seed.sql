-- ============================================================
-- Beijing PM2.5 Forecasting -- Seed & Load Data
-- Run AFTER schema.sql
-- ============================================================

USE beijing_air_quality;

-- ── 1. Insert the single monitoring station ──────────────────
INSERT INTO weather_stations (station_name, city, latitude, longitude)
VALUES ('PRSA Station', 'Beijing', 39.9042, 116.4074);

-- ── 2. Load CSV into a staging table ─────────────────────────
CREATE TABLE IF NOT EXISTS prsa_staging (
    row_no   INT,
    year     SMALLINT,
    month    TINYINT,
    day      TINYINT,
    hour     TINYINT,
    pm25     VARCHAR(10),   -- keep as string to handle 'NA'
    dewp     SMALLINT,
    temp     SMALLINT,
    pres     SMALLINT,
    cbwd     VARCHAR(5),
    iws      DECIMAL(7,2),
    is_snow  TINYINT,
    ir_rain  TINYINT
);

-- Adjust the path below to match your system if needed
LOAD DATA LOCAL INFILE 'data/PRSA_data_2010.1.1-2014.12.31.csv'
INTO TABLE prsa_staging
FIELDS TERMINATED BY ','
ENCLOSED BY '"'
LINES TERMINATED BY '\n'
IGNORE 1 ROWS
(row_no, year, month, day, hour, pm25, dewp, temp, pres, cbwd, iws, is_snow, ir_rain);

-- ── 3. Populate weather_readings from staging ─────────────────
INSERT INTO weather_readings
    (station_id, reading_ts, year, month, day, hour,
     dew_point, temperature, pressure, wind_dir, wind_speed)
SELECT
    1,
    TIMESTAMP(CONCAT(year,'-',LPAD(month,2,'0'),'-',LPAD(day,2,'0'),' ',LPAD(hour,2,'0'),':00:00')),
    year, month, day, hour,
    dewp, temp, pres, cbwd, iws
FROM prsa_staging;

-- ── 4. Populate pm25_measurements from staging ────────────────
INSERT INTO pm25_measurements (reading_id, pm25, snow_hours, rain_hours)
SELECT
    wr.reading_id,
    CASE WHEN s.pm25 = 'NA' THEN NULL ELSE CAST(s.pm25 AS FLOAT) END,
    s.is_snow,
    s.ir_rain
FROM prsa_staging s
JOIN weather_readings wr
  ON wr.year  = s.year
 AND wr.month = s.month
 AND wr.day   = s.day
 AND wr.hour  = s.hour
 AND wr.station_id = 1;

-- ── 5. Drop staging table ─────────────────────────────────────
DROP TABLE prsa_staging;
