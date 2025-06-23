"""
Refactored message handlers with hybrid conversation management.
Each handler maintains isolated message context while sharing metadata.
"""
import json
from typing import Dict, Any, List
from datetime import datetime, timezone
import logging

from resource_manager import resource_manager
from stream_parser import StreamParser
from tools import GetOrderHistoryTool, GetProductReviewsTool, KeywordProductSearchTool
from prompts import (
    ROUTER_PROMPT, ORDER_HISTORY_PROMPT, PRODUCT_SEARCH_PROMPT, 
    PRODUCT_DETAILS_PROMPT, COMPARE_PRODUCTS_PROMPT, GENERAL_INQUIRY_PROMPT,
    AGENT_ROUTER_PROMPT, PRODUCT_SEARCH_AGENT_PROMPT
)
from conversation_manager import create_conversation_manager
from performance_monitor import StreamingPerformanceMonitor, performance_monitor

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class MessageHandlerError(Exception):
    """Custom exception for message handler errors."""
    pass


class BaseMessageHandler:
    """Base class for message handlers with hybrid conversation management."""
    
    def __init__(self, connection_id: str, apigw_management, user_context: Dict[str, Any]):
        self.connection_id = connection_id
        self.apigw_management = apigw_management
        self.user_context = user_context
        self.rm = resource_manager
        
        # Extract user context
        self.user_id = user_context.get('user_id', '')
        self.session_id = user_context.get('session_id', connection_id)
        self.user_message = user_context.get('user_message', '')
        self.user_persona = user_context.get('user_persona', '')
        self.user_discount_persona = user_context.get('user_discount_persona', '')
        
        # Initialize hybrid conversation manager
        self.conversation_manager = create_conversation_manager()
        
        # Define handler type (to be overridden by subclasses)
        self.handler_type = 'base'
    
    def send_to_connection(self, data: Dict[str, Any]) -> bool:
        """Send data to WebSocket connection with error handling."""
        try:
            # Validate connection first
            if not self.rm.validate_connection(self.connection_id):
                logger.error(f"Connection {self.connection_id} is no longer valid")
                return False
            
            self.apigw_management.post_to_connection(
                ConnectionId=self.connection_id,
                Data=json.dumps(data)
            )
            
            if data.get('type') != 'text_chunk':
                logger.info(f"Sent message to connection: {data}")
            return True
            
        except Exception as e:
            logger.error(f"Error sending message to connection {self.connection_id}: {str(e)}")
            return False
    
    def send_wait_message(self, message: str):
        """Send a wait message to the client."""
        self.send_to_connection({"type": "wait", "message": message})
    
    def send_error_message(self, error: str):
        """Send an error message to the client."""
        self.send_to_connection({
            "type": "error", 
            "message": f"Sorry, I encountered an error: {error}"
        })
    
    def build_conversation_history(self, limit: int = 10):
        """
        Build conversation history using hybrid approach:
        - Handler-specific messages (isolated per handler type)
        - Shared context (products, orders, preferences)
        """
        logger.info(f"Building hybrid conversation history for user {self.user_id}, handler {self.handler_type}")
        try:
            # Get handler-specific conversation history
            handler_messages = self.conversation_manager.get_handler_conversation(
                self.session_id, self.handler_type, limit
            )
            
            # Get shared context for enrichment
            shared_context = self.conversation_manager.get_shared_context(self.session_id)
            
            # Add current user message
            handler_messages.append({
                "role": "user",
                "content": [{"text": self.user_message}]
            })
            
            # Log context information
            logger.info(f"Handler {self.handler_type}: {len(handler_messages)} messages")
            logger.info(f"Shared context: {len(shared_context.get('products', []))} products, "
                       f"{len(shared_context.get('orders', []))} orders")
            
            # Store shared context for use in prompts
            self.shared_context = shared_context
            
            return handler_messages
            
        except Exception as e:
            logger.error(f"Error building hybrid conversation history: {str(e)}")
            return [{"role": "user", "content": [{"text": self.user_message}]}]
    
    def save_message_to_handler(self, role: str, content: str, metadata: Dict = None):
        """Save message to handler-specific conversation."""
        try:
            self.conversation_manager.add_message_to_handler(
                self.session_id, self.handler_type, role, content, metadata
            )
            logger.info(f"Saved {role} message to handler {self.handler_type}")
        except Exception as e:
            logger.error(f"Error saving message to handler: {str(e)}")
    
    def update_shared_context(self, context_updates: Dict[str, Any]):
        """Update shared context with new products, orders, or preferences."""
        try:
            self.conversation_manager.update_shared_context(self.session_id, context_updates)
            logger.info(f"Updated shared context: {list(context_updates.keys())}")
        except Exception as e:
            logger.error(f"Error updating shared context: {str(e)}")
    
    def get_context_for_prompt(self) -> str:
        """
        Get shared context formatted for inclusion in prompts with timestamps.
        This allows handlers to be aware of cross-handler context without message contamination.
        """
        try:
            # Use the new timestamped context method
            timestamped_context = self.conversation_manager.get_timestamped_context_for_llm(self.session_id)
            return f"\n\n{timestamped_context}" if timestamped_context and timestamped_context != "No previous context available for this session." else ""
        except Exception as e:
            logger.error(f"Error getting timestamped context: {str(e)}")
            # Fallback to old method if there's an error
            if not hasattr(self, 'shared_context'):
                return ""
            
            context_parts = []
            
            # Add recent products context
            products = self.shared_context.get('products', [])
            if products:
                recent_products = products[-5:]  # Last 5 products
                product_info = []
                for product in recent_products:
                    if isinstance(product, dict) and 'id' in product:
                        product_info.append(f"- {product.get('name', 'Unknown')} (ID: {product['id']})")
                
                if product_info:
                    context_parts.append(f"Recent products discussed:\n" + "\n".join(product_info))
            
            # Add recent orders context
            orders = self.shared_context.get('orders', [])
            if orders:
                recent_orders = orders[-3:]  # Last 3 orders
                order_info = []
                for order in recent_orders:
                    if isinstance(order, dict) and 'order_id' in order:
                        order_info.append(f"- Order {order['order_id']} ({order.get('status', 'unknown status')})")
                
                if order_info:
                    context_parts.append(f"Recent orders discussed:\n" + "\n".join(order_info))
            
            return "\n\n".join(context_parts) if context_parts else ""
    
    def get_timestamp(self) -> str:
        """Get current timestamp in ISO format."""
        return datetime.now(timezone.utc).isoformat()
    
    def _add_cache_control_to_messages(self, messages: List[Dict]) -> List[Dict]:
        """
        Add cache control to messages for prompt caching optimization.
        Removes existing cache points and adds them only to the last 2 user messages.
        """
        if not messages:
            return messages
        
        # Make a deep copy to avoid modifying original messages
        import copy
        cached_messages = copy.deepcopy(messages)
        
        # First pass: Remove all existing cache points from all messages
        for message in cached_messages:
            if isinstance(message.get('content'), list):
                # Remove any existing cache point blocks
                message['content'] = [
                    block for block in message['content'] 
                    if not (isinstance(block, dict) and 'cachePoint' in block)
                ]
        
        # Second pass: Add cache points only to the last 2 user messages
        user_message_indices = []
        for i, message in enumerate(cached_messages):
            if message.get('role') == 'user':
                user_message_indices.append(i)
        
        # Get the last 2 user message indices
        cache_indices = user_message_indices[-2:] if len(user_message_indices) >= 2 else user_message_indices
        
        for i, message in enumerate(cached_messages):
            # Add cache control to the last 2 user messages only
            if i in cache_indices:
                if isinstance(message.get('content'), list):
                    # Add cachePoint to existing content list
                    message['content'].append({'cachePoint': {'type': 'default'}})
                elif isinstance(message.get('content'), str):
                    # Convert string content to list format with cache control
                    message['content'] = [
                        {'text': message['content']},
                        {'cachePoint': {'type': 'default'}}
                    ]
        
        cache_point_count = sum(1 for i in cache_indices)
        logger.info(f"Cleaned and added cache control to messages: {len(cached_messages)} total, "
                   f"{cache_point_count} cache points on last {cache_point_count} user messages at indices: {cache_indices}")
        return cached_messages


class RouterHandler(BaseMessageHandler):
    """Handles message routing logic."""
    
    def route_message(self, use_agent: bool = False) -> str:
        """Route message to appropriate handler."""
        logger.info(f"Routing message to appropriate handler for user {self.user_id}")
        
        try:
            system_prompt = AGENT_ROUTER_PROMPT if use_agent else ROUTER_PROMPT
            messages = [{
                "role": "user",
                "content": [{
                    "text": f"If the user's message is {self.user_message}, what assistant should I route it to? Respond with only the assistant number (1, 2, 3, 4, or 5) that should handle the user's message. Do not include explanations or additional text."
                }]
            }]
            
            response = self.rm.bedrock_client.converse(
                modelId="us.anthropic.claude-3-5-haiku-20241022-v1:0",
                messages=messages,
                system=[{"text": system_prompt}, {"cachePoint": {"type": "default"}}],
            )
            
            routing_result = response["output"]["message"]["content"][0]["text"]
            logger.info(f"Router decision: {routing_result} for message: '{self.user_message[:50]}...'")
            
            return routing_result
            
        except Exception as e:
            logger.error(f"Error in routing: {str(e)}")
            return "3" if use_agent else "4"


class OrderHistoryHandler(BaseMessageHandler):
    """Handles order history requests with isolated message context."""
    
    def __init__(self, connection_id: str, apigw_management, user_context: Dict[str, Any]):
        super().__init__(connection_id, apigw_management, user_context)
        self.handler_type = 'order_history'
    
    def handle(self):
        """Process order history request."""
        logger.info(f"Processing order history request for user {self.user_id}")
        
        # Start performance monitoring
        with StreamingPerformanceMonitor(
            self.session_id, self.user_id, self.handler_type, 
            "us.anthropic.claude-3-5-haiku-20241022-v1:0", False
        ) as perf_monitor:
            try:
                self.send_wait_message("Getting order history...")
                
                # Save user message to handler-specific conversation
                self.save_message_to_handler('user', self.user_message)
                
                # Get order history
                order_tool = GetOrderHistoryTool(
                    orders_table=self.rm.orders_table_name,
                    oss_client=self.rm.opensearch_client,
                    index=self.rm.os_index
                )
                order_history = order_tool.execute(self.user_id)
                
                # Update shared context with orders (for other handlers to reference)
                if order_history:
                    order_context = []
                    for order in order_history:
                        order_context.append({
                            'order_id': order.get('order_id'),
                            'status': order.get('delivery_status'),
                            'timestamp': order.get('timestamp')
                        })
                    
                    self.update_shared_context({'orders': order_context})
                
                # Build handler-specific conversation with shared context
                messages = self.build_conversation_history()
                
                # Add shared context to prompt
                context_info = self.get_context_for_prompt()
                enhanced_prompt = ORDER_HISTORY_PROMPT.format(order_history=order_history)
                if context_info:
                    enhanced_prompt += f"\n\nAdditional Context:\n{context_info}"
                
                stream_parser = StreamParser(
                    self.apigw_management, 
                    self.connection_id, 
                    orders_list=order_history
                )
                
                response = self.rm.bedrock_client.converse_stream(
                    modelId="us.anthropic.claude-3-5-haiku-20241022-v1:0",
                    messages=self._add_cache_control_to_messages(messages),
                    system=[{"text": enhanced_prompt}, {"cachePoint": {"type": "default"}}],
                )
                
                for event in response['stream']:
                    if 'contentBlockDelta' in event and 'delta' in event['contentBlockDelta']:
                        delta = event['contentBlockDelta']['delta']
                        if 'text' in delta:
                            text_chunk = delta['text']
                            # Record first token for performance monitoring
                            perf_monitor.record_streaming_token(text_chunk)
                            stream_parser.parse_chunk(text_chunk)
                    elif 'metadata' in event:
                        # Update token usage from metadata
                        if 'usage' in event['metadata']:
                            perf_monitor.update_token_usage(event['metadata']['usage'])
                
                stream_parser.finalize()
                
                # Save response to handler-specific conversation
                if stream_parser.complete_response:
                    metadata = {
                        'response_type': 'order_history',
                        'total_orders': len(order_history),
                        'order_ids': [order.get('order_id') for order in order_history]
                    }
                    self.save_message_to_handler('assistant', stream_parser.complete_response, metadata)
                    
            except Exception as e:
                logger.error(f"Error handling order history: {str(e)}")
                self.send_error_message("retrieving your order history")


class ProductSearchHandler(BaseMessageHandler):
    """Handles product search requests with isolated message context."""
    
    def __init__(self, connection_id: str, apigw_management, user_context: Dict[str, Any]):
        super().__init__(connection_id, apigw_management, user_context)
        self.handler_type = 'product_search'
    
    def handle(self):
        """Process product search request."""
        logger.info(f"Processing product search request for user {self.user_id}")
        
        with StreamingPerformanceMonitor(
            self.session_id, self.user_id, self.handler_type, 
            "us.anthropic.claude-3-5-haiku-20241022-v1:0", False
        ) as perf_monitor:
            try:
                self.send_wait_message("Searching for products...")
                
                # Save user message to handler-specific conversation
                self.save_message_to_handler('user', self.user_message)
                
                # Initialize product search tool
                product_search_tool = KeywordProductSearchTool(
                    os_host=self.rm.os_host,
                    index=self.rm.os_index,
                    cloudfront_url=self.rm.images_cloudfront_url,
                    dynamodb=self.rm.dynamodb_resource,
                    reviews_table=self.rm.reviews_table_name
                )
                
                messages = self.build_conversation_history()
                tool_config = {"tools": [product_search_tool.get_tool_spec()]}
                
                # Add shared context to prompt
                context_info = self.get_context_for_prompt()
                enhanced_prompt = PRODUCT_SEARCH_PROMPT.format(
                    user_id=self.user_id,
                    user_persona=self.user_persona,
                    user_discount_persona=self.user_discount_persona
                )
                if context_info:
                    enhanced_prompt += f"\n\nAdditional Context:\n{context_info}"
                
                response = self.rm.bedrock_client.converse(
                    modelId="us.anthropic.claude-3-5-haiku-20241022-v1:0",
                    messages=messages,
                    system=[{"text": enhanced_prompt}, {"cachePoint": {"type": "default"}}],
                    toolConfig=tool_config
                )
                
                # Handle tool execution and streaming
                self._handle_tool_response(response, messages, product_search_tool, tool_config, perf_monitor)
            
            except Exception as e:
                logger.error(f"Error handling product search: {str(e)}")
                self.send_error_message("searching for products")
    
    def _handle_tool_response(self, response, messages, tool, tool_config, perf_monitor=None):
        """Handle tool execution and streaming response."""
        if not response["output"]["message"].get("content"):
            return
        
        for content_block in response["output"]["message"]["content"]:
            if not content_block.get("toolUse"):
                continue
            
            tool_use = content_block["toolUse"]
            if tool_use["name"] != tool.get_tool_name():
                continue
            
            # Execute tool
            tool_input = tool_use["input"]
            search_results = tool.execute(tool_input["query_keywords"])
            
            # Update shared context with products (for other handlers to reference)
            if search_results:
                # Update search history and products
                self.update_shared_context({
                    'products': search_results,
                    'search_history': tool_input["query_keywords"]
                })
            
            # Build tool result message
            messages.append(response["output"]["message"])
            tool_result_message = {
                "role": "user",
                "content": [{
                    "toolResult": {
                        "toolUseId": tool_use["toolUseId"],
                        "content": [{"json": {"results": search_results}}]
                    }
                }]
            }
            messages.append(tool_result_message)
            
            # Save tool result to handler-specific conversation
            self.save_message_to_handler('user', 
                f"Tool result for search: {tool_input['query_keywords']}", 
                {
                    'message_type': 'tool_result',
                    'tool_name': 'keyword_product_search',
                    'tool_input': tool_input,
                    'tool_results': search_results,
                    'response_type': 'product_search_tool_result'
                })
            
            # Stream final response
            stream_parser = StreamParser(
                self.apigw_management, 
                self.connection_id, 
                search_results=search_results
            )
            
            # Add shared context to final prompt
            context_info = self.get_context_for_prompt()
            enhanced_prompt = PRODUCT_SEARCH_PROMPT.format(
                user_id=self.user_id,
                user_persona=self.user_persona,
                user_discount_persona=self.user_discount_persona
            )
            if context_info:
                enhanced_prompt += f"\n\nAdditional Context:\n{context_info}"
            
            final_response = self.rm.bedrock_client.converse_stream(
                modelId="us.anthropic.claude-3-5-haiku-20241022-v1:0",
                messages=self._add_cache_control_to_messages(messages),
                system=[{"text": enhanced_prompt}, {"cachePoint": {"type": "default"}}],
                toolConfig=tool_config
            )
            
            for event in final_response['stream']:
                if 'contentBlockDelta' in event and 'delta' in event['contentBlockDelta']:
                    delta = event['contentBlockDelta']['delta']
                    if 'text' in delta:
                        text_chunk = delta['text']
                        # Record first token for performance monitoring
                        perf_monitor.record_streaming_token(text_chunk)
                        stream_parser.parse_chunk(text_chunk)
                elif 'metadata' in event:
                    # Update token usage from metadata
                    if 'usage' in event['metadata']:
                        perf_monitor.update_token_usage(event['metadata']['usage'])
            
            stream_parser.finalize()
            
            # Save complete response to handler-specific conversation
            if stream_parser.complete_response:
                metadata = {
                    'response_type': 'product_search',
                    'search_keywords': tool_input["query_keywords"],
                    'products_found': len(search_results),
                    'product_ids': [hit['_source']['id'] for hit in search_results]
                }
                self.save_message_to_handler('assistant', stream_parser.complete_response, metadata)


class GeneralInquiryHandler(BaseMessageHandler):
    """Handles general inquiry requests with isolated message context."""
    
    def __init__(self, connection_id: str, apigw_management, user_context: Dict[str, Any]):
        super().__init__(connection_id, apigw_management, user_context)
        self.handler_type = 'general_inquiry'
    
    def handle(self):
        """Process general inquiry request."""
        logger.info(f"Processing general inquiry request for user {self.user_id}")
        
        with StreamingPerformanceMonitor(
            self.session_id, self.user_id, self.handler_type, 
            "us.anthropic.claude-3-5-haiku-20241022-v1:0", False
        ) as perf_monitor:
            try:
                # Save user message to handler-specific conversation
                self.save_message_to_handler('user', self.user_message)
            
                messages = self.build_conversation_history()
                stream_parser = StreamParser(self.apigw_management, self.connection_id)
                
                # Add shared context to prompt
                context_info = self.get_context_for_prompt()
                enhanced_prompt = GENERAL_INQUIRY_PROMPT
                if context_info:
                    enhanced_prompt += f"\n\nAdditional Context (for reference only):\n{context_info}"
                
                response = self.rm.bedrock_client.converse_stream(
                    modelId="us.anthropic.claude-3-5-haiku-20241022-v1:0",
                    messages=self._add_cache_control_to_messages(messages),
                    system=[{"text": enhanced_prompt}, {"cachePoint": {"type": "default"}}],
                )
                
                for event in response['stream']:
                    if 'contentBlockDelta' in event and 'delta' in event['contentBlockDelta']:
                        delta = event['contentBlockDelta']['delta']
                        if 'text' in delta:
                            text_chunk = delta['text']
                            # Record first token for performance monitoring
                            perf_monitor.record_streaming_token(text_chunk)
                            stream_parser.parse_chunk(text_chunk)
                    elif 'metadata' in event:
                        # Update token usage from metadata
                        if 'usage' in event['metadata']:
                            perf_monitor.update_token_usage(event['metadata']['usage'])
                
                stream_parser.finalize()
                
                if stream_parser.complete_response:
                    self.save_message_to_handler('assistant', stream_parser.complete_response, {
                        'response_type': 'general_inquiry'
                    })
                
            except Exception as e:
                logger.error(f"Error handling general inquiry: {str(e)}")
                self.send_error_message("processing your request")


class ProductDetailsHandler(BaseMessageHandler):
    """Handles product details requests with shared product context."""
    
    def __init__(self, connection_id: str, apigw_management, user_context: Dict[str, Any]):
        super().__init__(connection_id, apigw_management, user_context)
        self.handler_type = 'product_details'
    
    def handle(self):
        """Process product details request."""
        logger.info(f"Processing product details request for user {self.user_id}")
        
        with StreamingPerformanceMonitor(
            self.session_id, self.user_id, self.handler_type, 
            "us.anthropic.claude-3-5-haiku-20241022-v1:0", False
        ) as perf_monitor:
            try:
                # Save user message to handler-specific conversation
                self.save_message_to_handler('user', self.user_message)
                
                messages = self.build_conversation_history()
                stream_parser = StreamParser(self.apigw_management, self.connection_id)
                
                # Get shared context for product information
                shared_context = self.conversation_manager.get_shared_context(self.session_id)
                product_ids = []
                
                # Extract product IDs from shared context
                for product in shared_context.get('products', []):
                    if isinstance(product, dict) and 'id' in product:
                        product_ids.append(product['id'])
                
                logger.info(f"Found {len(product_ids)} product IDs in shared context")
                
                # Get product reviews for shared products
                product_reviews = {}
                if product_ids:
                    product_reviews = GetProductReviewsTool(
                        dynamodb=self.rm.dynamodb_resource,
                        reviews_table=self.rm.reviews_table_name
                    ).execute(product_ids[:10])  # Limit to 10 products
                    logger.info(f"Retrieved reviews for {len(product_reviews)} products")
                
                # Add shared context to prompt
                context_info = self.get_context_for_prompt()
                enhanced_prompt = PRODUCT_DETAILS_PROMPT.format(
                    user_persona=self.user_persona,
                    user_discount_persona=self.user_discount_persona,
                    product_reviews=product_reviews
                )
                if context_info:
                    enhanced_prompt += f"\n\nShared Context:\n{context_info}"

                response = self.rm.bedrock_client.converse_stream(
                    modelId="us.anthropic.claude-3-5-haiku-20241022-v1:0",
                    messages=self._add_cache_control_to_messages(messages),
                    system=[{"text": enhanced_prompt}, {"cachePoint": {"type": "default"}}],
                )

                for event in response['stream']:
                    if 'contentBlockDelta' in event and 'delta' in event['contentBlockDelta']:
                        delta = event['contentBlockDelta']['delta']
                        if 'text' in delta:
                            text_chunk = delta['text']
                            # Record first token for performance monitoring
                            perf_monitor.record_streaming_token(text_chunk)
                            stream_parser.parse_chunk(text_chunk)
                    elif 'metadata' in event:
                        # Update token usage from metadata
                        if 'usage' in event['metadata']:
                            perf_monitor.update_token_usage(event['metadata']['usage'])
                
                stream_parser.finalize()
                
                if stream_parser.complete_response:
                    self.save_message_to_handler('assistant', stream_parser.complete_response, {
                        'response_type': 'product_details',
                        'referenced_products': product_ids[:5]  # Track which products were referenced
                    })
                    
            except Exception as e:
                logger.error(f"Error handling product details: {str(e)}")
                self.send_error_message("processing your request")


class CompareProductsHandler(BaseMessageHandler):
    """Handles product comparison requests."""
    
    def handle(self):
        """Process product comparison request."""
        logger.info(f"Processing product comparison request for user {self.user_id}")
        try:
            messages = self.build_conversation_history()
            
            # Initialize product search tool for comparisons
            keyword_product_search_tool = KeywordProductSearchTool(
                os_host=self.rm.os_host,
                index=self.rm.os_index,
                cloudfront_url=self.rm.images_cloudfront_url,
                dynamodb=self.rm.dynamodb_resource,
                reviews_table=self.rm.reviews_table_name
            )
            
            tool_config = {
                "tools": [keyword_product_search_tool.get_tool_spec()]
            }
            
            # Global variable to store search results for the stream parser
            current_search_results = None
            
            def handle_streaming_with_tools(messages, is_continuation=False):
                """Handle streaming response with tool call detection and execution"""
                response = self.rm.bedrock_client.converse_stream(
                    modelId="us.anthropic.claude-3-5-haiku-20241022-v1:0",
                    messages=self._add_cache_control_to_messages(messages),
                    system=[{"text": COMPARE_PRODUCTS_PROMPT}, {"cachePoint": {"type": "default"}}],
                    toolConfig=tool_config
                )
                
                tool_calls = []
                current_tool_call = None
                
                # Create StreamParser instance outside the loop for non-tool responses
                # Pass current_search_results if available for product parsing
                stream_parser = StreamParser(self.apigw_management, self.connection_id, search_results=current_search_results)
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
                                self.send_wait_message("Searching for products to compare...")
                    
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
                            logger.info(f"Tool input delta: {delta['toolUse']}")
                            
                            if 'input' in delta['toolUse']:
                                input_chunk = delta['toolUse']['input']
                                
                                # Accumulate the input chunks in the buffer
                                current_tool_call['input_buffer'] += str(input_chunk)
                                logger.info(f"Accumulated input buffer: {current_tool_call['input_buffer']}")
                    
                    elif 'contentBlockStop' in event:
                        # Tool call completed, parse the accumulated JSON and execute
                        if tool_calls and current_tool_call:
                            try:
                                # Parse the complete JSON string
                                if current_tool_call['input_buffer']:
                                    parsed_input = json.loads(current_tool_call['input_buffer'])
                                    current_tool_call['input'] = parsed_input
                                    logger.info(f"Successfully parsed tool input: {parsed_input}")
                                
                                return execute_tools_and_continue(tool_calls, messages)
                            
                            except json.JSONDecodeError as e:
                                logger.error(f"Failed to parse tool input JSON: {e}")
                                logger.error(f"Raw input buffer: {current_tool_call['input_buffer']}")
                                
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
                                                logger.info(f"Extracted keywords via fallback: {keywords}")
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
                        
                        # Save tool result to handler conversation
                        self.save_message_to_handler('user', 
                                            f"Tool result for comparison search: {tool_input['query_keywords']}", 
                                            {
                                                'message_type': 'tool_result',
                                                'tool_name': 'keyword_product_search',
                                                'tool_input': tool_input,
                                                'tool_results': search_results,
                                                'response_type': 'product_comparison_tool_result',
                                                'connection_id': self.connection_id
                                            })
                
                # Add tool results message
                messages.append({
                    "role": "user",
                    "content": tool_results
                })
                
                # Initialize StreamParser with search results for the continuation
                stream_parser = StreamParser(
                    self.apigw_management, 
                    self.connection_id, 
                    search_results=current_search_results
                )
                
                # Continue with streaming after tool execution
                continuation_response = self.rm.bedrock_client.converse_stream(
                    modelId="us.anthropic.claude-3-5-haiku-20241022-v1:0",
                    messages=self._add_cache_control_to_messages(messages),
                    system=[{"text": COMPARE_PRODUCTS_PROMPT}, {"cachePoint": {"type": "default"}}],
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
                        'product_ids': [hit['_source']['id'] for hit in current_search_results],
                        'connection_id': self.connection_id
                    })
                
                self.save_message_to_handler('assistant', complete_response, metadata)
        
        except Exception as e:
            logger.error(f"Error handling product comparison: {str(e)}")
            self.send_error_message("processing your request")