import aws_cdk as cdk
import aws_cdk.aws_bedrock as bedrock
import aws_cdk.aws_dynamodb as dynamodb
import aws_cdk.aws_iam as iam
import aws_cdk.aws_lambda_event_sources as lambda_events
import aws_cdk.aws_s3 as s3
from aws_cdk import aws_sqs as sqs
from constructs import Construct

from rag_builder.constructs import (
    DockerPythonFunction,
    FastApiLambdaFunction,
    PythonFunction,
)


class RagBuilderStack(cdk.Stack):
    def __init__(self, scope: Construct, id: str, *, env: cdk.Environment) -> None:
        super().__init__(scope, id, env=env)

        # Storage
        embeddings_bucket = s3.Bucket(
            self, "embeddings-bucket", removal_policy=cdk.RemovalPolicy.DESTROY
        )

        ingestion_history_table = dynamodb.Table(
            self,
            "ingestion-history-table",
            partition_key=dynamodb.Attribute(
                name="ingestion_id",
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
        ingestion_queue = sqs.Queue(
            self,
            "ingestion-queue",
            visibility_timeout=cdk.Duration.minutes(5),
            dead_letter_queue=sqs.DeadLetterQueue(
                max_receive_count=2,
                queue=sqs.Queue(
                    self,
                    "ingestion-queue-dlq",
                    removal_policy=cdk.RemovalPolicy.DESTROY,
                ),
            ),
            removal_policy=cdk.RemovalPolicy.DESTROY,
        )

        deletion_queue = sqs.Queue(
            self,
            "deletion-queue",
            visibility_timeout=cdk.Duration.minutes(5),
            dead_letter_queue=sqs.DeadLetterQueue(
                max_receive_count=2,
                queue=sqs.Queue(
                    self,
                    "deletion-queue-dlq",
                    removal_policy=cdk.RemovalPolicy.DESTROY,
                ),
            ),
            removal_policy=cdk.RemovalPolicy.DESTROY,
        )

        # Lambda Functions (1)
        query_knowledge_base_function = PythonFunction(
            self,
            "query-knowledge-base-function",
            memory=1024,
            timeout=cdk.Duration.minutes(1),
            environment={
                "EMBEDDINGS_BUCKET": embeddings_bucket.bucket_name,
                "EMBEDDINGS_MODEL": embeddings_model.model_arn.partition("/")[2],
                "AGENT_MODEL": agent_model.model_arn.partition("/")[2],
            },
        )

        # FastAPI APIs
        backend_api = FastApiLambdaFunction(
            self,
            "backend-api-fastapi",
            environment={
                "INGESTION_QUEUE": ingestion_queue.queue_url,
                "INGESTION_HISTORY_TABLE": ingestion_history_table.table_name,
                "DELETION_QUEUE": deletion_queue.queue_url,
                "QUERY_FUNCTION": query_knowledge_base_function.function_name,
            },
        )
        _ = ingestion_queue.grant_send_messages(backend_api.function)
        _ = ingestion_history_table.grant_read_write_data(backend_api.function)
        _ = deletion_queue.grant_send_messages(backend_api.function)
        _ = query_knowledge_base_function.grant_invoke(backend_api.function)

        # Lambda Functions (2)
        ingest_document_function = DockerPythonFunction(
            self,
            "ingest-document-function",
            memory=1024,
            timeout=cdk.Duration.minutes(5),
            environment={
                "EMBEDDINGS_BUCKET": embeddings_bucket.bucket_name,
                "EMBEDDINGS_MODEL": embeddings_model.model_arn.partition("/")[2],
                "BACKEND_API_URL": backend_api.apigw.url,
            },
        )
        ingest_document_function.add_event_source(
            lambda_events.SqsEventSource(ingestion_queue, batch_size=1)
        )
        _ = embeddings_bucket.grant_read_write(ingest_document_function)
        _ = ingestion_history_table.grant_read_write_data(ingest_document_function)
        ingest_document_function.add_to_role_policy(
            iam.PolicyStatement(
                actions=["bedrock:InvokeModel"], resources=[embeddings_model.model_arn]
            )
        )

        delete_document_function = PythonFunction(
            self,
            "delete-document-function",
            memory=256,
            timeout=cdk.Duration.minutes(1),
            environment={
                "EMBEDDINGS_BUCKET": embeddings_bucket.bucket_name,
            },
        )
        delete_document_function.add_event_source(
            lambda_events.SqsEventSource(deletion_queue, batch_size=1)
        )
        _ = embeddings_bucket.grant_read(delete_document_function)
        _ = embeddings_bucket.grant_delete(delete_document_function)
