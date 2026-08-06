"""Dynamic plugin loader for AITBC white-label deployments (v0.16.2 §B3).

A manifest's entry_point names a module and a callable; loading it means importing that
module and calling it. That is arbitrary code execution, so what may be imported has to be
decided before the import happens, not after.

The loader previously called ``importlib.import_module`` on whatever string the manifest
carried and then called whatever attribute it named, with the manifest's own config as an
argument. Anyone able to supply a manifest could run any importable code in the process.
The module docstring noted that "a production implementation should enforce sandboxing,
signature verification, and dependency isolation" -- a comment does not stop an import.

Two gates now stand in front of the import:

1. An allowlist of module prefixes, defaulting to the plugin namespace only. Nothing
   outside it can be imported, so ``os:system`` is refused before ``os`` is touched.
2. Optional signature verification. A deployment that passes a ``verifier`` gets manifests
   rejected unless they carry a signature that verifier accepts.

Neither is a sandbox: an allowed plugin still runs with the host process's full
privileges. What they remove is the ability of an untrusted manifest to choose what runs.
"""

from __future__ import annotations

import importlib
from collections.abc import Callable, Sequence

from .manifest import PluginHookRegistry, PluginManifest

#: Modules a plugin may be loaded from unless a deployment widens this explicitly.
#: Deliberately narrow -- a plugin namespace, not a package root that happens to contain
#: one.
DEFAULT_ALLOWED_MODULE_PREFIXES: tuple[str, ...] = ("aitbc_plugins",)


class PluginSecurityError(Exception):
    """A plugin was refused before anything of it was imported or executed."""


class PluginNotAllowedError(PluginSecurityError):
    """The manifest's entry point is outside the allowlist."""


class PluginSignatureError(PluginSecurityError):
    """The manifest is unsigned, or its signature was not accepted."""


def _is_allowed(module_name: str, allowed_prefixes: Sequence[str]) -> bool:
    """Whether ``module_name`` falls under one of ``allowed_prefixes``.

    Matching is on dotted-path boundaries. A plain ``startswith`` would let
    ``aitbc_plugins_evil`` through on the strength of the ``aitbc_plugins`` prefix, which
    is the usual way an allowlist like this fails open.
    """
    for prefix in allowed_prefixes:
        if module_name == prefix or module_name.startswith(prefix + "."):
            return True
    return False


def _parse_entry_point(entry_point: str) -> tuple[str, str]:
    """Split ``module.path:callable``, rejecting anything that is not exactly that."""
    module_name, separator, attr_name = entry_point.rpartition(":")
    if not separator or not module_name or not attr_name:
        raise ValueError("entry_point must be 'module.path:callable'")

    # A relative or otherwise unresolvable name would be interpreted against whatever
    # package context happens to apply; require an absolute dotted path.
    if module_name.startswith(".") or module_name.endswith(".") or ".." in module_name:
        raise ValueError(f"entry_point module must be an absolute dotted path: {module_name!r}")

    if not all(part.isidentifier() for part in module_name.split(".")):
        raise ValueError(f"entry_point module is not a valid module path: {module_name!r}")

    if not attr_name.isidentifier():
        raise ValueError(f"entry_point attribute is not a valid identifier: {attr_name!r}")

    return module_name, attr_name


def load_plugin(
    manifest: PluginManifest,
    registry: PluginHookRegistry | None = None,
    *,
    allowed_module_prefixes: Sequence[str] | None = None,
    verifier: Callable[[PluginManifest], bool] | None = None,
) -> PluginHookRegistry:
    """Load a plugin from a manifest and register its hooks.

    :param allowed_module_prefixes: Module prefixes the entry point may live under.
        Defaults to :data:`DEFAULT_ALLOWED_MODULE_PREFIXES`. Passing an empty sequence
        disables plugin loading entirely, which is a reasonable setting for a deployment
        that does not use plugins.
    :param verifier: Called with the manifest before its module is imported. When given, a
        manifest without a signature, or one the verifier rejects, is refused.
    :raises PluginNotAllowedError: The entry point is outside the allowlist.
    :raises PluginSignatureError: A verifier was given and the manifest did not satisfy it.
    """
    registry = registry or PluginHookRegistry()
    if not manifest.entry_point:
        return registry

    module_name, attr_name = _parse_entry_point(manifest.entry_point)

    prefixes = DEFAULT_ALLOWED_MODULE_PREFIXES if allowed_module_prefixes is None else allowed_module_prefixes
    if not _is_allowed(module_name, prefixes):
        raise PluginNotAllowedError(
            f"plugin {manifest.name or manifest.entry_point!r} loads from {module_name!r}, "
            f"which is not under any allowed prefix {tuple(prefixes)!r}"
        )

    if verifier is not None:
        if not manifest.signature:
            raise PluginSignatureError(f"plugin {manifest.name or manifest.entry_point!r} is unsigned")
        if not verifier(manifest):
            raise PluginSignatureError(f"plugin {manifest.name or manifest.entry_point!r} has an invalid signature")

    module = importlib.import_module(module_name)
    plugin = getattr(module, attr_name)

    if callable(plugin):
        plugin(registry, manifest.config)
    else:
        raise TypeError(f"plugin entry point {manifest.entry_point} is not callable")

    return registry


def load_plugins(
    manifests: list[PluginManifest],
    *,
    allowed_module_prefixes: Sequence[str] | None = None,
    verifier: Callable[[PluginManifest], bool] | None = None,
) -> PluginHookRegistry:
    """Load multiple plugins into a single registry.

    A plugin that is refused stops the batch. Loading the rest would leave the registry in
    a state that matches neither what was asked for nor what is safe, and the caller would
    have no straightforward way to tell which hooks are present.
    """
    registry = PluginHookRegistry()
    for manifest in manifests:
        load_plugin(
            manifest,
            registry,
            allowed_module_prefixes=allowed_module_prefixes,
            verifier=verifier,
        )
    return registry
