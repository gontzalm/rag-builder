import json
import logging
from typing import Any, TypedDict

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class QueryRequest(TypedDict):
    query: str


class QueryResponse(TypedDict):
    status_code: int
    payload: dict[str, str] | None


def handler(payload: QueryRequest, _) -> QueryResponse:
    logger.info("Querying knowledge base with user query '%s'", payload["query"])

    model_response = "response here"

    return {"status_code": 200, "payload": {"model_response": model_response}}
