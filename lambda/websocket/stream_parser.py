import json

def send_to_connection(apigw_client, connection_id, data):
    """Send data to the WebSocket connection."""
    try:
        apigw_client.post_to_connection(
            ConnectionId=connection_id,
            Data=json.dumps(data)
        )
    except Exception as e:
        print(f"Error sending message to connection {connection_id}: {str(e)}")

class StreamParser:
    def __init__(self, apigw_management, connection_id, search_results=None, orders_list=None):
        self.apigw_management = apigw_management
        self.connection_id = connection_id
        self.search_results = search_results
        self.orders_list = orders_list
        self.buffer = ""
        self.complete_response = ""
        self.content_sent = False
        
    def parse_chunk(self, text_chunk):
        """Parse streaming text chunk and handle product/order delimiters"""
        self.complete_response += text_chunk
        self.buffer += text_chunk
        
        # If we already sent structured content, stop processing
        if self.content_sent:
            return
            
        # Check for products section
        if self._has_complete_section('<|PRODUCTS|>', '<|/PRODUCTS|>'):
            self._process_products_section()
        # Check for orders section
        elif self._has_complete_section('<|ORDERS|>', '<|/ORDERS|>'):
            self._process_orders_section()
        # Check if we've started either section
        elif '<|PRODUCTS|>' in self.buffer or '<|ORDERS|>' in self.buffer:
            self._handle_partial_section()
        else:
            # No markers yet - send safe text
            self._send_safe_text()
    
    def _has_complete_section(self, start_marker, end_marker):
        """Check if buffer contains complete section with both markers"""
        return start_marker in self.buffer and end_marker in self.buffer
    
    def _process_products_section(self):
        """Process complete products section"""
        start_marker = '<|PRODUCTS|>'
        end_marker = '<|/PRODUCTS|>'
        
        # Split and extract
        before_content, after_start = self.buffer.split(start_marker, 1)
        content_section, remaining = after_start.split(end_marker, 1)
        
        # Send text before structured content
        if before_content:
            self._send_text(before_content)
        
        # Send products
        self._send_products(content_section.strip())
        self._mark_content_sent()
    
    def _process_orders_section(self):
        """Process complete orders section"""
        start_marker = '<|ORDERS|>'
        end_marker = '<|/ORDERS|>'
        
        # Split and extract
        before_content, after_start = self.buffer.split(start_marker, 1)
        content_section, remaining = after_start.split(end_marker, 1)
        
        # Send text before structured content
        if before_content:
            self._send_text(before_content)
        
        # Send orders
        self._send_orders(content_section.strip())
        self._mark_content_sent()
    
    def _handle_partial_section(self):
        """Handle when we have start marker but not end marker"""
        products_start = '<|PRODUCTS|>'
        orders_start = '<|ORDERS|>'
        
        if products_start in self.buffer:
            parts = self.buffer.split(products_start, 1)
            if parts[0]:
                self._send_text(parts[0])
            self.buffer = products_start + parts[1]
        elif orders_start in self.buffer:
            parts = self.buffer.split(orders_start, 1)
            if parts[0]:
                self._send_text(parts[0])
            self.buffer = orders_start + parts[1]
    
    def _send_safe_text(self):
        """Send text while keeping potential partial markers in buffer"""
        # Keep enough characters to detect any marker
        max_marker_length = max(len('<|PRODUCTS|>'), len('<|ORDERS|>'))
        
        if len(self.buffer) > max_marker_length:
            safe_length = len(self.buffer) - max_marker_length
            safe_text = self.buffer[:safe_length]
            self.buffer = self.buffer[safe_length:]
            
            if safe_text:
                self._send_text(safe_text)
    
    def _send_text(self, text):
        """Send text chunk to client"""
        send_to_connection(self.apigw_management, self.connection_id, {
            'type': 'text_chunk',
            'content': text
        })
    
    def _send_products(self, product_data):
        """Extract product IDs and send to client"""
        try:
            item_ids = [id.strip() for id in product_data.split(',') if id.strip()]
            
            if item_ids and self.search_results:
                highlighted_products = [
                    result for result in self.search_results
                    if result['_source']['id'] in item_ids
                ]
                
                if highlighted_products:
                    send_to_connection(self.apigw_management, self.connection_id, {
                        "type": "product_search", 
                        "results": highlighted_products
                    })
                    
        except Exception as e:
            print(f"Error parsing products: {e}")
    
    def _send_orders(self, order_data):
        """Extract order IDs and send to client"""
        print(f"Order data: {order_data}")
        try:
            order_ids = [id.strip() for id in order_data.split(',') if id.strip()]
            
            if order_ids and self.orders_list:
                for order_id in order_ids:
                    # Find matching order
                    matching_order = next(
                        (order for order in self.orders_list if order.get('order_id') == order_id), 
                        None
                    )
                    
                    if matching_order:
                        send_to_connection(self.apigw_management, self.connection_id, {
                            "type": "order",
                            "content": {
                                "order_id": matching_order.get('order_id'),
                                "order_date": matching_order.get('timestamp'),
                                "status": matching_order.get('delivery_status')
                            }
                        })
                        
        except Exception as e:
            print(f"Error parsing orders: {e}")
    
    def _mark_content_sent(self):
        """Mark that structured content has been sent"""
        self.content_sent = True
        self.buffer = ""
    
    def finalize(self):
        """Call at end of streaming to flush remaining text"""
        if not self.content_sent and self.buffer:
            self._send_text(self.buffer)
            self.buffer = ""