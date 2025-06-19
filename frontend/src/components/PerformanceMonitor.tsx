import React, { useState, useEffect } from 'react';
import { createMonitoringApi } from '../services/monitoringApi';
import { users, getUserDisplayName } from '../data/users';
import './PerformanceMonitor.css';

interface PerformanceMetrics {
  session_id: string;
  timestamp: string;
  handler_type: string;
  user_id: string;
  first_token_time: number;
  total_response_time: number;
  input_tokens: number;
  output_tokens: number;
  cache_read_tokens: number;
  cache_write_tokens: number;
  total_cost: number;
  model_id: string;
  use_agent: boolean;
}

interface AggregatedMetrics {
  total_requests: number;
  avg_first_token_time: number;
  avg_response_time: number;
  total_input_tokens: number;
  total_output_tokens: number;
  total_cache_read_tokens: number;
  total_cache_write_tokens: number;
  total_cost: number;
  handler_breakdown: Record<string, {
    count: number;
    avg_first_token_time: number;
    avg_response_time: number;
    total_tokens: number;
    total_cost: number;
  }>;
}

const PerformanceMonitor: React.FC = () => {
  const [selectedUserId, setSelectedUserId] = useState<string>('all');
  const [selectedHandler, setSelectedHandler] = useState<string>('all');
  const [timeRange, setTimeRange] = useState<string>('24h');
  const [metrics, setMetrics] = useState<PerformanceMetrics[]>([]);
  const [aggregatedMetrics, setAggregatedMetrics] = useState<AggregatedMetrics | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string>('');

  // Create user options with display names
  const userOptions = [
    { id: 'all', name: 'All Users' },
    ...users.map(user => ({
      id: user.id,
      name: getUserDisplayName(user)
    }))
  ];

  const handlers = [
    { id: 'all', name: 'All Handlers' },
    { id: 'router_handler', name: 'Router Handler' },
    { id: 'product_search', name: 'Product Search' },
    { id: 'order_history', name: 'Order History' },
    { id: 'product_details', name: 'Product Details' },
    { id: 'general_inquiry', name: 'General Inquiry' },
    { id: 'agent_handler', name: 'Agent Mode' }
  ];

  const timeRanges = [
    { id: '1h', name: 'Last Hour' },
    { id: '24h', name: 'Last 24 Hours' },
    { id: '7d', name: 'Last 7 Days' },
    { id: '30d', name: 'Last 30 Days' }
  ];

  useEffect(() => {
    loadPerformanceMetrics();
  }, [selectedUserId, selectedHandler, timeRange]);

  const loadPerformanceMetrics = async () => {
    try {
      setLoading(true);
      setError('');

      console.log(`🌐 Loading performance metrics with filters:`, {
        userId: selectedUserId,
        handlerType: selectedHandler,
        timeRange: timeRange
      });

      // Use real API instead of mock data
      const monitoringApi = createMonitoringApi();
      const metrics = await monitoringApi.getPerformanceMetrics({
        userId: selectedUserId,
        handlerType: selectedHandler,
        timeRange: timeRange,
        limit: 100
      });

      console.log(`📊 Retrieved ${metrics.length} performance metrics`);
      setMetrics(metrics);
      setAggregatedMetrics(calculateAggregatedMetrics(metrics));

    } catch (err) {
      console.error('❌ Error loading performance metrics:', err);
      setError(`Failed to load performance metrics: ${err}`);
    } finally {
      setLoading(false);
    }
  };

  const calculateAggregatedMetrics = (metrics: PerformanceMetrics[]): AggregatedMetrics => {
    if (metrics.length === 0) {
      return {
        total_requests: 0,
        avg_first_token_time: 0,
        avg_response_time: 0,
        total_input_tokens: 0,
        total_output_tokens: 0,
        total_cache_read_tokens: 0,
        total_cache_write_tokens: 0,
        total_cost: 0,
        handler_breakdown: {}
      };
    }

    const handlerBreakdown: Record<string, any> = {};
    
    metrics.forEach(metric => {
      // Use actual handler_type, but group agent_handler under 'agent' for display
      const key = metric.handler_type === 'agent_handler' ? 'agent' : metric.handler_type;
      
      if (!handlerBreakdown[key]) {
        handlerBreakdown[key] = {
          count: 0,
          total_first_token_time: 0,
          total_response_time: 0,
          total_tokens: 0,
          total_cost: 0
        };
      }
      
      handlerBreakdown[key].count++;
      handlerBreakdown[key].total_first_token_time += metric.first_token_time;
      handlerBreakdown[key].total_response_time += metric.total_response_time;
      handlerBreakdown[key].total_tokens += metric.input_tokens + metric.output_tokens;
      handlerBreakdown[key].total_cost += metric.total_cost;
    });

    // Calculate averages for each handler
    Object.keys(handlerBreakdown).forEach(key => {
      const handler = handlerBreakdown[key];
      handler.avg_first_token_time = handler.total_first_token_time / handler.count;
      handler.avg_response_time = handler.total_response_time / handler.count;
    });

    return {
      total_requests: metrics.length,
      avg_first_token_time: metrics.reduce((sum, m) => sum + m.first_token_time, 0) / metrics.length,
      avg_response_time: metrics.reduce((sum, m) => sum + m.total_response_time, 0) / metrics.length,
      total_input_tokens: metrics.reduce((sum, m) => sum + m.input_tokens, 0),
      total_output_tokens: metrics.reduce((sum, m) => sum + m.output_tokens, 0),
      total_cache_read_tokens: metrics.reduce((sum, m) => sum + m.cache_read_tokens, 0),
      total_cache_write_tokens: metrics.reduce((sum, m) => sum + m.cache_write_tokens, 0),
      total_cost: metrics.reduce((sum, m) => sum + m.total_cost, 0),
      handler_breakdown: handlerBreakdown
    };
  };

  const formatDuration = (ms: number) => {
    if (ms < 1000) return `${Math.round(ms)}ms`;
    return `${(ms / 1000).toFixed(2)}s`;
  };

  const formatCost = (cost: number) => {
    return `$${cost.toFixed(4)}`;
  };

  const formatNumber = (num: number) => {
    return num.toLocaleString();
  };

  return (
    <div className="performance-monitor">
      <div className="monitor-header">
        <h1>📊 Performance Monitor</h1>
        <p>Monitor token consumption, response times, and costs across all handlers</p>
      </div>

      <div className="monitor-controls">
        <div className="control-group">
          <label htmlFor="user-select">User:</label>
          <select
            id="user-select"
            value={selectedUserId}
            onChange={(e) => setSelectedUserId(e.target.value)}
          >
            {userOptions.map(user => (
              <option key={user.id} value={user.id}>
                {user.name}
              </option>
            ))}
          </select>
        </div>

        <div className="control-group">
          <label htmlFor="handler-select">Handler:</label>
          <select
            id="handler-select"
            value={selectedHandler}
            onChange={(e) => setSelectedHandler(e.target.value)}
          >
            {handlers.map(handler => (
              <option key={handler.id} value={handler.id}>
                {handler.name}
              </option>
            ))}
          </select>
        </div>

        <div className="control-group">
          <label htmlFor="time-range-select">Time Range:</label>
          <select
            id="time-range-select"
            value={timeRange}
            onChange={(e) => setTimeRange(e.target.value)}
          >
            {timeRanges.map(range => (
              <option key={range.id} value={range.id}>
                {range.name}
              </option>
            ))}
          </select>
        </div>

        <button onClick={loadPerformanceMetrics} disabled={loading}>
          {loading ? 'Loading...' : 'Refresh Data'}
        </button>
      </div>

      {error && (
        <div className="error-message">
          ❌ {error}
        </div>
      )}

      {aggregatedMetrics && (
        <div className="performance-content">
          {/* Summary Cards */}
          <div className="summary-cards">
            <div className="summary-card">
              <div className="card-icon">🚀</div>
              <div className="card-content">
                <div className="card-value">{formatDuration(aggregatedMetrics.avg_first_token_time)}</div>
                <div className="card-label">Avg First Token Time</div>
              </div>
            </div>

            <div className="summary-card">
              <div className="card-icon">⏱️</div>
              <div className="card-content">
                <div className="card-value">{formatDuration(aggregatedMetrics.avg_response_time)}</div>
                <div className="card-label">Avg Response Time</div>
              </div>
            </div>

            <div className="summary-card">
              <div className="card-icon">🔤</div>
              <div className="card-content">
                <div className="card-value">{formatNumber(aggregatedMetrics.total_input_tokens + aggregatedMetrics.total_output_tokens)}</div>
                <div className="card-label">Total Tokens</div>
              </div>
            </div>

            <div className="summary-card">
              <div className="card-icon">💰</div>
              <div className="card-content">
                <div className="card-value">{formatCost(aggregatedMetrics.total_cost)}</div>
                <div className="card-label">Total Cost</div>
              </div>
            </div>

            <div className="summary-card">
              <div className="card-icon">📈</div>
              <div className="card-content">
                <div className="card-value">{formatNumber(aggregatedMetrics.total_requests)}</div>
                <div className="card-label">Total Requests</div>
              </div>
            </div>
          </div>

          {/* Token Breakdown */}
          <div className="metrics-section">
            <h2>🔤 Token Usage Breakdown</h2>
            <div className="token-breakdown">
              <div className="token-card">
                <h4>Input Tokens</h4>
                <div className="token-value">{formatNumber(aggregatedMetrics.total_input_tokens)}</div>
                <div className="token-percentage">
                  {((aggregatedMetrics.total_input_tokens / (aggregatedMetrics.total_input_tokens + aggregatedMetrics.total_output_tokens)) * 100).toFixed(1)}%
                </div>
              </div>

              <div className="token-card">
                <h4>Output Tokens</h4>
                <div className="token-value">{formatNumber(aggregatedMetrics.total_output_tokens)}</div>
                <div className="token-percentage">
                  {((aggregatedMetrics.total_output_tokens / (aggregatedMetrics.total_input_tokens + aggregatedMetrics.total_output_tokens)) * 100).toFixed(1)}%
                </div>
              </div>

              <div className="token-card">
                <h4>Cache Read</h4>
                <div className="token-value">{formatNumber(aggregatedMetrics.total_cache_read_tokens)}</div>
                <div className="token-savings">💾 Cache Hit</div>
              </div>

              <div className="token-card">
                <h4>Cache Write</h4>
                <div className="token-value">{formatNumber(aggregatedMetrics.total_cache_write_tokens)}</div>
                <div className="token-savings">📝 Cache Store</div>
              </div>
            </div>
          </div>

          {/* Handler Performance */}
          <div className="metrics-section">
            <h2>⚡ Handler Performance</h2>
            <div className="handler-performance">
              {Object.entries(aggregatedMetrics.handler_breakdown).map(([handler, stats]) => (
                <div key={handler} className="handler-card">
                  <div className="handler-header">
                    <h4>{handler.replace('_', ' ').toUpperCase()}</h4>
                    <span className="request-count">{stats.count} requests</span>
                  </div>
                  
                  <div className="handler-stats">
                    <div className="stat-item">
                      <span className="stat-label">First Token:</span>
                      <span className="stat-value">{formatDuration(stats.avg_first_token_time)}</span>
                    </div>
                    
                    <div className="stat-item">
                      <span className="stat-label">Response Time:</span>
                      <span className="stat-value">{formatDuration(stats.avg_response_time)}</span>
                    </div>
                    
                    <div className="stat-item">
                      <span className="stat-label">Total Tokens:</span>
                      <span className="stat-value">{formatNumber(stats.total_tokens)}</span>
                    </div>
                    
                    <div className="stat-item">
                      <span className="stat-label">Total Cost:</span>
                      <span className="stat-value">{formatCost(stats.total_cost)}</span>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Recent Requests */}
          <div className="metrics-section">
            <h2>📋 Recent Requests</h2>
            <div className="requests-table">
              <div className="table-header">
                <div>Timestamp</div>
                <div>Handler</div>
                <div>User</div>
                <div>First Token</div>
                <div>Total Time</div>
                <div>Tokens</div>
                <div>Cost</div>
              </div>
              
              {metrics.slice(0, 20).map((metric, index) => (
                <div key={index} className="table-row">
                  <div className="timestamp">
                    {new Date(metric.timestamp).toLocaleString()}
                  </div>
                  <div className={`handler-type ${metric.handler_type}`}>
                    {metric.handler_type === 'agent_handler' ? 'AGENT' : 
                     metric.handler_type === 'router_handler' ? 'ROUTER' :
                     metric.handler_type.replace('_', ' ').toUpperCase()}
                  </div>
                  <div>User {metric.user_id}</div>
                  <div>{formatDuration(metric.first_token_time)}</div>
                  <div>{formatDuration(metric.total_response_time)}</div>
                  <div>
                    <span className="token-breakdown-mini">
                      {metric.input_tokens}↗ {metric.output_tokens}↙
                    </span>
                  </div>
                  <div>{formatCost(metric.total_cost)}</div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default PerformanceMonitor;
