"""
Feature flags utilities for AITBC
Provides feature flag management for gradual rollouts
"""

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from .aitbc_logging import get_logger

logger = get_logger(__name__)


@dataclass
class FeatureFlag:
    """Feature flag configuration"""

    name: str
    enabled: bool
    description: str
    rollout_percentage: float = 100.0
    whitelisted_users: set[str] | None = None
    blacklisted_users: set[str] | None = None
    enabled_since: datetime | None = None


class FeatureFlagManager:
    """
    Feature flag manager for gradual rollouts.
    Provides feature flag management with user whitelisting and percentage-based rollouts.
    """

    def __init__(self, config_file: Path | None = None):
        """
        Initialize feature flag manager

        Args:
            config_file: Path to feature flags configuration file
        """
        self.config_file = config_file or Path("feature_flags.json")
        self._flags: dict[str, FeatureFlag] = {}
        self._load_flags()

    def _load_flags(self) -> None:
        """Load feature flags from configuration file"""
        if not self.config_file.exists():
            logger.info("No feature flags file found at %s, using defaults", self.config_file)
            return
        try:
            with open(self.config_file) as f:
                data = json.load(f)
            for name, config in data.items():
                self._flags[name] = FeatureFlag(
                    name=name,
                    enabled=config.get("enabled", False),
                    description=config.get("description", ""),
                    rollout_percentage=config.get("rollout_percentage", 100.0),
                    whitelisted_users=set(config.get("whitelisted_users", [])),
                    blacklisted_users=set(config.get("blacklisted_users", [])),
                    enabled_since=datetime.fromisoformat(config["enabled_since"]) if config.get("enabled_since") else None,
                )
            logger.info("Loaded %s feature flags from %s", len(self._flags), self.config_file)
        except Exception as e:
            logger.error("Failed to load feature flags: %s", e)

    def save_flags(self) -> None:
        """Save feature flags to configuration file"""
        data = {}
        for name, flag in self._flags.items():
            data[name] = {
                "enabled": flag.enabled,
                "description": flag.description,
                "rollout_percentage": flag.rollout_percentage,
                "whitelisted_users": list(flag.whitelisted_users) if flag.whitelisted_users else [],
                "blacklisted_users": list(flag.blacklisted_users) if flag.blacklisted_users else [],
                "enabled_since": flag.enabled_since.isoformat() if flag.enabled_since else None,
            }
        self.config_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_file, "w") as f:
            json.dump(data, f, indent=2)
        logger.info("Saved %s feature flags to %s", len(self._flags), self.config_file)

    def is_enabled(self, feature_name: str, user_id: str | None = None, user_hash: int | None = None) -> bool:
        """
        Check if a feature is enabled for a user

        Args:
            feature_name: Name of the feature flag
            user_id: User identifier
            user_hash: Hash of user identifier for percentage-based rollout

        Returns:
            True if feature is enabled, False otherwise
        """
        flag = self._flags.get(feature_name)
        if not flag:
            logger.warning("Feature flag %s not found, defaulting to disabled", feature_name)
            return False
        if not flag.enabled:
            return False
        if flag.blacklisted_users and user_id in flag.blacklisted_users:
            return False
        if flag.whitelisted_users and user_id in flag.whitelisted_users:
            return True
        if flag.rollout_percentage < 100.0 and user_hash is not None:
            if user_hash % 100 < flag.rollout_percentage:
                return True
            return False
        return True

    def enable_feature(self, feature_name: str, rollout_percentage: float = 100.0) -> None:
        """
        Enable a feature flag

        Args:
            feature_name: Name of the feature flag
            rollout_percentage: Rollout percentage (0-100)
        """
        if feature_name not in self._flags:
            self._flags[feature_name] = FeatureFlag(
                name=feature_name,
                enabled=True,
                description="",
                rollout_percentage=rollout_percentage,
                enabled_since=datetime.now(UTC),
            )
        else:
            self._flags[feature_name].enabled = True
            self._flags[feature_name].rollout_percentage = rollout_percentage
            if not self._flags[feature_name].enabled_since:
                self._flags[feature_name].enabled_since = datetime.now(UTC)
        logger.info("Enabled feature flag %s with %s% rollout", feature_name, rollout_percentage)
        self.save_flags()

    def disable_feature(self, feature_name: str) -> None:
        """
        Disable a feature flag

        Args:
            feature_name: Name of the feature flag
        """
        if feature_name in self._flags:
            self._flags[feature_name].enabled = False
            logger.info("Disabled feature flag %s", feature_name)
            self.save_flags()

    def add_whitelisted_user(self, feature_name: str, user_id: str) -> None:
        """
        Add user to feature whitelist

        Args:
            feature_name: Name of the feature flag
            user_id: User identifier
        """
        if feature_name not in self._flags:
            self._flags[feature_name] = FeatureFlag(name=feature_name, enabled=False, description="", whitelisted_users=set())
        if not self._flags[feature_name].whitelisted_users:
            self._flags[feature_name].whitelisted_users = set()
        self._flags[feature_name].whitelisted_users.add(user_id)
        logger.info("Added %s to whitelist for %s", user_id, feature_name)
        self.save_flags()

    def add_blacklisted_user(self, feature_name: str, user_id: str) -> None:
        """
        Add user to feature blacklist

        Args:
            feature_name: Name of the feature flag
            user_id: User identifier
        """
        if feature_name not in self._flags:
            self._flags[feature_name] = FeatureFlag(name=feature_name, enabled=False, description="", blacklisted_users=set())
        if not self._flags[feature_name].blacklisted_users:
            self._flags[feature_name].blacklisted_users = set()
        self._flags[feature_name].blacklisted_users.add(user_id)
        logger.info("Added %s to blacklist for %s", user_id, feature_name)
        self.save_flags()

    def get_all_flags(self) -> dict[str, FeatureFlag]:
        """
        Get all feature flags

        Returns:
            Dictionary of all feature flags
        """
        return self._flags.copy()

    def get_flag_status(self, feature_name: str) -> FeatureFlag | None:
        """
        Get status of a specific feature flag

        Args:
            feature_name: Name of the feature flag

        Returns:
            Feature flag or None if not found
        """
        return self._flags.get(feature_name)


_global_feature_flag_manager: FeatureFlagManager | None = None


def get_feature_flag_manager(config_file: Path | None = None) -> FeatureFlagManager:
    """
    Get the global feature flag manager instance

    Args:
        config_file: Path to feature flags configuration file

    Returns:
        FeatureFlagManager instance
    """
    global _global_feature_flag_manager
    if _global_feature_flag_manager is None:
        _global_feature_flag_manager = FeatureFlagManager(config_file)
    return _global_feature_flag_manager


def is_feature_enabled(feature_name: str, user_id: str | None = None, user_hash: int | None = None) -> bool:
    """
    Check if a feature is enabled using global manager

    Args:
        feature_name: Name of the feature flag
        user_id: User identifier
        user_hash: Hash of user identifier

    Returns:
        True if feature is enabled, False otherwise
    """
    manager = get_feature_flag_manager()
    return manager.is_enabled(feature_name, user_id, user_hash)
