import os

import aws_cdk as cdk

from rag_builder.stack import RagBuilderStack

app = cdk.App()

_ = RagBuilderStack(
    app,
    "rag-builder-stack",
    env=cdk.Environment(
        account=os.environ["CDK_DEFAULT_ACCOUNT"],
        region=os.environ["CDK_DEFAULT_REGION"],
    ),
)
_ = app.synth()
