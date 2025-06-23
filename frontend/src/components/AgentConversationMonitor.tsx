import React, { useState, useEffect } from 'react';
import { users, getUserDisplayName } from '../data/users';
import './AgentConversationMonitor.css';

interface AgentMessage {
  timestamp: string;
  role: string;
  content: string;
  message_id: string;
  metadata: {
    agent_type?: string;
    tool_use?: boolean;
    tool_name?: string;
    tool_input?: any;
    tool_result?: any;
  };
}

interface AgentMetadata {
  total_messages: number;
  user_messages: number;
  assistant_messages: number;
  tool_executions: number;
  agent_types_used: string[];
  conversation_duration: number | null;
  last_activity: string | null;
}

interface AgentConversationData {
  session_id: string;
  agent_messages: AgentMessage[];
  agent_metadata: AgentMetadata;
  event_loop_metrics: EventLoopMetricsSummary;
  has_metrics: boolean;
  retrieved_at: string;
  error?: string;
}

// Helper function to safely extract text content from various message formats
const extractTextContent = (content: any): string => {
  if (typeof content === 'string') {
    return content;
  }
  
  if (Array.isArray(content)) {
    // Handle array of content objects (Strands format)
    const textParts: string[] = [];
    for (const item of content) {
      if (typeof item === 'string') {
        textParts.push(item);
      } else if (typeof item === 'object' && item !== null) {
        if ('text' in item) {
          textParts.push(item.text);
        } else if ('toolUse' in item) {
          textParts.push(`[Tool: ${item.toolUse?.name || 'unknown'}]`);
        } else if ('toolResult' in item) {
          textParts.push('[Tool Result]');
        } else {
          textParts.push(JSON.stringify(item));
        }
      }
    }
    return textParts.join(' ');
  }
  
  if (typeof content === 'object' && content !== null) {
    if ('text' in content) {
      return content.text;
    }
    return JSON.stringify(content);
  }
  
  return String(content || '');
};

interface EventLoopMetricsSummary {
  session_id: string;
  has_metrics: boolean;
  total_snapshots: number;
  aggregated_metrics?: {
    total_cycles: number;
    total_duration: number;
    total_tokens: number;
    avg_cycles_per_message: number;
    avg_duration_per_message: number;
    avg_tokens_per_message: number;
  };
  snapshots_timeline?: Array<{
    message_number: number;
    timestamp: string;
    cycles: number;
    duration: number;
    tokens: number;
  }>;
  error?: string;
}

interface UserSession {
  session_id: string;
  user_id: string;
  created_at: string;
  last_activity: string;
  message_count: number;
  title?: string;
}

export const AgentConversationMonitor: React.FC = () => {
  const [selectedUserId, setSelectedUserId] = useState<string>('');
  const [selectedSessionId, setSelectedSessionId] = useState<string>('');
  const [userSessions, setUserSessions] = useState<UserSession[]>([]);
  const [agentData, setAgentData] = useState<AgentConversationData | null>(null);
  const [loading, setLoading] = useState(false);
  const [sessionsLoading, setSessionsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Create user options with display names
  const userOptions = [
    { id: '', name: 'Select a user...' },
    ...users.map(user => ({
      id: user.id,
      name: getUserDisplayName(user)
    }))
  ];

  const fetchUserSessions = async (userId: string) => {
    if (!userId) {
      setUserSessions([]);
      return;
    }

    setSessionsLoading(true);
    try {
      console.log(`🌐 Fetching sessions for user: ${userId}`);
      // Use the monitoring sessions endpoint (same as conversation monitor)
      const response = await fetch(
        `https://mselacy07a.execute-api.us-west-2.amazonaws.com/monitoring/sessions/${userId}`
      );
      
      console.log(`📡 Response status: ${response.status}`);
      
      if (!response.ok) {
        const errorText = await response.text();
        console.error(`❌ API Error: ${response.status} - ${errorText}`);
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      
      const data = await response.json();
      console.log(`📋 Raw session data received:`, data);
      
      const sessions = data.sessions || [];
      console.log(`📋 Processed sessions (${sessions.length}):`, sessions);
      
      // Validate session data structure
      sessions.forEach((session: UserSession, index: number) => {
        console.log(`Session ${index}:`, {
          session_id: session.session_id,
          message_count: session.message_count,
          last_activity: session.last_activity,
          created_at: session.created_at,
          title: session.title
        });
        
        if (!session.session_id) {
          console.warn(`⚠️ Session ${index} missing session_id:`, session);
        }
      });
      
      setUserSessions(sessions);
    } catch (err) {
      console.error('❌ Error fetching user sessions:', err);
      setUserSessions([]);
      setError(`Failed to fetch sessions: ${err instanceof Error ? err.message : 'Unknown error'}`);
    } finally {
      setSessionsLoading(false);
    }
  };

  const fetchAgentConversationData = async () => {
    if (!selectedSessionId) {
      setAgentData(null);
      return;
    }

    setLoading(true);
    setError(null);
    try {
      // Ensure we're only passing the session ID, not the display text
      const cleanSessionId = selectedSessionId.trim();
      console.log('🤖 Fetching agent data for session:', cleanSessionId);
      
      const response = await fetch(
        `https://mselacy07a.execute-api.us-west-2.amazonaws.com/monitoring/agent-conversations/${encodeURIComponent(cleanSessionId)}`
      );
      
      console.log('📡 Agent API Response status:', response.status);
      
      if (!response.ok) {
        const errorText = await response.text();
        console.error('❌ Agent API Error:', response.status, errorText);
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      
      const data: AgentConversationData = await response.json();
      console.log('📋 Agent conversation data received:', data);
      
      // Validate the data structure
      if (!data.agent_messages) {
        console.warn('⚠️ No agent_messages in response, setting empty array');
        data.agent_messages = [];
      }
      
      if (!data.agent_metadata) {
        console.warn('⚠️ No agent_metadata in response, setting default');
        data.agent_metadata = {
          total_messages: 0,
          user_messages: 0,
          assistant_messages: 0,
          tool_executions: 0,
          agent_types_used: [],
          conversation_duration: null,
          last_activity: null
        };
      }
      
      // Validate each message
      data.agent_messages = data.agent_messages.map((message, index) => {
        if (!message.role) {
          console.warn(`⚠️ Message ${index} missing role, setting to 'unknown'`);
          message.role = 'unknown';
        }
        if (!message.metadata) {
          console.warn(`⚠️ Message ${index} missing metadata, setting empty object`);
          message.metadata = {};
        }
        return message;
      });
      
      setAgentData(data);
      setError(data.error || null);
    } catch (err) {
      console.error('❌ Error fetching agent conversation data:', err);
      setError(err instanceof Error ? err.message : 'Unknown error occurred');
      setAgentData(null);
    } finally {
      setLoading(false);
    }
  };

  const formatTimestamp = (timestamp: string) => {
    try {
      return new Date(timestamp).toLocaleString();
    } catch {
      return timestamp;
    }
  };

  const formatDuration = (seconds: number | null) => {
    if (seconds === null || seconds === undefined) return 'N/A';
    
    const minutes = Math.floor(seconds / 60);
    const remainingSeconds = Math.floor(seconds % 60);
    
    if (minutes > 0) {
      return `${minutes}m ${remainingSeconds}s`;
    }
    return `${remainingSeconds}s`;
  };

  const formatSessionDisplay = (session: UserSession) => {
    try {
      // Provide defaults for undefined values
      const sessionId = session.session_id || 'Unknown Session';
      const messageCount = session.message_count || 0;
      const lastActivity = session.last_activity;
      
      let dateStr = 'Unknown date';
      if (lastActivity) {
        try {
          const date = new Date(lastActivity);
          if (!isNaN(date.getTime())) {
            dateStr = date.toLocaleString();
          }
        } catch (e) {
          console.warn('Error parsing date:', lastActivity, e);
        }
      }
      
      return `${sessionId} (${messageCount} messages) - ${dateStr}`;
    } catch (error) {
      console.warn('Error formatting session display:', error);
      return `${session.session_id || 'Unknown'} (${session.message_count || 0} messages)`;
    }
  };

  useEffect(() => {
    fetchUserSessions(selectedUserId);
    setSelectedSessionId(''); // Reset session when user changes
    setAgentData(null); // Clear agent data when user changes
  }, [selectedUserId]);

  useEffect(() => {
    fetchAgentConversationData();
    // Auto-refresh removed - now manual refresh only
  }, [selectedSessionId]);

  return (
    <div className="agent-conversation-monitor">
      {/* Header - matching conversation monitor style */}
      <div className="monitor-header">
        <h1>🤖 Agent Conversation Monitor</h1>
        <p>Monitor agent conversations, tool usage, and agent-specific metrics</p>
      </div>

      {/* Controls Section - matching conversation monitor style */}
      <div className="monitor-controls">
        <div className="control-group">
          <label>User:</label>
          <select
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
          <label>Session:</label>
          <select
            value={selectedSessionId}
            onChange={(e) => setSelectedSessionId(e.target.value)}
            disabled={!selectedUserId || sessionsLoading}
          >
            <option value="">
              {!selectedUserId ? 'Select a user first...' : 
               sessionsLoading ? 'Loading sessions...' : 
               userSessions.length === 0 ? 'No sessions found' : 
               'Select a session...'}
            </option>
            {userSessions.map(session => (
              <option key={session.session_id} value={session.session_id}>
                {formatSessionDisplay(session)}
              </option>
            ))}
          </select>
        </div>

        <button 
          onClick={async () => {
            console.log('🔄 Agent Monitor Refresh button clicked');
            console.log('🔄 Current state:', { selectedUserId, selectedSessionId, loading, sessionsLoading });
            
            try {
              if (selectedUserId) {
                console.log('🔄 Refreshing user sessions for:', selectedUserId);
                await fetchUserSessions(selectedUserId);
                console.log('✅ User sessions refreshed');
              }
              if (selectedSessionId) {
                console.log('🔄 Refreshing agent conversation data for:', selectedSessionId);
                await fetchAgentConversationData();
                console.log('✅ Agent conversation data refreshed');
              }
              console.log('✅ Agent Monitor refresh completed');
            } catch (error) {
              console.error('❌ Agent Monitor refresh failed:', error);
              setError(error instanceof Error ? error.message : 'Refresh failed');
            }
          }}
          disabled={!selectedUserId || loading || sessionsLoading}
          title={`Refresh ${selectedUserId ? 'sessions and data' : 'data (select user first)'}`}
        >
          {loading || sessionsLoading ? '🔄 Loading...' : '🔄 Refresh'}
        </button>
      </div>

      {/* Error Display */}
      {error && (
        <div className="error-message">
          Error: {error}
        </div>
      )}

      {/* Content Area */}
      <div className="monitor-content">
        {!selectedSessionId && (
          <div className="monitor-section">
            <h2>Select Session</h2>
            <div className="no-data">
              Choose a user from the dropdown above, then select one of their sessions to monitor agent interactions, tool usage, and conversation flow.
            </div>
          </div>
        )}

        {selectedSessionId && loading && (
          <div className="monitor-section">
            <h2>Loading...</h2>
            <div className="no-data">
              Loading agent conversation data...
            </div>
          </div>
        )}

        {selectedSessionId && !loading && !agentData && !error && (
          <div className="monitor-section">
            <h2>No Data Found</h2>
            <div className="no-data">
              This session may not have used agent mode, or the data may not be available yet.
            </div>
          </div>
        )}

        {agentData && (
          <>
            {/* Agent Metadata Summary - matching conversation monitor cards */}
            <div className="monitor-section">
              <h2>📊 Agent Session Summary</h2>
              <div className="summary-cards">
                <div className="summary-card">
                  <div className="card-header">
                    <span className="card-icon">💬</span>
                    <span className="card-title">Total Messages</span>
                  </div>
                  <div className="card-value">{agentData.agent_metadata.total_messages}</div>
                </div>

                <div className="summary-card">
                  <div className="card-header">
                    <span className="card-icon">👤</span>
                    <span className="card-title">User Messages</span>
                  </div>
                  <div className="card-value">{agentData.agent_metadata.user_messages}</div>
                </div>

                <div className="summary-card">
                  <div className="card-header">
                    <span className="card-icon">🤖</span>
                    <span className="card-title">Assistant Messages</span>
                  </div>
                  <div className="card-value">{agentData.agent_metadata.assistant_messages}</div>
                </div>

                <div className="summary-card">
                  <div className="card-header">
                    <span className="card-icon">🔧</span>
                    <span className="card-title">Tool Executions</span>
                  </div>
                  <div className="card-value">{agentData.agent_metadata.tool_executions}</div>
                </div>

                <div className="summary-card">
                  <div className="card-header">
                    <span className="card-icon">⏱️</span>
                    <span className="card-title">Duration</span>
                  </div>
                  <div className="card-value">
                    {formatDuration(agentData.agent_metadata.conversation_duration)}
                  </div>
                </div>

                <div className="summary-card">
                  <div className="card-header">
                    <span className="card-icon">🎯</span>
                    <span className="card-title">Agent Types</span>
                  </div>
                  <div className="card-value">
                    {agentData.agent_metadata.agent_types_used.length || 0}
                  </div>
                </div>
              </div>
            </div>

            {/* EventLoopMetrics Section */}
            {agentData.has_metrics && agentData.event_loop_metrics && (
              <div className="monitor-section">
                <h2>📈 EventLoop Performance Metrics</h2>
                
                {agentData.event_loop_metrics.has_metrics ? (
                  <>
                    {/* Aggregated Metrics Cards */}
                    <div className="metrics-summary-cards">
                      <div className="summary-card">
                        <div className="card-header">
                          <span className="card-icon">🔄</span>
                          <span className="card-title">Total Cycles</span>
                        </div>
                        <div className="card-value">
                          {agentData.event_loop_metrics.aggregated_metrics?.total_cycles || 0}
                        </div>
                      </div>

                      <div className="summary-card">
                        <div className="card-header">
                          <span className="card-icon">⏱️</span>
                          <span className="card-title">Total Duration</span>
                        </div>
                        <div className="card-value">
                          {agentData.event_loop_metrics.aggregated_metrics?.total_duration?.toFixed(2) || 0}s
                        </div>
                      </div>

                      <div className="summary-card">
                        <div className="card-header">
                          <span className="card-icon">🎯</span>
                          <span className="card-title">Total Tokens</span>
                        </div>
                        <div className="card-value">
                          {agentData.event_loop_metrics.aggregated_metrics?.total_tokens || 0}
                        </div>
                      </div>

                      <div className="summary-card">
                        <div className="card-header">
                          <span className="card-icon">📊</span>
                          <span className="card-title">Snapshots</span>
                        </div>
                        <div className="card-value">
                          {agentData.event_loop_metrics.total_snapshots}
                        </div>
                      </div>
                    </div>

                    {/* Average Performance Cards */}
                    <div className="metrics-averages-cards">
                      <div className="summary-card">
                        <div className="card-header">
                          <span className="card-icon">🔄</span>
                          <span className="card-title">Avg Cycles/Message</span>
                        </div>
                        <div className="card-value">
                          {agentData.event_loop_metrics.aggregated_metrics?.avg_cycles_per_message?.toFixed(1) || 0}
                        </div>
                      </div>

                      <div className="summary-card">
                        <div className="card-header">
                          <span className="card-icon">⏱️</span>
                          <span className="card-title">Avg Duration/Message</span>
                        </div>
                        <div className="card-value">
                          {agentData.event_loop_metrics.aggregated_metrics?.avg_duration_per_message?.toFixed(2) || 0}s
                        </div>
                      </div>

                      <div className="summary-card">
                        <div className="card-header">
                          <span className="card-icon">🎯</span>
                          <span className="card-title">Avg Tokens/Message</span>
                        </div>
                        <div className="card-value">
                          {agentData.event_loop_metrics.aggregated_metrics?.avg_tokens_per_message?.toFixed(0) || 0}
                        </div>
                      </div>
                    </div>

                    {/* Timeline Chart */}
                    {agentData.event_loop_metrics.snapshots_timeline && agentData.event_loop_metrics.snapshots_timeline.length > 0 && (
                      <div className="metrics-timeline">
                        <h4>📈 Performance Timeline</h4>
                        <div className="timeline-container">
                          {agentData.event_loop_metrics.snapshots_timeline.map((snapshot, index) => (
                            <div key={index} className="timeline-item">
                              <div className="timeline-header">
                                <span className="message-number">Message #{snapshot.message_number}</span>
                                <span className="timestamp">{formatTimestamp(snapshot.timestamp)}</span>
                              </div>
                              <div className="timeline-metrics">
                                <div className="metric-item">
                                  <span className="metric-label">Cycles:</span>
                                  <span className="metric-value">{snapshot.cycles}</span>
                                </div>
                                <div className="metric-item">
                                  <span className="metric-label">Duration:</span>
                                  <span className="metric-value">{snapshot.duration.toFixed(2)}s</span>
                                </div>
                                <div className="metric-item">
                                  <span className="metric-label">Tokens:</span>
                                  <span className="metric-value">{snapshot.tokens}</span>
                                </div>
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </>
                ) : (
                  <div className="no-metrics">
                    <p>No EventLoop metrics available for this session.</p>
                    {agentData.event_loop_metrics.error && (
                      <p className="error-text">Error: {agentData.event_loop_metrics.error}</p>
                    )}
                  </div>
                )}
              </div>
            )}

            {/* Agent Messages - matching conversation monitor style */}
            <div className="monitor-section">
              <h2>💬 Agent Messages ({agentData.agent_messages.length})</h2>
              
              {agentData.agent_messages.length === 0 ? (
                <div className="no-data">
                  No agent messages found for this session.
                </div>
              ) : (
                <div className="messages-list">
                  {(agentData.agent_messages || []).map((message, index) => {
                    // Extra defensive check for message object
                    if (!message) {
                      console.warn(`⚠️ Message ${index} is null/undefined, skipping`);
                      return null;
                    }
                    
                    // Ensure role is always a string
                    const safeRole = message.role || 'unknown';
                    const safeMetadata = message.metadata || {};
                    
                    return (
                      <div key={index} className={`message-item ${safeRole}`}>
                        <div className="message-header">
                          <span className={`role-badge ${safeRole}`}>
                            {safeRole.toUpperCase()}
                          </span>
                          <span className="message-timestamp">
                            {formatTimestamp(message.timestamp)}
                          </span>
                          {safeMetadata.agent_type && (
                            <span className="agent-type-badge">
                              {safeMetadata.agent_type}
                            </span>
                          )}
                          {safeMetadata.tool_use && (
                            <span className="tool-badge">🔧 Tool Used</span>
                          )}
                        </div>
                        
                        <div className="message-content">
                          {message.content && (
                            <div className="content-text">
                              {extractTextContent(message.content)}
                            </div>
                          )}
                          
                          {safeMetadata.tool_name && (
                            <div className="tool-details">
                              <div className="tool-name">
                                <strong>Tool:</strong> {safeMetadata.tool_name}
                              </div>
                              {safeMetadata.tool_input && (
                                <div className="tool-section">
                                  <strong>Input:</strong>
                                  <pre className="tool-data">
                                    {JSON.stringify(safeMetadata.tool_input, null, 2)}
                                  </pre>
                                </div>
                              )}
                              {safeMetadata.tool_result && (
                                <div className="tool-section">
                                  <strong>Result:</strong>
                                  <pre className="tool-data">
                                    {JSON.stringify(safeMetadata.tool_result, null, 2)}
                                  </pre>
                                </div>
                              )}
                            </div>
                          )}
                        </div>
                      </div>
                    );
                  }).filter(Boolean)}
                </div>
              )}
            </div>

            {/* Footer */}
          </>
        )}
      </div>
    </div>
  );
};
