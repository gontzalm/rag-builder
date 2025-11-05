import logging
from typing import TypedDict

from langchain_core.messages import HumanMessage

from agent import rag_agent  # pyright: ignore[reportUnknownVariableType]

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class Request(TypedDict):
    query: str


class Response(TypedDict):
    status_code: int
    payload: dict[str, str] | None


def handler(payload: Request, _) -> Response:
    logger.info("Querying knowledge base with user query '%s'", payload["query"])

    user_query = payload["query"]
    agent_response = (  # pyright: ignore[reportAny]
        rag_agent.invoke({"messages": [HumanMessage(user_query)]})[  # pyright: ignore[reportUnknownMemberType]
            "messages"
        ][-1]
    )

    return {
        "status_code": 200,
        "payload": {"agent_response": agent_response.pretty_repr()},  # pyright: ignore[reportAny]
    }
