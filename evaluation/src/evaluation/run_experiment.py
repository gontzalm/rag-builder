import asyncio
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any

import boto3
import instructor
import lancedb  # pyright: ignore[reportMissingTypeStubs]
import typer
from lancedb.rerankers import RRFReranker  # pyright: ignore[reportMissingTypeStubs]
from langchain.agents import create_agent  # pyright: ignore[reportUnknownVariableType]
from langchain.tools import tool  # pyright: ignore[reportUnknownVariableType]
from langchain_aws import BedrockEmbeddings, ChatBedrockConverse
from langchain_core.messages import HumanMessage
from ragas import Dataset, experiment  # pyright: ignore[reportUnknownVariableType]
from ragas.llms.base import InstructorLLM
from ragas.metrics.collections import AnswerAccuracy, Faithfulness
from rich.table import Table

from .console import get_console

RESULTS_CSV = Path("experiments/results.csv")

app = typer.Typer()

console = get_console()


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
        table_name = f"evaluation_{embedding_model.replace(':', '-')}"
        try:
            table = await db.open_table(table_name)
        except ValueError:
            console.print(
                f"❌ LanceDB table '{table_name}' not found, please run the `uv run create-kb {embedding_model}` command first",
                style="error",
            )
            _ = typer.Exit(code=1)

        retrieved_docs = await (  # pyright: ignore[reportUnknownVariableType]
            table.query()  # pyright: ignore[reportUnknownMemberType, reportPossiblyUnboundVariable]
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
            boto3.client("bedrock-runtime"),  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]
            async_client=True,
        ),
    )

    experiment_id = uuid.uuid4()
    experimented_at = datetime.now(tz=UTC)

    @experiment()
    async def rag_experiment(row: dict[str, str]) -> dict[str, Any]:  # pyright: ignore[reportExplicitAny]
        response = await agent.ainvoke({"messages": [HumanMessage(row["user_input"])]})  # pyright: ignore[reportUnknownMemberType]

        retrieved_contexts = response["messages"][-2].content.split("\n--\n")  # pyright: ignore[reportAny]
        agent_response = response["messages"][-1].content  # pyright: ignore[reportAny]

        # Compute metrics
        faithfulness = await Faithfulness(llm=evaluator_llm).ascore(
            user_input=row["user_input"],
            response=agent_response,  # pyright: ignore[reportAny]
            retrieved_contexts=retrieved_contexts,  # pyright: ignore[reportAny]
        )
        answer_accuracy = await AnswerAccuracy(llm=evaluator_llm).ascore(
            user_input=row["user_input"],
            response=agent_response,  # pyright: ignore[reportAny]
            reference=row["reference"],
        )

        return {
            **row,
            "response": agent_response,
            "faithfulness_score": faithfulness.value,  # pyright: ignore[reportAny]  # pyright: ignore[reportAny]
            "answer_accuracy_score": answer_accuracy.value,  # pyright: ignore[reportAny]
            # metadata
            "experiment_id": experiment_id,
            "experimented_at": experimented_at,
            "agent_model": agent_model,
            "temperature": temperature,
            "system_prompt": system_prompt,
            "embedding_model": embedding_model,
        }

    testset = Dataset.load("synthetic-testset", "local/csv", root_dir=".")  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
    results = await rag_experiment.arun(testset)  # pyright: ignore[reportUnknownMemberType]

    RESULTS_CSV.parent.mkdir(exist_ok=True)
    results.to_pandas().to_csv(
        RESULTS_CSV, header=(not RESULTS_CSV.exists()), mode="a", index=False
    )
    console.print(f"💾 Experiment results saved to '{RESULTS_CSV}'", style="success")


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
        typer.Option(help="Bedrock embedding model for the knowledge base"),
    ] = "amazon.titan-embed-text-v2:0",
    evaluator_model: Annotated[
        str, typer.Option(help="Bedrock model for the metrics evaluation")
    ] = "us.anthropic.claude-sonnet-4-20250514-v1:0",
) -> None:
    """Run an experiment with the specified parameters"""
    console.print("🚀 Running experiment with specified parameters", style="info")
    table = Table(
        title="Experiment Configuration",
        style="table",
        header_style="table.header",
    )
    table.add_column("Agent Model", style="data")
    table.add_column("Temperature", style="metric")
    table.add_column("System Prompt", style="info")
    table.add_column("Embedding Model", style="data")
    table.add_column("Evaluator Model", style="data")
    table.add_row(
        agent_model,
        f"{temperature:.2f}",
        system_prompt,
        embedding_model,
        evaluator_model,
    )
    console.print(table)
    asyncio.run(
        _run_experiment(
            agent_model, temperature, system_prompt, embedding_model, evaluator_model
        )
    )
