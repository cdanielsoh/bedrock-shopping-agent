from opensearchpy import OpenSearch, RequestsHttpConnection, AWSV4SignerAuth
import requests
import boto3
from boto3.dynamodb.conditions import Key
import re
import json
import os
from datetime import datetime, timezone
import uuid
from decimal import Decimal
from stream_parser import StreamParser
from tools import GetOrderHistoryTool, GetProductReviewsTool, KeywordProductSearchTool
from prompts import ROUTER_PROMPT, ORDER_HISTORY_PROMPT, PRODUCT_SEARCH_PROMPT, PRODUCT_DETAILS_PROMPT, COMPARE_PRODUCTS_PROMPT, GENERAL_INQUIRY_PROMPT
from chat_history import ChatHistory

# Get configuration from environment variables
HOST = os.environ.get('OPENSEARCH_ENDPOINT', '5np3mnj9qh1jiqt03wd3.us-west-2.aoss.amazonaws.com')
INDEX = os.environ.get('OPENSEARCH_INDEX', 'products')
REGION = os.environ.get('REGION', 'us-west-2')
ORDERS_TABLE = os.environ.get('ORDERS_TABLE', 'OrdersTable')
REVIEWS_TABLE = os.environ.get('REVIEWS_TABLE', 'ReviewsTable')
USERS_TABLE = os.environ.get('USERS_TABLE', 'UsersTable')

credentials = boto3.Session().get_credentials()
auth = AWSV4SignerAuth(
    credentials,
    REGION,
    'aoss',
)
chat_history = ChatHistory()

def convert_floats_to_decimal(obj):
    """
    Recursively convert float values to Decimal for DynamoDB compatibility.
    """
    if isinstance(obj, float):
        return Decimal(str(obj))
    elif isinstance(obj, dict):
        return {key: convert_floats_to_decimal(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [convert_floats_to_decimal(item) for item in obj]
    else:
        return obj


def handler(event, context):
    # Get connection ID
    connection_id = event['requestContext']['connectionId']

    # Parse message from client
    print(f"Received event: {event}")
    body = json.loads(event['body'])
    user_id = body.get('user_id', '')
    user_message = body.get('user_message', '')
    user_persona = body.get('user_persona', '')
    user_discount_persona = body.get('user_discount_persona', '')
    
    # Additional user data for enhanced personalization
    user_name = body.get('user_name', '')
    user_email = body.get('user_email', '')
    user_age = body.get('user_age', '')
    user_gender = body.get('user_gender', '')

    print(f"User {user_id} ({user_name}) with persona '{user_persona}' and discount persona '{user_discount_persona}' sent: {user_message}")

    # Save user message to chat history with enhanced metadata
    save_chat_message(user_id, connection_id, 'user', user_message, {
        'user_persona': user_persona,
        'user_discount_persona': user_discount_persona,
        'user_name': user_name,
        'user_email': user_email,
        'user_age': user_age,
        'user_gender': user_gender
    })

    # Get endpoint URL for sending messages
    domain = event['requestContext']['domainName']
    stage = event['requestContext']['stage']
    endpoint = f"https://{domain}/{stage}"

    # Set up API Gateway management client
    apigw_management = boto3.client(
        'apigatewaymanagementapi',
        endpoint_url=endpoint
    )

    assistant_number = handle_router(user_message)

    print(f"Routing to assistant: {assistant_number}")

    if assistant_number == "1":
        handle_order_history(connection_id, apigw_management, user_message, user_id)
    elif assistant_number == "2":
        handle_product_search(connection_id, apigw_management, user_message, user_id, user_persona, user_discount_persona)
    elif assistant_number == "3":
        handle_product_details(connection_id, apigw_management, user_message, user_id, user_persona, user_discount_persona)
    elif assistant_number == "4":
        handle_general_inquiry(connection_id, apigw_management, user_message, user_id)
    elif assistant_number == "5":
        handle_compare_products(connection_id, apigw_management, user_message, user_id)
    return {
        'statusCode': 200,
        'body': 'Streaming process completed'
    }


def save_chat_message(user_id: str, connection_id: str, message_type: str, content: str, metadata: dict = None):
    """
    Save a chat message to the ChatHistory table.
    
    Args:
        user_id: The user ID
        connection_id: WebSocket connection ID
        message_type: 'user' or 'assistant'
        content: The message content
        metadata: Additional metadata (e.g., product results, order IDs)
    """
    try:
        chat_table_name = os.environ.get('CHAT_HISTORY_TABLE')
        if not chat_table_name:
            print("CHAT_HISTORY_TABLE environment variable not set")
            return
            
        dynamodb = boto3.resource('dynamodb', region_name=REGION)
        chat_table = dynamodb.Table(chat_table_name)
        
        # Generate timestamp and TTL (30 days from now)
        now = datetime.now(timezone.utc)
        timestamp = now.isoformat()
        ttl = int(now.timestamp()) + (30 * 24 * 60 * 60)  # 30 days
        
        item = {
            'user_id': str(user_id),
            'timestamp': timestamp,
            'connection_id': connection_id,
            'message_id': str(uuid.uuid4()),
            'message_type': message_type,
            'content': content,
            'ttl': ttl
        }
        
        if metadata:
            # Convert floats to Decimal for DynamoDB compatibility
            item['metadata'] = convert_floats_to_decimal(metadata)
            
        chat_table.put_item(Item=item)
        print(f"Saved chat message for user {user_id}: {message_type}")
        
    except Exception as e:
        print(f"Error saving chat message: {str(e)}")


def build_conversation_history(user_id: str, connection_id: str, current_message: str, limit: int = 10):
    """
    Build conversation history for Bedrock Converse API.
    
    Args:
        user_id: The user ID
        connection_id: Current WebSocket connection ID
        current_message: The current user message
        limit: Number of previous messages to include
        
    Returns:
        List of messages formatted for Bedrock Converse API
    """
    try:
        # Get recent chat history for this session (connection)
        chat_table_name = os.environ.get('CHAT_HISTORY_TABLE')
        if not chat_table_name:
            # If no chat history available, return just the current message
            return [
                {
                    "role": "user",
                    "content": [{"text": current_message}]
                }
            ]
            
        dynamodb = boto3.resource('dynamodb', region_name=REGION)
        chat_table = dynamodb.Table(chat_table_name)
        
        # Query by connection_id to get session-specific history
        response = chat_table.query(
            IndexName='ConnectionIndex',
            KeyConditionExpression=Key('connection_id').eq(connection_id),
            ScanIndexForward=True,  # Sort by timestamp ascending (oldest first)
            Limit=limit
        )
        
        messages = response.get('Items', [])
        
        # Build conversation history in Bedrock format
        conversation = []
        
        for message in messages:
            role = "user" if message['message_type'] == 'user' else "assistant"
            content = message['content']
            
            # Skip if this is a streaming chunk or incomplete message
            if len(content.strip()) < 3:
                continue
                
            conversation.append({
                "role": role,
                "content": [{"text": content}]
            })
        
        # Add the current message
        conversation.append({
            "role": "user", 
            "content": [{"text": current_message}]
        })
        
        return conversation
        
    except Exception as e:
        print(f"Error building conversation history: {str(e)}")
        # Fallback to just the current message
        return [
            {
                "role": "user",
                "content": [{"text": current_message}]
            }
        ]


def get_recent_chat_history(user_id: str, limit: int = 10):
    """
    Get recent chat history for a user.
    
    Args:
        user_id: The user ID
        limit: Number of recent messages to retrieve
        
    Returns:
        List of recent chat messages
    """
    try:
        chat_table_name = os.environ.get('CHAT_HISTORY_TABLE')
        if not chat_table_name:
            return []
            
        dynamodb = boto3.resource('dynamodb', region_name=REGION)
        chat_table = dynamodb.Table(chat_table_name)
        
        response = chat_table.query(
            KeyConditionExpression=Key('user_id').eq(str(user_id)),
            ScanIndexForward=False,  # Sort by timestamp descending
            Limit=limit
        )
        
        return response.get('Items', [])
        
    except Exception as e:
        print(f"Error retrieving chat history: {str(e)}")
        return []


def send_to_connection(apigw_client, connection_id, data):
    """Send data to the WebSocket connection."""
    try:
        apigw_client.post_to_connection(
            ConnectionId=connection_id,
            Data=json.dumps(data)
        )
        if data.get('type') != 'text_chunk':
            print(f"Sent message to connection: {data}")
    except Exception as e:
        print(f"Error sending message to connection {connection_id}: {str(e)}")


def handle_router(user_message: str):
    """
    Enhanced router that includes product details handling.
    """
    system_prompt = ROUTER_PROMPT
    messages = [
        {
            "role": "user",
            "content": [
                {
                    "text": f"If the user's message is {user_message}, what assistant should I route it to? Respond with only the assistant number (1, 2, 3, 4, or 5) that should handle the user's message. Do not include explanations or additional text."
                }
            ]
        }
    ]

    bedrock_client = boto3.client("bedrock-runtime", region_name=REGION)

    response = bedrock_client.converse(
        modelId="us.anthropic.claude-3-5-haiku-20241022-v1:0",
        messages=messages,
        system=[{"text": system_prompt}, {"cachePoint": {"type": "default"}}],
    )

    return response["output"]["message"]["content"][0]["text"]


def handle_order_history(connection_id: str, apigw_management: boto3.client, user_message: str, user_id: str = None):
    """
    Bedrock Converse API function that uses get_orders_with_user_id as a tool.
    Now includes conversation history for context and StreamParser for order delimiters.
    """
    send_to_connection(apigw_management, connection_id, {"type": "wait", "message": "Getting order history..."})
        
    bedrock_client = boto3.client("bedrock-runtime", region_name=REGION)

    oss_client = OpenSearch(
        hosts=[{'host': HOST, 'port': 443}],
        http_auth=auth,
        use_ssl=True,
        verify_certs=True,
        connection_class=RequestsHttpConnection,
        pool_maxsize=30
    )

    order_history = GetOrderHistoryTool(
        orders_table=ORDERS_TABLE,
        oss_client=oss_client,
        index=INDEX
    ).execute(user_id)
    
    # Build conversation history including current message
    messages = build_conversation_history(user_id, connection_id, user_message)

    # Initialize StreamParser with order history
    stream_parser = StreamParser(
        apigw_management, 
        connection_id, 
        orders_list=order_history
    )

    final_response = bedrock_client.converse_stream(
        modelId="us.anthropic.claude-3-5-haiku-20241022-v1:0",
        messages=messages,
        system=[{"text": ORDER_HISTORY_PROMPT.format(order_history=order_history)}],
    )
    
    for event in final_response['stream']:
        if 'contentBlockDelta' in event:
            if 'delta' in event['contentBlockDelta']:
                text_chunk = event['contentBlockDelta']['delta']['text']
                
                # Use StreamParser to handle order delimiters
                stream_parser.parse_chunk(text_chunk)
    
    # Finalize streaming
    stream_parser.finalize()
    
    # Save the complete assistant response to chat history
    if stream_parser.complete_response:
        metadata = {
            'response_type': 'order_history',
            'total_orders': len(order_history),
            'order_ids': [order.get('order_id') for order in order_history]
        }
        save_chat_message(user_id, connection_id, 'assistant', stream_parser.complete_response, metadata)


def personalize_search_results(search_results: list, user_id: str) -> list:
    # Extract product IDs from search results    
    if not search_results:
        return []

    # Format item list for Personalize (list of item IDs)
    item_list = [
        str(hit['_source']['id']) 
        for hit in search_results
    ]

    try:
        # Get personalized ranking from Amazon Personalize
        personalize_runtime = boto3.client('personalize-runtime', region_name='us-west-2')
        
        # Use environment variable or construct ARN
        personalized_ranking_arn = os.environ.get('PERSONALIZE_RANKING_CAMPAIGN_ARN')
        if not personalized_ranking_arn:
            # Construct ARN using the campaign name from the stack
            account_id = boto3.client('sts').get_caller_identity()['Account']
            personalized_ranking_arn = f"arn:aws:personalize:us-west-2:{account_id}:campaign/personalized-ranking"
        
        personalized_ranking = personalize_runtime.get_personalized_ranking(
            campaignArn=personalized_ranking_arn,
            userId=str(user_id),
            inputList=item_list
        )

        # Sort original search results by personalized ranking
        personalized_hits = []
        for item in personalized_ranking['personalizedRanking']:
            item_id = item['itemId']
            # Find the corresponding hit from original search
            for hit in search_results:
                if hit['_source']['id'] == item_id:
                    # Add personalization score to the hit
                    hit['_personalization_score'] = item['score']
                    personalized_hits.append(hit)
                    break
        
        # Return top 5 personalized results
        return personalized_hits[:5]

    except Exception as e:
        print(f"Personalization failed: {str(e)}")
        # Fallback to original search results if personalization fails
        return search_results[:5]


def handle_product_search(connection_id: str, apigw_management: boto3.client, user_message: str, user_id: str = None, user_persona: str = None, user_discount_persona: str = None):
    """
    Bedrock Converse API function that uses keyword_product_search as a tool.
    Now includes conversation history for context and token-based parsing with StreamParser.
    """
    print(f"Product search with user message: {user_message}")
    send_to_connection(apigw_management, connection_id, {"type": "wait", "message": "Searching for products..."})

    bedrock_client = boto3.client("bedrock-runtime", region_name=REGION)
    
    product_search_tool = KeywordProductSearchTool(
        os_host=HOST,
        index=INDEX,
        cloudfront_url=os.environ.get('IMAGES_CLOUDFRONT_URL'),
        dynamodb=boto3.resource('dynamodb', region_name=REGION),
        reviews_table=REVIEWS_TABLE
    )

    # Build conversation history including current message with user context
    messages = build_conversation_history(user_id, connection_id, user_message)

    tool_config = {
        "tools": [
            product_search_tool.get_tool_spec()
        ]
    }

    response = bedrock_client.converse(
        modelId="us.anthropic.claude-3-5-haiku-20241022-v1:0",
        messages=messages,
        system=[{"text": PRODUCT_SEARCH_PROMPT.format(
            user_id=user_id, 
            user_persona=user_persona, 
            user_discount_persona=user_discount_persona
        )}],
        toolConfig=tool_config
    )

    # Handle tool use
    if response["output"]["message"].get("content"):
        for content_block in response["output"]["message"]["content"]:
            if content_block.get("toolUse"):
                tool_use = content_block["toolUse"]
                if tool_use["name"] == product_search_tool.get_tool_name():                    
                    # Execute the tool
                    tool_input = tool_use["input"]
                    search_results = product_search_tool.execute(tool_input["query_keywords"])
                    personalized_search_results = personalize_search_results(search_results, user_id)
                    print(f"Search results: {search_results}")

                    # Send tool result back
                    messages.append(response["output"]["message"])
                    tool_result_message = {
                        "role": "user",
                        "content": [
                            {
                                "toolResult": {
                                    "toolUseId": tool_use["toolUseId"],
                                    "content": [
                                        {
                                            "json": {"results": personalized_search_results}
                                        }
                                    ]
                                }
                            }
                        ]
                    }
                    messages.append(tool_result_message)
                    
                    # Save the tool result to chat history
                    save_chat_message(user_id, connection_id, 'user', 
                                    f"Tool result for search: {tool_input['query_keywords']}", 
                                    {
                                        'message_type': 'tool_result',
                                        'tool_name': 'keyword_product_search',
                                        'tool_input': tool_input,
                                        'tool_results': personalized_search_results,
                                        'response_type': 'product_search_tool_result'
                                    })

                    # Initialize StreamParser with search results
                    stream_parser = StreamParser(
                        apigw_management, 
                        connection_id, 
                        search_results=personalized_search_results
                    )

                    # Get final response with streaming
                    final_response = bedrock_client.converse_stream(
                        modelId="us.anthropic.claude-3-5-haiku-20241022-v1:0",
                        messages=messages,
                        system=[{"text": PRODUCT_SEARCH_PROMPT.format(
                            user_id=user_id, 
                            user_persona=user_persona, 
                            user_discount_persona=user_discount_persona
                        )}],
                        toolConfig=tool_config
                    )
                    
                    for event in final_response['stream']:
                        if 'contentBlockDelta' in event:
                            if 'delta' in event['contentBlockDelta']:
                                text_chunk = event['contentBlockDelta']['delta']['text']
                                
                                # Use new StreamParser
                                stream_parser.parse_chunk(text_chunk)
                    
                    # Finalize streaming
                    stream_parser.finalize()
                    
                    # Save the complete assistant response to chat history
                    if stream_parser.complete_response:
                        metadata = {
                            'response_type': 'product_search',
                            'search_keywords': tool_input["query_keywords"],
                            'products_found': len(personalized_search_results),
                            'product_ids': [hit['_source']['id'] for hit in personalized_search_results]
                        }
                        save_chat_message(user_id, connection_id, 'assistant', stream_parser.complete_response, metadata)


def handle_product_details(connection_id: str, apigw_management: boto3.client, user_message: str, user_id: str = None, user_persona: str = None, user_discount_persona: str = None):
    """
    Handle product detail requests using complete conversation history including tool results.
    Enhanced with product review information.
    """
    # First, extract product IDs from recent chat history
    recent_history = get_recent_chat_history(user_id, limit=10)
    product_ids = []
    
    # Extract product IDs from metadata in chat history
    for message in recent_history:
        metadata = message.get('metadata', {})
        if metadata.get('response_type') == 'product_search' and 'product_ids' in metadata:
            product_ids.extend(metadata['product_ids'])
    
    # Remove duplicates while preserving order
    unique_product_ids = []
    for pid in product_ids:
        if pid not in unique_product_ids:
            unique_product_ids.append(pid)
    
    # Get reviews for these products
    product_reviews = {}
    if unique_product_ids:
        product_reviews = GetProductReviewsTool(
            dynamodb=boto3.resource('dynamodb', region_name=REGION),
            reviews_table=REVIEWS_TABLE
        ).execute(unique_product_ids)
    
    # Build conversation history including current message
    messages = build_conversation_history(user_id, connection_id, user_message)

    bedrock_client = boto3.client("bedrock-runtime", region_name=REGION)
    
    stream_parser = StreamParser(apigw_management, connection_id)
    
    final_response = bedrock_client.converse_stream(
        modelId="us.anthropic.claude-3-5-haiku-20241022-v1:0",
        messages=messages,
        system=[{"text": PRODUCT_DETAILS_PROMPT.format(
            user_persona=user_persona, 
            user_discount_persona=user_discount_persona,
            product_reviews=product_reviews
        )}],
    )

    for event in final_response['stream']:
        if 'contentBlockDelta' in event:
            if 'delta' in event['contentBlockDelta']:
                text_chunk = event['contentBlockDelta']['delta']['text']
                stream_parser.parse_chunk(text_chunk)

    stream_parser.finalize()
    
    # Save the complete assistant response to chat history
    if stream_parser.complete_response:
        metadata = {
            'response_type': 'product_details',
            'product_ids_with_reviews': list(product_reviews.keys()) if product_reviews else []
        }
        save_chat_message(user_id, connection_id, 'assistant', stream_parser.complete_response, metadata)


def handle_general_inquiry(connection_id: str, apigw_management: boto3.client, user_message: str, user_id: str = None):
    """
    Handle general inquiries using complete conversation history including tool results.
    """

    stream_parser = StreamParser(apigw_management, connection_id)
    messages = build_conversation_history(user_id, connection_id, user_message)
    
    bedrock_client = boto3.client("bedrock-runtime", region_name=REGION)

    final_response = bedrock_client.converse_stream(
        modelId="us.anthropic.claude-3-5-haiku-20241022-v1:0",
        messages=messages,
        system=[{"text": GENERAL_INQUIRY_PROMPT}],
    )

    for event in final_response['stream']:
        if 'contentBlockDelta' in event:
            if 'delta' in event['contentBlockDelta']:
                text_chunk = event['contentBlockDelta']['delta']['text']
                stream_parser.parse_chunk(text_chunk)

    stream_parser.finalize()
    
    # Save the complete assistant response to chat history
    if stream_parser.complete_response:
        save_chat_message(user_id, connection_id, 'assistant', stream_parser.complete_response, {})


def handle_compare_products(connection_id: str, apigw_management: boto3.client, user_message: str, user_id: str = None):
    """
    Handle product comparison requests using complete conversation history including tool results.
    """
    
    messages = build_conversation_history(user_id, connection_id, user_message)
    bedrock_client = boto3.client("bedrock-runtime", region_name=REGION)

    keyword_product_search_tool = KeywordProductSearchTool(
        os_host=HOST,
        index=INDEX,
        cloudfront_url=os.environ.get('IMAGES_CLOUDFRONT_URL'),
        dynamodb=boto3.resource('dynamodb', region_name=REGION),
        reviews_table=REVIEWS_TABLE
    )

    tool_config = {
        "tools": [
            keyword_product_search_tool.get_tool_spec()
        ]
    }

    # Global variable to store search results for the stream parser
    current_search_results = None
    
    def handle_streaming_with_tools(messages, is_continuation=False):
        """Handle streaming response with tool call detection and execution"""        
        response = bedrock_client.converse_stream(
            modelId="us.anthropic.claude-3-5-haiku-20241022-v1:0",
            messages=messages,
            system=[{"text": COMPARE_PRODUCTS_PROMPT}],
            toolConfig=tool_config
        )
        
        tool_calls = []
        current_tool_call = None
        
        # Create StreamParser instance outside the loop for non-tool responses
        # Pass current_search_results if available for product parsing
        stream_parser = StreamParser(apigw_management, connection_id, search_results=current_search_results)
        complete_response = ""
        
        for event in response['stream']:
            if 'contentBlockStart' in event:
                content_block = event['contentBlockStart']['start']
                if 'toolUse' in content_block:
                    # Tool call detected
                    current_tool_call = {
                        'toolUseId': content_block['toolUse']['toolUseId'],
                        'name': content_block['toolUse']['name'],
                        'input': {},
                        'input_buffer': ''  # Add buffer to accumulate JSON string
                    }
                    tool_calls.append(current_tool_call)
                    
                    # Send wait message
                    if current_tool_call['name'] == keyword_product_search_tool.get_tool_name():
                        send_to_connection(apigw_management, connection_id, {
                            "type": "wait", 
                            "message": "Searching for products to compare..."
                        })
            
            elif 'contentBlockDelta' in event:
                delta = event['contentBlockDelta']['delta']
                
                if 'text' in delta:
                    # For text chunks, handle them if no tools are being used
                    if not tool_calls:
                        text_chunk = delta['text']
                        complete_response += text_chunk
                        # Use the single StreamParser instance
                        stream_parser.parse_chunk(text_chunk)
                
                elif 'toolUse' in delta and current_tool_call:
                    # Tool input is being built - accumulate the JSON string
                    print(f"Tool input delta: {delta['toolUse']}")
                    
                    if 'input' in delta['toolUse']:
                        input_chunk = delta['toolUse']['input']
                        
                        # Accumulate the input chunks in the buffer
                        current_tool_call['input_buffer'] += str(input_chunk)
                        print(f"Accumulated input buffer: {current_tool_call['input_buffer']}")
            
            elif 'contentBlockStop' in event:
                # Tool call completed, parse the accumulated JSON and execute
                if tool_calls and current_tool_call:
                    try:
                        # Parse the complete JSON string
                        if current_tool_call['input_buffer']:
                            parsed_input = json.loads(current_tool_call['input_buffer'])
                            current_tool_call['input'] = parsed_input
                            print(f"Successfully parsed tool input: {parsed_input}")
                        
                        return execute_tools_and_continue(tool_calls, messages)
                    
                    except json.JSONDecodeError as e:
                        print(f"Failed to parse tool input JSON: {e}")
                        print(f"Raw input buffer: {current_tool_call['input_buffer']}")
                        
                        # Fallback: try to extract query_keywords if it's a search tool
                        if current_tool_call['name'] == keyword_product_search_tool.get_tool_name():
                            # Try to extract keywords from malformed JSON
                            buffer = current_tool_call['input_buffer']
                            if 'query_keywords' in buffer:
                                # Simple regex to extract the keywords array
                                import re
                                match = re.search(r'"query_keywords":\s*(\[.*?\])', buffer)
                                if match:
                                    try:
                                        keywords_json = match.group(1)
                                        keywords = json.loads(keywords_json)
                                        current_tool_call['input'] = {"query_keywords": keywords}
                                        print(f"Extracted keywords via fallback: {keywords}")
                                        return execute_tools_and_continue(tool_calls, messages)
                                    except:
                                        pass
                        
                        # If all parsing fails, set empty input
                        current_tool_call['input'] = {}
                        return execute_tools_and_continue(tool_calls, messages)
            
            elif 'messageStop' in event:
                # Finalize stream parser for non-tool responses
                if not tool_calls:
                    stream_parser.finalize()
                break
        
        return complete_response  # Return the accumulated response for non-tool cases

    def execute_tools_and_continue(tool_calls, messages):
        """Execute tools and continue with streaming response"""
        nonlocal current_search_results
        
        # Build assistant message with tool calls
        assistant_content = []
        for tool_call in tool_calls:
            assistant_content.append({
                "toolUse": {
                    "toolUseId": tool_call['toolUseId'],
                    "name": tool_call['name'],
                    "input": tool_call['input']
                }
            })
        
        # Add assistant message to conversation
        messages.append({
            "role": "assistant",
            "content": assistant_content
        })
        
        # Execute each tool and build tool results
        tool_results = []
        for tool_call in tool_calls:
            if tool_call['name'] == keyword_product_search_tool.get_tool_name():
                # Execute product search
                tool_input = tool_call['input']
                search_results = keyword_product_search_tool.execute(tool_input["query_keywords"])
                current_search_results = search_results  # Store for stream parser
                
                tool_results.append({
                    "toolResult": {
                        "toolUseId": tool_call['toolUseId'],
                        "content": [
                            {
                                "json": {"results": search_results}
                            }
                        ]
                    }
                })
                
                # Save tool result to chat history
                save_chat_message(user_id, connection_id, 'user', 
                                f"Tool result for comparison search: {tool_input['query_keywords']}", 
                                {
                                    'message_type': 'tool_result',
                                    'tool_name': 'keyword_product_search',
                                    'tool_input': tool_input,
                                    'tool_results': search_results,
                                    'response_type': 'product_comparison_tool_result'
                                })
        
        # Add tool results message
        messages.append({
            "role": "user",
            "content": tool_results
        })
        
        # Initialize StreamParser with search results for the continuation
        stream_parser = StreamParser(
            apigw_management, 
            connection_id, 
            search_results=current_search_results
        )
        
        # Continue with streaming after tool execution
        continuation_response = bedrock_client.converse_stream(
            modelId="us.anthropic.claude-3-5-haiku-20241022-v1:0",
            messages=messages,
            system=[{"text": COMPARE_PRODUCTS_PROMPT}],
            toolConfig=tool_config
        )
        
        complete_response = ""
        for event in continuation_response['stream']:
            if 'contentBlockDelta' in event:
                if 'delta' in event['contentBlockDelta'] and 'text' in event['contentBlockDelta']['delta']:
                    text_chunk = event['contentBlockDelta']['delta']['text']
                    complete_response += text_chunk
                    
                    # Use StreamParser to handle product delimiters
                    stream_parser.parse_chunk(text_chunk)
        
        # Finalize streaming
        stream_parser.finalize()
        
        return complete_response

    # Start the streaming process
    complete_response = handle_streaming_with_tools(messages)
    
    # Save the complete assistant response to chat history
    if complete_response:
        # Determine metadata based on whether tools were used
        metadata = {'response_type': 'product_comparison'}
        
        # Add search results info if available
        if current_search_results:
            metadata.update({
                'products_found': len(current_search_results),
                'product_ids': [hit['_source']['id'] for hit in current_search_results]
            })
        
        save_chat_message(user_id, connection_id, 'assistant', complete_response, metadata)
