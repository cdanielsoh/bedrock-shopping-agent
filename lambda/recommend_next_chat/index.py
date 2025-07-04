import boto3
import os
import logging
from boto3.dynamodb.conditions import Key
import json
from datetime import datetime, timedelta

logger = logging.getLogger()
logger.setLevel(logging.INFO)

REGION = os.environ.get('AWS_REGION')


def handler(event, context):
    try:
        # Handle CORS preflight requests
        http_method = event.get('httpMethod') or event.get('requestContext', {}).get('http', {}).get('method', '')
        if http_method == 'OPTIONS':
            return {
                'statusCode': 200,
                'headers': {
                    'Access-Control-Allow-Origin': '*',
                    'Access-Control-Allow-Headers': 'Content-Type, Authorization, X-Requested-With',
                    'Access-Control-Allow-Methods': 'GET, POST, OPTIONS'
                },
                'body': json.dumps({'message': 'CORS preflight'})
            }
        
        # Handle both GET and POST requests
        if http_method == 'POST':
            # POST request with user data in body
            body = json.loads(event.get('body', '{}'))
            user_id = body.get('user_id')
            session_id = body.get('session_id')
            user_data = body.get('user_data', {})
            force_refresh = body.get('force_refresh', False)
        else:
            # GET request with user_id in query parameters
            if 'queryStringParameters' in event and event['queryStringParameters']:
                user_id = event['queryStringParameters'].get('user_id')
                session_id = event['queryStringParameters'].get('session_id')
                force_refresh = event['queryStringParameters'].get('force_refresh', '').lower() == 'true'
            else:
                user_id = event.get('user_id')
                session_id = event.get('session_id')
                force_refresh = event.get('force_refresh', False)
            user_data = {}
        
        if not user_id:
            return {
                'statusCode': 400,
                'headers': {
                    'Access-Control-Allow-Origin': '*',
                    'Access-Control-Allow-Headers': 'Content-Type, Authorization, X-Requested-With',
                    'Access-Control-Allow-Methods': 'GET, POST, OPTIONS'
                },
                'body': json.dumps({'error': 'user_id is required'})
            }
        
        recommendations = get_next_chat_recommendations(user_id, session_id, user_data, force_refresh)
        
        return {
            'statusCode': 200,
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Headers': 'Content-Type, Authorization, X-Requested-With',
                'Access-Control-Allow-Methods': 'GET, POST, OPTIONS'
            },
            'body': json.dumps({'recommendations': recommendations})
        }
    except Exception as e:
        logger.error(f"Error in handler: {str(e)}")
        return {
            'statusCode': 500,
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Headers': 'Content-Type, Authorization, X-Requested-With',
                'Access-Control-Allow-Methods': 'GET, POST, OPTIONS'
            },
            'body': json.dumps({'error': 'Internal server error'})
        }


def get_next_chat_recommendations(user_id: str, session_id: str = None, user_data: dict = None, force_refresh: bool = False):
    """
    Get the next chat recommendations for a user and session.
    """
    try:
        # Create cache key based on user_id and session_id for session-specific recommendations
        cache_key = f"{user_id}#{session_id}" if session_id else user_id
        
        # Skip cache check if force_refresh is True
        if not force_refresh:
            # Get the saved chat recommendations for the user/session (check if they're still fresh)
            saved_recommendations = get_saved_recommendations(cache_key)
            
            if saved_recommendations and len(saved_recommendations) > 0:
                # Check if recommendations are still fresh (less than 1 hour old)
                latest_rec = saved_recommendations[0]
                rec_time = datetime.fromisoformat(latest_rec.get('timestamp', ''))
                if datetime.now() - rec_time < timedelta(hours=1):
                    logger.info(f"Returning cached recommendations for cache_key {cache_key}")
                    return latest_rec.get('recommendations', [])

        logger.info(f"Generating fresh recommendations for user {user_id}, session {session_id} (force_refresh: {force_refresh})")

        # Generate new recommendations
        chat_history = get_recent_chat_history_from_both_tables(user_id, session_id, 5)
        logger.info(f"Retrieved {len(chat_history)} chat history messages for recommendations")
        
        # Use provided user_data or fetch from database
        if user_data:
            user_info = {**user_data, 'user_id': user_id}
        else:
            user_info = get_user_info(user_id)
        
        bedrock_client = boto3.client("bedrock-runtime", region_name=REGION)
        
        if chat_history and len(chat_history) > 0:
            # Generate recommendations based on chat history and user persona
            recommendations = generate_recommendations_with_history(bedrock_client, user_info, chat_history, force_refresh)
        else:
            # Generate initial recommendations based on user persona
            recommendations = generate_initial_recommendations(bedrock_client, user_info, force_refresh)
        
        # Save recommendations to DynamoDB with session-specific cache key
        save_recommendations(cache_key, recommendations)
        
        return recommendations
        
    except Exception as e:
        logger.error(f"Error getting recommendations: {str(e)}")
        # Return personalized fallback recommendations
        return get_personalized_fallback_recommendations(user_data or {'user_id': user_id})


def generate_recommendations_with_history(bedrock_client, user_info, chat_history, force_refresh=False):
    """Generate recommendations based on user info and chat history."""
    
    # Build context from chat history
    chat_context = ""
    for chat in chat_history[:3]:  # Use last 3 messages
        if chat.get('user_message'):
            chat_context += f"User: {chat['user_message']}\n"
        if chat.get('assistant_message'):
            chat_context += f"Assistant: {chat['assistant_message']}\n"
    
    # Build rich user context
    user_context = build_user_context(user_info)
    
    # Add variation prompt for refresh requests
    variation_instruction = ""
    if force_refresh:
        variation_instruction = "\n\nIMPORTANT: The user has requested fresh recommendations. Generate completely different suggestions from what they might have seen before. Be creative and offer new angles or approaches to their shopping interests."
    
    prompt = f"""Based on the following user information and recent chat history, generate exactly 4 short, engaging chat suggestions that would help continue the shopping conversation naturally.

User Information: {user_context}

Recent Chat History:
{chat_context}

Generate 4 different types of suggestions based on the user's persona and interests:
1. A follow-up question about their recent interest or conversation
2. A suggestion to explore a category from their persona ({user_info.get('persona', '')})
3. A question about their preferences that aligns with their shopping behavior
4. A suggestion about deals or recommendations that matches their discount preference ({user_info.get('discount_persona', '')})

Each suggestion should be:
- Maximum 8-10 words
- Natural and conversational
- Relevant to their shopping journey and persona
- Action-oriented and engaging
- Must be something that the user might say to the assistant and not the other way around
- Response should be in Korean

Return only the 4 suggestions as a JSON array of strings, nothing else."""

    try:
        response = bedrock_client.converse(
            modelId="us.anthropic.claude-3-7-sonnet-20250219-v1:0",
            messages=[
                {
                    "role": "user",
                    "content": [{"text": prompt}]
                }
            ],
            inferenceConfig={
                "maxTokens": 200,
                "temperature": 0.8 if force_refresh else 0.7  # Higher temperature for more variation
            }
        )
        
        content = response['output']['message']['content'][0]['text']
        # Try to parse JSON from the response
        try:
            recommendations = json.loads(content)
            if isinstance(recommendations, list) and len(recommendations) == 4:
                return recommendations
        except json.JSONDecodeError:
            pass
            
    except Exception as e:
        logger.error(f"Error generating recommendations with history: {str(e)}")
    
    # Fallback if Bedrock fails
    return get_contextual_fallback_recommendations(chat_history, user_info)


def generate_initial_recommendations(bedrock_client, user_info, force_refresh=False):
    """Generate initial recommendations for new users."""
    
    # Build rich user context
    user_context = build_user_context(user_info)
    
    # Add variation prompt for refresh requests
    variation_instruction = ""
    if force_refresh:
        variation_instruction = "\n\nIMPORTANT: The user has requested fresh recommendations. Generate completely different welcoming suggestions that offer new perspectives on their interests."
    
    prompt = f"""Based on the following user information, generate exactly 4 short, welcoming chat suggestions to start a personalized shopping conversation.

User Information: {user_context}

Generate 4 different types of initial suggestions that align with their persona and preferences:
1. A personalized greeting that acknowledges their interests ({user_info.get('persona', '')})
2. A question about what they're looking for in their preferred categories
3. A suggestion about popular items in their persona categories
4. A question about their shopping preferences that considers their discount behavior ({user_info.get('discount_persona', '')})

Each suggestion should be:
- Maximum 8-10 words
- Welcoming and friendly
- Relevant to their persona and shopping style
- Easy to respond to{variation_instruction}
- Must be something that the user might say to the assistant and not the other way around
- Response should be in Korean

Return only the 4 suggestions as a JSON array of strings, nothing else."""

    try:
        response = bedrock_client.converse(
            modelId="us.anthropic.claude-3-7-sonnet-20250219-v1:0",
            messages=[
                {
                    "role": "user",
                    "content": [{"text": prompt}]
                }
            ],
            inferenceConfig={
                "maxTokens": 200,
                "temperature": 0.8 if force_refresh else 0.7  # Higher temperature for more variation
            }
        )
        
        content = response['output']['message']['content'][0]['text']
        # Try to parse JSON from the response
        try:
            recommendations = json.loads(content)
            if isinstance(recommendations, list) and len(recommendations) == 4:
                return recommendations
        except json.JSONDecodeError:
            pass
            
    except Exception as e:
        logger.error(f"Error generating initial recommendations: {str(e)}")
    
    # Fallback if Bedrock fails
    return get_personalized_fallback_recommendations(user_info)


def build_user_context(user_info):
    """Build a rich user context string from user information."""
    context_parts = []
    
    if user_info.get('first_name'):
        context_parts.append(f"Name: {user_info['first_name']}")
    
    if user_info.get('age'):
        context_parts.append(f"Age: {user_info['age']}")
    
    if user_info.get('gender'):
        gender_display = "Male" if user_info['gender'] == 'M' else "Female" if user_info['gender'] == 'F' else user_info['gender']
        context_parts.append(f"Gender: {gender_display}")
    
    if user_info.get('persona'):
        persona_readable = user_info['persona'].replace('_', ', ').title()
        context_parts.append(f"Shopping Interests: {persona_readable}")
    
    if user_info.get('discount_persona'):
        discount_behavior = {
            'lower_priced_products': 'Prefers budget-friendly options',
            'all_discounts': 'Loves deals and discounts',
            'discount_indifferent': 'Values quality over price'
        }.get(user_info['discount_persona'], user_info['discount_persona'])
        context_parts.append(f"Price Preference: {discount_behavior}")
    
    return ", ".join(context_parts)


def get_contextual_fallback_recommendations(chat_history, user_info=None):
    """Get contextual fallback recommendations based on chat history and user info."""
    if user_info:
        return get_personalized_fallback_recommendations(user_info)
    
    if not chat_history:
        return get_fallback_recommendations()
    
    # Simple keyword-based fallback
    recent_message = chat_history[0].get('user_message', '').lower()
    
    if any(word in recent_message for word in ['shoe', 'boot', 'sneaker']):
        return [
            "Show me more shoe styles",
            "What's your shoe size?",
            "Looking for athletic or casual?",
            "Check out shoe deals today"
        ]
    elif any(word in recent_message for word in ['shirt', 'top', 'clothing']):
        return [
            "What size do you wear?",
            "Prefer casual or formal style?",
            "Show me clothing deals",
            "What colors do you like?"
        ]
    else:
        return get_fallback_recommendations()


def get_personalized_fallback_recommendations(user_info):
    """Get personalized fallback recommendations based on user persona."""
    if not user_info or not user_info.get('persona'):
        return get_fallback_recommendations()
    
    persona = user_info.get('persona', '').lower()
    discount_persona = user_info.get('discount_persona', '').lower()
    
    # Personalized fallbacks based on user persona
    if 'seasonal_furniture_floral' in persona:
        return [
            "Show me seasonal home decor",
            "What furniture is trending now?",
            "Help me find floral patterns",
            "Show me budget-friendly options" if 'lower_priced' in discount_persona else "What's new in home design?"
        ]
    elif 'books_apparel_homedecor' in persona:
        return [
            "Recommend some good books",
            "Show me latest fashion trends",
            "Help me decorate my space",
            "What deals are available?" if 'all_discounts' in discount_persona else "What's popular right now?"
        ]
    elif 'apparel_footwear_accessories' in persona:
        return [
            "Show me fashion trends",
            "Help me find the perfect shoes",
            "What accessories are popular?",
            "Find me affordable styles" if 'lower_priced' in discount_persona else "Show me premium collections"
        ]
    elif 'homedecor_electronics_outdoors' in persona:
        return [
            "Show me smart home gadgets",
            "Help me find outdoor gear",
            "What's new in electronics?",
            "Show me tech deals" if 'all_discounts' in discount_persona else "What's trending in home tech?"
        ]
    elif 'groceries_seasonal_tools' in persona:
        return [
            "Help me with grocery shopping",
            "Show me seasonal essentials",
            "What tools do I need?",
            "Show me quality products" if 'discount_indifferent' in discount_persona else "What's on sale today?"
        ]
    elif 'footwear_jewelry_furniture' in persona:
        return [
            "Help me find perfect shoes",
            "Show me jewelry collections",
            "What furniture fits my style?",
            "Find me great deals" if 'all_discounts' in discount_persona else "Show me premium options"
        ]
    elif 'accessories_groceries_books' in persona:
        return [
            "Recommend accessories for me",
            "Help with grocery planning",
            "Suggest some good reads",
            "Show me quality items" if 'discount_indifferent' in discount_persona else "What's popular today?"
        ]
    
    # Generic fallbacks
    return get_fallback_recommendations()


def get_fallback_recommendations():
    """Get default fallback recommendations."""
    return [
        "What are you shopping for today?",
        "Show me popular items",
        "Help me find deals",
        "What's trending now?"
    ]


def get_user_info(user_id: str):
    """Get user information from DynamoDB."""
    try:
        user_table_name = os.environ.get('USER_TABLE')
        if not user_table_name:
            return {'user_id': user_id}
            
        dynamodb = boto3.resource('dynamodb', region_name=REGION)
        user_table = dynamodb.Table(user_table_name)
        
        response = user_table.get_item(Key={'user_id': str(user_id)})
        return response.get('Item', {'user_id': user_id})
        
    except Exception as e:
        logger.error(f"Error getting user info: {str(e)}")
        return {'user_id': user_id}


def save_recommendations(cache_key: str, recommendations: list):
    """Save recommendations to DynamoDB with session-specific cache key."""
    try:
        chat_recommendations_table_name = os.environ.get('CHAT_RECOMMENDATIONS_TABLE')
        if not chat_recommendations_table_name:
            return
            
        dynamodb = boto3.resource('dynamodb', region_name=REGION)
        chat_recommendations_table = dynamodb.Table(chat_recommendations_table_name)
        
        chat_recommendations_table.put_item(
            Item={
                'user_id': str(cache_key),  # Using cache_key which includes session info
                'timestamp': datetime.now().isoformat(),
                'recommendations': recommendations,
                'ttl': int((datetime.now() + timedelta(hours=24)).timestamp())  # Expire after 24 hours
            }
        )
        
    except Exception as e:
        logger.error(f"Error saving recommendations: {str(e)}")


def get_saved_recommendations(cache_key: str):
    """
    Get the saved chat recommendations for a cache key (user#session).
    """
    try:
        chat_recommendations_table_name = os.environ.get('CHAT_RECOMMENDATIONS_TABLE')
        if not chat_recommendations_table_name:
            return []
            
        dynamodb = boto3.resource('dynamodb', region_name=REGION)
        chat_recommendations_table = dynamodb.Table(chat_recommendations_table_name)
        
        response = chat_recommendations_table.query(
            KeyConditionExpression=Key('user_id').eq(str(cache_key)),
            ScanIndexForward=False,  # Sort by timestamp descending
            Limit=1  # Only get the most recent
        )
        
        return response.get('Items', [])
    
    except Exception as e:
        logger.error(f"Error retrieving saved recommendations: {str(e)}")
        return []

def get_recent_chat_history_from_both_tables(user_id: str, session_id: str = None, limit: int = 10):
    """
    Get recent chat history from appropriate conversation table based on session mode.
    
    Args:
        user_id: The user ID
        session_id: The session ID 
        limit: Number of recent messages to retrieve
        
    Returns:
        List of recent chat messages from the appropriate conversation table
    """
    chat_history = []
    
    try:
        if session_id:
            # Determine session mode to choose appropriate table
            is_agent_mode = get_session_agent_mode(session_id)
            
            if is_agent_mode:
                # Agent mode - get from agent conversation table
                agent_history = get_agent_conversation_history(session_id, limit)
                chat_history.extend(agent_history)
                logger.info(f"Retrieved {len(agent_history)} messages from agent conversation table for session {session_id}")
            else:
                # Non-agent mode - get from conversation manager table
                conv_history = get_conversation_manager_history(session_id, limit)
                chat_history.extend(conv_history)
                logger.info(f"Retrieved {len(conv_history)} messages from conversation manager table for session {session_id}")
        else:
            # No session ID provided, try to get from legacy chat history table
            legacy_history = get_legacy_chat_history(user_id, limit)
            chat_history.extend(legacy_history)
            logger.info(f"Retrieved {len(legacy_history)} messages from legacy chat history table for user {user_id}")
        
        # Sort by timestamp and limit
        chat_history.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
        return chat_history[:limit]
        
    except Exception as e:
        logger.error(f"Error retrieving chat history: {str(e)}")
        return []


def get_session_agent_mode(session_id: str) -> bool:
    """
    Get the agent mode for a session from the sessions table.
    
    Args:
        session_id: The session ID
        
    Returns:
        True if session is in agent mode, False otherwise
    """
    try:
        sessions_table_name = os.environ.get('SESSIONS_TABLE')
        if not sessions_table_name:
            logger.warning("SESSIONS_TABLE environment variable not set, defaulting to non-agent mode")
            return False
            
        dynamodb = boto3.resource('dynamodb', region_name=REGION)
        sessions_table = dynamodb.Table(sessions_table_name)
        
        response = sessions_table.get_item(
            Key={'session_id': session_id}
        )
        
        if 'Item' in response:
            is_agent_mode = bool(response['Item'].get('is_agent_mode', False))
            logger.info(f"Session {session_id} agent mode: {is_agent_mode}")
            return is_agent_mode
        else:
            logger.info(f"Session {session_id} not found in sessions table, defaulting to non-agent mode")
            return False
        
    except Exception as e:
        logger.error(f"Error getting session agent mode for session {session_id}: {str(e)}")
        # If we can't determine the mode, try both tables as fallback
        return False


def get_legacy_chat_history(user_id: str, limit: int = 5):
    """Get chat history from legacy CHAT_HISTORY_TABLE."""
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
        logger.error(f"Error retrieving legacy chat history: {str(e)}")
        return []


def get_conversation_manager_history(session_id: str, limit: int = 5):
    """Get chat history from conversation manager table."""
    try:
        conversations_table_name = os.environ.get('CONVERSATIONS_TABLE')
        if not conversations_table_name:
            logger.warning("CONVERSATIONS_TABLE environment variable not set")
            return []
            
        dynamodb = boto3.resource('dynamodb', region_name=REGION)
        conversations_table = dynamodb.Table(conversations_table_name)
        
        # Query for all conversation entries for this session
        history = []
        
        # Try to get conversations with different handler types
        handler_types = ['search', 'order', 'recommendation', 'general']  # Common handler types
        
        for handler_type in handler_types:
            conversation_id = f"{session_id}#{handler_type}"
            
            try:
                response = conversations_table.get_item(
                    Key={'conversation_id': conversation_id}
                )
                
                if 'Item' in response:
                    messages = response['Item'].get('messages', [])
                    logger.info(f"Found {len(messages)} messages for conversation_id: {conversation_id}")
                    
                    # Convert to consistent format
                    for i, msg in enumerate(messages[-limit:]):
                        if isinstance(msg, dict):
                            role = msg.get('role', '')
                            content = msg.get('content', '')
                            timestamp = msg.get('timestamp', '')
                            
                            if role == 'user' and content:
                                history.append({
                                    'user_message': content,
                                    'assistant_message': None,
                                    'timestamp': timestamp,
                                    'source': f'conversation_manager_{handler_type}',
                                    'conversation_id': conversation_id
                                })
                            elif role == 'assistant' and content:
                                history.append({
                                    'user_message': None,
                                    'assistant_message': content,
                                    'timestamp': timestamp,
                                    'source': f'conversation_manager_{handler_type}',
                                    'conversation_id': conversation_id
                                })
                            
            except Exception as e:
                logger.warning(f"Error querying conversation_id {conversation_id}: {str(e)}")
                continue
        
        # Also try to get the session-level conversation (without handler type)
        try:
            response = conversations_table.get_item(
                Key={'conversation_id': session_id}
            )
            
            if 'Item' in response:
                messages = response['Item'].get('messages', [])
                logger.info(f"Found {len(messages)} messages for session-level conversation_id: {session_id}")
                
                # Convert to consistent format
                for msg in messages[-limit:]:
                    if isinstance(msg, dict):
                        role = msg.get('role', '')
                        content = msg.get('content', '')
                        timestamp = msg.get('timestamp', '')
                        
                        if role == 'user' and content:
                            history.append({
                                'user_message': content,
                                'assistant_message': None,
                                'timestamp': timestamp,
                                'source': 'conversation_manager_session',
                                'conversation_id': session_id
                            })
                        elif role == 'assistant' and content:
                            history.append({
                                'user_message': None,
                                'assistant_message': content,
                                'timestamp': timestamp,
                                'source': 'conversation_manager_session',
                                'conversation_id': session_id
                            })
                            
        except Exception as e:
            logger.warning(f"Error querying session-level conversation_id {session_id}: {str(e)}")
        
        logger.info(f"Total conversation manager history retrieved: {len(history)} messages")
        return history
        
    except Exception as e:
        logger.error(f"Error retrieving conversation manager history: {str(e)}")
        return []


def get_agent_conversation_history(session_id: str, limit: int = 5):
    """Get chat history from agent conversation manager table."""
    try:
        agent_conversations_table_name = os.environ.get('AGENT_CONVERSATIONS_TABLE')
        if not agent_conversations_table_name:
            logger.warning("AGENT_CONVERSATIONS_TABLE environment variable not set")
            return []
            
        dynamodb = boto3.resource('dynamodb', region_name=REGION)
        agent_conversations_table = dynamodb.Table(agent_conversations_table_name)
        
        response = agent_conversations_table.get_item(
            Key={'session_id': session_id}
        )
        
        if 'Item' in response:
            messages = response['Item'].get('messages', [])
            logger.info(f"Found {len(messages)} messages in agent conversation table for session {session_id}")
            
            # Convert to consistent format
            history = []
            for msg in messages[-limit:]:
                if not isinstance(msg, dict):
                    continue
                    
                role = msg.get('role', '')
                content = msg.get('content', '')
                timestamp = msg.get('timestamp', '')
                
                if role == 'user':
                    # Extract text content from user message
                    text_content = ''
                    if isinstance(content, list):
                        for content_block in content:
                            if isinstance(content_block, dict) and content_block.get('text'):
                                text_content += content_block['text']
                    elif isinstance(content, str):
                        text_content = content
                    
                    if text_content:
                        history.append({
                            'user_message': text_content,
                            'assistant_message': None,
                            'timestamp': timestamp,
                            'source': 'agent_conversation_manager'
                        })
                        
                elif role == 'assistant':
                    # Extract text content from assistant message
                    text_content = ''
                    if isinstance(content, list):
                        for content_block in content:
                            if isinstance(content_block, dict) and content_block.get('text'):
                                text_content += content_block['text']
                    elif isinstance(content, str):
                        text_content = content
                    
                    if text_content:
                        history.append({
                            'user_message': None,
                            'assistant_message': text_content,
                            'timestamp': timestamp,
                            'source': 'agent_conversation_manager'
                        })
            
            logger.info(f"Converted {len(history)} agent conversation messages")
            return history
        else:
            logger.info(f"No agent conversation found for session {session_id}")
            return []
        
    except Exception as e:
        logger.error(f"Error retrieving agent conversation history: {str(e)}")
        return []