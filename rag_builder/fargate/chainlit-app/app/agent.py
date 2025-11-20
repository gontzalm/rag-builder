import os
from pathlib import Path
from typing import Any, TypedDict

import chainlit as cl
from langchain.agents import (
    AgentState,
    create_agent,  # pyright: ignore[reportUnknownVariableType]
)
from langchain.agents.middleware import before_model
from langchain.messages import AIMessage, AnyMessage, HumanMessage, RemoveMessage
from langchain.tools import tool  # pyright: ignore[reportUnknownVariableType]
from langchain_aws import BedrockEmbeddings, ChatBedrockConverse
from langchain_community.vectorstores import LanceDB
from langchain_core.documents import Document
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.runtime import Runtime

_VECTOR_STORE_BUCKET = os.environ["VECTOR_STORE_BUCKET"]
_EMBEDDINGS_MODEL = os.environ["EMBEDDINGS_MODEL"]
_AGENT_MODEL = os.environ["AGENT_MODEL"]

MAX_MEMORY_WINDOW = 10
VECTOR_STORE = LanceDB(
    uri=f"s3://{_VECTOR_STORE_BUCKET}",
    embedding=BedrockEmbeddings(model_id=_EMBEDDINGS_MODEL),
)
MODEL = ChatBedrockConverse(model=_AGENT_MODEL, temperature=0.5)
SYSTEM_PROMPT = Path("agent_instructions.md")


class Conversation(TypedDict):
    thread_id: str
    messages: list[HumanMessage | AIMessage]


@tool(response_format="content_and_artifact")
def retrieve_context(query: str) -> tuple[str, list[Document]]:
    """Retrieves information to help answer a query."""
    retrieved_docs = VECTOR_STORE.similarity_search(query, k=2)
    serialized = "\n\n".join(
        (f"Source: {doc.metadata}\nContent: {doc.page_content}")  # pyright: ignore[reportUnknownMemberType]
        for doc in retrieved_docs
    )
    return serialized, retrieved_docs


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

        # Keep deleting messages until the first message is a human message in order to
        # avoid a Bedrock validation exception
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
        MODEL,
        [retrieve_context],
        system_prompt=SYSTEM_PROMPT.read_text(),
        middleware=[delete_messages],  # pyright: ignore[reportArgumentType]
        checkpointer=InMemorySaver(),
    )

    if conversation is not None:
        _ = agent.update_state(
            {"configurable": {"thread_id": conversation["thread_id"]}},
            {"messages": conversation["messages"]},
        )

    cl.user_session.set("agent", agent)  # pyright: ignore[reportUnknownMemberType]
