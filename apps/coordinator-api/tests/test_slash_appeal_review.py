"""#2966: governance terminal review of slash appeals.

``POST /governance/slash-appeals/{id}/resolve`` is admin-only. ``accepted``
restores the local bond projection only after a fresh chain point-read proves
the on-chain bond is ``active`` and unburned — it moves no funds and never
reverses a sealed BOND_SLASH. ``rejected`` only closes the appeal. Chain
access is stubbed at ``BlockchainService.get_bond``; everything else is real
SQLite state.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from aitbc.auth import create_access_token
from aitbc.exceptions import NetworkError

from coordinator_api.contexts.blockchain.services.blockchain import BlockchainService
from coordinator_api.contexts.governance.domain.slash_appeal import SlashAppeal, SlashAppealStatus
from coordinator_api.contexts.market.domain.provider_bond import ProviderBond, ProviderBondStatus

pytestmark = pytest.mark.unit

WALLET = "0x" + "11" * 20
OTHER_WALLET = "0x" + "22" * 20
PROVIDER_ID = "provider-1"
BOND_ID = "cb-appeal-1"
UNITS_PER_AIT = 36_000_000


def _headers(user_id: str = "admin-1", role: str = "admin") -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user_id, role)}"}


@pytest.fixture
def chain_state(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Stub ``BlockchainService.get_bond``; tests set ``response``/``error``.

    ``calls`` records the exact ``bond_id`` each lookup asked for.
    """
    state: dict[str, Any] = {"response": None, "error": None, "calls": []}

    def fake_get_bond(self: BlockchainService, bond_id: str) -> dict[str, Any]:
        state["calls"].append(bond_id)
        if state["error"] is not None:
            raise state["error"]
        return state["response"]

    monkeypatch.setattr(BlockchainService, "get_bond", fake_get_bond)
    return state


def _chain_bond(
    bond_id: str = BOND_ID,
    provider: str = WALLET,
    amount_ait: str = "10",
    status: str = "active",
    slashed_tx_hash: str | None = None,
    *,
    success: bool = True,
    include_slash_hash: bool = True,
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "success": success,
        "bond_id": bond_id,
        "provider": provider,
        "amount": int(Decimal(amount_ait) * UNITS_PER_AIT),
        "status": status,
        "locked_until": None,
        "created_tx_hash": "0xcreate",
        "released_tx_hash": None,
    }
    if include_slash_hash:
        record["slashed_tx_hash"] = slashed_tx_hash
    return record


def _legacy_meta(**over: Any) -> dict[str, Any]:
    """Meta written by the retired manual slash route — including a stale
    local ``slash_tx_hash`` holding an unrelated older action id and an old
    ``chain_verified_at`` reconcile cache stamp acceptance must drop."""
    meta: dict[str, Any] = {
        "chain_provider": WALLET,
        "chain_bond_id": BOND_ID,
        "slash_reason": "failed SLA",
        "slashed_by": "admin-1",
        "slash_tx_hash": "0xstale-local-action",
        "chain_verified_at": "2026-01-01T00:00:00+00:00",
    }
    meta.update(over)
    return meta


def _suspension_meta(event_id: str = "sev-1", **over: Any) -> dict[str, Any]:
    meta: dict[str, Any] = {
        "chain_provider": WALLET,
        "suspension_event_id": event_id,
        "suspended_at": "2026-11-20T00:00:00+00:00",
        "suspended_by": "admin-1",
        "suspension_reason": "operator review",
        "chain_verified_at": "2026-01-01T00:00:00+00:00",
    }
    meta.update(over)
    return meta


def _seed_bond(
    session: Session,
    *,
    status: str,
    meta: dict[str, Any],
    amount: str = "10",
    required: str = "5",
    provider_id: str = PROVIDER_ID,
    bond_id: str = BOND_ID,
) -> ProviderBond:
    bond = ProviderBond(
        provider_id=provider_id,
        bond_id=bond_id,
        status=status,
        amount=Decimal(amount),
        required_amount=Decimal(required),
        meta=meta,
    )
    session.add(bond)
    session.commit()
    session.refresh(bond)
    return bond


def _seed_legacy_bond(session: Session, **over: Any) -> ProviderBond:
    return _seed_bond(session, status=ProviderBondStatus.LIQUIDATED.value, meta=_legacy_meta(), **over)


def _seed_appeal(
    session: Session,
    *,
    bond_id: str = BOND_ID,
    provider_id: str = PROVIDER_ID,
    slash_event_id: str = "",
    status: str = SlashAppealStatus.SUBMITTED.value,
) -> SlashAppeal:
    appeal = SlashAppeal(
        bond_id=bond_id,
        provider_id=provider_id,
        slash_event_id=slash_event_id,
        reason="false positive",
        status=status,
    )
    session.add(appeal)
    session.commit()
    session.refresh(appeal)
    return appeal


def _resolve(
    client: TestClient,
    appeal_id: str,
    *,
    decision: str = "accepted",
    notes: str = "reviewed",
    headers: dict[str, str] | None = None,
):
    return client.post(
        f"/v1/governance/slash-appeals/{appeal_id}/resolve",
        json={"decision": decision, "notes": notes},
        headers=headers or _headers(),
    )


def _bond_row(session: Session, bond_id: str = BOND_ID) -> ProviderBond | None:
    return session.exec(select(ProviderBond).where(ProviderBond.bond_id == bond_id)).first()


def _appeal_row(session: Session, appeal_id: str) -> SlashAppeal | None:
    return session.exec(select(SlashAppeal).where(SlashAppeal.id == appeal_id)).first()


def _appeal_status(session: Session, appeal_id: str) -> str:
    row = _appeal_row(session, appeal_id)
    assert row is not None
    return row.status


def _ait(value: Any) -> Decimal:
    return Decimal(str(value))


class TestResolveAuthAndLifecycle:
    def test_unknown_appeal_is_404(self, client: TestClient) -> None:
        assert _resolve(client, "sa_missing").status_code == 404

    def test_terminal_appeal_cannot_be_resolved(self, client: TestClient, db_session: Session) -> None:
        appeal = _seed_appeal(db_session, status=SlashAppealStatus.REJECTED.value)
        assert _resolve(client, appeal.id).status_code == 409

    def test_non_admin_provider_owner_is_403(self, client: TestClient, db_session: Session) -> None:
        """AdminDep has no wallet-ownership override — the provider whose bond
        is under review still cannot resolve their own appeal."""
        _seed_legacy_bond(db_session)
        appeal = _seed_appeal(db_session)
        resp = _resolve(client, appeal.id, headers=_headers(user_id=PROVIDER_ID, role="client"))
        assert resp.status_code == 403

    def test_appeal_without_matching_bond_is_409(self, client: TestClient, db_session: Session) -> None:
        """The appeal's provider_id/bond_id binding must still match a bond row —
        never resolve against a rebound bond_id."""
        _seed_bond(db_session, status=ProviderBondStatus.LIQUIDATED.value, meta=_legacy_meta(), provider_id="provider-2")
        appeal = _seed_appeal(db_session, provider_id=PROVIDER_ID)
        assert _resolve(client, appeal.id).status_code == 409


class TestAcceptLegacyLiquidation:
    def test_accept_restores_active_from_chain(
        self, client: TestClient, db_session: Session, chain_state: dict[str, Any]
    ) -> None:
        """A legacy-marked liquidation clears only when the chain proves the
        bond active and never slashed; the authoritative chain amount wins and
        all local audit (including a stale slash_tx_hash) is preserved."""
        _seed_legacy_bond(db_session)
        appeal = _seed_appeal(db_session)
        chain_state["response"] = _chain_bond(amount_ait="12", slashed_tx_hash=None)

        resp = _resolve(client, appeal.id)

        assert resp.status_code == 200, resp.text
        assert resp.json() == {
            "id": appeal.id,
            "bond_id": BOND_ID,
            "provider_id": PROVIDER_ID,
            "status": "accepted",
            "bond_status": "active",
            "funds_moved": False,
        }
        assert chain_state["calls"] == [BOND_ID]
        row = _bond_row(db_session)
        assert row is not None
        assert row.status == ProviderBondStatus.ACTIVE.value
        assert _ait(row.amount) == Decimal("12")
        meta = row.meta
        assert meta["chain_status"] == "active"
        assert meta["chain_amount_units"] == int(Decimal("12") * UNITS_PER_AIT)
        assert meta["appeal_resolution_id"] == appeal.id
        assert meta["appeal_resolved_by"] == "admin-1"
        assert meta["slash_reason"] == "failed SLA"
        assert meta["slashed_by"] == "admin-1"
        assert meta["slash_tx_hash"] == "0xstale-local-action"
        assert "suspension_event_id" not in meta
        # The appeal's chain read is decision proof only — it must not seed
        # the reconcile TTL cache; the audit stamp records when it ran.
        assert "chain_verified_at" not in meta
        assert meta["appeal_chain_verified_at"]
        resolved = _appeal_row(db_session, appeal.id)
        assert resolved is not None
        assert resolved.status == SlashAppealStatus.ACCEPTED.value
        assert resolved.reviewer_notes == "reviewed"
        # Terminal: a second resolve is refused.
        assert _resolve(client, appeal.id).status_code == 409

    def test_accept_below_floor_restores_shortfall(
        self, client: TestClient, db_session: Session, chain_state: dict[str, Any]
    ) -> None:
        _seed_legacy_bond(db_session)  # required_amount 5 -> floor 5
        appeal = _seed_appeal(db_session)
        chain_state["response"] = _chain_bond(amount_ait="2", slashed_tx_hash=None)

        resp = _resolve(client, appeal.id)

        assert resp.status_code == 200, resp.text
        assert resp.json()["bond_status"] == "shortfall"
        row = _bond_row(db_session)
        assert row is not None
        assert row.status == ProviderBondStatus.SHORTFALL.value
        assert _ait(row.amount) == Decimal("2")

        # #2966 review: a SHORTFALL projection sits below the required floor —
        # local lock/release bookkeeping must not launder it back to
        # ACTIVE/LOCKED (and job eligibility keeps its own minimum anyway).
        for action in ("lock", "release"):
            resp = client.post(
                f"/v1/market/providers/{PROVIDER_ID}/bonds/{action}",
                headers=_headers(),
            )
            assert resp.status_code == 409, (action, resp.text)
        row = _bond_row(db_session)
        assert row is not None
        assert row.status == ProviderBondStatus.SHORTFALL.value


class TestReject:
    def test_reject_leaves_bond_untouched(self, client: TestClient, db_session: Session, chain_state: dict[str, Any]) -> None:
        _seed_legacy_bond(db_session)
        appeal = _seed_appeal(db_session)

        resp = _resolve(client, appeal.id, decision="rejected", notes="evidence insufficient")

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "rejected"
        assert body["bond_status"] == "liquidated"
        assert body["funds_moved"] is False
        # Rejection never consults the chain and never touches the bond row.
        assert chain_state["calls"] == []
        row = _bond_row(db_session)
        assert row is not None
        assert row.status == ProviderBondStatus.LIQUIDATED.value
        assert _ait(row.amount) == Decimal("10")
        resolved = _appeal_row(db_session, appeal.id)
        assert resolved is not None
        assert resolved.status == SlashAppealStatus.REJECTED.value
        assert resolved.reviewer_notes == "evidence insufficient"

    def test_reject_reports_suspended_projection(
        self, client: TestClient, db_session: Session, chain_state: dict[str, Any]
    ) -> None:
        """A rejected appeal on a suspended bond reports the projected
        ``suspended`` state; the bond row and suspension flag stay as-is."""
        _seed_bond(
            db_session,
            status=ProviderBondStatus.ACTIVE.value,
            meta=_suspension_meta(),
        )
        appeal = _seed_appeal(db_session, slash_event_id="sev-1")

        resp = _resolve(client, appeal.id, decision="rejected", notes="not a slash")

        assert resp.status_code == 200, resp.text
        assert resp.json()["bond_status"] == "suspended"
        assert chain_state["calls"] == []
        row = _bond_row(db_session)
        assert row is not None
        assert row.status == ProviderBondStatus.ACTIVE.value
        assert row.meta["suspension_event_id"] == "sev-1"


class TestAcceptSuspension:
    def test_accept_restores_fresh_chain_balance(
        self, client: TestClient, db_session: Session, chain_state: dict[str, Any]
    ) -> None:
        """Suspension acceptance uses the authoritative chain balance — a
        partial automatic slash while suspended is never restored — and lifts
        only the suspension flag, keeping its audit."""
        _seed_bond(db_session, status=ProviderBondStatus.ACTIVE.value, meta=_suspension_meta())
        appeal = _seed_appeal(db_session, slash_event_id="sev-1")
        # The automatic slasher ran while suspended: lower balance, its own
        # slash hash — neither may be compared against or undone here.
        chain_state["response"] = _chain_bond(amount_ait="7", slashed_tx_hash="0xautoslash")

        resp = _resolve(client, appeal.id)

        assert resp.status_code == 200, resp.text
        assert resp.json()["bond_status"] == "active"
        assert chain_state["calls"] == [BOND_ID]
        row = _bond_row(db_session)
        assert row is not None
        assert row.status == ProviderBondStatus.ACTIVE.value
        assert _ait(row.amount) == Decimal("7")
        meta = row.meta
        assert "suspension_event_id" not in meta
        assert meta["resolved_suspension_event_id"] == "sev-1"
        assert meta["suspended_by"] == "admin-1"
        assert meta["suspension_reason"] == "operator review"
        assert meta["chain_status"] == "active"
        # Same cache rule as legacy: no fresh chain_verified_at from the
        # appeal read — next dispatch re-verifies; audit keeps the stamp.
        assert "chain_verified_at" not in meta
        assert meta["appeal_chain_verified_at"]
        assert _appeal_status(db_session, appeal.id) == SlashAppealStatus.ACCEPTED.value

    def test_accept_preserves_locked_projection(
        self, client: TestClient, db_session: Session, chain_state: dict[str, Any]
    ) -> None:
        """A suspended bond that was LOCKED stays LOCKED when the fresh chain
        balance still clears the floor — the chain cannot see the job lock."""
        _seed_bond(db_session, status=ProviderBondStatus.LOCKED.value, meta=_suspension_meta())
        appeal = _seed_appeal(db_session, slash_event_id="sev-1")
        chain_state["response"] = _chain_bond(amount_ait="12", slashed_tx_hash=None)

        resp = _resolve(client, appeal.id)

        assert resp.status_code == 200, resp.text
        assert resp.json()["bond_status"] == "locked"
        row = _bond_row(db_session)
        assert row is not None
        assert row.status == ProviderBondStatus.LOCKED.value
        assert _ait(row.amount) == Decimal("12")

    def test_accept_mismatched_suspension_event_is_409(
        self, client: TestClient, db_session: Session, chain_state: dict[str, Any]
    ) -> None:
        """The appeal must name the suspension it disputes — a different
        slash_event_id is not actionable and never reaches the chain."""
        _seed_bond(db_session, status=ProviderBondStatus.ACTIVE.value, meta=_suspension_meta())
        appeal = _seed_appeal(db_session, slash_event_id="sev-other")

        resp = _resolve(client, appeal.id)

        assert resp.status_code == 409, resp.text
        assert chain_state["calls"] == []
        row = _bond_row(db_session)
        assert row is not None
        assert row.status == ProviderBondStatus.ACTIVE.value
        assert row.meta["suspension_event_id"] == "sev-1"
        assert _appeal_status(db_session, appeal.id) == SlashAppealStatus.SUBMITTED.value

    def test_suspension_appeal_without_event_id_is_409(
        self, client: TestClient, db_session: Session, chain_state: dict[str, Any]
    ) -> None:
        """A suspension is only resolvable by an appeal that names its event —
        an empty slash_event_id cannot accidentally clear it."""
        _seed_bond(db_session, status=ProviderBondStatus.ACTIVE.value, meta=_suspension_meta())
        appeal = _seed_appeal(db_session, slash_event_id="")

        resp = _resolve(client, appeal.id)

        assert resp.status_code == 409, resp.text
        assert chain_state["calls"] == []
        row = _bond_row(db_session)
        assert row is not None
        assert row.meta["suspension_event_id"] == "sev-1"
        assert _appeal_status(db_session, appeal.id) == SlashAppealStatus.SUBMITTED.value


def _mut_status_slashed(record: dict[str, Any]) -> None:
    record["status"] = "slashed"


def _mut_hash_recorded(record: dict[str, Any]) -> None:
    record["slashed_tx_hash"] = "0xdeadbeef"


def _mut_other_provider(record: dict[str, Any]) -> None:
    record["provider"] = OTHER_WALLET


def _mut_provider_missing(record: dict[str, Any]) -> None:
    del record["provider"]


def _mut_no_slash_hash_key(record: dict[str, Any]) -> None:
    del record["slashed_tx_hash"]


def _mut_success_false(record: dict[str, Any]) -> None:
    record["success"] = False


def _mut_wrong_bond_id(record: dict[str, Any]) -> None:
    record["bond_id"] = "cb-other"


def _mut_amount_zero(record: dict[str, Any]) -> None:
    record["amount"] = 0


def _mut_amount_bool(record: dict[str, Any]) -> None:
    record["amount"] = True


def _mut_amount_string(record: dict[str, Any]) -> None:
    record["amount"] = "36000000"


class TestAcceptRejectsInconsistentChainProof:
    """Every chain inconsistency is a 409 that leaves the appeal open and the
    bond untouched — acceptance is all-or-nothing in one transaction."""

    @pytest.mark.parametrize(
        "mutate",
        [
            _mut_status_slashed,
            _mut_hash_recorded,
            _mut_other_provider,
            _mut_provider_missing,
            _mut_no_slash_hash_key,
            _mut_success_false,
            _mut_wrong_bond_id,
            _mut_amount_zero,
            _mut_amount_bool,
            _mut_amount_string,
        ],
        ids=lambda f: f.__name__.removeprefix("_mut_"),
    )
    def test_inconsistent_chain_proof_is_409(
        self,
        client: TestClient,
        db_session: Session,
        chain_state: dict[str, Any],
        mutate: Any,
    ) -> None:
        _seed_legacy_bond(db_session)
        appeal = _seed_appeal(db_session)
        record = _chain_bond(slashed_tx_hash=None)
        mutate(record)
        chain_state["response"] = record

        resp = _resolve(client, appeal.id)

        assert resp.status_code == 409, resp.text
        assert chain_state["calls"] == [BOND_ID]
        assert _appeal_status(db_session, appeal.id) == SlashAppealStatus.SUBMITTED.value
        row = _bond_row(db_session)
        assert row is not None
        assert row.status == ProviderBondStatus.LIQUIDATED.value
        assert _ait(row.amount) == Decimal("10")

    def test_missing_meta_chain_provider_is_409_without_rpc(
        self, client: TestClient, db_session: Session, chain_state: dict[str, Any]
    ) -> None:
        """No registered-wallet fallback: without the creation-time
        chain_provider there is nothing to verify against — no RPC is spent."""
        meta = _legacy_meta()
        del meta["chain_provider"]
        _seed_bond(db_session, status=ProviderBondStatus.LIQUIDATED.value, meta=meta)
        appeal = _seed_appeal(db_session)

        resp = _resolve(client, appeal.id)

        assert resp.status_code == 409, resp.text
        assert chain_state["calls"] == []
        assert _appeal_status(db_session, appeal.id) == SlashAppealStatus.SUBMITTED.value

    def test_unsafe_bond_id_is_409_without_rpc(
        self, client: TestClient, db_session: Session, chain_state: dict[str, Any]
    ) -> None:
        meta = _legacy_meta(chain_bond_id="..")
        _seed_bond(db_session, status=ProviderBondStatus.LIQUIDATED.value, meta=meta, bond_id="..")
        appeal = _seed_appeal(db_session, bond_id="..")

        resp = _resolve(client, appeal.id)

        assert resp.status_code == 409, resp.text
        assert chain_state["calls"] == []

    def test_chain_rpc_error_is_502(self, client: TestClient, db_session: Session, chain_state: dict[str, Any]) -> None:
        _seed_legacy_bond(db_session)
        appeal = _seed_appeal(db_session)
        chain_state["error"] = NetworkError("chain unreachable")

        resp = _resolve(client, appeal.id)

        assert resp.status_code == 502, resp.text
        assert _appeal_status(db_session, appeal.id) == SlashAppealStatus.SUBMITTED.value
        row = _bond_row(db_session)
        assert row is not None
        assert row.status == ProviderBondStatus.LIQUIDATED.value

    def test_non_dict_chain_response_is_409(
        self, client: TestClient, db_session: Session, chain_state: dict[str, Any]
    ) -> None:
        """A malformed (non-object) RPC payload fails closed like any other
        inconsistent proof — it is not a crash and not an acceptance."""
        _seed_legacy_bond(db_session)
        appeal = _seed_appeal(db_session)
        chain_state["response"] = ["not", "a", "dict"]

        resp = _resolve(client, appeal.id)

        assert resp.status_code == 409, resp.text
        assert _appeal_status(db_session, appeal.id) == SlashAppealStatus.SUBMITTED.value
        row = _bond_row(db_session)
        assert row is not None
        assert row.status == ProviderBondStatus.LIQUIDATED.value


class TestStaleWriterCannotBeOverwritten:
    """The bond restore is compare-and-swap: when the row moved between the
    appeal's snapshot and the write (a concurrent suspension, slash or
    rebind), acceptance must fail closed — no stale restore, appeal stays
    open, and the newer row state is untouched."""

    def test_bond_cas_failure_rolls_back_acceptance(
        self, client: TestClient, db_session: Session, chain_state: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from coordinator_api.contexts.governance.services import slash_appeal_review

        _seed_legacy_bond(db_session)
        appeal = _seed_appeal(db_session)
        chain_state["response"] = _chain_bond(amount_ait="12", slashed_tx_hash=None)
        monkeypatch.setattr(slash_appeal_review, "stage_bond_projection", lambda *a, **k: False)

        resp = _resolve(client, appeal.id)

        assert resp.status_code == 409, resp.text
        # Single transaction: the appeal transition rolled back with the bond.
        assert _appeal_status(db_session, appeal.id) == SlashAppealStatus.SUBMITTED.value
        row = _bond_row(db_session)
        assert row is not None
        assert row.status == ProviderBondStatus.LIQUIDATED.value
        assert _ait(row.amount) == Decimal("10")
