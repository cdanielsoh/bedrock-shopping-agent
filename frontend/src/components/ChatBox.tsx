import { useState, useEffect, useRef } from 'react';
import ReactMarkdown from 'react-markdown';
import WebSocketService from '../services/websocket';
import UserSelector from './UserSelector';
import RecommendationBubbles from './RecommendationBubbles';
import SessionManagerComponent from './SessionManager';
import { getUserById } from '../data/users';
import { SessionManager } from '../services/sessionManager';
import { WEBSOCKET_URL, HTTP_API_URL } from '../config/api';
import type { WebSocketMessage, Product, OrderContent } from '../types';
import './ChatBox.css';

interface ChatMessage {
  type: 'user' | 'assistant';
  content: string;
  products?: Product[];
  isWaiting?: boolean;
  waitMessage?: string;
  orderInfo?: OrderContent;
  isError?: boolean;
}

interface ChatBoxProps {
  onViewChange: (view: 'chat' | 'monitoring') => void;
}

const ChatBox = ({ onViewChange }: ChatBoxProps) => {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [inputMessage, setInputMessage] = useState('');
  const [selectedUserId, setSelectedUserId] = useState('15'); // Default to first user
  const [wsService, setWsService] = useState<WebSocketService | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const [useAgent, setUseAgent] = useState(false); // New state for agent toggle
  const [showSuggestions, setShowSuggestions] = useState(true); // New state for suggestions toggle
  const [currentSessionId, setCurrentSessionId] = useState<string>('');
  const [conversationStarted, setConversationStarted] = useState(false); // Track if conversation has started
  const [isInitializing, setIsInitializing] = useState(true); // Track if we're still loading session data
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Debug log for messages state changes and track conversation status
  useEffect(() => {
    console.log("Messages state updated, count:", messages.length);
    // Log any waiting messages
    const waitingMessages = messages.filter(msg => msg.isWaiting);
    if (waitingMessages.length > 0) {
      console.log("Current waiting messages:", waitingMessages);
    }
    
    // Check if conversation has started (has any non-waiting messages)
    const realMessages = messages.filter(msg => !msg.isWaiting);
    const hasStarted = realMessages.length > 0;
    if (hasStarted !== conversationStarted) {
      console.log(`🗣️ Conversation started status changed: ${hasStarted}`);
      setConversationStarted(hasStarted);
    }
  }, [messages, conversationStarted]);

  useEffect(() => {
    console.log(`🔧 ChatBox useEffect: Initializing with selectedUserId: ${selectedUserId}`);
    
    // Initialize session API with HTTP API URL from CDK output
    SessionManager.initializeWithApi(HTTP_API_URL);
    
    // Initialize session with user ID (now async)
    const initializeSession = async () => {
      try {
        setIsInitializing(true);
        const sessionId = await SessionManager.getCurrentSessionId(selectedUserId, useAgent);
        console.log(`🎯 Initial session ID for user ${selectedUserId}: ${sessionId}`);
        setCurrentSessionId(sessionId);
        
        // Load session agent mode
        try {
          const sessionInfo = await SessionManager.getSessionInfo(sessionId, selectedUserId);
          if (sessionInfo && typeof sessionInfo.isAgentMode === 'boolean') {
            console.log(`🤖 Loading initial agent mode for session: ${sessionInfo.isAgentMode}`);
            setUseAgent(sessionInfo.isAgentMode);
          } else {
            console.log(`🤖 No agent mode info found for initial session, keeping current state: ${useAgent}`);
            // Save current agent mode to the session
            await SessionManager.updateSessionAgentMode(sessionId, selectedUserId, useAgent);
          }
        } catch (error) {
          console.warn('Failed to load initial session agent mode:', error);
        }
      } catch (error) {
        console.error('Error initializing session:', error);
        // Fallback to generating a session ID
        const fallbackSessionId = `session_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
        setCurrentSessionId(fallbackSessionId);
      } finally {
        setIsInitializing(false);
      }
    };
    
    initializeSession();
    
    // Replace with your WebSocket URL
    const ws = new WebSocketService(WEBSOCKET_URL);
    setWsService(ws);

    const removeHandler = ws.onMessage((message: WebSocketMessage) => {
      console.log('ChatBox processing message type:', message.type);
      
      if (message.type === 'error' && message.message) {
        // Handle error message - show error styling
        console.log('Processing error message:', message.message);
        setMessages(prev => {
          // Remove any waiting messages first
          const filtered = prev.filter(msg => !msg.isWaiting);
          return [...filtered, {
            type: 'assistant' as const,
            content: message.message || 'An error occurred',
            isError: true
          }];
        });
      } else if (message.type === 'stream_end') {
        // Handle stream end - just log it, no UI changes needed
        console.log('Stream ended');
      } else if (message.type === 'wait' && message.message) {
        // Handle wait message - show spinner with message
        console.log('Processing wait message:', message.message);
        setMessages(prev => {
          const newMessages = [...prev, {
            type: 'assistant' as const,
            content: '',
            isWaiting: true,
            waitMessage: message.message
          }];
          console.log('Updated messages with wait indicator:', newMessages);
          return newMessages;
        });
      } else if (message.type === 'product_search' && message.results) {
        // Handle product results - display in boxes
        // First, remove any waiting messages
        console.log('Processing product search results:', message.results.length, 'products');
        setMessages(prev => {
          const filtered = prev.filter(msg => !msg.isWaiting);
          console.log('Removed waiting messages, count before/after:', prev.length, filtered.length);
          return [...filtered, {
            type: 'assistant' as const,
            content: '', // Removed "Here are the products I found:" text
            products: message.results
          }];
        });
      } else if (message.type === 'order' && typeof message.content === 'object') {
        // Handle order information
        const orderContent = message.content as OrderContent;
        console.log('Processing order information:', orderContent);
        setMessages(prev => {
          const filtered = prev.filter(msg => !msg.isWaiting);
          return [...filtered, {
            type: 'assistant' as const,
            content: '',
            orderInfo: orderContent
          }];
        });
      } else if (message.type === 'text_chunk' && typeof message.content === 'string') {
        // Handle all text chunks uniformly
        const textContent = message.content;
        setMessages(prev => {
          // Remove any waiting messages first
          const filtered = prev.filter(msg => !msg.isWaiting);
          if (filtered.length < prev.length) {
            console.log('Removed waiting messages for text chunk');
          }
          
          const lastMessage = filtered[filtered.length - 1];
          if (lastMessage && lastMessage.type === 'assistant' && !lastMessage.products && !lastMessage.orderInfo && !lastMessage.isError) {
            // Append to existing assistant message (but not to error messages)
            return [
              ...filtered.slice(0, -1),
              { ...lastMessage, content: lastMessage.content + textContent }
            ];
          } else {
            // Create new assistant message
            return [...filtered, {
              type: 'assistant' as const,
              content: textContent || ''
            }];
          }
        });
      }
    });

    // Monitor connection status
    const checkConnection = () => {
      setIsConnected(ws.isConnected());
    };
    
    const interval = setInterval(checkConnection, 1000);

    return () => {
      removeHandler();
      clearInterval(interval);
      ws.disconnect();
    };
  }, []);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Effect to handle user changes and update session accordingly
  useEffect(() => {
    console.log(`👤 User change effect triggered. selectedUserId: ${selectedUserId}`);
    
    if (selectedUserId) {
      // Get or create session for the selected user (now async)
      const updateUserSession = async () => {
        try {
          const userSessionId = await SessionManager.getCurrentSessionId(selectedUserId, useAgent);
          console.log(`🔍 Retrieved session for user ${selectedUserId}: ${userSessionId}`);
          console.log(`🔍 Current session ID: ${currentSessionId}`);
          
          if (userSessionId !== currentSessionId) {
            console.log(`🔄 Session change detected! Old: ${currentSessionId}, New: ${userSessionId}`);
            setCurrentSessionId(userSessionId);
            setMessages([]); // Clear messages when switching to different user's session
            setConversationStarted(false); // Reset conversation status
            console.log(`✅ Updated session and cleared messages for user ${selectedUserId}`);
          } else {
            console.log(`✨ Session unchanged for user ${selectedUserId}: ${userSessionId}`);
          }
        } catch (error) {
          console.error('Error updating user session:', error);
        }
      };
      
      updateUserSession();
    } else {
      console.log(`⚠️ No selectedUserId provided`);
    }
  }, [selectedUserId]); // Only depend on selectedUserId to avoid loops

  // Save agent mode when it changes (but not during initialization)
  useEffect(() => {
    if (!isInitializing && currentSessionId && selectedUserId) {
      console.log(`🤖 Agent mode changed to: ${useAgent}, saving to session ${currentSessionId}`);
      SessionManager.updateSessionAgentMode(currentSessionId, selectedUserId, useAgent);
    }
  }, [useAgent, currentSessionId, selectedUserId, isInitializing]);

  const sendMessage = () => {
    if (!inputMessage.trim() || !selectedUserId) return;

    const selectedUser = getUserById(selectedUserId);

    setMessages(prev => [...prev, {
      type: 'user',
      content: inputMessage
    }]);

    // Send message with user persona data and agent flag
    wsService?.sendMessage(
      inputMessage, 
      selectedUserId, 
      selectedUser?.persona, 
      selectedUser?.discount_persona,
      useAgent, // Pass the agent flag
      currentSessionId // Pass the session ID
    );
    setInputMessage('');
    
    // Automatically turn off suggestions when user sends a message
    setShowSuggestions(false);
  };

  const handleRecommendationClick = (recommendation: string) => {
    if (!selectedUserId) return;

    const selectedUser = getUserById(selectedUserId);

    setMessages(prev => [...prev, {
      type: 'user',
      content: recommendation
    }]);

    // Send recommendation message with user persona data and agent flag
    wsService?.sendMessage(
      recommendation, 
      selectedUserId, 
      selectedUser?.persona, 
      selectedUser?.discount_persona,
      useAgent, // Pass the agent flag
      currentSessionId // Pass the session ID
    );
    
    // Automatically turn off suggestions when user clicks a recommendation
    setShowSuggestions(false);
  };

  const handleUserIdChange = async (userId: string) => {
    console.log(`👤 handleUserIdChange called: ${userId} (previous: ${selectedUserId})`);
    setSelectedUserId(userId);
    // The useEffect will handle session switching automatically
    // Automatically turn on suggestions when switching users
    setShowSuggestions(true);
    console.log(`✅ User change completed, suggestions enabled`);
  };

  const handleSessionChange = async (newSessionId: string) => {
    console.log(`🔄 handleSessionChange called: ${newSessionId} (previous: ${currentSessionId})`);
    setCurrentSessionId(newSessionId);
    // Clear current messages when switching sessions
    setMessages([]);
    // Reset conversation started flag
    setConversationStarted(false);
    
    // Load session agent mode
    try {
      const sessionInfo = await SessionManager.getSessionInfo(newSessionId, selectedUserId);
      if (sessionInfo && typeof sessionInfo.isAgentMode === 'boolean') {
        console.log(`🤖 Loading agent mode for session: ${sessionInfo.isAgentMode}`);
        setUseAgent(sessionInfo.isAgentMode);
      } else {
        console.log(`🤖 No agent mode info found, defaulting to false`);
        setUseAgent(false);
      }
    } catch (error) {
      console.warn('Failed to load session agent mode:', error);
      setUseAgent(false);
    }
    
    // Update session last used time with user ID
    console.log(`📝 Updating session last used for user ${selectedUserId}`);
    SessionManager.updateSessionLastUsed(newSessionId, selectedUserId);
    console.log(`✅ Session change completed`);
  };

  const renderProduct = (product: Product) => (
    <div key={product._source.id} className="product-card">
      <img src={product._source.image_url} alt={product._source.name} />
      <h3>{product._source.name}</h3>
      <p>{product._source.description}</p>
      <p>Price: ${product._source.price}</p>
      <p>Stock: {product._source.current_stock}</p>
    </div>
  );

  const renderOrderInfo = (orderInfo: OrderContent) => {
    // Convert status to lowercase without spaces for CSS class
    const statusClass = orderInfo.status.toLowerCase().replace(/\s+/g, '');
    
    // Format the status for display (capitalize first letter)
    const displayStatus = orderInfo.status.charAt(0).toUpperCase() + orderInfo.status.slice(1);
    
    return (
      <div className="order-info">
        <div className="order-header">
          <h3>Order Information</h3>
          <span className={`order-status ${statusClass}`}>
            {displayStatus}
          </span>
        </div>
        <div className="order-details">
          <p><strong>Order ID:</strong> {orderInfo.order_id}</p>
          <p><strong>Order Date:</strong> {new Date(orderInfo.order_date).toLocaleString()}</p>
        </div>
      </div>
    );
  };

  return (
    <div className="app-layout">
      <UserSelector 
        selectedUserId={selectedUserId}
        onUserIdChange={handleUserIdChange}
      />
      
      <div className="chat-container">
        <div className="chat-header">
          <div className="header-top">
            <h1>🛍️ AI Shopping Assistant</h1>
            <div className="header-navigation">
              <button
                className="nav-btn active"
                onClick={() => onViewChange('chat')}
              >
                💬 Chat
              </button>
              <button
                className="nav-btn"
                onClick={() => onViewChange('monitoring')}
              >
                🔧 Monitoring
              </button>
            </div>
          </div>
          <p>Your personal shopping companion powered by AI</p>
          <div className="session-section">
            <SessionManagerComponent
              currentSessionId={currentSessionId}
              onSessionChange={handleSessionChange}
              userId={selectedUserId}
              isAgentMode={useAgent}
            />
          </div>
        </div>
        
        <div className={`connection-status ${isConnected ? 'connected' : 'disconnected'} ${useAgent ? 'agent-mode' : ''}`}>
          {isConnected ? (useAgent ? '🤖 Agent Mode - Connected' : '🟢 Connected') : '🔴 Disconnected'}
        </div>
        
        <div className="chat-messages">
          {messages.map((message, index) => (
            <div key={index} className={`message ${message.type} ${message.isError ? 'error' : ''}`}>
              {/* Only render message content div if there's actual content or a waiting spinner */}
              {(message.content || message.isWaiting) && (
                <div className={`message-content ${message.isError ? 'error-content' : ''}`}>
                  {message.isWaiting ? (
                    <div className="spinner-container">
                      <div className="spinner"></div>
                      <span className="wait-message">{message.waitMessage}</span>
                    </div>
                  ) : (
                    <div className="markdown-content">
                      {message.isError && <span className="error-icon">⚠️ </span>}
                      <ReactMarkdown>
                        {message.content}
                      </ReactMarkdown>
                    </div>
                  )}
                </div>
              )}
              {message.products && (
                <div className="products-grid">
                  {message.products.map(product => renderProduct(product))}
                </div>
              )}
              {message.orderInfo && renderOrderInfo(message.orderInfo)}
            </div>
          ))}
          <div ref={messagesEndRef} />
        </div>
        
        {/* Show recommendation bubbles when there are no messages or after the last message */}
        <RecommendationBubbles
          user={selectedUserId ? getUserById(selectedUserId) || null : null}
          onRecommendationClick={handleRecommendationClick}
          isVisible={isConnected && selectedUserId !== '' && showSuggestions}
          sessionId={currentSessionId}
        />
        
        <div className="chat-input">
          <div className="input-controls">
            <div className="toggle-controls">
              <div className="agent-toggle">
                <label className="toggle-switch">
                  <input
                    type="checkbox"
                    checked={useAgent}
                    onChange={(e) => setUseAgent(e.target.checked)}
                    disabled={conversationStarted || isInitializing}
                  />
                  <span className="toggle-slider"></span>
                </label>
                <span className="toggle-label">
                  {isInitializing ? '⏳ Loading...' : (useAgent ? '🤖 Agent Mode' : '💬 Chat Mode')}
                  {conversationStarted && !isInitializing && <span className="disabled-note"> (locked)</span>}
                </span>
              </div>
              <div className="suggestions-toggle">
                <label className="toggle-switch">
                  <input
                    type="checkbox"
                    checked={showSuggestions}
                    onChange={(e) => setShowSuggestions(e.target.checked)}
                  />
                  <span className="toggle-slider"></span>
                </label>
                <span className="toggle-label">
                  {showSuggestions ? '💡 Suggestions On' : '💡 Suggestions Off'}
                </span>
              </div>
            </div>
            <div className="message-input-container">
              <input
                type="text"
                value={inputMessage}
                onChange={(e) => setInputMessage(e.target.value)}
                onKeyPress={(e) => e.key === 'Enter' && sendMessage()}
                placeholder={useAgent ? "Ask the agent to help with complex tasks..." : "Ask me about products, orders, or anything else..."}
                disabled={!isConnected || !selectedUserId}
              />
              <button 
                onClick={sendMessage}
                disabled={!isConnected || !selectedUserId || !inputMessage.trim()}
              >
                Send 🚀
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default ChatBox;
