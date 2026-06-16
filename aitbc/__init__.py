"""
AITBC Package
Centralized utilities for AITBC applications.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any

from ._version import __version__
from .aitbc_logging import (
    configure_logging,
    get_blockchain_logger,
    get_logger,
    setup_logger,
)
from .constants import (
    AGENT_COORDINATOR_PORT,
    BLOCKCHAIN_DATA_DIR,
    BLOCKCHAIN_P2P_PORT,
    BLOCKCHAIN_RPC_PORT,
    CONFIG_DIR,
    DATA_DIR,
    ENV_FILE,
    KEYSTORE_DIR,
    LOG_DIR,
    MARKETPLACE_DATA_DIR,
    MARKETPLACE_PORT,
    NODE_ENV_FILE,
    PACKAGE_VERSION,
    REPO_DIR,
)
from .exceptions import (
    AITBCError,
    AuthenticationError,
    BridgeError,
    CircuitBreakerOpenError,
    ConfigurationError,
    DatabaseError,
    EncryptionError,
    NetworkError,
    RateLimitError,
    RetryError,
    ValidationError,
)
from .middleware import (
    ErrorHandlerMiddleware,
    PerformanceLoggingMiddleware,
    RequestIDMiddleware,
    RequestValidationMiddleware,
)
from .utils.env import (
    get_bool_env_var,
    get_env_var,
    get_float_env_var,
    get_int_env_var,
    get_list_env_var,
    get_required_env_var,
)
from .utils.paths import (
    ensure_dir,
    ensure_file_dir,
    get_blockchain_data_path,
    get_config_path,
    get_data_path,
    get_keystore_path,
    get_log_path,
    get_marketplace_data_path,
    get_repo_path,
    resolve_path,
)

# Lazy exports for backward compatibility
_LAZY_EXPORTS: dict[str, tuple[str, str]] = {}

# JSON utils
for _name in (
    "load_json save_json merge_json json_to_string string_to_json get_nested_value set_nested_value flatten_json"
).split():
    _LAZY_EXPORTS[_name] = ("utils.json_utils", _name)

# Blockchain service
for _name in ("BlockchainService RPCBlockchainService BlockchainServiceFactory").split():
    _LAZY_EXPORTS[_name] = ("blockchain_service", _name)

# Database service
for _name in ("DatabaseService SQLiteDatabaseService DatabaseServiceFactory").split():
    _LAZY_EXPORTS[_name] = ("database_service", _name)

# HTTP client
for _name in ("AsyncAITBCHTTPClient AITBCHTTPClient Web3Client create_web3_client").split():
    _LAZY_EXPORTS[_name] = ("network", _name)

# Config
for _name in ("HierarchicalConfig ValidatedAITBCConfig").split():
    _LAZY_EXPORTS[_name] = ("config.hierarchical_config", _name)

# Decorators
for _name in ("retry timing cache_result validate_args handle_exceptions async_timing").split():
    _LAZY_EXPORTS[_name] = ("decorators", _name)

# Validation
for _name in (
    "validate_address validate_hash validate_url validate_port validate_email "
    "validate_non_empty validate_positive_number validate_range validate_chain_id validate_uuid"
).split():
    _LAZY_EXPORTS[_name] = ("utils.validation", _name)

# Time utils
for _name in (
    "run_sync gather_with_concurrency run_with_timeout batch_process sync_to_async async_to_sync "
    "retry_async wait_for_condition Timer"
).split():
    _LAZY_EXPORTS[_name] = ("async_helpers", _name)

for _name in (
    "get_utc_now get_timestamp_utc format_iso8601 parse_iso8601 timestamp_to_iso iso_to_timestamp "
    "format_duration format_duration_precise parse_duration add_duration subtract_duration get_time_until "
    "get_time_since calculate_deadline is_deadline_passed get_deadline_remaining format_time_ago "
    "format_time_in to_timezone get_timezone_offset is_business_hours get_start_of_day get_end_of_day "
    "get_start_of_week get_end_of_week get_start_of_month get_end_of_month sleep_until retry_until_deadline"
).split():
    _LAZY_EXPORTS[_name] = ("utils.time_utils", _name)

# Database connection
for _name in (
    "DatabaseConnection get_database_connection ensure_database vacuum_database get_table_info table_exists"
).split():
    _LAZY_EXPORTS[_name] = ("database", _name)

# Monitoring
for _name in ("MetricsCollector PerformanceTimer HealthChecker").split():
    _LAZY_EXPORTS[_name] = ("monitoring", _name)

# Data layer
for _name in ("DataLayer MockDataGenerator RealDataFetcher get_data_layer").split():
    _LAZY_EXPORTS[_name] = ("data_layer", _name)

# Crypto
for _name in (
    "derive_ethereum_address sign_transaction_hash verify_signature encrypt_private_key decrypt_private_key "
    "generate_secure_random_bytes keccak256_hash sha256_hash validate_ethereum_address "
    "generate_ethereum_private_key"
).split():
    _LAZY_EXPORTS[_name] = ("crypto", _name)

# Crypto Security
for _name in (
    "generate_token generate_api_key validate_token_format validate_api_key "
    "generate_secure_random_string generate_secure_random_int SecretManager "
    "hash_password verify_password generate_nonce generate_hmac verify_hmac"
).split():
    _LAZY_EXPORTS[_name] = ("crypto.security", _name)

# Events
for _name in (
    "Event EventPriority EventBus AsyncEventBus event_handler publish_event get_global_event_bus "
    "set_global_event_bus EventFilter EventAggregator EventRouter"
).split():
    _LAZY_EXPORTS[_name] = ("events", _name)

# Queue manager
for _name in ("Job JobStatus JobPriority TaskQueue JobScheduler BackgroundTaskManager WorkerPool debounce throttle").split():
    _LAZY_EXPORTS[_name] = ("queue_manager", _name)

# State
for _name in (
    "StateTransition StateTransitionError StatePersistenceError StateMachine ConfigurableStateMachine "
    "StatePersistence AsyncStateMachine StateMonitor StateValidator StateSnapshot"
).split():
    _LAZY_EXPORTS[_name] = ("state", _name)

# Testing
for _name in (
    "MockFactory TestDataGenerator TestHelpers MockResponse MockDatabase MockCache mock_async_call "
    "create_mock_config create_test_scenario"
).split():
    _LAZY_EXPORTS[_name] = ("testing", _name)

# API utils
for _name in (
    "APIResponse PaginatedResponse success_response error_response not_found_response unauthorized_response "
    "forbidden_response validation_error_response conflict_response internal_error_response PaginationParams "
    "paginate_items build_paginated_response RateLimitHeaders build_cors_headers build_standard_headers "
    "validate_sort_field validate_sort_order build_sort_params filter_fields exclude_fields sanitize_response "
    "merge_responses get_client_ip get_user_agent build_request_metadata"
).split():
    _LAZY_EXPORTS[_name] = ("api_utils", _name)


def __getattr__(name: str) -> Any:
    if name in _LAZY_EXPORTS:
        module_name, attr_name = _LAZY_EXPORTS[name]
        module = import_module(f".{module_name}", __name__)
        return getattr(module, attr_name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "get_logger",
    "get_blockchain_logger",
    "configure_logging",
    "setup_logger",
    "DATA_DIR",
    "CONFIG_DIR",
    "LOG_DIR",
    "REPO_DIR",
    "KEYSTORE_DIR",
    "BLOCKCHAIN_DATA_DIR",
    "MARKETPLACE_DATA_DIR",
    "ENV_FILE",
    "NODE_ENV_FILE",
    "BLOCKCHAIN_RPC_PORT",
    "BLOCKCHAIN_P2P_PORT",
    "AGENT_COORDINATOR_PORT",
    "MARKETPLACE_PORT",
    "PACKAGE_VERSION",
    "AITBCError",
    "ConfigurationError",
    "NetworkError",
    "AuthenticationError",
    "EncryptionError",
    "DatabaseError",
    "ValidationError",
    "BridgeError",
    "RetryError",
    "CircuitBreakerOpenError",
    "RateLimitError",
    "get_env_var",
    "get_required_env_var",
    "get_bool_env_var",
    "get_int_env_var",
    "get_float_env_var",
    "get_list_env_var",
    "get_data_path",
    "get_config_path",
    "get_log_path",
    "get_repo_path",
    "ensure_dir",
    "ensure_file_dir",
    "resolve_path",
    "get_keystore_path",
    "get_blockchain_data_path",
    "get_marketplace_data_path",
    *_LAZY_EXPORTS.keys(),
]
