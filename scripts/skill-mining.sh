#!/usr/bin/env bash
# =============================================================================
# skill-mining.sh — per-role skill-mining report with threshold verdicts
# (ABS-218, epic ABS-217)
# =============================================================================
# Joins the THREE log sources a single orchestrator run leaves behind and emits
# one Markdown mining report per role, each with a threshold verdict
# (SKILL-KANDIDAT / OK). The report answers: "which seat role repeats the same
# raw work often enough that a skill would pay for itself?".
#
# Sources (all optional — any missing source degrades gracefully, never breaks):
#   1) $STATE_DIR/telemetry/<ticket>.<role>.<epoch>.seq
#        one tool-call NAME per line (written by orchestrator.sh
#        record_spawn_telemetry, ~Z.682-711). Gives per-seat call VOLUME and
#        Skill-call count. One .seq file == one seat (spawn).
#   2) $STATE_DIR/run.log
#        TSV: <ts> <action> <ticket> <role> <to> <note>. The escalation intent
#        classes INTENT-HANDOFF-NOMOVE / INTENT-RESPAWN-LIMIT / INTENT-SPAWN-CRASH
#        are counted per role (column 4).
#   3) seat transcripts (CLI JSONL under $CONFIG_DIR/projects/**/<sid>.jsonl,
#        session ids read from $STATE_DIR/sessions/<ticket>.<role>.<status>).
#        Real Bash commands are extracted, NORMALIZED (ticket-ids -> ABS-N, first
#        3 tokens) and REDACTED (no secret/token values ever reach the report).
#
# Dependencies: bash + python3 stdlib only. No jq, no network, no pip installs.
#
# Usage:
#   scripts/skill-mining.sh [--state-dir D] [--config-dir D] [--proposals]
#                           [--out FILE] [--help]
#
#   --state-dir D    orchestrator state dir (default: $ORCH_STATE_DIR or
#                    work/.orchestrator)
#   --config-dir D   CLI config dir holding projects/**/<sid>.jsonl transcripts
#                    (default: $CLAUDE_CONFIG_DIR or ~/.claude)
#   --proposals      write a proposal skeleton per SKILL-KANDIDAT role into
#                    work/improvement-proposals/ (ABS-4 template)
#   --out FILE       write the report to FILE instead of stdout
#
# Thresholds are variables at the top of this script (AC3) and can be overridden
# from the environment.
# =============================================================================
set -euo pipefail

# --- Thresholds (AC3) — override via env ------------------------------------
THRESH_PATTERN_COUNT="${THRESH_PATTERN_COUNT:-10}"   # a normalized cmd pattern must recur >= this ...
THRESH_PATTERN_SEATS="${THRESH_PATTERN_SEATS:-3}"    # ... across >= this many distinct seats
THRESH_HELP_CALLS="${THRESH_HELP_CALLS:-3}"          # help invocations for a role
THRESH_NOMOVE_RESPAWN="${THRESH_NOMOVE_RESPAWN:-2}"  # NOMOVE + RESPAWN escalations for a role
THRESH_TOP_CMD="${THRESH_TOP_CMD:-3}"                # min count for a cmd to appear in the Top list
TURN_CEILING="${ORCH_MAX_TURNS:-25}"                 # per-spawn turn ceiling (orchestrator default)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

STATE_DIR="${ORCH_STATE_DIR:-$REPO_ROOT/work/.orchestrator}"
CONFIG_DIR="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
PROPOSALS_DIR="${PROPOSALS_DIR:-$REPO_ROOT/work/improvement-proposals}"
WRITE_PROPOSALS=0
OUT=""

usage() { sed -n '2,44p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; }

while [ $# -gt 0 ]; do
    case "$1" in
        --state-dir)  STATE_DIR="${2:?--state-dir needs a value}"; shift 2 ;;
        --config-dir) CONFIG_DIR="${2:?--config-dir needs a value}"; shift 2 ;;
        --proposals)  WRITE_PROPOSALS=1; shift ;;
        --out)        OUT="${2:?--out needs a value}"; shift 2 ;;
        -h|--help)    usage; exit 0 ;;
        *) echo "skill-mining.sh: unknown argument: $1" >&2; usage >&2; exit 2 ;;
    esac
done

command -v python3 >/dev/null 2>&1 || { echo "skill-mining.sh: python3 is required" >&2; exit 3; }

export STATE_DIR CONFIG_DIR PROPOSALS_DIR WRITE_PROPOSALS OUT
export THRESH_PATTERN_COUNT THRESH_PATTERN_SEATS THRESH_HELP_CALLS \
       THRESH_NOMOVE_RESPAWN THRESH_TOP_CMD TURN_CEILING

python3 - <<'PY'
import os, re, glob, json, statistics, datetime, sys

STATE_DIR      = os.environ["STATE_DIR"]
CONFIG_DIR     = os.environ["CONFIG_DIR"]
PROPOSALS_DIR  = os.environ["PROPOSALS_DIR"]
WRITE_PROPOSALS= os.environ.get("WRITE_PROPOSALS") == "1"
OUT            = os.environ.get("OUT") or ""

T_PAT_COUNT = int(os.environ["THRESH_PATTERN_COUNT"])
T_PAT_SEATS = int(os.environ["THRESH_PATTERN_SEATS"])
T_HELP      = int(os.environ["THRESH_HELP_CALLS"])
T_NOMOVE    = int(os.environ["THRESH_NOMOVE_RESPAWN"])
T_TOP       = int(os.environ["THRESH_TOP_CMD"])
TURN_CEIL   = int(os.environ["TURN_CEILING"])

# --- normalization + redaction ---------------------------------------------
TICKET_RE = re.compile(r'\b[A-Z][A-Z0-9]+-\d+\b')

def redact(s):
    # key=value / key: value forms for common secret keys
    s = re.sub(r'(?i)\b(token|secret|password|passwd|pwd|api[_-]?key|apikey|access[_-]?key|auth)(\s*[=:]\s*)(\S+)',
               lambda m: m.group(1) + m.group(2) + '<REDACTED>', s)
    s = re.sub(r'(?i)\bbearer\s+\S+', 'Bearer <REDACTED>', s)
    s = re.sub(r'sk-[A-Za-z0-9_-]{6,}', '<REDACTED>', s)
    s = re.sub(r'ghp_[A-Za-z0-9]{10,}', '<REDACTED>', s)
    s = re.sub(r'AKIA[0-9A-Z]{12,}', '<REDACTED>', s)
    s = re.sub(r'xox[baprs]-[A-Za-z0-9-]+', '<REDACTED>', s)
    s = re.sub(r'eyJ[A-Za-z0-9_.-]{20,}', '<REDACTED>', s)      # JWT-ish
    s = re.sub(r'\b[0-9a-fA-F]{32,}\b', '<REDACTED>', s)         # long hex blobs
    return s

def first_line(cmd):
    for ln in cmd.splitlines():
        ln = ln.strip()
        if ln:
            return ln
    return ""

def normalize(cmd):
    ln = first_line(cmd)
    ln = TICKET_RE.sub('ABS-N', ln)
    ln = redact(ln)
    toks = ln.split()
    return " ".join(toks[:3])

HELP_RE = re.compile(r'(^|\s)(--help|-h|help)(\s|$)')
def is_help(cmd):
    ln = first_line(cmd)
    return bool(HELP_RE.search(ln))

# --- ABS-318: applicable-but-not-loaded vs inapplicable ----------------------
# The universal PROCESS skills apply to EVERY deliverable-producing seat. The
# PRODUCT-DOMAIN skills (pattern-discovery, api/rls/frontend/testing patterns, …)
# only apply to a seat that actually touches product source or patterns_library/.
# A self-hosting HARNESS seat that edits scripts/ or harness/ never needed them,
# so counting its zero product-skill loads as a "miss" masks the real signal —
# the process-skill trigger layer. We classify each seat and report the split.
PROCESS_SKILLS = set(
    s for s in os.environ.get("PROCESS_SKILLS", "stop-slop verify simplify").split() if s
)
# Path tokens that mark a seat as product-domain-touching. Override via env for a
# consuming project whose app source lives elsewhere.
PRODUCT_DOMAIN_PATHS = [
    p for p in os.environ.get(
        "PRODUCT_DOMAIN_PATHS",
        "patterns_library/ src/ app/ components/ pages/"
    ).split() if p
]
def touches_product_domain(cmd):
    return any(tok in cmd for tok in PRODUCT_DOMAIN_PATHS)

def skill_name(inp):
    if not isinstance(inp, dict):
        return ""
    for k in ("skill", "name", "command"):
        v = inp.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip().split()[0]
    return ""

# --- per-role accumulator ----------------------------------------------------
class Role:
    def __init__(self):
        self.call_counts = []        # tool calls per seat (telemetry .seq line count)
        self.skill_counts = []       # Skill tool calls per seat
        self.seats = 0               # telemetry seq files (spawns)
        self.nomove = 0
        self.respawn = 0
        self.crash = 0
        self.nohash = 0              # HANDOFF-CLAIM-NOHASH advisories (ADR-A-0024 f)
        self.help = 0
        self.cmd_total = {}          # normalized cmd -> total occurrences
        self.cmd_seats = {}          # normalized cmd -> set of seat ids
        self.transcript_seats = 0
        self.product_domain_seats = 0  # transcript seats touching product source
        self.process_skill_calls = 0   # Skill calls named stop-slop/verify/simplify

roles = {}
def role(name):
    return roles.setdefault(name, Role())

# --- source 1: telemetry .seq -----------------------------------------------
for seq in sorted(glob.glob(os.path.join(STATE_DIR, "telemetry", "*.seq"))):
    base = os.path.basename(seq)[:-4]           # strip ".seq"
    parts = base.split(".")
    if len(parts) < 3:
        continue
    rname = parts[1]
    try:
        names = [l.strip() for l in open(seq, encoding="utf-8", errors="replace") if l.strip()]
    except OSError:
        continue
    r = role(rname)
    r.seats += 1
    r.call_counts.append(len(names))
    r.skill_counts.append(sum(1 for n in names if n == "Skill"))

# --- source 2: run.log intent classes ---------------------------------------
run_log = os.path.join(STATE_DIR, "run.log")
if os.path.isfile(run_log):
    for line in open(run_log, encoding="utf-8", errors="replace"):
        cols = line.rstrip("\n").split("\t")
        if len(cols) < 4:
            continue
        action, rname = cols[1], cols[3]
        if not rname or rname == "-":
            continue
        r = role(rname)
        # ABS-255: a mis-report (claimed commits that do not verify) is a
        # prompt-quality defect of the same class as a no-move — it feeds the
        # existing nomove signal rather than a new counter (ADR-A-0024 e).
        if action in ("INTENT-HANDOFF-NOMOVE", "INTENT-HANDOFF-MISREPORT"):
            r.nomove += 1
        elif action == "INTENT-RESPAWN-LIMIT":
            r.respawn += 1
        elif action == "INTENT-SPAWN-CRASH":
            r.crash += 1
        # PILOT-69 AC2 / ADR-A-0024 (f): the HANDOFF-CLAIM-NOHASH advisory is
        # counted as its OWN per-role signal (NOT folded into nomove — it is an
        # advisory, not a verified defect). This is the telemetry the ADR's
        # promotion criterion was always missing: the raw advisory volume per role,
        # so a human can see whether it concentrates in COMMITTING seats (a real
        # signal) or in review/PO seats (the expected false-positive class).
        elif action == "INTENT-HANDOFF-CLAIM-NOHASH":
            r.nohash += 1

# --- source 3: transcripts (Bash commands) ----------------------------------
def tool_uses(path):
    """Yield every (tool_name, input_dict) tool_use in a CLI JSONL transcript."""
    try:
        fh = open(path, encoding="utf-8", errors="replace")
    except OSError:
        return
    with fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            msg = obj.get("message") if isinstance(obj, dict) else None
            content = msg.get("content") if isinstance(msg, dict) else None
            if not isinstance(content, list):
                continue
            for block in content:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "tool_use":
                    yield block.get("name"), (block.get("input") or {})

def transcript_for(sid):
    hits = glob.glob(os.path.join(CONFIG_DIR, "projects", "**", sid + ".jsonl"), recursive=True)
    return hits[0] if hits else None

sessions_dir = os.path.join(STATE_DIR, "sessions")
if os.path.isdir(sessions_dir):
    for sf in sorted(glob.glob(os.path.join(sessions_dir, "*"))):
        if not os.path.isfile(sf):
            continue
        name = os.path.basename(sf)
        parts = name.split(".")
        if len(parts) < 3:
            continue
        rname = parts[1]
        try:
            sid = open(sf, encoding="utf-8", errors="replace").readline().strip()
        except OSError:
            continue
        if not sid:
            continue
        tf = transcript_for(sid)
        if not tf:
            continue
        r = role(rname)
        r.transcript_seats += 1
        seat_id = name                              # one session file == one seat
        seat_touched_product = False
        for tname, inp in tool_uses(tf):
            if tname == "Skill":
                if skill_name(inp) in PROCESS_SKILLS:
                    r.process_skill_calls += 1
                continue
            if tname != "Bash":
                continue
            cmd = inp.get("command")
            if not (isinstance(cmd, str) and cmd.strip()):
                continue
            if touches_product_domain(cmd):
                seat_touched_product = True
            if is_help(cmd):
                r.help += 1
            norm = normalize(cmd)
            if not norm:
                continue
            r.cmd_total[norm] = r.cmd_total.get(norm, 0) + 1
            r.cmd_seats.setdefault(norm, set()).add(seat_id)
        if seat_touched_product:
            r.product_domain_seats += 1

# --- verdict (AC3) -----------------------------------------------------------
def verdict(r):
    reasons = []
    for cmd, total in r.cmd_total.items():
        seats = len(r.cmd_seats.get(cmd, ()))
        if total >= T_PAT_COUNT and seats >= T_PAT_SEATS:
            reasons.append(f"pattern `{cmd}` {total}x across {seats} seats "
                           f"(>= {T_PAT_COUNT}x / {T_PAT_SEATS} seats)")
    if r.help >= T_HELP:
        reasons.append(f"help invocations {r.help} (>= {T_HELP})")
    if (r.nomove + r.respawn) >= T_NOMOVE:
        reasons.append(f"NOMOVE+RESPAWN {r.nomove + r.respawn} (>= {T_NOMOVE})")
    return ("SKILL-KANDIDAT", reasons) if reasons else ("OK", [])

def med(xs):
    return statistics.median(xs) if xs else 0

# --- render ------------------------------------------------------------------
def render_role(rname, r):
    v, reasons = verdict(r)
    L = []
    L.append(f"## Role: {rname}")
    L.append("")
    L.append(f"- Seats (spawns): {r.seats}")
    if r.call_counts:
        L.append(f"- Tool calls per seat — median: {med(r.call_counts):g}, "
                 f"max: {max(r.call_counts)} (turn-ceiling: {TURN_CEIL})")
    else:
        L.append(f"- Tool calls per seat — (no telemetry) (turn-ceiling: {TURN_CEIL})")
    L.append(f"- help invocations: {r.help}")
    L.append(f"- Escalations — NOMOVE: {r.nomove}, RESPAWN: {r.respawn}, CRASH: {r.crash}")
    # PILOT-69 AC2 / ADR-A-0024 (f): advisory volume, reported but never a verdict.
    L.append(f"- HANDOFF-CLAIM-NOHASH advisories: {r.nohash} "
             f"(ADR-A-0024 f — advisory, not counted as a defect)")
    if r.skill_counts:
        L.append(f"- Skill calls per seat — median: {med(r.skill_counts):g}, "
                 f"total: {sum(r.skill_counts)}")
    else:
        L.append("- Skill calls per seat — (no telemetry)")
    # ABS-318: applicable-but-not-loaded vs inapplicable. Process skills apply to
    # every seat; product-domain skills only to seats touching product source, so
    # a harness/infra seat's zero product-skill load is NOT a miss.
    L.append(f"- Process-skill calls (stop-slop/verify/simplify — applicable every seat): "
             f"{r.process_skill_calls}")
    if r.transcript_seats:
        L.append(f"- Product-domain-touching seats: {r.product_domain_seats}/{r.transcript_seats} "
                 f"(product-domain skills only applicable here; other seats = inapplicable, not a miss)")
    top = sorted(r.cmd_total.items(), key=lambda kv: (-kv[1], kv[0]))
    top = [(c, n) for c, n in top if n >= T_TOP]
    if top:
        L.append(f"- Top normalized commands (>= {T_TOP}x):")
        for cmd, n in top:
            seats = len(r.cmd_seats.get(cmd, ()))
            L.append(f"  - `{cmd}` — {n}x across {seats} seats")
    else:
        L.append(f"- Top normalized commands (>= {T_TOP}x): (none)")
    L.append("")
    if v == "SKILL-KANDIDAT":
        L.append(f"**Verdict: SKILL-KANDIDAT** — " + "; ".join(reasons))
    else:
        L.append("**Verdict: OK**")
    L.append("")
    return "\n".join(L), v, reasons

now = datetime.datetime.now(datetime.timezone.utc)
report = []
report.append("# Skill-Mining Report")
report.append("")
report.append(f"- Generated: {now.strftime('%Y-%m-%dT%H:%M:%SZ')}")
report.append(f"- State dir: `{STATE_DIR}`")
report.append(f"- Config dir: `{CONFIG_DIR}`")
report.append(f"- Roles analyzed: {len(roles)}")
report.append(f"- Thresholds: pattern>={T_PAT_COUNT}x/{T_PAT_SEATS} seats, "
              f"help>={T_HELP}, NOMOVE+RESPAWN>={T_NOMOVE}")
# PILOT-69 AC2 / ADR-A-0024 (f): run-level HANDOFF-CLAIM-NOHASH total. This is the
# measure the ADR's promotion criterion needs — evaluated each release retro (see
# ADR-A-0024 (f)). A run with no telemetry reports 0, which is honest (not "unknown").
_nohash_total = sum(r.nohash for r in roles.values())
report.append(f"- HANDOFF-CLAIM-NOHASH advisories (run total, ADR-A-0024 f promotion measure): {_nohash_total}")
report.append("")

candidates = []
for rname in sorted(roles):
    block, v, reasons = render_role(rname, roles[rname])
    report.append(block)
    if v == "SKILL-KANDIDAT":
        candidates.append((rname, reasons))

if not roles:
    report.append("_No sources found under the given state dir — nothing to mine._")
    report.append("")

report_text = "\n".join(report)

if OUT:
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write(report_text + "\n")
else:
    sys.stdout.write(report_text + "\n")

# --- proposals (AC4) ---------------------------------------------------------
def proposal_skeleton(rname, reasons):
    day = now.strftime("%Y-%m-%d")
    ev = "\n".join(f"- {x}" for x in reasons) or "- (see mining report)"
    return f"""# Add a skill for the `{rname}` seat — recurring un-skilled work

- **Filed**: {day}
- **Filed by**: skill-mining (trigger: threshold verdict SKILL-KANDIDAT)
- **Context**: automated mining of orchestrator telemetry + run.log + seat transcripts (ABS-218)

## Rationale

The `{rname}` role crossed a skill-mining threshold in this run:

{ev}

Recurring raw work at this volume is the signature of a missing skill: the same
sequence is re-derived by every seat instead of being encapsulated once.

## Suggested Boilerplate Change

Add or extend a skill for the `{rname}` seat that encapsulates the recurring
command pattern(s) above, then map it to the role in the harness skill matrix.
Candidate paths:

- `harness/claude/skills/<new-or-existing-skill>/SKILL.md`
- the `{rname}` role definition under `harness/claude/agents/` (skill mapping)

## Impact

Fewer tool calls / turns per `{rname}` seat, lower cost, and a consistent
encapsulated procedure. Effort: small-to-medium (author/extend one skill).
Risk: low — additive; verify against the ABS-218 before/after mining metric.

## Issue Body (copy-paste-ready)

Mining of an orchestrator run flagged the `{rname}` seat as a SKILL-KANDIDAT:
{ev}

Propose encapsulating the recurring work in a role-mapped skill and re-running
skill-mining.sh to confirm the volume drops.
"""

if WRITE_PROPOSALS and candidates:
    os.makedirs(PROPOSALS_DIR, exist_ok=True)
    day = now.strftime("%Y-%m-%d")
    written = []
    for rname, reasons in candidates:
        slug = re.sub(r'[^a-z0-9]+', '-', rname.lower()).strip('-')
        path = os.path.join(PROPOSALS_DIR, f"{day}-skill-mining-{slug}.md")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(proposal_skeleton(rname, reasons))
        written.append(path)
    sys.stderr.write("skill-mining: wrote %d proposal(s):\n" % len(written))
    for p in written:
        sys.stderr.write("  %s\n" % p)
PY
