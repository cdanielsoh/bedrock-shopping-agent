"""
Hybrid Conversation Manager for Non-Agent Mode
Separates message context by handler while sharing metadata across handlers
"""

import json
import boto3
import os
from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Dict, Any, Optional
import uuid
import logging

logger = logging.getLogger(__name__)


def convert_floats_to_decimal(obj):
    """Recursively convert float values to Decimal for DynamoDB compatibility."""
    if isinstance(obj, float):
        return Decimal(str(obj))
    elif isinstance(obj, dict):
        return {key: convert_floats_to_decimal(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [convert_floats_to_decimal(item) for item in obj]
    else:
        return obj


class ConversationManager:
    """
    Manages conversations with hybrid storage approach:
    - Conversations table: metadata + recent messages per handler
    - Shared context: products, orders, user info across handlers
    """
    
    def __init__(self, dynamodb_resource, conversations_table_name: str, shared_context_table_name: str):
        self.dynamodb = dynamodb_resource
        self.conversations_table = dynamodb_resource.Table(conversations_table_name)
        self.shared_context_table = dynamodb_resource.Table(shared_context_table_name)
    
    def get_handler_conversation(self, session_id: str, handler_type: str, limit: int = 10) -> List[Dict]:
        """
        Get conversation history for a specific handler type.
        Each handler maintains its own message context.
        """
        try:
            conversation_id = f"{session_id}#{handler_type}"
            
            response = self.conversations_table.get_item(
                Key={'conversation_id': conversation_id}
            )
            
            if 'Item' not in response:
                logger.info(f"No conversation found for {conversation_id}")
                return []
            
            conversation = response['Item']
            messages = conversation.get('messages', [])
            
            # Convert to Bedrock format
            bedrock_messages = []
            for msg in messages[-limit:]:  # Get last N messages
                bedrock_messages.append({
                    "role": msg['role'],
                    "content": [{"text": msg['content']}]
                })
            
            logger.info(f"Retrieved {len(bedrock_messages)} messages for handler {handler_type}")
            return bedrock_messages
            
        except Exception as e:
            logger.error(f"Error getting handler conversation: {str(e)}")
            return []
    
    def add_message_to_handler(self, session_id: str, handler_type: str, role: str, 
                              content: str, metadata: Dict = None):
        """
        Add a message to a specific handler's conversation.
        Messages are isolated per handler type.
        """
        try:
            conversation_id = f"{session_id}#{handler_type}"
            timestamp = datetime.now(timezone.utc).isoformat()
            
            # Convert floats to Decimals in metadata
            if metadata:
                metadata = convert_floats_to_decimal(metadata)
            
            message = {
                'timestamp': timestamp,
                'role': role,
                'content': content,
                'metadata': metadata or {}
            }
            
            # Update conversation with new message
            response = self.conversations_table.update_item(
                Key={'conversation_id': conversation_id},
                UpdateExpression="""
                    SET messages = list_append(if_not_exists(messages, :empty_list), :new_message),
                        updated_at = :timestamp,
                        message_count = if_not_exists(message_count, :zero) + :one,
                        handler_type = :handler_type,
                        session_id = :session_id
                """,
                ExpressionAttributeValues={
                    ':new_message': [message],
                    ':timestamp': timestamp,
                    ':empty_list': [],
                    ':zero': 0,
                    ':one': 1,
                    ':handler_type': handler_type,
                    ':session_id': session_id
                },
                ReturnValues='ALL_NEW'
            )
            
            # Keep only last 20 messages to prevent item size issues
            updated_item = response['Attributes']
            messages = updated_item.get('messages', [])
            
            if len(messages) > 20:
                # Trim to last 15 messages to leave room for growth
                trimmed_messages = messages[-15:]
                self.conversations_table.update_item(
                    Key={'conversation_id': conversation_id},
                    UpdateExpression="SET messages = :messages",
                    ExpressionAttributeValues={':messages': trimmed_messages}
                )
                logger.info(f"Trimmed conversation {conversation_id} to 15 messages")
            
            logger.info(f"Added {role} message to handler {handler_type}")
            
        except Exception as e:
            logger.error(f"Error adding message to handler: {str(e)}")
    
    def get_shared_context(self, session_id: str) -> Dict[str, Any]:
        """
        Get shared context (products, orders, user info) that all handlers can access.
        This provides cross-handler context without message contamination.
        """
        try:
            response = self.shared_context_table.get_item(
                Key={'session_id': session_id}
            )
            
            if 'Item' not in response:
                return {
                    'products': [],
                    'orders': [],
                    'user_preferences': {},
                    'search_history': [],
                    'last_updated': None
                }
            
            context = response['Item']
            logger.info(f"Retrieved shared context for session {session_id}")
            return {
                'products': context.get('products', []),
                'orders': context.get('orders', []),
                'user_preferences': context.get('user_preferences', {}),
                'search_history': context.get('search_history', []),
                'last_updated': context.get('last_updated')
            }
            
        except Exception as e:
            logger.error(f"Error getting shared context: {str(e)}")
            return {
                'products': [],
                'orders': [],
                'user_preferences': {},
                'search_history': [],
                'last_updated': None
            }
    
    def update_shared_context(self, session_id: str, context_updates: Dict[str, Any]):
        """
        Update shared context with new products, orders, or user preferences.
        This allows handlers to share relevant context without sharing messages.
        """
        try:
            # Convert floats to Decimals for DynamoDB compatibility
            context_updates = convert_floats_to_decimal(context_updates)
            
            timestamp = datetime.now(timezone.utc).isoformat()
            ttl = int(datetime.now(timezone.utc).timestamp()) + (7 * 24 * 60 * 60)  # 7 days
            
            update_expression_parts = ["last_updated = :timestamp", "#ttl = :ttl"]
            expression_values = {
                ':timestamp': timestamp,
                ':ttl': ttl
            }
            expression_names = {
                '#ttl': 'ttl'  # Use expression attribute name for reserved keyword
            }
            
            # Handle products update
            if 'products' in context_updates:
                products = context_updates['products']
                if products:
                    # Add timestamp to each product for recency tracking
                    timestamped_products = []
                    for product in products:
                        timestamped_product = dict(product) if isinstance(product, dict) else {'product': product}
                        timestamped_product['saved_at'] = timestamp
                        timestamped_products.append(timestamped_product)
                    
                    update_expression_parts.append("products = list_append(if_not_exists(products, :empty_list_products), :new_products)")
                    expression_values[':new_products'] = timestamped_products
                    expression_values[':empty_list_products'] = []
            
            # Handle orders update
            if 'orders' in context_updates:
                orders = context_updates['orders']
                if orders:
                    # Add timestamp to each order for recency tracking
                    timestamped_orders = []
                    for order in orders:
                        timestamped_order = dict(order) if isinstance(order, dict) else {'order': order}
                        timestamped_order['saved_at'] = timestamp
                        timestamped_orders.append(timestamped_order)
                    
                    update_expression_parts.append("orders = list_append(if_not_exists(orders, :empty_list_orders), :new_orders)")
                    expression_values[':new_orders'] = timestamped_orders
                    expression_values[':empty_list_orders'] = []
            
            # Handle user preferences - Set entire map (simple approach)
            if 'user_preferences' in context_updates:
                prefs = context_updates['user_preferences']
                if prefs:
                    update_expression_parts.append("user_preferences = :user_prefs")
                    expression_values[':user_prefs'] = prefs
            
            # Handle search history
            if 'search_history' in context_updates:
                search_terms = context_updates['search_history']
                if search_terms:
                    # Ensure search_terms is a list
                    if not isinstance(search_terms, list):
                        search_terms = [search_terms]
                    
                    # Add timestamp to each search term for recency tracking
                    timestamped_searches = []
                    for search_term in search_terms:
                        timestamped_search = {
                            'query': search_term,
                            'searched_at': timestamp
                        }
                        timestamped_searches.append(timestamped_search)
                    
                    update_expression_parts.append("search_history = list_append(if_not_exists(search_history, :empty_list_search), :new_searches)")
                    expression_values[':new_searches'] = timestamped_searches
                    expression_values[':empty_list_search'] = []
            
            if len(update_expression_parts) > 2:  # More than just timestamp and ttl
                update_expression = "SET " + ", ".join(update_expression_parts)
                
                self.shared_context_table.update_item(
                    Key={'session_id': session_id},
                    UpdateExpression=update_expression,
                    ExpressionAttributeValues=expression_values,
                    ExpressionAttributeNames=expression_names
                )
                
                logger.info(f"Updated shared context for session {session_id}")
            
        except Exception as e:
            logger.error(f"Error updating shared context: {str(e)}")
    
    def get_conversation_summary(self, session_id: str) -> Dict[str, Any]:
        """
        Get a summary of all handler conversations for analytics.
        """
        try:
            # Query all conversations for this session
            response = self.conversations_table.query(
                IndexName='SessionIndex',  # Assuming we have this GSI
                KeyConditionExpression='session_id = :session_id',
                ExpressionAttributeValues={':session_id': session_id}
            )
            
            conversations = response.get('Items', [])
            
            summary = {
                'session_id': session_id,
                'total_handlers': len(conversations),
                'handlers': {},
                'total_messages': 0,
                'last_activity': None
            }
            
            for conv in conversations:
                handler_type = conv.get('handler_type', 'unknown')
                message_count = conv.get('message_count', 0)
                updated_at = conv.get('updated_at')
                
                summary['handlers'][handler_type] = {
                    'message_count': message_count,
                    'last_activity': updated_at
                }
                summary['total_messages'] += message_count
                
                if not summary['last_activity'] or (updated_at and updated_at > summary['last_activity']):
                    summary['last_activity'] = updated_at
            
            return summary
            
        except Exception as e:
            logger.error(f"Error getting conversation summary: {str(e)}")
            return {'session_id': session_id, 'error': str(e)}
    
    def get_timestamped_context_for_llm(self, session_id: str) -> str:
        """
        Get shared context formatted for LLM with timestamps for recency awareness.
        Returns a formatted string that includes when items were searched/accessed.
        """
        try:
            context = self.get_shared_context(session_id)
            current_time = datetime.now(timezone.utc).isoformat()
            
            context_parts = [f"Current time: {current_time}"]
            
            # Format products with timestamps
            if context.get('products'):
                context_parts.append("Recently viewed products:")
                for product in context['products'][-10:]:  # Last 10 products
                    saved_at = product.get('saved_at', 'unknown time')
                    if isinstance(product.get('_source'), dict):
                        product_info = product['_source']
                        product_id = product_info.get('id', 'unknown')
                        product_name = product_info.get('name', 'Unknown Product')
                        context_parts.append(f"- {product_name} (ID: {product_id}) - searched at {saved_at}")
                    else:
                        context_parts.append(f"- Product searched at {saved_at}")
            
            # Format orders with timestamps
            if context.get('orders'):
                context_parts.append("\nRecent order references:")
                for order in context['orders'][-5:]:  # Last 5 orders
                    saved_at = order.get('saved_at', 'unknown time')
                    order_id = order.get('order_id', 'unknown')
                    context_parts.append(f"- Order {order_id} - accessed at {saved_at}")
            
            # Format search history with timestamps
            if context.get('search_history'):
                context_parts.append("\nRecent search queries:")
                for search in context['search_history'][-5:]:  # Last 5 searches
                    if isinstance(search, dict):
                        query = search.get('query', 'unknown query')
                        searched_at = search.get('searched_at', 'unknown time')
                        context_parts.append(f"- '{query}' - searched at {searched_at}")
                    else:
                        # Handle old format without timestamps
                        context_parts.append(f"- '{search}' - time unknown")
            
            if len(context_parts) > 1:  # More than just current time
                context_parts.insert(1, "Previous session context:")  # Insert after current time
                return "\n".join(context_parts)
            else:
                return f"Current time: {current_time}\nNo previous context available for this session."
                
        except Exception as e:
            logger.error(f"Error formatting timestamped context: {str(e)}")
            return "Error retrieving session context."
        

def create_conversation_manager(region: str = None) -> ConversationManager:
    """Factory function to create ConversationManager with proper configuration."""
    if not region:
        region = os.environ.get('AWS_REGION', 'us-west-2')
    
    dynamodb = boto3.resource('dynamodb', region_name=region)
    conversations_table = os.environ.get('CONVERSATIONS_TABLE', 'ConversationsTable')
    shared_context_table = os.environ.get('SHARED_CONTEXT_TABLE', 'SharedContextTable')
    
    return ConversationManager(dynamodb, conversations_table, shared_context_table)
