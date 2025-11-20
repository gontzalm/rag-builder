import os

import chainlit.data as cl_data
from chainlit.data.dynamodb import DynamoDBDataLayer
from chainlit.data.storage_clients.s3 import S3StorageClient


def setup_data_persistence() -> None:
    """Sets up data persistence in order to store threads (conversations)."""
    cl_data._data_layer = DynamoDBDataLayer(  # pyright: ignore[reportPrivateUsage]
        table_name=os.environ["CHAINLIT_TABLE"],
        storage_provider=S3StorageClient(bucket=os.environ["CHAINLIT_BUCKET"]),
    )
