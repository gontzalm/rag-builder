import subprocess
import textwrap
from collections.abc import Sequence
from pathlib import Path
from string import Template
from typing import Literal, TypedDict, final

import aws_cdk as cdk
import aws_cdk.aws_cognito as cognito
from aws_cdk import aws_apigateway as apigw
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as lambda_
from constructs import Construct

BASE_DIR = Path(__file__).parent
PIP_CACHE_DIR = BASE_DIR.parent / ".cdk-pip-cache"
PIP_CACHE_DIR.mkdir(exist_ok=True)

PYTHON_IGNORE_PATTERNS = (".venv", "__pycache__", "tests")


class Endpoint(TypedDict):
    path: str
    methods: Sequence[Literal["GET", "POST", "PUT", "PATCH", "DELETE"]]


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
                "--no-dev",
                "-o",
                "requirements.txt",
            ],
            check=True,
            cwd=str(lambda_path),
            stdout=subprocess.DEVNULL,
        )


@final
class PythonFunction(Construct):
    _DOCKERFILE_TEMPLATE = Template(
        textwrap.dedent("""\
            FROM public.ecr.aws/lambda/python:${python_version}

            COPY requirements.txt ${LAMBDA_TASK_ROOT}
            RUN pip install -r requirements.txt

            COPY . ${LAMBDA_TASK_ROOT}
        """)
    )

    def __init__(
        self,
        scope: Construct,
        id: str,
        *,
        containerized: bool = False,
        runtime: lambda_.Runtime = lambda_.Runtime.PYTHON_3_13,  # pyright: ignore[reportAny]
        memory: int = 128,
        timeout: cdk.Duration | None = None,
        environment: dict[str, str] | None,
    ) -> None:
        super().__init__(scope, id)

        lambda_code = BASE_DIR / "lambda" / id.removesuffix("-function")

        compile_uv_lock(lambda_code)

        if containerized:
            dockerignore = lambda_code / ".dockerignore"
            _ = dockerignore.write_text("\n".join(PYTHON_IGNORE_PATTERNS))

            dockerfile = lambda_code / "Dockerfile"
            dockerfile_content = self._DOCKERFILE_TEMPLATE.safe_substitute(
                {"python_version": runtime.name.removeprefix("python")}
            )
            _ = dockerfile.write_text(dockerfile_content)

            docker_code = lambda_.DockerImageCode.from_image_asset(
                str(lambda_code),
                cmd=["function.handler"],
            )

            self.function = lambda_.DockerImageFunction(
                scope,
                f"{id}-docker-function",
                code=docker_code,
                architecture=lambda_.Architecture.ARM_64,  # pyright: ignore[reportAny]
                memory_size=memory,
                environment=environment,
                timeout=timeout,
            )
        else:
            self.function = lambda_.Function(
                scope,
                f"{id}-zip-function",
                runtime=runtime,
                architecture=lambda_.Architecture.ARM_64,  # pyright: ignore[reportAny]
                memory_size=memory,
                handler="function.handler",
                code=lambda_.Code.from_asset(
                    str(lambda_code),
                    bundling=cdk.BundlingOptions(
                        image=runtime.bundling_image,
                        platform="linux/arm64",
                        volumes=[
                            cdk.DockerVolume(
                                host_path=str(PIP_CACHE_DIR),
                                container_path="/pip-cache",
                            )
                        ],
                        environment={"PIP_CACHE_DIR": "/pip-cache"},
                        command=[
                            "bash",
                            "-c",
                            " && ".join(
                                [
                                    "pip install -r requirements.txt -t /asset-output",
                                    f"rsync -a {' '.join(f'--exclude {p}' for p in PYTHON_IGNORE_PATTERNS)} . /asset-output",
                                ]
                            ),
                        ],
                    ),
                ),
                timeout=timeout,
                environment=environment,
            )


@final
class FastApiLambdaFunction(Construct):
    _DOCKERFILE_TEMPLATE = Template(
        textwrap.dedent("""\
            FROM python:${python_version}-slim

            COPY --from=public.ecr.aws/awsguru/aws-lambda-adapter:0.9.1 /lambda-adapter /opt/extensions/lambda-adapter

            ENV AWS_LWA_PORT=8000

            WORKDIR /var/task

            COPY requirements.txt .
            RUN pip install -r requirements.txt

            COPY . .

            CMD ["uvicorn", "--port", "8000", "--root-path", "/prod", "app.main:app"]
        """)
    )

    def __init__(
        self,
        scope: Construct,
        id: str,
        *,
        runtime: lambda_.Runtime = lambda_.Runtime.PYTHON_3_13,  # pyright: ignore[reportAny]
        memory: int = 256,
        environment: dict[str, str] | None = None,
        cognito_authorizer_pool: cognito.UserPool | None = None,
        cognito_authorization_scopes: Sequence[cognito.OAuthScope] | None = None,
        iam_authorized_endpoints: list[Endpoint] | None = None,
        cors_allow_origins: list[str] | None = None,
    ) -> None:
        super().__init__(scope, id)

        lambda_code = BASE_DIR / "lambda" / id.removesuffix("-fastapi")

        compile_uv_lock(lambda_code)

        dockerignore = lambda_code / ".dockerignore"
        _ = dockerignore.write_text("\n".join(PYTHON_IGNORE_PATTERNS))

        dockerfile = lambda_code / "Dockerfile"
        dockerfile_content = self._DOCKERFILE_TEMPLATE.safe_substitute(
            {"python_version": runtime.name.removeprefix("python")}
        )
        _ = dockerfile.write_text(dockerfile_content)

        self.function = lambda_.DockerImageFunction(
            scope,
            f"{id}-function",
            code=lambda_.DockerImageCode.from_image_asset(str(lambda_code)),
            architecture=lambda_.Architecture.ARM_64,  # pyright: ignore[reportAny]
            memory_size=memory,
            timeout=cdk.Duration.seconds(30),
            environment={
                "CORS_ALLOW_ORIGINS": ",".join(
                    ["http://localhost:8000"] + (cors_allow_origins or [])
                ),
                **(environment or {}),
            },
        )

        lambda_integration = apigw.LambdaIntegration(self.function)  # pyright: ignore[reportArgumentType]

        self.apigw = apigw.RestApi(
            scope,
            f"{id}-apigw",
            default_cors_preflight_options=apigw.CorsOptions(
                allow_origins=["http://localhost:8000"] + (cors_allow_origins or []),
                allow_credentials=True,
            ),
        )

        self._iam_authorized_methods: list[apigw.Method] = []

        if iam_authorized_endpoints is not None:
            for endpoint in iam_authorized_endpoints:
                resource = self.apigw.root.resource_for_path(endpoint["path"])

                for method in endpoint["methods"]:
                    self._iam_authorized_methods.append(
                        resource.add_method(
                            method,
                            lambda_integration,
                            authorization_type=apigw.AuthorizationType.IAM,
                        )
                    )

        _ = self.apigw.root.add_proxy(
            default_integration=lambda_integration,
            default_method_options=apigw.MethodOptions(
                authorizer=apigw.CognitoUserPoolsAuthorizer(
                    self,
                    f"{id}-cognito-authorizer",
                    cognito_user_pools=[cognito_authorizer_pool],
                ),
                authorization_scopes=[
                    scope.scope_name for scope in cognito_authorization_scopes
                ]
                if cognito_authorization_scopes is not None
                else None,
            )
            if cognito_authorizer_pool is not None
            else None,
        )

    def grant_execute_on_iam_methods(self, grantee: iam.IGrantable) -> None:
        for method in self._iam_authorized_methods:
            _ = method.grant_execute(grantee)


@final
class GithubActionsDeployRole(iam.Role):
    _PROVIDER_URL = "token.actions.githubusercontent.com"

    def __init__(
        self,
        scope: Construct,
        id: str,
        *,
        repo: str,  # Match the usage in stack.py
        role_name: str = "GithubActionsDeployRole",
    ) -> None:
        account = cdk.Stack.of(scope).account

        # Import the provider (must be created manually)
        provider = iam.OpenIdConnectProvider.from_open_id_connect_provider_arn(
            scope,
            f"{id}-provider",
            f"arn:aws:iam::{account}:oidc-provider/{self._PROVIDER_URL}",
        )

        super().__init__(
            scope,
            id,
            role_name=role_name,
            assumed_by=iam.FederatedPrincipal(  # pyright: ignore[reportArgumentType]
                provider.open_id_connect_provider_arn,
                {
                    "StringLike": {f"{self._PROVIDER_URL}:sub": f"repo:{repo}:*"},
                    "StringEquals": {f"{self._PROVIDER_URL}:aud": "sts.amazonaws.com"},
                },
                "sts:AssumeRoleWithWebIdentity",
            ),
            description="Role assumed by GitHub Actions to deploy the stack",
        )

        # Grant permissions to assume CDK bootstrap roles
        _ = self.add_to_principal_policy(
            iam.PolicyStatement(
                actions=["sts:AssumeRole"],
                resources=[
                    f"arn:aws:iam::{account}:role/cdk-{cdk.DefaultStackSynthesizer.DEFAULT_QUALIFIER}-*"  # pyright: ignore[reportAny]
                ],
            )
        )
