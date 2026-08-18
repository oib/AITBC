"""V23-103: nothing stopped a module that nothing imports from being added.

V23-102 deleted ``MarketplaceMonitor`` -- 280 lines of marketplace alerting that no code
path could reach. Deleting it fixed one module. It did not fix the reason there were 21
more behind it, which is that nothing in this repository has ever noticed when a file
stops being imported.

These tests cover ``scripts/lint/no_orphan_modules.py``, which does notice, and the
baseline that records today's set with a reviewed verdict per entry.

Written against two traps this release hit before:

* **A test that passes on main for the wrong reason proves nothing.** V23-102 shipped a
  vacuous assertion that held on every branch. Anything here that reads the real tree is
  paired with a control -- a module that must *not* be reported alongside one that must.
* **The hook has to survive the moment it is acted on.** ``git ls-files`` reads the index,
  so a file deleted in the working tree and not yet staged is still listed. That crashed
  ``no_float_money.py`` in V23-102 on an ordinary deletion. Deleting orphans is precisely
  the workflow *this* guard exists to encourage, so the same crash here would fire on its
  own success.
"""

from __future__ import annotations

import importlib.util
import json

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "lint" / "no_orphan_modules.py"
BASELINE = REPO_ROOT / "scripts" / "lint" / "no_orphan_modules_baseline.json"
COORD = "apps/coordinator-api/src/coordinator_api/"


def _load_module():
    """Import the lint by path -- ``scripts/`` is not a package and not on sys.path."""
    spec = importlib.util.spec_from_file_location("no_orphan_modules", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def lint():
    return _load_module()


@pytest.fixture(scope="module")
def baseline() -> dict:
    return json.loads(BASELINE.read_text(encoding="utf-8"))


class TestTheScanSeparatesReachableFromUnreachable:
    """The finding itself: which modules the import graph can and cannot reach."""

    def test_a_module_nothing_imports_is_reported(self, lint):
        # fhe_enhanced.py is a permanent fixture of this set -- a deliberate stub, verdict
        # "keep" -- so this assertion does not decay as the delete queue is worked off.
        found = lint._scan()
        assert COORD + "contexts/zk_applications/services/fhe_enhanced.py" in found

    def test_a_module_the_router_imports_is_not_reported(self, lint):
        # The control. Without it, a scan that returned every file in the tree would pass
        # the test above.
        found = lint._scan()
        assert COORD + "contexts/marketplace/services/marketplace.py" not in found

    def test_a_name_that_appears_only_as_a_string_does_not_count_as_an_import(self, lint):
        """The reason the conservative count is wrong.

        ``modality_optimization`` appears in ``monitoring_dashboard.py`` as a dict key and
        ``advanced_analytics`` in a privileges list. Grep calls both reachable. Neither
        string can execute the module, and an AST walk says so.
        """
        found = lint._scan()
        assert COORD + "contexts/multimodal/services/modality_optimization.py" in found
        assert COORD + "contexts/analytics/services/advanced_analytics.py" in found

    def test_entrypoints_are_not_reported(self, lint):
        """Nothing imports a ``main.py``; a process starts it."""
        assert not lint._is_candidate(Path(COORD + "main.py"))
        assert not lint._is_candidate(Path(COORD + "__init__.py"))
        assert lint._is_candidate(Path(COORD + "contexts/marketplace/services/anything.py"))


class TestATestOnlyImportStillCountsAsReachable:
    """The subtle half. Get this backwards and the guard nominates for deletion the very
    modules a test suite depends on -- and the deletion would be green until the suite ran.
    """

    def test_files_under_tests_are_importers_but_never_candidates(self, lint):
        assert not lint._is_candidate(Path(COORD + "contexts/marketplace/tests/helper.py"))
        tracked = {p.as_posix() for p in lint._tracked_python_files()}
        assert any(p.startswith("tests/") for p in tracked), "tests must be in the importer set"

    def test_a_module_imported_only_by_a_test_is_not_reported(self, lint, tmp_path):
        """Synthetic, because relying on a real example ties the test to one that may be
        deleted later for unrelated reasons."""
        module = Path(COORD + "contexts/marketplace/services/only_a_test_uses_me.py")
        test_file = Path("tests/unit/test_pretend.py")

        def fake_tracked():
            return [module, test_file]

        def fake_imports(path):
            return {"only_a_test_uses_me"} if path == test_file else set()

        lint_tracked, lint_imports = lint._tracked_python_files, lint._imported_module_names
        try:
            lint._tracked_python_files = fake_tracked
            lint._imported_module_names = fake_imports
            assert lint._scan() == {}
        finally:
            lint._tracked_python_files, lint._imported_module_names = lint_tracked, lint_imports


class TestTheGuardFailsOnlyOnSomethingNew:
    """Shrink-only, the same contract as ``no_float_money.py``."""

    def test_an_unbaselined_orphan_fails_the_run(self, lint, monkeypatch, capsys):
        monkeypatch.setattr(lint, "_scan", lambda: {COORD + "contexts/brand/new_orphan.py": 120})
        monkeypatch.setattr("sys.argv", ["no_orphan_modules.py"])
        assert lint.main() == 1
        assert "new_orphan.py" in capsys.readouterr().err

    def test_the_tree_as_it_stands_passes(self, lint, monkeypatch, capsys):
        monkeypatch.setattr("sys.argv", ["no_orphan_modules.py"])
        assert lint.main() == 0, capsys.readouterr().err

    def test_deleting_a_baselined_orphan_does_not_turn_the_tree_red(self, lint, monkeypatch, capsys):
        """Fixing something must never fail. It reports a loose baseline instead, because a
        loose baseline is how a shrink-only guard rots back into a decoration."""
        monkeypatch.setattr(lint, "_scan", lambda: {})
        monkeypatch.setattr("sys.argv", ["no_orphan_modules.py"])
        assert lint.main() == 0
        assert "Tighten the baseline" in capsys.readouterr().out


class TestDeletingAFileDoesNotCrashTheHook:
    """``git ls-files`` lists a file deleted in the working tree until the delete is staged."""

    def test_a_tracked_file_that_is_not_on_disk_yields_no_imports(self, lint):
        assert lint._imported_module_names(Path("apps/nope/gone.py")) == set()

    def test_a_whole_scan_survives_a_tracked_file_that_is_not_on_disk(self, lint):
        real = lint._tracked_python_files
        try:
            lint._tracked_python_files = lambda: [*real(), Path(COORD + "contexts/gone.py")]
            lint._scan()  # must not raise FileNotFoundError
        finally:
            lint._tracked_python_files = real


class TestEveryBaselinedOrphanCarriesADecision:
    """'Nothing imports it' is a reason to look, not a reason to delete. The baseline holds
    the looking, so an entry cannot quietly become an accepted state."""

    def test_the_baseline_covers_the_current_scan(self, lint, baseline):
        assert set(lint._scan()) <= set(baseline["orphans"])

    def test_every_entry_is_classified_delete_or_keep(self, baseline):
        unreviewed = [p for p, e in baseline["orphans"].items() if e.get("verdict") not in {"delete", "keep"}]
        assert unreviewed == []

    def test_every_entry_says_why(self, baseline):
        thin = [p for p, e in baseline["orphans"].items() if len(e.get("why", "")) < 40]
        assert thin == []

    def test_the_security_stub_is_kept_on_purpose(self, baseline):
        """fhe_enhanced.py records that the BFV implementation it replaced was not
        cryptographically secure. Deleting it would delete a security decision."""
        entry = baseline["orphans"][COORD + "contexts/zk_applications/services/fhe_enhanced.py"]
        assert entry["verdict"] == "keep"
        assert "secure" in entry["why"]

    def test_the_recorded_totals_match_the_entries(self, baseline):
        orphans = baseline["orphans"]
        assert baseline["total_modules"] == len(orphans)
        assert baseline["total_lines"] == sum(e["lines"] for e in orphans.values())


class TestAKeepJustifiedByDocsCanActuallyBeImportedThatWay:
    """Four modules are kept because documentation shows how to use them. That reason only
    holds if the documented import works -- and one of the four did not."""

    @pytest.mark.parametrize(
        ("doc", "module", "attr"),
        [
            (
                "docs/marketplace/advanced-marketplace/04-ml-search.md",
                "coordinator_api.contexts.marketplace.services.resource_matcher",
                "ResourceMatcher",
            ),
            (
                "docs/marketplace/advanced-marketplace/06-external-providers.md",
                "coordinator_api.contexts.marketplace.services.external_providers",
                "ExternalProviderService",
            ),
            (
                "docs/marketplace/advanced-marketplace/05-analytics.md",
                "coordinator_api.contexts.marketplace.services.market_analytics",
                "MarketAnalytics",
            ),
            (
                "docs/development/fhe-service.md",
                "coordinator_api.contexts.zk_applications.services.fhe_service",
                "FHEService",
            ),
        ],
    )
    def test_the_documented_import_line_resolves(self, doc, module, attr):
        line = f"from {module} import {attr}"
        assert line in (REPO_ROOT / doc).read_text(encoding="utf-8"), f"{doc} no longer shows {line}"
        assert getattr(importlib.import_module(module), attr)

    def test_no_doc_outside_the_release_logs_still_uses_the_pre_v23103_fhe_path(self):
        """It read ``coordinator_api.services.fhe_service``, a package that has no such
        module -- so the doc justifying the keep could never have been followed."""
        stale = [
            p.relative_to(REPO_ROOT).as_posix()
            for p in (REPO_ROOT / "docs").rglob("*.md")
            if "releases" not in p.parts and "coordinator_api.services.fhe_service" in p.read_text(encoding="utf-8")
        ]
        assert stale == []
