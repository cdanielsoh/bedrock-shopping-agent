import { useState, useEffect, useRef } from 'react';
import { SessionManager, SessionInfo } from '../services/sessionManager';
import './SessionManager.css';

interface SessionManagerProps {
  currentSessionId: string;
  onSessionChange: (sessionId: string) => void;
  userId?: string; // Add userId prop
  isAgentMode?: boolean; // Add agent mode prop
}

const SessionManagerComponent = ({ currentSessionId, onSessionChange, userId, isAgentMode }: SessionManagerProps) => {
  const [isOpen, setIsOpen] = useState(false);
  const [sessions, setSessions] = useState<SessionInfo[]>([]);
  const dropdownRef = useRef<HTMLDivElement>(null);

  // Load sessions on component mount and when currentSessionId or userId changes
  useEffect(() => {
    console.log(`📋 SessionManagerComponent useEffect triggered. currentSessionId: ${currentSessionId}, userId: ${userId}`);
    
    const loadSessions = async () => {
      // Use the provided userId or fall back to default
      const effectiveUserId = userId || 'default-user';
      console.log(`🔍 Loading sessions for effective user: ${effectiveUserId}`);
      
      let sessionHistory = await SessionManager.getSessionHistory(effectiveUserId);
      console.log(`📚 Retrieved session history:`, sessionHistory);
      
      // If no sessions exist, create one for the current session
      if (sessionHistory.length === 0 && currentSessionId) {
        console.log(`✨ No sessions found, creating current session entry`);
        const currentSession: SessionInfo = {
          sessionId: currentSessionId,
          createdAt: new Date().toISOString(),
          lastUsed: new Date().toISOString(),
          title: `Current Session`
        };
        sessionHistory = [currentSession];
        console.log(`📝 Created session history with current session`);
      }
      
      // Ensure current session is in the list
      const currentExists = sessionHistory.find(s => s.sessionId === currentSessionId);
      if (!currentExists && currentSessionId) {
        console.log(`🔍 Current session not in history, adding it`);
        const currentSession: SessionInfo = {
          sessionId: currentSessionId,
          createdAt: new Date().toISOString(),
          lastUsed: new Date().toISOString(),
          title: `Session ${new Date().toLocaleString()}`
        };
        sessionHistory.unshift(currentSession);
        console.log(`📝 Added current session to history`);
      }
      
      console.log(`💾 Setting sessions state:`, sessionHistory);
      setSessions(sessionHistory);
    };

    loadSessions();
  }, [currentSessionId, userId]); // Add userId to dependency array

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };

    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside);
    }

    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [isOpen]);

  const handleNewSession = async () => {
    const effectiveUserId = userId || 'default-user';
    console.log(`🚀 Creating new session for user: ${effectiveUserId}, agentMode: ${isAgentMode}`);
    
    const newSessionId = await SessionManager.startNewSession(effectiveUserId, isAgentMode);
    console.log(`✨ New session created: ${newSessionId}`);
    
    onSessionChange(newSessionId);
    setIsOpen(false);
    
    // Refresh sessions list
    console.log(`🔄 Refreshing sessions list...`);
    const updatedSessions = await SessionManager.getSessionHistory(effectiveUserId);
    console.log(`📚 Updated sessions:`, updatedSessions);
    setSessions(updatedSessions);
  };

  const handleSessionSelect = async (sessionId: string) => {
    const effectiveUserId = userId || 'default-user';
    console.log(`🎯 Selecting session: ${sessionId} for user: ${effectiveUserId}`);
    
    SessionManager.switchToSession(sessionId, effectiveUserId);
    await SessionManager.updateSessionLastUsed(sessionId, effectiveUserId);
    onSessionChange(sessionId);
    setIsOpen(false);
    
    // Refresh sessions list
    console.log(`🔄 Refreshing sessions list after selection...`);
    const updatedSessions = await SessionManager.getSessionHistory(effectiveUserId);
    console.log(`📚 Updated sessions after selection:`, updatedSessions);
    setSessions(updatedSessions);
  };

  const handleDeleteSession = async (sessionId: string, event: React.MouseEvent) => {
    event.stopPropagation();
    const effectiveUserId = userId || 'default-user';
    console.log(`🗑️ Deleting session: ${sessionId} for user: ${effectiveUserId}`);
    
    await SessionManager.deleteSession(sessionId, effectiveUserId);
    
    // Refresh sessions list
    console.log(`🔄 Refreshing sessions list after deletion...`);
    const updatedSessions = await SessionManager.getSessionHistory(effectiveUserId);
    console.log(`📚 Updated sessions after deletion:`, updatedSessions);
    setSessions(updatedSessions);
    
    // If we deleted the current session, get the new current session
    if (sessionId === currentSessionId) {
      const getNewSession = async () => {
        const newCurrentSession = await SessionManager.getCurrentSessionId(effectiveUserId);
        console.log(`🔄 Deleted current session, switching to: ${newCurrentSession}`);
        onSessionChange(newCurrentSession);
      };
      getNewSession();
    }
  };

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleString();
  };

  const truncateSessionId = (sessionId: string) => {
    return sessionId.replace('session_', '').substring(0, 8) + '...';
  };

  return (
    <div className="session-manager" ref={dropdownRef}>
      <button 
        className="session-toggle"
        onClick={() => setIsOpen(!isOpen)}
        title="Manage conversation sessions"
      >
        🗂️ Sessions ({truncateSessionId(currentSessionId)})
      </button>
      
      {isOpen && (
        <div className="session-dropdown">
          <div className="session-header">
            <h3>Conversation Sessions</h3>
            <button 
              className="new-session-btn"
              onClick={handleNewSession}
              title="Start new conversation"
            >
              ➕ New Session
            </button>
          </div>
          
          <div className="session-list">
            {sessions.length === 0 ? (
              <div className="no-sessions">
                <div>No previous sessions</div>
                <div style={{ fontSize: '12px', color: '#a0aec0', marginTop: '4px' }}>
                  Current: {truncateSessionId(currentSessionId)}
                </div>
              </div>
            ) : (
              sessions.map((session) => (
                <div 
                  key={session.sessionId}
                  className={`session-item ${session.sessionId === currentSessionId ? 'active' : ''}`}
                  onClick={() => handleSessionSelect(session.sessionId)}
                >
                  <div className="session-info">
                    <div className="session-title">
                      {session.isAgentMode && <span className="agent-indicator">🤖 </span>}
                      {session.title}
                    </div>
                    <div className="session-meta">
                      <span className="session-id">{truncateSessionId(session.sessionId)}</span>
                      <span className="session-date">{formatDate(session.lastUsed)}</span>
                      {session.isAgentMode && <span className="session-mode">Agent Mode</span>}
                    </div>
                  </div>
                  {sessions.length > 1 && (
                    <button 
                      className="delete-session"
                      onClick={(e) => handleDeleteSession(session.sessionId, e)}
                      title="Delete session"
                    >
                      🗑️
                    </button>
                  )}
                </div>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
};

export default SessionManagerComponent;
