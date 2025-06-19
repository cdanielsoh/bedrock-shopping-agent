"""
Improved StreamParser with better performance and error handling.
"""
import json
import re
from typing import Optional, List, Dict, Any
from dataclasses import dataclass


@dataclass
class ParsedSection:
    """Represents a parsed section from the stream."""
    section_type: str
    content: str
    data: List[str]


class StreamParser:
    """
    Improved stream parser with better performance and memory efficiency.
    Handles multiple delimiter formats for robustness.
    """
    
    # Pre-compiled regex patterns for better performance - handles multiple delimiter formats
    PRODUCTS_PATTERN = re.compile(r'<\|PRODUCTS\|>(.*?)(?:<\|/PRODUCTS\|>|<\|/PRODUCTS>|</\|PRODUCTS\|>)', re.DOTALL)
    ORDERS_PATTERN = re.compile(r'<\|ORDERS\|>(.*?)(?:<\|/ORDERS\|>|<\|/ORDERS>|</\|ORDERS\|>)', re.DOTALL)
    
    def __init__(self, apigw_management, connection_id: str, 
                 search_results: Optional[List[Dict]] = None, 
                 orders_list: Optional[List[Dict]] = None,
                 buffer_size: int = 1024):
        self.apigw_management = apigw_management
        self.connection_id = connection_id
        self.search_results = search_results or []
        self.orders_list = orders_list or []
        self.buffer_size = buffer_size
        
        # State management
        self.buffer = ""
        self.complete_response = ""
        self.content_sent = False
        self.last_sent_position = 0
        
        # Performance tracking
        self.chunks_processed = 0
        self.sections_found = 0
    
    def parse_chunk(self, text_chunk: str) -> None:
        """
        Parse streaming text chunk with improved efficiency.
        
        Args:
            text_chunk: New text chunk to process
        """
        if not text_chunk:
            return
            
        self.chunks_processed += 1
        self.complete_response += text_chunk
        self.buffer += text_chunk
        
        # If structured content already sent, skip processing
        if self.content_sent:
            return
        
        # Try to find and process complete sections
        if self._process_complete_sections():
            return
        
        # Handle partial sections or send safe text
        self._handle_streaming_text()
    
    def _process_complete_sections(self) -> bool:
        """
        Process complete sections if found.
        
        Returns:
            True if a complete section was processed, False otherwise
        """
        # Check for products section
        products_match = self.PRODUCTS_PATTERN.search(self.buffer)
        if products_match:
            self._process_products_section(products_match)
            return True
        
        # Check for orders section
        orders_match = self.ORDERS_PATTERN.search(self.buffer)
        if orders_match:
            self._process_orders_section(orders_match)
            return True
        
        return False
    
    def _process_products_section(self, match: re.Match) -> None:
        """Process complete products section."""
        try:
            # Send text before the section
            before_section = self.buffer[:match.start()]
            if before_section.strip():
                self._send_text_chunk(before_section)
            
            # Extract and process product data
            product_content = match.group(1).strip()
            self._send_products(product_content)
            
            # Mark content as sent and clear buffer
            self._mark_content_sent()
            self.sections_found += 1
            
        except Exception as e:
            print(f"Error processing products section: {e}")
            # Fallback to sending as regular text
            self._send_text_chunk(self.buffer)
    
    def _process_orders_section(self, match: re.Match) -> None:
        """Process complete orders section."""
        try:
            # Send text before the section
            before_section = self.buffer[:match.start()]
            if before_section.strip():
                self._send_text_chunk(before_section)
            
            # Extract and process order data
            order_content = match.group(1).strip()
            self._send_orders(order_content)
            
            # Mark content as sent and clear buffer
            self._mark_content_sent()
            self.sections_found += 1
            
        except Exception as e:
            print(f"Error processing orders section: {e}")
            # Fallback to sending as regular text
            self._send_text_chunk(self.buffer)
    
    def _handle_streaming_text(self) -> None:
        """Handle streaming text when no complete sections are found."""
        # Check if we have potential section markers
        if self._has_partial_markers():
            self._handle_partial_sections()
        else:
            self._send_safe_text()
    
    def _has_partial_markers(self) -> bool:
        """Check if buffer contains partial section markers - handles multiple formats."""
        return ('<|PRODUCTS|>' in self.buffer or 
                '<|ORDERS|>' in self.buffer or
                '<|/PRODUCTS|>' in self.buffer or
                '<|/ORDERS|>' in self.buffer or
                '</|PRODUCTS|>' in self.buffer or
                '</|ORDERS|>' in self.buffer)
    
    def _handle_partial_sections(self) -> None:
        """Handle when we have start markers but not complete sections."""
        # Find the earliest marker position
        markers = ['<|PRODUCTS|>', '<|ORDERS|>']
        earliest_pos = len(self.buffer)
        
        for marker in markers:
            pos = self.buffer.find(marker)
            if pos != -1 and pos < earliest_pos:
                earliest_pos = pos
        
        # Send text before the marker
        if earliest_pos > 0:
            safe_text = self.buffer[:earliest_pos]
            self._send_text_chunk(safe_text)
            self.buffer = self.buffer[earliest_pos:]
    
    def _send_safe_text(self) -> None:
        """Send text while keeping potential partial markers in buffer."""
        if len(self.buffer) <= 20:  # Keep small buffer for potential markers
            return
        
        # Calculate safe length (keep enough for longest marker)
        safe_length = len(self.buffer) - 20
        safe_text = self.buffer[:safe_length]
        self.buffer = self.buffer[safe_length:]
        
        if safe_text.strip():
            self._send_text_chunk(safe_text)
    
    def _send_text_chunk(self, text: str) -> None:
        """Send text chunk to client with error handling."""
        if not text.strip():
            return
            
        try:
            self._send_to_connection({
                'type': 'text_chunk',
                'content': text
            })
        except Exception as e:
            print(f"Error sending text chunk: {e}")
    
    def _send_products(self, product_data: str) -> None:
        """Extract product IDs and send structured product data."""
        try:
            # Parse product IDs (comma-separated)
            item_ids = [id.strip() for id in product_data.split(',') if id.strip()]
            
            if not item_ids or not self.search_results:
                return
            
            # Find matching products
            highlighted_products = [
                result for result in self.search_results
                if result.get('_source', {}).get('id') in item_ids
            ]
            
            if highlighted_products:
                self._send_to_connection({
                    "type": "product_search",
                    "results": highlighted_products
                })
                print(f"Sent {len(highlighted_products)} highlighted products")
                
        except Exception as e:
            print(f"Error processing products: {e}")
    
    def _send_orders(self, order_data: str) -> None:
        """Extract order IDs and send structured order data."""
        try:
            order_ids = [id.strip() for id in order_data.split(',') if id.strip()]
            
            if not order_ids or not self.orders_list:
                return
            
            # Send each matching order
            for order_id in order_ids:
                matching_order = next(
                    (order for order in self.orders_list 
                     if order.get('order_id') == order_id), 
                    None
                )
                
                if matching_order:
                    self._send_to_connection({
                        "type": "order",
                        "content": {
                            "order_id": matching_order.get('order_id'),
                            "order_date": matching_order.get('timestamp'),
                            "status": matching_order.get('delivery_status')
                        }
                    })
                    
        except Exception as e:
            print(f"Error processing orders: {e}")
    
    def _send_to_connection(self, data: Dict[str, Any]) -> None:
        """Send data to WebSocket connection with retry logic."""
        max_retries = 3
        for attempt in range(max_retries):
            try:
                self.apigw_management.post_to_connection(
                    ConnectionId=self.connection_id,
                    Data=json.dumps(data)
                )
                return
            except Exception as e:
                if attempt == max_retries - 1:
                    print(f"Failed to send message after {max_retries} attempts: {e}")
                    raise
                print(f"Retry {attempt + 1} for connection {self.connection_id}: {e}")
    
    def _mark_content_sent(self) -> None:
        """Mark that structured content has been sent."""
        self.content_sent = True
        self.buffer = ""

    def flush(self) -> None:
        """Flush the buffer and send any remaining content."""
        self._send_text_chunk(self.buffer)
        self.buffer = ""
    
    def finalize(self) -> None:
        """Finalize streaming and send any remaining content."""
        try:
            # Send any remaining text in buffer
            if not self.content_sent and self.buffer.strip():
                self._send_text_chunk(self.buffer)
            
            # Send stream end signal
            self._send_to_connection({"type": "stream_end"})
            
            # Log performance metrics
            print(f"StreamParser completed: {self.chunks_processed} chunks processed, "
                  f"{self.sections_found} sections found, "
                  f"{len(self.complete_response)} total characters")
                  
        except Exception as e:
            print(f"Error in finalize: {e}")
        finally:
            self.buffer = ""
    
    def get_stats(self) -> Dict[str, Any]:
        """Get parsing statistics for debugging."""
        return {
            'chunks_processed': self.chunks_processed,
            'sections_found': self.sections_found,
            'total_response_length': len(self.complete_response),
            'buffer_length': len(self.buffer),
            'content_sent': self.content_sent,
            'has_search_results': len(self.search_results) > 0,
            'has_orders': len(self.orders_list) > 0
        }


