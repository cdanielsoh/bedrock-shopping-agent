import type { User } from '../data/users';

export interface ChatRecommendation {
  recommendations: string[];
}

class RecommendationsService {
  private apiUrl: string;

  constructor() {
    // HTTP API URL from CDK deployment
    this.apiUrl = 'https://mselacy07a.execute-api.us-west-2.amazonaws.com';
  }

  async getRecommendations(user: User, forceRefresh: boolean = false, sessionId?: string): Promise<string[]> {
    console.log(`🔄 Getting recommendations for ${user.first_name} (${user.id}) - Session: ${sessionId || 'none'} - Force refresh: ${forceRefresh}`);
    
    try {
      // Send complete user data as POST request for better personalization
      const response = await fetch(`${this.apiUrl}/recommendations`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          user_id: user.id,
          session_id: sessionId,
          user_data: {
            age: user.age,
            gender: user.gender,
            persona: user.persona,
            discount_persona: user.discount_persona,
            first_name: user.first_name,
            username: user.username
          },
          force_refresh: forceRefresh,
          timestamp: forceRefresh ? Date.now() : undefined // Add timestamp to bypass cache
        })
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const data: ChatRecommendation = await response.json();
      console.log(`✅ Got ${data.recommendations?.length || 0} recommendations for ${user.first_name}`);
      return data.recommendations || [];
    } catch (error) {
      console.error('Error fetching recommendations:', error);
      console.log(`🔄 Using fallback recommendations for ${user.first_name}`);
      // Return personalized fallback recommendations based on user persona
      return this.getPersonalizedFallbacks(user);
    }
  }

  private getPersonalizedFallbacks(user: User): string[] {
    const persona = user.persona.toLowerCase();
    const discountPersona = user.discount_persona.toLowerCase();
    
    // Add some randomization to fallbacks for refresh functionality
    const randomSuffix = Math.random() > 0.5 ? " today" : " right now";
    
    // Personalized fallbacks based on user persona
    if (persona.includes('seasonal_furniture_floral')) {
      return [
        `Show me seasonal home decor${randomSuffix}`,
        "What furniture is trending now?",
        "Help me find floral patterns",
        discountPersona.includes('lower_priced') ? "Show me budget-friendly options" : "What's new in home design?"
      ];
    } else if (persona.includes('books_apparel_homedecor')) {
      return [
        "Recommend some good books",
        `Show me latest fashion trends${randomSuffix}`,
        "Help me decorate my space",
        discountPersona.includes('all_discounts') ? "What deals are available?" : "What's popular right now?"
      ];
    } else if (persona.includes('apparel_footwear_accessories')) {
      return [
        `Show me fashion trends${randomSuffix}`,
        "Help me find the perfect shoes",
        "What accessories are popular?",
        discountPersona.includes('lower_priced') ? "Find me affordable styles" : "Show me premium collections"
      ];
    } else if (persona.includes('homedecor_electronics_outdoors')) {
      return [
        "Show me smart home gadgets",
        "Help me find outdoor gear",
        `What's new in electronics${randomSuffix}?`,
        discountPersona.includes('all_discounts') ? "Show me tech deals" : "What's trending in home tech?"
      ];
    } else if (persona.includes('groceries_seasonal_tools')) {
      return [
        "Help me with grocery shopping",
        `Show me seasonal essentials${randomSuffix}`,
        "What tools do I need?",
        discountPersona.includes('discount_indifferent') ? "Show me quality products" : "What's on sale today?"
      ];
    } else if (persona.includes('footwear_jewelry_furniture')) {
      return [
        "Help me find perfect shoes",
        "Show me jewelry collections",
        `What furniture fits my style${randomSuffix}?`,
        discountPersona.includes('all_discounts') ? "Find me great deals" : "Show me premium options"
      ];
    } else if (persona.includes('accessories_groceries_books')) {
      return [
        "Recommend accessories for me",
        "Help with grocery planning",
        `Suggest some good reads${randomSuffix}`,
        discountPersona.includes('discount_indifferent') ? "Show me quality items" : "What's popular today?"
      ];
    }
    
    // Generic fallbacks with randomization
    const genericOptions = [
      [`What are you shopping for${randomSuffix}?`, "Show me popular items", "Help me find deals", "What's trending now?"],
      ["How can I help you shop today?", "Show me bestsellers", "Find me great deals", "What's new and exciting?"],
      ["What catches your interest today?", "Show me top picks", "Help me save money", "What's worth buying?"]
    ];
    
    return genericOptions[Math.floor(Math.random() * genericOptions.length)];
  }

  setApiUrl(url: string) {
    this.apiUrl = url;
  }
}

export default new RecommendationsService();
