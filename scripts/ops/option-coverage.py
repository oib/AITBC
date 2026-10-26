#!/usr/bin/env python3
"""Option-level scenario coverage census -> tasks/progress/SCENARIO-COVERAGE-OPTIONS.md.

For every visible, non-deprecated CLI leaf, list each option (--flags and
arguments) and mark whether any scenario command line exercises it.
Inputs: SCENARIO-PLAY-1 census.json (verdicts + resolved leaf paths from
census.py) and the newest cli-tree-<sha>.json dump. Staging only; docs-only
output, no live-node contact.
"""

import argparse
import json
import glob
import re
import shlex
import collections
import os
import sys

BASE = os.path.join(os.path.dirname(__file__), "..", "..")
P1 = os.path.join(BASE, "tasks/progress/SCENARIO-PLAY-1")


def _die(msg):
    sys.exit(f"option-coverage: {msg}")


ap = argparse.ArgumentParser(description="Option-level scenario coverage census")
ap.add_argument("--census", default=os.path.join(P1, "census.json"))
ap.add_argument(
    "--plays", default=os.path.join(P1, "plays*.json"), help="glob of extra play-row files merged into the census (default on)"
)
ap.add_argument(
    "--tree", default=None, help="cli-tree json; default = newest cli-tree-*.json under tasks/progress/SCENARIO-PLAY-1"
)
ap.add_argument("--out", default=os.path.join(BASE, "tasks/progress/SCENARIO-COVERAGE-OPTIONS.md"))
ap.add_argument(
    "--exclusions",
    default=os.path.join(BASE, "scripts/ops/option-coverage-exclusions.json"),
    help="leaf -> reason map; every option in a listed leaf is reported as unplayable:<reason> (UNPLAYABLE-TAG-1)",
)
a = ap.parse_args()

EXCLUSIONS = {}
if os.path.exists(a.exclusions):
    EXCLUSIONS = json.load(open(a.exclusions))

tree_path = a.tree
if tree_path is None:
    trees = sorted(glob.glob(os.path.join(P1, "cli-tree-*.json")))
    if not trees:
        _die(f"no cli-tree-*.json under {P1} — pass --tree")
    tree_path = trees[-1]
for p in (tree_path, a.census):
    if not os.path.exists(p):
        _die(f"missing input {p} — run the SCENARIO-PLAY-1 census first or pass --census/--tree")
TREE = json.load(open(tree_path))
CENSUS = json.load(open(a.census))
import glob as _glob

for _f in sorted(_glob.glob(a.plays)):
    if _f != a.census:
        CENSUS.extend(json.load(open(_f)))
OUT = a.out

SECRET_RE = re.compile(r"password|private[-_]?key|secret|seed|mnemonic", re.I)

# ---- leaf inventory -------------------------------------------------------
leaves = {}  # path-str -> node


def walk(n):
    ch = n.get("children") or {}
    if ch:
        for c in ch.values():
            walk(c)
    elif not n["hidden"] and not n["deprecated"] and len(n["path"]) > 1:
        leaves[" ".join(n["path"][1:])] = n


walk(TREE)

# ---- per-leaf option table ------------------------------------------------
# leaf -> option-name -> {'param':p, 'exercised':bool, 'secret':bool}
opt_state = {p: {} for p in leaves}
for path, node in leaves.items():
    for p in node["params"]:
        opt_state[path][p["name"]] = {
            "param": p,
            "exercised": False,
            "secret": bool(SECRET_RE.search(p["name"]) or any(SECRET_RE.search(o) for o in p["opts"])),
        }

# ---- re-tokenize census commands (same logic as census.py) ----------------
root_opts = {o for p in TREE["params"] for o in p["opts"]}
root_val = {o for p in TREE["params"] if not p["flag"] and p["kind"] == "Option" for o in p["opts"]}


def toks_of(cmd):
    line = re.sub(r"^\$\s*", "", cmd)
    line = re.split(r"\s*(?:\||&&|;|>|2>&1)\s*", line)[0] if not line.startswith("#") else line
    m = re.search(r"(?:^|\s|=|\()aitbc\s+(.*)$", line)
    if not m or line.startswith("#"):
        return None
    rest = m.group(1)
    rest = re.sub(r"\s+#.*$", "", rest)
    rest = re.sub(r"\s*&$", "", rest)
    try:
        return shlex.split(rest, comments=False)
    except Exception:
        return rest.split()


def leaf_tokens(toks):
    """Return (node, remaining tokens after the leaf path) or (None, toks)."""
    node = TREE
    j = 0
    while j < len(toks) and toks[j].startswith("-"):
        j += 2 if toks[j] in root_val else 1
    while "children" in node:
        if j >= len(toks):
            return None, toks
        t = toks[j]
        if t.startswith("-"):
            if t in root_val:
                j += 2
            elif t in root_opts:
                j += 1
            else:
                return None, toks
            continue
        if t in node["children"]:
            node = node["children"][t]
            j += 1
        else:
            return None, toks
    return node, toks[j:]


exercised_by = collections.defaultdict(set)  # (path, optname) -> scenarios
for row in CENSUS:
    if row["verdict"] != "ok" or not row.get("path"):
        continue
    path = row["path"]
    if path not in leaves:
        continue
    toks = toks_of(row["cmd"])
    if not toks:
        continue
    node, rest = leaf_tokens(toks)
    if node is None or " ".join(node["path"][1:]) != path:
        continue
    optmap = {}
    for p in node["params"]:
        for o in p["opts"]:
            optmap[o] = p["name"]
    pos = 0
    args = [p for p in node["params"] if p["kind"] == "Argument"]
    for t in rest:
        if t.startswith("-") and len(t) > 1 and not re.match(r"^-\d", t):
            name = t.split("=")[0]
            if name in optmap:
                exercised_by[(path, optmap[name])].add(row["scenario"])
        else:
            if pos < len(args):
                exercised_by[(path, args[pos]["name"])].add(row["scenario"])
            pos += 1
for (path, name), scs in exercised_by.items():
    opt_state[path][name]["exercised"] = True
    opt_state[path][name]["scenarios"] = sorted(scs)

# ---- stats ----------------------------------------------------------------
tot_opt = tot_ex = tot_req_unex = tot_sec_unex = 0
excl_groups = collections.defaultdict(int)
by_group = collections.defaultdict(lambda: [0, 0, 0, 0])  # opt, exercised, req-unex, secret
lines = []
lines += [
    "# SCENARIO-COVERAGE-OPTIONS — option-level census",
    "",
    "Generated by `scripts/ops/option-coverage.py` from "
    "SCENARIO-PLAY-1 `census.json` + newest `cli-tree-*.json`. "
    "Docs/staging analysis only — no live nodes touched.",
    "",
    "A leaf option counts as **exercised** when at least one scenario "
    "command line with verdict `ok` passes it (arguments count when a "
    "positional value is present). Options named like secrets "
    "(`password`/`private_key`/…) are marked 🔒 and their "
    "non-exercise is expected — docs should not embed secret values.",
    "",
]

leaf_rows = []
for path in sorted(leaves):
    node = leaves[path]
    params = [p for p in node["params"] if p["name"] != "help"]
    rows = []
    for p in params:
        st = opt_state[path][p["name"]]
        tot_opt += 1
        g = path.split()[0]
        by_group[g][0] += 1
        if st["exercised"]:
            tot_ex += 1
            by_group[g][1] += 1
        else:
            if st["secret"]:
                tot_sec_unex += 1
                by_group[g][3] += 1
            elif p["required"]:
                tot_req_unex += 1
                by_group[g][2] += 1
        rows.append((p, st))
    leaf_rows.append((path, rows))
    if path in EXCLUSIONS:
        excl_groups[path.split()[0]] += sum(1 for _, st in rows if not st["exercised"])

lines += [
    "## Headline",
    "",
    f"- Visible, non-deprecated leaves: **{len(leaves)}**",
    f"- Options + arguments total: **{tot_opt}**",
    f"- Exercised by ≥1 scenario: **{tot_ex}** ({tot_ex * 100 // max(tot_opt, 1)}%)",
    f"- Never exercised: **{tot_opt - tot_ex}** — {tot_opt - tot_ex - tot_sec_unex} real gap; "
    f"{tot_sec_unex} secret-value options are intentionally uncovered (SECRET-EXCL-1)",
    f"- **Required options with no exercised example: {tot_req_unex}** — the primary doc-gap class",
    "",
    "## Per-group breakdown",
    "",
    "| group | options | exercised | uncovered (non-secret) | secret-excluded | required unexercised | unplayable |",
    "|---|---|---|---|---|---|---|",
]
for g in sorted(by_group):
    o, e, r, s = by_group[g]
    x = excl_groups.get(g, 0)
    lines.append(f"| `{g}` | {o} | {e} | {o - e - s - x} | {s} | {r} | {x} |")
lines += [
    "",
    "## Per-leaf detail",
    "",
    "Legend: ✅ exercised (scenarios listed) · ❌ never exercised · "
    "🔒 secret-value · **(required)** flag/argument the CLI demands.",
    "",
]
excluded_leaf = {}
tot_excl = 0
for path, rows in leaf_rows:
    ex = EXCLUSIONS.get(path)
    if ex:
        excluded_leaf[path] = ex.get("reason", "unspecified")
        tot_excl += sum(1 for _, st in rows if not st["exercised"])
        lines.append(f"### `aitbc {path}` — unplayable: {excluded_leaf[path]}")
    else:
        lines.append(f"### `aitbc {path}`")
    if not rows:
        lines.append("_(no options)_")
    else:
        lines.append("| option | kind | required | status | scenarios |")
        lines.append("|---|---|---|---|---|")
        for p, st in rows:
            label = ", ".join(f"`{o}`" for o in p["opts"]) or f"`{p['name']}`"
            flags = ("🔒 " if st["secret"] else "") + ("**required**" if p["required"] else "")
            status = "✅" if st["exercised"] else "❌"
            scs = ", ".join(st.get("scenarios", [])) or "—"
            lines.append(f"| {label} | {p['kind']} | {flags or '—'} | {status} | {scs} |")
    lines.append("")
open(OUT, "w").write("\n".join(lines) + "\n")
print(
    f"leaves={len(leaves)} opts={tot_opt} exercised={tot_ex} "
    f"unexercised={tot_opt - tot_ex} req_unex={tot_req_unex} secret_unex={tot_sec_unex}"
)
for g in sorted(by_group, key=lambda g: -by_group[g][2])[:10]:
    o, e, r, sec = by_group[g]
    print(f"{g}: {e}/{o} exercised, {r} required-unexercised, {sec} secret-excluded")
