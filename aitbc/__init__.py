"""
AITBC Package
Centralized utilities for AITBC applications.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any

from .aitbc_logging import get_logger, setup_logger
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
from .env import (
    get_bool_env_var,
    get_env_var,
    get_float_env_var,
    get_int_env_var,
    get_list_env_var,
    get_required_env_var,
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
    RequestIDMiddleware,
    PerformanceLoggingMiddleware,
    RequestValidationMiddleware,
    ErrorHandlerMiddleware,
)
from .paths import (
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

__version__ = "0.6.0"

_LAZY_EXPORTS: dict[str, tuple[str, str]] = {
    "load_json": ("json_utils", "load_json"),
    "save_json": ("json_utils", "save_json"),
    "merge_json": ("json_utils", "merge_json"),
    "json_to_string": ("json_utils", "json_to_string"),
    "string_to_json": ("json_utils", "string_to_json"),
    "get_nested_value": ("json_utils", "get_nested_value"),
    "set_nested_value": ("json_utils", "set_nested_value"),
    "flatten_json": ("json_utils", "flatten_json"),
    "AITBCHTTPClient": ("http_client", "AITBCHTTPClient"),
    "AsyncAITBCHTTPClient": ("http_client", "AsyncAITBCHTTPClient"),
    "BaseAITBCConfig": ("config", "BaseAITBCConfig"),
    "AITBCConfig": ("config", "AITBCConfig"),
    "retry": ("decorators", "retry"),
    "timing": ("decorators", "timing"),
    "cache_result": ("decorators", "cache_result"),
    "validate_args": ("decorators", "validate_args"),
    "handle_exceptions": ("decorators", "handle_exceptions"),
    "async_timing": ("decorators", "async_timing"),
    "validate_address": ("validation", "validate_address"),
    "validate_hash": ("validation", "validate_hash"),
    "validate_url": ("validation", "validate_url"),
    "validate_port": ("validation", "validate_port"),
    "validate_email": ("validation", "validate_email"),
    "validate_non_empty": ("validation", "validate_non_empty"),
    "validate_positive_number": ("validation", "validate_positive_number"),
    "validate_range": ("validation", "validate_range"),
    "validate_chain_id": ("validation", "validate_chain_id"),
    "validate_uuid": ("validation", "validate_uuid"),
    "run_sync": ("async_helpers", "run_sync"),
    "gather_with_concurrency": ("async_helpers", "gather_with_concurrency"),
    "run_with_timeout": ("async_helpers", "run_with_timeout"),
    "batch_process": ("async_helpers", "batch_process"),
    "sync_to_async": ("async_helpers", "sync_to_async"),
    "async_to_sync": ("async_helpers", "async_to_sync"),
    "retry_async": ("async_helpers", "retry_async"),
    "wait_for_condition": ("async_helpers", "wait_for_condition"),
    "DatabaseConnection": ("database", "DatabaseConnection"),
    "get_database_connection": ("database", "get_database_connection"),
    "ensure_database": ("database", "ensure_database"),
    "vacuum_database": ("database", "vacuum_database"),
    "get_table_info": ("database", "get_table_info"),
    "table_exists": ("database", "table_exists"),
    "MetricsCollector": ("monitoring", "MetricsCollector"),
    "PerformanceTimer": ("monitoring", "PerformanceTimer"),
    "HealthChecker": ("monitoring", "HealthChecker"),
    "DataLayer": ("data_layer", "DataLayer"),
    "MockDataGenerator": ("data_layer", "MockDataGenerator"),
    "RealDataFetcher": ("data_layer", "RealDataFetcher"),
    "get_data_layer": ("data_layer", "get_data_layer"),
    "derive_ethereum_address": ("crypto", "derive_ethereum_address"),
    "sign_transaction_hash": ("crypto", "sign_transaction_hash"),
    "verify_signature": ("crypto", "verify_signature"),
    "encrypt_private_key": ("crypto", "encrypt_private_key"),
    "decrypt_private_key": ("crypto", "decrypt_private_key"),
    "generate_secure_random_bytes": ("crypto", "generate_secure_random_bytes"),
    "keccak256_hash": ("crypto", "keccak256_hash"),
    "sha256_hash": ("crypto", "sha256_hash"),
    "validate_ethereum_address": ("crypto", "validate_ethereum_address"),
    "generate_ethereum_private_key": ("crypto", "generate_ethereum_private_key"),
    "Web3Client": ("web3_utils", "Web3Client"),
    "create_web3_client": ("web3_utils", "create_web3_client"),
    "generate_token": ("security", "generate_token"),
    "generate_api_key": ("security", "generate_api_key"),
    "validate_token_format": ("security", "validate_token_format"),
    "validate_api_key": ("security", "validate_api_key"),
    "SessionManager": ("security", "SessionManager"),
    "APIKeyManager": ("security", "APIKeyManager"),
    "generate_secure_random_string": ("security", "generate_secure_random_string"),
    "generate_secure_random_int": ("security", "generate_secure_random_int"),
    "SecretManager": ("security", "SecretManager"),
    "hash_password": ("security", "hash_password"),
    "verify_password": ("security", "verify_password"),
    "generate_nonce": ("security", "generate_nonce"),
    "generate_hmac": ("security", "generate_hmac"),
    "verify_hmac": ("security", "verify_hmac"),
}

for _name in (
    "get_utc_now get_timestamp_utc format_iso8601 parse_iso8601 timestamp_to_iso iso_to_timestamp "
    "format_duration format_duration_precise parse_duration add_duration subtract_duration get_time_until "
    "get_time_since calculate_deadline is_deadline_passed get_deadline_remaining format_time_ago "
    "format_time_in to_timezone get_timezone_offset is_business_hours get_start_of_day get_end_of_day "
    "get_start_of_week get_end_of_week get_start_of_month get_end_of_month sleep_until retry_until_deadline Timer"
).split():
    _LAZY_EXPORTS[_name] = ("time_utils", _name)

for _name in (
    "APIResponse PaginatedResponse success_response error_response not_found_response unauthorized_response "
    "forbidden_response validation_error_response conflict_response internal_error_response PaginationParams "
    "paginate_items build_paginated_response RateLimitHeaders build_cors_headers build_standard_headers "
    "validate_sort_field validate_sort_order build_sort_params filter_fields exclude_fields sanitize_response "
    "merge_responses get_client_ip get_user_agent build_request_metadata"
).split():
    _LAZY_EXPORTS[_name] = ("api_utils", _name)

for _name in (
    "Event EventPriority EventBus AsyncEventBus event_handler publish_event get_global_event_bus "
    "set_global_event_bus EventFilter EventAggregator EventRouter"
).split():
    _LAZY_EXPORTS[_name] = ("events", _name)

for _name in (
    "Job JobStatus JobPriority TaskQueue JobScheduler BackgroundTaskManager WorkerPool debounce throttle"
).split():
    _LAZY_EXPORTS[_name] = ("queue_manager", _name)

for _name in (
    "StateTransition StateTransitionError StatePersistenceError StateMachine ConfigurableStateMachine "
    "StatePersistence AsyncStateMachine StateMonitor StateValidator StateSnapshot"
).split():
    _LAZY_EXPORTS[_name] = ("state", _name)

for _name in (
    "MockFactory TestDataGenerator TestHelpers MockResponse MockDatabase MockCache mock_async_call "
    "create_mock_config create_test_scenario"
).split():
    _LAZY_EXPORTS[_name] = ("testing", _name)


def __getattr__(name: str) -> Any:
    if name not in _LAZY_EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attribute_name = _LAZY_EXPORTS[name]
    module = import_module(f".{module_name}", __name__)
    value = getattr(module, attribute_name)
    globals()[name] = value
    return value


__all__ = [
    "get_logger",
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
