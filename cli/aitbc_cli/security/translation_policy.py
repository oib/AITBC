"""
AITBC CLI Translation Security Policy

This module implements strict security controls for CLI translation functionality,
ensuring that translation services never compromise security-sensitive operations.
"""

import os
import logging
from typing import Dict, List, Optional, Union
from dataclasses import dataclass
from enum import Enum
import asyncio
from pathlib import Path

logger = logging.getLogger(__name__)


class SecurityLevel(Enum):
    """Security levels for CLI operations"""
    CRITICAL = "critical"      # Security-sensitive commands (agent strategy, wallet operations)
    HIGH = "high"             # Important operations (deployment, configuration)
    MEDIUM = "medium"         # Standard operations (monitoring, reporting)
    LOW = "low"              # Informational operations (help, status)


class TranslationMode(Enum):
    """Translation operation modes"""
    DISABLED = "disabled"      # No translation allowed
    LOCAL_ONLY = "local_only"  # Only local translation (no external APIs)
    FALLBACK = "fallback"      # External APIs with local fallback
    FULL = "full"             # Full translation capabilities


@dataclass
class SecurityPolicy:
    """Security policy for translation usage"""
    security_level: SecurityLevel
    translation_mode: TranslationMode
    allow_external_apis: bool
    require_explicit_consent: bool
    timeout_seconds: int
    max_retries: int
    cache_translations: bool


@dataclass
class TranslationRequest:
    """Translation request with security context"""
    text: str
    target_language: str
    source_language: str = "en"
    command_name: Optional[str] = None
    security_level: SecurityLevel = SecurityLevel.MEDIUM
    user_consent: bool = False


@dataclass
class TranslationResponse:
    """Translation response with security metadata"""
    translated_text: str
    success: bool
    method_used: str
    security_compliant: bool
    warning_messages: List[str]
    fallback_used: bool


class CLITranslationSecurityManager:
    """
    Security manager for CLI translation operations
    
    Enforces strict policies to ensure translation never compromises
    security-sensitive operations.
    """
    
    def __init__(self, config_path: Optional[Path] = None):
        self.config_path = config_path or Path.home() / ".aitbc" / "translation_security.json"
        self.policies = self._load_default_policies()
        self.security_log = []
        
    def _load_default_policies(self) -> Dict[SecurityLevel, SecurityPolicy]:
        """Load default security policies"""
        return {
            SecurityLevel.CRITICAL: SecurityPolicy(
                security_level=SecurityLevel.CRITICAL,
                translation_mode=TranslationMode.DISABLED,
                allow_external_apis=False,
                require_explicit_consent=True,
                timeout_seconds=0,
                max_retries=0,
                cache_translations=False
            ),
            SecurityLevel.HIGH: SecurityPolicy(
                security_level=SecurityLevel.HIGH,
                translation_mode=TranslationMode.LOCAL_ONLY,
                allow_external_apis=False,
                require_explicit_consent=True,
                timeout_seconds=5,
                max_retries=1,
                cache_translations=True
            ),
            SecurityLevel.MEDIUM: SecurityPolicy(
                security_level=SecurityLevel.MEDIUM,
                translation_mode=TranslationMode.FALLBACK,
                allow_external_apis=True,
                require_explicit_consent=False,
                timeout_seconds=10,
                max_retries=2,
                cache_translations=True
            ),
            SecurityLevel.LOW: SecurityPolicy(
                security_level=SecurityLevel.LOW,
                translation_mode=TranslationMode.FULL,
                allow_external_apis=True,
                require_explicit_consent=False,
                timeout_seconds=15,
                max_retries=3,
                cache_translations=True
            )
        }
    
    def get_command_security_level(self, command_name: str) -> SecurityLevel:
        """Determine security level for a command"""
        # Critical security-sensitive commands
        critical_commands = {
            'agent', 'strategy', 'wallet', 'sign', 'deploy', 'genesis',
            'transfer', 'send', 'approve', 'mint', 'burn', 'stake'
        }
        
        # High importance commands
        high_commands = {
            'config', 'node', 'chain', 'marketplace', 'swap', 'liquidity',
            'governance', 'vote', 'proposal'
        }
        
        # Medium importance commands
        medium_commands = {
            'balance', 'status', 'monitor', 'analytics', 'logs', 'history',
            'simulate', 'test'
        }
        
        # Low importance commands (informational)
        low_commands = {
            'help', 'version', 'info', 'list', 'show', 'explain'
        }
        
        command_base = command_name.split()[0].lower()
        
        if command_base in critical_commands:
            return SecurityLevel.CRITICAL
        elif command_base in high_commands:
            return SecurityLevel.HIGH
        elif command_base in medium_commands:
            return SecurityLevel.MEDIUM
        elif command_base in low_commands:
            return SecurityLevel.LOW
        else:
            # Default to medium for unknown commands
            return SecurityLevel.MEDIUM
    
    async def translate_with_security(self, request: TranslationRequest) -> TranslationResponse:
        """
        Translate text with security enforcement
        
        Args:
            request: Translation request with security context
            
        Returns:
            Translation response with security metadata
        """
        # Determine security level if not provided
        if request.security_level == SecurityLevel.MEDIUM and request.command_name:
            request.security_level = self.get_command_security_level(request.command_name)
        
        policy = self.policies[request.security_level]
        warnings = []
        
        # Log security check
        self._log_security_check(request, policy)
        
        # Check if translation is allowed
        if policy.translation_mode == TranslationMode.DISABLED:
            return TranslationResponse(
                translated_text=request.text,  # Return original
                success=True,
                method_used="disabled",
                security_compliant=True,
                warning_messages=["Translation disabled for security-sensitive operation"],
                fallback_used=False
            )
        
        # Check user consent for high-security operations
        if policy.require_explicit_consent and not request.user_consent:
            return TranslationResponse(
                translated_text=request.text,  # Return original
                success=True,
                method_used="consent_required",
                security_compliant=True,
                warning_messages=["User consent required for translation"],
                fallback_used=False
            )
        
        # Attempt translation based on policy
        try:
            if policy.translation_mode == TranslationMode.LOCAL_ONLY:
                result = await self._local_translate(request)
                method_used = "local"
            elif policy.translation_mode == TranslationMode.FALLBACK:
                # Try external first, fallback to local
                result, fallback_used = await self._external_translate_with_fallback(request, policy)
                method_used = "external_fallback"
            else:  # FULL
                result = await self._external_translate(request, policy)
                method_used = "external"
                fallback_used = False
            
            return TranslationResponse(
                translated_text=result,
                success=True,
                method_used=method_used,
                security_compliant=True,
                warning_messages=warnings,
                fallback_used=fallback_used if method_used == "external_fallback" else False
            )
            
        except Exception as e:
            logger.error(f"Translation failed: {e}")
            warnings.append(f"Translation failed: {str(e)}")
            
            # Always fallback to original text for security
            return TranslationResponse(
                translated_text=request.text,
                success=False,
                method_used="error_fallback",
                security_compliant=True,
                warning_messages=warnings + ["Falling back to original text for security"],
                fallback_used=True
            )
    
    async def _local_translate(self, request: TranslationRequest) -> str:
        """Local translation without external APIs"""
        # Simple local translation dictionary for common terms
        local_translations = {
            # Help messages
            "help": {"es": "ayuda", "fr": "aide", "de": "hilfe", "zh": "帮助"},
            "error": {"es": "error", "fr": "erreur", "de": "fehler", "zh": "错误"},
            "success": {"es": "éxito", "fr": "succès", "de": "erfolg", "zh": "成功"},
            "warning": {"es": "advertencia", "fr": "avertissement", "de": "warnung", "zh": "警告"},
            "status": {"es": "estado", "fr": "statut", "de": "status", "zh": "状态"},
            "balance": {"es": "saldo", "fr": "solde", "de": "guthaben", "zh": "余额"},
            "wallet": {"es": "cartera", "fr": "portefeuille", "de": "börse", "zh": "钱包"},
            "transaction": {"es": "transacción", "fr": "transaction", "de": "transaktion", "zh": "交易"},
            "blockchain": {"es": "cadena de bloques", "fr": "chaîne de blocs", "de": "blockchain", "zh": "区块链"},
            "agent": {"es": "agente", "fr": "agent", "de": "agent", "zh": "代理"},
        }
        
        # Simple word-by-word translation
        words = request.text.lower().split()
        translated_words = []
        
        for word in words:
            if word in local_translations and request.target_language in local_translations[word]:
                translated_words.append(local_translations[word][request.target_language])
            else:
                translated_words.append(word)  # Keep original if no translation
        
        return " ".join(translated_words)
    
    async def _external_translate_with_fallback(self, request: TranslationRequest, policy: SecurityPolicy) -> tuple[str, bool]:
        """External translation with local fallback"""
        try:
            # Try external translation first
            result = await self._external_translate(request, policy)
            return result, False
        except Exception as e:
            logger.warning(f"External translation failed, using local fallback: {e}")
            result = await self._local_translate(request)
            return result, True
    
    async def _external_translate(self, request: TranslationRequest, policy: SecurityPolicy) -> str:
        """External translation with timeout and retry logic"""
        if not policy.allow_external_apis:
            raise Exception("External APIs not allowed for this security level")
        
        # This would integrate with external translation services
        # For security, we'll implement a mock that demonstrates the pattern
        await asyncio.sleep(0.1)  # Simulate API call
        
        # Mock translation - in reality, this would call external APIs
        return f"[Translated to {request.target_language}: {request.text}]"
    
    def _log_security_check(self, request: TranslationRequest, policy: SecurityPolicy):
        """Log security check for audit trail"""
        log_entry = {
            "timestamp": asyncio.get_event_loop().time(),
            "command": request.command_name,
            "security_level": request.security_level.value,
            "translation_mode": policy.translation_mode.value,
            "target_language": request.target_language,
            "user_consent": request.user_consent,
            "text_length": len(request.text)
        }
        
        self.security_log.append(log_entry)
        
        # Keep only last 1000 entries
        if len(self.security_log) > 1000:
            self.security_log = self.security_log[-1000:]
    
    def get_security_summary(self) -> Dict:
        """Get summary of security checks"""
        if not self.security_log:
            return {"total_checks": 0, "message": "No security checks performed"}
        
        total_checks = len(self.security_log)
        by_level = {}
        by_language = {}
        
        for entry in self.security_log:
            level = entry["security_level"]
            lang = entry["target_language"]
            
            by_level[level] = by_level.get(level, 0) + 1
            by_language[lang] = by_language.get(lang, 0) + 1
        
        return {
            "total_checks": total_checks,
            "by_security_level": by_level,
            "by_target_language": by_language,
            "recent_checks": self.security_log[-10:]  # Last 10 checks
        }
    
    def is_translation_allowed(self, command_name: str, target_language: str) -> bool:
        """Quick check if translation is allowed for a command"""
        security_level = self.get_command_security_level(command_name)
        policy = self.policies[security_level]
        
        return policy.translation_mode != TranslationMode.DISABLED
    
    def get_security_policy_for_command(self, command_name: str) -> SecurityPolicy:
        """Get security policy for a specific command"""
        security_level = self.get_command_security_level(command_name)
        return self.policies[security_level]


# Global security manager instance
cli_translation_security = CLITranslationSecurityManager()


# Decorator for CLI commands to enforce translation security
def secure_translation(allowed_languages: Optional[List[str]] = None, require_consent: bool = False):
    """
    Decorator to enforce translation security on CLI commands
    
    Args:
        allowed_languages: List of allowed target languages
        require_consent: Whether to require explicit user consent
    """
    def decorator(func):
        async def wrapper(*args, **kwargs):
            # This would integrate with the CLI command framework
            # to enforce translation policies
            return await func(*args, **kwargs)
        return wrapper
    return decorator


# Security policy configuration functions
def configure_translation_security(
    critical_level: str = "disabled",
    high_level: str = "local_only", 
    medium_level: str = "fallback",
    low_level: str = "full"
):
    """Configure translation security policies"""
    mode_mapping = {
        "disabled": TranslationMode.DISABLED,
        "local_only": TranslationMode.LOCAL_ONLY,
        "fallback": TranslationMode.FALLBACK,
        "full": TranslationMode.FULL
    }
    
    cli_translation_security.policies[SecurityLevel.CRITICAL].translation_mode = mode_mapping[critical_level]
    cli_translation_security.policies[SecurityLevel.HIGH].translation_mode = mode_mapping[high_level]
    cli_translation_security.policies[SecurityLevel.MEDIUM].translation_mode = mode_mapping[medium_level]
    cli_translation_security.policies[SecurityLevel.LOW].translation_mode = mode_mapping[low_level]


def get_translation_security_report() -> Dict:
    """Get comprehensive translation security report"""
    return {
        "security_policies": {
            level.value: policy.translation_mode.value 
            for level, policy in cli_translation_security.policies.items()
        },
        "security_summary": cli_translation_security.get_security_summary(),
        "critical_commands": [
            cmd for cmd in ['agent', 'strategy', 'wallet', 'sign', 'deploy']
            if cli_translation_security.get_command_security_level(cmd) == SecurityLevel.CRITICAL
        ],
        "recommendations": _get_security_recommendations()
    }


def _get_security_recommendations() -> List[str]:
    """Get security recommendations"""
    recommendations = []
    
    # Check if critical commands have proper restrictions
    for cmd in ['agent', 'strategy', 'wallet', 'sign']:
        if cli_translation_security.is_translation_allowed(cmd, 'es'):
            recommendations.append(f"Consider disabling translation for '{cmd}' command")
    
    # Check for external API usage in sensitive operations
    critical_policy = cli_translation_security.policies[SecurityLevel.CRITICAL]
    if critical_policy.allow_external_apis:
        recommendations.append("External APIs should be disabled for critical operations")
    
    return recommendations
