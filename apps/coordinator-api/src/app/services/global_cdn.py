"""
Global CDN Integration - Phase 6.3 Implementation
Content delivery network optimization with edge computing and caching
"""

import asyncio
import gzip
import time
import zlib
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import StrEnum
from typing import Any
from uuid import uuid4

from aitbc import get_logger

logger = get_logger(__name__)


class CDNProvider(StrEnum):
    """CDN providers"""

    CLOUDFLARE = "cloudflare"
    AKAMAI = "akamai"
    FASTLY = "fastly"
    AWS_CLOUDFRONT = "aws_cloudfront"
    AZURE_CDN = "azure_cdn"
    GOOGLE_CDN = "google_cdn"


class CacheStrategy(StrEnum):
    """Caching strategies"""

    TTL_BASED = "ttl_based"
    LRU = "lru"
    LFU = "lfu"
    ADAPTIVE = "adaptive"
    EDGE_OPTIMIZED = "edge_optimized"


class CompressionType(StrEnum):
    """Compression types"""

    GZIP = "gzip"
    BROTLI = "brotli"
    DEFLATE = "deflate"
    NONE = "none"


@dataclass
class EdgeLocation:
    """Edge location configuration"""

    location_id: str
    name: str
    code: str  # IATA airport code
    location: dict[str, float]  # lat, lng
    provider: CDNProvider
    endpoints: list[str]
    capacity: dict[str, int]  # max_connections, bandwidth_mbps
    current_load: dict[str, int] = field(default_factory=dict)
    cache_size_gb: int = 100
    hit_rate: float = 0.0
    avg_response_time_ms: float = 0.0
    status: str = "active"
    last_health_check: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class CacheEntry:
    """Cache entry"""

    cache_key: str
    content: bytes
    content_type: str
    size_bytes: int
    compressed: bool
    compression_type: CompressionType
    created_at: datetime
    expires_at: datetime
    access_count: int = 0
    last_accessed: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    edge_locations: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class CDNConfig:
    """CDN configuration"""

    provider: CDNProvider
    edge_locations: list[EdgeLocation]
    cache_strategy: CacheStrategy
    compression_enabled: bool = True
    compression_types: list[CompressionType] = field(default_factory=lambda: [CompressionType.GZIP, CompressionType.BROTLI])
    default_ttl: timedelta = field(default_factory=lambda: timedelta(hours=1))
    max_cache_size_gb: int = 1000
    purge_interval: timedelta = field(default_factory=lambda: timedelta(minutes=5))
    health_check_interval: timedelta = field(default_factory=lambda: timedelta(minutes=2))


class EdgeCache:
    """Edge caching system"""

    def __init__(self, location_id: str, max_size_gb: int = 100):
        self.location_id = location_id
        self.max_size_bytes = max_size_gb * 1024 * 1024 * 1024
        self.cache = {}
        self.cache_size_bytes = 0
        self.access_times = {}
        self.logger = get_logger(f"edge_cache_{location_id}")

    async def get(self, cache_key: str) -> CacheEntry | None:
        """Get cached content"""

        entry = self.cache.get(cache_key)
        if entry:
            # Check if expired
            if datetime.now(timezone.utc) > entry.expires_at:
                await self.remove(cache_key)
                return None

            # Update access statistics
            entry.access_count += 1
            entry.last_accessed = datetime.now(timezone.utc)
            self.access_times[cache_key] = datetime.now(timezone.utc)

            self.logger.debug(f"Cache hit: {cache_key}")
            return entry

        self.logger.debug(f"Cache miss: {cache_key}")
        return None

    async def put(
        self,
        cache_key: str,
        content: bytes,
        content_type: str,
        ttl: timedelta,
        compression_type: CompressionType = CompressionType.NONE,
    ) -> bool:
        """Cache content"""

        try:
            # Compress content if enabled
            compressed_content = content
            is_compressed = False

            if compression_type != CompressionType.NONE:
                compressed_content = await self._compress_content(content, compression_type)
                is_compressed = True

            # Check cache size limit
            entry_size = len(compressed_content)

            # Evict if necessary
            while (self.cache_size_bytes + entry_size) > self.max_size_bytes and self.cache:
                await self._evict_lru()

            # Create cache entry
            entry = CacheEntry(
                cache_key=cache_key,
                content=compressed_content,
                content_type=content_type,
                size_bytes=entry_size,
                compressed=is_compressed,
                compression_type=compression_type,
                created_at=datetime.now(timezone.utc),
                expires_at=datetime.now(timezone.utc) + ttl,
                edge_locations=[self.location_id],
            )

            # Store entry
            self.cache[cache_key] = entry
            self.cache_size_bytes += entry_size
            self.access_times[cache_key] = datetime.now(timezone.utc)

            self.logger.debug(f"Content cached: {cache_key} ({entry_size} bytes)")
            return True

        except Exception as e:
            self.logger.error(f"Cache put failed: {e}")
            return False

    async def remove(self, cache_key: str) -> bool:
        """Remove cached content"""

        entry = self.cache.pop(cache_key, None)
        if entry:
            self.cache_size_bytes -= entry.size_bytes
            self.access_times.pop(cache_key, None)

            self.logger.debug(f"Content removed from cache: {cache_key}")
            return True

        return False

    async def _compress_content(self, content: bytes, compression_type: CompressionType) -> bytes:
        """Compress content"""

        if compression_type == CompressionType.GZIP:
            return gzip.compress(content)
        elif compression_type == CompressionType.BROTLI:
            # Brotli compression (simplified)
            return zlib.compress(content, level=9)
        elif compression_type == CompressionType.DEFLATE:
            return zlib.compress(content)
        else:
            return content

    async def _decompress_content(self, content: bytes, compression_type: CompressionType) -> bytes:
        """Decompress content"""

        if compression_type == CompressionType.GZIP:
            return gzip.decompress(content)
        elif compression_type == CompressionType.BROTLI:
            return zlib.decompress(content)
        elif compression_type == CompressionType.DEFLATE:
            return zlib.decompress(content)
        else:
            return content

    async def _evict_lru(self):
        """Evict least recently used entry"""

        if not self.access_times:
            return

        # Find least recently used key
        lru_key = min(self.access_times, key=self.access_times.get)

        await self.remove(lru_key)

        self.logger.debug(f"LRU eviction: {lru_key}")

    async def get_cache_stats(self) -> dict[str, Any]:
        """Get cache statistics"""

        total_entries = len(self.cache)
        hit_rate = 0.0

        if total_entries > 0:
            total_accesses = sum(entry.access_count for entry in self.cache.values())
            hit_rate = total_accesses / (total_accesses + 1)  # Simplified hit rate calculation

        return {
            "location_id": self.location_id,
            "total_entries": total_entries,
            "cache_size_bytes": self.cache_size_bytes,
            "cache_size_gb": self.cache_size_bytes / (1024**3),
            "hit_rate": hit_rate,
            "utilization_percent": (self.cache_size_bytes / self.max_size_bytes) * 100,
        }


class CDNManager:
    """Global CDN manager"""

    def __init__(self, config: CDNConfig):
        self.config = config
        self.edge_caches = {}
        self.global_cache = {}
        self.purge_queue = []
        self.analytics = {"total_requests": 0, "cache_hits": 0, "cache_misses": 0, "edge_requests": {}, "bandwidth_saved": 0}
        self.logger = get_logger("cdn_manager")

    async def initialize(self) -> bool:
        """Initialize CDN manager"""

        try:
            # Initialize edge caches
            for location in self.config.edge_locations:
                edge_cache = EdgeCache(location.location_id, location.cache_size_gb)
                self.edge_caches[location.location_id] = edge_cache

            # Start background tasks
            asyncio.create_task(self._purge_expired_cache())
            asyncio.create_task(self._health_check_loop())

            self.logger.info(f"CDN manager initialized with {len(self.edge_caches)} edge locations")
            return True

        except Exception as e:
            self.logger.error(f"CDN manager initialization failed: {e}")
            return False

    async def get_content(self, cache_key: str, user_location: dict[str, float] | None = None) -> dict[str, Any]:
        """Get content from CDN"""

        try:
            self.analytics["total_requests"] += 1

            # Select optimal edge location
            edge_location = await self._select_edge_location(user_location)

            if not edge_location:
                # Fallback to origin
                return {"status": "edge_unavailable", "cache_hit": False}

            # Try edge cache first
            edge_cache = self.edge_caches.get(edge_location.location_id)
            if edge_cache:
                entry = await edge_cache.get(cache_key)
                if entry:
                    # Decompress if needed
                    content = await self._decompress_content(entry.content, entry.compression_type)

                    self.analytics["cache_hits"] += 1
                    self.analytics["edge_requests"][edge_location.location_id] = (
                        self.analytics["edge_requests"].get(edge_location.location_id, 0) + 1
                    )

                    return {
                        "status": "cache_hit",
                        "content": content,
                        "content_type": entry.content_type,
                        "edge_location": edge_location.location_id,
                        "compressed": entry.compressed,
                        "cache_age": (datetime.now(timezone.utc) - entry.created_at).total_seconds(),
                    }

            # Try global cache
            global_entry = self.global_cache.get(cache_key)
            if global_entry and datetime.now(timezone.utc) <= global_entry.expires_at:
                # Cache at edge location
                if edge_cache:
                    await edge_cache.put(
                        cache_key,
                        global_entry.content,
                        global_entry.content_type,
                        global_entry.expires_at - datetime.now(timezone.utc),
                        global_entry.compression_type,
                    )

                content = await self._decompress_content(global_entry.content, global_entry.compression_type)

                self.analytics["cache_hits"] += 1

                return {
                    "status": "global_cache_hit",
                    "content": content,
                    "content_type": global_entry.content_type,
                    "edge_location": edge_location.location_id if edge_location else None,
                }

            self.analytics["cache_misses"] += 1

            return {"status": "cache_miss", "edge_location": edge_location.location_id if edge_location else None}

        except Exception as e:
            self.logger.error(f"Content retrieval failed: {e}")
            return {"status": "error", "error": str(e)}

    async def put_content(
        self,
        cache_key: str,
        content: bytes,
        content_type: str,
        ttl: timedelta | None = None,
        edge_locations: list[str] | None = None,
    ) -> bool:
        """Cache content in CDN"""

        try:
            if ttl is None:
                ttl = self.config.default_ttl

            # Determine best compression
            compression_type = await self._select_compression_type(content, content_type)

            # Store in global cache
            global_entry = CacheEntry(
                cache_key=cache_key,
                content=content,
                content_type=content_type,
                size_bytes=len(content),
                compressed=False,
                compression_type=compression_type,
                created_at=datetime.now(timezone.utc),
                expires_at=datetime.now(timezone.utc) + ttl,
            )

            self.global_cache[cache_key] = global_entry

            # Cache at edge locations
            target_edges = edge_locations or list(self.edge_caches.keys())

            for edge_id in target_edges:
                edge_cache = self.edge_caches.get(edge_id)
                if edge_cache:
                    await edge_cache.put(cache_key, content, content_type, ttl, compression_type)

            self.logger.info(f"Content cached: {cache_key} at {len(target_edges)} edge locations")
            return True

        except Exception as e:
            self.logger.error(f"Content caching failed: {e}")
            return False

    async def _select_edge_location(self, user_location: dict[str, float] | None = None) -> EdgeLocation | None:
        """Select optimal edge location"""

        if not user_location:
            # Fallback to first available location
            available_locations = [loc for loc in self.config.edge_locations if loc.status == "active"]
            return available_locations[0] if available_locations else None

        user_lat = user_location.get("latitude", 0.0)
        user_lng = user_location.get("longitude", 0.0)

        # Find closest edge location
        available_locations = [loc for loc in self.config.edge_locations if loc.status == "active"]

        if not available_locations:
            return None

        closest_location = None
        min_distance = float("inf")

        for location in available_locations:
            loc_lat = location.location["latitude"]
            loc_lng = location.location["longitude"]

            # Calculate distance
            distance = self._calculate_distance(user_lat, user_lng, loc_lat, loc_lng)

            if distance < min_distance:
                min_distance = distance
                closest_location = location

        return closest_location

    def _calculate_distance(self, lat1: float, lng1: float, lat2: float, lng2: float) -> float:
        """Calculate distance between two points"""

        # Simplified distance calculation
        lat_diff = lat2 - lat1
        lng_diff = lng2 - lng1

        return (lat_diff**2 + lng_diff**2) ** 0.5

    async def _select_compression_type(self, content: bytes, content_type: str) -> CompressionType:
        """Select best compression type"""

        if not self.config.compression_enabled:
            return CompressionType.NONE

        # Check if content is compressible
        compressible_types = [
            "text/html",
            "text/css",
            "text/javascript",
            "application/json",
            "application/xml",
            "text/plain",
            "text/csv",
        ]

        if not any(ct in content_type for ct in compressible_types):
            return CompressionType.NONE

        # Test compression efficiency
        if len(content) < 1024:  # Don't compress very small content
            return CompressionType.NONE

        # Prefer Brotli for better compression ratio
        if CompressionType.BROTLI in self.config.compression_types:
            return CompressionType.BROTLI
        elif CompressionType.GZIP in self.config.compression_types:
            return CompressionType.GZIP

        return CompressionType.NONE

    async def purge_content(self, cache_key: str, edge_locations: list[str] | None = None) -> bool:
        """Purge content from CDN"""

        try:
            # Remove from global cache
            self.global_cache.pop(cache_key, None)

            # Remove from edge caches
            target_edges = edge_locations or list(self.edge_caches.keys())

            for edge_id in target_edges:
                edge_cache = self.edge_caches.get(edge_id)
                if edge_cache:
                    await edge_cache.remove(cache_key)

            self.logger.info(f"Content purged: {cache_key} from {len(target_edges)} edge locations")
            return True

        except Exception as e:
            self.logger.error(f"Content purge failed: {e}")
            return False

    async def _purge_expired_cache(self):
        """Background task to purge expired cache entries"""

        while True:
            try:
                await asyncio.sleep(self.config.purge_interval.total_seconds())

                current_time = datetime.now(timezone.utc)

                # Purge global cache
                expired_keys = [key for key, entry in self.global_cache.items() if current_time > entry.expires_at]

                for key in expired_keys:
                    self.global_cache.pop(key, None)

                # Purge edge caches
                for edge_cache in self.edge_caches.values():
                    expired_edge_keys = [key for key, entry in edge_cache.cache.items() if current_time > entry.expires_at]

                    for key in expired_edge_keys:
                        await edge_cache.remove(key)

                if expired_keys:
                    self.logger.debug(f"Purged {len(expired_keys)} expired cache entries")

            except Exception as e:
                self.logger.error(f"Cache purge failed: {e}")

    async def _health_check_loop(self):
        """Background task for health checks"""

        while True:
            try:
                await asyncio.sleep(self.config.health_check_interval.total_seconds())

                for location in self.config.edge_locations:
                    # Simulate health check
                    health_score = await self._check_edge_health(location)

                    # Update location status
                    if health_score < 0.5:
                        location.status = "degraded"
                    else:
                        location.status = "active"

            except Exception as e:
                self.logger.error(f"Health check failed: {e}")

    async def _check_edge_health(self, location: EdgeLocation) -> float:
        """Check edge location health"""

        try:
            # Simulate health check
            edge_cache = self.edge_caches.get(location.location_id)

            if not edge_cache:
                return 0.0

            # Check cache utilization
            utilization = edge_cache.cache_size_bytes / edge_cache.max_size_bytes

            # Check hit rate
            stats = await edge_cache.get_cache_stats()
            hit_rate = stats["hit_rate"]

            # Calculate health score
            health_score = (hit_rate * 0.6) + ((1 - utilization) * 0.4)

            return max(0.0, min(1.0, health_score))

        except Exception as e:
            self.logger.error(f"Edge health check failed: {e}")
            return 0.0

    async def get_analytics(self) -> dict[str, Any]:
        """Get CDN analytics"""

        total_requests = self.analytics["total_requests"]
        cache_hits = self.analytics["cache_hits"]
        cache_misses = self.analytics["cache_misses"]

        hit_rate = (cache_hits / total_requests) if total_requests > 0 else 0.0

        # Edge location stats
        edge_stats = {}
        for edge_id, edge_cache in self.edge_caches.items():
            edge_stats[edge_id] = await edge_cache.get_cache_stats()

        # Calculate bandwidth savings
        bandwidth_saved = 0
        for edge_cache in self.edge_caches.values():
            for entry in edge_cache.cache.values():
                if entry.compressed:
                    bandwidth_saved += entry.size_bytes * 0.3  # Assume 30% savings

        return {
            "total_requests": total_requests,
            "cache_hits": cache_hits,
            "cache_misses": cache_misses,
            "hit_rate": hit_rate,
            "bandwidth_saved_bytes": bandwidth_saved,
            "bandwidth_saved_gb": bandwidth_saved / (1024**3),
            "edge_locations": len(self.edge_caches),
            "active_edges": len([loc for loc in self.config.edge_locations if loc.status == "active"]),
            "edge_stats": edge_stats,
            "global_cache_size": len(self.global_cache),
            "provider": self.config.provider.value,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


class EdgeComputingManager:
    """Edge computing capabilities"""

    def __init__(self, cdn_manager: CDNManager):
        self.cdn_manager = cdn_manager
        self.edge_functions = {}
        self.function_executions = {}
        self.logger = get_logger("edge_computing")

    async def deploy_edge_function(
        self, function_id: str, function_code: str, edge_locations: list[str], config: dict[str, Any]
    ) -> bool:
        """Deploy function to edge locations"""

        try:
            function_config = {
                "function_id": function_id,
                "code": function_code,
                "edge_locations": edge_locations,
                "config": config,
                "deployed_at": datetime.now(timezone.utc),
                "status": "active",
            }

            self.edge_functions[function_id] = function_config

            self.logger.info(f"Edge function deployed: {function_id} to {len(edge_locations)} locations")
            return True

        except Exception as e:
            self.logger.error(f"Edge function deployment failed: {e}")
            return False

    async def execute_edge_function(
        self, function_id: str, user_location: dict[str, float] | None = None, payload: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Execute function at optimal edge location"""

        try:
            function = self.edge_functions.get(function_id)
            if not function:
                return {"error": f"Function not found: {function_id}"}

            # Select edge location
            edge_location = await self.cdn_manager._select_edge_location(user_location)

            if not edge_location:
                return {"error": "No available edge locations"}

            # Simulate function execution
            execution_id = str(uuid4())
            start_time = time.time()

            # Simulate function processing
            await asyncio.sleep(0.1)  # Simulate processing time

            execution_time = (time.time() - start_time) * 1000  # ms

            # Record execution
            execution_record = {
                "execution_id": execution_id,
                "function_id": function_id,
                "edge_location": edge_location.location_id,
                "execution_time_ms": execution_time,
                "timestamp": datetime.now(timezone.utc),
                "success": True,
            }

            if function_id not in self.function_executions:
                self.function_executions[function_id] = []

            self.function_executions[function_id].append(execution_record)

            return {
                "execution_id": execution_id,
                "edge_location": edge_location.location_id,
                "execution_time_ms": execution_time,
                "result": f"Function {function_id} executed successfully",
                "timestamp": execution_record["timestamp"].isoformat(),
            }

        except Exception as e:
            self.logger.error(f"Edge function execution failed: {e}")
            return {"error": str(e)}

    async def get_edge_computing_stats(self) -> dict[str, Any]:
        """Get edge computing statistics"""

        total_functions = len(self.edge_functions)
        total_executions = sum(len(executions) for executions in self.function_executions.values())

        # Calculate average execution time
        all_executions = []
        for executions in self.function_executions.values():
            all_executions.extend(executions)

        avg_execution_time = 0.0
        if all_executions:
            avg_execution_time = sum(exec["execution_time_ms"] for exec in all_executions) / len(all_executions)

        return {
            "total_functions": total_functions,
            "total_executions": total_executions,
            "average_execution_time_ms": avg_execution_time,
            "active_functions": len([f for f in self.edge_functions.values() if f["status"] == "active"]),
            "edge_locations": len(self.cdn_manager.edge_caches),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


class GlobalCDNIntegration:
    """Main global CDN integration service"""

    def __init__(self, config: CDNConfig):
        self.cdn_manager = CDNManager(config)
        self.edge_computing = EdgeComputingManager(self.cdn_manager)
        self.logger = get_logger("global_cdn")

    async def initialize(self) -> bool:
        """Initialize global CDN integration"""

        try:
            # Initialize CDN manager
            if not await self.cdn_manager.initialize():
                return False

            self.logger.info("Global CDN integration initialized")
            return True

        except Exception as e:
            self.logger.error(f"Global CDN integration initialization failed: {e}")
            return False

    async def deliver_content(self, cache_key: str, user_location: dict[str, float] | None = None) -> dict[str, Any]:
        """Deliver content via CDN"""

        return await self.cdn_manager.get_content(cache_key, user_location)

    async def cache_content(self, cache_key: str, content: bytes, content_type: str, ttl: timedelta | None = None) -> bool:
        """Cache content in CDN"""

        return await self.cdn_manager.put_content(cache_key, content, content_type, ttl)

    async def execute_edge_function(
        self, function_id: str, user_location: dict[str, float] | None = None, payload: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Execute edge function"""

        return await self.edge_computing.execute_edge_function(function_id, user_location, payload)

    async def get_performance_metrics(self) -> dict[str, Any]:
        """Get comprehensive performance metrics"""

        try:
            # Get CDN analytics
            cdn_analytics = await self.cdn_manager.get_analytics()

            # Get edge computing stats
            edge_stats = await self.edge_computing.get_edge_computing_stats()

            # Calculate overall performance score
            hit_rate = cdn_analytics["hit_rate"]
            avg_execution_time = edge_stats["average_execution_time_ms"]

            performance_score = (hit_rate * 0.7) + (max(0, 1 - (avg_execution_time / 100)) * 0.3)

            return {
                "performance_score": performance_score,
                "cdn_analytics": cdn_analytics,
                "edge_computing": edge_stats,
                "overall_status": (
                    "excellent" if performance_score >= 0.8 else "good" if performance_score >= 0.6 else "needs_improvement"
                ),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

        except Exception as e:
            self.logger.error(f"Performance metrics retrieval failed: {e}")
            return {"error": str(e)}


# Global CDN integration instance
global_cdn = None


async def get_global_cdn() -> GlobalCDNIntegration:
    """Get or create global CDN integration"""

    global global_cdn
    if global_cdn is None:
        # Create default CDN configuration
        config = CDNConfig(
            provider=CDNProvider.CLOUDFLARE,
            edge_locations=[
                EdgeLocation(
                    location_id="lax",
                    name="Los Angeles",
                    code="LAX",
                    location={"latitude": 34.0522, "longitude": -118.2437},
                    provider=CDNProvider.CLOUDFLARE,
                    endpoints=["https://cdn.aitbc.dev/lax"],
                    capacity={"max_connections": 10000, "bandwidth_mbps": 10000},
                ),
                EdgeLocation(
                    location_id="lhr",
                    name="London",
                    code="LHR",
                    location={"latitude": 51.5074, "longitude": -0.1278},
                    provider=CDNProvider.CLOUDFLARE,
                    endpoints=["https://cdn.aitbc.dev/lhr"],
                    capacity={"max_connections": 10000, "bandwidth_mbps": 10000},
                ),
                EdgeLocation(
                    location_id="sin",
                    name="Singapore",
                    code="SIN",
                    location={"latitude": 1.3521, "longitude": 103.8198},
                    provider=CDNProvider.CLOUDFLARE,
                    endpoints=["https://cdn.aitbc.dev/sin"],
                    capacity={"max_connections": 8000, "bandwidth_mbps": 8000},
                ),
            ],
            cache_strategy=CacheStrategy.ADAPTIVE,
            compression_enabled=True,
        )

        global_cdn = GlobalCDNIntegration(config)
        await global_cdn.initialize()

    return global_cdn
