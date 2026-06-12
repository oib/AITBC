"""
Tests for AITBC feature flags module (feature_flags.py)
This module has 0% coverage and 278 statements.
"""

import importlib.util
import json
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory


# Load module directly by file path to avoid namespace conflicts
def load_module_from_path(module_name, file_path):
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

feature_flags = load_module_from_path(
    "aitbc.feature_flags",
    Path("/opt/aitbc/aitbc/feature_flags.py")
)


# ============================================================================
# Feature Flag Dataclass Tests
# ============================================================================

class TestFeatureFlag:
    """Test FeatureFlag dataclass"""

    def test_feature_flag_initialization(self):
        flag = feature_flags.FeatureFlag(
            name="test_feature",
            enabled=True,
            description="Test feature"
        )
        assert flag.name == "test_feature"
        assert flag.enabled is True
        assert flag.description == "Test feature"
        assert flag.rollout_percentage == 100.0
        assert flag.whitelisted_users is None
        assert flag.blacklisted_users is None
        assert flag.enabled_since is None

    def test_feature_flag_with_rollout_percentage(self):
        flag = feature_flags.FeatureFlag(
            name="test_feature",
            enabled=True,
            description="Test feature",
            rollout_percentage=50.0
        )
        assert flag.rollout_percentage == 50.0

    def test_feature_flag_with_whitelist(self):
        flag = feature_flags.FeatureFlag(
            name="test_feature",
            enabled=True,
            description="Test feature",
            whitelisted_users={"user1", "user2"}
        )
        assert flag.whitelisted_users == {"user1", "user2"}

    def test_feature_flag_with_blacklist(self):
        flag = feature_flags.FeatureFlag(
            name="test_feature",
            enabled=True,
            description="Test feature",
            blacklisted_users={"user1", "user2"}
        )
        assert flag.blacklisted_users == {"user1", "user2"}

    def test_feature_flag_with_enabled_since(self):
        ts = datetime.now()
        flag = feature_flags.FeatureFlag(
            name="test_feature",
            enabled=True,
            description="Test feature",
            enabled_since=ts
        )
        assert flag.enabled_since == ts


# ============================================================================
# Feature Flag Manager Tests
# ============================================================================

class TestFeatureFlagManager:
    """Test FeatureFlagManager class"""

    def test_manager_initialization_no_file(self):
        with TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "nonexistent.json"
            manager = feature_flags.FeatureFlagManager(config_file)
            assert manager.config_file == config_file
            assert manager._flags == {}

    def test_manager_initialization_with_file(self):
        with TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "feature_flags.json"
            data = {
                "test_feature": {
                    "enabled": True,
                    "description": "Test",
                    "rollout_percentage": 100.0,
                    "whitelisted_users": [],
                    "blacklisted_users": [],
                    "enabled_since": "2024-01-01T00:00:00"
                }
            }
            with open(config_file, 'w') as f:
                json.dump(data, f)

            manager = feature_flags.FeatureFlagManager(config_file)
            assert "test_feature" in manager._flags
            assert manager._flags["test_feature"].enabled is True

    def test_manager_initialization_invalid_json(self):
        with TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "feature_flags.json"
            with open(config_file, 'w') as f:
                f.write("invalid json")

            manager = feature_flags.FeatureFlagManager(config_file)
            # Should not raise, just log error
            assert manager._flags == {}

    def test_save_flags(self):
        with TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "feature_flags.json"
            manager = feature_flags.FeatureFlagManager(config_file)

            manager._flags["test"] = feature_flags.FeatureFlag(
                name="test",
                enabled=True,
                description="Test"
            )
            manager.save_flags()

            assert config_file.exists()
            with open(config_file) as f:
                data = json.load(f)
            assert "test" in data
            assert data["test"]["enabled"] is True

    def test_is_enabled_feature_not_found(self):
        with TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "feature_flags.json"
            manager = feature_flags.FeatureFlagManager(config_file)
            result = manager.is_enabled("nonexistent")
            assert result is False

    def test_is_enabled_globally_disabled(self):
        with TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "feature_flags.json"
            manager = feature_flags.FeatureFlagManager(config_file)
            manager._flags["test"] = feature_flags.FeatureFlag(
                name="test",
                enabled=False,
                description="Test"
            )
            result = manager.is_enabled("test")
            assert result is False

    def test_is_enabled_globally_enabled(self):
        with TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "feature_flags.json"
            manager = feature_flags.FeatureFlagManager(config_file)
            manager._flags["test"] = feature_flags.FeatureFlag(
                name="test",
                enabled=True,
                description="Test"
            )
            result = manager.is_enabled("test")
            assert result is True

    def test_is_enabled_user_blacklisted(self):
        with TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "feature_flags.json"
            manager = feature_flags.FeatureFlagManager(config_file)
            manager._flags["test"] = feature_flags.FeatureFlag(
                name="test",
                enabled=True,
                description="Test",
                blacklisted_users={"user1"}
            )
            result = manager.is_enabled("test", user_id="user1")
            assert result is False

    def test_is_enabled_user_whitelisted(self):
        with TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "feature_flags.json"
            manager = feature_flags.FeatureFlagManager(config_file)
            manager._flags["test"] = feature_flags.FeatureFlag(
                name="test",
                enabled=True,
                description="Test",
                whitelisted_users={"user1"}
            )
            result = manager.is_enabled("test", user_id="user1")
            assert result is True

    def test_is_enabled_percentage_rollout_included(self):
        with TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "feature_flags.json"
            manager = feature_flags.FeatureFlagManager(config_file)
            manager._flags["test"] = feature_flags.FeatureFlag(
                name="test",
                enabled=True,
                description="Test",
                rollout_percentage=50.0
            )
            # user_hash % 100 = 45, which is < 50
            result = manager.is_enabled("test", user_hash=45)
            assert result is True

    def test_is_enabled_percentage_rollout_excluded(self):
        with TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "feature_flags.json"
            manager = feature_flags.FeatureFlagManager(config_file)
            manager._flags["test"] = feature_flags.FeatureFlag(
                name="test",
                enabled=True,
                description="Test",
                rollout_percentage=50.0
            )
            # user_hash % 100 = 75, which is >= 50
            result = manager.is_enabled("test", user_hash=75)
            assert result is False

    def test_is_enabled_percentage_rollout_no_hash(self):
        with TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "feature_flags.json"
            manager = feature_flags.FeatureFlagManager(config_file)
            manager._flags["test"] = feature_flags.FeatureFlag(
                name="test",
                enabled=True,
                description="Test",
                rollout_percentage=50.0
            )
            # No user_hash provided, should default to enabled
            result = manager.is_enabled("test")
            assert result is True

    def test_enable_feature_new(self):
        with TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "feature_flags.json"
            manager = feature_flags.FeatureFlagManager(config_file)
            manager.enable_feature("new_feature", rollout_percentage=75.0)

            assert "new_feature" in manager._flags
            assert manager._flags["new_feature"].enabled is True
            assert manager._flags["new_feature"].rollout_percentage == 75.0
            assert manager._flags["new_feature"].enabled_since is not None

    def test_enable_feature_existing(self):
        with TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "feature_flags.json"
            manager = feature_flags.FeatureFlagManager(config_file)
            manager._flags["test"] = feature_flags.FeatureFlag(
                name="test",
                enabled=False,
                description="Test"
            )
            manager.enable_feature("test", rollout_percentage=50.0)

            assert manager._flags["test"].enabled is True
            assert manager._flags["test"].rollout_percentage == 50.0

    def test_disable_feature(self):
        with TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "feature_flags.json"
            manager = feature_flags.FeatureFlagManager(config_file)
            manager._flags["test"] = feature_flags.FeatureFlag(
                name="test",
                enabled=True,
                description="Test"
            )
            manager.disable_feature("test")

            assert manager._flags["test"].enabled is False

    def test_disable_feature_nonexistent(self):
        with TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "feature_flags.json"
            manager = feature_flags.FeatureFlagManager(config_file)
            # Should not raise
            manager.disable_feature("nonexistent")

    def test_add_whitelisted_user_new_feature(self):
        with TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "feature_flags.json"
            manager = feature_flags.FeatureFlagManager(config_file)
            manager.add_whitelisted_user("new_feature", "user1")

            assert "new_feature" in manager._flags
            assert "user1" in manager._flags["new_feature"].whitelisted_users

    def test_add_whitelisted_user_existing_feature(self):
        with TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "feature_flags.json"
            manager = feature_flags.FeatureFlagManager(config_file)
            manager._flags["test"] = feature_flags.FeatureFlag(
                name="test",
                enabled=True,
                description="Test"
            )
            manager.add_whitelisted_user("test", "user1")

            assert "user1" in manager._flags["test"].whitelisted_users

    def test_add_blacklisted_user_new_feature(self):
        with TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "feature_flags.json"
            manager = feature_flags.FeatureFlagManager(config_file)
            manager.add_blacklisted_user("new_feature", "user1")

            assert "new_feature" in manager._flags
            assert "user1" in manager._flags["new_feature"].blacklisted_users

    def test_add_blacklisted_user_existing_feature(self):
        with TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "feature_flags.json"
            manager = feature_flags.FeatureFlagManager(config_file)
            manager._flags["test"] = feature_flags.FeatureFlag(
                name="test",
                enabled=True,
                description="Test"
            )
            manager.add_blacklisted_user("test", "user1")

            assert "user1" in manager._flags["test"].blacklisted_users

    def test_get_all_flags(self):
        with TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "feature_flags.json"
            manager = feature_flags.FeatureFlagManager(config_file)
            manager._flags["test"] = feature_flags.FeatureFlag(
                name="test",
                enabled=True,
                description="Test"
            )

            flags = manager.get_all_flags()
            assert "test" in flags
            assert flags is not manager._flags  # Should be a copy

    def test_get_flag_status(self):
        with TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "feature_flags.json"
            manager = feature_flags.FeatureFlagManager(config_file)
            manager._flags["test"] = feature_flags.FeatureFlag(
                name="test",
                enabled=True,
                description="Test"
            )

            flag = manager.get_flag_status("test")
            assert flag is not None
            assert flag.name == "test"

    def test_get_flag_status_nonexistent(self):
        with TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "feature_flags.json"
            manager = feature_flags.FeatureFlagManager(config_file)

            flag = manager.get_flag_status("nonexistent")
            assert flag is None


# ============================================================================
# Global Functions Tests
# ============================================================================

class TestGlobalFunctions:
    """Test global feature flag functions"""

    def test_get_feature_flag_manager_singleton(self):
        feature_flags._global_feature_flag_manager = None
        manager1 = feature_flags.get_feature_flag_manager()
        manager2 = feature_flags.get_feature_flag_manager()
        assert manager1 is manager2

    def test_get_feature_flag_manager_with_config(self):
        feature_flags._global_feature_flag_manager = None
        with TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "feature_flags.json"
            manager = feature_flags.get_feature_flag_manager(config_file)
            assert manager.config_file == config_file

    def test_is_feature_enabled(self):
        feature_flags._global_feature_flag_manager = None
        with TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "feature_flags.json"
            manager = feature_flags.get_feature_flag_manager(config_file)
            manager._flags["test"] = feature_flags.FeatureFlag(
                name="test",
                enabled=True,
                description="Test"
            )

            result = feature_flags.is_feature_enabled("test")
            assert result is True
