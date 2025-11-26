import os
from collections.abc import Generator

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from mypy_boto3_dynamodb.service_resource import DynamoDBServiceResource, Table
from mypy_boto3_sqs.service_resource import Queue, SQSServiceResource

ENDPOINT_URL = "http://localhost:8000"
os.environ["DYNAMODB_ENDPOINT_URL"] = ENDPOINT_URL

os.environ["CORS_ALLOW_ORIGINS"] = ""


@pytest.fixture(scope="session")
def sqs() -> Generator[SQSServiceResource, None, None]:
    """Mocks SQS service with moto."""
    with mock_aws():
        yield boto3.resource("sqs")  # pyright: ignore[reportUnknownMemberType]


@pytest.fixture(scope="session")
def document_load_queue(sqs: SQSServiceResource) -> Generator[Queue, None, None]:
    yield sqs.create_queue(QueueName="document-load-queue")


@pytest.fixture(scope="session")
def document_deletion_queue(sqs: SQSServiceResource) -> Generator[Queue, None, None]:
    yield sqs.create_queue(QueueName="document-deletion-queue")


@pytest.fixture(scope="session")
def dynamodb() -> Generator[DynamoDBServiceResource, None, None]:
    """Mocks DynamoDB service with dynamodb-local."""
    yield boto3.resource("dynamodb", endpoint_url=ENDPOINT_URL)  # pyright: ignore[reportUnknownMemberType]


@pytest.fixture(scope="session")
def documents_table(dynamodb: DynamoDBServiceResource) -> Generator[Table, None, None]:
    table = dynamodb.create_table(
        TableName="documents",
        KeySchema=[{"AttributeName": "document_id", "KeyType": "HASH"}],
        AttributeDefinitions=[{"AttributeName": "document_id", "AttributeType": "S"}],
        ProvisionedThroughput={"ReadCapacityUnits": 1, "WriteCapacityUnits": 1},
    )

    table.wait_until_exists()
    yield table
    _ = table.delete()


@pytest.fixture(scope="session")
def document_load_history_table(
    dynamodb: DynamoDBServiceResource,
) -> Generator[Table, None, None]:
    table = dynamodb.create_table(
        TableName="document-load-history",
        KeySchema=[{"AttributeName": "load_id", "KeyType": "HASH"}],
        AttributeDefinitions=[{"AttributeName": "load_id", "AttributeType": "S"}],
        ProvisionedThroughput={"ReadCapacityUnits": 1, "WriteCapacityUnits": 1},
    )

    table.wait_until_exists()
    yield table
    _ = table.delete()


@pytest.fixture(scope="session")
def client(
    document_load_queue: Queue,
    document_deletion_queue: Queue,
    documents_table: Table,
    document_load_history_table: Table,
) -> Generator[TestClient, None, None]:
    """Create a TestClient for the FastAPI app."""
    os.environ["DOCUMENT_LOAD_QUEUE"] = document_load_queue.url
    os.environ["DOCUMENT_DELETION_QUEUE"] = document_deletion_queue.url
    os.environ["DOCUMENT_TABLE"] = documents_table.table_name
    os.environ["DOCUMENT_LOAD_HISTORY_TABLE"] = document_load_history_table.table_name

    from app.main import app

    with TestClient(app) as client:
        yield client
