import logging
import os
import uuid
from datetime import UTC, datetime, timedelta
from enum import Enum

import boto3  # pyright: ignore[reportMissingTypeStubs]
from boto3.dynamodb.conditions import Attr  # pyright: ignore[reportMissingTypeStubs]
from fastapi import APIRouter, HTTPException, status
from pydantic import UUID4, BaseModel, HttpUrl

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

DOCUMENT_TABLE = os.environ["DOCUMENT_TABLE"]
DOCUMENT_LOAD_HISTORY_TABLE = os.environ["DOCUMENT_LOAD_HISTORY_TABLE"]
DOCUMENT_LOAD_QUEUE = os.environ["DOCUMENT_LOAD_QUEUE"]
DOCUMENT_DELETION_QUEUE = os.environ["DOCUMENT_DELETION_QUEUE"]

sqs = boto3.client("sqs")  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
dynamodb = boto3.client("dynamodb")  # pyright: ignore[reportUnknownVariableType, reportUnknownMemberType]

document_table = boto3.resource("dynamodb").Table(DOCUMENT_TABLE)  # pyright: ignore[reportUnknownVariableType, reportUnknownMemberType, reportAttributeAccessIssue]
document_load_history_table = boto3.resource("dynamodb").Table(  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType, reportAttributeAccessIssue]
    DOCUMENT_LOAD_HISTORY_TABLE
)


class Source(str, Enum):
    pdf = "pdf"


class Status(str, Enum):
    pending = "pending"
    in_progress = "in_progress"
    completed = "completed"
    failed = "failed"


class DocumentLoadSpec(BaseModel):
    source: Source
    url: HttpUrl


class DocumentLoadMessage(BaseModel):
    load_id: UUID4
    spec: DocumentLoadSpec


class DocumentLoad(BaseModel):
    load_id: UUID4
    source: Source
    url: HttpUrl
    status: Status = Status.pending
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_details: str | None = None
    ttl: int


class DocumentLoadProjected(BaseModel):
    source: Source
    url: HttpUrl
    status: Status
    started_at: datetime | None
    completed_at: datetime | None
    error_details: str | None = None


class GetLoadHistoryResponse(BaseModel):
    load_history: list[DocumentLoadProjected]
    next_token: str | None = None


class UpdateDocumentLoad(BaseModel):
    status: Status
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_details: str | None = None


class CreateDocumentRequest(BaseModel):
    title: str
    url: HttpUrl


class Document(BaseModel):
    document_id: UUID4
    title: str
    url: HttpUrl
    added_at: datetime


class GetDocumentsResponse(BaseModel):
    documents: list[Document]
    next_token: str | None = None


class DocumentDeletionMessage(BaseModel):
    document_id: str


router = APIRouter(
    prefix="/documents",
    tags=["documents"],
)


@router.post("/load", status_code=status.HTTP_201_CREATED)
async def load_document(spec: DocumentLoadSpec) -> None:
    load_id = uuid.uuid4()

    message = DocumentLoadMessage(load_id=load_id, spec=spec)
    sqs.send_message(  # pyright: ignore[reportUnknownMemberType]
        QueueUrl=DOCUMENT_LOAD_QUEUE,
        MessageBody=message.model_dump_json(),
    )

    logger.info(
        "Message sent to SQS queue '%s' for document load ID '%s'",
        DOCUMENT_LOAD_QUEUE,
        load_id,
    )

    document_load_history_table.put_item(  # pyright: ignore[reportUnknownMemberType]
        Item=DocumentLoad(
            load_id=load_id,
            source=spec.source,
            url=spec.url,
            ttl=int((datetime.now(tz=UTC) + timedelta(days=7)).timestamp()),
        ).model_dump(mode="json")
    )
    logger.info(
        "Inserted document load ID '%s' status into DynamoDB table '%s'",
        load_id,
        document_load_history_table.table_name,  # pyright: ignore[reportUnknownArgumentType, reportUnknownMemberType]
    )


@router.get("/load_history")
async def get_load_history(next_token: str | None = None) -> GetLoadHistoryResponse:
    scan_kwargs = {
        "ProjectionExpression": ",".join(
            f"#{f}" for f in DocumentLoadProjected.model_fields
        ),
        # Avoid conflict with reserved keywords
        "ExpressionAttributeNames": {
            f"#{f}": f for f in DocumentLoadProjected.model_fields
        },
    }

    if next_token is not None:
        scan_kwargs["ExclusiveStartKey"] = next_token

    r = document_load_history_table.scan(**scan_kwargs)  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
    items = r["Items"]  # pyright: ignore[reportUnknownVariableType]

    try:
        next_token = r["LastEvaluatedKey"]  # pyright: ignore[reportUnknownVariableType]
    except KeyError:
        return GetLoadHistoryResponse(
            load_history=[DocumentLoadProjected(**item) for item in items]  # pyright: ignore[reportUnknownVariableType, reportUnknownArgumentType]
        )
    else:
        return GetLoadHistoryResponse(
            load_history=[DocumentLoadProjected(**item) for item in items],  # pyright: ignore[reportUnknownArgumentType, reportUnknownVariableType]
            next_token=next_token,  # pyright: ignore[reportUnknownArgumentType]
        )


@router.patch("/load/{load_id}")
async def update_load(load_id: str, update_values: UpdateDocumentLoad) -> None:
    update_data = update_values.model_dump(mode="json", exclude_none=True)

    try:
        document_load_history_table.update_item(  # pyright: ignore[reportUnknownMemberType]
            Key={"load_id": load_id},
            UpdateExpression=f"SET {', '.join(f'#{k} = :{k}' for k in update_data)}",
            ExpressionAttributeNames={f"#{k}": k for k in update_data},
            ExpressionAttributeValues={f":{k}": v for k, v in update_data.items()},  # pyright: ignore[reportAny]
            ConditionExpression=Attr("load_id").exists(),
        )
    except dynamodb.exceptions.ConditionalCheckFailedException:  # pyright: ignore[reportUnknownMemberType]
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document load ID '{load_id}' not found",
        )

    logger.info(
        "Updated document load ID '%s' with data: %s",
        load_id,
        update_data,
    )


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_document(doc: CreateDocumentRequest) -> None:
    document_id = uuid.uuid4()

    document_table.put_item(  # pyright: ignore[reportUnknownMemberType]
        Item=Document(
            document_id=document_id,
            title=doc.title,
            url=doc.url,
            added_at=datetime.now(tz=UTC),
        ).model_dump(mode="json")
    )
    logger.info(
        "Inserted document ID '%s' into DynamoDB table '%s'",
        document_id,
        document_table.table_name,  # pyright: ignore[reportUnknownArgumentType, reportUnknownMemberType]
    )


@router.get("")
async def get_documents(next_token: str | None = None) -> GetDocumentsResponse:
    scan_kwargs = {}

    if next_token is not None:
        scan_kwargs["ExclusiveStartKey"] = next_token

    r = document_table.scan(**scan_kwargs)  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
    items = r["Items"]  # pyright: ignore[reportUnknownVariableType]

    try:
        next_token = r["LastEvaluatedKey"]  # pyright: ignore[reportUnknownVariableType]
    except KeyError:
        return GetDocumentsResponse(
            documents=[Document(**item) for item in items]  # pyright: ignore[reportUnknownVariableType, reportUnknownArgumentType]
        )
    else:
        return GetDocumentsResponse(
            documents=[Document(**item) for item in items],  # pyright: ignore[reportUnknownArgumentType, reportUnknownVariableType]
            next_token=next_token,  # pyright: ignore[reportUnknownArgumentType]
        )


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(document_id: str) -> None:
    try:
        document_table.delete_item(  # pyright: ignore[reportUnknownMemberType]
            Key={"document_id": document_id},
            ConditionExpression=Attr("document_id").exists(),
        )
    except dynamodb.exceptions.ConditionalCheckFailedException:  # pyright: ignore[reportUnknownMemberType]
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document ID '{document_id}' not found",
        )

    message = DocumentDeletionMessage(document_id=document_id)
    sqs.send_message(  # pyright: ignore[reportUnknownMemberType]
        QueueUrl=DOCUMENT_DELETION_QUEUE,
        MessageBody=message.model_dump_json(),
    )
