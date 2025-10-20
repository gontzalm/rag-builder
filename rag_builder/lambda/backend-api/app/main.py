from fastapi import FastAPI

from app.routers import ingest

app = FastAPI()

app.include_router(ingest.router)


@app.get("/")
async def root() -> dict[str, str]:
    return {
        "message": "Welcome to the RAG Builder app Backend API! Navigate to /docs to browse the OpenAPI docs"
    }
