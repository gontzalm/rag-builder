import os
import uuid
from pathlib import Path
from typing import Annotated

import typer
from rich.table import Table

from .console import get_console

EVALUATION_KB_DOCS = [
    "https://arxiv.org/pdf/2502.20754",
    "https://arxiv.org/pdf/2501.12599",
    "https://arxiv.org/pdf/2407.21783",
    "https://arxiv.org/pdf/2405.18346",
    "https://arxiv.org/pdf/2403.04132",
]

app = typer.Typer()
console = get_console()


def clean_docs() -> None:
    console.print("🧹 Cleaning 'documents' directory", style="info")
    docs = Path("documents")
    docs.mkdir(exist_ok=True)
    for doc in docs.iterdir():
        doc.unlink()


@app.command()
def create_kb(
    embedding_model: Annotated[
        str,
        typer.Argument(help="Bedrock embedding model to use for the knowledge base"),
    ] = "amazon.titan-embed-text-v2:0",
) -> None:
    """Create a knowledge base for evaluation as a LanceDB table named `evaluation_{embedding_model}`"""
    clean_docs()

    os.environ["EMBEDDINGS_MODEL"] = embedding_model

    from load_document.loader import (  # pyright: ignore[reportMissingTypeStubs]
        PdfLoader,
    )

    target_table = f"evaluation_{embedding_model.replace(':', '-')}"
    console.print(
        f"📚 Creating knowledge base as LanceDB table '{target_table}'", style="info"
    )

    table = Table(title="Documents Loaded", style="table", header_style="table.header")
    table.add_column("Document", style="data")
    table.add_column("URL", style="info")

    for url in EVALUATION_KB_DOCS:
        console.print(f"📄 Loading document '{url}'", style="info")
        with PdfLoader("", url) as loader:
            loader._TARGET_TABLE = target_table  # pyright: ignore[reportPrivateUsage]
            loader._DOCUMENT = Path("documents") / f"{uuid.uuid4()}.pdf"  # pyright: ignore[reportPrivateUsage]
            table.add_row(str(loader._DOCUMENT), url)  # pyright: ignore[reportPrivateUsage]
            loader._load_and_split_documents()  # pyright: ignore[reportPrivateUsage]
            loader._compute_metadata()  # pyright: ignore[reportPrivateUsage]
            _ = loader._vector_store.add_documents(loader._documents)  # pyright: ignore[reportPrivateUsage]
            loader._create_fts_index_if_not_exists()  # pyright: ignore[reportPrivateUsage]

    console.print("✅ Successfully created knowledge base", style="success")
    console.print(table)
