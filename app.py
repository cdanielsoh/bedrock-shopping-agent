#!/usr/bin/env python3
import os

import aws_cdk as cdk
from stacks.personalize.personalize_stack import PersonalizeDataImportStack
from stacks.opensearch.opensearch_stack import OpenSearchServerlessStack
from stacks.dynamodb.dynamodb_stack import DynamoDBUserTableStack
from stacks.bedrock_agents.search.search_agent import SearchAgentStack

app = cdk.App()
# PersonalizeDataImportStack(app, "PersonalizeDataImportStack")
# opensearch_stack = OpenSearchServerlessStack(app, "OpenSearchServerlessStack")
# DynamoDBUserTableStack(app, "DynamoDbStack")

# TODO: get the endpoint from the opensearch stack later
SearchAgentStack(app, "SearchAgentStack", "97g72c3e0b53f97m9hra.ap-northeast-2.aoss.amazonaws.com")

app.synth()
