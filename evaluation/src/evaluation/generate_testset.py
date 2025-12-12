import random
from pathlib import Path
from typing import Annotated

import typer
from langchain_aws import BedrockEmbeddings, ChatBedrockConverse
from langchain_community.document_loaders import PyPDFDirectoryLoader
from langchain_core.messages import HumanMessage
from langchain_core.outputs import ChatGeneration, ChatResult, LLMResult
from langchain_core.prompt_values import PromptValue, StringPromptValue
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
from rich.console import Console
from rich.table import Table

RUN_CONFIG = RunConfig(max_workers=4)
KB_DOCS = Path("documents")
MODEL_PRICING_PER_1K = {
    "us.anthropic.claude-sonnet-4-5-20250929-v1:0": {
        "input": 0.003,
        "output": 0.015,
    }
}

app = typer.Typer()

console = Console()
console_err = Console(stderr=True)


def adapt_kg_for_persona_generation(
    kg: KnowledgeGraph,
    *,
    llm: BaseRagasLLM,
    embedding_model: BaseRagasEmbeddings,
    sample_size: int = 20,
    min_content_length: int = 5,
) -> None:
    """
    Augments a random subset of nodes in the provided KnowledgeGraph (kg)
    in-place with 'summary' and 'summary_embedding' properties required by ragas.

    Args:
        kg: KnowledgeGraph object to modify.
        llm_wrapper: LLM wrapper for summarization.
        embedding_model: Model for generating embeddings.
        sample_size: Number of nodes to sample and augment.
        min_content_length: Minimum page_content length for a node to be considered.
    """
    console.print("Adapting knowledge graph for persona generation")
    candidate_nodes = [
        node
        for node in kg.nodes
        if len(node.properties["page_content"]) >= min_content_length  # pyright: ignore[reportUnknownMemberType]
    ]

    effective_sample_size = min(sample_size, len(candidate_nodes))
    if effective_sample_size == 0:
        console_err.print(
            "No nodes meet the minimum content length for persona generation"
        )
        _ = typer.Exit(code=1)

    sampled_nodes = random.sample(candidate_nodes, effective_sample_size)

    for i, node in enumerate(sampled_nodes):
        console.print(f"[{i + 1}/{effective_sample_size}] Adapting Node ID: {node.id}")

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
        node.properties["summary"] = result.generations[0][0].text
        node.properties["summary_embedding"] = embedding_model.embed_query(
            node.properties["summary"]
        )


def get_token_usage_for_bedrock(
    llm_result: LLMResult | ChatResult,
) -> TokenUsage:
    token_usages = [
        TokenUsage(
            input_tokens=g.message.usage_metadata["input_tokens"],
            output_tokens=g.message.usage_metadata["output_tokens"],
            model=g.message.response_metadata["model_name"],
        )
        for gs in llm_result.generations
        for g in gs
        if isinstance(g, ChatGeneration)
    ]
    model = next((usage.model for usage in token_usages if usage.model), "")
    return sum(token_usages, TokenUsage(input_tokens=0, output_tokens=0, model=model))


@app.command()
def generate_testset(
    model: Annotated[
        str, typer.Argument(help="Bedrock model to use for the testset generation")
    ] = "us.anthropic.claude-sonnet-4-5-20250929-v1:0",
) -> None:
    """Generate a synthetic testset with RAGAS based on the evaluation knowledge base"""
    if not KB_DOCS.exists() or not next(KB_DOCS.iterdir()):
        console_err.print(
            "Evaluation knowledge base documents not found, run the `create-kb` command first"
        )
        raise typer.Exit(code=1)

    generator_llm = LangchainLLMWrapper(ChatBedrockConverse(model=model))  # pyright: ignore[reportAny]
    generator_embeddings = LangchainEmbeddingsWrapper(  # pyright: ignore[reportAny]
        BedrockEmbeddings(model_id="amazon.titan-embed-text-v2:0")
    )

    console.print("Creating knowledge graph from documents")
    loader = PyPDFDirectoryLoader("documents")
    kg = KnowledgeGraph(
        [
            Node(
                properties={"page_content": doc.page_content, "metadata": doc.metadata}  # pyright: ignore[reportUnknownMemberType]
            )
            for doc in loader.lazy_load()
        ]
    )

    console.print("Applying transforms to knowledge graph")
    transforms = [
        HeadlinesExtractor(llm=generator_llm),  # pyright: ignore[reportAny]
        HeadlineSplitter(),
        KeyphrasesExtractor(llm=generator_llm),  # pyright: ignore[reportAny]
    ]
    apply_transforms(kg, transforms, run_config=RUN_CONFIG)  # pyright: ignore[reportArgumentType]

    adapt_kg_for_persona_generation(
        kg, llm=generator_llm, embedding_model=generator_embeddings
    )
    personas = generate_personas_from_kg(kg, generator_llm)  # pyright: ignore[reportAny]
    console.print("Generated personas:")
    console.print(personas)

    console.print("Generating synthetic testset")
    generator = TestsetGenerator(
        llm=generator_llm,  # pyright: ignore[reportAny]
        embedding_model=generator_embeddings,  # pyright: ignore[reportAny]
        knowledge_graph=kg,
        persona_list=personas,
    )
    query_distibution = [
        (
            SingleHopSpecificQuerySynthesizer(
                llm=generator_llm,
                property_name="headlines",  # pyright: ignore[reportAny]
            ),
            0.5,
        ),
        (
            SingleHopSpecificQuerySynthesizer(
                llm=generator_llm,
                property_name="keyphrases",  # pyright: ignore[reportAny]
            ),
            0.5,
        ),
    ]
    testset = generator.generate(  # pyright: ignore[reportUnknownMemberType]
        1,
        query_distribution=query_distibution,  # pyright: ignore[reportArgumentType]
        run_config=RUN_CONFIG,
        token_usage_parser=get_token_usage_for_bedrock,
    )

    testset_csv = Path("datasets/synthetic-testset.csv")
    console.print(f"Saving testset to '{testset_csv}'")
    testset.to_evaluation_dataset().to_csv(testset_csv)  # pyright: ignore[reportAttributeAccessIssue, reportUnusedCallResult, reportUnknownMemberType]

    console.print("Computing usage metrics")
    model_pricing = MODEL_PRICING_PER_1K[model]
    usage = testset.total_tokens()
    cost = testset.total_cost(  # pyright: ignore[reportUnknownMemberType, reportAttributeAccessIssue, reportUnknownVariableType]
        model_pricing["input"] / 1e3, model_pricing["output"] / 1e3
    )

    table = Table(
        "Model",
        "Metric",
        "Value",
        "Price / 1K",
    )
    table.add_row(
        usage.model,
        "Input Tokens",
        f"{usage.input_tokens:,}",
        f"${model_pricing['input']:.3f}",
    )
    table.add_row(
        "",
        "Output Tokens",
        f"{usage.output_tokens:,}",
        f"${model_pricing['output']:.3f}",
    )
    table.add_section()
    table.add_row(
        "",
        "[bold]Total Tokens[/bold]",
        f"{usage.input_tokens + usage.output_tokens:,}",
        "",
    )
    table.add_row(
        "",
        "[bold red]TOTAL COST (USD)[/bold red]",
        f"${cost:.4f}",
        "",
    )
    console.print(table)
