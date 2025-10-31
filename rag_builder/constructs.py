import subprocess
import textwrap
from pathlib import Path
from string import Template
from typing import final

import aws_cdk as cdk
import aws_cdk.aws_cognito as cognito
from aws_cdk import aws_apigateway as apigw
from aws_cdk import aws_lambda as lambda_
from constructs import Construct

BASE_DIR = Path(__file__).parent


def compile_uv_lock(lambda_path: Path) -> None:
    uv_lock = lambda_path / "uv.lock"
    requirements_txt = lambda_path / "requirements.txt"

    if (
        not requirements_txt.exists()
        or uv_lock.stat().st_mtime > requirements_txt.stat().st_mtime
    ):
        _ = subprocess.run(
            [
                "uv",
                "export",
                "-o",
                "requirements.txt",
            ],
            check=True,
            cwd=str(lambda_path),
        )


class PythonFunction(lambda_.Function):
    def __init__(
        self,
        scope: Construct,
        id: str,
        *,
        runtime: lambda_.Runtime = lambda_.Runtime.PYTHON_3_13,  # pyright: ignore[reportAny]
        memory: int = 128,
        timeout: cdk.Duration | None = None,
        environment: dict[str, str] | None,
    ) -> None:
        lambda_code = BASE_DIR / "lambda" / id.removesuffix("-function")

        compile_uv_lock(lambda_code)

        super().__init__(
            scope,
            id,
            runtime=runtime,
            architecture=lambda_.Architecture.ARM_64,  # pyright: ignore[reportAny]
            handler="function.handler",
            code=lambda_.Code.from_asset(
                str(lambda_code),
                bundling=cdk.BundlingOptions(
                    image=runtime.bundling_image,
                    platform="linux/arm64",
                    command=[
                        "bash",
                        "-c",
                        " && ".join(
                            [
                                "pip install --platform manylinux2014_aarch64 --only-binary=:all: -r requirements.txt -t /asset-output",
                                "rsync -a --exclude .venv --exclude __pycache__ . /asset-output",
                            ]
                        ),
                    ],
                ),
            ),
            timeout=timeout,
            environment=environment,
        )


@final
class DockerPythonFunction(lambda_.DockerImageFunction):
    _DOCKERFILE_TEMPLATE = Template(
        textwrap.dedent("""\
            FROM public.ecr.aws/lambda/python:${python_version}

            COPY --exclude=.venv . ${LAMBDA_TASK_ROOT}

            RUN pip install -r requirements.txt
        """)
    )

    def __init__(
        self,
        scope: Construct,
        id: str,
        *,
        runtime: lambda_.Runtime = lambda_.Runtime.PYTHON_3_13,  # pyright: ignore[reportAny]
        memory: int = 128,
        timeout: cdk.Duration | None = None,
        environment: dict[str, str] | None = None,
    ) -> None:
        lambda_code = BASE_DIR / "lambda" / id.removesuffix("-function")

        compile_uv_lock(lambda_code)

        # Create Dockerfile
        dockerfile = lambda_code / "Dockerfile"
        dockerfile_content = self._DOCKERFILE_TEMPLATE.safe_substitute(
            {"python_version": runtime.name.removeprefix("python")}
        )
        _ = dockerfile.write_text(dockerfile_content)

        docker_code = lambda_.DockerImageCode.from_image_asset(
            str(lambda_code),
            cmd=["function.handler"],
        )

        super().__init__(
            scope,
            id,
            code=docker_code,
            architecture=lambda_.Architecture.ARM_64,  # pyright: ignore[reportAny]
            memory_size=memory,
            environment=environment,
            timeout=timeout,
        )


@final
class FastApiLambdaFunction(Construct):
    _RUN_SH_CONTENT = textwrap.dedent("""\
        #!/bin/bash
        PATH=$PATH:$LAMBDA_TASK_ROOT/bin \\
            PYTHONPATH=$PYTHONPATH:/opt/python:$LAMBDA_RUNTIME_DIR
            exec python -m uvicorn --port ${PORT} --root-path /prod app.main:app
    """)

    def __init__(
        self,
        scope: Construct,
        id: str,
        *,
        runtime: lambda_.Runtime = lambda_.Runtime.PYTHON_3_13,  # pyright: ignore[reportAny]
        environment: dict[str, str] | None = None,
        cognito_authorizer_pool: cognito.UserPool | None = None,
    ) -> None:
        super().__init__(scope, id)

        lambda_code = BASE_DIR / "lambda" / id.removesuffix("-fastapi")

        compile_uv_lock(lambda_code)

        self.function = lambda_.Function(
            scope,
            f"{id}-function",
            runtime=runtime,
            architecture=lambda_.Architecture.ARM_64,  # pyright: ignore[reportAny]
            handler="run.sh",
            layers=[
                lambda_.LayerVersion.from_layer_version_arn(
                    self,
                    f"{id}-adapterlayer",
                    layer_version_arn=f"arn:aws:lambda:{cdk.Stack.of(self).region}:753240598075:layer:LambdaAdapterLayerArm64:24",
                )
            ],
            code=lambda_.Code.from_asset(
                str(lambda_code),
                bundling=cdk.BundlingOptions(
                    image=runtime.bundling_image,
                    platform="linux/arm64",
                    command=[
                        "bash",
                        "-c",
                        " && ".join(
                            [
                                f"echo -e '{self._RUN_SH_CONTENT}' > /asset-output/run.sh",
                                "chmod +x /asset-output/run.sh",
                                "pip install --platform manylinux2014_aarch64 --only-binary=:all: -r requirements.txt -t /asset-output",
                                "rsync -a --exclude .venv --exclude __pycache__ . /asset-output",
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
