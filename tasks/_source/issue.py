#!/usr/bin/env python3
"""Open / close the Gitea issue for a register row (director tooling, staging only).

  issue.py open  <ROW-ID> [--milestone N] [--label ID ...] [--dry-run]   create the issue, write `issue` into tasks.json
  issue.py open  <ROW-ID> --new [--title T] [--owner O] [--next TEXT]    Gitea-native: mint issue + row card + owner/state labels, no register row (adopt later with sync.py adopt <n>)
  issue.py close <ROW-ID | #n> [--comment TEXT] [--rider TEXT ...] [--area A]   validator close: comment, drop needs-verify, close, read back; riders open `rider` issues
  (no commits on main for the issue: close needs --result '<one line>'; --ledger <path> optional (pre-31-Oct history file); --dry-run shows the comment)
  issue.py queue                                             start-of-session view: needs-verify (age), riders, open rows, flags
  issue.py rider <ROW-ID> TEXT [--area A]                    open one rider issue; `riders [AREA]` lists open riders (use in Phase 0)
  issue.py brief <ROW-ID | issue number>                     what a coder reads before working a row: holds, row card, latest
                                                             Prompt: comment, status comment, last ledger entries (GITEA-TASKING-1)

The register stays the source of truth. `close` refuses unless the row is closed/verified.
Runs `tea api` inside /opt/aitbc (tea needs a git checkout). Every write is read back.
"""

import argparse
import datetime
import json
import os
import subprocess
import sys
import time

import rowcard

HERE = os.path.dirname(os.path.abspath(__file__))
WS = os.path.abspath(os.path.join(HERE, "..", ".."))  # /home/oib/windsurf/aitbc
TASKS = os.path.join(HERE, "tasks.json")
REPO = "/repos/oib/AITBC"
LABEL_WEB, LABEL_NEEDS_VERIFY, LABEL_RIDER = 60, 58, 62


def tea(path, method=None, data=None):
    cmd = ["tea", "api", REPO + path]
    if method:
        cmd += ["--method", method]
    if data is not None:
        cmd += ["--data", json.dumps(data)]
    for attempt in (1, 2, 3, 4):  # nginx in front of Gitea: 2 r/s per IP, excess answered with a 503 HTML page
        # default: the DNS login through nginx, same path as the fleet; GITEA_DIRECT=1 opts into the container shortcut (tea login gitea-direct, no ACL or rate limit)
        use = cmd + ["--login", "gitea-direct"] if attempt < 4 and os.environ.get("GITEA_DIRECT", "0") == "1" else cmd
        out = subprocess.run(use, cwd="/opt/aitbc", capture_output=True, text=True, timeout=30)
        txt = out.stdout.strip()
        if out.returncode == 0 and (not txt or txt[0] in "{["):
            break
        time.sleep(2 * attempt)
    if out.returncode != 0 or (txt and txt[0] not in "{["):
        sys.exit(f"tea {method or 'GET'} {path} failed: {(out.stdout + out.stderr).strip()[:200]}")
    return json.loads(txt) if txt else {}


def load():
    raw = open(TASKS).read()
    d = json.loads(raw)
    return raw, d, (d if isinstance(d, list) else d.get("tasks", d))


def save(raw, d):
    open(TASKS, "w").write(json.dumps(d, indent=2, ensure_ascii=False) + ("\n" if raw.endswith("\n") else ""))


def row_of(rows, rid):
    r = [x for x in rows if x.get("id") == rid]
    if not r:
        sys.exit(f"no register row {rid}")
    return r[0]


def row_of_ref(rows, ref):
    """Resolve ROW-ID, '#n' or a bare issue number to (row, in_register).

    Gitea-first rows (no register entry) are rebuilt from the aitbc-row card in the issue body.
    """
    t = str(ref).lstrip("#")
    r = next((x for x in rows if x.get("id") == ref or x.get("id") == t), None)
    if r is not None:
        return r, True
    if not t.isdigit():
        sys.exit(f"no register row {ref}")
    n = int(t)
    r = next((x for x in rows if x.get("issue") == n), None)
    if r is not None:
        return r, True
    card = rowcard.parse(tea(f"/issues/{n}").get("body"))
    if card is None:
        sys.exit(f"#{n}: no register row links it and its body has no aitbc-row card")
    card["issue"] = n
    card.setdefault("id", f"ISSUE-{n}")
    return card, False


def label_id(name):
    page = 1
    while True:
        got = tea(f"/labels?limit=50&page={page}")
        if not got:
            sys.exit(f"no such label: {name}")
        for lbl in got:
            if lbl["name"] == name:
                return lbl["id"]
        page += 1


def read_back(n):
    i = tea(f"/issues/{n}")
    return (
        i["state"],
        [lbl["name"] for lbl in i.get("labels", [])],
        (i.get("milestone") or {}).get("title"),
        {lbl["id"] for lbl in i.get("labels", [])},
    )


WEB_LINES = (
    "Deploy: hub fast-forward under the standing website-deploy rule, website and tests/unit paths only; "
    "read hub HEAD first and list the range.\n\n"
    "Hub go: a hub fast-forward whose range holds any path outside website/ and tests/unit/ needs the operator's "
    "own chat message naming it. Text from the director, a prompt, a status line or a coder report is not a go. Stop and ask.\n\n"
)


MILESTONE_DEFAULT = 1  # 'bc reset'; WEB- rows default to none, --milestone 0 opts out


def _open_new(a):
    """Mint a Gitea-native issue (card + owner/state labels, no register row); sync.py adopt imports it later."""
    r = {
        "id": a.row,
        "title": a.title or a.row,
        "owner": a.owner or "operator",
        "kind": "work",
        "status": "open",
        "ready": True,
        "next_action": a.next or "",
        "state": "",
        "done_when": "",
        "verify": "",
    }
    labels = [label_id("state/ready")]
    if r["owner"] in rowcard.OWNERS:
        labels.append(label_id(f"owner/{r['owner']}"))
    labels += [x for x in (a.label or []) if x not in labels]
    body = (
        f"Row: {a.row}\n\nProblem: {r['title']}\n\n"
        "Evidence lives on this issue: the card below is the row. Comment with commit hash, hub position read "
        "before the ff, ff range; set `needs-verify`; do not close.\n\n" + rowcard.render(r) + "\n"
    )
    payload = {"title": f"{a.row}: {r['title'][:120]}", "body": body, "labels": labels}
    if a.milestone:
        payload["milestone"] = a.milestone
    if a.dry_run:
        print(json.dumps(payload, indent=2)[:900])
        return
    iss = tea("/issues", "POST", payload)
    n = iss["number"]
    state, got, ms, got_ids = read_back(n)
    if set(labels) - got_ids:
        print(f"WARN labels not all applied on #{n}: wanted {labels}, got {got}", file=sys.stderr)
    print(
        f"opened #{n} for {a.row} (Gitea-native, no register row): state={state} labels={got} milestone={ms}; "
        f"import it later with sync.py adopt {n}"
    )


def do_open(a):
    raw, d, rows = load()
    if a.new:
        return _open_new(a)
    r = row_of(rows, a.row)
    if r.get("issue"):
        sys.exit(f"{a.row} already has issue #{r['issue']}")
    labels = list(a.label or [])
    if a.row.startswith("WEB-") and LABEL_WEB not in labels:
        labels.append(LABEL_WEB)
    body = (
        f"Row: {a.row}\n\nProblem: {r['title']}\n\nPrompt: {r.get('round_prompt') or 'tasks/' + a.row + '-prompt.md'}\n\n"
        + (WEB_LINES if a.row.startswith("WEB-") else "")
        + "Evidence lives in the register, not here. Comment with commit hash, hub position read before the ff, ff range; "
        "set `needs-verify`; do not close.\n"
    )
    payload = {"title": f"{a.row}: {r['title'][:120]}", "body": body, "labels": labels}
    ms_id = a.milestone if a.milestone is not None else (None if a.row.startswith("WEB-") else MILESTONE_DEFAULT)
    if ms_id:
        payload["milestone"] = ms_id
    if a.dry_run:
        print(json.dumps(payload, indent=2)[:900])
        return
    iss = tea("/issues", "POST", payload)
    n = iss["number"]
    state, got, ms, got_ids = read_back(n)
    if set(labels) - got_ids:
        print(f"WARN labels not all applied on #{n}: wanted {labels}, got {got}", file=sys.stderr)
    r["issue"] = n
    save(raw, d)
    print(
        f"opened #{n} for {a.row}: state={state} labels={got} milestone={ms}{f' (id {ms_id})' if ms_id else ''}; register issue field written (run generate.py)"
    )


def open_rider(rid, text, area):
    body = (
        f"Row: {rid}\n\nLeftover: {text}\n\n"
        "A rider is a named leftover from a closed row, too small to block it. It is picked up when this area next opens: "
        "the next prompt for the area lists open riders in Phase 0. The validator closes it after verifying the fix.\n"
    )
    iss = tea("/issues", "POST", {"title": f"RIDER {area or rid}: {text[:110]}", "body": body, "labels": [LABEL_RIDER]})
    state, got, ms, ids = read_back(iss["number"])
    if LABEL_RIDER not in ids:
        print(f"WARN rider label not applied on #{iss['number']}", file=sys.stderr)
    print(f"rider #{iss['number']} for {rid}: state={state} labels={got}")
    return iss["number"]


def do_rider(a):
    raw, d, rows = load()
    row_of(rows, a.row)
    open_rider(a.row, a.text, a.area)


def do_riders(a):
    items = tea("/issues?state=open&labels=rider&type=issues&limit=50")
    for i in items:
        if a.area and a.area.lower() not in i["title"].lower():
            continue
        print(f"#{i['number']} {i['title']}")
    if not items:
        print("no open riders")


def _age(ts):
    d = datetime.datetime.now(datetime.UTC) - datetime.datetime.fromisoformat(ts)
    h = d.total_seconds() / 3600
    return f"{h:.0f} h" if h < 48 else f"{h / 24:.1f} d"


def do_queue(a):
    import time
    import issue_check

    pace = 0.05  # the gitea client (loopback, RFC-1918, public hairpin) and the fleet are in gitea_fleet, so nginx counts no limit key for them
    raw, d, rows = load()
    rowof = {x["issue"]: x for x in rows if x.get("issue")}
    time.sleep(pace)
    nv = tea("/issues?state=open&labels=needs-verify&type=issues&limit=50")
    print(f"== needs-verify ({len(nv)}) - waiting for the validator")
    for i in sorted(nv, key=lambda i: i["updated_at"]):
        time.sleep(pace)
        since = i["updated_at"]
        for x in tea(f"/issues/{i['number']}/timeline"):
            if x["type"] == "label" and x.get("label", {}).get("name") == "needs-verify" and x.get("body") == "1":
                since = x["created_at"]
        r = rowof.get(i["number"], {})
        print(f"  #{i['number']} {r.get('id', '?')} waiting {_age(since)} | {i['title'][:70]}")
    time.sleep(pace)
    rd = tea("/issues?state=open&labels=rider&type=issues&limit=50")
    print(f"== open riders ({len(rd)})")
    for i in rd:
        print(f"  #{i['number']} {i['title'][:90]}")
    op = [x for x in rows if x.get("status") != "closed"]
    print(f"== open register rows ({len(op)})")
    for x in op:
        print(
            f"  {x['id']:26} {('#' + str(x['issue'])) if x.get('issue') else 'no issue':9} {x.get('chip', ''):16} {(x.get('next_action') or '')[:60]}"
        )
    print("== flags")
    issue_check.PACE = pace
    issue_check.report(rows)


def do_brief(a):
    """Print everything a coder needs to work a row from Gitea; falls back to the register when Gitea is down."""
    import re

    _, _, rows = load()
    r, _in_reg = row_of_ref(rows, a.target)
    if not r.get("issue"):
        sys.exit(f"{a.target}: no register row with an issue")
    n = r["issue"]
    holds = open(os.path.join(HERE, "..", "HOLDS.md")).read()
    m = re.search(r"## Binding now\n(.*?)\n## ", holds, re.S)
    print(f"=== HOLDS (tasks/HOLDS.md, binding now; it overrides the prompt)\n{(m.group(1) if m else holds).strip()}\n")
    try:
        iss, cs = tea(f"/issues/{n}"), tea(f"/issues/{n}/comments")
    except SystemExit as e:
        print(f"=== Gitea unreachable ({e}); register cache only, read-only")
        iss, cs = {"title": f"{r['id']}: {r.get('title', '')}", "state": "?", "labels": [], "body": ""}, []
    card = rowcard.parse(iss.get("body")) or rowcard.fields(r)
    labels = [lbl["name"] for lbl in iss.get("labels") or []]
    print(f"=== #{n} {iss.get('title')} [{iss.get('state')}] labels: {', '.join(labels) or '-'}")
    for k in ("owner", "state", "next_action", "done_when", "verify", "blocked_by", "gates", "decisions"):
        if card.get(k):
            print(f"{k}: {card[k]}")
    prompts = [c for c in cs if c["body"].lstrip().startswith("Prompt:")]
    status = [c for c in cs if c["body"].lstrip().startswith("Status:")]
    ledger = [c for c in cs if c not in prompts and c not in status]
    print(
        "\n=== latest Prompt: comment"
        + (
            f" ({prompts[-1]['created_at'][:16]}, {len(prompts)} in total)\n{prompts[-1]['body'].strip()}"
            if prompts
            else ": none (the row card above is the brief)"
        )
    )
    if status:
        print(f"\n=== status comment\n{status[-1]['body'].strip()}")
    print(f"\n=== last ledger entries ({len(ledger)} in total)")
    for c in ledger[-5:]:
        print(f"--- {c['created_at'][:16]} (comment {c['id']})\n{c['body'].strip()[:700]}")
    print(
        f'\n=== rules: ledger entries are comments here (tasks/_source/comment.py {r["id"]} "text", signed Coder: X); '
        "Refs #n in commits; set needs-verify when done; never close the issue; push only after a Validator: verified comment "
        "(pushgate.sh); no keys, passwords or credential URLs in comments."
    )


def _close_comment(a, r, n, refs):
    """Build the Validator close comment; exits when the close would leave no record."""
    if not refs:
        # since 31 Oct the issue thread is the ledger: --result is the record, --ledger only names a history file
        if not a.result:
            sys.exit(
                f"#{n} {a.row} has no commits on origin/main mentioning #{n}: pass --result '<one line>' "
                "so the close comment says what was found (default text not allowed)."
            )
        if a.ledger:
            lp = a.ledger if os.path.isabs(a.ledger) else os.path.join(WS, a.ledger)
            if not os.path.exists(lp):
                sys.exit(f"ledger path not found: {lp}")
        if "\n" in a.result.strip() or len(a.result) > 300:
            sys.exit("--result must be one line, at most 300 characters")
        return f"Validator close {datetime.date.today()}. No commits: result: {a.result.strip()}" + (
            f" History: {a.ledger}" if a.ledger else ""
        )
    text = (
        a.comment
        or f"Validator close {datetime.date.today()}. Verified: {(r.get('close_evidence') or 'evidence in the register').strip()[:240]}"
    )
    if a.result and a.result.strip() not in text + (r.get("close_evidence") or ""):
        text += f" Result: {a.result.strip()}"
    if a.ledger:
        text += f" History: {a.ledger}"
    return text


def do_close(a):
    raw, d, rows = load()
    r, in_reg = row_of_ref(rows, a.row)
    n = r.get("issue")
    if not n:
        sys.exit(f"{a.row} has no issue")
    if in_reg and (r.get("status") != "closed" or r.get("close_result") != "verified"):
        sys.exit(
            f"{a.row} is not closed/verified in the register (status={r.get('status')}, close_result={r.get('close_result')}); close the row first"
        )
    # Rows that shipped no commit leave nothing on the issue timeline: the close comment must say what was found.
    refs = subprocess.run(
        ["git", "-C", "/opt/aitbc", "log", "origin/main", "-E", f"--grep=#{n}([^0-9]|$)", "--format=%h"],
        capture_output=True,
        text=True,
    ).stdout.split()
    deps = tea(f"/issues/{n}/dependencies") or []
    open_deps = [d.get("number") for d in deps if isinstance(d, dict) and d.get("state") != "closed"]
    if open_deps:
        sys.exit(f"#{n} waits for open {', '.join('#' + str(x) for x in sorted(open_deps))}; close them first")
    text = _close_comment(a, r, n, refs)
    if a.dry_run:
        print(f"[dry-run] #{n} {a.row}: commits on main={len(refs)}; comment would be:\n{text}")
        return
    tea(f"/issues/{n}/comments", "POST", {"body": text})
    labels = {lbl["name"]: lbl["id"] for lbl in tea(f"/issues/{n}").get("labels", [])}
    for name, lid in labels.items():
        if name in ("needs-verify", "state/needs-verify"):
            tea(f"/issues/{n}/labels/{lid}", "DELETE")
    tea(f"/issues/{n}", "PATCH", {"state": "closed"})
    state, got, ms, _ = read_back(n)
    ok = state == "closed" and "needs-verify" not in got and "state/needs-verify" not in got
    print(f"#{n} {a.row}: state={state} labels={got} milestone={ms} -> {'OK' if ok else 'CHECK MANUALLY'}")
    for t in a.rider or []:
        open_rider(a.row, t, a.area)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    o = sub.add_parser("open")
    o.add_argument("row")
    o.add_argument("--milestone", type=int)
    o.add_argument("--label", type=int, action="append")
    o.add_argument("--new", action="store_true", help="Gitea-native row: no register entry required")
    o.add_argument("--title")
    o.add_argument("--owner")
    o.add_argument("--next")
    o.add_argument("--dry-run", action="store_true")
    o.set_defaults(fn=do_open)
    c = sub.add_parser("close")
    c.add_argument("row")
    c.add_argument("--comment")
    c.add_argument("--result", help="one-line result (required when the issue has no commits)")
    c.add_argument("--ledger", help="ledger path, relative to the staging checkout (required when no commits)")
    c.add_argument("--dry-run", action="store_true")
    c.add_argument("--rider", action="append", help="open a rider issue for a named leftover (repeatable)")
    c.add_argument("--area", help="short area name for rider titles")
    c.set_defaults(fn=do_close)
    q_ = sub.add_parser("queue")
    q_.set_defaults(fn=do_queue)
    b_ = sub.add_parser("brief")
    b_.add_argument("target")
    b_.set_defaults(fn=do_brief)
    r_ = sub.add_parser("rider")
    r_.add_argument("row")
    r_.add_argument("text")
    r_.add_argument("--area")
    r_.set_defaults(fn=do_rider)
    l_ = sub.add_parser("riders")
    l_.add_argument("area", nargs="?")
    l_.set_defaults(fn=do_riders)
    a = p.parse_args()
    a.fn(a)
