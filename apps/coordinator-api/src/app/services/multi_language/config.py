"""
Multi-Language Configuration
Configuration file for multi-language services
"""

import os
from typing import Any


class MultiLanguageConfig:
    """Configuration class for multi-language services"""

    def __init__(self):
        self.translation = self._get_translation_config()
        self.cache = self._get_cache_config()
        self.detection = self._get_detection_config()
        self.quality = self._get_quality_config()
        self.api = self._get_api_config()
        self.localization = self._get_localization_config()

    def _get_translation_config(self) -> dict[str, Any]:
        """Translation service configuration"""
        return {
            "providers": {
                "openai": {
                    "api_key": os.getenv("OPENAI_API_KEY"),
                    "model": "gpt-4",
                    "max_tokens": 2000,
                    "temperature": 0.3,
                    "timeout": 30,
                    "retry_attempts": 3,
                    "rate_limit": {"requests_per_minute": 60, "tokens_per_minute": 40000},
                },
                "google": {
                    "api_key": os.getenv("GOOGLE_TRANSLATE_API_KEY"),
                    "project_id": os.getenv("GOOGLE_PROJECT_ID"),
                    "timeout": 10,
                    "retry_attempts": 3,
                    "rate_limit": {"requests_per_minute": 100, "characters_per_minute": 100000},
                },
                "deepl": {
                    "api_key": os.getenv("DEEPL_API_KEY"),
                    "timeout": 15,
                    "retry_attempts": 3,
                    "rate_limit": {"requests_per_minute": 60, "characters_per_minute": 50000},
                },
                "local": {
                    "model_path": os.getenv("LOCAL_MODEL_PATH", "models/translation"),
                    "timeout": 5,
                    "max_text_length": 5000,
                },
            },
            "fallback_strategy": {"primary": "openai", "secondary": "google", "tertiary": "deepl", "local": "local"},
            "quality_thresholds": {"minimum_confidence": 0.6, "cache_eligibility": 0.8, "auto_retry": 0.4},
        }

    def _get_cache_config(self) -> dict[str, Any]:
        """Cache service configuration"""
        return {
            "redis": {
                "url": os.getenv("REDIS_URL", "redis://localhost:6379"),
                "password": os.getenv("REDIS_PASSWORD"),
                "db": int(os.getenv("REDIS_DB", 0)),
                "max_connections": 20,
                "retry_on_timeout": True,
                "socket_timeout": 5,
                "socket_connect_timeout": 5,
            },
            "cache_settings": {
                "default_ttl": 86400,  # 24 hours
                "max_ttl": 604800,  # 7 days
                "min_ttl": 300,  # 5 minutes
                "max_cache_size": 100000,
                "cleanup_interval": 3600,  # 1 hour
                "compression_threshold": 1000,  # Compress entries larger than 1KB
            },
            "optimization": {
                "enable_auto_optimize": True,
                "optimization_threshold": 0.8,  # Optimize when 80% full
                "eviction_policy": "least_accessed",
                "batch_size": 100,
            },
        }

    def _get_detection_config(self) -> dict[str, Any]:
        """Language detection configuration"""
        return {
            "methods": {
                "langdetect": {"enabled": True, "priority": 1, "min_text_length": 10, "max_text_length": 10000},
                "polyglot": {"enabled": True, "priority": 2, "min_text_length": 5, "max_text_length": 5000},
                "fasttext": {
                    "enabled": True,
                    "priority": 3,
                    "model_path": os.getenv("FASTTEXT_MODEL_PATH", "models/lid.176.bin"),
                    "min_text_length": 1,
                    "max_text_length": 100000,
                },
            },
            "ensemble": {"enabled": True, "voting_method": "weighted", "min_confidence": 0.5, "max_alternatives": 5},
            "fallback": {"default_language": "en", "confidence_threshold": 0.3},
        }

    def _get_quality_config(self) -> dict[str, Any]:
        """Quality assessment configuration"""
        return {
            "thresholds": {
                "overall": 0.7,
                "bleu": 0.3,
                "semantic_similarity": 0.6,
                "length_ratio": 0.5,
                "confidence": 0.6,
                "consistency": 0.4,
            },
            "weights": {"confidence": 0.3, "length_ratio": 0.2, "semantic_similarity": 0.3, "bleu": 0.2, "consistency": 0.1},
            "models": {
                "spacy_models": {
                    "en": "en_core_web_sm",
                    "zh": "zh_core_web_sm",
                    "es": "es_core_news_sm",
                    "fr": "fr_core_news_sm",
                    "de": "de_core_news_sm",
                    "ja": "ja_core_news_sm",
                    "ko": "ko_core_news_sm",
                    "ru": "ru_core_news_sm",
                },
                "download_missing": True,
                "fallback_model": "en_core_web_sm",
            },
            "features": {
                "enable_bleu": True,
                "enable_semantic": True,
                "enable_consistency": True,
                "enable_length_check": True,
            },
        }

    def _get_api_config(self) -> dict[str, Any]:
        """API configuration"""
        return {
            "rate_limiting": {
                "enabled": True,
                "requests_per_minute": {"default": 100, "premium": 1000, "enterprise": 10000},
                "burst_size": 10,
                "strategy": "fixed_window",
            },
            "request_limits": {"max_text_length": 10000, "max_batch_size": 100, "max_concurrent_requests": 50},
            "response_format": {
                "include_confidence": True,
                "include_provider": True,
                "include_processing_time": True,
                "include_cache_info": True,
            },
            "security": {
                "enable_api_key_auth": True,
                "enable_jwt_auth": True,
                "cors_origins": ["*"],
                "max_request_size": "10MB",
            },
        }

    def _get_localization_config(self) -> dict[str, Any]:
        """Localization configuration"""
        return {
            "default_language": "en",
            "supported_languages": [
                "en",
                "zh",
                "zh-cn",
                "zh-tw",
                "es",
                "fr",
                "de",
                "ja",
                "ko",
                "ru",
                "ar",
                "hi",
                "pt",
                "it",
                "nl",
                "sv",
                "da",
                "no",
                "fi",
                "pl",
                "tr",
                "th",
                "vi",
                "id",
                "ms",
                "tl",
                "sw",
                "zu",
                "xh",
            ],
            "auto_detect": True,
            "fallback_language": "en",
            "template_cache": {"enabled": True, "ttl": 3600, "max_size": 10000},  # 1 hour
            "ui_settings": {
                "show_language_selector": True,
                "show_original_text": False,
                "auto_translate": True,
                "quality_indicator": True,
            },
        }

    def get_database_config(self) -> dict[str, Any]:
        """Database configuration"""
        return {
            "connection_string": os.getenv("DATABASE_URL"),
            "pool_size": int(os.getenv("DB_POOL_SIZE", 10)),
            "max_overflow": int(os.getenv("DB_MAX_OVERFLOW", 20)),
            "pool_timeout": int(os.getenv("DB_POOL_TIMEOUT", 30)),
            "pool_recycle": int(os.getenv("DB_POOL_RECYCLE", 3600)),
            "echo": os.getenv("DB_ECHO", "false").lower() == "true",
        }

    def get_monitoring_config(self) -> dict[str, Any]:
        """Monitoring and logging configuration"""
        return {
            "logging": {
                "level": os.getenv("LOG_LEVEL", "INFO"),
                "format": "json",
                "enable_performance_logs": True,
                "enable_error_logs": True,
                "enable_access_logs": True,
            },
            "metrics": {
                "enabled": True,
                "endpoint": "/metrics",
                "include_cache_metrics": True,
                "include_translation_metrics": True,
                "include_quality_metrics": True,
            },
            "health_checks": {"enabled": True, "endpoint": "/health", "interval": 30, "timeout": 10},  # seconds
            "alerts": {
                "enabled": True,
                "thresholds": {
                    "error_rate": 0.05,  # 5%
                    "response_time_p95": 1000,  # 1 second
                    "cache_hit_ratio": 0.7,  # 70%
                    "quality_score_avg": 0.6,  # 60%
                },
            },
        }

    def get_deployment_config(self) -> dict[str, Any]:
        """Deployment configuration"""
        return {
            "environment": os.getenv("ENVIRONMENT", "development"),
            "debug": os.getenv("DEBUG", "false").lower() == "true",
            "workers": int(os.getenv("WORKERS", 4)),
            "host": os.getenv("HOST", "0.0.0.0"),
            "port": int(os.getenv("PORT", 8000)),
            "ssl": {
                "enabled": os.getenv("SSL_ENABLED", "false").lower() == "true",
                "cert_path": os.getenv("SSL_CERT_PATH"),
                "key_path": os.getenv("SSL_KEY_PATH"),
            },
            "scaling": {
                "auto_scaling": os.getenv("AUTO_SCALING", "false").lower() == "true",
                "min_instances": int(os.getenv("MIN_INSTANCES", 1)),
                "max_instances": int(os.getenv("MAX_INSTANCES", 10)),
                "target_cpu": 70,
                "target_memory": 80,
            },
        }

    def validate(self) -> list[str]:
        """Validate configuration and return list of issues"""
        issues = []

        # Check required API keys
        if not self.translation["providers"]["openai"]["api_key"]:
            issues.append("OpenAI API key not configured")

        if not self.translation["providers"]["google"]["api_key"]:
            issues.append("Google Translate API key not configured")

        if not self.translation["providers"]["deepl"]["api_key"]:
            issues.append("DeepL API key not configured")

        # Check Redis configuration
        if not self.cache["redis"]["url"]:
            issues.append("Redis URL not configured")

        # Check database configuration
        if not self.get_database_config()["connection_string"]:
            issues.append("Database connection string not configured")

        # Check FastText model
        if self.detection["methods"]["fasttext"]["enabled"]:
            model_path = self.detection["methods"]["fasttext"]["model_path"]
            if not os.path.exists(model_path):
                issues.append(f"FastText model not found at {model_path}")

        # Validate thresholds
        quality_thresholds = self.quality["thresholds"]
        for metric, threshold in quality_thresholds.items():
            if not 0 <= threshold <= 1:
                issues.append(f"Invalid threshold for {metric}: {threshold}")

        return issues

    def to_dict(self) -> dict[str, Any]:
        """Convert configuration to dictionary"""
        return {
            "translation": self.translation,
            "cache": self.cache,
            "detection": self.detection,
            "quality": self.quality,
            "api": self.api,
            "localization": self.localization,
            "database": self.get_database_config(),
            "monitoring": self.get_monitoring_config(),
            "deployment": self.get_deployment_config(),
        }


# Environment-specific configurations
class DevelopmentConfig(MultiLanguageConfig):
    """Development environment configuration"""

    def __init__(self):
        super().__init__()
        self.cache["redis"]["url"] = "redis://localhost:6379/1"
        self.monitoring["logging"]["level"] = "DEBUG"
        self.deployment["debug"] = True


class ProductionConfig(MultiLanguageConfig):
    """Production environment configuration"""

    def __init__(self):
        super().__init__()
        self.monitoring["logging"]["level"] = "INFO"
        self.deployment["debug"] = False
        self.api["rate_limiting"]["enabled"] = True
        self.cache["cache_settings"]["default_ttl"] = 86400  # 24 hours


class TestingConfig(MultiLanguageConfig):
    """Testing environment configuration"""

    def __init__(self):
        super().__init__()
        self.cache["redis"]["url"] = "redis://localhost:6379/15"
        self.translation["providers"]["local"]["model_path"] = "tests/fixtures/models"
        self.quality["features"]["enable_bleu"] = False  # Disable for faster tests


# Configuration factory
def get_config() -> MultiLanguageConfig:
    """Get configuration based on environment"""
    environment = os.getenv("ENVIRONMENT", "development").lower()

    if environment == "production":
        return ProductionConfig()
    elif environment == "testing":
        return TestingConfig()
    else:
        return DevelopmentConfig()


# Export configuration
config = get_config()
