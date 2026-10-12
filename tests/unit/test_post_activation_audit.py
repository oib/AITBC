"""Fixture tests for scripts/ops/post_activation_audit.py (BR-12) — pure logic
only: no network, no ssh, no sqlite. The remote/ssh paths are exercised live
by the script's own dry run, not here."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from datetime import UTC

REPO = Path(__file__).resolve().parents[2]


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


audit = _load("post_activation_audit", REPO / "scripts/ops/post_activation_audit.py")

ACT = 46_100


def test_short_truncates_hashes():
    assert audit.short("0xabcdef0123456789") == "0xabcdef012345"
    assert audit.short("abcdef0123456789") == "abcdef012345"
    assert audit.short(None) == "(empty)"
    assert audit.short("") == "(empty)"


def test_parse_block_meta_accepts_str_dict_none():
    assert audit.parse_block_meta('{"state_transition_version": 14}') == {"state_transition_version": 14}
    assert audit.parse_block_meta({"a": 1}) == {"a": 1}
    assert audit.parse_block_meta(None) == {}
    assert audit.parse_block_meta("") == {}
    assert audit.parse_block_meta("{not json") == {}
    assert audit.parse_block_meta("[1,2]") == {}


def test_lock_leaf_value_matches_v4_format():
    rec = {"transfer_id": "0xabc", "amount": 36000, "target_chain": "ait-shop"}
    assert audit.lock_leaf_value("0xabc", rec) == "lock:0xabc:36000:ait-shop"
    assert audit.lock_leaf_value("0xabc", None) == "lock:0xabc:0:unknown"


def test_version_window_not_yet_then_pass():
    rows = [(ACT - 2, 12), (ACT - 1, 12)]
    assert audit.eval_version_window(rows, ACT)[0] == audit.NOT_YET
    rows = [(ACT - 2, 12), (ACT - 1, 12), (ACT, 14), (ACT + 1, 14)]
    status, _ = audit.eval_version_window(rows, ACT)
    assert status == audit.PASS


def test_version_window_fails_on_wrong_stamp_early_stamp_or_gap():
    assert audit.eval_version_window([(ACT, 13)], ACT)[0] == audit.FAIL
    assert audit.eval_version_window([(ACT - 1, 14), (ACT, 14)], ACT)[0] == audit.FAIL  # pre-H stamped 14
    assert audit.eval_version_window([(ACT + 1, 14)], ACT)[0] == audit.FAIL  # first 14 not at ACT


def test_aux_window_not_yet_then_pass():
    by_host = {"h1": [(ACT - 1, None)], "h2": [(ACT - 1, None)]}
    assert audit.eval_aux_window(by_host, ACT)[0] == audit.NOT_YET
    root = "0x" + "ab" * 32
    by_host = {"h1": [(ACT - 1, None), (ACT, root)], "h2": [(ACT - 1, None), (ACT, root)]}
    assert audit.eval_aux_window(by_host, ACT)[0] == audit.PASS


def test_aux_window_fails_on_pre_h_nonempty_divergence_or_empty_post():
    root = "0x" + "ab" * 32
    assert (
        audit.eval_aux_window({"h1": [(ACT - 1, root), (ACT, root)], "h2": [(ACT - 1, None), (ACT, root)]}, ACT)[0]
        == audit.FAIL
    )
    other = "0x" + "cd" * 32
    assert audit.eval_aux_window({"h1": [(ACT, root)], "h2": [(ACT, other)]}, ACT)[0] == audit.FAIL
    assert audit.eval_aux_window({"h1": [(ACT, root)], "h2": [(ACT, None)]}, ACT)[0] == audit.FAIL


def test_attesters_exact_set():
    assert audit.eval_attesters({"0x19f0", "0x2ad5", "0x5e8e", "0xe894"})[0] == audit.PASS
    assert audit.eval_attesters({"0x19f0", "0x2ad5", "0x5e8e"})[0] == audit.FAIL  # missing one
    assert audit.eval_attesters({"0x19f0", "0x2ad5", "0x5e8e", "0xe894", "0xdead"})[0] == audit.FAIL  # extra


def test_head_rows_same_hash_and_fresh():
    now = 1_800_000_000.0
    ts = "2026-12-31T00:00:00"  # not evaluated against `now` below — see age arg
    heads = {h: {"height": 50, "hash": "0xaa", "timestamp": ts} for h in ("a", "b")}
    # compute `now` from the timestamp so age is small
    from datetime import datetime

    now = datetime.fromisoformat(ts).replace(tzinfo=UTC).timestamp() + 10
    assert audit.eval_head_rows(heads, now)[0] == audit.PASS


def test_head_rows_fails_on_mismatch_and_stale():
    now = 1_800_000_000.0
    heads = {
        "a": {"height": 50, "hash": "0xaa", "timestamp": "2026-12-31T00:00:00"},
        "b": {"height": 50, "hash": "0xbb", "timestamp": "2026-12-31T00:00:00"},
    }
    assert audit.eval_head_rows(heads, now)[0] == audit.FAIL
    stale = {h: {"height": 50, "hash": "0xaa", "timestamp": "2000-01-01T00:00:00"} for h in ("a",)}
    assert audit.eval_head_rows(stale, now)[0] == audit.FAIL
    assert audit.eval_head_rows({}, now)[0] == audit.FAIL


def test_consensus_mismatches_flags_divergent_heights_only():
    per_height = {
        100: {"h1": "fpA", "h2": "fpA"},
        101: {"h1": "fpB", "h2": "fpC"},
    }
    mism = audit.consensus_mismatches(per_height)
    assert len(mism) == 1 and "101" in mism[0]
    assert audit.consensus_mismatches({100: {"h1": "x", "h2": "x"}}) == []


def test_flagged_alert_lines_recent_firing_only():
    now = 1_800_000_000.0
    tail = "\n".join(
        [
            '{"alertname": "OldFire", "state": "firing", "timestamp_unix": 1799999000}',  # 1000s ago — flagged
            '{"alertname": "StaleFire", "state": "firing", "timestamp_unix": 1790000000}',  # old — not flagged
            '{"alertname": "Resolved", "state": "resolved", "timestamp_unix": 1799999000}',
            "2026-10-12 ERROR something broke",  # non-JSON ERROR — flagged
            '{"alertname": "info", "state": "pending", "timestamp_unix": 1799999000}',
        ]
    )
    bad = audit._flagged_alert_lines(tail, now)
    assert len(bad) == 2
    assert any("OldFire" in b for b in bad)
    assert any("ERROR" in b for b in bad)
    assert audit._flagged_alert_lines("", now) == []
