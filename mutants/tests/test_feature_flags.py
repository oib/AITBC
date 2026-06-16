"""
Tests for feature flags utilities
"""

import json
from datetime import datetime
from unittest.mock import patch

from aitbc.feature_flags import (
    FeatureFlag,
    FeatureFlagManager,
    get_feature_flag_manager,
    is_feature_enabled,
)


class TestFeatureFlag:
    """Tests for FeatureFlag dataclass"""

    def test_feature_flag_creation(self):
        """Test FeatureFlag dataclass creation"""
        flag = FeatureFlag(name="test_feature", enabled=True, description="Test feature", rollout_percentage=50.0)
        assert flag.name == "test_feature"
        assert flag.enabled is True
        assert flag.description == "Test feature"
        assert flag.rollout_percentage == 50.0

    def test_feature_flag_with_whitelist(self):
        """Test FeatureFlag with whitelisted users"""
        flag = FeatureFlag(name="test_feature", enabled=True, description="Test feature", whitelisted_users={"user1", "user2"})
        assert flag.whitelisted_users == {"user1", "user2"}

    def test_feature_flag_with_blacklist(self):
        """Test FeatureFlag with blacklisted users"""
        flag = FeatureFlag(name="test_feature", enabled=True, description="Test feature", blacklisted_users={"user3"})
        assert flag.blacklisted_users == {"user3"}

    def test_feature_flag_with_enabled_since(self):
        """Test FeatureFlag with enabled_since timestamp"""
        now = datetime.now()
        flag = FeatureFlag(name="test_feature", enabled=True, description="Test feature", enabled_since=now)
        assert flag.enabled_since == now


class TestFeatureFlagManager:
    """Tests for FeatureFlagManager"""

    def test_initialization_without_config_file(self, tmp_path):
        """Test initialization without config file"""
        manager = FeatureFlagManager(config_file=tmp_path / "nonexistent.json")
        assert manager._flags == {}
        assert manager.config_file == tmp_path / "nonexistent.json"

    @patch("aitbc.feature_flags.logger")
    def test_load_flags_from_file(self, mock_logger, tmp_path):
        """Test loading flags from configuration file"""
        config_file = tmp_path / "feature_flags.json"
        config_data = {
            "test_feature": {
                "enabled": True,
                "description": "Test feature",
                "rollout_percentage": 50.0,
                "whitelisted_users": ["user1"],
                "blacklisted_users": ["user2"],
                "enabled_since": "2024-01-01T00:00:00",
            }
        }
        config_file.write_text(json.dumps(config_data))

        manager = FeatureFlagManager(config_file=config_file)

        assert "test_feature" in manager._flags
        assert manager._flags["test_feature"].enabled is True
        assert manager._flags["test_feature"].description == "Test feature"
        assert manager._flags["test_feature"].rollout_percentage == 50.0
        mock_logger.info.assert_called_once()

    @patch("aitbc.feature_flags.logger")
    def test_load_flags_file_not_found(self, mock_logger, tmp_path):
        """Test loading flags when file doesn't exist"""
        FeatureFlagManager(config_file=tmp_path / "nonexistent.json")
        mock_logger.info.assert_called_once()
        assert "No feature flags file found" in mock_logger.info.call_args[0][0]

    @patch("aitbc.feature_flags.logger")
    def test_load_flags_invalid_json(self, mock_logger, tmp_path):
        """Test loading flags with invalid JSON"""
        config_file = tmp_path / "feature_flags.json"
        config_file.write_text("invalid json")

        FeatureFlagManager(config_file=config_file)
        mock_logger.error.assert_called_once()
        assert "Failed to load feature flags" in mock_logger.error.call_args[0][0]

    @patch("aitbc.feature_flags.logger")
    def test_save_flags(self, mock_logger, tmp_path):
        """Test saving flags to configuration file"""
        config_file = tmp_path / "feature_flags.json"
        manager = FeatureFlagManager(config_file=config_file)

        manager._flags["test_feature"] = FeatureFlag(name="test_feature", enabled=True, description="Test feature")

        manager.save_flags()

        assert config_file.exists()
        with open(config_file) as f:
            data = json.load(f)
        assert "test_feature" in data
        assert data["test_feature"]["enabled"] is True
        # Check that save was logged (may have other log calls from initialization)
        assert any("Saved" in str(call) for call in mock_logger.info.call_args_list)

    @patch("aitbc.feature_flags.logger")
    def test_is_enabled_flag_not_found(self, mock_logger):
        """Test is_enabled when flag not found"""
        manager = FeatureFlagManager()
        result = manager.is_enabled("nonexistent_feature")
        assert result is False
        mock_logger.warning.assert_called_once()

    def test_is_enabled_globally_disabled(self):
        """Test is_enabled when flag is globally disabled"""
        manager = FeatureFlagManager()
        manager._flags["test_feature"] = FeatureFlag(name="test_feature", enabled=False, description="Test feature")
        result = manager.is_enabled("test_feature")
        assert result is False

    def test_is_enabled_globally_enabled(self):
        """Test is_enabled when flag is globally enabled"""
        manager = FeatureFlagManager()
        manager._flags["test_feature"] = FeatureFlag(name="test_feature", enabled=True, description="Test feature")
        result = manager.is_enabled("test_feature")
        assert result is True

    def test_is_enabled_user_blacklisted(self):
        """Test is_enabled when user is blacklisted"""
        manager = FeatureFlagManager()
        manager._flags["test_feature"] = FeatureFlag(
            name="test_feature", enabled=True, description="Test feature", blacklisted_users={"user1"}
        )
        result = manager.is_enabled("test_feature", user_id="user1")
        assert result is False

    def test_is_enabled_user_whitelisted(self):
        """Test is_enabled when user is whitelisted"""
        manager = FeatureFlagManager()
        manager._flags["test_feature"] = FeatureFlag(
            name="test_feature", enabled=True, description="Test feature", whitelisted_users={"user1"}
        )
        result = manager.is_enabled("test_feature", user_id="user1")
        assert result is True

    def test_is_enabled_percentage_rollout_included(self):
        """Test is_enabled with percentage-based rollout - user included"""
        manager = FeatureFlagManager()
        manager._flags["test_feature"] = FeatureFlag(
            name="test_feature", enabled=True, description="Test feature", rollout_percentage=50.0
        )
        result = manager.is_enabled("test_feature", user_hash=25)
        assert result is True  # 25 % 100 = 25 < 50

    def test_is_enabled_percentage_rollout_excluded(self):
        """Test is_enabled with percentage-based rollout - user excluded"""
        manager = FeatureFlagManager()
        manager._flags["test_feature"] = FeatureFlag(
            name="test_feature", enabled=True, description="Test feature", rollout_percentage=50.0
        )
        result = manager.is_enabled("test_feature", user_hash=75)
        assert result is False  # 75 % 100 = 75 >= 50

    @patch("aitbc.feature_flags.logger")
    def test_enable_feature_new_flag(self, mock_logger, tmp_path):
        """Test enable_feature for new flag"""
        config_file = tmp_path / "feature_flags.json"
        manager = FeatureFlagManager(config_file=config_file)

        manager.enable_feature("new_feature", rollout_percentage=75.0)

        assert "new_feature" in manager._flags
        assert manager._flags["new_feature"].enabled is True
        assert manager._flags["new_feature"].rollout_percentage == 75.0
        assert manager._flags["new_feature"].enabled_since is not None
        # Check that enable was logged
        assert any("Enabled" in str(call) for call in mock_logger.info.call_args_list)

    @patch("aitbc.feature_flags.logger")
    def test_enable_feature_existing_flag(self, mock_logger, tmp_path):
        """Test enable_feature for existing flag"""
        config_file = tmp_path / "feature_flags.json"
        manager = FeatureFlagManager(config_file=config_file)
        manager._flags["existing_feature"] = FeatureFlag(
            name="existing_feature", enabled=False, description="Existing feature"
        )

        manager.enable_feature("existing_feature", rollout_percentage=50.0)

        assert manager._flags["existing_feature"].enabled is True
        assert manager._flags["existing_feature"].rollout_percentage == 50.0
        # Check that enable was logged
        assert any("Enabled" in str(call) for call in mock_logger.info.call_args_list)

    @patch("aitbc.feature_flags.logger")
    def test_disable_feature(self, mock_logger, tmp_path):
        """Test disable_feature"""
        config_file = tmp_path / "feature_flags.json"
        manager = FeatureFlagManager(config_file=config_file)
        manager._flags["test_feature"] = FeatureFlag(name="test_feature", enabled=True, description="Test feature")

        manager.disable_feature("test_feature")

        assert manager._flags["test_feature"].enabled is False
        # Check that disable was logged
        assert any("Disabled" in str(call) for call in mock_logger.info.call_args_list)

    @patch("aitbc.feature_flags.logger")
    def test_add_whitelisted_user_new_flag(self, mock_logger, tmp_path):
        """Test add_whitelisted_user for new flag"""
        config_file = tmp_path / "feature_flags.json"
        manager = FeatureFlagManager(config_file=config_file)

        manager.add_whitelisted_user("new_feature", "user1")

        assert "new_feature" in manager._flags
        assert "user1" in manager._flags["new_feature"].whitelisted_users
        # Check that add was logged
        assert any("whitelist" in str(call) for call in mock_logger.info.call_args_list)

    @patch("aitbc.feature_flags.logger")
    def test_add_whitelisted_user_existing_flag(self, mock_logger, tmp_path):
        """Test add_whitelisted_user for existing flag"""
        config_file = tmp_path / "feature_flags.json"
        manager = FeatureFlagManager(config_file=config_file)
        manager._flags["test_feature"] = FeatureFlag(
            name="test_feature", enabled=True, description="Test feature", whitelisted_users=set()
        )

        manager.add_whitelisted_user("test_feature", "user1")

        assert "user1" in manager._flags["test_feature"].whitelisted_users
        # Check that add was logged
        assert any("whitelist" in str(call) for call in mock_logger.info.call_args_list)

    @patch("aitbc.feature_flags.logger")
    def test_add_blacklisted_user_new_flag(self, mock_logger, tmp_path):
        """Test add_blacklisted_user for new flag"""
        config_file = tmp_path / "feature_flags.json"
        manager = FeatureFlagManager(config_file=config_file)

        manager.add_blacklisted_user("new_feature", "user1")

        assert "new_feature" in manager._flags
        assert "user1" in manager._flags["new_feature"].blacklisted_users
        # Check that add was logged
        assert any("blacklist" in str(call) for call in mock_logger.info.call_args_list)

    @patch("aitbc.feature_flags.logger")
    def test_add_blacklisted_user_existing_flag(self, mock_logger, tmp_path):
        """Test add_blacklisted_user for existing flag"""
        config_file = tmp_path / "feature_flags.json"
        manager = FeatureFlagManager(config_file=config_file)
        manager._flags["test_feature"] = FeatureFlag(
            name="test_feature", enabled=True, description="Test feature", blacklisted_users=set()
        )

        manager.add_blacklisted_user("test_feature", "user1")

        assert "user1" in manager._flags["test_feature"].blacklisted_users
        # Check that add was logged
        assert any("blacklist" in str(call) for call in mock_logger.info.call_args_list)

    def test_get_all_flags(self):
        """Test get_all_flags"""
        manager = FeatureFlagManager()
        manager._flags.clear()
        manager._flags["feature1"] = FeatureFlag(name="feature1", enabled=True, description="Feature 1")
        manager._flags["feature2"] = FeatureFlag(name="feature2", enabled=False, description="Feature 2")

        flags = manager.get_all_flags()

        assert len(flags) == 2
        assert "feature1" in flags
        assert "feature2" in flags

    def test_get_flag_status_found(self):
        """Test get_flag_status when flag exists"""
        manager = FeatureFlagManager()
        flag = FeatureFlag(name="test_feature", enabled=True, description="Test feature")
        manager._flags["test_feature"] = flag

        result = manager.get_flag_status("test_feature")

        assert result == flag

    def test_get_flag_status_not_found(self):
        """Test get_flag_status when flag doesn't exist"""
        manager = FeatureFlagManager()

        result = manager.get_flag_status("nonexistent_feature")

        assert result is None


class TestGlobalFunctions:
    """Tests for global feature flag functions"""

    def test_get_feature_flag_manager_singleton(self):
        """Test get_feature_flag_manager returns singleton"""
        manager1 = get_feature_flag_manager()
        manager2 = get_feature_flag_manager()

        assert manager1 is manager2

    def test_get_feature_flag_manager_with_config(self, tmp_path):
        """Test get_feature_flag_manager with custom config"""
        # Reset global manager first
        import aitbc.feature_flags as ff_module

        ff_module._global_feature_flag_manager = None

        manager = get_feature_flag_manager(config_file=tmp_path / "custom.json")

        assert manager.config_file == tmp_path / "custom.json"

    def test_is_feature_enabled_global(self):
        """Test is_feature_enabled global function"""
        manager = get_feature_flag_manager()
        manager._flags["test_feature"] = FeatureFlag(name="test_feature", enabled=True, description="Test feature")

        result = is_feature_enabled("test_feature")

        assert result is True
