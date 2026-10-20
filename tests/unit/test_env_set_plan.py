"""RESET-ENVAPPLY-1 (#341) — env-set-plan.py unit tests.

Coverage per the approved list: doc↔JSON drift, canned-file planning,
secret/mislabeled-name protection, drop/drop-if-matches, per-host value
maps, carrying-scope resolution, verify PASS/FAIL without values,
unknown names untouched, and the no-write guarantee.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import importlib.util

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_esp():
    p = REPO_ROOT / "scripts" / "ops" / "env-set-plan.py"
    spec = importlib.util.spec_from_file_location("env_set_plan", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


esp = _load_esp()

SET_PATH = REPO_ROOT / "docs" / "deployment" / "bc2-environment-set.json"
DOC_PATH = REPO_ROOT / "docs" / "deployment" / "bc2-environment-set.md"


@pytest.fixture()
def spec() -> dict:
    return json.loads(SET_PATH.read_text())


@pytest.fixture()
def host_dir(tmp_path: Path) -> Path:
    """A canned /etc/aitbc-like env dir on 'node2'."""
    (tmp_path / "blockchain.env").write_text(
        "CHAIN_ID=ait-hub.aitbc.bubuit.net\n"
        "SUPPORTED_CHAINS=ait-hub.aitbc.bubuit.net\n"
        "STATE_TRANSITION_V2_HEIGHT=12\n"
        "VALIDATOR_SET=[{...}]\n"
        "GPU_RETIRED_IDS=0xaaaa\n"
    )
    (tmp_path / "blockchain-secrets.env").write_text("VALIDATOR_KEYS={...}\nBLOCKCHAIN_RPC_API_KEY=fake-key-material\n")
    (tmp_path / "aitbc-blockchain-node.env").write_text(
        "ENABLE_BLOCK_PRODUCTION=false\nAUTO_SYNC_THRESHOLD=10\nGOSSIP_BACKEND=mesh\n"
    )
    (tmp_path / "aitbc-blockchain-rpc.env").write_text("ENABLE_BLOCK_PRODUCTION=true\nGOSSIP_BACKEND=mesh\n")
    (tmp_path / "aitbc-coordinator-api.env").write_text(
        "CHAIN_ID=ait-hub.aitbc.bubuit.net\nNATIVE_CHAIN_ID=ait-hub.aitbc.bubuit.net\n"
        "GOSSIP_WEBSOCKET_URL=wss://hub.example.net/ws\n"
    )
    return tmp_path


def _view(d: Path, spec: dict) -> esp.HostView:
    return esp.load_local(d, spec["units"])


def _plan_text(view: esp.HostView, spec: dict, host: str = "node2") -> str:
    lines, _ = esp.plan(view, spec["rows"], host)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Doc ↔ JSON drift
# ---------------------------------------------------------------------------


def _doc_rows() -> tuple[dict[str, set[str]], set[str]]:
    """(name -> all literal values in its doc value cells, names whose value
    cell is exactly one literal). Ranges (`X … Y`) and multi-name cells
    (`A` / `B`) expand to each name."""
    import re

    literals: dict[str, set[str]] = {}
    pure_literal_rows: set[str] = set()
    for line in DOC_PATH.read_text().splitlines():
        m = re.match(r"^\|\s*(.*?)\s*\|\s*(.*?)\s*\|", line)
        if not m or m.group(1).startswith("-"):
            continue
        name_cell, value_cell = m.group(1), m.group(2)
        names = re.findall(r"`([A-Z_][A-Z0-9_]*)`", name_cell)
        rng = re.match(r"`([A-Z_]*?)(\d+)([A-Z_]*)`\s*…\s*`([A-Z_]*?)(\d+)([A-Z_]*)`", name_cell)
        if rng and rng.group(1) == rng.group(4) and rng.group(3) == rng.group(6):
            names = [f"{rng.group(1)}{i}{rng.group(3)}" for i in range(int(rng.group(2)), int(rng.group(5)) + 1)]
        cell_literals = set(re.findall(r"`([^`]+)`", value_cell))
        for n in names:
            literals.setdefault(n, set()).update(cell_literals)
        if re.match(r"^`[^`]+`(?:\s+each)?$", value_cell):
            pure_literal_rows.update(names)
    return literals, pure_literal_rows


def _expand_ranges(names: set[str], text: str) -> set[str]:
    """Expand `PREFIX2_NAME … PREFIX14_NAME` style ranges in doc cells."""
    import re

    out = set(names)
    for m in re.finditer(r"`([A-Z_]*?)(\d+)([A-Z_]*)`\s*…\s*`([A-Z_]*?)(\d+)([A-Z_]*)`", text):
        if m.group(1) == m.group(4) and m.group(3) == m.group(6):
            for i in range(int(m.group(2)), int(m.group(5)) + 1):
                out.add(f"{m.group(1)}{i}{m.group(3)}")
    return out


def test_structured_file_matches_doc(spec):
    import re

    doc_text = DOC_PATH.read_text()
    doc_names = _expand_ranges(set(re.findall(r"`([A-Z_][A-Z0-9_]*)`", doc_text)), doc_text)
    rows = spec["rows"]
    # every JSON name is named in the doc
    for row in rows:
        assert row["name"] in doc_names, f"{row['name']} not named in the doc"
    # public values agree with the doc literals for that name
    doc_literals, pure_literal_rows = _doc_rows()
    for row in rows:
        if row.get("class") != "public" or row.get("op") != "set":
            continue
        v = row.get("value")
        values = list(v.values()) if isinstance(v, dict) else [v]
        for want in values:
            if want in ("operator-supplied", None):
                continue
            assert row["name"] in doc_literals, f"{row['name']}: no literal value in doc"
            assert str(want) in doc_literals[row["name"]], (
                f"{row['name']}: JSON {want} not among doc literals {doc_literals[row['name']]}"
            )
    # every doc row whose name AND value cells are both literal is covered
    json_names = {r["name"] for r in rows}
    for name in pure_literal_rows:
        assert name in json_names, f"doc literal {name} missing from JSON"


def test_json_rows_are_wellformed(spec):
    for row in spec["rows"]:
        assert row["name"].isupper()
        assert row.get("op", "set") in {"set", "drop", "drop-if-matches", "keep", "none"}
        if row.get("op") == "drop-if-matches":
            assert row.get("match")
        assert row.get("class") in {None, "public", "secret", "operator", "wiring", "carry"}


# ---------------------------------------------------------------------------
# Plan on canned files
# ---------------------------------------------------------------------------


def test_plan_on_canned_files(host_dir, spec, capsys):
    rc = esp.main(["plan", "--set", str(SET_PATH), "--local", str(host_dir), "--name", "node2"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "== node2 ==" in out
    # public rows show the old literal -> new literal
    assert "CHAIN_ID" in out and "bc-2" in out
    assert "ait-hub.aitbc.bubuit.net" in out  # old value of a public row
    # node0-explicit pins read as edits on node2 too
    assert "AUTO_SYNC_THRESHOLD" in out and "-> 0" in out


def test_secret_names_never_print_values(host_dir, spec, capsys):
    esp.main(["plan", "--set", str(SET_PATH), "--local", str(host_dir), "--name", "node2"])
    out = capsys.readouterr().out
    assert "fake-key-material" not in out
    assert "{...}" not in out  # VALIDATOR_KEYS / VALIDATOR_SET contents
    assert "<present>" in out or "<unset>" in out


def test_mislabeled_secret_looking_name_stays_hidden(spec, host_dir, capsys):
    (host_dir / "aitbc-blockchain-node.env").write_text(
        (host_dir / "aitbc-blockchain-node.env").read_text() + "PROPOSER_KEY=0xdeadbeef\n"
    )
    rows = spec["rows"] + [
        {"name": "PROPOSER_KEY", "op": "set", "value": "0xfeed", "scope": "units:aitbc-blockchain-node", "class": "public"}
    ]
    esp.plan(esp.load_local(host_dir, spec["units"]), rows, "node2")
    out = capsys.readouterr().out
    assert "0xdeadbeef" not in out
    assert not esp.printable(rows[-1])


def test_verify_prints_no_values(host_dir, spec, capsys):
    esp.main(["verify", "--set", str(SET_PATH), "--local", str(host_dir)])
    out = capsys.readouterr().out
    assert "fake-key-material" not in out
    assert "ait-hub.aitbc.bubuit.net" not in out  # verify never prints values
    assert "0xdeadbeef" not in out


# ---------------------------------------------------------------------------
# Ops
# ---------------------------------------------------------------------------


def test_drop_and_drop_if_matches(host_dir, spec):
    view = _view(host_dir, spec)
    rows = [
        {"name": "NATIVE_CHAIN_ID", "op": "drop", "scope": "units:aitbc-coordinator-api", "hosts": ["hub"]},
        {"name": "GOSSIP_WEBSOCKET_URL", "op": "drop-if-matches", "match": "wss://hub.example.net", "scope": "carrying"},
    ]
    lines, _ = esp.plan(view, rows, "hub")
    text = "\n".join(lines)
    assert "DROP" in text
    assert "wss://hub.example.net" in text
    # host filter: node2 has no NATIVE_CHAIN_ID drop row
    lines2, _ = esp.plan(view, rows, "node2")
    assert "NATIVE_CHAIN_ID" not in "\n".join(lines2)
    # verify: drops currently FAIL (name still present/matching)
    vlines, fails = esp.verify(view, rows, "hub")
    assert fails >= 2


def test_per_host_value_map(host_dir):
    rows = [
        {
            "name": "ENABLE_BLOCK_PRODUCTION",
            "op": "set",
            "value": {"hub": "true", "node0": "false", "node2": "true"},
            "scope": "units:aitbc-blockchain-node",
            "class": "public",
        }
    ]
    view = esp.load_local(host_dir, ["aitbc-blockchain-node"])
    for host, want in (("node2", "-> true"), ("node0", "-> false")):
        lines, _ = esp.plan(view, rows, host)
        assert want in "\n".join(lines)
    # a host missing from the map gets a note, not an edit
    lines, issues = esp.plan(view, rows, "hub1")
    assert "no value for host" in "\n".join(lines)


def test_carrying_scope_resolves_files(host_dir, spec):
    view = _view(host_dir, spec)
    row = next(r for r in spec["rows"] if r["name"] == "CHAIN_ID")
    targets, _ = esp.resolve_targets(view, row)
    names = {Path(p).name for p in targets}
    assert names == {"blockchain.env", "aitbc-coordinator-api.env"}
    # carrying never creates a line somewhere it was absent
    assert all(view.presence(p, "CHAIN_ID") for p in targets)


def test_units_scope_uses_unit_exclusive_files(host_dir):
    view = esp.load_local(host_dir, ["aitbc-blockchain-node", "aitbc-blockchain-rpc"])
    row = {"name": "GOSSIP_BACKEND", "op": "set", "value": "redis", "scope": "units:aitbc-blockchain-rpc"}
    targets, _ = esp.resolve_targets(view, row)
    assert targets == [str(host_dir / "aitbc-blockchain-rpc.env")]
    # a shared file (blockchain.env) is never a units-scope target
    row2 = {"name": "X", "op": "set", "value": "1", "scope": "units:aitbc-blockchain-rpc"}
    targets2, notes = esp.resolve_targets(view, row2)
    assert targets2 == [str(host_dir / "aitbc-blockchain-rpc.env")]


def test_verify_counts_and_pass_fail(host_dir, spec, capsys):
    # fixture state fails literal checks (old values) but passes presence
    rc = esp.main(["verify", "--set", str(SET_PATH), "--local", str(host_dir)])
    out = capsys.readouterr().out
    assert rc == 1
    assert "FAIL" in out and "PASS" in out
    assert "literal-match=0" in out


def test_verify_after_ideal_state(tmp_path: Path):
    (tmp_path / "blockchain.env").write_text("CHAIN_ID=bc-2\n")
    rows = [{"name": "CHAIN_ID", "op": "set", "value": "bc-2", "scope": "carrying", "class": "public"}]
    view = esp.load_local(tmp_path, [])
    lines, fails = esp.verify(view, rows, "hub")
    assert fails == 0
    assert "literal-match=1" in "\n".join(lines)


def test_unknown_names_untouched(host_dir, spec):
    view = _view(host_dir, spec)
    row = {"name": "SOME_UNLISTED_NAME", "op": "set", "value": "x", "scope": "carrying"}
    targets, _ = esp.resolve_targets(view, row)
    assert targets == []
    lines, issues = esp.plan(view, [row], "node2")
    assert "no target file resolved" in "\n".join(lines)
    assert issues == 1


# ---------------------------------------------------------------------------
# No-write guarantee
# ---------------------------------------------------------------------------


def test_script_opens_no_env_path_for_writing(host_dir, spec, monkeypatch):
    opened: list[tuple[str, str]] = []
    real_open = open

    def spy(file, mode="r", *a, **kw):
        opened.append((str(file), mode))
        return real_open(file, mode, *a, **kw)

    import builtins

    monkeypatch.setattr(builtins, "open", spy)
    esp.main(["plan", "--set", str(SET_PATH), "--local", str(host_dir)])
    esp.main(["verify", "--set", str(SET_PATH), "--local", str(host_dir)])
    bad = [f for f, m in opened if f.endswith(".env") and any(c in m for c in "wax+")]
    assert bad == [], f"env paths opened for writing: {bad}"


# ---------------------------------------------------------------------------
# Live-mode shape (no ssh in unit tests)
# ---------------------------------------------------------------------------


def test_live_view_is_names_only(spec):
    view = esp.HostView()
    view.add_file("/etc/aitbc/aitbc-blockchain-node.env", {"CHAIN_ID": None, "AUTO_SYNC_THRESHOLD": None})
    view.unit_files["aitbc-blockchain-node"] = ["/etc/aitbc/aitbc-blockchain-node.env"]
    row = {"name": "CHAIN_ID", "op": "set", "value": "bc-2", "scope": "carrying", "class": "public"}
    lines, _ = esp.verify(view, [row], "node2")
    assert "presence-level" in "\n".join(lines)
    plan_lines, _ = esp.plan(view, [row], "node2")
    assert "<present>" in "\n".join(plan_lines)  # live mode shows no old value
