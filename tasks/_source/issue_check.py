"""Issue / register agreement checks (director tooling, staging only). Read-only.

Used by generate.py (after it writes the task files) and by issue.py (queue). Never writes to Gitea or tasks.json.
"""

import datetime
import json
import re
import subprocess
import time
import rowcard

# ---- Gitea issue / register agreement (pilot). The register is the source of truth;
# a row's `issue` field names its Gitea issue (null = none). Read-only: one `tea api`
# GET per linked issue, run inside the /opt/aitbc checkout. Skipped with --no-issues;
# an unreachable Gitea is reported as "unchecked", never as a disagreement.
# --strict makes any flag exit 1. Never writes to Gitea.
EXEMPTED = []  # (row id, sha, reason, used) - filled by check_issues, printed quietly by report()
PACE = 0.0  # seconds slept before each Gitea call (queue sets 0.6: nginx rate limit)

# Everything a tea/git call or a JSON reply can raise here; blind `except Exception`
# is ratchet-blocked, and these are the only real failure modes.
_FETCH_ERRORS = (ValueError, OSError, subprocess.SubprocessError, KeyError)


def _tea_get(path):
    """One paced `tea api` GET inside /opt/aitbc. Raises on failure."""
    if PACE:
        time.sleep(PACE)
    out = subprocess.run(
        ["tea", "api", path],
        cwd="/opt/aitbc",
        capture_output=True,
        text=True,
        timeout=20,
    )
    blob = (out.stdout + out.stderr).strip()
    if out.returncode != 0 or not out.stdout.lstrip().startswith(("{", "[")):
        raise ValueError("Gitea unreachable or unexpected reply: " + (blob.splitlines() or [""])[0][-80:])
    return json.loads(out.stdout)


def _recent_commits(since="2026-10-18"):
    """One pass over origin/main: [(sha, committed datetime, message)]. None when git fails."""
    p = subprocess.run(
        ["git", "-C", "/opt/aitbc", "log", "origin/main", f"--since={since}", "--format=%H%x1f%cI%x1f%B%x1e"],
        capture_output=True,
        text=True,
    )
    if p.returncode:
        return None
    out = []
    for rec in p.stdout.split("\x1e"):
        if not rec.strip():
            continue
        sha, when, msg = rec.strip("\n").split("\x1f", 2)
        out.append((sha, datetime.datetime.fromisoformat(when), msg))
    return out


def _names_row(msg, rid):
    return re.search(rf"(?<![A-Za-z0-9-]){re.escape(rid)}(?![A-Za-z0-9])(?!-\d)", msg) is not None


def _exemptions(t):
    """Row `ref_exempt`: list of {"sha": short sha, "reason": one line} (or "sha reason" strings). Returns [(sha, reason)]."""
    out = []
    for e in t.get("ref_exempt") or []:
        if isinstance(e, dict):
            sha, why = str(e.get("sha", "")).strip(), str(e.get("reason", "")).strip()
        else:
            sha, _, why = str(e).strip().partition(" ")
            why = why.strip()
        out.append((sha, why))
    return out


def _bulk_issues():
    """All issues in a few paged list calls ({number: issue}); None when Gitea fails, then the per-issue GETs run."""
    got, page = {}, 1
    while page < 40:
        out = subprocess.run(
            ["tea", "api", f"/repos/oib/AITBC/issues?state=all&type=issues&limit=50&page={page}"],
            cwd="/opt/aitbc",
            capture_output=True,
            text=True,
            timeout=60,
        )
        try:
            items = json.loads(out.stdout)
        except ValueError:
            return None
        if not isinstance(items, list):
            return None
        if not items:
            return got
        got.update({i["number"]: i for i in items if isinstance(i, dict) and "number" in i})
        page += 1
    return got


def _fetch_issue(n, bulk):
    """The issue dict for number n: bulk list hit, else a paced single GET with backoff."""
    if bulk and n in bulk:
        return bulk[n]
    # The nginx in front of Gitea limits each source IP to 2 r/s (burst 20) and answers the excess with
    # a 503 HTML page: pace the GETs and back off on an HTML reply instead of hammering (20 Oct).
    for attempt in (1, 2, 3, 4):
        if PACE:
            time.sleep(PACE)
        out = subprocess.run(
            ["tea", "api", f"/repos/oib/AITBC/issues/{n}"],
            cwd="/opt/aitbc",
            capture_output=True,
            text=True,
            timeout=20,
        )
        blob = (out.stdout + out.stderr).strip()
        if "request failed" in blob:
            raise ValueError("Gitea unreachable: " + blob.splitlines()[0][-80:])
        if out.returncode == 0 and out.stdout.lstrip().startswith("{"):
            iss = json.loads(out.stdout)
            if isinstance(iss, dict) and "number" in iss:
                return iss
            raise ValueError(blob[:80])
        time.sleep(2 * attempt)
    raise ValueError("Gitea unreachable or unexpected reply: " + (blob.splitlines() or [""])[0][-80:])


def _comment_bodies(n):
    """Comment bodies for issue n (rules 3b/3d only - kept rare for the nginx rate limit)."""
    cm = _tea_get(f"/repos/oib/AITBC/issues/{n}/comments")
    if not isinstance(cm, list):
        raise ValueError("comments reply is not a list")
    return [c.get("body", "") for c in cm if isinstance(c, dict)]


def _blocked_by_cycle(t, by_id):
    """The sorted member set when the row's blocked_by chain returns to itself, else None."""
    seen, cur = set(), t["id"]
    while cur in by_id and cur not in seen:
        seen.add(cur)
        cur = next(iter(by_id[cur].get("blocked_by") or []), None)
    return sorted(seen) if cur == t["id"] and len(seen) > 1 else None


def _agreement_flags(t, iss, by_id, flags):
    """Register-vs-issue agreement: deps, title prefix, state/labels (rules outside 3a-3d)."""
    n = t.get("issue")
    labels = {lbl["name"] for lbl in iss.get("labels", [])}
    has_nv = "needs-verify" in labels or "state/needs-verify" in labels  # legacy label 58 deleted; 72 is the live marker
    done = t.get("status") == "closed"
    deps = {d.get("number") for d in iss.get("dependencies") or [] if isinstance(d, dict)}
    for b in t.get("blocked_by") or []:
        bn = by_id.get(b, {}).get("issue")
        if bn and bn not in deps:
            flags.append(f"{t['id']} #{n}: blocked_by {b} (#{bn}) has no dependency on Gitea")
    if not iss.get("title", "").startswith(t["id"] + ":"):
        flags.append(f"{t['id']} #{n}: issue title does not start with '{t['id']}:' ({iss.get('title', '')[:50]!r})")
    if t["id"].startswith("WEB-") and "mark/web" not in labels:
        flags.append(f"{t['id']} #{n}: label 'mark/web' missing")
    if not done and iss["state"] == "closed":
        flags.append(f"{t['id']} #{n}: issue closed but register row is {t.get('status')} ({t.get('chip')})")
    if done and iss["state"] == "open":
        flags.append(
            f"{t['id']} #{n}: register closed ({t.get('close_result') or t.get('chip')}) but issue still open"
            + (" with needs-verify" if has_nv else "")
            + " - director closes the issue (operator ruling 19 Oct)"
        )
    if not done and has_nv and t.get("chip") == "ready":
        flags.append(
            f"{t['id']} #{n}: issue says needs-verify but the register row is still 'ready' - director to verify or register is stale"
        )
    return has_nv


def _check_commits_3a(t, n, ex, used, flags, unchecked):
    """Rule 3a: every commit the row lists must carry `Refs #<issue>`."""
    for sha in t.get("commits") or []:
        hit3a = [xs for xs, why in ex if len(xs) >= 7 and why and sha.startswith(xs)]
        if hit3a:
            used.add(hit3a[0])
            continue
        p = subprocess.run(["git", "-C", "/opt/aitbc", "log", "-1", "--format=%B", sha], capture_output=True, text=True)
        if p.returncode:
            unchecked.append(f"{t['id']} #{n}: commit {sha} not in /opt/aitbc (git fetch origin?)")
            continue
        if not re.search(rf"\bRefs\b[^\n]*#{n}\b", p.stdout, re.I):
            flags.append(f"{t['id']} #{n}: commit {sha} lacks 'Refs #{n}'")


def _check_commits_3c(t, n, iss, recent, ex, used, flags, unchecked):
    """Rule 3c: a commit after the issue opened that names the row ID must carry `Refs #<issue>`."""
    if recent is None:
        return
    opened = datetime.datetime.fromisoformat(iss["created_at"])
    listed = list(t.get("commits") or [])
    for xs, why in ex:
        if len(xs) < 7 or not why:
            flags.append(f"{t['id']} #{n}: ref_exempt entry {xs or '?'!r} needs a sha of 7+ characters and a one-line reason")
    for sha, when, msg in recent:
        if when < opened or any(sha.startswith(x) for x in listed):
            continue
        hit = [xs for xs, why in ex if len(xs) >= 7 and why and sha.startswith(xs)]
        if hit:
            used.add(hit[0])
            continue
        # A commit that links some other issue (`Refs #331`) only mentions this row in prose: not a finding.
        if _names_row(msg, t["id"]) and not re.search(r"\bRefs\b[^\n]*#\d+", msg, re.I):
            flags.append(
                f"{t['id']} #{n}: commit {sha[:9]} names the row but links no issue (no 'Refs #n' line) ({msg.splitlines()[0][:60]!r})"
            )
    for xs, why in ex:
        if len(xs) >= 7 and why:
            EXEMPTED.append((t["id"], xs, why, xs in used))


def _check_validator_comment_3d(t, n, flags, unchecked):
    """Rule 3d (forward-only, 27 Oct 2026): a row closed `verified` on or after 2026-10-27 needs a
    validator comment on its issue ("Validator: ... verified <sha>"). Rows closed with
    close.py --no-comment-check carry `comment_exempt`."""
    if not (
        t.get("close_result") == "verified"
        and str(t.get("last_verified") or "") >= "2026-10-27"
        and not t.get("comment_exempt")
    ):
        return
    try:
        texts = _comment_bodies(n)
        if not any(
            b.lstrip().lower().startswith("validator:")
            and "verified" in b.lower()
            and (t.get("tool_row") or re.search(r"\b[0-9a-f]{7,40}\b", b))
            for b in texts
        ):
            flags.append(f"{t['id']} #{n}: closed verified but no 'Validator: ... verified <sha>' comment on the issue")
    except _FETCH_ERRORS as e:
        unchecked.append(f"{t['id']} #{n}: comments unreadable for rule 3d ({str(e)[:50]})")


def _check_web_range_comment(t, n, has_nv, iss_state, flags, unchecked):
    """Rule 3b: a WEB- issue waiting for the validator must carry the coder's range-paths line."""
    if not (t["id"].startswith("WEB-") and has_nv and iss_state == "open"):
        return
    try:
        texts = _comment_bodies(n)
        if not any(re.search(r"range paths outside website/tests", b, re.I) for b in texts):
            flags.append(
                f"{t['id']} #{n}: needs-verify but no comment carries 'Range paths outside website/tests: none|<list>'"
            )
    except _FETCH_ERRORS as e:
        unchecked.append(f"{t['id']} #{n}: comments unreadable ({str(e)[:50]})")


def _check_unlinked_and_cards(rows, bulk, flags, unchecked):
    """Open issues no row links, plus row-card/label agreement for open rows (bulk data only)."""
    if bulk is None:
        unchecked.append("unlinked open issues: issue list unreadable")
        return
    linked = {t.get("issue") for t in rows if t.get("issue")}
    for n, iss in sorted(bulk.items()):
        if (
            iss.get("state") == "open"
            and n not in linked
            and "mark/rider" not in {lbl["name"] for lbl in iss.get("labels") or []}
        ):
            flags.append(
                f"#{n}: open issue without a register row ({iss.get('title', '')[:60]!r}); link it with finding.py ID ... --issue {n}"
            )
    for t in rows:
        n = t.get("issue")
        if t.get("status") == "closed" or not n or n not in bulk:
            continue
        iss = bulk[n]
        card = rowcard.parse(iss.get("body"))
        if card is None:
            flags.append(f"{t['id']} #{n}: open row has no row card (sync.py push {t['id']})")
            continue
        d = rowcard.diff(card, t)
        if d:
            flags.append(
                f"{t['id']} #{n}: row card differs from the register: {', '.join(d[:6])} "
                f"(sync.py push {t['id']} if the register is newer, sync.py pull {t['id']} if Gitea is)"
            )
        names = {lbl["name"] for lbl in iss.get("labels") or []}
        owner, state = rowcard.expected_labels(t, names)
        have_o, have_s = rowcard.scoped(names, "owner"), rowcard.scoped(names, "state")
        if have_o != ([owner] if owner else []) or have_s != ([state] if state else []):
            flags.append(
                f"{t['id']} #{n}: labels {have_o + have_s} but the register says {[x for x in (owner, state) if x]} (sync.py push or pull)"
            )


def check_issues(rows):
    flags, unchecked = [], []
    bulk = _bulk_issues()
    EXEMPTED.clear()
    recent = _recent_commits()
    if recent is None:
        unchecked.append("rule 3c: git log on /opt/aitbc origin/main failed (fetch?)")
    by_id = {x["id"]: x for x in rows}
    today = datetime.date.today().isoformat()
    for t in rows:
        cycle = _blocked_by_cycle(t, by_id)
        if cycle:
            flags.append(f"{t['id']}: blocked_by cycle through {cycle}")
        if t.get("wait_until") and not t.get("ready") and t.get("status") != "closed" and str(t["wait_until"])[:10] < today:
            flags.append(f"{t['id']} #{t.get('issue')}: wait_until {t['wait_until']} expired on a held row")
        n = t.get("issue")
        if not n:
            continue
        try:
            iss = _fetch_issue(n, bulk)
        except _FETCH_ERRORS as e:
            unchecked.append(f"{t['id']} #{n}: {str(e)[:80]}")
            continue
        has_nv = _agreement_flags(t, iss, by_id, flags)
        ex = _exemptions(t)
        used = set()
        _check_commits_3a(t, n, ex, used, flags, unchecked)
        _check_commits_3c(t, n, iss, recent, ex, used, flags, unchecked)
        _check_validator_comment_3d(t, n, flags, unchecked)
        _check_web_range_comment(t, n, has_nv, iss.get("state"), flags, unchecked)
    _check_unlinked_and_cards(rows, bulk, flags, unchecked)
    return flags, unchecked


def report(alltasks, strict=False):
    fl, un = check_issues(alltasks)
    linked = sum(1 for t in alltasks if t.get("issue"))
    print(f"issues: {linked} linked rows, {len(fl)} flag(s), {len(un)} unchecked")
    if un:
        print(
            f"!!! UNCHECKED: {len(un)} item(s) were NOT verified against Gitea; a clean flag count above does not mean the issues agree !!!"
        )
    for x in fl:
        print("  FLAG", x)
    for x in un:
        print("  UNCHECKED", x)
    if EXEMPTED:  # quiet, but visible: exempted commits never vanish from the output
        print(f"exempted: {len(EXEMPTED)} commit(s) skipped by rule 3c")
        for rid, xs, why, used in EXEMPTED:
            print(f"  exempt {rid} {xs}{'' if used else ' (no matching commit in range)'}: {why}")
    try:  # open riders: informational, never a flag
        rl = _tea_get("/repos/oib/AITBC/issues?state=open&labels=mark/rider&type=issues&limit=50")
        print(f"riders: {len(rl)} open" + "".join(f"\n  RIDER #{i['number']} {i['title'][:90]}" for i in rl))
    except _FETCH_ERRORS:
        print("riders: unchecked")
    return 1 if ((fl or un) and strict) else 0
