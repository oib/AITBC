#!/bin/sh
# fix-x-forwarded-proto.sh — repair the #1694/#1778 client-echo defect in
# LIVE nginx configs: `proxy_set_header X-Forwarded-Proto
# $http_x_forwarded_proto;` lets a client claim any scheme; it must be
# `$scheme`. Repo examples are already fixed — this script exists because
# /etc/nginx does not pick up repo changes.
#
# Run ON the target host (hub, hub1, ...) as root:
#   ssh hub 'sh /opt/aitbc/scripts/ops/fix-x-forwarded-proto.sh'            # dry-run report
#   ssh hub 'sh /opt/aitbc/scripts/ops/fix-x-forwarded-proto.sh --apply'    # fix + reload
#
# --apply: backs up every touched file to <file>.xfp-bak-<epoch>, seds,
# runs `nginx -t`, and reloads ONLY if the config test passes; on failure
# the backups are restored and nothing is reloaded. Idempotent — a second
# run reports zero occurrences.
#
# ORDERING (#1778): fix hub's live site BEFORE regenerating failover
# variants — failover-gen.py copies FLIP blocks verbatim from the source
# live file, so a variant generated pre-fix re-inherits the defect.
#
# Env: NGINX_ROOT=/etc/nginx   SCAN_DIRS="/etc/nginx/sites-enabled /etc/nginx/conf.d"
set -euo pipefail

NGINX_ROOT="${NGINX_ROOT:-/etc/nginx}"
SCAN_DIRS="${SCAN_DIRS:-/etc/nginx/sites-enabled /etc/nginx/conf.d}"
BAD='proxy_set_header X-Forwarded-Proto $http_x_forwarded_proto;'
GOOD='proxy_set_header X-Forwarded-Proto $scheme;'
APPLY=0
[ "${1:-}" = "--apply" ] && APPLY=1

occurrences=0
files=""
for d in $SCAN_DIRS; do
  [ -d "$d" ] || continue
  # shellcheck disable=SC2044
  for f in $(grep -rlF 'X-Forwarded-Proto $http_x_forwarded_proto' "$d" 2>/dev/null | grep -v '\.xfp-bak-' || true); do
    n=$(grep -cF "$BAD" "$f" || true)
    [ "$n" -gt 0 ] || continue
    occurrences=$((occurrences + n))
    files="$files$f
"
    printf '%-58s %s occurrence(s)\n' "$f" "$n"
  done
done

if [ -f "$NGINX_ROOT/nginx.conf" ] && grep -qF "$BAD" "$NGINX_ROOT/nginx.conf"; then
  n=$(grep -cF "$BAD" "$NGINX_ROOT/nginx.conf" || true)
  occurrences=$((occurrences + n))
  files="$files$NGINX_ROOT/nginx.conf
"
  printf '%-58s %s occurrence(s)\n' "$NGINX_ROOT/nginx.conf" "$n"
fi

printf 'total: %s occurrence(s) in %s file(s)\n' "$occurrences" "$(printf '%s' "$files" | grep -c . || true)"

if [ "$APPLY" -eq 0 ]; then
  [ "$occurrences" -gt 0 ] && echo "dry-run — re-run with --apply to fix" >&2 || echo "clean — nothing to do"
  exit 0
fi
[ "$occurrences" -eq 0 ] && { echo "nothing to do"; exit 0; }

stamp=$(date +%s)
printf '%s' "$files" | while IFS= read -r f; do
  [ -n "$f" ] || continue
  cp -a "$f" "$f.xfp-bak-$stamp"
  sed -i "s|$BAD|$GOOD|g" "$f"
done
# verify substitution took — check only the files we touched; .xfp-bak-*
# backups still contain the old header by design and must not trip this.
still_bad=$(printf '%s' "$files" | while IFS= read -r f; do
  [ -n "$f" ] && grep -lF "$BAD" "$f"
done || true)
if [ -n "$still_bad" ]; then
  echo "FAIL: occurrences remain after sed — restoring backups" >&2
  printf '%s' "$files" | while IFS= read -r f; do
    [ -n "$f" ] && [ -f "$f.xfp-bak-$stamp" ] && mv "$f.xfp-bak-$stamp" "$f"
  done
  exit 1
fi

if ! nginx -t; then
  echo "FAIL: nginx -t rejected config — restoring backups" >&2
  printf '%s' "$files" | while IFS= read -r f; do
    [ -n "$f" ] && [ -f "$f.xfp-bak-$stamp" ] && mv "$f.xfp-bak-$stamp" "$f"
  done
  exit 1
fi

systemctl reload nginx
printf 'OK: fixed %s occurrence(s); backups at <file>.xfp-bak-%s\n' "$occurrences" "$stamp"
echo "NEXT: regenerate failover variants (failover-gen.py reads the live file)"
