"""PKG-03: the plugin loader must decide what may be imported before importing it.

load_plugin used to call importlib.import_module on whatever string a manifest carried,
then call whatever attribute it named, passing the manifest's own config. Anyone who could
supply a manifest could run any importable code in the process. The module docstring said a
production implementation "should enforce sandboxing, signature verification, and
dependency isolation" -- which stops nothing.

These tests attack the loader the way a hostile manifest would.
"""

import sys
from pathlib import Path

import pytest

CORE_SRC = Path(__file__).resolve().parents[2] / "packages" / "aitbc-core"
if str(CORE_SRC) not in sys.path:
    sys.path.insert(0, str(CORE_SRC))

from aitbc_core.plugins import (  # noqa: E402
    DEFAULT_ALLOWED_MODULE_PREFIXES,
    PluginManifest,
    PluginNotAllowedError,
    PluginSignatureError,
    load_plugin,
    load_plugins,
)


@pytest.fixture
def plugin_on_path(tmp_path):
    """A real, importable plugin package, so allowed loads can be tested end to end."""
    package = tmp_path / "aitbc_plugins"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "demo.py").write_text(
        "def register(registry, config):\n    registry.register('onProofGeneration', lambda ctx: config.get('value'))\n",
        encoding="utf-8",
    )
    sys.path.insert(0, str(tmp_path))
    yield
    sys.path.remove(str(tmp_path))
    for name in [m for m in sys.modules if m.startswith("aitbc_plugins")]:
        del sys.modules[name]


class TestAllowlist:
    def test_refuses_a_module_outside_the_allowlist(self):
        manifest = PluginManifest(name="evil", entry_point="os:system")

        with pytest.raises(PluginNotAllowedError):
            load_plugin(manifest)

    def test_refuses_before_importing_anything(self, monkeypatch):
        """The check must run ahead of the import, not clean up after it."""
        import importlib

        def fail_if_called(name, *args, **kwargs):
            raise AssertionError(f"import_module was reached for {name!r}")

        monkeypatch.setattr(importlib, "import_module", fail_if_called)

        with pytest.raises(PluginNotAllowedError):
            load_plugin(PluginManifest(name="evil", entry_point="subprocess:run"))

    def test_a_lookalike_prefix_does_not_slip_through(self):
        """`aitbc_plugins_evil` shares a string prefix with the allowed namespace.

        A plain startswith check -- the usual way an allowlist like this fails open --
        would admit it.
        """
        manifest = PluginManifest(name="lookalike", entry_point="aitbc_plugins_evil.mod:go")

        with pytest.raises(PluginNotAllowedError):
            load_plugin(manifest)

    def test_allows_the_plugin_namespace(self, plugin_on_path):
        manifest = PluginManifest(
            name="demo",
            entry_point="aitbc_plugins.demo:register",
            config={"value": 42},
        )

        registry = load_plugin(manifest)

        assert registry.run("onProofGeneration") == [42]

    def test_a_deployment_can_widen_the_allowlist_explicitly(self, plugin_on_path):
        manifest = PluginManifest(
            name="demo",
            entry_point="aitbc_plugins.demo:register",
            config={"value": 7},
        )

        registry = load_plugin(manifest, allowed_module_prefixes=["aitbc_plugins"])

        assert registry.run("onProofGeneration") == [7]

    def test_an_empty_allowlist_disables_plugin_loading(self, plugin_on_path):
        manifest = PluginManifest(name="demo", entry_point="aitbc_plugins.demo:register")

        with pytest.raises(PluginNotAllowedError):
            load_plugin(manifest, allowed_module_prefixes=[])

    def test_the_default_allowlist_is_narrow(self):
        """A prefix like "aitbc" or "" would admit most of the codebase."""
        assert DEFAULT_ALLOWED_MODULE_PREFIXES == ("aitbc_plugins",)


class TestEntryPointParsing:
    @pytest.mark.parametrize(
        "entry_point",
        [
            "os.system",  # no separator at all
            ":system",  # no module
            "os:",  # no attribute
            ".relative.mod:go",  # relative path, resolved against who knows what
            "aitbc_plugins..demo:go",  # empty path component
            "aitbc_plugins.demo:not an identifier",
            "aitbc_plugins.de-mo:go",  # not a valid module path
        ],
    )
    def test_rejects_a_malformed_entry_point(self, entry_point):
        with pytest.raises(ValueError):
            load_plugin(PluginManifest(name="bad", entry_point=entry_point))

    def test_an_empty_entry_point_loads_nothing(self):
        """A manifest that declares no entry point is not an error, it is just inert."""
        registry = load_plugin(PluginManifest(name="inert"))

        assert registry.list_hooks() == []


class TestSignatureVerification:
    def test_an_unsigned_manifest_is_refused_when_verifying(self, plugin_on_path):
        manifest = PluginManifest(name="demo", entry_point="aitbc_plugins.demo:register")

        with pytest.raises(PluginSignatureError):
            load_plugin(manifest, verifier=lambda _m: True)

    def test_a_rejected_signature_stops_the_load(self, plugin_on_path):
        manifest = PluginManifest(
            name="demo",
            entry_point="aitbc_plugins.demo:register",
            signature="not-a-real-signature",
        )

        with pytest.raises(PluginSignatureError):
            load_plugin(manifest, verifier=lambda _m: False)

    def test_an_accepted_signature_loads(self, plugin_on_path):
        manifest = PluginManifest(
            name="demo",
            entry_point="aitbc_plugins.demo:register",
            config={"value": 1},
            signature="good",
        )

        registry = load_plugin(manifest, verifier=lambda m: m.signature == "good")

        assert registry.run("onProofGeneration") == [1]

    def test_the_verifier_runs_before_the_import(self, plugin_on_path, monkeypatch):
        import importlib

        monkeypatch.setattr(
            importlib,
            "import_module",
            lambda *a, **k: pytest.fail("import_module was reached despite a bad signature"),
        )

        with pytest.raises(PluginSignatureError):
            load_plugin(
                PluginManifest(
                    name="demo",
                    entry_point="aitbc_plugins.demo:register",
                    signature="bad",
                ),
                verifier=lambda _m: False,
            )

    def test_no_verifier_means_no_signature_requirement(self, plugin_on_path):
        """Signature checking is opt-in; the allowlist is the gate that is always on."""
        manifest = PluginManifest(
            name="demo",
            entry_point="aitbc_plugins.demo:register",
            config={"value": 5},
        )

        assert load_plugin(manifest).run("onProofGeneration") == [5]


class TestBatchLoading:
    def test_a_refused_plugin_stops_the_batch(self, plugin_on_path):
        """Loading the survivors would leave a registry matching neither request nor policy."""
        manifests = [
            PluginManifest(name="ok", entry_point="aitbc_plugins.demo:register", config={"value": 1}),
            PluginManifest(name="evil", entry_point="os:system"),
        ]

        with pytest.raises(PluginNotAllowedError):
            load_plugins(manifests)

    def test_loads_several_allowed_plugins_into_one_registry(self, plugin_on_path):
        manifests = [
            PluginManifest(name="a", entry_point="aitbc_plugins.demo:register", config={"value": 1}),
            PluginManifest(name="b", entry_point="aitbc_plugins.demo:register", config={"value": 2}),
        ]

        registry = load_plugins(manifests)

        assert registry.run("onProofGeneration") == [1, 2]
