"""
Cache Configuration for AITBC Event-Driven Caching System

Configuration settings for Redis distributed caching with event-driven invalidation
across global edge nodes for GPU marketplace and real-time data.
"""

import os
from typing import Dict, Any, Optional
from dataclasses import dataclass


@dataclass
class RedisConfig:
    """Redis connection configuration"""
    host: str = "localhost"
    port: int = 6379
    db: int = 0
    password: Optional[str] = None
    ssl: bool = False
    max_connections: int = 20
    socket_timeout: int = 5
    socket_connect_timeout: int = 5
    retry_on_timeout: bool = True
    health_check_interval: int = 30


@dataclass
class CacheConfig:
    """Cache behavior configuration"""
    l1_cache_size: int = 1000
    l1_ttl_multiplier: float = 0.5  # L1 cache TTL as fraction of L2 TTL
    event_queue_size: int = 10000
    event_processing_timeout: int = 30
    invalidation_batch_size: int = 100
    stats_retention_hours: int = 24
    health_check_interval: int = 60


@dataclass
class EdgeNodeConfig:
    """Edge node configuration"""
    node_id: Optional[str] = None
    region: str = "default"
    datacenter: str = "default"
    rack: Optional[str] = None
    availability_zone: Optional[str] = None
    network_tier: str = "standard"  # standard, premium, edge
    cache_tier: str = "edge"  # edge, regional, global


@dataclass
class EventDrivenCacheSettings:
    """Complete event-driven cache settings"""
    redis: RedisConfig
    cache: CacheConfig
    edge_node: EdgeNodeConfig
    
    # Feature flags
    enable_l1_cache: bool = True
    enable_event_driven_invalidation: bool = True
    enable_compression: bool = True
    enable_metrics: bool = True
    enable_health_checks: bool = True
    
    # Performance settings
    connection_pool_size: int = 20
    max_event_queue_size: int = 10000
    event_processing_workers: int = 4
    cache_warmup_enabled: bool = True
    
    # Security settings
    enable_tls: bool = False
    require_auth: bool = False
    auth_token: Optional[str] = None


def load_config_from_env() -> EventDrivenCacheSettings:
    """Load configuration from environment variables"""
    
    # Redis configuration
    redis_config = RedisConfig(
        host=os.getenv("REDIS_HOST", "localhost"),
        port=int(os.getenv("REDIS_PORT", "6379")),
        db=int(os.getenv("REDIS_DB", "0")),
        password=os.getenv("REDIS_PASSWORD"),
        ssl=os.getenv("REDIS_SSL", "false").lower() == "true",
        max_connections=int(os.getenv("REDIS_MAX_CONNECTIONS", "20")),
        socket_timeout=int(os.getenv("REDIS_SOCKET_TIMEOUT", "5")),
        socket_connect_timeout=int(os.getenv("REDIS_SOCKET_CONNECT_TIMEOUT", "5")),
        retry_on_timeout=os.getenv("REDIS_RETRY_ON_TIMEOUT", "true").lower() == "true",
        health_check_interval=int(os.getenv("REDIS_HEALTH_CHECK_INTERVAL", "30"))
    )
    
    # Cache configuration
    cache_config = CacheConfig(
        l1_cache_size=int(os.getenv("CACHE_L1_SIZE", "1000")),
        l1_ttl_multiplier=float(os.getenv("CACHE_L1_TTL_MULTIPLIER", "0.5")),
        event_queue_size=int(os.getenv("CACHE_EVENT_QUEUE_SIZE", "10000")),
        event_processing_timeout=int(os.getenv("CACHE_EVENT_PROCESSING_TIMEOUT", "30")),
        invalidation_batch_size=int(os.getenv("CACHE_INVALIDATION_BATCH_SIZE", "100")),
        stats_retention_hours=int(os.getenv("CACHE_STATS_RETENTION_HOURS", "24")),
        health_check_interval=int(os.getenv("CACHE_HEALTH_CHECK_INTERVAL", "60"))
    )
    
    # Edge node configuration
    edge_node_config = EdgeNodeConfig(
        node_id=os.getenv("EDGE_NODE_ID"),
        region=os.getenv("EDGE_NODE_REGION", "default"),
        datacenter=os.getenv("EDGE_NODE_DATACENTER", "default"),
        rack=os.getenv("EDGE_NODE_RACK"),
        availability_zone=os.getenv("EDGE_NODE_AVAILABILITY_ZONE"),
        network_tier=os.getenv("EDGE_NODE_NETWORK_TIER", "standard"),
        cache_tier=os.getenv("EDGE_NODE_CACHE_TIER", "edge")
    )
    
    # Feature flags
    enable_l1_cache = os.getenv("CACHE_ENABLE_L1", "true").lower() == "true"
    enable_event_driven_invalidation = os.getenv("CACHE_ENABLE_EVENT_DRIVEN", "true").lower() == "true"
    enable_compression = os.getenv("CACHE_ENABLE_COMPRESSION", "true").lower() == "true"
    enable_metrics = os.getenv("CACHE_ENABLE_METRICS", "true").lower() == "true"
    enable_health_checks = os.getenv("CACHE_ENABLE_HEALTH_CHECKS", "true").lower() == "true"
    
    # Performance settings
    connection_pool_size = int(os.getenv("CACHE_CONNECTION_POOL_SIZE", "20"))
    max_event_queue_size = int(os.getenv("CACHE_MAX_EVENT_QUEUE_SIZE", "10000"))
    event_processing_workers = int(os.getenv("CACHE_EVENT_PROCESSING_WORKERS", "4"))
    cache_warmup_enabled = os.getenv("CACHE_WARMUP_ENABLED", "true").lower() == "true"
    
    # Security settings
    enable_tls = os.getenv("CACHE_ENABLE_TLS", "false").lower() == "true"
    require_auth = os.getenv("CACHE_REQUIRE_AUTH", "false").lower() == "true"
    auth_token = os.getenv("CACHE_AUTH_TOKEN")
    
    return EventDrivenCacheSettings(
        redis=redis_config,
        cache=cache_config,
        edge_node=edge_node_config,
        enable_l1_cache=enable_l1_cache,
        enable_event_driven_invalidation=enable_event_driven_invalidation,
        enable_compression=enable_compression,
        enable_metrics=enable_metrics,
        enable_health_checks=enable_health_checks,
        connection_pool_size=connection_pool_size,
        max_event_queue_size=max_event_queue_size,
        event_processing_workers=event_processing_workers,
        cache_warmup_enabled=cache_warmup_enabled,
        enable_tls=enable_tls,
        require_auth=require_auth,
        auth_token=auth_token
    )


def get_redis_url(config: RedisConfig) -> str:
    """Construct Redis URL from configuration"""
    auth_part = ""
    if config.password:
        auth_part = f":{config.password}@"
    
    ssl_part = "s" if config.ssl else ""
    
    return f"redis{ssl_part}://{auth_part}{config.host}:{config.port}/{config.db}"


# Default configurations for different environments

def get_development_config() -> EventDrivenCacheSettings:
    """Development environment configuration"""
    return EventDrivenCacheSettings(
        redis=RedisConfig(
            host="localhost",
            port=6379,
            db=1,  # Use different DB for development
            ssl=False
        ),
        cache=CacheConfig(
            l1_cache_size=100,  # Smaller cache for development
            l1_ttl_multiplier=0.3,
            event_queue_size=1000
        ),
        edge_node=EdgeNodeConfig(
            node_id="dev_node",
            region="development"
        ),
        enable_metrics=False,  # Disable overhead in development
        enable_health_checks=False
    )


def get_staging_config() -> EventDrivenCacheSettings:
    """Staging environment configuration"""
    return EventDrivenCacheSettings(
        redis=RedisConfig(
            host="redis-staging.internal",
            port=6379,
            db=0,
            ssl=True
        ),
        cache=CacheConfig(
            l1_cache_size=500,
            l1_ttl_multiplier=0.4,
            event_queue_size=5000
        ),
        edge_node=EdgeNodeConfig(
            node_id=None,  # Auto-generate
            region="staging"
        ),
        enable_metrics=True,
        enable_health_checks=True
    )


def get_production_config() -> EventDrivenCacheSettings:
    """Production environment configuration"""
    return EventDrivenCacheSettings(
        redis=RedisConfig(
            host=os.getenv("REDIS_CLUSTER_HOST", "redis-cluster.internal"),
            port=int(os.getenv("REDIS_CLUSTER_PORT", "6379")),
            db=0,
            password=os.getenv("REDIS_CLUSTER_PASSWORD"),
            ssl=True,
            max_connections=50,
            socket_timeout=10,
            socket_connect_timeout=10,
            health_check_interval=15
        ),
        cache=CacheConfig(
            l1_cache_size=2000,
            l1_ttl_multiplier=0.6,
            event_queue_size=20000,
            event_processing_timeout=60,
            invalidation_batch_size=200,
            health_check_interval=30
        ),
        edge_node=EdgeNodeConfig(
            node_id=None,  # Auto-generate from hostname/IP
            region=os.getenv("EDGE_NODE_REGION", "global"),
            datacenter=os.getenv("EDGE_NODE_DATACENTER"),
            availability_zone=os.getenv("EDGE_NODE_AZ"),
            network_tier="premium",
            cache_tier="edge"
        ),
        enable_l1_cache=True,
        enable_event_driven_invalidation=True,
        enable_compression=True,
        enable_metrics=True,
        enable_health_checks=True,
        connection_pool_size=50,
        max_event_queue_size=20000,
        event_processing_workers=8,
        cache_warmup_enabled=True,
        enable_tls=True,
        require_auth=True,
        auth_token=os.getenv("CACHE_AUTH_TOKEN")
    )


def get_edge_node_config(region: str) -> EventDrivenCacheSettings:
    """Configuration for edge nodes in specific regions"""
    base_config = get_production_config()
    
    # Override edge node specific settings
    base_config.edge_node.region = region
    base_config.edge_node.cache_tier = "edge"
    base_config.edge_node.network_tier = "edge"
    
    # Edge nodes have smaller L1 cache but faster event processing
    base_config.cache.l1_cache_size = 500
    base_config.cache.l1_ttl_multiplier = 0.3
    base_config.event_processing_workers = 2
    
    return base_config


def get_regional_cache_config(region: str) -> EventDrivenCacheSettings:
    """Configuration for regional cache nodes"""
    base_config = get_production_config()
    
    # Override regional cache settings
    base_config.edge_node.region = region
    base_config.edge_node.cache_tier = "regional"
    base_config.edge_node.network_tier = "premium"
    
    # Regional caches have larger L1 cache
    base_config.cache.l1_cache_size = 5000
    base_config.cache.l1_ttl_multiplier = 0.8
    base_config.event_processing_workers = 6
    
    return base_config


# Configuration validation
def validate_config(config: EventDrivenCacheSettings) -> bool:
    """Validate cache configuration"""
    errors = []
    
    # Redis configuration validation
    if not config.redis.host:
        errors.append("Redis host is required")
    
    if not (1 <= config.redis.port <= 65535):
        errors.append("Redis port must be between 1 and 65535")
    
    if not (0 <= config.redis.db <= 15):
        errors.append("Redis DB must be between 0 and 15")
    
    # Cache configuration validation
    if config.cache.l1_cache_size <= 0:
        errors.append("L1 cache size must be positive")
    
    if not (0.1 <= config.cache.l1_ttl_multiplier <= 1.0):
        errors.append("L1 TTL multiplier must be between 0.1 and 1.0")
    
    if config.cache.event_queue_size <= 0:
        errors.append("Event queue size must be positive")
    
    # Edge node configuration validation
    if not config.edge_node.region:
        errors.append("Edge node region is required")
    
    if config.edge_node.cache_tier not in ["edge", "regional", "global"]:
        errors.append("Cache tier must be one of: edge, regional, global")
    
    if errors:
        raise ValueError(f"Configuration validation failed: {', '.join(errors)}")
    
    return True


# Environment-specific configuration loader
def get_config_for_environment(env: str = None) -> EventDrivenCacheSettings:
    """Get configuration for specific environment"""
    env = env or os.getenv("ENVIRONMENT", "development").lower()
    
    if env == "production":
        return get_production_config()
    elif env == "staging":
        return get_staging_config()
    elif env == "development":
        return get_development_config()
    else:
        # Default to environment variables
        return load_config_from_env()
