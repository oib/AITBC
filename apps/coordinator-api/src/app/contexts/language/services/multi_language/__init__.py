"""
Multi-Language Service Initialization
Main entry point for multi-language services
"""

import asyncio
import os
from pathlib import Path
from typing import Any, Optional

from aitbc import get_logger

from .language_detector import LanguageDetector
from .quality_assurance import TranslationQualityChecker
from .translation_cache import TranslationCache
from .translation_engine import TranslationEngine

logger = get_logger(__name__)


class MultiLanguageService:
    """Main service class for multi-language functionality"""

    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or self._load_default_config()
        self.translation_engine: TranslationEngine | None = None
        self.language_detector: LanguageDetector | None = None
        self.translation_cache: TranslationCache | None = None
        self.quality_checker: TranslationQualityChecker | None = None
        self._initialized = False

    def _load_default_config(self) -> dict[str, Any]:
        """Load default configuration"""
        return {
            "translation": {
                "openai": {"api_key": os.getenv("OPENAI_API_KEY"), "model": "gpt-4"},
                "google": {"api_key": os.getenv("GOOGLE_TRANSLATE_API_KEY")},
                "deepl": {"api_key": os.getenv("DEEPL_API_KEY")},
            },
            "cache": {
                "redis_url": os.getenv("REDIS_URL", "redis://localhost:6379"),
                "default_ttl": 86400,
                "max_cache_size": 100000,
            },
            "detection": {"fasttext": {"model_path": os.getenv("FASTTEXT_MODEL_PATH", "lid.176.bin")}},
            "quality": {
                "thresholds": {"overall": 0.7, "bleu": 0.3, "semantic_similarity": 0.6, "length_ratio": 0.5, "confidence": 0.6}
            },
        }

    async def initialize(self) -> None:
        """Initialize all multi-language services"""
        if self._initialized:
            return
        try:
            logger.info("Initializing Multi-Language Service...")
            await self._initialize_cache()
            await self._initialize_translation_engine()
            await self._initialize_language_detector()
            await self._initialize_quality_checker()
            self._initialized = True
            logger.info("Multi-Language Service initialized successfully")
        except Exception as e:
            logger.error("Failed to initialize Multi-Language Service: %s", e)
            raise

    async def _initialize_cache(self) -> None:
        """Initialize translation cache"""
        try:
            self.translation_cache = TranslationCache(redis_url=self.config["cache"]["redis_url"], config=self.config["cache"])
            await self.translation_cache.initialize()
            logger.info("Translation cache initialized")
        except Exception as e:
            logger.warning("Failed to initialize translation cache: %s", e)
            self.translation_cache = None

    async def _initialize_translation_engine(self) -> None:
        """Initialize translation engine"""
        try:
            self.translation_engine = TranslationEngine(self.config["translation"])
            if self.translation_cache and self.translation_engine is not None:
                self.translation_engine.cache = self.translation_cache
            logger.info("Translation engine initialized")
        except Exception as e:
            logger.error("Failed to initialize translation engine: %s", e)
            raise

    async def _initialize_language_detector(self) -> None:
        """Initialize language detector"""
        try:
            self.language_detector = LanguageDetector(self.config["detection"])
            logger.info("Language detector initialized")
        except Exception as e:
            logger.error("Failed to initialize language detector: %s", e)
            raise

    async def _initialize_quality_checker(self) -> None:
        """Initialize quality checker"""
        try:
            self.quality_checker = TranslationQualityChecker(self.config["quality"])
            logger.info("Quality checker initialized")
        except Exception as e:
            logger.warning("Failed to initialize quality checker: %s", e)
            self.quality_checker = None

    async def shutdown(self) -> None:
        """Shutdown all services"""
        logger.info("Shutting down Multi-Language Service...")
        if self.translation_cache:
            await self.translation_cache.close()
        self._initialized = False
        logger.info("Multi-Language Service shutdown complete")

    async def health_check(self) -> dict[str, Any]:
        """Comprehensive health check"""
        if not self._initialized:
            return {"status": "not_initialized"}
        health_status: dict[str, Any] = {"overall": "healthy", "services": {}}
        if self.translation_engine:
            try:
                translation_health = await self.translation_engine.health_check()
                health_status["services"]["translation_engine"] = translation_health
                if not all(translation_health.values()):
                    health_status["overall"] = "degraded"
            except Exception as e:
                health_status["services"]["translation_engine"] = {"error": str(e)}
                health_status["overall"] = "unhealthy"
        if self.language_detector:
            try:
                detection_health = await self.language_detector.health_check()
                health_status["services"]["language_detector"] = detection_health
                if not all(detection_health.values()):
                    health_status["overall"] = "degraded"
            except Exception as e:
                health_status["services"]["language_detector"] = {"error": str(e)}
                health_status["overall"] = "unhealthy"
        if self.translation_cache:
            try:
                cache_health = await self.translation_cache.health_check()
                health_status["services"]["translation_cache"] = cache_health
                if cache_health.get("status") != "healthy":
                    health_status["overall"] = "degraded"
            except Exception as e:
                health_status["services"]["translation_cache"] = {"error": str(e)}
                health_status["overall"] = "degraded"
        if self.quality_checker:
            try:
                quality_health = await self.quality_checker.health_check()
                health_status["services"]["quality_checker"] = quality_health
                if not all(quality_health.values()):
                    health_status["overall"] = "degraded"
            except Exception as e:
                health_status["services"]["quality_checker"] = {"error": str(e)}
        return health_status

    def get_service_status(self) -> dict[str, bool]:
        """Get basic service status"""
        return {
            "initialized": self._initialized,
            "translation_engine": self.translation_engine is not None,
            "language_detector": self.language_detector is not None,
            "translation_cache": self.translation_cache is not None,
            "quality_checker": self.quality_checker is not None,
        }


multi_language_service = MultiLanguageService()


async def initialize_multi_language_service(config: dict[str, Any] | None = None) -> MultiLanguageService:
    """Initialize the multi-language service"""
    global multi_language_service
    if config:
        multi_language_service.config.update(config)
    await multi_language_service.initialize()
    return multi_language_service


async def get_translation_engine() -> TranslationEngine | None:
    """Get translation engine instance"""
    if not multi_language_service.translation_engine:
        await multi_language_service.initialize()
    return multi_language_service.translation_engine


async def get_language_detector() -> LanguageDetector | None:
    """Get language detector instance"""
    if not multi_language_service.language_detector:
        await multi_language_service.initialize()
    return multi_language_service.language_detector


async def get_translation_cache() -> TranslationCache | None:
    """Get translation cache instance"""
    if not multi_language_service.translation_cache:
        await multi_language_service.initialize()
    return multi_language_service.translation_cache


async def get_quality_checker() -> TranslationQualityChecker | None:
    """Get quality checker instance"""
    if not multi_language_service.quality_checker:
        await multi_language_service.initialize()
    return multi_language_service.quality_checker


__all__ = [
    "MultiLanguageService",
    "multi_language_service",
    "initialize_multi_language_service",
    "get_translation_engine",
    "get_language_detector",
    "get_translation_cache",
    "get_quality_checker",
]
