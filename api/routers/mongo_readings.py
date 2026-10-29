from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, HTTPException, Response, status
from pymongo import ReturnDocument

from api.config import get_mongo_collection
from api.schemas import MongoReadingOut, ReadingIn

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
