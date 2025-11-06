import os

import dotenv

IS_LOCAL_DEV_ENV = os.environ.get("AWS_LAMBDA_FUNCTION_NAME") is None

if IS_LOCAL_DEV_ENV:
    _ = dotenv.load_dotenv()

APP_SECRET_KEY_SECRET = os.environ["APP_SECRET_KEY_SECRET"]
BACKEND_API_URL = os.environ["BACKEND_API_URL"]
COGNITO_USER_POOL_ID = os.environ["COGNITO_USER_POOL_ID"]
COGNITO_DOMAIN = os.environ["COGNITO_DOMAIN"]
