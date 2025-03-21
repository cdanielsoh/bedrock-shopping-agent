#!/usr/bin/env python3
import os

import aws_cdk as cdk

from stacks.bedrock_agents.recommend.recommend_agent import RecommendAgentStack
from stacks.personalize.personalize_stack import PersonalizeDataImportStack
from stacks.personalize.personalize_training_stack import PersonalizeTrainingStack
from stacks.opensearch.opensearch_stack import OpenSearchServerlessStack
from stacks.dynamodb.dynamodb_stack import DynamoDBUserTableStack
from stacks.bedrock_agents.search.search_agent import SearchAgentStack

app = cdk.App()
# PersonalizeDataImportStack(app, "PersonalizeDataImportStack")

# TODO: get the dataset_group_arn from PersonalizeDataImportStack later
# PersonalizeTrainingStack(app, "PersonalizeTrainingStack3", "arn:aws:personalize:ap-northeast-2:851725462015:dataset-group/personalize-dataset-group-3d4fb71d")
# opensearch_stack = OpenSearchServerlessStack(app, "OpenSearchServerlessStack")
# DynamoDBUserTableStack(app, "DynamoDbStack")

# TODO: get the ARNs from PersonalizeTrainingStack later
personalize_recommenders = {
    "USER_PERSONALIZATION_ARN": "arn:aws:personalize:ap-northeast-2:851725462015:campaign/user-personalization",
    "PERSONALIZED_RANKING_ARN": "arn:aws:personalize:ap-northeast-2:851725462015:campaign/personalized-ranking",
    "BEST_SELLERS_ARN": "arn:aws:personalize:ap-northeast-2:851725462015:recommender/best-sellers-recommender",
    "MOST_VIEWED_ARN": "arn:aws:personalize:ap-northeast-2:851725462015:recommender/most-viewed-recommender"
}
RecommendAgentStack(app, "RecommendAgentStack", personalize_recommenders)

# TODO: get the endpoint from the opensearch stack later
# SearchAgentStack(app, "SearchAgentStack", "97g72c3e0b53f97m9hra.ap-northeast-2.aoss.amazonaws.com")

app.synth()
