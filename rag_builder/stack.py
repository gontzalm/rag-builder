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

        embeddings_bucket = s3.Bucket(
            self, "embeddings-bucket", removal_policy=cdk.RemovalPolicy.DESTROY
        )

        embeddings_model = bedrock.FoundationModel.from_foundation_model_id(
            self,
            "embeddings-model",
            bedrock.FoundationModelIdentifier.AMAZON_TITAN_EMBED_TEXT_V2_0,  # pyright: ignore[reportAny]
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

        backend_api = FastApiLambdaFunction(
            self,
            "backend-api-fastapi",
            environment={
                "INGESTION_QUEUE": ingestion_queue.queue_url,
                "DELETION_QUEUE": deletion_queue.queue_url,
                "INGESTION_HISTORY_TABLE": ingestion_history_table.table_name,
            },
        )
        _ = ingestion_history_table.grant_read_write_data(backend_api.function)
        _ = ingestion_queue.grant_send_messages(backend_api.function)
        _ = deletion_queue.grant_send_messages(backend_api.function)

        ingest_function = DockerPythonFunction(
            self,
            "ingest-function",
            memory=1024,
            timeout=cdk.Duration.minutes(5),
            environment={
                "EMBEDDINGS_BUCKET": embeddings_bucket.bucket_name,
                "EMBEDDINGS_MODEL": embeddings_model.model_arn.partition("/")[2],
                "BACKEND_API_URL": backend_api.apigw.url,
            },
        )
        ingest_function.add_event_source(
            lambda_events.SqsEventSource(ingestion_queue, batch_size=1)
        )
        _ = embeddings_bucket.grant_read_write(ingest_function)
        _ = ingestion_history_table.grant_read_write_data(ingest_function)
        ingest_function.add_to_role_policy(
            iam.PolicyStatement(
                actions=["bedrock:InvokeModel"], resources=[embeddings_model.model_arn]
            )
        )

        delete_function = PythonFunction(
            self,
            "delete-function",
            memory=1024,
            timeout=cdk.Duration.minutes(1),
            environment={
                "EMBEDDINGS_BUCKET": embeddings_bucket.bucket_name,
            },
        )
        _ = embeddings_bucket.grant_read(delete_function)
        _ = embeddings_bucket.grant_delete(delete_function)
