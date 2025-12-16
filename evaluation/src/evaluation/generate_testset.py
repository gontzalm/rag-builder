import random
from pathlib import Path
from typing import Annotated

import typer
from langchain_aws import BedrockEmbeddings, ChatBedrockConverse
from langchain_community.document_loaders import PyPDFDirectoryLoader
from langchain_core.outputs import ChatGeneration, ChatResult, LLMResult
from langchain_core.prompt_values import StringPromptValue
from ragas.cost import TokenUsage
from ragas.embeddings import BaseRagasEmbeddings, LangchainEmbeddingsWrapper
from ragas.llms import BaseRagasLLM, LangchainLLMWrapper
from ragas.run_config import RunConfig
from ragas.testset import TestsetGenerator
from ragas.testset.graph import KnowledgeGraph, Node, NodeType
from ragas.testset.persona import generate_personas_from_kg
from ragas.testset.synthesizers.single_hop.specific import (
    SingleHopSpecificQuerySynthesizer,
)
from ragas.testset.transforms import (
    HeadlinesExtractor,
    HeadlineSplitter,
    KeyphrasesExtractor,
    apply_transforms,
)
from rich.table import Table

from .console import get_console

RUN_CONFIG = RunConfig(max_workers=8)
KB_DOCS = Path("documents")
TESTSET_CSV = Path("datasets/synthetic-testset.csv")
MODEL_PRICING_PER_1K = {
    "us.anthropic.claude-sonnet-4-5-20250929-v1:0": {
        "input": 0.003,
        "output": 0.015,
    }
}

app = typer.Typer()

console = get_console()


def adapt_kg_for_persona_generation(
    kg: KnowledgeGraph,
    *,
    llm: BaseRagasLLM,
    embedding_model: BaseRagasEmbeddings,
    sample_size: int = 20,
    min_content_length: int = 200,  # change after tape recording
) -> None:
    """
    Augments a random subset of nodes in the provided KnowledgeGraph (kg)
    in-place with 'summary' and 'summary_embedding' properties required by ragas.

    Args:
        kg: KnowledgeGraph object to modify.
        llm: LLM for summarization.
        embedding_model: Model for generating embeddings.
        sample_size: Number of nodes to sample and augment.
        min_content_length: Minimum page_content length for a node to be considered.
    """
    console.print("🔧 Adapting knowledge graph for persona generation", style="info")
    candidate_nodes = [
        node
        for node in kg.nodes
        if len(node.properties["page_content"]) >= min_content_length  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]
    ]

    effective_sample_size = min(sample_size, len(candidate_nodes))
    if effective_sample_size == 0:
        console.print(
            "❌ No nodes meet the minimum content length for persona generation",
            style="error",
        )
        _ = typer.Exit(code=1)

    sampled_nodes = random.sample(candidate_nodes, effective_sample_size)

    for i, node in enumerate(sampled_nodes):
        console.print(
            f"  🧠 [{i + 1}/{effective_sample_size}] Processing Node ID: {node.id}",
            style="info",
        )

        # necessary for RAGAS default node filter for persona generation
        node.type = NodeType.DOCUMENT

        content = node.properties["page_content"]  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]

        summarization_prompt = StringPromptValue(
            text=f"""\
            Briefly and concisely summarize the following document content in
            one or two sentences. Focus on the main topic and purpose.

            CONTENT: {content}
        """
        )

        result = llm.generate_text(summarization_prompt)
        node.properties["summary"] = result.generations[0][0].text  # pyright: ignore[reportUnknownMemberType]
        node.properties["summary_embedding"] = embedding_model.embed_query(  # pyright: ignore[reportUnknownMemberType]
            node.properties["summary"]  # pyright: ignore[reportUnknownMemberType]
        )


def get_token_usage_for_bedrock(
    llm_result: LLMResult | ChatResult,
) -> TokenUsage:
    token_usages = [
        TokenUsage(
            input_tokens=g.message.usage_metadata["input_tokens"],  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType, reportAttributeAccessIssue]
            output_tokens=g.message.usage_metadata["output_tokens"],  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType, reportAttributeAccessIssue]
            model=g.message.response_metadata["model_name"],  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]
        )
        for gs in llm_result.generations
        for g in gs
        if isinstance(g, ChatGeneration)
    ]
    model = next((usage.model for usage in token_usages if usage.model), "")
    return sum(token_usages, TokenUsage(input_tokens=0, output_tokens=0, model=model))


@app.command()
def generate_testset(
    generator_model: Annotated[
        str, typer.Option(help="Bedrock model to use for the testset generation")
    ] = "us.anthropic.claude-sonnet-4-5-20250929-v1:0",
    size: Annotated[int, typer.Option(help="Number of test samples to generate")] = 10,
) -> None:
    """Generate a synthetic testset with RAGAS based on the evaluation knowledge base"""
    if not KB_DOCS.exists() or not next(KB_DOCS.iterdir()):
        console.print(
            "❌ Evaluation knowledge base documents not found, run the `create-kb` command first",
            style="error",
        )
        raise typer.Exit(code=1)

    console.print("🕸️ Creating knowledge graph from documents", style="info")
    loader = PyPDFDirectoryLoader("documents")
    kg = KnowledgeGraph(
        [
            Node(
                properties={"page_content": doc.page_content, "metadata": doc.metadata}  # pyright: ignore[reportUnknownMemberType]
            )
            for doc in loader.lazy_load()
        ]
    )

    generator_llm = LangchainLLMWrapper(ChatBedrockConverse(model=generator_model))  # pyright: ignore[reportAny]
    generator_embeddings = LangchainEmbeddingsWrapper(  # pyright: ignore[reportAny]
        BedrockEmbeddings(model_id="amazon.titan-embed-text-v2:0")
    )

    console.print("⚡ Applying transforms to knowledge graph", style="info")
    transforms = [
        HeadlinesExtractor(llm=generator_llm),  # pyright: ignore[reportAny]
        HeadlineSplitter(),
        KeyphrasesExtractor(llm=generator_llm),  # pyright: ignore[reportAny]
    ]
    apply_transforms(kg, transforms, run_config=RUN_CONFIG)  # pyright: ignore[reportArgumentType]

    adapt_kg_for_persona_generation(
        kg,
        llm=generator_llm,  # pyright: ignore[reportAny]
        embedding_model=generator_embeddings,  # pyright: ignore[reportAny]
    )
    console.print("👥 Generating personas", style="info")
    personas = generate_personas_from_kg(kg, generator_llm)  # pyright: ignore[reportAny]
    table = Table(title="Personas", style="table", header_style="table.header")
    table.add_column("Name", style="metric")
    table.add_column("Role", style="data")
    for p in personas:
        table.add_row(p.name, p.role_description)
    console.print(table)

    console.print(f"🏗️ Generating synthetic testset with {size} samples", style="info")
    console.print(
        "⚠️ This operation will incur costs from Bedrock model usage", style="warning"
    )
    generator = TestsetGenerator(
        llm=generator_llm,  # pyright: ignore[reportAny]
        embedding_model=generator_embeddings,  # pyright: ignore[reportAny]
        knowledge_graph=kg,
        persona_list=personas,
    )
    query_distibution = [
        (
            SingleHopSpecificQuerySynthesizer(
                llm=generator_llm,  # pyright: ignore[reportAny]
                property_name="headlines",
            ),
            0.5,
        ),
        (
            SingleHopSpecificQuerySynthesizer(
                llm=generator_llm,  # pyright: ignore[reportAny]
                property_name="keyphrases",
            ),
            0.5,
        ),
    ]
    testset = generator.generate(  # pyright: ignore[reportUnknownMemberType]
        size,
        query_distribution=query_distibution,  # pyright: ignore[reportArgumentType]
        run_config=RUN_CONFIG,
        token_usage_parser=get_token_usage_for_bedrock,
    )

    console.print(f"💾 Saving testset to '{TESTSET_CSV}'", style="info")
    TESTSET_CSV.parent.mkdir(exist_ok=True)
    testset.to_evaluation_dataset().to_csv(TESTSET_CSV)  # pyright: ignore[reportAttributeAccessIssue, reportUnusedCallResult, reportUnknownMemberType]

    console.print("📊 Computing usage metrics", style="info")
    model_pricing = MODEL_PRICING_PER_1K[generator_model]
    usage = testset.total_tokens()  # pyright: ignore[reportUnknownMemberType, reportAttributeAccessIssue, reportUnknownVariableType]
    cost = testset.total_cost(  # pyright: ignore[reportUnknownMemberType, reportAttributeAccessIssue, reportUnknownVariableType]
        model_pricing["input"] / 1e3, model_pricing["output"] / 1e3
    )

    table = Table(title="Usage Metrics", style="table", header_style="table.header")
    table.add_column("Model", style="data")
    table.add_column("Metric", style="metric")
    table.add_column("Value", style="data")
    table.add_column("Price / 1K", style="data")
    table.add_row(
        usage.model,  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType, reportAttributeAccessIssue]
        "Input Tokens",
        f"{usage.input_tokens:,}",  # pyright: ignore[reportUnknownMemberType, reportAttributeAccessIssue]
        f"${model_pricing['input']:.3f}",
    )
    table.add_row(
        "",
        "Output Tokens",
        f"{usage.output_tokens:,}",  # pyright: ignore[reportUnknownMemberType, reportAttributeAccessIssue]
        f"${model_pricing['output']:.3f}",
    )
    table.add_section()
    table.add_row(
        "",
        "[bold]Total Tokens[/bold]",
        f"{usage.input_tokens + usage.output_tokens:,}",  # pyright: ignore[reportUnknownMemberType, reportAttributeAccessIssue]
        "",
    )
    table.add_row("", "[bold red]TOTAL COST (USD)[/bold red]", f"${cost:.4f}", "")
    console.print(table)
