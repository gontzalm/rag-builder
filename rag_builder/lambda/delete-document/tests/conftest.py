from unittest.mock import MagicMock

import pytest
from pytest_mock import MockerFixture


@pytest.fixture
def lancedb(mocker: MockerFixture) -> MagicMock:
    """Mocks lancedb.connect and its subsequent calls."""
    # Mock lancedb.connect
    mock = mocker.patch("delete_document.deleter.lancedb.connect")
    mock_db = mock.return_value  # pyright: ignore[reportAny]

    # Mock the Table object and its delete method
    mock_table = MagicMock()
    mock_table.delete.return_value = None  # pyright: ignore[reportAny]
    mock_db.open_table.return_value = mock_table  # pyright: ignore[reportAny]

    return mock_db  # pyright: ignore[reportAny]
