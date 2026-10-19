"""RESET-GENESIS-BUILDER-1 Phase 1 tests.

Covers the pure ``build_genesis_doc``, the loader's consumption of a built
file (parameters at height 0, bridge-validator digest + row seeding through
the shared ``insert_bridge_validator``), register-route parity for the
extracted helper, the DATA_DIR-aware genesis path fix, and the scratch/live
CLI refusal paths. All addresses are synthetic test fixtures — no real
wallet or key material is used.
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path

import pytest
from aitbc_chain.config import ProposerConfig
from aitbc_chain.consensus.poa import PoAProposer
from aitbc_chain.genesis_builder import (
    GenesisBuildError,
    bridge_validators_digest,
    build_genesis_doc,
    check_live_conditions,
)
from aitbc_chain.base_models import ChainParameter
from aitbc_chain.models import Account, Block, BridgeValidator
from sqlmodel import Session, create_engine, select

from aitbc_chain.metadata import chain_metadata

CHAIN_ID = "bc-2.test"

ADDR_A = "0xF5A930bBC90c15dB0bbf28f8485D18eEf24c3F43"
ADDR_B = "0x71C7656EC7ab88b098defB751B7401B5f6d8976F"
ADDR_C = "0xcE7d4a5f5A5d9dD5320A053fA00ee5C0fa0C1b2f"
ADDR_D = "0xAFDcE2F27d3970db25bdC2e9B1b31Bd247145B7C"

PUBKEY = "0x" + "aa" * 33  # compressed-pubkey-shaped hex

PARAMS = {
    "governance_executors": f"{ADDR_A.lower()},{ADDR_B.lower()}",
    "escrow_settlement_authority": ADDR_C.lower(),
    "bond_slash_authority": ADDR_D.lower(),
    "bridge_release_authority": ADDR_A.lower(),
    "escrow_fee_recipient": ADDR_B.lower(),
}

VALIDATORS = [
    {"address": ADDR_A, "public_key": PUBKEY, "epoch": 1},
    {"address": ADDR_B, "public_key": PUBKEY, "epoch": 1},
    {"address": ADDR_C, "public_key": PUBKEY, "epoch": 1},
    {"address": ADDR_D, "public_key": PUBKEY, "epoch": 1},
]

ALLOCS = [
    {"address": ADDR_A, "balance": 100},
    {"address": ADDR_B, "balance": 200},
]


# ---------------------------------------------------------------------------
# build_genesis_doc
# ---------------------------------------------------------------------------


def test_build_doc_emits_loader_contract() -> None:
    doc = build_genesis_doc(
        chain_id=CHAIN_ID,
        allocations=ALLOCS,
        parameters=PARAMS,
        bridge_validators=VALIDATORS,
        timestamp="2026-10-19T12:00:00+00:00",
        expected_total=300,
    )
    assert doc["chain_id"] == CHAIN_ID
    assert doc["genesis_hash"].startswith("0x")
    assert doc["state_root"].startswith("0x")
    assert doc["bridge_validators_digest"] == bridge_validators_digest(VALIDATORS, chain_id=CHAIN_ID)
    assert all(r["chain_id"] == CHAIN_ID for r in doc["bridge_validators"])
    assert all(r["address"] == r["address"].lower() for r in doc["bridge_validators"])


def test_z_suffix_timestamp_is_refused() -> None:
    with pytest.raises(GenesisBuildError, match="round-trip"):
        build_genesis_doc(chain_id=CHAIN_ID, allocations=ALLOCS, timestamp="2026-10-19T12:00:00Z")


def test_duplicate_allocation_address_is_refused() -> None:
    # A case-variant duplicate is refused even earlier (on checksum — covered
    # by test_non_hex_address_is_refused); identical repeats exercise dedup.
    dup = [{"address": ADDR_A, "balance": 1}, {"address": ADDR_A, "balance": 2}]
    with pytest.raises(GenesisBuildError, match="duplicated address"):
        build_genesis_doc(chain_id=CHAIN_ID, allocations=dup)


def test_non_hex_address_is_refused() -> None:
    with pytest.raises(GenesisBuildError, match="not an EVM address"):
        build_genesis_doc(chain_id=CHAIN_ID, allocations=[{"address": "0xnothex", "balance": 1}])
    with pytest.raises(GenesisBuildError, match="not EIP-55 checksummed"):
        build_genesis_doc(chain_id=CHAIN_ID, allocations=[{"address": ADDR_A.lower(), "balance": 1}])


def test_total_mismatch_is_refused() -> None:
    with pytest.raises(GenesisBuildError, match="expected_total"):
        build_genesis_doc(chain_id=CHAIN_ID, allocations=ALLOCS, expected_total=999)


def test_doubled_0x_pubkey_is_refused() -> None:
    bad = [{"address": ADDR_A, "public_key": "0x0x" + "aa" * 33}]
    with pytest.raises(GenesisBuildError, match="doubled 0x"):
        build_genesis_doc(chain_id=CHAIN_ID, allocations=ALLOCS, bridge_validators=bad)


def test_empty_allocations_and_live_chain_id_are_refused() -> None:
    with pytest.raises(GenesisBuildError, match="non-empty"):
        build_genesis_doc(chain_id=CHAIN_ID, allocations=[])
    with pytest.raises(GenesisBuildError, match="live chain id"):
        build_genesis_doc(chain_id="ait-hub.aitbc.bubuit.net", allocations=ALLOCS)


def test_digest_is_order_independent() -> None:
    doc1 = build_genesis_doc(
        chain_id=CHAIN_ID, allocations=ALLOCS, bridge_validators=VALIDATORS, timestamp="2026-10-19T12:00:00+00:00"
    )
    doc2 = build_genesis_doc(
        chain_id=CHAIN_ID,
        allocations=ALLOCS,
        bridge_validators=list(reversed(VALIDATORS)),
        timestamp="2026-10-19T12:00:00+00:00",
    )
    assert doc1["bridge_validators_digest"] == doc2["bridge_validators_digest"]
    assert doc1["genesis_hash"] == doc2["genesis_hash"]


# ---------------------------------------------------------------------------
# loader consumption
# ---------------------------------------------------------------------------


@pytest.fixture
def session_factory(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'chain.db'}", echo=False)
    chain_metadata.create_all(engine)

    @contextmanager
    def _factory():
        with Session(engine) as session:
            yield session

    try:
        yield _factory
    finally:
        engine.dispose()


def _proposer(session_factory, chain_id: str = CHAIN_ID) -> PoAProposer:
    return PoAProposer(
        config=ProposerConfig(
            chain_id=chain_id,
            proposer_id="",
            interval_seconds=5,
            max_block_size_bytes=1_000_000,
            max_txs_per_block=100,
        ),
        session_factory=session_factory,
    )


def _built_doc(**overrides):
    kwargs = {
        "chain_id": CHAIN_ID,
        "allocations": ALLOCS,
        "parameters": PARAMS,
        "bridge_validators": VALIDATORS,
        "timestamp": "2026-10-19T12:00:00+00:00",
    }
    kwargs.update(overrides)
    return build_genesis_doc(**kwargs)


async def test_loader_loads_built_doc_and_seeds_params_and_validators(session_factory) -> None:
    node = _proposer(session_factory)
    from unittest.mock import AsyncMock, patch

    with (
        patch.object(PoAProposer, "_load_genesis_data_from_file", lambda self: _built_doc()),
        patch.object(PoAProposer, "_load_genesis_block_from_rpc", AsyncMock(return_value=None)),
    ):
        await node._ensure_genesis_block()

    with session_factory() as session:
        genesis = session.exec(select(Block).where(Block.chain_id == CHAIN_ID).where(Block.height == 0)).first()
        assert genesis is not None
        assert genesis.state_root == _built_doc()["state_root"]

        accounts = session.exec(select(Account).where(Account.chain_id == CHAIN_ID)).all()
        assert {a.address for a in accounts} == {ADDR_A, ADDR_B}

        params = session.exec(select(ChainParameter).where(ChainParameter.chain_id == CHAIN_ID)).all()
        assert {p.parameter: p.value for p in params} == {k: str(v) for k, v in PARAMS.items()}
        assert all(p.applied_height == 0 for p in params)

        rows = session.exec(select(BridgeValidator).where(BridgeValidator.chain_id == CHAIN_ID)).all()
        assert len(rows) == 4
        assert all(r.is_active and r.epoch == 1 for r in rows)
        assert all(r.address == r.address.lower() for r in rows)


async def test_digest_mismatch_is_refused(session_factory) -> None:
    doc = _built_doc()
    doc["bridge_validators_digest"] = "0x" + "ff" * 32
    node = _proposer(session_factory)
    from unittest.mock import AsyncMock, patch

    with (
        patch.object(PoAProposer, "_load_genesis_data_from_file", lambda self: doc),
        patch.object(PoAProposer, "_load_genesis_block_from_rpc", AsyncMock(return_value=None)),
    ):
        with pytest.raises(RuntimeError, match="digest mismatch"):
            await node._ensure_genesis_block()

    with session_factory() as session:
        assert session.exec(select(Block).where(Block.chain_id == CHAIN_ID).where(Block.height == 0)).first() is None
        assert session.exec(select(BridgeValidator).where(BridgeValidator.chain_id == CHAIN_ID)).all() == []


async def test_validators_without_digest_are_refused(session_factory) -> None:
    doc = _built_doc()
    del doc["bridge_validators_digest"]
    node = _proposer(session_factory)
    from unittest.mock import AsyncMock, patch

    with (
        patch.object(PoAProposer, "_load_genesis_data_from_file", lambda self: doc),
        patch.object(PoAProposer, "_load_genesis_block_from_rpc", AsyncMock(return_value=None)),
    ):
        with pytest.raises(RuntimeError, match="no bridge_validators_digest"):
            await node._ensure_genesis_block()


async def test_legacy_doc_without_validator_keys_still_loads(session_factory) -> None:
    doc = _built_doc()
    del doc["bridge_validators"]
    del doc["bridge_validators_digest"]
    node = _proposer(session_factory)
    from unittest.mock import AsyncMock, patch

    with (
        patch.object(PoAProposer, "_load_genesis_data_from_file", lambda self: doc),
        patch.object(PoAProposer, "_load_genesis_block_from_rpc", AsyncMock(return_value=None)),
    ):
        await node._ensure_genesis_block()

    with session_factory() as session:
        assert session.exec(select(Block).where(Block.chain_id == CHAIN_ID).where(Block.height == 0)).first() is not None


# ---------------------------------------------------------------------------
# DATA_DIR-aware genesis path
# ---------------------------------------------------------------------------


def test_load_genesis_data_honours_data_dir(tmp_path, monkeypatch) -> None:
    import aitbc.constants as constants

    doc = _built_doc()
    chain_dir = tmp_path / "data" / CHAIN_ID
    chain_dir.mkdir(parents=True)
    (chain_dir / "genesis.json").write_text(json.dumps(doc))
    # A stray chain-less file must not shadow the per-chain one.
    stray = tmp_path / "data" / "genesis.json"
    stray.write_text(json.dumps({"chain_id": "wrong", "allocations": []}))

    monkeypatch.setattr(constants, "DATA_DIR", tmp_path)
    node = _proposer(lambda: None)
    loaded = node._load_genesis_data_from_file()
    assert loaded["chain_id"] == CHAIN_ID
    assert loaded["allocations"] == doc["allocations"]


# ---------------------------------------------------------------------------
# register-route parity for insert_bridge_validator
# ---------------------------------------------------------------------------


def test_insert_bridge_validator_route_parity(session_factory) -> None:
    """The extracted helper writes the same row the old inline route code did.

    Insert path: all five columns set, registered_at non-null. Update path:
    re-registering the same (chain_id, address, epoch) refreshes pubkey,
    is_active and registered_at instead of duplicating the row.
    """
    from aitbc_chain.cross_chain.bridge_validator import insert_bridge_validator

    with session_factory() as session:
        insert_bridge_validator(session, CHAIN_ID, ADDR_A.lower(), PUBKEY, 1)
        session.commit()
        rows = session.exec(select(BridgeValidator).where(BridgeValidator.chain_id == CHAIN_ID)).all()
        assert len(rows) == 1
        row = rows[0]
        assert row.address == ADDR_A.lower()
        assert row.public_key == PUBKEY
        assert row.epoch == 1
        assert row.is_active
        assert row.registered_at is not None
        first_registered = row.registered_at

    with session_factory() as session:
        insert_bridge_validator(session, CHAIN_ID, ADDR_A.lower(), "0x" + "bb" * 33, 1)
        session.commit()
        rows = session.exec(select(BridgeValidator).where(BridgeValidator.chain_id == CHAIN_ID)).all()
        assert len(rows) == 1
        assert rows[0].public_key == "0x" + "bb" * 33
        assert rows[0].registered_at >= first_registered


# ---------------------------------------------------------------------------
# CLI scratch/live refusal paths
# ---------------------------------------------------------------------------


REPO_ROOT = Path(__file__).resolve().parents[3]
CLI = REPO_ROOT / "scripts" / "ops" / "build-genesis.py"
CHECKER = REPO_ROOT / "scripts" / "ops" / "verify-genesis-root.py"


def _script_main(path: Path):
    """Import an ops script by path and return its ``main`` (in-process)."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(path.stem.replace("-", "_"), path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.main


def _write_inputs(tmp_path: Path, *, chain_id: str = CHAIN_ID) -> tuple[Path, Path, Path]:
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"chain_id": chain_id, "expected_total_units": 300}))
    allocs = tmp_path / "allocations.json"
    allocs.write_text(json.dumps(ALLOCS))
    validators = tmp_path / "validators.json"
    validators.write_text(json.dumps(VALIDATORS))
    return manifest, allocs, validators


def test_cli_scratch_writes_genesis_file_and_checker_passes(tmp_path, capsys) -> None:
    manifest, allocs, validators = _write_inputs(tmp_path)
    params = tmp_path / "params.json"
    params.write_text(json.dumps(PARAMS))
    data_dir = tmp_path / "scratch-data"
    rc = _script_main(CLI)(
        [
            "--manifest",
            str(manifest),
            "--allocations",
            str(allocs),
            "--parameters",
            str(params),
            "--bridge-validators",
            str(validators),
            "--data-dir",
            str(data_dir),
            "--operator-line",
            "test-operator",
        ]
    )
    assert rc == 0
    genesis = data_dir / "data" / CHAIN_ID / "genesis.json"
    assert genesis.exists()
    doc = json.loads(genesis.read_text())
    assert doc["chain_id"] == CHAIN_ID
    assert doc["bridge_validators_digest"].startswith("0x")
    manifest_out = json.loads((data_dir / "data" / CHAIN_ID / "genesis.manifest.json").read_text())
    assert manifest_out["operator_line"] == "test-operator"

    # The checker must accept the built file.
    capsys.readouterr()
    rc = _script_main(CHECKER)([str(genesis)])
    assert rc == 0

    # Existing target without --force refuses.
    capsys.readouterr()
    rc = _script_main(CLI)(["--manifest", str(manifest), "--allocations", str(allocs), "--data-dir", str(data_dir)])
    assert rc == 2
    assert "already exists" in capsys.readouterr().err


def test_cli_refuses_forbidden_prefix(tmp_path, capsys) -> None:
    manifest, allocs, _ = _write_inputs(tmp_path)
    rc = _script_main(CLI)(["--manifest", str(manifest), "--allocations", str(allocs), "--data-dir", "/var/lib/aitbc"])
    assert rc == 2
    assert "forbidden prefix" in capsys.readouterr().err


def test_cli_refuses_existing_chain_db(tmp_path, capsys) -> None:
    manifest, allocs, _ = _write_inputs(tmp_path)
    data_dir = tmp_path / "scratch-data"
    chain_dir = data_dir / "data" / CHAIN_ID
    chain_dir.mkdir(parents=True)
    (chain_dir / "chain.db").write_bytes(b"")
    rc = _script_main(CLI)(["--manifest", str(manifest), "--allocations", str(allocs), "--data-dir", str(data_dir)])
    assert rc == 2
    assert "not empty" in capsys.readouterr().err


def test_cli_live_mode_refusals(tmp_path, capsys) -> None:
    manifest, allocs, _ = _write_inputs(tmp_path)
    data_dir = tmp_path / "scratch-data"
    main = _script_main(CLI)

    # Missing operator line → refused naming the unmet condition.
    capsys.readouterr()
    rc = main(["--live", "--manifest", str(manifest), "--allocations", str(allocs), "--data-dir", str(data_dir)])
    assert rc == 2
    assert "operator line" in capsys.readouterr().err

    # Manifest chain id is the single source of the target id; a manifest for
    # a different chain id builds a different doc — the live gate compares the
    # two. Simulate the mismatch at the check level via check_live_conditions
    # (covered by test_check_live_conditions_reports_each_unmet) and here prove
    # an existing target dir for that chain is refused.
    (data_dir / "data" / CHAIN_ID).mkdir(parents=True)
    capsys.readouterr()
    rc = main(
        [
            "--live",
            "--manifest",
            str(manifest),
            "--allocations",
            str(allocs),
            "--data-dir",
            str(data_dir),
            "--operator-line",
            "op",
        ]
    )
    assert rc == 2
    assert "already holds" in capsys.readouterr().err


def test_cli_live_mode_always_refuses_the_write(tmp_path, capsys) -> None:
    """All preconditions met → still refuses: the live write is designed, not enabled."""
    manifest, allocs, _ = _write_inputs(tmp_path)
    data_dir = tmp_path / "scratch-data"
    rc = _script_main(CLI)(
        [
            "--live",
            "--manifest",
            str(manifest),
            "--allocations",
            str(allocs),
            "--data-dir",
            str(data_dir),
            "--operator-line",
            "op",
        ]
    )
    assert rc == 2
    assert "not enabled" in capsys.readouterr().err


def test_check_live_conditions_reports_each_unmet() -> None:
    unmet = check_live_conditions(
        doc={"chain_id": "bc-2"},
        manifest={"chain_id": "bc-3"},
        target_dir_exists=True,
        operator_line=None,
    )
    assert any("chain_id" in m for m in unmet)
    assert any("already holds" in m for m in unmet)
    assert any("operator line" in m for m in unmet)
    assert (
        check_live_conditions(
            doc={"chain_id": "bc-2"},
            manifest={"chain_id": "bc-2"},
            target_dir_exists=False,
            operator_line="op",
        )
        == []
    )
