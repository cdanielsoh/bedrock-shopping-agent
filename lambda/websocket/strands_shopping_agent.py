"""
Strands Customer Agent implementation with configurable tools and prompts.
"""
import asyncio
import json
import time
from typing import Dict, Any, Optional, List
from strands_agent_factory import agent_factory, AgentType
from agent_conversation_manager import AgentConversationManager
from stream_parser import StreamParser
from resource_manager import resource_manager
from performance_monitor import PerformanceMonitor
import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

class StrandsShoppingAgent:
    """
    Main Strands customer agent with support for different agent types,
    custom tools, and conversation management.
    """
    
    def __init__(self, connection_id: str, apigw_management, user_context: Dict[str, Any], request_start_time: float = None):
        self.connection_id = connection_id
        self.apigw_management = apigw_management
        self.user_context = user_context
        self.request_start_time = request_start_time
        self.rm = resource_manager
        self.order_history = agent_factory._prefetch_order_history(self.user_context['user_id'])
        
        # Initialize conversation manager
        self.conversation_manager = AgentConversationManager(
            dynamodb_table_name=self.rm.agent_conversations_table_name,
            event_loop_metrics_table_name=self.rm.agent_event_loop_metrics_table_name
        )
        
        # Performance monitoring
        self.perf_monitor = PerformanceMonitor()
    
    async def handle_request(self, 
                           agent_type: str = AgentType.PRODUCT_SEARCH,
                           tools_path: Optional[str] = None) -> None:
        """
        Handle user request with specified agent configuration.
        
        Args:
            agent_type: Type of agent to use
            tools_path: Path to custom tools file
        """
        # Use StreamingPerformanceMonitor for agent case to capture streaming tokens
        from performance_monitor import StreamingPerformanceMonitor
        
        session_id = self.user_context.get('session_id', self.connection_id)
        user_id = self.user_context.get('user_id', 'unknown')
        
        with StreamingPerformanceMonitor(
            session_id, user_id, 'agent_handler', 
            "us.anthropic.claude-3-5-haiku-20241022-v1:0", True,  # use_agent=True
            self.request_start_time
        ) as perf_monitor:
            try:
                with self.perf_monitor.measure_operation("agent_initialization"):
                    # Create agent
                    agent = agent_factory.create_agent(
                        agent_type=agent_type,
                        user_context=self.user_context,
                        tools_path=tools_path
                    )
                    
                    # Load existing conversation
                    existing_messages = self.conversation_manager.load_agent_messages(session_id)
                    
                    if existing_messages:
                        agent.messages = self._add_cache_control_to_agent_messages(existing_messages)
                        print(f"Loaded {len(existing_messages)} messages for session {session_id} with cache control")
                
                # Send initial status
                self._send_status_message(f"AI agent ({agent_type}) is processing your request...")
                
                # Stream response with performance monitoring
                with self.perf_monitor.measure_operation("agent_streaming"):
                    await self._stream_agent_response(agent, session_id, perf_monitor)
                
                # Log performance (local operations only, not DynamoDB)
                self.perf_monitor.log_summary(self.connection_id)
                
            except Exception as e:
                print(f"Error in agent request handling: {str(e)}")
                self._send_error_message(f"Agent processing failed: {str(e)}")
    
    async def _stream_agent_response(self, agent, session_id: str, perf_monitor=None) -> None:
        """Stream agent response with proper error handling and performance monitoring."""
        try:
            # Initialize stream parser
            stream_parser = StreamParser(
                self.apigw_management, 
                self.connection_id,
                orders_list=self.order_history
            )
            
            complete_response = ""
            tool_results = []
            
            # Stream the agent response
            # Initialize custom metrics accumulator
            custom_metrics = {
                'cycle_count': 0,
                'cycle_durations': [],
                'total_duration': 0.0,
                'accumulated_usage': {
                    'inputTokens': 0,
                    'outputTokens': 0,
                    'totalTokens': 0,
                    'cacheReadInputTokens': 0,
                    'cacheWriteInputTokens': 0
                },
                'accumulated_metrics': {
                    'latencyMs': 0
                },
                'tool_metrics': [],
                'tool_metrics_count': 0
            }
            
            cycle_start_time = time.time()
            
            async for event in agent.stream_async(prompt=self.user_context['user_message']):
                if "data" in event:
                    text_chunk = event["data"]
                    complete_response += text_chunk
                    stream_parser.parse_chunk(text_chunk)
                    
                    # Record streaming token for performance monitoring
                    if perf_monitor:
                        perf_monitor.record_streaming_token(text_chunk)
                
                elif "message" in event:
                    # Handle tool execution results
                    message_content = event.get("message", {}).get("content", [])
                    for content in message_content:
                        if "toolResult" in content:
                            # Extract and process tool results
                            tool_result = self._extract_tool_results(content)
                            if tool_result:
                                tool_results.extend(tool_result)
                                # Update stream parser with results
                                self._update_stream_parser_with_results(stream_parser, tool_result)
                        
                        elif "toolUse" in content:
                            tool_use = content["toolUse"]
                            stream_parser.flush()
                            logger.info(f"Tool executed: {tool_use.get('name')} with input: {tool_use.get('input')}")
                
                elif "event" in event:
                    # Log the full event for debugging
                    logger.info(f"Agent event: {event}")
                    
                    # Handle contentBlockStart events (tool use detection)
                    if "contentBlockStart" in event["event"]:
                        content_block = event["event"]["contentBlockStart"]
                        if "start" in content_block and "toolUse" in content_block["start"]:
                            tool_use = content_block["start"]["toolUse"]
                            custom_metrics['tool_metrics'].append({
                                'toolUseId': tool_use.get('toolUseId'),
                                'name': tool_use.get('name'),
                                'timestamp': time.time()
                            })
                            custom_metrics['tool_metrics_count'] += 1
                            logger.info(f"Tool use detected: {tool_use.get('name')} (ID: {tool_use.get('toolUseId')})")
                    
                    # Handle metadata events (usage and metrics)
                    elif "metadata" in event["event"]:
                        metadata = event["event"]["metadata"]
                        
                        # Accumulate usage metrics
                        if "usage" in metadata:
                            usage = metadata["usage"]
                            custom_metrics['accumulated_usage']['inputTokens'] += usage.get('inputTokens', 0)
                            custom_metrics['accumulated_usage']['outputTokens'] += usage.get('outputTokens', 0)
                            custom_metrics['accumulated_usage']['totalTokens'] = usage.get('totalTokens', 0)  # Use latest total
                            custom_metrics['accumulated_usage']['cacheReadInputTokens'] += usage.get('cacheReadInputTokens', 0)
                            custom_metrics['accumulated_usage']['cacheWriteInputTokens'] += usage.get('cacheWriteInputTokens', 0)
                            
                            # Update performance monitor
                            if perf_monitor:
                                perf_monitor.update_token_usage(usage)
                        
                        # Accumulate latency metrics
                        if "metrics" in metadata:
                            metrics = metadata["metrics"]
                            latency = metrics.get('latencyMs', 0)
                            custom_metrics['accumulated_metrics']['latencyMs'] += latency
                            
                            # Record cycle completion
                            cycle_duration = time.time() - cycle_start_time
                            custom_metrics['cycle_durations'].append(cycle_duration)
                            custom_metrics['cycle_count'] += 1
                            custom_metrics['total_duration'] += cycle_duration
                            
                            # Reset cycle timer
                            cycle_start_time = time.time()
                            
                            logger.info(f"Cycle {custom_metrics['cycle_count']} completed: {latency}ms latency, {cycle_duration:.3f}s duration")
            
            # Finalize streaming
            stream_parser.finalize()
            
            # Save conversation state
            with self.perf_monitor.measure_operation("conversation_save"):
                self.conversation_manager.save_agent_messages(
                    session_id, 
                    self.user_context['user_id'], 
                    agent.messages
                )
                self.conversation_manager.save_agent_event_loop_metrics(
                    session_id, 
                    self.user_context['user_id'], 
                    custom_metrics
                )
            
            logger.info(f"Agent streaming completed. Response: {len(complete_response)} chars, "
                  f"Tools used: {len(tool_results)}, Messages: {len(agent.messages)}")
            
        except Exception as e:
            logger.error(f"Error in agent streaming: {str(e)}")
            self._send_error_message("processing your request with the AI agent")
    
    def _extract_tool_results(self, content: Dict[str, Any]) -> List[Dict]:
        """Extract tool results from agent message content."""
        try:
            tool_result = content.get("toolResult", {})
            tool_content = tool_result.get("content", [])
            
            results = []
            for item in tool_content:
                if "text" in item:
                    # Try to parse as JSON/list
                    try:
                        import ast
                        parsed_result = ast.literal_eval(item["text"])
                        if isinstance(parsed_result, list):
                            results.extend(parsed_result)
                        else:
                            results.append(parsed_result)
                    except:
                        # If parsing fails, treat as raw text
                        results.append({"content": item["text"]})
                
                elif "json" in item:
                    json_data = item["json"]
                    if "results" in json_data:
                        results.extend(json_data["results"])
                    else:
                        results.append(json_data)
            
            return results
            
        except Exception as e:
            logger.error(f"Error extracting tool results: {e}")
            return []
    
    def _update_stream_parser_with_results(self, stream_parser: StreamParser, results: List[Dict]):
        """Update stream parser with tool results for structured output."""
        try:
            # Check if results are products (have _source.id structure)
            if results and isinstance(results[0], dict) and '_source' in results[0]:
                stream_parser.search_results.extend(results)
                logger.info(f"Updated stream parser with {len(results)} product results")
            
            # Check if results are orders (have order_id)
            elif results and isinstance(results[0], dict) and 'order_id' in results[0]:
                stream_parser.orders_list.extend(results)
                logger.info(f"Updated stream parser with {len(results)} order results")
            
        except Exception as e:
            logger.error(f"Error updating stream parser: {e}")
    
    def _send_status_message(self, message: str):
        """Send status message to client."""
        self._send_to_connection({"type": "wait", "message": message})
    
    def _send_error_message(self, error_context: str):
        """Send error message to client."""
        self._send_to_connection({
            "type": "error",
            "message": f"Sorry, I encountered an error while {error_context}. Please try again."
        })
    
    def _send_to_connection(self, data: Dict[str, Any]):
        """Send data to WebSocket connection."""
        try:
            self.apigw_management.post_to_connection(
                ConnectionId=self.connection_id,
                Data=json.dumps(data)
            )
        except Exception as e:
            logger.error(f"Error sending to connection {self.connection_id}: {e}")
    
    def _save_response_to_history(self, response: str, tool_results: List[Dict]):
        """Save response to chat history for compatibility."""
        try:
            if not self.rm.chat_history_table:
                return
            
            from datetime import datetime, timezone
            import uuid
            from decimal import Decimal
            
            now = datetime.now(timezone.utc)
            ttl = int(now.timestamp()) + (30 * 24 * 60 * 60)  # 30 days
            
            # Determine response type based on tool results
            response_type = "strands_agent_response"
            metadata = {
                'response_type': response_type,
                'agent_type': 'strands_customer_agent',
                'tools_used': len(tool_results) > 0,
                'connection_id': self.connection_id
            }
            
            # Add specific metadata based on tool results
            if tool_results:
                # Check for products
                product_results = [r for r in tool_results if isinstance(r, dict) and '_source' in r]
                if product_results:
                    metadata.update({
                        'products_found': len(product_results),
                        'product_ids': [p['_source']['id'] for p in product_results if '_source' in p and 'id' in p['_source']]
                    })
                
                # Check for orders
                order_results = [r for r in tool_results if isinstance(r, dict) and 'order_id' in r]
                if order_results:
                    metadata.update({
                        'orders_found': len(order_results),
                        'order_ids': [o['order_id'] for o in order_results]
                    })
            
            # Convert floats to Decimal for DynamoDB
            def convert_floats_to_decimal(obj):
                if isinstance(obj, float):
                    return Decimal(str(obj))
                elif isinstance(obj, dict):
                    return {key: convert_floats_to_decimal(value) for key, value in obj.items()}
                elif isinstance(obj, list):
                    return [convert_floats_to_decimal(item) for item in obj]
                else:
                    return obj
            
            item = {
                'user_id': str(self.user_context['user_id']),
                'timestamp': now.isoformat(),
                'connection_id': self.connection_id,
                'session_id': self.user_context.get('session_id', self.connection_id),
                'message_id': str(uuid.uuid4()),
                'message_type': 'assistant',
                'content': response,
                'metadata': convert_floats_to_decimal(metadata),
                'ttl': ttl
            }
            
            self.rm.chat_history_table.put_item(Item=item)
            logger.info(f"Saved agent response to chat history")
            
        except Exception as e:
            logger.error(f"Error saving to chat history: {e}")
    
    def _add_cache_control_to_agent_messages(self, messages: List[Dict]) -> List[Dict]:
        """
        Add cache control to agent messages for prompt caching optimization.
        Cache older messages and leave recent ones uncached for efficiency.
        """
        if not messages:
            return messages
        
        # Make a deep copy to avoid modifying original messages
        import copy
        cached_messages = copy.deepcopy(messages)
        
        # Strategy: Cache all but the last 2 messages (recent conversation)
        # This balances cache efficiency with conversation freshness
        cache_cutoff = max(0, len(cached_messages) - 2)
        
        for i, message in enumerate(cached_messages):
            # Add cache control to the last message to be cached
            if i == cache_cutoff - 1 and cache_cutoff > 0:
                # Mark the last message to be cached as a cache breakpoint
                if isinstance(message.get('content'), list):
                    # Find the last content block and add cache control
                    for content_block in reversed(message['content']):
                        if isinstance(content_block, dict) and 'text' in content_block:
                            # Add cachePoint as a separate content block after the text
                            break
                    # Add the cachePoint as a separate content block
                    message['content'].append({'cachePoint': {'type': 'default'}})
                elif isinstance(message.get('content'), str):
                    # Convert string content to list format with cache control
                    message['content'] = [
                        {'text': message['content']},
                        {'cachePoint': {'type': 'default'}}
                    ]
                elif 'content' not in message and 'role' in message:
                    # Handle cases where message might have different structure
                    # Add content with cache control
                    message['content'] = [{'cachePoint': {'type': 'default'}}]
        
        logger.info(f"Added cache control to agent messages: {len(cached_messages)} total, "
                   f"cache cutoff at message {cache_cutoff}")
        return cached_messages


def create_strands_agent_handler(connection_id: str, apigw_management, user_context: Dict[str, Any], request_start_time: float = None) -> StrandsShoppingAgent:
    """Factory function to create a Strands customer agent handler."""
    return StrandsShoppingAgent(connection_id, apigw_management, user_context, request_start_time)
