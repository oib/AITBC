#!/usr/bin/env python3
"""Generate consolidated route docs from live service OpenAPI specs.

Fetches /openapi.json from each listed service on the node where it runs and
renders a Markdown route table. The service inventory is deliberately NOT in
the repo — pass it per run:

    python3 scripts/docs/gen_all_routes.py \
        --node <node-name> \
        --services "api-gateway:8201,coordinator-api:8203,marketplace:8102,..."

    # or via env
    AITBC_ROUTE_SERVICES="api-gateway:8201,..." python3 ... --node <name>

Unreachable services are listed under "unreachable services" rather than
silently dropped.
"""

import argparse
import json
import os
import sys
import urllib.request


def parse_services(raw: str) -> list[tuple[str, int]]:
    services = []
    for item in raw.split(","):
        name, _, port = item.strip().partition(":")
        if not name or not port:
            raise SystemExit(f"bad --services entry {item!r} (expected name:port)")
        services.append((name, int(port)))
    return services


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
    parser.add_argument("--node", required=True, help="label for the node being scanned (heading text only)")
    parser.add_argument(
        "--services",
        default=os.environ.get("AITBC_ROUTE_SERVICES", ""),
        help="comma-separated name:port inventory, or set AITBC_ROUTE_SERVICES",
    )
    args = parser.parse_args()
    if not args.services:
        parser.error("--services or AITBC_ROUTE_SERVICES is required")

    print(f"## Routes on {args.node}")
    print()
    unreachable = []
    for name, port in parse_services(args.services):
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
