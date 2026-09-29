"""GOVERNANCE_EXECUTE executor gate — the fail-closed parameter check.

Pins the v5 enforcement: a funded non-executor cannot rewrite authority
parameters, an unset executor list rejects (not "no restriction"), and the
listed executor passes. Pre-v5 history stays lenient for sealed executes
that predate the parameter.
"""

from __future__ import annotations

from aitbc_chain.base_models import Account, ChainParameter
from aitbc_chain.state.state_transition import StateTransition

_CHAIN = "test-gov-executor"
_EXECUTOR = "0x02B8F2C61DB19B04aB68cfb43d0605E63dE74c5B"
_ATTACKER = "0xF4924759508E420eeD947BD33326731B11c4B7Df"


def _tx(sender: str) -> dict:
    return {
        "type": "GOVERNANCE_EXECUTE",
        "from": sender,
        "to": sender,
        "value": 0,
        "fee": 1000,
        "nonce": 0,
        "tx_hash": "0x" + "ab" * 32,
        "payload": {
            "proposal_id": "p1",
            "execution_payload": {
                "action": "parameter_change",
                "parameter": "bridge_release_authority",
                "value": _ATTACKER,
            },
        },
    }


def _seed(session, executor_value) -> None:
    if executor_value is not None:
        session.add(ChainParameter(chain_id=_CHAIN, parameter="governance_executors", value=executor_value))
    session.add(Account(chain_id=_CHAIN, address=_ATTACKER, balance=10**9, nonce=0))
    session.add(Account(chain_id=_CHAIN, address=_EXECUTOR, balance=10**9, nonce=0))
    session.commit()


class TestGovernanceExecutorGate:
    def test_non_executor_rejected_v5_through_v8(self, session):
        _seed(session, _EXECUTOR)
        st = StateTransition()
        for ver in (5, 6, 7, 8):
            ok, why = st.validate_transaction(
                session, _CHAIN, _tx(_ATTACKER), "0x" + "ab" * 32, block_version=ver, block_height=100
            )
            assert not ok and "not an authorized executor" in why, (ver, ok, why)

    def test_executor_passes(self, session):
        _seed(session, _EXECUTOR)
        st = StateTransition()
        ok, _ = st.validate_transaction(session, _CHAIN, _tx(_EXECUTOR), "0x" + "ab" * 32, block_version=5, block_height=100)
        assert ok

    def test_unset_executor_fails_closed_v5_plus(self, session):
        _seed(session, None)
        st = StateTransition()
        for ver in (5, 8):
            ok, why = st.validate_transaction(
                session, _CHAIN, _tx(_ATTACKER), "0x" + "ab" * 32, block_version=ver, block_height=100
            )
            assert not ok and "not set" in why, (ver, ok, why)

    def test_unset_executor_lenient_below_v5(self, session):
        _seed(session, None)
        st = StateTransition()
        ok, _ = st.validate_transaction(session, _CHAIN, _tx(_ATTACKER), "0x" + "ab" * 32, block_version=4, block_height=100)
        assert ok
