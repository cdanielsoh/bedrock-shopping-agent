export interface Product {
  _source: {
    id: string;
    image_url: string;
    name: string;
    description: string;
    price: number;
    gender_affinity: string;
    current_stock: number;
  };
}

export interface Order {
  order_id: string;
  timestamp: string;
  item_id: string;
  delivery_status: string;
  item_details: {
    hits: {
      hits: Product[];
    };
  };
}

export interface WebSocketMessage {
  type: 'text_chunk' | 'product_search' | 'wait' | 'order' | 'error' | 'stream_end';
  content?: string | OrderContent;
  message?: string;
  results?: Product[];
}

export interface OrderContent {
  order_id: string;
  order_date: string;
  status: string;
}

// Also export as a namespace for better compatibility
export type { Product as ProductType, Order as OrderType, WebSocketMessage as WebSocketMessageType };
