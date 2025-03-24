#!/usr/bin/env python3
import os

import aws_cdk as cdk

from stacks.personalize.personalize_data_import_stack import PersonalizeDataImportStack
from stacks.bedrock_agents.recommend.recommend_agent import RecommendAgentStack
from stacks.personalize.personalize_training_stack import PersonalizeTrainingStack
from stacks.opensearch.opensearch_stack import OpenSearchServerlessStack
from stacks.dynamodb.dynamodb_stack import DynamoDBUserTableStack
from stacks.bedrock_agents.search.search_agent import SearchAgentStack
from stacks.bedrock_agents.customers.customers_agent import CustomerAgentStack

app = cdk.App()

# Personalize data import and init training
personalize_dataset_group = PersonalizeDataImportStack(app, "PersonalizeDataImportStack")
PersonalizeTrainingStack(app, "PersonalizeTrainingStack3", personalize_dataset_group.dataset_group_arn)

# Dataset load to OpenSearch and DynamoDB
opensearch = OpenSearchServerlessStack(app, "OpenSearchServerlessStack")
dynamodb = DynamoDBUserTableStack(app, "DynamoDbStack")

# Bedrock Agents
customer_agent = CustomerAgentStack(app, "CustomerAgentStack", dynamodb.orders_table_name, dynamodb.usrs_table_name)
recommend_agent = RecommendAgentStack(app, "RecommendAgentStack")
search_agent = SearchAgentStack(app, "SearchAgentStack", opensearch.opensearch_endpoint)

app.synth()
