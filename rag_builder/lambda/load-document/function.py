import json
import logging
from typing import Any, TypedDict

from aws_lambda_powertools.utilities.data_classes.sqs_event import SQSEvent

from loader import PdfLoader

logger = logging.getLogger()
logger.setLevel(logging.INFO)


class DocumentLoadSpec(TypedDict):
    source: str
    url: str


class DocumentLoadMessage(TypedDict):
    load_id: str
    spec: DocumentLoadSpec


def handler(event: dict[str, Any], _) -> None:  # pyright: ignore[reportExplicitAny]
    sqs_event = SQSEvent(event)
    record = next(sqs_event.records)
    logger.info("Processing SQS message ID '%s'", record.message_id)

    message_data: DocumentLoadMessage = json.loads(record.body)  # pyright: ignore[reportAny]

    load_id = message_data["load_id"]
    load_spec = message_data["spec"]

    logger.info("Successfully parsed message for document load ID '%s'", load_id)
    logger.info(f"Ingestion spec: {load_spec}")

    match load_spec["source"]:
        case "pdf":
            with PdfLoader(load_id, load_spec["url"]) as loader:
                loader.load_document()
        case _:
            raise NotImplementedError
