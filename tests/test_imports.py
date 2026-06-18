"""Test imports for all 15 aitbc submodules.

This test verifies that all 15 submodules can be imported successfully
and their public exports are accessible.

This test should achieve 100% coverage for all submodule __init__.py files.
"""

import pytest


class TestSubmoduleImports:
    """Test that all aitbc submodules can be imported."""

    def test_log_utils_imports(self):
        """Test aitbc.log_utils imports."""
        from aitbc.log_utils import (
            BlockchainTextFormatter,
            StructuredFormatter,
            configure_logging,
            get_blockchain_logger,
            get_logger,
            setup_logger,
        )

        assert configure_logging is not None
        assert get_logger is not None
        assert get_blockchain_logger is not None
        assert setup_logger is not None
        assert StructuredFormatter is not None
        assert BlockchainTextFormatter is not None

    def test_middleware_imports(self):
        """Test aitbc.middleware imports."""
        from aitbc.middleware import (
            CorrelationIDMiddleware,
            ErrorHandlerMiddleware,
            PerformanceLoggingMiddleware,
            RequestIDMiddleware,
            RequestValidationMiddleware,
        )

        assert RequestIDMiddleware is not None
        assert CorrelationIDMiddleware is not None
        assert ErrorHandlerMiddleware is not None
        assert PerformanceLoggingMiddleware is not None
        assert RequestValidationMiddleware is not None

    def test_config_imports(self):
        """Test aitbc.config imports."""
        from aitbc.config import (
            AITBCConfig,
            BaseAITBCConfig,
            HierarchicalConfig,
            ValidatedAITBCConfig,
            create_config_template,
            load_config,
        )

        assert HierarchicalConfig is not None
        assert ValidatedAITBCConfig is not None
        assert BaseAITBCConfig is not None
        assert AITBCConfig is not None
        assert load_config is not None
        assert create_config_template is not None

    def test_crypto_imports(self):
        """Test aitbc.crypto imports."""
        from aitbc.crypto import (
            SecretManager,
            derive_ethereum_address,
        )

        # Just verify they're importable
        assert derive_ethereum_address is not None
        assert SecretManager is not None

    def test_database_imports(self):
        """Test aitbc.database imports."""
        from aitbc.database import (
            DatabaseConnection,
            DatabaseService,
            DatabaseServiceFactory,
        )

        assert DatabaseConnection is not None
        assert DatabaseService is not None
        assert DatabaseServiceFactory is not None

    def test_network_imports(self):
        """Test aitbc.network imports."""
        from aitbc.network import (
            AITBCHTTPClient,
            AsyncAITBCHTTPClient,
            Web3Client,
            create_web3_client,
        )

        assert AITBCHTTPClient is not None
        assert AsyncAITBCHTTPClient is not None
        assert Web3Client is not None
        assert create_web3_client is not None

    def test_utils_imports(self):
        """Test aitbc.utils imports."""
        from aitbc.utils import (
            Timer,
            ensure_dir,
            get_bool_env_var,
            load_json,
            validate_address,
        )

        # Just verify a few key imports
        assert load_json is not None
        assert validate_address is not None
        assert Timer is not None
        assert get_bool_env_var is not None
        assert ensure_dir is not None

    def test_events_imports(self):
        """Test aitbc.events imports."""
        from aitbc.events import (
            Event,
            EventBus,
        )

        assert Event is not None
        assert EventBus is not None

    def test_queues_imports(self):
        """Test aitbc.queues imports."""
        from aitbc.queues import (
            Job,
            JobStatus,
            TaskQueue,
        )

        assert Job is not None
        assert JobStatus is not None
        assert TaskQueue is not None

    def test_state_imports(self):
        """Test aitbc.state imports."""
        from aitbc.state import (
            StateMachine,
            StateTransition,
        )

        assert StateMachine is not None
        assert StateTransition is not None

    def test_testing_imports(self):
        """Test aitbc.testing imports."""
        from aitbc.testing import (
            MockFactory,
            TestDataGenerator,
        )

        assert MockFactory is not None
        assert TestDataGenerator is not None

    def test_data_layer_imports(self):
        """Test aitbc.data_layer imports."""
        from aitbc.data_layer import (
            DataLayer,
            MockDataGenerator,
            RealDataFetcher,
            get_data_layer,
        )

        assert DataLayer is not None
        assert MockDataGenerator is not None
        assert RealDataFetcher is not None
        assert get_data_layer is not None

    def test_api_imports(self):
        """Test aitbc.api imports."""
        from aitbc.api import (
            APIResponse,
            error_response,
            success_response,
        )

        assert APIResponse is not None
        assert success_response is not None
        assert error_response is not None

    def test_decorators_imports(self):
        """Test aitbc.decorators imports."""
        from aitbc.decorators import (
            retry,
            timing,
        )

        assert retry is not None
        assert timing is not None

    def test_monitoring_imports(self):
        """Test aitbc.monitoring imports."""
        from aitbc.monitoring import (
            HealthChecker,
            MetricsCollector,
            PerformanceTimer,
        )

        assert HealthChecker is not None
        assert MetricsCollector is not None
        assert PerformanceTimer is not None

    def test_oracles_imports(self):
        """Test aitbc.oracles imports."""
        from aitbc.oracles import (
            PriceOracle,
            get_price_oracle,
        )

        assert PriceOracle is not None
        assert get_price_oracle is not None

    def test_async_helpers_imports(self):
        """Test aitbc.async_helpers imports."""
        from aitbc.async_helpers import (
            async_to_sync,
            gather_with_concurrency,
            run_sync,
        )

        assert run_sync is not None
        assert gather_with_concurrency is not None
        assert async_to_sync is not None

    def test_blockchain_imports(self):
        """Test aitbc.blockchain imports."""
        from aitbc.blockchain import (
            BlockchainService,
        )

        assert BlockchainService is not None


class TestRootPackageImports:
    """Test that root package imports work correctly."""

    def test_root_imports(self):
        """Test that main aitbc package imports work."""
        from aitbc import (
            AITBCError,
            ErrorHandlerMiddleware,
            configure_logging,
            get_data_path,
            get_env_var,
        )

        # Just verify imports work
        assert configure_logging is not None
        assert AITBCError is not None
        assert ErrorHandlerMiddleware is not None
        assert get_env_var is not None
        assert get_data_path is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
