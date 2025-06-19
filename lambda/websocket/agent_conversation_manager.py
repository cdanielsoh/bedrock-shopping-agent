import json
import boto3
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Union
from decimal import Decimal

class AgentConversationManager:
    """
    Manages conversation history and EventLoopMetrics for Strands agents using DynamoDB storage.
    Handles loading/saving agent.messages and agent.event_loop.metrics for session continuity and monitoring.
    """
    
    def __init__(self, dynamodb_table_name: str, event_loop_metrics_table_name: str, region: str = 'us-west-2'):
        self.dynamodb = boto3.resource('dynamodb', region_name=region)
        self.table = self.dynamodb.Table(dynamodb_table_name)
        self.event_loop_metrics_table = self.dynamodb.Table(event_loop_metrics_table_name)
        
    def _convert_floats_to_decimal(self, obj):
        """Convert float values to Decimal for DynamoDB compatibility."""
        if isinstance(obj, float):
            return Decimal(str(obj))
        elif isinstance(obj, dict):
            return {key: self._convert_floats_to_decimal(value) for key, value in obj.items()}
        elif isinstance(obj, list):
            return [self._convert_floats_to_decimal(item) for item in obj]
        else:
            return obj
    
    def _convert_decimals_to_float(self, obj):
        """Convert Decimal values back to float for agent consumption."""
        if isinstance(obj, Decimal):
            return float(obj)
        elif isinstance(obj, dict):
            return {key: self._convert_decimals_to_float(value) for key, value in obj.items()}
        elif isinstance(obj, list):
            return [self._convert_decimals_to_float(item) for item in obj]
        else:
            return obj
    
    def _extract_event_loop_metrics(self, metrics) -> Dict[str, Any]:
        """
        Extract EventLoopMetrics from Strands agent or custom metrics dictionary.
        
        Args:
            metrics: Either EventLoopMetrics object from Strands SDK or custom metrics dict
            
        Returns:
            Dictionary containing extracted EventLoopMetrics data
        """
        try:
            if isinstance(metrics, dict):
                # Handle custom metrics dictionary from streaming
                print(f"Processing custom streaming metrics: {metrics.get('cycle_count', 0)} cycles, {metrics.get('tool_metrics_count', 0)} tools")
                return {
                    'timestamp': datetime.now(timezone.utc).isoformat(),
                    'summary': {
                        'cycle_count': metrics.get('cycle_count', 0),
                        'total_duration': metrics.get('total_duration', 0.0),
                        'tool_metrics_count': metrics.get('tool_metrics_count', 0),
                        'total_tokens': metrics.get('accumulated_usage', {}).get('totalTokens', 0),
                        'input_tokens': metrics.get('accumulated_usage', {}).get('inputTokens', 0),
                        'output_tokens': metrics.get('accumulated_usage', {}).get('outputTokens', 0),
                        'latency_ms': metrics.get('accumulated_metrics', {}).get('latencyMs', 0)
                    },
                    'raw_metrics': metrics
                }
            elif metrics:
                # Handle original EventLoopMetrics object from Strands SDK
                summary = metrics.get_summary()
                extracted_data = {
                    'timestamp': datetime.now(timezone.utc).isoformat(),
                    'summary': summary,
                    'raw_metrics': {
                        'cycle_count': metrics.cycle_count,
                        'cycle_durations': metrics.cycle_durations,
                        'total_duration': sum(metrics.cycle_durations),
                        'accumulated_usage': dict(metrics.accumulated_usage),
                        'accumulated_metrics': dict(metrics.accumulated_metrics),
                        'tool_metrics_count': len(metrics.tool_metrics)
                    }
                }
                
                print(f"Extracted EventLoopMetrics: {metrics.cycle_count} cycles, {len(metrics.tool_metrics)} tools")
                return extracted_data
            else:
                print("No EventLoopMetrics found")
                return {}
                
        except Exception as e:
            print(f"Error extracting EventLoopMetrics: {str(e)}")
            return {'error': str(e), 'timestamp': datetime.now(timezone.utc).isoformat()}
    
    def save_agent_event_loop_metrics(self, session_id: str, user_id: str, agent_metrics) -> Dict[str, Any]:
        """
        Save EventLoopMetrics to DynamoDB as a list of snapshots.
        
        Args:
            session_id: Unique session identifier
            user_id: User identifier
            agent_metrics: EventLoopMetrics from agent.agent_result.metrics
            
        Returns:
            Dictionary with save results and metrics summary
        """
        try:
            now = datetime.now(timezone.utc)
            ttl = int(now.timestamp()) + (24 * 60 * 60)  # 24 hours TTL
            
            # Extract EventLoopMetrics if provided
            event_loop_metrics = {}
            if agent_metrics:
                event_loop_metrics = self._extract_event_loop_metrics(agent_metrics)
                event_loop_metrics = self._convert_floats_to_decimal(event_loop_metrics)
            
            # Get existing metrics list
            existing_response = self.event_loop_metrics_table.get_item(Key={'session_id': session_id})
            
            if 'Item' in existing_response:
                # Append to existing list
                existing_metrics = existing_response['Item'].get('metrics_snapshots', [])
                existing_metrics = self._convert_decimals_to_float(existing_metrics)
            else:
                # Start new list
                existing_metrics = []
            
            # Create new snapshot with metadata
            new_snapshot = {
                'timestamp': now.isoformat(),
                'message_number': len(existing_metrics) + 1,
                'snapshot': event_loop_metrics
            }
            
            # Append new snapshot
            existing_metrics.append(new_snapshot)
            
            # Prepare item for DynamoDB
            item = {
                'session_id': session_id,
                'user_id': user_id,
                'metrics_snapshots': self._convert_floats_to_decimal(existing_metrics),
                'updated_at': now.isoformat(),
                'ttl': ttl,
                'snapshot_count': len(existing_metrics)
            }
            
            # Save to DynamoDB
            self.event_loop_metrics_table.put_item(Item=item)
            
            # Create summary for logging/monitoring
            summary = {
                'session_id': session_id,
                'metrics_captured': bool(event_loop_metrics and 'error' not in event_loop_metrics),
                'snapshot_number': len(existing_metrics),
                'timestamp': now.isoformat()
            }
            
            if event_loop_metrics and 'error' not in event_loop_metrics:
                raw_metrics = event_loop_metrics.get('raw_metrics', {})
                summary.update({
                    'cycle_count': raw_metrics.get('cycle_count', 0),
                    'total_duration': raw_metrics.get('total_duration', 0.0),
                    'tool_metrics_count': raw_metrics.get('tool_metrics_count', 0),
                    'total_tokens': raw_metrics.get('accumulated_usage', {}).get('totalTokens', 0)
                })
            
            print(f"Saved EventLoopMetrics snapshot #{len(existing_metrics)} for session {session_id}: {summary}")
            return summary
            
        except Exception as e:
            error_msg = f"Error saving agent event loop metrics: {str(e)}"
            print(error_msg)
            return {'error': error_msg, 'session_id': session_id}
    
    def save_agent_messages(self, session_id: str, user_id: str, agent_messages: List[Dict[str, Any]]):
        """
        Save agent.messages to DynamoDB for session persistence.
        
        Args:
            session_id: Unique session identifier (e.g., connection_id)
            user_id: User identifier
            agent_messages: List of messages from agent.messages
        """
        try:
            now = datetime.now(timezone.utc)
            ttl = int(now.timestamp()) + (24 * 60 * 60)  # 24 hours TTL
            
            # Convert floats to Decimal for DynamoDB compatibility
            converted_messages = self._convert_floats_to_decimal(agent_messages)
            
            # Prepare item for DynamoDB
            item = {
                'session_id': session_id,
                'messages': converted_messages,
                'ttl': ttl,
                'updated_at': now.isoformat(),
                'user_id': user_id
            }
            
            # Save to DynamoDB
            self.table.put_item(Item=item)
            
            print(f"Saved {len(agent_messages)} agent messages for session {session_id}")
            
        except Exception as e:
            error_msg = f"Error saving agent messages: {str(e)}"
            print(error_msg)
            raise Exception(error_msg)
    
    def load_agent_messages(self, session_id: str) -> List[Dict[str, Any]]:
        """
        Load agent.messages from DynamoDB for session continuity.
        
        Args:
            session_id: Unique session identifier
            
        Returns:
            List of messages to restore to agent.messages
        """
        try:
            response = self.table.get_item(Key={'session_id': session_id})
            
            if 'Item' in response:
                print(f"Loaded {len(response['Item']['messages'])} agent messages for session {session_id}")
                messages = response['Item']['messages']
                # Convert back from DynamoDB format
                return self._convert_decimals_to_float(messages)
            else:
                print(f"No existing conversation found for session {session_id}")
                return []
                
        except Exception as e:
            print(f"Error loading agent messages: {str(e)}")
            return []
    
    def load_event_loop_metrics(self, session_id: str) -> Dict[str, Any]:
        """
        Load EventLoopMetrics from DynamoDB for monitoring and analysis.
        
        Args:
            session_id: Unique session identifier
            
        Returns:
            Dictionary containing EventLoopMetrics data
        """
        try:
            response = self.event_loop_metrics_table.get_item(Key={'session_id': session_id})
            
            if 'Item' in response and 'event_loop_metrics' in response['Item']:
                metrics = response['Item']['event_loop_metrics']
                converted_metrics = self._convert_decimals_to_float(metrics)
                print(f"Loaded EventLoopMetrics for session {session_id}")
                return converted_metrics
            else:
                print(f"No EventLoopMetrics found for session {session_id}")
                return []
                
        except Exception as e:
            print(f"Error loading EventLoopMetrics: {str(e)}")
            return {'error': str(e)}
    
    def get_conversation_with_metrics_summary(self, session_id: str) -> Dict[str, Any]:
        """Get comprehensive summary including both conversation and EventLoopMetrics data."""
        try:
            response = self.table.get_item(Key={'session_id': session_id})
            
            if 'Item' in response:
                item = response['Item']
                messages = item.get('messages', [])
                metrics = item.get('event_loop_metrics', {})
                
                summary = {
                    'session_id': session_id,
                    'user_id': item.get('user_id'),
                    'message_count': len(messages),
                    'last_updated': item.get('updated_at'),
                    'has_metrics': item.get('has_metrics', False),
                    'conversation_stats': {
                        'has_tool_calls': any(
                            msg.get('role') == 'assistant' and 
                            any('tool_call' in str(content) for content in msg.get('content', []))
                            for msg in messages
                        ),
                        'user_messages': len([msg for msg in messages if msg.get('role') == 'user']),
                        'assistant_messages': len([msg for msg in messages if msg.get('role') == 'assistant'])
                    }
                }
                
                # Add EventLoopMetrics summary if available
                if metrics and 'error' not in metrics:
                    raw_metrics = metrics.get('raw_metrics', {})
                    summary['event_loop_stats'] = {
                        'cycle_count': raw_metrics.get('cycle_count', 0),
                        'total_duration': raw_metrics.get('total_duration', 0.0),
                        'tool_metrics_count': raw_metrics.get('tool_metrics_count', 0),
                        'total_tokens': raw_metrics.get('accumulated_usage', {}).get('totalTokens', 0),
                        'input_tokens': raw_metrics.get('accumulated_usage', {}).get('inputTokens', 0),
                        'output_tokens': raw_metrics.get('accumulated_usage', {}).get('outputTokens', 0),
                        'latency_ms': raw_metrics.get('accumulated_metrics', {}).get('latencyMs', 0)
                    }
                
                return summary
            else:
                return {'session_id': session_id, 'message_count': 0, 'has_metrics': False}
                
        except Exception as e:
            print(f"Error getting conversation summary with metrics: {str(e)}")
            return {'session_id': session_id, 'error': str(e)}
    
    def clear_session(self, session_id: str):
        """Clear conversation history and EventLoopMetrics for a session."""
        try:
            self.table.delete_item(Key={'session_id': session_id})
            print(f"Cleared conversation history and EventLoopMetrics for session {session_id}")
        except Exception as e:
            print(f"Error clearing session: {str(e)}")
    
    def get_conversation_summary(self, session_id: str) -> Dict[str, Any]:
        """Get summary information about a conversation session (backward compatibility)."""
        return self.get_conversation_with_metrics_summary(session_id)
    
    def load_event_loop_metrics_snapshots(self, session_id: str) -> List[Dict[str, Any]]:
        """Load EventLoopMetrics snapshots from DynamoDB for monitoring."""
        try:
            response = self.event_loop_metrics_table.get_item(Key={'session_id': session_id})
            
            if 'Item' in response and 'metrics_snapshots' in response['Item']:
                snapshots = response['Item']['metrics_snapshots']
                converted_snapshots = self._convert_decimals_to_float(snapshots)
                print(f"Loaded {len(converted_snapshots)} EventLoopMetrics snapshots for session {session_id}")
                return converted_snapshots
            else:
                print(f"No EventLoopMetrics snapshots found for session {session_id}")
                return []
                
        except Exception as e:
            print(f"Error loading EventLoopMetrics snapshots: {str(e)}")
            return []
    
    def get_metrics_summary_for_monitoring(self, session_id: str) -> Dict[str, Any]:
        """Get aggregated metrics summary for monitoring dashboard."""
        try:
            snapshots = self.load_event_loop_metrics_snapshots(session_id)
            
            if not snapshots:
                return {'session_id': session_id, 'has_metrics': False, 'total_snapshots': 0}
            
            # Aggregate basic metrics
            total_cycles = sum(snap['snapshot'].get('raw_metrics', {}).get('cycle_count', 0) for snap in snapshots)
            total_duration = sum(snap['snapshot'].get('raw_metrics', {}).get('total_duration', 0.0) for snap in snapshots)
            total_tokens = sum(snap['snapshot'].get('raw_metrics', {}).get('accumulated_usage', {}).get('totalTokens', 0) for snap in snapshots)
            
            return {
                'session_id': session_id,
                'has_metrics': True,
                'total_snapshots': len(snapshots),
                'aggregated_metrics': {
                    'total_cycles': total_cycles,
                    'total_duration': round(total_duration, 3),
                    'total_tokens': total_tokens,
                    'avg_cycles_per_message': round(total_cycles / len(snapshots), 2) if len(snapshots) > 0 else 0,
                    'avg_duration_per_message': round(total_duration / len(snapshots), 3) if len(snapshots) > 0 else 0,
                    'avg_tokens_per_message': round(total_tokens / len(snapshots), 1) if len(snapshots) > 0 else 0
                },
                'snapshots_timeline': [
                    {
                        'message_number': snap['message_number'],
                        'timestamp': snap['timestamp'],
                        'cycles': snap['snapshot'].get('raw_metrics', {}).get('cycle_count', 0),
                        'duration': snap['snapshot'].get('raw_metrics', {}).get('total_duration', 0.0),
                        'tokens': snap['snapshot'].get('raw_metrics', {}).get('accumulated_usage', {}).get('totalTokens', 0)
                    }
                    for snap in snapshots
                ]
            }
            
        except Exception as e:
            print(f"Error generating metrics summary: {str(e)}")
            return {'session_id': session_id, 'has_metrics': False, 'error': str(e)}
    
    def add_conversation_reset_endpoint(self):
        """
        Utility method to add a conversation reset capability.
        This can be called when users want to start fresh.
        """
        def reset_conversation(session_id: str, user_id: str) -> bool:
            """Reset conversation for a session and start fresh."""
            try:
                self.clear_session(session_id)
                
                # Optionally, you can initialize with a welcome message
                welcome_messages = [
                    {
                        "role": "assistant",
                        "content": "Hello! I'm your AI shopping assistant. How can I help you find products today?"
                    }
                ]
                
                self.save_agent_messages(session_id, user_id, welcome_messages)
                return True
                
            except Exception as e:
                print(f"Error resetting conversation: {str(e)}")
                return False
        
        return reset_conversation
    