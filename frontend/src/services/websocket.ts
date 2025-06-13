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
      const data = JSON.parse(event.data);
      this.messageHandlers.forEach(handler => handler(data));
    };

    this.ws.onclose = () => {
      console.log('WebSocket connection closed');
      // Attempt to reconnect after 5 seconds
      setTimeout(() => this.connect(url), 5000);
    };

    this.ws.onerror = (error) => {
      console.error('WebSocket error:', error);
    };
  }

  public sendMessage(message: string, userId?: string, userPersona?: string, userDiscountPersona?: string) {
    if (this.ws?.readyState === WebSocket.OPEN) {
      const payload: any = {
        user_message: message
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
      
      this.ws.send(JSON.stringify(payload));
    } else {
      console.error('WebSocket is not connected');
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
