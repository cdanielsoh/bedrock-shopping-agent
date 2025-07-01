from enum import Enum


class BedrockModelId(Enum):

    # Anthropic Claude
    CLAUDE_4_SONNET_1_0 = "us.anthropic.claude-sonnet-4-20250514-v1:0"
    CLAUDE_3_7_SONNET_1_0 = "us.anthropic.claude-3-7-sonnet-20250219-v1:0"
    CLAUDE_3_5_SONNET_1_0 = "us.anthropic.claude-3-5-sonnet-20240620-v1:0"
    CLAUDE_3_5_HAIKU_1_0 = "us.anthropic.claude-3-5-haiku-20241022-v1:0"

    # Amazon Nova
    AMAZON_NOVA_PREMIER = "us.amazon.nova-premier-v1:0"
    AMAZON_NOVA_PRO = "us.amazon.nova-pro-v1:0"
    AMAZON_NOVA_LITE = "us.amazon.nova-lite-v1:0"
    AMAZON_NOVA_MICRO = "us.amazon.nova-micro-v1:0"
