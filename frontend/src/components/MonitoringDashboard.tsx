import React, { useState } from 'react';
import ConversationMonitor from './ConversationMonitor';
import PerformanceMonitor from './PerformanceMonitor';
import { AgentConversationMonitor } from './AgentConversationMonitor';
import './MonitoringDashboard.css';

type MonitoringView = 'conversations' | 'performance' | 'agent-conversations';

interface MonitoringDashboardProps {
  onViewChange: (view: 'chat' | 'monitoring') => void;
}

const MonitoringDashboard: React.FC<MonitoringDashboardProps> = ({ onViewChange }) => {
  const [activeView, setActiveView] = useState<MonitoringView>('conversations');

  const views = [
    {
      id: 'conversations' as MonitoringView,
      name: 'Conversation Monitor',
      icon: '💬',
      description: 'View standard conversations, shared context, and routing decisions'
    },
    {
      id: 'agent-conversations' as MonitoringView,
      name: 'Agent Monitor',
      icon: '🤖',
      description: 'Monitor agent conversations, tool usage, and agent-specific metrics'
    },
    {
      id: 'performance' as MonitoringView,
      name: 'Performance Monitor',
      icon: '📊',
      description: 'Monitor token consumption, response times, and costs'
    }
  ];

  return (
    <div className="monitoring-dashboard">
      <div className="dashboard-header">
        <div className="header-top">
          <h1>🔧 Monitoring Dashboard</h1>
          <div className="header-navigation">
            <button
              className="nav-btn"
              onClick={() => onViewChange('chat')}
            >
              💬 Chat
            </button>
            <button
              className="nav-btn active"
              onClick={() => onViewChange('monitoring')}
            >
              🔧 Monitoring
            </button>
          </div>
        </div>
        <p>Comprehensive monitoring for the Bedrock Shopping Assistant</p>
      </div>

      <div className="dashboard-navigation">
        {views.map(view => (
          <button
            key={view.id}
            className={`nav-button ${activeView === view.id ? 'active' : ''}`}
            onClick={() => setActiveView(view.id)}
          >
            <div className="nav-icon">{view.icon}</div>
            <div className="nav-content">
              <div className="nav-title">{view.name}</div>
              <div className="nav-description">{view.description}</div>
            </div>
          </button>
        ))}
      </div>

      <div className="dashboard-content">
        {activeView === 'conversations' && <ConversationMonitor />}
        {activeView === 'agent-conversations' && <AgentConversationMonitor />}
        {activeView === 'performance' && <PerformanceMonitor />}
      </div>
    </div>
  );
};

export default MonitoringDashboard;
