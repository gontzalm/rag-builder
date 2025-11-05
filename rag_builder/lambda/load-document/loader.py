import logging
import os
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from functools import cached_property
from pathlib import Path
from typing import Self, override

from httpx import Client
from langchain_aws import BedrockEmbeddings
from langchain_community.document_loaders import PyPDFLoader
from langchain_community.vectorstores import LanceDB
from langchain_core.document_loaders import BaseLoader
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

logger = logging.getLogger(__name__)


class LanceDbLoader(ABC):
    _VECTOR_STORE_BUCKET: str = os.environ["VECTOR_STORE_BUCKET"]
    _EMBEDDINGS_MODEL: str = os.environ["EMBEDDINGS_MODEL"]
    _BACKEND_API_URL: str = os.environ["BACKEND_API_URL"]

    def __init__(self, load_id: str, url: str) -> None:
        self._http: Client = Client(base_url=self._BACKEND_API_URL)
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
    @abstractmethod
    def _loader(self) -> BaseLoader:
        raise NotImplementedError

    def _split_documents(self) -> list[Document]:
        logger.info("Recursively splitting documents")
        return RecursiveCharacterTextSplitter().split_documents(
            self._loader.lazy_load()
        )

    def _mark_in_progress(self) -> None:
        _ = self._http.patch(
            f"/document/load/{self.load_id}",
            json={"status": "in_progress", "started_at": str(datetime.now(tz=UTC))},
        )

    def _mark_completed(self) -> None:
        _ = self._http.patch(
            f"/document/load/{self.load_id}",
            json={"status": "completed", "completed_at": str(datetime.now(tz=UTC))},
        )

    def _mark_failed(self, e: Exception) -> None:
        _ = self._http.patch(
            f"/document/load/{self.load_id}",
            json={"status": "failed", "error_details": repr(e)},
        )

    def _add_document(self) -> None:
        _ = self._http.post("/document", json={"title": "test", "url": self.url})

    def load_document(self) -> None:
        logger.info("Starting document load ID '%s'", self.load_id)
        self._mark_in_progress()
        try:
            documents = self._split_documents()
            _ = self._vector_store.add_documents(
                documents,
                ids=[f"{self.load_id}-{i:04d}" for i in range(len(documents))],
            )
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
