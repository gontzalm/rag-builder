from fastapi.testclient import TestClient


class TestMain:
    def test_root(self, client: TestClient):
        response = client.get("/")
        assert response.status_code == 200
        assert (
            response.json()["message"]
            == "Welcome to the RAG Builder app Backend API! Navigate to /docs to browse the OpenAPI docs"
        )
