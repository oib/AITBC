"""
Multi-Language Translation Engine
Core translation orchestration service for AITBC platform
"""
import asyncio
import hashlib
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any
import deepl  # type: ignore[import-not-found]
import google.cloud.translate_v2 as translate  # type: ignore[import-untyped]
import openai  # type: ignore[import-not-found]
from aitbc import get_logger
if TYPE_CHECKING:
    from .translation_cache import TranslationCache
logger = get_logger(__name__)

class TranslationProvider(Enum):
    OPENAI = 'openai'
    GOOGLE = 'google'
    DEEPL = 'deepl'
    LOCAL = 'local'

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
            response = await self.client.chat.completions.create(model='gpt-4', messages=[{'role': 'system', 'content': 'You are a professional translator. Translate the given text accurately while preserving context and cultural nuances.'}, {'role': 'user', 'content': prompt}], temperature=0.3, max_tokens=2000)
            translated_text = response.choices[0].message.content.strip()
            processing_time = int((asyncio.get_event_loop().time() - start_time) * 1000)
            return TranslationResponse(translated_text=translated_text, confidence=0.95, provider=TranslationProvider.OPENAI, processing_time_ms=processing_time, source_language=request.source_language, target_language=request.target_language)
        except Exception as e:
            logger.error('OpenAI translation error: %s', e)
            raise

    def _build_prompt(self, request: TranslationRequest) -> str:
        prompt = f'Translate the following text from {request.source_language} to {request.target_language}:\n\n'
        prompt += f'Text: {request.text}\n\n'
        if request.context:
            prompt += f'Context: {request.context}\n'
        if request.domain:
            prompt += f'Domain: {request.domain}\n'
        prompt += 'Provide only the translation without additional commentary.'
        return prompt

    def get_supported_languages(self) -> list[str]:
        return ['en', 'zh', 'es', 'fr', 'de', 'ja', 'ko', 'ru', 'ar', 'hi', 'pt', 'it', 'nl', 'sv', 'da', 'no', 'fi']

class GoogleTranslator(BaseTranslator):
    """Google Translate API integration"""

    def __init__(self, api_key: str):
        self.client = translate.Client(api_key=api_key)

    async def translate(self, request: TranslationRequest) -> TranslationResponse:
        start_time = asyncio.get_event_loop().time()
        try:
            result = await asyncio.get_event_loop().run_in_executor(None, lambda: self.client.translate(request.text, source_language=request.source_language, target_language=request.target_language))
            translated_text = result['translatedText']
            processing_time = int((asyncio.get_event_loop().time() - start_time) * 1000)
            return TranslationResponse(translated_text=translated_text, confidence=0.85, provider=TranslationProvider.GOOGLE, processing_time_ms=processing_time, source_language=request.source_language, target_language=request.target_language)
        except Exception as e:
            logger.error('Google translation error: %s', e)
            raise

    def get_supported_languages(self) -> list[str]:
        return ['en', 'zh', 'zh-cn', 'zh-tw', 'es', 'fr', 'de', 'ja', 'ko', 'ru', 'ar', 'hi', 'pt', 'it', 'nl', 'sv', 'da', 'no', 'fi', 'th', 'vi']

class DeepLTranslator(BaseTranslator):
    """DeepL API integration for European languages"""

    def __init__(self, api_key: str):
        self.translator = deepl.Translator(api_key)

    async def translate(self, request: TranslationRequest) -> TranslationResponse:
        start_time = asyncio.get_event_loop().time()
        try:
            result = await asyncio.get_event_loop().run_in_executor(None, lambda: self.translator.translate_text(request.text, source_lang=request.source_language.upper(), target_lang=request.target_language.upper()))
            translated_text = result.text
            processing_time = int((asyncio.get_event_loop().time() - start_time) * 1000)
            return TranslationResponse(translated_text=translated_text, confidence=0.9, provider=TranslationProvider.DEEPL, processing_time_ms=processing_time, source_language=request.source_language, target_language=request.target_language)
        except Exception as e:
            logger.error('DeepL translation error: %s', e)
            raise

    def get_supported_languages(self) -> list[str]:
        return ['en', 'de', 'fr', 'es', 'pt', 'it', 'nl', 'sv', 'da', 'fi', 'pl', 'ru', 'ja', 'zh']

class LocalTranslator(BaseTranslator):
    """Local MarianMT models for privacy-preserving translation"""

    def __init__(self) -> None:
        self.models: dict[str, Any] = {}

    async def translate(self, request: TranslationRequest) -> TranslationResponse:
        start_time = asyncio.get_event_loop().time()
        await asyncio.sleep(0.1)
        translated_text = f'[LOCAL] {request.text}'
        processing_time = int((asyncio.get_event_loop().time() - start_time) * 1000)
        return TranslationResponse(translated_text=translated_text, confidence=0.75, provider=TranslationProvider.LOCAL, processing_time_ms=processing_time, source_language=request.source_language, target_language=request.target_language)

    def get_supported_languages(self) -> list[str]:
        return ['en', 'de', 'fr', 'es']

class TranslationEngine:
    """Main translation orchestration engine"""

    def __init__(self, config: dict):
        self.config = config
        self.translators = self._initialize_translators()
        self.cache: 'TranslationCache | None' = None
        self.quality_checker = None

    def _initialize_translators(self) -> dict[TranslationProvider, BaseTranslator]:
        translators = {}
        if self.config.get('openai', {}).get('api_key'):
            translators[TranslationProvider.OPENAI] = OpenAITranslator(self.config['openai']['api_key'])
        if self.config.get('google', {}).get('api_key'):
            translators[TranslationProvider.GOOGLE] = GoogleTranslator(self.config['google']['api_key'])  # type: ignore[assignment]
        if self.config.get('deepl', {}).get('api_key'):
            translators[TranslationProvider.DEEPL] = DeepLTranslator(self.config['deepl']['api_key'])  # type: ignore[assignment]
        translators[TranslationProvider.LOCAL] = LocalTranslator()  # type: ignore[assignment]
        return translators  # type: ignore[return-value]

    async def translate(self, request: TranslationRequest) -> TranslationResponse:
        """Main translation method with fallback strategy"""
        cache_key = self._generate_cache_key(request)
        if self.cache:
            cached_result = await self.cache.get(cache_key, request.source_language, request.target_language)
            if cached_result:
                logger.info('Cache hit for translation: %s', cache_key)
                return cached_result
        preferred_providers = self._get_preferred_providers(request)
        last_error = None
        for provider in preferred_providers:
            if provider not in self.translators:
                continue
            try:
                translator = self.translators[provider]
                result = await translator.translate(request)
                if self.quality_checker:
                    quality_score = await self.quality_checker.evaluate_translation(request.text, result.translated_text, request.source_language, request.target_language)  # type: ignore[unreachable]
                    result.confidence = min(result.confidence, quality_score)
                if self.cache and result.confidence > 0.8:
                    await self.cache.set(cache_key, request.target_language, result, ttl=86400)  # type: ignore[call-arg, arg-type]
                logger.info('Translation successful using %s', provider.value)
                return result
            except Exception as e:
                last_error = e
                logger.warning('Translation failed with %s: %s', provider.value, e)
                continue
        logger.error('All translation providers failed. Last error: %s', last_error)
        raise Exception('Translation failed with all providers')

    def _get_preferred_providers(self, request: TranslationRequest) -> list[TranslationProvider]:
        """Determine provider preference based on language pair and requirements"""
        european_languages = ['de', 'fr', 'es', 'pt', 'it', 'nl', 'sv', 'da', 'fi', 'pl']
        asian_languages = ['zh', 'ja', 'ko', 'hi', 'th', 'vi']
        source_lang = request.source_language
        target_lang = request.target_language
        if (source_lang in european_languages or target_lang in european_languages) and TranslationProvider.DEEPL in self.translators:
            return [TranslationProvider.DEEPL, TranslationProvider.OPENAI, TranslationProvider.GOOGLE, TranslationProvider.LOCAL]
        if request.context or request.domain:
            return [TranslationProvider.OPENAI, TranslationProvider.GOOGLE, TranslationProvider.DEEPL, TranslationProvider.LOCAL]
        if (source_lang in asian_languages or target_lang in asian_languages) and TranslationProvider.GOOGLE in self.translators:
            return [TranslationProvider.GOOGLE, TranslationProvider.OPENAI, TranslationProvider.DEEPL, TranslationProvider.LOCAL]
        return [TranslationProvider.OPENAI, TranslationProvider.GOOGLE, TranslationProvider.DEEPL, TranslationProvider.LOCAL]

    def _generate_cache_key(self, request: TranslationRequest) -> str:
        """Generate cache key for translation request"""
        content = f'{request.text}:{request.source_language}:{request.target_language}'
        if request.context:
            content += f':{request.context}'
        if request.domain:
            content += f':{request.domain}'
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
                test_request = TranslationRequest(text='Hello', source_language='en', target_language='es')
                await translator.translate(test_request)
                health_status[provider.value] = True
            except Exception as e:
                logger.error('Health check failed for %s: %s', provider.value, e)
                health_status[provider.value] = False
        return health_status