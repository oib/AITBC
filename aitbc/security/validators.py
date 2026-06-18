"""
Security validators for input validation and sanitization
"""

import html
import re
from typing import Any


class SecurityValidator:
    """
    Security validator for input validation and sanitization.
    Provides methods to validate and sanitize user inputs.
    """

    EMAIL_PATTERN = re.compile("^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$")
    URL_PATTERN = re.compile(
        "^https?://(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\\.)+(?:[A-Z]{2,6}\\.?|[A-Z0-9-]{2,}\\.?)|localhost|\\d{1,3}\\.\\d{1,3}\\.\\d{1,3}\\.\\d{1,3})(?::\\d+)?(?:/?|[/?]\\S+)$",
        re.IGNORECASE,
    )
    ETHEREUM_ADDRESS_PATTERN = re.compile("^0x[a-fA-F0-9]{40}$")
    TX_HASH_PATTERN = re.compile("^0x[a-fA-F0-9]{64}$")
    PRIVATE_KEY_PATTERN = re.compile("^(0x)?[a-fA-F0-9]{64}$")
    CHAIN_ID_PATTERN = re.compile("^[1-9]\\d*$")
    CONTRACT_ADDRESS_PATTERN = re.compile("^0x[a-fA-F0-9]{40}$")
    BLOCK_NUMBER_PATTERN = re.compile("^[1-9]\\d*$")
    GAS_PRICE_PATTERN = re.compile("^[1-9]\\d*$")
    GAS_LIMIT_PATTERN = re.compile("^[1-9]\\d{1,7}$")

    @staticmethod
    def validate_email(email: str) -> bool:
        """
        Validate email address format

        Args:
            email: Email address to validate

        Returns:
            True if valid, False otherwise
        """
        return bool(SecurityValidator.EMAIL_PATTERN.match(email))

    @staticmethod
    def validate_url(url: str) -> bool:
        """
        Validate URL format

        Args:
            url: URL to validate

        Returns:
            True if valid, False otherwise
        """
        return bool(SecurityValidator.URL_PATTERN.match(url))

    @staticmethod
    def validate_ethereum_address(address: str) -> bool:
        """
        Validate Ethereum address format

        Args:
            address: Ethereum address to validate

        Returns:
            True if valid, False otherwise
        """
        return bool(SecurityValidator.ETHEREUM_ADDRESS_PATTERN.match(address))

    @staticmethod
    def validate_tx_hash(tx_hash: str) -> bool:
        """
        Validate transaction hash format

        Args:
            tx_hash: Transaction hash to validate

        Returns:
            True if valid, False otherwise
        """
        return bool(SecurityValidator.TX_HASH_PATTERN.match(tx_hash))

    @staticmethod
    def sanitize_html(html_content: str) -> str:
        """
        Sanitize HTML content to prevent XSS attacks

        Args:
            html_content: HTML content to sanitize

        Returns:
            Sanitized HTML content
        """
        return html.escape(html_content)

    @staticmethod
    def sanitize_json_string(json_string: str) -> str:
        """
        Sanitize JSON string to prevent injection attacks

        Args:
            json_string: JSON string to sanitize

        Returns:
            Sanitized JSON string
        """
        sanitized = re.sub("[\\x00-\\x1f\\x7f-\\x9f]", "", json_string)
        return sanitized

    @staticmethod
    def validate_json_structure(data: Any, required_fields: list[str]) -> bool:
        """
        Validate JSON structure has required fields

        Args:
            data: Data to validate
            required_fields: List of required field names

        Returns:
            True if valid, False otherwise
        """
        if not isinstance(data, dict):
            return False
        return all(field in data for field in required_fields)

    @staticmethod
    def sanitize_filename(filename: str) -> str:
        """
        Sanitize filename to prevent path traversal attacks

        Args:
            filename: Filename to sanitize

        Returns:
            Sanitized filename
        """
        sanitized = re.sub("[\\\\/\\0]", "", filename)
        sanitized = re.sub("[\\x00-\\x1f\\x7f-\\x9f]", "", sanitized)
        return sanitized

    @staticmethod
    def validate_ethereum_private_key(private_key: str) -> bool:
        """
        Validate Ethereum private key format

        Args:
            private_key: Private key to validate

        Returns:
            True if valid, False otherwise
        """
        return bool(SecurityValidator.PRIVATE_KEY_PATTERN.match(private_key))

    @staticmethod
    def validate_chain_id(chain_id: str | int) -> bool:
        """
        Validate blockchain chain ID

        Args:
            chain_id: Chain ID to validate

        Returns:
            True if valid, False otherwise
        """
        chain_id_str = str(chain_id)
        return bool(SecurityValidator.CHAIN_ID_PATTERN.match(chain_id_str))

    @staticmethod
    def validate_contract_address(address: str) -> bool:
        """
        Validate smart contract address format

        Args:
            address: Contract address to validate

        Returns:
            True if valid, False otherwise
        """
        return bool(SecurityValidator.CONTRACT_ADDRESS_PATTERN.match(address))

    @staticmethod
    def validate_block_number(block_number: str | int) -> bool:
        """
        Validate block number

        Args:
            block_number: Block number to validate

        Returns:
            True if valid, False otherwise
        """
        block_number_str = str(block_number)
        return bool(SecurityValidator.BLOCK_NUMBER_PATTERN.match(block_number_str))

    @staticmethod
    def validate_gas_price(gas_price: str | int) -> bool:
        """
        Validate gas price (in wei)

        Args:
            gas_price: Gas price to validate

        Returns:
            True if valid, False otherwise
        """
        gas_price_str = str(gas_price)
        return bool(SecurityValidator.GAS_PRICE_PATTERN.match(gas_price_str))

    @staticmethod
    def validate_gas_limit(gas_limit: str | int) -> bool:
        """
        Validate gas limit (reasonable bounds)

        Args:
            gas_limit: Gas limit to validate

        Returns:
            True if valid, False otherwise
        """
        gas_limit_str = str(gas_limit)
        return bool(SecurityValidator.GAS_LIMIT_PATTERN.match(gas_limit_str))

    @staticmethod
    def validate_transaction_data(tx_data: str) -> bool:
        """
        Validate transaction data hex string

        Args:
            tx_data: Transaction data hex string to validate

        Returns:
            True if valid, False otherwise
        """
        if not tx_data:
            return True
        if tx_data.startswith("0x"):
            tx_data = tx_data[2:]
            if not tx_data:
                return True
        try:
            int(tx_data, 16)
            return True
        except ValueError:
            return False

    @staticmethod
    def validate_amount(amount: str | int | float) -> bool:
        """
        Validate transaction amount (positive numbers only)

        Args:
            amount: Amount to validate

        Returns:
            True if valid, False otherwise
        """
        try:
            amount_float = float(amount)
            return amount_float >= 0
        except (ValueError, TypeError):
            return False
