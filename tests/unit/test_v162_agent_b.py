"""Unit tests for v0.16.2 Agent B tasks."""

from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType

REPO_ROOT = Path(__file__).resolve().parents[2]
CORE_SRC = str(REPO_ROOT / "packages" / "aitbc-core")


def _core_module(module_path: str) -> ModuleType:
    """Import an aitbc_core module by adding the distribution root to path."""
    if CORE_SRC not in sys.path:
        sys.path.insert(0, CORE_SRC)
    return __import__(module_path, fromlist=["__name__"])


def test_brand_manifest_serialization() -> None:
    brand = _core_module("aitbc_core.manifest.brand")
    manifest = brand.BrandManifest(
        brand_id="acme",
        name="Acme",
        domain="acme.example.com",
    )
    data = manifest.to_dict()
    assert data["brand_id"] == "acme"
    assert data["name"] == "Acme"


def test_plugin_registry_runs_hooks() -> None:
    plugins = _core_module("aitbc_core.plugins.manifest")
    registry = plugins.PluginHookRegistry()
    registry.register("onResourceDiscovery", lambda ctx: ctx.get("x"))
    results = registry.run("onResourceDiscovery", {"x": 1})
    assert results == [1]
    assert registry.list_hooks() == ["onResourceDiscovery"]


def test_plugin_loader_loads_dynamic_plugin() -> None:
    import tempfile

    plugins = _core_module("aitbc_core.plugins")
    loader = _core_module("aitbc_core.plugins.loader")

    with tempfile.TemporaryDirectory() as tmpdir:
        plugin_dir = Path(tmpdir) / "myplugin"
        plugin_dir.mkdir()
        (plugin_dir / "__init__.py").write_text("", encoding="utf-8")
        (plugin_dir / "plugin.py").write_text(
            "def register(registry, config):\n    registry.register('onProofGeneration', lambda ctx: config.get('value'))\n",
            encoding="utf-8",
        )
        sys.path.insert(0, tmpdir)
        manifest = plugins.manifest.PluginManifest(
            name="myplugin",
            entry_point="myplugin.plugin:register",
            config={"value": 42},
        )
        # "myplugin" is outside DEFAULT_ALLOWED_MODULE_PREFIXES, so the caller has to say
        # so explicitly. That is the point of the allowlist: loading from an arbitrary
        # module is a decision someone makes, not the default.
        registry = loader.load_plugin(manifest, allowed_module_prefixes=["myplugin"])
        results = registry.run("onProofGeneration")
        assert results == [42]
        sys.path.remove(tmpdir)


def test_cli_platform_init() -> None:
    import tempfile

    from click.testing import CliRunner
    from cli.aitbc_cli.core.main import cli

    runner = CliRunner()
    with tempfile.TemporaryDirectory() as tmpdir:
        result = runner.invoke(
            cli,
            ["platform", "init-platform", "--name", "Acme", "--output", tmpdir],
        )
        assert result.exit_code == 0
        manifest_path = Path(tmpdir) / "brand-manifest.json"
        assert manifest_path.exists()


def test_cli_plugin_create() -> None:
    import tempfile

    from click.testing import CliRunner
    from cli.aitbc_cli.core.main import cli

    runner = CliRunner()
    with tempfile.TemporaryDirectory() as tmpdir:
        result = runner.invoke(
            cli,
            ["plugin", "create", "--type", "negotiation", "--name", "my-plugin", "--output", tmpdir],
        )
        assert result.exit_code == 0
        assert (Path(tmpdir) / "my-plugin" / "plugin-manifest.json").exists()


def test_cli_deploy_brand() -> None:
    import json
    import tempfile

    from click.testing import CliRunner
    from cli.aitbc_cli.core.main import cli

    runner = CliRunner()
    with tempfile.TemporaryDirectory() as tmpdir:
        manifest = {"brand_id": "acme", "name": "Acme"}
        manifest_path = Path(tmpdir) / "brand-manifest.json"
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f)
        storage = Path(tmpdir) / "deployments"
        result = runner.invoke(
            cli,
            ["deploy", "deploy-brand", "--config", str(manifest_path), "--storage", str(storage)],
        )
        assert result.exit_code == 0
        assert (storage / "local" / "acme" / "brand-manifest.json").exists()
