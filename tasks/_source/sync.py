#!/usr/bin/env python3
"""Sync register rows and their Gitea issues (GITEA-TASKING-1, P1/P2; director tooling, staging only).

  sync.py push [ROW ...] [--dry-run]   register -> issue: row card in the body, one owner/* and one state/* label
  sync.py pull [ROW ...] [--dry-run]   issue -> register: card edits and owner/state label changes made on Gitea
  sync.py diff [ROW ...]               read-only: what push would change
  sync.py adopt <n> [...] [--dry-run]  import a Gitea-created issue (aitbc-row card in the body) into the register

Default rows: every open row with an issue. Text outside the card markers is never rewritten, labels other than
owner/* and state/* are never touched, and a second push changes nothing. During the transition the register is
the source and finding.py, row.py and close.py push after each write; pull brings back what was edited on Gitea.

Merge base: sync-state.json keeps, per row, the hash of the card and the labels of the last push. pull takes a
Gitea change only when the register still matches that base; when both sides changed it refuses the row (conflict).
"""

import argparse
import glob
import hashlib
import json
import os
import subprocess
import sys
from issue import tea
import rowcard

HERE = os.path.dirname(os.path.abspath(__file__))
P = os.path.join(HERE, "tasks.json")
STATE = os.path.join(HERE, "sync-state.json")
PY = "/opt/aitbc/venv/bin/python"


def card_hash(f):
    """Order-insensitive hash of a row's card fields (the merge base for pull)."""
    return hashlib.sha256(json.dumps(f, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]


def label_ids():
    out, page = {}, 1
    while True:
        got = tea(f"/labels?limit=50&page={page}")
        if not got:
            return out
        for lbl in got:
            out.setdefault(lbl["name"], lbl["id"])  # duplicate names (needs-verify 58/63): the older id wins
        page += 1


def load_rows():
    return json.load(open(P))


def pick(rows, ids):
    if ids:
        by = {r["id"]: r for r in rows}
        missing = [i for i in ids if i not in by]
        if missing:
            sys.exit(f"no such row(s): {', '.join(missing)}")
        sel = [by[i] for i in ids]
    else:
        sel = [r for r in rows if r.get("status") != "closed"]
    nolink = [r["id"] for r in sel if not r.get("issue")]
    if nolink:
        print(f"skipped (no issue): {', '.join(nolink)}")
    return [r for r in sel if r.get("issue")]


def plan_push(row, iss):
    """(new body or None, labels to add, label names to remove) for one row."""
    body = (iss.get("body") or "").replace("\r\n", "\n")
    new = rowcard.splice(body, rowcard.render(row))
    names = {lbl["name"] for lbl in iss.get("labels") or []}
    owner, state = rowcard.expected_labels(row, names)
    want = {x for x in (owner, state) if x}
    have = set(rowcard.scoped(names, "owner") + rowcard.scoped(names, "state"))
    return (new if new != body else None), sorted(want - have), sorted(have - want), owner, state


def push(rows, dry, quiet=False):
    ids = None
    st = json.load(open(STATE)) if os.path.exists(STATE) else {}
    changed = 0
    for r in rows:
        n = r["issue"]
        iss = tea(f"/issues/{n}")
        new, add, rem, owner, state = plan_push(r, iss)
        what = (["body"] if new else []) + [f"+{x}" for x in add] + [f"-{x}" for x in rem]
        note = "" if r.get("owner") in rowcard.OWNERS else f" (owner {r.get('owner')!r} has no label)"
        if not what:
            if not quiet:
                print(f"{r['id']} #{n}: in sync{note}")
            if not dry:
                st[r["id"]] = {"card": card_hash(rowcard.fields(r)), "owner": owner, "state": state}
            continue
        changed += 1
        print(f"{r['id']} #{n}: {' '.join(what)}{note}" + (" (dry-run)" if dry else ""))
        if dry:
            continue
        ids = ids or label_ids()
        _apply_push(r, n, new, add, rem, ids)
        st[r["id"]] = {"card": card_hash(rowcard.fields(r)), "owner": owner, "state": state}
    if not dry:
        json.dump(st, open(STATE, "w"), indent=1, sort_keys=True)
    print(f"push: {len(rows)} row(s), {changed} changed" + (" (dry-run)" if dry else ""))
    return changed


def _apply_push(r, n, new, add, rem, ids):
    """Write one row's body/label diff to Gitea and verify the read-back."""
    if new:
        tea(f"/issues/{n}", "PATCH", {"body": new})
    if add:
        tea(f"/issues/{n}/labels", "POST", {"labels": [ids[x] for x in add]})
    for x in rem:
        tea(f"/issues/{n}/labels/{ids[x]}", "DELETE")
    back = tea(f"/issues/{n}")
    names = {lbl["name"] for lbl in back.get("labels") or []}
    ok = (
        rowcard.parse(back.get("body")) == rowcard.fields(r)
        and all(x in names for x in add)
        and not any(x in names for x in rem)
    )
    if not ok:
        sys.exit(f"{r['id']} #{n}: read-back differs after push; check the issue by hand")


def _pull_update(r, iss, base):
    """(new row or None, conflict message or None): what pull would take from one issue."""
    n = r["issue"]
    card = rowcard.parse(iss.get("body"))
    names = {lbl["name"] for lbl in iss.get("labels") or []}
    if card is None or base is None:
        print(f"{r['id']} #{n}: no card or never pushed; push it first")
        return None, None
    reg_moved = card_hash(rowcard.fields(r)) != base["card"]
    new = dict(r)
    if card_hash(card) != base["card"]:
        if reg_moved:
            return (
                None,
                f"{r['id']} #{n}: card edited on Gitea and register changed since the last push ({', '.join(rowcard.diff(card, r))})",
            )
        new = dict(card, issue=n)
    owners, states = rowcard.scoped(names, "owner"), rowcard.scoped(names, "state")
    if len(owners) == 1 and owners[0] != base.get("owner"):
        new["owner"] = owners[0].split("/", 1)[1]
    if len(states) == 1 and states[0] != base.get("state") and states[0] in ("state/held", "state/ready"):
        new["ready"] = states[0] == "state/ready"
    return (new if rowcard.diff(rowcard.fields(new), r) else None), None


def pull(rows, dry):
    st = json.load(open(STATE)) if os.path.exists(STATE) else {}
    alls = load_rows()
    updates, conflicts = {}, []
    for r in rows:
        n = r["issue"]
        iss = tea(f"/issues/{n}")
        base = st.get(r["id"])
        new, conflict = _pull_update(r, iss, base)
        if conflict:
            conflicts.append(conflict)
        if new is not None:
            updates[r["id"]] = new
            d = rowcard.diff(rowcard.fields(new), r)
            print(f"{r['id']} #{n}: from Gitea: {', '.join(d)}" + (" (dry-run)" if dry else ""))
    for c in conflicts:
        print("CONFLICT", c)
    if updates and not dry:
        nums = [int(f[len(P) + 6 :]) for f in glob.glob(P + ".bak-s*") if f[len(P) + 6 :].isdigit()]
        bak = f"{P}.bak-s{max(nums, default=0) + 1}"
        open(bak, "w").write(open(P).read())
        json.dump([updates.get(x["id"], x) for x in alls], open(P, "w"), indent=2, ensure_ascii=False)
        open(P, "a").write("\n")
        for old in sorted(
            (f for f in glob.glob(P + ".bak-s*") if f[len(P) + 6 :].isdigit()), key=os.path.getmtime, reverse=True
        )[10:]:
            os.remove(old)
        print(f"register updated ({len(updates)} row(s)); backup {os.path.basename(bak)}")
        push([updates[k] for k in updates], dry=False, quiet=True)  # re-base: the pulled state is the new last push
        g = subprocess.run([PY, os.path.join(HERE, "generate.py")], cwd=HERE, capture_output=True, text=True, timeout=180)
        tail = (g.stdout or g.stderr).strip().splitlines()
        print(f"generate.py rc={g.returncode}: {tail[-1][:120] if tail else ''}")
    print(f"pull: {len(rows)} row(s), {len(updates)} update(s), {len(conflicts)} conflict(s)" + (" (dry-run)" if dry else ""))
    return 1 if conflicts else 0


def adopt(refs, dry):
    """Import Gitea-created issues (row card in the body, no register row) into tasks.json."""
    alls = load_rows()
    by = {r["id"]: r for r in alls}
    st = json.load(open(STATE)) if os.path.exists(STATE) else {}
    for t in refs:
        n = int(str(t).lstrip("#"))
        if any(r.get("issue") == n for r in alls):
            print(f"#{n}: already linked to a register row; skipped")
            continue
        iss = tea(f"/issues/{n}")
        card = rowcard.parse(iss.get("body"))
        if card is None:
            print(f"#{n}: no aitbc-row card in the body; skipped")
            continue
        rid = card.get("id") or f"ISSUE-{n}"
        card["issue"] = n
        names = {lbl["name"] for lbl in iss.get("labels") or []}
        owners, states = rowcard.scoped(names, "owner"), rowcard.scoped(names, "state")
        if len(owners) == 1:
            card["owner"] = owners[0].split("/", 1)[1]
        if len(states) == 1 and states[0] in ("state/held", "state/ready", "state/working"):
            card["ready"] = states[0] != "state/held"
        verb = "update" if rid in by else "import"
        print(f"#{n} -> {rid}: {verb}" + (" (dry-run)" if dry else ""))
        if dry:
            continue
        if rid in by:
            by[rid].update(card)
        else:
            alls.append(card)
            by[rid] = card
        st[rid] = {
            "card": card_hash(rowcard.fields(card)),
            "owner": owners[0] if len(owners) == 1 else None,
            "state": states[0] if len(states) == 1 else None,
        }
    if not dry:
        bak = P + ".bak-adopt"
        open(bak, "w").write(open(P).read())
        json.dump(alls, open(P, "w"), indent=2, ensure_ascii=False)
        open(P, "a").write("\n")
        json.dump(st, open(STATE, "w"), indent=1, sort_keys=True)
        print(f"register written; backup {os.path.basename(bak)}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["push", "pull", "diff", "adopt"])
    ap.add_argument("rows", nargs="*")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    if a.cmd == "adopt":
        if not a.rows:
            sys.exit("adopt needs at least one issue number")
        adopt(a.rows, a.dry_run)
        sys.exit(0)
    sel = pick(load_rows(), a.rows)
    if a.cmd == "pull":
        sys.exit(pull(sel, a.dry_run))
    push(sel, dry=a.dry_run or a.cmd == "diff")
