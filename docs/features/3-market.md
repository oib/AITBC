# Market

## 3. Market

### Core Market

| Feature | Description | Documentation | Status | Release |
|---------|-------------|---------------|--------|---------|
| List Offers | List offers with filters (status, region, gpu_model, chain_id) | [docs/api/market-api.md](../api/market-api.md) | ✅ | — |
| Get Offer | Get a specific offer by ID | [docs/api/market-api.md](../api/market-api.md) | ✅ | — |
| Create Offer | Create a new market offer | [docs/api/market-api.md](../api/market-api.md) | ✅ | — |
| Cancel Offer | Cancel a market offer | [docs/api/market-api.md](../api/market-api.md) | ✅ | — |
| Book Offer | Book/purchase an offer with escrow creation | [docs/api/market-api.md](../api/market-api.md) | ✅ | — |
| Offer History | Get offer history | [docs/features/offer-history.md](./offer-history.md) | ✅ | — |
| Match Request | Match a compute request to best GPU offer (price-time priority) | [docs/features/match-request.md](./match-request.md) | ✅ | v0.6.6 |
| Market Analytics | Get market analytics and performance metrics | [docs/features/market-analytics.md](./market-analytics.md) | ✅ | — |
| Dynamic Pricing | Apply dynamic pricing strategies to offers | [docs/features/dynamic-pricing.md](./dynamic-pricing.md) | ✅ | — |

### Edge Integration

| Feature | Description | Documentation | Status | Release |
|---------|-------------|---------------|--------|---------|
| Edge Advertise | Advertise edge node GPU capabilities to market | [docs/features/edge-advertise.md](./edge-advertise.md) | ✅ | v0.6.6 |
| List Edge Nodes | List all registered edge nodes | [docs/features/list-edge-nodes.md](./list-edge-nodes.md) | ✅ | v0.6.6 |
| Edge Health | Get edge node health status | [docs/features/edge-health.md](./edge-health.md) | ✅ | v0.6.6 |

### Ratings & Reputation

| Feature | Description | Documentation | Status | Release |
|---------|-------------|---------------|--------|---------|
| Rate Offer | Rate a market offer/service | [docs/features/rate-offer.md](./rate-offer.md) | ✅ | — |
| Get Ratings | Get ratings for an offer | [docs/features/get-ratings.md](./get-ratings.md) | ✅ | — |
| Sync Ratings | Sync ratings to blockchain | [docs/features/sync-ratings.md](./sync-ratings.md) | ✅ | — |
| Service Reputation | Service reputation system | [docs/market/service-reputation-system.md](../market/service-reputation-system.md) | ✅ | — |

### Knowledge Graph

| Feature | Description | Documentation | Status | Release |
|---------|-------------|---------------|--------|---------|
| Create Knowledge Graph | Create a knowledge graph | [docs/features/create-knowledge-graph.md](./create-knowledge-graph.md) | ✅ | — |
| Add Nodes/Edges | Add nodes and edges to a knowledge graph | [docs/features/add-nodes-edges.md](./add-nodes-edges.md) | ✅ | — |
| Get Knowledge Graph | Get a knowledge graph | [docs/features/get-knowledge-graph.md](./get-knowledge-graph.md) | ✅ | — |

### Plugin System

| Feature | Description | Documentation | Status | Release |
|---------|-------------|---------------|--------|---------|
| List Plugins | List market plugins | [docs/features/list-plugins.md](./list-plugins.md) | ✅ | — |
| Install Plugin | Install a market plugin | [docs/features/install-plugin.md](./install-plugin.md) | ✅ | — |
| Plugin Offers | Get offers from specific plugins | [docs/features/plugin-offers.md](./plugin-offers.md) | ✅ | — |

### Parameter Automation

| Feature | Description | Documentation | Status | Release |
|---------|-------------|---------------|--------|---------|
| Apply Parameters | Apply governance-approved parameters to market | [docs/features/apply-parameters.md](./apply-parameters.md) | ✅ | v0.10.1 |

### Advanced Market (Deprecated)

| Feature | Description | Documentation | Status | Release |
|---------|-------------|---------------|--------|---------|
| ~~Pricing Strategies~~ | ~~TIME_BASED, REPUTATION_BASED, MULTI_FACTOR, PREDICTIVE~~ | [docs/market/advanced-market/02-pricing-strategies.md](../market/advanced-market/02-pricing-strategies.md) | ~~Deprecated~~ | v0.5.0 |
| ~~ML-Based Search~~ | ~~Advanced search and recommendations~~ | [docs/market/advanced-market/04-ml-search.md](../market/advanced-market/04-ml-search.md) | ~~Deprecated~~ | v0.5.0 |
| ~~External Providers~~ | ~~AWS/GCP/Azure integrations~~ | [docs/market/advanced-market/06-external-providers.md](../market/advanced-market/06-external-providers.md) | ~~Deprecated~~ | v0.5.0 |

---
