import secrets
import textwrap

import aws_cdk as cdk
import aws_cdk.aws_bedrock as bedrock
import aws_cdk.aws_cloudfront as cloudfront
import aws_cdk.aws_cloudfront_origins as cloudfront_origins
import aws_cdk.aws_cognito as cognito
import aws_cdk.aws_dynamodb as dynamodb
import aws_cdk.aws_ec2 as ec2
import aws_cdk.aws_ecs as ecs
import aws_cdk.aws_ecs_patterns as ecs_patterns
import aws_cdk.aws_iam as iam
import aws_cdk.aws_lambda_event_sources as lambda_events
import aws_cdk.aws_s3 as s3
import aws_cdk.aws_scheduler as scheduler
import aws_cdk.aws_scheduler_targets as scheduler_targets
from aws_cdk import aws_sqs as sqs
from constructs import Construct

from rag_builder.constructs import BASE_DIR, FastApiLambdaFunction, PythonFunction


class RagBuilderStack(cdk.Stack):
    def __init__(self, scope: Construct, id: str, *, env: cdk.Environment) -> None:
        super().__init__(scope, id, env=env)

        # S3
        vector_store_bucket = s3.Bucket(
            self,
            "vector-store-bucket",
            removal_policy=cdk.RemovalPolicy.DESTROY,
            auto_delete_objects=True,
        )

        chainlit_bucket = s3.Bucket(
            self,
            "chainlit-bucket",
            removal_policy=cdk.RemovalPolicy.DESTROY,
            auto_delete_objects=True,
        )

        # DYNAMODB
        document_table = dynamodb.Table(
            self,
            "document-table",
            partition_key=dynamodb.Attribute(
                name="document_id",
                type=dynamodb.AttributeType.STRING,
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=cdk.RemovalPolicy.DESTROY,
        )

        document_load_history_table = dynamodb.Table(
            self,
            "document-load-history-table",
            partition_key=dynamodb.Attribute(
                name="load_id",
                type=dynamodb.AttributeType.STRING,
            ),
            time_to_live_attribute="ttl",
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=cdk.RemovalPolicy.DESTROY,
        )

        chainlit_table = dynamodb.Table(
            self,
            "chainlit-table",
            partition_key=dynamodb.Attribute(
                name="PK",
                type=dynamodb.AttributeType.STRING,
            ),
            sort_key=dynamodb.Attribute(
                name="SK",
                type=dynamodb.AttributeType.STRING,
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=cdk.RemovalPolicy.DESTROY,
        )
        chainlit_table.add_global_secondary_index(
            index_name="UserThread",
            partition_key=dynamodb.Attribute(
                name="UserThreadPK",
                type=dynamodb.AttributeType.STRING,
            ),
            sort_key=dynamodb.Attribute(
                name="UserThreadSK",
                type=dynamodb.AttributeType.STRING,
            ),
            projection_type=dynamodb.ProjectionType.INCLUDE,
            non_key_attributes=["id", "name"],
        )

        # BEDROCK
        embeddings_model = bedrock.FoundationModel.from_foundation_model_id(
            self,
            "embeddings-model",
            bedrock.FoundationModelIdentifier.AMAZON_TITAN_EMBED_TEXT_V2_0,  # pyright: ignore[reportAny]
        )
        agent_model = bedrock.FoundationModel.from_foundation_model_id(
            self,
            "agent-model",
            bedrock.FoundationModelIdentifier.AMAZON_NOVA_PRO_V1_0,  # pyright: ignore[reportAny]
        )

        # SQS
        document_load_queue = sqs.Queue(
            self,
            "document-load-queue",
            visibility_timeout=cdk.Duration.minutes(5),
            dead_letter_queue=sqs.DeadLetterQueue(
                max_receive_count=2,
                queue=sqs.Queue(
                    self,
                    "document-load-queue-dlq",
                    removal_policy=cdk.RemovalPolicy.DESTROY,
                ),
            ),
            removal_policy=cdk.RemovalPolicy.DESTROY,
        )

        document_deletion_queue = sqs.Queue(
            self,
            "document-deletion-queue",
            visibility_timeout=cdk.Duration.minutes(5),
            dead_letter_queue=sqs.DeadLetterQueue(
                max_receive_count=2,
                queue=sqs.Queue(
                    self,
                    "document-deletion-queue-dlq",
                    removal_policy=cdk.RemovalPolicy.DESTROY,
                ),
            ),
            removal_policy=cdk.RemovalPolicy.DESTROY,
        )

        # COGNITO
        user_pool = cognito.UserPool(
            self,
            "user-pool",
            sign_in_aliases=cognito.SignInAliases(email=True),
            removal_policy=cdk.RemovalPolicy.DESTROY,
        )

        full_scope = cognito.ResourceServerScope(
            scope_name="documents.*",
            scope_description="Full access to the Document API",
        )
        resource_server = user_pool.add_resource_server(
            "user-pool-resource-server",
            identifier="backend-api",
            scopes=[full_scope],
        )
        oauth_scope = cognito.OAuthScope.resource_server(resource_server, full_scope)

        user_pool_domain = user_pool.add_domain(
            "user-pool-domain",
            cognito_domain=cognito.CognitoDomainOptions(
                domain_prefix=f"rag-builder-chainlit-app-{self.account}"
            ),
        )

        # BACKEND API
        backend_api = FastApiLambdaFunction(
            self,
            "backend-api-fastapi",
            environment={
                "DOCUMENT_TABLE": document_table.table_name,
                "DOCUMENT_LOAD_HISTORY_TABLE": document_load_history_table.table_name,
                "DOCUMENT_LOAD_QUEUE": document_load_queue.queue_url,
                "DOCUMENT_DELETION_QUEUE": document_deletion_queue.queue_url,
            },
            cognito_authorizer_pool=user_pool,
            cognito_authorization_scopes=[oauth_scope],
            iam_authorized_endpoints=[
                {"path": "/documents/load/{id}", "methods": ["PATCH"]},
                {"path": "/documents", "methods": ["POST"]},
            ],
        )
        _ = document_table.grant_read_write_data(backend_api.function)
        _ = document_load_history_table.grant_read_write_data(backend_api.function)
        _ = document_load_queue.grant_send_messages(backend_api.function)
        _ = document_deletion_queue.grant_send_messages(backend_api.function)

        # LAMBDA
        load_document_function = PythonFunction(
            self,
            "load-document-function",
            containerized=True,
            memory=1024,
            timeout=cdk.Duration.minutes(5),
            environment={
                "VECTOR_STORE_BUCKET": vector_store_bucket.bucket_name,
                "EMBEDDINGS_MODEL": embeddings_model.model_arn.partition("/")[2],
                "BACKEND_API_URL": backend_api.apigw.url,
            },
        )
        _ = vector_store_bucket.grant_read_write(load_document_function.function)
        load_document_function.function.add_to_role_policy(
            iam.PolicyStatement(
                actions=["bedrock:InvokeModel"], resources=[embeddings_model.model_arn]
            )
        )
        backend_api.grant_execute_on_iam_methods(load_document_function.function)

        load_document_function.function.add_event_source(
            lambda_events.SqsEventSource(document_load_queue, batch_size=1)
        )

        delete_document_function = PythonFunction(
            self,
            "delete-document-function",
            containerized=True,
            memory=256,
            timeout=cdk.Duration.minutes(1),
            environment={
                "VECTOR_STORE_BUCKET": vector_store_bucket.bucket_name,
            },
        )
        delete_document_function.function.add_event_source(
            lambda_events.SqsEventSource(document_deletion_queue, batch_size=1)
        )
        _ = vector_store_bucket.grant_read_write(delete_document_function.function)

        optimize_vector_store_function = PythonFunction(
            self,
            "optimize-vector-store-function",
            containerized=True,
            memory=512,
            timeout=cdk.Duration.minutes(5),
            environment={
                "VECTOR_STORE_BUCKET": vector_store_bucket.bucket_name,
            },
        )
        _ = vector_store_bucket.grant_read_write(
            optimize_vector_store_function.function
        )
        _ = vector_store_bucket.grant_delete(optimize_vector_store_function.function)
        _ = scheduler.Schedule(
            self,
            "optimize-vector-store-schedule",
            schedule=scheduler.ScheduleExpression.rate(cdk.Duration.days(7)),
            target=scheduler_targets.LambdaInvoke(
                optimize_vector_store_function.function  # pyright: ignore[reportArgumentType]
            ),
        )

        # FRONTEND APP
        deploy_chainlit: str | None = self.node.try_get_context("deploy_chainlit")  # pyright: ignore[reportAny]
        if deploy_chainlit is None or deploy_chainlit.lower() == "true":
            # Cloudfront -> ALB -> ECS Service (Fargate)
            chainlit_app = BASE_DIR / "fargate" / "chainlit-app"
            chainlit_app_fargate = ecs_patterns.ApplicationLoadBalancedFargateService(
                self,
                "chainlit-app-fargate",
                task_image_options=ecs_patterns.ApplicationLoadBalancedTaskImageOptions(
                    image=ecs.ContainerImage.from_asset(str(chainlit_app)),
                    container_port=8000,
                ),
                cpu=1024,
                memory_limit_mib=2048,
                circuit_breaker=ecs.DeploymentCircuitBreaker(rollback=True),
                listener_port=8000,
                open_listener=False,
            )
            chainlit_app_fargate.load_balancer.connections.allow_from(
                ec2.PrefixList.from_lookup(
                    self,
                    "cloudfront-prefix-list",
                    prefix_list_name="com.amazonaws.global.cloudfront.origin-facing",
                ),
                ec2.Port.tcp(8000),
            )
            _ = vector_store_bucket.grant_read(
                chainlit_app_fargate.task_definition.task_role
            )
            _ = chainlit_bucket.grant_read_write(
                chainlit_app_fargate.task_definition.task_role
            )
            _ = chainlit_table.grant_read_write_data(
                chainlit_app_fargate.task_definition.task_role
            )
            _ = chainlit_app_fargate.task_definition.add_to_task_role_policy(
                iam.PolicyStatement(
                    actions=["bedrock:InvokeModel"],
                    resources=[embeddings_model.model_arn],
                )
            )
            _ = chainlit_app_fargate.task_definition.add_to_task_role_policy(
                iam.PolicyStatement(
                    actions=["bedrock:InvokeModelWithResponseStream"],
                    resources=[agent_model.model_arn],
                ),
            )

            # Add a Cloudfront distribution in front of the ALB in order to use Cognito OAuth (it needs HTTPS)
            chainlit_app_distribution = cloudfront.Distribution(
                self,
                "chainlit-app-distribution",
                default_behavior=cloudfront.BehaviorOptions(
                    origin=cloudfront_origins.LoadBalancerV2Origin(
                        chainlit_app_fargate.load_balancer,
                        protocol_policy=cloudfront.OriginProtocolPolicy.HTTP_ONLY,
                        http_port=8000,
                    ),
                    viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                    allowed_methods=cloudfront.AllowedMethods.ALLOW_ALL,  # pyright: ignore[reportAny]
                    cache_policy=cloudfront.CachePolicy.CACHING_DISABLED,  # pyright: ignore[reportAny]
                    origin_request_policy=cloudfront.OriginRequestPolicy.ALL_VIEWER_EXCEPT_HOST_HEADER,  # pyright: ignore[reportAny]
                ),
            )
            _ = cdk.CfnOutput(
                self,
                "chainlit-app-url-output",
                value=f"https://{chainlit_app_distribution.domain_name}",
            )

            chainlit_client = user_pool.add_client(
                "chainlit-app-client",
                generate_secret=True,
                o_auth=cognito.OAuthSettings(
                    scopes=[
                        cognito.OAuthScope.OPENID,  # pyright: ignore[reportAny]
                        cognito.OAuthScope.PROFILE,  # pyright: ignore[reportAny]
                        cognito.OAuthScope.EMAIL,  # pyright: ignore[reportAny]
                        oauth_scope,
                    ],
                    callback_urls=[
                        "http://localhost:8000/auth/oauth/aws-cognito/callback",
                        f"https://{chainlit_app_distribution.domain_name}/auth/oauth/aws-cognito/callback",
                    ],
                    logout_urls=[
                        "http://localhost:8000/logout",
                        f"https://{chainlit_app_distribution.domain_name}/logout",
                    ],
                ),
            )

            for k, v in {
                # Auth
                "CHAINLIT_URL": f"https://{chainlit_app_distribution.domain_name}",
                "CHAINLIT_AUTH_SECRET": secrets.token_hex(64),
                "OAUTH_COGNITO_CLIENT_ID": chainlit_client.user_pool_client_id,
                "OAUTH_COGNITO_CLIENT_SECRET": chainlit_client.user_pool_client_secret.unsafe_unwrap(),
                "OAUTH_COGNITO_DOMAIN": user_pool_domain.base_url().removeprefix(
                    "https://"
                ),
                "OAUTH_COGNITO_SCOPE": f"openid profile email {oauth_scope.scope_name}",
                # AWS Resources
                "CHAINLIT_BUCKET": chainlit_bucket.bucket_name,
                "CHAINLIT_TABLE": chainlit_table.table_name,
                "VECTOR_STORE_BUCKET": vector_store_bucket.bucket_name,
                "EMBEDDINGS_MODEL": embeddings_model.model_arn.partition("/")[2],
                "AGENT_MODEL": agent_model.model_arn.partition("/")[2],
                "BACKEND_API_URL": backend_api.apigw.url,
            }.items():
                chainlit_app_fargate.task_definition.default_container.add_environment(  # pyright: ignore[reportOptionalMemberAccess]
                    k, v
                )

        else:
            # Cognito client for local development
            chainlit_client = user_pool.add_client(
                "chainlit-app-client",
                generate_secret=True,
                o_auth=cognito.OAuthSettings(
                    scopes=[
                        cognito.OAuthScope.OPENID,  # pyright: ignore[reportAny]
                        cognito.OAuthScope.PROFILE,  # pyright: ignore[reportAny]
                        cognito.OAuthScope.EMAIL,  # pyright: ignore[reportAny]
                        oauth_scope,
                    ],
                    callback_urls=[
                        "http://localhost:8000/auth/oauth/aws-cognito/callback",
                    ],
                    logout_urls=[
                        "http://localhost:8000/logout",
                    ],
                ),
            )

        _ = cdk.CfnOutput(
            self,
            "chainlit-app-local-dotenv-output",
            value=textwrap.dedent(f"""
                # COPY THIS TO (chainlit_app / .env) FOR LOCAL TESTING
                # DO NOT SHARE THIS FILE

                # Auth
                CHAINLIT_AUTH_SECRET={secrets.token_hex(64)}
                OAUTH_COGNITO_CLIENT_ID={chainlit_client.user_pool_client_id}
                OAUTH_COGNITO_CLIENT_SECRET={chainlit_client.user_pool_client_secret.unsafe_unwrap()}
                OAUTH_COGNITO_DOMAIN={user_pool_domain.base_url().removeprefix("https://")}
                OAUTH_COGNITO_SCOPE="openid profile email {oauth_scope.scope_name}"

                # AWS Resources
                CHAINLIT_BUCKET={chainlit_bucket.bucket_name}
                CHAINLIT_TABLE={chainlit_table.table_name}
                VECTOR_STORE_BUCKET={vector_store_bucket.bucket_name}
                EMBEDDINGS_MODEL={embeddings_model.model_arn.partition("/")[2]}
                AGENT_MODEL={agent_model.model_arn.partition("/")[2]}
                BACKEND_API_URL={backend_api.apigw.url}
            """),
        )
