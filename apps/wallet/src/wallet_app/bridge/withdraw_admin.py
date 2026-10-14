#!/usr/bin/env python3
"""Operator commands for AIT->ETH withdrawal rows (ETH-14).

Run on hub inside the wallet environment — the same env files the
aitbc-wallet unit loads::

    cd /opt/aitbc
    PYTHONPATH=/opt/aitbc/apps/wallet/src:/opt/aitbc/packages/py/aitbc-sdk/src:/opt/aitbc/packages/py/aitbc-crypto/src \
        venv/bin/python -m wallet_app.bridge.withdraw_admin <command> [args]

Commands:
    status <ait_tx_hash>                show the ledger row, recorded release
                                        attempts and the live on-chain outcome
    release-retry <ait_tx_hash>         re-release the recorded ETH amount to the
                                        recorded address. DRY-RUN by default —
                                        prints the full proof bundle and the
                                        exact planned send; --confirm actually
                                        signs and broadcasts.
    mark-review <ait_tx_hash> --note …  move a falsely-'completed' or parked row
                                        to 'needs_review' — the monitor's resume
                                        pass then proves not_sent and refunds
                                        the AIT automatically (fallback for a
                                        retry that cannot land).

Safety rules (ETH-14):
- release-retry refuses unless the recorded release is proven failed on TWO
  independent Ethereum RPC endpoints in the same run (ETH_RPC_URL plus
  --verify-rpc / ETH_VERIFY_RPC_URL): receipt status 0 at the release
  confirmation depth, the recorded nonce consumed, and no balance gain for
  the receiver inside the failed tx's block — or, for a later retry whose
  broadcast never sealed, the recorded hash absent AND its nonce still free.
- The AIT leg must read 'confirmed' on the hub chain RPC before any send.
- The retry resends exactly the recorded amount_eth to the recorded
  eth_address at the CURRENT account nonce (a provably free nonce is
  reused, so a still-floating earlier blob can never double-pay: two
  transactions at one nonce are mutually exclusive).
- Eligible rows: 'completed' with a failed recorded release, or
  'needs_review_release' (a parked earlier retry). Rows owned by the
  monitor ('releasing'/'needs_review') and rows with a recorded refund are
  refused — never race the machine, never double-compensate.
- The signing step (--confirm) additionally refuses unless the bridge
  release environment is loaded — BRIDGE_ENABLED, withdraws enabled, and a
  release key that derives to ETH_WALLET_ADDRESS. In practice that is only
  hub's aitbc-wallet env; everywhere else only the dry-run works.
- Every attempt is recorded (resolved_by / resolved_at / operator_note) and
  the row's retry_count is bumped BEFORE broadcast; intent ('releasing_retry'
  + new nonce + deterministic hash) persists before the send, as ETH-9 does.
- A retry row ends 'completed' only on a status-1 receipt at depth; a proven
  failure parks at 'needs_review_release' for the operator — auto-refund is
  never triggered by a retried release.
- ETH-15: an endpoint is never printed or stored with its path/query —
  keyed RPC URLs appear as scheme://host only, including inside error text.
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import os
import sys
from decimal import Decimal
from typing import Any

import httpx

from .url_redact import redact_text, redact_url

# The aitbc-wallet unit's EnvironmentFile set, in unit order.
_DEFAULT_ENV_FILES = [
    "/etc/aitbc/blockchain.env",
    "/etc/aitbc/blockchain-secrets.env",
    "/etc/aitbc/node.env",
    "/etc/aitbc/exchange.env",
    "/etc/aitbc/aitbc-wallet.env",
]

# Statuses an operator may drive a release-retry for. 'releasing' /
# 'needs_review' rows are machine-owned (the monitor's resume pass processes
# them — retrying would race the auto-refund); 'releasing_retry' means a
# retry is in flight; 'failed'/'refunded' rows may already have unrecorded
# refund traffic — all refused.
_RETRY_ELIGIBLE = {"completed", "needs_review_release"}
_MARK_REVIEW_ELIGIBLE = {"completed", "needs_review_release"}

_RETRY_OUTCOME_WAIT_SECONDS = 120
_RETRY_OUTCOME_POLL_SECONDS = 10


def _load_env_files(paths: list[str]) -> None:
    """Populate os.environ from EnvironmentFile-style files (last file wins).

    Missing files are skipped with a warning, like systemd's optional '-'
    prefix. Among the files themselves this matches systemd EnvironmentFile
    semantics — a variable set by a later file overrides an earlier file.
    An already-exported shell variable still wins over every file, so the
    operator can always override any single value (e.g. ETH_RPC_URL).
    """
    values: dict[str, str] = {}
    for path in paths:
        try:
            with open(path) as fh:
                for line in fh:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, _, val = line.partition("=")
                    values[key.strip()] = val.strip().strip('"').strip("'")
        except OSError as e:
            print(f"warning: cannot read env file {path}: {e}", file=sys.stderr)
    for key, val in values.items():
        os.environ.setdefault(key, val)


def _sync_wdm_env(wdm: Any) -> None:
    """Re-apply the loaded env to the monitor's import-time constants.

    The package __init__ imports bridge_withdraw_monitor before --env-file
    is read, so its module-level os.getenv() results must be refreshed here.
    """
    for name in (
        "ETH_RPC_URL",
        "ETH_WALLET_ADDRESS",
        "ETH_WALLET_PRIVATE_KEY",
        "BRIDGE_ADMIN_PRIVATE_KEY",
        "BLOCKCHAIN_RPC_URL",
        "ETH_NETWORK",
        "ETH_WITHDRAW_GAS",
        "GENESIS_WALLET_ADDRESS",
        "GENESIS_WALLET_PRIVATE_KEY",
    ):
        val = os.getenv(name)
        if val is not None:
            setattr(wdm, name, val)
    wdm.ETH_WITHDRAW_GAS_MARGIN = Decimal(os.getenv("ETH_WITHDRAW_GAS_MARGIN", "1.25"))
    wdm.ETH_WITHDRAW_GAS_MAX = int(os.getenv("ETH_WITHDRAW_GAS_MAX", "300000"))
    wdm.ETH_RELEASE_CONFIRMATIONS = int(os.getenv("BRIDGE_RELEASE_CONFIRMATIONS", os.getenv("BRIDGE_CONFIRMATIONS", "3")))
    wdm.ETH_RELEASE_ABSENCE_GRACE_SECONDS = int(os.getenv("ETH_RELEASE_ABSENCE_GRACE_SECONDS", "600"))
    wdm.BRIDGE_ENABLED = os.getenv("BRIDGE_ENABLED", "false").lower() == "true"
    wdm.WITHDRAW_ENABLED = os.getenv("BRIDGE_WITHDRAW_ENABLED", "true").lower() == "true"


async def _rpc_call(rpc_url: str, method: str, params: list[Any]) -> Any:
    """Plain JSON-RPC POST to an arbitrary endpoint (not the monitor's)."""
    payload = {"jsonrpc": "2.0", "method": method, "params": params, "id": 1}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(rpc_url, json=payload)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError as e:
        # httpx error text embeds the full request URL — redact it (ETH-15).
        raise RuntimeError(f"{method} request to {redact_url(rpc_url)} failed: {redact_text(str(e))}") from e
    if "error" in data:
        raise RuntimeError(f"{method} error from {redact_url(rpc_url)}: {data['error']}")
    return data.get("result")


async def _release_verdict(wdm: Any, rpc_url: str, row: dict[str, Any]) -> dict[str, Any]:
    """Prove the recorded release's on-chain fate on ONE endpoint.

    verdict: 'reverted' | 'never_mined' | 'sent' | 'ambiguous'. Only
    'reverted' and 'never_mined' permit a retry — anything else means the
    row cannot be proven unpaid and must be left for the operator.
    """
    out: dict[str, Any] = {"rpc": redact_url(rpc_url)}
    eth_tx_hash = str(row.get("eth_tx_hash") or "")
    nonce = row.get("release_nonce")
    to_address = str(row.get("eth_address") or "")
    if not eth_tx_hash or nonce is None:
        out["verdict"] = "ambiguous"
        out["detail"] = "row has no recorded eth_tx_hash/release_nonce"
        return out

    receipt = await _rpc_call(rpc_url, "eth_getTransactionReceipt", [eth_tx_hash])
    latest = int(await _rpc_call(rpc_url, "eth_blockNumber", []), 16)
    if receipt is not None:
        status = wdm._receipt_status(receipt)
        block = int(receipt.get("blockNumber") or "0x0", 16)
        depth = latest - block + 1 if block else 0
        out.update({"block": block, "receipt_status": status, "depth": depth})
        if status == 1:
            out["verdict"] = "sent"
            out["detail"] = "recorded release receipt is successful — the ETH actually left"
            return out
        if depth < wdm.ETH_RELEASE_CONFIRMATIONS:
            out["verdict"] = "ambiguous"
            out["detail"] = f"reverted receipt below confirmation depth ({depth})"
            return out
        # A status-0 receipt reverts every effect: the receiver's balance at
        # the failed block equals its balance just before it. A difference
        # means another tx in that block paid the receiver — ambiguous.
        pre = int(await _rpc_call(rpc_url, "eth_getBalance", [to_address, hex(block - 1)]), 16)
        post = int(await _rpc_call(rpc_url, "eth_getBalance", [to_address, hex(block)]), 16)
        out.update({"receiver_pre": pre, "receiver_post": post})
        if pre != post:
            out["verdict"] = "ambiguous"
            out["detail"] = "receiver balance moved inside the failed tx's block"
            return out
        latest_nonce = int(await _rpc_call(rpc_url, "eth_getTransactionCount", [wdm.ETH_WALLET_ADDRESS, "latest"]), 16)
        out["latest_nonce"] = latest_nonce
        if latest_nonce <= int(nonce):
            out["verdict"] = "ambiguous"
            out["detail"] = "recorded release nonce not consumed despite a sealed revert"
            return out
        out["verdict"] = "reverted"
        return out

    tx = await _rpc_call(rpc_url, "eth_getTransactionByHash", [eth_tx_hash])
    latest_nonce = int(await _rpc_call(rpc_url, "eth_getTransactionCount", [wdm.ETH_WALLET_ADDRESS, "latest"]), 16)
    out["latest_nonce"] = latest_nonce
    if tx is not None:
        out["verdict"] = "ambiguous"
        out["detail"] = "tx is known to the node but unmined — it may still seal"
        return out
    if latest_nonce <= int(nonce):
        out["verdict"] = "never_mined"
        out["detail"] = "hash absent from chain and its nonce is still free"
        return out
    out["verdict"] = "ambiguous"
    out["detail"] = "hash absent but the recorded nonce was consumed by another tx"
    return out


async def _ait_rpc_get(url: str) -> Any:
    """GET a hub chain-rpc endpoint (seam for tests)."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPError as e:
        raise RuntimeError(f"chain RPC request to {redact_url(url)} failed: {redact_text(str(e))}") from e


async def _ait_leg_confirmed(wdm: Any, ait_tx_hash: str) -> tuple[bool, str]:
    """The AIT BRIDGE_WITHDRAW tx must be sealed on the hub chain."""
    url = f"{wdm.BLOCKCHAIN_RPC_URL}/rpc/transaction/{ait_tx_hash}"
    data = await _ait_rpc_get(url)
    if not isinstance(data, dict):
        return False, f"unexpected chain response: {data!r}"
    status = data.get("status")
    height = data.get("block_height")
    if status == "confirmed" and height is not None:
        return True, f"AIT tx sealed at block {height}"
    return False, f"AIT tx status={status} block_height={height}"


def _print_row(row: dict[str, Any]) -> None:
    for key in (
        "id",
        "ait_tx_hash",
        "from_address",
        "eth_address",
        "amount_ait",
        "fee_ait",
        "net_ait",
        "amount_eth",
        "status",
        "eth_tx_hash",
        "release_nonce",
        "refund_tx_hash",
        "error",
        "created_at",
        "released_at",
        "completed_at",
        "refunded_at",
        "retry_count",
    ):
        print(f"  {key}: {row.get(key)}")


def _print_verdicts(verdicts: list[dict[str, Any]]) -> None:
    for v in verdicts:
        extras = {k: val for k, val in v.items() if k not in ("rpc", "verdict", "detail")}
        print(f"  {v['rpc']}: {v['verdict']}  {extras}")
        if v.get("detail"):
            print(f"    detail: {v['detail']}")


async def _gather_proofs(
    wdm: Any, row: dict[str, Any], verify_rpc: str | None, *, require_pair: bool = True
) -> list[dict[str, Any]] | None:
    """Run the release-verdict bundle on ETH_RPC_URL plus a second endpoint.

    Returns the per-endpoint verdicts, or None when the setup itself is
    missing (caller prints). For mutating commands two *independent*
    endpoints are mandatory — a single-RPC verdict is never enough to
    move money. ``status`` passes ``require_pair=False`` and accepts
    whatever endpoints are configured.
    """
    urls = [u for u in (wdm.ETH_RPC_URL, verify_rpc) if u]
    if require_pair and len(set(urls)) < 2:
        print("refusing: two independent Ethereum RPC endpoints are required")
        print("  set --verify-rpc or ETH_VERIFY_RPC_URL to a second public endpoint")
        return None
    verdicts = []
    for url in dict.fromkeys(urls):
        try:
            verdicts.append(await _release_verdict(wdm, url, row))
        except Exception as e:
            detail = f"rpc error: {redact_text(str(e))}"
            if "historical state" in detail or "-32000" in detail:
                # The receiver-balance proof reads state at the failed
                # block — a pruned endpoint can never answer it.
                detail += " — endpoint is not archive-capable (proof needs state at the failed block)"
            verdicts.append({"rpc": redact_url(url), "verdict": "ambiguous", "detail": detail})
    return verdicts


def _proofs_allow_retry(verdicts: list[dict[str, Any]]) -> bool:
    return all(v.get("verdict") in ("reverted", "never_mined") for v in verdicts)


def _proofs_share_nonce(verdicts: list[dict[str, Any]]) -> int | None:
    nonces = {v.get("latest_nonce") for v in verdicts}
    if len(nonces) != 1:
        return None
    shared = nonces.pop()
    return int(shared) if shared is not None else None


def _release_environment_ok(wdm: Any) -> bool:
    """The signing step may only run where the release environment is
    loaded — in practice hub's aitbc-wallet env: BRIDGE_ENABLED, withdraws
    not disabled, and a release key present. Anywhere else --confirm
    refuses (a dry-run still works everywhere for inspection)."""
    if not wdm.BRIDGE_ENABLED:
        print("refusing: BRIDGE_ENABLED is not set in this environment — this is not the releasing host")
        return False
    if not wdm.WITHDRAW_ENABLED:
        print("refusing: BRIDGE_WITHDRAW_ENABLED=false — releases are disabled on this host")
        return False
    key, error = wdm._validate_release_key()
    if not key:
        print(f"refusing: {error} — a live retry can only sign where the release key is configured")
        return False
    return True


async def _cmd_status(wdm: Any, db: Any, ait_tx_hash: str, verify_rpc: str | None) -> int:
    row = db.get_withdrawal_by_ait_tx_hash(ait_tx_hash)
    if not row:
        print(f"no withdrawal row {ait_tx_hash}")
        return 1
    _print_row(row)
    attempts = db.get_release_attempts(ait_tx_hash)
    if attempts:
        print("release attempts:")
        for a in attempts:
            print(
                f"  #{a['id']} {a['resolved_at']} by={a['resolved_by']} "
                f"outcome={a['outcome']} nonce={a['release_nonce']} eth_tx={a['eth_tx_hash']}"
            )
            if a.get("operator_note"):
                print(f"      note: {a['operator_note']}")
    print("live outcome:")
    print(f"  monitor view: {await wdm._verify_release_outcome(ait_tx_hash)}")
    verdicts = await _gather_proofs(wdm, row, verify_rpc, require_pair=False)
    if verdicts:
        _print_verdicts(verdicts)
    return 0


def _retry_eligibility_error(row: dict[str, Any]) -> str | None:
    """Why this row may not be retried, or None when it may."""
    if row.get("refund_tx_hash"):
        return "refund already recorded — a retry would double-compensate"
    if row["status"] not in _RETRY_ELIGIBLE:
        return (
            f"status={row['status']} is not retryable "
            f"(allowed: {sorted(_RETRY_ELIGIBLE)}; monitor-owned or in-flight rows are left alone)"
        )
    return None


async def _release_retry_preflight(wdm: Any, row: dict[str, Any], verify_rpc: str | None) -> tuple[int, int, int] | None:
    """Prove the recorded release failed and price the retry.

    Returns (nonce, gas_limit, gas_price), or None when any proof is
    missing — every refusal prints its reason. Pure reads; no writes.
    """
    verdicts = await _gather_proofs(wdm, row, verify_rpc)
    if verdicts is None:
        return None
    print("release-fate proofs:")
    _print_verdicts(verdicts)
    if not _proofs_allow_retry(verdicts):
        print("refusing: recorded release is not proven failed on all endpoints")
        return None
    nonce = _proofs_share_nonce(verdicts)
    if nonce is None:
        print("refusing: endpoints disagree on the current account nonce")
        return None

    ok, detail = await _ait_leg_confirmed(wdm, str(row["ait_tx_hash"]))
    print(f"AIT leg: {detail}")
    if not ok:
        print("refusing: the AIT withdraw tx is not sealed on the hub chain")
        return None

    to_address = str(row["eth_address"])
    amount_eth = Decimal(str(row["amount_eth"]))
    try:
        gas_limit = await wdm._release_gas_limit(to_address, amount_eth)
        gas_price = await wdm._eth_gas_price()
    except Exception as e:
        print(f"refusing: cannot bound release gas safely: {redact_text(str(e))}")
        return None
    print("planned retry:")
    print(f"  to: {to_address}")
    print(f"  amount_eth: {amount_eth}  (recorded value, never re-quoted)")
    print(f"  nonce: {nonce}  (current account nonce; reuses the free slot when a prior send never sealed)")
    print(f"  gas_limit: {gas_limit}")
    print(f"  gas_price: {gas_price} wei  (~{Decimal(gas_limit * gas_price) / Decimal(10**18)} ETH worst case)")
    return nonce, gas_limit, gas_price


async def _await_retry_outcome(wdm: Any, db: Any, row: dict[str, Any], tx_hash: str, nonce: int, attempt_id: int) -> int:
    """Watch the broadcast retry for a bounded window; resolve the row."""
    ait_tx_hash = str(row["ait_tx_hash"])
    waited = 0
    while True:
        outcome = await wdm._verify_release_outcome(ait_tx_hash)
        if outcome == "sent":
            await wdm._update_status_with_retry(ait_tx_hash, "completed", eth_tx_hash=tx_hash)
            db.update_release_attempt(attempt_id, outcome="sent")
            print(f"withdrawal {row['id']} completed — receipt verified at depth")
            return 0
        if outcome == "not_sent":
            db.update_withdrawal_status(
                ait_tx_hash,
                "needs_review_release",
                error="release retry proven unsent — operator decision required",
            )
            db.update_release_attempt(attempt_id, outcome="not_sent")
            print("retry proven unsent — row parked at needs_review_release")
            print("fallback: mark-review for the AIT refund path, or retry again once provable")
            return 1
        if waited >= _RETRY_OUTCOME_WAIT_SECONDS:
            break
        await asyncio.sleep(_RETRY_OUTCOME_POLL_SECONDS)
        waited += _RETRY_OUTCOME_POLL_SECONDS
    print("still unverifiable — row stays 'releasing_retry'; the monitor's resume pass owns it")
    db.update_release_attempt(attempt_id, outcome="broadcast (unconfirmed at wait end)")
    return 0


async def _cmd_release_retry(wdm: Any, db: Any, args: argparse.Namespace) -> int:
    ait_tx_hash = args.ait_tx_hash
    row = db.get_withdrawal_by_ait_tx_hash(ait_tx_hash)
    if not row:
        print(f"no withdrawal row {ait_tx_hash}")
        return 1
    _print_row(row)

    eligible_error = _retry_eligibility_error(row)
    if eligible_error:
        print(f"refusing: {eligible_error}")
        return 1

    plan = await _release_retry_preflight(wdm, row, args.verify_rpc)
    if plan is None:
        return 1
    nonce, _gas_limit, _gas_price = plan

    if not args.confirm:
        print("dry-run: no write, no send. Re-run with --confirm --note '…' to release.")
        return 0
    if not _release_environment_ok(wdm):
        return 1
    if not args.note or not args.note.strip():
        print("refusing: --confirm requires --note (a written justification is mandatory)")
        return 2

    operator = args.operator or getpass.getuser()
    attempt_id = db.record_release_attempt(ait_tx_hash, resolved_by=operator, operator_note=args.note.strip())
    print(f"attempt #{attempt_id} recorded (retry_count bumped) — signing and broadcasting")
    try:
        tx_hash = await wdm._release_eth_for_withdrawal(
            str(row["id"]),
            ait_tx_hash,
            str(row["eth_address"]),
            Decimal(str(row["amount_eth"])),
            intent_status="releasing_retry",
            nonce=nonce,
        )
    except Exception as e:
        db.update_release_attempt(attempt_id, outcome=f"failed: {redact_text(str(e))}")
        print(f"release attempt failed before/at broadcast: {redact_text(str(e))}")
        print("row stays eligible for another proven retry or mark-review")
        return 1
    db.update_release_attempt(attempt_id, eth_tx_hash=tx_hash, release_nonce=nonce, outcome="broadcast")
    print(f"broadcast: {tx_hash} — waiting for a status-1 receipt (up to {_RETRY_OUTCOME_WAIT_SECONDS}s)")
    return await _await_retry_outcome(wdm, db, row, tx_hash, nonce, attempt_id)


async def _cmd_mark_review(wdm: Any, db: Any, args: argparse.Namespace) -> int:
    ait_tx_hash = args.ait_tx_hash
    row = db.get_withdrawal_by_ait_tx_hash(ait_tx_hash)
    if not row:
        print(f"no withdrawal row {ait_tx_hash}")
        return 1
    _print_row(row)

    if row.get("refund_tx_hash"):
        print("refusing: refund already recorded")
        return 1
    if row["status"] not in _MARK_REVIEW_ELIGIBLE:
        print(f"refusing: status={row['status']} not eligible (allowed: {sorted(_MARK_REVIEW_ELIGIBLE)})")
        return 1
    if not args.note or not args.note.strip():
        print("refusing: --note is required (the reason lands in the row's error field)")
        return 2

    # The flip is still gated on the recorded release being proven unsent —
    # the resume pass re-verifies before refunding, so this is belt on braces.
    verdicts = await _gather_proofs(wdm, row, args.verify_rpc)
    if verdicts is None:
        return 1
    _print_verdicts(verdicts)
    if not _proofs_allow_retry(verdicts):
        print("refusing: recorded release is not proven failed on all endpoints")
        return 1

    if not args.confirm:
        print("dry-run: would set 'needs_review' — the monitor then proves not_sent and refunds")
        return 0
    db.update_withdrawal_status(ait_tx_hash, "needs_review", error=args.note.strip())
    print("row → needs_review; next monitor poll proves the release unsent and refunds the AIT")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="withdraw_admin",
        description="Operator commands for AIT->ETH withdrawal rows (see module docstring).",
    )
    parser.add_argument(
        "--env-file",
        action="append",
        default=None,
        help="EnvironmentFile to load (repeatable; default: the aitbc-wallet unit's set)",
    )
    parser.add_argument("--db", default=None, help="bridge sqlite path (default: the service's DB_PATH)")
    parser.add_argument(
        "--verify-rpc",
        default=None,
        help="second independent Ethereum RPC endpoint (or ETH_VERIFY_RPC_URL) — required for mutating commands",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_status = sub.add_parser("status", help="show ledger row, attempts, live outcome")
    p_status.add_argument("ait_tx_hash")

    p_retry = sub.add_parser("release-retry", help="re-release a proven-failed release (dry-run default)")
    p_retry.add_argument("ait_tx_hash")
    p_retry.add_argument("--note", default=None, help="written justification — mandatory with --confirm")
    p_retry.add_argument("--operator", default=None, help="recorded operator name (default: current user)")
    p_retry.add_argument("--confirm", action="store_true", help="actually sign and broadcast")

    p_review = sub.add_parser("mark-review", help="move a row to needs_review (auto-refund lane)")
    p_review.add_argument("ait_tx_hash")
    p_review.add_argument("--note", default=None, help="reason recorded on the row")
    p_review.add_argument("--operator", default=None, help="recorded operator name (default: current user)")
    p_review.add_argument("--confirm", action="store_true", help="perform the status write")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    _load_env_files(args.env_file or _DEFAULT_ENV_FILES)

    from . import bridge_db as db
    from . import bridge_withdraw_monitor as wdm

    _sync_wdm_env(wdm)
    if args.db:
        if not os.path.exists(args.db):
            print(f"no such db: {args.db}")
            return 2
        db.DB_PATH = args.db
    db.init_db()
    args.verify_rpc = args.verify_rpc or os.getenv("ETH_VERIFY_RPC_URL")

    if args.command == "status":
        return asyncio.run(_cmd_status(wdm, db, args.ait_tx_hash, args.verify_rpc))
    if args.command == "release-retry":
        return asyncio.run(_cmd_release_retry(wdm, db, args))
    if args.command == "mark-review":
        return asyncio.run(_cmd_mark_review(wdm, db, args))
    return 2


if __name__ == "__main__":
    sys.exit(main())
