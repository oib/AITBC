# ML-Based Search and Recommendations

## Overview

The ResourceMatcher service provides intelligent resource matching with ML-based ranking and personalized recommendations.

## Features

### Advanced Search
- Multi-factor filtering (memory, model, region, price, capabilities)
- ML-based ranking of results
- Search history tracking for personalization

### Recommendations
- Personalized GPU recommendations based on user profile
- Popular GPUs fallback for new users
- Preference learning from search history

### Similarity Search
- Vector embeddings for GPU resources
- Cosine similarity-based recommendations
- Real-time embedding generation

## Usage Example

```python
from app.contexts.marketplace.services.resource_matcher import ResourceMatcher

matcher = ResourceMatcher(session)

# Advanced search with ML ranking
results = matcher.advanced_search(
    filters={
        "gpu_memory_min": 16,
        "model": "A100",
        "region": "us-east",
        "price_max": 1.0
    },
    user_id="user-123",
    limit=10
)

# Get personalized recommendations
recommendations = matcher.get_recommendations(
    user_id="user-123",
    limit=5
)

# Find similar GPUs
similar = matcher.find_similar_resources(
    resource_id="gpu-456",
    limit=3
)
```
