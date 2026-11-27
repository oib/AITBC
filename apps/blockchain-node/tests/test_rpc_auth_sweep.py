"""Auth sweep — every mutating route under the public /rpc proxy must reject
uncredentialed callers.

GAP-56: nginx ``location /rpc/`` is a blanket proxy, so any router mounted
there is internet-facing. The audit found unauthenticated mutations ranging
from lease revocation to a full governance takeover chain (public proposal →
vote with caller-chosen voting_power → execute signed by the node's genesis
key). These tests pin the X-API-Key gate on each route and the stake-derived
voting power, so the surface cannot silently reopen.

#3056 (AUDIT-RPC-AUTH-SWEEP-COVERAGE-1): the per-route pins above cover the
routes the audit happened to enumerate; auth is per-route with no router-level
net, so a NEW mutating route added without an auth decision would be
internet-facing by default and no test would fail. ``TestRpcAuthCoverageRatchet``
closes that hole: it enumerates the app's live route table (``app.routes``)
and requires every mutating route to appear in an explicit auth-decision
registry — key-gated, signed-payload, admin-auth, or intentionally-public with
a reason. A new route fails CI until its class is declared.
"""

from __future__ import annotations

import inspect
import re
import time
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import aitbc_chain.rpc.escrow_routes as escrow_routes

KEY = "test-key-123"


def _app(*routers) -> TestClient:
    app = FastAPI()
    for r in routers:
        app.include_router(r, prefix="/rpc")
    # Handlers without a test DB may crash; we only care that the status isn't
    # 403, so convert handler exceptions to 500s instead of raising.
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _api_key(monkeypatch):
    monkeypatch.setattr(escrow_routes, "_RPC_API_KEY", KEY)


class TestGovernanceIdentityAuth:
    """The public proposal→vote→execute chain was a remote chain-parameter
    write signed by the node's own genesis key — a takeover. All five
    mutating routes now require X-API-Key."""

    @pytest.fixture
    def client(self):
        from aitbc_chain.rpc.routers.staking import router

        return _app(router)

    @pytest.mark.parametrize(
        "path",
        [
            "/rpc/identity/register",
            "/rpc/identity/verify",
            "/rpc/governance/proposal",
            "/rpc/governance/vote",
            "/rpc/governance/proposal/p1/execute",
        ],
    )
    def test_reject_missing_key(self, client, path):
        assert client.post(path, json={}).status_code == 403, path

    @pytest.mark.parametrize(
        "path",
        [
            "/rpc/identity/register",
            "/rpc/governance/proposal",
            "/rpc/governance/vote",
            "/rpc/governance/proposal/p1/execute",
        ],
    )
    def test_reject_wrong_key(self, client, path):
        assert client.post(path, json={}, headers={"X-API-Key": "nope"}).status_code == 403, path

    def test_valid_key_reaches_handler(self, client):
        resp = client.post("/rpc/governance/vote", json={}, headers={"X-API-Key": KEY})
        assert resp.status_code != 403

    def test_reads_stay_public(self, client):
        assert client.get("/rpc/governance/proposal/p1").status_code != 403
        assert client.get("/rpc/identity/agent-1").status_code != 403


class TestEscrowSettlementAuth:
    """#1917: escrow release/refund move money, so they require the dedicated
    settlement credential (X-Settlement-Key, BLOCKCHAIN_RPC_SETTLEMENT_API_KEY)
    ON TOP OF the router-wide X-API-Key. Possession of the shared RPC key —
    which every service and issued join key's parent holds — must no longer
    be sufficient to settle an escrow. Other escrow routes (create, reads)
    keep the base-key gate only."""

    SETTLE_KEY = "settle-key-9"

    @pytest.fixture
    def client(self, monkeypatch):
        monkeypatch.setattr(escrow_routes, "_RPC_SETTLEMENT_API_KEY", self.SETTLE_KEY)
        return _app(escrow_routes.router)

    def _post(self, client, path, *, api_key=KEY, settle_key="__unset__"):
        headers = {"X-API-Key": api_key} if api_key is not None else {}
        if settle_key != "__unset__":
            headers["X-Settlement-Key"] = settle_key
        return client.post(path, json={}, headers=headers)

    @pytest.mark.parametrize("path", ["/rpc/escrow/job-1/release", "/rpc/escrow/job-1/refund"])
    def test_rejects_missing_settlement_key(self, client, path):
        """Valid base RPC key alone is no longer sufficient to settle."""
        assert self._post(client, path).status_code == 403, path

    @pytest.mark.parametrize("path", ["/rpc/escrow/job-1/release", "/rpc/escrow/job-1/refund"])
    def test_rejects_wrong_settlement_key(self, client, path):
        assert self._post(client, path, settle_key="nope").status_code == 403, path

    @pytest.mark.parametrize("path", ["/rpc/escrow/job-1/release", "/rpc/escrow/job-1/refund"])
    def test_rejects_missing_base_key_even_with_settlement_key(self, client, path):
        """The settlement credential does not replace X-API-Key."""
        assert self._post(client, path, api_key=None, settle_key=self.SETTLE_KEY).status_code == 403, path

    @pytest.mark.parametrize("path", ["/rpc/escrow/job-1/release", "/rpc/escrow/job-1/refund"])
    def test_valid_both_keys_reaches_handler(self, client, path):
        """Both credentials pass auth; the handler then runs (and fails on
        test scaffolding — no escrow manager / signing key — never 403)."""
        resp = self._post(client, path, settle_key=self.SETTLE_KEY)
        assert resp.status_code != 403, path

    @pytest.mark.parametrize("path", ["/rpc/escrow/job-1/release", "/rpc/escrow/job-1/refund"])
    def test_unset_settlement_key_fails_closed_503(self, client, monkeypatch, path):
        """An unconfigured node refuses settlement outright — never open."""
        monkeypatch.setattr(escrow_routes, "_RPC_SETTLEMENT_API_KEY", "")
        resp = self._post(client, path, settle_key=self.SETTLE_KEY)
        assert resp.status_code == 503, path

    def test_non_settlement_routes_keep_base_key_only(self, client):
        """Create/read stay on the shared key — the settlement credential is
        scoped to release/refund and must not be required elsewhere."""
        create = client.post("/rpc/escrow/create", json={}, headers={"X-API-Key": KEY})
        assert create.status_code != 403
        read = client.get("/rpc/escrow/job-1", headers={"X-API-Key": KEY})
        assert read.status_code != 403

    @pytest.mark.parametrize("path", ["/rpc/escrow/job-1/release", "/rpc/escrow/job-1/refund"])
    def test_peer_key_with_settlement_key_reaches_handler(self, client, monkeypatch, path):
        """#2742: a fleet peer node's own RPC key + the fleet-shared settlement
        credential is a legitimate settlement caller — customer nodes hold
        both by design and must be able to refund escrows they cannot settle
        locally."""
        monkeypatch.setattr(escrow_routes, "_RPC_API_PEER_KEYS", frozenset({"peer-key-a"}))
        resp = self._post(client, path, api_key="peer-key-a", settle_key=self.SETTLE_KEY)
        assert resp.status_code != 403, path

    @pytest.mark.parametrize("path", ["/rpc/escrow/job-1/release", "/rpc/escrow/job-1/refund"])
    def test_peer_key_without_settlement_key_still_403(self, client, monkeypatch, path):
        """The peer-key base gate does not weaken the settlement credential:
        X-Settlement-Key is still mandatory."""
        monkeypatch.setattr(escrow_routes, "_RPC_API_PEER_KEYS", frozenset({"peer-key-a"}))
        assert self._post(client, path, api_key="peer-key-a").status_code == 403, path

    def test_peer_key_still_rejected_on_non_settlement_routes(self, client, monkeypatch):
        """Peer keys unlock settlement routes only — create/read keep the
        own-key gate so the escrow control plane stays scoped."""
        monkeypatch.setattr(escrow_routes, "_RPC_API_PEER_KEYS", frozenset({"peer-key-a"}))
        h = {"X-API-Key": "peer-key-a"}
        assert client.get("/rpc/escrow/job-1", headers=h).status_code == 403
        assert client.post("/rpc/escrow/create", json={}, headers=h).status_code == 403


class TestControlPlaneAuth:
    """Chain lifecycle and block import are operator operations."""

    @pytest.fixture
    def client(self):
        from aitbc_chain.rpc.routers.core import router

        return _app(router)

    def test_chains_start_stop_reject_missing_key(self, client):
        body = {"chain_id": "micro-1", "chain_type": "micro"}
        assert client.post("/rpc/chains/start", json=body).status_code == 403
        assert client.post("/rpc/chains/stop", json=body).status_code == 403

    def test_import_block_rejects_missing_key(self, client):
        assert client.post("/rpc/importBlock", json={}).status_code == 403

    def test_wrong_key_rejected(self, client):
        body = {"chain_id": "micro-1", "chain_type": "micro"}
        assert client.post("/rpc/chains/stop", json=body, headers={"X-API-Key": "nope"}).status_code == 403

    @pytest.mark.slow
    def test_valid_key_reaches_handler(self, client):
        body = {"chain_id": "micro-1", "chain_type": "micro"}
        resp = client.post("/rpc/chains/start", json=body, headers={"X-API-Key": KEY})
        assert resp.status_code != 403

    def test_register_account_stays_public(self, client):
        """register-account is a read-only report (documented no-write)."""
        assert client.post("/rpc/register-account", json={}).status_code != 403


class TestSubscriptionAuth:
    """Lease register/heartbeat/revoke are node-internal. Fleet nodes each
    hold their own BLOCKCHAIN_RPC_API_KEY, so the hub accepts its own key OR
    the peer set in BLOCKCHAIN_RPC_API_KEY_PEERS — scoped to these routes
    only, never the control plane."""

    @pytest.fixture
    def client(self, monkeypatch):
        monkeypatch.setattr(escrow_routes, "_RPC_API_PEER_KEYS", frozenset({"peer-key-a", "peer-key-b"}))
        from aitbc_chain.rpc.routers.subscription import router

        return _app(router)

    def test_reject_missing_key(self, client):
        assert client.post("/rpc/subscribe", json={}).status_code == 403
        assert client.post("/rpc/heartbeat", json={}).status_code == 403
        assert client.delete("/rpc/lease/node-1").status_code == 403

    def test_valid_key_reaches_handler(self, client):
        resp = client.post(
            "/rpc/subscribe",
            json={"node_id": "n1", "transport": "redis", "chain_id": "ait-testnet"},
            headers={"X-API-Key": KEY},
        )
        assert resp.status_code != 403

    def test_peer_key_reaches_handler(self, client):
        resp = client.post(
            "/rpc/heartbeat",
            json={"node_id": "n1", "chain_id": "ait-testnet"},
            headers={"X-API-Key": "peer-key-a"},
        )
        assert resp.status_code != 403

    def test_peer_key_does_not_open_control_plane(self):
        """A leaked peer key must not unlock governance or chain control."""
        from aitbc_chain.rpc.routers.staking import router as staking_router
        from aitbc_chain.rpc.routers.core import router as core_router

        c = _app(staking_router, core_router)
        h = {"X-API-Key": "peer-key-a"}
        assert c.post("/rpc/governance/vote", json={}, headers=h).status_code == 403
        assert c.post("/rpc/chains/stop", json={"chain_id": "x"}, headers=h).status_code == 403

    def test_lease_reads_require_peer_key(self, client):
        """#1936: lease/subscriber reads expose node-local fleet topology,
        not chain data — they take the same peer-key credential as the
        rest of the lease API."""
        assert client.get("/rpc/lease/node-1").status_code == 403
        assert client.get("/rpc/subscribers").status_code == 403

    def test_lease_reads_reject_wrong_key(self, client):
        assert client.get("/rpc/lease/node-1", headers={"X-API-Key": "nope"}).status_code == 403
        assert client.get("/rpc/subscribers", headers={"X-API-Key": "nope"}).status_code == 403

    def test_lease_read_peer_key_reaches_handler(self, client):
        resp = client.get("/rpc/subscribers", headers={"X-API-Key": "peer-key-a"})
        assert resp.status_code != 403

    def test_lease_status_issued_key_binding(self, client, monkeypatch, tmp_path):
        """An issued join key may read only its own node_id's lease —
        same binding the mutating lease routes enforce."""
        monkeypatch.setenv("PEER_KEYS_DB", str(tmp_path / "peer_keys.db"))
        from aitbc_chain.rpc import peer_keys

        issued = peer_keys.issue("joiner.example.net", "10.0.0.9")
        own = client.get("/rpc/lease/joiner.example.net", headers={"X-API-Key": issued})
        assert own.status_code != 403
        other = client.get("/rpc/lease/other-node", headers={"X-API-Key": issued})
        assert other.status_code == 403


class TestExportChainAuth:
    """export-chain is a bulk/state-disclosure route: fleet keys only — the
    node's own BLOCKCHAIN_RPC_API_KEY or a BLOCKCHAIN_RPC_API_KEY_PEERS
    member. Issued /rpc/join keys are self-serve and must not unlock a full
    chain export (#1871)."""

    @pytest.fixture
    def client(self, monkeypatch, tmp_path):
        monkeypatch.setattr(escrow_routes, "_RPC_API_PEER_KEYS", frozenset({"peer-key-a"}))
        monkeypatch.setenv("PEER_KEYS_DB", str(tmp_path / "peer_keys.db"))
        from aitbc_chain.rpc.routers.core import router

        return _app(router)

    def test_reject_missing_key(self, client):
        assert client.get("/rpc/export-chain").status_code == 403

    def test_reject_wrong_key(self, client):
        assert client.get("/rpc/export-chain", headers={"X-API-Key": "nope"}).status_code == 403

    def test_issued_join_key_rejected(self, client):
        """A live issued join key — valid for subscribe/heartbeat/lease —
        must still get 403 here."""
        from aitbc_chain.rpc import peer_keys

        issued = peer_keys.issue("joiner.example.net", "10.0.0.9")
        assert client.get("/rpc/export-chain", headers={"X-API-Key": issued}).status_code == 403

    def test_peer_key_reaches_handler(self, client):
        resp = client.get("/rpc/export-chain", headers={"X-API-Key": "peer-key-a"})
        assert resp.status_code != 403

    def test_admin_key_reaches_handler(self, client):
        resp = client.get("/rpc/export-chain", headers={"X-API-Key": KEY})
        assert resp.status_code != 403


class TestIslandsAuth:
    """islands/join returned node credentials publicly."""

    @pytest.fixture
    def client(self):
        from aitbc_chain.rpc.routers.islands import router

        return _app(router)

    def test_reject_missing_key(self, client):
        join = {"island_id": "i1", "island_name": "i1", "chain_id": "ait-testnet"}
        assert client.post("/rpc/islands/join", json=join).status_code == 403
        assert client.post("/rpc/islands/leave", json={"island_id": "i1"}).status_code == 403
        assert client.post("/rpc/islands/bridge", json={"target_island_id": "i2"}).status_code == 403

    def test_valid_key_reaches_handler(self, client):
        join = {"island_id": "i1", "island_name": "i1", "chain_id": "ait-testnet"}
        resp = client.post("/rpc/islands/join", json=join, headers={"X-API-Key": KEY})
        assert resp.status_code != 403

    def test_reads_require_peer_key(self, client):
        """#1945: island membership topology is operational metadata — peer-keyed."""
        assert client.get("/rpc/islands").status_code == 403
        assert client.get("/rpc/islands/isl-1", headers={"X-API-Key": KEY}).status_code != 403


class TestContractsAuth:
    """Contracts deploy + forum mutations trusted caller-supplied identities;
    moderate_message had an unenforced 'moderator only' docstring."""

    @pytest.fixture
    def client(self):
        from aitbc_chain.rpc.routers.contracts import router

        return _app(router)

    @pytest.mark.parametrize(
        "path",
        [
            "/rpc/contracts/deploy",
            "/rpc/contracts/deploy/messaging",
            "/rpc/contracts/messaging/topics/create",
            "/rpc/contracts/messaging/messages/post",
            "/rpc/contracts/messaging/messages/m1/vote",
            "/rpc/contracts/messaging/messages/m1/moderate",
        ],
    )
    def test_reject_missing_key(self, client, path):
        assert client.post(path, json={}).status_code == 403, path

    def test_valid_key_reaches_handler(self, client):
        resp = client.post("/rpc/contracts/messaging/messages/post", json={}, headers={"X-API-Key": KEY})
        assert resp.status_code != 403

    def test_reads_stay_public(self, client):
        """call/verify are pure reads (select-only); keep them open."""
        assert client.post("/rpc/contracts/call", json={}).status_code != 403
        assert client.get("/rpc/contracts/messaging/topics").status_code != 403


class TestGpuResourcesAuth:
    """GPU/edge registration wrote resource claims with no auth."""

    @pytest.fixture
    def client(self):
        from aitbc_chain.rpc.gpu_resources import router

        return _app(router)

    def test_reject_missing_key(self, client):
        assert client.post("/rpc/gpu/register", json={}).status_code == 403
        assert client.post("/rpc/gpu/allocate", json={}).status_code == 403
        assert client.post("/rpc/edge/register", json={}).status_code == 403


class TestVotingPowerFromStake:
    """cast_governance_vote must derive voting_power from the voter's active
    stake — the request field was caller-chosen, so one vote with
    voting_power=N could push any proposal over quorum (which defaults to 0)."""

    @pytest.fixture
    def env(self, tmp_path, monkeypatch):
        from aitbc_chain.metadata import chain_metadata
        from aitbc_chain.models import Account, Stake
        from aitbc_chain.base_models import GovernanceProposal
        from aitbc_chain.rpc import staking as staking_module
        from sqlmodel import Session, create_engine

        engine = create_engine(f"sqlite:///{tmp_path / 'gov.db'}")
        chain_metadata.create_all(engine)

        @contextmanager
        def _scope():
            with Session(engine) as s:
                yield s

        monkeypatch.setattr(staking_module, "session_scope", _scope)
        monkeypatch.setattr(staking_module, "get_chain_id", lambda cid: cid or "ait-testnet")
        # The governance write routes now require a signed actor (#2773);
        # these tests exercise voting-power math, not signature recovery, so
        # the verifier is stubbed and the freshness fields supplied.
        monkeypatch.setattr(staking_module, "verify_request_signature", lambda *a, **k: True)

        now = datetime.now(UTC)
        with Session(engine) as s:
            s.add(
                GovernanceProposal(
                    chain_id="ait-testnet",
                    proposal_id="p1",
                    proposer_address="0x" + "a" * 40,
                    title="t",
                    description="d",
                    status="active",
                    quorum_required=100,
                    voting_starts=now,
                    voting_ends=now + timedelta(days=7),
                )
            )
            s.add(
                Account(
                    chain_id="ait-testnet",
                    address="0x" + "b" * 40,
                    balance=10_000,
                    nonce=0,
                )
            )
            s.add(
                Stake(
                    chain_id="ait-testnet",
                    address="0x" + "b" * 40,
                    amount=250,
                    locked_until=now + timedelta(days=30),
                    status="active",
                )
            )
            s.commit()
        return staking_module

    @pytest.mark.anyio
    @pytest.mark.asyncio
    async def test_voting_power_comes_from_stake(self, env):
        """Caller claims voting_power=999999; only 250 (the active stake) counts."""
        resp = env.cast_governance_vote(
            None,
            {
                "proposal_id": "p1",
                "voter_address": "0x" + "b" * 40,
                "vote_type": "for",
                "voting_power": 999999,
                "chain_id": "ait-testnet",
                "signature": "0xsig",
                "timestamp": time.time(),
                "nonce": 0,
            },
        )
        assert resp["voting_power"] == 250

    @pytest.mark.anyio
    @pytest.mark.asyncio
    async def test_no_stake_means_no_power(self, env):
        resp = env.cast_governance_vote(
            None,
            {
                "proposal_id": "p1",
                "voter_address": "0x" + "c" * 40,
                "vote_type": "for",
                "voting_power": 999999,
                "chain_id": "ait-testnet",
                "signature": "0xsig",
                "timestamp": time.time(),
                "nonce": 0,
            },
        )
        assert resp["voting_power"] == 0

    @pytest.mark.anyio
    @pytest.mark.asyncio
    async def test_checksummed_stake_row_matches_lowercase_voter(self, env):
        """Stake rows are written EIP-55-checksummed by the state transition;
        the request address is lowercased. The lookup must still match."""
        now = datetime.now(UTC)
        with env.session_scope() as s:
            s.add(
                env.Stake(
                    chain_id="ait-testnet",
                    address="0x" + "Dd" * 20,
                    amount=777,
                    locked_until=now + timedelta(days=30),
                    status="active",
                )
            )
            s.commit()
        resp = env.cast_governance_vote(
            None,
            {
                "proposal_id": "p1",
                "voter_address": "0x" + "dd" * 20,
                "vote_type": "for",
                "chain_id": "ait-testnet",
                "signature": "0xsig",
                "timestamp": time.time(),
                "nonce": 0,
            },
        )
        assert resp["voting_power"] == 777

    @pytest.mark.anyio
    @pytest.mark.asyncio
    async def test_zero_power_vote_on_zero_quorum_proposal_does_not_500(self, env):
        """quorum_required defaults to 0; a 0-power vote made total_votes=0 ≥ 0,
        then divided by zero. The proposal must stay 'active', not crash."""
        now = datetime.now(UTC)
        with env.session_scope() as s:
            s.add(
                env.GovernanceProposal(
                    chain_id="ait-testnet",
                    proposal_id="p-zeroq",
                    proposer_address="0x" + "a" * 40,
                    title="t",
                    description="d",
                    status="active",
                    quorum_required=0,
                    voting_starts=now,
                    voting_ends=now + timedelta(days=7),
                )
            )
            s.commit()
        resp = env.cast_governance_vote(
            None,
            {
                "proposal_id": "p-zeroq",
                "voter_address": "0x" + "e" * 40,
                "vote_type": "for",
                "chain_id": "ait-testnet",
                "signature": "0xsig",
                "timestamp": time.time(),
                "nonce": 0,
            },
        )
        assert resp["voting_power"] == 0
        with env.session_scope() as s:
            prop = s.exec(env.select(env.GovernanceProposal).where(env.GovernanceProposal.proposal_id == "p-zeroq")).one()
        assert prop.status == "active"


class TestBountyAuthBinding:
    """Bounty protocol transfers now carry auth evidence; the consensus
    binding must bind bounty_id / submission_id / party per type."""

    def _bind(self, tx_type, message, tx_data):
        from aitbc_chain.state.state_transition import _payload_auth_binds_transfer

        return _payload_auth_binds_transfer(tx_type, message, tx_data)

    def test_lock_binds_creator_amount_bounty(self):
        msg = {"bounty_id": "b1", "user_address": "0x" + "a" * 40, "reward_amount": 500}
        tx = {"from": "0x" + "a" * 40, "value": 500, "payload": {"bounty_id": "b1"}}
        assert self._bind("BOUNTY_LOCK", msg, tx)

    def test_lock_rejects_wrong_creator(self):
        msg = {"bounty_id": "b1", "user_address": "0x" + "a" * 40, "reward_amount": 500}
        tx = {"from": "0x" + "b" * 40, "value": 500, "payload": {"bounty_id": "b1"}}
        assert not self._bind("BOUNTY_LOCK", msg, tx)

    def test_lock_rejects_amount_mismatch(self):
        msg = {"bounty_id": "b1", "user_address": "0x" + "a" * 40, "reward_amount": 500}
        tx = {"from": "0x" + "a" * 40, "value": 9000, "payload": {"bounty_id": "b1"}}
        assert not self._bind("BOUNTY_LOCK", msg, tx)

    def test_lock_rejects_bounty_mismatch(self):
        msg = {"bounty_id": "b1", "user_address": "0x" + "a" * 40, "reward_amount": 500}
        tx = {"from": "0x" + "a" * 40, "value": 500, "payload": {"bounty_id": "b2"}}
        assert not self._bind("BOUNTY_LOCK", msg, tx)

    def test_payout_binds_submission(self):
        msg = {"submission_id": "s1", "verified": True}
        tx = {"to": "0x" + "a" * 40, "payload": {"bounty_id": "b1", "submission_id": "s1"}}
        assert self._bind("BOUNTY_PAYOUT", msg, tx)

    def test_payout_rejects_submission_mismatch(self):
        msg = {"submission_id": "s1", "verified": True}
        tx = {"to": "0x" + "a" * 40, "payload": {"bounty_id": "b1", "submission_id": "s2"}}
        assert not self._bind("BOUNTY_PAYOUT", msg, tx)

    def test_refund_binds_payee(self):
        msg = {"user_address": "0x" + "a" * 40}
        tx = {"to": "0x" + "a" * 40, "payload": {"bounty_id": "b1"}}
        assert self._bind("BOUNTY_REFUND", msg, tx)

    def test_refund_rejects_wrong_payee(self):
        msg = {"user_address": "0x" + "a" * 40}
        tx = {"to": "0x" + "b" * 40, "payload": {"bounty_id": "b1"}}
        assert not self._bind("BOUNTY_REFUND", msg, tx)

    def test_unknown_type_still_rejected(self):
        assert not self._bind("TRANSFER", {"user_address": "0x" + "a" * 40}, {})


class TestGovernanceExecutorGate:
    """The consensus gate at validate_transaction: once the
    ``governance_executors`` chain parameter is set, only listed senders may
    land a GOVERNANCE_EXECUTE. While unset (live chain today) the gate is
    open — the param write in the deploy closes it fleet-wide."""

    @pytest.fixture
    def session(self, tmp_path):
        from aitbc_chain.metadata import chain_metadata
        from aitbc_chain.models import Account
        from aitbc_chain.base_models import ChainParameter
        from sqlmodel import Session, create_engine

        engine = create_engine(f"sqlite:///{tmp_path / 'exec.db'}")
        chain_metadata.create_all(engine)
        s = Session(engine)
        s.add(Account(chain_id="ait-testnet", address="0x" + "a" * 40, balance=1000, nonce=0))
        s.add(Account(chain_id="ait-testnet", address="0x" + "e" * 40, balance=1000, nonce=0))
        s.add(
            ChainParameter(
                chain_id="ait-testnet",
                parameter="governance_executors",
                value="0x" + "e" * 40,
            )
        )
        s.commit()
        yield s
        s.close()

    def _tx(self, sender: str) -> dict:
        return {
            "type": "GOVERNANCE_EXECUTE",
            "from": sender,
            "to": sender,
            "value": 0,
            "fee": 0,
            "nonce": 0,
            "chain_id": "ait-testnet",
            "payload": {"proposal_id": "p1", "parameter_change": {"parameter": "x", "value": "1"}},
        }

    def test_non_executor_rejected(self, session):
        from aitbc_chain.state.state_transition import StateTransition

        ok, msg = StateTransition().validate_transaction(session, "ait-testnet", self._tx("0x" + "a" * 40), "0xdead01")
        assert not ok
        assert "not an authorized executor" in msg

    def test_executor_passes_gate(self, session):
        from aitbc_chain.state.state_transition import StateTransition

        ok, msg = StateTransition().validate_transaction(session, "ait-testnet", self._tx("0x" + "e" * 40), "0xdead02")
        assert ok, msg


# ---------------------------------------------------------------------------
# #3056 AUDIT-RPC-AUTH-SWEEP-COVERAGE-1 — auth-decision coverage ratchet
# ---------------------------------------------------------------------------

#: HTTP methods that can change state. GET/HEAD/OPTIONS are reads.
_MUTATING_METHODS = frozenset({"POST", "PUT", "DELETE", "PATCH"})

#: Dependency callables that gate a route on the X-API-Key credential family —
#: the node's own BLOCKCHAIN_RPC_API_KEY, a fleet peer key, an issued join key,
#: the settlement credential, or the export/fleet-read variant. Detected
#: mechanically by walking ``route.dependant`` (this also sees router-level
#: ``APIRouter(dependencies=[...])`` gates, which FastAPI flattens into each
#: route). A new credential dependency must be added here or the ratchet fails.
_KEY_GATE_DEPENDENCIES = frozenset(
    {
        "verify_rpc_api_key",
        "verify_rpc_peer_key",
        "verify_rpc_fleet_read_key",
        "verify_rpc_fleet_peer_key",
        "verify_rpc_export_key",
        "verify_rpc_settlement_key",
    }
)

#: Source tokens proving an in-handler cryptographic auth decision. The check
#: reads the endpoint's source plus two hops of same-module callees, so thin
#: ``rpc/routers/*.py`` wrappers that delegate to ``rpc/<module>.py``
#: implementations still resolve their verifier.
_SIGNATURE_TOKENS = (
    "verify_request_signature",
    "verify_transaction_signature",
    "verify_signed_request_with_freshness",
    "require_operator_signature",
    "get_signed_dispute_address",
    "require_admin_signature",
    "verify_admin_signature",
    "_verify_market_signature",
)

#: Token proving the wallet-identity gate (``get_authenticated_address`` —
#: trusted X-Wallet-Address / bearer admin credential, fail-closed 401).
_ADMIN_AUTH_TOKENS = ("get_authenticated_address",)

_CALL_RE = re.compile(r"\b([A-Za-z_]\w*)\s*\(")

#: Routes gated by an X-API-Key-family dependency (mechanically verified
#: against ``route.dependant``). Format: ``"METHOD /rpc/path"``.
_KEY_GATED_ROUTES = frozenset(
    {
        "POST /rpc/bridge/ledger/register",
        "POST /rpc/bridge/ledger/{transfer_id}/status",
        "POST /rpc/bridge/settlement/create",
        "POST /rpc/bridge/settlement/{escrow_id}/dispute",
        "POST /rpc/bridge/settlement/{escrow_id}/execute",
        "POST /rpc/bridge/settlement/{escrow_id}/extend-timeout",
        "POST /rpc/bridge/settlement/{escrow_id}/lock",
        "POST /rpc/bridge/settlement/{escrow_id}/refund",
        "POST /rpc/bridge/settlement/{escrow_id}/resolve",
        "POST /rpc/bridge/settlement/{escrow_id}/settle",
        "POST /rpc/bridge/settlement/{escrow_id}/verify",
        "POST /rpc/chains/start",
        "POST /rpc/chains/stop",
        "POST /rpc/contracts/deploy",
        "POST /rpc/contracts/deploy/messaging",
        "POST /rpc/contracts/messaging/messages/post",
        "POST /rpc/contracts/messaging/messages/{message_id}/moderate",
        "POST /rpc/contracts/messaging/messages/{message_id}/vote",
        "POST /rpc/contracts/messaging/topics/create",
        "POST /rpc/edge/register",
        "POST /rpc/escrow/create",
        "POST /rpc/escrow/{job_id}/refund",
        "POST /rpc/escrow/{job_id}/release",
        "POST /rpc/force-sync",
        "POST /rpc/governance/proposal",
        "POST /rpc/governance/proposal/{proposal_id}/execute",
        "POST /rpc/governance/vote",
        "POST /rpc/gpu/allocate",
        "POST /rpc/gpu/register",
        "POST /rpc/heartbeat",
        "POST /rpc/identity/register",
        "POST /rpc/identity/verify",
        "POST /rpc/import-chain",
        "POST /rpc/importBlock",
        "POST /rpc/islands/bridge",
        "POST /rpc/islands/join",
        "POST /rpc/islands/leave",
        "DELETE /rpc/lease/{node_id}",
        "POST /rpc/subscribe",
    }
)

#: Routes whose auth is a cryptographic signature verified inside the handler
#: or its delegated service — secp256k1 over the request/transaction payload
#: (wallet, operator, validator, seller, bridge party, or tx signer). Verified
#: by the source-token sweep, not by a dependency.
_SIGNED_PAYLOAD_ROUTES = frozenset(
    {
        "POST /rpc/agent-staking/agents/{agent_wallet}/distribute",
        "POST /rpc/agent-staking/claim-rewards",
        "POST /rpc/agent-staking/performance",
        "POST /rpc/agent-staking/stake",
        "POST /rpc/agent-staking/stake/{stake_id}/add",
        "POST /rpc/agent-staking/stake/{stake_id}/complete",
        "POST /rpc/agent-staking/stake/{stake_id}/unbond",
        "POST /rpc/ai/job/{job_id}/cancel",
        "POST /rpc/ai/submit",
        "POST /rpc/bounty/deploy",
        "POST /rpc/bounty/{bounty_id}/dispute",
        "POST /rpc/bounty/{bounty_id}/expire",
        "POST /rpc/bounty/{bounty_id}/submit",
        "POST /rpc/bounty/{bounty_id}/verify",
        "POST /rpc/bridge/batch/confirm",
        "POST /rpc/bridge/block-headers",
        "POST /rpc/bridge/confirm",
        "POST /rpc/bridge/lock",
        "POST /rpc/bridge/unlock",
        "POST /rpc/bridge/validators/register",
        "POST /rpc/cross-chain/bridge",
        "POST /rpc/disputes/evidence",
        "POST /rpc/disputes/file",
        "POST /rpc/disputes/verify-evidence",
        "POST /rpc/disputes/vote",
        "POST /rpc/market/create",
        "DELETE /rpc/market/listing/{listing_id}",
        "POST /rpc/staking/stake",
        "POST /rpc/staking/unstake",
        "POST /rpc/swap",
        "POST /rpc/transaction",
        "POST /rpc/transactions/market",
    }
)

#: Routes gated by the admin wallet identity (``get_authenticated_address``).
#: The dispute arbitrator grants additionally carry an owner signature that
#: the contract verifies on-chain.
_ADMIN_AUTH_ROUTES = frozenset(
    {
        "POST /rpc/disputes/arbitrators/authorize",
        "POST /rpc/disputes/arbitrators/revoke",
        "POST /rpc/mining/start",
        "POST /rpc/mining/stop",
    }
)

#: Intentionally-public mutating routes — each entry MUST carry a reason.
#: "Public" is an audited decision, not a default: a route lands here only
#: after someone states why unauthenticated access is safe.
_PUBLIC_ROUTES: dict[str, str] = {
    "POST /rpc/join": (
        "Self-serve island join: anonymous by design — it issues a "
        "node_id-bound peer key. IP rate-limited and capacity-capped "
        "(peer_keys.MAX_KEYS_PER_IP_PER_DAY / MAX_TOTAL_KEYS); the issued key "
        "unlocks only that node's own lease routes."
    ),
    "POST /rpc/register-account": (
        "Read-only account-state report; documented no-write — account rows "
        "are created by the first crediting transaction, never by this route."
    ),
    "POST /rpc/eth_getLogs": ("Read-only event-log query (eth_getLogs-compatible); row/block budgets clamp the scan."),
    "POST /rpc/contracts/call": ("Read-only contract state lookup against the node-local registry; no writes."),
    "POST /rpc/contracts/verify": ("Read-only ZK-proof status check; returns an honest invalid result and writes nothing."),
    "POST /rpc/liquidity/build-deposit": (
        "Build-only: returns an unsigned LIQUIDITY_DEPOSIT transaction for the "
        "caller's wallet to sign and submit via /rpc/transaction."
    ),
    "POST /rpc/liquidity/build-claim": ("Build-only: returns an unsigned LIQUIDITY_CLAIM transaction; no state change."),
    "POST /rpc/liquidity/build-withdraw": ("Build-only: returns an unsigned LIQUIDITY_WITHDRAW transaction; no state change."),
}


def _rpc_auth_decisions() -> dict[str, str]:
    """The full declared auth decision per mutating /rpc route."""
    decisions: dict[str, str] = {}
    for route in _KEY_GATED_ROUTES:
        decisions[route] = "key-gated"
    for route in _SIGNED_PAYLOAD_ROUTES:
        decisions[route] = "signed-payload"
    for route in _ADMIN_AUTH_ROUTES:
        decisions[route] = "admin-auth"
    for route in _PUBLIC_ROUTES:
        decisions[route] = "public"
    return decisions


def _live_rpc_mutating_routes() -> dict[str, object]:
    """Enumerate the app's actual mutating route table under /rpc.

    The rpc router is mounted twice (``/rpc`` and ``/v1``); /v1 paths are
    normalized onto /rpc so both mounts collapse to one decision per route.
    """
    from fastapi.routing import APIRoute

    from aitbc_chain.app import create_app

    found: dict[str, object] = {}
    for route in create_app().routes:
        if not isinstance(route, APIRoute):
            continue
        for method in route.methods & _MUTATING_METHODS:
            path = route.path
            if path.startswith("/v1/"):
                path = "/rpc/" + path[len("/v1/") :]
            if path.startswith("/rpc/"):
                found[f"{method} {path}"] = route
    return found


def _dependency_call_names(route: object) -> set[str]:
    """All callable names in the route's dependency tree (recursive)."""
    names: set[str] = set()
    stack = list(route.dependant.dependencies)  # type: ignore[attr-defined]
    while stack:
        dep = stack.pop()
        call = dep.call
        if call is not None:
            names.add(getattr(call, "__name__", type(call).__name__))
        stack.extend(dep.dependencies)
    return names


def _callable_source_closure(func: object, hops: int = 2) -> str:
    """Source of *func* plus *hops* levels of same-module callees.

    Thin router wrappers delegate to ``rpc/<module>.py`` implementations; the
    callee hop keeps the signature-token sweep honest for them. Decorators are
    unwrapped first (``@rate_limit`` uses ``functools.wraps``).
    """
    parts: list[str] = []
    seen: set[int] = set()
    frontier = [func]
    for _ in range(hops + 1):
        following = []
        for fn in frontier:
            if id(fn) in seen:
                continue
            seen.add(id(fn))
            try:
                target = inspect.unwrap(fn)  # type: ignore[arg-type]
            except ValueError:
                # unwrap() raises ValueError on a __wrapped__ cycle.
                target = fn
            try:
                src = inspect.getsource(target)  # type: ignore[arg-type]
            except (OSError, TypeError):
                continue
            parts.append(src)
            globs = getattr(target, "__globals__", {})
            for name in _CALL_RE.findall(src):
                callee = globs.get(name)
                if callee is not None and (inspect.isfunction(callee) or inspect.ismethod(callee)):
                    following.append(callee)
        frontier = following
    return "\n".join(parts)


class TestRpcAuthCoverageRatchet:
    """#3056: every mutating route under the public /rpc proxy must declare an
    auth decision. The registry above is the ratchet — a new mutating route
    fails here until its class (key-gated / signed-payload / admin-auth /
    intentionally-public-with-reason) is stated, and a stale registry entry
    fails when its route disappears."""

    @pytest.fixture(scope="class")
    def live_routes(self):
        return _live_rpc_mutating_routes()

    @pytest.fixture(scope="class")
    def decisions(self):
        return _rpc_auth_decisions()

    def test_route_table_is_nonempty(self, live_routes):
        """Guard against a silent enumeration break (import failure, prefix
        change) passing every other test vacuously."""
        assert len(live_routes) > 50, f"only {len(live_routes)} mutating /rpc routes found — enumeration is broken"

    def test_every_mutating_route_declares_an_auth_decision(self, live_routes, decisions):
        live = set(live_routes)
        declared = set(decisions)
        undeclared = sorted(live - declared)
        stale = sorted(declared - live)
        assert not undeclared, (
            "Mutating /rpc routes with NO declared auth decision — add each to "
            "_KEY_GATED_ROUTES / _SIGNED_PAYLOAD_ROUTES / _ADMIN_AUTH_ROUTES / "
            "_PUBLIC_ROUTES in this file:\n  " + "\n  ".join(undeclared)
        )
        assert not stale, (
            "Registry entries with no live route — remove them (or fix the "
            "path/method if the route moved):\n  " + "\n  ".join(stale)
        )

    def test_no_duplicate_decisions(self, decisions):
        """A route key must map to exactly one class — the builders above would
        silently overwrite otherwise."""
        total = len(_KEY_GATED_ROUTES) + len(_SIGNED_PAYLOAD_ROUTES) + len(_ADMIN_AUTH_ROUTES) + len(_PUBLIC_ROUTES)
        assert len(decisions) == total, "a route appears in more than one auth-decision class"

    def test_key_gated_routes_carry_a_credential_dependency(self, live_routes, decisions):
        """key-gated is not just a label: the route's dependency tree must
        contain a known X-API-Key-family verifier."""
        offenders = []
        for key, route in live_routes.items():
            if decisions[key] != "key-gated":
                continue
            deps = _dependency_call_names(route)
            if not deps & _KEY_GATE_DEPENDENCIES:
                offenders.append(f"{key} (deps: {sorted(deps) or 'none'})")
        assert not offenders, "Declared key-gated but no verify_rpc_* dependency found:\n  " + "\n  ".join(offenders)

    def test_public_routes_have_no_credential_dependency(self, live_routes, decisions):
        """A route declared public must not secretly carry a key gate — if it
        does, it belongs in _KEY_GATED_ROUTES instead."""
        offenders = []
        for key, route in live_routes.items():
            if decisions[key] != "public":
                continue
            deps = _dependency_call_names(route)
            if deps & _KEY_GATE_DEPENDENCIES:
                offenders.append(f"{key} (deps: {sorted(deps & _KEY_GATE_DEPENDENCIES)})")
        assert not offenders, "Declared public but carries a credential dependency:\n  " + "\n  ".join(offenders)

    def test_public_routes_carry_a_reason(self):
        for key, reason in _PUBLIC_ROUTES.items():
            assert reason and reason.strip(), f"{key} is public without a stated reason"

    def test_signed_payload_routes_verify_a_signature(self, live_routes, decisions):
        """signed-payload is verified by source: the endpoint (or a callee two
        hops down) must reference a known signature verifier."""
        offenders = []
        for key, route in live_routes.items():
            if decisions[key] != "signed-payload":
                continue
            closure = _callable_source_closure(route.endpoint)  # type: ignore[attr-defined]
            if not any(token in closure for token in _SIGNATURE_TOKENS):
                offenders.append(key)
        assert not offenders, (
            "Declared signed-payload but no signature verifier found in the "
            "handler call graph — reclassify or fix the handler:\n  " + "\n  ".join(offenders)
        )

    def test_admin_auth_routes_require_wallet_identity(self, live_routes, decisions):
        offenders = []
        for key, route in live_routes.items():
            if decisions[key] != "admin-auth":
                continue
            closure = _callable_source_closure(route.endpoint)  # type: ignore[attr-defined]
            if not any(token in closure for token in _ADMIN_AUTH_TOKENS):
                offenders.append(key)
        assert not offenders, (
            "Declared admin-auth but get_authenticated_address not found in the "
            "handler call graph:\n  " + "\n  ".join(offenders)
        )
