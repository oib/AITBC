"""Reconciling the coin-request database against the chain (V23-66).

A coin request records its `transaction_hash` in a database the chain knows nothing about. The
two can disagree — the hub's chain was reset on 2026-08-15 and every hash recorded before it
now points at a transaction that does not exist — and nothing detects that on its own. The
database goes on claiming a payout that happened on a chain nobody has any more.

`reconcile` reports the disagreements. `reopen` clears one hash so the request can be paid
again, which is the operation that can pay twice: that hash is the only thing standing between
a request and a second payout, both here and at `/execute`. So the tests that matter here are
the refusals — reopen must not act on a request the chain still has, and must not act when the
chain cannot be reached to say either way. An unreachable node looks exactly like a missing
transaction if you are not careful, and treating the two alike would invite someone to reissue
a payout that was made perfectly well.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from click.testing import CliRunner

pytest.importorskip("click")

from aitbc.db import agent_db  # noqa: E402
from aitbc.models import CoinRequest, CoinRequestStatus  # noqa: E402
from aitbc_cli.commands.coin_requests import coin_requests  # noqa: E402

PAID_HASH = "0x" + "2d" * 32
LOST_HASH = "0x" + "ab" * 32
RPC = "http://chain.test"


class _Response:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code
        self.text = "" if status_code == 200 else "not found"


@pytest.fixture
def chain(monkeypatch):
    """A chain that has PAID_HASH and nothing else, unless a test says otherwise."""
    state = {"known": {PAID_HASH}, "error": None, "params": []}

    def _get(url: str, params=None, timeout: int = 10):
        if state["error"]:
            raise state["error"]
        state["params"].append(params)
        return _Response(200 if url.rsplit("/", 1)[-1] in state["known"] else 404)

    monkeypatch.setattr("aitbc_cli.commands.coin_requests.requests.get", _get)
    return state


@pytest.fixture
def db(monkeypatch, tmp_path):
    monkeypatch.setenv("AGENT_DB_PATH", str(tmp_path / "coin_requests.db"))
    monkeypatch.setattr(agent_db, "_engine", None)
    monkeypatch.setattr(agent_db, "_SessionLocal", None)
    agent_db.init_db()

    now = datetime.now(UTC).replace(tzinfo=None)
    with agent_db.get_db_session() as session:
        for request_id, tx_hash in (("req-paid", PAID_HASH), ("req-lost", LOST_HASH)):
            session.add(
                CoinRequest(
                    id=request_id,
                    sender="agent-alpha",
                    recipient="hub-coordinator",
                    amount=100,
                    wallet_address="0xe0383C465aF763F2489B61Ec169bB06E485DAB95",
                    status=CoinRequestStatus.APPROVED,
                    approval_mode="manual",
                    approved_by="cli",
                    created_at=now,
                    expires_at=now + timedelta(days=1),
                    transaction_hash=tx_hash,
                )
            )
    yield
    agent_db._engine = None
    agent_db._SessionLocal = None


def _run(*args):
    return CliRunner().invoke(coin_requests, list(args), catch_exceptions=False)


def _hash_of(request_id: str) -> str | None:
    with agent_db.get_db_session() as session:
        found = session.query(CoinRequest).filter(CoinRequest.id == request_id).first()
        return None if found is None else found.transaction_hash


# --- reconcile --------------------------------------------------------------------------


def test_reconcile_names_the_request_the_chain_has_never_heard_of(db, chain) -> None:
    result = _run("reconcile", "--rpc-url", RPC)

    assert "req-lost" in result.output
    assert LOST_HASH in result.output
    assert "req-paid" not in result.output
    assert "1 checked" not in result.output and "2 checked" in result.output
    assert "1 not on chain" in result.output


def test_reconcile_changes_nothing_without_annotate(db, chain) -> None:
    """Read-only by default: the report is safe to run on a schedule."""
    _run("reconcile", "--rpc-url", RPC)

    assert _hash_of("req-lost") == LOST_HASH


def test_annotate_records_the_discrepancy_but_still_does_not_clear_it(db, chain) -> None:
    """Clearing is `reopen`'s job. Annotating a whole database must not make anything payable."""
    _run("reconcile", "--rpc-url", RPC, "--annotate")

    with agent_db.get_db_session() as session:
        lost = session.query(CoinRequest).filter(CoinRequest.id == "req-lost").first()
        assert "absent from chain" in (lost.audit_log or "")
        assert lost.transaction_hash == LOST_HASH


def test_an_unreachable_chain_is_counted_apart_from_a_missing_transaction(db, chain) -> None:
    chain["error"] = RuntimeError("connection refused")

    result = _run("reconcile", "--rpc-url", RPC)

    assert "2 unverifiable" in result.output
    assert "0 not on chain" in result.output


def test_a_request_stranded_mid_execution_is_reported_not_checked(db, chain) -> None:
    """`claiming:` is the execute claim marker, not a hash — asking the chain for it is noise."""
    with agent_db.get_db_session() as session:
        stranded = session.query(CoinRequest).filter(CoinRequest.id == "req-lost").first()
        stranded.transaction_hash = "claiming:2026-08-15T11:12:00+00:00"

    result = _run("reconcile", "--rpc-url", RPC)

    assert "stranded mid-execution" in result.output
    assert "1 checked" in result.output


def test_the_node_is_left_to_say_which_chain_it_serves(db, chain) -> None:
    """No client-side guess at `chain_id`, because a wrong guess 404s every hash.

    That reads as "not one of these payouts happened", which is the state that invites
    reopening requests that were paid. The hub serves `ait-hub.aitbc.bubuit.net` while
    `CHAIN_ID` defaults to `ait-hub`, so the guess is wrong exactly where it is load-bearing.
    """
    _run("reconcile", "--rpc-url", RPC)

    assert chain["params"] == [None, None]


def test_an_explicit_chain_id_is_passed_through(db, chain) -> None:
    """Still available for a node serving several islands — but only when asked for."""
    _run("reconcile", "--rpc-url", RPC, "--chain-id", "ait-island-2")

    assert chain["params"] == [{"chain_id": "ait-island-2"}] * 2


# --- reopen, which is the one that can pay twice ----------------------------------------


def test_reopen_clears_a_hash_the_chain_does_not_have(db, chain) -> None:
    result = _run("reopen", "req-lost", "--rpc-url", RPC)

    assert "Reopened" in result.output
    assert _hash_of("req-lost") is None


def test_reopen_refuses_a_request_the_chain_still_has(db, chain) -> None:
    """The whole point. This hash is what stops `/execute` paying a second time."""
    result = _run("reopen", "req-paid", "--rpc-url", RPC)

    assert "Refusing to reopen" in result.output
    assert _hash_of("req-paid") == PAID_HASH


def test_reopen_refuses_when_the_chain_cannot_be_reached(db, chain) -> None:
    """An unreachable node must not read as a missing transaction."""
    chain["error"] = RuntimeError("connection refused")

    result = _run("reopen", "req-lost", "--rpc-url", RPC)

    assert "could not confirm" in result.output
    assert _hash_of("req-lost") == LOST_HASH


def test_force_overrides_the_refusal_and_says_so(db, chain) -> None:
    result = _run("reopen", "req-paid", "--rpc-url", RPC, "--force")

    assert "--force given" in result.output
    assert _hash_of("req-paid") is None


def test_reopen_leaves_a_trail(db, chain) -> None:
    _run("reopen", "req-lost", "--rpc-url", RPC)

    with agent_db.get_db_session() as session:
        reopened = session.query(CoinRequest).filter(CoinRequest.id == "req-lost").first()
        assert LOST_HASH in (reopened.audit_log or "")
        assert "Reopened" in (reopened.audit_log or "")


def test_reopening_an_unexecuted_request_is_a_no_op(db, chain) -> None:
    _run("reopen", "req-lost", "--rpc-url", RPC)

    result = _run("reopen", "req-lost", "--rpc-url", RPC)

    assert "already executable" in result.output
