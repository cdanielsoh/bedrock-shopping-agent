import boto3
from strands import Agent, tool
from typing import Union, List, Dict, Optional
import copy

def converse_bedrock(
    system_prompt: str,
    message: Union[str, List[Dict]], 
    model_id: str = "us.anthropic.claude-3-5-sonnet-20241022-v2:0", 
    cache_system: bool = False, 
    cache_messages: bool = False,
    tool_config: Optional[Union[Dict, List[Dict]]] = None,
    inference_config: Optional[Dict] = None,
    region_name: str = "us-west-2"
):
    """
    Converse with Claude via AWS Bedrock.
    
    Args:
        system_prompt: System prompt for the conversation
        message: Either a string message or list of message dictionaries
        model_id: Bedrock model ID to use
        cache_system: Whether to cache the system prompt
        cache_messages: Whether to cache messages
        tool_config: Tool configuration - can be:
            - Single tool dict
            - List of tool dicts  
            - Dict with "tools" key containing list of tools
        inference_config: Inference configuration (temperature, etc.)
        region_name: AWS region
    
    Returns:
        Bedrock response object
    """
    
    # Initialize client
    bedrock_client = boto3.client(
        service_name='bedrock-runtime',
        region_name=region_name
    )
    
    # Build system configuration
    system = _build_system_config(system_prompt, cache_system)
    
    # Build messages configuration
    messages = _build_messages_config(message, cache_messages)
    
    # Build request parameters
    request_params = {
        "modelId": model_id,
        "system": system,
        "messages": messages
    }
    
    # Add optional parameters
    if inference_config:
        request_params["inferenceConfig"] = inference_config
    
    if tool_config:
        request_params["toolConfig"] = _build_tool_config(tool_config)
    
    # Make the API call
    return bedrock_client.converse(**request_params)

def _build_tool_config(tool_config: Union[Dict, List[Dict]]) -> Dict:
    """Build tool configuration, handling both single tools and lists of tools."""
    
    if isinstance(tool_config, dict):
        # Single tool definition
        if "tools" in tool_config:
            # Already properly formatted
            return tool_config
        else:
            # Single tool, wrap in tools array
            return {"tools": [tool_config]}
    
    elif isinstance(tool_config, list):
        # List of tools
        return {"tools": tool_config}


def _build_system_config(system_prompt: str, cache_system: bool) -> List[Dict]:
    """Build system configuration with optional caching."""
    system = [{"text": system_prompt}]
    
    if cache_system:
        system.append({"cachePoint": {"type": "default"}})
    
    return system


def _build_messages_config(message: Union[str, List[Dict]], cache_messages: bool) -> List[Dict]:
    """Build messages configuration with optional caching."""
    
    if isinstance(message, str):
        messages = [{
            "role": "user",
            "content": [{"text": message}]
        }]
    else:
        messages = copy.deepcopy(message)
        
        for msg in messages:
            msg["content"] = [
                item for item in msg["content"] 
                if not (isinstance(item, dict) and "cachePoint" in item)
            ]
    
    # Add cache points if requested
    if cache_messages and messages:
        _add_cache_points(messages)
    
    return messages


def _add_cache_points(messages: List[Dict]) -> None:
    """Add cache points to messages."""
    cache_point = {"cachePoint": {"type": "default"}}
    
    # Cache the last message
    if messages:
        messages[-1]["content"].append(cache_point)
    
    # Cache the third-to-last message if it exists
    if len(messages) >= 3:
        messages[-3]["content"].append(cache_point)

if __name__ == "__main__":
    system_prompt = "Whatever the user asks, respond with 1 and 1 only"
    user_prompt = "Test"
    response= converse_bedrock(system_prompt, user_prompt, cache_system=False, cache_messages=False)
    print(response)