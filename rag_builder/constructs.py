import textwrap
from pathlib import Path
from typing import final

import aws_cdk as cdk
import aws_cdk.aws_cognito as cognito
import aws_cdk.aws_lambda_python_alpha as lambda_python
from aws_cdk import aws_apigateway as apigw
from aws_cdk import aws_lambda as lambda_
from constructs import Construct

BASE_DIR = Path(__file__).parent


class PythonFunction(lambda_python.PythonFunction):
    def __init__(
        self,
        scope: Construct,
        id: str,
        *,
        runtime: lambda_.Runtime = lambda_.Runtime.PYTHON_3_13,  # pyright: ignore[reportAny]
        memory: int = 128,
        environment: dict[str, str] | None,
    ) -> None:
        super().__init__(
            scope,
            id,
            index="function.py",
            runtime=runtime,
            architecture=lambda_.Architecture.ARM_64,  # pyright: ignore[reportAny]
            memory_size=memory,
            environment=environment,
            entry=str(BASE_DIR / "lambda" / id.removesuffix("-function")),
            bundling=lambda_python.BundlingOptions(
                asset_excludes=[".venv", "__pycache__"]
            ),
        )


@final
class FastApiLambdaFunction(Construct):
    def __init__(
        self,
        scope: Construct,
        id: str,
        *,
        python_runtime: lambda_.Runtime,
        environment: dict[str, str] | None = None,
        cognito_authorizer_pool: cognito.UserPool | None = None,
    ) -> None:
        super().__init__(scope, id)

        RUN_SH_CONTENT = textwrap.dedent("""\
            #!/bin/bash
            PATH=$PATH:$LAMBDA_TASK_ROOT/bin \\
                PYTHONPATH=$PYTHONPATH:/opt/python:$LAMBDA_RUNTIME_DIR
                exec python -m uvicorn --port ${PORT} --root-path /prod app.main:app
        """)

        self.function = lambda_.Function(
            scope,
            f"{id}-function",
            runtime=python_runtime,
            handler="run.sh",
            layers=[
                lambda_.LayerVersion.from_layer_version_arn(
                    self,
                    f"{id}-adapterlayer",
                    layer_version_arn=f"arn:aws:lambda:{cdk.Stack.of(self).region}:753240598075:layer:LambdaAdapterLayerX86:25",
                )
            ],
            code=lambda_.Code.from_asset(
                str(BASE_DIR / "lambda" / id.removesuffix("-fastapi")),
                bundling=cdk.BundlingOptions(
                    image=python_runtime.bundling_image,
                    command=[
                        "bash",
                        "-c",
                        " && ".join(
                            [
                                f"echo -e '{RUN_SH_CONTENT}' > /asset-output/run.sh",
                                "chmod +x /asset-output/run.sh",
                                "pip install -r requirements.txt -t /asset-output",
                                "rm -r .venv || true",
                                "cp -au . /asset-output",
                            ]
                        ),
                    ],
                ),
            ),
            timeout=cdk.Duration.seconds(30),
            environment={
                "AWS_LAMBDA_EXEC_WRAPPER": "/opt/bootstrap",
                "PORT": "8080",
                **(environment or {}),
            },
        )

        self.apigw = apigw.LambdaRestApi(
            scope,
            f"{id}-apigw",
            handler=self.function,  # pyright: ignore[reportArgumentType]
            default_method_options=apigw.MethodOptions(
                authorizer=apigw.CognitoUserPoolsAuthorizer(
                    self,
                    f"{id}-cognito-authorizer",
                    cognito_user_pools=[cognito_authorizer_pool],
                )
            )
            if cognito_authorizer_pool is not None
            else None,
        )
