"""Shared parser context for unified CLI command registration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping


@dataclass(slots=True)
class ParserContext:
    default_rpc_url: str
    default_coordinator_url: str
    cli_version: str
    first: Callable[..., Any]
    read_password: Callable[..., Any]
    output_format: Callable[..., Any]
    render_mapping: Callable[..., Any]
    read_blockchain_env: Callable[..., Any]
    normalize_rpc_url: Callable[..., Any]
    probe_rpc_node: Callable[..., Any]
    get_network_snapshot: Callable[..., Any]
    handlers: Mapping[str, Callable[..., Any]]

    def __getattr__(self, name: str):
        try:
            return self.handlers[name]
        except KeyError as exc:
            raise AttributeError(name) from exc
