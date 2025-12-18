from unittest.mock import MagicMock

import pytest
from pytest_mock import MockerFixture


@pytest.fixture
def lancedb(mocker: MockerFixture) -> MagicMock:
    """Mocks lancedb.connect and its subsequent calls."""
    # Mock lancedb.connect
    mock = mocker.patch("optimize_vector_store.optimizer.lancedb.connect")
    mock_db = mock.return_value  # pyright: ignore[reportAny]

    # Mock open_table and its optimize method
    mock_table = mocker.MagicMock()
    mock_table.optimize.return_value = (  # pyright: ignore[reportAny]
        None  # optimize() doesn't return anything specific
    )
    mock_db.open_table.return_value = mock_table  # pyright: ignore[reportAny]

    return mock_db  # pyright: ignore[reportAny]
