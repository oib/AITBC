"""Fixture tests for BRIDGE_VALIDATOR_PRIVATE_KEY_FILE_<N> support.

Exercises ``_read_key_file`` + ``_collect_validator_private_keys`` from
``scripts/ops/register_bridge_validators.py``: a file-sourced validator key
must be mode-safe (0o077 clear), owned by the caller or root, non-empty,
and bound to its declared ``BRIDGE_VALIDATOR_ADDRESS_<N>`` when declared —
with no key material ever reaching stdout/stderr.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "ops"))
import register_bridge_validators as rbv  # noqa: E402

KEY_HEX = "01" * 32  # fixture key, derives to a known fixture address


@pytest.fixture(autouse=True)
def _clean_validator_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in (
        "BRIDGE_VALIDATOR_PRIVATE_KEY_1",
        "BRIDGE_VALIDATOR_PRIVATE_KEY_SOURCE_1",
        "BRIDGE_VALIDATOR_PRIVATE_KEY_FILE_1",
        "BRIDGE_VALIDATOR_ADDRESS_1",
        "BRIDGE_VALIDATOR_PRIVATE_KEY_2",
        "BRIDGE_VALIDATOR_PRIVATE_KEY_SOURCE_2",
        "BRIDGE_VALIDATOR_PRIVATE_KEY_FILE_2",
        "BRIDGE_ADMIN_PRIVATE_KEY",
        "BRIDGE_ADMIN_PRIVATE_KEY_FILE",
        "BRIDGE_ADMIN_PRIVATE_KEY_SOURCE",
        "BRIDGE_ADMIN_ADDRESS",
        "PROPOSER_KEY",
        "GENESIS_PRIVATE_KEY",
    ):
        monkeypatch.delenv(var, raising=False)


def _key_file(tmp_path: Path, mode: int = 0o600, contents: str = KEY_HEX) -> Path:
    f = tmp_path / "validator.key"
    f.write_text(contents)
    f.chmod(mode)
    return f


def test_file_source_collects_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    f = _key_file(tmp_path)
    monkeypatch.setenv("BRIDGE_VALIDATOR_PRIVATE_KEY_FILE_1", str(f))
    assert rbv._collect_validator_private_keys() == [("validator-1", KEY_HEX)]


def test_file_source_binds_declared_address(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    derived, _ = rbv._derive_address_and_public_key(KEY_HEX)
    f = _key_file(tmp_path)
    monkeypatch.setenv("BRIDGE_VALIDATOR_PRIVATE_KEY_FILE_1", str(f))
    monkeypatch.setenv("BRIDGE_VALIDATOR_ADDRESS_1", derived)
    assert rbv._collect_validator_private_keys() == [("validator-1", KEY_HEX)]


def test_file_source_refuses_group_readable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    f = _key_file(tmp_path, mode=0o640)
    monkeypatch.setenv("BRIDGE_VALIDATOR_PRIVATE_KEY_FILE_1", str(f))
    with pytest.raises(SystemExit) as exc:
        rbv._collect_validator_private_keys()
    assert exc.value.code == 1


def test_file_source_refuses_wrong_owner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    f = _key_file(tmp_path)
    if os.geteuid() == 0:
        # Running as root the tmp file is uid-0-owned — allowed by the check
        # (st_uid in (euid, 0)). Chown to a foreign uid so the refusal is real.
        os.chown(f, 12345, 12345)
    monkeypatch.setenv("BRIDGE_VALIDATOR_PRIVATE_KEY_FILE_1", str(f))
    monkeypatch.setattr(os, "geteuid", lambda: 99999)  # file owned by us, not 99999 or root
    with pytest.raises(SystemExit) as exc:
        rbv._collect_validator_private_keys()
    assert exc.value.code == 1


def test_file_source_address_mismatch_dies(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    f = _key_file(tmp_path)
    monkeypatch.setenv("BRIDGE_VALIDATOR_PRIVATE_KEY_FILE_1", str(f))
    monkeypatch.setenv("BRIDGE_VALIDATOR_ADDRESS_1", "0x0000000000000000000000000000000000000001")
    with pytest.raises(SystemExit) as exc:
        rbv._collect_validator_private_keys()
    assert exc.value.code == 1


def test_file_source_empty_dies(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    f = _key_file(tmp_path, contents="")
    monkeypatch.setenv("BRIDGE_VALIDATOR_PRIVATE_KEY_FILE_1", str(f))
    with pytest.raises(SystemExit):
        rbv._collect_validator_private_keys()


def test_no_key_material_in_die_output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    f = _key_file(tmp_path, mode=0o644)
    monkeypatch.setenv("BRIDGE_VALIDATOR_PRIVATE_KEY_FILE_1", str(f))
    with pytest.raises(SystemExit):
        rbv._collect_validator_private_keys()
    out = capsys.readouterr()
    assert KEY_HEX not in out.out and KEY_HEX not in out.err
    assert str(f) in out.err  # path is named, contents never are


# --- admin BRIDGE_ADMIN_PRIVATE_KEY_FILE: same hardening (A34-5) ---


def test_admin_file_collects_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Identical behaviour for a correctly protected file."""
    f = _key_file(tmp_path)
    monkeypatch.setenv("BRIDGE_ADMIN_PRIVATE_KEY_FILE", str(f))
    assert rbv._get_admin_private_key() == KEY_HEX


def test_admin_file_refuses_group_readable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    f = _key_file(tmp_path, mode=0o640)
    monkeypatch.setenv("BRIDGE_ADMIN_PRIVATE_KEY_FILE", str(f))
    with pytest.raises(SystemExit):
        rbv._get_admin_private_key()


def test_admin_file_refuses_wrong_owner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    f = _key_file(tmp_path)
    if os.geteuid() == 0:
        os.chown(f, 12345, 12345)
    monkeypatch.setenv("BRIDGE_ADMIN_PRIVATE_KEY_FILE", str(f))
    monkeypatch.setattr(os, "geteuid", lambda: 99999)
    with pytest.raises(SystemExit):
        rbv._get_admin_private_key()


def test_admin_file_refuses_symlink_out_of_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    target = _key_file(outside)
    link = tmp_path / "key.link"
    link.symlink_to(target)
    monkeypatch.setenv("BRIDGE_ADMIN_PRIVATE_KEY_FILE", str(link))
    with pytest.raises(SystemExit):
        rbv._get_admin_private_key()


def test_admin_file_allows_symlink_within_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = _key_file(tmp_path)
    link = tmp_path / "key.link"
    link.symlink_to(target)
    monkeypatch.setenv("BRIDGE_ADMIN_PRIVATE_KEY_FILE", str(link))
    assert rbv._get_admin_private_key() == KEY_HEX
