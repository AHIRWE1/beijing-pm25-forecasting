-- ============================================================
-- Beijing PM2.5 Forecasting -- Relational Database Schema
-- ============================================================

CREATE DATABASE IF NOT EXISTS beijing_air_quality;
USE beijing_air_quality;

-- Table 1: weather_stations
-- Stores static metadata about the monitoring station
CREATE TABLE weather_stations (
    station_id   INT           NOT NULL AUTO_INCREMENT,
    station_name VARCHAR(100)  NOT NULL,
    city         VARCHAR(100)  NOT NULL DEFAULT 'Beijing',
    latitude     DECIMAL(9,6)  NULL,
    longitude    DECIMAL(9,6)  NULL,
    PRIMARY KEY (station_id)
);

-- Table 2: weather_readings
-- Hourly meteorological conditions
CREATE TABLE weather_readings (
    reading_id   BIGINT        NOT NULL AUTO_INCREMENT,
    station_id   INT           NOT NULL,
    reading_ts   DATETIME      NOT NULL,          -- combined year/month/day/hour
    year         SMALLINT      NOT NULL,
    month        TINYINT       NOT NULL,
    day          TINYINT       NOT NULL,
    hour         TINYINT       NOT NULL,
    dew_point    SMALLINT      NOT NULL,          -- DEWP (°C)
    temperature  SMALLINT      NOT NULL,          -- TEMP (°C)
    pressure     SMALLINT      NOT NULL,          -- PRES (hPa)
    wind_dir     VARCHAR(5)    NOT NULL,          -- cbwd: NW/NE/SE/cv
    wind_speed   DECIMAL(7,2)  NOT NULL,          -- Iws (m/s cumulative)
    PRIMARY KEY (reading_id),
    UNIQUE KEY uq_station_ts (station_id, reading_ts),
    FOREIGN KEY (station_id) REFERENCES weather_stations(station_id),
    INDEX idx_reading_ts (reading_ts)
);

-- Table 3: pm25_measurements
-- Hourly PM2.5 and precipitation linked to a weather reading
CREATE TABLE pm25_measurements (
    measurement_id  BIGINT       NOT NULL AUTO_INCREMENT,
    reading_id      BIGINT       NOT NULL,
    pm25            FLOAT        NULL,            -- µg/m³; NULL when sensor offline
    snow_hours      TINYINT      NOT NULL DEFAULT 0,  -- Is: cumulative hours of snow
    rain_hours      TINYINT      NOT NULL DEFAULT 0,  -- Ir: cumulative hours of rain
    PRIMARY KEY (measurement_id),
    UNIQUE KEY uq_reading (reading_id),
    FOREIGN KEY (reading_id) REFERENCES weather_readings(reading_id),
    INDEX idx_pm25 (pm25)
);
