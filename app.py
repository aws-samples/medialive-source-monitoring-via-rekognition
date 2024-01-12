# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import os
from aws_cdk import App, Environment, Aspects

from StackBuild.source_monitor_stack import EmlRekognitionStack
import cdk_nag

app = App()

EmlRekognitionStack(
    app,
    "MediaLiveRekognitionThumbnails",
    env=Environment(
        region=os.environ.get("CDK_DEPLOY_REGION"),
        account=os.environ.get("CDK_DEPLOY_ACCOUNT")
    ),
)

Aspects.of(app).add(cdk_nag.AwsSolutionsChecks())

app.synth()
