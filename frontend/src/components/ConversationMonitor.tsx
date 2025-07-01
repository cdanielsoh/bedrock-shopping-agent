import React, { useState, useEffect } from 'react';
import { createMonitoringApi } from '../services/monitoringApi';
import { users, getUserDisplayName } from '../data/users';
import './ConversationMonitor.css';

interface ConversationData {
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

interface SharedContext {
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
  search_history: Array<string | { searched_at?: string; query?: string; [key: string]: any }>;
  last_updated: string;
}

interface RouterData {
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

interface UserSession {
  session_id: string;
  user_id: string;
  created_at: string;
  last_activity: string;
  message_count: number;
  title?: string;
}

const ConversationMonitor: React.FC = () => {
  const [selectedUserId, setSelectedUserId] = useState<string>('15');
  const [selectedSessionId, setSelectedSessionId] = useState<string>('');
  const [userSessions, setUserSessions] = useState<UserSession[]>([]);  // Changed from string[] to UserSession[]
  const [conversations, setConversations] = useState<ConversationData[]>([]);
  const [sharedContext, setSharedContext] = useState<SharedContext | null>(null);
  const [routerData, setRouterData] = useState<RouterData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string>('');

  // Create user options with display names
  const userOptions = [
    { id: 'all', name: 'All Users' },
    ...users.map(user => ({
      id: user.id,
      name: getUserDisplayName(user)
    }))
  ];

  // Load user sessions when user changes
  useEffect(() => {
    loadUserSessions();
  }, [selectedUserId]);

  // Load conversation data when session changes
  useEffect(() => {
    if (selectedSessionId) {
      loadConversationData();
    }
  }, [selectedSessionId]);

  const loadUserSessions = async () => {
    try {
      setLoading(true);
      console.log(`🌐 Loading sessions for user: ${selectedUserId}`);
      
      // Use the monitoring API to get user sessions
      const monitoringApi = createMonitoringApi();
      const sessions = await monitoringApi.getUserSessions(selectedUserId);
      
      console.log(`📋 Retrieved ${sessions.length} sessions for user ${selectedUserId}:`, sessions);
      
      // Validate sessions data
      const validSessions = sessions.filter(session => session && session.session_id);
      if (validSessions.length !== sessions.length) {
        console.warn(`⚠️ Filtered out ${sessions.length - validSessions.length} invalid sessions`);
      }
      
      setUserSessions(validSessions);
      
      if (validSessions.length > 0 && !selectedSessionId) {
        setSelectedSessionId(validSessions[0].session_id);  // Use session_id property instead of entire object
        console.log(`🎯 Auto-selected first session: ${validSessions[0].session_id}`);
      }
    } catch (err) {
      console.error('❌ Error loading sessions:', err);
      setError(`Failed to load sessions: ${err}`);
      setUserSessions([]);  // Clear sessions on error
    } finally {
      setLoading(false);
    }
  };

  const loadConversationData = async () => {
    try {
      setLoading(true);
      setError('');

      // Load conversations, shared context, and router data
      await Promise.all([
        loadConversations(),
        loadSharedContext(),
        loadRouterData()
      ]);

    } catch (err) {
      setError(`Failed to load conversation data: ${err}`);
    } finally {
      setLoading(false);
    }
  };

  const loadConversations = async () => {
    console.log(`🌐 Loading conversations for session: ${selectedSessionId}`);
    
    const monitoringApi = createMonitoringApi();
    const conversations = await monitoringApi.getConversations(selectedSessionId);
    
    console.log(`💬 Retrieved ${conversations.length} conversations`);
    setConversations(conversations);
  };

  const loadSharedContext = async () => {
    console.log(`🌐 Loading shared context for session: ${selectedSessionId}`);
    
    const monitoringApi = createMonitoringApi();
    const context = await monitoringApi.getSharedContext(selectedSessionId);
    
    console.log(`🔗 Retrieved shared context:`, context);
    setSharedContext(context);
  };

  const loadRouterData = async () => {
    console.log(`🌐 Loading router data for session: ${selectedSessionId}`);
    
    const monitoringApi = createMonitoringApi();
    const routerData = await monitoringApi.getRouterData(selectedSessionId);
    
    console.log(`🧭 Retrieved router data:`, routerData);
    setRouterData(routerData);
  };

  const formatTimestamp = (timestamp: string) => {
    return new Date(timestamp).toLocaleString();
  };

  const formatJSON = (obj: any) => {
    return JSON.stringify(obj, null, 2);
  };

  return (
    <div className="conversation-monitor">
      <div className="monitor-header">
        <h1>🔍 Conversation Monitor</h1>
        <p>Monitor conversations, shared context, and routing decisions</p>
      </div>

      <div className="monitor-controls">
        <div className="control-group">
          <label htmlFor="user-select">User:</label>
          <select
            id="user-select"
            value={selectedUserId}
            onChange={(e) => setSelectedUserId(e.target.value)}
          >
            {userOptions.map(user => (
              <option key={user.id} value={user.id}>
                {user.name}
              </option>
            ))}
          </select>
        </div>

        <div className="control-group">
          <label htmlFor="session-select">Session:</label>
          <select
            id="session-select"
            value={selectedSessionId}
            onChange={(e) => setSelectedSessionId(e.target.value)}
            disabled={userSessions.length === 0}
          >
            <option value="">Select a session</option>
            {userSessions.map(session => (
              <option key={session.session_id} value={session.session_id}>
                {(session.session_id || 'Unknown').replace('session_', '').substring(0, 12)}... ({session.message_count || 0} messages)
              </option>
            ))}
          </select>
        </div>

        <button onClick={loadConversationData} disabled={loading || !selectedSessionId}>
          {loading ? 'Loading...' : 'Refresh Data'}
        </button>
      </div>

      {error && (
        <div className="error-message">
          ❌ {error}
        </div>
      )}

      {selectedSessionId && (
        <div className="monitor-content">
          {/* Router Decisions */}
          <div className="monitor-section">
            <h2>🧭 Router Decisions</h2>
            {routerData ? (
              <div className="router-data">
                {(routerData.routing_decisions || []).map((decision, index) => (
                  <div key={index} className="routing-decision">
                    <div className="decision-header">
                      <span className="timestamp">{formatTimestamp(decision.timestamp)}</span>
                      <span className={`handler-badge handler-${decision.assistant_number}`}>
                        {decision.handler_name || `Handler ${decision.assistant_number}`}
                      </span>
                      <span className="assistant-number">#{decision.assistant_number}</span>
                    </div>
                    <div className="user-message">
                      <strong>User:</strong> "{decision.user_message}"
                    </div>
                    <div className="routing-result">
                      <strong>Decision:</strong> {decision.routing_decision}
                    </div>
                    {decision.routing_reasoning && (
                      <div className="reasoning">
                        <strong>Reasoning:</strong> {decision.routing_reasoning}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            ) : (
              <div className="no-data">No router data available</div>
            )}
          </div>

          {/* Handler Conversations */}
          <div className="monitor-section">
            <h2>💬 Handler Conversations</h2>
            <div className="conversations-grid">
              {conversations.map(conv => (
                <div key={conv.conversation_id} className="conversation-card">
                  <div className="conversation-header">
                    <h3>{conv.handler_type.replace('_', ' ').toUpperCase()}</h3>
                    <span className="message-count">{conv.message_count} messages</span>
                  </div>
                  
                  <div className="messages-list">
                    {conv.messages.map((message, index) => (
                      <div key={index} className={`message ${message.role}`}>
                        <div className="message-header">
                          <span className="role">{message.role}</span>
                          <span className="timestamp">{formatTimestamp(message.timestamp)}</span>
                        </div>
                        <div className="message-content">{message.content}</div>
                        {message.metadata && (
                          <details className="message-metadata">
                            <summary>Metadata</summary>
                            <pre>{formatJSON(message.metadata)}</pre>
                          </details>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Shared Context */}
          <div className="monitor-section">
            <h2>🔗 Shared Context</h2>
            {sharedContext ? (
              <div className="shared-context">
                <div className="context-grid">
                  <div className="context-card">
                    <h4>🛍️ Products ({(sharedContext.products || []).length})</h4>
                    <div className="products-list">
                      {(sharedContext.products || []).map(product => (
                        <div key={product.id} className="product-item">
                          <span className="product-name">{product.name}</span>
                          <span className="product-price">${product.price}</span>
                          <span className="product-category">{product.category}</span>
                        </div>
                      ))}
                    </div>
                  </div>

                  <div className="context-card">
                    <h4>📦 Orders ({(sharedContext.orders || []).length})</h4>
                    <div className="orders-list">
                      {(sharedContext.orders || []).map(order => (
                        <div key={order.order_id} className="order-item">
                          <span className="order-id">{order.order_id}</span>
                          <span className={`order-status ${order.status}`}>{order.status}</span>
                          {order.timestamp && (
                            <span className="order-date">
                              {formatTimestamp(order.timestamp)}
                            </span>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>

                  <div className="context-card">
                    <h4>⚙️ User Preferences</h4>
                    <div className="preferences-list">
                      {Object.entries(sharedContext.user_preferences || {}).map(([key, value]) => (
                        <div key={key} className="preference-item">
                          <span className="pref-key">{key}:</span>
                          <span className="pref-value">{String(value)}</span>
                        </div>
                      ))}
                    </div>
                  </div>

                  <div className="context-card">
                    <h4>🔍 Search History</h4>
                    <div className="search-history">
                      {(sharedContext.search_history || []).map((term, index) => (
                        <span key={index} className="search-term">
                          {typeof term === 'string' ? term : (term as any)?.query || JSON.stringify(term)}
                        </span>
                      ))}
                    </div>
                  </div>
                </div>

                <div className="context-meta">
                  <p>Last updated: {sharedContext.last_updated ? formatTimestamp(sharedContext.last_updated) : 'Never'}</p>
                </div>
              </div>
            ) : (
              <div className="no-data">No shared context available</div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

export default ConversationMonitor;
