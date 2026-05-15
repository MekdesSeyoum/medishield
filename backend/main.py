import os
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.cases import router as cases_router

_CORS_ORIGINS = [
    o.strip()
    for o in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
    if o.strip()
]


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    yield


app = FastAPI(
    title="MediShield — Document Processing API",
    description=(
        "Accepts insurance documents (JPEG, PNG, PDF, TIFF), "
        "stores them in MinIO, runs the LangGraph agent pipeline asynchronously, "
        "and exposes case status, agent outputs, and a manual review override endpoint."
    ),
    version="0.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(cases_router)


@app.get("/health", tags=["ops"])
def health() -> dict:
    return {"status": "ok"}
