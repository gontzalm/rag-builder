import json
import logging
import os

import boto3  # pyright: ignore[reportMissingTypeStubs]
from fastapi import APIRouter
from pydantic import BaseModel

logger = logging.getLogger(__name__)


QUERY_FUNCTION = os.environ["QUERY_FUNCTION"]

lambda_ = boto3.client("lambda")  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]


class QueryResponse(BaseModel):
    model_response: str


router = APIRouter(
    prefix="/query",
    tags=["query"],
)


@router.get("/")
async def query_knowledge_base(query: str) -> QueryResponse:
    logger.info(
        "Invoking lambda function '%s' with user query '%s'",
        QUERY_FUNCTION,
        query,
    )
    r = lambda_.invoke(  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
        FunctionName=QUERY_FUNCTION, Payload=json.dumps({"query": query})
    )
    payload = json.loads(r["Payload"].read())  # pyright: ignore[reportAny, reportUnknownMemberType, reportUnknownArgumentType]
    return QueryResponse(model_response=payload["model_response"])  # pyright: ignore[reportAny]
