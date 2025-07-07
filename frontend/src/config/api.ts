/**
 * Centralized API configuration
 * Update these URLs to match your deployed infrastructure
 */

export const API_CONFIG = {
  // WebSocket API for real-time chat
  WEBSOCKET_URL: 'wss://rihakjloyf.execute-api.us-west-2.amazonaws.com/prod',
  
  // HTTP API for REST endpoints (sessions, monitoring, recommendations)
  HTTP_API_URL: 'https://mselacy07a.execute-api.us-west-2.amazonaws.com/',
} as const;

// Export individual URLs for convenience
export const { WEBSOCKET_URL, HTTP_API_URL } = API_CONFIG;
