import json
import uuid

from fastapi.testclient import TestClient
from mypy_boto3_sqs.service_resource import Queue


class TestDocuments:
    def test_document_lifecycle(
        self, client: TestClient, document_deletion_queue: Queue
    ) -> None:
        # Create
        id_ = str(uuid.uuid4())
        title = "Test Document"
        url = "https://example.com/test.pdf"
        r = client.post(
            "/documents",
            json={"document_id": id_, "title": title, "url": url},
        )
        assert r.status_code == 201

        # Read
        r = client.get("/documents")
        assert r.status_code == 200
        doc = r.json()["documents"][0]  # pyright: ignore[reportAny]
        assert doc["document_id"] == id_
        assert doc["title"] == title
        assert doc["url"] == url

        # Delete
        r = client.delete(f"/documents/{id_}")
        assert r.status_code == 204
        messages = document_deletion_queue.receive_messages()
        assert len(messages) == 1
        message = json.loads(messages[0].body)  # pyright: ignore[reportAny]
        assert message["document_id"] == id_

        # Verify deletion
        r = client.get("/documents")
        assert r.status_code == 200
        assert r.json()["documents"] == []

    def test_delete_document_not_found(self, client: TestClient) -> None:
        r = client.delete(f"/documents/{uuid.uuid4()}")
        assert r.status_code == 404


class TestDocumentLoadHistory:
    def test_document_load_lifecycle(
        self, client: TestClient, document_load_queue: Queue
    ) -> None:
        url = "https://example.com/document.pdf"

        # Create
        r = client.post("/documents/load", json={"source": "pdf", "url": url})
        assert r.status_code == 201
        messages = document_load_queue.receive_messages()
        assert len(messages) == 1
        message = json.loads(messages[0].body)  # pyright: ignore[reportAny]
        load_id = message["load_id"]  # pyright: ignore[reportAny]
        assert message["spec"] == {"source": "pdf", "url": url}

        # Read
        r = client.get("/documents/load_history")
        assert r.status_code == 200
        history_item = r.json()["load_history"][0]  # pyright: ignore[reportAny]
        assert history_item["source"] == "pdf"
        assert history_item["url"] == url
        assert history_item["status"] == "pending"

        # Update
        r = client.patch(f"/documents/load/{load_id}", json={"status": "in_progress"})
        assert r.status_code == 200

        r = client.get("/documents/load_history")
        assert r.json()["load_history"][0]["status"] == "in_progress"

        r = client.patch(f"/documents/load/{load_id}", json={"status": "completed"})
        assert r.status_code == 200

        r = client.get("/documents/load_history")
        assert r.json()["load_history"][0]["status"] == "completed"

    def test_update_load_history_not_found(self, client: TestClient) -> None:
        r = client.patch("/documents/load/invalid-id", json={"status": "in_progress"})
        assert r.status_code == 404
