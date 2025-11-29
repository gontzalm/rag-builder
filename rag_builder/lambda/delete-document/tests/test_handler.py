import json
import os
from unittest.mock import MagicMock

from aws_lambda_powertools.utilities.typing import LambdaContext

from function import handler


class TestDeleteDocument:
    def test_delete(self, lancedb: MagicMock) -> None:
        document_id = "test-document-123"
        sqs_event = {
            "Records": [
                {
                    "messageId": "msg-123",
                    "body": json.dumps({"document_id": document_id}),
                    "eventSource": "aws:sqs",
                    "eventSourceARN": "arn:aws:sqs:us-east-1:123456789012:test-queue",
                    "awsRegion": "us-east-1",
                }
            ]
        }

        handler(sqs_event, LambdaContext())

        lancedb.open_table.assert_called_once_with("vectorstore")  # pyright: ignore[reportAny]
        lancedb.open_table.return_value.delete.assert_called_once_with(  # pyright: ignore[reportAny]
            f"id like '{document_id}%'"
        )
