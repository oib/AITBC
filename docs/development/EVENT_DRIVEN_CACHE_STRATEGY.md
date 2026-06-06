# Event-Driven Redis Caching Strategy for Global Edge Nodes

## Overview

This document describes the implementation of an event-driven Redis caching strategy for the AITBC platform, specifically designed to handle distributed edge nodes with immediate propagation of GPU availability and pricing changes on booking/cancellation events.

## Architecture

### Multi-Tier Caching

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Edge Node 1   │    │   Edge Node 2   │    │   Edge Node N   │
│                 │    │                 │    │                 │
│ ┌─────────────┐ │    │ ┌─────────────┐ │    │ ┌─────────────┐ │
│ │   L1 Cache  │ │    │ │   L1 Cache  │ │    │ │   L1 Cache  │ │
│ │   (Memory)  │ │    │ │   (Memory)  │ │    │ │   (Memory)  │ │
│ └─────────────┘ │    │ └─────────────┘ │    │ └─────────────┘ │
└─────────┬───────┘    └─────────┬───────┘    └─────────┬───────┘
          │                      │                      │
          └──────────────────────┼──────────────────────┘
                                 │
                    ┌─────────────┴─────────────┐
                    │      Redis Cluster       │
                    │     (L2 Distributed)     │
                    │                           │
                    │ ┌─────────────────────┐   │
                    │ │   Pub/Sub Channel   │   │
                    │ │ Cache Invalidation  │   │
                    │ └─────────────────────┘   │
                    └─────────────────────────┘
```

### Event-Driven Invalidation Flow

```
Booking/Cancellation Event
           │
           ▼
    Event Publisher
           │
           ▼
    Redis Pub/Sub
           │
           ▼
    Event Subscribers
    (All Edge Nodes)
           │
           ▼
    Cache Invalidation
    (L1 + L2 Cache)
           │
           ▼
    Immediate Propagation
```

## Key Features

### 1. Event-Driven Cache Invalidation

**Problem Solved**: TTL-only caching causes stale data propagation delays across edge nodes.

**Solution**: Real-time event-driven invalidation using Redis pub/sub for immediate propagation.

**Critical Data Types**:
- GPU availability status
- GPU pricing information  
- Order book data
- Provider status

### 2. Multi-Tier Cache Architecture

**L1 Cache (Memory)**:
- Fastest access (sub-millisecond)
- Limited size (1000-5000 entries)
- Shorter TTL (30-60 seconds)
- Immediate invalidation on events

**L2 Cache (Redis)**:
- Distributed across all edge nodes
- Larger capacity (GBs)
- Longer TTL (5-60 minutes)
- Event-driven updates

### 3. Distributed Edge Node Coordination

**Node Identification**:
- Unique node IDs for each edge node
- Regional grouping for optimization
- Network tier classification (edge/regional/global)

**Event Propagation**:
- Pub/sub for real-time events
- Event queuing for reliability
- Automatic failover and recovery

## Implementation Details

### Cache Event Types

```python
class CacheEventType(Enum):
    GPU_AVAILABILITY_CHANGED = "gpu_availability_changed"
    PRICING_UPDATED = "pricing_updated"
    BOOKING_CREATED = "booking_created"
    BOOKING_CANCELLED = "booking_cancelled"
    PROVIDER_STATUS_CHANGED = "provider_status_changed"
    MARKET_STATS_UPDATED = "market_stats_updated"
    ORDER_BOOK_UPDATED = "order_book_updated"
    MANUAL_INVALIDATION = "manual_invalidation"
```

### Cache Configurations

| Data Type | TTL | Event-Driven | Critical | Memory Limit |
|-----------|-----|--------------|----------|--------------|
| GPU Availability | 30s | ✅ | ✅ | 100MB |
| GPU Pricing | 60s | ✅ | ✅ | 50MB |
| Order Book | 5s | ✅ | ✅ | 200MB |
| Provider Status | 120s | ✅ | ❌ | 50MB |
| Market Stats | 300s | ✅ | ❌ | 100MB |
| Historical Data | 3600s | ❌ | ❌ | 500MB |

### Event Structure

```python
@dataclass
class CacheEvent:
    event_type: CacheEventType
    resource_id: str
    data: Dict[str, Any]
    timestamp: float
    source_node: str
    event_id: str
    affected_namespaces: List[str]
```

## Usage Examples

### Basic Cache Operations

```python
from aitbc_cache import init_marketplace_cache, get_marketplace_cache

# Initialize cache manager
cache_manager = await init_marketplace_cache(
    redis_url="redis://redis-cluster:6379/0",
    node_id="edge_node_us_east_1",
    region="us-east"
)

# Get GPU availability
gpus = await cache_manager.get_gpu_availability(
    region="us-east",
    gpu_type="RTX 3080"
)

# Update GPU status (triggers event)
await cache_manager.update_gpu_status("gpu_123", "busy")
```

### Booking Operations with Cache Updates

```python
# Create booking (automatically updates caches)
booking = BookingInfo(
    booking_id="booking_456",
    gpu_id="gpu_123",
    user_id="user_789",
    start_time=datetime.utcnow(),
    end_time=datetime.utcnow() + timedelta(hours=2),
    status="active",
    total_cost=0.2
)

success = await cache_manager.create_booking(booking)
# This triggers:
# 1. GPU availability update
# 2. Pricing recalculation
# 3. Order book invalidation
# 4. Market stats update
# 5. Event publishing to all nodes
```

### Event-Driven Pricing Updates

```python
# Update pricing (immediately propagated)
await cache_manager.update_gpu_pricing("RTX 3080", 0.15, "us-east")

# All edge nodes receive this event instantly
# and invalidate their pricing caches
```

## Deployment Configuration

### Environment Variables

```bash
# Redis Configuration
REDIS_HOST=redis-cluster.internal
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=your_redis_password
REDIS_SSL=true
REDIS_MAX_CONNECTIONS=50

# Edge Node Configuration
EDGE_NODE_ID=edge_node_us_east_1
EDGE_NODE_REGION=us-east
EDGE_NODE_DATACENTER=dc1
EDGE_NODE_CACHE_TIER=edge

# Cache Configuration
CACHE_L1_SIZE=1000
CACHE_ENABLE_EVENT_DRIVEN=true
CACHE_ENABLE_METRICS=true
CACHE_HEALTH_CHECK_INTERVAL=30

# Security
CACHE_ENABLE_TLS=true
CACHE_REQUIRE_AUTH=true
CACHE_AUTH_TOKEN=your_auth_token
```

### Redis Cluster Setup

```yaml
# docker-compose.yml
version: '3.8'
services:
  redis-master:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    command: redis-server --appendonly yes --cluster-enabled yes
    
  redis-replica-1:
    image: redis:7-alpine
    ports:
      - "6380:6379"
    command: redis-server --appendonly yes --cluster-enabled yes
    
  redis-replica-2:
    image: redis:7-alpine
    ports:
      - "6381:6379"
    command: redis-server --appendonly yes --cluster-enabled yes
```

## Performance Optimization

### Cache Hit Ratios

**Target Performance**:
- L1 Cache Hit Ratio: >80%
- L2 Cache Hit Ratio: >95%
- Event Propagation Latency: <100ms
- Total Cache Response Time: <5ms

### Optimization Strategies

1. **L1 Cache Sizing**:
   - Edge nodes: 500 entries (faster lookup)
   - Regional nodes: 2000 entries (better coverage)
   - Global nodes: 5000 entries (maximum coverage)

2. **Event Processing**:
   - Batch event processing for high throughput
   - Event deduplication to prevent storms
   - Priority queues for critical events

3. **Memory Management**:
   - LFU eviction for frequently accessed data
   - Time-based expiration for stale data
   - Memory pressure monitoring

## Monitoring and Observability

### Cache Metrics

```python
# Get cache statistics
stats = await cache_manager.get_cache_stats()

# Key metrics:
# - cache_hits / cache_misses
# - events_processed
# - invalidations
# - l1_cache_size
# - redis_memory_used_mb
```

### Health Checks

```python
# Comprehensive health check
health = await cache_manager.health_check()

# Health indicators:
# - redis_connected
# - pubsub_active
# - event_queue_size
# - last_event_age
```

### Alerting Thresholds

| Metric | Warning | Critical |
|--------|---------|----------|
| Cache Hit Ratio | <70% | <50% |
| Event Queue Size | >1000 | >5000 |
| Event Latency | >500ms | >2000ms |
| Redis Memory | >80% | >95% |
| Connection Failures | >5/min | >20/min |

## Security Considerations

### Network Security

1. **TLS Encryption**: All Redis connections use TLS
2. **Authentication**: Redis AUTH tokens required
3. **Network Isolation**: Redis cluster in private VPC
4. **Access Control**: IP whitelisting for edge nodes

### Data Security

1. **Sensitive Data**: No private keys or passwords cached
2. **Data Encryption**: At-rest encryption for Redis
3. **Access Logging**: All cache operations logged
4. **Data Retention**: Automatic cleanup of old data

## Troubleshooting

### Common Issues

1. **Stale Cache Data**:
   - Check event propagation
   - Verify pub/sub connectivity
   - Review event queue size

2. **High Memory Usage**:
   - Monitor L1 cache size
   - Check TTL configurations
   - Review eviction policies

3. **Slow Performance**:
   - Check Redis connection pool
   - Monitor network latency
   - Review cache hit ratios

### Debug Commands

```python
# Check cache health
health = await cache_manager.health_check()
print(f"Cache status: {health['status']}")

# Check event processing
stats = await cache_manager.get_cache_stats()
print(f"Events processed: {stats['events_processed']}")

# Manual cache invalidation
await cache_manager.invalidate_cache('gpu_availability', reason='debug')
```

## Best Practices

### 1. Cache Key Design

- Use consistent naming conventions
- Include relevant parameters in key
- Avoid key collisions
- Use appropriate TTL values

### 2. Event Design

- Include all necessary context
- Use unique event IDs
- Timestamp all events
- Handle event idempotency

### 3. Error Handling

- Graceful degradation on Redis failures
- Retry logic for transient errors
- Fallback to database when needed
- Comprehensive error logging

### 4. Performance Optimization

- Batch operations when possible
- Use connection pooling
- Monitor memory usage
- Optimize serialization

## Migration Guide

### From TTL-Only Caching

1. **Phase 1**: Deploy event-driven cache alongside existing cache
2. **Phase 2**: Enable event-driven invalidation for critical data
3. **Phase 3**: Migrate all data types to event-driven
4. **Phase 4**: Remove old TTL-only cache

### Configuration Migration

```python
# Old configuration
cache_ttl = {
    'gpu_availability': 30,
    'gpu_pricing': 60
}

# New configuration
cache_configs = {
    'gpu_availability': CacheConfig(
        namespace='gpu_avail',
        ttl_seconds=30,
        event_driven=True,
        critical_data=True
    ),
    'gpu_pricing': CacheConfig(
        namespace='gpu_pricing',
        ttl_seconds=60,
        event_driven=True,
        critical_data=True
    )
}
```

## Future Enhancements

### Planned Features

1. **Intelligent Caching**: ML-based cache preloading
2. **Adaptive TTL**: Dynamic TTL based on access patterns
3. **Multi-Region Replication**: Cross-region cache synchronization
4. **Cache Analytics**: Advanced usage analytics and optimization

### Scalability Improvements

1. **Sharding**: Horizontal scaling of cache data
2. **Compression**: Data compression for memory efficiency
3. **Tiered Storage**: SSD/HDD tiering for large datasets
4. **Edge Computing**: Push cache closer to users

## Conclusion

The event-driven Redis caching strategy provides:

- **Immediate Propagation**: Sub-100ms event propagation across all edge nodes
- **High Performance**: Multi-tier caching with >95% hit ratios
- **Scalability**: Distributed architecture supporting global edge deployment
- **Reliability**: Automatic failover and recovery mechanisms
- **Security**: Enterprise-grade security with TLS and authentication

This system ensures that GPU availability and pricing changes are immediately propagated to all edge nodes, eliminating stale data issues and providing a consistent user experience across the global AITBC platform.
