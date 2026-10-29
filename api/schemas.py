from datetime import datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator


class Weather(BaseModel):
    dew_point: int
    temperature: int
    pressure: int
    wind_dir: Literal["NE", "NW", "SE", "cv"]
    wind_speed: float = Field(ge=0)


class Precipitation(BaseModel):
    snow_hours: int = Field(default=0, ge=0, le=127)
    rain_hours: int = Field(default=0, ge=0, le=127)


class ReadingIn(BaseModel):
    timestamp: datetime
    pm25: Optional[float] = Field(default=None, ge=0)
    weather: Weather
    precipitation: Precipitation = Precipitation()

    @field_validator("timestamp")
    @classmethod
    def to_naive_utc(cls, value: datetime) -> datetime:
        # Hourly data: aware input is converted to UTC, then stored naive and truncated to the hour
        if value.tzinfo is not None:
            value = value.astimezone(timezone.utc).replace(tzinfo=None)
        return value.replace(minute=0, second=0, microsecond=0)


class ReadingOut(ReadingIn):
    year: int
    month: int
    day: int
    hour: int


class SQLReadingOut(ReadingOut):
    id: int
    measurement_id: int
    station_id: int


class MongoReadingOut(ReadingOut):
    id: str
    station: str
