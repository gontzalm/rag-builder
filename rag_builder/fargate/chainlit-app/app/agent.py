import os
from pathlib import Path
from typing import Any, TypedDict

import chainlit as cl
import lancedb  # pyright: ignore[reportMissingTypeStubs]
from lancedb.rerankers import RRFReranker  # pyright: ignore[reportMissingTypeStubs]
from langchain.agents import (
    AgentState,
    create_agent,  # pyright: ignore[reportUnknownVariableType]
)
from langchain.agents.middleware import before_model
from langchain.messages import AIMessage, AnyMessage, HumanMessage, RemoveMessage
from langchain.tools import tool  # pyright: ignore[reportUnknownVariableType]
from langchain_aws import BedrockEmbeddings, ChatBedrockConverse
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.runtime import Runtime

_VECTOR_STORE_BUCKET = os.environ["VECTOR_STORE_BUCKET"]

MAX_MEMORY_WINDOW = 10
EMBEDDING_MODEL = BedrockEmbeddings(model_id=os.environ["EMBEDDINGS_MODEL"])
AGENT_MODEL = ChatBedrockConverse(model=os.environ["AGENT_MODEL"], temperature=0.5)
SYSTEM_PROMPT = Path("agent_instructions.md")


class Conversation(TypedDict):
    thread_id: str
    messages: list[HumanMessage | AIMessage]


async def is_vector_store_empty(db: lancedb.AsyncConnection) -> bool:
    try:
        _ = await db.open_table("vectorstore")
    except ValueError:
        return True
    else:
        return False


@tool
async def retrieve_context(query: str) -> str:
    """Retrieves information to help answer a query."""
    db = await lancedb.connect_async(f"s3://{_VECTOR_STORE_BUCKET}")

    if await is_vector_store_empty(db):
        return "The vector store is empty."

    # Hybrid search via `langchain_community.vectorstores.LanceDB` is currently not working
    # retrieved_docs = await VECTOR_STORE.asimilarity_search(query, query_type="hybrid")

    # Workaround: Hybrid search directly via LancedDB
    table = await db.open_table("vectorstore")

    retrieved_docs = await (  # pyright: ignore[reportUnknownVariableType]
        table.query()  # pyright: ignore[reportUnknownMemberType]
        # Vector search (should use an index for databases with >100k vectors)
        .nearest_to(await EMBEDDING_MODEL.aembed_query(query))
        # + Keyword search (needs an FTS index)
        .nearest_to_text(query)
        .rerank(reranker=RRFReranker())
        .limit(10)
        .select(["metadata", "text"])
        .to_list()
    )
    return "\n--\n".join(
        f"Source: {doc['metadata']}\nContent: {doc['text']}"
        for doc in retrieved_docs  # pyright: ignore[reportUnknownVariableType]
    )


@before_model  # pyright: ignore[reportCallIssue, reportArgumentType, reportUntypedFunctionDecorator]
def delete_messages(state: AgentState, _: Runtime) -> dict[str, list[Any]] | None:  # pyright: ignore[reportMissingTypeArgument, reportExplicitAny, reportUnknownParameterType]
    """Deletes messages to keep a maximum conversation size of MAX_MEMORY_WINDOW."""
    messages = state["messages"]

    if len(messages) <= MAX_MEMORY_WINDOW:
        return

    minimum_to_delete = len(messages) - MAX_MEMORY_WINDOW
    messages_to_delete: list[AnyMessage] = []

    for i, message in enumerate(messages, 1):
        if i <= minimum_to_delete:
            messages_to_delete.append(message)
            continue

        # The first message must be a HumanMessage in order to avoid a Bedrock validation exception
        if message.type != "human":
            messages_to_delete.append(message)
        else:
            break

    return {
        "messages": [
            RemoveMessage(message.id)  # pyright: ignore[reportArgumentType]
            for message in messages_to_delete
        ]
    }


def setup_agent(conversation: Conversation | None = None) -> None:
    """Sets up an agent, optionally restoring a conversation.

    Args:
        conversation: A past conversation to restore.
    """
    agent = create_agent(  # pyright: ignore[reportUnknownVariableType]
        AGENT_MODEL,
        [retrieve_context],
        system_prompt=SYSTEM_PROMPT.read_text(),
        middleware=[delete_messages],  # pyright: ignore[reportArgumentType]
        checkpointer=InMemorySaver(),
    )

    if conversation is not None:
        messages = conversation["messages"][-MAX_MEMORY_WINDOW:]

        # The first message must be a HumanMessage in order to avoid a Bedrock validation exception
        while not isinstance(messages[0], HumanMessage):
            _ = messages.pop(0)

        _ = agent.update_state(
            {"configurable": {"thread_id": conversation["thread_id"]}},
            {"messages": messages},
        )

    cl.user_session.set("agent", agent)  # pyright: ignore[reportUnknownMemberType]
