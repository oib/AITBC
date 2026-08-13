# Marketplace

## 3. Marketplace

### Core Marketplace

| Feature | Description | Documentation | Status | Release |
|---------|-------------|---------------|--------|---------|
| List Offers | List offers with filters (status, region, gpu_model, chain_id) | [docs/api/marketplace-api.md](../api/marketplace-api.md) | ✅ | — |
| Get Offer | Get a specific offer by ID | [docs/api/marketplace-api.md](../api/marketplace-api.md) | ✅ | — |
| Create Offer | Create a new marketplace offer | [docs/api/marketplace-api.md](../api/marketplace-api.md) | ✅ | — |
| Cancel Offer | Cancel a marketplace offer | [docs/api/marketplace-api.md](../api/marketplace-api.md) | ✅ | — |
| Book Offer | Book/purchase an offer with escrow creation | [docs/api/marketplace-api.md](../api/marketplace-api.md) | ✅ | — |
| Offer History | Get offer history | [docs/features/offer-history.md](./offer-history.md) | ✅ | — |
| Match Request | Match a compute request to best GPU offer (price-time priority) | [docs/features/match-request.md](./match-request.md) | ✅ | v0.6.6 |
| Marketplace Analytics | Get marketplace analytics and performance metrics | [docs/features/marketplace-analytics.md](./marketplace-analytics.md) | ✅ | — |
| Dynamic Pricing | Apply dynamic pricing strategies to offers | [docs/features/dynamic-pricing.md](./dynamic-pricing.md) | ✅ | — |

### Edge Integration

| Feature | Description | Documentation | Status | Release |
|---------|-------------|---------------|--------|---------|
| Edge Advertise | Advertise edge node GPU capabilities to marketplace | [docs/features/edge-advertise.md](./edge-advertise.md) | ✅ | v0.6.6 |
| List Edge Nodes | List all registered edge nodes | [docs/features/list-edge-nodes.md](./list-edge-nodes.md) | ✅ | v0.6.6 |
| Edge Health | Get edge node health status | [docs/features/edge-health.md](./edge-health.md) | ✅ | v0.6.6 |

### Ratings & Reputation

| Feature | Description | Documentation | Status | Release |
|---------|-------------|---------------|--------|---------|
| Rate Offer | Rate a marketplace offer/service | [docs/features/rate-offer.md](./rate-offer.md) | ✅ | — |
| Get Ratings | Get ratings for an offer | [docs/features/get-ratings.md](./get-ratings.md) | ✅ | — |
| Sync Ratings | Sync ratings to blockchain | [docs/features/sync-ratings.md](./sync-ratings.md) | ✅ | — |
| Service Reputation | Service reputation system | [docs/marketplace/service-reputation-system.md](../marketplace/service-reputation-system.md) | ✅ | — |

### Knowledge Graph

| Feature | Description | Documentation | Status | Release |
|---------|-------------|---------------|--------|---------|
| Create Knowledge Graph | Create a knowledge graph | [docs/features/create-knowledge-graph.md](./create-knowledge-graph.md) | ✅ | — |
| Add Nodes/Edges | Add nodes and edges to a knowledge graph | [docs/features/add-nodes-edges.md](./add-nodes-edges.md) | ✅ | — |
| Get Knowledge Graph | Get a knowledge graph | [docs/features/get-knowledge-graph.md](./get-knowledge-graph.md) | ✅ | — |

### Plugin System

| Feature | Description | Documentation | Status | Release |
|---------|-------------|---------------|--------|---------|
| List Plugins | List marketplace plugins | [docs/features/list-plugins.md](./list-plugins.md) | ✅ | — |
| Install Plugin | Install a marketplace plugin | [docs/features/install-plugin.md](./install-plugin.md) | ✅ | — |
| Plugin Offers | Get offers from specific plugins | [docs/features/plugin-offers.md](./plugin-offers.md) | ✅ | — |

### Parameter Automation

| Feature | Description | Documentation | Status | Release |
|---------|-------------|---------------|--------|---------|
| Apply Parameters | Apply governance-approved parameters to marketplace | [docs/features/apply-parameters.md](./apply-parameters.md) | ✅ | v0.10.1 |

### Advanced Marketplace (Deprecated)

| Feature | Description | Documentation | Status | Release |
|---------|-------------|---------------|--------|---------|
| ~~Pricing Strategies~~ | ~~TIME_BASED, REPUTATION_BASED, MULTI_FACTOR, PREDICTIVE~~ | [docs/marketplace/advanced-marketplace/02-pricing-strategies.md](../marketplace/advanced-marketplace/02-pricing-strategies.md) | ~~Deprecated~~ | v0.5.0 |
| ~~ML-Based Search~~ | ~~Advanced search and recommendations~~ | [docs/marketplace/advanced-marketplace/04-ml-search.md](../marketplace/advanced-marketplace/04-ml-search.md) | ~~Deprecated~~ | v0.5.0 |
| ~~External Providers~~ | ~~AWS/GCP/Azure integrations~~ | [docs/marketplace/advanced-marketplace/06-external-providers.md](../marketplace/advanced-marketplace/06-external-providers.md) | ~~Deprecated~~ | v0.5.0 |

---
