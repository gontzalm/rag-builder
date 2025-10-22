import json
import logging
from typing import Any, TypedDict

from aws_lambda_powertools.utilities.data_classes.sqs_event import SQSEvent

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class IngestionSpec(TypedDict):
    source: str
    url: str


class IngestionMessage(TypedDict):
    ingestion_id: str
    spec: IngestionSpec


def handler(event: dict[str, Any], _) -> None:  # pyright: ignore[reportExplicitAny]
    sqs_event = SQSEvent(event)
    record = next(sqs_event.records)
    logger.info("Processing SQS message ID %s", record.message_id)

    message_data: IngestionMessage = json.loads(record.body)  # pyright: ignore[reportAny]

    ingestion_id = message_data["ingestion_id"]
    ingestion_spec = message_data["spec"]

    logger.info("Successfully parsed message for Ingestion ID %s", ingestion_id)
    logger.info(f"Ingestion spec: {ingestion_spec}")

    # TODO: implement ingestion logic
