"""#890: the in-container explorer uses the same-origin /rpc/ proxy and
pinned, integrity-hashed third-party scripts.

On base the page fetched http://localhost:8202 — the *visitor's* machine —
and loaded cdn.tailwindcss.com + unpkg lucide@latest unpinned and
unhashed, so any upstream change ran in the explorer's origin. Now the
nginx vhost proxies /rpc/ to the node and both scripts are version-pinned
with SRI.
"""

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
IN_CONTAINER = REPO / "scripts" / "deployment" / "deploy" / "deploy-in-container.sh"
REMOTE = REPO / "scripts" / "deployment" / "deploy" / "deploy-explorer-remote.sh"

BOTH = [IN_CONTAINER, REMOTE]


def test_same_origin_rpc_and_proxy_location():
    src = IN_CONTAINER.read_text()
    assert "RPC_URL = ''" in src
    assert "localhost:8202';" not in src
    block = src[src.index("location /rpc/") :]
    assert "proxy_pass http://localhost:8202" in block


def test_proxy_block_inside_the_explorer_server():
    src = IN_CONTAINER.read_text()
    server = src[src.index("server {") : src.index("EOL", src.index("server {"))]
    assert "location /rpc/" in server and "proxy_pass" in server


def test_third_party_scripts_pinned_with_sri():
    for p in BOTH:
        src = p.read_text()
        assert "lucide@latest" not in src, f"{p.name} still unpinned"
        assert 'src="https://cdn.tailwindcss.com"' not in src, f"{p.name} still unversioned tailwind"
        for m in re.finditer(r'<script src="(https://[^"]+)"', src):
            tag = src[m.start() : src.index(">", m.start())]
            assert 'integrity="sha384-' in tag and 'crossorigin="anonymous"' in tag, (
                f"{p.name}: external script {m.group(1)} lacks SRI"
            )
