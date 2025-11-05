import logging
import os
from functools import cached_property
from typing import final

import lancedb  # pyright: ignore[reportMissingTypeStubs]

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


@final
class LanceDbOptimizer:
    _VECTOR_STORE_BUCKET: str = os.environ["VECTOR_STORE_BUCKET"]

    @cached_property
    def _vector_store(self) -> lancedb.DBConnection:
        logger.info("Connecting to LanceDB vector store")
        return lancedb.connect(uri=f"s3://{self._VECTOR_STORE_BUCKET}")

    def optimize(self) -> None:
        logger.info("Optimizing LanceDB vector store")
        logger.info("Available tables: '%s'", self._vector_store.table_names())
        self._vector_store.open_table("vectorstore").optimize()
