"""
Multi-Language Translation Engine
Core translation orchestration service for AITBC platform
"""

import asyncio
import hashlib
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum

import deepl
import google.cloud.translate_v2 as translate
import openai

from aitbc import get_logger

logger = get_logger(__name__)


class TranslationProvider(Enum):
    OPENAI = "openai"
    GOOGLE = "google"
    DEEPL = "deepl"
    LOCAL = "local"


@dataclass
class TranslationRequest:
    text: str
    source_language: str
    target_language: str
    context: str | None = None
    domain: str | None = None


@dataclass
class TranslationResponse:
    translated_text: str
    confidence: float
    provider: TranslationProvider
    processing_time_ms: int
    source_language: str
    target_language: str


class BaseTranslator(ABC):
    """Base class for translation providers"""

    @abstractmethod
    async def translate(self, request: TranslationRequest) -> TranslationResponse:
        pass

    @abstractmethod
    def get_supported_languages(self) -> list[str]:
        pass


class OpenAITranslator(BaseTranslator):
    """OpenAI GPT-4 based translation"""

    def __init__(self, api_key: str):
        self.client = openai.AsyncOpenAI(api_key=api_key)

    async def translate(self, request: TranslationRequest) -> TranslationResponse:
        start_time = asyncio.get_event_loop().time()

        prompt = self._build_prompt(request)

        try:
            response = await self.client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {
                        "role": "system",
                        "content": "You are a professional translator. Translate the given text accurately while preserving context and cultural nuances.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                max_tokens=2000,
            )

            translated_text = response.choices[0].message.content.strip()
            processing_time = int((asyncio.get_event_loop().time() - start_time) * 1000)

            return TranslationResponse(
                translated_text=translated_text,
                confidence=0.95,  # GPT-4 typically high confidence
                provider=TranslationProvider.OPENAI,
                processing_time_ms=processing_time,
                source_language=request.source_language,
                target_language=request.target_language,
            )

        except Exception as e:
            logger.error(f"OpenAI translation error: {e}")
            raise

    def _build_prompt(self, request: TranslationRequest) -> str:
        prompt = f"Translate the following text from {request.source_language} to {request.target_language}:\n\n"
        prompt += f"Text: {request.text}\n\n"

        if request.context:
            prompt += f"Context: {request.context}\n"

        if request.domain:
            prompt += f"Domain: {request.domain}\n"

        prompt += "Provide only the translation without additional commentary."
        return prompt

    def get_supported_languages(self) -> list[str]:
        return ["en", "zh", "es", "fr", "de", "ja", "ko", "ru", "ar", "hi", "pt", "it", "nl", "sv", "da", "no", "fi"]


class GoogleTranslator(BaseTranslator):
    """Google Translate API integration"""

    def __init__(self, api_key: str):
        self.client = translate.Client(api_key=api_key)

    async def translate(self, request: TranslationRequest) -> TranslationResponse:
        start_time = asyncio.get_event_loop().time()

        try:
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.client.translate(
                    request.text, source_language=request.source_language, target_language=request.target_language
                ),
            )

            translated_text = result["translatedText"]
            processing_time = int((asyncio.get_event_loop().time() - start_time) * 1000)

            return TranslationResponse(
                translated_text=translated_text,
                confidence=0.85,  # Google Translate moderate confidence
                provider=TranslationProvider.GOOGLE,
                processing_time_ms=processing_time,
                source_language=request.source_language,
                target_language=request.target_language,
            )

        except Exception as e:
            logger.error(f"Google translation error: {e}")
            raise

    def get_supported_languages(self) -> list[str]:
        return [
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
            "th",
            "vi",
        ]


class DeepLTranslator(BaseTranslator):
    """DeepL API integration for European languages"""

    def __init__(self, api_key: str):
        self.translator = deepl.Translator(api_key)

    async def translate(self, request: TranslationRequest) -> TranslationResponse:
        start_time = asyncio.get_event_loop().time()

        try:
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.translator.translate_text(
                    request.text, source_lang=request.source_language.upper(), target_lang=request.target_language.upper()
                ),
            )

            translated_text = result.text
            processing_time = int((asyncio.get_event_loop().time() - start_time) * 1000)

            return TranslationResponse(
                translated_text=translated_text,
                confidence=0.90,  # DeepL high confidence for European languages
                provider=TranslationProvider.DEEPL,
                processing_time_ms=processing_time,
                source_language=request.source_language,
                target_language=request.target_language,
            )

        except Exception as e:
            logger.error(f"DeepL translation error: {e}")
            raise

    def get_supported_languages(self) -> list[str]:
        return ["en", "de", "fr", "es", "pt", "it", "nl", "sv", "da", "fi", "pl", "ru", "ja", "zh"]


class LocalTranslator(BaseTranslator):
    """Local MarianMT models for privacy-preserving translation"""

    def __init__(self):
        # Placeholder for local model initialization
        # In production, this would load MarianMT models
        self.models = {}

    async def translate(self, request: TranslationRequest) -> TranslationResponse:
        start_time = asyncio.get_event_loop().time()

        # Placeholder implementation
        # In production, this would use actual local models
        await asyncio.sleep(0.1)  # Simulate processing time

        translated_text = f"[LOCAL] {request.text}"
        processing_time = int((asyncio.get_event_loop().time() - start_time) * 1000)

        return TranslationResponse(
            translated_text=translated_text,
            confidence=0.75,  # Local models moderate confidence
            provider=TranslationProvider.LOCAL,
            processing_time_ms=processing_time,
            source_language=request.source_language,
            target_language=request.target_language,
        )

    def get_supported_languages(self) -> list[str]:
        return ["en", "de", "fr", "es"]


class TranslationEngine:
    """Main translation orchestration engine"""

    def __init__(self, config: dict):
        self.config = config
        self.translators = self._initialize_translators()
        self.cache = None  # Will be injected
        self.quality_checker = None  # Will be injected

    def _initialize_translators(self) -> dict[TranslationProvider, BaseTranslator]:
        translators = {}

        if self.config.get("openai", {}).get("api_key"):
            translators[TranslationProvider.OPENAI] = OpenAITranslator(self.config["openai"]["api_key"])

        if self.config.get("google", {}).get("api_key"):
            translators[TranslationProvider.GOOGLE] = GoogleTranslator(self.config["google"]["api_key"])

        if self.config.get("deepl", {}).get("api_key"):
            translators[TranslationProvider.DEEPL] = DeepLTranslator(self.config["deepl"]["api_key"])

        # Always include local translator as fallback
        translators[TranslationProvider.LOCAL] = LocalTranslator()

        return translators

    async def translate(self, request: TranslationRequest) -> TranslationResponse:
        """Main translation method with fallback strategy"""

        # Check cache first
        cache_key = self._generate_cache_key(request)
        if self.cache:
            cached_result = await self.cache.get(cache_key)
            if cached_result:
                logger.info(f"Cache hit for translation: {cache_key}")
                return cached_result

        # Determine optimal translator for this request
        preferred_providers = self._get_preferred_providers(request)

        last_error = None
        for provider in preferred_providers:
            if provider not in self.translators:
                continue

            try:
                translator = self.translators[provider]
                result = await translator.translate(request)

                # Quality check
                if self.quality_checker:
                    quality_score = await self.quality_checker.evaluate_translation(
                        request.text, result.translated_text, request.source_language, request.target_language
                    )
                    result.confidence = min(result.confidence, quality_score)

                # Cache the result
                if self.cache and result.confidence > 0.8:
                    await self.cache.set(cache_key, result, ttl=86400)  # 24 hours

                logger.info(f"Translation successful using {provider.value}")
                return result

            except Exception as e:
                last_error = e
                logger.warning(f"Translation failed with {provider.value}: {e}")
                continue

        # All providers failed
        logger.error(f"All translation providers failed. Last error: {last_error}")
        raise Exception("Translation failed with all providers")

    def _get_preferred_providers(self, request: TranslationRequest) -> list[TranslationProvider]:
        """Determine provider preference based on language pair and requirements"""

        # Language-specific preferences
        european_languages = ["de", "fr", "es", "pt", "it", "nl", "sv", "da", "fi", "pl"]
        asian_languages = ["zh", "ja", "ko", "hi", "th", "vi"]

        source_lang = request.source_language
        target_lang = request.target_language

        # DeepL for European languages
        if (
            source_lang in european_languages or target_lang in european_languages
        ) and TranslationProvider.DEEPL in self.translators:
            return [
                TranslationProvider.DEEPL,
                TranslationProvider.OPENAI,
                TranslationProvider.GOOGLE,
                TranslationProvider.LOCAL,
            ]

        # OpenAI for complex translations with context
        if request.context or request.domain:
            return [
                TranslationProvider.OPENAI,
                TranslationProvider.GOOGLE,
                TranslationProvider.DEEPL,
                TranslationProvider.LOCAL,
            ]

        # Google for speed and Asian languages
        if (
            source_lang in asian_languages or target_lang in asian_languages
        ) and TranslationProvider.GOOGLE in self.translators:
            return [
                TranslationProvider.GOOGLE,
                TranslationProvider.OPENAI,
                TranslationProvider.DEEPL,
                TranslationProvider.LOCAL,
            ]

        # Default preference
        return [TranslationProvider.OPENAI, TranslationProvider.GOOGLE, TranslationProvider.DEEPL, TranslationProvider.LOCAL]

    def _generate_cache_key(self, request: TranslationRequest) -> str:
        """Generate cache key for translation request"""
        content = f"{request.text}:{request.source_language}:{request.target_language}"
        if request.context:
            content += f":{request.context}"
        if request.domain:
            content += f":{request.domain}"

        return hashlib.sha256(content.encode()).hexdigest()

    def get_supported_languages(self) -> dict[str, list[str]]:
        """Get all supported languages by provider"""
        supported = {}
        for provider, translator in self.translators.items():
            supported[provider.value] = translator.get_supported_languages()
        return supported

    async def health_check(self) -> dict[str, bool]:
        """Check health of all translation providers"""
        health_status = {}

        for provider, translator in self.translators.items():
            try:
                # Simple test translation
                test_request = TranslationRequest(text="Hello", source_language="en", target_language="es")
                await translator.translate(test_request)
                health_status[provider.value] = True
            except Exception as e:
                logger.error(f"Health check failed for {provider.value}: {e}")
                health_status[provider.value] = False

        return health_status
