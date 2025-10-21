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

        ingestion_status_table = dynamodb.Table(
            self,
            "ingestion-status-table",
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
            environment={"INGESTION_QUEUE": ingestion_queue.queue_name},
        )
        ingestion_status_table.grant_read_write_data(backend_api)
        ingestion_queue.grant_send_messages(backend_api)

        ingest_function = PythonFunction(
            self,
            "ingest-function",
            memory=1024,
            environment={
                "BUCKET": embeddings_bucket.name,
                "INGESTION_STATUS_TABLE": ingestion_status_table.name,
            },
        )
        ingest_function.add_event_source(
            lambda_events.SqsEventSource(ingestion_queue, batch_size=1)
        )
        embeddings_bucket.grant_read_write(ingest_function)
        ingestion_status_table.grant_read_write_data(ingest_function)
