import chainlit as cl


def setup_oauth() -> None:
    @cl.oauth_callback
    def oauth_callback(
        provider_id: str,
        token: str,
        raw_user_data: dict[str, str],
        default_user: cl.User,
    ) -> cl.User:
        """This function is called *immediately* after a successful Cognito login."""
        # Store the tokens in the user's session metadata
        default_user.metadata = {
            "access_token": token,
        }

        return default_user
