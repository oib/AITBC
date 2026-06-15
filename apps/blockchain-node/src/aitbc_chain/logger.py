"""Blockchain-node logger — delegates to central aitbc_logging module."""

from aitbc.aitbc_logging import get_blockchain_logger as get_logger

__all__ = ["get_logger"]
