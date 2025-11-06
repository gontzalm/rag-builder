import logging
import time
from typing import Literal, TypedDict

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from starlette.datastructures import URL

from app.utils.auth import COGNITO_CLIENT_CREDENTIALS, COGNITO_URL

logger = logging.getLogger(f"uvicorn.{__name__}")


class Oauth2Tokens(TypedDict):
    id_token: str
    access_token: str
    refresh_token: str
    token_type: Literal["Bearer"]
    expires_in: Literal[3600]


class UserInfo(TypedDict):
    email: str


router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/login")
async def login(request: Request):
    """Redirects the user to the Cognito UI for login."""
    login_url = URL(COGNITO_URL["auth"]).include_query_params(
        response_type="code",
        client_id=COGNITO_CLIENT_CREDENTIALS["client_id"],
        redirect_uri=request.url_for("auth_callback"),
        scope="openid email profile",
    )
    return RedirectResponse(login_url)


@router.get("/callback")
async def auth_callback(request: Request, code: str):
    """Handles the callback from Cognito. Exchanges the code for tokens and stores them in the session."""
    async with httpx.AsyncClient() as http:
        r = await http.post(
            COGNITO_URL["token"],
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            auth=(
                COGNITO_CLIENT_CREDENTIALS["client_id"],
                COGNITO_CLIENT_CREDENTIALS["client_secret"],
            ),
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": request.url_for("auth_callback"),
            },
        )

        _ = r.raise_for_status()
        tokens: Oauth2Tokens = r.json()  # pyright: ignore[reportAny]

        r = await http.get(
            COGNITO_URL["user_info"],
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )
        _ = r.raise_for_status()
        user_info: UserInfo = r.json()  # pyright: ignore[reportAny]

    # Store tokens and user info in the secure, HttpOnly session cookie
    request.session["id_token"] = tokens["id_token"]
    request.session["refresh_token"] = tokens["refresh_token"]
    request.session["expires_at"] = int(time.time()) + tokens["expires_in"]
    request.session["email"] = user_info["email"]
    # request.session["refresh_token"] = tokens["refresh_token"]

    return RedirectResponse(request.url_for("get_frontend"))


@router.get("/logout")
async def logout(request: Request):
    """Clears the local session and logs the user out of Cognito."""
    request.session.clear()

    logout_url = URL(COGNITO_URL["logout"]).include_query_params(
        client_id=COGNITO_CLIENT_CREDENTIALS["client_id"],
        logout_uri=request.url_for("get_frontend"),
    )
    return RedirectResponse(logout_url)
