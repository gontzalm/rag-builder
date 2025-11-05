import os

IS_LOCAL_DEV_ENV = os.environ.get("AWS_LAMBDA_FUNCTION_NAME") is None
