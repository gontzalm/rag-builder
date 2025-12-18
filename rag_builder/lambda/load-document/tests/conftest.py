from unittest.mock import MagicMock

import pytest
from pytest_mock import MockerFixture, MockType


@pytest.fixture
def lancedb(mocker: MockerFixture) -> MagicMock:
    """Mocks LanceDB vector store."""
    mock = mocker.patch("load_document.loader.LanceDB")
    mock_instance = mock.return_value  # pyright: ignore[reportAny]
    mock_instance.add_documents.return_value = None  # pyright: ignore[reportAny]

    # Mock the connection and table structure
    # Simulate: self._connection.open_table() -> table_mock
    mock_table = mocker.MagicMock()
    mock_table.index_stats.return_value = (  # pyright: ignore[reportAny]
        None  # Index does not exist initially
    )
    mock_instance._connection.open_table.return_value = mock_table  # pyright: ignore[reportAny]

    return mock_instance  # pyright: ignore[reportAny]


@pytest.fixture
def lancedb_table(lancedb: MagicMock) -> MagicMock:
    """Returns mocked LanceDB table for assertions."""
    return lancedb._connection.open_table.return_value  # pyright: ignore[reportAny]


@pytest.fixture
def bedrock_embeddings(mocker: MockerFixture) -> MagicMock:
    return mocker.patch("load_document.loader.BedrockEmbeddings").return_value  # pyright: ignore[reportAny]


@pytest.fixture
def pypdf_loader(mocker: MockerFixture) -> MagicMock:
    mock = mocker.patch("load_document.loader.PyPDFLoader")
    mock_instance = mock.return_value  # pyright: ignore[reportAny]

    # Setup default document return for the mock instance's lazy_load method
    mock_document = mocker.MagicMock()
    mock_document.page_content = "This is some test document content."
    mock_document.metadata = {}
    mock_instance.lazy_load.return_value = [mock_document]  # pyright: ignore[reportAny]

    return mock_instance  # pyright: ignore[reportAny]


@pytest.fixture
def path_write_bytes(mocker: MockerFixture) -> MagicMock:
    """Mocks pathlib.Path.write_bytes to avoid writing files."""
    return mocker.patch("pathlib.Path.write_bytes")


@pytest.fixture
def aws_auth(mocker: MockerFixture) -> MockType:
    """Mocks AwsBotoAuth to avoid credential resolution during Client init."""
    mock = mocker.patch("load_document.loader.AwsBotoAuth")
    # The instance returned by AwsBotoAuth() needs to be callable
    # and return the request passed to it, satisfying httpx auth protocol.
    mock.return_value.side_effect = lambda request: request  # pyright: ignore[reportAny, reportUnknownLambdaType]
    return mock
