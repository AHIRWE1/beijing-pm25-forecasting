from dataclasses import dataclass
from datetime import datetime

from fastapi import HTTPException, Query

from api.schemas import to_naive_utc

DEFAULT_LIMIT = 100
MAX_LIMIT = 1000


@dataclass
class DateRange:
    start: datetime
    end: datetime
    limit: int
    offset: int


def date_range(
    start: datetime = Query(..., description="ISO 8601, inclusive"),
    end: datetime = Query(..., description="ISO 8601, inclusive"),
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    offset: int = Query(0, ge=0),
) -> DateRange:
    start, end = to_naive_utc(start), to_naive_utc(end)
    if start > end:
        raise HTTPException(status_code=400, detail="start must not be after end")
    return DateRange(start=start, end=end, limit=limit, offset=offset)
