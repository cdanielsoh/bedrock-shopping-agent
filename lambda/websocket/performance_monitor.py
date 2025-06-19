"""
Performance monitoring utility for tracking operations and token usage
"""

import time
import boto3
import os
from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, Any, Optional
import logging
from contextlib import contextmanager

logger = logging.getLogger(__name__)

class PerformanceMonitor:
    """
    Monitors and records performance metrics for operations and Bedrock API calls
    """
    
    def __init__(self, dynamodb_resource=None):
        self.dynamodb = dynamodb_resource or boto3.resource('dynamodb')
        self.performance_table_name = os.environ.get('PERFORMANCE_METRICS_TABLE')
        self.performance_table = None
        
        if self.performance_table_name:
            self.performance_table = self.dynamodb.Table(self.performance_table_name)
        
        # Operation timing tracking
        self.operations = {}
        self.operation_start_times = {}
        
        # Token tracking for Bedrock calls
        self.start_time = None
        self.first_token_time = None
        self.first_token_received = False
        
        # Token usage
        self.input_tokens = 0
        self.output_tokens = 0
        self.cache_read_tokens = 0
        self.cache_write_tokens = 0
        
        # Request context
        self.session_id = None
        self.user_id = None
        self.handler_type = None
        self.model_id = None
        self.use_agent = False
    
    @contextmanager
    def measure_operation(self, operation_name: str):
        """Context manager to measure operation duration"""
        start_time = time.time()
        self.operation_start_times[operation_name] = start_time
        
        try:
            yield
        finally:
            end_time = time.time()
            duration = end_time - start_time
            self.operations[operation_name] = duration
            logger.debug(f"Operation '{operation_name}' took {duration:.3f} seconds")
    
    def log_summary(self, connection_id: str = None):
        """Log performance summary"""
        if not self.operations:
            logger.info("No operations to log")
            return
        
        total_time = sum(self.operations.values())
        logger.info(f"Performance Summary for {connection_id or 'session'}:")
        logger.info(f"  Total time: {total_time:.3f}s")
        
        for operation, duration in self.operations.items():
            percentage = (duration / total_time) * 100 if total_time > 0 else 0
            logger.info(f"  {operation}: {duration:.3f}s ({percentage:.1f}%)")
    
    def start_request(self, session_id: str, user_id: str, handler_type: str, 
                     model_id: str = None, use_agent: bool = False, request_start_time: Optional[float] = None):
        """Start monitoring a Bedrock request"""
        self.start_time = request_start_time or time.time()
        self.first_token_time = None
        self.first_token_received = False
        
        self.session_id = session_id
        self.user_id = user_id
        self.handler_type = handler_type
        self.model_id = model_id or "unknown"
        self.use_agent = use_agent
        
        # Reset token counters
        self.input_tokens = 0
        self.output_tokens = 0
        self.cache_read_tokens = 0
        self.cache_write_tokens = 0
        
        logger.info(f"Started performance monitoring for {handler_type} - User: {user_id}, Session: {session_id}")
    
    def record_first_token(self):
        """Record when the first token is received"""
        if not self.first_token_received and self.start_time:
            self.first_token_time = time.time()
            self.first_token_received = True
            first_token_latency = (self.first_token_time - self.start_time) * 1000  # Convert to ms
            logger.info(f"First token received after {first_token_latency:.2f}ms")
    
    def update_token_usage(self, usage_data: Dict[str, Any]):
        """Update token usage from Bedrock response"""
        if not usage_data:
            return
        
        # Handle different response formats
        if 'usage' in usage_data:
            usage = usage_data['usage']
        else:
            usage = usage_data
        
        # Update token counts
        self.input_tokens += usage.get('inputTokens', 0)
        self.output_tokens += usage.get('outputTokens', 0)
        
        # Handle cache tokens if available
        if 'cacheReadInputTokens' in usage:
            self.cache_read_tokens += usage.get('cacheReadInputTokens', 0)
        if 'cacheCreationInputTokens' in usage:
            self.cache_write_tokens += usage.get('cacheCreationInputTokens', 0)
        
        logger.debug(f"Updated token usage - Input: {self.input_tokens}, Output: {self.output_tokens}")
    
    def calculate_cost(self) -> float:
        """Calculate estimated cost based on token usage and model"""
        # Pricing per 1K tokens (approximate)
        pricing = {
            'claude-3-5-haiku': {'input': 0.00025, 'output': 0.00125},
            'claude-3-5-sonnet': {'input': 0.003, 'output': 0.015},
            'claude-3-opus': {'input': 0.015, 'output': 0.075}
        }
        
        # Default pricing if model not found
        default_pricing = {'input': 0.0008, 'output': 0.004}
        
        model_pricing = pricing.get(self.model_id.lower(), default_pricing)
        
        input_cost = (self.input_tokens / 1000) * model_pricing['input']
        output_cost = (self.output_tokens / 1000) * model_pricing['output']
        
        # Cache reads are typically cheaper
        cache_read_cost = (self.cache_read_tokens / 1000) * (model_pricing['input'] * 0.1)
        cache_write_cost = (self.cache_write_tokens / 1000) * (model_pricing['input'] * 0.25)
        
        total_cost = input_cost + output_cost + cache_read_cost + cache_write_cost
        return round(total_cost, 6)
    
    def finish_request(self, success: bool = True) -> Dict[str, Any]:
        """Finish monitoring and save metrics"""
        if not self.start_time:
            logger.warning("Performance monitoring not started")
            return {}
        
        end_time = time.time()
        total_response_time = (end_time - self.start_time) * 1000  # Convert to ms
        
        # Calculate first token time
        first_token_latency = 0
        if self.first_token_time:
            first_token_latency = (self.first_token_time - self.start_time) * 1000
        
        # Calculate cost
        total_cost = self.calculate_cost()
        
        metrics = {
            'metric_id': f"{self.session_id}#{int(time.time() * 1000)}",
            'session_id': self.session_id,
            'user_id': self.user_id,
            'handler_type': self.handler_type,
            'model_id': self.model_id,
            'use_agent': self.use_agent,
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'first_token_time': Decimal(str(round(first_token_latency, 2))),
            'total_response_time': Decimal(str(round(total_response_time, 2))),
            'input_tokens': self.input_tokens,
            'output_tokens': self.output_tokens,
            'cache_read_tokens': self.cache_read_tokens,
            'cache_write_tokens': self.cache_write_tokens,
            'total_cost': Decimal(str(total_cost)),
            'success': success,
            'ttl': int(datetime.now(timezone.utc).timestamp()) + (30 * 24 * 60 * 60)  # 30 days
        }
        
        # Save to DynamoDB
        if self.performance_table:
            try:
                self.performance_table.put_item(Item=metrics)
                logger.info(f"Saved performance metrics - First token: {first_token_latency:.2f}ms, "
                           f"Total: {total_response_time:.2f}ms, Tokens: {self.input_tokens}→{self.output_tokens}, "
                           f"Cost: ${total_cost:.6f}")
            except Exception as e:
                logger.error(f"Failed to save performance metrics: {str(e)}")
        else:
            logger.warning("Performance metrics table not configured")
        
        return metrics
    
    def record_streaming_token(self, token_text: str = ""):
        """Record a streaming token (for first token timing)"""
        if not self.first_token_received:
            self.record_first_token()


# Global performance monitor instance
performance_monitor = PerformanceMonitor()


def monitor_bedrock_request(session_id: str, user_id: str, handler_type: str, 
                           model_id: str = None, use_agent: bool = False):
    """Decorator to monitor Bedrock requests"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            performance_monitor.start_request(session_id, user_id, handler_type, model_id, use_agent)
            
            try:
                result = func(*args, **kwargs)
                performance_monitor.finish_request(success=True)
                return result
            except Exception as e:
                performance_monitor.finish_request(success=False)
                raise e
        
        return wrapper
    return decorator


class StreamingPerformanceMonitor:
    """
    Context manager for monitoring streaming responses
    """
    
    def __init__(self, session_id: str, user_id: str, handler_type: str, 
                 model_id: str = None, use_agent: bool = False, request_start_time: Optional[float] = None):
        self.session_id = session_id
        self.user_id = user_id
        self.handler_type = handler_type
        self.model_id = model_id
        self.use_agent = use_agent
        self.request_start_time = request_start_time
    
    def __enter__(self):
        performance_monitor.start_request(
            self.session_id, self.user_id, self.handler_type, 
            self.model_id, self.use_agent, self.request_start_time
        )
        return performance_monitor
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        success = exc_type is None
        performance_monitor.finish_request(success=success)
        return False
