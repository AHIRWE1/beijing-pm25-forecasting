"""
Task 3: Load the Beijing PM2.5 CSV into MongoDB (air_quality_readings).

Run from the project root:
    python scripts/load_mongo.py            # refuses if the collection already has documents
    python scripts/load_mongo.py --drop     # clears the collection first

Connection settings come from api/.env (MONGO_URI, MONGO_DB, MONGO_COLLECTION).
"""
import argparse
import csv
import os
import sys
from datetime import datetime

from pymongo import ASCENDING

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from api.config import close_mongo_client, get_mongo_collection  # noqa: E402

RAW = "data/raw/PRSA_data_2010.1.1-2014.12.31.csv"
BATCH_SIZE = 1000
STATION_NAME = "PRSA Station"


def number(value, cast):
    value = value.strip()
    if value in ("", "NA"):
        return None
    return cast(float(value))


def to_document(row: dict) -> dict:
    year, month, day, hour = (int(row[k]) for k in ("year", "month", "day", "hour"))
    return {
        "timestamp": datetime(year, month, day, hour),
        "year": year,
        "month": month,
        "day": day,
        "hour": hour,
        "pm25": number(row["pm2.5"], float),
        "weather": {
            "dew_point": number(row["DEWP"], int),
            "temperature": number(row["TEMP"], int),
            "pressure": number(row["PRES"], int),
            "wind_dir": row["cbwd"].strip(),
            "wind_speed": number(row["Iws"], float),
        },
        "precipitation": {
            "snow_hours": number(row["Is"], int),
            "rain_hours": number(row["Ir"], int),
        },
        "station": STATION_NAME,
    }


def load(csv_path: str, batch_size: int, drop: bool) -> None:
    collection = get_mongo_collection()
    existing = collection.estimated_document_count()
    if existing and not drop:
        sys.exit(f"{collection.full_name} already has {existing} documents. Use --drop to reload.")
    if drop:
        collection.drop()

    inserted = 0
    batch = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            batch.append(to_document(row))
            if len(batch) == batch_size:
                inserted += len(collection.insert_many(batch).inserted_ids)
                batch = []
                print(f"inserted {inserted}")
    if batch:
        inserted += len(collection.insert_many(batch).inserted_ids)

    collection.create_index([("timestamp", ASCENDING)])
    collection.create_index([("pm25", ASCENDING)])
    collection.create_index([("weather.wind_dir", ASCENDING)])

    missing = collection.count_documents({"pm25": None})
    print(f"Done: {inserted} documents in {collection.full_name}, {missing} with pm25 = null")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--csv", default=RAW, help=f"CSV path (default: {RAW})")
    parser.add_argument("--batch-size", type=int, default=BATCH_SIZE)
    parser.add_argument("--drop", action="store_true", help="drop the collection before loading")
    args = parser.parse_args()

    if not os.path.exists(args.csv):
        sys.exit(f"CSV not found: {args.csv}")
    try:
        load(args.csv, args.batch_size, args.drop)
    finally:
        close_mongo_client()


if __name__ == "__main__":
    main()
