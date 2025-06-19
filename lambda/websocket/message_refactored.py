"""
Refactored main message handler with improved efficiency and organization.
"""
import json
import os
import time
from typing import Dict, Any
import logging

from resource_manager import resource_manager
from message_handlers import (
    RouterHandler, OrderHistoryHandler, ProductSearchHandler, 
    GeneralInquiryHandler, MessageHandlerError, ProductDetailsHandler, CompareProductsHandler
)
from performance_monitor import StreamingPerformanceMonitor, performance_monitor

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

def handler(event, context):
    """
    Main WebSocket message handler with improved efficiency and error handling.
    """
    # Capture request start time immediately for accurate first token latency
    request_start_time = time.time()
    
    try:
        # Extract connection and request info
        connection_id = event['requestContext']['connectionId']
        domain = event['requestContext']['domainName']
        stage = event['requestContext']['stage']
        endpoint = f"https://{domain}/{stage}"
        
        # Parse message body
        body = json.loads(event['body'])
        user_context = _extract_user_context(body, connection_id)
        
        logger.info(f"User {user_context['user_id']} ({user_context['user_name']}) "
                    f"with persona '{user_context['user_persona']}' sent: {user_context['user_message']}")
        
        # Save/update session in DynamoDB
        session_id = user_context.get('session_id', connection_id)
        _save_session_to_dynamodb(session_id, user_context['user_id'])
        
        # Start performance monitoring
        use_agent = user_context.get('use_agent', False)
        
        # Skip outer performance monitoring for agent cases since they have their own
        if not use_agent:
            handler_type = 'standard'
            
            with StreamingPerformanceMonitor(
                session_id=session_id,
                user_id=user_context['user_id'],
                handler_type=handler_type,
                model_id="us.anthropic.claude-3-5-haiku-20241022-v1:0",
                use_agent=use_agent,
                request_start_time=request_start_time
            ) as perf_monitor:
                # Get API Gateway management client
                apigw_management = resource_manager.get_apigw_management_client(endpoint)
                
                # Validate connection
                if not resource_manager.validate_connection(connection_id):
                    logger.error(f"Invalid connection: {connection_id}")
                    return {'statusCode': 410, 'body': 'Connection no longer exists'}
                
                # Standard routing and handling (not agent)
                router = RouterHandler(connection_id, apigw_management, user_context)
                
                # Save user message first
                router.save_message_to_handler('user', user_context['user_message'], {
                    'user_persona': user_context['user_persona'],
                    'user_discount_persona': user_context['user_discount_persona'],
                    'user_name': user_context['user_name'],
                    'user_email': user_context['user_email'],
                    'user_age': user_context['user_age'],
                    'user_gender': user_context['user_gender'],
                    'connection_id': connection_id
                })
                
                # Route the message
                assistant_number = router.route_message(user_context.get('use_agent', False))
                
                # Map assistant numbers to handler names for better display
                handler_names = {
                    "1": "Order History Handler",
                    "2": "Product Search Handler", 
                    "3": "Product Details Handler",
                    "4": "General Inquiry Handler",
                    "5": "Compare Products Handler"
                }
                
                handler_name = handler_names.get(str(assistant_number), f"Handler {assistant_number}")
                routing_decision = f"Routed to {handler_name} (#{assistant_number})"
                routing_reasoning = f"Claude determined that assistant #{assistant_number} should handle: '{user_context['user_message'][:100]}...'"
                
                # Save routing decision
                router.save_message_to_handler('system', routing_decision, {
                    'type': 'routing_decision',
                    'assistant_number': assistant_number,
                    'handler_name': handler_name,
                    'user_message': user_context['user_message'],
                    'routing_reasoning': routing_reasoning,
                    'timestamp': router.get_timestamp()
                })
                
                # Dispatch to appropriate handler
                _dispatch_to_handler(assistant_number, connection_id, apigw_management, user_context, request_start_time)
        else:
            # Agent case: No outer performance monitoring (handled inside agent)
            try:
                # Get API Gateway management client
                apigw_management = resource_manager.get_apigw_management_client(endpoint)
                
                # Validate connection
                if not resource_manager.validate_connection(connection_id):
                    logger.error(f"Invalid connection: {connection_id}")
                    return {'statusCode': 410, 'body': 'Connection no longer exists'}
                
                # Agent routing and handling
                assistant_number = "4"
                routing_decision = "Agent Mode (Direct)"
                handler_name = "Agent Handler"
                routing_reasoning = "User requested agent mode"
                
                # Dispatch to agent handler (which has its own performance monitoring)
                _dispatch_to_handler(assistant_number, connection_id, apigw_management, user_context, request_start_time)
                
            except Exception as e:
                logger.error(f"Error in agent request handling: {str(e)}")
                try:
                    apigw_management.post_to_connection(
                        ConnectionId=connection_id,
                        Data=json.dumps({
                            'type': 'error',
                            'message': 'Sorry, there was an error processing your request with the AI agent. Please try again.'
                        })
                    )
                except Exception as send_error:
                    logger.error(f"Failed to send error message: {str(send_error)}")
        
        return {'statusCode': 200, 'body': 'Message processed successfully'}
        
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in request body: {str(e)}")
        return {'statusCode': 400, 'body': 'Invalid JSON format'}
        
    except MessageHandlerError as e:
        logger.error(f"Message handler error: {str(e)}")
        return {'statusCode': 500, 'body': f'Handler error: {str(e)}'}
        
    except Exception as e:
        logger.error(f"Unexpected error in message handler: {str(e)}")
        return {'statusCode': 500, 'body': 'Internal server error'}


def _extract_user_context(body: Dict[str, Any], connection_id: str) -> Dict[str, Any]:
    """Extract and validate user context from request body."""
    return {
        'user_id': body.get('user_id', ''),
        'user_message': body.get('user_message', ''),
        'user_persona': body.get('user_persona', ''),
        'user_discount_persona': body.get('user_discount_persona', ''),
        'session_id': body.get('session_id', connection_id),
        'user_name': body.get('user_name', ''),
        'user_email': body.get('user_email', ''),
        'user_age': body.get('user_age', ''),
        'user_gender': body.get('user_gender', ''),
        'use_agent': body.get('use_agent', False)
    }


def _dispatch_to_handler(assistant_number: str, connection_id: str, apigw_management, user_context: Dict[str, Any], request_start_time: float):
    """Dispatch message to appropriate specialized handler."""
    try:
        use_agent = user_context.get('use_agent', False)
        
        # Use agent mode if explicitly requested OR if using unified agent (assistant_number "4")
        if use_agent:
            _handle_agent_mode(assistant_number, connection_id, apigw_management, user_context, request_start_time)
        else:
            _handle_standard_mode(assistant_number, connection_id, apigw_management, user_context, request_start_time)
            
    except Exception as e:
        logger.error(f"Error in handler dispatch: {str(e)}")
        # Send error message directly through API Gateway
        try:
            apigw_management.post_to_connection(
                ConnectionId=connection_id,
                Data=json.dumps({
                    'type': 'error',
                    'message': 'Sorry, there was an error processing your request. Please try again.'
                })
            )
        except Exception as send_error:
            logger.error(f"Failed to send error message: {str(send_error)}")


def _handle_agent_mode(assistant_number: str, connection_id: str, apigw_management, user_context: Dict[str, Any], request_start_time: float):
    """Handle requests in agent mode with intelligent configuration selection."""
    import asyncio
    from strands_shopping_agent import create_strands_agent_handler
    from agent_configurations import select_agent_configuration
    
    try:
        # Create Strands customer agent
        agent_handler = create_strands_agent_handler(connection_id, apigw_management, user_context, request_start_time)
        
        # Select optimal agent configuration based on user context and routing
        config = select_agent_configuration(assistant_number)
        
        logger.info(f"Using agent configuration: {config['agent_type']}")
        
        # Execute async agent request with selected configuration
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(
                agent_handler.handle_request(
                    agent_type=config['agent_type'],
                    tools_path=config.get('tools_path'),
                )
            )
        finally:
            loop.close()
            
    except Exception as e:
        logger.error(f"Error in agent mode handler: {str(e)}")
        # Send error message directly through API Gateway
        try:
            apigw_management.post_to_connection(
                ConnectionId=connection_id,
                Data=json.dumps({
                    'type': 'error',
                    'message': 'Sorry, there was an error processing your request with the AI agent. Please try again.'
                })
            )
        except Exception as send_error:
            logger.error(f"Failed to send error message: {str(send_error)}")


def _handle_standard_mode(assistant_number: str, connection_id: str, apigw_management, user_context: Dict[str, Any], request_start_time: float):
    """Handle requests in standard mode."""
    if assistant_number == "1":
        handler = OrderHistoryHandler(connection_id, apigw_management, user_context)
        handler.handle()
    elif assistant_number == "2":
        handler = ProductSearchHandler(connection_id, apigw_management, user_context)
        handler.handle()
    elif assistant_number == "3":
        handler = ProductDetailsHandler(connection_id, apigw_management, user_context)
        handler.handle()
    elif assistant_number == "4":
        handler = GeneralInquiryHandler(connection_id, apigw_management, user_context)
        handler.handle()
    elif assistant_number == "5":
        handler = CompareProductsHandler(connection_id, apigw_management, user_context)
        handler.handle()


def _save_session_to_dynamodb(session_id: str, user_id: str):
    """Save or update session information in DynamoDB."""
    try:
        import boto3
        from datetime import datetime, timezone
        
        # Get sessions table
        sessions_table_name = os.environ.get('SESSIONS_TABLE')
        if not sessions_table_name:
            logger.warning("SESSIONS_TABLE environment variable not set, skipping session save")
            return
        
        dynamodb = boto3.resource('dynamodb')
        sessions_table = dynamodb.Table(sessions_table_name)
        
        # Current timestamp
        now = datetime.now(timezone.utc).isoformat()
        
        # Try to get existing session
        try:
            response = sessions_table.get_item(Key={'session_id': session_id})
            existing_session = response.get('Item')
        except Exception as e:
            logger.warning(f"Error checking existing session: {str(e)}")
            existing_session = None
        
        if existing_session:
            # Update existing session
            sessions_table.update_item(
                Key={'session_id': session_id},
                UpdateExpression='SET last_used = :last_used, message_count = message_count + :inc',
                ExpressionAttributeValues={
                    ':last_used': now,
                    ':inc': 1
                }
            )
            logger.info(f"Updated existing session: {session_id}")
        else:
            # Create new session
            sessions_table.put_item(
                Item={
                    'session_id': session_id,
                    'user_id': user_id,
                    'created_at': now,
                    'last_used': now,
                    'message_count': 1,
                    'title': f"Session {datetime.now().strftime('%Y-%m-%d %H:%M')}",
                    'ttl': int((datetime.now(timezone.utc).timestamp()) + (30 * 24 * 60 * 60))  # 30 days TTL
                }
            )
            logger.info(f"Created new session: {session_id} for user: {user_id}")
            
    except Exception as e:
        logger.error(f"Error saving session to DynamoDB: {str(e)}")
        # Don't fail the entire request if session saving fails
