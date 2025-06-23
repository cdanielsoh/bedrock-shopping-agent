/**
 * Session API service for backend session management
 */

export interface SessionInfo {
  sessionId: string;
  userId: string;
  title: string;
  createdAt: string;
  lastUsed: string;
  messageCount: number;
  isAgentMode?: boolean;
}

export class SessionApiService {
  private baseUrl: string;

  constructor(baseUrl: string) {
    this.baseUrl = baseUrl.replace(/\/$/, ''); // Remove trailing slash
  }

  /**
   * Get all sessions for a user
   */
  async getUserSessions(userId: string): Promise<SessionInfo[]> {
    console.log(`🌐 SessionApiService.getUserSessions called for userId: ${userId}`);
    console.log(`📡 API URL: ${this.baseUrl}/sessions/${userId}`);
    
    try {
      const response = await fetch(`${this.baseUrl}/sessions/${userId}`, {
        method: 'GET',
        headers: {
          'Content-Type': 'application/json',
        },
      });

      console.log(`📡 API Response status: ${response.status} ${response.statusText}`);

      if (!response.ok) {
        console.error(`❌ API Error: ${response.status} ${response.statusText}`);
        throw new Error(`Failed to get sessions: ${response.statusText}`);
      }

      const data = await response.json();
      console.log(`📚 API Response data:`, data);
      const sessions = data.sessions || [];
      console.log(`✅ Retrieved ${sessions.length} sessions for user ${userId}`);
      return sessions;
    } catch (error) {
      console.error('❌ Error getting user sessions:', error);
      return [];
    }
  }

  /**
   * Create a new session
   */
  async createSession(sessionId: string, userId: string, title?: string, isAgentMode?: boolean): Promise<boolean> {
    const sessionTitle = title || `Session ${new Date().toLocaleString()}`;
    console.log(`🌐 SessionApiService.createSession called:`, { sessionId, userId, title: sessionTitle, isAgentMode });
    console.log(`📡 API URL: ${this.baseUrl}/sessions`);
    
    try {
      const requestBody = {
        sessionId,
        userId,
        title: sessionTitle,
        isAgentMode: isAgentMode || false,
      };
      console.log(`📤 Request body:`, requestBody);
      
      const response = await fetch(`${this.baseUrl}/sessions`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(requestBody),
      });

      console.log(`📡 API Response status: ${response.status} ${response.statusText}`);
      
      if (response.ok) {
        const responseData = await response.json();
        console.log(`✅ Session created successfully:`, responseData);
      } else {
        console.error(`❌ Failed to create session: ${response.status} ${response.statusText}`);
      }

      return response.ok;
    } catch (error) {
      console.error('❌ Error creating session:', error);
      return false;
    }
  }

  /**
   * Update a session
   */
  async updateSession(sessionId: string, updates: Partial<Pick<SessionInfo, 'title' | 'messageCount' | 'isAgentMode'>>): Promise<boolean> {
    try {
      const response = await fetch(`${this.baseUrl}/sessions/${sessionId}`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(updates),
      });

      return response.ok;
    } catch (error) {
      console.error('Error updating session:', error);
      return false;
    }
  }

  /**
   * Delete a session
   */
  async deleteSession(sessionId: string): Promise<boolean> {
    try {
      const response = await fetch(`${this.baseUrl}/sessions/${sessionId}`, {
        method: 'DELETE',
        headers: {
          'Content-Type': 'application/json',
        },
      });

      return response.ok;
    } catch (error) {
      console.error('Error deleting session:', error);
      return false;
    }
  }
}
