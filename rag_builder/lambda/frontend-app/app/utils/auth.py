import logging
import os
from typing import TypedDict

import boto3  # pyright: ignore[reportMissingTypeStubs]
from fastapi import HTTPException, Request, status

logger = logging.getLogger(f"uvicorn.{__name__}")


def get_app_secret_key() -> str:
    return boto3.client("secretsmanager").get_secret_value(  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
        SecretId=os.environ["APP_SECRET_KEY_SECRET"]
    )["SecretString"]


class CognitoClientCredentials(TypedDict):
    client_id: str
    client_secret: str


def get_cognito_client_credentials() -> CognitoClientCredentials:
    user_pool_id = os.environ["COGNITO_USER_POOL_ID"]
    cognito = boto3.client("cognito-idp")  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]

    # Find the client ID by its name
    paginator = cognito.get_paginator("list_user_pool_clients")  # pyright: ignore[reportUnknownVariableType, reportUnknownMemberType]
    client_id = next(  # pyright: ignore[reportUnknownVariableType]
        client["ClientId"]  # pyright: ignore[reportUnknownArgumentType]
        for page in paginator.paginate(UserPoolId=user_pool_id)  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
        for client in page["UserPoolClients"]  # pyright: ignore[reportUnknownVariableType]
        if client["ClientName"] == "frontend-app-client"
    )

    # Use the client ID to get the client secret
    client_secret = cognito.describe_user_pool_client(  # pyright: ignore[reportUnknownVariableType, reportUnknownMemberType]
        UserPoolId=user_pool_id, ClientId=client_id
    )["UserPoolClient"]["ClientSecret"]

    return {"client_id": client_id, "client_secret": client_secret}


async def get_current_user_token(request: Request) -> str:
    """Dependency to protect routes. Checks for a valid session and returns the access token."""
    try:
        access_token: str = request.session["access_token"]  # pyright: ignore[reportAny]
    except KeyError:
        # Redirect to login if not authenticated
        raise HTTPException(
            status_code=status.HTTP_307_TEMPORARY_REDIRECT,
            detail="Not authenticated",
            headers={"Location": str(request.url_for("login"))},
        )

    # TODO: get user info via /oauth2/userInfo
    # You could add token validation/refresh logic here
    return access_token
