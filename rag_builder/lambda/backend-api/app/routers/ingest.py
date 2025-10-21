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
sqs = boto3.client("sqs")


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


class IngestionStartedResponse(BaseModel):
    ingestion_id: UUID4


class IngestionStatus(BaseModel):
    ingestion_id: UUID4
    status: Status = Status.pending
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_details: str | None = None


router = APIRouter(
    prefix="/ingest",
    tags=["ingest"],
)


@router.post("/")
async def ingest(spec: IngestionSpec) -> IngestionStartedResponse:
    ingestion_id = uuid.uuid4()

    message_body = {
        "ingestion_id": str(ingestion_id),
        "spec": spec.model_dump(),
    }
    sqs.send_message(  # pyright: ignore[reportUnknownMemberType]
        QueueUrl=INGESTION_QUEUE,
        MessageBody=json.dumps(message_body),
    )
    logger.info("Message sent for Ingestion ID '%s'", ingestion_id)

    # TODO: add ingestion status to DDB table

    return IngestionStartedResponse(ingestion_id=ingestion_id)


@router.get("/")
async def get_ingestions() -> list[IngestionStatus]:
    # TODO: implement
    return [IngestionStatus(ingestion_id=uuid.uuid4())]
