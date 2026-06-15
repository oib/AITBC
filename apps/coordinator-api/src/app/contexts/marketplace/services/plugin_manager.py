"""Plugin Manager for marketplace extensibility."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from aitbc import get_logger

from ..domain.gpu_marketplace import Plugin

logger = get_logger(__name__)
_plugin_manager = None


def get_plugin_manager() -> PluginManager:
    """Get the global plugin manager instance."""
    global _plugin_manager
    if _plugin_manager is None:
        _plugin_manager = PluginManager()
    return _plugin_manager


class PluginManager:
    """Singleton plugin manager for marketplace extensions."""

    def __init__(self) -> None:
        self.plugins: dict[str, Plugin] = {}
        self.plugin_hooks: dict[str, list[Callable]] = {
            "before_booking": [],
            "after_booking": [],
            "before_pricing": [],
            "after_pricing": [],
        }

    def register_plugin(
        self,
        plugin_name: str,
        plugin_version: str = "1.0.0",
        plugin_type: str = "extension",
        config: dict[str, Any] | None = None,
        description: str = "",
        author: str = "",
    ) -> Plugin:
        """Register a new plugin."""
        if plugin_name in self.plugins:
            logger.warning("Plugin %s already registered, updating", plugin_name)
        plugin = Plugin(
            plugin_name=plugin_name,
            plugin_version=plugin_version,
            plugin_type=plugin_type,
            config=config or {},
            description=description,
            author=author,
        )
        self.plugins[plugin_name] = plugin
        logger.info("Registered plugin: %s v%s", plugin_name, plugin_version)
        return plugin

    def execute_hook(self, hook_name: str, context: dict[str, Any]) -> dict[str, Any]:
        """Execute all registered hooks for a given hook name."""
        if hook_name not in self.plugin_hooks:
            logger.warning("Unknown hook: %s", hook_name)
            return context
        results = []
        for hook in self.plugin_hooks[hook_name]:
            try:
                result = hook(context)
                results.append(result)
            except Exception as e:
                logger.error("Hook %s failed: %s", hook_name, e)
        context["hook_results"] = results
        return context

    def enable_plugin(self, plugin_name: str) -> bool:
        """Enable a plugin."""
        if plugin_name not in self.plugins:
            logger.error("Plugin %s not found", plugin_name)
            return False
        self.plugins[plugin_name].enabled = True
        self.plugins[plugin_name].updated_at = datetime.now(UTC)
        logger.info("Enabled plugin: %s", plugin_name)
        return True

    def disable_plugin(self, plugin_name: str) -> bool:
        """Disable a plugin."""
        if plugin_name not in self.plugins:
            logger.error("Plugin %s not found", plugin_name)
            return False
        self.plugins[plugin_name].enabled = False
        self.plugins[plugin_name].updated_at = datetime.now(UTC)
        logger.info("Disabled plugin: %s", plugin_name)
        return True

    def register_hook(self, hook_name: str, hook_func: Callable) -> bool:
        """Register a hook function for a specific hook name."""
        if hook_name not in self.plugin_hooks:
            logger.warning("Unknown hook: %s", hook_name)
            return False
        self.plugin_hooks[hook_name].append(hook_func)
        logger.info("Registered hook: %s", hook_name)
        return True

    def get_plugin(self, plugin_name: str) -> Plugin | None:
        """Get a plugin by name."""
        return self.plugins.get(plugin_name)

    def list_plugins(self, enabled_only: bool = False) -> list[Plugin]:
        """List all registered plugins."""
        if enabled_only:
            return [p for p in self.plugins.values() if p.enabled]
        return list(self.plugins.values())

    def unregister_plugin(self, plugin_name: str) -> bool:
        """Unregister a plugin."""
        if plugin_name not in self.plugins:
            logger.error("Plugin %s not found", plugin_name)
            return False
        del self.plugins[plugin_name]
        logger.info("Unregistered plugin: %s", plugin_name)
        return True
