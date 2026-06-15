"""
Multi-Language API Endpoints
REST API endpoints for translation and language detection services
"""
import asyncio
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

from aitbc import get_logger

from .language_detector import DetectionMethod, LanguageDetector
from .quality_assurance import TranslationQualityChecker
from .translation_cache import TranslationCache
from .translation_engine import TranslationEngine, TranslationRequest

logger = get_logger(__name__)

class TranslationAPIRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=10000, description='Text to translate')
    source_language: str = Field(..., description="Source language code (e.g., 'en', 'zh')")
    target_language: str = Field(..., description="Target language code (e.g., 'es', 'fr')")
    context: str | None = Field(None, description='Additional context for translation')
    domain: str | None = Field(None, description="Domain-specific context (e.g., 'medical', 'legal')")
    use_cache: bool = Field(True, description='Whether to use cached translations')
    quality_check: bool = Field(False, description='Whether to perform quality assessment')

    @field_validator('text')
    @classmethod
    def validate_text(cls, v: str) -> str:
        if not v.strip():
            raise ValueError('Text cannot be empty')
        return v.strip()

class BatchTranslationRequest(BaseModel):
    translations: list[TranslationAPIRequest] = Field(..., max_items=100, description='List of translation requests')  # type: ignore[call-overload]

    @field_validator('translations')
    @classmethod
    def validate_translations(cls, v: list[TranslationAPIRequest]) -> list[TranslationAPIRequest]:
        if len(v) == 0:
            raise ValueError('At least one translation request is required')
        return v

class LanguageDetectionRequest(BaseModel):
    text: str = Field(..., min_length=10, max_length=10000, description='Text for language detection')
    methods: list[str] | None = Field(None, description='Detection methods to use')

    @field_validator('methods')
    @classmethod
    def validate_methods(cls, v: list[str] | None) -> list[str] | None:
        if v:
            valid_methods = [method.value for method in DetectionMethod]
            for method in v:
                if method not in valid_methods:
                    raise ValueError(f'Invalid detection method: {method}')
        return v

class BatchDetectionRequest(BaseModel):
    texts: list[str] = Field(..., max_items=100, description='List of texts for language detection')  # type: ignore[call-overload]
    methods: list[str] | None = Field(None, description='Detection methods to use')

class TranslationAPIResponse(BaseModel):
    translated_text: str
    confidence: float
    provider: str
    processing_time_ms: int
    source_language: str
    target_language: str
    cached: bool = False
    quality_assessment: dict[str, Any] | None = None

class BatchTranslationResponse(BaseModel):
    translations: list[TranslationAPIResponse]
    total_processed: int
    failed_count: int
    processing_time_ms: int
    errors: list[str] = []

class LanguageDetectionResponse(BaseModel):
    language: str
    confidence: float
    method: str
    alternatives: list[dict[str, float]]
    processing_time_ms: int

class BatchDetectionResponse(BaseModel):
    detections: list[LanguageDetectionResponse]
    total_processed: int
    processing_time_ms: int

class SupportedLanguagesResponse(BaseModel):
    languages: dict[str, list[str]]
    total_languages: int

class HealthResponse(BaseModel):
    status: str
    services: dict[str, bool]
    timestamp: datetime

async def get_translation_engine() -> TranslationEngine:
    """Dependency injection for translation engine"""
    from ..main import translation_engine  # type: ignore[import-not-found]
    return translation_engine  # type: ignore[no-any-return]

async def get_language_detector() -> LanguageDetector:
    """Dependency injection for language detector"""
    from ..main import language_detector
    return language_detector  # type: ignore[no-any-return]

async def get_translation_cache() -> TranslationCache | None:
    """Dependency injection for translation cache"""
    from ..main import translation_cache
    return translation_cache  # type: ignore[no-any-return]

async def get_quality_checker() -> TranslationQualityChecker | None:
    """Dependency injection for quality checker"""
    from ..main import quality_checker
    return quality_checker  # type: ignore[no-any-return]
router = APIRouter(prefix='/api/v1/multi-language', tags=['multi-language'])

@router.post('/translate', response_model=TranslationAPIResponse)
async def translate_text(request: TranslationAPIRequest, background_tasks: BackgroundTasks, engine: TranslationEngine=Depends(get_translation_engine), cache: TranslationCache | None=Depends(get_translation_cache), quality_checker: TranslationQualityChecker | None=Depends(get_quality_checker)) -> TranslationAPIResponse:
    """
    Translate text between supported languages with caching and quality assessment
    """
    asyncio.get_event_loop().time()
    try:
        cached_result = None
        if request.use_cache and cache:
            cached_result = await cache.get(request.text, request.source_language, request.target_language, request.context, request.domain)
        if cached_result:
            background_tasks.add_task(cache.get if cache else lambda *args: None, request.text, request.source_language, request.target_language, request.context, request.domain)
            return TranslationAPIResponse(translated_text=cached_result.translated_text, confidence=cached_result.confidence, provider=cached_result.provider.value, processing_time_ms=cached_result.processing_time_ms, source_language=cached_result.source_language, target_language=cached_result.target_language, cached=True)
        translation_request = TranslationRequest(text=request.text, source_language=request.source_language, target_language=request.target_language, context=request.context, domain=request.domain)
        translation_result = await engine.translate(translation_request)
        if cache and translation_result.confidence > 0.8:
            background_tasks.add_task(cache.set, request.text, request.source_language, request.target_language, translation_result, context=request.context, domain=request.domain)
        quality_assessment = None
        if request.quality_check and quality_checker:
            assessment = await quality_checker.evaluate_translation(request.text, translation_result.translated_text, request.source_language, request.target_language)
            quality_assessment = {'overall_score': assessment.overall_score, 'passed_threshold': assessment.passed_threshold, 'recommendations': assessment.recommendations}
        return TranslationAPIResponse(translated_text=translation_result.translated_text, confidence=translation_result.confidence, provider=translation_result.provider.value, processing_time_ms=translation_result.processing_time_ms, source_language=translation_result.source_language, target_language=translation_result.target_language, cached=False, quality_assessment=quality_assessment)
    except Exception as e:
        logger.error('Translation error: %s', e)
        raise HTTPException(status_code=500, detail=str(e))

@router.post('/translate/batch', response_model=BatchTranslationResponse)
async def translate_batch(request: BatchTranslationRequest, background_tasks: BackgroundTasks, engine: TranslationEngine=Depends(get_translation_engine), cache: TranslationCache | None=Depends(get_translation_cache)) -> BatchTranslationResponse:
    """
    Translate multiple texts in a single request
    """
    start_time = asyncio.get_event_loop().time()
    try:
        tasks = []
        for translation_req in request.translations:
            task = translate_text(translation_req, background_tasks, engine, cache, None)
            tasks.append(task)
        results = await asyncio.gather(*tasks, return_exceptions=True)
        translations = []
        errors = []
        failed_count = 0
        for i, result in enumerate(results):
            if isinstance(result, TranslationAPIResponse):
                translations.append(result)
            else:
                errors.append(f'Translation {i + 1} failed: {str(result)}')
                failed_count += 1
        processing_time = int((asyncio.get_event_loop().time() - start_time) * 1000)
        return BatchTranslationResponse(translations=translations, total_processed=len(request.translations), failed_count=failed_count, processing_time_ms=processing_time, errors=errors)
    except Exception as e:
        logger.error('Batch translation error: %s', e)
        raise HTTPException(status_code=500, detail=str(e))

@router.post('/detect-language', response_model=LanguageDetectionResponse)
async def detect_language(request: LanguageDetectionRequest, detector: LanguageDetector=Depends(get_language_detector)) -> None:
    """
    Detect the language of given text
    """
    try:
        methods = None
        if request.methods:
            methods = [DetectionMethod(method) for method in request.methods]
        result = await detector.detect_language(request.text, methods)
        return LanguageDetectionResponse(language=result.language, confidence=result.confidence, method=result.method.value, alternatives=[{'language': lang, 'confidence': conf} for lang, conf in result.alternatives], processing_time_ms=result.processing_time_ms) # type: ignore[return-value]
    except Exception as e:
        logger.error('Language detection error: %s', e)
        raise HTTPException(status_code=500, detail=str(e))

@router.post('/detect-language/batch', response_model=BatchDetectionResponse)
async def detect_language_batch(request: BatchDetectionRequest, detector: LanguageDetector=Depends(get_language_detector)) -> None:
    """
    Detect languages for multiple texts in a single request
    """
    start_time = asyncio.get_event_loop().time()
    try:
        if request.methods:
            [DetectionMethod(method) for method in request.methods]
        results = await detector.batch_detect(request.texts)
        detections = []
        for result in results:
            detections.append(LanguageDetectionResponse(language=result.language, confidence=result.confidence, method=result.method.value, alternatives=[{'language': lang, 'confidence': conf} for lang, conf in result.alternatives], processing_time_ms=result.processing_time_ms))
        processing_time = int((asyncio.get_event_loop().time() - start_time) * 1000)
        return BatchDetectionResponse(detections=detections, total_processed=len(request.texts), processing_time_ms=processing_time) # type: ignore[return-value]
    except Exception as e:
        logger.error('Batch language detection error: %s', e)
        raise HTTPException(status_code=500, detail=str(e))

@router.get('/languages', response_model=SupportedLanguagesResponse)
async def get_supported_languages(engine: TranslationEngine=Depends(get_translation_engine), detector: LanguageDetector=Depends(get_language_detector)) -> SupportedLanguagesResponse:
    """
    Get list of supported languages for translation and detection
    """
    try:
        translation_languages = engine.get_supported_languages()
        detection_languages = detector.get_supported_languages()
        all_languages = set()
        for lang_list in translation_languages.values():
            all_languages.update(lang_list)
        all_languages.update(detection_languages)
        return SupportedLanguagesResponse(languages=translation_languages, total_languages=len(all_languages))
    except Exception as e:
        logger.error('Get supported languages error: %s', e)
        raise HTTPException(status_code=500, detail=str(e))

@router.get('/cache/stats')
async def get_cache_stats(cache: TranslationCache | None=Depends(get_translation_cache)) -> None:
    """
    Get translation cache statistics
    """
    if not cache:
        raise HTTPException(status_code=404, detail='Cache service not available')
    try:
        stats = await cache.get_cache_stats()
        return JSONResponse(content=stats) # type: ignore[return-value]
    except Exception as e:
        logger.error('Cache stats error: %s', e)
        raise HTTPException(status_code=500, detail=str(e))

@router.post('/cache/clear')
async def clear_cache(source_language: str | None=None, target_language: str | None=None, cache: TranslationCache | None=Depends(get_translation_cache)) -> dict[str, Any]:
    """
    Clear translation cache (optionally by language pair)
    """
    if not cache:
        raise HTTPException(status_code=404, detail='Cache service not available')
    try:
        if source_language and target_language:
            cleared_count = await cache.clear_by_language_pair(source_language, target_language)
            return {'cleared_count': cleared_count, 'scope': f'{source_language}->{target_language}'}
        else:
            return {'message': 'Full cache clear not implemented yet'}
    except Exception as e:
        logger.error('Cache clear error: %s', e)
        raise HTTPException(status_code=500, detail=str(e))

@router.get('/health', response_model=HealthResponse)
async def health_check(engine: TranslationEngine=Depends(get_translation_engine), detector: LanguageDetector=Depends(get_language_detector), cache: TranslationCache | None=Depends(get_translation_cache), quality_checker: TranslationQualityChecker | None=Depends(get_quality_checker)) -> HealthResponse:
    """
    Health check for all multi-language services
    """
    try:
        services = {}
        translation_health = await engine.health_check()
        services['translation_engine'] = all(translation_health.values())
        detection_health = await detector.health_check()
        services['language_detector'] = all(detection_health.values())
        if cache:
            cache_health = await cache.health_check()
            services['translation_cache'] = cache_health.get('status') == 'healthy'
        else:
            services['translation_cache'] = False
        if quality_checker:
            quality_health = await quality_checker.health_check()
            services['quality_checker'] = all(quality_health.values())
        else:
            services['quality_checker'] = False
        all_healthy = all(services.values())
        status = 'healthy' if all_healthy else 'degraded' if any(services.values()) else 'unhealthy'
        return HealthResponse(status=status, services=services, timestamp=datetime.now(UTC))
    except Exception as e:
        logger.error('Health check error: %s', e)
        return HealthResponse(status='unhealthy', services={'error': str(e)}, timestamp=datetime.now(UTC))

@router.get('/cache/top-translations')
async def get_top_translations(limit: int=100, cache: TranslationCache | None=Depends(get_translation_cache)) -> None:
    """
    Get most accessed translations from cache
    """
    if not cache:
        raise HTTPException(status_code=404, detail='Cache service not available')
    try:
        top_translations = await cache.get_top_translations(limit)
        return JSONResponse(content={'translations': top_translations}) # type: ignore[return-value]
    except Exception as e:
        logger.error('Get top translations error: %s', e)
        raise HTTPException(status_code=500, detail=str(e))

@router.post('/cache/optimize')
async def optimize_cache(cache: TranslationCache | None=Depends(get_translation_cache)) -> None:
    """
    Optimize cache by removing low-access entries
    """
    if not cache:
        raise HTTPException(status_code=404, detail='Cache service not available')
    try:
        optimization_result = await cache.optimize_cache()
        return JSONResponse(content=optimization_result) # type: ignore[return-value]
    except Exception as e:
        logger.error('Cache optimization error: %s', e)
        raise HTTPException(status_code=500, detail=str(e))

@router.exception_handler(ValueError)  # type: ignore[attr-defined, untyped-decorator]
async def value_error_handler(request: Request, exc: ValueError) -> JSONResponse:
    return JSONResponse(status_code=400, content={'error': 'Validation error', 'details': str(exc)})

@router.exception_handler(Exception)  # type: ignore[attr-defined, untyped-decorator]
async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error('Unhandled exception: %s', exc)
    return JSONResponse(status_code=500, content={'error': 'Internal server error', 'details': str(exc)})
