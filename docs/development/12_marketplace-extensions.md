# Building Marketplace Extensions in AITBC

This tutorial shows how to extend the AITBC marketplace with custom features, plugins, and integrations.

> **⚠️ DEPRECATION NOTICE (v0.4.7)**: Auction functionality has been deprecated. GPU-only marketplace auctions are no longer supported. The marketplace now focuses on hardware+software bundles with fixed pricing. See the "Auction Extensions" section below for details.

## Overview

The AITBC marketplace is designed to be extensible. You can add:
- ~~Custom auction types~~ (deprecated in v0.4.7)
- Specialized service categories
- Advanced filtering and search
- Integration with external systems
- Custom pricing models

## Prerequisites

- Node.js 16+
- AITBC marketplace source code
- Understanding of React/TypeScript
- API development experience

## Step 1: Create a Custom Auction Type ~~(DEPRECATED)~~

> **⚠️ DEPRECATED (v0.4.7)**: This section describes auction functionality that has been removed. The AITBC marketplace no longer supports GPU auctions. The system now uses hardware+software bundles with fixed pricing. If auction functionality is needed in the future, it should be designed fresh for the software service marketplace model.

The following code is provided for reference only and will not work with the current marketplace architecture.

Let's create a Dutch auction extension:

```typescript
// src/extensions/DutchAuction.ts
import { Auction, Bid, MarketplacePlugin } from '../types';

interface DutchAuctionConfig {
  startPrice: number;
  reservePrice: number;
  decrementRate: number;
  decrementInterval: number; // in seconds
}

export class DutchAuction implements MarketplacePlugin {
  config: DutchAuctionConfig;
  currentPrice: number;
  lastDecrement: number;

  constructor(config: DutchAuctionConfig) {
    this.config = config;
    this.currentPrice = config.startPrice;
    this.lastDecrement = Date.now();
  }

  async updatePrice(): Promise<void> {
    const now = Date.now();
    const elapsed = (now - this.lastDecrement) / 1000;
    
    if (elapsed >= this.config.decrementInterval) {
      const decrements = Math.floor(elapsed / this.config.decrementInterval);
      this.currentPrice = Math.max(
        this.config.reservePrice,
        this.currentPrice - (decrements * this.config.decrementRate)
      );
      this.lastDecrement = now;
    }
  }

  async validateBid(bid: Bid): Promise<boolean> {
    await this.updatePrice();
    return bid.amount >= this.currentPrice;
  }

  async getCurrentState(): Promise<any> {
    await this.updatePrice();
    return {
      type: 'dutch',
      currentPrice: this.currentPrice,
      nextDecrement: this.config.decrementInterval - 
        ((Date.now() - this.lastDecrement) / 1000)
    };
  }
}
```

## Step 2: Register the Extension ~~(DEPRECATED)~~

> **⚠️ DEPRECATED (v0.4.7)**: Auction registration functionality has been removed.

```typescript
// src/extensions/index.ts
import { DutchAuction } from './DutchAuction';
import { MarketplaceRegistry } from '../core/MarketplaceRegistry';

const registry = new MarketplaceRegistry();

// Register Dutch auction
registry.registerAuctionType('dutch', DutchAuction, {
  defaultConfig: {
    startPrice: 1000,
    reservePrice: 100,
    decrementRate: 10,
    decrementInterval: 60
  },
  validation: {
    startPrice: { type: 'number', min: 0 },
    reservePrice: { type: 'number', min: 0 },
    decrementRate: { type: 'number', min: 0 },
    decrementInterval: { type: 'number', min: 1 }
  }
});

export default registry;
```

## Step 3: Create UI Components ~~(DEPRECATED)~~

> **⚠️ DEPRECATED (v0.4.7)**: Auction UI components are no longer supported.

```tsx
// src/components/DutchAuctionCard.tsx
import React, { useState, useEffect } from 'react';
import { Card, Button, Progress, Typography } from 'antd';
import { useMarketplace } from '../hooks/useMarketplace';

const { Title, Text } = Typography;

interface DutchAuctionCardProps {
  auction: any;
}

export const DutchAuctionCard: React.FC<DutchAuctionCardProps> = ({ auction }) => {
  const [currentState, setCurrentState] = useState<any>(null);
  const [timeLeft, setTimeLeft] = useState<number>(0);
  const { placeBid } = useMarketplace();

  useEffect(() => {
    const updateState = async () => {
      const state = await auction.getCurrentState();
      setCurrentState(state);
      setTimeLeft(state.nextDecrement);
    };

    updateState();
    const interval = setInterval(updateState, 1000);

    return () => clearInterval(interval);
  }, [auction]);

  const handleBid = async () => {
    try {
      await placeBid(auction.id, currentState.currentPrice);
    } catch (error) {
      console.error('Bid failed:', error);
    }
  };

  if (!currentState) return <div>Loading...</div>;

  const priceProgress = 
    ((currentState.currentPrice - auction.config.reservePrice) / 
     (auction.config.startPrice - auction.config.reservePrice)) * 100;

  return (
    <Card title={auction.title} extra={`Auction #${auction.id}`}>
      <div className="mb-4">
        <Title level={4}>Current Price: {currentState.currentPrice} AITBC</Title>
        <Progress 
          percent={100 - priceProgress} 
          status="active"
          format={() => `${timeLeft}s until next drop`}
        />
      </div>
      
      <div className="flex justify-between items-center">
        <Text type="secondary">
          Reserve Price: {auction.config.reservePrice} AITBC
        </Text>
        <Button 
          type="primary" 
          onClick={handleBid}
          disabled={currentState.currentPrice <= auction.config.reservePrice}
        >
          Buy Now
        </Button>
      </div>
    </Card>
  );
};
```

## Step 4: Add Backend API Support ~~(DEPRECATED)~~

> **⚠️ DEPRECATED (v0.4.7)**: Auction API endpoints have been removed from coordinator-api.

```python
# apps/coordinator-api/src/app/routers/marketplace_extensions.py
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, List
import asyncio

router = APIRouter(prefix="/marketplace/extensions", tags=["marketplace-extensions"])

class DutchAuctionRequest(BaseModel):
    title: str
    description: str
    start_price: float
    reserve_price: float
    decrement_rate: float
    decrement_interval: int

class DutchAuctionState(BaseModel):
    auction_id: str
    current_price: float
    next_decrement: int
    total_bids: int

@router.post("/dutch-auction/create")
async def create_dutch_auction(request: DutchAuctionRequest) -> Dict[str, str]:
    """Create a new Dutch auction."""
    
    # Validate auction parameters
    if request.reserve_price >= request.start_price:
        raise HTTPException(400, "Reserve price must be less than start price")
    
    # Create auction in database
    auction_id = await marketplace_service.create_extension_auction(
        type="dutch",
        config=request.dict()
    )
    
    # Start price decrement task
    asyncio.create_task(start_price_decrement(auction_id))
    
    return {"auction_id": auction_id}

@router.get("/dutch-auction/{auction_id}/state")
async def get_dutch_auction_state(auction_id: str) -> DutchAuctionState:
    """Get current state of a Dutch auction."""
    
    auction = await marketplace_service.get_auction(auction_id)
    if not auction or auction.type != "dutch":
        raise HTTPException(404, "Dutch auction not found")
    
    current_price = calculate_current_price(auction)
    next_decrement = calculate_next_decrement(auction)
    
    return DutchAuctionState(
        auction_id=auction_id,
        current_price=current_price,
        next_decrement=next_decrement,
        total_bids=auction.bid_count
    )

async def start_price_decrement(auction_id: str):
    """Background task to decrement auction price."""
    while True:
        await asyncio.sleep(60)  # Check every minute
        
        auction = await marketplace_service.get_auction(auction_id)
        if not auction or auction.status != "active":
            break
        
        new_price = calculate_current_price(auction)
        await marketplace_service.update_auction_price(auction_id, new_price)
        
        if new_price <= auction.config["reserve_price"]:
            await marketplace_service.close_auction(auction_id)
            break
```

## Step 5: Add Custom Service Category

```typescript
// src/extensions/ServiceCategories.ts
export interface ServiceCategory {
  id: string;
  name: string;
  icon: string;
  description: string;
  requirements: ServiceRequirement[];
  pricing: PricingModel;
}

export interface ServiceRequirement {
  type: 'gpu' | 'cpu' | 'memory' | 'storage';
  minimum: number;
  recommended: number;
  unit: string;
}

export interface PricingModel {
  type: 'fixed' | 'hourly' | 'per-unit';
  basePrice: number;
  unitPrice?: number;
}

export const AI_INFERENCE_CATEGORY: ServiceCategory = {
  id: 'ai-inference',
  name: 'AI Inference',
  icon: 'brain',
  description: 'Large language model and neural network inference',
  requirements: [
    { type: 'gpu', minimum: 8, recommended: 24, unit: 'GB' },
    { type: 'memory', minimum: 16, recommended: 64, unit: 'GB' },
    { type: 'cpu', minimum: 4, recommended: 16, unit: 'cores' }
  ],
  pricing: {
    type: 'hourly',
    basePrice: 10,
    unitPrice: 0.5
  }
};

// Category registry
export const SERVICE_CATEGORIES: Record<string, ServiceCategory> = {
  'ai-inference': AI_INFERENCE_CATEGORY,
  'video-rendering': {
    id: 'video-rendering',
    name: 'Video Rendering',
    icon: 'video',
    description: 'High-quality video rendering and encoding',
    requirements: [
      { type: 'gpu', minimum: 12, recommended: 24, unit: 'GB' },
      { type: 'memory', minimum: 32, recommended: 128, unit: 'GB' },
      { type: 'storage', minimum: 100, recommended: 1000, unit: 'GB' }
    ],
    pricing: {
      type: 'per-unit',
      basePrice: 5,
      unitPrice: 0.1
    }
  }
};
```

## Step 6: Create Advanced Search Filters

```tsx
// src/components/AdvancedSearch.tsx
import React, { useState } from 'react';
import { Select, Slider, Input, Button, Space } from 'antd';
import { SERVICE_CATEGORIES } from '../extensions/ServiceCategories';

const { Option } = Select;
const { Search } = Input;

interface SearchFilters {
  category?: string;
  priceRange: [number, number];
  gpuMemory: [number, number];
  providerRating: number;
}

export const AdvancedSearch: React.FC<{
  onSearch: (filters: SearchFilters) => void;
}> = ({ onSearch }) => {
  const [filters, setFilters] = useState<SearchFilters>({
    priceRange: [0, 1000],
    gpuMemory: [0, 24],
    providerRating: 0
  });

  const handleSearch = () => {
    onSearch(filters);
  };

  return (
    <div className="p-4 bg-gray-50 rounded-lg">
      <Space direction="vertical" className="w-full">
        <Search
          placeholder="Search services..."
          onSearch={(value) => setFilters({ ...filters, query: value })}
          style={{ width: '100%' }}
        />
        
        <Select
          placeholder="Select category"
          style={{ width: '100%' }}
          onChange={(value) => setFilters({ ...filters, category: value })}
          allowClear
        >
          {Object.values(SERVICE_CATEGORIES).map(category => (
            <Option key={category.id} value={category.id}>
              {category.name}
            </Option>
          ))}
        </Select>
        
        <div>
          <label>Price Range: {filters.priceRange[0]} - {filters.priceRange[1]} AITBC</label>
          <Slider
            range
            min={0}
            max={1000}
            value={filters.priceRange}
            onChange={(value) => setFilters({ ...filters, priceRange: value })}
          />
        </div>
        
        <div>
          <label>GPU Memory: {filters.gpuMemory[0]} - {filters.gpuMemory[1]} GB</label>
          <Slider
            range
            min={0}
            max={24}
            value={filters.gpuMemory}
            onChange={(value) => setFilters({ ...filters, gpuMemory: value })}
          />
        </div>
        
        <div>
          <label>Minimum Provider Rating: {filters.providerRating} stars</label>
          <Slider
            min={0}
            max={5}
            step={0.5}
            value={filters.providerRating}
            onChange={(value) => setFilters({ ...filters, providerRating: value })}
          />
        </div>
        
        <Button type="primary" onClick={handleSearch} block>
          Apply Filters
        </Button>
      </Space>
    </div>
  );
};
```

## Step 7: Add Integration with External Systems

```python
# apps/coordinator-api/src/app/integrations/slack.py
import httpx
from typing import Dict, Any

class SlackIntegration:
    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url

    async def notify_new_offer(self, offer: Dict[str, Any]) -> None:
        """Send notification about new marketplace offer to Slack."""
        message = {
            "text": f"New offer created: {offer['title']}",
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*New Offer Alert*\n\n*Title:* {offer['title']}\n"
                               f"*Price:* {offer['price']} AITBC\n"
                               f"*Category:* {offer.get('category', 'General')}"
                    }
                },
                {
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "View Offer"},
                            "url": f"https://aitbc.bubuit.net/marketplace/offer/{offer['id']}"
                        }
                    ]
                }
            ]
        }

        async with httpx.AsyncClient() as client:
            await client.post(self.webhook_url, json=message)

    async def notify_booking_completed(self, offer_id: str, amount: float) -> None:
        """Notify when a booking is completed."""
        message = {
            "text": f"Booking of {amount} AITBC completed for offer {offer_id}"
        }

        async with httpx.AsyncClient() as client:
            await client.post(self.webhook_url, json=message)

# Integration with Discord
class DiscordIntegration:
    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url
    
    async def send_embed(self, title: str, description: str, fields: list) -> None:
        """Send rich embed message to Discord."""
        embed = {
            "title": title,
            "description": description,
            "fields": fields,
            "color": 0x00ff00
        }
        
        payload = {"embeds": [embed]}
        
        async with httpx.AsyncClient() as client:
            await client.post(self.webhook_url, json=payload)
```

## Step 8: Create Custom Pricing Model

```typescript
// src/extensions/DynamicPricing.ts
export interface PricingRule {
  condition: (context: PricingContext) => boolean;
  calculate: (basePrice: number, context: PricingContext) => number;
}

export interface PricingContext {
  demand: number;
  supply: number;
  timeOfDay: number;
  dayOfWeek: number;
  providerRating: number;
  serviceCategory: string;
}

export class DynamicPricingEngine {
  private rules: PricingRule[] = [];
  
  addRule(rule: PricingRule) {
    this.rules.push(rule);
  }
  
  calculatePrice(basePrice: number, context: PricingContext): number {
    let finalPrice = basePrice;
    
    for (const rule of this.rules) {
      if (rule.condition(context)) {
        finalPrice = rule.calculate(finalPrice, context);
      }
    }
    
    return Math.round(finalPrice * 100) / 100;
  }
}

// Example pricing rules
export const DEMAND_SURGE_RULE: PricingRule = {
  condition: (ctx) => ctx.demand / ctx.supply > 2,
  calculate: (price) => price * 1.5, // 50% surge
};

export const PEAK_HOURS_RULE: PricingRule = {
  condition: (ctx) => ctx.timeOfDay >= 9 && ctx.timeOfDay <= 17,
  calculate: (price) => price * 1.2, // 20% peak hour premium
};

export const TOP_PROVIDER_RULE: PricingRule = {
  condition: (ctx) => ctx.providerRating >= 4.5,
  calculate: (price) => price * 1.1, // 10% premium for top providers
};

// Usage
const pricingEngine = new DynamicPricingEngine();
pricingEngine.addRule(DEMAND_SURGE_RULE);
pricingEngine.addRule(PEAK_HOURS_RULE);
pricingEngine.addRule(TOP_PROVIDER_RULE);

const finalPrice = pricingEngine.calculatePrice(100, {
  demand: 100,
  supply: 30,
  timeOfDay: 14,
  dayOfWeek: 2,
  providerRating: 4.8,
  serviceCategory: 'ai-inference'
});
```

## Testing Your Extensions ~~(Auction Tests Deprecated)~~

> **⚠️ DEPRECATED (v0.4.7)**: Auction extension tests are no longer relevant.

```typescript
// src/extensions/__tests__/DutchAuction.test.ts ~~(DEPRECATED)~~
import { DutchAuction } from '../DutchAuction';

describe('DutchAuction', () => {
  let auction: DutchAuction;

  beforeEach(() => {
    auction = new DutchAuction({
      startPrice: 1000,
      reservePrice: 100,
      decrementRate: 10,
      decrementInterval: 60
    });
  });

  test('should start with initial price', () => {
    expect(auction.currentPrice).toBe(1000);
  });

  test('should decrement price after interval', async () => {
    // Mock time passing
    jest.spyOn(Date, 'now').mockReturnValue(Date.now() + 60000);

    await auction.updatePrice();
    expect(auction.currentPrice).toBe(990);
  });

  test('should not go below reserve price', async () => {
    // Mock significant time passing
    jest.spyOn(Date, 'now').mockReturnValue(Date.now() + 600000);

    await auction.updatePrice();
    expect(auction.currentPrice).toBe(100);
  });
});
```

**For current marketplace extensions**, focus on testing:
- Service category registration
- Advanced search filters
- External system integrations
- Dynamic pricing models
- Plugin system hooks

## Deployment

1. **Build your extensions**:
```bash
npm run build:extensions
```

2. **Deploy to production**:
```bash
# Copy extension files
cp -r src/extensions/* /var/www/aitbc.bubuit.net/marketplace/extensions/

# Update API
scp apps/coordinator-api/src/app/routers/marketplace_extensions.py \
  aitbc:/opt/coordinator-api/src/app/routers/

# Restart services
ssh aitbc "systemctl restart coordinator-api"
```

## Best Practices

1. **Modular Design** - Keep extensions independent
2. **Backward Compatibility** - Ensure extensions work with existing marketplace
3. **Performance** - Optimize for high-frequency operations
4. **Security** - Validate all inputs and permissions
5. **Documentation** - Document extension APIs and usage

## Conclusion

This tutorial covered creating marketplace extensions including service categories, advanced search filters, external system integrations, and custom pricing models. Auction functionality has been deprecated in v0.4.7 as the marketplace now focuses on hardware+software bundles with fixed pricing.

**Current supported extension areas:**
- Service categories for specialized workloads
- Advanced search and filtering capabilities
- External system integrations (Slack, Discord, etc.)
- Dynamic pricing models based on demand/supply
- Plugin system for marketplace hooks

If auction functionality is needed in the future for software service bundles, it should be designed fresh for the new marketplace microservice architecture.

For more examples and community contributions, visit the marketplace extensions repository.
