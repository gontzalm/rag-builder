import logging
import os
import uuid
from datetime import datetime
from enum import Enum

import boto3  # pyright: ignore[reportMissingTypeStubs]
from boto3.dynamodb.conditions import Attr  # pyright: ignore[reportMissingTypeStubs]
from fastapi import APIRouter, HTTPException, status
from pydantic import UUID4, BaseModel, HttpUrl

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

INGESTION_QUEUE = os.environ["INGESTION_QUEUE"]
INGESTION_HISTORY_TABLE = os.environ["INGESTION_HISTORY_TABLE"]
DELETION_QUEUE = os.environ["DELETION_QUEUE"]

sqs = boto3.client("sqs")  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
dynamodb = boto3.client("dynamodb")  # pyright: ignore[reportUnknownVariableType, reportUnknownMemberType]

ingestion_history_table = boto3.resource("dynamodb").Table(INGESTION_HISTORY_TABLE)  # pyright: ignore[reportUnknownVariableType, reportUnknownMemberType, reportAttributeAccessIssue]


class Source(str, Enum):
    pdf = "pdf"


class Status(str, Enum):
    pending = "pending"
    in_progress = "in_progress"
    completed = "completed"
    failed = "failed"


class IngestionSpec(BaseModel):
    source: Source
    url: HttpUrl


class IngestionMessage(BaseModel):
    ingestion_id: UUID4
    spec: IngestionSpec


class Ingestion(BaseModel):
    ingestion_id: UUID4
    spec: IngestionSpec
    status: Status = Status.pending
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_details: str | None = None


class GetIngestionsResponse(BaseModel):
    ingestions: list[Ingestion]
    next_token: str | None = None


class UpdateIngestionValues(BaseModel):
    status: Status
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_details: str | None = None


class DeletionMessage(BaseModel):
    ingestion_id: UUID4


router = APIRouter(
    prefix="/ingest",
    tags=["ingest"],
)


@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_ingestion(spec: IngestionSpec) -> None:
    ingestion_id = uuid.uuid4()

    message = IngestionMessage(ingestion_id=ingestion_id, spec=spec)
    sqs.send_message(  # pyright: ignore[reportUnknownMemberType]
        QueueUrl=INGESTION_QUEUE,
        MessageBody=message.model_dump_json(),
    )

    logger.info(
        "Message sent to SQS queue '%s' for Ingestion ID '%s'",
        INGESTION_QUEUE,
        ingestion_id,
    )

    ingestion_history_table.put_item(  # pyright: ignore[reportUnknownMemberType]
        Item=Ingestion(ingestion_id=ingestion_id, spec=spec).model_dump(mode="json")
    )
    logger.info(
        "Inserted Ingestion ID '%s' status into DynamoDB table '%s'",
        ingestion_id,
        ingestion_history_table.table_name,  # pyright: ignore[reportUnknownArgumentType, reportUnknownMemberType]
    )


@router.get("/")
async def get_ingestions(next_token: str | None = None) -> GetIngestionsResponse:
    scan_kwargs = {}

    if next_token is not None:
        scan_kwargs["ExclusiveStartKey"] = next_token

    r = ingestion_history_table.scan(**scan_kwargs)  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
    items = r["Items"]  # pyright: ignore[reportUnknownVariableType]

    try:
        next_token = r["LastEvaluatedKey"]  # pyright: ignore[reportUnknownVariableType]
    except KeyError:
        return GetIngestionsResponse(ingestions=[Ingestion(**item) for item in items])  # pyright: ignore[reportUnknownArgumentType, reportUnknownVariableType]
    else:
        return GetIngestionsResponse(
            ingestions=[Ingestion(**item) for item in items],  # pyright: ignore[reportUnknownArgumentType, reportUnknownVariableType]
            next_token=next_token,  # pyright: ignore[reportUnknownArgumentType]
        )


@router.patch("/{ingestion_id}")
async def update_ingestion(
    ingestion_id: str, update_values: UpdateIngestionValues
) -> None:
    update_data = update_values.model_dump(mode="json", exclude_none=True)

    try:
        ingestion_history_table.update_item(  # pyright: ignore[reportUnknownMemberType]
            Key={"ingestion_id": ingestion_id},
            UpdateExpression=f"SET {', '.join(f'#{k} = :{k}' for k in update_data)}",
            ExpressionAttributeNames={f"#{k}": k for k in update_data},
            ExpressionAttributeValues={f":{k}": v for k, v in update_data.items()},  # pyright: ignore[reportAny]
            ConditionExpression=Attr("ingestion_id").exists(),
        )
    except dynamodb.exceptions.ConditionalCheckFailedException:  # pyright: ignore[reportUnknownMemberType]
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Ingestion ID '{ingestion_id}' not found",
        )

    logger.info(
        "Updated Ingestion ID '%s' with data: %s",
        ingestion_id,
        update_data,
    )


@router.delete("/{ingestion_id}")
async def delete_ingestion(ingestion_id: UUID4) -> None:
    try:
        ingestion_history_table.delete_item(  # pyright: ignore[reportUnknownMemberType]
            Key={"ingestion_id": ingestion_id},
            ConditionExpression=Attr("ingestion_id").exists(),
        )
    except dynamodb.exceptions.ConditionalCheckFailedException:  # pyright: ignore[reportUnknownMemberType]
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Ingestion ID '{ingestion_id}' not found",
        )

    message = DeletionMessage(ingestion_id=ingestion_id)
    sqs.send_message(  # pyright: ignore[reportUnknownMemberType]
        QueueUrl=DELETION_QUEUE,
        MessageBody=message.model_dump_json(),
    )
