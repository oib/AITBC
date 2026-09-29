"""Parity between the fleet digest monitor's embedded spec and the repo's
table classification.

``fleet-config-check.sh`` embeds a fallback copy of the digest spec for
control hosts without an importable checkout. The authoritative source is
``aitbc_chain.state.block_deltas`` (table classification, volatile columns,
address columns, allowlists) plus ``aitbc_chain.aux_state.AUX_TABLES`` —
this test fails if either side of the mirror drifts.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / "scripts" / "monitoring" / "fleet-config-check.sh"
SPEC_GEN = REPO_ROOT / "scripts" / "monitoring" / "state-digest-spec.py"


def _load_spec_gen():
    import importlib.util

    spec = importlib.util.spec_from_file_location("state_digest_spec", SPEC_GEN)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


def _embedded_spec() -> dict:
    text = SCRIPT.read_text()
    m = re.search(r"^DIGEST_SPEC_FALLBACK='(.*)'$", text, re.MULTILINE)
    assert m, "DIGEST_SPEC_FALLBACK line not found in fleet-config-check.sh"
    return json.loads(m.group(1))


def test_embedded_spec_matches_repo_constants():
    build_spec = _load_spec_gen().build_spec

    generated = build_spec()
    embedded = _embedded_spec()
    # Compare normalized (sorted keys) — generation emits sort_keys=True.
    assert json.loads(json.dumps(embedded, sort_keys=True)) == json.loads(json.dumps(generated, sort_keys=True)), (
        "DIGEST_SPEC_FALLBACK in fleet-config-check.sh is stale — regenerate it with scripts/monitoring/state-digest-spec.py"
    )


def test_classification_covers_all_tables():
    import aitbc_chain.database  # noqa: F401 — registers every model
    from aitbc_chain.metadata import chain_metadata
    from aitbc_chain.state.block_deltas import CONSENSUS_STATE_TABLES, SERVICE_STATE_TABLES

    all_tables = set(chain_metadata.tables)
    classified = set(CONSENSUS_STATE_TABLES) | set(SERVICE_STATE_TABLES)
    assert not (all_tables - classified), f"unclassified tables: {sorted(all_tables - classified)}"
    assert not (classified - all_tables), f"classified but absent from metadata: {sorted(classified - all_tables)}"
    assert not (set(CONSENSUS_STATE_TABLES) & set(SERVICE_STATE_TABLES))


def test_aux_shipped_mirror():
    from aitbc_chain.aux_state import AUX_TABLES
    from aitbc_chain.state.block_deltas import AUX_SHIPPED_TABLES

    shipped = {spec.model.__tablename__ for spec in AUX_TABLES.values()}
    assert set(AUX_SHIPPED_TABLES) == shipped


def test_governance_vote_service_local_but_dup_hard():
    """governance_vote is service-local RPC bookkeeping (apply never reads
    it) and must not be aux-shipped, yet its per-host (proposal_id,
    lower(voter_address)) duplicate invariant stays a hard failure."""
    build_spec = _load_spec_gen().build_spec

    generated = build_spec()
    assert generated["tables"]["governance_vote"]["class"] == "service"
    assert "governance_vote" in generated["dup_hard"]
    assert generated["dupkeys"]["governance_vote"] == {
        "key": ["proposal_id", "voter_address"],
        "addr": ["voter_address"],
    }


def test_digest_keeps_semantic_columns():
    """No consensus/aux table may lose every column to the volatile set —
    the digest would hash an empty projection and always match."""
    import aitbc_chain.database  # noqa: F401
    from aitbc_chain.metadata import chain_metadata
    from aitbc_chain.state.block_deltas import (
        AUX_SHIPPED_TABLES,
        CONSENSUS_STATE_TABLES,
        DIGEST_COLUMN_ALLOWLIST,
        VOLATILE_DIGEST_COLUMNS,
    )

    for name in sorted(set(CONSENSUS_STATE_TABLES) | set(AUX_SHIPPED_TABLES)):
        table = chain_metadata.tables[name]
        cols = {c.name for c in table.columns}
        allow = DIGEST_COLUMN_ALLOWLIST.get(name)
        keep = cols - set(VOLATILE_DIGEST_COLUMNS)
        if allow is not None:
            keep &= set(allow)
        assert keep, f"{name}: volatile columns consumed the whole table"


def test_volatile_columns_exist_somewhere():
    """Volatile entries should name real columns somewhere in the schema —
    a typo'd name silently never excludes anything."""
    import aitbc_chain.database  # noqa: F401
    from aitbc_chain.metadata import chain_metadata
    from aitbc_chain.state.block_deltas import VOLATILE_DIGEST_COLUMNS

    known = {c.name for t in chain_metadata.tables.values() for c in t.columns}
    unused = set(VOLATILE_DIGEST_COLUMNS) - known
    # `confirmed_at`/`updated` are defensive generics for future/historical
    # schemas — keep the assert to names with no column anywhere.
    unexpected = unused - {"confirmed_at", "updated"}
    assert not unexpected, f"volatile columns that exist nowhere: {sorted(unexpected)}"


def test_remote_helper_end_to_end(tmp_path):
    """The stdlib remote helper produces stable digests on a seeded DB and
    detects a checksum/lowercase natural-key twin."""
    import sqlite3
    import subprocess

    build_spec = _load_spec_gen().build_spec

    db = tmp_path / "chain.db"
    con = sqlite3.connect(db)
    con.execute(
        "CREATE TABLE governance_vote (id INTEGER PRIMARY KEY, chain_id TEXT,"
        " proposal_id TEXT, voter_address TEXT, vote_type TEXT, voting_power INTEGER,"
        " reason TEXT, created_at TEXT)"
    )
    con.execute("CREATE TABLE account (chain_id TEXT, address TEXT, balance INTEGER, nonce INTEGER, updated_at TEXT)")
    con.execute(
        "INSERT INTO governance_vote (chain_id, proposal_id, voter_address, vote_type, voting_power)"
        " VALUES ('test','p1','0xAbCd','for',10)"
    )
    con.execute(
        "INSERT INTO governance_vote (chain_id, proposal_id, voter_address, vote_type, voting_power)"
        " VALUES ('test','p1','0xabcd','for',10)"
    )
    con.execute("INSERT INTO account VALUES ('test','0xAbCd',100,1,'2026-01-01 00:00:00.000000')")
    con.commit()
    con.close()

    spec = json.dumps(build_spec())
    helper = REPO_ROOT / "scripts" / "monitoring" / "state-digest-remote.py"
    out = subprocess.run(
        [sys.executable, str(helper), str(db), "test", spec],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    result = json.loads(out)
    assert result["tables"]["account"]["rows"] == 1
    # The twin rows differ only in address case → one dup group reported.
    assert result["dupes"]["governance_vote"] == [["p1", "0xabcd", 2]]


def test_helper_digest_normalizes_case_and_datetimes(tmp_path):
    """Identical rows stored with different address casing / datetime
    separators must hash equal — that's the semantic the monitor asserts."""
    import sqlite3
    import subprocess

    build_spec = _load_spec_gen().build_spec

    spec = json.dumps(build_spec())
    helper = REPO_ROOT / "scripts" / "monitoring" / "state-digest-remote.py"
    digests = []
    for i, (addr, ts) in enumerate(
        [
            ("0x02B8F2C61DB19B04aB68cfb43d0605E63dE74c5B", "2026-01-01 00:00:00.5"),
            ("0x02b8f2c61db19b04ab68cfb43d0605e63de74c5b", "2026-01-01T00:00:00.500000"),
        ]
    ):
        db = tmp_path / f"c{i}.db"
        con = sqlite3.connect(db)
        con.execute("CREATE TABLE account (chain_id TEXT, address TEXT, balance INTEGER, nonce INTEGER, updated_at TEXT)")
        con.execute("INSERT INTO account VALUES ('test',?,100,1,?)", (addr, ts))
        con.commit()
        con.close()
        out = subprocess.run(
            [sys.executable, str(helper), str(db), "test", spec],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        digests.append(json.loads(out)["tables"]["account"]["digest"])
    assert digests[0] == digests[1]
