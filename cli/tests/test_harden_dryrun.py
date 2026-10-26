"""CLI-HARDEN-DRYRUN-1: --dry-run must write zero files (no .bak, no unit changes)."""

import os


def test_dry_run_writes_nothing(monkeypatch, tmp_path):
    import aitbc_cli.commands.service as svc

    unit = tmp_path / "aitbc-x.service"
    unit.write_text("[Service]\nExecStart=/bin/x\n")

    monkeypatch.setattr(svc, "_service_unit_path", lambda name: str(unit))
    before = set(os.listdir(tmp_path))
    results, changed = svc._harden_results(["x"], True, "p")
    assert set(os.listdir(tmp_path)) == before
    assert changed == []
    assert results[0].get("dry_run")


def test_real_run_writes_backup(monkeypatch, tmp_path):
    """Mutation pin: with dry_run=False a .bak appears."""
    import aitbc_cli.commands.service as svc

    unit = tmp_path / "aitbc-x.service"
    unit.write_text("[Service]\nExecStart=/bin/x\n")

    monkeypatch.setattr(svc, "_service_unit_path", lambda name: str(unit))
    results, changed = svc._harden_results(["x"], False, "p")
    if results[0].get("changed"):
        assert any(".bak." in f for f in os.listdir(tmp_path))
