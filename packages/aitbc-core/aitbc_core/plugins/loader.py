"""Dynamic plugin loader for AITBC white-label deployments (v0.16.2 §B3).

ponytail: This loader only imports callables from a manifest entry-point string.
A production implementation should enforce sandboxing, signature verification,
and dependency isolation for third-party plugins.
"""

from __future__ import annotations

import importlib

from .manifest import PluginHookRegistry, PluginManifest


def load_plugin(manifest: PluginManifest, registry: PluginHookRegistry | None = None) -> PluginHookRegistry:
    """Load a plugin from a manifest and register its hooks."""
    registry = registry or PluginHookRegistry()
    if not manifest.entry_point:
        return registry

    try:
        module_name, attr_name = manifest.entry_point.rsplit(":", 1)
    except ValueError:  # noqa: B904
        raise ValueError("entry_point must be 'module.path:callable'")  # noqa: B904 from None

    module = importlib.import_module(module_name)
    plugin = getattr(module, attr_name)

    if callable(plugin):
        plugin(registry, manifest.config)
    else:
        raise TypeError(f"plugin entry point {manifest.entry_point} is not callable")

    return registry


def load_plugins(manifests: list[PluginManifest]) -> PluginHookRegistry:
    """Load multiple plugins into a single registry."""
    registry = PluginHookRegistry()
    for manifest in manifests:
        load_plugin(manifest, registry)
    return registry
