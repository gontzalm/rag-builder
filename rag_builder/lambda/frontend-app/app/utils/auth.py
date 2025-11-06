import logging
import os
import time
from typing import Literal, TypedDict

import boto3  # pyright: ignore[reportMissingTypeStubs]
import httpx
from fastapi import HTTPException, Request, status

from app.utils.env import APP_SECRET_KEY_SECRET, COGNITO_DOMAIN, COGNITO_USER_POOL_ID

logger = logging.getLogger(f"uvicorn.{__name__}")


COGNITO_URL = {
    "auth": f"{COGNITO_DOMAIN}/oauth2/authorize",
    "token": f"{COGNITO_DOMAIN}/oauth2/token",
    "user_info": f"{COGNITO_DOMAIN}/oauth2/userInfo",
    "logout": f"{COGNITO_DOMAIN}/logout",
}


class CognitoClientCredentials(TypedDict):
    client_id: str
    client_secret: str


class RefreshedToken(TypedDict):
    id_token: str
    access_token: str
    token_type: Literal["Bearer"]
    expires_in: Literal[3600]


def get_cognito_client_credentials() -> CognitoClientCredentials:
    cognito = boto3.client("cognito-idp")  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]

    # Find the client ID by its name
    paginator = cognito.get_paginator("list_user_pool_clients")  # pyright: ignore[reportUnknownVariableType, reportUnknownMemberType]
    client_id = next(  # pyright: ignore[reportUnknownVariableType]
        client["ClientId"]  # pyright: ignore[reportUnknownArgumentType]
        for page in paginator.paginate(UserPoolId=COGNITO_USER_POOL_ID)  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
        for client in page["UserPoolClients"]  # pyright: ignore[reportUnknownVariableType]
        if client["ClientName"] == "frontend-app-client"
    )

    # Use the client ID to get the client secret
    client_secret = cognito.describe_user_pool_client(  # pyright: ignore[reportUnknownVariableType, reportUnknownMemberType]
        UserPoolId=COGNITO_USER_POOL_ID, ClientId=client_id
    )["UserPoolClient"]["ClientSecret"]

    return {"client_id": client_id, "client_secret": client_secret}


COGNITO_CLIENT_CREDENTIALS = get_cognito_client_credentials()


def get_app_secret_key() -> str:
    return boto3.client("secretsmanager").get_secret_value(  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
        SecretId=APP_SECRET_KEY_SECRET
    )["SecretString"]


async def refresh_token(request: Request) -> None:
    """Refreshes the access token using the refresh token."""
    async with httpx.AsyncClient() as http:
        try:
            r = await http.post(
                COGNITO_URL["token"],
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                auth=(
                    COGNITO_CLIENT_CREDENTIALS["client_id"],
                    COGNITO_CLIENT_CREDENTIALS["client_secret"],
                ),
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                },
            )
            _ = r.raise_for_status()

        except httpx.HTTPStatusError:
            logger.exception("Refresh token expired, forcing re-login")
            request.session.clear()
            raise HTTPException(
                status_code=status.HTTP_307_TEMPORARY_REDIRECT,
                detail="Session expired",
                headers={"Location": str(request.url_for("login"))},
            )

        new_token: RefreshedToken = r.json()  # pyright: ignore[reportAny]

        request.session["id_token"] = new_token["id_token"]
        request.session["expires_at"] = int(time.time()) + new_token["expires_in"]

        logger.info("Successfully refreshed access token")


async def get_current_user_token(request: Request) -> str:
    """Checks for a valid session and returns the access token."""
    try:
        _ = request.session["id_token"]  # pyright: ignore[reportAny]
    except KeyError:
        # Redirect to login if not authenticated
        raise HTTPException(
            status_code=status.HTTP_307_TEMPORARY_REDIRECT,
            detail="Not authenticated",
            headers={"Location": str(request.url_for("login"))},
        )

    current_time = int(time.time())
    if current_time > request.session["expires_at"]:
        await refresh_token(request)

    return request.session["id_token"]  # pyright: ignore[reportAny]
