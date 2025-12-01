import logging
import os
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from functools import cached_property
from pathlib import Path
from typing import Self, override

from httpx import Client
from lancedb import DBConnection
from langchain_aws import BedrockEmbeddings
from langchain_community.document_loaders import PyPDFLoader
from langchain_community.vectorstores import LanceDB
from langchain_core.document_loaders import BaseLoader
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from auth import AwsBotoAuth

logger = logging.getLogger()


class LanceDbLoader(ABC):
    _VECTOR_STORE_BUCKET: str = os.environ["VECTOR_STORE_BUCKET"]
    _EMBEDDINGS_MODEL: str = os.environ["EMBEDDINGS_MODEL"]
    _BACKEND_API_URL: str = os.environ["BACKEND_API_URL"]
    _DEFAULT_TABLE: str = "vectorstore"
    _DEFAULT_TEXT_COLUMN: str = "text"

    def __init__(self, load_id: str, url: str) -> None:
        self._http: Client = Client(base_url=self._BACKEND_API_URL, auth=AwsBotoAuth())
        self.load_id: str = load_id
        self.url: str = url

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_) -> None:
        self._http.close()

    @cached_property
    def _vector_store(self) -> LanceDB:
        logger.info("Connecting to LanceDB vector store")
        return LanceDB(
            uri=f"s3://{self._VECTOR_STORE_BUCKET}",
            embedding=BedrockEmbeddings(model_id=self._EMBEDDINGS_MODEL),
        )

    @cached_property
    def _db(self) -> DBConnection:
        return self._vector_store._connection  # pyright: ignore[reportReturnType, reportPrivateUsage]

    @cached_property
    @abstractmethod
    def _loader(self) -> BaseLoader:
        raise NotImplementedError

    @cached_property
    def _doc_title(self) -> str:
        try:
            title = self._documents[0].metadata["title"]  # pyright: ignore[reportUnknownVariableType, reportUnknownMemberType]
        except KeyError:
            title = "Unknown"

        return title  # pyright: ignore[reportUnknownVariableType]

    @cached_property
    def _extra_metadata(self) -> dict[str, str]:
        return {"url": self.url}

    def _load_and_split_documents(self) -> None:
        logger.info("Recursively splitting documents")
        self._documents: list[Document] = (
            RecursiveCharacterTextSplitter().split_documents(self._loader.lazy_load())
        )

    def _add_extra_metadata(self) -> None:
        for doc in self._documents:
            doc.metadata.update(self._extra_metadata)  # pyright: ignore[reportUnknownMemberType]

    def _create_fts_index_if_not_exists(self) -> None:
        table = self._db.open_table(self._DEFAULT_TABLE)

        if table.index_stats(f"{self._DEFAULT_TEXT_COLUMN}_idx") is None:
            table.create_fts_index(self._DEFAULT_TEXT_COLUMN)
            table.wait_for_index([f"{self._DEFAULT_TEXT_COLUMN}_idx"])

    def _mark_in_progress(self) -> None:
        _ = self._http.patch(
            f"/documents/load/{self.load_id}",
            json={"status": "in_progress", "started_at": str(datetime.now(tz=UTC))},
        )

    def _mark_completed(self) -> None:
        _ = self._http.patch(
            f"/documents/load/{self.load_id}",
            json={"status": "completed", "completed_at": str(datetime.now(tz=UTC))},
        )

    def _mark_failed(self, e: Exception) -> None:
        _ = self._http.patch(
            f"/documents/load/{self.load_id}",
            json={"status": "failed", "error_details": repr(e)},
        )

    def _add_document(self) -> None:
        _ = self._http.post(
            "/documents",
            json={
                "document_id": self.load_id,
                "title": self._doc_title,
                "url": self.url,
            },
        )

    def load_document(self) -> None:
        logger.info("Starting document load ID '%s'", self.load_id)
        self._mark_in_progress()
        try:
            self._load_and_split_documents()
            self._add_extra_metadata()
            _ = self._vector_store.add_documents(
                self._documents,
                ids=[f"{self.load_id}-{i:04d}" for i in range(len(self._documents))],
            )
            self._create_fts_index_if_not_exists()
        except Exception as e:
            self._mark_failed(e)
            logger.exception("Document load ID '%s' failed", self.load_id)
        else:
            self._mark_completed()
            self._add_document()
            logger.info("Sucessfully completed document load ID '%s'", self.load_id)


class PdfLoader(LanceDbLoader):
    @cached_property
    @override
    def _loader(self) -> PyPDFLoader:
        logger.info("Downloading PDF document from url '%s'", self.url)
        r = self._http.get(self.url)
        _ = r.raise_for_status()
        document = Path("/tmp/document.pdf")
        _ = document.write_bytes(r.content)
        logger.info("Creating PyPDFLoader from document '%s'", document)
        return PyPDFLoader(document)
