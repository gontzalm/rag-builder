import pytest
from pytest_mock import MockerFixture
from syrupy.assertion import SnapshotAssertion
from syrupy.extensions.json import JSONSnapshotExtension
from syrupy.filters import props


# Mock secrets.token_hex to return a consistent value for snapshot testing
@pytest.fixture(autouse=True)
def mock_secrets_token_hex(mocker: MockerFixture) -> None:
    _ = mocker.patch("secrets.token_hex", return_value="MOCKED_TOKEN_HEX_VALUE")


@pytest.fixture
def snapshot_json(snapshot: SnapshotAssertion) -> SnapshotAssertion:
    print(type(snapshot))
    # Exclude dynamic properties that change with every asset build or deployment
    # S3Key: Changes when Zip-based Lambda source code changes
    # ImageUri: Changes when Docker-based Lambda source code changes
    # Image: Changes when ECS container source code changes
    return snapshot.with_defaults(
        extension_class=JSONSnapshotExtension,
        exclude=props("S3Key", "ImageUri", "Image"),
    )
