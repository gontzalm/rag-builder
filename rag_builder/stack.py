import aws_cdk as cdk
import aws_cdk.aws_bedrock as bedrock
import aws_cdk.aws_cognito as cognito
import aws_cdk.aws_dynamodb as dynamodb
import aws_cdk.aws_iam as iam
import aws_cdk.aws_lambda_event_sources as lambda_events
import aws_cdk.aws_s3 as s3
import aws_cdk.aws_scheduler as scheduler
import aws_cdk.aws_scheduler_targets as scheduler_targets
import aws_cdk.aws_secretsmanager as secretsmanager
from aws_cdk import aws_sqs as sqs
from constructs import Construct

from rag_builder.constructs import (
    Endpoint,
    FastApiLambdaFunction,
    PythonFunction,
)


class RagBuilderStack(cdk.Stack):
    def __init__(self, scope: Construct, id: str, *, env: cdk.Environment) -> None:
        super().__init__(scope, id, env=env)

        # Storage
        vector_store_bucket = s3.Bucket(
            self,
            "vector-store-bucket",
            removal_policy=cdk.RemovalPolicy.DESTROY,
            auto_delete_objects=True,
        )

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
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=cdk.RemovalPolicy.DESTROY,
        )

        # Bedrock Models
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

        # SQS Queues
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

        # Cognito
        user_pool = cognito.UserPool(
            self,
            "user-pool",
            sign_in_aliases=cognito.SignInAliases(email=True),
            auto_verify=cognito.AutoVerifiedAttrs(email=True),
            self_sign_up_enabled=True,
            user_verification=cognito.UserVerificationConfig(
                email_subject="RAG Builder - Email verification",
                email_body="Thanks for signing up to RAG Builder. Your verification code is {####}.",
            ),
            email=cognito.UserPoolEmail.with_cognito(),
            removal_policy=cdk.RemovalPolicy.DESTROY,
        )
        user_pool_domain = user_pool.add_domain(
            "user-pool-domain",
            cognito_domain=cognito.CognitoDomainOptions(
                domain_prefix=f"rag-builder-{self.account}"
            ),
            managed_login_version=cognito.ManagedLoginVersion.NEWER_MANAGED_LOGIN,
        )

        # Backend API
        IAM_AUTHORIZED_ENDPOINTS: list[Endpoint] = [
            {"path": "/document/load/{id}", "methods": ["PATCH"]},
            {"path": "/document", "methods": ["POST"]},
        ]
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
            iam_authorized_endpoints=IAM_AUTHORIZED_ENDPOINTS,
        )
        _ = document_table.grant_read_write_data(backend_api.function)
        _ = document_load_history_table.grant_read_write_data(backend_api.function)
        _ = document_load_queue.grant_send_messages(backend_api.function)
        _ = document_deletion_queue.grant_send_messages(backend_api.function)

        # Frontend App
        frontend_app = FastApiLambdaFunction(
            self,
            "frontend-app-fastapi",
            environment={
                "COGNITO_USER_POOL_ID": user_pool.user_pool_id,
                "COGNITO_DOMAIN": user_pool_domain.base_url(),
                "BACKEND_API_URL": backend_api.apigw.url,
            },
        )
        _ = user_pool.grant(
            frontend_app.function,
            "cognito-idp:ListUserPoolClients",
            "cognito-idp:DescribeUserPoolClient",
        )

        app_client = user_pool.add_client(
            "frontend-app-client",
            # Predictable name to fetch the client ID and secret from the frontend app
            # Avoids circular dependencies in CDK (`frontend_app` must not depend on `app_client`)
            user_pool_client_name="frontend-app-client",
            o_auth=cognito.OAuthSettings(
                flows=cognito.OAuthFlows(authorization_code_grant=True),
                scopes=[
                    cognito.OAuthScope.OPENID,  # pyright: ignore[reportAny]
                    cognito.OAuthScope.EMAIL,  # pyright: ignore[reportAny]
                    cognito.OAuthScope.PROFILE,  # pyright: ignore[reportAny]
                ],
                callback_urls=[
                    "http://127.0.0.1:8000/auth/callback",
                    f"{frontend_app.apigw.url}/auth/callback",
                ],
                logout_urls=[
                    "http://127.0.0.1:8000/frontend/logged-out",
                    f"{frontend_app.apigw.url}/frontend/logged-out",
                ],
            ),
            generate_secret=True,
        )
        _ = cognito.CfnManagedLoginBranding(
            self,
            "frontend-app-managed-login-branding",
            user_pool_id=user_pool.user_pool_id,
            client_id=app_client.user_pool_client_id,
            use_cognito_provided_values=True,
        )

        app_secret_key_secret = secretsmanager.Secret(
            self, "frontend-app-secret-key-secret"
        )
        _ = frontend_app.function.add_environment(
            "APP_SECRET_KEY_SECRET", app_secret_key_secret.secret_name
        )
        _ = app_secret_key_secret.grant_read(frontend_app.function)

        # Lambda Functions
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

        # for endpoint in IAM_AUTHORIZED_ENDPOINTS:
        #     load_document_function.function.add_to_role_policy(
        #         iam.PolicyStatement(
        #             actions=["execute-api:Invoke"],
        #             resources=[
        #                 backend_api.apigw.arn_for_execute_api(
        #                     method=method,
        #                     path=endpoint["path"],
        #                     stage=backend_api.apigw.deployment_stage.stage_name,
        #                 )
        #                 for method in endpoint["methods"]
        #             ],
        #         )
        #     )
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

        query_knowledge_base_function = PythonFunction(
            self,
            "query-knowledge-base-function",
            containerized=True,
            memory=1024,
            timeout=cdk.Duration.minutes(1),
            environment={
                "VECTOR_STORE_BUCKET": vector_store_bucket.bucket_name,
                "EMBEDDINGS_MODEL": embeddings_model.model_arn.partition("/")[2],
                "AGENT_MODEL": agent_model.model_arn.partition("/")[2],
            },
        )
        _ = vector_store_bucket.grant_read(query_knowledge_base_function.function)
        query_knowledge_base_function.function.add_to_role_policy(
            iam.PolicyStatement(
                actions=["bedrock:InvokeModel"],
                resources=[embeddings_model.model_arn, agent_model.model_arn],
            )
        )
        _ = query_knowledge_base_function.function.grant_invoke(backend_api.function)
        _ = backend_api.function.add_environment(
            "QUERY_KNOWLEDGE_BASE_FUNCTION",
            query_knowledge_base_function.function.function_name,
        )
