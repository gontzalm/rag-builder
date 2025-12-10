import logging
import os
from functools import cached_property
from typing import final

import lancedb  # pyright: ignore[reportMissingTypeStubs]

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


@final
class LanceDbDeleter:
    _VECTOR_STORE_BUCKET: str = os.environ["VECTOR_STORE_BUCKET"]

    def __init__(self, document_id: str) -> None:
        self.document_id = document_id

    @cached_property
    def _vector_store(self) -> lancedb.DBConnection:
        logger.info("Connecting to LanceDB vector store")
        return lancedb.connect(uri=f"s3://{self._VECTOR_STORE_BUCKET}")

    def delete_document(self) -> None:
        logger.info("Deleting document ID '%s'", self.document_id)
        _ = self._vector_store.open_table("vectorstore").delete(
            f"id like '{self.document_id}%'"
        )
        logger.info("Sucessfully deleted document ID '%s'", self.document_id)
