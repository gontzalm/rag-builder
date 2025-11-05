import logging

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from starlette.middleware.sessions import SessionMiddleware

from app.routers import auth, frontend
from app.utils.auth import get_app_secret_key
from app.utils.env import IS_LOCAL_DEV_ENV

logger = logging.getLogger(f"uvicorn.{__name__}")

app = FastAPI()

app.add_middleware(
    SessionMiddleware,
    secret_key=get_app_secret_key(),
    https_only=not IS_LOCAL_DEV_ENV,
    same_site="lax",
)

app.include_router(auth.router)
app.include_router(frontend.router)


@app.get("/")
def get_frontend(request: Request) -> RedirectResponse:
    return RedirectResponse(request.url_for("get_home_page"))
