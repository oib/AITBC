"""Plugin manifest and lifecycle hooks for OpenClaw agent execution (v0.16.2 §B3).

ponytail: Hook registration is by name. In a real deployment each hook would be
a callable loaded from a plugin module and validated by signature.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from collections.abc import Callable


@dataclass
class PluginManifest:
    """Describes a plugin and the hooks it exposes."""

    name: str = ""
    version: str = ""
    entry_point: str = ""
    hooks: list[str] = field(default_factory=list)
    config: dict[str, Any] = field(default_factory=dict)


HookRegistry = dict[str, list[Callable[..., Any]]]


class PluginHookRegistry:
    """Central registry for plugin lifecycle hooks."""

    VALID_HOOKS = {
        "onResourceDiscovery",
        "onNegotiationStart",
        "onProofGeneration",
        "onVerificationSuccess",
    }

    def __init__(self) -> None:
        self._hooks: HookRegistry = {name: [] for name in self.VALID_HOOKS}

    def register(self, hook_name: str, callback: Callable[..., Any]) -> None:
        """Register a callback for a lifecycle hook."""
        if hook_name not in self.VALID_HOOKS:
            raise ValueError(f"unknown hook: {hook_name}")
        self._hooks[hook_name].append(callback)

    def run(self, hook_name: str, context: dict[str, Any] | None = None) -> list[Any]:
        """Execute all callbacks for a hook and return their results."""
        if hook_name not in self._hooks:
            raise ValueError(f"unknown hook: {hook_name}")
        context = context or {}
        return [callback(context) for callback in self._hooks[hook_name]]

    def list_hooks(self) -> list[str]:
        """Return the names of registered hooks with at least one callback."""
        return [name for name, callbacks in self._hooks.items() if callbacks]
