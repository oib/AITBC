"""
Utility functions for AITBC
Provides validation, time utilities, JSON utilities, path utilities, and environment variable utilities
"""

from .validation import (
    validate_address,
    validate_hash,
    validate_url,
    validate_port,
    validate_email,
    validate_non_empty,
    validate_positive_number,
    validate_range,
    validate_chain_id,
    validate_uuid
)

from .time_utils import (
    get_utc_now,
    get_timestamp_utc,
    format_iso8601,
    parse_iso8601,
    timestamp_to_iso,
    iso_to_timestamp,
    format_duration,
    format_duration_precise,
    parse_duration,
    add_duration,
    subtract_duration,
    get_time_until,
    get_time_since,
    calculate_deadline,
    is_deadline_passed,
    get_deadline_remaining,
    format_time_ago,
    format_time_in,
    to_timezone,
    get_timezone_offset,
    is_business_hours,
    get_start_of_day,
    get_end_of_day,
    get_start_of_week,
    get_end_of_week,
    get_start_of_month,
    get_end_of_month,
    sleep_until,
    retry_until_deadline
)

from .json_utils import (
    load_json,
    save_json,
    merge_json,
    json_to_string,
    string_to_json,
    get_nested_value,
    set_nested_value,
    flatten_json
)

from .paths import (
    get_data_path,
    get_config_path,
    get_log_path,
    get_repo_path,
    ensure_dir,
    ensure_file_dir,
    resolve_path,
    get_keystore_path,
    get_blockchain_data_path,
    get_marketplace_data_path
)

from .env import (
    get_env_var,
    get_required_env_var,
    get_bool_env_var,
    get_int_env_var,
    get_float_env_var,
    get_list_env_var
)

__all__ = [
    # Validation
    'validate_address',
    'validate_hash',
    'validate_url',
    'validate_port',
    'validate_email',
    'validate_non_empty',
    'validate_positive_number',
    'validate_range',
    'validate_chain_id',
    'validate_uuid',
    # Time utils
    'get_utc_now',
    'get_timestamp_utc',
    'format_iso8601',
    'parse_iso8601',
    'timestamp_to_iso',
    'iso_to_timestamp',
    'format_duration',
    'format_duration_precise',
    'parse_duration',
    'add_duration',
    'subtract_duration',
    'get_time_until',
    'get_time_since',
    'calculate_deadline',
    'is_deadline_passed',
    'get_deadline_remaining',
    'format_time_ago',
    'format_time_in',
    'to_timezone',
    'get_timezone_offset',
    'is_business_hours',
    'get_start_of_day',
    'get_end_of_day',
    'get_start_of_week',
    'get_end_of_week',
    'get_start_of_month',
    'get_end_of_month',
    'sleep_until',
    'retry_until_deadline',
    # JSON utils
    'load_json',
    'save_json',
    'merge_json',
    'json_to_string',
    'string_to_json',
    'get_nested_value',
    'set_nested_value',
    'flatten_json',
    # Paths
    'get_data_path',
    'get_config_path',
    'get_log_path',
    'get_repo_path',
    'ensure_dir',
    'ensure_file_dir',
    'resolve_path',
    'get_keystore_path',
    'get_blockchain_data_path',
    'get_marketplace_data_path',
    # Environment
    'get_env_var',
    'get_required_env_var',
    'get_bool_env_var',
    'get_int_env_var',
    'get_float_env_var',
    'get_list_env_var'
]
