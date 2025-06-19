/**
 * Session Manager for handling conversation sessions
 * Supports both local storage and backend API
 */

import { SessionApiService } from './sessionApi';
import type { SessionInfo as ApiSessionInfo } from './sessionApi';

export interface SessionInfo {
  sessionId: string;
  createdAt: string;
  lastUsed: string;
  title: string;
}

export class SessionManager {
  private static readonly SESSION_KEY = 'bedrock_shopping_session';
  private static readonly SESSION_HISTORY_KEY = 'bedrock_shopping_sessions';
  private static readonly USER_SESSION_KEY = 'bedrock_shopping_user_sessions'; // New key for user-specific sessions
  private static sessionApi: SessionApiService | null = null;
  
  /**
   * Initialize with backend API
   */
  static initializeWithApi(apiBaseUrl: string) {
    this.sessionApi = new SessionApiService(apiBaseUrl);
  }
  
  /**
   * Generate a new session ID
   */
  static generateSessionId(): string {
    return `session_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
  }
  
  /**
   * Get current session ID for a specific user or create new one
   * Now uses DynamoDB as primary storage, localStorage as fallback only
   */
  static async getCurrentSessionId(userId?: string): Promise<string> {
    console.log(`🔍 SessionManager.getCurrentSessionId called with userId: ${userId}`);
    
    if (userId && this.sessionApi) {
      try {
        // Try to get the most recent session from DynamoDB
        console.log(`🌐 Fetching sessions from DynamoDB for user: ${userId}`);
        const sessions = await this.sessionApi.getUserSessions(userId);
        console.log(`📋 Retrieved ${sessions.length} sessions from DynamoDB`);
        
        if (sessions.length > 0) {
          // Use the most recent session
          const mostRecentSession = sessions[0];
          console.log(`♻️ Using existing session from DynamoDB: ${mostRecentSession.sessionId}`);
          return mostRecentSession.sessionId;
        } else {
          // No sessions found, create a new one
          console.log(`✨ No sessions found in DynamoDB, creating new session`);
          const newSessionId = this.generateSessionId();
          await this.createSessionInDynamoDB(newSessionId, userId);
          return newSessionId;
        }
      } catch (error) {
        console.warn('⚠️ Failed to get session from DynamoDB, falling back to localStorage:', error);
      }
    }
    
    // Fallback to localStorage (for backward compatibility or when API is unavailable)
    console.log(`🔄 Falling back to localStorage for session management`);
    if (userId) {
      const userSessions = this.getUserSessions();
      let sessionId = userSessions[userId];
      
      if (!sessionId) {
        sessionId = this.generateSessionId();
        userSessions[userId] = sessionId;
        localStorage.setItem(this.USER_SESSION_KEY, JSON.stringify(userSessions));
        console.log(`✨ Created new localStorage session for user ${userId}: ${sessionId}`);
      }
      
      return sessionId;
    } else {
      // Global session fallback
      let sessionId = localStorage.getItem(this.SESSION_KEY);
      if (!sessionId) {
        sessionId = this.generateSessionId();
        localStorage.setItem(this.SESSION_KEY, sessionId);
        console.log(`✨ Created new global session: ${sessionId}`);
      }
      return sessionId;
    }
  }
  
  /**
   * Create a new session in DynamoDB
   */
  private static async createSessionInDynamoDB(sessionId: string, userId: string): Promise<void> {
    if (!this.sessionApi) {
      throw new Error('Session API not initialized');
    }
    
    console.log(`🌐 Creating session in DynamoDB: ${sessionId} for user: ${userId}`);
    const title = `Session ${new Date().toLocaleString()}`;
    
    try {
      const success = await this.sessionApi.createSession(sessionId, userId, title);
      if (success) {
        console.log(`✅ Session created successfully in DynamoDB`);
      } else {
        throw new Error('Failed to create session in DynamoDB');
      }
    } catch (error) {
      console.error(`❌ Error creating session in DynamoDB:`, error);
      throw error;
    }
  }

  /**
   * Get all user sessions from localStorage
   */
  private static getUserSessions(): Record<string, string> {
    const userSessions = localStorage.getItem(this.USER_SESSION_KEY);
    return userSessions ? JSON.parse(userSessions) : {};
  }
  
  /**
   * Start a new session for a specific user (clear current)
   * Now creates session in DynamoDB first, localStorage as backup
   */
  static async startNewSession(userId?: string): Promise<string> {
    console.log(`🚀 SessionManager.startNewSession called with userId: ${userId}`);
    
    const newSessionId = this.generateSessionId();
    console.log(`✨ Generated new session ID: ${newSessionId}`);
    
    if (userId && this.sessionApi) {
      try {
        // Create session in DynamoDB first
        await this.createSessionInDynamoDB(newSessionId, userId);
        console.log(`✅ Session created in DynamoDB: ${newSessionId}`);
        
        // Also update localStorage for immediate access
        const userSessions = this.getUserSessions();
        userSessions[userId] = newSessionId;
        localStorage.setItem(this.USER_SESSION_KEY, JSON.stringify(userSessions));
        console.log(`💾 Updated localStorage as backup`);
        
        return newSessionId;
      } catch (error) {
        console.warn('⚠️ Failed to create session in DynamoDB, falling back to localStorage:', error);
      }
    }
    
    // Fallback to localStorage-only approach
    console.log(`🔄 Using localStorage fallback for session creation`);
    if (userId) {
      const userSessions = this.getUserSessions();
      userSessions[userId] = newSessionId;
      localStorage.setItem(this.USER_SESSION_KEY, JSON.stringify(userSessions));
      console.log(`💾 Updated user sessions in localStorage:`, userSessions);
    } else {
      localStorage.setItem(this.SESSION_KEY, newSessionId);
      console.log(`🔄 Set global session: ${newSessionId}`);
    }
    
    // Add to session history (localStorage backup)
    console.log(`📝 Adding session to localStorage history...`);
    await this.addToSessionHistory(newSessionId, userId);
    
    console.log(`✅ Session creation completed: ${newSessionId}`);
    return newSessionId;
  }
  
  /**
   * Switch to an existing session for a specific user
   */
  static switchToSession(sessionId: string, userId?: string): void {
    console.log(`🔄 SessionManager.switchToSession called with sessionId: ${sessionId}, userId: ${userId}`);
    
    if (userId) {
      const userSessions = this.getUserSessions();
      console.log(`📋 Current user sessions before switch:`, userSessions);
      
      userSessions[userId] = sessionId;
      localStorage.setItem(this.USER_SESSION_KEY, JSON.stringify(userSessions));
      console.log(`💾 Updated user sessions after switch:`, userSessions);
      console.log(`🎯 Switched user ${userId} to session: ${sessionId}`);
    } else {
      localStorage.setItem(this.SESSION_KEY, sessionId);
      console.log(`🔄 Switched global session to: ${sessionId}`);
    }
  }
  
  /**
   * Get session history for user with user-specific filtering
   */
  static async getSessionHistory(userId?: string): Promise<SessionInfo[]> {
    // Try to get from API first
    if (this.sessionApi && userId) {
      try {
        const apiSessions: ApiSessionInfo[] = await this.sessionApi.getUserSessions(userId);
        // Convert API format to local format
        return apiSessions.map(session => ({
          sessionId: session.sessionId,
          createdAt: session.createdAt,
          lastUsed: session.lastUsed,
          title: session.title
        }));
      } catch (error) {
        console.warn('Failed to get sessions from API, falling back to localStorage:', error);
      }
    }
    
    // Fallback to localStorage
    const historyKey = userId ? `${this.SESSION_HISTORY_KEY}_${userId}` : this.SESSION_HISTORY_KEY;
    const history = localStorage.getItem(historyKey);
    return history ? JSON.parse(history) : [];
  }
  
  /**
   * Add session to history with user-specific storage
   */
  private static async addToSessionHistory(sessionId: string, userId?: string): Promise<void> {
    console.log(`📝 SessionManager.addToSessionHistory called with sessionId: ${sessionId}, userId: ${userId}`);
    
    const sessionInfo: SessionInfo = {
      sessionId,
      createdAt: new Date().toISOString(),
      lastUsed: new Date().toISOString(),
      title: `Session ${new Date().toLocaleString()}`
    };
    console.log(`📋 Created session info:`, sessionInfo);
    
    // Try to save to API
    if (this.sessionApi && userId) {
      console.log(`🌐 Attempting to save session to API...`);
      try {
        const success = await this.sessionApi.createSession(sessionId, userId, sessionInfo.title);
        if (success) {
          console.log(`✅ Session saved to API successfully`);
        } else {
          console.warn(`⚠️ Failed to save session to API`);
        }
      } catch (error) {
        console.warn('⚠️ Failed to create session in API:', error);
      }
    } else {
      console.log(`🔄 Skipping API save (sessionApi: ${!!this.sessionApi}, userId: ${userId})`);
    }
    
    // Always save to localStorage as backup with user-specific key
    console.log(`💾 Saving session to localStorage...`);
    const history = await this.getSessionHistory(userId);
    console.log(`📚 Current history before adding:`, history);
    
    history.unshift(sessionInfo);
    const limitedHistory = history.slice(0, 10);
    console.log(`📚 Updated history (limited to 10):`, limitedHistory);
    
    const historyKey = userId ? `${this.SESSION_HISTORY_KEY}_${userId}` : this.SESSION_HISTORY_KEY;
    console.log(`🔑 Using history key: ${historyKey}`);
    localStorage.setItem(historyKey, JSON.stringify(limitedHistory));
    console.log(`✅ Session history saved to localStorage`);
  }
  
  /**
   * Update session last used time with user-specific storage
   */
  static async updateSessionLastUsed(sessionId: string, userId?: string): Promise<void> {
    // Try to update in API
    if (this.sessionApi && userId) {
      try {
        await this.sessionApi.updateSession(sessionId, {});
      } catch (error) {
        console.warn('Failed to update session in API:', error);
      }
    }
    
    // Update in localStorage with user-specific key
    const history = await this.getSessionHistory(userId);
    const sessionIndex = history.findIndex(s => s.sessionId === sessionId);
    
    if (sessionIndex >= 0) {
      history[sessionIndex].lastUsed = new Date().toISOString();
      const historyKey = userId ? `${this.SESSION_HISTORY_KEY}_${userId}` : this.SESSION_HISTORY_KEY;
      localStorage.setItem(historyKey, JSON.stringify(history));
    }
  }
  
  /**
   * Delete a session from history with user-specific storage
   */
  static async deleteSession(sessionId: string, userId?: string): Promise<void> {
    // Try to delete from API
    if (this.sessionApi && userId) {
      try {
        await this.sessionApi.deleteSession(sessionId);
      } catch (error) {
        console.warn('Failed to delete session from API:', error);
      }
    }
    
    // Delete from localStorage with user-specific key
    const history = await this.getSessionHistory(userId);
    const filteredHistory = history.filter(s => s.sessionId !== sessionId);
    const historyKey = userId ? `${this.SESSION_HISTORY_KEY}_${userId}` : this.SESSION_HISTORY_KEY;
    localStorage.setItem(historyKey, JSON.stringify(filteredHistory));
    
    // If deleting current session, start new one
    const currentSessionId = await this.getCurrentSessionId(userId);
    if (currentSessionId === sessionId) {
      await this.startNewSession(userId);
    }
  }
  
  /**
   * Clear all sessions
   */
  static clearAllSessions(): void {
    localStorage.removeItem(this.SESSION_KEY);
    localStorage.removeItem(this.SESSION_HISTORY_KEY);
  }
}
