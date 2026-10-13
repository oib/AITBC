#!/bin/bash
# offsite-pull-backups.sh -- pull the newest complete aitbc-backup generation
# from each fleet host onto this machine.
#
# Pull model: the fleet hosts never push and hold no credentials for the
# destination; the operator's IDE host reaches out over the existing ssh
# aliases. Each generation is rsynced into <host>/<gen>.partial/, verified
# against a sha256 manifest computed on the host in the same ssh session
# that selected the generation, encrypted with age to AGE_RECIPIENT
# (operator decision BK-2: encrypt every pulled file), then completed
# atomically as <host>/<gen>/. The plaintext staging dir is removed; the
# sha256 manifest travels along encrypted as SHA256SUMS.age so a restore
# can re-verify after decryption.
#
# Env:
#   DEST          landing root (default ~/windsurf/aitbc/backups/fleet-nightly)
#   HOSTS         space-separated ssh aliases (default: hub hub1 node0 node1 node2)
#   KEEP          generations retained per host (default 14)
#   AGE_RECIPIENT age recipient; REQUIRED -- plaintext storage is refused
#   STABLE_MIN    minutes a generation must be untouched to count complete (10)
#   MIN_FREE_GB   refuse below this free space on the destination fs (20)
#   REMOTE_BASE   fleet-side backup root (default /var/backups/aitbc)
#
# Args: --dry-run (list what would be pulled), --host <alias> (one host).
# Exit: non-zero if any host failed or any checksum mismatched.
set -euo pipefail
umask 077

DEST="${DEST:-$HOME/windsurf/aitbc/backups/fleet-nightly}"
HOSTS="${HOSTS:-hub hub1 node0 node1 node2}"
KEEP="${KEEP:-14}"
AGE_RECIPIENT="${AGE_RECIPIENT:-}"
STABLE_MIN="${STABLE_MIN:-10}"
MIN_FREE_GB="${MIN_FREE_GB:-20}"
REMOTE_BASE="${REMOTE_BASE:-/var/backups/aitbc}"
GEN_GLOB='20??????_??????'
DRY_RUN=0
ONE_HOST=""

log() { printf '%s\n' "$*"; }
warn() { printf 'WARN: %s\n' "$*" >&2; }

usage() {
    sed -n '2,30p' "$0"
    exit "${1:-0}"
}

while [ $# -gt 0 ]; do
    case "$1" in
        --dry-run) DRY_RUN=1 ;;
        --host) ONE_HOST="${2:?--host needs an alias}"; shift ;;
        -h|--help) usage 0 ;;
        *) warn "unknown arg: $1"; usage 2 ;;
    esac
    shift
done
[ -n "$ONE_HOST" ] && HOSTS="$ONE_HOST"

[ -n "$AGE_RECIPIENT" ] || {
    warn "AGE_RECIPIENT unset -- refusing to store unencrypted fleet backups."
    warn "Set AGE_RECIPIENT to an age recipient (age1...) for the operator identity."
    exit 2
}
command -v age >/dev/null || { warn "age not installed"; exit 2; }
command -v rsync >/dev/null || { warn "rsync not installed"; exit 2; }

# --- disk guard: refuse under MIN_FREE_GB on the destination filesystem ---
_p="$DEST"; while [ ! -d "$_p" ]; do _p="$(dirname "$_p")"; done
avail_kb=$(df -Pk "$_p" | awk 'NR==2 {print $4}')
if [ "$avail_kb" -lt "$((MIN_FREE_GB * 1024 * 1024))" ]; then
    warn "only $((avail_kb / 1024 / 1024)) GB free on $_p (need ${MIN_FREE_GB}G) -- refusing"
    exit 2
fi
install -d -m 700 "$DEST"

# Remote probe: pick the newest generation dir untouched for STABLE_MIN
# minutes (the nightly job finishes in well under a minute at ~01:0x; a dir
# still being written has recent mtimes), then emit its sha256 manifest and
# byte size. One ssh session covers selection + manifest so the manifest can
# never describe a different generation than the one we pull.
remote_probe() {
    # client-side expansion of REMOTE_BASE/STABLE_MIN is intentional: they
    # are sent as assignments and expanded by the remote shell.
    # shellcheck disable=SC2029
    ssh "$1" "REMOTE_BASE='$REMOTE_BASE'; STABLE_MIN='$STABLE_MIN';
        gen=\$(find \"\$REMOTE_BASE\" -maxdepth 1 -type d -name '$GEN_GLOB' -mmin +\"\$STABLE_MIN\" -printf '%f\n' | sort | tail -1);
        [ -n \"\$gen\" ] || exit 3;
        size=\$(du -sb \"\$REMOTE_BASE/\$gen\" | cut -f1);
        (cd \"\$REMOTE_BASE/\$gen\" && sha256sum -- *);
        echo \"GEN \$gen\"; echo \"SIZE \$size\""
}

retention() {
    # Keep the newest KEEP name-matched generations; never delete the newest
    # VERIFIED one (SHA256SUMS.age present); never touch foreign names.
    local dir=$1 d name kept=0 newest_verified=""
    [ -d "$dir" ] || return 0
    while IFS= read -r d; do
        name=${d##*/}
        if [ -f "$d/SHA256SUMS.age" ] && [ -z "$newest_verified" ]; then
            newest_verified=$name
        fi
        kept=$((kept + 1))
        if [ "$kept" -gt "$KEEP" ] && [ "$name" != "$newest_verified" ]; then
            log "retention: removing $name (> ${KEEP} generations)"
            rm -rf "$d"
        fi
    done < <(find "$dir" -maxdepth 1 -type d -name "$GEN_GLOB" -printf '%p\n' | sort -r)
}

fails=0
for host in $HOSTS; do
    probe=$(remote_probe "$host") || {
        warn "$host: probe failed (rc=$? -- no stable generation or unreachable)"
        fails=$((fails + 1)); continue
    }
    gen=$(printf '%s\n' "$probe" | awk '/^GEN /{print $2}')
    size=$(printf '%s\n' "$probe" | awk '/^SIZE /{print $2}')
    manifest=$(printf '%s\n' "$probe" | grep -v -e '^GEN ' -e '^SIZE ')
    [ -n "$gen" ] || { warn "$host: no generation reported"; fails=$((fails+1)); continue; }

    dest_dir="$DEST/$host/$gen"
    if [ -f "$dest_dir/SHA256SUMS.age" ]; then
        log "$host: $gen already verified -- skipped"
        retention "$DEST/$host"
        continue
    fi
    if [ "$DRY_RUN" -eq 1 ]; then
        log "$host: would pull $gen ($((size / 1024 / 1024)) MB, $(printf '%s\n' "$manifest" | grep -c .) files)"
        continue
    fi

    install -d -m 700 "$DEST/$host"
    partial="$dest_dir.partial"
    rm -rf "$partial"
    install -d -m 700 "$partial"
    if ! rsync -a --partial "$host:$REMOTE_BASE/$gen/" "$partial/" >/dev/null; then
        warn "$host: rsync failed for $gen"
        rm -rf "$partial"; fails=$((fails + 1)); continue
    fi

    # Checksum the received plaintext against the host-side manifest.
    local_sums=$(cd "$partial" && sha256sum -- *)
    if [ "$local_sums" != "$manifest" ]; then
        warn "$host: CHECKSUM MISMATCH for $gen -- discarded"
        rm -rf "$partial"; fails=$((fails + 1)); continue
    fi

    # Encrypt every pulled file; manifest travels encrypted for restore-time
    # verification. dest_dir exists only when fully encrypted (SHA256SUMS.age
    # is written last and doubles as the verified marker).
    [ -d "$dest_dir" ] && rm -rf "$dest_dir"
    install -d -m 700 "$dest_dir"
    enc_ok=1
    while IFS= read -r f; do
        age -r "$AGE_RECIPIENT" -o "$dest_dir/$f.age" "$partial/$f" || { enc_ok=0; break; }
        chmod 600 "$dest_dir/$f.age"
    done < <(cd "$partial" && find . -maxdepth 1 -type f -printf '%f\n')
    if [ "$enc_ok" -eq 1 ]; then
        printf '%s\n' "$manifest" | age -r "$AGE_RECIPIENT" -o "$dest_dir/SHA256SUMS.age" || enc_ok=0
        [ -f "$dest_dir/SHA256SUMS.age" ] && chmod 600 "$dest_dir/SHA256SUMS.age"
    fi
    if [ "$enc_ok" -ne 1 ]; then
        warn "$host: encryption failed for $gen -- discarded"
        rm -rf "$partial" "$dest_dir"; fails=$((fails + 1)); continue
    fi
    rm -rf "$partial"
    log "$host: pulled $gen -> $dest_dir ($((size / 1024 / 1024)) MB, verified + encrypted)"
    retention "$DEST/$host"
done

if [ "$fails" -gt 0 ]; then
    log "offsite-pull: DONE with $fails host failure(s)"
    exit 1
fi
log "offsite-pull: DONE all hosts ok"
