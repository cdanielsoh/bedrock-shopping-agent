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
            user_data = body.get('user_data', {})
            force_refresh = body.get('force_refresh', False)
        else:
            # GET request with user_id in query parameters
            if 'queryStringParameters' in event and event['queryStringParameters']:
                user_id = event['queryStringParameters'].get('user_id')
                force_refresh = event['queryStringParameters'].get('force_refresh', '').lower() == 'true'
            else:
                user_id = event.get('user_id')
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
        
        recommendations = get_next_chat_recommendations(user_id, user_data, force_refresh)
        
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


def get_next_chat_recommendations(user_id: str, user_data: dict = None, force_refresh: bool = False):
    """
    Get the next chat recommendations for a user.
    """
    try:
        # Skip cache check if force_refresh is True
        if not force_refresh:
            # Get the saved chat recommendations for the user (check if they're still fresh)
            saved_recommendations = get_saved_recommendations(user_id)
            
            if saved_recommendations and len(saved_recommendations) > 0:
                # Check if recommendations are still fresh (less than 1 hour old)
                latest_rec = saved_recommendations[0]
                rec_time = datetime.fromisoformat(latest_rec.get('timestamp', ''))
                if datetime.now() - rec_time < timedelta(hours=1):
                    logger.info(f"Returning cached recommendations for user {user_id}")
                    return latest_rec.get('recommendations', [])

        logger.info(f"Generating fresh recommendations for user {user_id} (force_refresh: {force_refresh})")

        # Generate new recommendations
        chat_history = get_recent_chat_history(user_id, 5)
        
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
        
        # Save recommendations to DynamoDB
        save_recommendations(user_id, recommendations)
        
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
- Action-oriented and engaging{variation_instruction}
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


def save_recommendations(user_id: str, recommendations: list):
    """Save recommendations to DynamoDB."""
    try:
        chat_recommendations_table_name = os.environ.get('CHAT_RECOMMENDATIONS_TABLE')
        if not chat_recommendations_table_name:
            return
            
        dynamodb = boto3.resource('dynamodb', region_name=REGION)
        chat_recommendations_table = dynamodb.Table(chat_recommendations_table_name)
        
        chat_recommendations_table.put_item(
            Item={
                'user_id': str(user_id),
                'timestamp': datetime.now().isoformat(),
                'recommendations': recommendations,
                'ttl': int((datetime.now() + timedelta(hours=24)).timestamp())  # Expire after 24 hours
            }
        )
        
    except Exception as e:
        logger.error(f"Error saving recommendations: {str(e)}")


def get_saved_recommendations(user_id: str):
    """
    Get the saved chat recommendations for a user.
    """
    try:
        chat_recommendations_table_name = os.environ.get('CHAT_RECOMMENDATIONS_TABLE')
        if not chat_recommendations_table_name:
            return []
            
        dynamodb = boto3.resource('dynamodb', region_name=REGION)
        chat_recommendations_table = dynamodb.Table(chat_recommendations_table_name)
        
        response = chat_recommendations_table.query(
            KeyConditionExpression=Key('user_id').eq(str(user_id)),
            ScanIndexForward=False,  # Sort by timestamp descending
            Limit=1  # Only get the most recent
        )
        
        return response.get('Items', [])
    
    except Exception as e:
        logger.error(f"Error retrieving saved recommendations: {str(e)}")
        return []

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
        logger.error(f"Error retrieving chat history: {str(e)}")
        return []