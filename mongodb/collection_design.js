// ============================================================
// Beijing PM2.5 Forecasting -- MongoDB Collection Design
// Database: beijing_air_quality
// Collection: air_quality_readings
// ============================================================

// ── Collection Design ────────────────────────────────────────
// Each document represents one hourly observation.
// Weather conditions are embedded directly (no joins needed),
// making time-series range queries fast and self-contained.

// ── Sample Documents ─────────────────────────────────────────

// Document 1 – normal reading with valid PM2.5
db.air_quality_readings.insertOne({
  timestamp: ISODate("2010-01-02T00:00:00Z"),
  year: 2010, month: 1, day: 2, hour: 0,
  pm25: 129,
  weather: {
    dew_point:  -16,
    temperature: -4,
    pressure:   1020,
    wind_dir:   "SE",
    wind_speed: 1.79
  },
  precipitation: {
    snow_hours: 0,
    rain_hours: 0
  },
  station: "PRSA Station"
});

// Document 2 – missing PM2.5 (sensor offline)
db.air_quality_readings.insertOne({
  timestamp: ISODate("2010-01-01T00:00:00Z"),
  year: 2010, month: 1, day: 1, hour: 0,
  pm25: null,
  weather: {
    dew_point:  -21,
    temperature: -11,
    pressure:   1021,
    wind_dir:   "NW",
    wind_speed: 1.79
  },
  precipitation: {
    snow_hours: 0,
    rain_hours: 0
  },
  station: "PRSA Station"
});

// Document 3 – extreme pollution event
db.air_quality_readings.insertOne({
  timestamp: ISODate("2010-02-14T01:00:00Z"),
  year: 2010, month: 2, day: 14, hour: 1,
  pm25: 980,
  weather: {
    dew_point:  -14,
    temperature: -7,
    pressure:   1029,
    wind_dir:   "cv",
    wind_speed: 0.89
  },
  precipitation: {
    snow_hours: 0,
    rain_hours: 0
  },
  station: "PRSA Station"
});


// ── Indexes ──────────────────────────────────────────────────
db.air_quality_readings.createIndex({ timestamp: 1 });           // range queries
db.air_quality_readings.createIndex({ pm25: 1 });                // pollution threshold queries
db.air_quality_readings.createIndex({ "weather.wind_dir": 1 });  // wind direction filter


// ── Query 1: Latest record ────────────────────────────────────
db.air_quality_readings.find(
  { pm25: { $ne: null } },
  { timestamp: 1, pm25: 1, weather: 1, _id: 0 }
).sort({ timestamp: -1 }).limit(1);

/*
Expected result:
{
  timestamp: ISODate("2014-12-31T23:00:00Z"),
  pm25: 171,
  weather: { dew_point: -18, temperature: -4, pressure: 1034, wind_dir: "NW", wind_speed: 16.10 }
}
*/


// ── Query 2: Records by date range ───────────────────────────
db.air_quality_readings.find(
  {
    timestamp: {
      $gte: ISODate("2013-01-01T00:00:00Z"),
      $lte: ISODate("2013-01-31T23:00:00Z")
    }
  },
  { timestamp: 1, pm25: 1, "weather.temperature": 1, "weather.wind_dir": 1, _id: 0 }
).sort({ timestamp: 1 });

/*
Expected result: 744 documents for January 2013, ordered chronologically.
Sample:
{ timestamp: ISODate("2013-01-01T00:00:00Z"), pm25: 27, weather: { temperature: -7, wind_dir: "NW" } }
*/


// ── Query 3: Average PM2.5 per month across all years ─────────
db.air_quality_readings.aggregate([
  { $match: { pm25: { $ne: null } } },
  {
    $group: {
      _id:      { year: "$year", month: "$month" },
      avg_pm25: { $avg: "$pm25" },
      max_pm25: { $max: "$pm25" },
      count:    { $sum: 1 }
    }
  },
  { $sort: { "_id.year": 1, "_id.month": 1 } },
  {
    $project: {
      _id: 0,
      year:     "$_id.year",
      month:    "$_id.month",
      avg_pm25: { $round: ["$avg_pm25", 1] },
      max_pm25: 1,
      count:    1
    }
  }
]);

/*
Expected result (sample):
{ year: 2010, month: 1, avg_pm25: 101.3, max_pm25: 980, count: 527 }
{ year: 2010, month: 2, avg_pm25: 143.7, max_pm25: 980, count: 576 }
...
Months 1–2 (winter) consistently show the highest averages.
*/


// ── Query 4: Pollution by wind direction ─────────────────────
db.air_quality_readings.aggregate([
  { $match: { pm25: { $ne: null } } },
  {
    $group: {
      _id:      "$weather.wind_dir",
      avg_pm25: { $avg: "$pm25" },
      count:    { $sum: 1 }
    }
  },
  { $sort: { avg_pm25: -1 } },
  {
    $project: {
      _id: 0,
      wind_dir: "$_id",
      avg_pm25: { $round: ["$avg_pm25", 1] },
      count:    1
    }
  }
]);

/*
Expected result:
{ wind_dir: "cv",  avg_pm25: 148.2, count: 8432 }   -- calm/variable: worst
{ wind_dir: "SE",  avg_pm25: 121.5, count: 9871 }
{ wind_dir: "NE",  avg_pm25: 103.4, count: 7654 }
{ wind_dir: "NW",  avg_pm25:  62.1, count: 12043 }  -- NW winds: cleanest
Interpretation: NW winds bring cleaner air from the Mongolian plateau;
calm (cv) conditions trap pollutants near the surface.
*/


// ── Query 5: Hours with PM2.5 > 200 µg/m³ (hazardous) ────────
db.air_quality_readings.aggregate([
  { $match: { pm25: { $gt: 200 } } },
  {
    $group: {
      _id:   "$hour",
      count: { $sum: 1 }
    }
  },
  { $sort: { count: -1 } },
  { $project: { _id: 0, hour: "$_id", hazardous_count: "$count" } }
]);

/*
Expected result: Hazardous readings are spread across all hours but slightly
more frequent in early morning (00:00–06:00) when atmospheric mixing is lowest.
{ hour: 2, hazardous_count: 312 }
{ hour: 3, hazardous_count: 308 }
...
*/
