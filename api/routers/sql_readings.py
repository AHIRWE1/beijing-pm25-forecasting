from fastapi import APIRouter, Depends, HTTPException, Response, status
from mysql.connector import errors

from api.config import DEFAULT_STATION_ID, get_mysql_connection
from api.schemas import ReadingIn, SQLReadingOut

router = APIRouter(prefix="/sql/readings", tags=["sql"])

DUPLICATE_ENTRY = 1062

SELECT_READING = """
    SELECT wr.reading_id, wr.station_id, wr.reading_ts, wr.year, wr.month, wr.day, wr.hour,
           wr.dew_point, wr.temperature, wr.pressure, wr.wind_dir, wr.wind_speed,
           pm.measurement_id, pm.pm25, pm.snow_hours, pm.rain_hours
    FROM weather_readings wr
    JOIN pm25_measurements pm ON pm.reading_id = wr.reading_id
"""


def _row_to_reading(row: dict) -> SQLReadingOut:
    return SQLReadingOut(
        id=row["reading_id"],
        measurement_id=row["measurement_id"],
        station_id=row["station_id"],
        timestamp=row["reading_ts"],
        year=row["year"],
        month=row["month"],
        day=row["day"],
        hour=row["hour"],
        pm25=row["pm25"],
        weather={
            "dew_point": row["dew_point"],
            "temperature": row["temperature"],
            "pressure": row["pressure"],
            "wind_dir": row["wind_dir"],
            "wind_speed": float(row["wind_speed"]),
        },
        precipitation={
            "snow_hours": row["snow_hours"],
            "rain_hours": row["rain_hours"],
        },
    )


def _fetch_reading(conn, reading_id: int):
    with conn.cursor(dictionary=True) as cur:
        cur.execute(SELECT_READING + " WHERE wr.reading_id = %s", (reading_id,))
        row = cur.fetchone()
    return _row_to_reading(row) if row else None


def _weather_values(reading: ReadingIn) -> tuple:
    ts = reading.timestamp
    w = reading.weather
    return (
        ts, ts.year, ts.month, ts.day, ts.hour,
        w.dew_point, w.temperature, w.pressure, w.wind_dir, w.wind_speed,
    )


def _measurement_values(reading: ReadingIn) -> tuple:
    p = reading.precipitation
    return (reading.pm25, p.snow_hours, p.rain_hours)


def _duplicate_timestamp_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="A reading already exists for this station and timestamp",
    )


@router.post("", response_model=SQLReadingOut, status_code=status.HTTP_201_CREATED)
def create_reading(reading: ReadingIn, conn=Depends(get_mysql_connection)):
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO weather_readings
                    (station_id, reading_ts, year, month, day, hour,
                     dew_point, temperature, pressure, wind_dir, wind_speed)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (DEFAULT_STATION_ID, *_weather_values(reading)),
            )
            reading_id = cur.lastrowid
            cur.execute(
                """
                INSERT INTO pm25_measurements (reading_id, pm25, snow_hours, rain_hours)
                VALUES (%s, %s, %s, %s)
                """,
                (reading_id, *_measurement_values(reading)),
            )
        conn.commit()
    except errors.IntegrityError as exc:
        conn.rollback()
        if exc.errno == DUPLICATE_ENTRY:
            raise _duplicate_timestamp_error()
        raise
    except Exception:
        conn.rollback()
        raise
    return _fetch_reading(conn, reading_id)


@router.get("/{reading_id}", response_model=SQLReadingOut)
def get_reading(reading_id: int, conn=Depends(get_mysql_connection)):
    reading = _fetch_reading(conn, reading_id)
    if reading is None:
        raise HTTPException(status_code=404, detail="Reading not found")
    return reading


@router.put("/{reading_id}", response_model=SQLReadingOut)
def update_reading(reading_id: int, reading: ReadingIn, conn=Depends(get_mysql_connection)):
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT reading_id FROM weather_readings WHERE reading_id = %s FOR UPDATE",
                (reading_id,),
            )
            if cur.fetchone() is None:
                raise HTTPException(status_code=404, detail="Reading not found")
            cur.execute(
                """
                UPDATE weather_readings
                SET reading_ts = %s, year = %s, month = %s, day = %s, hour = %s,
                    dew_point = %s, temperature = %s, pressure = %s,
                    wind_dir = %s, wind_speed = %s
                WHERE reading_id = %s
                """,
                (*_weather_values(reading), reading_id),
            )
            cur.execute(
                """
                UPDATE pm25_measurements
                SET pm25 = %s, snow_hours = %s, rain_hours = %s
                WHERE reading_id = %s
                """,
                (*_measurement_values(reading), reading_id),
            )
        conn.commit()
    except errors.IntegrityError as exc:
        conn.rollback()
        if exc.errno == DUPLICATE_ENTRY:
            raise _duplicate_timestamp_error()
        raise
    except Exception:
        conn.rollback()
        raise
    return _fetch_reading(conn, reading_id)


@router.delete("/{reading_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_reading(reading_id: int, conn=Depends(get_mysql_connection)):
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT reading_id FROM weather_readings WHERE reading_id = %s FOR UPDATE",
                (reading_id,),
            )
            if cur.fetchone() is None:
                raise HTTPException(status_code=404, detail="Reading not found")
            cur.execute("DELETE FROM pm25_measurements WHERE reading_id = %s", (reading_id,))
            cur.execute("DELETE FROM weather_readings WHERE reading_id = %s", (reading_id,))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return Response(status_code=status.HTTP_204_NO_CONTENT)
