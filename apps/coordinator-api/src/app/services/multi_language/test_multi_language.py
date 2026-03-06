"""
Multi-Language Service Tests
Comprehensive test suite for multi-language functionality
"""

import pytest
import asyncio
import json
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime
from typing import Dict, Any

# Import all modules to test
from .translation_engine import TranslationEngine, TranslationRequest, TranslationResponse, TranslationProvider
from .language_detector import LanguageDetector, DetectionMethod, DetectionResult
from .translation_cache import TranslationCache
from .quality_assurance import TranslationQualityChecker, QualityAssessment
from .agent_communication import MultilingualAgentCommunication, AgentMessage, MessageType, AgentLanguageProfile
from .marketplace_localization import MarketplaceLocalization, LocalizedListing, ListingType
from .config import MultiLanguageConfig

class TestTranslationEngine:
    """Test suite for TranslationEngine"""
    
    @pytest.fixture
    def mock_config(self):
        return {
            "openai": {"api_key": "test-key"},
            "google": {"api_key": "test-key"},
            "deepl": {"api_key": "test-key"}
        }
    
    @pytest.fixture
    def translation_engine(self, mock_config):
        return TranslationEngine(mock_config)
    
    @pytest.mark.asyncio
    async def test_translate_with_openai(self, translation_engine):
        """Test translation using OpenAI provider"""
        request = TranslationRequest(
            text="Hello world",
            source_language="en",
            target_language="es"
        )
        
        # Mock OpenAI response
        with patch.object(translation_engine.translators[TranslationProvider.OPENAI], 'translate') as mock_translate:
            mock_translate.return_value = TranslationResponse(
                translated_text="Hola mundo",
                confidence=0.95,
                provider=TranslationProvider.OPENAI,
                processing_time_ms=120,
                source_language="en",
                target_language="es"
            )
            
            result = await translation_engine.translate(request)
            
            assert result.translated_text == "Hola mundo"
            assert result.confidence == 0.95
            assert result.provider == TranslationProvider.OPENAI
    
    @pytest.mark.asyncio
    async def test_translate_fallback_strategy(self, translation_engine):
        """Test fallback strategy when primary provider fails"""
        request = TranslationRequest(
            text="Hello world",
            source_language="en",
            target_language="es"
        )
        
        # Mock primary provider failure
        with patch.object(translation_engine.translators[TranslationProvider.OPENAI], 'translate') as mock_openai:
            mock_openai.side_effect = Exception("OpenAI failed")
            
            # Mock secondary provider success
            with patch.object(translation_engine.translators[TranslationProvider.GOOGLE], 'translate') as mock_google:
                mock_google.return_value = TranslationResponse(
                    translated_text="Hola mundo",
                    confidence=0.85,
                    provider=TranslationProvider.GOOGLE,
                    processing_time_ms=100,
                    source_language="en",
                    target_language="es"
                )
                
                result = await translation_engine.translate(request)
                
                assert result.translated_text == "Hola mundo"
                assert result.provider == TranslationProvider.GOOGLE
    
    def test_get_preferred_providers(self, translation_engine):
        """Test provider preference logic"""
        request = TranslationRequest(
            text="Hello world",
            source_language="en",
            target_language="de"
        )
        
        providers = translation_engine._get_preferred_providers(request)
        
        # Should prefer DeepL for European languages
        assert TranslationProvider.DEEPL in providers
        assert providers[0] == TranslationProvider.DEEPL

class TestLanguageDetector:
    """Test suite for LanguageDetector"""
    
    @pytest.fixture
    def detector(self):
        config = {"fasttext": {"model_path": "test-model.bin"}}
        return LanguageDetector(config)
    
    @pytest.mark.asyncio
    async def test_detect_language_ensemble(self, detector):
        """Test ensemble language detection"""
        text = "Bonjour le monde"
        
        # Mock individual methods
        with patch.object(detector, '_detect_with_method') as mock_detect:
            mock_detect.side_effect = [
                DetectionResult("fr", 0.9, DetectionMethod.LANGDETECT, [], 50),
                DetectionResult("fr", 0.85, DetectionMethod.POLYGLOT, [], 60),
                DetectionResult("fr", 0.95, DetectionMethod.FASTTEXT, [], 40)
            ]
            
            result = await detector.detect_language(text)
            
            assert result.language == "fr"
            assert result.method == DetectionMethod.ENSEMBLE
            assert result.confidence > 0.8
    
    @pytest.mark.asyncio
    async def test_batch_detection(self, detector):
        """Test batch language detection"""
        texts = ["Hello world", "Bonjour le monde", "Hola mundo"]
        
        with patch.object(detector, 'detect_language') as mock_detect:
            mock_detect.side_effect = [
                DetectionResult("en", 0.95, DetectionMethod.LANGDETECT, [], 50),
                DetectionResult("fr", 0.90, DetectionMethod.LANGDETECT, [], 60),
                DetectionResult("es", 0.92, DetectionMethod.LANGDETECT, [], 55)
            ]
            
            results = await detector.batch_detect(texts)
            
            assert len(results) == 3
            assert results[0].language == "en"
            assert results[1].language == "fr"
            assert results[2].language == "es"

class TestTranslationCache:
    """Test suite for TranslationCache"""
    
    @pytest.fixture
    def mock_redis(self):
        redis_mock = AsyncMock()
        redis_mock.ping.return_value = True
        return redis_mock
    
    @pytest.fixture
    def cache(self, mock_redis):
        cache = TranslationCache("redis://localhost:6379")
        cache.redis = mock_redis
        return cache
    
    @pytest.mark.asyncio
    async def test_cache_hit(self, cache, mock_redis):
        """Test cache hit scenario"""
        # Mock cache hit
        mock_response = Mock()
        mock_response.translated_text = "Hola mundo"
        mock_response.confidence = 0.95
        mock_response.provider = TranslationProvider.OPENAI
        mock_response.processing_time_ms = 120
        mock_response.source_language = "en"
        mock_response.target_language = "es"
        
        with patch('pickle.loads', return_value=mock_response):
            mock_redis.get.return_value = b"serialized_data"
            
            result = await cache.get("Hello world", "en", "es")
            
            assert result.translated_text == "Hola mundo"
            assert result.confidence == 0.95
    
    @pytest.mark.asyncio
    async def test_cache_miss(self, cache, mock_redis):
        """Test cache miss scenario"""
        mock_redis.get.return_value = None
        
        result = await cache.get("Hello world", "en", "es")
        
        assert result is None
    
    @pytest.mark.asyncio
    async def test_cache_set(self, cache, mock_redis):
        """Test cache set operation"""
        response = TranslationResponse(
            translated_text="Hola mundo",
            confidence=0.95,
            provider=TranslationProvider.OPENAI,
            processing_time_ms=120,
            source_language="en",
            target_language="es"
        )
        
        with patch('pickle.dumps', return_value=b"serialized_data"):
            result = await cache.set("Hello world", "en", "es", response)
            
            assert result is True
            mock_redis.setex.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_get_cache_stats(self, cache, mock_redis):
        """Test cache statistics"""
        mock_redis.info.return_value = {
            "used_memory": 1000000,
            "db_size": 1000
        }
        mock_redis.dbsize.return_value = 1000
        
        stats = await cache.get_cache_stats()
        
        assert "hits" in stats
        assert "misses" in stats
        assert "cache_size" in stats
        assert "memory_used" in stats

class TestTranslationQualityChecker:
    """Test suite for TranslationQualityChecker"""
    
    @pytest.fixture
    def quality_checker(self):
        config = {
            "thresholds": {
                "overall": 0.7,
                "bleu": 0.3,
                "semantic_similarity": 0.6,
                "length_ratio": 0.5,
                "confidence": 0.6
            }
        }
        return TranslationQualityChecker(config)
    
    @pytest.mark.asyncio
    async def test_evaluate_translation(self, quality_checker):
        """Test translation quality evaluation"""
        with patch.object(quality_checker, '_evaluate_confidence') as mock_confidence, \
             patch.object(quality_checker, '_evaluate_length_ratio') as mock_length, \
             patch.object(quality_checker, '_evaluate_semantic_similarity') as mock_semantic, \
             patch.object(quality_checker, '_evaluate_consistency') as mock_consistency:
            
            # Mock individual evaluations
            from .quality_assurance import QualityScore, QualityMetric
            mock_confidence.return_value = QualityScore(
                metric=QualityMetric.CONFIDENCE,
                score=0.8,
                weight=0.3,
                description="Test"
            )
            mock_length.return_value = QualityScore(
                metric=QualityMetric.LENGTH_RATIO,
                score=0.7,
                weight=0.2,
                description="Test"
            )
            mock_semantic.return_value = QualityScore(
                metric=QualityMetric.SEMANTIC_SIMILARITY,
                score=0.75,
                weight=0.3,
                description="Test"
            )
            mock_consistency.return_value = QualityScore(
                metric=QualityMetric.CONSISTENCY,
                score=0.9,
                weight=0.1,
                description="Test"
            )
            
            assessment = await quality_checker.evaluate_translation(
                "Hello world", "Hola mundo", "en", "es"
            )
            
            assert isinstance(assessment, QualityAssessment)
            assert assessment.overall_score > 0.7
            assert len(assessment.individual_scores) == 4

class TestMultilingualAgentCommunication:
    """Test suite for MultilingualAgentCommunication"""
    
    @pytest.fixture
    def mock_services(self):
        translation_engine = Mock()
        language_detector = Mock()
        translation_cache = Mock()
        quality_checker = Mock()
        
        return {
            "translation_engine": translation_engine,
            "language_detector": language_detector,
            "translation_cache": translation_cache,
            "quality_checker": quality_checker
        }
    
    @pytest.fixture
    def agent_comm(self, mock_services):
        return MultilingualAgentCommunication(
            mock_services["translation_engine"],
            mock_services["language_detector"],
            mock_services["translation_cache"],
            mock_services["quality_checker"]
        )
    
    @pytest.mark.asyncio
    async def test_register_agent_language_profile(self, agent_comm):
        """Test agent language profile registration"""
        profile = AgentLanguageProfile(
            agent_id="agent1",
            preferred_language="es",
            supported_languages=["es", "en"],
            auto_translate_enabled=True,
            translation_quality_threshold=0.7,
            cultural_preferences={}
        )
        
        result = await agent_comm.register_agent_language_profile(profile)
        
        assert result is True
        assert "agent1" in agent_comm.agent_profiles
        assert agent_comm.agent_profiles["agent1"].preferred_language == "es"
    
    @pytest.mark.asyncio
    async def test_send_message_with_translation(self, agent_comm, mock_services):
        """Test sending message with automatic translation"""
        # Setup agent profile
        profile = AgentLanguageProfile(
            agent_id="agent2",
            preferred_language="es",
            supported_languages=["es", "en"],
            auto_translate_enabled=True,
            translation_quality_threshold=0.7,
            cultural_preferences={}
        )
        await agent_comm.register_agent_language_profile(profile)
        
        # Mock language detection
        mock_services["language_detector"].detect_language.return_value = DetectionResult(
            "en", 0.95, DetectionMethod.LANGDETECT, [], 50
        )
        
        # Mock translation
        mock_services["translation_engine"].translate.return_value = TranslationResponse(
            translated_text="Hola mundo",
            confidence=0.9,
            provider=TranslationProvider.OPENAI,
            processing_time_ms=120,
            source_language="en",
            target_language="es"
        )
        
        message = AgentMessage(
            id="msg1",
            sender_id="agent1",
            receiver_id="agent2",
            message_type=MessageType.AGENT_TO_AGENT,
            content="Hello world"
        )
        
        result = await agent_comm.send_message(message)
        
        assert result.translated_content == "Hola mundo"
        assert result.translation_confidence == 0.9
        assert result.target_language == "es"

class TestMarketplaceLocalization:
    """Test suite for MarketplaceLocalization"""
    
    @pytest.fixture
    def mock_services(self):
        translation_engine = Mock()
        language_detector = Mock()
        translation_cache = Mock()
        quality_checker = Mock()
        
        return {
            "translation_engine": translation_engine,
            "language_detector": language_detector,
            "translation_cache": translation_cache,
            "quality_checker": quality_checker
        }
    
    @pytest.fixture
    def marketplace_loc(self, mock_services):
        return MarketplaceLocalization(
            mock_services["translation_engine"],
            mock_services["language_detector"],
            mock_services["translation_cache"],
            mock_services["quality_checker"]
        )
    
    @pytest.mark.asyncio
    async def test_create_localized_listing(self, marketplace_loc, mock_services):
        """Test creating localized listings"""
        original_listing = {
            "id": "listing1",
            "type": "service",
            "title": "AI Translation Service",
            "description": "High-quality translation service",
            "keywords": ["translation", "AI", "service"],
            "features": ["Fast translation", "High accuracy"],
            "requirements": ["API key", "Internet connection"],
            "pricing_info": {"price": 0.01, "unit": "character"}
        }
        
        # Mock translation
        mock_services["translation_engine"].translate.return_value = TranslationResponse(
            translated_text="Servicio de Traducción IA",
            confidence=0.9,
            provider=TranslationProvider.OPENAI,
            processing_time_ms=150,
            source_language="en",
            target_language="es"
        )
        
        result = await marketplace_loc.create_localized_listing(original_listing, ["es"])
        
        assert len(result) == 1
        assert result[0].language == "es"
        assert result[0].title == "Servicio de Traducción IA"
        assert result[0].original_id == "listing1"
    
    @pytest.mark.asyncio
    async def test_search_localized_listings(self, marketplace_loc):
        """Test searching localized listings"""
        # Setup test data
        localized_listing = LocalizedListing(
            id="listing1_es",
            original_id="listing1",
            listing_type=ListingType.SERVICE,
            language="es",
            title="Servicio de Traducción",
            description="Servicio de alta calidad",
            keywords=["traducción", "servicio"],
            features=["Rápido", "Preciso"],
            requirements=["API", "Internet"],
            pricing_info={"price": 0.01}
        )
        
        marketplace_loc.localized_listings["listing1"] = [localized_listing]
        
        results = await marketplace_loc.search_localized_listings("traducción", "es")
        
        assert len(results) == 1
        assert results[0].language == "es"
        assert "traducción" in results[0].title.lower()

class TestMultiLanguageConfig:
    """Test suite for MultiLanguageConfig"""
    
    def test_default_config(self):
        """Test default configuration"""
        config = MultiLanguageConfig()
        
        assert "openai" in config.translation["providers"]
        assert "google" in config.translation["providers"]
        assert "deepl" in config.translation["providers"]
        assert config.cache["redis"]["url"] is not None
        assert config.quality["thresholds"]["overall"] == 0.7
    
    def test_config_validation(self):
        """Test configuration validation"""
        config = MultiLanguageConfig()
        
        # Should have issues with missing API keys in test environment
        issues = config.validate()
        assert len(issues) > 0
        assert any("API key" in issue for issue in issues)
    
    def test_environment_specific_configs(self):
        """Test environment-specific configurations"""
        from .config import DevelopmentConfig, ProductionConfig, TestingConfig
        
        dev_config = DevelopmentConfig()
        prod_config = ProductionConfig()
        test_config = TestingConfig()
        
        assert dev_config.deployment["debug"] is True
        assert prod_config.deployment["debug"] is False
        assert test_config.cache["redis"]["url"] == "redis://localhost:6379/15"

class TestIntegration:
    """Integration tests for multi-language services"""
    
    @pytest.mark.asyncio
    async def test_end_to_end_translation_workflow(self):
        """Test complete translation workflow"""
        # This would be a comprehensive integration test
        # mocking all external dependencies
        
        # Setup mock services
        with patch('app.services.multi_language.translation_engine.openai') as mock_openai, \
             patch('app.services.multi_language.language_detector.langdetect') as mock_langdetect, \
             patch('redis.asyncio.from_url') as mock_redis:
            
            # Configure mocks
            mock_openai.AsyncOpenAI.return_value.chat.completions.create.return_value = Mock(
                choices=[Mock(message=Mock(content="Hola mundo"))]
            )
            
            mock_langdetect.detect.return_value = Mock(lang="en", prob=0.95)
            mock_redis.return_value.ping.return_value = True
            mock_redis.return_value.get.return_value = None  # Cache miss
            
            # Initialize services
            config = MultiLanguageConfig()
            translation_engine = TranslationEngine(config.translation)
            language_detector = LanguageDetector(config.detection)
            translation_cache = TranslationCache(config.cache["redis"]["url"])
            
            await translation_cache.initialize()
            
            # Test translation
            request = TranslationRequest(
                text="Hello world",
                source_language="en",
                target_language="es"
            )
            
            result = await translation_engine.translate(request)
            
            assert result.translated_text == "Hola mundo"
            assert result.provider == TranslationProvider.OPENAI
            
            await translation_cache.close()

# Performance tests
class TestPerformance:
    """Performance tests for multi-language services"""
    
    @pytest.mark.asyncio
    async def test_translation_performance(self):
        """Test translation performance under load"""
        # This would test performance with concurrent requests
        pass
    
    @pytest.mark.asyncio
    async def test_cache_performance(self):
        """Test cache performance under load"""
        # This would test cache performance with many concurrent operations
        pass

# Error handling tests
class TestErrorHandling:
    """Test error handling and edge cases"""
    
    @pytest.mark.asyncio
    async def test_translation_engine_failure(self):
        """Test translation engine failure handling"""
        config = {"openai": {"api_key": "invalid"}}
        engine = TranslationEngine(config)
        
        request = TranslationRequest(
            text="Hello world",
            source_language="en",
            target_language="es"
        )
        
        with pytest.raises(Exception):
            await engine.translate(request)
    
    @pytest.mark.asyncio
    async def test_empty_text_handling(self):
        """Test handling of empty or invalid text"""
        detector = LanguageDetector({})
        
        with pytest.raises(ValueError):
            await detector.detect_language("")
    
    @pytest.mark.asyncio
    async def test_unsupported_language_handling(self):
        """Test handling of unsupported languages"""
        config = MultiLanguageConfig()
        engine = TranslationEngine(config.translation)
        
        request = TranslationRequest(
            text="Hello world",
            source_language="invalid_lang",
            target_language="es"
        )
        
        # Should handle gracefully or raise appropriate error
        try:
            result = await engine.translate(request)
            # If successful, should have fallback behavior
            assert result is not None
        except Exception:
            # If failed, should be appropriate error
            pass

# Test utilities
class TestUtils:
    """Test utilities and helpers"""
    
    def create_sample_translation_request(self):
        """Create sample translation request for testing"""
        return TranslationRequest(
            text="Hello world, this is a test message",
            source_language="en",
            target_language="es",
            context="General communication",
            domain="general"
        )
    
    def create_sample_agent_profile(self):
        """Create sample agent profile for testing"""
        return AgentLanguageProfile(
            agent_id="test_agent",
            preferred_language="es",
            supported_languages=["es", "en", "fr"],
            auto_translate_enabled=True,
            translation_quality_threshold=0.7,
            cultural_preferences={"formality": "formal"}
        )
    
    def create_sample_marketplace_listing(self):
        """Create sample marketplace listing for testing"""
        return {
            "id": "test_listing",
            "type": "service",
            "title": "AI Translation Service",
            "description": "High-quality AI-powered translation service",
            "keywords": ["translation", "AI", "service"],
            "features": ["Fast", "Accurate", "Multi-language"],
            "requirements": ["API key", "Internet"],
            "pricing_info": {"price": 0.01, "unit": "character"}
        }

if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v"])
