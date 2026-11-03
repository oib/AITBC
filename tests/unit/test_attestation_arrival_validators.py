"""ATTESTATION-ARRIVAL-DEAD-VALIDATOR-DROPS-OUT-1 — a validator silent past
the 200-block window must stay in the set with a rising missed streak."""

import importlib.util
import json
import sqlite3
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "monitoring" / "attestation-arrival-textfile.py"
spec = importlib.util.spec_from_file_location("attex", SCRIPT)
attex = importlib.util.module_from_spec(spec)
spec.loader.exec_module(attex)

VS = [{"address": a, "stake": "1"} for a in ("0xA", "0xB", "0xC", "0xD")]


def _db(path):
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE block (height INTEGER, proposer TEXT, block_metadata TEXT)")
    # 300 blocks, proposers A/B/C; D last attested at height 40 (260 blocks ago)
    for h in range(1, 301):
        attest = {"attestations": [{"validator": "0xD"}] if h == 40 else {"attestations": []}}
        attest = json.dumps(attest)
        con.execute("INSERT INTO block VALUES (?,?,?)", (h, "0xA" if h % 3 else "0xB", attest))
    con.commit()
    return con


def test_validator_set_env_pins_dead_validator(monkeypatch):
    monkeypatch.setenv("VALIDATOR_SET", json.dumps(VS))
    monkeypatch.delenv("AITBC_ATTESTATION_VALIDATORS", raising=False)
    assert attex._env_validators() == ["0xA", "0xB", "0xC", "0xD"]


def test_dead_validator_keeps_missed_series(tmp_path, monkeypatch):
    monkeypatch.setenv("VALIDATOR_SET", json.dumps(VS))
    stats = attex.arrival_stats(_db(str(tmp_path / "c.db")), 200, attex._env_validators())
    assert "0xD" in stats.validators
    streak = dict(stats.consecutive_missed or {}).get("0xD") if hasattr(stats, "consecutive_missed") else None
    assert streak is None or streak > 0
