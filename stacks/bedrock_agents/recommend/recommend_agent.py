from aws_cdk import (
    Stack,
    aws_iam as iam,
    aws_bedrock as bedrock,
    aws_lambda as lambda_
)
from constructs import Construct
import json

class RecommendAgentStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Names are fixed in personalize_training_stack
        personalize_recommenders = {
            "USER_PERSONALIZATION_ARN": f"arn:aws:personalize:{self.region}:{self.account}:campaign/user-personalization",
            "PERSONALIZED_RANKING_ARN": f"arn:aws:personalize:{self.region}:{self.account}:campaign/personalized-ranking",
            "BEST_SELLERS_ARN": f"arn:aws:personalize:{self.region}:{self.account}:recommender/best-sellers-recommender",
            "MOST_VIEWED_ARN": f"arn:aws:personalize:{self.region}:{self.account}:recommender/most-viewed-recommender"
        }

        # Create IAM role for Bedrock Agent
        agent_role = iam.Role(
            self, "BedrockAgentRole",
            assumed_by=iam.ServicePrincipal("bedrock.amazonaws.com"),
            role_name = 'AmazonBedrockExecutionRoleForAgents_RecommendAgentStack',
            inline_policies = {
                'BedrockAndLambdaAccess': iam.PolicyDocument(
                    statements=[
                        iam.PolicyStatement(
                            effect=iam.Effect.ALLOW,
                            actions=['bedrock:*'],
                            resources=['*']
                        ),
                        iam.PolicyStatement(
                            effect=iam.Effect.ALLOW,
                            actions=['lambda:InvokeFunction'],
                            resources=[f'arn:aws:lambda:{self.region}:{self.account}:function:*']
                        )
                    ]
                )
            }
        )

        # Grant permissions to access Personalize
        agent_role.add_to_policy(iam.PolicyStatement(
            actions=[
                "personalize:*"
            ],
            resources=["*"]  # You can restrict this to specific collections if needed
        ))

        lambda_role = iam.Role(
            self, "ActionGroupLambdaRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com")
        )

        lambda_role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSLambdaBasicExecutionRole")
        )

        lambda_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "personalize:*",
                ],
                resources=["*"]
            )
        )

        recommend_function = lambda_.Function(
            self, "PersonalizeAccessFunction",
            runtime=lambda_.Runtime.PYTHON_3_9,
            handler="index.handler",
            code=lambda_.Code.from_inline(self._get_lambda_code()),
            environment=personalize_recommenders,
            role=lambda_role
        )

        recommend_function.add_permission(
            "AllowBedrockInvokation",
            principal=iam.ServicePrincipal("bedrock.amazonaws.com"),
            action="lambda:InvokeFunction"
        )

        # Create Bedrock Agent
        agent = bedrock.CfnAgent(
            self, "RecommendAgent",
            agent_name="RecommendAgent",
            agent_resource_role_arn=agent_role.role_arn,
            instruction="You are an agent that can retrieve recommendations from Amazon Personalize.",
            foundation_model="anthropic.claude-3-haiku-20240307-v1:0",
            action_groups=[
                bedrock.CfnAgent.AgentActionGroupProperty(
                    action_group_name="GetRecommendations",
                    action_group_executor=bedrock.CfnAgent.ActionGroupExecutorProperty(
                        lambda_=recommend_function.function_arn
                    ),
                    function_schema=bedrock.CfnAgent.FunctionSchemaProperty(
                        functions=[
                            bedrock.CfnAgent.FunctionProperty(
                                name="get_user_personalized_recommendations",
                                parameters={
                                    "user_id": bedrock.CfnAgent.ParameterDetailProperty(
                                        type="string",
                                        required=True
                                    )
                                }
                            ),
                            bedrock.CfnAgent.FunctionProperty(
                                name="rerank_items_for_user",
                                parameters={
                                    "user_id": bedrock.CfnAgent.ParameterDetailProperty(
                                        type="string",
                                        required=True
                                    ),
                                    "item_list": bedrock.CfnAgent.ParameterDetailProperty(
                                        type="string",
                                        required=True
                                    )
                                }
                            ),
                            bedrock.CfnAgent.FunctionProperty(
                                name="get_best_sellers",
                                parameters={
                                    "user_id": bedrock.CfnAgent.ParameterDetailProperty(
                                        type="string",
                                        required=True
                                    )
                                }
                            ),
                            bedrock.CfnAgent.FunctionProperty(
                                name="get_most_viewed",
                                parameters={
                                    "user_id": bedrock.CfnAgent.ParameterDetailProperty(
                                        type="string",
                                        required=True
                                    )
                                }
                            ),
                        ]
                    ),
                    action_group_state="ENABLED",
                )
            ]
        )

# TODO: Move lambda function to a separate file
    def _get_lambda_code(self):
        return """
import json
import os
import boto3

personalizeRt = boto3.client('personalize-runtime')

USER_PERSONALIZATION_ARN = os.environ["USER_PERSONALIZATION_ARN"]
PERSONALIZED_RANKING_ARN = os.environ["PERSONALIZED_RANKING_ARN"]
BEST_SELLERS_ARN = os.environ["BEST_SELLERS_ARN"]
MOST_VIEWED_ARN = os.environ["MOST_VIEWED_ARN"]

def get_user_personalized_recommendations(user_id):
    response = personalizeRt.get_recommendations(
        campaignArn=USER_PERSONALIZATION_ARN,
        userId=user_id
    )
    return response['itemList']

def rerank_items_for_user(user_id, item_list):
    response = personalizeRt.get_personalized_ranking(
        campaignArn=PERSONALIZED_RANKING_ARN,
        userId=user_id,
        inputList=item_list
    )
    return response['personalizedRanking']

def get_best_sellers(user_id):
    response = personalizeRt.get_recommendations(
        recommenderArn=BEST_SELLERS_ARN,
        userId=user_id
    )
    return response['itemList']

def get_most_viewed(user_id):
    response = personalizeRt.get_recommendations(
        recommenderArn=MOST_VIEWED_ARN,
        userId=user_id
    )
    return response['itemList']

def handler(event, context):
    agent = event['agent']
    actionGroup = event['actionGroup']
    function = event['function']
    parameters = event.get('parameters', [])

    if function == 'get_user_personalized_recommendations':
        user_id = next((param["value"] for param in parameters if param["name"] == 'user_id'), None)
        function_response = get_user_personalized_recommendations(user_id)

    elif function == 'rerank_items_for_user':
        user_id = next((param["value"] for param in parameters if param["name"] == 'user_id'), None)
        item_list = json.loads(next((param["value"] for param in parameters if param["name"] == 'item_list'), None))
        function_response = rerank_items_for_user(user_id, item_list)

    elif function == 'get_best_sellers':
        user_id = next((param["value"] for param in parameters if param["name"] == 'user_id'), None)
        function_response = get_best_sellers(user_id)

    elif function == 'get_most_viewed':
        user_id = next((param["value"] for param in parameters if param["name"] == 'user_id'), None)
        function_response = get_most_viewed(user_id)

    else:
        function_response = {"error": "Invalid function"}

    responseBody = {
        "TEXT": {
            "body": json.dumps(function_response)
        }
    }

    action_response = {
        'actionGroup': actionGroup,
        'function': function,
        'functionResponse': {
            'responseBody': responseBody
        }
    }

    response = {'response': action_response, 'messageVersion': event['messageVersion']}
    print("Response: {}".format(response))

    return response
"""