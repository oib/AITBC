"""Tests for scripts/ops/check-alloc-file.py (RESET-ALLOC-FILE-1 #332).

Placeholder addresses only: every address is ``canonical_address`` over a
fixed keccak seed — no wallet, keystore, or live address anywhere. The real
operator allocation file and class manifest drop into the same CLI flags
unchanged.
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "ops" / "check-alloc-file.py"
spec = importlib.util.spec_from_file_location("check_alloc_file", SCRIPT)
caf = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = caf
spec.loader.exec_module(caf)

# Loading the module does not touch aitbc_chain (lazy imports); the fixture
# needs the real address helpers, which _chain_modules() wires up.
canonical_address, keccak = caf._chain_modules()


def _addr(seed: str) -> str:
    return canonical_address("0x" + keccak(f"alloc-test-{seed}".encode()).hex()[:40])


SERVICE_NAMES = [
    "aiengine",
    "market-service",
    "coordinator-service",
    "trading-service",
    "exchange-service",
    "agent-coordinator",
    "pool-hub",
    "gpu-service",
    "edge-service",
    "ait-sell-escrow",
    "bridge-monitor",
]
AUTHORITY_NAMES = ["bond_slash", "bridge_release", "escrow_settlement"]


@pytest.fixture()
def bond_env_clear(monkeypatch):
    """Derived bond addresses depend on BOND_*_ADDRESS env overrides — pin
    them unset so the fixture uses the keccak defaults."""
    monkeypatch.delenv("BOND_ESCROW_ADDRESS", raising=False)
    monkeypatch.delenv("BOND_BURN_ADDRESS", raising=False)


@pytest.fixture()
def valid(bond_env_clear, tmp_path):
    """A fully-valid allocations file + class manifest on placeholder
    addresses, matching PARAMS exactly."""
    classes = {
        "treasury": _addr("treasury"),
        "service_floats": {name: _addr(f"svc-{name}") for name in SERVICE_NAMES},
        "executors": [_addr(f"exec-{i}") for i in range(2)],
        "authorities": {name: _addr(f"auth-{name}") for name in AUTHORITY_NAMES},
        "ops_float": _addr("ops-float"),
        "retired": [_addr(f"retired-{i}") for i in range(3)],
        "faucet": _addr("faucet"),
    }
    bonds = caf._bond_addresses()
    small = [classes["service_floats"][n] for n in SERVICE_NAMES]
    small += classes["executors"]
    small += list(classes["authorities"].values())
    allocs = [{"address": classes["treasury"], "balance": caf.TREASURY_UNITS, "nonce": 0}]
    allocs += [{"address": a, "balance": caf.SERVICE_UNITS, "nonce": 0} for a in small]
    ops_balance = caf.FLOAT_UNITS - len(small) * caf.SERVICE_UNITS
    allocs.append({"address": classes["ops_float"], "balance": ops_balance, "nonce": 0})
    allocs += [{"address": a, "balance": 0, "nonce": 0} for a in classes["retired"]]
    allocs.append({"address": classes["faucet"], "balance": caf.PARAMS["faucet_ait"] * caf.UNITS_PER_AIT, "nonce": 0})
    allocs += [{"address": a, "balance": 0, "nonce": 0} for a in bonds]

    alloc_path = tmp_path / "allocations.json"
    class_path = tmp_path / "classes.json"
    alloc_path.write_text(json.dumps(allocs))
    class_path.write_text(json.dumps(classes))
    return alloc_path, class_path, allocs, classes


def _run(capsys, *argv) -> tuple[int, str]:
    code = caf.main(list(argv))
    return code, capsys.readouterr().out


# ---------- positive paths ----------


def test_valid_file_passes_with_classes(valid, capsys):
    alloc_path, class_path, _, _ = valid
    code, out = _run(capsys, "--allocations", str(alloc_path), "--classes", str(class_path), "--require-classes")
    assert code == 0 and "PASS" in out and "FAIL" not in out
    for cls in ("treasury", "service_floats", "executors", "authorities", "retired", "faucet", "bond", "float band"):
        assert cls in out


def test_independent_checks_without_classes(valid, capsys):
    alloc_path, _, _, _ = valid
    code, out = _run(capsys, "--allocations", str(alloc_path))
    assert code == 0 and "PASS" in out and "SKIP" in out


def test_require_classes_refuses_without_manifest(valid):
    alloc_path, _, _, _ = valid
    code = caf.main(["--allocations", str(alloc_path), "--require-classes"])
    assert code == 2


def test_missing_allocations_file_fails(tmp_path, capsys):
    code, out = _run(capsys, "--allocations", str(tmp_path / "nope.json"))
    assert code == 1 and "cannot read" in out


# ---------- negative paths (director list) ----------


def test_treasury_in_whole_units_fails(valid, capsys):
    """The classic denomination bug: 100_000_000 instead of 100M*36M base units."""
    alloc_path, class_path, allocs, _ = valid
    allocs[0]["balance"] = caf.PARAMS["treasury_ait"]
    alloc_path.write_text(json.dumps(allocs))
    code, out = _run(capsys, "--allocations", str(alloc_path), "--classes", str(class_path))
    assert code == 1 and "supply" in out and "FAIL" in out


def test_lowercase_address_fails(valid, capsys):
    alloc_path, class_path, allocs, classes = valid
    allocs[0]["address"] = allocs[0]["address"].lower()
    alloc_path.write_text(json.dumps(allocs))
    code, out = _run(capsys, "--allocations", str(alloc_path), "--classes", str(class_path))
    assert code == 1 and "not an EIP-55 checksummed" in out


def test_duplicate_address_fails(valid, capsys):
    alloc_path, class_path, allocs, _ = valid
    allocs.append({"address": allocs[0]["address"], "balance": 1, "nonce": 0})
    alloc_path.write_text(json.dumps(allocs))
    code, out = _run(capsys, "--allocations", str(alloc_path), "--classes", str(class_path))
    assert code == 1 and "duplicated address" in out


def test_nonzero_faucet_fails(valid, capsys):
    alloc_path, class_path, allocs, classes = valid
    faucet = classes["faucet"].lower()
    for row in allocs:
        if row["address"].lower() == faucet:
            row["balance"] = caf.SERVICE_UNITS
    alloc_path.write_text(json.dumps(allocs))
    code, out = _run(capsys, "--allocations", str(alloc_path), "--classes", str(class_path))
    assert code == 1 and "must sit at balance 0" in out


def test_missing_bond_account_fails(bond_env_clear, valid, capsys):
    alloc_path, class_path, allocs, _ = valid
    bond = caf._bond_addresses()[0].lower()
    allocs = [a for a in allocs if a["address"].lower() != bond]
    alloc_path.write_text(json.dumps(allocs))
    code, out = _run(capsys, "--allocations", str(alloc_path), "--classes", str(class_path))
    assert code == 1 and "bond account" in out and "missing" in out


def test_treasury_also_listed_as_service_fails(valid, capsys):
    alloc_path, class_path, allocs, classes = valid
    classes["service_floats"]["aiengine"] = classes["treasury"]
    class_path.write_text(json.dumps(classes))
    code, out = _run(capsys, "--allocations", str(alloc_path), "--classes", str(class_path))
    assert code == 1 and "listed in both" in out


def test_total_off_by_one_fails(valid, capsys):
    alloc_path, class_path, allocs, _ = valid
    allocs[0]["balance"] += 1
    alloc_path.write_text(json.dumps(allocs))
    code, out = _run(capsys, "--allocations", str(alloc_path), "--classes", str(class_path))
    assert code == 1 and "off by +1" in out


def test_stray_funded_row_fails(valid, capsys):
    alloc_path, class_path, allocs, _ = valid
    allocs.append({"address": _addr("stray"), "balance": 1, "nonce": 0})
    alloc_path.write_text(json.dumps(allocs))
    code, out = _run(capsys, "--allocations", str(alloc_path), "--classes", str(class_path))
    assert code == 1 and "no listed class" in out


# ---------- treasury spendability proof (--treasury-proof) ----------


def _scratch_account():
    """A deterministic scratch key — generated, never a live wallet."""
    from eth_account import Account

    return Account.from_key(keccak(b"check-alloc-treasury-scratch"))


def _rebind_treasury(valid, acct):
    """Point the valid fixture's treasury at the scratch key's address."""
    alloc_path, class_path, allocs, classes = valid
    old = classes["treasury"].lower()
    classes["treasury"] = acct.address
    for row in allocs:
        if row["address"].lower() == old:
            row["address"] = acct.address
    alloc_path.write_text(json.dumps(allocs))
    class_path.write_text(json.dumps(classes))
    return alloc_path, class_path


def _write_proof(tmp_path, acct, *, message=None, address=None, signature=None):
    from eth_account.messages import encode_defunct

    msg = message if message is not None else caf.treasury_challenge(address or acct.address)
    sig = signature if signature is not None else acct.sign_message(encode_defunct(text=msg)).signature.hex()
    path = tmp_path / "treasury-proof.json"
    path.write_text(json.dumps({"address": address or acct.address, "message": msg, "signature": sig}))
    return path


def test_treasury_proof_passes(valid, tmp_path, capsys):
    acct = _scratch_account()
    alloc_path, class_path = _rebind_treasury(valid, acct)
    proof = _write_proof(tmp_path, acct)
    code, out = _run(capsys, "--allocations", str(alloc_path), "--classes", str(class_path), "--treasury-proof", str(proof))
    assert code == 0 and "treasury proof" in out and "WARNING" not in out


def test_no_proof_warns_but_passes(valid, capsys):
    alloc_path, class_path, _, _ = valid
    code, out = _run(capsys, "--allocations", str(alloc_path), "--classes", str(class_path))
    assert code == 0 and "treasury spendability unproven" in out and "treasury proof challenge:" in out


def test_proof_wrong_signer_fails(valid, tmp_path, capsys):
    """Signed by a different key — recovery cannot equal the claimed address."""
    from eth_account import Account
    from eth_account.messages import encode_defunct

    acct = _scratch_account()
    alloc_path, class_path = _rebind_treasury(valid, acct)
    other = Account.from_key(keccak(b"check-alloc-other-scratch"))
    msg = caf.treasury_challenge(acct.address)
    proof = tmp_path / "treasury-proof.json"
    proof.write_text(
        json.dumps(
            {
                "address": acct.address,
                "message": msg,
                "signature": other.sign_message(encode_defunct(text=msg)).signature.hex(),
            }
        )
    )
    code, out = _run(capsys, "--allocations", str(alloc_path), "--classes", str(class_path), "--treasury-proof", str(proof))
    assert code == 1 and "signer" in out and "!=" in out


def test_proof_not_treasury_fails(valid, tmp_path, capsys):
    """A valid signature from the wrong account does not prove the treasury."""
    from eth_account import Account

    alloc_path, class_path, _, _ = valid  # treasury stays a non-key placeholder address
    other = Account.from_key(keccak(b"check-alloc-other-scratch"))
    proof = _write_proof(tmp_path, other)
    code, out = _run(capsys, "--allocations", str(alloc_path), "--classes", str(class_path), "--treasury-proof", str(proof))
    assert code == 1 and "!= treasury" in out


def test_proof_wrong_message_fails(valid, tmp_path, capsys):
    acct = _scratch_account()
    alloc_path, class_path = _rebind_treasury(valid, acct)
    proof = _write_proof(tmp_path, acct, message="some other message")
    code, out = _run(capsys, "--allocations", str(alloc_path), "--classes", str(class_path), "--treasury-proof", str(proof))
    assert code == 1 and "challenge" in out


def test_proof_malformed_signature_fails(valid, tmp_path, capsys):
    acct = _scratch_account()
    alloc_path, class_path = _rebind_treasury(valid, acct)
    proof = _write_proof(tmp_path, acct, signature="0xdeadbeef")
    code, out = _run(capsys, "--allocations", str(alloc_path), "--classes", str(class_path), "--treasury-proof", str(proof))
    assert code == 1 and "unrecoverable" in out


def test_proof_missing_field_fails(valid, tmp_path, capsys):
    alloc_path, class_path, _, classes = valid
    path = tmp_path / "treasury-proof.json"
    path.write_text(json.dumps({"address": classes["treasury"], "message": caf.treasury_challenge(classes["treasury"])}))
    code, out = _run(capsys, "--allocations", str(alloc_path), "--classes", str(class_path), "--treasury-proof", str(path))
    assert code == 1 and "signature" in out


# ---------- PARAMS mirror (numbers, not the sentence — coder A rewords A2) ----------


def test_params_match_runbook_a2_numbers():
    """Every decided figure must still appear numerically in the runbook's A2
    row — tolerant of rewording, strict on the numbers."""
    runbook = Path(__file__).resolve().parents[2] / "docs" / "deployment" / "bc2-reset-runbook.md"
    a2 = next(line for line in runbook.read_text().splitlines() if line.startswith("| A2 "))
    numbers = {int(n.replace(",", "").replace("_", "")) for n in re.findall(r"[0-9][0-9,_]*", a2)}
    # supply is derivable (treasury + floats) and is not required in the row
    expected = {
        caf.PARAMS["units_per_ait"],  # 36,000,000
        caf.PARAMS["float_ait"],  # 256
        caf.PARAMS["service_accounts"],  # 11
        caf.PARAMS["retired_accounts"],  # 3
        caf.PARAMS["bond_accounts"],  # 2
    }
    missing = {n for n in expected if n not in numbers}
    assert not missing, f"A2 row lost decided figure(s) {missing}: {a2.strip()}"
    # treasury: 100M written as "100M", "100,000,000" or "100_000_000"
    assert "100M" in a2 or caf.PARAMS["treasury_ait"] in numbers, f"A2 row lost the treasury figure: {a2.strip()}"
    # faucet sits at zero
    assert 0 in numbers or "faucet 0" in a2, f"A2 row lost the faucet figure: {a2.strip()}"


def test_params_self_consistent():
    """The single edit point must stay internally consistent: supply equals
    treasury plus the float band, and the derived constants agree."""
    p = caf.PARAMS
    assert p["supply_ait"] == p["treasury_ait"] + p["float_ait"]
    assert caf.EXPECTED_TOTAL_UNITS == p["supply_ait"] * p["units_per_ait"]
    assert caf.TREASURY_UNITS == p["treasury_ait"] * p["units_per_ait"]
    assert caf.SERVICE_UNITS == p["service_ait_each"] * p["units_per_ait"]
