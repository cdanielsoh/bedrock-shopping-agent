from aws_cdk import (
    Stack,
    aws_iam as iam,
    aws_bedrock as bedrock,
    aws_lambda as lambda_
)
from constructs import Construct
import json

class SearchAgentStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, opensearch_endpoint: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Create IAM role for Bedrock Agent
        agent_role = iam.Role(
            self, "BedrockAgentRole",
            assumed_by=iam.ServicePrincipal("bedrock.amazonaws.com"),
            role_name = 'AmazonBedrockExecutionRoleForAgents_SearchAgentStack',
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

        # Grant permissions to access OpenSearch
        agent_role.add_to_policy(iam.PolicyStatement(
            actions=[
                "aoss:APIAccessAll",
                "aoss:Get*"
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
                    "aoss:APIAccessAll",
                ],
                resources=["*"]
            )
        )
        opensearchpy_layer = lambda_.LayerVersion(
            self, "opensearchpyLayer",
            code=lambda_.Code.from_asset("./layers/opensearchpy"),
            compatible_runtimes=[lambda_.Runtime.PYTHON_3_9],
            description="Layer containing opensearchpy module"
        )

        search_function = lambda_.Function(
            self, "OpenSearchServerlessSearchFunction",
            runtime=lambda_.Runtime.PYTHON_3_9,
            handler="index.handler",
            code=lambda_.Code.from_inline(self._get_lambda_code()),
            environment={
                "OPENSEARCH_ENDPOINT": opensearch_endpoint,
                "OPENSEARCH_INDEX": "products"
            },
            layers=[opensearchpy_layer],
            role=lambda_role
        )

        search_function.add_to_role_policy(iam.PolicyStatement(
            actions=[
                "aoss:APIAccessAll",
                "aoss:Get*"
            ],
            resources=["*"]
        ))

        search_function.add_permission(
            "AllowBedrockInvokation",
            principal=iam.ServicePrincipal("bedrock.amazonaws.com"),
            action="lambda:InvokeFunction"
        )

        # Create Bedrock Agent
        self.agent = bedrock.CfnAgent(
            self, "SearchAgent",
            agent_name="SearchAgent",
            agent_resource_role_arn=agent_role.role_arn,
            instruction="You are an agent that searches an OpenSearch collection. Use the provided OpenSearch endpoint to perform searches.",
            foundation_model="anthropic.claude-3-haiku-20240307-v1:0",
            action_groups=[
                bedrock.CfnAgent.AgentActionGroupProperty(
                    action_group_name="SearchOpenSearch",
                    action_group_executor=bedrock.CfnAgent.ActionGroupExecutorProperty(
                        lambda_=search_function.function_arn
                    ),
                    function_schema=bedrock.CfnAgent.FunctionSchemaProperty(
                        functions=[
                            bedrock.CfnAgent.FunctionProperty(
                                name="keyword_product_search",
                                parameters={
                                    "query_keywords": bedrock.CfnAgent.ParameterDetailProperty(
                                        type="string",
                                        required=True
                                    )
                                }
                            ),
                            bedrock.CfnAgent.FunctionProperty(
                                name="semantic_product_search",
                                parameters={
                                    "query_string": bedrock.CfnAgent.ParameterDetailProperty(
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

        self.agent_alias = bedrock.CfnAgentAlias(
            self, "SearchAgentAlias",
            agent_id=self.agent.attr_agent_id,
            agent_alias_name="SearchAgentAlias",
        )

    def _get_lambda_code(self):
        return """
import json
import os
from opensearchpy import OpenSearch, RequestsHttpConnection, AWSV4SignerAuth
import requests
import boto3

HOST = os.environ['OPENSEARCH_ENDPOINT']
MODEL_ID = '7FzEGpQBRAQ7-2vvczrE'
INDEX = os.environ['OPENSEARCH_INDEX']
REGION = os.environ['AWS_REGION']

credentials = boto3.Session().get_credentials()
auth = AWSV4SignerAuth(
    credentials,
    REGION,
    'aoss',
)

client = OpenSearch(
    hosts=[{'host': HOST, 'port': 443}],
    http_auth=auth,
    use_ssl=True,
    verify_certs=True,
    connection_class=RequestsHttpConnection,
    pool_maxsize=30
)


def keyword_product_search(query_keywords):
    body = {
        "query": {
            "multi_match": {
                "query": query_keywords,
                "fields": ["name", "category", "style", "description"],
            }
        },
        "size": 10
    }

    response = client.search(
        index=INDEX,
        body=body,
    )

    return response['hits']['hits']


def semantic_product_search(query_string):
    body_personalize = {
        "query": {
            "neural": {
                "product_description_vector": {
                    "model_id": MODEL_ID,
                    "query_text": query_string,
                    "k": 5
                }
            },
        },
    }

    response = client.search(
        index=INDEX,
        body=body_personalize,
    )
    
    return response['hits']['hits']
    

def handler(event, context):
    agent = event['agent']
    actionGroup = event['actionGroup']
    function = event['function']
    parameters = event.get('parameters', [])


    if function == 'semantic_product_search':
        for param in parameters:
            if param["name"] == 'query_string':
                query_string = param["value"]

        function_response = semantic_product_search(query_string)

    elif function == 'keyword_product_search':
        for param in parameters:
            if param["name"] == 'query_keywords':
                query_keywords = param["value"]

        function_response = keyword_product_search(query_keywords)

    responseBody =  {
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

    dummy_function_response = {'response': action_response, 'messageVersion': event['messageVersion']}
    print("Response: {}".format(dummy_function_response))

    return dummy_function_response

"""