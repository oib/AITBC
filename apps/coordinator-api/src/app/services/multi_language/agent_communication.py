"""
Multi-Language Agent Communication Integration
Enhanced agent communication with translation support
"""

from dataclasses import asdict, dataclass
from datetime import datetime
from enum import Enum
from typing import Any

from aitbc import get_logger
from .language_detector import LanguageDetector
from .quality_assurance import TranslationQualityChecker
from .translation_cache import TranslationCache
from .translation_engine import TranslationEngine, TranslationRequest, TranslationResponse

logger = get_logger(__name__)


class MessageType(Enum):
    TEXT = "text"
    AGENT_TO_AGENT = "agent_to_agent"
    AGENT_TO_USER = "agent_to_user"
    USER_TO_AGENT = "user_to_agent"
    SYSTEM = "system"


@dataclass
class AgentMessage:
    """Enhanced agent message with multi-language support"""

    id: str
    sender_id: str
    receiver_id: str
    message_type: MessageType
    content: str
    original_language: str | None = None
    translated_content: str | None = None
    target_language: str | None = None
    translation_confidence: float | None = None
    translation_provider: str | None = None
    metadata: dict[str, Any] = None
    created_at: datetime = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.utcnow()
        if self.metadata is None:
            self.metadata = {}


@dataclass
class AgentLanguageProfile:
    """Agent language preferences and capabilities"""

    agent_id: str
    preferred_language: str
    supported_languages: list[str]
    auto_translate_enabled: bool
    translation_quality_threshold: float
    cultural_preferences: dict[str, Any]
    created_at: datetime = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.utcnow()
        if self.cultural_preferences is None:
            self.cultural_preferences = {}


class MultilingualAgentCommunication:
    """Enhanced agent communication with multi-language support"""

    def __init__(
        self,
        translation_engine: TranslationEngine,
        language_detector: LanguageDetector,
        translation_cache: TranslationCache | None = None,
        quality_checker: TranslationQualityChecker | None = None,
    ):
        self.translation_engine = translation_engine
        self.language_detector = language_detector
        self.translation_cache = translation_cache
        self.quality_checker = quality_checker
        self.agent_profiles: dict[str, AgentLanguageProfile] = {}
        self.message_history: list[AgentMessage] = []
        self.translation_stats = {
            "total_translations": 0,
            "successful_translations": 0,
            "failed_translations": 0,
            "cache_hits": 0,
            "cache_misses": 0,
        }

    async def register_agent_language_profile(self, profile: AgentLanguageProfile) -> bool:
        """Register agent language preferences"""
        try:
            self.agent_profiles[profile.agent_id] = profile
            logger.info(f"Registered language profile for agent {profile.agent_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to register agent language profile: {e}")
            return False

    async def get_agent_language_profile(self, agent_id: str) -> AgentLanguageProfile | None:
        """Get agent language profile"""
        return self.agent_profiles.get(agent_id)

    async def send_message(self, message: AgentMessage) -> AgentMessage:
        """Send message with automatic translation if needed"""
        try:
            # Detect source language if not provided
            if not message.original_language:
                detection_result = await self.language_detector.detect_language(message.content)
                message.original_language = detection_result.language

            # Get receiver's language preference
            receiver_profile = await self.get_agent_language_profile(message.receiver_id)

            if receiver_profile and receiver_profile.auto_translate_enabled:
                # Check if translation is needed
                if message.original_language != receiver_profile.preferred_language:
                    message.target_language = receiver_profile.preferred_language

                    # Perform translation
                    translation_result = await self._translate_message(
                        message.content, message.original_language, receiver_profile.preferred_language, message.message_type
                    )

                    if translation_result:
                        message.translated_content = translation_result.translated_text
                        message.translation_confidence = translation_result.confidence
                        message.translation_provider = translation_result.provider.value

                        # Quality check if threshold is set
                        if (
                            receiver_profile.translation_quality_threshold > 0
                            and translation_result.confidence < receiver_profile.translation_quality_threshold
                        ):
                            logger.warning(
                                f"Translation confidence {translation_result.confidence} below threshold {receiver_profile.translation_quality_threshold}"
                            )

            # Store message
            self.message_history.append(message)

            return message

        except Exception as e:
            logger.error(f"Failed to send message: {e}")
            raise

    async def _translate_message(
        self, content: str, source_lang: str, target_lang: str, message_type: MessageType
    ) -> TranslationResponse | None:
        """Translate message content with context"""
        try:
            # Add context based on message type
            context = self._get_translation_context(message_type)
            domain = self._get_translation_domain(message_type)

            # Check cache first
            if self.translation_cache:
                cached_result = await self.translation_cache.get(content, source_lang, target_lang, context, domain)
                if cached_result:
                    self.translation_stats["cache_hits"] += 1
                    return cached_result
                self.translation_stats["cache_misses"] += 1

            # Perform translation
            translation_request = TranslationRequest(
                text=content, source_language=source_lang, target_language=target_lang, context=context, domain=domain
            )

            translation_result = await self.translation_engine.translate(translation_request)

            # Cache the result
            if self.translation_cache and translation_result.confidence > 0.8:
                await self.translation_cache.set(
                    content, source_lang, target_lang, translation_result, context=context, domain=domain
                )

            self.translation_stats["total_translations"] += 1
            self.translation_stats["successful_translations"] += 1

            return translation_result

        except Exception as e:
            logger.error(f"Failed to translate message: {e}")
            self.translation_stats["failed_translations"] += 1
            return None

    def _get_translation_context(self, message_type: MessageType) -> str:
        """Get translation context based on message type"""
        contexts = {
            MessageType.TEXT: "General text communication between AI agents",
            MessageType.AGENT_TO_AGENT: "Technical communication between AI agents",
            MessageType.AGENT_TO_USER: "AI agent responding to human user",
            MessageType.USER_TO_AGENT: "Human user communicating with AI agent",
            MessageType.SYSTEM: "System notification or status message",
        }
        return contexts.get(message_type, "General communication")

    def _get_translation_domain(self, message_type: MessageType) -> str:
        """Get translation domain based on message type"""
        domains = {
            MessageType.TEXT: "general",
            MessageType.AGENT_TO_AGENT: "technical",
            MessageType.AGENT_TO_USER: "customer_service",
            MessageType.USER_TO_AGENT: "user_input",
            MessageType.SYSTEM: "system",
        }
        return domains.get(message_type, "general")

    async def translate_message_history(self, agent_id: str, target_language: str) -> list[AgentMessage]:
        """Translate agent's message history to target language"""
        try:
            agent_messages = [msg for msg in self.message_history if msg.receiver_id == agent_id or msg.sender_id == agent_id]
            translated_messages = []

            for message in agent_messages:
                if message.original_language != target_language and not message.translated_content:
                    translation_result = await self._translate_message(
                        message.content, message.original_language, target_language, message.message_type
                    )

                    if translation_result:
                        message.translated_content = translation_result.translated_text
                        message.translation_confidence = translation_result.confidence
                        message.translation_provider = translation_result.provider.value
                        message.target_language = target_language

                translated_messages.append(message)

            return translated_messages

        except Exception as e:
            logger.error(f"Failed to translate message history: {e}")
            return []

    async def get_conversation_summary(self, agent_ids: list[str], language: str | None = None) -> dict[str, Any]:
        """Get conversation summary with optional translation"""
        try:
            # Filter messages by participants
            conversation_messages = [
                msg for msg in self.message_history if msg.sender_id in agent_ids and msg.receiver_id in agent_ids
            ]

            if not conversation_messages:
                return {"summary": "No conversation found", "message_count": 0}

            # Sort by timestamp
            conversation_messages.sort(key=lambda x: x.created_at)

            # Generate summary
            summary = {
                "participants": agent_ids,
                "message_count": len(conversation_messages),
                "languages_used": list({msg.original_language for msg in conversation_messages if msg.original_language}),
                "start_time": conversation_messages[0].created_at.isoformat(),
                "end_time": conversation_messages[-1].created_at.isoformat(),
                "messages": [],
            }

            # Add messages with optional translation
            for message in conversation_messages:
                message_data = {
                    "id": message.id,
                    "sender": message.sender_id,
                    "receiver": message.receiver_id,
                    "type": message.message_type.value,
                    "timestamp": message.created_at.isoformat(),
                    "original_language": message.original_language,
                    "original_content": message.content,
                }

                # Add translated content if requested and available
                if language and message.translated_content and message.target_language == language:
                    message_data["translated_content"] = message.translated_content
                    message_data["translation_confidence"] = message.translation_confidence
                elif language and language != message.original_language and not message.translated_content:
                    # Translate on-demand
                    translation_result = await self._translate_message(
                        message.content, message.original_language, language, message.message_type
                    )

                    if translation_result:
                        message_data["translated_content"] = translation_result.translated_text
                        message_data["translation_confidence"] = translation_result.confidence

                summary["messages"].append(message_data)

            return summary

        except Exception as e:
            logger.error(f"Failed to get conversation summary: {e}")
            return {"error": str(e)}

    async def detect_language_conflicts(self, conversation: list[AgentMessage]) -> list[dict[str, Any]]:
        """Detect potential language conflicts in conversation"""
        try:
            conflicts = []
            language_changes = []

            # Track language changes
            for i, message in enumerate(conversation):
                if i > 0:
                    prev_message = conversation[i - 1]
                    if message.original_language != prev_message.original_language:
                        language_changes.append(
                            {
                                "message_id": message.id,
                                "from_language": prev_message.original_language,
                                "to_language": message.original_language,
                                "timestamp": message.created_at.isoformat(),
                            }
                        )

            # Check for translation quality issues
            for message in conversation:
                if message.translation_confidence and message.translation_confidence < 0.6:
                    conflicts.append(
                        {
                            "type": "low_translation_confidence",
                            "message_id": message.id,
                            "confidence": message.translation_confidence,
                            "recommendation": "Consider manual review or re-translation",
                        }
                    )

            # Check for unsupported languages
            supported_languages = set()
            for profile in self.agent_profiles.values():
                supported_languages.update(profile.supported_languages)

            for message in conversation:
                if message.original_language not in supported_languages:
                    conflicts.append(
                        {
                            "type": "unsupported_language",
                            "message_id": message.id,
                            "language": message.original_language,
                            "recommendation": "Add language support or use fallback translation",
                        }
                    )

            return conflicts

        except Exception as e:
            logger.error(f"Failed to detect language conflicts: {e}")
            return []

    async def optimize_agent_languages(self, agent_id: str) -> dict[str, Any]:
        """Optimize language settings for an agent based on communication patterns"""
        try:
            agent_messages = [msg for msg in self.message_history if msg.sender_id == agent_id or msg.receiver_id == agent_id]

            if not agent_messages:
                return {"recommendation": "No communication data available"}

            # Analyze language usage
            language_frequency = {}
            translation_frequency = {}

            for message in agent_messages:
                # Count original languages
                lang = message.original_language
                language_frequency[lang] = language_frequency.get(lang, 0) + 1

                # Count translations
                if message.translated_content:
                    target_lang = message.target_language
                    translation_frequency[target_lang] = translation_frequency.get(target_lang, 0) + 1

            # Get current profile
            profile = await self.get_agent_language_profile(agent_id)
            if not profile:
                return {"error": "Agent profile not found"}

            # Generate recommendations
            recommendations = []

            # Most used languages
            if language_frequency:
                most_used = max(language_frequency, key=language_frequency.get)
                if most_used != profile.preferred_language:
                    recommendations.append(
                        {
                            "type": "preferred_language",
                            "suggestion": most_used,
                            "reason": f"Most frequently used language ({language_frequency[most_used]} messages)",
                        }
                    )

            # Add missing languages to supported list
            missing_languages = set(language_frequency.keys()) - set(profile.supported_languages)
            for lang in missing_languages:
                if language_frequency[lang] > 5:  # Significant usage
                    recommendations.append(
                        {
                            "type": "add_supported_language",
                            "suggestion": lang,
                            "reason": f"Used in {language_frequency[lang]} messages",
                        }
                    )

            return {
                "current_profile": asdict(profile),
                "language_frequency": language_frequency,
                "translation_frequency": translation_frequency,
                "recommendations": recommendations,
            }

        except Exception as e:
            logger.error(f"Failed to optimize agent languages: {e}")
            return {"error": str(e)}

    async def get_translation_statistics(self) -> dict[str, Any]:
        """Get comprehensive translation statistics"""
        try:
            stats = self.translation_stats.copy()

            # Calculate success rate
            total = stats["total_translations"]
            if total > 0:
                stats["success_rate"] = stats["successful_translations"] / total
                stats["failure_rate"] = stats["failed_translations"] / total
            else:
                stats["success_rate"] = 0.0
                stats["failure_rate"] = 0.0

            # Calculate cache hit ratio
            cache_total = stats["cache_hits"] + stats["cache_misses"]
            if cache_total > 0:
                stats["cache_hit_ratio"] = stats["cache_hits"] / cache_total
            else:
                stats["cache_hit_ratio"] = 0.0

            # Agent statistics
            agent_stats = {}
            for agent_id, profile in self.agent_profiles.items():
                agent_messages = [
                    msg for msg in self.message_history if msg.sender_id == agent_id or msg.receiver_id == agent_id
                ]

                translated_count = len([msg for msg in agent_messages if msg.translated_content])

                agent_stats[agent_id] = {
                    "preferred_language": profile.preferred_language,
                    "supported_languages": profile.supported_languages,
                    "total_messages": len(agent_messages),
                    "translated_messages": translated_count,
                    "translation_rate": translated_count / len(agent_messages) if agent_messages else 0.0,
                }

            stats["agent_statistics"] = agent_stats

            return stats

        except Exception as e:
            logger.error(f"Failed to get translation statistics: {e}")
            return {"error": str(e)}

    async def health_check(self) -> dict[str, Any]:
        """Health check for multilingual agent communication"""
        try:
            health_status = {"overall": "healthy", "services": {}, "statistics": {}}

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
            health_status["overall"] = (
                "healthy" if all_healthy else "degraded" if any(health_status["services"].values()) else "unhealthy"
            )

            # Add statistics
            health_status["statistics"] = {
                "registered_agents": len(self.agent_profiles),
                "total_messages": len(self.message_history),
                "translation_stats": self.translation_stats,
            }

            return health_status

        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return {"overall": "unhealthy", "error": str(e)}
