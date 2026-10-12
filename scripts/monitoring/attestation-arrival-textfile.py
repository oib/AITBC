#!/usr/bin/env python3
"""Export remote-attestation arrival stats as a node_exporter textfile.

Remote attestations carry no arrival timestamp on-chain — the only timing
signal is the proposer's journal ("Attestation arrival:" INFO lines in
aitbc_chain/consensus/remote_attestation.py). This exporter measures the
sealed outcome instead: each block's ``block_metadata.attestations`` list
holds ONLY the remote attestations that arrived before sealing (the
proposer's own is implicit and never listed), so a validator absent from
the list was too late or never arrived.

Reads the last ``AITBC_ATTESTATION_WINDOW_BLOCKS`` blocks of every chain.db
found under ``AITBC_DATA_DIR`` (or the explicit ``AITBC_CHAIN_DB``),
read-only. The validator set is the union of proposers and attesting
validators seen in the window unless ``AITBC_ATTESTATION_VALIDATORS``
pins it. A validator-set rotation mixes two eras inside one window for a
few runs — the alerting rule's ``for:`` absorbs that transient.

A block whose metadata is malformed JSON counts as "no attestations"
(all remote validators missing for it). A DB that cannot be opened or
lacks the block table reads as failure, not "all clear".

Writes, atomically, to ``<TEXTFILE_DIR>/aitbc_attestation_arrival.prom``:

    aitbc_attestation_window_blocks{db=...}         blocks examined
    aitbc_attestation_validators{db=...}            validators in the set
    aitbc_attestation_head_height{db=...}           highest block seen
    aitbc_attestation_expected_remote_total{db=...} remote attestations owed
    aitbc_attestation_arrived_remote_total{db=...}  remote attestations sealed
    aitbc_attestation_arrival_share{db=...}         arrived / expected (1.0 at 0)
    aitbc_attestation_short_blocks{db=...}          blocks missing >=1 remote
    aitbc_attestation_missed_blocks{db=...,validator=...}      blocks it owed and missed
    aitbc_attestation_consecutive_missed{db=...,validator=...} miss streak from head
    aitbc_attestation_scrape_success{db=...}        1 when the DB read worked
    aitbc_attestation_scrape_timestamp_seconds      when this run finished

Stdlib only.
"""

from __future__ import annotations

import glob
import json
import os
import sqlite3
import sys
import tempfile
import time
from typing import NamedTuple

OUTPUT_NAME = "aitbc_attestation_arrival.prom"
DEFAULT_WINDOW_BLOCKS = 200


# NamedTuple, not @dataclass: the test suite importlib-loads this script without
# registering it in sys.modules, and dataclass field resolution requires the
# module entry under Python 3.13.
class ArrivalStats(NamedTuple):
    window_blocks: int
    validators: tuple[str, ...]
    head_height: int
    expected_remote_total: int
    arrived_remote_total: int
    arrival_share: float
    short_blocks: int
    missed_blocks: dict[str, int]
    consecutive_missed: dict[str, int]


def find_chain_dbs(data_dir: str) -> list[str]:
    """Every ``data/*/chain.db`` under the data dir, sorted for determinism."""
    return sorted(glob.glob(os.path.join(data_dir, "data", "*", "chain.db")))


def _attesting_validators(block_metadata: object) -> set[str]:
    """Distinct validator addresses in the attestation list; malformed -> empty."""
    try:
        meta = json.loads(str(block_metadata))
    except (json.JSONDecodeError, TypeError, ValueError):
        return set()
    attestations = meta.get("attestations") if isinstance(meta, dict) else None
    if not isinstance(attestations, list):
        return set()
    out = set()
    for entry in attestations:
        if isinstance(entry, dict) and entry.get("validator"):
            out.add(str(entry["validator"]))
    return out


def _consecutive_missed(blocks: list[tuple[str, set[str]]], validator: str) -> int:
    """Miss streak counting back from the head over blocks the validator should
    have attested; blocks it proposed are skipped, not streak-breaking."""
    streak = 0
    for proposer, present in blocks:  # head-first order
        if proposer == validator:
            continue
        if validator in present:
            break
        streak += 1
    return streak


def arrival_stats(con: sqlite3.Connection, window: int, validators: list[str] | None = None) -> ArrivalStats:
    rows = con.execute(
        "SELECT height, proposer, block_metadata FROM block ORDER BY height DESC LIMIT ?",
        (int(window),),
    ).fetchall()

    parsed = [(int(h), str(p or ""), _attesting_validators(m)) for h, p, m in rows]
    if validators is None:
        vset = set()
        for _, proposer, present in parsed:
            vset.add(proposer)
            vset.update(present)
        vset.discard("")
    else:
        vset = {v for v in validators if v}
    vlist = tuple(sorted(vset))

    expected_total = 0
    arrived_total = 0
    short_blocks = 0
    missed: dict[str, int] = dict.fromkeys(vlist, 0)
    owe_blocks: list[tuple[str, set[str]]] = []  # (proposer, present) head-first
    for _, proposer, present in parsed:
        expected_remote = vset - {proposer}
        arrived = present & expected_remote
        missing = expected_remote - arrived
        expected_total += len(expected_remote)
        arrived_total += len(arrived)
        if missing:
            short_blocks += 1
            for v in missing:
                missed[v] += 1
        owe_blocks.append((proposer, arrived))

    consecutive = {v: _consecutive_missed(owe_blocks, v) for v in vlist}
    share = arrived_total / expected_total if expected_total else 1.0
    return ArrivalStats(
        window_blocks=len(parsed),
        validators=vlist,
        head_height=parsed[0][0] if parsed else 0,
        expected_remote_total=expected_total,
        arrived_remote_total=arrived_total,
        arrival_share=share,
        short_blocks=short_blocks,
        missed_blocks=missed,
        consecutive_missed=consecutive,
    )


def read_db(path: str, window: int, validators: list[str] | None) -> ArrivalStats | None:
    """None on failure — a broken check must not mask the disease it watches."""
    try:
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            return arrival_stats(con, window, validators)
        finally:
            con.close()
    except sqlite3.Error:
        return None


def _label(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _fmt_share(share: float) -> str:
    return repr(round(share, 6))


def _render_db(lines: list[str], db: str, s: ArrivalStats) -> None:
    d = f'{{db="{_label(db)}"}}'
    lines.append(f"aitbc_attestation_window_blocks{d} {s.window_blocks}")
    lines.append(f"aitbc_attestation_validators{d} {len(s.validators)}")
    lines.append(f"aitbc_attestation_head_height{d} {s.head_height}")
    lines.append(f"aitbc_attestation_expected_remote_total{d} {s.expected_remote_total}")
    lines.append(f"aitbc_attestation_arrived_remote_total{d} {s.arrived_remote_total}")
    lines.append(f"aitbc_attestation_arrival_share{d} {_fmt_share(s.arrival_share)}")
    lines.append(f"aitbc_attestation_short_blocks{d} {s.short_blocks}")
    for v in s.validators:
        labels = f'{{db="{_label(db)}",validator="{_label(v)}"}}'
        lines.append(f"aitbc_attestation_missed_blocks{labels} {s.missed_blocks.get(v, 0)}")
        lines.append(f"aitbc_attestation_consecutive_missed{labels} {s.consecutive_missed.get(v, 0)}")


def render(results: dict[str, ArrivalStats | None], now: float) -> str:
    """results maps db path → arrival stats, or None when the read failed."""
    lines = [
        "# HELP aitbc_attestation_window_blocks Blocks examined for attestation arrival.",
        "# TYPE aitbc_attestation_window_blocks gauge",
        "# HELP aitbc_attestation_validators Validators in the derived or pinned set.",
        "# TYPE aitbc_attestation_validators gauge",
        "# HELP aitbc_attestation_head_height Highest block height seen.",
        "# TYPE aitbc_attestation_head_height gauge",
        "# HELP aitbc_attestation_expected_remote_total Remote attestations owed in the window.",
        "# TYPE aitbc_attestation_expected_remote_total gauge",
        "# HELP aitbc_attestation_arrived_remote_total Remote attestations sealed in the window.",
        "# TYPE aitbc_attestation_arrived_remote_total gauge",
        "# HELP aitbc_attestation_arrival_share Share of owed remote attestations that sealed (1.0 when none owed).",
        "# TYPE aitbc_attestation_arrival_share gauge",
        "# HELP aitbc_attestation_short_blocks Blocks missing at least one remote attestation.",
        "# TYPE aitbc_attestation_short_blocks gauge",
        "# HELP aitbc_attestation_missed_blocks Blocks a validator owed a remote attestation and missed.",
        "# TYPE aitbc_attestation_missed_blocks gauge",
        "# HELP aitbc_attestation_consecutive_missed Consecutive owed-but-missed blocks counting back from the head.",
        "# TYPE aitbc_attestation_consecutive_missed gauge",
        "# HELP aitbc_attestation_scrape_success 1 when the chain.db read worked.",
        "# TYPE aitbc_attestation_scrape_success gauge",
        "# HELP aitbc_attestation_scrape_timestamp_seconds Unix time of this scrape.",
        "# TYPE aitbc_attestation_scrape_timestamp_seconds gauge",
    ]
    for db, stats in sorted(results.items()):
        ok = stats is not None
        lines.append(f'aitbc_attestation_scrape_success{{db="{_label(db)}"}} {1 if ok else 0}')
        if ok:
            _render_db(lines, db, stats)
    lines.append(f"aitbc_attestation_scrape_timestamp_seconds {int(now)}")
    return "\n".join(lines) + "\n"


def write_atomic(directory: str, text: str) -> None:
    """Write beside the target and rename: node_exporter never reads a half-written file."""
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".aitbc_attestation_arrival.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.rename(tmp, os.path.join(directory, OUTPUT_NAME))
    except BaseException:
        os.unlink(tmp)
        raise


def resolve_dbs() -> list[str]:
    explicit = os.getenv("AITBC_CHAIN_DB", "").strip()
    if explicit:
        return [explicit]
    return find_chain_dbs(os.getenv("AITBC_DATA_DIR", "/var/lib/aitbc"))


def _env_validators() -> list[str] | None:
    raw = os.getenv("AITBC_ATTESTATION_VALIDATORS", "").strip()
    if not raw:
        return None
    return [v.strip() for v in raw.split(",") if v.strip()]


def main() -> int:
    directory = os.getenv("AITBC_TEXTFILE_DIR", "/var/lib/prometheus/node-exporter")
    window = int(os.getenv("AITBC_ATTESTATION_WINDOW_BLOCKS", str(DEFAULT_WINDOW_BLOCKS)))
    validators = _env_validators()
    now = time.time()
    dbs = resolve_dbs()
    results: dict[str, ArrivalStats | None] = {}
    rc = 0
    for db in dbs or ["<none>"]:
        if db == "<none>":
            results[db] = None
            rc = 1
            continue
        stats = read_db(db, window, validators)
        results[db] = stats
        if stats is None:
            rc = 1
    write_atomic(directory, render(results, now))
    return rc


if __name__ == "__main__":
    sys.exit(main())
