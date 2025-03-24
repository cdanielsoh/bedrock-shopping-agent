from aws_cdk import (
    Stack,
    aws_iam as iam,
    aws_bedrock as bedrock,
    aws_lambda as lambda_
)
from constructs import Construct
import json

class CustomerAgentStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, orders_table_name: str, users_table_name: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Create IAM role for Bedrock Agent
        agent_role = iam.Role(
            self, "BedrockAgentRole",
            assumed_by=iam.ServicePrincipal("bedrock.amazonaws.com"),
            role_name = 'AmazonBedrockExecutionRoleForAgents_CustomerAgentStack',
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

        # Grant permissions to access DynamoDB
        agent_role.add_to_policy(iam.PolicyStatement(
            actions=[
                "dynamodb:*"
            ],
            resources=["*"]
        ))

        lambda_role = iam.Role(
            self, "ActionGroupLambdaRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com")
        )

        lambda_role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSLambdaBasicExecutionRole")
        )

        lambda_role.add_to_policy(iam.PolicyStatement(
            actions=[
                "dynamodb:*"
            ],
            resources=["*"] 
        ))

        orders_function = lambda_.Function(
            self, "OrdersAccessFunction",
            runtime=lambda_.Runtime.PYTHON_3_9,
            handler="index.handler",
            code=lambda_.Code.from_inline(self._get_orders_lambda_code()),
            environment={
                "ORDERS_TABLE_NAME": orders_table_name
            },
            role=lambda_role
        )

        orders_function.add_permission(
            "AllowBedrockInvokation",
            principal=iam.ServicePrincipal("bedrock.amazonaws.com"),
            action="lambda:InvokeFunction"
        )

        users_function = lambda_.Function(
            self, "UsersAccessFunction",
            runtime=lambda_.Runtime.PYTHON_3_9,
            handler="index.handler",
            code=lambda_.Code.from_inline(self._get_users_lambda_code()),
            environment={
                "USERS_TABLE_NAME": users_table_name
            },
            role=lambda_role
        )

        users_function.add_permission(
            "AllowBedrockInvokation",
            principal=iam.ServicePrincipal("bedrock.amazonaws.com"),
            action="lambda:InvokeFunction"
        )

        self.agent = bedrock.CfnAgent(
            self, "CustomerAgent",
            agent_name="CustomerAgent",
            agent_resource_role_arn=agent_role.role_arn,
            instruction="You are an agent that interact with DynamoDB tables that contain user data and order data.",
            foundation_model="anthropic.claude-3-haiku-20240307-v1:0",
            action_groups=[
                bedrock.CfnAgent.AgentActionGroupProperty(
                    action_group_name="QueryOrdersTable",
                    action_group_executor=bedrock.CfnAgent.ActionGroupExecutorProperty(
                        lambda_=orders_function.function_arn
                    ),
                    function_schema=bedrock.CfnAgent.FunctionSchemaProperty(
                        functions=[
                            bedrock.CfnAgent.FunctionProperty(
                                name="get_user_orders",
                                parameters={
                                    "user_id": bedrock.CfnAgent.ParameterDetailProperty(
                                        type="string",
                                        required=True
                                    )
                                }
                            ),
                            # Think about this later
                            bedrock.CfnAgent.FunctionProperty(
                                name="purchase_order",
                                parameters={
                                    "user_id": bedrock.CfnAgent.ParameterDetailProperty(
                                        type="string",
                                        required=True
                                    ),
                                    "item_id": bedrock.CfnAgent.ParameterDetailProperty(
                                        type="string",
                                        required=True
                                    )
                                },
                                require_confirmation="ENABLED"
                            ),
                        ]
                    ),
                    action_group_state="ENABLED",
                ),
                bedrock.CfnAgent.AgentActionGroupProperty(
                    action_group_name="QueryUsersTable",
                    action_group_executor=bedrock.CfnAgent.ActionGroupExecutorProperty(
                        lambda_=users_function.function_arn
                    ),
                    function_schema=bedrock.CfnAgent.FunctionSchemaProperty(
                        functions=[
                            bedrock.CfnAgent.FunctionProperty(
                                name="update_address",
                                parameters={
                                    "user_id": bedrock.CfnAgent.ParameterDetailProperty(
                                        type="string",
                                        required=True
                                    )
                                },
                                require_confirmation="ENABLED"
                            ),
                            bedrock.CfnAgent.FunctionProperty(
                                name="get_address",
                                parameters={
                                    "user_id": bedrock.CfnAgent.ParameterDetailProperty(
                                        type="string",
                                        required=True
                                    )
                                }
                            ),
                            bedrock.CfnAgent.FunctionProperty(
                                name="update_email",
                                parameters={
                                    "user_id": bedrock.CfnAgent.ParameterDetailProperty(
                                        type="string",
                                        required=True
                                    )
                                },
                                require_confirmation="ENABLED"
                            ),
                            bedrock.CfnAgent.FunctionProperty(
                                name="get_email",
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

        self.agent_alias = bedrock.CfnAgentAlias(
            self, "CustomerAgentAlias",
            agent_id=self.agent.attr_agent_id,
            agent_alias_name="CustomerAgentAlias"
        )

    def _get_orders_lambda_code(self):
        return """
import boto3
import json
import os
import datetime
from boto3.dynamodb.conditions import Key

def handler(event, context):
    agent = event['agent']
    actionGroup = event['actionGroup']
    print(f"Received event: {json.dumps(event)}")
    
    try:
        # Get the DynamoDB table name from the environment variable
        table_name = os.environ.get('ORDERS_TABLE_NAME')
        
        # Initialize DynamoDB client
        dynamodb = boto3.resource('dynamodb')
        table = dynamodb.Table(table_name)
        
        # Extract request info from Bedrock agent
        function = event.get('function')
        
        # Parse parameters
        parameters = {}
        if 'parameters' in event and event['parameters']:
            for param in event['parameters']:
                parameters[param['name']] = param['value']
        
        print(f"Function: {function}, Parameters: {parameters}")
        
        # Logic to handle different functions
        if function == 'get_user_orders':
            function_response = get_user_orders(table, parameters)
        elif function == 'purchase_order':
            function_response =  purchase_order(table, parameters)
        else:
            error_msg = f"Unknown Function: {function}"
            print(error_msg)
            function_response =  {
                "messageVersion": "1.0",
                "response": {
                    "error": error_msg
                }
            }

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
            
    except Exception as e:
        error_msg = f"Error processing request: {str(e)}"
        print(error_msg)
        return {
            "messageVersion": "1.0",
            "response": {
                "error": error_msg
            }
        }

def get_user_orders(table, parameters):
    # Extract user_id from parameters
    user_id = parameters.get('user_id')
    
    if not user_id:
        return {
            "messageVersion": "1.0",
            "response": {
                "error": "user_id is required"
            }
        }
    
    # Query the table for orders with the given user_id
    try:
        response = table.query(
            IndexName='UserStatusIndex',
            KeyConditionExpression=Key('user_id').eq(int(user_id))
        )
        
        orders = response.get('Items', [])
        
        # Format orders for response
        formatted_orders = []
        for order in orders:
            formatted_order = {
                "order_id": order.get('order_id'),
                "timestamp": order.get('timestamp'),
                "item_id": order.get('item_id'),
                "delivery_status": order.get('delivery_status')
            }
            formatted_orders.append(formatted_order)
        print(formatted_orders)
        return {
            "messageVersion": "1.0",
            "response": {
                "orders": formatted_orders
            }
        }
    except Exception as e:
        error_msg = f"Error getting orders: {str(e)}"
        print(error_msg)
        return {
            "messageVersion": "1.0",
            "response": {
                "error": error_msg
            }
        }

def purchase_order(table, parameters):
    # Extract parameters
    user_id = parameters.get('user_id')
    item_id = parameters.get('item_id')
    
    if not user_id or not item_id:
        return {
            "messageVersion": "1.0",
            "response": {
                "error": "user_id and item_id are required"
            }
        }
    
    try:
        # Generate timestamp
        timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # Get the count of existing items to generate a new order_id
        count_response = table.scan(
            Select='COUNT'
        )
        new_order_id = str(count_response.get('Count', 0))
        
        # Create a new order
        new_order = {
            'order_id': new_order_id,
            'user_id': int(user_id),
            'timestamp': timestamp,
            'item_id': item_id,
            'delivery_status': 'Pending'
        }
        
        # Save to DynamoDB
        table.put_item(Item=new_order)
        
        return {
            "messageVersion": "1.0",
            "response": {
                "message": "Order created successfully",
                "order_id": new_order_id,
                "user_id": user_id,
                "item_id": item_id,
                "timestamp": timestamp,
                "delivery_status": "Pending"
            }
        }
    except Exception as e:
        error_msg = f"Error creating order: {str(e)}"
        print(error_msg)
        return {
            "messageVersion": "1.0",
            "response": {
                "error": error_msg
            }
        }"""


    def _get_users_lambda_code(self):
        return """
import boto3
import json
import os
import ast

def handler(event, context):
    agent = event['agent']
    actionGroup = event['actionGroup']
    print(f"Received event: {json.dumps(event)}")
    
    try:
        # Get the DynamoDB table name from the environment variable
        table_name = os.environ.get('USERS_TABLE_NAME')
        
        # Initialize DynamoDB client
        dynamodb = boto3.resource('dynamodb')
        table = dynamodb.Table(table_name)
        
        # Extract request info from Bedrock agent
        function = event.get('function')
        
        # Parse parameters
        parameters = {}
        if 'parameters' in event and event['parameters']:
            for param in event['parameters']:
                parameters[param['name']] = param['value']
        
        print(f"Function: {function}, Parameters: {parameters}")
        
        # Logic to handle different functions
        if function == 'update_address':
            function_response = update_address(table, parameters)
        elif function == 'get_address':
            function_response = get_address(table, parameters)
        elif function == 'update_email':
            function_response = update_email(table, parameters)
        elif function == 'get_email':
            function_response = get_email(table, parameters)
        else:
            error_msg = f"Unknown Function: {function}"
            print(error_msg)
            return {
                "messageVersion": "1.0",
                "response": {
                    "error": error_msg
                }
            }
        
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
            
    except Exception as e:
        error_msg = f"Error processing request: {str(e)}"
        print(error_msg)
        return {
            "messageVersion": "1.0",
            "response": {
                "error": error_msg
            }
        }

def get_address(table, parameters):
    # Extract user_id from parameters
    user_id = parameters.get('user_id')
    
    if not user_id:
        return {
            "messageVersion": "1.0",
            "response": {
                "error": "user_id is required"
            }
        }
    
    try:
        # Get the user from DynamoDB
        response = table.get_item(
            Key={
                'id': user_id
            }
        )
        
        user = response.get('Item')
        
        if not user:
            return {
                "messageVersion": "1.0",
                "response": {
                    "error": f"User with ID {user_id} not found"
                }
            }
        
        # Extract addresses from the user
        addresses = user.get('addresses', '[]')
        
        # The addresses might be stored as a string representation of a list
        if isinstance(addresses, str):
            try:
                addresses = ast.literal_eval(addresses)
            except:
                addresses = json.loads(addresses)
        
        return {
            "messageVersion": "1.0",
            "response": {
                "addresses": addresses
            }
        }
    except Exception as e:
        error_msg = f"Error getting address: {str(e)}"
        print(error_msg)
        return {
            "messageVersion": "1.0",
            "response": {
                "error": error_msg
            }
        }

def update_address(table, parameters):
    # Extract parameters
    user_id = parameters.get('user_id')
    address1 = parameters.get('address1', '')
    address2 = parameters.get('address2', '')
    city = parameters.get('city', '')
    state = parameters.get('state', '')
    zipcode = parameters.get('zipcode', '')
    country = parameters.get('country', 'US')
    
    if not user_id:
        return {
            "messageVersion": "1.0",
            "response": {
                "error": "user_id is required"
            }
        }
    
    try:
        # Get the current user
        response = table.get_item(
            Key={
                'id': user_id
            }
        )
        
        user = response.get('Item')
        
        if not user:
            return {
                "messageVersion": "1.0",
                "response": {
                    "error": f"User with ID {user_id} not found"
                }
            }
        
        # Extract user info for the new address
        first_name = user.get('first_name', '')
        last_name = user.get('last_name', '')
        
        # Extract current addresses
        addresses = user.get('addresses', '[]')
        
        # Convert from string if needed
        if isinstance(addresses, str):
            try:
                addresses = ast.literal_eval(addresses)
            except:
                addresses = json.loads(addresses)
        
        # Create the new address
        new_address = {
            'first_name': first_name,
            'last_name': last_name,
            'address1': address1,
            'address2': address2,
            'country': country,
            'city': city,
            'state': state,
            'zipcode': zipcode,
            'default': True
        }
        
        # Set this as default and unset other defaults
        for addr in addresses:
            if isinstance(addr, dict):
                addr['default'] = False
        
        # Add the new address
        addresses.append(new_address)
        
        # Update the user with the new addresses
        table.update_item(
            Key={
                'id': user_id
            },
            UpdateExpression='SET addresses = :addresses',
            ExpressionAttributeValues={
                ':addresses': json.dumps(addresses)  # Convert to JSON string
            }
        )
        
        return {
            "messageVersion": "1.0",
            "response": {
                "message": "Address updated successfully",
                "address": new_address
            }
        }
    except Exception as e:
        error_msg = f"Error updating address: {str(e)}"
        print(error_msg)
        return {
            "messageVersion": "1.0",
            "response": {
                "error": error_msg
            }
        }

def get_email(table, parameters):
    # Extract user_id from parameters
    user_id = parameters.get('user_id')
    
    if not user_id:
        return {
            "messageVersion": "1.0",
            "response": {
                "error": "user_id is required"
            }
        }
    
    try:
        # Get the user from DynamoDB
        response = table.get_item(
            Key={
                'id': user_id
            }
        )
        
        user = response.get('Item')
        
        if not user:
            return {
                "messageVersion": "1.0",
                "response": {
                    "error": f"User with ID {user_id} not found"
                }
            }
        
        # Extract email from the user
        email = user.get('email', '')
        
        return {
            "messageVersion": "1.0",
            "response": {
                "email": email
            }
        }
    except Exception as e:
        error_msg = f"Error getting email: {str(e)}"
        print(error_msg)
        return {
            "messageVersion": "1.0",
            "response": {
                "error": error_msg
            }
        }

def update_email(table, parameters):
    # Extract parameters
    user_id = parameters.get('user_id')
    new_email = parameters.get('email')
    
    if not user_id or not new_email:
        return {
            "messageVersion": "1.0",
            "response": {
                "error": "user_id and email are required"
            }
        }
    
    try:
        # Update the user with the new email
        table.update_item(
            Key={
                'id': user_id
            },
            UpdateExpression='SET email = :email',
            ExpressionAttributeValues={
                ':email': new_email
            }
        )
        
        return {
            "messageVersion": "1.0",
            "response": {
                "message": "Email updated successfully",
                "email": new_email
            }
        }
    except Exception as e:
        error_msg = f"Error updating email: {str(e)}"
        print(error_msg)
        return {
            "messageVersion": "1.0",
            "response": {
                "error": error_msg
            }
        }
"""

