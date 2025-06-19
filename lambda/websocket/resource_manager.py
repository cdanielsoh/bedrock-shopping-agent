"""
Shared resource manager for WebSocket handlers to improve efficiency
and reduce initialization overhead.
"""
import boto3
import os
from opensearchpy import OpenSearch, RequestsHttpConnection, AWSV4SignerAuth

class ResourceManager:
    """Singleton resource manager for AWS services and clients."""
    
    _instance = None
    _initialized = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not self._initialized:
            self._setup_resources()
            ResourceManager._initialized = True
    
    def _setup_resources(self):
        """Initialize all AWS resources and clients."""
        # Environment variables
        self.region = os.environ.get('REGION', 'us-west-2')
        self.os_endpoint = os.environ.get('OPENSEARCH_ENDPOINT', '5np3mnj9qh1jiqt03wd3.us-west-2.aoss.amazonaws.com')
        self.os_host = self.os_endpoint if not self.os_endpoint.startswith('https://') else self.os_endpoint.replace('https://', '')
        self.os_index = os.environ.get('OPENSEARCH_INDEX', 'products')
        
        # Table names
        self.orders_table_name = os.environ.get('ORDERS_TABLE', 'OrdersTable')
        self.reviews_table_name = os.environ.get('REVIEWS_TABLE', 'ReviewsTable')
        self.users_table_name = os.environ.get('USERS_TABLE', 'UsersTable')
        self.chat_history_table_name = os.environ.get('CHAT_HISTORY_TABLE')
        self.agent_conversations_table_name = os.environ.get('AGENT_CONVERSATIONS_TABLE', 'AgentConversationsTable')
        self.agent_event_loop_metrics_table_name = os.environ.get('AGENT_EVENT_LOOP_METRICS_TABLE', 'AgentEventLoopMetricsTable')
        self.connections_table_name = os.environ.get('CONNECTIONS_TABLE')
        
        # CloudFront URL
        self.images_cloudfront_url = os.environ.get('IMAGES_CLOUDFRONT_URL')
        
        # Initialize clients
        self._session = boto3.Session()
        self._credentials = self._session.get_credentials()
        
        # Bedrock client
        self._bedrock_client = None
        
        # DynamoDB resources
        self._dynamodb_resource = None
        self._orders_table = None
        self._reviews_table = None
        self._users_table = None
        self._chat_history_table = None
        self._agent_conversations_table = None
        self._connections_table = None
        
        # OpenSearch client
        self._opensearch_client = None
        
        # API Gateway Management client (will be set per request)
        self._apigw_management_client = None
    
    @property
    def bedrock_client(self):
        """Lazy-loaded Bedrock client."""
        if self._bedrock_client is None:
            self._bedrock_client = boto3.client("bedrock-runtime", region_name=self.region)
        return self._bedrock_client
    
    @property
    def dynamodb_resource(self):
        """Lazy-loaded DynamoDB resource."""
        if self._dynamodb_resource is None:
            self._dynamodb_resource = boto3.resource('dynamodb', region_name=self.region)
        return self._dynamodb_resource
    
    @property
    def orders_table(self):
        """Lazy-loaded Orders table."""
        if self._orders_table is None:
            self._orders_table = self.dynamodb_resource.Table(self.orders_table_name)
        return self._orders_table
    
    @property
    def reviews_table(self):
        """Lazy-loaded Reviews table."""
        if self._reviews_table is None:
            self._reviews_table = self.dynamodb_resource.Table(self.reviews_table_name)
        return self._reviews_table
    
    @property
    def users_table(self):
        """Lazy-loaded Users table."""
        if self._users_table is None:
            self._users_table = self.dynamodb_resource.Table(self.users_table_name)
        return self._users_table
    
    @property
    def chat_history_table(self):
        """Lazy-loaded Chat History table."""
        if self._chat_history_table is None and self.chat_history_table_name:
            self._chat_history_table = self.dynamodb_resource.Table(self.chat_history_table_name)
        return self._chat_history_table
    
    @property
    def agent_conversations_table(self):
        """Lazy-loaded Agent Conversations table."""
        if self._agent_conversations_table is None:
            self._agent_conversations_table = self.dynamodb_resource.Table(self.agent_conversations_table_name)
        return self._agent_conversations_table
    
    @property
    def connections_table(self):
        """Lazy-loaded Connections table."""
        if self._connections_table is None and self.connections_table_name:
            self._connections_table = self.dynamodb_resource.Table(self.connections_table_name)
        return self._connections_table
    
    @property
    def opensearch_client(self):
        """Lazy-loaded OpenSearch client."""
        if self._opensearch_client is None:
            auth = AWSV4SignerAuth(self._credentials, self.region, 'aoss')
            self._opensearch_client = OpenSearch(
                hosts=[{'host': self.os_host, 'port': 443}],
                http_auth=auth,
                use_ssl=True,
                verify_certs=True,
                http_compress=True,
                connection_class=RequestsHttpConnection,
                pool_maxsize=30,
                timeout=30,
                max_retries=3,
                retry_on_timeout=True
            )
        return self._opensearch_client
    
    def get_apigw_management_client(self, endpoint_url: str):
        """Get API Gateway Management client for specific endpoint."""
        return boto3.client('apigatewaymanagementapi', endpoint_url=endpoint_url)
    
    def validate_connection(self, connection_id: str) -> bool:
        """Validate if a WebSocket connection is still active."""
        if not self.connections_table:
            return True  # Assume valid if no connections table
        
        try:
            response = self.connections_table.get_item(Key={'connectionId': connection_id})
            return 'Item' in response
        except Exception as e:
            print(f"Error validating connection {connection_id}: {str(e)}")
            return False

# Global instance
resource_manager = ResourceManager()
