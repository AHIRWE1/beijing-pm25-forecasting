# Entity Relationship Diagram — Beijing PM2.5 SQL Schema

```mermaid
erDiagram
    WEATHER_STATIONS {
        INT     station_id   PK
        VARCHAR station_name
        VARCHAR city
        DECIMAL latitude
        DECIMAL longitude
    }

    WEATHER_READINGS {
        BIGINT  reading_id   PK
        INT     station_id   FK
        DATETIME reading_ts
        SMALLINT year
        TINYINT  month
        TINYINT  day
        TINYINT  hour
        SMALLINT dew_point
        SMALLINT temperature
        SMALLINT pressure
        VARCHAR  wind_dir
        DECIMAL  wind_speed
    }

    PM25_MEASUREMENTS {
        BIGINT  measurement_id  PK
        BIGINT  reading_id      FK
        FLOAT   pm25
        TINYINT snow_hours
        TINYINT rain_hours
    }

    WEATHER_STATIONS  ||--o{ WEATHER_READINGS    : "has"
    WEATHER_READINGS  ||--||  PM25_MEASUREMENTS  : "has"
```

## Design Rationale

| Decision | Reason |
|---|---|
| `weather_stations` separated | Allows multiple stations to be added without schema changes |
| `weather_readings` separated from `pm25_measurements` | Weather sensors and PM2.5 sensors can fail independently; NULL handling is cleaner in a dedicated table |
| `reading_ts` DATETIME + UNIQUE constraint | Prevents duplicate hourly entries per station |
| `pm25` stored as FLOAT (nullable) | Preserves the original NA values as SQL NULL rather than a sentinel value |
| Index on `reading_ts` | Optimises the date-range queries required by Task 3 |
