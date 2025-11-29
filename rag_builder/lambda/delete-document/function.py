import json
import logging
from typing import Any, TypedDict

from aws_lambda_powertools.utilities.data_classes.sqs_event import SQSEvent
from aws_lambda_powertools.utilities.typing import LambdaContext

from deleter import LanceDbDeleter

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class DocumentDeletionMessage(TypedDict):
    document_id: str


def handler(event: dict[str, Any], _: LambdaContext) -> None:  # pyright: ignore[reportExplicitAny]
    sqs_event = SQSEvent(event)
    record = next(sqs_event.records)
    logger.info("Processing SQS message ID '%s'", record.message_id)

    message_data: DocumentDeletionMessage = json.loads(record.body)  # pyright: ignore[reportAny]

    document_id = message_data["document_id"]

    logger.info("Successfully parsed message for document ID '%s'", document_id)

    LanceDbDeleter(document_id).delete_document()
