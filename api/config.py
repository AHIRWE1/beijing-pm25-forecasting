import os
from pathlib import Path

import mysql.connector
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv(Path(__file__).resolve().parent / ".env")

MYSQL_CONFIG = {
    "host": os.getenv("MYSQL_HOST", "localhost"),
    "port": int(os.getenv("MYSQL_PORT", "3306")),
    "user": os.getenv("MYSQL_USER", "root"),
    "password": os.getenv("MYSQL_PASSWORD", ""),
    "database": os.getenv("MYSQL_DATABASE", "beijing_air_quality"),
}

# station_id used for new weather_readings rows (seed.sql inserts station 1)
DEFAULT_STATION_ID = int(os.getenv("DEFAULT_STATION_ID", "1"))

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB = os.getenv("MONGO_DB", "beijing_air_quality")
MONGO_COLLECTION = os.getenv("MONGO_COLLECTION", "air_quality_readings")

_mongo_client = None


def get_mysql_connection():
    conn = mysql.connector.connect(**MYSQL_CONFIG)
    try:
        yield conn
    finally:
        conn.close()


def get_mongo_collection():
    global _mongo_client
    if _mongo_client is None:
        _mongo_client = MongoClient(MONGO_URI, tz_aware=False)
    return _mongo_client[MONGO_DB][MONGO_COLLECTION]


def close_mongo_client():
    global _mongo_client
    if _mongo_client is not None:
        _mongo_client.close()
        _mongo_client = None
