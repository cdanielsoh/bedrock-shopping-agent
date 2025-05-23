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
from stacks.bedrock_agents.shopping.shopping_agent import SupervisorAgentStack

app = cdk.App()

# Personalize data import and init training
personalize_dataset_group = PersonalizeDataImportStack(app, "PersonalizeDataImportStack")
personalize_training = PersonalizeTrainingStack(app, "PersonalizeTrainingStack", personalize_dataset_group.dataset_group_arn)
personalize_training.add_dependency(personalize_dataset_group)

# Dataset load to OpenSearch and DynamoDB
opensearch = OpenSearchServerlessStack(app, "OpenSearchServerlessStack")
dynamodb = DynamoDBUserTableStack(app, "DynamoDbStack")

# Bedrock Agents
customer_agent = CustomerAgentStack(app, "CustomerAgentStack", dynamodb.orders_table_name, dynamodb.user_table_name)
customer_agent.add_dependency(dynamodb)
recommend_agent = RecommendAgentStack(app, "RecommendAgentStack")
search_agent = SearchAgentStack(app, "SearchAgentStack", opensearch.opensearch_endpoint)
search_agent.add_dependency(opensearch)
supervisor_agent = SupervisorAgentStack(app, "ShoppingAgentStack", customer_agent, recommend_agent, search_agent)

app.synth()
