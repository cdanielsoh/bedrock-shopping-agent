import boto3
from strands import Agent, tool


def converse_bedrock(
        system_prompt: str,
        user_prompt: str, 
        model_id: str = "us.anthropic.claude-3-7-sonnet-20250219-v1:0", 
        cache_system: bool = False, 
        cache_messages: bool = False
    ):
    bedrock_client = boto3.client(
        service_name='bedrock-runtime',
        region_name='us-west-2'
    )

    system = [
        {
            "text": system_prompt
        }
    ]
    
    if cache_system:
        system.append({
            "cachePoint": {
                "type": "default"
            }
        })

    messages = [
        {
            "role": "user",
            "content": [{"text": user_prompt}]
        }
    ]

    if cache_messages:
        messages[-1]["content"].append({
            "cachePoint": {
                "type": "default"
            }
        })

    response = bedrock_client.converse(
        modelId=model_id,
        system=system,
        messages=messages,
    )

    return response.get('output'), response.get('usage'), response.get('metrics')

if __name__ == "__main__":
    system_prompt = "Whatever the user asks, respond with 1 and 1 only"
    user_prompt = "Test"
    response, usage, metrics = converse_bedrock(system_prompt, user_prompt, cache_system=True, cache_messages=True)
    print(response)
    print(usage)
    print(metrics)