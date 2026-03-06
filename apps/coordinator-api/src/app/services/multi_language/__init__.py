"""
Multi-Language Service Initialization
Main entry point for multi-language services
"""

import asyncio
import logging
from typing import Dict, Any, Optional
import os
from pathlib import Path

from .translation_engine import TranslationEngine
from .language_detector import LanguageDetector
from .translation_cache import TranslationCache
from .quality_assurance import TranslationQualityChecker

logger = logging.getLogger(__name__)

class MultiLanguageService:
    """Main service class for multi-language functionality"""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or self._load_default_config()
        self.translation_engine: Optional[TranslationEngine] = None
        self.language_detector: Optional[LanguageDetector] = None
        self.translation_cache: Optional[TranslationCache] = None
        self.quality_checker: Optional[TranslationQualityChecker] = None
        self._initialized = False
    
    def _load_default_config(self) -> Dict[str, Any]:
        """Load default configuration"""
        return {
            "translation": {
                "openai": {
                    "api_key": os.getenv("OPENAI_API_KEY"),
                    "model": "gpt-4"
                },
                "google": {
                    "api_key": os.getenv("GOOGLE_TRANSLATE_API_KEY")
                },
                "deepl": {
                    "api_key": os.getenv("DEEPL_API_KEY")
                }
            },
            "cache": {
                "redis_url": os.getenv("REDIS_URL", "redis://localhost:6379"),
                "default_ttl": 86400,  # 24 hours
                "max_cache_size": 100000
            },
            "detection": {
                "fasttext": {
                    "model_path": os.getenv("FASTTEXT_MODEL_PATH", "lid.176.bin")
                }
            },
            "quality": {
                "thresholds": {
                    "overall": 0.7,
                    "bleu": 0.3,
                    "semantic_similarity": 0.6,
                    "length_ratio": 0.5,
                    "confidence": 0.6
                }
            }
        }
    
    async def initialize(self):
        """Initialize all multi-language services"""
        if self._initialized:
            return
        
        try:
            logger.info("Initializing Multi-Language Service...")
            
            # Initialize translation cache first
            await self._initialize_cache()
            
            # Initialize translation engine
            await self._initialize_translation_engine()
            
            # Initialize language detector
            await self._initialize_language_detector()
            
            # Initialize quality checker
            await self._initialize_quality_checker()
            
            self._initialized = True
            logger.info("Multi-Language Service initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize Multi-Language Service: {e}")
            raise
    
    async def _initialize_cache(self):
        """Initialize translation cache"""
        try:
            self.translation_cache = TranslationCache(
                redis_url=self.config["cache"]["redis_url"],
                config=self.config["cache"]
            )
            await self.translation_cache.initialize()
            logger.info("Translation cache initialized")
        except Exception as e:
            logger.warning(f"Failed to initialize translation cache: {e}")
            self.translation_cache = None
    
    async def _initialize_translation_engine(self):
        """Initialize translation engine"""
        try:
            self.translation_engine = TranslationEngine(self.config["translation"])
            
            # Inject cache dependency
            if self.translation_cache:
                self.translation_engine.cache = self.translation_cache
            
            logger.info("Translation engine initialized")
        except Exception as e:
            logger.error(f"Failed to initialize translation engine: {e}")
            raise
    
    async def _initialize_language_detector(self):
        """Initialize language detector"""
        try:
            self.language_detector = LanguageDetector(self.config["detection"])
            logger.info("Language detector initialized")
        except Exception as e:
            logger.error(f"Failed to initialize language detector: {e}")
            raise
    
    async def _initialize_quality_checker(self):
        """Initialize quality checker"""
        try:
            self.quality_checker = TranslationQualityChecker(self.config["quality"])
            logger.info("Quality checker initialized")
        except Exception as e:
            logger.warning(f"Failed to initialize quality checker: {e}")
            self.quality_checker = None
    
    async def shutdown(self):
        """Shutdown all services"""
        logger.info("Shutting down Multi-Language Service...")
        
        if self.translation_cache:
            await self.translation_cache.close()
        
        self._initialized = False
        logger.info("Multi-Language Service shutdown complete")
    
    async def health_check(self) -> Dict[str, Any]:
        """Comprehensive health check"""
        if not self._initialized:
            return {"status": "not_initialized"}
        
        health_status = {
            "overall": "healthy",
            "services": {}
        }
        
        # Check translation engine
        if self.translation_engine:
            try:
                translation_health = await self.translation_engine.health_check()
                health_status["services"]["translation_engine"] = translation_health
                if not all(translation_health.values()):
                    health_status["overall"] = "degraded"
            except Exception as e:
                health_status["services"]["translation_engine"] = {"error": str(e)}
                health_status["overall"] = "unhealthy"
        
        # Check language detector
        if self.language_detector:
            try:
                detection_health = await self.language_detector.health_check()
                health_status["services"]["language_detector"] = detection_health
                if not all(detection_health.values()):
                    health_status["overall"] = "degraded"
            except Exception as e:
                health_status["services"]["language_detector"] = {"error": str(e)}
                health_status["overall"] = "unhealthy"
        
        # Check cache
        if self.translation_cache:
            try:
                cache_health = await self.translation_cache.health_check()
                health_status["services"]["translation_cache"] = cache_health
                if cache_health.get("status") != "healthy":
                    health_status["overall"] = "degraded"
            except Exception as e:
                health_status["services"]["translation_cache"] = {"error": str(e)}
                health_status["overall"] = "degraded"
        
        # Check quality checker
        if self.quality_checker:
            try:
                quality_health = await self.quality_checker.health_check()
                health_status["services"]["quality_checker"] = quality_health
                if not all(quality_health.values()):
                    health_status["overall"] = "degraded"
            except Exception as e:
                health_status["services"]["quality_checker"] = {"error": str(e)}
        
        return health_status
    
    def get_service_status(self) -> Dict[str, bool]:
        """Get basic service status"""
        return {
            "initialized": self._initialized,
            "translation_engine": self.translation_engine is not None,
            "language_detector": self.language_detector is not None,
            "translation_cache": self.translation_cache is not None,
            "quality_checker": self.quality_checker is not None
        }

# Global service instance
multi_language_service = MultiLanguageService()

# Initialize function for app startup
async def initialize_multi_language_service(config: Optional[Dict[str, Any]] = None):
    """Initialize the multi-language service"""
    global multi_language_service
    
    if config:
        multi_language_service.config.update(config)
    
    await multi_language_service.initialize()
    return multi_language_service

# Dependency getters for FastAPI
async def get_translation_engine():
    """Get translation engine instance"""
    if not multi_language_service.translation_engine:
        await multi_language_service.initialize()
    return multi_language_service.translation_engine

async def get_language_detector():
    """Get language detector instance"""
    if not multi_language_service.language_detector:
        await multi_language_service.initialize()
    return multi_language_service.language_detector

async def get_translation_cache():
    """Get translation cache instance"""
    if not multi_language_service.translation_cache:
        await multi_language_service.initialize()
    return multi_language_service.translation_cache

async def get_quality_checker():
    """Get quality checker instance"""
    if not multi_language_service.quality_checker:
        await multi_language_service.initialize()
    return multi_language_service.quality_checker

# Export main components
__all__ = [
    "MultiLanguageService",
    "multi_language_service",
    "initialize_multi_language_service",
    "get_translation_engine",
    "get_language_detector",
    "get_translation_cache",
    "get_quality_checker"
]
