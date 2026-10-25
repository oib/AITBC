#!/usr/bin/env python3
"""Option-level scenario coverage census for the aitbc CLI.

For every visible, non-deprecated CLI leaf, lists each option (--flags and
positional arguments) and marks whether at least one documented scenario
command line in docs/scenarios/ exercises it.  Options that are required but
never exercised are the doc-gap class this census exists to surface.

The script is read-only: it never touches a live node and only writes the
markdown report to --out.  Inputs come from the operator staging checkout
(the SCENARIO-PLAY-1 census verdicts plus the newest cli-tree-*.json dump),
which intentionally lives outside the repository.

Usage:

    python scripts/dev/gen_option_coverage.py \
        --staging-dir /path/to/staging \
        --out /path/to/staging/tasks/progress/SCENARIO-COVERAGE-OPTIONS.md

Defaults assume the staging checkout is the parent of the repository
checkout that contains this script (the IDE worktree-under-staging layout);
pass --staging-dir explicitly when running elsewhere.
"""

from __future__ import annotations

import argparse
import collections
import glob
import json
import os
import re
import shlex
import sys

SECRET_RE = re.compile(r"password|private[-_]?key|secret|seed|mnemonic", re.I)


def default_staging_dir() -> str:
    """First ancestor of this script holding tasks/progress/SCENARIO-PLAY-1."""
    cand = os.path.dirname(os.path.abspath(__file__))
    while True:
        if os.path.isdir(os.path.join(cand, "tasks", "progress", "SCENARIO-PLAY-1")):
            return cand
        parent = os.path.dirname(cand)
        if parent == cand:
            # Fall back to the repository checkout containing this script.
            return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        cand = parent


def toks_of(cmd, root_opts, root_val):
    line = re.sub(r"^\$\s*", "", cmd)
    # Same as census.py: mask <...> placeholders before the shell-operator
    # split, otherwise the '>' inside a placeholder truncates the command.
    line = re.sub(r"<[^<>]*>", "PH", line)
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


def leaf_tokens(toks, tree, root_opts, root_val):
    """Return (node, remaining tokens after the leaf path) or (None, toks)."""
    node = tree
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


def _leaf_inventory(tree) -> dict:
    """path-str -> leaf node for every visible, non-deprecated leaf."""
    leaves = {}

    def walk(n):
        ch = n.get("children") or {}
        if ch:
            for c in ch.values():
                walk(c)
        elif not n["hidden"] and not n["deprecated"] and len(n["path"]) > 1:
            leaves[" ".join(n["path"][1:])] = n

    walk(tree)
    return leaves


def _scan_tokens(path, rest, optmap, pos_args, scenario, exercised_by) -> None:
    """Mark every option/argument present in one command line's tokens."""
    pos = 0
    for t in rest:
        if t.startswith("-") and len(t) > 1 and not re.match(r"^-\d", t):
            name = t.split("=")[0]
            if name in optmap:
                exercised_by[(path, optmap[name])].add(scenario)
        else:
            if pos < len(pos_args):
                exercised_by[(path, pos_args[pos]["name"])].add(scenario)
            pos += 1


def _mark_exercised(census, tree, leaves, opt_state) -> None:
    """Flag each option seen in a verdict-ok scenario command line."""
    root_opts = {o for p in tree["params"] for o in p["opts"]}
    root_val = {o for p in tree["params"] if not p["flag"] and p["kind"] == "Option" for o in p["opts"]}
    exercised_by = collections.defaultdict(set)  # (path, optname) -> scenarios
    for row in census:
        if row["verdict"] != "ok" or not row.get("path"):
            continue
        path = row["path"]
        if path not in leaves:
            continue
        toks = toks_of(row["cmd"], root_opts, root_val)
        if not toks:
            continue
        node, rest = leaf_tokens(toks, tree, root_opts, root_val)
        if node is None or " ".join(node["path"][1:]) != path:
            continue
        optmap = {o: p["name"] for p in node["params"] for o in p["opts"]}
        pos_args = [p for p in node["params"] if p["kind"] == "Argument"]
        _scan_tokens(path, rest, optmap, pos_args, row["scenario"], exercised_by)
    for (path, name), scs in exercised_by.items():
        opt_state[path][name]["exercised"] = True
        opt_state[path][name]["scenarios"] = sorted(scs)


def _report(leaves, opt_state):
    """Return (lines, tot_opt, tot_ex, tot_req_unex, tot_sec_unex, by_group)."""
    tot_opt = tot_ex = tot_req_unex = tot_sec_unex = 0
    by_group = collections.defaultdict(lambda: [0, 0, 0])  # opt, exercised, req-unex
    lines = [
        "# SCENARIO-COVERAGE-OPTIONS — option-level census",
        "",
        "Generated by `scripts/dev/gen_option_coverage.py` from "
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
                elif p["required"]:
                    tot_req_unex += 1
                    by_group[g][2] += 1
            rows.append((p, st))
        leaf_rows.append((path, rows))

    lines += [
        "## Headline",
        "",
        f"- Visible, non-deprecated leaves: **{len(leaves)}**",
        f"- Options + arguments total: **{tot_opt}**",
        f"- Exercised by ≥1 scenario: **{tot_ex}** ({tot_ex * 100 // max(tot_opt, 1)}%)",
        f"- Never exercised: **{tot_opt - tot_ex}** (of which {tot_sec_unex} are 🔒 secret-value options, expected)",
        f"- **Required options with no exercised example: {tot_req_unex}** — the primary doc-gap class",
        "",
        "## Per-group breakdown",
        "",
        "| group | options | exercised | never exercised | required unexercised |",
        "|---|---|---|---|---|",
    ]
    for g in sorted(by_group):
        o, e, r = by_group[g]
        lines.append(f"| `{g}` | {o} | {e} | {o - e} | {r} |")
    lines += [
        "",
        "## Per-leaf detail",
        "",
        "Legend: ✅ exercised (scenarios listed) · ❌ never exercised · "
        "🔒 secret-value · **(required)** flag/argument the CLI demands.",
        "",
    ]
    for path, rows in leaf_rows:
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
    return lines, tot_opt, tot_ex, tot_req_unex, tot_sec_unex, by_group


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument(
        "--staging-dir",
        default=default_staging_dir(),
        help="staging checkout holding tasks/progress/SCENARIO-PLAY-1 (default: repo root or its parent)",
    )
    ap.add_argument("--out", default=None, help="report path (default: <staging>/tasks/progress/SCENARIO-COVERAGE-OPTIONS.md)")
    args = ap.parse_args()

    p1 = os.path.join(args.staging_dir, "tasks", "progress", "SCENARIO-PLAY-1")
    trees = sorted(glob.glob(os.path.join(p1, "cli-tree-*.json")))
    census_path = os.path.join(p1, "census.json")
    if not trees or not os.path.exists(census_path):
        sys.exit(f"missing SCENARIO-PLAY-1 inputs under {p1} (pass --staging-dir)")
    tree = json.load(open(trees[-1]))
    census = json.load(open(census_path))
    out = args.out or os.path.join(args.staging_dir, "tasks", "progress", "SCENARIO-COVERAGE-OPTIONS.md")

    # ---- leaf inventory ----------------------------------------------------
    leaves = _leaf_inventory(tree)  # path-str -> node

    # ---- per-leaf option table ----------------------------------------------
    # leaf -> option-name -> {'param':p, 'exercised':bool, 'secret':bool}
    opt_state = {p: {} for p in leaves}
    for path, node in leaves.items():
        for p in node["params"]:
            opt_state[path][p["name"]] = {
                "param": p,
                "exercised": False,
                "secret": bool(SECRET_RE.search(p["name"]) or any(SECRET_RE.search(o) for o in p["opts"])),
            }

    # ---- re-tokenize census commands (same logic as census.py) ---------------
    _mark_exercised(census, tree, leaves, opt_state)

    # ---- stats + report -------------------------------------------------------
    lines, tot_opt, tot_ex, tot_req_unex, tot_sec_unex, by_group = _report(leaves, opt_state)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w") as fh:
        fh.write("\n".join(lines) + "\n")
    print(
        f"leaves={len(leaves)} opts={tot_opt} exercised={tot_ex} "
        f"unexercised={tot_opt - tot_ex} req_unex={tot_req_unex} secret_unex={tot_sec_unex}"
    )
    for g in sorted(by_group, key=lambda g: -by_group[g][2])[:10]:
        o, e, r = by_group[g]
        print(f"{g}: {e}/{o} exercised, {r} required-unexercised")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
