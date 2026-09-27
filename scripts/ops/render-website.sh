#!/bin/bash
# Render website branding tokens (public domain + chain id) into the committed
# static files under website/. The site is served by nginx straight from the
# repo checkout, so "configuring" these files means rewriting them in place:
#
#   sitemap.xml robots.txt llms.txt structured-data.jsonld index.html
#   follower-api-key-announcement.html   <- absolute https://<domain>/... URLs
#   config.js dashboard.js               <- hardcoded chainId fallbacks
#
# Values come from /etc/aitbc/website.env:
#   WEBSITE_DOMAIN    e.g. hub.example.net      (fallback: node.env AITBC_HOSTNAME,
#                                                 then HUB_DISCOVERY_URL)
#   WEBSITE_CHAIN_ID  e.g. ait-hub.example.net  (fallback: node.env CHAIN_ID)
#
# The render step is opt-in: it only runs when /etc/aitbc/website.env exists
# (see examples/website.env.example). update.sh calls this after every pull, so files
# re-render whenever a pull reverts them to the committed defaults. On the
# canonical deployment the env values equal the committed defaults and the
# render is a no-op, keeping the working tree clean.
#
# To revert to the committed values: remove /etc/aitbc/website.env and
# /etc/aitbc/.website-rendered.env, then `git -C /opt/aitbc checkout -- website/`.
#
# Usage (on the hub, as root):
#   bash /opt/aitbc/scripts/ops/render-website.sh

set -euo pipefail

AITBC_ROOT="${AITBC_ROOT:-/opt/aitbc}"
WEB_DIR="$AITBC_ROOT/website"
ENV_FILE="${WEBSITE_ENV_FILE:-/etc/aitbc/website.env}"
NODE_ENV="${NODE_ENV_FILE:-/etc/aitbc/node.env}"
STATE_FILE="${STATE_FILE:-/etc/aitbc/.website-rendered.env}"

# Source tokens recognized in the files: the committed defaults plus
# hub.example.net, which doc-style pages have used as a stand-in for "this
# hub" and is rewritten to the real domain like everything else. After the
# first render the values recorded in STATE_FILE are anchors too, so a
# website.env change re-renders even when the working tree keeps the
# previously rendered content (update.sh stash/pop preserves it across pulls).
DEFAULT_DOMAIN="hub.aitbc.bubuit.net"
DEFAULT_CHAIN_ID="ait-hub.aitbc.bubuit.net"
EXTRA_DOMAINS="hub.example.net"

# Unlikely sentinel used to shield chain-id occurrences while the domain is
# rewritten (a chain id like ait-hub.<domain> contains the domain as a
# substring — without shielding, the domain pass would corrupt it).
PH='@__AITBC_CHAIN_ID__@'

FILES="sitemap.xml robots.txt llms.txt structured-data.jsonld index.html config.js dashboard.js follower-api-key-announcement.html"

[ -f "$ENV_FILE" ] || { echo "No $ENV_FILE — website branding not configured, nothing to do."; exit 0; }
[ -d "$WEB_DIR" ] || { echo "Missing website dir: $WEB_DIR" >&2; exit 1; }

value_of() {  # value_of <key> <file>
    grep -E "^${1}=" "$2" 2>/dev/null | tail -1 | cut -d= -f2- | tr -d "'\"" || true
}

# Resolve target values: website.env first, node.env fallbacks, then defaults.
NEW_DOMAIN="$(value_of WEBSITE_DOMAIN "$ENV_FILE")"
NEW_CHAIN_ID="$(value_of WEBSITE_CHAIN_ID "$ENV_FILE")"
[ -z "$NEW_DOMAIN" ]   && NEW_DOMAIN="$(value_of AITBC_HOSTNAME "$NODE_ENV")"
[ -z "$NEW_DOMAIN" ]   && NEW_DOMAIN="$(value_of HUB_DISCOVERY_URL "$NODE_ENV")"
[ -z "$NEW_CHAIN_ID" ] && NEW_CHAIN_ID="$(value_of CHAIN_ID "$NODE_ENV")"
NEW_DOMAIN="${NEW_DOMAIN:-$DEFAULT_DOMAIN}"
NEW_CHAIN_ID="${NEW_CHAIN_ID:-$DEFAULT_CHAIN_ID}"

# Conservative charset: these values are substituted into sed patterns and
# markup; anything outside it is a config error, not something to escape.
[[ "$NEW_DOMAIN" =~ ^[a-z0-9][a-z0-9.-]*$ ]] \
    || { echo "Invalid WEBSITE_DOMAIN: $NEW_DOMAIN" >&2; exit 1; }
[[ "$NEW_CHAIN_ID" =~ ^[a-zA-Z0-9][a-zA-Z0-9._~-]*$ ]] \
    || { echo "Invalid WEBSITE_CHAIN_ID: $NEW_CHAIN_ID" >&2; exit 1; }

# What is currently in the files: last rendered values if recorded, else the
# committed defaults.
CUR_DOMAIN="$(value_of WEBSITE_DOMAIN "$STATE_FILE")"
CUR_CHAIN_ID="$(value_of WEBSITE_CHAIN_ID "$STATE_FILE")"
CUR_DOMAIN="${CUR_DOMAIN:-$DEFAULT_DOMAIN}"
CUR_CHAIN_ID="${CUR_CHAIN_ID:-$DEFAULT_CHAIN_ID}"

esc() { printf '%s' "$1" | sed 's/\./\\./g'; }  # escape dots for the match side

# Chain strings to shield: every form that may appear in the files (current,
# committed-default, and target — a partially rendered file can hold NEW).
CHAIN_ALT=""
while IFS= read -r v; do
    CHAIN_ALT="${CHAIN_ALT:+$CHAIN_ALT|}$(esc "$v")"
done < <(printf '%s\n' "$CUR_CHAIN_ID" "$DEFAULT_CHAIN_ID" "$NEW_CHAIN_ID" | sort -u)

# Domain rewrites: only sources that differ from the target need substituting.
DOMAIN_EXPRS=()
TRIGGER_ALTS=()
add_domain() {  # add_domain <source>
    [ "$1" = "$NEW_DOMAIN" ] && return
    DOMAIN_EXPRS+=(-e "s#$(esc "$1")#$NEW_DOMAIN#g")
    TRIGGER_ALTS+=("$(esc "$1")")
}
add_domain "$CUR_DOMAIN"
add_domain "$DEFAULT_DOMAIN"
for d in $EXTRA_DOMAINS; do add_domain "$d"; done

# Chain rewrites likewise (CUR/DEFAULT -> NEW); NEW itself is already covered
# by the shield/restore pair.
[ "$CUR_CHAIN_ID" != "$NEW_CHAIN_ID" ]     && TRIGGER_ALTS+=("$(esc "$CUR_CHAIN_ID")")
[ "$DEFAULT_CHAIN_ID" != "$NEW_CHAIN_ID" ] && TRIGGER_ALTS+=("$(esc "$DEFAULT_CHAIN_ID")")

if [ "${#TRIGGER_ALTS[@]}" -eq 0 ]; then
    printf 'WEBSITE_DOMAIN=%s\nWEBSITE_CHAIN_ID=%s\n' "$NEW_DOMAIN" "$NEW_CHAIN_ID" > "$STATE_FILE"
    chmod 644 "$STATE_FILE"
    echo "Website branding already up to date (domain=$NEW_DOMAIN, chain_id=$NEW_CHAIN_ID)."
    exit 0
fi

# Safety: the sentinel must not already appear in content.
if grep -rlF "$PH" "$WEB_DIR" >/dev/null 2>&1; then
    echo "Sentinel $PH found in $WEB_DIR — refusing to render." >&2
    exit 1
fi

GREP_RE="$(IFS='|'; echo "${TRIGGER_ALTS[*]}")"
CHANGED=0
for f in $FILES; do
    path="$WEB_DIR/$f"
    [ -f "$path" ] || continue
    if grep -qE "$GREP_RE" "$path"; then
        sed -i -E \
            -e "s#$CHAIN_ALT#$PH#g" \
            "${DOMAIN_EXPRS[@]}" \
            -e "s#$PH#$NEW_CHAIN_ID#g" \
            "$path"
        CHANGED=$((CHANGED + 1))
    fi
done

printf 'WEBSITE_DOMAIN=%s\nWEBSITE_CHAIN_ID=%s\n' "$NEW_DOMAIN" "$NEW_CHAIN_ID" > "$STATE_FILE"
chmod 644 "$STATE_FILE"

echo "Website branding rendered: domain=$NEW_DOMAIN chain_id=$NEW_CHAIN_ID ($CHANGED files updated)."
