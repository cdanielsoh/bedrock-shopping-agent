#!/usr/bin/env python3
import os

import aws_cdk as cdk

from stacks.opensearch.opensearch_stack import OpenSearchServerlessStack
from stacks.dynamodb.dynamodb_stack import DynamoDBUserTableStack
from stacks.webfrontend.webfrontend_stack import WebFrontendStack

app = cdk.App()

# Dataset load to OpenSearch and DynamoDB
opensearch = OpenSearchServerlessStack(app, "OpenSearchServerlessStack")
dynamodb = DynamoDBUserTableStack(app, "DynamoDbStack")

# Web frontend with WebSocket and HTTP API (merged stack)
webfrontend = WebFrontendStack(
    app, 
    "WebFrontendStack",
    opensearch_endpoint=opensearch.opensearch_endpoint,
    orders_table_name=dynamodb.orders_table_name,
    reviews_table_name=dynamodb.reviews_table_name,
    users_table_name=dynamodb.user_table_name
)
webfrontend.add_dependency(opensearch)
webfrontend.add_dependency(dynamodb)

app.synth()
