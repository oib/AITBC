"""
Language Detection Service
Automatic language detection for multi-language support
"""

import asyncio
from dataclasses import dataclass
from enum import Enum

import fasttext  # type: ignore[import-not-found]
import langdetect  # type: ignore[import-not-found]
from langdetect.lang_detect_exception import LangDetectException  # type: ignore[import-not-found]
from polyglot.detect import Detector  # type: ignore[import-not-found]

from aitbc.aitbc_logging import get_logger

logger = get_logger(__name__)


class DetectionMethod(Enum):
    LANGDETECT = "langdetect"
    POLYGLOT = "polyglot"
    FASTTEXT = "fasttext"
    ENSEMBLE = "ensemble"


@dataclass
class DetectionResult:
    language: str
    confidence: float
    method: DetectionMethod
    alternatives: list[tuple[str, float]]
    processing_time_ms: int


class LanguageDetector:
    """Advanced language detection with multiple methods and ensemble voting"""

    def __init__(self, config: dict):
        self.config = config
        self.fasttext_model = None
        self._initialize_fasttext()

    def _initialize_fasttext(self) -> None:
        """Initialize FastText language detection model"""
        try:
            model_path = self.config.get("fasttext", {}).get("model_path", "lid.176.bin")
            self.fasttext_model = fasttext.load_model(model_path)
            logger.info("FastText model loaded successfully")
        except Exception as e:
            logger.warning("FastText model initialization failed: %s", e)
            self.fasttext_model = None

    async def detect_language(self, text: str, methods: list[DetectionMethod] | None = None) -> DetectionResult:
        """Detect language with specified methods or ensemble"""
        if not methods:
            methods = [DetectionMethod.ENSEMBLE]
        if DetectionMethod.ENSEMBLE in methods:
            return await self._ensemble_detection(text)
        method = methods[0]
        return await self._detect_with_method(text, method)

    async def _detect_with_method(self, text: str, method: DetectionMethod) -> DetectionResult:
        """Detect language using specific method"""
        start_time = asyncio.get_event_loop().time()
        try:
            if method == DetectionMethod.LANGDETECT:
                return await self._langdetect_method(text, start_time)
            elif method == DetectionMethod.POLYGLOT:
                return await self._polyglot_method(text, start_time)
            elif method == DetectionMethod.FASTTEXT:
                return await self._fasttext_method(text, start_time)
            else:
                raise ValueError(f"Unsupported detection method: {method}")
        except Exception as e:
            logger.error("Language detection failed with %s: %s", method.value, e)
            return await self._langdetect_method(text, start_time)

    async def _langdetect_method(self, text: str, start_time: float) -> DetectionResult:
        """Language detection using langdetect library"""

        def detect() -> None:
            try:
                langs = langdetect.detect_langs(text)
                return langs  # type: ignore[no-any-return]
            except LangDetectException:
                return [langdetect.DetectLanguage("en", 1.0)]  # type: ignore[return-value]

        langs = await asyncio.get_event_loop().run_in_executor(None, detect)  # type: ignore[func-returns-value]
        primary_lang = langs[0].lang  # type: ignore[index]
        confidence = langs[0].prob  # type: ignore[index]
        alternatives = [(lang.lang, lang.prob) for lang in langs[1:]]  # type: ignore[index]
        processing_time = int((asyncio.get_event_loop().time() - start_time) * 1000)
        return DetectionResult(
            language=primary_lang,
            confidence=confidence,
            method=DetectionMethod.LANGDETECT,
            alternatives=alternatives,
            processing_time_ms=processing_time,
        )

    async def _polyglot_method(self, text: str, start_time: float) -> DetectionResult:
        """Language detection using Polyglot library"""

        def detect() -> None:
            try:
                detector = Detector(text)
                return detector  # type: ignore[no-any-return]
            except Exception as e:
                logger.warning("Polyglot detection failed: %s", e)

                class FallbackDetector:
                    def __init__(self) -> None:
                        self.language = "en"
                        self.confidence = 0.5

                return FallbackDetector()  # type: ignore[return-value]

        detector = await asyncio.get_event_loop().run_in_executor(None, detect)  # type: ignore[func-returns-value]
        primary_lang = detector.language  # type: ignore[attr-defined]
        confidence = getattr(detector, "confidence", 0.8)
        alternatives: list = []
        processing_time = int((asyncio.get_event_loop().time() - start_time) * 1000)
        return DetectionResult(
            language=primary_lang,
            confidence=confidence,
            method=DetectionMethod.POLYGLOT,
            alternatives=alternatives,
            processing_time_ms=processing_time,
        )

    async def _fasttext_method(self, text: str, start_time: float) -> DetectionResult:
        """Language detection using FastText model"""
        if not self.fasttext_model:
            raise Exception("FastText model not available")

        def detect():  # type: ignore[unreachable]
            processed_text = text.replace("\n", " ").strip()
            if len(processed_text) < 10:
                processed_text += " " * (10 - len(processed_text))
            labels, probabilities = self.fasttext_model.predict(processed_text, k=5)
            results = []
            for label, prob in zip(labels, probabilities, strict=False):
                lang = label.replace("__label__", "")
                results.append((lang, float(prob)))
            return results

        results = await asyncio.get_event_loop().run_in_executor(None, detect)
        if not results:
            raise Exception("FastText detection failed")
        primary_lang, confidence = results[0]
        alternatives = results[1:]
        processing_time = int((asyncio.get_event_loop().time() - start_time) * 1000)
        return DetectionResult(
            language=primary_lang,
            confidence=confidence,
            method=DetectionMethod.FASTTEXT,
            alternatives=alternatives,
            processing_time_ms=processing_time,
        )

    async def _ensemble_detection(self, text: str) -> DetectionResult:
        """Ensemble detection combining multiple methods"""
        methods = [DetectionMethod.LANGDETECT, DetectionMethod.POLYGLOT]
        if self.fasttext_model:
            methods.append(DetectionMethod.FASTTEXT)  # type: ignore[unreachable]
        tasks = [self._detect_with_method(text, method) for method in methods]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        valid_results = []
        for result in results:
            if isinstance(result, DetectionResult):
                valid_results.append(result)
            else:
                logger.warning("Detection method failed: %s", result)
        if not valid_results:
            return DetectionResult(
                language="en", confidence=0.5, method=DetectionMethod.LANGDETECT, alternatives=[], processing_time_ms=0
            )
        return self._ensemble_voting(valid_results)

    def _ensemble_voting(self, results: list[DetectionResult]) -> DetectionResult:
        """Combine multiple detection results using weighted voting"""
        method_weights = {DetectionMethod.LANGDETECT: 0.3, DetectionMethod.POLYGLOT: 0.2, DetectionMethod.FASTTEXT: 0.5}
        votes = {}
        total_confidence = 0
        total_processing_time = 0
        for result in results:
            weight = method_weights.get(result.method, 0.1)
            weighted_confidence = result.confidence * weight
            if result.language not in votes:
                votes[result.language] = 0
            votes[result.language] += weighted_confidence  # type: ignore[assignment]
            total_confidence += weighted_confidence  # type: ignore[assignment]
            total_processing_time += result.processing_time_ms
        if not votes:
            return results[0]
        winner_language = max(votes.keys(), key=lambda x: votes[x])
        winner_confidence = votes[winner_language] / total_confidence if total_confidence > 0 else 0.5
        alternatives = []
        for lang, score in sorted(votes.items(), key=lambda x: x[1], reverse=True):
            if lang != winner_language:
                alternatives.append((lang, score / total_confidence))
        return DetectionResult(
            language=winner_language,
            confidence=winner_confidence,
            method=DetectionMethod.ENSEMBLE,
            alternatives=alternatives[:5],
            processing_time_ms=int(total_processing_time / len(results)),
        )

    def get_supported_languages(self) -> list[str]:
        """Get list of supported languages for detection"""
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
            "pl",
            "tr",
            "th",
            "vi",
            "id",
            "ms",
            "tl",
            "sw",
            "af",
            "is",
            "mt",
            "cy",
            "ga",
            "gd",
            "eu",
            "ca",
            "gl",
            "ast",
            "lb",
            "rm",
            "fur",
            "lld",
            "lij",
            "lmo",
            "vec",
            "scn",
            "ro",
            "mo",
            "hr",
            "sr",
            "sl",
            "sk",
            "cs",
            "pl",
            "uk",
            "be",
            "bg",
            "mk",
            "sq",
            "hy",
            "ka",
            "he",
            "yi",
            "fa",
            "ps",
            "ur",
            "bn",
            "as",
            "or",
            "pa",
            "gu",
            "mr",
            "ne",
            "si",
            "ta",
            "te",
            "ml",
            "kn",
            "my",
            "km",
            "lo",
            "th",
            "vi",
            "id",
            "ms",
            "jv",
            "su",
            "tl",
            "sw",
            "zu",
            "xh",
            "af",
            "is",
            "mt",
            "cy",
            "ga",
            "gd",
            "eu",
            "ca",
            "gl",
            "ast",
            "lb",
            "rm",
            "fur",
            "lld",
            "lij",
            "lmo",
            "vec",
            "scn",
        ]

    async def batch_detect(self, texts: list[str]) -> list[DetectionResult]:
        """Detect languages for multiple texts in parallel"""
        tasks = [self.detect_language(text) for text in texts]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, DetectionResult):
                processed_results.append(result)
            else:
                logger.error("Batch detection failed for text %s: %s", i, result)
                processed_results.append(
                    DetectionResult(
                        language="en", confidence=0.5, method=DetectionMethod.LANGDETECT, alternatives=[], processing_time_ms=0
                    )
                )
        return processed_results

    def validate_language_code(self, language_code: str) -> bool:
        """Validate if language code is supported"""
        supported = self.get_supported_languages()
        return language_code.lower() in supported

    def normalize_language_code(self, language_code: str) -> str:
        """Normalize language code to standard format"""
        mappings = {
            "zh": "zh-cn",
            "zh-cn": "zh-cn",
            "zh_tw": "zh-tw",
            "en_us": "en",
            "en-us": "en",
            "en_gb": "en",
            "en-gb": "en",
        }
        normalized = language_code.lower().replace("_", "-")
        return mappings.get(normalized, normalized)

    async def health_check(self) -> dict[str, bool]:
        """Health check for all detection methods"""
        health_status = {}
        test_text = "Hello, how are you today?"
        methods_to_test = [DetectionMethod.LANGDETECT, DetectionMethod.POLYGLOT]
        if self.fasttext_model:
            methods_to_test.append(DetectionMethod.FASTTEXT)  # type: ignore[unreachable]
        for method in methods_to_test:
            try:
                result = await self._detect_with_method(test_text, method)
                health_status[method.value] = result.confidence > 0.5
            except Exception as e:
                logger.error("Health check failed for %s: %s", method.value, e)
                health_status[method.value] = False
        try:
            result = await self._ensemble_detection(test_text)
            health_status["ensemble"] = result.confidence > 0.5
        except Exception as e:
            logger.error("Ensemble health check failed: %s", e)
            health_status["ensemble"] = False
        return health_status
