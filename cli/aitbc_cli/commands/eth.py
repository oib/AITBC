"""Ethereum (Sepolia) inspection commands — read-only and key-free.

Only Sepolia (chainId 11155111) is supported until the v1 mainnet
switch. These commands never touch wallet files, keys, env files, or
the bridge ledger; all data comes from a public block explorer and a
public JSON-RPC endpoint.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from pathlib import Path

import click

from ..utils import error, info, warning
from ..utils.evm_rpc import display_rpc_url, mask_rpc_url

SEPOLIA_CHAIN_ID = 11155111
DEFAULT_RPC_URL = "https://ethereum-sepolia-rpc.publicnode.com"
DEFAULT_EXPLORER_URL = "https://eth-sepolia.blockscout.com"
DEFAULT_LOG_PATH = "~/.aitbc/eth-transfers.jsonl"
USER_AGENT = "aitbc-cli/0.25 (+read-only; https://github.com/oib/AITBC)"
WEI_PER_ETH = 10**18

MAX_PAGES = 50
RETRIES = 3
BACKOFF_S = 0.5

# label -> address. This is the single source of truth for the wallet
# label table; docs/ops/node-sepolia-wallets.md mirrors it.
DEFAULT_WALLETS: list[tuple[str, str]] = [
    ("bridge", "0x310dcE00270D0aC10CAccfBD636Ff07BD5648781"),
    ("bridge-old", "0x09362894C18f7CbCdb85b124ef4c8F63DEC09B32"),
    ("hub", "0xA556E23897ea7FF5f0ED0F925f5eB2e68D7EC74C"),
    ("hub1", "0x86FAA186474DC63d77ECcDBE242084a04F45101C"),
    ("node0", "0xF1C83cd90e4d33F35BE73Dd57CaBa21Ea52D4584"),
    ("node1", "0xFdE0fBa0098645d20D64e3D7f87F2fcf3f4754c1"),
    ("node2", "0xCf1719140054AB3fD52ce8aa3128dec9317426E3"),
]

_RETRYABLE_HTTP = {403, 429, 500, 502, 503, 504}


class ExplorerError(RuntimeError):
    """Raised when the explorer or RPC endpoint cannot be reached."""


def _check_url(url: str) -> None:
    if not url.lower().startswith(("https://", "http://")):
        raise ExplorerError(f"refusing non-http(s) URL: {url}")


def _http_json(url: str) -> object:
    """GET JSON with a User-Agent (keyless explorers 403 without one) and
    bounded retry/backoff on 403/429/5xx."""
    _check_url(url)
    delay = BACKOFF_S
    last: Exception | None = None
    for attempt in range(RETRIES):
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:  # nosec B310 - https-only public explorer
                return json.load(resp)
        except urllib.error.HTTPError as exc:
            last = ExplorerError(f"HTTP {exc.code} for {url}")
            if exc.code in _RETRYABLE_HTTP and attempt < RETRIES - 1:
                time.sleep(delay)
                delay *= 2
                continue
            raise last from exc
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            last = ExplorerError(f"cannot reach {url}: {exc}")
            if attempt < RETRIES - 1:
                time.sleep(delay)
                delay *= 2
                continue
            raise last from exc
    raise last if last else ExplorerError(f"failed fetching {url}")


def _rpc(rpc_url: str, method: str, params: list[object]) -> object:
    _check_url(rpc_url)
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    req = urllib.request.Request(rpc_url, data=body, headers={"Content-Type": "application/json", "User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:  # nosec B310 - https-only public RPC
            payload = json.load(resp)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
        raise ExplorerError(
            f"RPC {method} failed against {display_rpc_url(rpc_url)}: {mask_rpc_url(str(exc), rpc_url)}"
        ) from exc
    if payload.get("error"):
        raise ExplorerError(f"RPC {method} error: {mask_rpc_url(str(payload['error']), rpc_url)}")
    return payload["result"]


def _verify_sepolia(rpc_url: str) -> None:
    chain_id = int(str(_rpc(rpc_url, "eth_chainId", [])), 16)
    if chain_id != SEPOLIA_CHAIN_ID:
        raise ExplorerError(
            f"refusing non-Sepolia network: {display_rpc_url(rpc_url)} reports chainId {chain_id} "
            f"(only {SEPOLIA_CHAIN_ID} is allowed)"
        )


def _explorer_page(explorer_url: str, path: str, extra: str = "") -> tuple[list[dict], str | None]:
    data = _http_json(f"{explorer_url.rstrip('/')}/api/v2/{path}{extra}")
    if not isinstance(data, dict) or "items" not in data:
        raise ExplorerError(f"unexpected explorer response for {path}")
    params = data.get("next_page_params")
    if not params:
        return data["items"], None
    qs = "&".join(f"{k}={v}" for k, v in params.items() if v is not None)
    return data["items"], qs


def fetch_transfers(explorer_url: str, path: str) -> list[dict]:
    """Follow next_page_params over an /api/v2/addresses/ endpoint."""
    items: list[dict] = []
    qs: str | None = ""
    for _ in range(MAX_PAGES):
        page, qs = _explorer_page(explorer_url, path, "&" + qs if qs else "")
        items += page
        if not qs:
            return items
    raise ExplorerError(f"pagination did not converge after {MAX_PAGES} pages for {path}")


def _norm_status(value: object) -> str:
    if value in ("ok", 1, "1", "success"):
        return "success"
    if value in ("error", 0, "0", "failed"):
        return "failed"
    return str(value or "unknown")


def _row(
    label: str,
    address: str,
    direction: str,
    tx_hash: str,
    block: object,
    timestamp: str,
    frm: str,
    to: str | None,
    value_wei: int,
    gas_fee_wei: int | None,
    status: str,
    method: str,
    internal: bool,
) -> dict:
    return {
        "label": label,
        "address": address,
        "direction": direction,
        "tx_hash": tx_hash,
        "block": int(str(block)) if block is not None else None,
        "timestamp": timestamp,
        "from": frm,
        "to": to,
        "value_wei": str(value_wei),
        "gas_fee_wei": str(gas_fee_wei) if gas_fee_wei is not None else None,
        "status": status,
        "method": method,
        "internal": internal,
    }


def normalize_address_txs(label: str, address: str, txs: list[dict]) -> list[dict]:
    """Blockscout transaction objects -> log rows for one wallet."""
    rows = []
    a = address.lower()
    for t in txs:
        frm = ((t.get("from") or {}).get("hash") or "").lower()
        to_obj = t.get("to") or {}
        to = (to_obj.get("hash") or "").lower() or None
        created = (t.get("created_contract") or {}).get("hash")
        if not to and created:
            to = created.lower()
        if frm == a and to == a:
            direction = "self"
        elif frm == a:
            direction = "out"
        else:
            direction = "in"
        gas_used = t.get("gas_used")
        gas_price = t.get("gas_price")
        gas_fee = int(gas_used) * int(gas_price) if (direction in ("out", "self") and gas_used and gas_price) else None
        method = t.get("method") or ("contract_creation" if to_obj.get("hash") is None and created else "transfer")
        rows.append(
            _row(
                label,
                address,
                direction,
                t["hash"],
                t.get("block_number"),
                t.get("timestamp") or "",
                frm,
                to,
                int(t.get("value") or 0),
                gas_fee,
                _norm_status(t.get("status")),
                method,
                False,
            )
        )
    return rows


def normalize_internal_txs(label: str, address: str, items: list[dict]) -> list[dict]:
    rows = []
    a = address.lower()
    for i, t in enumerate(items):
        frm = ((t.get("from") or {}).get("hash") or "").lower()
        to = ((t.get("to") or {}).get("hash") or "").lower() or None
        if frm != a and to != a:
            continue
        direction = "self" if frm == a and to == a else ("out" if frm == a else "in")
        idx = t.get("index", t.get("trace_id", i))
        row = _row(
            label,
            address,
            direction,
            t.get("transaction_hash") or t.get("tx_hash") or "",
            t.get("block"),
            t.get("timestamp") or "",
            frm,
            to,
            int(t.get("value") or 0),
            None,
            _norm_status(t.get("status") or ("success" if t.get("success", True) else "failed")),
            str(t.get("type") or "internal"),
            True,
        )
        row["log_index"] = str(idx)
        rows.append(row)
    return rows


def row_key(row: dict) -> tuple[str, str, str]:
    return (row["address"].lower(), row["tx_hash"].lower(), f"int:{row.get('log_index')}" if row["internal"] else "ext")


def _parse_since(since: str) -> tuple[str, object]:
    """--since: digits -> minimum block; YYYY-MM-DD -> UTC timestamp cutoff."""
    since = since.strip()
    if since.isdigit():
        return ("block", int(since))
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            import datetime as _dt

            dt = _dt.datetime.strptime(since, fmt).replace(tzinfo=_dt.UTC)
            return ("timestamp", dt.isoformat())
        except ValueError:
            continue
    raise click.BadParameter(f"--since must be a block number or a date (YYYY-MM-DD[THH:MM:SS]), got {since!r}")


def _apply_since(rows: list[dict], kind: str, cutoff: object) -> list[dict]:
    if kind == "block":
        return [r for r in rows if r["block"] is None or int(str(r["block"])) >= int(str(cutoff))]
    return [r for r in rows if str(r["timestamp"]) >= str(cutoff)]


def _load_log_keys(path: Path) -> set[tuple[str, str, str]]:
    keys: set[tuple[str, str, str]] = set()
    if not path.exists():
        return keys
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            keys.add(row_key(json.loads(line)))
        except (json.JSONDecodeError, KeyError):
            continue
    return keys


def _fmt_eth(wei: object) -> str:
    v = int(str(wei))
    short = f"{v / WEI_PER_ETH:.6f}".rstrip("0").rstrip(".")
    if short in ("", "0") and v != 0:
        return f"{v / WEI_PER_ETH:.12f}".rstrip("0")  # dust: keep sub-micro precision
    return short or "0"


def _resolve_targets(wanted: list[str]) -> list[tuple[str, str]]:
    """Positional/--address args → (label, address); empty → the default set."""
    labels = {a.lower(): lbl for lbl, a in DEFAULT_WALLETS}
    label_of = {lbl: a.lower() for lbl, a in DEFAULT_WALLETS}
    if not wanted:
        return list(DEFAULT_WALLETS)
    targets = []
    for w in wanted:
        wl = w.lower()
        if wl in label_of:
            targets.append((wl, label_of[wl]))
        elif wl.startswith("0x"):
            targets.append((labels.get(wl, wl[:10]), wl))
        else:
            error(f"unknown wallet label or address: {w!r} — labels: {', '.join(sorted(label_of))}")
            raise SystemExit(2)
    return targets


def _wallet_report(label: str, addr: str, explorer_url: str, rpc_url: str) -> tuple[list[dict], int, int] | None:
    """Fetch + normalize one wallet; returns (rows, nonce, balance_wei) or None on fetch failure."""
    try:
        # Blockscout's transactions endpoint accepts a single direction
        # per filter; fetch both and merge by hash (self-sends appear twice).
        raw: dict[str, dict] = {}
        for direction in ("to", "from"):
            for t in fetch_transfers(explorer_url, f"addresses/{addr}/transactions?filter={direction}"):
                raw[t["hash"]] = t
        internal = fetch_transfers(explorer_url, f"addresses/{addr}/internal-transactions")
        nonce = int(str(_rpc(rpc_url, "eth_getTransactionCount", [addr, "latest"])), 16)
        balance = int(str(_rpc(rpc_url, "eth_getBalance", [addr, "latest"])), 16)
    except ExplorerError as e:
        error(f"{label}: {e}")
        return None
    rows = normalize_address_txs(label, addr, list(raw.values())) + normalize_internal_txs(label, addr, internal)
    return rows, nonce, balance


def _summary(label: str, addr: str, rows: list[dict], fresh_count: int, balance: int) -> dict:
    in_v = sum(int(r["value_wei"]) for r in rows if r["direction"] in ("in", "self") and r["status"] == "success")
    out_v = sum(int(r["value_wei"]) for r in rows if r["direction"] in ("out", "self") and r["status"] == "success")
    gas_v = sum(int(r["gas_fee_wei"] or 0) for r in rows if not r["internal"])
    net = in_v - out_v - gas_v
    return {
        "label": label,
        "address": addr,
        "rows": len(rows),
        "new": fresh_count,
        "in_wei": in_v,
        "out_wei": out_v,
        "gas_wei": gas_v,
        "net_wei": net,
        "balance_wei": balance,
        "net_matches_balance": net == balance,
    }


def _append_log(log_file: Path, new_rows: list[dict], no_log: bool) -> None:
    if no_log or not new_rows:
        return
    log_file.parent.mkdir(parents=True, exist_ok=True)
    with log_file.open("a", encoding="utf-8") as fh:
        for r in new_rows:
            fh.write(json.dumps(r, sort_keys=True) + "\n")


def _print_result(
    new_rows: list[dict], summaries: list[dict], as_json: bool, log_file: Path, no_log: bool, seen_count: int
) -> None:
    if as_json:
        click.echo(json.dumps(new_rows, indent=2))
        return
    for r in sorted(new_rows, key=lambda x: (x["address"], x["block"] or 0, x["tx_hash"])):
        cp = r["to"] if r["direction"] == "out" else r["from"]
        direction = "self" if r["direction"] == "self" else (" >>" if r["direction"] == "out" else " <<")
        click.echo(
            f"{r['label']:<10} {direction:>4} {r['block'] or '-':>8} {r['timestamp'][:16]:<17}"
            f"{_fmt_eth(r['value_wei']):>12} ETH {r['status']:<8}{r['method'] or '':<20}"
            f"{cp or '-':<44}{'int' if r['internal'] else ''} {r['tx_hash'][:14]}"
        )
    click.echo()
    click.echo(
        f"{'wallet':<10}{'in ETH':>12}{'out ETH':>12}{'gas ETH':>12}{'net ETH':>13}"
        f"{'balance ETH':>13}{'net=bal':>9}{'rows':>6}{'new':>5}"
    )
    for s in summaries:
        click.echo(
            f"{s['label']:<10}{_fmt_eth(s['in_wei']):>12}{_fmt_eth(s['out_wei']):>12}"
            f"{_fmt_eth(s['gas_wei']):>12}{_fmt_eth(s['net_wei']):>13}{_fmt_eth(s['balance_wei']):>13}"
            f"{'yes' if s['net_matches_balance'] else 'NO':>9}{s['rows']:>6}{s['new']:>5}"
        )
    if not no_log:
        info(f"log: {log_file} (+{len(new_rows)} rows, {seen_count} known)")


@click.group(
    epilog="""Examples:

  aitbc eth transfers

  aitbc eth transfers --since 2026-10-01 --no-log"""
)
def eth():
    """Inspect public Sepolia ETH activity — read-only, key-free, no polling."""
    pass


@eth.command(
    epilog="""Examples:

  aitbc eth transfers

  aitbc eth transfers 0x310dcE00270D0aC10CAccfBD636Ff07BD5648781

  aitbc eth transfers --address bridge --since 11860000 --json

  aitbc eth transfers --no-log --since 2026-10-01"""
)
@click.argument("addresses", nargs=-1)
@click.option("--address", "-a", multiple=True, help="Address or wallet label (repeatable)")
@click.option("--since", default=None, help="Only rows at/after this block number or UTC date (YYYY-MM-DD)")
@click.option("--json", "as_json", is_flag=True, help="Emit the new rows as JSON")
@click.option(
    "--log",
    "log_path",
    default=DEFAULT_LOG_PATH,
    show_default=True,
    type=click.Path(dir_okay=False, writable=True),
    help="JSONL transfer log",
)
@click.option("--no-log", is_flag=True, help="Print only; do not read or write the log")
@click.option("--rpc-url", default=DEFAULT_RPC_URL, show_default=True, help="Sepolia JSON-RPC endpoint")
@click.option(
    "--explorer-url", default=DEFAULT_EXPLORER_URL, show_default=True, help="Blockscout-compatible explorer base URL"
)
def transfers(
    addresses: tuple[str, ...],
    address: tuple[str, ...],
    since: str | None,
    as_json: bool,
    log_path: str,
    no_log: bool,
    rpc_url: str,
    explorer_url: str,
):
    """Fetch ETH transfers for the fleet's Sepolia wallets and append new rows to a JSONL log.

    Read-only and key-free: no wallet file, key, env file, ledger or
    database is touched. On a second run only rows not yet in the log
    are appended. Every wallet's outgoing transaction count is
    cross-checked against its RPC nonce; a mismatch warns and exits
    non-zero.
    """
    targets = _resolve_targets(list(addresses) + list(address))
    try:
        _verify_sepolia(rpc_url)
    except ExplorerError as e:
        error(str(e))
        raise SystemExit(2) from e

    since_filter = _parse_since(since) if since else None
    log_file = Path(log_path).expanduser()
    seen = set() if no_log else _load_log_keys(log_file)
    new_rows: list[dict] = []
    summaries = []
    rc = 0

    for label, addr in targets:
        report = _wallet_report(label, addr, explorer_url, rpc_url)
        if report is None:
            rc = 1
            continue
        rows, nonce, balance = report

        # The nonce check and net=balance math always use the full
        # history; --since only narrows which rows get listed/logged.
        out_count = sum(1 for r in rows if r["direction"] in ("out", "self") and not r["internal"])
        if out_count != nonce:
            warning(f"{label}: explorer shows {out_count} outgoing transactions but RPC nonce is {nonce}")
            rc = 1
        listed = _apply_since(rows, *since_filter) if since_filter else rows
        fresh = [r for r in listed if row_key(r) not in seen]
        new_rows += fresh
        seen.update(row_key(r) for r in fresh)
        summaries.append(_summary(label, addr, rows, len(fresh), balance))

    _append_log(log_file, new_rows, no_log)
    _print_result(new_rows, summaries, as_json, log_file, no_log, len(seen))

    if rc:
        warning("one or more wallets failed the nonce cross-check — log was still written for consistent rows")
    raise SystemExit(rc)
