import os
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.utils.auth import get_current_user_token

BACKEND_API_URL = os.environ["BACKEND_API_URL"]

templates = Jinja2Templates(Path(__file__).parent.parent / "templates")
router = APIRouter(prefix="/frontend", tags=["frontend"])


@router.get("")
async def get_home_page(
    request: Request,
    token: str = Depends(get_current_user_token),  # pyright: ignore[reportCallInDefaultInitializer]
) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "index.html", context={"user": request.session["id_token"]}
    )
