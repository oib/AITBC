"""
Tests for AITBC blue-green deployment module (blue_green_deployment.py)
This module has 0% coverage and 358 statements.
"""

import importlib.util
import time
from pathlib import Path
from unittest.mock import Mock, patch


# Load module directly by file path to avoid namespace conflicts
def load_module_from_path(module_name, file_path):
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


bg_deployment = load_module_from_path("aitbc.blue_green_deployment", Path("/opt/aitbc/aitbc/blue_green_deployment.py"))


# ============================================================================
# Deployment Status Enum Tests
# ============================================================================


class TestDeploymentStatus:
    """Test DeploymentStatus enum"""

    def test_status_values(self):
        assert bg_deployment.DeploymentStatus.PENDING.value == "pending"
        assert bg_deployment.DeploymentStatus.DEPLOYING.value == "deploying"
        assert bg_deployment.DeploymentStatus.HEALTH_CHECKING.value == "health_checking"
        assert bg_deployment.DeploymentStatus.SWITCHING_TRAFFIC.value == "switching_traffic"
        assert bg_deployment.DeploymentStatus.COMPLETED.value == "completed"
        assert bg_deployment.DeploymentStatus.FAILED.value == "failed"
        assert bg_deployment.DeploymentStatus.ROLLING_BACK.value == "rolling_back"
        assert bg_deployment.DeploymentStatus.ROLLED_BACK.value == "rolled_back"


# ============================================================================
# Deployment Config Dataclass Tests
# ============================================================================


class TestDeploymentConfig:
    """Test DeploymentConfig dataclass"""

    def test_config_initialization(self):
        config = bg_deployment.DeploymentConfig(
            environment="production",
            service_name="test-service",
            blue_version="v1.0.0",
            green_version="v2.0.0",
            health_check_url="http://localhost:8080/health",
        )
        assert config.environment == "production"
        assert config.service_name == "test-service"
        assert config.blue_version == "v1.0.0"
        assert config.green_version == "v2.0.0"
        assert config.health_check_url == "http://localhost:8080/health"
        assert config.health_check_timeout == 300
        assert config.health_check_interval == 5
        assert config.rollback_on_failure is True

    def test_config_custom_values(self):
        config = bg_deployment.DeploymentConfig(
            environment="staging",
            service_name="test-service",
            blue_version="v1.0.0",
            green_version="v2.0.0",
            health_check_url="http://localhost:8080/health",
            health_check_timeout=600,
            health_check_interval=10,
            rollback_on_failure=False,
        )
        assert config.health_check_timeout == 600
        assert config.health_check_interval == 10
        assert config.rollback_on_failure is False


# ============================================================================
# Deployment Result Dataclass Tests
# ============================================================================


class TestDeploymentResult:
    """Test DeploymentResult dataclass"""

    def test_result_initialization(self):
        result = bg_deployment.DeploymentResult(
            status=bg_deployment.DeploymentStatus.COMPLETED,
            version="v2.0.0",
            message="Deployment successful",
            start_time=time.time(),
        )
        assert result.status == bg_deployment.DeploymentStatus.COMPLETED
        assert result.version == "v2.0.0"
        assert result.message == "Deployment successful"
        assert result.end_time is None
        assert result.error is None

    def test_result_with_end_time(self):
        start = time.time()
        result = bg_deployment.DeploymentResult(
            status=bg_deployment.DeploymentStatus.COMPLETED,
            version="v2.0.0",
            message="Deployment successful",
            start_time=start,
            end_time=time.time(),
        )
        assert result.end_time is not None

    def test_result_with_error(self):
        result = bg_deployment.DeploymentResult(
            status=bg_deployment.DeploymentStatus.FAILED,
            version="v2.0.0",
            message="Deployment failed",
            start_time=time.time(),
            error="Connection error",
        )
        assert result.error == "Connection error"


# ============================================================================
# Blue Green Deployer Tests
# ============================================================================


class TestBlueGreenDeployer:
    """Test BlueGreenDeployer class"""

    def test_deployer_initialization(self):
        config = bg_deployment.DeploymentConfig(
            environment="production",
            service_name="test-service",
            blue_version="v1.0.0",
            green_version="v2.0.0",
            health_check_url="http://localhost:8080/health",
        )
        deployer = bg_deployment.BlueGreenDeployer(config)
        assert deployer.config == config
        assert deployer._current_version == "v1.0.0"
        assert deployer._new_version == "v2.0.0"
        assert deployer._deployment_history == []

    def test_get_current_version(self):
        config = bg_deployment.DeploymentConfig(
            environment="production",
            service_name="test-service",
            blue_version="v1.0.0",
            green_version="v2.0.0",
            health_check_url="http://localhost:8080/health",
        )
        deployer = bg_deployment.BlueGreenDeployer(config)
        assert deployer.get_current_version() == "v1.0.0"

    def test_get_deployment_history(self):
        config = bg_deployment.DeploymentConfig(
            environment="production",
            service_name="test-service",
            blue_version="v1.0.0",
            green_version="v2.0.0",
            health_check_url="http://localhost:8080/health",
        )
        deployer = bg_deployment.BlueGreenDeployer(config)
        history = deployer.get_deployment_history()
        assert history == []

    @patch("requests.get")
    def test_deploy_success(self, mock_get):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_get.return_value = mock_response

        config = bg_deployment.DeploymentConfig(
            environment="production",
            service_name="test-service",
            blue_version="v1.0.0",
            green_version="v2.0.0",
            health_check_url="http://localhost:8080/health",
        )
        deployer = bg_deployment.BlueGreenDeployer(config)
        result = deployer.deploy()

        assert result.status == bg_deployment.DeploymentStatus.COMPLETED
        assert result.version == "v2.0.0"
        assert result.message == "Deployment completed successfully"
        assert result.error is None
        assert deployer.get_current_version() == "v2.0.0"

    @patch("requests.get")
    def test_deploy_health_check_failure_with_rollback(self, mock_get):
        mock_get.side_effect = Exception("Connection error")

        config = bg_deployment.DeploymentConfig(
            environment="production",
            service_name="test-service",
            blue_version="v1.0.0",
            green_version="v2.0.0",
            health_check_url="http://localhost:8080/health",
            rollback_on_failure=True,
        )
        deployer = bg_deployment.BlueGreenDeployer(config)
        result = deployer.deploy()

        assert result.status == bg_deployment.DeploymentStatus.ROLLED_BACK
        assert result.version == "v1.0.0"
        assert deployer.get_current_version() == "v1.0.0"

    @patch("requests.get")
    def test_deploy_health_check_failure_no_rollback(self, mock_get):
        mock_get.side_effect = Exception("Connection error")

        config = bg_deployment.DeploymentConfig(
            environment="production",
            service_name="test-service",
            blue_version="v1.0.0",
            green_version="v2.0.0",
            health_check_url="http://localhost:8080/health",
            rollback_on_failure=False,
        )
        deployer = bg_deployment.BlueGreenDeployer(config)
        result = deployer.deploy()

        assert result.status == bg_deployment.DeploymentStatus.FAILED
        assert result.version == "v2.0.0"
        assert deployer.get_current_version() == "v1.0.0"

    @patch("requests.get")
    def test_deploy_traffic_switch_failure_with_rollback(self, mock_get):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_get.return_value = mock_response

        config = bg_deployment.DeploymentConfig(
            environment="production",
            service_name="test-service",
            blue_version="v1.0.0",
            green_version="v2.0.0",
            health_check_url="http://localhost:8080/health",
            rollback_on_failure=True,
        )
        deployer = bg_deployment.BlueGreenDeployer(config)

        # Mock _switch_traffic to fail

        def failing_switch():
            return bg_deployment.DeploymentResult(
                status=bg_deployment.DeploymentStatus.FAILED,
                version="v2.0.0",
                message="Traffic switch failed",
                start_time=time.time(),
                error="Switch error",
            )

        deployer._switch_traffic = failing_switch

        result = deployer.deploy()
        assert result.status == bg_deployment.DeploymentStatus.ROLLED_BACK

    def test_deploy_to_green(self):
        config = bg_deployment.DeploymentConfig(
            environment="production",
            service_name="test-service",
            blue_version="v1.0.0",
            green_version="v2.0.0",
            health_check_url="http://localhost:8080/health",
        )
        deployer = bg_deployment.BlueGreenDeployer(config)
        result = deployer._deploy_to_green()

        assert result.status == bg_deployment.DeploymentStatus.DEPLOYING
        assert result.version == "v2.0.0"

    @patch("requests.get")
    def test_health_check_green_success(self, mock_get):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_get.return_value = mock_response

        config = bg_deployment.DeploymentConfig(
            environment="production",
            service_name="test-service",
            blue_version="v1.0.0",
            green_version="v2.0.0",
            health_check_url="http://localhost:8080/health",
        )
        deployer = bg_deployment.BlueGreenDeployer(config)
        result = deployer._health_check_green()

        assert result.status == bg_deployment.DeploymentStatus.HEALTH_CHECKING
        assert result.message == "Health check passed"

    @patch("requests.get")
    def test_health_check_green_timeout(self, mock_get):
        import requests

        mock_get.side_effect = requests.RequestException("Connection error")

        config = bg_deployment.DeploymentConfig(
            environment="production",
            service_name="test-service",
            blue_version="v1.0.0",
            green_version="v2.0.0",
            health_check_url="http://localhost:8080/health",
            health_check_timeout=1,
            health_check_interval=0.1,
        )
        deployer = bg_deployment.BlueGreenDeployer(config)
        result = deployer._health_check_green()

        assert result.status == bg_deployment.DeploymentStatus.FAILED
        assert "timeout" in result.message.lower()

    def test_switch_traffic(self):
        config = bg_deployment.DeploymentConfig(
            environment="production",
            service_name="test-service",
            blue_version="v1.0.0",
            green_version="v2.0.0",
            health_check_url="http://localhost:8080/health",
        )
        deployer = bg_deployment.BlueGreenDeployer(config)
        result = deployer._switch_traffic()

        assert result.status == bg_deployment.DeploymentStatus.SWITCHING_TRAFFIC
        assert result.message == "Traffic switched to green"

    def test_rollback(self):
        config = bg_deployment.DeploymentConfig(
            environment="production",
            service_name="test-service",
            blue_version="v1.0.0",
            green_version="v2.0.0",
            health_check_url="http://localhost:8080/health",
        )
        deployer = bg_deployment.BlueGreenDeployer(config)
        result = deployer._rollback()

        assert result.status == bg_deployment.DeploymentStatus.ROLLED_BACK
        assert result.version == "v1.0.0"
        assert result.message == "Rollback completed"

    def test_cleanup(self):
        config = bg_deployment.DeploymentConfig(
            environment="production",
            service_name="test-service",
            blue_version="v1.0.0",
            green_version="v2.0.0",
            health_check_url="http://localhost:8080/health",
        )
        deployer = bg_deployment.BlueGreenDeployer(config)
        # Should not raise
        deployer._cleanup()

    def test_deployment_history_tracking(self):
        config = bg_deployment.DeploymentConfig(
            environment="production",
            service_name="test-service",
            blue_version="v1.0.0",
            green_version="v2.0.0",
            health_check_url="http://localhost:8080/health",
        )
        deployer = bg_deployment.BlueGreenDeployer(config)

        result = bg_deployment.DeploymentResult(
            status=bg_deployment.DeploymentStatus.COMPLETED, version="v2.0.0", message="Test", start_time=time.time()
        )
        deployer._deployment_history.append(result)

        history = deployer.get_deployment_history()
        assert len(history) == 1
        assert history[0] == result


# ============================================================================
# Canary Deployer Tests
# ============================================================================


class TestCanaryDeployer:
    """Test CanaryDeployer class"""

    def test_canary_deployer_initialization(self):
        config = bg_deployment.DeploymentConfig(
            environment="production",
            service_name="test-service",
            blue_version="v1.0.0",
            green_version="v2.0.0",
            health_check_url="http://localhost:8080/health",
        )
        deployer = bg_deployment.CanaryDeployer(config)
        assert deployer.config == config
        assert deployer.canary_percentage == 10.0
        assert deployer._current_percentage == 0.0

    def test_canary_deployer_custom_percentage(self):
        config = bg_deployment.DeploymentConfig(
            environment="production",
            service_name="test-service",
            blue_version="v1.0.0",
            green_version="v2.0.0",
            health_check_url="http://localhost:8080/health",
        )
        deployer = bg_deployment.CanaryDeployer(config, canary_percentage=25.0)
        assert deployer.canary_percentage == 25.0

    def test_deploy_canary(self):
        config = bg_deployment.DeploymentConfig(
            environment="production",
            service_name="test-service",
            blue_version="v1.0.0",
            green_version="v2.0.0",
            health_check_url="http://localhost:8080/health",
        )
        deployer = bg_deployment.CanaryDeployer(config)
        result = deployer.deploy_canary()

        assert result.status == bg_deployment.DeploymentStatus.COMPLETED
        assert result.version == "v2.0.0"
        assert result.message == "Canary deployment completed"
