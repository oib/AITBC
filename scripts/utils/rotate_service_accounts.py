#!/usr/bin/env python3
"""Rotate the derivable service accounts onto freshly minted keys.

The genesis writers allocated these accounts at Account.from_key(sha256(name)),
so their private keys are reproducible by anyone holding the public repo. This
moves each balance to a new address whose key is random, and persists the new
keys before any transfer is submitted.

Ordering is the whole safety property: keys are minted, written, fsynced and
read back BEFORE the first transaction goes out. A crash after that loses at
most an unsubmitted transfer -- never a key for an address already holding funds.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "apps" / "blockchain-node" / "src"))
sys.path.insert(0, str(REPO))

from eth_account import Account  # noqa: E402
from aitbc_chain.rpc.utils import sign_transaction_data, verify_transaction_signature  # noqa: E402

SERVICE_NAMES = (
    "aiengine",
    "surveillance",
    "analytics",
    "marketplace",
    "enterprise",
    "multimodal",
    "zkproofs",
    "crosschain",
    "developer1",
    "developer2",
    "tester",
)
UNITS_PER_AIT = 36_000_000
DEFAULT_KEYS_FILE = Path("/var/lib/aitbc/keystore/service_accounts.json")


def rpc_get(base: str, path: str) -> dict:
    with urllib.request.urlopen(f"{base}{path}", timeout=10) as r:
        return json.load(r)


def rpc_post(base: str, path: str, body: dict) -> tuple[int, dict | str]:
    req = urllib.request.Request(
        f"{base}{path}", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        raw = e.read().decode(errors="replace")
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, raw


def extract_tx_hash(resp) -> str | None:
    """Pull the submitted hash out of POST /v1/transaction's response.

    The endpoint returns ``transaction_hash``; ``tx_hash``/``hash`` are kept as
    fallbacks for older peers.
    """
    if not isinstance(resp, dict):
        return None
    return resp.get("transaction_hash") or resp.get("tx_hash") or resp.get("hash")


def old_account(name: str):
    return Account.from_key(hashlib.sha256(f"aitbc1{name}".encode()).digest())


def load_or_mint(keys_file: Path, dry_run: bool) -> dict[str, dict]:
    """Reuse an existing key file if present, else mint. Never mint twice."""
    if keys_file.exists():
        existing = json.loads(keys_file.read_text())
        missing = [n for n in SERVICE_NAMES if n not in existing]
        if missing:
            raise SystemExit(
                f"ABORT: {keys_file} exists but lacks {missing}. Refusing to partially overwrite an existing key file."
            )
        print(f"[keys] reusing existing {keys_file} ({len(existing)} accounts)")
        return existing

    minted = {}
    for name in SERVICE_NAMES:
        acct = Account.from_key(os.urandom(32))
        minted[name] = {"address": acct.address, "private_key": "0x" + acct.key.hex()}

    if dry_run:
        print(f"[keys] DRY RUN: would write {len(minted)} new keys to {keys_file} (0600)")
        return minted

    keys_file.parent.mkdir(parents=True, exist_ok=True)
    tmp = keys_file.with_suffix(".json.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as fh:
        json.dump(minted, fh, indent=2, sort_keys=True)
        fh.flush()
        os.fsync(fh.fileno())
    os.chmod(tmp, 0o600)
    os.replace(tmp, keys_file)
    dirfd = os.open(keys_file.parent, os.O_RDONLY)
    os.fsync(dirfd)
    os.close(dirfd)

    # Read back and compare before a single unit moves.
    readback = json.loads(keys_file.read_text())
    if readback != minted:
        raise SystemExit(f"ABORT: read-back of {keys_file} does not match what was minted. No transactions submitted.")
    mode = oct(keys_file.stat().st_mode & 0o777)
    if mode != "0o600":
        raise SystemExit(f"ABORT: {keys_file} has mode {mode}, expected 0o600.")
    print(f"[keys] wrote + fsynced + verified {keys_file} mode={mode}")
    return minted


def build_signed(chain_id: str, src, dst_addr: str, amount: int, nonce: int, fee: int) -> dict:
    """Build the tx exactly as the server will reconstruct it, then sign that.

    TransactionRequest.validate_payload runs mode="before" on the *aliased*
    input: "recipient" is not a key there (the wire field is "to"), so an
    omitted payload becomes {"amount": N} server-side -- not {}. Signing over
    the payload we send only matches if we send the payload explicitly.
    """
    payload = {"to": dst_addr, "amount": amount}
    tx = {
        "from": src.address,
        "to": dst_addr,
        "amount": amount,
        "fee": fee,
        "nonce": nonce,
        "payload": payload,
        "type": "TRANSFER",
        "chain_id": chain_id,
        "signature": "",
    }
    sig = sign_transaction_data(tx, "0x" + src.key.hex())
    tx["signature"] = sig
    if not verify_transaction_signature(tx, sig, src.address):
        raise SystemExit(f"ABORT: locally built signature for {src.address} does not verify.")
    return tx


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rpc", required=True, help="e.g. http://127.0.0.1:8202")
    ap.add_argument("--chain-id", required=True)
    ap.add_argument("--keys-file", type=Path, default=DEFAULT_KEYS_FILE)
    ap.add_argument("--fee", type=int, default=0)
    ap.add_argument(
        "--execute", action="store_true", help="Actually write keys and submit. Without it, nothing leaves this process."
    )
    args = ap.parse_args()
    dry = not args.execute

    head = rpc_get(args.rpc, "/v1/chain/head")
    print(f"[chain] head height={head.get('height')} ts={head.get('timestamp')}")

    keys = load_or_mint(args.keys_file, dry)

    plan, total = [], 0
    for name in SERVICE_NAMES:
        src = old_account(name)
        bal = rpc_get(args.rpc, f"/v1/balance/{src.address}")
        acct = rpc_get(args.rpc, f"/v1/account/{src.address}")
        amount = int(bal.get("total_balance", 0))
        nonce = int(acct.get("nonce", 0))
        staked = int(bal.get("staked_balance", 0) or 0)
        if staked:
            raise SystemExit(f"ABORT: {name} has {staked} staked; unbond before rotating.")
        if amount <= args.fee:
            print(f"[skip] {name}: balance {amount} <= fee {args.fee}")
            continue
        send = amount - args.fee
        dst = keys[name]["address"]
        tx = build_signed(args.chain_id, src, dst, send, nonce, args.fee)
        plan.append((name, src.address, dst, send, nonce, tx))
        total += send
        print(f"[plan] {name:<14} {src.address} -> {dst}  {send} units  nonce={nonce}  sig OK")

    print(f"\n[plan] {len(plan)} transfers, {total} units = {total // UNITS_PER_AIT:,} AIT, fee={args.fee}")

    if dry:
        print("\nDRY RUN -- nothing written, nothing submitted. Re-run with --execute.")
        return 0

    submitted = []
    for name, _src_addr, _dst, _send, _nonce, tx in plan:
        status, resp = rpc_post(args.rpc, "/v1/transaction", tx)
        if status not in (200, 201, 202):
            print(f"[FAIL] {name}: HTTP {status} {resp}")
            print(
                f"\nSTOPPED after {len(submitted)} of {len(plan)}. "
                f"Keys for all accounts are already saved in {args.keys_file}."
            )
            return 1
        txh = extract_tx_hash(resp)
        submitted.append((name, txh))
        print(f"[sent] {name:<14} {txh}")
        time.sleep(0.2)

    print(f"\n[done] {len(submitted)} submitted. Confirm with:")
    print(f"  for each old address: {args.rpc}/v1/balance/<addr>  -> expect total_balance 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
