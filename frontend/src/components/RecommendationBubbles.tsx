import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import RecommendationsService from '../services/recommendations';
import type { User } from '../data/users';
import './RecommendationBubbles.css';

interface RecommendationBubblesProps {
  user: User | null;
  onRecommendationClick: (recommendation: string) => void;
  isVisible: boolean;
  sessionId?: string;
}

const RecommendationBubbles = ({ user, onRecommendationClick, isVisible, sessionId }: RecommendationBubblesProps) => {
  const { t } = useTranslation();
  const [recommendations, setRecommendations] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [refreshCount, setRefreshCount] = useState(0);
  const [lastRefreshTime, setLastRefreshTime] = useState<Date | null>(null);
  const [isAnimating, setIsAnimating] = useState(false);

  useEffect(() => {
    if (isVisible && user) {
      setIsAnimating(true);
      fetchRecommendations(false); // Don't force refresh on user change
      setTimeout(() => setIsAnimating(false), 400);
    }
  }, [user, isVisible, sessionId]); // Include sessionId in dependencies

  useEffect(() => {
    if (isVisible && user && refreshCount > 0) {
      fetchRecommendations(true); // Force refresh only when refresh button is clicked
    }
  }, [refreshCount]); // Separate effect for refresh button

  const fetchRecommendations = async (forceRefresh: boolean = false) => {
    if (!user) return;
    
    setLoading(true);
    try {
      const recs = await RecommendationsService.getRecommendations(user, forceRefresh, sessionId);
      setRecommendations(recs);
      if (forceRefresh) {
        setLastRefreshTime(new Date());
      }
    } catch (error) {
      console.error('Error fetching recommendations:', error);
      // Set personalized fallback recommendations based on user persona
      setRecommendations(getPersonalizedFallbacks(user));
    } finally {
      setLoading(false);
    }
  };

  const handleRefreshRecommendations = () => {
    setRefreshCount(prev => prev + 1);
  };

  const getPersonalizedFallbacks = (user: User): string[] => {
    const persona = user.persona.toLowerCase();
    const discountPersona = user.discount_persona.toLowerCase();
    
    // Personalized fallbacks based on user persona
    if (persona.includes('seasonal_furniture_floral')) {
      return [
        "Show me seasonal home decor",
        "What furniture is trending now?",
        "Help me find floral patterns",
        discountPersona.includes('lower_priced') ? "Show me budget-friendly options" : "What's new in home design?"
      ];
    } else if (persona.includes('books_apparel_homedecor')) {
      return [
        "Recommend some good books",
        "Show me latest fashion trends", 
        "Help me decorate my space",
        discountPersona.includes('all_discounts') ? "What deals are available?" : "What's popular right now?"
      ];
    } else if (persona.includes('apparel_footwear_accessories')) {
      return [
        "Show me fashion trends",
        "Help me find the perfect shoes",
        "What accessories are popular?",
        discountPersona.includes('lower_priced') ? "Find me affordable styles" : "Show me premium collections"
      ];
    } else if (persona.includes('homedecor_electronics_outdoors')) {
      return [
        "Show me smart home gadgets",
        "Help me find outdoor gear", 
        "What's new in electronics?",
        discountPersona.includes('all_discounts') ? "Show me tech deals" : "What's trending in home tech?"
      ];
    } else if (persona.includes('groceries_seasonal_tools')) {
      return [
        "Help me with grocery shopping",
        "Show me seasonal essentials",
        "What tools do I need?",
        discountPersona.includes('discount_indifferent') ? "Show me quality products" : "What's on sale today?"
      ];
    } else if (persona.includes('footwear_jewelry_furniture')) {
      return [
        "Help me find perfect shoes",
        "Show me jewelry collections",
        "What furniture fits my style?",
        discountPersona.includes('all_discounts') ? "Find me great deals" : "Show me premium options"
      ];
    } else if (persona.includes('accessories_groceries_books')) {
      return [
        "Recommend accessories for me",
        "Help with grocery planning",
        "Suggest some good reads",
        discountPersona.includes('discount_indifferent') ? "Show me quality items" : "What's popular today?"
      ];
    }
    
    // Generic fallbacks
    return [
      "What are you shopping for today?",
      "Show me popular items",
      "Help me find deals", 
      "What's trending now?"
    ];
  };

  const handleBubbleClick = (recommendation: string) => {
    onRecommendationClick(recommendation);
  };

  const formatRefreshTime = (time: Date): string => {
    const now = new Date();
    const diffInSeconds = Math.floor((now.getTime() - time.getTime()) / 1000);
    
    if (diffInSeconds < 60) {
      return 'just now';
    } else if (diffInSeconds < 3600) {
      const minutes = Math.floor(diffInSeconds / 60);
      return `${minutes}m ago`;
    } else {
      const hours = Math.floor(diffInSeconds / 3600);
      return `${hours}h ago`;
    }
  };

  if (!isVisible || !user) {
    return null;
  }

  return (
    <div className={`recommendation-bubbles ${isAnimating ? 'slide-in' : ''}`}>
      <div className="bubbles-header">
        <div className="bubbles-title-row">
          <span className="bubbles-title">💡 {t('chat.recommendations.title')}:</span>
          <div className="refresh-section">
            {lastRefreshTime && (
              <span className="refresh-indicator">
                ✨ Refreshed {formatRefreshTime(lastRefreshTime)}
              </span>
            )}
            <button 
              className="refresh-button"
              onClick={handleRefreshRecommendations}
              disabled={loading}
              title={t('monitoring.refresh')}
            >
              {loading ? (
                <span className="refresh-spinner">⟳</span>
              ) : (
                <span className="refresh-icon">🔄</span>
              )}
            </button>
          </div>
        </div>
        <span className="user-context">Based on your interests in {user.persona.replace(/_/g, ', ')}</span>
      </div>
      <div className="bubbles-container">
        {loading ? (
          <div className="loading-bubbles">
            {[1, 2, 3, 4].map((i) => (
              <div key={i} className="bubble-skeleton" />
            ))}
          </div>
        ) : (
          recommendations.map((recommendation, index) => (
            <button
              key={`${refreshCount}-${index}`} // Key includes refresh count for re-animation
              className="recommendation-bubble"
              onClick={() => handleBubbleClick(recommendation)}
              title={recommendation}
            >
              {recommendation}
            </button>
          ))
        )}
      </div>
    </div>
  );
};

export default RecommendationBubbles;
