"""
Factory for creating different types of Strands agents with configurable tools and prompts.
"""
import os
import importlib.util
from typing import Dict, List, Any, Optional, Callable
from strands import Agent, tool
from strands.models import BedrockModel
from resource_manager import resource_manager
from prompts import PRODUCT_SEARCH_AGENT_PROMPT, CUSTOMER_SERVICE_AGENT_PROMPT, \
    GENERAL_ASSISTANT_AGENT_PROMPT, UNIFIED_AGENT_PROMPT
import logging

# Import tools at module level to avoid import issues
from tools import GetOrderHistoryTool, GetUserInfoTool

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

class AgentType:
    """Agent type constants."""
    PRODUCT_SEARCH = "product_search"
    CUSTOMER_SERVICE = "customer_service"
    GENERAL_ASSISTANT = "general_assistant"
    UNIFIED = "unified"

class StrandsAgentFactory:
    """Factory for creating different types of Strands agents."""
    
    def __init__(self):
        self.rm = resource_manager
    
    def create_agent(self, 
                    agent_type: str,
                    user_context: Dict[str, Any],
                    tools_path: Optional[str] = None) -> Agent:
        """
        Create a Strands agent with specified configuration.
        
        Args:
            agent_type: Type of agent to create
            user_context: User context for personalization
            tools_path: Path to custom tools module
            
        Returns:
            Configured Strands Agent
        """
        # Get system prompt for agent type
        system_prompt = self._load_system_prompt(agent_type, user_context)
        
        # Load tools
        tools = self._load_tools(agent_type, tools_path)

        logger.info(f"Initializing {agent_type} agent with {len(tools)} tools")

        if tools:
            return Agent(
                system_prompt=system_prompt,
                tools=tools,
                model=BedrockModel(
                    model_id="us.anthropic.claude-3-5-haiku-20241022-v1:0",
                    cache_prompt="default",
                    cache_tools="default"
                )
            )
    
        else:
            return Agent(
                system_prompt=system_prompt,
                model=BedrockModel(
                    model_id="us.anthropic.claude-3-5-haiku-20241022-v1:0",
                    cache_prompt="default",
                    cache_tools="default"
                )
            )
    
    def _load_system_prompt(self, agent_type: str, user_context: Dict[str, Any]) -> str:
        """Load system prompt for agent type."""
        prompts = {
            AgentType.PRODUCT_SEARCH: self._get_product_search_prompt(user_context),
            AgentType.CUSTOMER_SERVICE: self._get_customer_service_prompt(user_context),
            AgentType.GENERAL_ASSISTANT: self._get_general_assistant_prompt(user_context),
            AgentType.UNIFIED: self._get_unified_agent_prompt(user_context)
        }
        return prompts.get(agent_type, prompts[AgentType.GENERAL_ASSISTANT])
    
    def _load_tools(self, agent_type: str, tools_path: Optional[str] = None) -> List[Callable]:
        """Load tools for agent type."""
        if tools_path:
            return self._load_tools_from_path(tools_path)
        
        # Default tools based on agent type
        tool_map = {
            AgentType.PRODUCT_SEARCH: self._get_product_search_tools(),
            AgentType.CUSTOMER_SERVICE: self._get_customer_service_tools(),
            AgentType.GENERAL_ASSISTANT: self._get_general_tools(),
            AgentType.UNIFIED: self._get_product_search_tools()
        }
        
        return tool_map.get(agent_type, [])
    
    def _get_product_search_tools(self) -> List[Callable]:
        """Get product search tools."""
        @tool
        def keyword_product_search(query_keywords: str) -> list[dict]:
            """Search for products by keywords."""
            from tools import KeywordProductSearchTool
            
            tool_instance = KeywordProductSearchTool(
                os_host=self.rm.os_host,
                index=self.rm.os_index,
                cloudfront_url=self.rm.images_cloudfront_url,
                dynamodb=self.rm.dynamodb_resource,
                reviews_table=self.rm.reviews_table_name
            )
            
            return tool_instance.execute(query_keywords)
        
        return [keyword_product_search]
    
    def _get_customer_service_tools(self) -> List[Callable]:
        """Get customer service tools."""
        # @tool
        # def get_order_history(user_id: str) -> list[dict]:
        #     """Get order history for a user."""
        #     from tools import GetOrderHistoryTool
            
        #     tool_instance = GetOrderHistoryTool(
        #         orders_table=self.rm.orders_table_name,
        #         oss_client=self.rm.opensearch_client,
        #         index=self.rm.os_index
        #     )
            
        #     return tool_instance.execute(user_id)
        
        # @tool
        # def get_user_info(user_id: str) -> dict:
        #     """Get user info for a user."""
        #     from tools import GetUserInfoTool
            
        #     tool_instance = GetUserInfoTool(
        #         user_table=self.rm.users_table_name
        #     )
            
        #     return tool_instance.execute(user_id)
        
        # return [get_order_history, get_user_info]
        return [] # Information is already in the system prompt -> Reduce latency
    
    def _get_general_tools(self) -> List[Callable]:
        """Get general purpose tools."""
        return []  # No tools for general assistant
    
    def _get_product_search_prompt(self, user_context: Dict[str, Any]) -> str:
        """Product search agent prompt."""
        return PRODUCT_SEARCH_AGENT_PROMPT.format(
            order_history=self._prefetch_order_history(user_context.get('user_id', 'unknown')),
            user_info=self._prefetch_user_info(user_context.get('user_id', 'unknown'))
        )
    
    def _get_customer_service_prompt(self, user_context: Dict[str, Any]) -> str:
        """Customer service agent prompt. Prepopulate system prompt with order history and user info."""
        return CUSTOMER_SERVICE_AGENT_PROMPT.format(
            order_history=self._prefetch_order_history(user_context.get('user_id', 'unknown')),
            user_info=self._prefetch_user_info(user_context.get('user_id', 'unknown'))
        )

    def _get_general_assistant_prompt(self, user_context: Dict[str, Any]) -> str:
        """General assistant prompt."""
        return GENERAL_ASSISTANT_AGENT_PROMPT.format(
            user_id=user_context.get('user_id', 'unknown'),
            user_persona=user_context.get('user_persona', 'general'),
            user_discount_persona=user_context.get('user_discount_persona', 'regular'),
            user_name=user_context.get('user_name', ''),
            user_age=user_context.get('user_age', ''),
            user_gender=user_context.get('user_gender', '')
        )

    def _get_unified_agent_prompt(self, user_context: Dict[str, Any]) -> str:
        """Unified agent prompt. Prepopulate system prompt with order history and user info."""
        return UNIFIED_AGENT_PROMPT.format(
            user_info=self._prefetch_user_info(user_context.get('user_id', 'unknown')),
            order_history=self._prefetch_order_history(user_context.get('user_id', 'unknown'))
        )

    def _prefetch_user_info(self, user_id: str) -> Dict[str, Any]:
        """Prefetch user info for a user."""
        from tools import GetUserInfoTool
        return GetUserInfoTool(
            user_table=self.rm.users_table_name
        ).execute(user_id)

    def _prefetch_order_history(self, user_id: str) -> List[Dict[str, Any]]:
        """Prefetch order history for a user."""
        from tools import GetOrderHistoryTool
        return GetOrderHistoryTool(
            orders_table=self.rm.orders_table_name,
            oss_client=self.rm.opensearch_client,
            index=self.rm.os_index).execute(user_id)
    

# Global factory instance
agent_factory = StrandsAgentFactory()
