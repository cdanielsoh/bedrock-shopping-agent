class WebSocketService {
  private ws: WebSocket | null = null;
  private messageHandlers: ((message: any) => void)[] = [];

  constructor(url: string) {
    this.connect(url);
  }

  private connect(url: string) {
    this.ws = new WebSocket(url);

    this.ws.onopen = () => {
      console.log('WebSocket connection established');
    };

    this.ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        this.messageHandlers.forEach(handler => handler(data));
      } catch (error) {
        console.error('Error parsing WebSocket message:', error);
        // Send error message to handlers
        const errorMessage = {
          type: 'error',
          message: 'Failed to parse server response. Please try again.'
        };
        this.messageHandlers.forEach(handler => handler(errorMessage));
      }
    };

    this.ws.onclose = (event) => {
      console.log('WebSocket connection closed', event.code, event.reason);
      // Send connection error to handlers if it wasn't a clean close
      if (event.code !== 1000) {
        const errorMessage = {
          type: 'error',
          message: 'Connection lost. Attempting to reconnect...'
        };
        this.messageHandlers.forEach(handler => handler(errorMessage));
      }
      // Attempt to reconnect after 5 seconds
      setTimeout(() => this.connect(url), 5000);
    };

    this.ws.onerror = (error) => {
      console.error('WebSocket error:', error);
      const errorMessage = {
        type: 'error',
        message: 'Connection error occurred. Please check your internet connection.'
      };
      this.messageHandlers.forEach(handler => handler(errorMessage));
    };
  }

  public sendMessage(message: string, userId?: string, userPersona?: string, userDiscountPersona?: string, useAgent?: boolean, sessionId?: string) {
    console.log(`📤 WebSocket.sendMessage called with:`, {
      message: message.substring(0, 50) + (message.length > 50 ? '...' : ''),
      userId,
      userPersona: userPersona?.substring(0, 30) + (userPersona && userPersona.length > 30 ? '...' : ''),
      useAgent,
      sessionId
    });
    
    if (this.ws?.readyState === WebSocket.OPEN) {
      try {
        const payload: any = {
          user_message: message,
          use_agent: useAgent || false // Add agent flag to payload
        };
        
        if (userId) {
          payload.user_id = userId;
        }
        
        if (userPersona) {
          payload.user_persona = userPersona;
        }
        
        if (userDiscountPersona) {
          payload.user_discount_persona = userDiscountPersona;
        }
        
        if (sessionId) {
          payload.session_id = sessionId;
        }
        
        console.log(`📡 Sending WebSocket payload:`, payload);
        this.ws.send(JSON.stringify(payload));
        console.log(`✅ WebSocket message sent successfully`);
      } catch (error) {
        console.error('❌ Error sending message:', error);
        const errorMessage = {
          type: 'error',
          message: 'Failed to send message. Please try again.'
        };
        this.messageHandlers.forEach(handler => handler(errorMessage));
      }
    } else {
      console.error('❌ WebSocket is not connected, readyState:', this.ws?.readyState);
      const errorMessage = {
        type: 'error',
        message: 'Not connected to server. Please wait for reconnection.'
      };
      this.messageHandlers.forEach(handler => handler(errorMessage));
    }
  }

  public onMessage(handler: (message: any) => void) {
    const wrappedHandler = (message: any) => {
      // Log all messages except text chunks to avoid console spam
      if (message.type !== 'text_chunk') {
        console.log('WebSocket received message:', message);
      } else if (message.type === 'text_chunk') {
        // Just log that a text chunk was received without the content
        console.log('WebSocket received text chunk');
      }
      
      // Special handling for error messages
      if (message.type === 'error') {
        console.error('WebSocket received error:', message.message);
      }
      
      handler(message);
    };
    
    this.messageHandlers.push(wrappedHandler);
    return () => {
      this.messageHandlers = this.messageHandlers.filter(h => h !== wrappedHandler);
    };
  }

  public isConnected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN;
  }

  public disconnect() {
    if (this.ws) {
      this.ws.close();
    }
  }
}

export default WebSocketService;
