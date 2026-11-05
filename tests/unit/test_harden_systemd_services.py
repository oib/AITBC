"""Pins for scripts/utils/harden-systemd-services.py (UTILS-HARDEN-SYSTEMD-DROPS-INSTALL-SECTION-1, #935).

The tool's ``insert_after_section_header`` broke out of its scan at the first
section header after ``[Service]`` and returned the truncated ``result``, so
every line from that header on — including ``[Install]`` / ``WantedBy`` — was
lost on each unit it rewrote. ``main()`` also scanned ``repo.rglob("*.service")``,
rewriting stray copies outside the unit directories. The tail is now preserved,
a trailing newline is kept, and only ``apps/*/*.service`` +
``scripts/*/*.service`` under ``--root``/``AITBC_HARDEN_ROOT`` are touched.
"""

import importlib.util
import shutil
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "utils" / "harden-systemd-services.py"
WALLET_UNIT = REPO_ROOT / "apps" / "wallet" / "aitbc-wallet.service"


def _load_module():
    spec = importlib.util.spec_from_file_location("harden_systemd_services", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def mod():
    return _load_module()


def _sections(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip().startswith("[") and line.strip().endswith("]")]


def test_insert_keeps_lines_after_next_section(mod):
    content = "[Unit]\nA=1\n\n[Service]\nExecStart=/bin/x\n\n[Install]\nWantedBy=multi-user.target\n"
    out = mod.insert_after_section_header(content, "Service", ["PrivateTmp=yes"])
    assert "[Install]" in out
    assert "WantedBy=multi-user.target" in out
    assert "PrivateTmp=yes" in out
    assert out.endswith("\n")
    # Insertion lands inside [Service], before [Install]
    assert out.index("PrivateTmp=yes") < out.index("[Install]")


def test_insert_when_target_is_last_section(mod):
    content = "[Unit]\nA=1\n\n[Service]\nExecStart=/bin/x\n"
    out = mod.insert_after_section_header(content, "Service", ["PrivateTmp=yes"])
    assert "PrivateTmp=yes" in out
    assert out.endswith("\n")


def test_insert_missing_section_returns_content(mod):
    content = "[Unit]\nA=1\n"
    assert mod.insert_after_section_header(content, "Service", ["X=1"]) == content


def test_harden_wallet_copy_keeps_install_section(mod, tmp_path):
    # done_when: a hardened copy of aitbc-wallet.service keeps its [Install] section
    copy = tmp_path / "aitbc-wallet.service"
    shutil.copy2(WALLET_UNIT, copy)
    before = copy.read_text()
    assert _sections(before) == ["[Unit]", "[Service]", "[Install]"]
    assert before.count("WantedBy=") == 1

    report = mod.harden_service_file(copy)
    after = copy.read_text()

    assert report["modified"]
    assert _sections(after) == ["[Unit]", "[Service]", "[Install]"]
    assert after.count("WantedBy=") == 1
    assert "WantedBy=multi-user.target" in after
    # The [Install] tail must survive verbatim (RestartSec=10->5 etc. are
    # intentional rewrites inside [Service], so only the tail is byte-compared).
    assert after.split("[Install]", 1)[1] == before.split("[Install]", 1)[1]
    assert (tmp_path / "aitbc-wallet.service.bak").exists()


def test_second_run_is_idempotent(mod, tmp_path):
    copy = tmp_path / "aitbc-wallet.service"
    shutil.copy2(WALLET_UNIT, copy)
    mod.harden_service_file(copy)
    first = copy.read_text()
    mod.harden_service_file(copy)
    assert copy.read_text() == first


def test_iter_service_files_scoped_to_unit_dirs(mod, tmp_path):
    for rel in (
        "apps/wallet/aitbc-wallet.service",
        "scripts/monitoring/aitbc-foo.service",
        "docs/x/dont.service",
        "venv/lib/dont.service",
        "data/dont.service",
        "apps/deep/nested/dont.service",
    ):
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("[Unit]\nA=1\n")
    found = {p.name for p in mod.iter_service_files(tmp_path)}
    assert found == {"aitbc-wallet.service", "aitbc-foo.service"}


def test_main_only_rewrites_unit_dirs(mod, tmp_path, monkeypatch):
    outside = tmp_path / "docs" / "x"
    outside.mkdir(parents=True)
    stray = outside / "stray.service"
    stray.write_text("[Unit]\nA=1\n\n[Service]\nExecStart=/bin/x\n\n[Install]\nWantedBy=multi-user.target\n")
    monkeypatch.setattr(sys, "argv", ["harden-systemd-services.py", "--root", str(tmp_path)])
    mod.main()
    assert "PrivateTmp" not in stray.read_text()
    assert not stray.with_suffix(".service.bak").exists()
