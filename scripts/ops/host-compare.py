#!/usr/bin/env python3
"""host-compare.py — read-only two-host comparison for failover readiness.

B4 (note 1493): compares the AITBC service set, configuration key names
(never values), chain synchronisation state, and memory between two hosts
— intended as ``host-compare.py --a hub --b hub1`` for the hub→hub1
failover-readiness audit. The script is descriptive: it reports
differences, it does not judge which side is correct.

Everything is collected over a single ``ssh`` per host running one
read-only shell probe, so the fleet-side SSH accounting sees two
connections total. The probe never prints env *values* — only key names
per file — and never opens wallets or keystores. sqlite3 runs with
``-readonly``.

Sections compared:

  HOST      hostname / boot time / ssh alias
  UNITS     aitbc-* unit files (enabled state) and active states
  UNITENV   EnvironmentFiles each aitbc unit consumes (paths only)
  ENVKEYS   key names per /etc/aitbc/*.env file (values never read)
  CHAIN     per chain.db: height, hash prefix, last-block timestamp, size
  STORES    sizes of the data dir's top-level databases
  MEM       cgroup memory.current/peak/max plus MemTotal/MemAvailable

Usage:
    host-compare.py --a hub --b hub1 [--output table|json]
    host-compare.py --a-file captured-a.txt --b-file captured-b.txt   # offline
    host-compare.py --probe > probe.sh    # emit the remote probe for review

Exit codes: 0 = collected and compared, 2 = collection failed.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass

# The remote probe. One sh -s invocation per host. Every command is
# read-only; lines starting with @@ are section markers the parser splits
# on. Env files contribute key names only — values are stripped by the
# sed before anything crosses the wire.
PROBE = r"""
echo "@@HOST"
hostname
date +%s
echo "boot_epoch $(cat /proc/stat | awk '/btime/{print $2}')"
echo "@@UNITS_FILES"
systemctl list-unit-files 'aitbc-*' --no-legend --no-pager 2>/dev/null
echo "@@UNITS_ACTIVE"
systemctl list-units 'aitbc-*' --all --no-legend --no-pager 2>/dev/null | sed 's/^[^[:alnum:]_-]*[[:space:]]*//' | awk '{print $1, $2, $3, $4}'
echo "@@UNITENV"
for u in $(systemctl list-unit-files 'aitbc-*' --no-legend --no-pager 2>/dev/null | awk '{print $1}'); do
    echo "UNIT $u"
    systemctl show "$u" -p EnvironmentFiles --value 2>/dev/null
done
echo "@@ENVKEYS"
for f in /etc/aitbc/*.env; do
    [ -f "$f" ] || continue
    echo "FILE $(basename "$f")"
    grep -oE '^[[:space:]]*(export[[:space:]]+)?[A-Za-z_][A-Za-z0-9_]*[[:space:]]*=' "$f" 2>/dev/null \
        | sed -E 's/[[:space:]]*(export[[:space:]]+)?//; s/[[:space:]]*=.*//' | sort -u
done
echo "@@CHAIN"
for db in /var/lib/aitbc/data/*/chain.db /opt/aitbc/data/*/chain.db; do
    [ -f "$db" ] || continue
    echo "DB $db"
    sqlite3 -readonly "$db" \
        "SELECT height, substr(hash,1,18), timestamp FROM block ORDER BY height DESC LIMIT 1" 2>/dev/null
    echo "SIZE $(stat -c %s "$db" 2>/dev/null)"
done
echo "@@STORES"
for db in /var/lib/aitbc/data/*.db /var/lib/aitbc/*.db /var/lib/aitbc/data/*/*.db; do
    [ -f "$db" ] || continue
    [ "${db##*/}" = "chain.db" ] && continue
    echo "$db $(stat -c %s "$db" 2>/dev/null)"
done
echo "@@MEM"
for f in /sys/fs/cgroup/memory.current /sys/fs/cgroup/memory.peak /sys/fs/cgroup/memory.max \
         /sys/fs/cgroup/memory.events; do
    [ -f "$f" ] && echo "$f = $(cat "$f" 2>/dev/null | tr '\n' ' ')"
done
grep -E '^(MemTotal|MemAvailable|SwapTotal|SwapFree):' /proc/meminfo
"""


@dataclass
class HostData:
    name: str
    raw: str
    sections: dict[str, list[str]]


def parse(raw: str, name: str) -> HostData:
    sections: dict[str, list[str]] = {}
    cur = "PREAMBLE"
    for line in raw.splitlines():
        line = line.rstrip()
        if line.startswith("@@"):
            cur = line[2:]
            sections[cur] = []
        elif line:
            sections.setdefault(cur, []).append(line)
    return HostData(name=name, raw=raw, sections=sections)


def collect(alias: str, timeout: int = 30) -> str | None:
    try:
        out = subprocess.run(
            ["ssh", "-o", "BatchMode=yes", alias, "sh -s"],
            input=PROBE,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if out.returncode == 0 and "@@HOST" in out.stdout:
            return out.stdout
        sys.stderr.write(f"ssh {alias}: rc={out.returncode} err={out.stderr.strip()[:200]}\n")
    except Exception as e:  # noqa: BLE001 - report and let caller exit(2)
        sys.stderr.write(f"ssh {alias}: {e}\n")
    return None


def unit_states(lines: list[str]) -> dict[str, str]:
    """list-unit-files rows: 'name.service enabled' -> {name: state}."""
    out: dict[str, str] = {}
    for ln in lines:
        parts = ln.split()
        if len(parts) >= 2:
            out[parts[0]] = parts[1]
    return out


def active_states(lines: list[str]) -> dict[str, str]:
    """list-units rows: 'name.service loaded active running' -> {name: 'active/running'}.

    Not-found/failed units carry a leading ``●`` marker column; strip any
    leading non-alphanumeric token so the row keeps its unit name.
    """
    out: dict[str, str] = {}
    for ln in lines:
        parts = ln.lstrip("●* ").split()
        if len(parts) >= 4 and "." in parts[0]:
            out[parts[0]] = f"{parts[2]}/{parts[3]}"
    return out


def envkey_map(lines: list[str]) -> dict[str, list[str]]:
    """'FILE x.env' followed by key names -> {filename: [keys]}."""
    out: dict[str, list[str]] = {}
    cur = ""
    for ln in lines:
        if ln.startswith("FILE "):
            cur = ln[5:]
            out[cur] = []
        elif cur:
            out[cur].append(ln.strip())
    return out


def unitenv_map(lines: list[str]) -> dict[str, list[str]]:
    """'UNIT x.service' followed by EnvironmentFiles paths."""
    out: dict[str, list[str]] = {}
    cur = ""
    for ln in lines:
        if ln.startswith("UNIT "):
            cur = ln[5:]
            out[cur] = []
        elif cur:
            out[cur].extend(t for t in ln.split() if t.startswith("/"))
    return out


def chain_rows(lines: list[str]) -> list[dict]:
    """'DB path' followed by 'height|hash|timestamp' and 'SIZE n' rows."""
    out: list[dict] = []
    cur: dict | None = None
    for ln in lines:
        if ln.startswith("DB "):
            cur = {"db": ln[3:], "height": None, "hash": "", "ts": "", "size": 0}
            out.append(cur)
        elif ln.startswith("SIZE ") and cur:
            cur["size"] = int(ln[5:] or 0)
        elif "|" in ln and cur:
            h, hh, ts = (ln.split("|") + ["", ""])[:3]
            cur["height"], cur["hash"], cur["ts"] = int(h or 0), hh, ts
    return out


def diff_set(a: dict[str, str], b: dict[str, str]) -> list[tuple[str, str, str]]:
    """Keys/values present on either side; yields (name, a-state, b-state)."""
    rows = []
    for k in sorted(set(a) | set(b)):
        rows.append((k, a.get(k, "-"), b.get(k, "-")))
    return rows


def fmt_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f}{unit}" if unit != "B" else f"{n}B"
        n /= 1024
    return f"{n}B"


def _cmp_units_enabled(a: HostData, b: HostData, out: list[str]) -> None:
    out.append("== UNITS (enabled state)")
    ua, ub = unit_states(a.sections.get("UNITS_FILES", [])), unit_states(b.sections.get("UNITS_FILES", []))
    for name, sa, sb in diff_set(ua, ub):
        if sa != sb:
            out.append(f"  DIFF  {name:<48} {a.name}={sa:<12} {b.name}={sb}")
    out.append(f"  ({sum(1 for k in ua if ua[k] == ub.get(k))} identical)")


def _cmp_units_active(a: HostData, b: HostData, out: list[str]) -> None:
    out.append("== UNITS (active state)")
    aa, ab = active_states(a.sections.get("UNITS_ACTIVE", [])), active_states(b.sections.get("UNITS_ACTIVE", []))
    for name, sa, sb in diff_set(aa, ab):
        if sa != sb:
            out.append(f"  DIFF  {name:<48} {a.name}={sa:<16} {b.name}={sb}")


def _cmp_unit_env(a: HostData, b: HostData, out: list[str]) -> None:
    out.append("== UNIT ENV FILES")
    ea, eb = unitenv_map(a.sections.get("UNITENV", [])), unitenv_map(b.sections.get("UNITENV", []))
    for name in sorted(set(ea) | set(eb)):
        fa, fb = sorted(ea.get(name, [])), sorted(eb.get(name, []))
        if fa != fb:
            out.append(f"  DIFF  {name}: {a.name}={fa} {b.name}={fb}")


def _cmp_env_keys(a: HostData, b: HostData, out: list[str]) -> None:
    out.append("== ENV KEY NAMES (per file; values never compared)")
    ka, kb = envkey_map(a.sections.get("ENVKEYS", [])), envkey_map(b.sections.get("ENVKEYS", []))
    for fname in sorted(set(ka) | set(kb)):
        na, nb = set(ka.get(fname, [])), set(kb.get(fname, []))
        if fname not in ka:
            out.append(f"  DIFF  {fname}: absent on {a.name} ({len(nb)} keys on {b.name})")
            continue
        if fname not in kb:
            out.append(f"  DIFF  {fname}: absent on {b.name} ({len(na)} keys on {a.name})")
            continue
        only_a, only_b = sorted(na - nb), sorted(nb - na)
        if only_a or only_b:
            out.append(f"  DIFF  {fname}: only-{a.name}={only_a} only-{b.name}={only_b}")


def _chain_db_tail(db: str) -> list[str]:
    return db.split("/")[-2:]


def _cmp_chain(a: HostData, b: HostData, out: list[str]) -> None:
    out.append("== CHAIN HEADS")
    ca, cb = chain_rows(a.sections.get("CHAIN", [])), chain_rows(b.sections.get("CHAIN", []))
    for ra in ca:
        twin = next((r for r in cb if _chain_db_tail(r["db"]) == _chain_db_tail(ra["db"])), None)
        if twin:
            delta = ra["height"] - twin["height"]
            match = (
                "MATCH"
                if ra["hash"] == twin["hash"] and delta == 0
                else f"delta={delta:+d} hashA={ra['hash']} hashB={twin['hash']}"
            )
            out.append(
                f"  {ra['db']}: {a.name} h={ra['height']} {ra['hash']} {ra['ts']} | "
                f"{b.name} h={twin['height']} {twin['hash']} {twin['ts']} -> {match}"
            )
        else:
            out.append(f"  {ra['db']}: only on {a.name} (h={ra['height']})")
    for rb in cb:
        if not any(_chain_db_tail(rb["db"]) == _chain_db_tail(ra["db"]) for ra in ca):
            out.append(f"  {rb['db']}: only on {b.name} (h={rb['height']})")


def _cmp_stores(a: HostData, b: HostData, out: list[str]) -> None:
    out.append("== STORES (bytes)")
    sa = {ln.rsplit(" ", 1)[0]: int(ln.rsplit(" ", 1)[1]) for ln in a.sections.get("STORES", [])}
    sb = {ln.rsplit(" ", 1)[0]: int(ln.rsplit(" ", 1)[1]) for ln in b.sections.get("STORES", [])}
    for path in sorted(set(sa) | set(sb)):
        va, vb = sa.get(path), sb.get(path)
        flag = "DIFF" if va != vb else "same"
        da = fmt_size(va) if va is not None else "-"
        db_ = fmt_size(vb) if vb is not None else "-"
        out.append(f"  {flag}  {path}: {a.name}={da} {b.name}={db_}")


def compare(a: HostData, b: HostData) -> list[str]:
    out: list[str] = [f"== HOST  {a.name} vs {b.name}"]
    for ln in a.sections.get("HOST", [])[:4]:
        out.append(f"  {a.name}: {ln}")
    for ln in b.sections.get("HOST", [])[:4]:
        out.append(f"  {b.name}: {ln}")

    _cmp_units_enabled(a, b, out)
    _cmp_units_active(a, b, out)
    _cmp_unit_env(a, b, out)
    _cmp_env_keys(a, b, out)
    _cmp_chain(a, b, out)
    _cmp_stores(a, b, out)

    out.append("== MEMORY")
    for tag, h in ((a.name, a), (b.name, b)):
        for ln in h.sections.get("MEM", []):
            out.append(f"  {tag}: {ln}")
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--a", default=None, help="ssh alias of host A (e.g. hub)")
    p.add_argument("--b", default=None, help="ssh alias of host B (e.g. hub1)")
    p.add_argument("--a-file", default=None, help="parse a previously captured probe output for A")
    p.add_argument("--b-file", default=None, help="parse a previously captured probe output for B")
    p.add_argument("--a-name", default=None, help="label override for A")
    p.add_argument("--b-name", default=None, help="label override for B")
    p.add_argument("--output", choices=("table", "json"), default="table")
    p.add_argument("--probe", action="store_true", help="print the remote probe and exit")
    args = p.parse_args(argv)

    if args.probe:
        sys.stdout.write(PROBE)
        return 0

    raws: dict[str, str] = {}
    for tag, alias, path in (("a", args.a, args.a_file), ("b", args.b, args.b_file)):
        label = getattr(args, f"{tag}_name") or alias or (path or tag)
        if path:
            raws[label] = open(path).read()  # noqa: PTH123 - ops tool, path is operator-supplied
        elif alias:
            raw = collect(alias)
            if raw is None:
                return 2
            raws[label] = raw
        else:
            p.error(f"need --{tag} or --{tag}-file")

    names = list(raws)
    ha, hb = parse(raws[names[0]], names[0]), parse(raws[names[1]], names[1])
    if args.output == "json":
        print(json.dumps({names[0]: ha.sections, names[1]: hb.sections}, indent=2))
        return 0
    for line in compare(ha, hb):
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
