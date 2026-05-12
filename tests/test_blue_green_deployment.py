"""
Tests for blue-green deployment utilities
"""

import pytest
import time
from unittest.mock import Mock, patch, MagicMock

from aitbc.blue_green_deployment import (
    DeploymentStatus,
    DeploymentConfig,
    DeploymentResult,
    BlueGreenDeployer,
    CanaryDeployer,
)


class TestDeploymentStatus:
    """Tests for DeploymentStatus enum"""

    def test_deployment_status_values(self):
        """Test DeploymentStatus enum values"""
        assert DeploymentStatus.PENDING.value == "pending"
        assert DeploymentStatus.DEPLOYING.value == "deploying"
        assert DeploymentStatus.HEALTH_CHECKING.value == "health_checking"
        assert DeploymentStatus.SWITCHING_TRAFFIC.value == "switching_traffic"
        assert DeploymentStatus.COMPLETED.value == "completed"
        assert DeploymentStatus.FAILED.value == "failed"
        assert DeploymentStatus.ROLLING_BACK.value == "rolling_back"
        assert DeploymentStatus.ROLLED_BACK.value == "rolled_back"


class TestDeploymentConfig:
    """Tests for DeploymentConfig dataclass"""

    def test_deployment_config_creation(self):
        """Test DeploymentConfig creation"""
        config = DeploymentConfig(
            environment="production",
            service_name="aitbc-service",
            blue_version="v1.0.0",
            green_version="v2.0.0",
            health_check_url="http://localhost:8000/health"
        )
        assert config.environment == "production"
        assert config.service_name == "aitbc-service"
        assert config.blue_version == "v1.0.0"
        assert config.green_version == "v2.0.0"

    def test_deployment_config_defaults(self):
        """Test DeploymentConfig with default values"""
        config = DeploymentConfig(
            environment="production",
            service_name="service",
            blue_version="v1.0",
            green_version="v2.0",
            health_check_url="http://localhost/health"
        )
        assert config.health_check_timeout == 300
        assert config.health_check_interval == 5
        assert config.rollback_on_failure is True


class TestDeploymentResult:
    """Tests for DeploymentResult dataclass"""

    def test_deployment_result_creation(self):
        """Test DeploymentResult creation"""
        result = DeploymentResult(
            status=DeploymentStatus.COMPLETED,
            version="v2.0.0",
            message="Success",
            start_time=1234567890.0,
            end_time=1234567900.0
        )
        assert result.status == DeploymentStatus.COMPLETED
        assert result.version == "v2.0.0"
        assert result.message == "Success"

    def test_deployment_result_optional_fields(self):
        """Test DeploymentResult with optional fields"""
        result = DeploymentResult(
            status=DeploymentStatus.FAILED,
            version="v2.0.0",
            message="Failed",
            start_time=1234567890.0
        )
        assert result.end_time is None
        assert result.error is None


class TestBlueGreenDeployer:
    """Tests for BlueGreenDeployer"""

    def test_initialization(self):
        """Test BlueGreenDeployer initialization"""
        config = DeploymentConfig(
            environment="production",
            service_name="service",
            blue_version="v1.0",
            green_version="v2.0",
            health_check_url="http://localhost/health"
        )
        deployer = BlueGreenDeployer(config)
        
        assert deployer.config == config
        assert deployer._current_version == "v1.0"
        assert deployer._new_version == "v2.0"
        assert deployer._deployment_history == []

    @patch('aitbc.blue_green_deployment.time.sleep')
    @patch('aitbc.blue_green_deployment.requests.get')
    @patch('aitbc.blue_green_deployment.logger')
    def test_deploy_success(self, mock_logger, mock_get, mock_sleep):
        """Test successful deployment"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_get.return_value = mock_response
        
        config = DeploymentConfig(
            environment="production",
            service_name="service",
            blue_version="v1.0",
            green_version="v2.0",
            health_check_url="http://localhost/health",
            health_check_timeout=10,
            health_check_interval=1
        )
        deployer = BlueGreenDeployer(config)
        
        result = deployer.deploy()
        
        assert result.status == DeploymentStatus.COMPLETED
        assert result.version == "v2.0"
        assert deployer._current_version == "v2.0"
        assert len(deployer._deployment_history) == 1

    @patch('aitbc.blue_green_deployment.time.sleep')
    @patch('aitbc.blue_green_deployment.requests.get')
    @patch('aitbc.blue_green_deployment.logger')
    def test_deploy_health_check_failure_with_rollback(self, mock_logger, mock_get, mock_sleep):
        """Test deployment rollback on health check failure"""
        mock_get.side_effect = Exception("Health check failed")
        
        config = DeploymentConfig(
            environment="production",
            service_name="service",
            blue_version="v1.0",
            green_version="v2.0",
            health_check_url="http://localhost/health",
            health_check_timeout=10,
            health_check_interval=1,
            rollback_on_failure=True
        )
        deployer = BlueGreenDeployer(config)
        
        result = deployer.deploy()
        
        assert result.status == DeploymentStatus.ROLLED_BACK
        assert result.version == "v1.0"

    @patch('aitbc.blue_green_deployment.time.sleep')
    @patch('aitbc.blue_green_deployment.requests.get')
    @patch('aitbc.blue_green_deployment.logger')
    def test_deploy_health_check_failure_no_rollback(self, mock_logger, mock_get, mock_sleep):
        """Test deployment without rollback on health check failure"""
        mock_get.side_effect = Exception("Health check failed")
        
        config = DeploymentConfig(
            environment="production",
            service_name="service",
            blue_version="v1.0",
            green_version="v2.0",
            health_check_url="http://localhost/health",
            health_check_timeout=10,
            health_check_interval=1,
            rollback_on_failure=False
        )
        deployer = BlueGreenDeployer(config)
        
        result = deployer.deploy()
        
        assert result.status == DeploymentStatus.FAILED
        assert result.version == "v2.0"

    @patch('aitbc.blue_green_deployment.time.sleep')
    @patch('aitbc.blue_green_deployment.requests.get')
    @patch('aitbc.blue_green_deployment.logger')
    def test_deploy_exception_with_rollback(self, mock_logger, mock_get, mock_sleep):
        """Test deployment exception in _deploy_to_green returns FAILED"""
        mock_sleep.side_effect = Exception("Deployment error")
        
        config = DeploymentConfig(
            environment="production",
            service_name="service",
            blue_version="v1.0",
            green_version="v2.0",
            health_check_url="http://localhost/health",
            rollback_on_failure=True
        )
        deployer = BlueGreenDeployer(config)
        
        result = deployer.deploy()
        
        # Exception in _deploy_to_green is caught and returns FAILED, no rollback
        assert result.status == DeploymentStatus.FAILED
        assert result.error is not None

    @patch('aitbc.blue_green_deployment.time.sleep')
    @patch('aitbc.blue_green_deployment.logger')
    def test_deploy_to_green_success(self, mock_logger, mock_sleep):
        """Test _deploy_to_green success"""
        config = DeploymentConfig(
            environment="production",
            service_name="service",
            blue_version="v1.0",
            green_version="v2.0",
            health_check_url="http://localhost/health"
        )
        deployer = BlueGreenDeployer(config)
        
        result = deployer._deploy_to_green()
        
        assert result.status == DeploymentStatus.DEPLOYING
        assert result.version == "v2.0"

    @patch('aitbc.blue_green_deployment.time.sleep')
    @patch('aitbc.blue_green_deployment.logger')
    def test_deploy_to_green_failure(self, mock_logger, mock_sleep):
        """Test _deploy_to_green failure"""
        mock_sleep.side_effect = Exception("Deploy failed")
        
        config = DeploymentConfig(
            environment="production",
            service_name="service",
            blue_version="v1.0",
            green_version="v2.0",
            health_check_url="http://localhost/health"
        )
        deployer = BlueGreenDeployer(config)
        
        result = deployer._deploy_to_green()
        
        assert result.status == DeploymentStatus.FAILED
        assert result.error is not None

    @patch('aitbc.blue_green_deployment.time.sleep')
    @patch('aitbc.blue_green_deployment.requests.get')
    @patch('aitbc.blue_green_deployment.logger')
    def test_health_check_green_success(self, mock_logger, mock_get, mock_sleep):
        """Test _health_check_green success"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_get.return_value = mock_response
        
        config = DeploymentConfig(
            environment="production",
            service_name="service",
            blue_version="v1.0",
            green_version="v2.0",
            health_check_url="http://localhost/health",
            health_check_timeout=10,
            health_check_interval=1
        )
        deployer = BlueGreenDeployer(config)
        
        result = deployer._health_check_green()
        
        assert result.status == DeploymentStatus.HEALTH_CHECKING
        assert result.message == "Health check passed"

    @patch('aitbc.blue_green_deployment.time.sleep')
    @patch('aitbc.blue_green_deployment.requests.get')
    @patch('aitbc.blue_green_deployment.logger')
    def test_health_check_green_timeout(self, mock_logger, mock_get, mock_sleep):
        """Test _health_check_green timeout"""
        mock_response = Mock()
        mock_response.status_code = 500  # Non-200 status
        mock_get.return_value = mock_response
        
        config = DeploymentConfig(
            environment="production",
            service_name="service",
            blue_version="v1.0",
            green_version="v2.0",
            health_check_url="http://localhost/health",
            health_check_timeout=2,
            health_check_interval=1
        )
        deployer = BlueGreenDeployer(config)
        
        result = deployer._health_check_green()
        
        assert result.status == DeploymentStatus.FAILED
        assert "timeout" in result.message.lower()

    @patch('aitbc.blue_green_deployment.time.sleep')
    @patch('aitbc.blue_green_deployment.logger')
    def test_switch_traffic_success(self, mock_logger, mock_sleep):
        """Test _switch_traffic success"""
        config = DeploymentConfig(
            environment="production",
            service_name="service",
            blue_version="v1.0",
            green_version="v2.0",
            health_check_url="http://localhost/health"
        )
        deployer = BlueGreenDeployer(config)
        
        result = deployer._switch_traffic()
        
        assert result.status == DeploymentStatus.SWITCHING_TRAFFIC
        assert result.message == "Traffic switched to green"

    @patch('aitbc.blue_green_deployment.time.sleep')
    @patch('aitbc.blue_green_deployment.logger')
    def test_switch_traffic_failure(self, mock_logger, mock_sleep):
        """Test _switch_traffic failure"""
        mock_sleep.side_effect = Exception("Switch failed")
        
        config = DeploymentConfig(
            environment="production",
            service_name="service",
            blue_version="v1.0",
            green_version="v2.0",
            health_check_url="http://localhost/health"
        )
        deployer = BlueGreenDeployer(config)
        
        result = deployer._switch_traffic()
        
        assert result.status == DeploymentStatus.FAILED
        assert result.error is not None

    @patch('aitbc.blue_green_deployment.time.sleep')
    @patch('aitbc.blue_green_deployment.logger')
    def test_rollback_success(self, mock_logger, mock_sleep):
        """Test _rollback success"""
        config = DeploymentConfig(
            environment="production",
            service_name="service",
            blue_version="v1.0",
            green_version="v2.0",
            health_check_url="http://localhost/health"
        )
        deployer = BlueGreenDeployer(config)
        
        result = deployer._rollback()
        
        assert result.status == DeploymentStatus.ROLLED_BACK
        assert result.version == "v1.0"

    @patch('aitbc.blue_green_deployment.time.sleep')
    @patch('aitbc.blue_green_deployment.logger')
    def test_rollback_failure(self, mock_logger, mock_sleep):
        """Test _rollback failure"""
        mock_sleep.side_effect = Exception("Rollback failed")
        
        config = DeploymentConfig(
            environment="production",
            service_name="service",
            blue_version="v1.0",
            green_version="v2.0",
            health_check_url="http://localhost/health"
        )
        deployer = BlueGreenDeployer(config)
        
        result = deployer._rollback()
        
        assert result.status == DeploymentStatus.FAILED

    @patch('aitbc.blue_green_deployment.logger')
    def test_cleanup(self, mock_logger):
        """Test _cleanup method"""
        config = DeploymentConfig(
            environment="production",
            service_name="service",
            blue_version="v1.0",
            green_version="v2.0",
            health_check_url="http://localhost/health"
        )
        deployer = BlueGreenDeployer(config)
        
        deployer._cleanup()
        
        # Should not raise any exception
        assert True

    def test_get_deployment_history(self):
        """Test get_deployment_history"""
        config = DeploymentConfig(
            environment="production",
            service_name="service",
            blue_version="v1.0",
            green_version="v2.0",
            health_check_url="http://localhost/health"
        )
        deployer = BlueGreenDeployer(config)
        
        result = DeploymentResult(
            status=DeploymentStatus.COMPLETED,
            version="v2.0",
            message="Success",
            start_time=time.time()
        )
        deployer._deployment_history.append(result)
        
        history = deployer.get_deployment_history()
        
        assert len(history) == 1
        assert history[0] == result

    def test_get_current_version(self):
        """Test get_current_version"""
        config = DeploymentConfig(
            environment="production",
            service_name="service",
            blue_version="v1.0",
            green_version="v2.0",
            health_check_url="http://localhost/health"
        )
        deployer = BlueGreenDeployer(config)
        
        version = deployer.get_current_version()
        
        assert version == "v1.0"


class TestCanaryDeployer:
    """Tests for CanaryDeployer"""

    def test_initialization(self):
        """Test CanaryDeployer initialization"""
        config = DeploymentConfig(
            environment="production",
            service_name="service",
            blue_version="v1.0",
            green_version="v2.0",
            health_check_url="http://localhost/health"
        )
        deployer = CanaryDeployer(config, canary_percentage=20.0)
        
        assert deployer.config == config
        assert deployer.canary_percentage == 20.0
        assert deployer._current_percentage == 0.0

    def test_initialization_default_percentage(self):
        """Test CanaryDeployer with default canary percentage"""
        config = DeploymentConfig(
            environment="production",
            service_name="service",
            blue_version="v1.0",
            green_version="v2.0",
            health_check_url="http://localhost/health"
        )
        deployer = CanaryDeployer(config)
        
        assert deployer.canary_percentage == 10.0

    @patch('aitbc.blue_green_deployment.logger')
    def test_deploy_canary(self, mock_logger):
        """Test deploy_canary method"""
        config = DeploymentConfig(
            environment="production",
            service_name="service",
            blue_version="v1.0",
            green_version="v2.0",
            health_check_url="http://localhost/health"
        )
        deployer = CanaryDeployer(config, canary_percentage=15.0)
        
        result = deployer.deploy_canary()
        
        assert result.status == DeploymentStatus.COMPLETED
        assert result.version == "v2.0"
        assert result.message == "Canary deployment completed"
