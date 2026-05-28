#!/usr/bin/env python3
"""
AWS CDK App for Algo Backend Infrastructure
"""

import os
from aws_cdk import App, Environment
from stacks.algo_backend_stack import AlgoBackendStack

app = App()

# Get environment from context or default to 'dev'
env_name = app.node.try_get_context("env") or os.environ.get("ENVIRONMENT", "dev")

# Define AWS environment
aws_env = Environment(
    account=os.environ.get("CDK_DEFAULT_ACCOUNT"),
    region=os.environ.get("CDK_DEFAULT_REGION", "ap-south-1"),
)

# Create the stack
AlgoBackendStack(
    app,
    f"AlgoBackendStack-{env_name}",
    env_name=env_name,
    env=aws_env,
    description=f"Algo Builder, Backtesting, Screening & Alert Services ({env_name})",
)

app.synth()
