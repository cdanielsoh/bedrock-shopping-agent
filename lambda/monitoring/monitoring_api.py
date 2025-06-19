"""
Monitoring API Lambda functions for retrieving conversation and performance data
"""

import json
import boto3
import os
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import List, Dict, Any, Optional
import logging
from boto3.dynamodb.conditions import Key, Attr

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# DynamoDB setup
dynamodb = boto3.resource('dynamodb')

# Table names from environment
CONVERSATIONS_TABLE = os.environ.get('CONVERSATIONS_TABLE')
SHARED_CONTEXT_TABLE = os.environ.get('SHARED_CONTEXT_TABLE')
PERFORMANCE_METRICS_TABLE = os.environ.get('PERFORMANCE_METRICS_TABLE')
SESSIONS_TABLE = os.environ.get('SESSIONS_TABLE')
AGENT_CONVERSATIONS_TABLE = os.environ.get('AGENT_CONVERSATIONS_TABLE')
AGENT_EVENT_LOOP_METRICS_TABLE = os.environ.get('AGENT_EVENT_LOOP_METRICS_TABLE')

def lambda_handler(event, context):
    """
    Main handler for monitoring API requests
    """
    try:
        print(f"Received event: {json.dumps(event)}")
        
        http_method = event.get('requestContext', {}).get('http', {}).get('method', event.get('httpMethod', ''))
        path = event.get('requestContext', {}).get('http', {}).get('path', event.get('path', ''))
        
        # Handle CORS preflight requests
        if http_method == 'OPTIONS':
            return create_response(200, {'message': 'CORS preflight'})
        
        # Extract path parameters
        path_params = event.get('pathParameters') or {}
        query_params = event.get('queryStringParameters') or {}
        
        print(f"Method: {http_method}, Path: {path}")
        print(f"Path params: {path_params}, Query params: {query_params}")
        
        # Route to appropriate handler
        if '/monitoring/conversations/' in path:
            session_id = path_params.get('sessionId')
            return get_conversations(session_id)
        elif '/monitoring/agent-conversations/' in path:
            session_id = path_params.get('sessionId')
            return get_agent_conversations(session_id)
        elif '/monitoring/context/' in path:
            session_id = path_params.get('sessionId')
            return get_shared_context(session_id)
        elif '/monitoring/router/' in path:
            session_id = path_params.get('sessionId')
            return get_router_data(session_id)
        elif '/monitoring/sessions/' in path:
            user_id = path_params.get('userId')
            return get_user_sessions(user_id)
        elif '/monitoring/performance' in path:
            return get_performance_metrics(query_params)
        else:
            return create_response(404, {'error': 'Not found', 'path': path})
            
    except Exception as e:
        logger.error(f"Error in monitoring API: {str(e)}")
        import traceback
        traceback.print_exc()
        return create_response(500, {'error': str(e)})

def create_response(status_code: int, body: dict):
    """Create a standardized API response with CORS headers"""
    return {
        'statusCode': status_code,
        'headers': {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Content-Type, Authorization, X-Requested-With',
            'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
            'Content-Type': 'application/json'
        },
        'body': json.dumps(body, default=decimal_default)
    }

def decimal_default(obj):
    """JSON serializer for Decimal objects"""
    if isinstance(obj, Decimal):
        return float(obj)
    raise TypeError

def get_conversations(session_id: str):
    """Get all conversations for a session"""
    try:
        if not session_id:
            return create_response(400, {'error': 'session_id is required'})
        
        logger.info(f"Getting conversations for session: {session_id}")
        
        if not CONVERSATIONS_TABLE:
            return create_response(500, {'error': 'Conversations table not configured'})
        
        conversations_table = dynamodb.Table(CONVERSATIONS_TABLE)
        
        # Query all conversations for this session using GSI
        response = conversations_table.query(
            IndexName='SessionIndex',
            KeyConditionExpression=Key('session_id').eq(session_id),
            ScanIndexForward=False  # Most recent first
        )
        
        conversations = []
        for item in response.get('Items', []):
            conversation = {
                'conversation_id': item.get('conversation_id'),
                'handler_type': item.get('handler_type'),
                'session_id': item.get('session_id'),
                'messages': item.get('messages', []),
                'message_count': item.get('message_count', 0),
                'updated_at': item.get('updated_at')
            }
            conversations.append(conversation)
        
        logger.info(f"Found {len(conversations)} conversations for session {session_id}")
        return create_response(200, {'conversations': conversations})
        
    except Exception as e:
        logger.error(f"Error getting conversations: {str(e)}")
        return create_response(500, {'error': str(e)})

def get_shared_context(session_id: str):
    """Get shared context for a session"""
    try:
        if not session_id:
            return create_response(400, {'error': 'session_id is required'})
        
        logger.info(f"Getting shared context for session: {session_id}")
        
        if not SHARED_CONTEXT_TABLE:
            return create_response(500, {'error': 'Shared context table not configured'})
        
        shared_context_table = dynamodb.Table(SHARED_CONTEXT_TABLE)
        
        response = shared_context_table.get_item(
            Key={'session_id': session_id}
        )
        
        if 'Item' not in response:
            logger.info(f"No shared context found for session {session_id}")
            return create_response(200, {'context': None})
        
        context = response['Item']
        logger.info(f"Found shared context for session {session_id}")
        return create_response(200, {'context': context})
        
    except Exception as e:
        logger.error(f"Error getting shared context: {str(e)}")
        return create_response(500, {'error': str(e)})

def get_router_data(session_id: str):
    """Get router decisions for a session from conversation messages"""
    try:
        if not session_id:
            return create_response(400, {'error': 'session_id is required'})
        
        logger.info(f"Getting router data for session: {session_id}")
        
        # Query the conversations table for routing decisions
        # Router decisions are stored in the handler-specific conversations
        table = dynamodb.Table(CONVERSATIONS_TABLE)
        
        # Look for system messages in the base handler conversation
        conversation_id = f"{session_id}#base"
        
        try:
            response = table.get_item(Key={'conversation_id': conversation_id})
            
            router_decisions = []
            if 'Item' in response and 'messages' in response['Item']:
                messages = response['Item']['messages']
                
                # Filter for system messages that are routing decisions
                for message in messages:
                    if (message.get('role') == 'system' and 
                        message.get('metadata', {}).get('type') == 'routing_decision'):
                        
                        metadata = message.get('metadata', {})
                        router_decisions.append({
                            'timestamp': message.get('timestamp'),
                            'assistant_number': metadata.get('assistant_number'),
                            'handler_name': metadata.get('handler_name', f"Handler {metadata.get('assistant_number', 'Unknown')}"),
                            'user_message': metadata.get('user_message', ''),
                            'routing_decision': message.get('content', ''),
                            'routing_reasoning': metadata.get('routing_reasoning', 'No reasoning provided'),
                            'message_id': metadata.get('message_id', f"msg_{len(router_decisions)}")
                        })
            
            # Sort by timestamp (most recent first)
            router_decisions.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
            
            logger.info(f"Found {len(router_decisions)} router decisions for session {session_id}")
            router_data = {
                'session_id': session_id,
                'routing_decisions': router_decisions
            }
            
            return create_response(200, {'router_data': router_data})
            
        except Exception as query_error:
            logger.warning(f"Error querying conversation for router data: {str(query_error)}")
            # Return empty router data instead of failing
            router_data = {
                'session_id': session_id,
                'routing_decisions': []
            }
            return create_response(200, {'router_data': router_data})
        
    except Exception as e:
        logger.error(f"Error getting router data: {str(e)}")
        return create_response(500, {'error': str(e)})

def get_user_sessions(user_id: str):
    """Get all sessions for a user"""
    try:
        if not user_id:
            return create_response(400, {'error': 'user_id is required'})
        
        logger.info(f"Getting sessions for user: {user_id}")
        
        if not SESSIONS_TABLE:
            return create_response(500, {'error': 'Sessions table not configured'})
        
        sessions_table = dynamodb.Table(SESSIONS_TABLE)
        
        # Query sessions by user_id using GSI
        response = sessions_table.query(
            IndexName='UserIdIndex',
            KeyConditionExpression=Key('user_id').eq(user_id),
            ScanIndexForward=False,  # Most recent first
            Limit=50  # Limit to recent sessions
        )
        
        sessions = []
        for item in response.get('Items', []):
            # Return full session objects with all metadata
            session_data = {
                'session_id': item.get('session_id'),
                'user_id': item.get('user_id'),
                'created_at': item.get('created_at'),
                'last_activity': item.get('last_used'),  # Map last_used to last_activity for consistency
                'message_count': int(item.get('message_count', 0)),
                'title': item.get('title', f"Session {item.get('created_at', '')[:10]}")
            }
            sessions.append(session_data)
        
        logger.info(f"Found {len(sessions)} sessions for user {user_id}")
        return create_response(200, {'sessions': sessions})
        
    except Exception as e:
        logger.error(f"Error getting user sessions: {str(e)}")
        return create_response(500, {'error': str(e)})

def get_performance_metrics(query_params: Dict[str, str]):
    """Get performance metrics with optional filters"""
    try:
        logger.info(f"Getting performance metrics with params: {query_params}")
        
        if not PERFORMANCE_METRICS_TABLE:
            return create_response(500, {'error': 'Performance metrics table not configured'})
        
        performance_table = dynamodb.Table(PERFORMANCE_METRICS_TABLE)
        
        # Extract query parameters
        user_id = query_params.get('user_id')
        handler_type = query_params.get('handler_type')
        time_range = query_params.get('time_range', '24h')
        limit = int(query_params.get('limit', '100'))
        
        # Calculate time filter
        now = datetime.now(timezone.utc)
        if time_range == '1h':
            start_time = now - timedelta(hours=1)
        elif time_range == '24h':
            start_time = now - timedelta(hours=24)
        elif time_range == '7d':
            start_time = now - timedelta(days=7)
        elif time_range == '30d':
            start_time = now - timedelta(days=30)
        else:
            start_time = now - timedelta(hours=24)
        
        start_time_str = start_time.isoformat()
        
        # Build query based on filters
        if user_id and user_id != 'all':
            # Query by user_id
            response = performance_table.query(
                IndexName='UserIdIndex',
                KeyConditionExpression=Key('user_id').eq(user_id) & Key('timestamp').gte(start_time_str),
                ScanIndexForward=False,
                Limit=limit
            )
        elif handler_type and handler_type != 'all' and handler_type != 'agent':
            # Query by handler_type
            response = performance_table.query(
                IndexName='HandlerTypeIndex',
                KeyConditionExpression=Key('handler_type').eq(handler_type) & Key('timestamp').gte(start_time_str),
                ScanIndexForward=False,
                Limit=limit
            )
        else:
            # Scan with filters (less efficient but more flexible)
            filter_expression = Key('timestamp').gte(start_time_str)
            
            if handler_type == 'agent':
                filter_expression = filter_expression & Attr('use_agent').eq(True)
            elif handler_type and handler_type != 'all':
                filter_expression = filter_expression & Attr('handler_type').eq(handler_type)
            
            response = performance_table.scan(
                FilterExpression=filter_expression,
                Limit=limit
            )
        
        metrics = response.get('Items', [])
        
        # Sort by timestamp (most recent first)
        metrics.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
        
        logger.info(f"Found {len(metrics)} performance metrics")
        return create_response(200, {'metrics': metrics})
        
    except Exception as e:
        logger.error(f"Error getting performance metrics: {str(e)}")
        return create_response(500, {'error': str(e)})

def get_agent_conversations(session_id: str):
    """
    Get agent conversation data and EventLoopMetrics for monitoring
    """
    try:
        if not session_id:
            return create_response(400, {'error': 'session_id parameter is required'})
        
        logger.info(f"Getting agent conversations and EventLoopMetrics for session: {session_id}")
        
        if not AGENT_CONVERSATIONS_TABLE:
            logger.warning("AGENT_CONVERSATIONS_TABLE environment variable not set")
            return create_response(200, {
                'session_id': session_id,
                'agent_messages': [],
                'agent_metadata': {},
                'event_loop_metrics': {},
                'error': 'Agent conversations table not configured'
            })
        
        logger.info(f"Using agent conversations table: {AGENT_CONVERSATIONS_TABLE}")
        agent_conversations_table = dynamodb.Table(AGENT_CONVERSATIONS_TABLE)
        
        # Get conversation messages
        logger.info(f"Getting conversation messages for session: {session_id}")
        response = agent_conversations_table.get_item(Key={'session_id': session_id})
        
        agent_messages = []
        agent_metadata = {
            'total_messages': 0,
            'user_messages': 0,
            'assistant_messages': 0,
            'tool_executions': 0,
            'agent_types_used': ['strands_agent'],
            'conversation_duration': None,
            'last_activity': None
        }
        
        if 'Item' in response:
            item = response['Item']
            messages = item.get('messages', [])
            
            # Convert messages to monitoring format
            for i, msg in enumerate(messages):
                # Extract text content properly from Strands agent message format
                content = msg.get('content', '')
                
                # Debug logging for content structure
                if i < 3:  # Only log first 3 messages to avoid spam
                    logger.info(f"Message {i} content type: {type(content)}, content: {str(content)[:200]}...")
                
                if isinstance(content, list):
                    # Handle array of content objects (Strands format)
                    text_parts = []
                    for content_item in content:
                        if isinstance(content_item, dict):
                            if 'text' in content_item:
                                text_parts.append(content_item['text'])
                            elif 'toolUse' in content_item:
                                tool_use = content_item['toolUse']
                                text_parts.append(f"[Tool: {tool_use.get('name', 'unknown')}]")
                            elif 'toolResult' in content_item:
                                text_parts.append("[Tool Result]")
                        else:
                            text_parts.append(str(content_item))
                    content_text = ' '.join(text_parts)
                elif isinstance(content, dict):
                    # Handle single content object
                    if 'text' in content:
                        content_text = content['text']
                    else:
                        content_text = str(content)
                else:
                    # Handle string content
                    content_text = str(content) if content else ''
                
                # Enhanced tool use detection
                has_tool_use = False
                if isinstance(content, list):
                    # Check for toolUse or toolResult in content array
                    has_tool_use = any(
                        isinstance(item, dict) and ('toolUse' in item or 'toolResult' in item)
                        for item in content
                    )
                elif isinstance(content, dict):
                    # Check for toolUse or toolResult in single content object
                    has_tool_use = 'toolUse' in content or 'toolResult' in content
                else:
                    # Check for tool indicators in string content
                    content_str = str(content).lower()
                    has_tool_use = any(indicator in content_str for indicator in [
                        'tool_call', 'tooluse', 'toolresult', '[tool:', 'tool executed'
                    ])
                
                agent_messages.append({
                    'timestamp': item.get('updated_at', ''),
                    'role': msg.get('role', 'unknown'),
                    'content': content_text,
                    'message_id': f"{session_id}_{i}",
                    'metadata': {
                        'agent_type': 'strands_agent',
                        'tool_use': has_tool_use
                    }
                })
            
            # Update metadata
            agent_metadata.update({
                'total_messages': len(messages),
                'user_messages': len([msg for msg in messages if msg.get('role') == 'user']),
                'assistant_messages': len([msg for msg in messages if msg.get('role') == 'assistant']),
                'last_activity': item.get('updated_at')
            })
        
        # Get EventLoopMetrics from separate table
        event_loop_metrics = get_event_loop_metrics_summary(session_id)
        
        # Update tool executions count from metrics
        if event_loop_metrics.get('has_metrics'):
            # Count actual tool executions from our custom streaming metrics
            total_tool_calls = 0
            
            # Get the raw snapshots data to access tool metrics
            try:
                event_loop_metrics_table_name = os.environ.get('AGENT_EVENT_LOOP_METRICS_TABLE', 'AgentEventLoopMetricsTable')
                event_loop_metrics_table = dynamodb.Table(event_loop_metrics_table_name)
                response = event_loop_metrics_table.get_item(Key={'session_id': session_id})
                
                if 'Item' in response and 'metrics_snapshots' in response['Item']:
                    snapshots = convert_decimals_to_float(response['Item']['metrics_snapshots'])
                    
                    for snapshot in snapshots:
                        snapshot_data = snapshot.get('snapshot', {})
                        raw_metrics = snapshot_data.get('raw_metrics', {})
                        tool_count = raw_metrics.get('tool_metrics_count', 0)
                        total_tool_calls += tool_count
                        
                        # Debug logging
                        if tool_count > 0:
                            logger.info(f"Found {tool_count} tools in snapshot {snapshot.get('message_number', 'unknown')}")
                    
                    logger.info(f"Total tool calls from streaming metrics: {total_tool_calls}")
            except Exception as e:
                logger.warning(f"Error accessing raw metrics snapshots: {str(e)}")
            
            # Also count from agent messages that contain tool use
            message_tool_count = len([msg for msg in agent_messages if msg.get('metadata', {}).get('tool_use')])
            
            # Use the higher count (streaming metrics vs message analysis)
            agent_metadata['tool_executions'] = max(total_tool_calls, message_tool_count)
            
            logger.info(f"Tool execution count - from metrics: {total_tool_calls}, from messages: {message_tool_count}, final: {agent_metadata['tool_executions']}")
        else:
            # Fallback: count from agent messages
            agent_metadata['tool_executions'] = len([msg for msg in agent_messages if msg.get('metadata', {}).get('tool_use')])
        
        # Prepare response
        response_data = {
            'session_id': session_id,
            'agent_messages': agent_messages,
            'agent_metadata': agent_metadata,
            'event_loop_metrics': event_loop_metrics,
            'has_metrics': event_loop_metrics.get('has_metrics', False),
            'retrieved_at': datetime.now(timezone.utc).isoformat()
        }
        
        logger.info(f"Returning response with {len(agent_messages)} messages and metrics: {event_loop_metrics.get('has_metrics', False)}")
        return create_response(200, response_data)
        
    except Exception as e:
        logger.error(f"Error retrieving agent conversation data: {str(e)}")
        return create_response(500, {
            'session_id': session_id,
            'agent_messages': [],
            'agent_metadata': {},
            'event_loop_metrics': {},
            'error': str(e)
        })

def get_event_loop_metrics_summary(session_id: str) -> dict:
    """
    Get aggregated EventLoopMetrics summary for monitoring dashboard.
    This function replicates the logic from AgentConversationManager.
    """
    try:
        # Get the EventLoopMetrics table name
        event_loop_metrics_table_name = os.environ.get('AGENT_EVENT_LOOP_METRICS_TABLE', 'AgentEventLoopMetricsTable')
        event_loop_metrics_table = dynamodb.Table(event_loop_metrics_table_name)
        
        logger.info(f"Getting EventLoopMetrics from table: {event_loop_metrics_table_name}")
        
        # Get metrics snapshots
        response = event_loop_metrics_table.get_item(Key={'session_id': session_id})
        
        if 'Item' not in response or 'metrics_snapshots' not in response['Item']:
            logger.info(f"No EventLoopMetrics snapshots found for session {session_id}")
            return {
                'session_id': session_id,
                'has_metrics': False,
                'total_snapshots': 0
            }
        
        snapshots = response['Item']['metrics_snapshots']
        logger.info(f"Found {len(snapshots)} EventLoopMetrics snapshots for session {session_id}")
        
        # Convert Decimal values back to float for processing
        snapshots = convert_decimals_to_float(snapshots)
        
        # Aggregate basic metrics
        total_cycles = 0
        total_duration = 0.0
        total_tokens = 0
        
        for snapshot in snapshots:
            snapshot_data = snapshot.get('snapshot', {})
            raw_metrics = snapshot_data.get('raw_metrics', {})
            
            total_cycles += raw_metrics.get('cycle_count', 0)
            total_duration += raw_metrics.get('total_duration', 0.0)
            
            # Get token usage
            usage = raw_metrics.get('accumulated_usage', {})
            total_tokens += usage.get('totalTokens', 0)
        
        # Calculate averages
        snapshot_count = len(snapshots)
        avg_cycles_per_message = total_cycles / snapshot_count if snapshot_count > 0 else 0
        avg_duration_per_message = total_duration / snapshot_count if snapshot_count > 0 else 0
        avg_tokens_per_message = total_tokens / snapshot_count if snapshot_count > 0 else 0
        
        # Build timeline
        snapshots_timeline = []
        for snap in snapshots:
            snapshot_data = snap.get('snapshot', {})
            raw_metrics = snapshot_data.get('raw_metrics', {})
            usage = raw_metrics.get('accumulated_usage', {})
            
            snapshots_timeline.append({
                'message_number': snap.get('message_number', 0),
                'timestamp': snap.get('timestamp', ''),
                'cycles': raw_metrics.get('cycle_count', 0),
                'duration': raw_metrics.get('total_duration', 0.0),
                'tokens': usage.get('totalTokens', 0)
            })
        
        return {
            'session_id': session_id,
            'has_metrics': True,
            'total_snapshots': snapshot_count,
            'aggregated_metrics': {
                'total_cycles': total_cycles,
                'total_duration': round(total_duration, 3),
                'total_tokens': total_tokens,
                'avg_cycles_per_message': round(avg_cycles_per_message, 2),
                'avg_duration_per_message': round(avg_duration_per_message, 3),
                'avg_tokens_per_message': round(avg_tokens_per_message, 1)
            },
            'snapshots_timeline': snapshots_timeline
        }
        
    except Exception as e:
        logger.error(f"Error getting EventLoopMetrics summary: {str(e)}")
        return {
            'session_id': session_id,
            'has_metrics': False,
            'error': str(e)
        }

def convert_decimals_to_float(obj):
    """Convert Decimal values back to float for JSON serialization."""
    from decimal import Decimal
    
    if isinstance(obj, Decimal):
        return float(obj)
    elif isinstance(obj, dict):
        return {key: convert_decimals_to_float(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [convert_decimals_to_float(item) for item in obj]
    else:
        return obj

def _generate_metrics_analytics(event_loop_metrics: dict) -> dict:
    """
    Generate analytics summary from EventLoopMetrics for monitoring dashboard.
    """
    try:
        if not event_loop_metrics or 'error' in event_loop_metrics:
            return {}
        
        analytics = {
            'performance_summary': {
                'total_duration': event_loop_metrics.get('total_duration', 0.0),
                'total_iterations': event_loop_metrics.get('total_iterations', 0),
                'avg_iteration_time': event_loop_metrics.get('performance_stats', {}).get('avg_iteration_time', 0.0),
                'efficiency_score': _calculate_efficiency_score(event_loop_metrics)
            },
            'tool_summary': {
                'total_tool_executions': len(event_loop_metrics.get('tool_executions', [])),
                'successful_tools': len([t for t in event_loop_metrics.get('tool_executions', []) if t.get('success', True)]),
                'tool_success_rate': 0.0,
                'most_used_tools': _get_top_tools(event_loop_metrics.get('tool_executions', []))
            },
            'model_summary': {
                'total_model_calls': len(event_loop_metrics.get('model_calls', [])),
                'total_tokens': sum(
                    call.get('input_tokens', 0) + call.get('output_tokens', 0) 
                    for call in event_loop_metrics.get('model_calls', [])
                ),
                'total_cost': sum(call.get('cost', 0.0) for call in event_loop_metrics.get('model_calls', [])),
                'avg_tokens_per_call': 0.0
            },
            'decision_summary': {
                'total_decisions': len(event_loop_metrics.get('decision_points', [])),
                'avg_confidence': 0.0,
                'high_confidence_decisions': len([
                    d for d in event_loop_metrics.get('decision_points', []) 
                    if d.get('confidence', 0.0) > 0.8
                ])
            },
            'error_summary': {
                'total_errors': event_loop_metrics.get('error_count', 0),
                'tool_errors': len([t for t in event_loop_metrics.get('tool_executions', []) if not t.get('success', True)]),
                'error_rate': 0.0
            }
        }
        
        # Calculate rates and averages
        tool_executions = event_loop_metrics.get('tool_executions', [])
        if tool_executions:
            analytics['tool_summary']['tool_success_rate'] = round(
                analytics['tool_summary']['successful_tools'] / len(tool_executions), 3
            )
        
        model_calls = event_loop_metrics.get('model_calls', [])
        if model_calls:
            analytics['model_summary']['avg_tokens_per_call'] = round(
                analytics['model_summary']['total_tokens'] / len(model_calls), 1
            )
        
        decision_points = event_loop_metrics.get('decision_points', [])
        if decision_points:
            analytics['decision_summary']['avg_confidence'] = round(
                sum(d.get('confidence', 0.0) for d in decision_points) / len(decision_points), 3
            )
        
        # Calculate error rate
        total_operations = (
            event_loop_metrics.get('total_iterations', 0) +
            len(tool_executions) +
            len(model_calls)
        )
        if total_operations > 0:
            analytics['error_summary']['error_rate'] = round(
                event_loop_metrics.get('error_count', 0) / total_operations, 3
            )
        
        return analytics
        
    except Exception as e:
        logger.error(f"Error generating metrics analytics: {str(e)}")
        return {'error': str(e)}

def _calculate_efficiency_score(metrics: dict) -> float:
    """Calculate efficiency score from EventLoopMetrics."""
    try:
        total_duration = metrics.get('total_duration', 0.0)
        total_iterations = metrics.get('total_iterations', 1)
        error_count = metrics.get('error_count', 0)
        tool_executions = len(metrics.get('tool_executions', []))
        
        if total_duration == 0:
            return 0.0
        
        # Base efficiency: iterations per second
        base_efficiency = total_iterations / total_duration
        
        # Penalty for errors
        error_penalty = 1.0 - (error_count * 0.1)
        error_penalty = max(0.1, error_penalty)
        
        # Bonus for tool usage
        tool_bonus = 1.0 + (tool_executions * 0.05)
        tool_bonus = min(2.0, tool_bonus)
        
        efficiency_score = base_efficiency * error_penalty * tool_bonus
        return round(efficiency_score, 3)
        
    except Exception:
        return 0.0

def _get_top_tools(tool_executions: list) -> list:
    """Get most frequently used tools."""
    try:
        tool_counts = {}
        for tool in tool_executions:
            tool_name = tool.get('tool_name', 'unknown')
            tool_counts[tool_name] = tool_counts.get(tool_name, 0) + 1
        
        # Return top 3 tools
        sorted_tools = sorted(tool_counts.items(), key=lambda x: x[1], reverse=True)
        return [{'tool': tool, 'count': count} for tool, count in sorted_tools[:3]]
        
    except Exception:
        return []
        
        # Calculate conversation duration
        conversation_duration = None
        
        # Try to get duration from EventLoop metrics first
        if event_loop_metrics.get('has_metrics') and event_loop_metrics.get('aggregated_metrics'):
            metrics_duration = event_loop_metrics['aggregated_metrics'].get('total_duration', 0)
            if metrics_duration > 0:
                conversation_duration = metrics_duration
                logger.info(f"Using EventLoop metrics duration: {conversation_duration}s")
        
        # Fallback: try to calculate from message timestamps
        if conversation_duration is None and agent_messages:
            try:
                # Get unique timestamps
                timestamps = list(set(msg['timestamp'] for msg in agent_messages if msg['timestamp']))
                if len(timestamps) > 1:
                    timestamps.sort()
                    first_time = datetime.fromisoformat(timestamps[0].replace('Z', '+00:00'))
                    last_time = datetime.fromisoformat(timestamps[-1].replace('Z', '+00:00'))
                    conversation_duration = (last_time - first_time).total_seconds()
                    logger.info(f"Calculated duration from timestamps: {conversation_duration}s")
                else:
                    # Single timestamp or all same - estimate based on message count
                    message_count = len(agent_messages)
                    if message_count > 1:
                        # Rough estimate: 2-5 seconds per message exchange
                        conversation_duration = message_count * 3.5
                        logger.info(f"Estimated duration from message count: {conversation_duration}s")
            except Exception as e:
                logger.warning(f"Could not calculate conversation duration from timestamps: {str(e)}")
        
        # Final fallback: use a default based on message count
        if conversation_duration is None and agent_messages:
            conversation_duration = len(agent_messages) * 2.0  # 2 seconds per message
            logger.info(f"Using fallback duration estimate: {conversation_duration}s")
        
        agent_metadata['conversation_duration'] = conversation_duration
        
        # Convert set to list for JSON serialization
        agent_metadata['agent_types_used'] = list(agent_metadata['agent_types_used'])
        
        return create_response(200, {
            'session_id': session_id,
            'agent_messages': agent_messages,
            'agent_metadata': agent_metadata,
            'retrieved_at': datetime.now(timezone.utc).isoformat()
        })
        
    except Exception as e:
        logger.error(f"Error retrieving agent conversation data: {str(e)}")
        return create_response(500, {
            'session_id': session_id,
            'agent_messages': [],
            'agent_metadata': {},
            'error': str(e)
        })
