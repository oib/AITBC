"""Per-chain configuration string parser.

Parses config strings in "key:value,key:value" format into
typed dictionaries. Used for CHAIN_CONFIG_* env vars.
"""

from __future__ import annotations


class ChainConfigParser:
    """Parses per-chain configuration strings into typed dictionaries.

    Parses config strings in "key:value,key:value" format into
    typed dictionaries. Used for CHAIN_CONFIG_* env vars.

    Example:
        "block_time_seconds:2,max_txs_per_block:500"
        → {"block_time_seconds": 2, "max_txs_per_block": 500}
    """

    # Known config keys and their types
    KNOWN_KEYS: dict[str, type] = {
        "block_time_seconds": int,
        "max_txs_per_block": int,
        "max_block_size_bytes": int,
        "block_generation_mode": str,
        "max_empty_block_interval": int,
    }

    @classmethod
    def parse(cls, config_str: str) -> dict[str, int | str]:
        """Parse a "key:value,key:value" config string into a typed dict.

        Args:
            config_str: Config string in "key:value,key:value" format.

        Returns:
            Dict mapping key → typed value (int or str).

        Raises:
            ValueError: If the string is malformed (missing colon, empty key,
                unknown key, or value type mismatch).
        """
        if not config_str or not config_str.strip():
            return {}
        result: dict[str, int | str] = {}
        for pair in config_str.split(","):
            pair = pair.strip()
            if not pair:
                continue
            if ":" not in pair:
                raise ValueError(f"Invalid chain config entry (expected 'key:value'): {pair}")
            key, value = pair.split(":", 1)
            key = key.strip()
            value = value.strip()
            if not key or not value:
                raise ValueError(f"Invalid chain config entry (empty key or value): {pair}")
            if key not in cls.KNOWN_KEYS:
                raise ValueError(f"Unknown chain config key '{key}'. Known keys: {sorted(cls.KNOWN_KEYS.keys())}")
            expected_type = cls.KNOWN_KEYS[key]
            if expected_type is int:
                try:
                    result[key] = int(value)
                except ValueError:
                    raise ValueError(f"Invalid int value for key '{key}': '{value}'") from None
            else:
                result[key] = value
        return result

    @classmethod
    def parse_multiple(cls, configs: dict[str, str]) -> dict[str, dict[str, int | str]]:
        """Parse multiple chain config strings at once.

        Args:
            configs: Dict mapping chain_id → config string.

        Returns:
            Dict mapping chain_id → typed config dict.
        """
        result: dict[str, dict[str, int | str]] = {}
        for chain_id, config_str in configs.items():
            if not config_str or not config_str.strip():
                continue
            result[chain_id] = cls.parse(config_str)
        return result
