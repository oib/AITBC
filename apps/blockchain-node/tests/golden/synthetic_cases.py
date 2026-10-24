"""Synthetic golden-vector cases — every gate branch in the Phase 0 matrix.

Each case is ``{case_id, gate, description, chain_id, prestate, block, tx|txs}``:

- ``prestate`` maps table names to row dicts (raw inserts — the same rows a
  follower would hold after replaying the earlier history the case assumes:
  sealed ``transaction`` rows for locks/proposes, ``block`` rows for
  lock-version lookups, ``chain_parameter`` rows for the authority
  parameters, ``gpu_registration``/``cross_chain_transfer`` where needed).
- ``block`` is ``{height, block_metadata}`` — ``get_block_version`` derives
  the version the same way ``_append_block`` does: at/above the v8 pin the
  height wins, below it a recorded ``state_transition_version`` stamp wins,
  and under ``gates0`` (all pins 0) every threshold is falsy so a stamp always
  wins and an unstamped block replays as v1. Cases pick heights that target
  the intended version under ``deployed``; the stamp is included where the
  real history would have written one.

Keys are fixed test scalars like the rest of the suite (deterministic
addresses/signatures — they control nothing). Signatures are computed at
build time so the corpus JSONs carry the real signature bytes as data.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from aitbc.crypto.crypto import derive_ethereum_address
from aitbc_chain.rpc.utils import sign_transaction_data
from aitbc_chain.state.bridge_credit import sign_bridge_credit, sign_bridge_lock
from aitbc_chain.state.state_transition import _escrow_address

CHAIN = "gv-synth"

KEY_A = "0x" + "11" * 32
KEY_B = "0x" + "22" * 32
KEY_AUTH = "0x" + "33" * 32  # settlement + bridge authority
KEY_EXEC = "0x" + "44" * 32  # governance executor
KEY_OTHER = "0x" + "55" * 32  # funded non-authority

ADDR_A = derive_ethereum_address(KEY_A)
ADDR_B = derive_ethereum_address(KEY_B)
ADDR_AUTH = derive_ethereum_address(KEY_AUTH)
ADDR_EXEC = derive_ethereum_address(KEY_EXEC)
ADDR_OTHER = derive_ethereum_address(KEY_OTHER)

_EXECUTOR_MIN_BALANCE_UNITS = 1  # conservative — the v12 funded-member floor


def _tx_hash(*parts: Any) -> str:
    return "0x" + hashlib.sha256(":".join(str(p) for p in parts).encode()).hexdigest()


def _tx(
    case_id: str,
    n: int,
    tx_type: str,
    *,
    sender: str,
    to: str = "",
    value: int = 0,
    fee: int = 1,
    nonce: int = 0,
    payload: dict | None = None,
    **extra: Any,
) -> dict[str, Any]:
    tx = {
        "from": sender,
        "to": to,
        "value": value,
        "amount": value,
        "fee": fee,
        "nonce": nonce,
        "payload": payload or {},
        "type": tx_type,
        "chain_id": CHAIN,
        "tx_hash": _tx_hash(case_id, n),
        **extra,
    }
    return tx


def _sign(tx: dict[str, Any], key: str) -> dict[str, Any]:
    tx["signature"] = sign_transaction_data(tx, key)
    return tx


def _block(height: int, version: int | None = None) -> dict[str, Any]:
    meta = {"state_transition_version": version} if version is not None else None
    return {
        "height": height,
        "hash": _tx_hash("block", height),
        "timestamp": "2026-01-01T00:00:00+00:00",
        "block_metadata": meta,
    }


def _acct(address: str, balance: int, nonce: int = 0) -> dict[str, Any]:
    return {"chain_id": CHAIN, "address": address, "balance": balance, "nonce": nonce}


def _param(name: str, value: str, applied_height: int = 0) -> dict[str, Any]:
    return {"chain_id": CHAIN, "parameter": name, "value": value, "applied_height": applied_height}


def _sealed_tx(
    case_id: str,
    tag: str,
    tx_type: str,
    *,
    height: int,
    sender: str,
    recipient: str = "",
    value: int = 0,
    payload: dict | None = None,
    nonce: int = 0,
) -> dict[str, Any]:
    return {
        "chain_id": CHAIN,
        "tx_hash": _tx_hash(case_id, "sealed", tag),
        "block_height": height,
        "sender": sender,
        "recipient": recipient,
        "payload": payload or {},
        "type": tx_type,
        "value": value,
        "fee": 1,
        "nonce": nonce,
        "status": "confirmed",
        "created_at": "2026-01-01 00:00:00",
    }


def _sealed_block(case_id: str, tag: str, height: int, version: int | None = None) -> dict[str, Any]:
    return {
        "chain_id": CHAIN,
        "height": height,
        "hash": _tx_hash(case_id, "sealedblock", tag),
        "parent_hash": "0x00",
        "proposer": ADDR_A,
        "timestamp": "2026-01-01 00:00:00",
        "tx_count": 1,
        "block_metadata": {"state_transition_version": version} if version is not None else None,
    }


def _escrow_lock_row(
    case_id: str, tag: str, height: int, *, job: str, provider: str, sender: str, value: int
) -> dict[str, Any]:
    return _sealed_tx(
        case_id,
        tag,
        "ESCROW_LOCK",
        height=height,
        sender=sender,
        recipient="",
        value=value,
        payload={"job_id": job, "provider": provider},
    )


def _bridge_lock_row(case_id: str, tag: str, height: int, *, sender: str, value: int) -> dict[str, Any]:
    h = _tx_hash(case_id, "sealed", tag)
    return {
        **_sealed_tx(
            case_id,
            tag,
            "BRIDGE_LOCK",
            height=height,
            sender=sender,
            recipient="bridge_lock",
            value=value,
            payload={
                "transfer_id": h,
                "amount": value,
                "target_chain": "sep",
                "target_recipient": "0x" + "ab" * 20,
                "asset": "AIT",
            },
        ),
        "tx_hash": h,
    }


def _propose_row(case_id: str, tag: str, height: int, proposal_id: str, execution_payload: dict | None) -> dict[str, Any]:
    payload: dict[str, Any] = {"proposal_id": proposal_id, "title": tag}
    if execution_payload is not None:
        payload["execution_payload"] = execution_payload
    return _sealed_tx(case_id, tag, "GOVERNANCE_PROPOSE", height=height, sender=ADDR_EXEC, payload=payload)


def _execute_row(case_id: str, tag: str, height: int, proposal_id: str, execution_payload: dict | None) -> dict[str, Any]:
    payload: dict[str, Any] = {"proposal_id": proposal_id}
    if execution_payload is not None:
        payload["execution_payload"] = execution_payload
    return _sealed_tx(case_id, tag, "GOVERNANCE_EXECUTE", height=height, sender=ADDR_EXEC, payload=payload)


def cases() -> list[dict[str, Any]]:
    job_v2 = "job-v2-era"
    job_v3 = "job-v3-era"
    job_sweep = "job-sweep"
    cases: list[dict[str, Any]] = [
        # ---- v1/v2/v3 escrow-lock eras -------------------------------------
        {
            "case_id": "escrow-lock-unversioned-v1",
            "gate": "v2",
            "description": "Unstamped ESCROW_LOCK below every pin — deployed: v1 (no account auto-create); gates0: v2.",
            "prestate": {"account": [_acct(ADDR_A, 10_000)]},
            "block": _block(3000),
            "tx": _tx("escrow-lock-unversioned-v1", 0, "ESCROW_LOCK", sender=ADDR_A, to=ADDR_B, value=1000, payload={}),
        },
        {
            "case_id": "escrow-lock-v3-custody",
            "gate": "v3",
            "description": "ESCROW_LOCK in the v3 band: job_id+provider required, "
            "value goes to the derived escrow address. gates0: unstamped -> v2 "
            "plain transfer.",
            "prestate": {"account": [_acct(ADDR_A, 10_000)]},
            "block": _block(6000),
            "tx": _tx(
                "escrow-lock-v3-custody",
                0,
                "ESCROW_LOCK",
                sender=ADDR_A,
                to=ADDR_B,
                value=1000,
                payload={"job_id": job_v3, "provider": ADDR_B},
            ),
        },
        {
            "case_id": "escrow-lock-v3-missing-job",
            "gate": "v3",
            "description": "v3 custody refuses a lock with no job_id.",
            "prestate": {"account": [_acct(ADDR_A, 10_000)]},
            "block": _block(6000),
            "tx": _tx(
                "escrow-lock-v3-missing-job",
                0,
                "ESCROW_LOCK",
                sender=ADDR_A,
                to=ADDR_B,
                value=1000,
                payload={"provider": ADDR_B},
            ),
        },
        {
            "case_id": "escrow-lock-post-v4",
            "gate": "v4",
            "description": "ESCROW_LOCK after 11000 — same custody path.",
            "prestate": {"account": [_acct(ADDR_A, 10_000)]},
            "block": _block(12000),
            "tx": _tx(
                "escrow-lock-post-v4",
                0,
                "ESCROW_LOCK",
                sender=ADDR_A,
                to=ADDR_B,
                value=1000,
                payload={"job_id": "job-post-v4", "provider": ADDR_B},
            ),
        },
        # ---- escrow release/refund over locks of each era -------------------
        {
            "case_id": "escrow-release-v2lock",
            "gate": "v2-era lock / v3 apply",
            "description": "Release at v3 height of a lock sealed below 5470: "
            "lock_version resolves to the pre-v3 fallback and value comes from "
            "the SENDER, not the custody address. Lenient authority (pre-v5).",
            "prestate": {
                "account": [_acct(ADDR_A, 10_000)],
                "transaction": [
                    _escrow_lock_row(
                        "escrow-release-v2lock", "lock", 3000, job=job_v2, provider=ADDR_B, sender=ADDR_A, value=1000
                    ),
                ],
                "block": [_sealed_block("escrow-release-v2lock", "lock", 3000)],
            },
            "block": _block(6000),
            "tx": _tx(
                "escrow-release-v2lock", 0, "ESCROW_RELEASE", sender=ADDR_A, to=ADDR_B, value=1000, payload={"job_id": job_v2}
            ),
        },
        {
            "case_id": "escrow-release-v3lock",
            "gate": "v3/v4",
            "description": "Release of a v3 custody lock at v4: settlement "
            "authority signs, pays fee only; escrow address pays provider.",
            "prestate": {
                "account": [_acct(ADDR_AUTH, 10_000), _acct(_escrow_address(job_v3), 1000)],
                "transaction": [
                    _escrow_lock_row(
                        "escrow-release-v3lock", "lock", 6000, job=job_v3, provider=ADDR_B, sender=ADDR_A, value=1000
                    ),
                ],
                "block": [_sealed_block("escrow-release-v3lock", "lock", 6000, version=3)],
                "chain_parameter": [_param("escrow_settlement_authority", ADDR_AUTH)],
            },
            "block": _block(12000),
            "tx": _tx(
                "escrow-release-v3lock",
                0,
                "ESCROW_RELEASE",
                sender=ADDR_AUTH,
                to=ADDR_B,
                value=1000,
                payload={"job_id": job_v3},
            ),
        },
        {
            "case_id": "escrow-release-wrong-signer",
            "gate": "v3/v4",
            "description": "Same custody release signed by a non-authority — refused.",
            "prestate": {
                "account": [_acct(ADDR_A, 10_000), _acct(_escrow_address(job_v3), 1000)],
                "transaction": [
                    _escrow_lock_row(
                        "escrow-release-wrong-signer", "lock", 6000, job=job_v3, provider=ADDR_B, sender=ADDR_A, value=1000
                    ),
                ],
                "block": [_sealed_block("escrow-release-wrong-signer", "lock", 6000, version=3)],
                "chain_parameter": [_param("escrow_settlement_authority", ADDR_AUTH)],
            },
            "block": _block(12000),
            "tx": _tx(
                "escrow-release-wrong-signer",
                0,
                "ESCROW_RELEASE",
                sender=ADDR_A,
                to=ADDR_B,
                value=1000,
                payload={"job_id": job_v3},
            ),
        },
        {
            "case_id": "escrow-release-v2lock-v5-failclosed",
            "gate": "v5",
            "description": "v5 fail-closed: a release at 24500 with no "
            "escrow_settlement_authority parameter is refused even though the "
            "v2-era lock predates the authority rule.",
            "prestate": {
                "account": [_acct(ADDR_A, 10_000)],
                "transaction": [
                    _escrow_lock_row(
                        "escrow-release-v2lock-v5-failclosed",
                        "lock",
                        3000,
                        job=job_v2,
                        provider=ADDR_B,
                        sender=ADDR_A,
                        value=1000,
                    ),
                ],
                "block": [_sealed_block("escrow-release-v2lock-v5-failclosed", "lock", 3000)],
            },
            "block": _block(24500),
            "tx": _tx(
                "escrow-release-v2lock-v5-failclosed",
                0,
                "ESCROW_RELEASE",
                sender=ADDR_A,
                to=ADDR_B,
                value=1000,
                payload={"job_id": job_v2},
            ),
        },
        {
            "case_id": "escrow-refund-v3lock",
            "gate": "v3/v4",
            "description": "v3 custody refund pays the LOCK SENDER, authority signs.",
            "prestate": {
                "account": [_acct(ADDR_AUTH, 10_000), _acct(_escrow_address(job_v3), 1000)],
                "transaction": [
                    _escrow_lock_row(
                        "escrow-refund-v3lock", "lock", 6000, job=job_v3, provider=ADDR_B, sender=ADDR_A, value=1000
                    ),
                ],
                "block": [_sealed_block("escrow-refund-v3lock", "lock", 6000, version=3)],
                "chain_parameter": [_param("escrow_settlement_authority", ADDR_AUTH)],
            },
            "block": _block(12000),
            "tx": _tx(
                "escrow-refund-v3lock", 0, "ESCROW_REFUND", sender=ADDR_AUTH, to=ADDR_A, value=1000, payload={"job_id": job_v3}
            ),
        },
        # ---- v11 fee sweep ---------------------------------------------------
        {
            "case_id": "escrow-fee-sweep-v11",
            "gate": "v11",
            "description": "Settlement authority sweeps custody residue to the "
            "governed fee recipient at 36000 — signed (v9-era height).",
            "prestate": {
                "account": [_acct(ADDR_AUTH, 10_000), _acct(_escrow_address(job_sweep), 500)],
                "chain_parameter": [
                    _param("escrow_settlement_authority", ADDR_AUTH),
                    _param("escrow_fee_recipient", ADDR_B),
                ],
            },
            "block": _block(36000),
            "tx": _sign(
                _tx(
                    "escrow-fee-sweep-v11",
                    0,
                    "ESCROW_FEE_SWEEP",
                    sender=ADDR_AUTH,
                    to=ADDR_B,
                    value=500,
                    payload={"job_id": job_sweep},
                ),
                KEY_AUTH,
            ),
        },
        {
            "case_id": "escrow-fee-sweep-wrong-recipient",
            "gate": "v11",
            "description": "Sweep paying anyone but escrow_fee_recipient is refused.",
            "prestate": {
                "account": [_acct(ADDR_AUTH, 10_000), _acct(_escrow_address(job_sweep), 500)],
                "chain_parameter": [
                    _param("escrow_settlement_authority", ADDR_AUTH),
                    _param("escrow_fee_recipient", ADDR_B),
                ],
            },
            "block": _block(36000),
            "tx": _sign(
                _tx(
                    "escrow-fee-sweep-wrong-recipient",
                    0,
                    "ESCROW_FEE_SWEEP",
                    sender=ADDR_AUTH,
                    to=ADDR_A,
                    value=500,
                    payload={"job_id": job_sweep},
                ),
                KEY_AUTH,
            ),
        },
        {
            "case_id": "escrow-fee-sweep-prev11",
            "gate": "v11 boundary",
            "description": "ESCROW_FEE_SWEEP below the v11 band — the v11 branch "
            "does not run; the tx falls to the generic path.",
            "prestate": {
                "account": [_acct(ADDR_AUTH, 10_000), _acct(_escrow_address(job_sweep), 500)],
                "chain_parameter": [
                    _param("escrow_settlement_authority", ADDR_AUTH),
                    _param("escrow_fee_recipient", ADDR_B),
                ],
            },
            "block": _block(32000),
            "tx": _sign(
                _tx(
                    "escrow-fee-sweep-prev11",
                    0,
                    "ESCROW_FEE_SWEEP",
                    sender=ADDR_AUTH,
                    to=ADDR_B,
                    value=500,
                    payload={"job_id": job_sweep},
                ),
                KEY_AUTH,
            ),
        },
    ]
    cases += _bridge_cases() + _v5_cases() + _v9_cases() + _v10_cases()
    cases += _governance_cases() + _v14_cases() + _stake_cases() + _boundary_cases() + _v16_cases()
    cases += _first_block_cases() + _gates1_signed_cases()
    return cases


def _gates1_signed_cases() -> list[dict[str, Any]]:
    """Signed twins of cases whose unsigned forms hit the v9 signature gate
    first under ``gates1``. Signing moves the rejection back onto the rule the
    case was written for, so the gates1 tree still records the actual v5
    fail-closed, wrong-authority, and v4 maturity verdicts — not just
    ``missing_signature``."""
    exec_no_param = _tx(
        "gov-execute-v5-failclosed-signed",
        0,
        "GOVERNANCE_EXECUTE",
        sender=ADDR_A,
        to=ADDR_A,
        value=0,
        payload={"proposal_id": "p1", "execution_payload": {}},
    )
    _sign(exec_no_param, KEY_A)

    rel_failclosed = _tx(
        "escrow-release-v5-failclosed-signed",
        0,
        "ESCROW_RELEASE",
        sender=ADDR_A,
        to=ADDR_B,
        value=1000,
        payload={"job_id": "job-v2-era"},
    )
    _sign(rel_failclosed, KEY_A)
    failclosed_lock = _escrow_lock_row(
        "escrow-release-v5-failclosed-signed", "lock", 2, job="job-v2-era", provider=ADDR_B, sender=ADDR_A, value=1000
    )

    rel_wrongauth = _tx(
        "escrow-release-wrong-authority-signed",
        0,
        "ESCROW_RELEASE",
        sender=ADDR_A,
        to=ADDR_B,
        value=1000,
        payload={"job_id": "job-wa"},
    )
    _sign(rel_wrongauth, KEY_A)
    wrongauth_lock = _escrow_lock_row(
        "escrow-release-wrong-authority-signed", "lock", 2, job="job-wa", provider=ADDR_B, sender=ADDR_A, value=1000
    )

    lock_matured = _sealed_tx(
        "stake-release-signed-matured", "lock", "STAKE_LOCK", height=2, sender=ADDR_B, recipient=ADDR_B, value=1000, payload={}
    )
    lock_immature = _sealed_tx(
        "stake-release-signed-immature",
        "lock",
        "STAKE_LOCK",
        height=2,
        sender=ADDR_B,
        recipient=ADDR_B,
        value=1000,
        payload={"lock_days": 30},
    )
    prior_release = _sealed_tx(
        "stake-release-signed-spent",
        "prior",
        "STAKE_RELEASE",
        height=3,
        sender=ADDR_B,
        recipient=ADDR_B,
        value=1000,
        payload={"lock_tx_hashes": [lock_matured["tx_hash"]]},
    )

    def rel(case_id: str, hashes: list[str] | None) -> dict[str, Any]:
        tx = _tx(case_id, 0, "STAKE_RELEASE", sender=ADDR_B, to=ADDR_B, value=1000, payload={})
        if hashes is not None:
            tx["payload"]["lock_tx_hashes"] = hashes
        _sign(tx, KEY_B)
        return tx

    head = [_sealed_block("stake-release-signed", "head", 4)]
    return [
        {
            "case_id": "gov-execute-v5-failclosed-signed",
            "gate": "v5 / gates1",
            "description": "Signed GOVERNANCE_EXECUTE with governance_executors "
            "unset — under gates1 the signature verifies and the v5 executors "
            "gate fails closed; under deployed (v5 height) the same gate refuses.",
            "prestate": {"account": [_acct(ADDR_A, 10_000)]},
            "block": _block(24500),
            "tx": exec_no_param,
        },
        {
            "case_id": "escrow-release-v5-failclosed-signed",
            "gate": "v5 / gates1",
            "description": "Signed release of a custody lock with escrow_settlement_authority unset — v5 fail-closed refusal.",
            "prestate": {
                "account": [_acct(ADDR_A, 10_000), _acct(_escrow_address("job-v2-era"), 1000)],
                "transaction": [failclosed_lock],
                "block": [_sealed_block("escrow-release-v5-failclosed-signed", "lock", 2)],
            },
            "block": _block(24500),
            "tx": rel_failclosed,
        },
        {
            "case_id": "escrow-release-wrong-authority-signed",
            "gate": "v5 / gates1",
            "description": "Signed release by a funded non-authority — signature "
            "verifies, the settlement-authority check refuses.",
            "prestate": {
                "account": [_acct(ADDR_A, 10_000), _acct(_escrow_address("job-wa"), 1000)],
                "transaction": [wrongauth_lock],
                "block": [_sealed_block("escrow-release-wrong-authority-signed", "lock", 2)],
                "chain_parameter": [_param("escrow_settlement_authority", ADDR_AUTH)],
            },
            "block": _block(24500),
            "tx": rel_wrongauth,
        },
        {
            "case_id": "stake-release-signed-no-locks",
            "gate": "v4 / gates1",
            "description": "Signed STAKE_RELEASE with no lock_tx_hashes — refused.",
            "prestate": {"account": [_acct(ADDR_B, 10_000)]},
            "block": _block(5),
            "tx": rel("stake-release-signed-no-locks", None),
        },
        {
            "case_id": "stake-release-signed-matured",
            "gate": "v4 / gates1",
            "description": "Signed release of a matured sealed STAKE_LOCK — accepted.",
            "prestate": {"account": [_acct(ADDR_B, 10_000)], "transaction": [lock_matured], "block": head},
            "block": _block(5),
            "tx": rel("stake-release-signed-matured", [lock_matured["tx_hash"]]),
        },
        {
            "case_id": "stake-release-signed-immature",
            "gate": "v4 / gates1",
            "description": "Signed release of a lock with lock_days=30 — still locked.",
            "prestate": {"account": [_acct(ADDR_B, 10_000)], "transaction": [lock_immature], "block": head},
            "block": _block(5),
            "tx": rel("stake-release-signed-immature", [lock_immature["tx_hash"]]),
        },
        {
            "case_id": "stake-release-signed-spent",
            "gate": "v4 / gates1",
            "description": "Signed release of a lock already spent by a sealed STAKE_RELEASE — refused.",
            "prestate": {
                "account": [_acct(ADDR_B, 10_000)],
                "transaction": [lock_matured, prior_release],
                "block": head,
            },
            "block": _block(5),
            "tx": rel("stake-release-signed-spent", [lock_matured["tx_hash"]]),
        },
    ]


def _first_block_cases() -> list[dict[str, Any]]:
    """bc-2 first-block probes (RESET-VECTORS-2 item 4): under ``gates1`` every
    block at height >= 1 resolves to v14 on both the replay and the producer
    path, so these cases record whether the newest rules really are live from
    the first produced block. Under ``deployed`` the same heights sit below
    every pin and replay as v1 — the flip is era-dependent by design."""
    auth_params = [
        _param("bridge_release_authority", ADDR_AUTH),
        _param("escrow_settlement_authority", ADDR_AUTH),
        _param("governance_executors", ADDR_EXEC),
    ]
    accts = [_acct(ADDR_A, 10_000), _acct(ADDR_EXEC, 10_000)]

    transfer_signed = _tx("firstblock-transfer-h1", 0, "TRANSFER", sender=ADDR_A, to=ADDR_B, value=100)
    _sign(transfer_signed, KEY_A)
    transfer_unsigned = _tx("firstblock-transfer-unsigned-h1", 0, "TRANSFER", sender=ADDR_A, to=ADDR_B, value=100)

    escrow_lock = _tx(
        "firstblock-escrow-lock-h2",
        0,
        "ESCROW_LOCK",
        sender=ADDR_A,
        to=ADDR_B,
        value=1000,
        payload={"job_id": "job-first", "provider": ADDR_B},
    )
    _sign(escrow_lock, KEY_A)

    bridge_lock = _tx(
        "firstblock-bridge-lock-h2",
        0,
        "BRIDGE_LOCK",
        sender=ADDR_A,
        to="bridge_lock",
        value=500,
        fee=0,
        payload={
            "transfer_id": _tx_hash("firstblock-bridge-lock-h2", "tid"),
            "amount": 500,
            "target_chain": "sep",
            "target_recipient": "0x" + "ab" * 20,
            "asset": "AIT",
        },
    )
    bridge_lock["bridge_signature"] = sign_bridge_lock(bridge_lock, bridge_lock["tx_hash"], KEY_AUTH)

    propose = _tx(
        "firstblock-gov-propose-h2",
        0,
        "GOVERNANCE_PROPOSE",
        sender=ADDR_EXEC,
        to=ADDR_EXEC,
        value=0,
        payload={
            "proposal_id": "prop-first",
            "title": "first",
            "execution_payload": {"action": "parameter_change", "parameter": "bond_slash_authority", "value": ADDR_AUTH},
        },
    )
    _sign(propose, KEY_EXEC)

    execute = _tx(
        "firstblock-gov-execute-h3",
        0,
        "GOVERNANCE_EXECUTE",
        sender=ADDR_EXEC,
        to=ADDR_EXEC,
        value=0,
        payload={
            "proposal_id": "prop-first",
            "execution_payload": {"action": "parameter_change", "parameter": "bond_slash_authority", "value": ADDR_AUTH},
        },
    )
    _sign(execute, KEY_EXEC)

    return [
        {
            "case_id": "firstblock-empty-h1",
            "gate": "gates1 boundary",
            "description": "Empty block at height 1 — records the version the "
            "unstamped replay path resolves (gates1: 14; deployed: 1) and the "
            "committed fingerprint on an empty apply.",
            "prestate": {},
            "block": _block(1),
            "txs": [],
        },
        {
            "case_id": "firstblock-transfer-h1",
            "gate": "gates1 boundary",
            "description": "Signed TRANSFER at height 1 — v9 signature rule must be live from the first block under gates1.",
            "prestate": {"account": accts},
            "block": _block(1),
            "tx": transfer_signed,
        },
        {
            "case_id": "firstblock-transfer-unsigned-h1",
            "gate": "gates1 boundary",
            "description": "Unsigned TRANSFER at height 1 — refused under gates1 (v9 live), accepted under deployed (v1 era).",
            "prestate": {"account": accts},
            "block": _block(1),
            "tx": transfer_unsigned,
        },
        {
            "case_id": "firstblock-escrow-lock-h2",
            "gate": "gates1 boundary",
            "description": "ESCROW_LOCK with job_id+provider at height 2 — v3 "
            "custody form live; value goes to the derived escrow address.",
            "prestate": {"account": accts, "chain_parameter": auth_params},
            "block": _block(2),
            "tx": escrow_lock,
        },
        {
            "case_id": "firstblock-bridge-lock-h2",
            "gate": "gates1 boundary",
            "description": "BRIDGE_LOCK carrying the authority bridge_signature "
            "at height 2 — v9 lock rule live; leaf-v2 binds the recipient "
            "(bridge_lock_leaf_v2_height=1).",
            "prestate": {"account": accts, "chain_parameter": auth_params},
            "block": _block(2),
            "tx": bridge_lock,
        },
        {
            "case_id": "firstblock-gov-propose-h2",
            "gate": "gates1 boundary",
            "description": "GOVERNANCE_PROPOSE carrying an explicit execution_payload at height 2 — v13 binding live.",
            "prestate": {"account": accts, "chain_parameter": auth_params},
            "block": _block(2),
            "tx": propose,
        },
        {
            "case_id": "firstblock-gov-execute-h3",
            "gate": "gates1 boundary",
            "description": "GOVERNANCE_EXECUTE at height 3 binding the h2 "
            "propose — executor-signed, execution_payload matches the sealed "
            "proposal; applies the parameter_change.",
            "prestate": {
                "account": accts,
                "chain_parameter": auth_params,
                "transaction": [
                    _propose_row(
                        "firstblock-gov-execute-h3",
                        "p",
                        2,
                        "prop-first",
                        {"action": "parameter_change", "parameter": "bond_slash_authority", "value": ADDR_AUTH},
                    )
                ],
                "block": [_sealed_block("firstblock-gov-execute-h3", "p", 2)],
            },
            "block": _block(3),
            "tx": execute,
        },
        {
            "case_id": "firstblock-stamp-v1-h1",
            "gate": "gates1 boundary",
            "description": "A block stamped state_transition_version=1 at "
            "height 1: under gates1 the v8 advisory mode is already active "
            "(1 >= v8_height), so the stamp is ignored and the block replays "
            "as v14 — stamps cannot downgrade a post-genesis block. Under "
            "deployed the stamp wins and the block replays as v1.",
            "prestate": {"account": accts},
            "block": _block(1, version=1),
            "tx": transfer_signed | {"tx_hash": _tx_hash("firstblock-stamp-v1-h1", 0)},
        },
    ]


def _bridge_cases() -> list[dict[str, Any]]:
    lock_v7 = _bridge_lock_row("bridge-refund-v6-with-hash", "lock", 24600, sender=ADDR_A, value=5000)
    lock_hash = lock_v7["tx_hash"]
    refund_ok = _tx(
        "bridge-refund-v6-with-hash",
        0,
        "BRIDGE_REFUND",
        sender="bridge_refund",
        to=ADDR_A,
        value=5000,
        fee=0,
        payload={
            "lock_tx_hash": lock_hash,
            "amount": 5000,
            "recipient": ADDR_A,
            "remote_chain": "sep",
            "remote_tx": "0xremote",
        },
    )
    refund_ok["bridge_signature"] = sign_bridge_credit(refund_ok, refund_ok["tx_hash"], KEY_AUTH)

    refund_nohash = _tx(
        "bridge-refund-v6-no-hash",
        0,
        "BRIDGE_REFUND",
        sender="bridge_refund",
        to=ADDR_A,
        value=5000,
        fee=0,
        payload={"amount": 5000, "recipient": ADDR_A, "remote_chain": "sep", "remote_tx": "0xremote"},
    )
    refund_nohash["bridge_signature"] = sign_bridge_credit(refund_nohash, refund_nohash["tx_hash"], KEY_AUTH)

    r1 = _tx(
        "bridge-refund-double",
        1,
        "BRIDGE_REFUND",
        sender="bridge_refund",
        to=ADDR_A,
        value=5000,
        fee=0,
        payload={"lock_tx_hash": lock_hash, "amount": 5000, "recipient": ADDR_A},
    )
    r1["bridge_signature"] = sign_bridge_credit(r1, r1["tx_hash"], KEY_AUTH)
    r2 = _tx(
        "bridge-refund-double",
        2,
        "BRIDGE_REFUND",
        sender="bridge_refund",
        to=ADDR_A,
        value=5000,
        fee=0,
        payload={"lock_tx_hash": lock_hash, "amount": 5000, "recipient": ADDR_A},
    )
    r2["bridge_signature"] = sign_bridge_credit(r2, r2["tx_hash"], KEY_AUTH)

    lock_v9 = _tx(
        "bridge-lock-v9-signed",
        0,
        "BRIDGE_LOCK",
        sender=ADDR_A,
        to="bridge_lock",
        value=5000,
        fee=0,
        nonce=0,
        payload={
            "transfer_id": _tx_hash("bridge-lock-v9-signed", "tid"),
            "amount": 5000,
            "target_chain": "sep",
            "target_recipient": "0x" + "ab" * 20,
            "asset": "AIT",
        },
    )
    lock_v9["bridge_signature"] = sign_bridge_lock(lock_v9, lock_v9["tx_hash"], KEY_AUTH)

    lock_unsigned = _tx(
        "bridge-lock-v9-unsigned",
        0,
        "BRIDGE_LOCK",
        sender=ADDR_A,
        to="bridge_lock",
        value=5000,
        fee=0,
        nonce=0,
        payload={
            "transfer_id": _tx_hash("bridge-lock-v9-unsigned", "tid"),
            "amount": 5000,
            "target_chain": "sep",
            "target_recipient": "0x" + "ab" * 20,
            "asset": "AIT",
        },
    )

    lock_v14 = _tx(
        "bridge-lock-v14-leaf",
        0,
        "BRIDGE_LOCK",
        sender=ADDR_A,
        to="bridge_lock",
        value=5000,
        fee=0,
        nonce=0,
        payload={
            "transfer_id": _tx_hash("bridge-lock-v14-leaf", "tid"),
            "amount": 5000,
            "target_chain": "sep",
            "target_recipient": "0x" + "ab" * 20,
            "asset": "AIT",
        },
    )
    lock_v14["bridge_signature"] = sign_bridge_lock(lock_v14, lock_v14["tx_hash"], KEY_AUTH)

    lock_v14_bare = _tx(
        "bridge-lock-v14-unreadable", 0, "BRIDGE_LOCK", sender=ADDR_A, to="bridge_lock", value=5000, fee=0, nonce=0, payload={}
    )
    lock_v14_bare["bridge_signature"] = sign_bridge_lock(lock_v14_bare, lock_v14_bare["tx_hash"], KEY_AUTH)

    lock_v51 = _tx(
        "bridge-lock-leafv2",
        0,
        "BRIDGE_LOCK",
        sender=ADDR_A,
        to="bridge_lock",
        value=5000,
        fee=0,
        nonce=0,
        payload={
            "transfer_id": _tx_hash("bridge-lock-leafv2", "tid"),
            "amount": 5000,
            "target_chain": "sep",
            "target_recipient": "0x" + "ab" * 20,
            "asset": "AIT",
        },
    )
    lock_v51["bridge_signature"] = sign_bridge_lock(lock_v51, lock_v51["tx_hash"], KEY_AUTH)

    auth_params = [_param("bridge_release_authority", ADDR_AUTH)]
    return [
        {
            "case_id": "bridge-refund-v6-with-hash",
            "gate": "v6",
            "description": "BRIDGE_REFUND carrying payload.lock_tx_hash at 25000 — "
            "v6 binding resolves the sealed lock: exists, unrefunded, recipient=="
            "lock sender, amount==lock value.",
            "prestate": {
                "account": [_acct(ADDR_A, 0)],
                "transaction": [lock_v7],
                "block": [_sealed_block("bridge-refund-v6-with-hash", "lock", 24600, version=6)],
                "chain_parameter": auth_params,
            },
            "block": _block(25000),
            "tx": refund_ok,
        },
        {
            "case_id": "bridge-refund-v6-no-hash",
            "gate": "v6",
            "description": "Post-v7 BRIDGE_REFUND without lock_tx_hash — refused even with a valid authority signature.",
            "prestate": {"chain_parameter": auth_params},
            "block": _block(25000),
            "tx": refund_nohash,
        },
        {
            "case_id": "bridge-refund-double",
            "gate": "v6 double-refund",
            "description": "Two BRIDGE_REFUNDs naming one lock in the same block: "
            "the first seals, the second sees refunded=True and is refused.",
            "prestate": {
                "account": [_acct(ADDR_A, 0)],
                "transaction": [lock_v7],
                "block": [_sealed_block("bridge-refund-double", "lock", 24600, version=6)],
                "chain_parameter": auth_params,
            },
            "block": _block(25000),
            "txs": [r1, r2],
        },
        {
            "case_id": "bridge-lock-v9-signed",
            "gate": "v9",
            "description": "BRIDGE_LOCK carrying the authority bridge_signature at 31000 — accepted.",
            "prestate": {"account": [_acct(ADDR_A, 10_000)], "chain_parameter": auth_params},
            "block": _block(31000),
            "tx": lock_v9,
        },
        {
            "case_id": "bridge-lock-v9-unsigned",
            "gate": "v9",
            "description": "BRIDGE_LOCK with no bridge_signature at 31000 — refused "
            "(below v9 the same unsigned lock is only shadow-counted).",
            "prestate": {"account": [_acct(ADDR_A, 10_000)], "chain_parameter": auth_params},
            "block": _block(31000),
            "tx": lock_unsigned,
        },
        {
            "case_id": "bridge-lock-v8-unsigned",
            "gate": "v9 boundary",
            "description": "Unsigned BRIDGE_LOCK at 25000 — pre-v9, shadow only, applies.",
            "prestate": {"account": [_acct(ADDR_A, 10_000)], "chain_parameter": auth_params},
            "block": _block(25000),
            "tx": lock_unsigned | {"tx_hash": _tx_hash("bridge-lock-v8-unsigned", 0)},
        },
        {
            "case_id": "bridge-lock-v14-leaf",
            "gate": "v14",
            "description": "v14 BRIDGE_LOCK with derivable leaf data in payload — "
            "accepted; derived root recorded (leaf-v1 below 51000).",
            "prestate": {"account": [_acct(ADDR_A, 10_000)], "chain_parameter": auth_params},
            "block": _block(50000),
            "tx": lock_v14,
        },
        {
            "case_id": "bridge-lock-v14-unreadable",
            "gate": "v14",
            "description": "v14 BRIDGE_LOCK with no leaf fields in payload or envelope — refused.",
            "prestate": {"account": [_acct(ADDR_A, 10_000)], "chain_parameter": auth_params},
            "block": _block(50000),
            "tx": lock_v14_bare,
        },
        {
            "case_id": "bridge-lock-leafv2",
            "gate": "BRIDGE_LOCK_LEAF_V2",
            "description": "Lock at 51001: leaf derivation binds the recipient "
            "(leaf-v2). gates0 records the same v2 leaf — pin 0 means on from "
            "genesis for this gate.",
            "prestate": {"account": [_acct(ADDR_A, 10_000)], "chain_parameter": auth_params},
            "block": _block(51001),
            "tx": lock_v51,
        },
    ]


def _v5_cases() -> list[dict[str, Any]]:
    return [
        {
            "case_id": "gov-execute-v5-no-executors",
            "gate": "v5",
            "description": "GOVERNANCE_EXECUTE at 24500 with governance_executors unset — fail-closed refusal.",
            "prestate": {"account": [_acct(ADDR_A, 10_000)]},
            "block": _block(24500),
            "tx": _tx(
                "gov-execute-v5-no-executors",
                0,
                "GOVERNANCE_EXECUTE",
                sender=ADDR_A,
                value=0,
                payload={"proposal_id": "p1", "execution_payload": {}},
            ),
        },
        {
            "case_id": "bridge-release-v5-no-authority",
            "gate": "v5",
            "description": "BRIDGE_RELEASE at 24500 with bridge_release_authority unset — fail-closed refusal.",
            "prestate": {},
            "block": _block(24500),
            "tx": _tx(
                "bridge-release-v5-no-authority",
                0,
                "BRIDGE_RELEASE",
                sender="bridge_release",
                to=ADDR_B,
                value=500,
                fee=0,
                payload={"remote_chain": "sep", "remote_tx": "0xr"},
            ),
        },
    ]


def _v9_cases() -> list[dict[str, Any]]:
    unsigned = _tx("transfer-v9-unsigned", 0, "TRANSFER", sender=ADDR_A, to=ADDR_B, value=100)
    signed = _tx("transfer-v9-signed", 0, "TRANSFER", sender=ADDR_A, to=ADDR_B, value=100)
    _sign(signed, KEY_A)
    badsig = _tx("transfer-v9-badsig", 0, "TRANSFER", sender=ADDR_A, to=ADDR_B, value=100)
    _sign(badsig, KEY_B)  # signed by the wrong key — recovers to ADDR_B
    pre_v9 = _tx("transfer-v8-unsigned", 0, "TRANSFER", sender=ADDR_A, to=ADDR_B, value=100)
    return [
        {
            "case_id": "transfer-v9-unsigned",
            "gate": "v9",
            "description": "Unsigned TRANSFER at 31000 — v9 refuses.",
            "prestate": {"account": [_acct(ADDR_A, 10_000)]},
            "block": _block(31000),
            "tx": unsigned,
        },
        {
            "case_id": "transfer-v9-signed",
            "gate": "v9",
            "description": "Signed TRANSFER at 31000 — v9 accepts; the signature covers the sealed nonce (v7+ authoritative).",
            "prestate": {"account": [_acct(ADDR_A, 10_000)]},
            "block": _block(31000),
            "tx": signed,
        },
        {
            "case_id": "transfer-v9-badsig",
            "gate": "v9",
            "description": "TRANSFER signed by a different key — signature verification refuses before the v9 verdict.",
            "prestate": {"account": [_acct(ADDR_A, 10_000)]},
            "block": _block(31000),
            "tx": badsig,
        },
        {
            "case_id": "transfer-v8-unsigned",
            "gate": "v9 boundary",
            "description": "Unsigned TRANSFER at 25000 — v8, signature rule is shadow-only; applies.",
            "prestate": {"account": [_acct(ADDR_A, 10_000)]},
            "block": _block(25000),
            "tx": pre_v9,
        },
    ]


def _v10_cases() -> list[dict[str, Any]]:
    reg = {
        "chain_id": CHAIN,
        "gpu_id": "gpu-1",
        "miner_id": "miner-1",
        "model": "test-gpu",
        "memory_gb": 24,
        "cuda_version": "12.4",
        "region": "test",
        "capabilities": [],
        "registered_by": ADDR_A,
        "status": "active",
        "price_per_hour": "1.0",
    }
    reg_off = dict(reg, status="deactivated")
    dereg_ok = _tx("gpu-deregister-v10", 0, "GPU_DEREGISTER", sender=ADDR_A, to=ADDR_A, value=0, payload={"gpu_id": "gpu-1"})
    dereg_wrong = _tx(
        "gpu-deregister-v10-wrong-sender", 0, "GPU_DEREGISTER", sender=ADDR_B, to=ADDR_B, value=0, payload={"gpu_id": "gpu-1"}
    )
    dereg_value = _tx(
        "gpu-deregister-v10-nonzero-value",
        0,
        "GPU_DEREGISTER",
        sender=ADDR_A,
        to=ADDR_A,
        value=100,
        payload={"gpu_id": "gpu-1"},
    )
    alloc_off = _tx(
        "gpu-allocate-v10-deactivated",
        0,
        "GPU_ALLOCATE",
        sender=ADDR_B,
        to=ADDR_B,
        value=0,
        payload={"gpu_id": "gpu-1", "client_id": "c1", "duration_hours": 1, "total_cost": 10},
    )
    reg_foreign = _tx(
        "gpu-register-v7-foreign",
        0,
        "GPU_REGISTER",
        sender=ADDR_B,
        to=ADDR_B,
        value=0,
        payload={"gpu_id": "gpu-1", "price_per_hour": "2.0"},
    )
    for tx in (dereg_ok, dereg_wrong, dereg_value, alloc_off, reg_foreign):
        _sign(tx, KEY_A if tx["from"] == ADDR_A else KEY_B)
    return [
        {
            "case_id": "gpu-deregister-v10",
            "gate": "v10",
            "description": "Registrant deregisters its active GPU at 33000 — accepted.",
            "prestate": {"account": [_acct(ADDR_A, 10_000)], "gpu_registration": [reg]},
            "block": _block(33000),
            "tx": dereg_ok,
        },
        {
            "case_id": "gpu-deregister-v10-wrong-sender",
            "gate": "v10",
            "description": "Non-registrant deregister — refused.",
            "prestate": {"account": [_acct(ADDR_B, 10_000)], "gpu_registration": [reg]},
            "block": _block(33000),
            "tx": dereg_wrong,
        },
        {
            "case_id": "gpu-deregister-v10-nonzero-value",
            "gate": "v10",
            "description": "GPU_DEREGISTER joins the zero-value set at v10 — value!=0 refused even from the registrant.",
            "prestate": {"account": [_acct(ADDR_A, 10_000)], "gpu_registration": [reg]},
            "block": _block(33000),
            "tx": dereg_value,
        },
        {
            "case_id": "gpu-allocate-v10-deactivated",
            "gate": "v10",
            "description": "GPU_ALLOCATE naming a deactivated gpu — refused.",
            "prestate": {"account": [_acct(ADDR_B, 10_000)], "gpu_registration": [reg_off]},
            "block": _block(33000),
            "tx": alloc_off,
        },
        {
            "case_id": "gpu-register-v7-foreign",
            "gate": "v7",
            "description": "v7 registrant-only: re-register of ADDR_A's gpu_id by ADDR_B — refused.",
            "prestate": {"account": [_acct(ADDR_B, 10_000)], "gpu_registration": [reg]},
            "block": _block(25000),
            "tx": reg_foreign,
        },
    ]


def _v16_cases() -> list[dict[str, Any]]:
    """GPU-ADMISSION-1 (#384): v16 requires allocation_id + existing gpu_id."""
    reg = {
        "chain_id": CHAIN,
        "gpu_id": "gpu-1",
        "miner_id": "miner-1",
        "model": "test-gpu",
        "memory_gb": 24,
        "cuda_version": "12.4",
        "region": "test",
        "capabilities": [],
        "registered_by": ADDR_A,
        "status": "active",
        "price_per_hour": "1.0",
    }
    alloc_noid = _tx(
        "gpu-allocate-v16-missing-allocation-id",
        0,
        "GPU_ALLOCATE",
        sender=ADDR_B,
        to=ADDR_B,
        value=0,
        payload={"gpu_id": "gpu-1", "client_id": "c1", "duration_hours": 1, "total_cost": 10},
    )
    alloc_bogus = _tx(
        "gpu-allocate-v16-unknown-gpu",
        0,
        "GPU_ALLOCATE",
        sender=ADDR_B,
        to=ADDR_B,
        value=0,
        payload={
            "gpu_id": "gpu-nope",
            "client_id": "c1",
            "duration_hours": 1,
            "total_cost": 10,
            "allocation_id": "alloc-fixed-1",
        },
    )
    _sign(alloc_noid, KEY_B)
    _sign(alloc_bogus, KEY_B)
    return [
        {
            "case_id": "gpu-allocate-v16-missing-allocation-id",
            "gate": "v16",
            "description": "GPU_ALLOCATE without allocation_id — refused at/after v16, minted below.",
            "prestate": {"account": [_acct(ADDR_B, 10_000)], "gpu_registration": [reg]},
            "block": _block(100),
            "tx": alloc_noid,
        },
        {
            "case_id": "gpu-allocate-v16-unknown-gpu",
            "gate": "v16",
            "description": "GPU_ALLOCATE naming an unregistered gpu — refused at/after v16, dies at apply below.",
            "prestate": {"account": [_acct(ADDR_B, 10_000)]},
            "block": _block(100),
            "tx": alloc_bogus,
        },
    ]


def _governance_cases() -> list[dict[str, Any]]:
    executors_param = _param("governance_executors", ADDR_EXEC)
    exec_acct = _acct(ADDR_EXEC, 10_000)

    propose_ok = _tx(
        "gov-propose-v13-with-payload",
        0,
        "GOVERNANCE_PROPOSE",
        sender=ADDR_EXEC,
        to=ADDR_EXEC,
        value=0,
        payload={
            "proposal_id": "prop-ok",
            "title": "t",
            "execution_payload": {"action": "parameter_change", "parameter": "bond_slash_authority", "value": ADDR_AUTH},
        },
    )
    _sign(propose_ok, KEY_EXEC)
    propose_bare = _tx(
        "gov-propose-v13-no-payload",
        0,
        "GOVERNANCE_PROPOSE",
        sender=ADDR_EXEC,
        to=ADDR_EXEC,
        value=0,
        payload={"proposal_id": "prop-bare", "title": "t"},
    )
    _sign(propose_bare, KEY_EXEC)

    def exec_tx(case_id: str, n: int, sender: str, payload: dict) -> dict[str, Any]:
        tx = _tx(case_id, n, "GOVERNANCE_EXECUTE", sender=sender, to=sender, value=0, payload=payload)
        _sign(tx, KEY_EXEC if sender == ADDR_EXEC else KEY_OTHER)
        return tx

    v12_bad = exec_tx(
        "gov-execute-v12-bad-value",
        0,
        ADDR_EXEC,
        {
            "proposal_id": "p12bad",
            "execution_payload": {
                "action": "parameter_change",
                "parameter": "escrow_settlement_authority",
                "value": "not-an-address",
            },
        },
    )
    v12_good = exec_tx(
        "gov-execute-v12-good",
        0,
        ADDR_EXEC,
        {
            "proposal_id": "p12good",
            "execution_payload": {
                "action": "parameter_change",
                "parameter": "escrow_settlement_authority",
                "value": ADDR_AUTH,
            },
        },
    )
    setgov = exec_tx(
        "gov-execute-setgovaddr",
        0,
        ADDR_EXEC,
        {"proposal_id": "psetgov", "execution_payload": {"action": "set_governance_address", "address": ADDR_B}},
    )

    v13_exec_ok = exec_tx(
        "gov-execute-v13-empty-executor", 0, ADDR_EXEC, {"proposal_id": "prop-empty", "execution_payload": {}}
    )
    v13_exec_nonexec = exec_tx(
        "gov-execute-v13-empty-nonexecutor", 0, ADDR_OTHER, {"proposal_id": "prop-empty", "execution_payload": {}}
    )
    v13_exec_nokey = exec_tx("gov-execute-v13-missing-key", 0, ADDR_EXEC, {"proposal_id": "prop-empty"})
    v13_exec_unknown = exec_tx("gov-execute-v13-unknown", 0, ADDR_EXEC, {"proposal_id": "prop-nope", "execution_payload": {}})
    v13_exec_twice = exec_tx(
        "gov-execute-v13-already-executed", 0, ADDR_EXEC, {"proposal_id": "prop-done", "execution_payload": {}}
    )

    return [
        {
            "case_id": "gov-propose-v13-with-payload",
            "gate": "v13",
            "description": "GOVERNANCE_PROPOSE with a dict execution_payload at "
            "47000 — accepted and bound for a later execute.",
            "prestate": {"account": [exec_acct]},
            "block": _block(47000),
            "tx": propose_ok,
        },
        {
            "case_id": "gov-propose-v13-no-payload",
            "gate": "v13",
            "description": "GOVERNANCE_PROPOSE without execution_payload at v13 — refused.",
            "prestate": {"account": [exec_acct]},
            "block": _block(47000),
            "tx": propose_bare,
        },
        {
            "case_id": "gov-execute-v12-bad-value",
            "gate": "v12",
            "description": "v12 authority-parameter check: a parameter_change to "
            "escrow_settlement_authority with a non-address value is refused. "
            "v13 binding is shadow-only at this height so no sealed propose is "
            "needed.",
            "prestate": {"account": [exec_acct], "chain_parameter": [executors_param]},
            "block": _block(38000),
            "tx": v12_bad,
        },
        {
            "case_id": "gov-execute-v12-good",
            "gate": "v12",
            "description": "Well-formed authority parameter_change at 38000 — accepted; the parameter row lands.",
            "prestate": {"account": [exec_acct], "chain_parameter": [executors_param]},
            "block": _block(38000),
            "tx": v12_good,
        },
        {
            "case_id": "gov-execute-setgovaddr",
            "gate": "v5+",
            "description": "set_governance_address is named-but-unimplemented — refused explicitly.",
            "prestate": {"account": [exec_acct], "chain_parameter": [executors_param]},
            "block": _block(38000),
            "tx": setgov,
        },
        {
            "case_id": "gov-execute-v13-empty-executor",
            "gate": "v13",
            "description": "The gap57 shape: an executor executes a proposal whose "
            "sealed execution_payload is {} — the execute carries "
            "execution_payload:{} explicitly and binds; applies as a marker "
            "no-op.",
            "prestate": {
                "account": [exec_acct],
                "chain_parameter": [executors_param],
                "transaction": [_propose_row("gov-execute-v13-empty-executor", "p", 46500, "prop-empty", {})],
                "block": [_sealed_block("gov-execute-v13-empty-executor", "p", 46500, version=14)],
            },
            "block": _block(47000),
            "tx": v13_exec_ok,
        },
        {
            "case_id": "gov-execute-v13-empty-nonexecutor",
            "gate": "v13",
            "description": "The same empty-payload execute from a funded non-executor — refused at the executors gate.",
            "prestate": {
                "account": [_acct(ADDR_OTHER, 10_000)],
                "chain_parameter": [executors_param],
                "transaction": [_propose_row("gov-execute-v13-empty-nonexecutor", "p", 46500, "prop-empty", {})],
            },
            "block": _block(47000),
            "tx": v13_exec_nonexec,
        },
        {
            "case_id": "gov-execute-v13-missing-key",
            "gate": "v13",
            "description": "Execute with NO execution_payload key — reads as None != {} and is refused.",
            "prestate": {
                "account": [exec_acct],
                "chain_parameter": [executors_param],
                "transaction": [_propose_row("gov-execute-v13-missing-key", "p", 46500, "prop-empty", {})],
            },
            "block": _block(47000),
            "tx": v13_exec_nokey,
        },
        {
            "case_id": "gov-execute-v13-unknown",
            "gate": "v13",
            "description": "Execute naming a proposal never sealed — refused.",
            "prestate": {"account": [exec_acct], "chain_parameter": [executors_param]},
            "block": _block(47000),
            "tx": v13_exec_unknown,
        },
        {
            "case_id": "gov-execute-v13-already-executed",
            "gate": "v13",
            "description": "A second execute for an already-executed proposal — refused.",
            "prestate": {
                "account": [exec_acct],
                "chain_parameter": [executors_param],
                "transaction": [
                    _propose_row("gov-execute-v13-already-executed", "p", 46500, "prop-done", {}),
                    _execute_row("gov-execute-v13-already-executed", "e", 46600, "prop-done", {}),
                ],
            },
            "block": _block(47000),
            "tx": v13_exec_twice,
        },
    ]


def _v14_cases() -> list[dict[str, Any]]:
    # The aux-root gate is a block-level check: the stream covers it for real
    # blocks; this case exercises an unstamped block under both profiles and a
    # stamped v14 block.
    tx = _tx("aux-root-v14-block", 0, "TRANSFER", sender=ADDR_A, to=ADDR_B, value=100)
    _sign(tx, KEY_A)
    return [
        {
            "case_id": "aux-root-v14-block",
            "gate": "v14",
            "description": "Signed transfer at 47000 — the recorded output carries "
            "the post-block committed fingerprint (the aux_state_root basis). "
            "gates0 (stamp absent) replays this at v2 instead.",
            "prestate": {"account": [_acct(ADDR_A, 10_000)]},
            "block": _block(47000),
            "tx": tx,
        },
        {
            "case_id": "aux-root-v14-stamped-low",
            "gate": "v14 / stamp",
            "description": "Stamped v14 at height 100 — recorded metadata wins "
            "below the v8 pin under deployed and everywhere under gates0.",
            "prestate": {"account": [_acct(ADDR_A, 10_000)]},
            "block": _block(100, version=14),
            "tx": _tx("aux-root-v14-stamped-low", 0, "TRANSFER", sender=ADDR_A, to=ADDR_B, value=100),
        },
    ]


def _stake_cases() -> list[dict[str, Any]]:
    lock_matured = _sealed_tx(
        "stake-release-v4-matured", "lock", "STAKE_LOCK", height=12000, sender=ADDR_B, recipient=ADDR_B, value=1000, payload={}
    )
    lock_immature = _sealed_tx(
        "stake-release-v4-immature",
        "lock",
        "STAKE_LOCK",
        height=12000,
        sender=ADDR_B,
        recipient=ADDR_B,
        value=1000,
        payload={"lock_days": 30},
    )
    rel_no_locks = _tx("stake-release-v4-no-locks", 0, "STAKE_RELEASE", sender=ADDR_B, to=ADDR_B, value=1000, payload={})
    rel_ok = _tx(
        "stake-release-v4-matured",
        0,
        "STAKE_RELEASE",
        sender=ADDR_B,
        to=ADDR_B,
        value=1000,
        payload={"lock_tx_hashes": [lock_matured["tx_hash"]]},
    )
    rel_immature = _tx(
        "stake-release-v4-immature",
        0,
        "STAKE_RELEASE",
        sender=ADDR_B,
        to=ADDR_B,
        value=1000,
        payload={"lock_tx_hashes": [lock_immature["tx_hash"]]},
    )
    rel_spent = _tx(
        "stake-release-v4-already-released",
        0,
        "STAKE_RELEASE",
        sender=ADDR_B,
        to=ADDR_B,
        value=1000,
        payload={"lock_tx_hashes": [lock_matured["tx_hash"]]},
    )
    prior_release = _sealed_tx(
        "stake-release-v4-already-released",
        "prior",
        "STAKE_RELEASE",
        height=12500,
        sender=ADDR_B,
        recipient=ADDR_B,
        value=1000,
        payload={"lock_tx_hashes": [lock_matured["tx_hash"]]},
    )
    return [
        {
            "case_id": "stake-release-v4-no-locks",
            "gate": "v4",
            "description": "STAKE_RELEASE with no lock_tx_hashes — refused.",
            "prestate": {"account": [_acct(ADDR_B, 10_000)]},
            "block": _block(13000),
            "tx": rel_no_locks,
        },
        {
            "case_id": "stake-release-v4-matured",
            "gate": "v4",
            "description": "Release naming a matured (no lock_days) sealed STAKE_LOCK owned by the payee — accepted.",
            "prestate": {
                "account": [_acct(ADDR_B, 10_000)],
                "transaction": [lock_matured],
                "block": [_sealed_block("stake-release-v4-matured", "head", 12999)],
            },
            "block": _block(13000),
            "tx": rel_ok,
        },
        {
            "case_id": "stake-release-v4-immature",
            "gate": "v4",
            "description": "Release naming a lock with lock_days=30 — maturity 1440 blocks/day, still locked at next_height.",
            "prestate": {
                "account": [_acct(ADDR_B, 10_000)],
                "transaction": [lock_immature],
                "block": [_sealed_block("stake-release-v4-immature", "head", 12999)],
            },
            "block": _block(13000),
            "tx": rel_immature,
        },
        {
            "case_id": "stake-release-v4-already-released",
            "gate": "v4",
            "description": "Lock already spent by a sealed STAKE_RELEASE — refused.",
            "prestate": {
                "account": [_acct(ADDR_B, 10_000)],
                "transaction": [lock_matured, prior_release],
                "block": [_sealed_block("stake-release-v4-already-released", "head", 12999)],
            },
            "block": _block(13000),
            "tx": rel_spent,
        },
    ]


def _boundary_cases() -> list[dict[str, Any]]:
    stamped_v9_low = _tx("stamp-v9-below-v8pin", 0, "TRANSFER", sender=ADDR_A, to=ADDR_B, value=100)
    _sign(stamped_v9_low, KEY_A)
    v8_lie = _tx("stamp-below-height-v8", 0, "TRANSFER", sender=ADDR_A, to=ADDR_B, value=100)
    legacy = _tx(
        "gpu-marketplace-legacy",
        0,
        "GPU_MARKETPLACE",
        sender=ADDR_A,
        to=ADDR_B,
        value=0,
        payload={"job_id": "legacy-job", "gpu_id": "gpu-9"},
    )
    _sign(legacy, KEY_A)
    return [
        {
            "case_id": "stamp-v9-below-v8pin",
            "gate": "v8 stamp precedence",
            "description": "Block stamped v9 at height 100 — below the v8 pin the "
            "recorded stamp wins, so the v9 signature gate applies at a height "
            "the thresholds would call v2.",
            "prestate": {"account": [_acct(ADDR_A, 10_000)]},
            "block": _block(100, version=9),
            "tx": stamped_v9_low,
        },
        {
            "case_id": "stamp-below-height-v8",
            "gate": "v8",
            "description": "Block stamped v3 at height 25000 — at/above the v8 "
            "pin the height-derived version (v8) wins; the stamp is advisory.",
            "prestate": {"account": [_acct(ADDR_A, 10_000)]},
            "block": _block(25000, version=3),
            "tx": v8_lie,
        },
        {
            "case_id": "gpu-marketplace-legacy",
            "gate": "type coverage",
            "description": "GPU_MARKETPLACE — the legacy spelling 38 sealed rows "
            "carry; recorded so the collapsed ruleset keeps whatever it does "
            "today.",
            "prestate": {"account": [_acct(ADDR_A, 10_000)]},
            "block": _block(33000),
            "tx": legacy,
        },
        {
            "case_id": "empty-block",
            "gate": "block mechanics",
            "description": "A block with no transactions — roots must be the pre-state roots unchanged.",
            "prestate": {"account": [_acct(ADDR_A, 10_000)]},
            "block": _block(13000),
            "txs": [],
        },
    ]


def emit(cases_dir) -> list[str]:
    """Write every case to ``cases/synthetic/<case_id>.json``; returns names."""
    import pathlib

    out = pathlib.Path(cases_dir) / "synthetic"
    out.mkdir(parents=True, exist_ok=True)
    names = []
    for case in cases():
        (out / f"{case['case_id']}.json").write_text(json.dumps(case, sort_keys=True, indent=1) + "\n")
        names.append(case["case_id"])
    return names


if __name__ == "__main__":
    import sys

    for name in emit(sys.argv[1] if len(sys.argv) > 1 else "cases"):
        print(name)
