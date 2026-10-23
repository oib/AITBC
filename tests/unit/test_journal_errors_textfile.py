"""Fixture tests for journal-errors-textfile.py (ATTEST-PROM-FOLLOW-1, RAM-B1).

AITBCJournalErrors evaluates aitbc_journal_error_messages > 0, but the exporter
emitted that metric only for units with hits — a quiet window produced a .prom
with just the scan metrics and the alert could not distinguish "no errors"
from "exporter blind". render() now emits a bare zero anchor whenever no unit
has an error count.

RAM-B1 replaced the buffered journalctl calls with a streaming reader plus an
indexed _TRANSPORT=stdout pre-filter on the -g pass. The fixture tests below
pin the counting contract: identical counts for identical logical entries in
full-field or trimmed-field form, dedup across passes via __CURSOR, and the
journalctl argv carrying the indexed filter plus --output-fields."""

from __future__ import annotations

import importlib.util
import json
import os
import stat
from collections import Counter
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


exporter = _load("journal_errors_textfile", REPO / "scripts/monitoring/journal-errors-textfile.py")


def test_render_emits_zero_anchor_when_no_unit_has_errors():
    counts: Counter[tuple[int, str]] = Counter({(0, "aitbc-market.service"): 3})
    text = exporter.render(counts, 1700000000.0, True)
    assert "aitbc_journal_error_messages 0\n" in text
    assert "aitbc_journal_error_messages{unit=" not in text
    assert 'aitbc_journal_warning_messages{unit="aitbc-market.service"} 3' in text


def test_render_emits_zero_anchor_when_window_empty():
    text = exporter.render(Counter(), 1700000000.0, True)
    assert "aitbc_journal_error_messages 0\n" in text
    assert "aitbc_journal_scan_success 1\n" in text
    assert "aitbc_journal_scan_timestamp_seconds 1700000000\n" in text


def test_render_no_anchor_when_a_unit_has_errors():
    counts: Counter[tuple[int, str]] = Counter({(1, "aitbc-blockchain-node.service"): 7})
    text = exporter.render(counts, 1700000000.0, True)
    assert 'aitbc_journal_error_messages{unit="aitbc-blockchain-node.service"} 7' in text
    assert "aitbc_journal_error_messages 0\n" not in text


# --- RAM-B1: streaming journalctl reader -------------------------------------
#
# The fixture journal below is the contract the rewrite must preserve. It is
# deliberately nasty: a priority-3 service record that *also* carries a text
# level (arrives in both passes -> must dedup via __CURSOR), a priority-4
# record without a text token (counted via priority only), stdout text-level
# records at priority 6, and a plain info line that must not count at all.

FIXTURE_RECORDS = [
    {
        "__CURSOR": "c-real-err",
        "PRIORITY": "3",
        "MESSAGE": "[ERROR] attest submit failed",
        "_SYSTEMD_UNIT": "aitbc-blockchain-node.service",
        "SYSLOG_IDENTIFIER": "python3",
        "_COMM": "python3",
        "_TRANSPORT": "stdout",
    },
    # Priority-4 with a [WARN] text token on stdout: emitted by the text
    # pass (old AND new semantics -- stdout transport is where service
    # levels live), counted as a warning.
    {
        "__CURSOR": "c-text-warn4",
        "PRIORITY": "4",
        "MESSAGE": "[WARN] rpc peer pool degraded",
        "_SYSTEMD_UNIT": "aitbc-blockchain-rpc.service",
        "_TRANSPORT": "stdout",
    },
    # Priority-4 WITHOUT a level token: NEITHER pass emits it ("-p err" is
    # 0..3, the text pass needs the bracket) -- pinned here so nobody
    # "fixes" the gap silently; a no-token warning is invisible by design.
    {
        "__CURSOR": "c-real-warn",
        "PRIORITY": "4",
        "MESSAGE": "unit reported a degraded peer",
        "_SYSTEMD_UNIT": "aitbc-blockchain-rpc.service",
        "_TRANSPORT": "journal",
    },
    {
        "__CURSOR": "c-text-warn",
        "PRIORITY": "6",
        "MESSAGE": "[WARNING] pool heartbeat slow",
        "_SYSTEMD_UNIT": "aitbc-wallet.service",
        "_TRANSPORT": "stdout",
    },
    {
        "__CURSOR": "c-text-err",
        "PRIORITY": "6",
        "MESSAGE": "[CRITICAL] bridge payout ledger locked",
        "_SYSTEMD_UNIT": "aitbc-bridge-monitor.service",
        "_TRANSPORT": "stdout",
    },
    {
        "__CURSOR": "c-info",
        "PRIORITY": "6",
        "MESSAGE": "Imported block 1742",
        "_SYSTEMD_UNIT": "aitbc-blockchain-node.service",
        "_TRANSPORT": "stdout",
    },
    # A syslog_transport record with a bracket word that is NOT a level
    # token: the -g pass would only match a real level; kept here so a
    # fixture change can't silently alter counting.
    {
        "__CURSOR": "c-info-bracket",
        "PRIORITY": "6",
        "MESSAGE": "[notice] benign bracket word",
        "_SYSTEMD_UNIT": "cron.service",
        "_TRANSPORT": "syslog",
    },
]

LEVEL_TOKENS = ("WARNING", "WARN", "ERROR", "CRITICAL", "FATAL")


def _pass_emitted(record) -> bool:
    """Would a journalctl pass emit this record? Models the pass-level
    filters (old or new -- identical emit sets on this fleet): ``-p err``
    emits priority <= 3; the text pass emits stdout-transport rows whose
    MESSAGE carries a [LEVEL] token."""
    prio = int(record.get("PRIORITY", 6))
    if prio <= 3:
        return True
    msg = str(record.get("MESSAGE") or "")
    return record.get("_TRANSPORT") == "stdout" and any(msg.startswith(f"[{lv}]") for lv in LEVEL_TOKENS)


EXPECTED_COUNTS = Counter(
    {
        (1, "aitbc-blockchain-node.service"): 1,  # prio 3 (dedup'd vs pass 2)
        (0, "aitbc-blockchain-rpc.service"): 1,  # [WARN] text at prio 4
        (0, "aitbc-wallet.service"): 1,  # [WARNING] text
        (1, "aitbc-bridge-monitor.service"): 1,  # [CRITICAL] text
    }
)


def _count(records):
    """Same counting loop as collect(), factored for fixture use."""
    counts: Counter[tuple[int, str]] = Counter()
    seen: set[str] = set()
    for record in records:
        cursor = record.get("__CURSOR")
        if cursor is not None:
            if cursor in seen:
                continue
            seen.add(cursor)
        try:
            priority = int(record.get("PRIORITY", 6))
        except (TypeError, ValueError):
            priority = 6
        level = exporter.TEXT_LEVEL_RE.match(str(record.get("MESSAGE") or ""))
        level_name = level.group(1) if level else None
        is_error = priority <= 3 or level_name in exporter.TEXT_ERROR_LEVELS
        is_warning = priority == 4 or level_name in exporter.TEXT_WARNING_LEVELS
        if not (is_error or is_warning):
            continue
        unit = exporter._LABEL_SAFE.sub("_", exporter.entry_unit(record))[:80]
        counts[(1 if is_error else 0, unit)] += 1
    return counts


def _as_trimmed(record):
    """A record as --output-fields= delivers it: only the requested fields."""
    return {k: record[k] for k in exporter.JOURNAL_FIELDS if k in record}


def test_fixture_counts_identical_full_vs_trimmed():
    """Full-field and --output-fields-trimmed rows of the same logical journal
    must produce identical counts -- the fields the counter reads are all
    present in the projection."""
    emitted = [r for r in FIXTURE_RECORDS if _pass_emitted(r)]
    full = _count(iter(emitted))
    trimmed = _count(_as_trimmed(r) for r in emitted)
    assert full == trimmed == EXPECTED_COUNTS


def test_fixture_dedup_cursors():
    """The prio-3 stdout record appears in both passes on the real journal;
    feeding it twice must still count once."""
    emitted = [r for r in FIXTURE_RECORDS if _pass_emitted(r)]
    doubled = emitted + [dict(emitted[0])]
    assert _count(iter(doubled)) == EXPECTED_COUNTS


def test_collect_streaming_counts(tmp_path, monkeypatch):
    """End-to-end through a fake journalctl: same fixture, same counts, and
    the pass-2 argv carries the indexed transport filter + output fields."""

    fake = tmp_path / "journalctl"
    fixture_jsonl = tmp_path / "journal.jsonl"
    fixture_jsonl.write_text("\n".join(json.dumps(r) for r in FIXTURE_RECORDS) + "\n")
    fake.write_text(
        "#!/usr/bin/env python3\n"
        "import json, sys\n"
        "sys.stderr.write('ARGS ' + json.dumps(sys.argv[1:]) + '\\n')\n"
        "args = sys.argv[1:]\n"
        f"fixture = {str(fixture_jsonl)!r}\n"
        "if '-n' in args:\n"
        "    print(json.dumps({'MESSAGE': 'x', 'PRIORITY': '6'}))\n"
        "elif '-g' in args:\n"
        "    for line in open(fixture):\n"
        "        rec = json.loads(line)\n"
        "        msg = rec.get('MESSAGE') or ''\n"
        "        if rec.get('_TRANSPORT') == 'stdout' and any(\n"
        "            msg.startswith('[' + lv + ']')\n"
        "            for lv in ('WARNING', 'WARN', 'ERROR', 'CRITICAL', 'FATAL')\n"
        "        ):\n"
        "            print(json.dumps(rec))\n"
        "elif '-p' in args and 'err' in args:\n"
        "    for line in open(fixture):\n"
        "        rec = json.loads(line)\n"
        "        if int(rec.get('PRIORITY', 6)) <= 3:\n"
        "            print(json.dumps(rec))\n"
    )
    fake.chmod(fake.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    monkeypatch.setenv("PATH", f"{tmp_path}:{os.environ['PATH']}")
    monkeypatch.setenv("AITBC_TEXTFILE_DIR", str(tmp_path))

    assert exporter.main() == 0
    prom = (tmp_path / exporter.OUTPUT_NAME).read_text()
    for (is_error, unit), count in EXPECTED_COUNTS.items():
        metric = "aitbc_journal_error_messages" if is_error else "aitbc_journal_warning_messages"
        assert f'{metric}{{unit="{unit}"}} {count}' in prom
    assert "aitbc_journal_scan_success 1" in prom


def test_g_pass_uses_indexed_transport_and_field_projection(tmp_path, monkeypatch):
    """The -g pass must be pre-narrowed by the indexed _TRANSPORT match and
    every pass must request --output-fields -- the two properties that keep
    a chatty 15-minute window from ballooning the journalctl child."""

    argv_seen: list[list[str]] = []

    def fake_popen(argv, **kwargs):
        argv_seen.append(argv)
        # A real pipe whose write end is already closed: select() reports it
        # readable (EOF) and readline() returns "", so the streaming loop
        # terminates exactly as it would on an empty journal window.
        rfd, wfd = os.pipe()
        os.close(wfd)

        class _Proc:
            returncode = 0
            stdout = os.fdopen(rfd, "r")
            stderr = None

            def wait(self, timeout=None):
                return 0

            def kill(self):
                return None

        return _Proc()

    # The reachable check still uses subprocess.run; leave it functional by
    # stubbing the journald-probe call too.
    monkeypatch.setattr(exporter.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(
        exporter,
        "_journald_reachable",
        lambda: True,
    )
    exporter.collect("15 minutes ago")

    g_pass = [a for a in argv_seen if "-g" in a]
    assert g_pass, "expected a -g pass"
    for argv in argv_seen:
        assert any(a.startswith("--output-fields=") for a in argv), argv
    for argv in g_pass:
        assert "_TRANSPORT=stdout" in argv, argv
