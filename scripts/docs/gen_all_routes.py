#!/usr/bin/env python3
"""Generate docs/reference/all-routes.md from live service OpenAPI specs.

Fetches /openapi.json from every reachable service on a node and renders a
consolidated Markdown route reference. Run once per node:

    python3 scripts/docs/gen_all_routes.py --node hub   > /tmp/routes-hub.md
    python3 scripts/docs/gen_all_routes.py --node node2 > /tmp/routes-node2.md

Then concatenate the outputs (plus the static header) into
docs/reference/all-routes.md. Services that are unreachable are listed under
"unreachable services" rather than silently dropped.
"""

import argparse
import json
import sys
import urllib.request

FLEET = {
    "hub": [
        ("api-gateway", 8201),
        ("blockchain-rpc", 8202),
        ("coordinator-api", 8203),
        ("explorer", 8100),
        ("marketplace", 8102),
        ("trading", 8104),
        ("governance", 8105),
        ("exchange", 8106),
        ("agent-coordinator", 8107),
        ("wallet", 8108),
        ("pool-hub", 8210),
    ],
    "node2": [
        ("gpu", 8101),
        ("edge-api", 8111),
        ("ffmpeg", 8230),
        ("hermes", 8270),
    ],
}


def fetch_openapi(port: int, timeout: float = 5.0) -> dict | None:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/openapi.json", timeout=timeout) as resp:
            return json.load(resp)
    except Exception:
        return None


def render_service(name: str, port: int, spec: dict) -> list[str]:
    title = spec.get("info", {}).get("title", name)
    version = spec.get("info", {}).get("version", "?")
    lines = [f"### {name} (`:{port}`, {title} v{version})", ""]
    lines.append("| Method | Path | Summary |")
    lines.append("|---|---|---|")
    paths = spec.get("paths", {})
    for path in sorted(paths):
        for method, op in sorted(paths[path].items()):
            if method not in ("get", "post", "put", "delete", "patch", "head", "options"):
                continue
            summary = (op.get("summary") or op.get("operationId") or "").replace("|", "\\|")
            lines.append(f"| `{method.upper()}` | `{path}` | {summary} |")
    lines.append("")
    return lines


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--node", required=True, choices=sorted(FLEET), help="fleet node whose localhost services to scan")
    args = parser.parse_args()

    print(f"## Routes on {args.node}")
    print()
    unreachable = []
    for name, port in FLEET[args.node]:
        spec = fetch_openapi(port)
        if spec is None:
            unreachable.append(f"{name} (`:{port}`)")
            continue
        for line in render_service(name, port, spec):
            print(line)
    if unreachable:
        print("### Unreachable services")
        print()
        for s in unreachable:
            print(f"- {s}")
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
