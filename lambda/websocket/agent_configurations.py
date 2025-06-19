"""
Agent configuration examples showing how to use different agent types,
custom tools, and prompts with the Strands Customer Agent system.
"""
from strands_agent_factory import AgentType
from typing import Dict, Any, Optional


class AgentConfigurations:
    """Predefined agent configurations for different use cases."""
    
    @staticmethod
    def get_product_search_config() -> Dict[str, Any]:
        """Standard product search agent configuration."""
        return {
            'agent_type': AgentType.PRODUCT_SEARCH,
            'tools_path': None
        }
    
    @staticmethod
    def get_customer_service_config() -> Dict[str, Any]:
        """Customer service agent configuration."""
        return {
            'agent_type': AgentType.CUSTOMER_SERVICE,
            'tools_path': None
        }
    
    @staticmethod
    def get_general_assistant_config() -> Dict[str, Any]:
        """General assistant configuration."""
        return {
            'agent_type': AgentType.GENERAL_ASSISTANT,
            'tools_path': None
        }

    @staticmethod
    def get_unified_agent_config() -> Dict[str, Any]:
        """Unified agent configuration."""
        return {
            'agent_type': AgentType.UNIFIED,
            'tools_path': None
        }

    @staticmethod
    def get_config_by_intent(intent: str) -> Dict[str, Any]:
        """Get agent configuration based on detected user intent."""
        intent_configs = {
            'product_search': AgentConfigurations.get_product_search_config(),
            'customer_support': AgentConfigurations.get_customer_service_config(),
            'customer_service': AgentConfigurations.get_customer_service_config(),  # Alternative key
            'general': AgentConfigurations.get_general_assistant_config(),
            'unified': AgentConfigurations.get_unified_agent_config(),
            'order_inquiry': AgentConfigurations.get_customer_service_config()  # Map order inquiry to customer service
        }
        
        return intent_configs.get(intent, AgentConfigurations.get_unified_agent_config())


def select_agent_configuration(routing_number: str) -> Dict[str, Any]:
    """
    Select the best agent configuration based on user context and routing.
    
    Args:
        user_context: User context information
        routing_number: Router output number
        
    Returns:
        Agent configuration dictionary
    """
    # Map routing numbers to intents
    intent_map = {
        '1': 'order_inquiry',
        '2': 'product_search',
        '3': 'general',
        '4': 'unified'
    }
    
    intent = intent_map.get(routing_number, 'general')
    
    return AgentConfigurations.get_config_by_intent(intent)
