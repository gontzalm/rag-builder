import logging
import os

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from starlette.datastructures import URL

from app.utils.auth import get_cognito_client_credentials

logger = logging.getLogger(f"uvicorn.{__name__}")

COGNITO_DOMAIN = os.environ["COGNITO_DOMAIN"]
COGNITO_AUTH_URL = f"{COGNITO_DOMAIN}/oauth2/authorize"
COGNITO_TOKEN_URL = f"{COGNITO_DOMAIN}/oauth2/token"
COGNITO_LOGOUT_URL = f"{COGNITO_DOMAIN}/logout"
COGNITO_CLIENT_CREDENTIALS = get_cognito_client_credentials()

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/login")
async def login(request: Request):
    """Redirects the user to the Cognito UI for login."""
    login_url = URL(COGNITO_AUTH_URL).include_query_params(
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
        response = await http.post(
            COGNITO_TOKEN_URL,
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

    tokens = response.json()  # pyright: ignore[reportAny]

    # Store tokens in the secure, HttpOnly session cookie
    request.session["access_token"] = tokens["access_token"]
    # request.session["refresh_token"] = tokens["refresh_token"]

    return RedirectResponse(request.url_for("get_frontend"))


@router.get("/logout")
async def logout(request: Request):
    """Clears the local session and logs the user out of Cognito."""
    request.session.clear()

    logout_url = URL(COGNITO_LOGOUT_URL).include_query_params(
        client_id=COGNITO_CLIENT_CREDENTIALS["client_id"],
        logout_uri=request.url_for("get_home_page"),
    )
    return RedirectResponse(logout_url)
