"""
Translation Quality Assurance Module
Quality assessment and validation for translation results
"""

import asyncio
import logging
import re
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from enum import Enum
import nltk
from nltk.tokenize import word_tokenize, sent_tokenize
from nltk.translate.bleu_score import sentence_bleu, SmoothingFunction
import spacy
import numpy as np
from collections import Counter
import difflib

logger = logging.getLogger(__name__)

class QualityMetric(Enum):
    BLEU = "bleu"
    SEMANTIC_SIMILARITY = "semantic_similarity"
    LENGTH_RATIO = "length_ratio"
    CONFIDENCE = "confidence"
    CONSISTENCY = "consistency"

@dataclass
class QualityScore:
    metric: QualityMetric
    score: float
    weight: float
    description: str

@dataclass
class QualityAssessment:
    overall_score: float
    individual_scores: List[QualityScore]
    passed_threshold: bool
    recommendations: List[str]
    processing_time_ms: int

class TranslationQualityChecker:
    """Advanced quality assessment for translation results"""
    
    def __init__(self, config: Dict):
        self.config = config
        self.nlp_models = {}
        self.thresholds = config.get("thresholds", {
            "overall": 0.7,
            "bleu": 0.3,
            "semantic_similarity": 0.6,
            "length_ratio": 0.5,
            "confidence": 0.6
        })
        self._initialize_models()
    
    def _initialize_models(self):
        """Initialize NLP models for quality assessment"""
        try:
            # Load spaCy models for different languages
            languages = ["en", "zh", "es", "fr", "de", "ja", "ko", "ru"]
            for lang in languages:
                try:
                    model_name = f"{lang}_core_web_sm"
                    self.nlp_models[lang] = spacy.load(model_name)
                except OSError:
                    logger.warning(f"Spacy model for {lang} not found, using fallback")
                    # Fallback to English model for basic processing
                    if "en" not in self.nlp_models:
                        self.nlp_models["en"] = spacy.load("en_core_web_sm")
                    self.nlp_models[lang] = self.nlp_models["en"]
            
            # Download NLTK data if needed
            try:
                nltk.data.find('tokenizers/punkt')
            except LookupError:
                nltk.download('punkt')
            
            logger.info("Quality checker models initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize quality checker models: {e}")
    
    async def evaluate_translation(self, source_text: str, translated_text: str,
                                 source_lang: str, target_lang: str,
                                 reference_translation: Optional[str] = None) -> QualityAssessment:
        """Comprehensive quality assessment of translation"""
        
        start_time = asyncio.get_event_loop().time()
        
        scores = []
        
        # 1. Confidence-based scoring
        confidence_score = await self._evaluate_confidence(translated_text, source_lang, target_lang)
        scores.append(confidence_score)
        
        # 2. Length ratio assessment
        length_score = await self._evaluate_length_ratio(source_text, translated_text, source_lang, target_lang)
        scores.append(length_score)
        
        # 3. Semantic similarity (if models available)
        semantic_score = await self._evaluate_semantic_similarity(source_text, translated_text, source_lang, target_lang)
        scores.append(semantic_score)
        
        # 4. BLEU score (if reference available)
        if reference_translation:
            bleu_score = await self._evaluate_bleu_score(translated_text, reference_translation)
            scores.append(bleu_score)
        
        # 5. Consistency check
        consistency_score = await self._evaluate_consistency(source_text, translated_text)
        scores.append(consistency_score)
        
        # Calculate overall score
        overall_score = self._calculate_overall_score(scores)
        
        # Generate recommendations
        recommendations = self._generate_recommendations(scores, overall_score)
        
        processing_time = int((asyncio.get_event_loop().time() - start_time) * 1000)
        
        return QualityAssessment(
            overall_score=overall_score,
            individual_scores=scores,
            passed_threshold=overall_score >= self.thresholds["overall"],
            recommendations=recommendations,
            processing_time_ms=processing_time
        )
    
    async def _evaluate_confidence(self, translated_text: str, source_lang: str, target_lang: str) -> QualityScore:
        """Evaluate translation confidence based on various factors"""
        
        confidence_factors = []
        
        # Text completeness
        if translated_text.strip():
            confidence_factors.append(0.8)
        else:
            confidence_factors.append(0.1)
        
        # Language detection consistency
        try:
            # Basic language detection (simplified)
            if self._is_valid_language(translated_text, target_lang):
                confidence_factors.append(0.7)
            else:
                confidence_factors.append(0.3)
        except:
            confidence_factors.append(0.5)
        
        # Text structure preservation
        source_sentences = sent_tokenize(source_text)
        translated_sentences = sent_tokenize(translated_text)
        
        if len(source_sentences) > 0:
            sentence_ratio = len(translated_sentences) / len(source_sentences)
            if 0.5 <= sentence_ratio <= 2.0:
                confidence_factors.append(0.6)
            else:
                confidence_factors.append(0.3)
        else:
            confidence_factors.append(0.5)
        
        # Average confidence
        avg_confidence = np.mean(confidence_factors)
        
        return QualityScore(
            metric=QualityMetric.CONFIDENCE,
            score=avg_confidence,
            weight=0.3,
            description=f"Confidence based on text completeness, language detection, and structure preservation"
        )
    
    async def _evaluate_length_ratio(self, source_text: str, translated_text: str,
                                   source_lang: str, target_lang: str) -> QualityScore:
        """Evaluate appropriate length ratio between source and target"""
        
        source_length = len(source_text.strip())
        translated_length = len(translated_text.strip())
        
        if source_length == 0:
            return QualityScore(
                metric=QualityMetric.LENGTH_RATIO,
                score=0.0,
                weight=0.2,
                description="Empty source text"
            )
        
        ratio = translated_length / source_length
        
        # Expected length ratios by language pair (simplified)
        expected_ratios = {
            ("en", "zh"): 0.8,  # Chinese typically shorter
            ("en", "ja"): 0.9,
            ("en", "ko"): 0.9,
            ("zh", "en"): 1.2,  # English typically longer
            ("ja", "en"): 1.1,
            ("ko", "en"): 1.1,
        }
        
        expected_ratio = expected_ratios.get((source_lang, target_lang), 1.0)
        
        # Calculate score based on deviation from expected ratio
        deviation = abs(ratio - expected_ratio)
        score = max(0.0, 1.0 - deviation)
        
        return QualityScore(
            metric=QualityMetric.LENGTH_RATIO,
            score=score,
            weight=0.2,
            description=f"Length ratio: {ratio:.2f} (expected: {expected_ratio:.2f})"
        )
    
    async def _evaluate_semantic_similarity(self, source_text: str, translated_text: str,
                                          source_lang: str, target_lang: str) -> QualityScore:
        """Evaluate semantic similarity using NLP models"""
        
        try:
            # Get appropriate NLP models
            source_nlp = self.nlp_models.get(source_lang, self.nlp_models.get("en"))
            target_nlp = self.nlp_models.get(target_lang, self.nlp_models.get("en"))
            
            # Process texts
            source_doc = source_nlp(source_text)
            target_doc = target_nlp(translated_text)
            
            # Extract key features
            source_features = self._extract_text_features(source_doc)
            target_features = self._extract_text_features(target_doc)
            
            # Calculate similarity
            similarity = self._calculate_feature_similarity(source_features, target_features)
            
            return QualityScore(
                metric=QualityMetric.SEMANTIC_SIMILARITY,
                score=similarity,
                weight=0.3,
                description=f"Semantic similarity based on NLP features"
            )
            
        except Exception as e:
            logger.warning(f"Semantic similarity evaluation failed: {e}")
            # Fallback to basic similarity
            return QualityScore(
                metric=QualityMetric.SEMANTIC_SIMILARITY,
                score=0.5,
                weight=0.3,
                description="Fallback similarity score"
            )
    
    async def _evaluate_bleu_score(self, translated_text: str, reference_text: str) -> QualityScore:
        """Calculate BLEU score against reference translation"""
        
        try:
            # Tokenize texts
            reference_tokens = word_tokenize(reference_text.lower())
            candidate_tokens = word_tokenize(translated_text.lower())
            
            # Calculate BLEU score with smoothing
            smoothing = SmoothingFunction().method1
            bleu_score = sentence_bleu([reference_tokens], candidate_tokens, smoothing_function=smoothing)
            
            return QualityScore(
                metric=QualityMetric.BLEU,
                score=bleu_score,
                weight=0.2,
                description=f"BLEU score against reference translation"
            )
            
        except Exception as e:
            logger.warning(f"BLEU score calculation failed: {e}")
            return QualityScore(
                metric=QualityMetric.BLEU,
                score=0.0,
                weight=0.2,
                description="BLEU score calculation failed"
            )
    
    async def _evaluate_consistency(self, source_text: str, translated_text: str) -> QualityScore:
        """Evaluate internal consistency of translation"""
        
        consistency_factors = []
        
        # Check for repeated patterns
        source_words = word_tokenize(source_text.lower())
        translated_words = word_tokenize(translated_text.lower())
        
        source_word_freq = Counter(source_words)
        translated_word_freq = Counter(translated_words)
        
        # Check if high-frequency words are preserved
        common_words = [word for word, freq in source_word_freq.most_common(5) if freq > 1]
        
        if common_words:
            preserved_count = 0
            for word in common_words:
                # Simplified check - in reality, this would be more complex
                if len(translated_words) >= len(source_words) * 0.8:
                    preserved_count += 1
            
            consistency_score = preserved_count / len(common_words)
            consistency_factors.append(consistency_score)
        else:
            consistency_factors.append(0.8)  # No repetition issues
        
        # Check for formatting consistency
        source_punctuation = re.findall(r'[.!?;:,]', source_text)
        translated_punctuation = re.findall(r'[.!?;:,]', translated_text)
        
        if len(source_punctuation) > 0:
            punctuation_ratio = len(translated_punctuation) / len(source_punctuation)
            if 0.5 <= punctuation_ratio <= 2.0:
                consistency_factors.append(0.7)
            else:
                consistency_factors.append(0.4)
        else:
            consistency_factors.append(0.8)
        
        avg_consistency = np.mean(consistency_factors)
        
        return QualityScore(
            metric=QualityMetric.CONSISTENCY,
            score=avg_consistency,
            weight=0.1,
            description="Internal consistency of translation"
        )
    
    def _extract_text_features(self, doc) -> Dict[str, Any]:
        """Extract linguistic features from spaCy document"""
        features = {
            "pos_tags": [token.pos_ for token in doc],
            "entities": [(ent.text, ent.label_) for ent in doc.ents],
            "noun_chunks": [chunk.text for chunk in doc.noun_chunks],
            "verbs": [token.lemma_ for token in doc if token.pos_ == "VERB"],
            "sentence_count": len(list(doc.sents)),
            "token_count": len(doc),
        }
        return features
    
    def _calculate_feature_similarity(self, source_features: Dict, target_features: Dict) -> float:
        """Calculate similarity between text features"""
        
        similarities = []
        
        # POS tag similarity
        source_pos = Counter(source_features["pos_tags"])
        target_pos = Counter(target_features["pos_tags"])
        
        if source_pos and target_pos:
            pos_similarity = self._calculate_counter_similarity(source_pos, target_pos)
            similarities.append(pos_similarity)
        
        # Entity similarity
        source_entities = set([ent[0].lower() for ent in source_features["entities"]])
        target_entities = set([ent[0].lower() for ent in target_features["entities"]])
        
        if source_entities and target_entities:
            entity_similarity = len(source_entities & target_entities) / len(source_entities | target_entities)
            similarities.append(entity_similarity)
        
        # Length similarity
        source_len = source_features["token_count"]
        target_len = target_features["token_count"]
        
        if source_len > 0 and target_len > 0:
            length_similarity = min(source_len, target_len) / max(source_len, target_len)
            similarities.append(length_similarity)
        
        return np.mean(similarities) if similarities else 0.5
    
    def _calculate_counter_similarity(self, counter1: Counter, counter2: Counter) -> float:
        """Calculate similarity between two Counters"""
        all_items = set(counter1.keys()) | set(counter2.keys())
        
        if not all_items:
            return 1.0
        
        dot_product = sum(counter1[item] * counter2[item] for item in all_items)
        magnitude1 = sum(counter1[item] ** 2 for item in all_items) ** 0.5
        magnitude2 = sum(counter2[item] ** 2 for item in all_items) ** 0.5
        
        if magnitude1 == 0 or magnitude2 == 0:
            return 0.0
        
        return dot_product / (magnitude1 * magnitude2)
    
    def _is_valid_language(self, text: str, expected_lang: str) -> bool:
        """Basic language validation (simplified)"""
        # This is a placeholder - in reality, you'd use a proper language detector
        lang_patterns = {
            "zh": r"[\u4e00-\u9fff]",
            "ja": r"[\u3040-\u309f\u30a0-\u30ff]",
            "ko": r"[\uac00-\ud7af]",
            "ar": r"[\u0600-\u06ff]",
            "ru": r"[\u0400-\u04ff]",
        }
        
        pattern = lang_patterns.get(expected_lang, r"[a-zA-Z]")
        matches = re.findall(pattern, text)
        
        return len(matches) > len(text) * 0.1  # At least 10% of characters should match
    
    def _calculate_overall_score(self, scores: List[QualityScore]) -> float:
        """Calculate weighted overall quality score"""
        
        if not scores:
            return 0.0
        
        weighted_sum = sum(score.score * score.weight for score in scores)
        total_weight = sum(score.weight for score in scores)
        
        return weighted_sum / total_weight if total_weight > 0 else 0.0
    
    def _generate_recommendations(self, scores: List[QualityScore], overall_score: float) -> List[str]:
        """Generate improvement recommendations based on quality assessment"""
        
        recommendations = []
        
        if overall_score < self.thresholds["overall"]:
            recommendations.append("Translation quality below threshold - consider manual review")
        
        for score in scores:
            if score.score < self.thresholds.get(score.metric.value, 0.5):
                if score.metric == QualityMetric.LENGTH_RATIO:
                    recommendations.append("Translation length seems inappropriate - check for truncation or expansion")
                elif score.metric == QualityMetric.SEMANTIC_SIMILARITY:
                    recommendations.append("Semantic meaning may be lost - verify key concepts are preserved")
                elif score.metric == QualityMetric.CONSISTENCY:
                    recommendations.append("Translation lacks consistency - check for repeated patterns and formatting")
                elif score.metric == QualityMetric.CONFIDENCE:
                    recommendations.append("Low confidence detected - verify translation accuracy")
        
        return recommendations
    
    async def batch_evaluate(self, translations: List[Tuple[str, str, str, str, Optional[str]]]) -> List[QualityAssessment]:
        """Evaluate multiple translations in parallel"""
        
        tasks = []
        for source_text, translated_text, source_lang, target_lang, reference in translations:
            task = self.evaluate_translation(source_text, translated_text, source_lang, target_lang, reference)
            tasks.append(task)
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Handle exceptions
        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, QualityAssessment):
                processed_results.append(result)
            else:
                logger.error(f"Quality assessment failed for translation {i}: {result}")
                # Add fallback assessment
                processed_results.append(QualityAssessment(
                    overall_score=0.5,
                    individual_scores=[],
                    passed_threshold=False,
                    recommendations=["Quality assessment failed"],
                    processing_time_ms=0
                ))
        
        return processed_results
    
    async def health_check(self) -> Dict[str, bool]:
        """Health check for quality checker"""
        
        health_status = {}
        
        # Test with sample translation
        try:
            sample_assessment = await self.evaluate_translation(
                "Hello world", "Hola mundo", "en", "es"
            )
            health_status["basic_assessment"] = sample_assessment.overall_score > 0
        except Exception as e:
            logger.error(f"Quality checker health check failed: {e}")
            health_status["basic_assessment"] = False
        
        # Check model availability
        health_status["nlp_models_loaded"] = len(self.nlp_models) > 0
        
        return health_status
