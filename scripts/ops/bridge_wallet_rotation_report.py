#!/usr/bin/env python3
"""Rotation-aware bridge wallet reconcile — report only (BR-6/B13).

Reads the bridge ledger (mode=ro) plus an operator-supplied dump of every
Sepolia transaction that touched a configured bridge wallet, then reports
the wallet-by-wallet decomposition a single-wallet reconcile cannot see:
deposits ledger-expected on one wallet that landed on a historical one,
wallet-to-wallet sweeps (internal transfers), unledgered outbound sends,
and residual balances no ledger row explains.

    python scripts/ops/bridge_wallet_rotation_report.py \
        --ledger /var/lib/aitbc/data/bridge_deposits.db \
        --txs wallet_txs.json \
        --wallets 0x0936…,0x310d… \
        --current-wallet 0x310d…

``--txs`` names a JSON list of observed chain txs (produced by the
operator from a block explorer or a public RPC — this script never
reaches the network). One entry per tx that touches a listed wallet, in
either direction:

    {
      "tx_hash": "0x…",            # required
      "from": "0x…",               # required, sender
      "to": "0x…",                 # required, recipient
      "value_wei": "123",          # required, decimal string or int
      "status": 1,                 # optional; failed txs count gas only
      "gas_used": 21000,           # optional, for the gas term
      "gas_price_wei": "1000017"
    }

Wallet list: ``--wallets`` or ``BRIDGE_KNOWN_WALLETS`` (comma-separated),
every bridge wallet that ever held the payout float — the old
``0x0936…9B32`` and the current ``0x310d…8781``. The current payout
wallet comes from ``--current-wallet`` or ``BRIDGE_ETH_ADDRESS`` and is
always in the list. A send between two listed wallets is an *internal
transfer*, not a deficit.

Deposit attribution: ``eth_deposits.deposit_address`` names the wallet a
row's funds were meant for. Rows where it is NULL (pre-column rows are
never backfilled) are treated as the current wallet and reported
"address unknown". Releases are joined from ``eth_withdrawals`` by
``eth_tx_hash``; the release leg is attributed to the current wallet.

This is a report, not a corrector: it writes nothing to the chain,
nothing to ledger rows, and never touches another node's wallet. Every
unmatched inflow or outflow is reported "unexplained, needs operator
note". Exit 1 when any item needs a note (so a scheduler can alert on
it), 0 when every residual decomposes. Sepolia only.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path

WEI_PER_ETH = Decimal(10) ** 18


def _wei(value: object, field: str) -> int:
    try:
        wei = int(str(value))
    except (TypeError, ValueError) as exc:
        raise SystemExit(f"unparseable wei value {value!r} in {field}") from exc
    if wei < 0:
        raise SystemExit(f"negative wei value {value!r} in {field}")
    return wei


def _eth_to_wei(amount: object, field: str) -> int:
    try:
        return int((Decimal(str(amount)) * WEI_PER_ETH).to_integral_value())
    except (InvalidOperation, ValueError) as exc:
        raise SystemExit(f"unparseable amount_eth {amount!r} on {field}") from exc


def _norm(addr: object) -> str:
    """Lowercase, stripped, single leading ``0x`` removed — the ledger mixes
    hash conventions (eth_deposits bare, eth_withdrawals prefixed), so all
    hash/address compares go through this."""
    v = str(addr or "").strip().lower()
    return v[2:] if v.startswith("0x") else v


def _short(addr: str) -> str:
    return addr if len(addr) <= 16 else f"{addr[:6]}…{addr[-4:]}"


def _fmt_signed(wei: int) -> str:
    return f"+{wei}" if wei >= 0 else str(wei)


def _load_ledger(ledger: Path) -> dict:
    """Deposits, depositors and withdrawal hashes from the ledger (mode=ro).

    Tolerates a pre-B13 schema: a missing ``deposit_address`` column reads
    as NULL on every row, a missing ``eth_withdrawals`` table as empty.
    """
    con = sqlite3.connect(f"file:{ledger}?mode=ro", uri=True)
    try:
        cols = {r[1] for r in con.execute("PRAGMA table_info(eth_deposits)")}
        dep_addr_expr = "deposit_address" if "deposit_address" in cols else "NULL"
        # dep_addr_expr is one of two hardcoded literals above.
        deposits = [
            {
                "id": r[0],
                "tx_hash": r[1],
                "from_address": r[2],
                "amount_wei": _eth_to_wei(r[3], f"deposit {r[0]}"),
                "status": r[4],
                "deposit_address": r[5],
            }
            for r in con.execute(f"SELECT id, tx_hash, from_address, amount_eth, status, {dep_addr_expr} FROM eth_deposits")  # nosec
        ]
        depositors = {
            _norm(r[0]) for r in con.execute("SELECT DISTINCT from_address FROM eth_deposits WHERE from_address IS NOT NULL")
        }
        try:
            withdrawals = [
                {"eth_tx_hash": _norm(r[0]), "amount_wei": _eth_to_wei(r[1], f"withdrawal {r[0]}"), "status": r[2]}
                for r in con.execute(
                    "SELECT eth_tx_hash, amount_eth, status FROM eth_withdrawals WHERE eth_tx_hash IS NOT NULL"
                )
            ]
        except sqlite3.OperationalError:
            withdrawals = []
        # Sell-flow releases: the payout leg's ETH hash is recorded on the
        # sell lock or the exchange settlement, not in eth_withdrawals —
        # without these joins every sell release flags as unexplained.
        # Both tables may be absent on a pre-ETH-8 ledger.
        sell_releases: list[dict] = []
        for table in ("bridge_sell_locks", "exchange_settlements"):
            try:
                sell_releases += [
                    {
                        "eth_tx_hash": _norm(r[0]),
                        "amount_wei": _eth_to_wei(r[1], f"{table} {r[0]}"),
                        "status": r[2],
                        "source": table,
                    }
                    for r in con.execute(
                        f"SELECT eth_tx_hash, eth_amount, status FROM {table} WHERE eth_tx_hash IS NOT NULL"  # nosec
                    )
                ]
            except sqlite3.OperationalError:
                continue
    finally:
        con.close()
    return {"deposits": deposits, "depositors": depositors, "withdrawals": withdrawals, "sell_releases": sell_releases}


class _Book:
    """One wallet's ledger-vs-chain terms."""

    def __init__(self, address: str, is_current: bool) -> None:
        self.address = address
        self.is_current = is_current
        self.expected_in = 0  # deposits attributed to this wallet
        self.expected_out = 0  # releases the ledger says it sent
        self.observed_in = 0  # chain inflows to it (value only)
        self.observed_out = 0  # chain outflows from it (value only)
        self.gas = 0  # gas burned by its outbound txs
        self.deposit_rows = 0
        self.address_unknown: list[dict] = []
        self.components: list[tuple[int, str]] = []
        self.flags: list[str] = []

    @property
    def expected(self) -> int:
        return self.expected_in - self.expected_out

    @property
    def observed(self) -> int:
        return self.observed_in - self.observed_out

    @property
    def residual(self) -> int:
        return self.observed - self.expected


def _attribute_ledger(deposits: list[dict], withdrawals: list[dict], books: dict[str, _Book], current: str) -> None:
    """Ledger expectation: deposits attribute to their deposit_address
    (NULL -> current wallet, reported "address unknown"); releases are
    the payout wallet's business and attribute to current."""
    for d in deposits:
        addr = _norm(d["deposit_address"]) or current
        book = books.get(addr)
        if book is None:  # row names a wallet outside the configured list
            book = books[current]
            book.flags.append(
                f"deposit {d['id']} names unlisted wallet {_norm(d['deposit_address'])} — attributed to current for this report — needs operator note"
            )
        book.expected_in += d["amount_wei"]
        book.deposit_rows += 1
        if not d["deposit_address"]:
            book.address_unknown.append(d)
    for w in withdrawals:
        books[current].expected_out += w["amount_wei"]


def _inbound(book: _Book, tx: dict, value: int, sender: str, deposit_by_hash: dict[str, dict]) -> None:
    book.observed_in += value
    # A tx matching a deposit row is a deposit arrival; its residual
    # component is written in the deposit pass (_deposit_components).
    if _norm(tx["tx_hash"]) in deposit_by_hash:
        return
    book.components.append((value, "arrived-unexpected — unexplained inflow"))
    book.flags.append(f"unexplained inflow {tx['tx_hash']}: {value} wei from {sender} — needs operator note")


def _outbound(
    book: _Book,
    tx: dict,
    value: int,
    dest: str,
    withdrawal_by_hash: dict[str, dict],
    depositors: set[str],
    funding: set[str],
    sell_release_by_hash: dict[str, dict] | None = None,
) -> None:
    book.observed_out += value
    w = withdrawal_by_hash.get(_norm(tx["tx_hash"]))
    if w is None and sell_release_by_hash:
        w = sell_release_by_hash.get(_norm(tx["tx_hash"]))
    if w is not None:
        if not book.is_current:
            book.flags.append(f"ledgered release {tx['tx_hash']} observed from non-current wallet — needs operator note")
        delta = w["amount_wei"] - value
        if delta:
            book.components.append((delta, "release amount delta (ledger vs chain)"))
            book.flags.append(
                f"release {tx['tx_hash']} value {value} wei != ledger amount {w['amount_wei']} wei — needs operator note"
            )
    elif dest in depositors or dest in funding:
        book.components.append((-value, f"unledgered outflow — refund to depositor {_short(dest)}"))
        book.flags.append(f"unledgered outflow {tx['tx_hash']}: {value} wei to depositor {_short(dest)} — needs operator note")
    else:
        book.components.append((-value, "unexplained outflow"))
        book.flags.append(f"unexplained outflow {tx['tx_hash']}: {value} wei to {_short(dest)} — needs operator note")


def _classify_tx(
    i: int,
    tx: dict,
    books: dict[str, _Book],
    deposit_by_hash: dict[str, dict],
    withdrawal_by_hash: dict[str, dict],
    depositors: set[str],
    funding: set[str],
    transfers: list[dict],
    sell_release_by_hash: dict[str, dict] | None = None,
) -> None:
    if not isinstance(tx, dict) or not tx.get("tx_hash") or not tx.get("to") or not tx.get("from"):
        raise SystemExit(f"txs[{i}]: missing tx_hash, from or to")
    value = _wei(tx.get("value_wei", 0), f"txs[{i}].value_wei")
    sender = _norm(tx["from"])
    dest = _norm(tx["to"])

    if sender in books:
        gas_used, gas_price = tx.get("gas_used"), tx.get("gas_price_wei")
        if gas_used is not None and gas_price is not None:
            books[sender].gas += _wei(gas_used, f"txs[{i}].gas_used") * _wei(gas_price, f"txs[{i}].gas_price_wei")
    if tx.get("status") in (0, "0", "failed") or value == 0:
        return  # a failed send moves no value; gas already counted

    if sender in books and dest in books:
        books[sender].observed_out += value
        books[dest].observed_in += value
        transfers.append({"tx_hash": tx["tx_hash"], "from": sender, "to": dest, "value_wei": value})
        books[sender].components.append((-value, f"internal transfer to {books[dest].address}"))
        books[dest].components.append((value, f"internal transfer from {books[sender].address}"))
        return
    if dest in books:
        _inbound(books[dest], tx, value, sender, deposit_by_hash)
    if sender in books:
        _outbound(books[sender], tx, value, dest, withdrawal_by_hash, depositors, funding, sell_release_by_hash)


def _deposit_components(deposits: list[dict], books: dict[str, _Book], dump_by_hash: dict[str, dict], current: str) -> None:
    """Every row's expected wallet vs where the chain says it landed.
    Arrived-on-attributed rows cancel out of the residual; the rest are
    its decomposition."""
    for d in deposits:
        addr = _norm(d["deposit_address"]) or current
        book = books.get(addr) or books[current]
        tx = dump_by_hash.get(_norm(d["tx_hash"]))
        if tx is None:
            book.components.append((-d["amount_wei"], "expected-never-arrived — no chain tx in dump"))
            book.flags.append(f"deposit {d['id']} ({d['tx_hash']}): ledger row has no chain tx in dump — needs operator note")
            continue
        dest = _norm(tx["to"])
        if tx.get("status") in (0, "0", "failed"):
            book.components.append((-d["amount_wei"], "expected-never-arrived — chain tx failed"))
            book.flags.append(f"deposit {d['id']} ({d['tx_hash']}): chain tx failed — needs operator note")
        elif dest == addr:
            pass  # arrived where the ledger expected — cancels
        elif dest in books:
            book.components.append((-d["amount_wei"], f"expected-never-arrived — landed on {books[dest].address}"))
            books[dest].components.append((d["amount_wei"], f"inflow attributed to {book.address}"))
        else:
            book.components.append((-d["amount_wei"], f"expected-never-arrived — landed off-list on {_short(dest)}"))
            book.flags.append(f"deposit {d['id']} ({d['tx_hash']}): landed off-list on {_short(dest)} — needs operator note")


def _collect_flags(books: dict[str, _Book], dust_wei: int) -> list[str]:
    flags: list[str] = []
    for book in books.values():
        flags.extend(book.flags)
        undiag = book.residual - sum(delta for delta, _ in book.components)
        if abs(undiag) > dust_wei:
            flags.append(f"{book.address}: residual under-decomposed by {undiag} wei — unexplained, needs operator note")
        if not book.is_current and abs(book.residual) > dust_wei:
            flags.append(f"{book.address}: retains {_fmt_signed(book.residual)} wei — unexplained, needs operator note")
    return flags


def analyze(
    txs: list[dict],
    deposits: list[dict],
    depositors: set[str],
    withdrawals: list[dict],
    funding: set[str],
    wallets: dict[str, str],
    current: str,
    sell_releases: list[dict] | None = None,
    dust_wei: int = 0,
) -> tuple[dict[str, _Book], list[dict], list[str]]:
    """Attribute every ledger row and chain tx to a wallet, then decompose
    each wallet's residual. ``wallets`` maps lowercase address -> display
    form and must contain ``current``. Returns ``(books, internal_transfers, flags)``.
    """
    current = _norm(current)
    depositors = {_norm(d) for d in depositors}
    funding = {_norm(f) for f in funding}
    books = {_norm(addr): _Book(display, _norm(addr) == current) for addr, display in wallets.items()}
    _attribute_ledger(deposits, withdrawals, books, current)

    deposit_by_hash = {_norm(d["tx_hash"]): d for d in deposits}
    withdrawal_by_hash = {w["eth_tx_hash"]: w for w in withdrawals}
    sell_release_by_hash = {w["eth_tx_hash"]: w for w in (sell_releases or [])}
    dump_by_hash = {_norm(t.get("tx_hash")): t for t in txs if isinstance(t, dict)}
    transfers: list[dict] = []
    for i, tx in enumerate(txs):
        _classify_tx(i, tx, books, deposit_by_hash, withdrawal_by_hash, depositors, funding, transfers, sell_release_by_hash)
    _deposit_components(deposits, books, dump_by_hash, current)
    return books, transfers, _collect_flags(books, dust_wei)


def _parse_wallets(arg: str | None, current: str) -> dict[str, str]:
    raw = arg if arg is not None else os.getenv("BRIDGE_KNOWN_WALLETS", "")
    out: dict[str, str] = {}
    for addr in (a.strip() for a in raw.split(",") if a.strip()):
        if not (addr.startswith("0x") and len(addr) == 42):
            raise SystemExit(f"not an address in wallet list: {addr!r}")
        out[addr.lower()] = addr
    out.setdefault(current.lower(), current)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--ledger", required=True, type=Path, help="bridge ledger sqlite (opened read-only)")
    parser.add_argument("--txs", required=True, type=Path, help="JSON dump of every chain tx touching a listed wallet")
    parser.add_argument("--wallets", help="comma-separated historical+current wallets (default: BRIDGE_KNOWN_WALLETS)")
    parser.add_argument("--current-wallet", help="current payout wallet (default: BRIDGE_ETH_ADDRESS)")
    parser.add_argument("--funding-json", type=Path, help="JSON list of funding-source addresses")
    parser.add_argument("--dust-wei", type=int, default=0, help="residual tolerance in wei (default 0)")
    args = parser.parse_args(argv)

    current = args.current_wallet or os.getenv("BRIDGE_ETH_ADDRESS", "")
    if not (current.startswith("0x") and len(current) == 42):
        raise SystemExit("current payout wallet required: --current-wallet or BRIDGE_ETH_ADDRESS")
    wallets = _parse_wallets(args.wallets, current)

    txs = json.loads(args.txs.read_text(encoding="utf-8"))
    if not isinstance(txs, list):
        raise SystemExit("--txs must be a JSON list")
    funding = {_norm(a) for a in json.loads(args.funding_json.read_text())} if args.funding_json else set()
    ledger = _load_ledger(args.ledger)

    books, transfers, flags = analyze(
        txs,
        ledger["deposits"],
        ledger["depositors"],
        ledger["withdrawals"],
        funding,
        wallets,
        _norm(current),
        sell_releases=ledger["sell_releases"],
        dust_wei=args.dust_wei,
    )
    return _print_report(books, transfers, flags, dust_wei=args.dust_wei)


def _print_book(book: _Book, dust_wei: int) -> None:
    role = "current" if book.is_current else "historical"
    print(f"wallet {book.address} ({role})")
    print("-" * 70)
    print("  ledger expectation")
    print(f"    deposits attributed {book.deposit_rows:>4} row(s) {book.expected_in:>24} wei")
    if book.address_unknown:
        print(f'      ({len(book.address_unknown)} row(s) deposit_address NULL — "address unknown", treated as this wallet)')
    if book.expected_out:
        print(f"    releases (eth_withdrawals)      {book.expected_out:>24} wei")
    print(f"    expected balance                {book.expected:>24} wei")
    print("  chain-observed")
    print(f"    inbound value                   {book.observed_in:>24} wei")
    print(f"    outbound value                  {book.observed_out:>24} wei")
    print(f"    gas spent                       {book.gas:>24} wei (excluded from residual)")
    unexplained_note = ""
    if not book.is_current and abs(book.residual) > dust_wei:
        unexplained_note = " — unexplained, needs operator note"
    print(f"  residual (observed - expected)    {_fmt_signed(book.residual):>24} wei{unexplained_note}")
    print("  decomposition")
    for delta, label in book.components:
        print(f"    {_fmt_signed(delta):>24}  {label}")
    undiag = book.residual - sum(d for d, _ in book.components)
    if abs(undiag) > dust_wei:
        print(f"    {_fmt_signed(undiag):>24}  under-decomposed — unexplained, needs operator note")
    elif not book.is_current and abs(book.residual) > dust_wei:
        print(f"    {'':>24}  residual retained on a wallet the ledger does not attribute funds to")
    else:
        print(f"    {'':>24}  fully decomposed — no unexplained remainder")
    print()


def _print_report(books: dict[str, _Book], transfers: list[dict], flags: list[str], dust_wei: int = 0) -> int:
    print("BRIDGE WALLET ROTATION RECONCILE (BR-6/B13) — report only")
    print("=" * 70)
    ordered = sorted(books.values(), key=lambda b: not b.is_current)
    print("wallets: " + ", ".join(f"{b.address} ({'current' if b.is_current else 'historical'})" for b in ordered))
    print("NOTE: writes nothing. Unmatched terms are reported")
    print('"unexplained, needs operator note" — never corrected.')
    print()
    for book in ordered:
        _print_book(book, dust_wei)
    if transfers:
        print("internal transfers (wallet-to-wallet — not deficits)")
        print("-" * 70)
        for t in transfers:
            print(f"  {t['tx_hash']}  {t['value_wei']:>24} wei  {_short(t['from'])} -> {_short(t['to'])}")
        print()
    if flags:
        print("items needing an operator note")
        print("-" * 70)
        for f in flags:
            print(f"  {f}")
        print(f"SUMMARY: {len(flags)} item(s) need an operator note")
        return 1
    print("SUMMARY: no unexplained items")
    return 0


if __name__ == "__main__":
    sys.exit(main())
