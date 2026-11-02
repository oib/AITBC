#!/usr/bin/env python3
"""Post a comment on a register row's Gitea issue (director tooling, staging only).

  comment.py ROW "text" [--dry-run]        post the text, read the thread back, print the new comment id
                                           (ROW is a register id, '#n' or a bare issue number with an aitbc-row card)
  comment.py ROW --file PATH [--dry-run]   same, text from a file
  comment.py ROW "Status: ..." --status    edit the issue's one "Status:" comment (posts it the first time)
  --allow-hex                              let a full 64-hex value through (a public tx or block hash, never a key)

Rules (27 Oct 2026): no "idle"/"ack"/"waiting" comments (session state goes on the board); a comment over 1500
characters needs --long. Since 31 Oct the issue thread is the ledger (operator): ledger entries are posted here,
tasks/progress/*.md is read-only history.

Reuses issue.tea (retry on the nginx 2 r/s 503 pages). Replaces `tea issues comment`, which prints a listing and posts nothing.
"""

import argparse
import sys
from issue import tea, load, row_of_ref

ap = argparse.ArgumentParser()
ap.add_argument("row")
ap.add_argument("text", nargs="?")
ap.add_argument("--file")
ap.add_argument("--dry-run", action="store_true")
ap.add_argument("--status", action="store_true")
ap.add_argument("--long", action="store_true")
ap.add_argument("--allow-hex", action="store_true")
a = ap.parse_args()
body = open(a.file).read().strip() if a.file else (a.text or "").strip()
if not body:
    sys.exit("no comment text")
import re

if len(body) < 150 and re.search(r"\b(idle|ack|acked|waiting|standing by)\b", body, re.I):
    sys.exit("refused: idle/ack/waiting comments are noise; put session state on the board (AGENTS/gitea-issue.md)")
if len(body) > 1500 and not a.long:
    sys.exit(f"refused: {len(body)} characters; summarize or split it (<= 1500 each), or pass --long for a full ledger entry")
# the issue thread is the ledger since 31 Oct: refuse anything that looks like a secret value (GITEA-TASKING-1 P1)
SECRET = [
    (r"PRIVATE_KEY\s*[=:]\s*(0x)?[0-9a-fA-F]{32,}", "a PRIVATE_KEY value"),
    (r'://[^/\s:@`\'"]+:[^/\s@`\'"]+@', "a URL with user:password"),
    (r'(?i)\bpass(word|wd)?\s*[=:]\s*[^\s`\'"<>]{6,}', "a password value"),
    (r"(?i)\b(token|secret|api_key)\s*[=:]\s*[A-Za-z0-9_\-]{16,}", "a token or secret value"),
]
PLACEHOLDER = re.compile(r"(?i)(://)?(user|<user>|\*+):(pass|password|<password>|\*+)@?$")  # documentation, not a value
for pat, what in SECRET:
    if any(not PLACEHOLDER.search(m.group(0)) for m in re.finditer(pat, body)):
        sys.exit(f"refused: the text carries {what}; never post keys, passwords or credential URLs (AGENTS.md)")
if not a.allow_hex and re.search(r"(?<![0-9a-fA-F])(0x)?[0-9a-fA-F]{64}(?![0-9a-fA-F])", body):
    sys.exit("refused: a full 64-hex value; shorten it to a prefix (0x7233782b...) or pass --allow-hex if it is a public hash")
if a.status and not body.startswith("Status:"):
    sys.exit('--status text must start with "Status:"')
_, _, rows = load()
r, _in_reg = row_of_ref(rows, a.row)
n = r.get("issue")
if not n:
    sys.exit(f"row {a.row} has no issue")
if a.dry_run:
    print(f"would post on #{n}:\n{body}")
    sys.exit(0)
if a.status:
    old = [x for x in tea(f"/issues/{n}/comments") if x["body"].lstrip().startswith("Status:")]
    if old:
        c = tea(f"/issues/comments/{old[-1]['id']}", "PATCH", {"body": body})
        print(f"#{n}: status comment {c['id']} edited")
        sys.exit(0)
c = tea(f"/issues/{n}/comments", "POST", {"body": body})
last = tea(f"/issues/{n}/comments")[-1]
ok = last["id"] == c["id"] and last["body"].strip() == body
print(f"#{n}: comment id {c['id']} {'OK' if ok else 'CHECK MANUALLY (read-back differs)'}")
sys.exit(0 if ok else 1)
