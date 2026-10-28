#!/bin/bash
# v17 activation verification — run after the chain seals
# STATE_TRANSITION_V17_HEIGHT (the v17 pin; 8900 on the bc-2 fleet).
#
# v17 (BNT-1 revival) re-arms the protocol-escrow surfaces whose emissions
# carry payload.auth — staking, agent staking, bounty — while HTLC and
# AUTO_STAKE stay retired forever (they emit no auth and can never seal;
# the HTLC contract mutators raise RetiredProtocolTransfer in-process and
# AUTO_STAKE only log-skips). A green run proves all four things at once:
#
#   a) pin uniformity    STATE_TRANSITION_V17_HEIGHT is set to the same
#                        non-empty value in /etc/aitbc/blockchain.env on every
#                        host — drift here is a replay/fork vector.
#   b) head carries v17  the hub's /rpc/block head reports height >= the pin
#                        and block_metadata.state_transition_version == 17
#                        (block_metadata is a JSON *string* — double-decoded).
#   c) revived surface   POST /rpc/staking/stake on --probe-host answers past
#      live              the unarmed gate. An unsigned probe cannot tell armed
#                        from unarmed — the 403 signature check runs BEFORE
#                        the 410 v17 gate — so this signs a real request with
#                        an EPHEMERAL secp256k1 key generated and discarded
#                        in-process on the probe host (no real key material
#                        anywhere). Interpretation: 410 = gate still unarmed
#                        (FAIL), 403 = probe signature rejected (FAIL — the
#                        probe itself is broken), anything else = surface is
#                        answering post-gate (expect 404 "Account not found"
#                        for the unfunded ephemeral address; the request can
#                        never succeed past the gate — there is no account).
#   d) dead surfaces     HTLC and AUTO_STAKE have no HTTP routes, so "still
#      stay dead         dead" is proven by absence: (d1) /rpc/htlc/initiate
#                        answers 404 (route never mounted) and (d2) the hub
#                        chain.db holds zero HTLC*/AUTO_STAKE transactions
#                        sealed at/above the pin. The db is opened read-only
#                        via a sqlite3 mode=ro URI and only after the file is
#                        verified to exist — a wrong path fails instead of
#                        silently creating an empty database.
#
# Read-only everywhere: the script ssh-es, greps env files (sudo -n when the
# file is not directly readable), curls loopback endpoints and opens chain.db
# read-only. It never restarts services, edits env files or writes to the
# chain db. The single POST (check c) is authenticated only by the throwaway
# key above and cannot mutate anything — the address it signs for does not
# exist on-chain.
#
# Usage: v17-activation-verify.sh [options] [host ...]
#   --hosts "h ..."      host list (canonical names: hub hub1 node0 node1 node2)
#   --probe-host <name>  node for the HTTP probes (default: node2 — the
#                        restarted node)
#   --hub <name>         hub host for the head/chain-db checks (default: hub)
#   --json               emit one JSON object at the end:
#                        {"checks":[{"name","ok","details"}...],"pass":bool}
#   -h, --help           this text
#
# Hosts come from --hosts, else positional args, else AITBC_FLEET_HOSTS —
# there is no built-in roster (same contract as fleet-config-check.sh: a
# hardcoded one named the operator's hosts in a public repository and was
# wrong for every other site).
#
# A host that cannot be verified over ssh is UNREACHABLE — a failure, never
# a silent skip ("a skipped section must never look like a clean one").
# Dependencies: bash, ssh, curl, base64 and python3 on the remote hosts
# (python3 only locally when --json is used). No jq anywhere.

set -euo pipefail

usage() {
    cat <<'EOF'
Usage: v17-activation-verify.sh [options] [host ...]
  --hosts "h ..."      host list (canonical names: hub hub1 node0 node1 node2)
  --probe-host <name>  node for the HTTP probes (default: node2)
  --hub <name>         hub host for the head/chain-db checks (default: hub)
  --json               emit one JSON object at the end:
                       {"checks":[{"name","ok","details"}...],"pass":bool}
  -h, --help           this text

Hosts come from --hosts, else positional args, else $AITBC_FLEET_HOSTS.
Four checks: (a) v17 pin uniformity across hosts, (b) chain head carries
v17, (c) revived staking surface answers post-gate on the probe host,
(d) dead HTLC/AUTO_STAKE surfaces stay dead. Exit 0 = PASS, 1 = FAIL.
EOF
}

PROBE_HOST="node2"
HUB_HOST="hub"
JSON_OUT=0
HOSTS_OPT=""
POS_ARGS=()

# Positionals are collected, not broken on — options stay valid anywhere on
# the line (canonical host names never start with "-").
while [ $# -gt 0 ]; do
    case "$1" in
        --hosts)         [ $# -ge 2 ] || { echo "--hosts needs a value" >&2; exit 2; }; HOSTS_OPT="$2"; shift 2 ;;
        --hosts=*)       HOSTS_OPT="${1#*=}"; shift ;;
        --probe-host)    [ $# -ge 2 ] || { echo "--probe-host needs a value" >&2; exit 2; }; PROBE_HOST="$2"; shift 2 ;;
        --probe-host=*)  PROBE_HOST="${1#*=}"; shift ;;
        --hub)           [ $# -ge 2 ] || { echo "--hub needs a value" >&2; exit 2; }; HUB_HOST="$2"; shift 2 ;;
        --hub=*)         HUB_HOST="${1#*=}"; shift ;;
        --json)          JSON_OUT=1; shift ;;
        -h|--help)       usage; exit 0 ;;
        --)              shift; while [ $# -gt 0 ]; do POS_ARGS+=("$1"); shift; done ;;
        -*)              echo "unknown option: $1" >&2; usage >&2; exit 2 ;;
        *)               POS_ARGS+=("$1"); shift ;;
    esac
done

if [ -n "$HOSTS_OPT" ]; then
    HOSTS="$HOSTS_OPT"
elif [ "${#POS_ARGS[@]}" -gt 0 ]; then
    HOSTS="${POS_ARGS[*]}"
else
    HOSTS="${AITBC_FLEET_HOSTS:?set AITBC_FLEET_HOSTS to the hosts to check (e.g. \"hub hub1 node0 node1 node2\"), pass them as arguments, or use --hosts}"
fi

# Every ssh probe goes through sshr: a single transient blip (jump-host
# hiccup, connection drop) must not paint a host UNREACHABLE — each failed
# check reads that as failure the same way a real one does. One retry with
# a short delay is enough; anything still failing after two tries is
# genuinely down. (Same helper as fleet-config-check.sh.)
sshr() {
    if ssh -o ConnectTimeout=8 -o BatchMode=yes "$@" 2>/dev/null; then
        return 0
    fi
    sleep 2
    ssh -o ConnectTimeout=8 -o BatchMode=yes "$@" 2>/dev/null
}

# Hostname-verified ssh resolution. A candidate must not only answer ssh —
# it must BE the host (a wildcard ssh config or a jump box would happily
# serve its own env files as the target's). The only candidate is the bare
# canonical name; sites resolve it via ~/.ssh/config.
declare -A RESOLVED=()
declare -A _SEEN=()
RESOLVE_LIST=""
# shellcheck disable=SC2086 # $HOSTS is a deliberate word list
for h in $HOSTS "$PROBE_HOST" "$HUB_HOST"; do
    [ -z "$h" ] && continue
    [ -n "${_SEEN[$h]:-}" ] && continue
    _SEEN[$h]=1
    RESOLVE_LIST="$RESOLVE_LIST $h"
done

resolve_bad=0
unresolved=""
# shellcheck disable=SC2086 # $RESOLVE_LIST is a deliberate word list
for h in $RESOLVE_LIST; do
    RESOLVED[$h]=""
    got=$(ssh -o ConnectTimeout=8 -o BatchMode=yes "$h" 'hostname -s' 2>/dev/null || true)
    if [ "$got" = "$h" ]; then
        RESOLVED[$h]="$h"
    elif [ -n "$got" ]; then
        echo "  NOTE: $h answers as '$got', not '$h' — ignored"
    fi
    if [ -z "${RESOLVED[$h]}" ]; then
        unresolved="$unresolved $h"
    fi
done
if [ -n "$unresolved" ]; then
    resolve_bad=1
    echo "NOTE: no verified ssh reach to:$unresolved — they will read UNREACHABLE (a failure, not a skip)"
fi

host_ok() { [ -n "$1" ] && [ "${RESOLVED[$1]:-}" = "$1" ]; }

# grep_env <canonical-host> <VAR> [remote file ...]
# Print the effective (last-wins) value of VAR across the given env files on
# the host, using sudo -n when a file is not directly readable — mirroring
# systemd EnvironmentFile ordering (later files win → tail -1). Prints
# UNREACHABLE on ssh failure. The file list expands into the remote command
# BEFORE ssh runs, so a glob like /etc/aitbc/*.env arrives literal and is
# expanded by the remote shell — required, because the remote shell is zsh
# and will not glob-expand the contents of a variable.
grep_env() {
    local h="$1" var="$2" out
    shift 2
    local files="${*:-/etc/aitbc/*.env}"
    out=$(sshr "${RESOLVED[$h]:-$h}" \
        "for f in $files; do \
             if [ -r \"\$f\" ]; then grep -h '^${var}=' \"\$f\" 2>/dev/null; \
             else sudo -n grep -h '^${var}=' \"\$f\" 2>/dev/null; fi; \
         done | tail -1 | cut -d= -f2-" \
        2>/dev/null) || { echo "UNREACHABLE"; return; }
    printf '%s' "$out"
}

# Per-check results for the optional --json report. Details are kept
# single-line and tab-free so the TSV hand-off below survives.
CHECK_NAMES=()
CHECK_OKS=()
CHECK_DETAILS=()
record() {
    CHECK_NAMES+=("$1"); CHECK_OKS+=("$2"); CHECK_DETAILS+=("$3")
}

# ---------------------------------------------------------------------------
echo "=== v17 pin uniformity (STATE_TRANSITION_V17_HEIGHT in /etc/aitbc/blockchain.env) ==="
# The pin the whole activation hinges on: every host must carry the same
# non-empty value or the fleet activates the revival rules at different
# heights — a replay/fork vector, not a cosmetic drift.
pin_bad=0
pin_conflict=0
PIN=""
seen=""
seen_set=0
pin_report=""
# shellcheck disable=SC2086 # $HOSTS is a deliberate word list
for h in $HOSTS; do
    if ! host_ok "$h"; then
        pin_bad=1
        printf "  %-14s UNREACHABLE\n" "$h"
        pin_report="$pin_report $h=UNREACHABLE"
        continue
    fi
    val=$(grep_env "$h" STATE_TRANSITION_V17_HEIGHT /etc/aitbc/blockchain.env)
    if [ "$val" = "UNREACHABLE" ]; then
        pin_bad=1
        printf "  %-14s UNREACHABLE\n" "$h"
        pin_report="$pin_report $h=UNREACHABLE"
        continue
    fi
    val=$(printf '%s' "$val" | tr -d '[:space:]')
    pin_report="$pin_report $h=${val:-<unset>}"
    if [ -z "$val" ]; then
        pin_bad=1
        printf "  %-14s <unset>  <- pin missing\n" "$h"
        continue
    fi
    printf "  %-14s %s\n" "$h" "$val"
    if [ "$seen_set" -eq 0 ]; then
        seen="$val"
        seen_set=1
    elif [ "$seen" != "$val" ]; then
        pin_bad=1
        pin_conflict=1
        printf "  FAIL: %s=%s differs from the fleet's %s — activation heights diverge\n" "$h" "$val" "$seen"
    fi
done
# Uniform-but-non-integer is a failure too; PIN only feeds the later
# assertions when it is an integer.
if [ "$pin_bad" -eq 0 ] && [[ ! "$seen" =~ ^[0-9]+$ ]]; then
    pin_bad=1
    echo "  FAIL: pin value '$seen' is uniform but not an integer"
fi
# PIN is derived whenever every host that answered reported the same
# integer — even when the check itself already failed (unset/unreachable
# hosts), so the head/db sections still get a bound to assert against. A
# genuinely conflicting observed value leaves PIN empty.
if [ "$pin_conflict" -eq 0 ] && [[ "$seen" =~ ^[0-9]+$ ]]; then
    PIN="$seen"
fi
if [ "$pin_bad" -eq 0 ]; then
    echo "  ok: STATE_TRANSITION_V17_HEIGHT=$PIN identical on all hosts"
    record "pin-uniformity" 1 "STATE_TRANSITION_V17_HEIGHT=$PIN uniform on all hosts"
else
    [ -n "$PIN" ] && echo "  NOTE: pin check failed but all reachable hosts agree on $PIN — continuing with it as the bound"
    record "pin-uniformity" 0 "pin drift/unset/unreachable:${pin_report}"
fi

# ---------------------------------------------------------------------------
echo "=== head carries v17 (${HUB_HOST} /rpc/block head) ==="
# The activation itself: the sealed head must sit at/above the pin AND its
# block_metadata must stamp state_transition_version 17. The metadata field
# is stored and served as a JSON string, so the parser decodes it twice.
# No jq anywhere — python3 -c does the JSON work on the remote side.
head_bad=0
head_detail="not run"
if ! host_ok "$HUB_HOST"; then
    head_bad=1
    printf "  %-14s UNREACHABLE — head not verified\n" "$HUB_HOST"
    head_detail="$HUB_HOST unreachable"
elif [ -z "$PIN" ]; then
    head_bad=1
    echo "  FAIL: no uniform integer pin from the pin section — cannot assert head >= pin"
    head_detail="no uniform pin"
else
    # Parses the head block body passed in via HEAD_BODY; prints
    # RESULT|<height>|<stv> or PARSEFAIL|<body prefix>. sys.argv[1] is the pin
    # (kept for future stricter checks).
    HEAD_B64=$(printf '%s' 'import json, os, sys
pin = int(sys.argv[1])
raw = os.environ.get("HEAD_BODY", "")
try:
    d = json.loads(raw)
except Exception:
    print("PARSEFAIL|" + raw[:160].replace("\n", " ")); sys.exit(0)
bm = d.get("block_metadata")
if isinstance(bm, str):
    try:
        bm = json.loads(bm)
    except Exception:
        bm = None
h = d.get("height")
stv = bm.get("state_transition_version") if isinstance(bm, dict) else None
print("RESULT|%s|%s" % (h, stv))' | base64 -w0)
    res=$(sshr "${RESOLVED[$HUB_HOST]}" \
        "port=\$(for f in /etc/aitbc/*.env; do \
             if [ -r \"\$f\" ]; then grep -h '^RPC_BIND_PORT=' \"\$f\" 2>/dev/null; \
             else sudo -n grep -h '^RPC_BIND_PORT=' \"\$f\" 2>/dev/null; fi; \
         done | tail -1 | cut -d= -f2- | tr -d '[:space:]'); \
         port=\${port:-8202}; \
         echo \"PORT|\$port\"; \
         HEAD_BODY=\$(curl -s --max-time 8 \"http://127.0.0.1:\$port/rpc/block\" 2>/dev/null); \
         export HEAD_BODY; \
         python3 -c \"\$(echo '$HEAD_B64' | base64 -d)\" $PIN" \
        || echo "UNREACHABLE")
    rport=$(printf '%s\n' "$res" | sed -n 's/^PORT|//p' | tail -1)
    rline=$(printf '%s\n' "$res" | grep '^RESULT|' | tail -1 || true)
    pline=$(printf '%s\n' "$res" | grep '^PARSEFAIL|' | tail -1 || true)
    if [ -n "$rline" ]; then
        rest=${rline#RESULT|}
        rh=${rest%%|*}
        rs=${rest#*|}
        problems=""
        if [[ ! "$rh" =~ ^[0-9]+$ ]]; then
            problems=" head height '$rh' non-integer"
        elif [ "$rh" -lt "$PIN" ]; then
            problems=" head $rh below pin $PIN — v17 block not sealed yet"
        fi
        [ "$rs" = "17" ] || problems="$problems state_transition_version=$rs (want 17)"
        if [ -n "$problems" ]; then
            head_bad=1
            printf "  %-14s FAIL:%s\n" "$HUB_HOST" "$problems"
            head_detail="head=$rh stv=$rs (want >=$PIN, 17)"
        else
            printf "  %-14s ok: head %s >= pin %s, state_transition_version=17 (port %s)\n" "$HUB_HOST" "$rh" "$PIN" "${rport:-?}"
            head_detail="head=$rh stv=17 pin=$PIN"
        fi
    elif [ -n "$pline" ]; then
        head_bad=1
        printf "  %-14s FAIL: /rpc/block on port %s did not return head JSON (%s)\n" "$HUB_HOST" "${rport:-?}" "${pline#PARSEFAIL|}"
        head_detail="unparseable /rpc/block response on port ${rport:-?}"
    else
        head_bad=1
        printf "  %-14s UNREACHABLE (or no probe output)\n" "$HUB_HOST"
        head_detail="$HUB_HOST unreachable/no output"
    fi
fi
if [ "$head_bad" -eq 0 ]; then
    record "head-carries-v17" 1 "$head_detail"
else
    record "head-carries-v17" 0 "$head_detail"
fi

# ---------------------------------------------------------------------------
echo "=== revived surface live (${PROBE_HOST} /rpc/staking/stake, signed ephemeral probe) ==="
# Signature order on the server: field checks -> 403 signature verify ->
# 410 v17 gate -> 404 account. A signed request that reaches the gate is
# therefore decisive: 410 means still unarmed, anything else means the
# surface is live post-gate (an unfunded ephemeral address can only ever
# draw 404 "Account not found" — the request provably cannot mutate state).
revive_bad=0
revive_detail="not run"
if ! host_ok "$PROBE_HOST"; then
    revive_bad=1
    printf "  %-14s UNREACHABLE — surface not verified\n" "$PROBE_HOST"
    revive_detail="$PROBE_HOST unreachable"
else
    # Runs under /opt/aitbc/venv/bin/python on the probe host (eth_keys +
    # eth_utils live there). The key is generated and discarded in-process —
    # nothing real is ever read, written or sent. Prints STATUS|<code>|<port>|<detail>
    # or ERROR|<err>.
    PROBE_B64=$(printf '%s' 'import json, os, sys, time
import urllib.error
import urllib.request

chain_id = sys.argv[1]
port = sys.argv[2]
try:
    from eth_keys import keys
    from eth_utils import keccak
except Exception as e:
    print("ERROR|import: %s" % e); sys.exit(0)
pk = keys.PrivateKey(os.urandom(32))
addr = pk.public_key.to_checksum_address()
ts = int(time.time())
nonce = 0
amount = 1
msg = {
    "address": addr.lower(),
    "chain_id": chain_id,
    "action": "stake",
    "nonce": nonce,
    "timestamp": ts,
    "amount": amount,
}
digest = keccak(json.dumps(msg, sort_keys=True, separators=(",", ":")).encode())
sig = pk.sign_msg_hash(digest).to_hex()
body = json.dumps({
    "address": addr,
    "chain_id": chain_id,
    "amount": amount,
    "lock_days": 30,
    "nonce": nonce,
    "timestamp": ts,
    "signature": sig,
}).encode()
req = urllib.request.Request(
    "http://127.0.0.1:%s/rpc/staking/stake" % port,
    data=body,
    headers={"Content-Type": "application/json"},
)
try:
    with urllib.request.urlopen(req, timeout=10) as r:
        code, detail = r.getcode(), r.read()
except urllib.error.HTTPError as e:
    code, detail = e.code, e.read()
except Exception as e:
    print("ERROR|%s" % e); sys.exit(0)
detail = detail.decode("utf-8", "replace")[:160].replace("\n", " ")
print("STATUS|%s|%s|%s" % (code, port, detail))' | base64 -w0)
    res=$(sshr "${RESOLVED[$PROBE_HOST]}" \
        "chain=\$(if [ -r /etc/aitbc/blockchain.env ]; then grep -h '^CHAIN_ID=' /etc/aitbc/blockchain.env 2>/dev/null; else sudo -n grep -h '^CHAIN_ID=' /etc/aitbc/blockchain.env 2>/dev/null; fi | tail -1 | cut -d= -f2-); \
         port=\$(if [ -r /etc/aitbc/blockchain.env ]; then grep -h '^RPC_BIND_PORT=' /etc/aitbc/blockchain.env 2>/dev/null; else sudo -n grep -h '^RPC_BIND_PORT=' /etc/aitbc/blockchain.env 2>/dev/null; fi | tail -1 | cut -d= -f2- | tr -d '[:space:]'); \
         chain=\${chain:-bc-2}; port=\${port:-8202}; \
         PY=/opt/aitbc/venv/bin/python; [ -x \"\$PY\" ] || PY=python3; \
         \"\$PY\" -c \"\$(echo '$PROBE_B64' | base64 -d)\" \"\$chain\" \"\$port\"" \
        || echo "UNREACHABLE")
    st=$(printf '%s\n' "$res" | grep '^STATUS|' | tail -1 || true)
    er=$(printf '%s\n' "$res" | grep '^ERROR|' | tail -1 || true)
    if [ -n "$st" ]; then
        rest=${st#STATUS|}
        code=${rest%%|*}
        rest=${rest#*|}
        sport=${rest%%|*}
        sdet=${rest#*|}
        case "$code" in
            410)
                revive_bad=1
                printf "  %-14s FAIL: HTTP 410 — v17 gate still unarmed on this node (%s)\n" "$PROBE_HOST" "$sdet"
                revive_detail="HTTP 410 unarmed on $PROBE_HOST" ;;
            403)
                revive_bad=1
                printf "  %-14s FAIL: HTTP 403 — signed probe rejected; the probe itself is broken (%s)\n" "$PROBE_HOST" "$sdet"
                revive_detail="HTTP 403 signature rejected on $PROBE_HOST" ;;
            *)
                printf "  %-14s ok: HTTP %s on :%s — revived surface answering post-gate (%s)\n" "$PROBE_HOST" "$code" "$sport" "$sdet"
                revive_detail="HTTP $code on $PROBE_HOST:$sport" ;;
        esac
    elif [ -n "$er" ]; then
        revive_bad=1
        printf "  %-14s FAIL: probe error: %s\n" "$PROBE_HOST" "${er#ERROR|}"
        revive_detail="probe error on $PROBE_HOST: ${er#ERROR|}"
    else
        revive_bad=1
        printf "  %-14s UNREACHABLE (or no probe output)\n" "$PROBE_HOST"
        revive_detail="$PROBE_HOST unreachable/no output"
    fi
fi
if [ "$revive_bad" -eq 0 ]; then
    record "revived-surface-live" 1 "$revive_detail"
else
    record "revived-surface-live" 0 "$revive_detail"
fi

# ---------------------------------------------------------------------------
echo "=== dead surfaces stay dead (HTLC + AUTO_STAKE) ==="
# d1: no HTTP route was ever mounted for HTLC — the mutators raise
# RetiredProtocolTransfer in-process — so a plausible dead path must 404.
# d2: the hub chain.db must hold zero HTLC*/AUTO_STAKE rows sealed at/above
# the pin; either type sealing post-activation would mean the retirement
# is not holding.
dead_bad=0
dead_detail="not run"

# d1 — dead-path probe on --probe-host
if ! host_ok "$PROBE_HOST"; then
    dead_bad=1
    printf "  %-14s UNREACHABLE — dead-path probe skipped\n" "$PROBE_HOST"
    dead_detail="$PROBE_HOST unreachable"
else
    res=$(sshr "${RESOLVED[$PROBE_HOST]}" \
        "port=\$(for f in /etc/aitbc/*.env; do \
             if [ -r \"\$f\" ]; then grep -h '^RPC_BIND_PORT=' \"\$f\" 2>/dev/null; \
             else sudo -n grep -h '^RPC_BIND_PORT=' \"\$f\" 2>/dev/null; fi; \
         done | tail -1 | cut -d= -f2- | tr -d '[:space:]'); \
         port=\${port:-8202}; \
         code=\$(curl -s -o /dev/null -w '%{http_code}' --max-time 8 \"http://127.0.0.1:\$port/rpc/htlc/initiate\" 2>/dev/null); \
         echo \"HTLC|\${code:-000}|\$port\"" \
        || echo "UNREACHABLE")
    hline=$(printf '%s\n' "$res" | grep '^HTLC|' | tail -1 || true)
    if [ -n "$hline" ]; then
        hrest=${hline#HTLC|}
        hcode=${hrest%%|*}
        hport=${hrest#*|}
        if [ "$hcode" = "404" ]; then
            printf "  %-14s ok: /rpc/htlc/initiate -> 404 on :%s (route never mounted)\n" "$PROBE_HOST" "$hport"
            dead_detail="htlc-path 404 on :$hport"
        else
            dead_bad=1
            printf "  %-14s FAIL: /rpc/htlc/initiate -> HTTP %s on :%s (expected 404 — something is mounted there)\n" "$PROBE_HOST" "$hcode" "$hport"
            dead_detail="htlc-path HTTP $hcode on :$hport (want 404)"
        fi
    else
        dead_bad=1
        printf "  %-14s UNREACHABLE (or no probe output)\n" "$PROBE_HOST"
        dead_detail="$PROBE_HOST unreachable/no output"
    fi
fi

# d2 — sealed HTLC*/AUTO_STAKE rows at/above the pin, hub chain.db, read-only
if ! host_ok "$HUB_HOST"; then
    dead_bad=1
    printf "  %-14s UNREACHABLE — chain.db check skipped\n" "$HUB_HOST"
    dead_detail="$dead_detail; $HUB_HOST unreachable"
elif [ -z "$PIN" ]; then
    dead_bad=1
    echo "  FAIL: no uniform integer pin from the pin section — cannot bound the db count"
    dead_detail="$dead_detail; no uniform pin for db bound"
else
    # Resolves the db on the remote side and counts in one pass. argv:
    # chain_id, AITBC_DATA_DIR (may be empty), pin. Path resolution:
    # <base>/data/<chain>/chain.db over the env value then the fallbacks;
    # if none matches, a single-hit */chain.db glob is the last resort.
    # sqlite3 mode=ro + isfile so a wrong path can never create an empty db.
    DB_B64=$(printf '%s' 'import glob, os, sqlite3, sys
chain = sys.argv[1]
data_dir = sys.argv[2]
pin = int(sys.argv[3])
bases = ([data_dir] if data_dir else []) + ["/var/lib/aitbc", "/opt/aitbc/data", "/opt/aitbc"]
db = None
for b in bases:
    c = os.path.join(b, "data", chain, "chain.db")
    if os.path.isfile(c):
        db = c
        break
if db is None:
    hits = []
    for b in bases:
        hits += glob.glob(os.path.join(b, "data", "*", "chain.db"))
    if len(hits) == 1:
        db = hits[0]
if db is None:
    print("NODB|" + ",".join(bases) + "|chain=" + chain); sys.exit(0)
try:
    con = sqlite3.connect("file:%s?mode=ro" % db, uri=True)
    n = con.execute(
        "SELECT COUNT(*) FROM \"transaction\""
        " WHERE (type LIKE ? OR type = ?) AND block_height >= ?",
        ("HTLC%", "AUTO_STAKE", pin),
    ).fetchone()[0]
except Exception as e:
    print("DBERR|%s|%s" % (db, e)); sys.exit(0)
print("DB|%s|%d" % (db, n))' | base64 -w0)
    res=$(sshr "${RESOLVED[$HUB_HOST]}" \
        "data_dir=\$(for f in /etc/aitbc/*.env; do \
             if [ -r \"\$f\" ]; then grep -h '^AITBC_DATA_DIR=' \"\$f\" 2>/dev/null; \
             else sudo -n grep -h '^AITBC_DATA_DIR=' \"\$f\" 2>/dev/null; fi; \
         done | tail -1 | cut -d= -f2- | tr -d '[:space:]'); \
         chain=\$(for f in /etc/aitbc/*.env; do \
             if [ -r \"\$f\" ]; then grep -h '^CHAIN_ID=' \"\$f\" 2>/dev/null; \
             else sudo -n grep -h '^CHAIN_ID=' \"\$f\" 2>/dev/null; fi; \
         done | tail -1 | cut -d= -f2-); \
         python3 -c \"\$(echo '$DB_B64' | base64 -d)\" \"\${chain:-bc-2}\" \"\$data_dir\" $PIN" \
        || echo "UNREACHABLE")
    dline=$(printf '%s\n' "$res" | grep '^DB|' | tail -1 || true)
    nline=$(printf '%s\n' "$res" | grep '^NODB|' | tail -1 || true)
    eline=$(printf '%s\n' "$res" | grep '^DBERR|' | tail -1 || true)
    if [ -n "$dline" ]; then
        drest=${dline#DB|}
        dbpath=${drest%%|*}
        dn=${drest#*|}
        if [ "$dn" = "0" ]; then
            printf "  %-14s ok: 0 HTLC*/AUTO_STAKE txs sealed at/above %s in %s\n" "$HUB_HOST" "$PIN" "$dbpath"
            dead_detail="$dead_detail; 0 retired-type rows >=$PIN"
        else
            dead_bad=1
            printf "  %-14s FAIL: %s HTLC*/AUTO_STAKE tx(s) sealed at/above %s in %s — retirement not holding\n" "$HUB_HOST" "$dn" "$PIN" "$dbpath"
            dead_detail="$dead_detail; $dn retired-type rows >=$PIN"
        fi
    elif [ -n "$nline" ]; then
        dead_bad=1
        printf "  %-14s FAIL: no chain.db found under any candidate base (%s) — dead-type count not proven\n" "$HUB_HOST" "${nline#NODB|}"
        dead_detail="$dead_detail; chain.db not found"
    elif [ -n "$eline" ]; then
        dead_bad=1
        printf "  %-14s FAIL: chain.db open/query failed: %s\n" "$HUB_HOST" "${eline#DBERR|}"
        dead_detail="$dead_detail; db error: ${eline#DBERR|}"
    else
        dead_bad=1
        printf "  %-14s UNREACHABLE (or no probe output)\n" "$HUB_HOST"
        dead_detail="$dead_detail; $HUB_HOST unreachable/no output"
    fi
fi
if [ "$dead_bad" -eq 0 ]; then
    record "dead-surfaces-stay-dead" 1 "$dead_detail"
else
    record "dead-surfaces-stay-dead" 0 "$dead_detail"
fi

# ---------------------------------------------------------------------------
echo
overall_bad=$(( pin_bad || head_bad || revive_bad || dead_bad || resolve_bad ))
if [ "$overall_bad" -eq 0 ]; then
    echo "v17-activation-verify: PASS — pin uniform, head on v17, revived surface live, dead surfaces dead"
else
    echo "v17-activation-verify: FAIL — see flagged sections above"
fi

if [ "$JSON_OUT" -eq 1 ]; then
    if command -v python3 >/dev/null 2>&1; then
        for i in "${!CHECK_NAMES[@]}"; do
            printf '%s\t%s\t%s\n' "${CHECK_NAMES[$i]}" "${CHECK_OKS[$i]}" "${CHECK_DETAILS[$i]}"
        done | OVERALL=$((1 - overall_bad)) python3 -c 'import json, os, sys
checks = []
for line in sys.stdin:
    line = line.rstrip("\n")
    if not line:
        continue
    name, ok, det = line.split("\t", 2)
    checks.append({"name": name, "ok": ok == "1", "details": det})
print(json.dumps({"checks": checks, "pass": os.environ.get("OVERALL") == "1"}))'
    else
        echo "NOTE: --json requested but no local python3 — JSON report skipped" >&2
    fi
fi

exit "$overall_bad"
