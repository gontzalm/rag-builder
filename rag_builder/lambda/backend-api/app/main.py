import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import documents

logging.basicConfig(level=logging.INFO)

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ["CORS_ALLOW_ORIGINS"].split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(documents.router)


@app.get("/")
async def root() -> dict[str, str]:
    return {
        "message": "Welcome to the RAG Builder app Backend API! Navigate to /docs to browse the OpenAPI docs"
    }
