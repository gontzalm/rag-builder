from unittest.mock import MagicMock

from function import handler  # pyright: ignore[reportUnknownVariableType]


class TestOptimizeVectorStore:
    def test_optimize(self, lancedb: MagicMock) -> None:
        handler({}, {})

        lancedb.open_table.assert_called_once_with("vectorstore")  # pyright: ignore[reportAny]
        lancedb.open_table.return_value.optimize.assert_called_once()  # pyright: ignore[reportAny]
