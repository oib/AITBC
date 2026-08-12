"""No repo-managed config or page may publish a credentials file over HTTP (V23-58).

The hub served `/agent/blockchain-secrets.env` unauthenticated, with CORS open to `*`, for as
long as the endpoint existed. The two values behind it are credentials rather than settings:
`COORDINATOR_API_KEY` authenticates as role `miner` through the `X-Api-Key` dependency in
`aitbc/auth/dependencies.py`, and the agent-coordinator faucet and websocket routers accept
either it *or* `SECRET_KEY`, so one value opens both surfaces.

Nothing needed it to be public. `blockchain-node` reads neither variable, so a node joining
the island to follow the chain never had a reason to fetch it — only `blockchain.env` and
`genesis.json`, which are genuinely public.

This survived because it looked deliberate at every layer: an nginx block, a documented curl,
a link on the landing page, and a doc line asserting the keys "are public". One reviewer got
close enough to write "that file is published on the website ... must not contain database
credentials" in `setup-service-selection.md` and routed around it instead. So these tests
pin the invariant rather than any single file: a grep-able rule is what a future reviewer
consults, and re-adding the alias is the obvious way this returns.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

# Files that describe what a host serves publicly.
PUBLISHING_CONFIGS = [
    "examples/nginx/nginx-aitbc.conf.example",
    "website/index.html",
]

# Anything matching this names a secrets file in a served path.
SECRETS_FILE = re.compile(r"[\w.-]*secrets?[\w.-]*\.env")


def _read(relative: str) -> str:
    path = REPO / relative
    if not path.exists():
        pytest.skip(f"{relative} not in this checkout")
    return path.read_text()


def test_no_nginx_location_serves_a_secrets_file() -> None:
    """The exact defect: `location = /agent/blockchain-secrets.env { alias ...; }`."""
    config = _read("examples/nginx/nginx-aitbc.conf.example")

    for block in re.finditer(r"location[^{]*\{[^}]*\}", config, re.DOTALL):
        body = block.group(0)
        if "alias" not in body and "root" not in body:
            continue  # a proxy_pass or a `return 404` cannot expose a local file
        assert not SECRETS_FILE.search(body), f"nginx serves a secrets file from disk:\n{body}"


def test_the_secrets_path_is_explicitly_refused() -> None:
    """Removing the block is not enough — a later `alias /etc/aitbc/` would re-expose it.

    nginx matches regex locations ahead of prefix locations, so the deny must be a regex to
    win against a future prefix rule.
    """
    config = _read("examples/nginx/nginx-aitbc.conf.example")

    deny = re.search(r"location\s+~[^{]*secret[^{]*\{([^}]*)\}", config, re.IGNORECASE)
    assert deny is not None, "no regex location denies secrets paths"
    assert "return 404" in deny.group(1), "the secrets location must return 404"


@pytest.mark.parametrize("relative", PUBLISHING_CONFIGS + ["website/README.md"])
def test_nothing_advertises_a_secrets_endpoint(relative: str) -> None:
    """The landing page linked to it, and called it 'required for follower nodes'."""
    for line in _read(relative).splitlines():
        if "404" in line or "not published" in line or "V23-58" in line:
            continue  # the deny rule and the notes explaining it
        # The backtick matters: markdown endpoint tables are how README advertised it.
        assert not re.search(r"""["'(=\s`]/agent/[\w.-]*secrets?[\w.-]*\.env""", line), (
            f"{relative} advertises a secrets endpoint: {line.strip()}"
        )


def test_no_doc_tells_an_operator_to_curl_secrets_over_http() -> None:
    """Four guides did. An operator following any of them fetched live keys over the wire."""
    offenders = []

    for doc in (REPO / "docs").rglob("*.md"):
        if "releases" in doc.relative_to(REPO).parts:
            continue  # historical changelogs record what happened; they are not instructions
        for number, line in enumerate(doc.read_text().splitlines(), 1):
            if not re.search(r"\b(curl|wget)\b", line):
                continue
            if SECRETS_FILE.search(line) and re.search(r"https?://", line):
                offenders.append(f"{doc.relative_to(REPO)}:{number}: {line.strip()}")

    assert not offenders, "docs instruct fetching secrets over HTTP:\n" + "\n".join(offenders)


def test_the_hubs_live_secret_is_not_committed() -> None:
    """It was, as an 'example' in ENVIRONMENT_CONFIGURATION.md, in a public repo since June.

    A sample credential in a doc is indistinguishable from a real one to a reader, which is
    exactly why it stopped being a sample: the hub's deployed values matched it byte for byte.
    Examples must be visibly unusable.
    """
    doc = _read("docs/blockchain/ENVIRONMENT_CONFIGURATION.md")

    assignments = re.findall(r"^\s*(COORDINATOR_API_KEY|SECRET_KEY)\s*=\s*(\S+)", doc, re.MULTILINE)
    assert assignments, "the example block disappeared; this test no longer guards anything"

    for name, value in assignments:
        assert not re.fullmatch(r"[0-9a-fA-F]{32,}", value), (
            f"{name} is set to a literal hex secret. Use a placeholder such as "
            f"`<64 hex chars from `openssl rand -hex 32`>` instead."
        )
