"""
Agent Metadata Module
Handles metadata validation, storage, and management
"""

import logging
from typing import ClassVar

logger = logging.getLogger(__name__)


def log_error(msg: str):
    logger.error(msg)


class MetadataValidator:
    """Validator for agent metadata"""

    # Valid metadata keys and their types
    VALID_METADATA_KEYS: ClassVar[dict[str, type]] = {
        "location": str,
        "region": str,
        "country": str,
        "hardware_specs": dict,
        "gpu_type": str,
        "gpu_count": int,
        "memory_gb": int,
        "storage_gb": int,
        "network_bandwidth_mbps": int,
        "latency_ms": int,
        "uptime_percentage": float,
        "supported_frameworks": list,
        "model_types": list,
        "max_batch_size": int,
        "specializations": list,
        "certifications": list,
        "compliance_level": str,
        "data_privacy_level": str,
        "sla_guarantee": str,
    }

    @staticmethod
    def validate_metadata(metadata: dict) -> tuple[bool, str]:
        """
        Validate agent metadata

        Args:
            metadata: Metadata dictionary to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        if not metadata:
            return True, "No metadata provided"

        # Check for unknown keys
        unknown_keys = set(metadata.keys()) - set(MetadataValidator.VALID_METADATA_KEYS.keys())
        if unknown_keys:
            log_error(f"Unknown metadata keys: {unknown_keys}")
            return False, f"Unknown metadata keys: {unknown_keys}"

        # Validate each key's type
        for key, value in metadata.items():
            expected_type = MetadataValidator.VALID_METADATA_KEYS.get(key)
            if expected_type and not isinstance(value, expected_type):
                return False, f"Invalid type for {key}: expected {expected_type.__name__}, got {type(value).__name__}"

        # Validate specific fields
        if "uptime_percentage" in metadata and not 0 <= metadata["uptime_percentage"] <= 100:
            return False, "uptime_percentage must be between 0 and 100"

        if "latency_ms" in metadata and metadata["latency_ms"] < 0:
            return False, "latency_ms must be non-negative"

        if "gpu_count" in metadata and metadata["gpu_count"] < 0:
            return False, "gpu_count must be non-negative"

        if "memory_gb" in metadata and metadata["memory_gb"] < 0:
            return False, "memory_gb must be non-negative"

        return True, "Metadata is valid"

    @staticmethod
    def sanitize_metadata(metadata: dict) -> dict:
        """
        Sanitize metadata by removing invalid keys and converting types

        Args:
            metadata: Metadata dictionary to sanitize

        Returns:
            Sanitized metadata dictionary
        """
        if not metadata:
            return {}

        # Remove unknown keys
        sanitized = {k: v for k, v in metadata.items() if k in MetadataValidator.VALID_METADATA_KEYS}

        # Convert types where possible
        for key, value in sanitized.items():
            expected_type = MetadataValidator.VALID_METADATA_KEYS[key]
            if not isinstance(value, expected_type):
                try:
                    if expected_type is int:
                        sanitized[key] = int(value)
                    elif expected_type is float:
                        sanitized[key] = float(value)
                    elif expected_type is str:
                        sanitized[key] = str(value)
                    elif expected_type is list:
                        if isinstance(value, str):
                            sanitized[key] = [value]
                        else:
                            sanitized[key] = list(value)
                    elif expected_type is dict:
                        if isinstance(value, str):
                            sanitized[key] = {}
                        else:
                            sanitized[key] = dict(value)
                except (ValueError, TypeError):
                    # If conversion fails, remove the key
                    del sanitized[key]

        return sanitized

    @staticmethod
    def merge_metadata(base_metadata: dict, new_metadata: dict) -> dict:
        """
        Merge new metadata into base metadata

        Args:
            base_metadata: Existing metadata
            new_metadata: New metadata to merge

        Returns:
            Merged metadata dictionary
        """
        merged = base_metadata.copy()
        merged.update(new_metadata)
        return MetadataValidator.sanitize_metadata(merged)

    @staticmethod
    def get_required_metadata_fields() -> list[str]:
        """Get list of required metadata fields (currently none)"""
        return []

    @staticmethod
    def get_optional_metadata_fields() -> list[str]:
        """Get list of optional metadata fields"""
        return list(MetadataValidator.VALID_METADATA_KEYS.keys())


class MetadataManager:
    """Manager for agent metadata operations"""

    def __init__(self):
        """Initialize metadata manager"""
        self.validator = MetadataValidator()

    def update_agent_metadata(self, agent_id: str, current_metadata: dict, new_metadata: dict) -> tuple[bool, str, dict]:
        """
        Update agent metadata

        Args:
            agent_id: Agent ID
            current_metadata: Current metadata
            new_metadata: New metadata to add/update

        Returns:
            Tuple of (success, message, updated_metadata)
        """
        # Validate new metadata
        is_valid, error_msg = self.validator.validate_metadata(new_metadata)
        if not is_valid:
            return False, error_msg, current_metadata

        # Merge metadata
        updated_metadata = self.validator.merge_metadata(current_metadata, new_metadata)

        return True, "Metadata updated successfully", updated_metadata

    def validate_agent_metadata(self, metadata: dict) -> tuple[bool, str]:
        """
        Validate agent metadata

        Args:
            metadata: Metadata to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        return self.validator.validate_metadata(metadata)

    def get_metadata_template(self) -> dict:
        """
        Get a template for agent metadata with default values

        Returns:
            Metadata template dictionary
        """
        return {
            "location": "",
            "region": "",
            "country": "",
            "hardware_specs": {},
            "gpu_type": "",
            "gpu_count": 0,
            "memory_gb": 0,
            "storage_gb": 0,
            "network_bandwidth_mbps": 0,
            "latency_ms": 0,
            "uptime_percentage": 99.0,
            "supported_frameworks": [],
            "model_types": [],
            "max_batch_size": 1,
            "specializations": [],
            "certifications": [],
            "compliance_level": "basic",
            "data_privacy_level": "standard",
            "sla_guarantee": "best_effort",
        }
