/**
 * API service for monitoring data
 */

export interface ConversationData {
  conversation_id: string;
  handler_type: string;
  session_id: string;
  messages: Array<{
    timestamp: string;
    role: string;
    content: string;
    metadata?: any;
  }>;
  message_count: number;
  updated_at: string;
}

export interface SharedContext {
  session_id: string;
  products: Array<{
    id: string;
    name: string;
    price: number;
    category?: string;
  }>;
  orders: Array<{
    order_id: string;
    status: string;
    timestamp?: string;
  }>;
  user_preferences: Record<string, any>;
  search_history: string[];
  last_updated: string;
}

export interface RouterData {
  session_id: string;
  routing_decisions: Array<{
    timestamp: string;
    assistant_number: string;
    handler_name: string;
    user_message: string;
    routing_decision: string;
    routing_reasoning: string;
    message_id: string;
  }>;
}

export interface PerformanceMetrics {
  session_id: string;
  timestamp: string;
  handler_type: string;
  user_id: string;
  first_token_time: number;
  total_response_time: number;
  input_tokens: number;
  output_tokens: number;
  cache_read_tokens: number;
  cache_write_tokens: number;
  total_cost: number;
  model_id: string;
  use_agent: boolean;
}

interface UserSession {
  session_id: string;
  user_id: string;
  created_at: string;
  last_activity: string;
  message_count: number;
  title?: string;
}

export class MonitoringApiService {
  private baseUrl: string;

  constructor(baseUrl: string) {
    this.baseUrl = baseUrl.replace(/\/$/, '');
  }

  /**
   * Get conversations for a specific session
   */
  async getConversations(sessionId: string): Promise<ConversationData[]> {
    try {
      console.log(`🌐 MonitoringApi.getConversations for session: ${sessionId}`);
      
      const response = await fetch(`${this.baseUrl}/monitoring/conversations/${sessionId}`, {
        method: 'GET',
        headers: {
          'Content-Type': 'application/json',
        },
      });

      if (!response.ok) {
        console.error(`❌ API Error: ${response.status} ${response.statusText}`);
        throw new Error(`Failed to get conversations: ${response.statusText}`);
      }

      const data = await response.json();
      console.log(`📚 Retrieved ${data.conversations?.length || 0} conversations`);
      return data.conversations || [];
    } catch (error) {
      console.error('❌ Error getting conversations:', error);
      return [];
    }
  }

  /**
   * Get shared context for a session
   */
  async getSharedContext(sessionId: string): Promise<SharedContext | null> {
    try {
      console.log(`🌐 MonitoringApi.getSharedContext for session: ${sessionId}`);
      
      const response = await fetch(`${this.baseUrl}/monitoring/context/${sessionId}`, {
        method: 'GET',
        headers: {
          'Content-Type': 'application/json',
        },
      });

      if (!response.ok) {
        console.error(`❌ API Error: ${response.status} ${response.statusText}`);
        throw new Error(`Failed to get shared context: ${response.statusText}`);
      }

      const data = await response.json();
      console.log(`🔗 Retrieved shared context for session ${sessionId}`);
      return data.context || null;
    } catch (error) {
      console.error('❌ Error getting shared context:', error);
      return null;
    }
  }

  /**
   * Get router decisions for a session
   */
  async getRouterData(sessionId: string): Promise<RouterData | null> {
    try {
      console.log(`🌐 MonitoringApi.getRouterData for session: ${sessionId}`);
      
      const response = await fetch(`${this.baseUrl}/monitoring/router/${sessionId}`, {
        method: 'GET',
        headers: {
          'Content-Type': 'application/json',
        },
      });

      if (!response.ok) {
        console.error(`❌ API Error: ${response.status} ${response.statusText}`);
        throw new Error(`Failed to get router data: ${response.statusText}`);
      }

      const data = await response.json();
      console.log(`🧭 Retrieved router data for session ${sessionId}`);
      return data.router_data || null;
    } catch (error) {
      console.error('❌ Error getting router data:', error);
      return null;
    }
  }

  /**
   * Get performance metrics with filters
   */
  async getPerformanceMetrics(filters: {
    userId?: string;
    handlerType?: string;
    timeRange?: string;
    limit?: number;
  }): Promise<PerformanceMetrics[]> {
    try {
      console.log(`🌐 MonitoringApi.getPerformanceMetrics with filters:`, filters);
      
      const params = new URLSearchParams();
      if (filters.userId && filters.userId !== 'all') params.append('user_id', filters.userId);
      if (filters.handlerType && filters.handlerType !== 'all') params.append('handler_type', filters.handlerType);
      if (filters.timeRange) params.append('time_range', filters.timeRange);
      if (filters.limit) params.append('limit', filters.limit.toString());

      const response = await fetch(`${this.baseUrl}/monitoring/performance?${params.toString()}`, {
        method: 'GET',
        headers: {
          'Content-Type': 'application/json',
        },
      });

      if (!response.ok) {
        console.error(`❌ API Error: ${response.status} ${response.statusText}`);
        throw new Error(`Failed to get performance metrics: ${response.statusText}`);
      }

      const data = await response.json();
      console.log(`📊 Retrieved ${data.metrics?.length || 0} performance metrics`);
      return data.metrics || [];
    } catch (error) {
      console.error('❌ Error getting performance metrics:', error);
      return [];
    }
  }

  /**
   * Get all sessions for a user
   */
  async getUserSessions(userId: string): Promise<UserSession[]> {
    try {
      console.log(`🌐 MonitoringApi.getUserSessions for user: ${userId}`);
      
      const response = await fetch(`${this.baseUrl}/monitoring/sessions/${userId}`, {
        method: 'GET',
        headers: {
          'Content-Type': 'application/json',
        },
      });

      if (!response.ok) {
        console.error(`❌ API Error: ${response.status} ${response.statusText}`);
        throw new Error(`Failed to get user sessions: ${response.statusText}`);
      }

      const data = await response.json();
      console.log(`📋 Retrieved ${data.sessions?.length || 0} sessions for user ${userId}:`, data.sessions);
      return data.sessions || [];
    } catch (error) {
      console.error('❌ Error getting user sessions:', error);
      return [];
    }
  }
}

// Factory function to create monitoring API service
export function createMonitoringApi(baseUrl?: string): MonitoringApiService {
  const apiUrl = baseUrl || 'https://mselacy07a.execute-api.us-west-2.amazonaws.com';
  return new MonitoringApiService(apiUrl);
}
