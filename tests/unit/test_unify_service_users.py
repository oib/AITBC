"""#883: unify_service_users.sh must not rewrite tracked unit files.

On base it walked ``/opt/aitbc/apps`` and sed-rewrote every ``*.service``
to ``User=aitbc`` — including the deliberate exceptions
(``aitbc-ops-signer.service`` runs as root, ``aitbc-hermes-agent.service``
as ``aitbc-hermes``) — dirtying the tracked working tree on every run.

The script now carries an allow-list of the units that are meant to run
as aitbc, applies it only to the *deployed* units under
``AITBC_SYSTEMD_DIR`` (default ``/etc/systemd/system``), and never edits
the repo. Tracked files are already correct — they are the source the
allow-list is validated against.
"""

import os
import re
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "deployment" / "unify_service_users.sh"
APPS = REPO / "apps"


def _src() -> str:
    return SCRIPT.read_text()


def _allowlist() -> set[str]:
    """Parse the AITBC_UNITS allow-list out of the script."""
    m = re.search(r"AITBC_UNITS=\(([^)]*)\)", _src(), re.S)
    assert m, "script has no AITBC_UNITS allow-list"
    return set(re.findall(r"aitbc-[\w.-]+\.service", m.group(1)))


def _repo_units():
    units = {}
    for f in sorted(APPS.rglob("*.service")):
        m = re.search(r"^User=(\S+)", f.read_text(), re.M)
        units[f.name] = m.group(1) if m else None
    return units


# ---------------------------------------------------------------------------
# static / invariant checks
# ---------------------------------------------------------------------------


def test_script_does_not_edit_tracked_files():
    src = _src()
    assert "AITBC_SYSTEMD_DIR" in src, "deployed-unit dir is not env-overridable"
    # No sed -i against the repo tree.
    body = re.sub(r"^\s*#.*$", "", src, flags=re.M)
    assert not re.search(r"sed -i[^\n]*apps/", body), "script still sed-edits files under apps/"
    assert not re.search(r'SERVICE_DIR="?/opt/aitbc/apps', body), "script still targets /opt/aitbc/apps"


def test_allowlist_matches_repo_intent():
    units = _repo_units()
    allow = _allowlist()
    aitbc_units = {name for name, user in units.items() if user == "aitbc"}
    deliberate = {name for name, user in units.items() if user not in (None, "aitbc")}
    missing = aitbc_units - allow
    overbroad = allow - aitbc_units
    assert not missing, f"aitbc units missing from allow-list: {missing}"
    assert not overbroad, f"allow-list names units that are not User=aitbc in repo: {overbroad}"
    assert deliberate == {"aitbc-ops-signer.service", "aitbc-hermes-agent.service"}
    for name in deliberate:
        assert name not in allow, f"deliberate non-aitbc unit {name} is allow-listed"


# ---------------------------------------------------------------------------
# functional: run against a scratch systemd dir
# ---------------------------------------------------------------------------


def _run(tmp_path):
    sysdir = tmp_path / "systemd"
    sysdir.mkdir()
    (sysdir / "aitbc-market.service").write_text("[Service]\nUser=root\nExecStart=/bin/x\n")
    (sysdir / "aitbc-ops-signer.service").write_text("[Service]\nUser=root\nExecStart=/bin/x\n")
    (sysdir / "other-vendor.service").write_text("[Service]\nUser=root\nExecStart=/bin/x\n")

    bindir = tmp_path / "bin"
    bindir.mkdir()
    (bindir / "id").write_text("#!/bin/bash\nexit 0\n")
    (bindir / "id").chmod(0o755)

    libdir = tmp_path / "lib"
    libdir.mkdir()

    env = dict(os.environ)
    env["PATH"] = f"{bindir}:{env['PATH']}"
    env["AITBC_SYSTEMD_DIR"] = str(sysdir)
    env["AITBC_LIB_DIR"] = str(libdir)
    r = subprocess.run(["bash", str(SCRIPT)], env=env, capture_output=True, text=True, timeout=60)
    return r, sysdir


@pytest.mark.skipif(os.geteuid() != 0, reason="script requires root")
def test_deployed_units_updated_selectively(tmp_path):
    r, sysdir = _run(tmp_path)
    assert r.returncode == 0, r.stderr
    assert "User=aitbc" in (sysdir / "aitbc-market.service").read_text()
    assert "User=root" in (sysdir / "aitbc-ops-signer.service").read_text(), "deliberate root unit was rewritten"
    assert "User=root" in (sysdir / "other-vendor.service").read_text()


@pytest.mark.skipif(os.geteuid() != 0, reason="script requires root")
def test_repo_units_untouched(tmp_path):
    before = {f: f.read_bytes() for f in APPS.rglob("*.service")}
    r, _ = _run(tmp_path)
    assert r.returncode == 0, r.stderr
    for f, content in before.items():
        assert f.read_bytes() == content, f"tracked unit {f} was modified"
