import os

import aws_cdk as cdk

from bobbeori_stack import BobbeoriStack


app = cdk.App()
environment_name = app.node.try_get_context("environment") or "dev"
BobbeoriStack(
    app,
    f"Bobbeori-{environment_name}",
    env=cdk.Environment(
        account=os.getenv("CDK_DEFAULT_ACCOUNT"),
        region=os.getenv("CDK_DEFAULT_REGION", "ap-northeast-2"),
    ),
)
app.synth()
