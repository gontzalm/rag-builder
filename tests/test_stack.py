import aws_cdk as cdk
from syrupy.assertion import SnapshotAssertion

from rag_builder.stack import RagBuilderStack


class TestStack:
    def test_stack(self, snapshot_json: SnapshotAssertion) -> None:
        app = cdk.App()
        stack = RagBuilderStack(
            app,
            "rag-builder-stack",
            env=cdk.Environment(
                account="123456789012",  # Use a dummy account for testing
                region="us-east-1",
            ),
        )
        template = cdk.assertions.Template.from_stack(stack)
        assert template.to_json() == snapshot_json
