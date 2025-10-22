import aws_cdk as cdk
import aws_cdk.aws_dynamodb as dynamodb
import aws_cdk.aws_lambda as lambda_
import aws_cdk.aws_lambda_event_sources as lambda_events
import aws_cdk.aws_s3 as s3
from aws_cdk import aws_sqs as sqs
from constructs import Construct

from rag_builder.constructs import FastApiLambdaFunction, PythonFunction


class RagBuilderStack(cdk.Stack):
    def __init__(self, scope: Construct, id: str, *, env: cdk.Environment) -> None:
        super().__init__(scope, id, env=env)

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

        backend_api = FastApiLambdaFunction(
            self,
            "backend-api-fastapi",
            python_runtime=lambda_.Runtime.PYTHON_3_13,  # pyright: ignore[reportAny]
            environment={
                "INGESTION_QUEUE": ingestion_queue.queue_url,
                "INGESTION_HISTORY_TABLE": ingestion_history_table.table_name,
            },
        )
        _ = ingestion_history_table.grant_read_write_data(backend_api.function)
        _ = ingestion_queue.grant_send_messages(backend_api.function)

        ingest_function = PythonFunction(
            self,
            "ingest-function",
            memory=1024,
            environment={
                "EMBEDDINGS_BUCKET": embeddings_bucket.bucket_name,
                "INGESTION_HISTORY_TABLE": ingestion_history_table.table_name,
            },
        )
        ingest_function.add_event_source(
            lambda_events.SqsEventSource(ingestion_queue, batch_size=1)
        )
        _ = embeddings_bucket.grant_read_write(ingest_function)
        _ = ingestion_history_table.grant_read_write_data(ingest_function)
