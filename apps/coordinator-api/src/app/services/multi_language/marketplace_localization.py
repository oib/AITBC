"""
Marketplace Localization Support
Multi-language support for marketplace listings and content
"""

import asyncio
import logging
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict
from enum import Enum
import json
from datetime import datetime

from .translation_engine import TranslationEngine, TranslationRequest, TranslationResponse
from .language_detector import LanguageDetector, DetectionResult
from .translation_cache import TranslationCache
from .quality_assurance import TranslationQualityChecker

logger = logging.getLogger(__name__)

class ListingType(Enum):
    SERVICE = "service"
    AGENT = "agent"
    RESOURCE = "resource"
    DATASET = "dataset"

@dataclass
class LocalizedListing:
    """Multi-language marketplace listing"""
    id: str
    original_id: str
    listing_type: ListingType
    language: str
    title: str
    description: str
    keywords: List[str]
    features: List[str]
    requirements: List[str]
    pricing_info: Dict[str, Any]
    translation_confidence: Optional[float] = None
    translation_provider: Optional[str] = None
    translated_at: Optional[datetime] = None
    reviewed: bool = False
    reviewer_id: Optional[str] = None
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.translated_at is None:
            self.translated_at = datetime.utcnow()
        if self.metadata is None:
            self.metadata = {}

@dataclass
class LocalizationRequest:
    """Request for listing localization"""
    listing_id: str
    target_languages: List[str]
    translate_title: bool = True
    translate_description: bool = True
    translate_keywords: bool = True
    translate_features: bool = True
    translate_requirements: bool = True
    quality_threshold: float = 0.7
    priority: str = "normal"  # low, normal, high

class MarketplaceLocalization:
    """Marketplace localization service"""
    
    def __init__(self, translation_engine: TranslationEngine,
                 language_detector: LanguageDetector,
                 translation_cache: Optional[TranslationCache] = None,
                 quality_checker: Optional[TranslationQualityChecker] = None):
        self.translation_engine = translation_engine
        self.language_detector = language_detector
        self.translation_cache = translation_cache
        self.quality_checker = quality_checker
        self.localized_listings: Dict[str, List[LocalizedListing]] = {}  # listing_id -> [LocalizedListing]
        self.localization_queue: List[LocalizationRequest] = []
        self.localization_stats = {
            "total_localizations": 0,
            "successful_localizations": 0,
            "failed_localizations": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "quality_checks": 0
        }
    
    async def create_localized_listing(self, original_listing: Dict[str, Any], 
                                     target_languages: List[str]) -> List[LocalizedListing]:
        """Create localized versions of a marketplace listing"""
        try:
            localized_listings = []
            
            # Detect original language if not specified
            original_language = original_listing.get("language", "en")
            if not original_language:
                # Detect from title and description
                text_to_detect = f"{original_listing.get('title', '')} {original_listing.get('description', '')}"
                detection_result = await self.language_detector.detect_language(text_to_detect)
                original_language = detection_result.language
            
            # Create localized versions for each target language
            for target_lang in target_languages:
                if target_lang == original_language:
                    continue  # Skip same language
                
                localized_listing = await self._translate_listing(
                    original_listing, original_language, target_lang
                )
                
                if localized_listing:
                    localized_listings.append(localized_listing)
            
            # Store localized listings
            listing_id = original_listing.get("id")
            if listing_id not in self.localized_listings:
                self.localized_listings[listing_id] = []
            self.localized_listings[listing_id].extend(localized_listings)
            
            return localized_listings
            
        except Exception as e:
            logger.error(f"Failed to create localized listings: {e}")
            return []
    
    async def _translate_listing(self, original_listing: Dict[str, Any], 
                               source_lang: str, target_lang: str) -> Optional[LocalizedListing]:
        """Translate a single listing to target language"""
        try:
            translations = {}
            confidence_scores = []
            
            # Translate title
            title = original_listing.get("title", "")
            if title:
                title_result = await self._translate_text(
                    title, source_lang, target_lang, "marketplace_title"
                )
                if title_result:
                    translations["title"] = title_result.translated_text
                    confidence_scores.append(title_result.confidence)
            
            # Translate description
            description = original_listing.get("description", "")
            if description:
                desc_result = await self._translate_text(
                    description, source_lang, target_lang, "marketplace_description"
                )
                if desc_result:
                    translations["description"] = desc_result.translated_text
                    confidence_scores.append(desc_result.confidence)
            
            # Translate keywords
            keywords = original_listing.get("keywords", [])
            translated_keywords = []
            for keyword in keywords:
                keyword_result = await self._translate_text(
                    keyword, source_lang, target_lang, "marketplace_keyword"
                )
                if keyword_result:
                    translated_keywords.append(keyword_result.translated_text)
                    confidence_scores.append(keyword_result.confidence)
            translations["keywords"] = translated_keywords
            
            # Translate features
            features = original_listing.get("features", [])
            translated_features = []
            for feature in features:
                feature_result = await self._translate_text(
                    feature, source_lang, target_lang, "marketplace_feature"
                )
                if feature_result:
                    translated_features.append(feature_result.translated_text)
                    confidence_scores.append(feature_result.confidence)
            translations["features"] = translated_features
            
            # Translate requirements
            requirements = original_listing.get("requirements", [])
            translated_requirements = []
            for requirement in requirements:
                req_result = await self._translate_text(
                    requirement, source_lang, target_lang, "marketplace_requirement"
                )
                if req_result:
                    translated_requirements.append(req_result.translated_text)
                    confidence_scores.append(req_result.confidence)
            translations["requirements"] = translated_requirements
            
            # Calculate overall confidence
            overall_confidence = sum(confidence_scores) / len(confidence_scores) if confidence_scores else 0.0
            
            # Create localized listing
            localized_listing = LocalizedListing(
                id=f"{original_listing.get('id')}_{target_lang}",
                original_id=original_listing.get("id"),
                listing_type=ListingType(original_listing.get("type", "service")),
                language=target_lang,
                title=translations.get("title", ""),
                description=translations.get("description", ""),
                keywords=translations.get("keywords", []),
                features=translations.get("features", []),
                requirements=translations.get("requirements", []),
                pricing_info=original_listing.get("pricing_info", {}),
                translation_confidence=overall_confidence,
                translation_provider="mixed",  # Could be enhanced to track actual providers
                translated_at=datetime.utcnow()
            )
            
            # Quality check
            if self.quality_checker and overall_confidence > 0.5:
                await self._perform_quality_check(localized_listing, original_listing)
            
            self.localization_stats["total_localizations"] += 1
            self.localization_stats["successful_localizations"] += 1
            
            return localized_listing
            
        except Exception as e:
            logger.error(f"Failed to translate listing: {e}")
            self.localization_stats["failed_localizations"] += 1
            return None
    
    async def _translate_text(self, text: str, source_lang: str, target_lang: str, 
                           context: str) -> Optional[TranslationResponse]:
        """Translate text with caching and context"""
        try:
            # Check cache first
            if self.translation_cache:
                cached_result = await self.translation_cache.get(text, source_lang, target_lang, context)
                if cached_result:
                    self.localization_stats["cache_hits"] += 1
                    return cached_result
                self.localization_stats["cache_misses"] += 1
            
            # Perform translation
            translation_request = TranslationRequest(
                text=text,
                source_language=source_lang,
                target_language=target_lang,
                context=context,
                domain="marketplace"
            )
            
            translation_result = await self.translation_engine.translate(translation_request)
            
            # Cache the result
            if self.translation_cache and translation_result.confidence > 0.8:
                await self.translation_cache.set(text, source_lang, target_lang, translation_result, context=context)
            
            return translation_result
            
        except Exception as e:
            logger.error(f"Failed to translate text: {e}")
            return None
    
    async def _perform_quality_check(self, localized_listing: LocalizedListing, 
                                  original_listing: Dict[str, Any]):
        """Perform quality assessment on localized listing"""
        try:
            if not self.quality_checker:
                return
            
            # Quality check title
            if localized_listing.title and original_listing.get("title"):
                title_assessment = await self.quality_checker.evaluate_translation(
                    original_listing["title"],
                    localized_listing.title,
                    "en",  # Assuming original is English for now
                    localized_listing.language
                )
                
                # Update confidence based on quality check
                if title_assessment.overall_score < localized_listing.translation_confidence:
                    localized_listing.translation_confidence = title_assessment.overall_score
            
            # Quality check description
            if localized_listing.description and original_listing.get("description"):
                desc_assessment = await self.quality_checker.evaluate_translation(
                    original_listing["description"],
                    localized_listing.description,
                    "en",
                    localized_listing.language
                )
                
                # Update confidence
                if desc_assessment.overall_score < localized_listing.translation_confidence:
                    localized_listing.translation_confidence = desc_assessment.overall_score
            
            self.localization_stats["quality_checks"] += 1
            
        except Exception as e:
            logger.error(f"Failed to perform quality check: {e}")
    
    async def get_localized_listing(self, listing_id: str, language: str) -> Optional[LocalizedListing]:
        """Get localized listing for specific language"""
        try:
            if listing_id in self.localized_listings:
                for listing in self.localized_listings[listing_id]:
                    if listing.language == language:
                        return listing
            return None
        except Exception as e:
            logger.error(f"Failed to get localized listing: {e}")
            return None
    
    async def search_localized_listings(self, query: str, language: str, 
                                     filters: Optional[Dict[str, Any]] = None) -> List[LocalizedListing]:
        """Search localized listings with multi-language support"""
        try:
            results = []
            
            # Detect query language if needed
            query_language = language
            if language != "en":  # Assume English as default
                detection_result = await self.language_detector.detect_language(query)
                query_language = detection_result.language
            
            # Search in all localized listings
            for listing_id, listings in self.localized_listings.items():
                for listing in listings:
                    if listing.language != language:
                        continue
                    
                    # Simple text matching (could be enhanced with proper search)
                    if self._matches_query(listing, query, query_language):
                        # Apply filters if provided
                        if filters and not self._matches_filters(listing, filters):
                            continue
                        
                        results.append(listing)
            
            # Sort by relevance (could be enhanced with proper ranking)
            results.sort(key=lambda x: x.translation_confidence or 0, reverse=True)
            
            return results
            
        except Exception as e:
            logger.error(f"Failed to search localized listings: {e}")
            return []
    
    def _matches_query(self, listing: LocalizedListing, query: str, query_language: str) -> bool:
        """Check if listing matches search query"""
        query_lower = query.lower()
        
        # Search in title
        if query_lower in listing.title.lower():
            return True
        
        # Search in description
        if query_lower in listing.description.lower():
            return True
        
        # Search in keywords
        for keyword in listing.keywords:
            if query_lower in keyword.lower():
                return True
        
        # Search in features
        for feature in listing.features:
            if query_lower in feature.lower():
                return True
        
        return False
    
    def _matches_filters(self, listing: LocalizedListing, filters: Dict[str, Any]) -> bool:
        """Check if listing matches provided filters"""
        # Filter by listing type
        if "listing_type" in filters:
            if listing.listing_type.value != filters["listing_type"]:
                return False
        
        # Filter by minimum confidence
        if "min_confidence" in filters:
            if (listing.translation_confidence or 0) < filters["min_confidence"]:
                return False
        
        # Filter by reviewed status
        if "reviewed_only" in filters and filters["reviewed_only"]:
            if not listing.reviewed:
                return False
        
        # Filter by price range
        if "price_range" in filters:
            price_info = listing.pricing_info
            if "min_price" in price_info and "max_price" in price_info:
                price_min = filters["price_range"].get("min", 0)
                price_max = filters["price_range"].get("max", float("inf"))
                if price_info["min_price"] > price_max or price_info["max_price"] < price_min:
                    return False
        
        return True
    
    async def batch_localize_listings(self, listings: List[Dict[str, Any]], 
                                    target_languages: List[str]) -> Dict[str, List[LocalizedListing]]:
        """Localize multiple listings in batch"""
        try:
            results = {}
            
            # Process listings in parallel
            tasks = []
            for listing in listings:
                task = self.create_localized_listing(listing, target_languages)
                tasks.append(task)
            
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Process results
            for i, result in enumerate(batch_results):
                listing_id = listings[i].get("id", f"unknown_{i}")
                if isinstance(result, list):
                    results[listing_id] = result
                else:
                    logger.error(f"Failed to localize listing {listing_id}: {result}")
                    results[listing_id] = []
            
            return results
            
        except Exception as e:
            logger.error(f"Failed to batch localize listings: {e}")
            return {}
    
    async def update_localized_listing(self, localized_listing: LocalizedListing) -> bool:
        """Update an existing localized listing"""
        try:
            listing_id = localized_listing.original_id
            
            if listing_id not in self.localized_listings:
                self.localized_listings[listing_id] = []
            
            # Find and update existing listing
            for i, existing in enumerate(self.localized_listings[listing_id]):
                if existing.id == localized_listing.id:
                    self.localized_listings[listing_id][i] = localized_listing
                    return True
            
            # Add new listing if not found
            self.localized_listings[listing_id].append(localized_listing)
            return True
            
        except Exception as e:
            logger.error(f"Failed to update localized listing: {e}")
            return False
    
    async def get_localization_statistics(self) -> Dict[str, Any]:
        """Get comprehensive localization statistics"""
        try:
            stats = self.localization_stats.copy()
            
            # Calculate success rate
            total = stats["total_localizations"]
            if total > 0:
                stats["success_rate"] = stats["successful_localizations"] / total
                stats["failure_rate"] = stats["failed_localizations"] / total
            else:
                stats["success_rate"] = 0.0
                stats["failure_rate"] = 0.0
            
            # Calculate cache hit ratio
            cache_total = stats["cache_hits"] + stats["cache_misses"]
            if cache_total > 0:
                stats["cache_hit_ratio"] = stats["cache_hits"] / cache_total
            else:
                stats["cache_hit_ratio"] = 0.0
            
            # Language statistics
            language_stats = {}
            total_listings = 0
            
            for listing_id, listings in self.localized_listings.items():
                for listing in listings:
                    lang = listing.language
                    if lang not in language_stats:
                        language_stats[lang] = 0
                    language_stats[lang] += 1
                    total_listings += 1
            
            stats["language_distribution"] = language_stats
            stats["total_localized_listings"] = total_listings
            
            # Quality statistics
            quality_stats = {
                "high_quality": 0,  # > 0.8
                "medium_quality": 0,  # 0.6-0.8
                "low_quality": 0,  # < 0.6
                "reviewed": 0
            }
            
            for listings in self.localized_listings.values():
                for listing in listings:
                    confidence = listing.translation_confidence or 0
                    if confidence > 0.8:
                        quality_stats["high_quality"] += 1
                    elif confidence > 0.6:
                        quality_stats["medium_quality"] += 1
                    else:
                        quality_stats["low_quality"] += 1
                    
                    if listing.reviewed:
                        quality_stats["reviewed"] += 1
            
            stats["quality_statistics"] = quality_stats
            
            return stats
            
        except Exception as e:
            logger.error(f"Failed to get localization statistics: {e}")
            return {"error": str(e)}
    
    async def health_check(self) -> Dict[str, Any]:
        """Health check for marketplace localization"""
        try:
            health_status = {
                "overall": "healthy",
                "services": {},
                "statistics": {}
            }
            
            # Check translation engine
            translation_health = await self.translation_engine.health_check()
            health_status["services"]["translation_engine"] = all(translation_health.values())
            
            # Check language detector
            detection_health = await self.language_detector.health_check()
            health_status["services"]["language_detector"] = all(detection_health.values())
            
            # Check cache
            if self.translation_cache:
                cache_health = await self.translation_cache.health_check()
                health_status["services"]["translation_cache"] = cache_health.get("status") == "healthy"
            else:
                health_status["services"]["translation_cache"] = False
            
            # Check quality checker
            if self.quality_checker:
                quality_health = await self.quality_checker.health_check()
                health_status["services"]["quality_checker"] = all(quality_health.values())
            else:
                health_status["services"]["quality_checker"] = False
            
            # Overall status
            all_healthy = all(health_status["services"].values())
            health_status["overall"] = "healthy" if all_healthy else "degraded" if any(health_status["services"].values()) else "unhealthy"
            
            # Add statistics
            health_status["statistics"] = {
                "total_listings": len(self.localized_listings),
                "localization_stats": self.localization_stats
            }
            
            return health_status
            
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return {
                "overall": "unhealthy",
                "error": str(e)
            }
