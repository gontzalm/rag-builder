import json
import os
from unittest.mock import MagicMock

import pytest
from aws_lambda_powertools.utilities.typing import LambdaContext
from respx import MockRouter

from function import handler


@pytest.mark.respx(base_url=os.environ["BACKEND_API_URL"], assert_all_called=False)
@pytest.mark.usefixtures("path_write_bytes", "aws_auth")
class TestLoadDocument:
    @pytest.mark.usefixtures("pypdf_loader", "bedrock_embeddings")
    def test_load(
        self, respx_mock: MockRouter, lancedb: MagicMock, lancedb_table: MagicMock
    ):
        # Mock backend API calls
        patch_status_route = respx_mock.patch("/documents/load/test-load-123").respond(  # pyright: ignore[reportUnknownMemberType]
            200
        )
        route_add_doc = respx_mock.post("/documents").respond(200)  # pyright: ignore[reportUnknownMemberType]

        # Mock PDF download
        route_pdf = respx_mock.get("http://example.com/doc.pdf").respond(  # pyright: ignore[reportUnknownMemberType]
            200, content=b"pdf content"
        )

        # Run handler
        sqs_event = {
            "Records": [
                {
                    "messageId": "12345",
                    "body": json.dumps(
                        {
                            "load_id": "test-load-123",
                            "spec": {
                                "source": "pdf",
                                "url": "http://example.com/doc.pdf",
                            },
                        }
                    ),
                }
            ]
        }

        handler(sqs_event, LambdaContext())

        # Verify HTTP calls
        assert patch_status_route.call_count == 2
        assert (
            json.loads(patch_status_route.calls[0].request.content)["status"]  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]
            == "in_progress"
        )
        assert (
            json.loads(patch_status_route.calls[1].request.content)["status"]  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]
            == "completed"
        )

        assert route_add_doc.call_count == 1
        assert (
            json.loads(route_add_doc.calls.last.request.content)["document_id"]
            == "test-load-123"
        )

        assert route_pdf.call_count == 1

        # Verify LanceDB interactions
        lancedb.add_documents.assert_called_once()  # pyright: ignore[reportAny]
        lancedb_table.create_fts_index.assert_called_once_with("text")  # pyright: ignore[reportAny]
        lancedb_table.wait_for_index.assert_called_once_with(["text_idx"])  # pyright: ignore[reportAny]

    @pytest.mark.usefixtures("pypdf_loader")
    def test_load_failed(self, respx_mock: MockRouter, lancedb: MagicMock):
        # respx_mock.base_url = "http://test-api"

        # Simulate an error during add_documents
        lancedb.add_documents.side_effect = Exception("LanceDB failed to add documents")  # pyright: ignore[reportAny]

        # Mock backend API calls
        patch_status_route = respx_mock.patch("/documents/load/test-load-123").respond(  # pyright: ignore[reportUnknownMemberType]
            200
        )
        route_add_doc = respx_mock.post("/documents").respond(200)  # pyright: ignore[reportUnknownMemberType]

        # Mock PDF download
        route_pdf = respx_mock.get("http://example.com/doc.pdf").respond(  # pyright: ignore[reportUnknownMemberType]
            200, content=b"pdf content"
        )

        # Run handler
        sqs_event = {
            "Records": [
                {
                    "messageId": "12345",
                    "body": json.dumps(
                        {
                            "load_id": "test-load-123",
                            "spec": {
                                "source": "pdf",
                                "url": "http://example.com/doc.pdf",
                            },
                        }
                    ),
                }
            ]
        }

        handler(sqs_event, LambdaContext())

        # Verify HTTP calls
        assert patch_status_route.call_count == 2
        assert (
            json.loads(patch_status_route.calls[0].request.content)["status"]  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]
            == "in_progress"
        )
        assert (
            json.loads(patch_status_route.calls[1].request.content)["status"]  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]
            == "failed"
        )

        assert not route_add_doc.called

        assert route_pdf.call_count == 1

    def test_unsupported_source(self) -> None:
        sqs_event = {
            "Records": [
                {
                    "messageId": "12345",
                    "body": json.dumps(
                        {
                            "load_id": "test-load-456",
                            "spec": {
                                "source": "unsupported",
                                "url": "http://example.com/doc.txt",
                            },
                        }
                    ),
                }
            ]
        }

        with pytest.raises(NotImplementedError):
            handler(sqs_event, LambdaContext())
