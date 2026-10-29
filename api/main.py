from contextlib import asynccontextmanager

from fastapi import FastAPI

from api.config import close_mongo_client
from api.routers import mongo_readings, sql_readings


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    close_mongo_client()


app = FastAPI(title="Beijing PM2.5 Air Quality API", lifespan=lifespan)

app.include_router(sql_readings.router)
app.include_router(mongo_readings.router)


@app.get("/", tags=["health"])
def root():
    return {"status": "ok"}
