import asyncio
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import boto3  # pyright: ignore[reportMissingTypeStubs]
import instructor
import lancedb  # pyright: ignore[reportMissingTypeStubs]
import typer
from lancedb.rerankers import RRFReranker  # pyright: ignore[reportMissingTypeStubs]
from langchain.agents import create_agent  # pyright: ignore[reportUnknownVariableType]
from langchain.tools import tool  # pyright: ignore[reportUnknownVariableType]
from langchain_aws import BedrockEmbeddings, ChatBedrockConverse
from langchain_community.document_loaders import PyPDFDirectoryLoader
from langchain_core.messages import HumanMessage
from langchain_core.outputs import ChatGeneration, ChatResult, LLMResult
from ragas import Dataset, experiment  # pyright: ignore[reportUnknownVariableType]
from ragas.cost import TokenUsage
from ragas.llms.base import InstructorLLM
from ragas.metrics.collections import AnswerAccuracy, Faithfulness
from ragas.run_config import RunConfig
from rich.console import Console
from rich.table import Table

RESULTS_CSV = Path("experiments/results.csv")

app = typer.Typer()

console = Console()
console_err = Console(stderr=True)


async def _run_experiment(
    agent_model: str,
    temperature: float,
    system_prompt: str,
    embedding_model: str,
    evaluator_model: str,
) -> None:
    @tool
    async def retrieve_context(query: str) -> str:
        """Retrieves information to help answer a query."""
        db = await lancedb.connect_async(f"s3://{os.environ['VECTOR_STORE_BUCKET']}")

        table = await db.open_table(f"evaluation_{embedding_model.replace(':', '-')}")

        retrieved_docs = await (  # pyright: ignore[reportUnknownVariableType]
            table.query()  # pyright: ignore[reportUnknownMemberType]
            # Vector search (should use an index for databases with >100k vectors)
            .nearest_to(
                await BedrockEmbeddings(model_id=embedding_model).aembed_query(query)
            )
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

    agent = create_agent(  # pyright: ignore[reportUnknownVariableType]
        ChatBedrockConverse(model=agent_model, temperature=temperature),
        [retrieve_context],
        system_prompt=(Path("system-prompts") / system_prompt)
        .with_suffix(".md")
        .read_text(),
    )

    evaluator_llm = InstructorLLM(
        model=evaluator_model,
        provider="bedrock",
        client=instructor.from_bedrock(
            boto3.client("bedrock-runtime"), async_client=True
        ),
    )

    experiment_id = uuid.uuid4()
    experimented_at = datetime.now(tz=UTC)

    @experiment()
    async def rag_experiment(row: dict[str, str]) -> dict[str, Any]:
        response = await agent.ainvoke({"messages": [HumanMessage(row["user_input"])]})

        retrieved_contexts = response["messages"][-2].content
        agent_response = response["messages"][-1].content

        print(retrieved_contexts)
        print(agent_response)

        # Compute metrics
        faithfulness = await Faithfulness(llm=evaluator_llm).ascore(
            user_input=row["user_input"],
            response=agent_response,
            retrieved_contexts=retrieved_contexts,
        )
        answer_accuracy = await AnswerAccuracy(llm=evaluator_llm).ascore(
            user_input=row["user_input"],
            response=agent_response,
            reference=row["reference"],
        )

        return {
            **row,
            "response": agent_response,
            "faithfulness_score": faithfulness.value,
            "answer_accuracy_score": answer_accuracy.value,
            # metadata
            "experiment_id": experiment_id,
            "experimented_at": experimented_at,
            "agent_model": agent_model,
            "temperature": temperature,
            "system_prompt": system_prompt,
            "embedding_model": embedding_model,
        }

    testset = Dataset.load("synthetic-testset", "local/csv", root_dir=".")

    results = await rag_experiment.arun(testset)
    results.to_pandas().to_csv(
        RESULTS_CSV, header=(not RESULTS_CSV.exists()), mode="a", index=False
    )


@app.command()
def run_experiment(
    agent_model: Annotated[
        str,
        typer.Argument(help="Bedrock model for the agent"),
    ],
    temperature: Annotated[
        float, typer.Argument(help="Temperature of the agent model")
    ],
    system_prompt: Annotated[
        str,
        typer.Argument(
            help="Name of the system prompt in the 'system_prompts' directory for the agent"
        ),
    ],
    embedding_model: Annotated[
        str,
        typer.Argument(help="Bedrock embedding model for the knowledge base"),
    ] = "amazon.titan-embed-text-v2:0",
    evaluator_model: Annotated[
        str, typer.Argument(help="Bedrock model for the metrics evaluation")
    ] = "us.anthropic.claude-sonnet-4-20250514-v1:0",
) -> None:
    """Run an experiment with the specified parameters"""

    asyncio.run(
        _run_experiment(
            agent_model, temperature, system_prompt, embedding_model, evaluator_model
        )
    )
