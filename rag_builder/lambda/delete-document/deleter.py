import logging
import os
from functools import cached_property
from typing import final

from langchain_community.vectorstores import LanceDB

logger = logging.getLogger(__name__)


@final
class LanceDbDeleter:
    _EMBEDDINGS_BUCKET: str = os.environ["EMBEDDINGS_BUCKET"]

    def __init__(self, ingestion_id: str) -> None:
        self.ingestion_id = ingestion_id

    @cached_property
    def _vector_store(self) -> LanceDB:
        logger.info("Connecting to LanceDB vector store")
        return LanceDB(uri=f"s3://{self._EMBEDDINGS_BUCKET}")

    def delete_document(self) -> None:
        logger.info("Deleting document associated with ingestion ID '%s'")
        self._vector_store.delete(filter=f"id like '{self.ingestion_id}%'")
