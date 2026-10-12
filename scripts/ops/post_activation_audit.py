#!/usr/bin/env python3
"""Post-activation audit for the shared v14/v13 rung (ACT-1, height 46,100).

Independent cross-check of the bridge/consensus side after the shared
activation fires. Read-only by construction:

- all RPC reads go through ``ssh <host> curl 127.0.0.1:8202`` — the node RPC
  binds localhost only, so nothing is reachable from outside and nothing is
  written;
- the chain.db recomputations run ON each host by piping this same file over
  ssh stdin in ``--local-db`` mode — SQLite ``mode=ro`` + ``PRAGMA
  query_only=ON`` (no ``immutable``: a live WAL database would serve a stale
  snapshot), niced, nothing installed;
- alert state is read from hub's ``/var/log/aitbc/alerts.log`` tail and
  Prometheus ``/api/v1/alerts``.

Checks (a–g per BR-12):

  a. block hash + parent hash for activation-2..H identical on all five
     hosts (H = lowest head), and the parent chain links correctly;
  b. ``block_metadata.state_transition_version`` is 14 for blocks >= H_act
     and lower before; block H_act is the first stamped 14;
  c. ``aux_state_root`` empty before H_act, non-empty and identical across
     hosts from H_act;
  d. ``bridge_state_root`` recomputed from the sealed BRIDGE_LOCK leaves
     (``lock:{transfer_id}:{amount}:{target_chain}`` keyed by tx_hash in a
     MerklePatriciaTrie — the exact V-4 derivation in poa.py /
     sync_block_import.py) equals the committed column, on hub and one
     follower;
  e. the active validator set (``/rpc/consensus/validators``,
     role=validator && is_active) equals the expected four on every host,
     and recent-block attesters are a subset;
  f. all five heads share hash/height (no fork), head age < ~4× the block
     interval, no firing Prometheus alert and no new ERROR/ALERT lines in
     hub's alerts.log tail;
  g. ``shadow_side_root`` fingerprints agree per shared height on all five
     hosts (the same comparison the ACT-1 soak used).

Statuses: PASS / FAIL / NOT-YET (activation window not sealed yet —
expected pre-H) / INFO (data reported without a verdict).

Usage (IDE host or anywhere with ssh access):

    python3 scripts/ops/post_activation_audit.py
    python3 scripts/ops/post_activation_audit.py --activation-height 46100 --window 12

Remote mode (invoked by the script itself over ssh, not for direct use):

    ... | venv/bin/python - --local-db /path/chain.db --mode shadow --limit 25
    ... | venv/bin/python - --local-db /path/chain.db --mode bridge-roots --from 46098 --to 46110
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import subprocess
import sys
import urllib.parse
from datetime import datetime, UTC
from pathlib import Path

HOSTS = ["hub", "hub1", "node0", "node1", "node2"]
RPC_PORT = 8202
RPC_TIMEOUT = 8
DEFAULT_ACTIVATION = 46_100
DEFAULT_WINDOW = 12
BLOCK_INTERVAL_S = 68.0
HEAD_AGE_LIMIT_S = 300.0  # ~4x the 68 s interval
CHAIN_DB = "/var/lib/aitbc/data/ait-hub.aitbc.bubuit.net/chain.db"
REMOTE_PREFIX = "cd /opt/aitbc && nice -n 19 env PYTHONPATH=apps/blockchain-node/src venv/bin/python -"
ALERT_LOG = "/var/log/aitbc/alerts.log"
PROM_ALERTS = "http://127.0.0.1:9090/api/v1/alerts"

# The live attester set (ACT-1 record + operator-provided): hub 0x2aD5,
# node2 0xE894, node1 0x19f0, hub1 0x5E8E. Compared on the first 6 chars
# (0x + 4 hex) so full addresses from the RPC still match.
EXPECTED_VALIDATORS = {"0x19f0", "0x2ad5", "0x5e8e", "0xe894"}

PASS, FAIL, NOT_YET, INFO = "PASS", "FAIL", "NOT-YET", "INFO"
_HASH_RE = re.compile(r"^0x?[0-9a-fA-F]{4,}$")


# --------------------------------------------------------------------------
# pure helpers (unit-tested, no IO)
# --------------------------------------------------------------------------


def short(value: object, n: int = 12) -> str:
    """First ``n`` hex chars of a hash-like value (keeps the 0x prefix)."""
    s = "" if value is None else str(value)
    if not s:
        return "(empty)"
    if s.startswith("0x"):
        return "0x" + s[2 : 2 + n]
    return s[:n]


def parse_block_meta(raw: object) -> dict:
    """``block.block_metadata`` may arrive as JSON text, a dict, or None."""
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            out = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return out if isinstance(out, dict) else {}
    return {}


def lock_leaf_value(tx_hash: str, record: dict | None) -> str:
    """The exact V-4 leaf string from poa._compute_bridge_state_root /
    sync_block_import._derive_bridge_state_root."""
    if record is None:
        return f"lock:{tx_hash}:0:unknown"
    return f"lock:{record['transfer_id']}:{record['amount']}:{record['target_chain']}"


def eval_version_window(rows: list[tuple[int, int | None]], activation: int, expected: int = 14) -> tuple[str, str]:
    """rows = (height, state_transition_version or None) sorted by height.

    PASS when every block >= activation is stamped ``expected``, every block
    below is stamped lower, and the first ``expected`` block is exactly the
    activation height. NOT-YET when no row reaches activation.
    """
    post = [(h, v) for h, v in rows if h >= activation]
    pre = [(h, v) for h, v in rows if h < activation]
    if not post:
        top = rows[-1][0] if rows else -1
        return NOT_YET, f"no sealed block >= {activation} (window top {top})"
    bad = [(h, v) for h, v in post if v != expected]
    if bad:
        return FAIL, f"blocks {bad[:3]} not stamped {expected}"
    first = min(h for h, _ in post)
    if first != activation:
        return FAIL, f"first v{expected} block is {first}, expected {activation}"
    early = [(h, v) for h, v in pre if v is not None and v >= expected]
    if early:
        return FAIL, f"pre-activation blocks {early[:3]} stamped >= {expected}"
    versions = sorted({v for _, v in post})
    prev = sorted({v for _, v in pre if v is not None})
    return PASS, f"{len(post)} blocks v{versions}; pre-H versions {prev or ['(none stamped)']}"


def _aux_problems(rows_by_host: dict[str, list[tuple[int, str | None]]], activation: int, post: list[int]) -> list[str]:
    problems = []
    for host, rows in rows_by_host.items():
        for h, aux in rows:
            if h < activation and aux not in (None, "", "0x"):
                problems.append(f"{host}@{h}: non-empty pre-H aux {short(aux)}")
    for h in post:
        vals = {host: dict(rows)[h] for host, rows in rows_by_host.items() if h in dict(rows)}
        if len(vals) < 2:
            continue
        if any(v in (None, "", "0x") for v in vals.values()):
            problems.append(f"height {h}: empty aux on {[k for k, v in vals.items() if v in (None, '', '0x')]}")
        elif len(set(vals.values())) > 1:
            problems.append(f"height {h}: aux differs across hosts ({[short(v) for v in vals.values()]})")
    return problems


def eval_aux_window(rows_by_host: dict[str, list[tuple[int, str | None]]], activation: int) -> tuple[str, str]:
    """rows_by_host[host] = (height, aux_state_root) pairs.

    PASS when aux is empty for all blocks < activation and non-empty +
    identical across hosts for every shared block >= activation.
    """
    all_heights = sorted({h for rows in rows_by_host.values() for h, _ in rows})
    post = [h for h in all_heights if h >= activation]
    if not post:
        return NOT_YET, f"no sealed block >= {activation} on any host"
    problems = _aux_problems(rows_by_host, activation, post)
    if problems:
        return FAIL, "; ".join(problems[:4])
    sample = next(
        (v for h in post for host, rows in rows_by_host.items() for hh, v in rows if hh == post[-1] and v),
        None,
    )
    return PASS, f"{len(post)} post-H heights identical; aux@{post[-1]} {short(sample)}"


def eval_attesters(found: set[str], expected: set[str] = EXPECTED_VALIDATORS) -> tuple[str, str]:
    """found = lowercase 0x+4 prefixes seen (validators + recent attesters)."""
    missing = expected - found
    extra = found - expected
    if missing or extra:
        return FAIL, f"missing {sorted(missing) or '[]'} unexpected {sorted(extra) or '[]'}"
    return PASS, f"active set == expected {sorted(expected)}"


def eval_head_rows(
    heads: dict[str, dict], now_ts: float, interval: float = BLOCK_INTERVAL_S, limit: float = HEAD_AGE_LIMIT_S
) -> tuple[str, str]:
    """heads[host] = /rpc/chain/head dict. PASS = same hash+height, youngest
    head age < ``limit`` seconds."""
    if not heads:
        return FAIL, "no head data from any host"
    sigs = {(h["height"], h["hash"]) for h in heads.values()}
    if len(sigs) > 1:
        return FAIL, f"head mismatch across hosts: {sorted(sigs)}"
    ((height, hhash),) = sigs
    try:
        ts = datetime.fromisoformat(str(heads[next(iter(heads))]["timestamp"]).replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=UTC)
        age = now_ts - ts.timestamp()
    except (KeyError, ValueError):
        age = None
    if age is None:
        return FAIL, f"unparseable head timestamp at {height}"
    if age > limit:
        return FAIL, f"head {height} is {age:.0f}s old (> {limit:.0f}s ~ {limit / interval:.1f} intervals)"
    return PASS, f"head {height} {short(hhash)} identical x{len(heads)}, age {age:.0f}s"


def consensus_mismatches(per_height: dict[int, dict[str, str]]) -> list[str]:
    """per_height[height][host] = fingerprint -> mismatched heights."""
    out = []
    for h, by_host in sorted(per_height.items()):
        vals = set(by_host.values())
        if len(vals) > 1:
            out.append(f"height {h}: {by_host}")
    return out


# --------------------------------------------------------------------------
# remote (--local-db) mode: runs ON a host, piped over ssh stdin
# --------------------------------------------------------------------------


def _ro_conn(db: str) -> sqlite3.Connection:
    uri = "file:" + urllib.parse.quote(db) + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.execute("PRAGMA query_only=ON")
    return conn


def _local_shadow(db: str, limit: int) -> None:
    conn = _ro_conn(db)
    try:
        rows = conn.execute(
            "SELECT block_height, fingerprint FROM shadow_side_root ORDER BY block_height DESC LIMIT ?",
            (limit,),
        ).fetchall()
    finally:
        conn.close()
    print(json.dumps({"mode": "shadow", "rows": [[h, f] for h, f in rows]}))


def _local_bridge_roots(db: str, first: int, last: int, lock_lookback: int) -> None:
    """Recompute block.bridge_state_root per the V-4 derivation for the
    sealed range [first,last] plus up to 3 lock-bearing blocks inside the
    lookback window. Emits one JSON object per block."""
    from aitbc_chain.state.merkle_patricia_trie import MerklePatriciaTrie  # noqa: PLC0415

    conn = _ro_conn(db)
    try:
        (chain_id,) = conn.execute("SELECT chain_id FROM block ORDER BY height DESC LIMIT 1").fetchone()
        heights = set(range(first, last + 1))
        extra = conn.execute(
            'SELECT DISTINCT t.block_height FROM "transaction" t '
            "WHERE t.chain_id = ? AND upper(t.type) = 'BRIDGE_LOCK' AND t.block_height <= ? "
            "ORDER BY t.block_height DESC LIMIT 3",
            (chain_id, last),
        ).fetchall()
        heights.update(h for (h,) in extra if h >= first - lock_lookback)
        out = []
        for height in sorted(heights):
            row = conn.execute(
                "SELECT bridge_state_root FROM block WHERE chain_id = ? AND height = ?", (chain_id, height)
            ).fetchone()
            if row is None:
                continue
            committed = row[0]
            lock_txs = conn.execute(
                "SELECT tx_hash FROM \"transaction\" WHERE chain_id = ? AND block_height = ? AND upper(type) = 'BRIDGE_LOCK'",
                (chain_id, height),
            ).fetchall()
            trie = MerklePatriciaTrie()
            ids = [t for (t,) in lock_txs]
            records = {}
            if ids:
                marks = ",".join("?" for _ in ids)
                for r in conn.execute(
                    f"SELECT transfer_id, amount, target_chain FROM cross_chain_transfer WHERE source_chain = ? AND transfer_id IN ({marks})",  # nosec B608 - placeholders only
                    (chain_id, *ids),
                ).fetchall():
                    records[r[0]] = {"transfer_id": r[0], "amount": r[1], "target_chain": r[2]}
            for tx_hash in ids:
                trie.put(tx_hash.encode(), lock_leaf_value(tx_hash, records.get(tx_hash)).encode())
            recomputed = "0x" + trie.get_root().hex()
            out.append(
                {
                    "height": height,
                    "locks": len(ids),
                    "committed": short(committed),
                    "recomputed": short(recomputed),
                    "match": (committed or "") == recomputed,
                }
            )
    finally:
        conn.close()
    print(json.dumps({"mode": "bridge-roots", "rows": out}))


def _remote_main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="post_activation_audit --local-db")
    p.add_argument("--local-db", required=True)
    p.add_argument("--mode", choices=["shadow", "bridge-roots"], required=True)
    p.add_argument("--limit", type=int, default=25)
    p.add_argument("--from", dest="first", type=int, default=0)
    p.add_argument("--to", dest="last", type=int, default=0)
    p.add_argument("--lock-lookback", type=int, default=20_000)
    a = p.parse_args(argv)
    if a.mode == "shadow":
        _local_shadow(a.local_db, a.limit)
    else:
        _local_bridge_roots(a.local_db, a.first, a.last, a.lock_lookback)
    return 0


# --------------------------------------------------------------------------
# orchestrator side: ssh + rpc helpers
# --------------------------------------------------------------------------


def ssh(host: str, cmd: str, timeout: int = 20, stdin_file: Path | None = None) -> str:
    """Run ``cmd`` on ``host``; returns stdout (stderr merged)."""
    args = ["ssh", "-o", "ConnectTimeout=8", host, cmd]
    try:
        if stdin_file is not None:
            with open(stdin_file, "rb") as fh:  # noqa: PTH123
                r = subprocess.run(args, stdin=fh, capture_output=True, text=True, timeout=timeout)
        else:
            r = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return "__SSH_TIMEOUT__"
    return r.stdout + (r.stderr if r.returncode else "")


def rpc(host: str, path: str) -> dict | None:
    out = ssh(host, f"curl -s --max-time {RPC_TIMEOUT} http://127.0.0.1:{RPC_PORT}{path}", timeout=RPC_TIMEOUT + 10)
    if not out or out == "__SSH_TIMEOUT__":
        return None
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return None


def remote_py(host: str, mode_args: str, self_path: Path, timeout: int = 120) -> dict:
    """Pipe this script to the host's venv python in --local-db mode."""
    cmd = f"{REMOTE_PREFIX} --local-db {CHAIN_DB} {mode_args}"
    out = ssh(host, cmd, timeout=timeout, stdin_file=self_path)
    for line in out.splitlines():
        line = line.strip()
        if line.startswith("{"):
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue
    return {"mode": "error", "raw": out[:400]}


def report(status: str, name: str, evidence: str) -> bool:
    print(f"[{status:>7}] {name}: {evidence}")
    return status != FAIL


# --------------------------------------------------------------------------
# checks a-g
# --------------------------------------------------------------------------


def check_a_hashes(hosts: list[str], first: int, last: int) -> bool:
    if last < first:
        return report(NOT_YET, "a hash/parent agreement", f"sealed head below {first} — nothing to compare yet")
    rows: dict[int, dict[str, tuple[str, str]]] = {}
    for host in hosts:
        for h in range(first, last + 1):
            b = rpc(host, f"/rpc/blocks/{h}")
            if b is None or "hash" not in b:
                rows.setdefault(h, {})[host] = ("<rpc-error>", "<rpc-error>")
            else:
                rows.setdefault(h, {})[host] = (b["hash"], b.get("parent_hash") or "")
    problems = []
    for h, by_host in sorted(rows.items()):
        sigs = set(by_host.values())
        if len(sigs) > 1:
            problems.append(f"@{h} { {k: short(v[0]) for k, v in by_host.items()} }")
        for host, (_hsh, par) in by_host.items():
            prev = rows.get(h - 1, {}).get(host)
            if prev and par != prev[0]:
                problems.append(f"@{h} {host}: parent {short(par)} != prev hash {short(prev[0])}")
    if problems:
        return report(FAIL, "a hash/parent agreement", "; ".join(problems[:4]))
    sample = rows.get(last, {})
    h0 = next(iter(sample.values()))[0] if sample else "?"
    return report(PASS, "a hash/parent agreement", f"{first}..{last} identical x{len(hosts)} (hash@{last} {short(h0)})")


def check_b_versions(hosts: list[str], first: int, last: int, activation: int) -> bool:
    per_host = {}
    for host in hosts:
        rows = []
        for h in range(first, last + 1):
            b = rpc(host, f"/rpc/blocks/{h}")
            if b is None:
                continue
            rows.append((h, parse_block_meta(b.get("block_metadata")).get("state_transition_version")))
        per_host[host] = rows
    status, detail = eval_version_window(per_host[hosts[0]], activation)
    for host in hosts[1:]:
        if per_host[host] != per_host[hosts[0]]:
            status, detail = FAIL, f"version stamps differ: {hosts[0]} {per_host[hosts[0]][:4]} vs {host} {per_host[host][:4]}"
            break
    return report(status, "b state_transition_version", detail)


def check_c_aux(hosts: list[str], first: int, last: int, activation: int) -> bool:
    per_host = {}
    for host in hosts:
        rows = []
        for h in range(first, last + 1):
            b = rpc(host, f"/rpc/blocks/{h}")
            if b is None:
                continue
            rows.append((h, b.get("aux_state_root")))
        per_host[host] = rows
    status, detail = eval_aux_window(per_host, activation)
    return report(status, "c aux_state_root", detail)


def check_d_bridge_root(hosts: list[str], first: int, last: int, activation: int, self_path: Path, min_head: int) -> bool:
    targets = [hosts[0]] + ([h for h in ("node2", "node0", "node1") if h in hosts][:1])
    if min_head < first:
        f, t = max(0, min_head - 11), min_head
        label = f"pre-activation probe {f}..{t}"
    else:
        f, t = first, last
        label = f"{f}..{t}"
    ok = True
    for host in targets:
        res = remote_py(host, f"--mode bridge-roots --from {f} --to {t}", self_path)
        rows = res.get("rows", [])
        if res.get("mode") == "error" or not rows:
            ok &= report(FAIL, f"d bridge_state_root @{host}", f"remote run failed: {res.get('raw', res)}")
            continue
        mism = [r for r in rows if not r["match"]]
        n_locks = sum(r["locks"] for r in rows)
        if mism:
            ok &= report(FAIL, f"d bridge_state_root @{host}", f"{len(mism)} mismatch(es): {mism[:3]}")
        else:
            ex = rows[-1]
            ok &= report(
                PASS,
                f"d bridge_state_root @{host}",
                f"{label}: {len(rows)} blocks recompute==committed ({n_locks} lock leaves; root {ex['recomputed']} == {ex['committed']})",
            )
    return ok


def check_e_validators(hosts: list[str], attestation_lookback: int, min_head: int) -> bool:
    ok = True
    top = min_head
    first = max(1, top - attestation_lookback)
    for host in hosts:
        v = rpc(host, "/rpc/consensus/validators")
        active = set()
        if v is not None:
            active = {
                x["address"][:6].lower()
                for x in v.get("validators", [])
                if x.get("is_active") and x.get("role") == "validator"
            }
        status, detail = eval_attesters(active)
        if status == FAIL:
            ok &= report(FAIL, f"e validator set @{host}", detail)
            continue
        attested = set()
        for h in range(first, top + 1):
            b = rpc(host, f"/rpc/blocks/{h}")
            if b is None:
                continue
            for a in parse_block_meta(b.get("block_metadata")).get("attestations", []):
                attested.add(str(a.get("validator", ""))[:6].lower())
        unexpected = attested - EXPECTED_VALIDATORS
        if unexpected:
            ok &= report(FAIL, f"e validator set @{host}", f"unexpected attesters in {first}..{top}: {sorted(unexpected)}")
        else:
            ok &= report(status, f"e validator set @{host}", f"{detail}; attesters seen {sorted(attested)}")
    return ok


def check_f_liveness(hosts: list[str]) -> bool:
    heads = {}
    for host in hosts:
        h = rpc(host, "/rpc/chain/head")
        if h is not None:
            heads[host] = h
    status, detail = eval_head_rows(heads, datetime.now(UTC).timestamp())
    missing = [h for h in hosts if h not in heads]
    if missing:
        status = FAIL
        detail += f"; no head from {missing}"
    ok = report(status, "f head liveness/fork", detail)
    # Prometheus firing alerts on hub
    prom = ssh("hub", f"curl -s --max-time 8 {PROM_ALERTS}", timeout=15)
    try:
        alerts = json.loads(prom).get("data", {}).get("alerts", [])
        firing = [a for a in alerts if a.get("state") == "firing"]
    except json.JSONDecodeError:
        firing = None
    if firing is None:
        ok &= report(INFO, "f prometheus alerts", "unparseable response — check manually")
    elif firing:
        ok &= report(
            FAIL, "f prometheus alerts", f"{len(firing)} firing: {[a.get('labels', {}).get('alertname') for a in firing][:5]}"
        )
    else:
        ok &= report(PASS, "f prometheus alerts", "0 firing on hub")
    # alerts.log tail on hub — recent ERROR/ALERT lines
    tail = ssh("hub", f"tail -n 60 {ALERT_LOG}", timeout=15)
    bad = [ln for ln in tail.splitlines() if re.search(r"ERROR|CRITICAL|FIRING|ALERT", ln, re.I)]
    if bad:
        ok &= report(FAIL, "f alerts.log tail", f"{len(bad)} flagged line(s): {bad[-1][:120]}")
    else:
        ok &= report(PASS, "f alerts.log tail", "no ERROR/ALERT lines in last 60")
    return ok


def check_g_shadow(hosts: list[str], self_path: Path, limit: int) -> bool:
    per_host = {}
    for host in hosts:
        res = remote_py(host, f"--mode shadow --limit {limit}", self_path)
        rows = res.get("rows", [])
        if res.get("mode") == "error" or not rows:
            return report(FAIL, "g side-root fingerprints", f"{host}: remote run failed: {res.get('raw', res)}")
        per_host[host] = dict(rows)
    shared = sorted(set.intersection(*(set(v) for v in per_host.values()))) if per_host else []
    per_height = {h: {host: per_host[host][h] for host in hosts} for h in shared}
    mism = consensus_mismatches(per_height)
    if mism:
        return report(FAIL, "g side-root fingerprints", "; ".join(mism[:4]))
    latest = shared[-1] if shared else None
    fp = per_host[hosts[0]][latest] if latest else "?"
    return report(
        PASS,
        "g side-root fingerprints",
        f"{len(shared)} shared heights identical x{len(hosts)} (latest @{latest} {short(fp, 12)})",
    )


# --------------------------------------------------------------------------


def main(argv: list[str]) -> int:
    if argv and argv[0] == "--local-db":
        return _remote_main(argv)

    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--activation-height", type=int, default=DEFAULT_ACTIVATION)
    p.add_argument("--window", type=int, default=DEFAULT_WINDOW, help="blocks on each side of the activation height")
    p.add_argument("--shadow-limit", type=int, default=25)
    p.add_argument("--hosts", nargs="*", default=HOSTS)
    a = p.parse_args(argv)

    self_path = Path(__file__).resolve()
    act = a.activation_height
    first, last = act - 2, act + a.window

    heads = {h: (rpc(h, "/rpc/chain/head") or {}).get("height") for h in a.hosts}
    min_head = min((x for x in heads.values() if isinstance(x, int)), default=0)
    if min_head < last:
        last = min_head
    print(f"# post-activation audit — activation {act}, window {first}..{last}, hosts {a.hosts}")
    print(f"# heads: {heads} (min {min_head})")

    ok = True
    ok &= check_a_hashes(a.hosts, first, last)
    ok &= check_b_versions(a.hosts, first, last, act)
    ok &= check_c_aux(a.hosts, first, last, act)
    ok &= check_d_bridge_root(a.hosts, first, last, act, self_path, min_head)
    ok &= check_e_validators(a.hosts, 200, min_head)
    ok &= check_f_liveness(a.hosts)
    ok &= check_g_shadow(a.hosts, self_path, a.shadow_limit)
    print(f"# verdict: {'ALL PASS' if ok else 'FAILURES PRESENT'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
