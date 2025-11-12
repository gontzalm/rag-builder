import aws_cdk as cdk
import aws_cdk.aws_bedrock as bedrock
import aws_cdk.aws_cloudfront as cloudfront
import aws_cdk.aws_cloudfront_origins as cloudfront_origins
import aws_cdk.aws_cognito as cognito
import aws_cdk.aws_dynamodb as dynamodb
import aws_cdk.aws_iam as iam
import aws_cdk.aws_lambda_event_sources as lambda_events
import aws_cdk.aws_s3 as s3
import aws_cdk.aws_s3_deployment as s3_deployment
import aws_cdk.aws_scheduler as scheduler
import aws_cdk.aws_scheduler_targets as scheduler_targets
from aws_cdk import aws_sqs as sqs
from constructs import Construct

from rag_builder.constructs import FastApiLambdaFunction, PythonFunction


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
            removal_policy=cdk.RemovalPolicy.DESTROY,
        )
        _ = cdk.CfnOutput(self, "user-pool-id-output", value=user_pool.user_pool_id)

        # Frontend App
        app_client = user_pool.add_client(
            "frontend-app-client",
        )
        _ = cdk.CfnOutput(
            self, "user-pool-client-output", value=app_client.user_pool_client_id
        )
        # TODO: add Chainlint App Runner deployment

        # Backend API
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
            iam_authorized_endpoints=[
                {"path": "/document/load/{id}", "methods": ["PATCH"]},
                {"path": "/document", "methods": ["POST"]},
            ],
        )
        _ = document_table.grant_read_write_data(backend_api.function)
        _ = document_load_history_table.grant_read_write_data(backend_api.function)
        _ = document_load_queue.grant_send_messages(backend_api.function)
        _ = document_deletion_queue.grant_send_messages(backend_api.function)

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

        # TODO: move logic to chainlit app
        # query_knowledge_base_function = PythonFunction(
        #     self,
        #     "query-knowledge-base-function",
        #     containerized=True,
        #     memory=1024,
        #     timeout=cdk.Duration.minutes(1),
        #     environment={
        #         "VECTOR_STORE_BUCKET": vector_store_bucket.bucket_name,
        #         "EMBEDDINGS_MODEL": embeddings_model.model_arn.partition("/")[2],
        #         "AGENT_MODEL": agent_model.model_arn.partition("/")[2],
        #     },
        # )
        # _ = vector_store_bucket.grant_read(query_knowledge_base_function.function)
        # query_knowledge_base_function.function.add_to_role_policy(
        #     iam.PolicyStatement(
        #         actions=["bedrock:InvokeModel"],
        #         resources=[embeddings_model.model_arn, agent_model.model_arn],
        #     )
        # )
        # _ = query_knowledge_base_function.function.grant_invoke(backend_api.function)
        # _ = backend_api.function.add_environment(
        #     "QUERY_KNOWLEDGE_BASE_FUNCTION",
        #     query_knowledge_base_function.function.function_name,
        # )
