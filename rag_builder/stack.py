import aws_cdk as cdk
import aws_cdk.aws_dynamodb as dynamodb
import aws_cdk.aws_lambda as lambda_
import aws_cdk.aws_s3 as s3
from aws_cdk import aws_sqs as sqs
from constructs import Construct

from rag_builder.constructs import FastApiLambdaFunction


class RagBuilderStack(cdk.Stack):
    def __init__(self, scope: Construct, id: str, *, env: cdk.Environment) -> None:
        super().__init__(scope, id, env=env)

        bucket = s3.Bucket(self, "bucket", removal_policy=cdk.RemovalPolicy.DESTROY)

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
            dead_letter_queue=sqs.DeadLetterQueue(
                max_receive_count=3,  # Max number of times a message can be processed before moving to DLQ
                queue=sqs.Queue(
                    self,
                    "ingestion-queue-dlq",
                    removal_policy=cdk.RemovalPolicy.DESTROY,
                ),
            ),
            visibility_timeout=cdk.Duration.minutes(5),
            removal_policy=cdk.RemovalPolicy.DESTROY,
        )

        # Backend
        backend_api = FastApiLambdaFunction(
            self,
            "backend-api-fastapi",
            python_runtime=lambda_.Runtime.PYTHON_3_13,  # pyright: ignore[reportAny]
            environment={"INGESTION_QUEUE": ingestion_queue.queue_name},
        )
