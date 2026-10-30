from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, HTTPException, Response, status
from pymongo import ASCENDING, DESCENDING, ReturnDocument

from api.config import get_mongo_collection
from api.routers.common import DateRange, date_range
from api.schemas import MongoReadingOut, Page, ReadingIn

router = APIRouter(prefix="/mongo/readings", tags=["mongo"])

STATION_NAME = "PRSA Station"


def _to_document(reading: ReadingIn) -> dict:
    ts = reading.timestamp
    return {
        "timestamp": ts,
        "year": ts.year,
        "month": ts.month,
        "day": ts.day,
        "hour": ts.hour,
        "pm25": reading.pm25,
        "weather": reading.weather.model_dump(),
        "precipitation": reading.precipitation.model_dump(),
        "station": STATION_NAME,
    }


def _to_reading(doc: dict) -> MongoReadingOut:
    return MongoReadingOut(id=str(doc.pop("_id")), **doc)


def _object_id(reading_id: str) -> ObjectId:
    try:
        return ObjectId(reading_id)
    except InvalidId:
        raise HTTPException(status_code=404, detail="Reading not found")


@router.post("", response_model=MongoReadingOut, status_code=status.HTTP_201_CREATED)
def create_reading(reading: ReadingIn, collection=Depends(get_mongo_collection)):
    doc = _to_document(reading)
    collection.insert_one(doc)
    return _to_reading(doc)


@router.get("/latest", response_model=MongoReadingOut)
def get_latest_reading(collection=Depends(get_mongo_collection)):
    doc = collection.find_one(sort=[("timestamp", DESCENDING), ("_id", DESCENDING)])
    if doc is None:
        raise HTTPException(status_code=404, detail="No readings found")
    return _to_reading(doc)


@router.get("/range", response_model=Page[MongoReadingOut])
def get_readings_in_range(params: DateRange = Depends(date_range), collection=Depends(get_mongo_collection)):
    query = {"timestamp": {"$gte": params.start, "$lte": params.end}}
    cursor = (
        collection.find(query)
        .sort([("timestamp", ASCENDING), ("_id", ASCENDING)])
        .skip(params.offset)
        .limit(params.limit)
    )
    return Page(
        total=collection.count_documents(query),
        limit=params.limit,
        offset=params.offset,
        items=[_to_reading(doc) for doc in cursor],
    )


@router.get("/{reading_id}", response_model=MongoReadingOut)
def get_reading(reading_id: str, collection=Depends(get_mongo_collection)):
    doc = collection.find_one({"_id": _object_id(reading_id)})
    if doc is None:
        raise HTTPException(status_code=404, detail="Reading not found")
    return _to_reading(doc)


@router.put("/{reading_id}", response_model=MongoReadingOut)
def update_reading(reading_id: str, reading: ReadingIn, collection=Depends(get_mongo_collection)):
    doc = collection.find_one_and_replace(
        {"_id": _object_id(reading_id)},
        _to_document(reading),
        return_document=ReturnDocument.AFTER,
    )
    if doc is None:
        raise HTTPException(status_code=404, detail="Reading not found")
    return _to_reading(doc)


@router.delete("/{reading_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_reading(reading_id: str, collection=Depends(get_mongo_collection)):
    result = collection.delete_one({"_id": _object_id(reading_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Reading not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
