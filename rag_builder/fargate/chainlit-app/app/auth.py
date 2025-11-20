import chainlit as cl


def setup_oauth() -> None:
    """Sets up OAuth authentication."""

    @cl.oauth_callback  # pyright: ignore[reportUnknownMemberType, reportArgumentType]
    def oauth_callback(  # pyright: ignore[reportUnusedFunction]
        provider_id: str,  # pyright: ignore[reportUnusedParameter]
        token: str,
        raw_user_data: dict[str, str],  # pyright: ignore[reportUnusedParameter]
        default_user: cl.User,
    ) -> cl.User:
        # Store the access token in the user's session metadata
        default_user.metadata = {
            "access_token": token,
        }

        return default_user
