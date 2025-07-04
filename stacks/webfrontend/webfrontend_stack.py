import aws_cdk as cdk
from constructs import Construct
from aws_cdk import (
    aws_lambda as lambda_,
    aws_apigatewayv2 as apigatewayv2,
    aws_apigatewayv2_integrations as apigatewayv2_integrations,
    aws_iam as iam,
    aws_s3 as s3,
    aws_s3_deployment as s3_deployment,
    aws_cloudfront as cloudfront,
    aws_cloudfront_origins as origins,
    aws_dynamodb as dynamodb,
    aws_apigateway as apigateway,
    aws_sqs as sqs,
    aws_lambda_event_sources as lambda_event_sources,
    Duration,
    CustomResource
)
from aws_cdk.custom_resources import (
    Provider
)
import os
import json
from datetime import datetime


class WebFrontendStack(cdk.Stack):
    def __init__(self, scope: Construct, id: str, opensearch_endpoint: str, orders_table_name: str, reviews_table_name: str, users_table_name: str, **kwargs):
        super().__init__(scope, id, **kwargs)

        # Create DynamoDB table to store WebSocket connections
        connections_table = dynamodb.Table(
            self, 'ConnectionsTable',
            partition_key=dynamodb.Attribute(
                name='connectionId',
                type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=cdk.RemovalPolicy.DESTROY,
        )

        # Create DynamoDB table for hybrid conversations (handler-specific messages)
        conversations_table = dynamodb.Table(
            self, 'ConversationsTable',
            partition_key=dynamodb.Attribute(
                name='conversation_id',  # Format: session_id#handler_type
                type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=cdk.RemovalPolicy.DESTROY,
            time_to_live_attribute='ttl'  # Auto-cleanup old conversations
        )

        # Add GSI for querying by session_id
        conversations_table.add_global_secondary_index(
            index_name='SessionIndex',
            partition_key=dynamodb.Attribute(
                name='session_id',
                type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name='updated_at',
                type=dynamodb.AttributeType.STRING
            ),
            projection_type=dynamodb.ProjectionType.ALL
        )

        # Create DynamoDB table for shared context (products, orders, preferences)
        shared_context_table = dynamodb.Table(
            self, 'SharedContextTable',
            partition_key=dynamodb.Attribute(
                name='session_id',
                type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=cdk.RemovalPolicy.DESTROY,
            time_to_live_attribute='ttl'  # Auto-cleanup old context
        )

        # Create DynamoDB table for performance metrics
        performance_metrics_table = dynamodb.Table(
            self, 'PerformanceMetricsTable',
            partition_key=dynamodb.Attribute(
                name='metric_id',  # Format: session_id#timestamp
                type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=cdk.RemovalPolicy.DESTROY,
            time_to_live_attribute='ttl'  # Auto-cleanup old metrics
        )

        # Add GSI for querying by user_id and timestamp
        performance_metrics_table.add_global_secondary_index(
            index_name='UserIdIndex',
            partition_key=dynamodb.Attribute(
                name='user_id',
                type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name='timestamp',
                type=dynamodb.AttributeType.STRING
            ),
            projection_type=dynamodb.ProjectionType.ALL
        )

        # Add GSI for querying by handler_type and timestamp
        performance_metrics_table.add_global_secondary_index(
            index_name='HandlerTypeIndex',
            partition_key=dynamodb.Attribute(
                name='handler_type',
                type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name='timestamp',
                type=dynamodb.AttributeType.STRING
            ),
            projection_type=dynamodb.ProjectionType.ALL
        )

        # Create DynamoDB table to store chat recommendations
        chat_recommendations_table = dynamodb.Table(
            self, 'ChatRecommendationsTable',
            partition_key=dynamodb.Attribute(
                name='user_id',
                type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name='timestamp',
                type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=cdk.RemovalPolicy.DESTROY,
            time_to_live_attribute='ttl'  # Auto-cleanup old recommendations
        )

        # Create DynamoDB table for user sessions
        user_sessions_table = dynamodb.Table(
            self, 'UserSessionsTable',
            partition_key=dynamodb.Attribute(
                name='session_id',
                type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=cdk.RemovalPolicy.DESTROY,
            time_to_live_attribute='ttl'  # Auto-cleanup old sessions
        )

        # Add GSI for querying sessions by user_id
        user_sessions_table.add_global_secondary_index(
            index_name='UserIdIndex',
            partition_key=dynamodb.Attribute(
                name='user_id',
                type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name='last_used',
                type=dynamodb.AttributeType.STRING
            ),
            projection_type=dynamodb.ProjectionType.ALL
        )

        # Add this table to your existing DynamoDB stack
        agent_conversations_table = dynamodb.Table(
            self, "AgentConversationsTable",
            table_name="AgentConversationsTable",
            partition_key=dynamodb.Attribute(
                name="session_id",
                type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            time_to_live_attribute="ttl",  # Auto-cleanup after 24 hours
            point_in_time_recovery=False,
            stream=dynamodb.StreamViewType.NEW_AND_OLD_IMAGES,
            removal_policy=cdk.RemovalPolicy.DESTROY
        )

        # Add GSI for querying by user_id if needed
        agent_conversations_table.add_global_secondary_index(
            index_name="UserIdIndex",
            partition_key=dynamodb.Attribute(
                name="user_id",
                type=dynamodb.AttributeType.STRING
            ),
            projection_type=dynamodb.ProjectionType.ALL
        )

        agent_event_loop_metrics_table = dynamodb.Table(
            self, "AgentEventLoopMetricsTable",
            table_name="AgentEventLoopMetricsTable",
            partition_key=dynamodb.Attribute(
                name="session_id",
                type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            time_to_live_attribute="ttl",  # Auto-cleanup after 24 hours
            point_in_time_recovery=False,
            stream=dynamodb.StreamViewType.NEW_AND_OLD_IMAGES,
            removal_policy=cdk.RemovalPolicy.DESTROY
        )

        agent_event_loop_metrics_table.add_global_secondary_index(
            index_name="UserIdIndex",
            partition_key=dynamodb.Attribute(
                name="user_id",
                type=dynamodb.AttributeType.STRING
            ),
        )

        # Create Lambda functions for WebSocket routes
        connect_function = lambda_.Function(
            self, 'ConnectFunction',
            runtime=lambda_.Runtime.PYTHON_3_10,
            handler='connect.handler',
            code=lambda_.Code.from_asset('lambda/websocket'),
            environment={
                'CONNECTIONS_TABLE': connections_table.table_name,
            },
        )

        disconnect_function = lambda_.Function(
            self, 'DisconnectFunction',
            runtime=lambda_.Runtime.PYTHON_3_10,
            handler='disconnect.handler',
            code=lambda_.Code.from_asset('lambda/websocket'),
            environment={
                'CONNECTIONS_TABLE': connections_table.table_name,
            },
        )

        # Create Lambda layer for OpenSearch integration
        opensearch_layer = lambda_.LayerVersion(
            self, 'OpenSearchLayer',
            code=lambda_.Code.from_asset('layers/opensearchpy'),
            compatible_runtimes=[lambda_.Runtime.PYTHON_3_10],
            description='Layer containing the OpenSearch SDK'
        )
        
        # Create Lambda layer for boto3
        boto3_layer = lambda_.LayerVersion(
            self, 'Boto3Layer',
            code=lambda_.Code.from_asset('layers/boto3'),
            compatible_runtimes=[lambda_.Runtime.PYTHON_3_10],
            description='Layer containing the latest boto3 SDK with prompt caching support'
        )

        # Create Lambda layer for strands
        strands_layer = lambda_.LayerVersion(
            self, 'StrandsLayer',
            code=lambda_.Code.from_asset('layers/strands'),
            compatible_runtimes=[lambda_.Runtime.PYTHON_3_10],
            description='Layer containing the strands SDK'
        )

        # Create Bedrock Lambda function with both KnowledgeBase and OpenSearch access
        message_function = lambda_.Function(
            self, 'MessageLambdaFunction',
            runtime=lambda_.Runtime.PYTHON_3_10,
            handler='message_refactored.handler',
            code=lambda_.Code.from_asset('lambda/websocket'),
            layers=[opensearch_layer, boto3_layer, strands_layer],
            environment={
                'REGION': self.region,
                'CONNECTIONS_TABLE': connections_table.table_name,
                'CONVERSATIONS_TABLE': conversations_table.table_name,
                'SHARED_CONTEXT_TABLE': shared_context_table.table_name,
                'PERFORMANCE_METRICS_TABLE': performance_metrics_table.table_name,
                'SESSIONS_TABLE': user_sessions_table.table_name,
                'OPENSEARCH_ENDPOINT': opensearch_endpoint,
                'OPENSEARCH_INDEX': 'products',
                'ORDERS_TABLE': orders_table_name,
                'REVIEWS_TABLE': reviews_table_name,
                'USERS_TABLE': users_table_name,
                'AGENT_CONVERSATIONS_TABLE': agent_conversations_table.table_name,
                'AGENT_EVENT_LOOP_METRICS_TABLE': agent_event_loop_metrics_table.table_name,
            },
            timeout=Duration.minutes(5),
            memory_size=1024
        )

        # Create Lambda function for session management
        session_management_function = lambda_.Function(
            self, 'SessionManagementFunction',
            runtime=lambda_.Runtime.PYTHON_3_10,
            handler='session_manager.lambda_handler',
            code=lambda_.Code.from_asset('lambda/sessions'),
            environment={
                'REGION': self.region,
                'SESSIONS_TABLE': user_sessions_table.table_name,
            },
            timeout=Duration.minutes(2),
            memory_size=512
        )

        # Grant permissions to session management function
        user_sessions_table.grant_read_write_data(session_management_function)

        # Create Lambda function for chat recommendations
        recommend_chat_function = lambda_.Function(
            self, 'RecommendChatFunction',
            runtime=lambda_.Runtime.PYTHON_3_10,
            handler='index.handler',
            code=lambda_.Code.from_asset('lambda/recommend_next_chat'),
            layers=[boto3_layer],
            environment={
                'REGION': self.region,
                'CHAT_RECOMMENDATIONS_TABLE': chat_recommendations_table.table_name,
                'USER_TABLE': users_table_name,
                'AGENT_CONVERSATIONS_TABLE': agent_conversations_table.table_name,
                'CONVERSATIONS_TABLE': conversations_table.table_name,
                'SESSIONS_TABLE': user_sessions_table.table_name,
            },
            timeout=Duration.minutes(2),
            memory_size=512
        )

        # Grant permissions to Lambda functions
        connections_table.grant_read_write_data(connect_function)
        connections_table.grant_read_write_data(disconnect_function)
        connections_table.grant_read_write_data(message_function)

        # Grant hybrid conversation tables permissions
        conversations_table.grant_read_write_data(message_function)
        shared_context_table.grant_read_write_data(message_function)
        performance_metrics_table.grant_read_write_data(message_function)
        
        # Grant sessions table permissions
        user_sessions_table.grant_read_write_data(message_function)
        
        # Grant agent conversations table permissions
        agent_conversations_table.grant_read_write_data(message_function)
        agent_event_loop_metrics_table.grant_read_write_data(message_function)
        
        # Grant chat recommendations table permissions
        chat_recommendations_table.grant_read_write_data(recommend_chat_function)
        
        # Grant sessions table permissions to recommend_chat_function
        user_sessions_table.grant_read_data(recommend_chat_function)
        
        # Grant conversations table permissions to recommend_chat_function
        conversations_table.grant_read_data(recommend_chat_function)
        agent_conversations_table.grant_read_data(recommend_chat_function)

        # Grant Bedrock permissions to Lambda functions
        bedrock_policy = iam.PolicyStatement(
            actions=[
                'bedrock:RetrieveAndGenerate',
                'bedrock:Retrieve',
                'bedrock:InvokeModelWithResponseStream',
                'bedrock:InvokeModel',
                'bedrock:Rerank'
            ],
            resources=['*'],
        )
        message_function.add_to_role_policy(bedrock_policy)
        recommend_chat_function.add_to_role_policy(bedrock_policy)

        # Grant OpenSearch Serverless permissions
        opensearch_policy = iam.PolicyStatement(
            actions=['aoss:APIAccessAll'],
            resources=['*'],
        )
        message_function.add_to_role_policy(opensearch_policy)

        # Grant DynamoDB permissions for external tables
        external_dynamodb_policy = iam.PolicyStatement(
            actions=[
                'dynamodb:GetItem',
                'dynamodb:Query',
                'dynamodb:Scan',
                'dynamodb:BatchGetItem',
                'dynamodb:DescribeTable'
            ],
            resources=[
                f'arn:aws:dynamodb:{self.region}:{self.account}:table/{orders_table_name}',
                f'arn:aws:dynamodb:{self.region}:{self.account}:table/{reviews_table_name}',
                f'arn:aws:dynamodb:{self.region}:{self.account}:table/{users_table_name}',
                f'arn:aws:dynamodb:{self.region}:{self.account}:table/{orders_table_name}/index/*',
                f'arn:aws:dynamodb:{self.region}:{self.account}:table/{reviews_table_name}/index/*',
                f'arn:aws:dynamodb:{self.region}:{self.account}:table/{users_table_name}/index/*'
            ]
        )
        message_function.add_to_role_policy(external_dynamodb_policy)
        recommend_chat_function.add_to_role_policy(external_dynamodb_policy)

        # Grant Amazon Personalize permissions (if needed in future)
        personalize_policy = iam.PolicyStatement(
            actions=[
                'personalize:GetPersonalizedRanking',
                'personalize:GetRecommendations'
            ],
            resources=['*']
        )
        message_function.add_to_role_policy(personalize_policy)

        # Grant STS permissions to get account ID
        sts_policy = iam.PolicyStatement(
            actions=['sts:GetCallerIdentity'],
            resources=['*']
        )
        message_function.add_to_role_policy(sts_policy)

        # Create WebSocket API
        websocket_api = apigatewayv2.WebSocketApi(
            self, 'BedrockWebSocketAPI',
            connect_route_options=apigatewayv2.WebSocketRouteOptions(
                integration=apigatewayv2_integrations.WebSocketLambdaIntegration(
                    'ConnectIntegration', connect_function
                )
            ),
            disconnect_route_options=apigatewayv2.WebSocketRouteOptions(
                integration=apigatewayv2_integrations.WebSocketLambdaIntegration(
                    'DisconnectIntegration', disconnect_function
                )
            ),
            default_route_options=apigatewayv2.WebSocketRouteOptions(
                integration=apigatewayv2_integrations.WebSocketLambdaIntegration(
                    'MessageIntegration', message_function
                )
            ),
        )

        # Add permissions for Lambda to post to connections
        websocket_stage = apigatewayv2.WebSocketStage(
            self, 'WebSocketStage',
            web_socket_api=websocket_api,
            stage_name='prod',
            auto_deploy=True,
        )

        # Grant permission for Bedrock Lambda to manage WebSocket connections
        websocket_policy = iam.PolicyStatement(
            actions=['execute-api:ManageConnections'],
            resources=[f'arn:aws:execute-api:{self.region}:{self.account}:{websocket_api.api_id}/*'],
        )
        message_function.add_to_role_policy(websocket_policy)

        # Create HTTP API Gateway for recommendations
        http_api = apigatewayv2.HttpApi(
            self, 'RecommendationsHttpApi',
            cors_preflight=apigatewayv2.CorsPreflightOptions(
                allow_origins=['*'],
                allow_methods=[
                    apigatewayv2.CorsHttpMethod.GET, 
                    apigatewayv2.CorsHttpMethod.POST, 
                    apigatewayv2.CorsHttpMethod.PUT,
                    apigatewayv2.CorsHttpMethod.DELETE,
                    apigatewayv2.CorsHttpMethod.OPTIONS
                ],
                allow_headers=['Content-Type', 'Authorization', 'X-Requested-With'],
                max_age=Duration.seconds(300)
            )
        )

        # Add routes for session management
        # GET /sessions/{userId} - Get user sessions
        http_api.add_routes(
            path='/sessions/{userId}',
            methods=[apigatewayv2.HttpMethod.GET],
            integration=apigatewayv2_integrations.HttpLambdaIntegration(
                'GetUserSessionsIntegration',
                session_management_function
            )
        )

        # POST /sessions - Create new session
        http_api.add_routes(
            path='/sessions',
            methods=[apigatewayv2.HttpMethod.POST],
            integration=apigatewayv2_integrations.HttpLambdaIntegration(
                'CreateSessionIntegration',
                session_management_function
            )
        )

        # PUT /sessions/{sessionId} - Update session
        http_api.add_routes(
            path='/sessions/{sessionId}',
            methods=[apigatewayv2.HttpMethod.PUT],
            integration=apigatewayv2_integrations.HttpLambdaIntegration(
                'UpdateSessionIntegration',
                session_management_function
            )
        )

        # DELETE /sessions/{sessionId} - Delete session
        http_api.add_routes(
            path='/sessions/{sessionId}',
            methods=[apigatewayv2.HttpMethod.DELETE],
            integration=apigatewayv2_integrations.HttpLambdaIntegration(
                'DeleteSessionIntegration',
                session_management_function
            )
        )

        # Add routes for getting recommendations (both GET and POST)
        http_api.add_routes(
            path='/recommendations',
            methods=[apigatewayv2.HttpMethod.GET],
            integration=apigatewayv2_integrations.HttpLambdaIntegration(
                'RecommendChatGetIntegration',
                recommend_chat_function
            )
        )

        http_api.add_routes(
            path='/recommendations',
            methods=[apigatewayv2.HttpMethod.POST],
            integration=apigatewayv2_integrations.HttpLambdaIntegration(
                'RecommendChatPostIntegration',
                recommend_chat_function
            )
        )

        # Create S3 bucket for hosting React website
        website_bucket = s3.Bucket(
            self, 'ReactWebsiteBucket',
            removal_policy=cdk.RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
        )

        # Create S3 bucket for product images
        images_bucket = s3.Bucket(
            self, 'ProductImagesBucket',
            removal_policy=cdk.RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
        )

        # Deploy images to S3 bucket
        s3_deployment.BucketDeployment(
            self, 'ProductImagesDeployment',
            sources=[s3_deployment.Source.asset('images')],
            destination_bucket=images_bucket,
        )

        # CloudFront Origin Access Identity for website S3
        website_oai = cloudfront.OriginAccessIdentity(
            self, 'WebsiteOAI',
            comment=f'OAI for {id} website'
        )

        # CloudFront Origin Access Identity for images S3
        images_oai = cloudfront.OriginAccessIdentity(
            self, 'ImagesOAI',
            comment=f'OAI for {id} product images'
        )

        # Grant read permissions to CloudFront
        website_bucket.grant_read(website_oai)
        images_bucket.grant_read(images_oai)

        # Create CloudFront distribution for website
        website_distribution = cloudfront.Distribution(
            self, 'WebsiteDistribution',
            default_behavior=cloudfront.BehaviorOptions(
                origin=origins.S3Origin(
                    website_bucket,
                    origin_access_identity=website_oai
                ),
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                cache_policy=cloudfront.CachePolicy.CACHING_OPTIMIZED,
                origin_request_policy=cloudfront.OriginRequestPolicy.CORS_S3_ORIGIN,
            ),
            default_root_object="index.html",
            error_responses=[
                # For SPA routing, redirect all 404s to index.html
                cloudfront.ErrorResponse(
                    http_status=404,
                    response_http_status=200,
                    response_page_path="/index.html",
                )
            ],
        )

        # Create CloudFront distribution for product images
        images_distribution = cloudfront.Distribution(
            self, 'ImagesDistribution',
            default_behavior=cloudfront.BehaviorOptions(
                origin=origins.S3Origin(
                    images_bucket,
                    origin_access_identity=images_oai
                ),
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                cache_policy=cloudfront.CachePolicy.CACHING_OPTIMIZED,
                compress=True,
            ),
        )

        # Add environment variable for images CloudFront URL to Lambda
        message_function.add_environment(
            'IMAGES_CLOUDFRONT_URL', 
            f'https://{images_distribution.distribution_domain_name}'
        )

        # Create monitoring API Lambda function
        monitoring_function = lambda_.Function(
            self, 'MonitoringApiFunction',
            runtime=lambda_.Runtime.PYTHON_3_10,
            handler='monitoring_api.lambda_handler',
            code=lambda_.Code.from_asset('lambda/monitoring'),
            timeout=cdk.Duration.seconds(30),
            memory_size=256,
            environment={
                'REGION': self.region,
                'CONVERSATIONS_TABLE': conversations_table.table_name,
                'SHARED_CONTEXT_TABLE': shared_context_table.table_name,
                'PERFORMANCE_METRICS_TABLE': performance_metrics_table.table_name,
                'SESSIONS_TABLE': user_sessions_table.table_name,
                'AGENT_CONVERSATIONS_TABLE': agent_conversations_table.table_name,  # Added agent conversations
                'AGENT_EVENT_LOOP_METRICS_TABLE': agent_event_loop_metrics_table.table_name,
            },
            layers=[boto3_layer]
        )

        # Grant monitoring function read access to tables
        conversations_table.grant_read_data(monitoring_function)
        shared_context_table.grant_read_data(monitoring_function)
        performance_metrics_table.grant_read_data(monitoring_function)
        user_sessions_table.grant_read_data(monitoring_function)
        agent_conversations_table.grant_read_data(monitoring_function)  # Added agent conversations access
        agent_event_loop_metrics_table.grant_read_data(monitoring_function)  # Added agent event loop metrics access

        # Add monitoring routes to HTTP API
        monitoring_integration = apigatewayv2_integrations.HttpLambdaIntegration(
            'MonitoringIntegration',
            monitoring_function
        )

        # Add monitoring API routes
        http_api.add_routes(
            path='/monitoring/conversations/{sessionId}',
            methods=[apigatewayv2.HttpMethod.GET, apigatewayv2.HttpMethod.OPTIONS],
            integration=monitoring_integration
        )

        # Add agent conversation monitoring routes
        http_api.add_routes(
            path='/monitoring/agent-conversations/{sessionId}',
            methods=[apigatewayv2.HttpMethod.GET, apigatewayv2.HttpMethod.OPTIONS],
            integration=monitoring_integration  # Use the same monitoring integration
        )

        http_api.add_routes(
            path='/monitoring/context/{sessionId}',
            methods=[apigatewayv2.HttpMethod.GET, apigatewayv2.HttpMethod.OPTIONS],
            integration=monitoring_integration
        )

        http_api.add_routes(
            path='/monitoring/router/{sessionId}',
            methods=[apigatewayv2.HttpMethod.GET, apigatewayv2.HttpMethod.OPTIONS],
            integration=monitoring_integration
        )

        http_api.add_routes(
            path='/monitoring/sessions/{userId}',
            methods=[apigatewayv2.HttpMethod.GET, apigatewayv2.HttpMethod.OPTIONS],
            integration=monitoring_integration
        )

        http_api.add_routes(
            path='/monitoring/performance',
            methods=[apigatewayv2.HttpMethod.GET, apigatewayv2.HttpMethod.OPTIONS],
            integration=monitoring_integration
        )

        # Output the WebSocket API URL
        cdk.CfnOutput(
            self, 'WebSocketURL',
            value=websocket_stage.url,
            description='URL of the WebSocket API',
        )

        # Output the HTTP API URL
        cdk.CfnOutput(
            self, 'HttpApiUrl',
            value=http_api.url,
            description='URL of the HTTP API for recommendations',
        )

        # Output the CloudFront distribution URL
        cdk.CfnOutput(
            self, 'WebsiteURL',
            value=f'https://{website_distribution.distribution_domain_name}',
            description='URL of the website',
        )

        # Output the Images CloudFront URL
        cdk.CfnOutput(
            self, 'ImagesURL',
            value=f'https://{images_distribution.distribution_domain_name}',
            description='URL of the product images CDN',
        )

        # Output the S3 bucket name for frontend deployment
        cdk.CfnOutput(
            self, 'WebsiteBucketName',
            value=website_bucket.bucket_name,
            description='Name of the S3 bucket hosting the website',
        )

        # Store references for potential future use
        self.chat_recommendations_table = chat_recommendations_table
        self.http_api = http_api
        self.websocket_api = websocket_api
