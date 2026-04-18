"""
Translation Cache Service
Redis-based caching for translation results to improve performance
"""

import hashlib
import json
import logging
import pickle
import time
from dataclasses import asdict, dataclass
from typing import Any

import redis.asyncio as redis
from redis.asyncio import Redis

from ...services.secure_pickle import safe_loads
from .translation_engine import TranslationProvider, TranslationResponse

logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    """Cache entry for translation results"""

    translated_text: str
    confidence: float
    provider: str
    processing_time_ms: int
    source_language: str
    target_language: str
    created_at: float
    access_count: int = 0
    last_accessed: float = 0


class TranslationCache:
    """Redis-based translation cache with intelligent eviction and statistics"""

    def __init__(self, redis_url: str, config: dict | None = None):
        self.redis_url = redis_url
        self.config = config or {}
        self.redis: Redis | None = None
        self.default_ttl = self.config.get("default_ttl", 86400)  # 24 hours
        self.max_cache_size = self.config.get("max_cache_size", 100000)
        self.stats = {"hits": 0, "misses": 0, "sets": 0, "evictions": 0}

    async def initialize(self):
        """Initialize Redis connection"""
        try:
            self.redis = redis.from_url(self.redis_url, decode_responses=False)
            # Test connection
            await self.redis.ping()
            logger.info("Translation cache Redis connection established")
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            raise

    async def close(self):
        """Close Redis connection"""
        if self.redis:
            await self.redis.close()

    def _generate_cache_key(
        self, text: str, source_lang: str, target_lang: str, context: str | None = None, domain: str | None = None
    ) -> str:
        """Generate cache key for translation request"""

        # Create a consistent key format
        key_parts = ["translate", source_lang.lower(), target_lang.lower(), hashlib.sha256(text.encode()).hexdigest()]

        if context:
            key_parts.append(hashlib.sha256(context.encode()).hexdigest())

        if domain:
            key_parts.append(domain.lower())

        return ":".join(key_parts)

    async def get(
        self, text: str, source_lang: str, target_lang: str, context: str | None = None, domain: str | None = None
    ) -> TranslationResponse | None:
        """Get translation from cache"""

        if not self.redis:
            return None

        cache_key = self._generate_cache_key(text, source_lang, target_lang, context, domain)

        try:
            cached_data = await self.redis.get(cache_key)

            if cached_data:
                # Deserialize cache entry
                cache_entry = safe_loads(cached_data)

                # Update access statistics
                cache_entry.access_count += 1
                cache_entry.last_accessed = time.time()

                # Update access count in Redis
                await self.redis.hset(f"{cache_key}:stats", "access_count", cache_entry.access_count)
                await self.redis.hset(f"{cache_key}:stats", "last_accessed", cache_entry.last_accessed)

                self.stats["hits"] += 1

                # Convert back to TranslationResponse
                return TranslationResponse(
                    translated_text=cache_entry.translated_text,
                    confidence=cache_entry.confidence,
                    provider=TranslationProvider(cache_entry.provider),
                    processing_time_ms=cache_entry.processing_time_ms,
                    source_language=cache_entry.source_language,
                    target_language=cache_entry.target_language,
                )

            self.stats["misses"] += 1
            return None

        except Exception as e:
            logger.error(f"Cache get error: {e}")
            self.stats["misses"] += 1
            return None

    async def set(
        self,
        text: str,
        source_lang: str,
        target_lang: str,
        response: TranslationResponse,
        ttl: int | None = None,
        context: str | None = None,
        domain: str | None = None,
    ) -> bool:
        """Set translation in cache"""

        if not self.redis:
            return False

        cache_key = self._generate_cache_key(text, source_lang, target_lang, context, domain)
        ttl = ttl or self.default_ttl

        try:
            # Create cache entry
            cache_entry = CacheEntry(
                translated_text=response.translated_text,
                confidence=response.confidence,
                provider=response.provider.value,
                processing_time_ms=response.processing_time_ms,
                source_language=response.source_language,
                target_language=response.target_language,
                created_at=time.time(),
                access_count=1,
                last_accessed=time.time(),
            )

            # Serialize and store
            serialized_entry = pickle.dumps(cache_entry)

            # Use pipeline for atomic operations
            pipe = self.redis.pipeline()

            # Set main cache entry
            pipe.setex(cache_key, ttl, serialized_entry)

            # Set statistics
            stats_key = f"{cache_key}:stats"
            pipe.hset(
                stats_key,
                {
                    "access_count": 1,
                    "last_accessed": cache_entry.last_accessed,
                    "created_at": cache_entry.created_at,
                    "confidence": response.confidence,
                    "provider": response.provider.value,
                },
            )
            pipe.expire(stats_key, ttl)

            await pipe.execute()

            self.stats["sets"] += 1
            return True

        except Exception as e:
            logger.error(f"Cache set error: {e}")
            return False

    async def delete(
        self, text: str, source_lang: str, target_lang: str, context: str | None = None, domain: str | None = None
    ) -> bool:
        """Delete translation from cache"""

        if not self.redis:
            return False

        cache_key = self._generate_cache_key(text, source_lang, target_lang, context, domain)

        try:
            pipe = self.redis.pipeline()
            pipe.delete(cache_key)
            pipe.delete(f"{cache_key}:stats")
            await pipe.execute()
            return True
        except Exception as e:
            logger.error(f"Cache delete error: {e}")
            return False

    async def clear_by_language_pair(self, source_lang: str, target_lang: str) -> int:
        """Clear all cache entries for a specific language pair"""

        if not self.redis:
            return 0

        pattern = f"translate:{source_lang.lower()}:{target_lang.lower()}:*"

        try:
            keys = await self.redis.keys(pattern)
            if keys:
                # Also delete stats keys
                stats_keys = [f"{key.decode()}:stats" for key in keys]
                all_keys = keys + stats_keys
                await self.redis.delete(*all_keys)
                return len(keys)
            return 0
        except Exception as e:
            logger.error(f"Cache clear by language pair error: {e}")
            return 0

    async def get_cache_stats(self) -> dict[str, Any]:
        """Get comprehensive cache statistics"""

        if not self.redis:
            return {"error": "Redis not connected"}

        try:
            # Get Redis info
            info = await self.redis.info()

            # Calculate hit ratio
            total_requests = self.stats["hits"] + self.stats["misses"]
            hit_ratio = self.stats["hits"] / total_requests if total_requests > 0 else 0

            # Get cache size
            cache_size = await self.redis.dbsize()

            # Get memory usage
            memory_used = info.get("used_memory", 0)
            memory_human = self._format_bytes(memory_used)

            return {
                "hits": self.stats["hits"],
                "misses": self.stats["misses"],
                "sets": self.stats["sets"],
                "evictions": self.stats["evictions"],
                "hit_ratio": hit_ratio,
                "cache_size": cache_size,
                "memory_used": memory_used,
                "memory_human": memory_human,
                "redis_connected": True,
            }

        except Exception as e:
            logger.error(f"Cache stats error: {e}")
            return {"error": str(e), "redis_connected": False}

    async def get_top_translations(self, limit: int = 100) -> list[dict[str, Any]]:
        """Get most accessed translations"""

        if not self.redis:
            return []

        try:
            # Get all stats keys
            stats_keys = await self.redis.keys("translate:*:stats")

            if not stats_keys:
                return []

            # Get access counts for all entries
            pipe = self.redis.pipeline()
            for key in stats_keys:
                pipe.hget(key, "access_count")
                pipe.hget(key, "translated_text")
                pipe.hget(key, "source_language")
                pipe.hget(key, "target_language")
                pipe.hget(key, "confidence")

            results = await pipe.execute()

            # Process results
            translations = []
            for i in range(0, len(results), 5):
                access_count = results[i]
                translated_text = results[i + 1]
                source_lang = results[i + 2]
                target_lang = results[i + 3]
                confidence = results[i + 4]

                if access_count and translated_text:
                    translations.append(
                        {
                            "access_count": int(access_count),
                            "translated_text": (
                                translated_text.decode() if isinstance(translated_text, bytes) else translated_text
                            ),
                            "source_language": source_lang.decode() if isinstance(source_lang, bytes) else source_lang,
                            "target_language": target_lang.decode() if isinstance(target_lang, bytes) else target_lang,
                            "confidence": float(confidence) if confidence else 0.0,
                        }
                    )

            # Sort by access count and limit
            translations.sort(key=lambda x: x["access_count"], reverse=True)
            return translations[:limit]

        except Exception as e:
            logger.error(f"Get top translations error: {e}")
            return []

    async def cleanup_expired(self) -> int:
        """Clean up expired entries"""

        if not self.redis:
            return 0

        try:
            # Redis automatically handles TTL expiration
            # This method can be used for manual cleanup if needed
            # For now, just return cache size
            cache_size = await self.redis.dbsize()
            return cache_size
        except Exception as e:
            logger.error(f"Cleanup error: {e}")
            return 0

    async def optimize_cache(self) -> dict[str, Any]:
        """Optimize cache by removing low-access entries"""

        if not self.redis:
            return {"error": "Redis not connected"}

        try:
            # Get current cache size
            current_size = await self.redis.dbsize()

            if current_size <= self.max_cache_size:
                return {"status": "no_optimization_needed", "current_size": current_size}

            # Get entries with lowest access counts
            stats_keys = await self.redis.keys("translate:*:stats")

            if not stats_keys:
                return {"status": "no_stats_found", "current_size": current_size}

            # Get access counts
            pipe = self.redis.pipeline()
            for key in stats_keys:
                pipe.hget(key, "access_count")

            access_counts = await pipe.execute()

            # Sort by access count
            entries_with_counts = []
            for i, key in enumerate(stats_keys):
                count = access_counts[i]
                if count:
                    entries_with_counts.append((key, int(count)))

            entries_with_counts.sort(key=lambda x: x[1])

            # Remove entries with lowest access counts
            entries_to_remove = entries_with_counts[: len(entries_with_counts) // 4]  # Remove bottom 25%

            if entries_to_remove:
                keys_to_delete = []
                for key, _ in entries_to_remove:
                    key_str = key.decode() if isinstance(key, bytes) else key
                    keys_to_delete.append(key_str)
                    keys_to_delete.append(key_str.replace(":stats", ""))  # Also delete main entry

                await self.redis.delete(*keys_to_delete)
                self.stats["evictions"] += len(entries_to_remove)

            new_size = await self.redis.dbsize()

            return {
                "status": "optimization_completed",
                "entries_removed": len(entries_to_remove),
                "previous_size": current_size,
                "new_size": new_size,
            }

        except Exception as e:
            logger.error(f"Cache optimization error: {e}")
            return {"error": str(e)}

    def _format_bytes(self, bytes_value: int) -> str:
        """Format bytes in human readable format"""
        for unit in ["B", "KB", "MB", "GB"]:
            if bytes_value < 1024.0:
                return f"{bytes_value:.2f} {unit}"
            bytes_value /= 1024.0
        return f"{bytes_value:.2f} TB"

    async def health_check(self) -> dict[str, Any]:
        """Health check for cache service"""

        health_status = {"redis_connected": False, "cache_size": 0, "hit_ratio": 0.0, "memory_usage": 0, "status": "unhealthy"}

        if not self.redis:
            return health_status

        try:
            # Test Redis connection
            await self.redis.ping()
            health_status["redis_connected"] = True

            # Get stats
            stats = await self.get_cache_stats()
            health_status.update(stats)

            # Determine health status
            if stats.get("hit_ratio", 0) > 0.7 and stats.get("redis_connected", False):
                health_status["status"] = "healthy"
            elif stats.get("hit_ratio", 0) > 0.5:
                health_status["status"] = "degraded"

            return health_status

        except Exception as e:
            logger.error(f"Cache health check failed: {e}")
            health_status["error"] = str(e)
            return health_status

    async def export_cache_data(self, output_file: str) -> bool:
        """Export cache data for backup or analysis"""

        if not self.redis:
            return False

        try:
            # Get all cache keys
            keys = await self.redis.keys("translate:*")

            if not keys:
                return True

            # Export data
            export_data = []

            for key in keys:
                if b":stats" in key:
                    continue  # Skip stats keys

                try:
                    cached_data = await self.redis.get(key)
                    if cached_data:
                        cache_entry = safe_loads(cached_data)
                        export_data.append(asdict(cache_entry))
                except Exception as e:
                    logger.warning(f"Failed to export key {key}: {e}")
                    continue

            # Write to file
            with open(output_file, "w") as f:
                json.dump(export_data, f, indent=2)

            logger.info(f"Exported {len(export_data)} cache entries to {output_file}")
            return True

        except Exception as e:
            logger.error(f"Cache export failed: {e}")
            return False
