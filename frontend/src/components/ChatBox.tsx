import { useState, useEffect, useRef } from 'react';
import WebSocketService from '../services/websocket';
import UserSelector from './UserSelector';
import RecommendationBubbles from './RecommendationBubbles';
import { getUserById } from '../data/users';
import type { WebSocketMessage, Product, OrderContent } from '../types';
import './ChatBox.css';

interface ChatMessage {
  type: 'user' | 'assistant';
  content: string;
  products?: Product[];
  isWaiting?: boolean;
  waitMessage?: string;
  orderInfo?: OrderContent;
}

const ChatBox = () => {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [inputMessage, setInputMessage] = useState('');
  const [selectedUserId, setSelectedUserId] = useState('15'); // Default to first user
  const [wsService, setWsService] = useState<WebSocketService | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Debug log for messages state changes
  useEffect(() => {
    console.log("Messages state updated, count:", messages.length);
    // Log any waiting messages
    const waitingMessages = messages.filter(msg => msg.isWaiting);
    if (waitingMessages.length > 0) {
      console.log("Current waiting messages:", waitingMessages);
    }
  }, [messages]);

  useEffect(() => {
    // Replace with your WebSocket URL
    const ws = new WebSocketService('wss://rihakjloyf.execute-api.us-west-2.amazonaws.com/prod');
    setWsService(ws);

    const removeHandler = ws.onMessage((message: WebSocketMessage) => {
      console.log('ChatBox processing message type:', message.type);
      
      if (message.type === 'wait' && message.message) {
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
          if (lastMessage && lastMessage.type === 'assistant' && !lastMessage.products && !lastMessage.orderInfo) {
            // Append to existing assistant message
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

  const sendMessage = () => {
    if (!inputMessage.trim() || !selectedUserId) return;

    const selectedUser = getUserById(selectedUserId);

    setMessages(prev => [...prev, {
      type: 'user',
      content: inputMessage
    }]);

    // Send message with user persona data
    wsService?.sendMessage(
      inputMessage, 
      selectedUserId, 
      selectedUser?.persona, 
      selectedUser?.discount_persona
    );
    setInputMessage('');
  };

  const handleRecommendationClick = (recommendation: string) => {
    if (!selectedUserId) return;

    const selectedUser = getUserById(selectedUserId);

    setMessages(prev => [...prev, {
      type: 'user',
      content: recommendation
    }]);

    // Send recommendation message with user persona data
    wsService?.sendMessage(
      recommendation, 
      selectedUserId, 
      selectedUser?.persona, 
      selectedUser?.discount_persona
    );
  };

  const handleUserIdChange = (userId: string) => {
    setSelectedUserId(userId);
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
          <h1>🛍️ AI Shopping Assistant</h1>
          <p>Your personal shopping companion powered by AI</p>
        </div>
        
        <div className={`connection-status ${isConnected ? 'connected' : 'disconnected'}`}>
          {isConnected ? '🟢 Connected' : '🔴 Disconnected'}
        </div>
        
        <div className="chat-messages">
          {messages.map((message, index) => (
            <div key={index} className={`message ${message.type}`}>
              {/* Only render message content div if there's actual content or a waiting spinner */}
              {(message.content || message.isWaiting) && (
                <div className="message-content">
                  {message.isWaiting ? (
                    <div className="spinner-container">
                      <div className="spinner"></div>
                      <span className="wait-message">{message.waitMessage}</span>
                    </div>
                  ) : (
                    message.content
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
          isVisible={isConnected && selectedUserId !== ''}
        />
        
        <div className="chat-input">
          <input
            type="text"
            value={inputMessage}
            onChange={(e) => setInputMessage(e.target.value)}
            onKeyPress={(e) => e.key === 'Enter' && sendMessage()}
            placeholder="Ask me about products, orders, or anything else..."
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
  );
};

export default ChatBox;
