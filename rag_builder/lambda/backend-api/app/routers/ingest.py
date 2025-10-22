import json
import logging
import os
import uuid
from datetime import datetime
from enum import Enum

import boto3
from fastapi import APIRouter, HTTPException
from pydantic import UUID4, BaseModel, HttpUrl

logger = logging.getLogger(__name__)

INGESTION_QUEUE = os.environ["INGESTION_QUEUE"]
INGESTION_HISTORY_TABLE = os.environ["INGESTION_HISTORY_TABLE"]

sqs = boto3.client("sqs")  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
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


class PostIngestionResponse(BaseModel):
    ingestion_id: UUID4


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


router = APIRouter(
    prefix="/ingest",
    tags=["ingest"],
)


@router.post("/")
async def ingest(spec: IngestionSpec) -> PostIngestionResponse:
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

    return PostIngestionResponse(ingestion_id=ingestion_id)


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
