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
                 transaction and its signing digest. Needs no signing key;
                 --proof-key-file files are read to report custody status.
    sign-submit  Sign with the key from --key-file (never argv, never
                 printed), POST to the node's /rpc/transaction, wait for the
                 seal, and read the parameter back. Requires --confirm and
                 refuses when the current value already equals the target.
                 For governance_executors it also refuses unless every member
                 the new list adds is proven by a --proof-key-file (repeatable)
                 deriving to it, and a dropped signing key leaves at least one
                 proven survivor. For escrow_settlement_authority and
                 bond_slash_authority it also refuses when the new authority
                 cannot pay its own tx fees, unless --allow-unfunded-target is
                 passed deliberately.

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

# Authority parameters whose target must already hold a fee-paying balance
# when the change seals — the new authority sends its own fee-paying
# transactions, so rotating to an unfunded address silently disables the
# capability. bridge_release_authority signs in-state bridge credits (no
# account fees) and escrow_fee_recipient only receives fees, so neither is
# gated here.
FEE_PAYING_TARGET_PARAMETERS = (
    "escrow_settlement_authority",
    "bond_slash_authority",
)

_ADDRESS_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")
_ZERO_ADDRESS = "0x" + "0" * 40

# The execute tx costs DEFAULT_TX_FEE_UNITS; the headroom keeps the signer
# (and, on rotation, the surviving executor) funded for follow-up changes
# instead of being drained to the dust boundary by this one. Five more
# transactions' worth, stated for the audit trail.
FEE_HEADROOM_UNITS = 5 * DEFAULT_TX_FEE_UNITS
REQUIRED_BALANCE_UNITS = DEFAULT_TX_FEE_UNITS + FEE_HEADROOM_UNITS


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


def _fetch_account(rpc_url: str, chain_id: str, address: str) -> tuple[int, int]:
    """(nonce, balance) in base units; an absent account row is a fresh 0/0 account."""
    try:
        row = _rpc_get(rpc_url, f"/rpc/account/{address}?chain_id={chain_id}")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return 0, 0
        _fail(f"cannot read account {address}: HTTP {e.code}")
    except Exception as e:
        _fail(f"cannot read account {address}: {e}")
    return int(row.get("nonce", 0)), int(row.get("balance", 0))


def _check_fee_balance(label: str, address: str, balance: int) -> None:
    """Refuse when ``address`` cannot cover the tx fee plus headroom."""
    if balance < REQUIRED_BALANCE_UNITS:
        _fail(
            f"{label} {address} balance {balance} < required {REQUIRED_BALANCE_UNITS} units "
            f"(fee {DEFAULT_TX_FEE_UNITS} + headroom {FEE_HEADROOM_UNITS}) — fund it first"
        )


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


def _proof_addresses(
    proof_files: list[str], target_elements: list[str], *, strict: bool = True
) -> tuple[list[str], list[str]]:
    """The executor addresses the ``--proof-key-file`` keys prove custody of.

    Each file's key derives to one address, and that address must be a member
    of the new executor list — proving a key outside it demonstrates custody
    of nothing the change keeps. Deduped by lowercased address: the same key
    passed twice still counts once. Returns ``(proven, invalid)``: deduped
    member addresses in first-seen order (original spelling) plus one message
    per out-of-list proof. ``strict=False`` collects those messages instead of
    failing — plan reports them as warnings; sign-submit leaves the default.
    Addresses and file paths only, never keys.
    """
    new_set = {e.lower() for e in target_elements}
    proven: dict[str, str] = {}
    invalid: list[str] = []
    for path in proof_files:
        address = _executor_address(_read_key_file(path))
        if address.lower() not in new_set:
            message = f"proof key file {path} derives to {address}, which is not in the new executor list"
            if strict:
                _fail(message + " — refusing")
            invalid.append(message)
            continue
        proven.setdefault(address.lower(), address)
    return list(proven.values()), invalid


def _executor_lockout_reason(executor: str, target_elements: list[str], proof_addresses: list[str]) -> str | None:
    """Why a governance_executors change would permanently lock out every
    executor — or None when the signer survives or custody of a listed survivor
    is proven. ``proof_addresses`` are new-list members already proven via
    --proof-key-file (validated by _proof_addresses); a dropped signer without
    one leaves the operator holding no key able to ever sign a
    GOVERNANCE_EXECUTE again — the only exit is consensus surgery."""
    if executor.lower() in {e.lower() for e in target_elements}:
        return None
    if not proof_addresses:
        return (
            f"the signing key {executor} is NOT in the new governance_executors list — "
            "accepting it would lock every executor out permanently. Pass "
            "--proof-key-file for one of the listed addresses to prove custody of a surviving key."
        )
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

    proven: set[str] = set()
    if args.parameter == "governance_executors":
        proven_list, invalid_proofs = _proof_addresses(args.proof_key_file, target_elements, strict=False)
        proven = {a.lower() for a in proven_list}
        for message in invalid_proofs:
            print(f"warning: {message} — it proves nothing this change keeps", file=sys.stderr)

    nonce, balance = _fetch_account(args.rpc_url, chain_id, executor)
    proposal_id = args.proposal_id or _new_proposal_id(args.parameter, nonce)
    tx = _build_tx(executor, chain_id, nonce, proposal_id, args.parameter, args.value)

    print(f"chain_id:   {chain_id}")
    print(f"parameter:  {args.parameter}")
    print(f"current:    {current if current is not None else '(unset)'}")
    print(f"target:     {args.value}")
    if args.parameter == "governance_executors":
        current_set = {e.strip().lower() for e in (current or "").split(",") if e.strip()}
        unproven: list[str] = []
        for element in target_elements:
            if element.lower() in current_set:
                mark = "kept"
            elif element.lower() in proven:
                mark = "added — proof provided"
            else:
                mark = "added — proof REQUIRED"
                unproven.append(element)
            print(f"  member:   {element}  {mark}")
        if unproven:
            print(
                f"warning: added member(s) without a key custody proof: {', '.join(unproven)} — "
                "sign-submit refuses until every added member has a --proof-key-file",
                file=sys.stderr,
            )
    if args.parameter in FEE_PAYING_TARGET_PARAMETERS:
        for address in target_elements:
            _, target_balance = _fetch_account(args.rpc_url, chain_id, address)
            print(f"  target:   {address}  balance {target_balance} units")
            if target_balance < REQUIRED_BALANCE_UNITS:
                print(
                    f"warning: new {args.parameter} {address} cannot cover its own tx fees "
                    f"(balance {target_balance} < required {REQUIRED_BALANCE_UNITS}) — "
                    "sign-submit refuses unless funded or --allow-unfunded-target",
                    file=sys.stderr,
                )
    print(f"executor:   {executor}  (nonce {nonce}, balance {balance} units at read time — re-fetched on sign-submit)")
    if balance < REQUIRED_BALANCE_UNITS:
        print(
            f"warning: executor balance {balance} < required {REQUIRED_BALANCE_UNITS} units "
            f"(fee {DEFAULT_TX_FEE_UNITS} + headroom {FEE_HEADROOM_UNITS}) — sign-submit would refuse",
            file=sys.stderr,
        )
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

    nonce, balance = _fetch_account(args.rpc_url, chain_id, executor)
    _check_fee_balance("executor", executor, balance)

    # Custody guard for governance_executors: every member the new list adds
    # must come with a --proof-key-file deriving to it — the chain only gates
    # on a listed address, so an unproven entry could be a key nobody holds.
    # And a dropped signer must leave a proven survivor behind, or no held key
    # is left to ever sign a GOVERNANCE_EXECUTE again.
    if args.parameter == "governance_executors":
        new_set = {e.lower() for e in target_elements}
        proven, _ = _proof_addresses(args.proof_key_file, target_elements)
        proven_set = {a.lower() for a in proven}
        added = [e for e in target_elements if e.lower() not in executors]
        unproven = [e for e in added if e.lower() not in proven_set]
        if unproven:
            _fail(
                f"new governance_executors member(s) without a key custody proof: {', '.join(unproven)} — "
                "pass --proof-key-file for every added address"
            )
        reason = _executor_lockout_reason(executor, target_elements, proven)
        if reason is not None:
            _fail(reason)
        for address in proven:
            _check_fee_balance("executor member", address, _fetch_account(args.rpc_url, chain_id, address)[1])
        if executor.lower() not in new_set:
            print(
                f"executor rotation: signing key {executor} leaves the set; "
                f"custody of surviving executor {', '.join(proven)} proven by --proof-key-file"
            )
        if added:
            print(f"new executor members with custody proven by --proof-key-file: {', '.join(added)}")

    # Funded-authority gate (FEE_PAYING_TARGET_PARAMETERS): the target pays
    # its own tx fees after the rotation, so an unfunded target silently
    # disables the capability. --allow-unfunded-target is the deliberate
    # escape hatch for intentionally parking a capability unfunded.
    if args.parameter in FEE_PAYING_TARGET_PARAMETERS:
        for address in target_elements:
            _, target_balance = _fetch_account(args.rpc_url, chain_id, address)
            if args.allow_unfunded_target:
                if target_balance < REQUIRED_BALANCE_UNITS:
                    print(
                        f"warning: --allow-unfunded-target — new {args.parameter} {address} "
                        f"balance {target_balance} < required {REQUIRED_BALANCE_UNITS} units",
                        file=sys.stderr,
                    )
            else:
                _check_fee_balance(f"new {args.parameter}", address, target_balance)

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
        p.add_argument(
            "--proof-key-file",
            action="append",
            default=[],
            metavar="PATH",
            help=(
                "Key file proving custody of a governance_executors member — repeat once per address the new "
                "list adds. sign-submit refuses unless every added member is proven, and a signing key dropped "
                "from the list additionally needs a proven survivor. On plan it only affects the member report."
            ),
        )

    plan = sub.add_parser("plan", help="Show the change and the unsigned transaction digest (no signing key)")
    add_common(plan)
    plan.set_defaults(func=cmd_plan)

    submit = sub.add_parser("sign-submit", help="Sign with --key-file and submit")
    add_common(submit)
    submit.add_argument("--key-file", required=True, help="File containing the executor's raw-hex private key (mode 600)")
    submit.add_argument("--confirm", action="store_true", help="Required — refuse without it")
    submit.add_argument(
        "--allow-unfunded-target",
        action="store_true",
        help=(
            "Deliberately rotate escrow_settlement_authority/bond_slash_authority to an address that "
            "cannot yet pay its own tx fees — the capability stays disabled until the address is funded"
        ),
    )
    submit.add_argument("--timeout", type=int, default=240, help="Seconds to wait for the seal (default 240)")
    submit.set_defaults(func=cmd_sign_submit)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
