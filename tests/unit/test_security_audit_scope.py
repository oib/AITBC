"""SECURITY-AUDIT-SCANS-VENV-AND-POSITIVE-CHECKS-CANNOT-FAIL-1 — code scans
cover tracked files only: a secret inside venv/ never fires, and a bare
ethereum-address literal is not a secret."""

import importlib.util
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("security_audit", REPO / "scripts" / "security" / "security_audit.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def _tracked_tree(tmp_path):
    (tmp_path / "venv").mkdir()
    (tmp_path / "venv" / "lib.py").write_text('API_KEY = "hardcoded-real-key-12345"\n')
    (tmp_path / "app.py").write_text('ADDR = "0x2aD555A9e5208A6438b24FbdA4BC83c4c2453e64"\n')
    subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True, check=True)
    subprocess.run(["git", "add", "app.py"], cwd=tmp_path, capture_output=True, check=True)


def test_venv_not_scanned_and_address_not_flagged(tmp_path):
    _tracked_tree(tmp_path)
    a = mod.SecurityAudit(str(tmp_path))
    _, issues = a.check_secret_management()
    assert not any("venv" in i.get("file", "") for i in issues)
    assert not any(i["type"] == "ethereum_address" for i in issues)


def test_tracked_secret_still_flags(tmp_path):
    _tracked_tree(tmp_path)
    (tmp_path / "app.py").write_text('API_KEY = "hardcoded-real-key-12345"\n')
    subprocess.run(["git", "add", "app.py"], cwd=tmp_path, capture_output=True, check=True)
    a = mod.SecurityAudit(str(tmp_path))
    _, issues = a.check_secret_management()
    assert any(i["type"] == "hardcoded_api_key" and i["file"] == "app.py" for i in issues)
