"""Fixture tests for scripts/ops/watch_drift_check.py.

Fixtures use the standard eth dev keys ``\\x01``*32 / ``\\x02``*32 — public
test vectors, never real keys. No host is touched; ``--env-dir`` points at a
tmp dir.
"""

import io
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "ops"))

import watch_drift_check as wdc  # noqa: E402

KEY_A = "0x" + "01" * 32
KEY_B = "0x" + "02" * 32
CANARY_KEY = "0x" + "aa" * 32  # not bound to any role; proves no key leaks

# Derived through the implementation under test — these are public test
# vectors, never real keys.
ADDR_A = wdc.derive_address(KEY_A)
ADDR_B = wdc.derive_address(KEY_B)

UNIT = """[Service]
Environment=AITBC_WATCH_ACCOUNTS=escrow_settlement:0x1111111111111111111111111111111111111111,bond_slash:0x2222222222222222222222222222222222222222,governance_proposer:{prop},validator_hub:{val},proposer_retired:0x4444444444444444444444444444444444444444
ExecStart=/bin/true
"""


@pytest.fixture()
def env_dir(tmp_path: Path) -> Path:
    (tmp_path / "aitbc-governance.env").write_text(f"# governance env\nGOVERNANCE_PROPOSER_PRIVATE_KEY={KEY_A}\n")
    (tmp_path / "validator-secrets.env").write_text(f"PROPOSER_ID=0xsomething\nPROPOSER_KEY={KEY_B}\n")
    (tmp_path / "other.env").write_text(f"UNRELATED={CANARY_KEY}\n")
    return tmp_path


def run(unit_text: str, env_dir: Path) -> tuple[int, str]:
    out = io.StringIO()
    rc = wdc.check(unit_text, env_dir, out=out)
    return rc, out.getvalue()


def test_all_ok(env_dir: Path) -> None:
    rc, text = run(UNIT.format(prop=ADDR_A, val=ADDR_B), env_dir)
    assert rc == 0
    assert "OK" in text and "governance_proposer" in text and "validator_hub" in text
    assert ADDR_A in text and ADDR_B.lower() in text.lower()


def test_mismatch_exits_1(env_dir: Path) -> None:
    # watch entry for the proposer still carries KEY_B's address.
    rc, text = run(UNIT.format(prop=ADDR_B, val=ADDR_B), env_dir)
    assert rc == 1
    mismatched = [ln for ln in text.splitlines() if "MISMATCH" in ln]
    assert len(mismatched) == 1 and "governance_proposer" in mismatched[0]


def test_parameter_and_retired_roles_skip(env_dir: Path) -> None:
    rc, text = run(UNIT.format(prop=ADDR_A, val=ADDR_B), env_dir)
    assert rc == 0
    for role in ("escrow_settlement", "bond_slash", "proposer_retired"):
        line = next(ln for ln in text.splitlines() if role in ln)
        assert line.startswith("SKIP"), line


def test_missing_env_var_is_error(env_dir: Path) -> None:
    (env_dir / "validator-secrets.env").unlink()
    rc, text = run(UNIT.format(prop=ADDR_A, val=ADDR_B), env_dir)
    assert rc == 1
    assert any("ERROR" in ln and "validator_hub" in ln for ln in text.splitlines())


def test_no_key_material_printed(env_dir: Path) -> None:
    rc, text = run(UNIT.format(prop=ADDR_A, val=ADDR_B), env_dir)
    assert rc == 0
    for needle in (KEY_A[2:], KEY_B[2:], CANARY_KEY[2:], "PROPOSER_KEY=", "PRIVATE_KEY="):
        assert needle not in text


def test_known_derivation_vector() -> None:
    # Private key 0x00..01 maps to the well-known generator-point address —
    # pins the derivation to a published vector, not just self-consistency.
    assert wdc.derive_address("0x" + "0" * 63 + "1") == "0x7e5f4552091a69125d5dfcb7b8c2659029395bdf"


def test_unparsable_watch_entry_is_error(env_dir: Path) -> None:
    rc, text = run("Environment=AITBC_WATCH_ACCOUNTS=bad-entry\n", env_dir)
    assert rc == 1
    assert "ERROR" in text
