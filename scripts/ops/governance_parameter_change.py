#!/usr/bin/env python3
"""Plan or submit an operator-signed governance parameter change.

The authority parameters (``governance_executors``,
``escrow_settlement_authority``, ``bond_slash_authority``,
``bridge_release_authority``, ``escrow_fee_recipient``) change only through a
sealed ``GOVERNANCE_EXECUTE`` transaction signed by an address in the on-chain
``governance_executors`` set. The node-side ``execute_governance_proposal``
route signs with the node's own key, so it cannot speak for the executor —
whose key lives only on the operator workstation. This tool is the offline-key
path:

    plan         Read the parameter from the chain, print the unsigned
                 transaction and its signing digest. Needs no key.
    sign-submit  Sign with the key from --key-file (never argv, never
                 printed), POST to the node's /rpc/transaction, wait for the
                 seal, and read the parameter back. Requires --confirm and
                 refuses when the current value already equals the target.

Submissions go to whatever --rpc-url names — the transaction-intake endpoint is
unauthenticated (the sender signature is the credential). The envelope matches
the sealed shape of the executed parameter changes: a flat payload carrying
to/amount/type/chain_id plus proposal_id/executor/execution_payload, fee
DEFAULT_TX_FEE_UNITS.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import NoReturn

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "apps" / "blockchain-node" / "src"))
sys.path.insert(0, str(REPO))

from aitbc.utils.units import DEFAULT_TX_FEE_UNITS  # noqa: E402
from aitbc_chain.rpc.utils import _unsigned_tx_fields, sign_transaction_data, verify_transaction_signature  # noqa: E402

# The five address-valued authority parameters this tool covers. Values are a
# 0x address; governance_executors takes a comma-separated list of them.
AUTHORITY_PARAMETERS = (
    "governance_executors",
    "escrow_settlement_authority",
    "bond_slash_authority",
    "bridge_release_authority",
    "escrow_fee_recipient",
)

_ADDRESS_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")
_ZERO_ADDRESS = "0x" + "0" * 40


def _fail(message: str) -> NoReturn:
    print(f"error: {message}", file=sys.stderr)
    sys.exit(2)


def _rpc_get(base: str, path: str) -> dict:
    with urllib.request.urlopen(f"{base}{path}", timeout=15) as r:  # nosec B310 -- operator-supplied internal RPC endpoint
        return json.load(r)


def _rpc_post(base: str, path: str, body: dict) -> tuple[int, dict | str]:
    req = urllib.request.Request(
        f"{base}{path}", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:  # nosec B310 -- operator-supplied internal RPC endpoint
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode())
        except Exception:
            return e.code, ""


def _fetch_chain_id(rpc_url: str) -> str:
    try:
        return str(_rpc_get(rpc_url, "/rpc/info")["chain_id"])
    except Exception as e:
        _fail(f"cannot read chain_id from {rpc_url}/rpc/info: {e}")


def _fetch_parameters(rpc_url: str, chain_id: str) -> dict[str, str]:
    """Current chain parameters from the state snapshot."""
    try:
        snap = _rpc_get(rpc_url, f"/rpc/state/snapshot?chain_id={chain_id}")
    except Exception as e:
        _fail(f"cannot read chain parameters from {rpc_url}: {e}")
    return {p["parameter"]: p["value"] for p in snap.get("chain_parameters", [])}


def _fetch_nonce(rpc_url: str, chain_id: str, address: str) -> int:
    """Account nonce; an absent account row means nonce 0."""
    try:
        return int(_rpc_get(rpc_url, f"/rpc/account/{address}?chain_id={chain_id}").get("nonce", 0))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return 0
        _fail(f"cannot read account {address}: HTTP {e.code}")
    except Exception as e:
        _fail(f"cannot read account {address}: {e}")


def _validate_target(value: str) -> list[str]:
    """Every comma-separated element must be a 0x address and not the zero address."""
    elements = [v.strip() for v in value.split(",")]
    for element in elements:
        if not _ADDRESS_RE.match(element):
            _fail(f"invalid target address {element!r} — expected 0x + 40 hex")
        if element.lower() == _ZERO_ADDRESS:
            _fail("target is the zero address — refusing")
    return elements


def _build_tx(executor: str, chain_id: str, nonce: int, proposal_id: str, parameter: str, value: str) -> dict:
    """The sealed-envelope shape: flat payload carrying the tx fields plus the
    governance triple (proposal_id, executor, execution_payload)."""
    return {
        "from": executor,
        "to": executor,
        "amount": 0,
        "fee": DEFAULT_TX_FEE_UNITS,
        "nonce": nonce,
        "payload": {
            "to": executor,
            "amount": 0,
            "type": "GOVERNANCE_EXECUTE",
            "chain_id": chain_id,
            "proposal_id": proposal_id,
            "executor": executor,
            "execution_payload": {"action": "parameter_change", "parameter": parameter, "value": value},
        },
        "type": "GOVERNANCE_EXECUTE",
        "chain_id": chain_id,
    }


def _signing_digest(tx: dict) -> str:
    """The keccak256 hash sign_transaction_data signs — what the operator audits."""
    from eth_utils import keccak

    message = json.dumps(_unsigned_tx_fields(tx), sort_keys=True, separators=(",", ":")).encode()
    return "0x" + keccak(message).hex()


def _read_key_file(path: str) -> str:
    """Read a raw-hex private key file. Never prints the value; on malformed
    input the error names the file, not the bytes. Refuses files readable by
    group or others — a world-readable executor key is a custody failure."""
    key_path = Path(path)
    try:
        mode = key_path.stat().st_mode & 0o777
        text = key_path.read_text().strip()
    except OSError as e:
        _fail(f"cannot read key file {path}: {e}")
    if mode & 0o077:
        _fail(f"key file {path} is group/other-accessible (mode {mode:03o}) — chmod 600 it first")
    if not re.fullmatch(r"(0x)?[0-9a-fA-F]{64}", text):
        _fail(f"key file {path} is not a bare secp256k1 private key (expected 0x + 64 hex)")
    return "0x" + text.removeprefix("0x")


def _executor_address(private_key: str) -> str:
    from eth_account import Account

    return Account.from_key(private_key).address  # type: ignore[no-any-return]


def _wait_confirmed(rpc_url: str, tx_hash: str, chain_id: str, timeout_s: int, interval_s: float = 5.0) -> dict | None:
    """Poll /rpc/transaction/{hash} until the row is confirmed; None on timeout."""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            row = _rpc_get(rpc_url, f"/rpc/transaction/{tx_hash}?chain_id={chain_id}")
        except urllib.error.HTTPError as e:
            if e.code == 404:  # not sealed yet
                time.sleep(interval_s)
                continue
            raise
        if row.get("status") == "confirmed" and row.get("block_height") is not None:
            return row
        time.sleep(interval_s)
    return None


def _default_executor(parameters: dict[str, str]) -> str:
    executors = parameters.get("governance_executors", "")
    parts = [e.strip() for e in executors.split(",") if e.strip()]
    if len(parts) == 1:
        return parts[0]
    _fail("on-chain governance_executors holds multiple/zero executors — pass --executor explicitly")


def _new_proposal_id(parameter: str, nonce: int) -> str:
    """Label-only id — the chain does not deduplicate proposal_ids (execution
    writes history keyed by (parameter, height)), but a default of
    parameter + date + signer nonce keeps the audit trail unambiguous."""
    return f"manual-{parameter}-{datetime.now(UTC).date().isoformat()}-n{nonce}"


def cmd_plan(args: argparse.Namespace) -> int:
    if args.parameter not in AUTHORITY_PARAMETERS:
        _fail(f"unknown authority parameter {args.parameter!r} — expected one of {', '.join(AUTHORITY_PARAMETERS)}")
    target_elements = _validate_target(args.value)

    chain_id = args.chain_id or _fetch_chain_id(args.rpc_url)
    parameters = _fetch_parameters(args.rpc_url, chain_id)
    executor = args.executor or _default_executor(parameters)
    current = parameters.get(args.parameter)

    if args.parameter == "governance_executors" and executor.lower() not in {e.lower() for e in target_elements}:
        print(
            f"WARNING: executor {executor} is NOT in the new list — signing this change with that "
            "key permanently locks out every executor (no key left able to sign). "
            "sign-submit refuses unless --proof-key-file proves custody of a surviving key.",
            file=sys.stderr,
        )

    nonce = _fetch_nonce(args.rpc_url, chain_id, executor)
    proposal_id = args.proposal_id or _new_proposal_id(args.parameter, nonce)
    tx = _build_tx(executor, chain_id, nonce, proposal_id, args.parameter, args.value)

    print(f"chain_id:   {chain_id}")
    print(f"parameter:  {args.parameter}")
    print(f"current:    {current if current is not None else '(unset)'}")
    print(f"target:     {args.value}")
    print(f"executor:   {executor}  (nonce {nonce} at read time — re-fetched on sign-submit)")
    print(f"proposal_id: {proposal_id}")
    print("unsigned transaction:")
    print(json.dumps(tx, indent=2, sort_keys=True))
    print(f"signing digest (keccak256 of canonical unsigned fields): {_signing_digest(tx)}")
    if current is not None and current.lower() == args.value.lower():
        print("note: current value already equals the target — sign-submit would refuse this change")
    return 0


def cmd_sign_submit(args: argparse.Namespace) -> int:
    if args.parameter not in AUTHORITY_PARAMETERS:
        _fail(f"unknown authority parameter {args.parameter!r} — expected one of {', '.join(AUTHORITY_PARAMETERS)}")
    target_elements = _validate_target(args.value)
    if not args.confirm:
        _fail("sign-submit requires --confirm")

    chain_id = args.chain_id or _fetch_chain_id(args.rpc_url)
    parameters = _fetch_parameters(args.rpc_url, chain_id)
    current = parameters.get(args.parameter)
    if current is not None and current.lower() == args.value.lower():
        _fail(f"{args.parameter} is already {current} — nothing to change")

    private_key = _read_key_file(args.key_file)
    executor = _executor_address(private_key)
    executors = {e.strip().lower() for e in parameters.get("governance_executors", "").split(",") if e.strip()}
    if executor.lower() not in executors:
        _fail(
            f"key file {args.key_file} derives to {executor}, which is not in the on-chain "
            f"governance_executors ({parameters.get('governance_executors', '(unset)')}) — the chain would refuse it"
        )

    # Lock-out guard: a governance_executors change that drops every key the
    # operator holds freezes all parameters forever — no signed executor is
    # left to ever write one. Refuse unless the signing key survives, or
    # --proof-key-file demonstrates custody of a listed survivor.
    if args.parameter == "governance_executors":
        new_set = {e.lower() for e in target_elements}
        if executor.lower() not in new_set:
            if not args.proof_key_file:
                _fail(
                    f"the signing key {executor} is NOT in the new governance_executors list — "
                    "accepting it would lock every executor out permanently. Pass "
                    "--proof-key-file for one of the listed addresses to prove custody of a surviving key."
                )
            proof_address = _executor_address(_read_key_file(args.proof_key_file))
            if proof_address.lower() not in new_set:
                _fail(
                    f"proof key {args.proof_key_file} derives to {proof_address}, "
                    "which is not in the new executor list either — refusing"
                )
            print(
                f"executor rotation: signing key {executor} leaves the set; "
                f"custody of surviving executor {proof_address} proven by --proof-key-file"
            )

    nonce = _fetch_nonce(args.rpc_url, chain_id, executor)
    proposal_id = args.proposal_id or _new_proposal_id(args.parameter, nonce)
    tx = _build_tx(executor, chain_id, nonce, proposal_id, args.parameter, args.value)
    digest = _signing_digest(tx)
    tx["signature"] = sign_transaction_data(tx, private_key)

    # Self-check before the wire: the node's intake refuses a signature that
    # does not recover to the sender, so refuse locally first.
    if not verify_transaction_signature(tx, tx["signature"], executor):
        _fail("local signature verification failed — not submitting")

    status, body = _rpc_post(args.rpc_url, "/rpc/transaction", {"signed_tx": tx, **tx})
    if status != 200 or not (isinstance(body, dict) and body.get("success")):
        _fail(f"submission refused: HTTP {status} {body}")
    tx_hash = str(body["transaction_hash"])
    print(f"submitted {tx_hash} — digest was {digest}")
    print(f"waiting for a block to seal it (timeout {args.timeout}s)…")

    try:
        row = _wait_confirmed(args.rpc_url, tx_hash, chain_id, args.timeout)
    except Exception as e:
        _fail(f"lost contact with {args.rpc_url} while waiting for {tx_hash}: {e}")
    if row is None:
        _fail(f"timed out after {args.timeout}s waiting for {tx_hash} to seal — check /rpc/mempool on {args.rpc_url}")

    after = _fetch_parameters(args.rpc_url, chain_id).get(args.parameter)
    print(f"sealed at block {row.get('block_height')}")
    print(f"{args.parameter}: {current if current is not None else '(unset)'} -> {after}")
    if after is None or after.lower() != args.value.lower():
        _fail(f"parameter did not land: chain now reports {after!r}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--rpc-url",
        required=True,
        help="Node RPC base URL WITHOUT the /rpc suffix (the tool adds it), e.g. http://127.0.0.1:8202 or https://hub.aitbc.bubuit.net",
    )
    parser.add_argument("--chain-id", default=None, help="Chain ID (default: read from /rpc/info)")

    sub = parser.add_subparsers(dest="command", required=True)

    def add_common(p: argparse.ArgumentParser) -> None:
        p.add_argument("--parameter", required=True, help="Authority parameter to change")
        p.add_argument("--value", required=True, help="New value (0x address; comma-separated list for governance_executors)")
        p.add_argument("--executor", default=None, help="Executor address (default: the single on-chain executor)")
        p.add_argument("--proposal-id", default=None, help="Proposal label (default: manual-<parameter>-<date>)")

    plan = sub.add_parser("plan", help="Show the change and the unsigned transaction digest (no key)")
    add_common(plan)
    plan.set_defaults(func=cmd_plan)

    submit = sub.add_parser("sign-submit", help="Sign with --key-file and submit")
    add_common(submit)
    submit.add_argument("--key-file", required=True, help="File containing the executor's raw-hex private key (mode 600)")
    submit.add_argument(
        "--proof-key-file",
        default=None,
        help="Second key file proving custody of a surviving executor — required when the signing key is dropped from a new governance_executors list",
    )
    submit.add_argument("--confirm", action="store_true", help="Required — refuse without it")
    submit.add_argument("--timeout", type=int, default=240, help="Seconds to wait for the seal (default 240)")
    submit.set_defaults(func=cmd_sign_submit)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
