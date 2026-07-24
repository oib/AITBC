"""White-label plugin loader for agent ecosystem branding."""

from __future__ import annotations

import importlib.util
import os
import pathlib
from dataclasses import dataclass
from types import ModuleType
from .branding import BrandSettings
from .roles import Role


@dataclass(frozen=True)
class LoadedPlugin:
    """A validated brand plugin loaded from a Python module."""

    name: str
    brand: BrandSettings
    roles: dict[Role, str]
    identity_method: str


def _load_module(path: pathlib.Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(path.stem, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not create module spec for {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _parse_brand(name: str, module: ModuleType) -> BrandSettings:
    brand = getattr(module, "brand", None)
    if not isinstance(brand, BrandSettings):
        raise TypeError(f"Plugin {name} must define a 'brand: BrandSettings'")
    return brand


def _parse_roles(name: str, module: ModuleType) -> dict[Role, str]:
    raw_roles = getattr(module, "roles", {})
    if not isinstance(raw_roles, dict):
        raise TypeError(f"Plugin {name} 'roles' must be a dict")

    allowed = {role.value for role in Role}
    parsed: dict[Role, str] = {}
    for key, value in raw_roles.items():
        if isinstance(key, Role):
            parsed[key] = str(value)
        elif key in allowed:
            parsed[Role(key)] = str(value)
        else:
            raise ValueError(f"Plugin {name} has unknown role {key!r}; expected one of {allowed}")
    return parsed


def _parse_identity_method(name: str, module: ModuleType) -> str:
    identity_method = getattr(module, "identity_method", "did:aitbc")
    if not isinstance(identity_method, str):
        raise TypeError(f"Plugin {name} 'identity_method' must be a string")
    return identity_method


class PluginManager:
    """Load brand-specific plugins from a directory of Python files."""

    def __init__(self, plugins_dir: str | pathlib.Path | None = None) -> None:
        if plugins_dir is not None:
            resolved = pathlib.Path(plugins_dir)
        else:
            resolved = pathlib.Path(os.getenv("AITBC_PLUGINS_DIR", "plugins"))
        self.plugins_dir = resolved.expanduser().resolve()

    def load(self, name: str) -> LoadedPlugin:
        """Load a plugin by name."""
        path = self.plugins_dir / f"{name}.py"
        if not path.is_file():
            raise FileNotFoundError(f"Plugin {name} not found at {path}")

        module = _load_module(path)
        return LoadedPlugin(
            name=name,
            brand=_parse_brand(name, module),
            roles=_parse_roles(name, module),
            identity_method=_parse_identity_method(name, module),
        )

    def list_plugins(self) -> list[str]:
        """Return the names of available plugin files."""
        if not self.plugins_dir.is_dir():
            return []
        return sorted(
            path.stem for path in self.plugins_dir.iterdir() if path.suffix == ".py" and not path.stem.startswith(("_", "~"))
        )


def get_active_brand() -> BrandSettings:
    """Return the brand settings for the active plugin, or AITBC defaults."""
    active = os.getenv("AITBC_ACTIVE_PLUGIN")
    if not active:
        return BrandSettings.default()
    return PluginManager().load(active).brand
