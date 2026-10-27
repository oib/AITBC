#!/usr/bin/env python3
"""failover-gen.py — build a hub1 flip variant of hub's nginx site.

Offline generator: reads a byte-copy of hub's live
``sites-enabled/aitbc`` and writes the flip variant that proxies the
FLIP location set to hub1 while pinning node-local paths to hub. See
``docs/ops/failover-runbook.md``.

Usage: failover-gen.py <live-file> <output-file> [include-path]

  <live-file>    copy of the live sites-enabled/aitbc (sha-check it first)
  <output-file>  the variant to write (drill name: aitbc.flip-a)
  [include-path] upstream include emitted inside each flipped location
                 (default /etc/nginx/aitbc-flip/to-hub1.conf)

The FLIP set is the five location blocks proxied to hub1 (rpc +
explorer API read paths). The STAY/carve-out sets are node-local views
and hub-local data that must keep answering from hub, emitted as exact
(=) or prefix (^~) matches ahead of the flipped prefix blocks.
"""

import re
import sys

FLIP = [
    "location /rpc/ {",
    "location /explorer-api/ {",
    "location = /explorer-api/api/messages {",
    "location = /explorer-api/api/messages/topics {",
    "location = /explorer-api/api/messages/state {",
]

# Node-local state behind a flipped prefix: pinned to hub explicitly.
# islands/chains/network-info are the node's own membership/advertisement
# views; subscribers/join/subscribe/heartbeat/lease/market are local state.
CARVE_RPC = [
    ("=", "/rpc/join"),
    ("=", "/rpc/subscribe"),
    ("=", "/rpc/heartbeat"),
    ("=", "/rpc/subscribers"),
    ("^~", "/rpc/lease/"),
    ("^~", "/rpc/market/"),
    ("^~", "/rpc/islands"),
    ("^~", "/rpc/chains"),
    ("=", "/rpc/network-info"),
]
CARVE_EXP = [("^~", "/explorer-api/api/journal/"), ("^~", "/explorer-api/api/alerts")]


def _blk(mod, loc, target):
    return [
        f"    location {mod} {loc} {{",
        f"        proxy_pass http://{target};",
        "        proxy_set_header Host $host;",
        "        proxy_set_header X-Real-IP $remote_addr;",
        "        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;",
        "        proxy_set_header X-Forwarded-Proto $http_x_forwarded_proto;",
        "    }",
    ]


def _prefixers(include):
    return {
        "location /rpc/ {": [
            "    # failover: node-local rpc state stays on hub (peer_keys, leases, rpc market,\n"
            "    # islands/chains membership views, advertised endpoints)"
        ]
        + sum([_blk(m, loc, "blockchain_rpc" + loc) for m, loc in CARVE_RPC], [])
        + [""],
        "location /explorer-api/ {": ["    # failover: node-local explorer data stays on hub (journal, alerts)"]
        + sum([_blk(m, loc, "blockchain_explorer" + loc[len("/explorer-api") :]) for m, loc in CARVE_EXP], [])
        + [""],
    }


def _collect_block(lines, i):
    """Return (block_lines, next_i) for the location block starting at line i."""
    depth = 0
    block = []
    while True:
        b = lines[i]
        block.append(b)
        depth += b.count("{") - b.count("}")
        i += 1
        if depth == 0:
            return block, i


def _rewrite_block(block, include):
    """Rewrite one FLIP location block to include the failover upstream stub."""
    ind = re.match(r"\s*", block[1]).group(0)
    rip = any("X-Real-IP" in b for b in block)
    out = []
    done = False
    for b in block:
        t = b.strip()
        if t.startswith("proxy_pass "):
            if not done:
                out.append(ind + f"include {include};  # failover flip, was: {t}")
                if not rip:
                    out.append(ind + "proxy_set_header X-Real-IP $remote_addr;")
                done = True
            continue
        if t.startswith("proxy_set_header Host ") or t.startswith("proxy_ssl_"):
            continue
        out.append(b)
    if not done:
        sys.exit("no proxy_pass in " + block[0].strip())
    return out


def build(src, include):
    lines = open(src).read().split("\n")
    pre = _prefixers(include)
    out = []
    i = 0
    hit = set()
    while i < len(lines):
        s = lines[i].strip()
        if s in FLIP and s not in hit:
            hit.add(s)
            out.extend(pre.get(s, []))
            block, i = _collect_block(lines, i)
            out.extend(_rewrite_block(block, include))
            continue
        out.append(lines[i])
        i += 1
    if set(FLIP) - hit:
        sys.exit("missing: %s" % (set(FLIP) - hit))
    return "\n".join(out)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    src, dst = sys.argv[1], sys.argv[2]
    inc = sys.argv[3] if len(sys.argv) > 3 else "/etc/nginx/aitbc-flip/to-hub1.conf"
    open(dst, "w").write(build(src, inc))
    print("ok flipped:", len(FLIP), "carve-outs:", len(CARVE_RPC) + len(CARVE_EXP))
