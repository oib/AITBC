"""Units that write /run/aitbc must declare RuntimeDirectory=aitbc (#1691).

``ReadWritePaths=/run/aitbc`` makes systemd set up the mount namespace
against that path; when ``/run`` (tmpfs) was cleaned and
``/etc/tmpfiles.d/aitbc-secrets.conf`` was missing or not yet run, every
such unit failed ``226/NAMESPACE`` and crash-looped (aitbc-test-n3,
8–10 Nov 2026). ``RuntimeDirectory=aitbc`` makes systemd create the
directory before namespace setup, so the unit survives a missing
tmpfiles provisioning.

Scope: long-running units only. ``Type=oneshot`` units are excluded —
their RuntimeDirectory is removed on exit, which would delete the dir out
from under running services.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _service_files() -> list[Path]:
    return sorted(p for base in (REPO_ROOT / "apps", REPO_ROOT / "scripts") for p in base.rglob("*.service") if p.is_file())


def test_units_referencing_run_aitbc_declare_runtime_directory() -> None:
    missing = []
    for path in _service_files():
        text = path.read_text()
        if "run/aitbc" not in text or "Type=oneshot" in text:
            continue
        if not re.search(r"(?m)^RuntimeDirectory=aitbc\s*$", text):
            missing.append(str(path.relative_to(REPO_ROOT)))
    assert not missing, f"units referencing /run/aitbc without RuntimeDirectory=aitbc: {missing}"


def test_oneshot_units_do_not_declare_runtime_directory() -> None:
    offenders = []
    for path in _service_files():
        text = path.read_text()
        if "Type=oneshot" in text and re.search(r"(?m)^RuntimeDirectory=", text):
            offenders.append(str(path.relative_to(REPO_ROOT)))
    assert not offenders, f"oneshot units must not own RuntimeDirectory (removed on exit): {offenders}"
