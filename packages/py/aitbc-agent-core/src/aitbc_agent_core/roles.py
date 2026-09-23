"""Generic white-label smart contract and market roles."""

from enum import StrEnum


class Role(StrEnum):
    """Brand-agnostic participants in compute and trading contracts."""

    PROVIDER = "Provider"
    CONSUMER = "Consumer"
    VALIDATOR = "Validator"
    ARBITER = "Arbiter"
