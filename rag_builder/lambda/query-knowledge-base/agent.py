import logging
import os
import textwrap

from langchain.agents import create_agent  # pyright: ignore[reportUnknownVariableType]
from langchain.tools import tool  # pyright: ignore[reportUnknownVariableType]
from langchain_aws import BedrockEmbeddings, ChatBedrockConverse
from langchain_community.vectorstores import LanceDB
from langchain_core.documents import Document

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

_VECTOR_STORE_BUCKET = os.environ["VECTOR_STORE_BUCKET"]
_EMBEDDINGS_MODEL = os.environ["EMBEDDINGS_MODEL"]
_AGENT_MODEL = os.environ["AGENT_MODEL"]


vector_store = LanceDB(
    uri=f"s3://{_VECTOR_STORE_BUCKET}",
    embedding=BedrockEmbeddings(model_id=_EMBEDDINGS_MODEL),
)


@tool(response_format="content_and_artifact")
def retrieve_context(query: str) -> tuple[str, list[Document]]:
    """Retrieve information to help answer a query."""
    retrieved_docs = vector_store.similarity_search(query, k=2)
    serialized = "\n\n".join(
        (f"Source: {doc.metadata}\nContent: {doc.page_content}")  # pyright: ignore[reportUnknownMemberType]
        for doc in retrieved_docs
    )
    return serialized, retrieved_docs


model = ChatBedrockConverse(model=_AGENT_MODEL)
tools = [retrieve_context]
prompt = textwrap.dedent("""\
    - You have access to a tool that retrieves context from a vector store with
      different documents. Use the tool to help answer user queries.
    - If you can provide a reliable answer, also provide the references to the documents.
    - If you cannot provide a reliable answer, state it and kindly ask the user to only
      perform queries related to documents available in the vector store.
""")

rag_agent = create_agent(model, tools, system_prompt=prompt)  # pyright: ignore[reportUnknownVariableType]
