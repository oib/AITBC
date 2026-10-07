"""Fixture test for ValidatorSetRegistry accumulation + threshold source (A36-2).

Proves three things with the real classes:
1. Four ``register_validator`` calls at the same epoch ACCUMULATE into one
   4-member in-memory set (validators.py:48-51) — correcting the A33 claim
   that each POST creates a single-member set. The single-member state is
   only the transient window between POSTs.
2. The in-memory set's own ``threshold`` field is the ValidatorSet
   dataclass default (3, types.py:99) — register_validator never sets it.
   Only the DB-load path stamps ``settings.bridge_multisig_threshold``
   (bridge_validator.py:163).
3. Verification never uses the set's own field anyway: both verify sites
   pass ``settings.bridge_multisig_threshold`` explicitly to
   check_threshold (bridge_validator.py:364 and :445), which prefers the
   explicit arg over ``validator_set.threshold`` (multisig.py:91).
   ``len/2 + 1`` is used nowhere.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime
from unittest.mock import patch

from sqlmodel import Session, create_engine

from aitbc.bridge.types import ValidatorInfo, ValidatorSet
from aitbc.bridge.validators import ValidatorSetRegistry
from aitbc_chain.base_models import BridgeValidator
from aitbc_chain.cross_chain.bridge_validator import BridgeValidatorMixin

ADDRS = ["0xAA", "0xBB", "0xCC", "0xDD"]
CHAIN = "c"


def _info(addr: str, epoch: int = 1) -> ValidatorInfo:
    return ValidatorInfo(address=addr, public_key="0x04", chain_id=CHAIN, epoch=epoch, is_active=True)


def test_four_registrations_accumulate_one_set() -> None:
    reg = ValidatorSetRegistry()
    sizes = []
    for addr in ADDRS:
        reg.register_validator(_info(addr))
        sizes.append(reg.get_validator_set(CHAIN).total)  # transient N=1..4
    assert sizes == [1, 2, 3, 4]
    vset = reg.get_validator_set(CHAIN)  # epoch None -> current epoch
    assert len(vset.validators) == 4 and vset.total == 4
    assert reg.get_current_epoch(CHAIN) == 1


def test_in_memory_set_threshold_is_dataclass_default_not_settings() -> None:
    reg = ValidatorSetRegistry()
    with patch("aitbc_chain.cross_chain.bridge_validator.settings") as s:
        s.bridge_multisig_threshold = 2
        reg.register_validator(_info("0xAA"))
    vset = reg.get_validator_set(CHAIN)
    # register_validator never stamps settings; the field keeps the
    # ValidatorSet default (3). len/2+1 for N=1 would be 1 — not used either.
    assert vset.threshold == ValidatorSet(chain_id=CHAIN, epoch=1).threshold == 3


class _DBStub(BridgeValidatorMixin):
    """Simulates a freshly restarted RPC process: empty registry, rows only
    in the DB. ``load_validator_set`` rebuilds from ``bridge_validators``."""

    def __init__(self, engine):
        self._engine = engine
        self._validator_registry = ValidatorSetRegistry()
        self._validator_cache_loaded: set = set()

    @contextmanager
    def _session_for(self, chain_id: str = ""):
        with Session(self._engine) as session:
            yield session


def _stub_with_rows(epoch: int = 1) -> _DBStub:
    engine = create_engine("sqlite://")
    BridgeValidator.__table__.create(engine)
    with Session(engine) as s:
        for addr in ADDRS:
            s.add(
                BridgeValidator(
                    chain_id=CHAIN,
                    address=addr,
                    public_key="0x04",
                    epoch=epoch,
                    is_active=True,
                    registered_at=datetime.now(UTC),
                )
            )
        s.commit()
    return _DBStub(engine)


def test_restart_rebuild_matches_in_memory_set() -> None:
    stub = _stub_with_rows()
    with patch("aitbc_chain.cross_chain.bridge_validator.settings") as s:
        s.bridge_multisig_threshold = 2
        rebuilt = stub.load_validator_set(CHAIN)  # epoch None -> latest
    assert rebuilt is not None
    assert rebuilt.epoch == 1
    assert {v.address for v in rebuilt.validators} == set(ADDRS)
    assert rebuilt.total == 4
    # DB-load path stamps the SETTINGS value (2), distinct from both the
    # dataclass default and len/2+1 — proving the source.
    assert rebuilt.threshold == 2
    # Registry now resolves epoch=None to the rebuilt epoch-1 set.
    assert stub.get_validator_set(CHAIN).total == 4
    assert stub._validator_registry.get_current_epoch(CHAIN) == 1


def test_verification_threshold_comes_from_settings_not_set_size() -> None:
    """check_threshold honours the explicit arg (settings) over both the
    set's own field and len/2+1: with N=4, len/2+1=3, set field=3, and the
    settings override=2 — only the settings value can make count=2 pass."""
    from aitbc.bridge.multisig import check_threshold

    vset = ValidatorSet(
        chain_id=CHAIN,
        epoch=1,
        validators=[_info(a) for a in ADDRS],
        threshold=3,  # as stored on the set
        total=4,
    )
    meets, count, _ = check_threshold(["0xAA", "0xBB"], vset, threshold=2)
    assert (meets, count) == (True, 2)
    # Same two signers under the set's own field (3) would fail — showing
    # which source the verify path's explicit arg overrides.
    meets3, _, _ = check_threshold(["0xAA", "0xBB"], vset, threshold=None)
    assert meets3 is False
