"""Repo-static config assertions — the ``config/`` tier of the security suite.

Complements ``test_nginx_route_scope.py`` (nginx reference config) with the
remaining config-layer pins approved under the #1196 suite layout:

* env-file / systemd-unit expectations that are checkable without a host
* ``JWT_NO_EXPIRATION`` consumer guard — no repo-carried config may enable
  non-expiring tokens
* ``GOSSIP_AUTH_REQUIRE_CHAIN_SCOPE`` must stay off in repo config — the
  #1159 Phase-B gate is explicit; a config file silently flipping it would
  change validator auth semantics without a code review
* env examples must not carry live-looking secrets

Host-managed values (real env files under ``/etc/aitbc``, live nginx vhosts,
live unit drop-ins) are out of scope — those belong to the live-probe tier.
Everything here asserts on files tracked in this repository only.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]

_EXCLUDE_DIRS = {".git", "node_modules", "venv", ".venv", "data", "__pycache__", ".mypy_cache", ".ruff_cache"}


def _repo_files(suffixes: tuple[str, ...]) -> list[Path]:
    """Tracked-looking files under the repo matching suffixes, minus noise dirs."""
    out: list[Path] = []
    for path in REPO_ROOT.rglob("*"):
        if not path.is_file() or path.suffix not in suffixes:
            continue
        if any(part in _EXCLUDE_DIRS for part in path.relative_to(REPO_ROOT).parts):
            continue
        out.append(path)
    return out


# env examples have compound names (.env.example, .env.open-island, ...).
_ENV_FILES = [
    p
    for p in REPO_ROOT.rglob("*")
    if p.is_file()
    and (p.name.startswith(".env") or p.name.endswith(".env.example") or ".env." in p.name)
    and not any(part in _EXCLUDE_DIRS for part in p.relative_to(REPO_ROOT).parts)
]
_SERVICE_FILES = list(_repo_files((".service",)))

_TRUTHY = r"(?i)^\s*[\"']?(1|true|yes|on)[\"']?\s*$"


def _env_assignments(path: Path) -> list[tuple[str, str]]:
    """Yield (name, value) pairs from env-style files and systemd units."""
    pairs: list[tuple[str, str]] = []
    for line in path.read_text(errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # systemd: Environment="NAME=value" / Environment=NAME=value
        m = re.match(r'(?:Environment=)?"?([A-Za-z_][A-Za-z0-9_]*)=(.*)"?\s*$', line)
        if m:
            pairs.append((m.group(1), m.group(2).strip().strip('"')))
    return pairs


# ── JWT_NO_EXPIRATION consumer guard ──────────────────────────────────


def test_no_repo_config_enables_jwt_no_expiration() -> None:
    """``JWT_NO_EXPIRATION`` makes access *and* refresh tokens non-expiring
    (aitbc/auth/jwt.py). No env example or unit file in the repo may carry a
    truthy value — enabling it is an operator decision that lives in host env
    files, never in tracked config."""
    offenders: list[str] = []
    for path in _ENV_FILES + _SERVICE_FILES:
        for name, value in _env_assignments(path):
            if name == "JWT_NO_EXPIRATION" and re.match(_TRUTHY, value):
                offenders.append(f"{path.relative_to(REPO_ROOT)}: JWT_NO_EXPIRATION={value}")
    assert not offenders, "repo config enables non-expiring JWTs:\n" + "\n".join(offenders)


# ── #1159 Phase-B flag must stay off in repo config ────────────────────


def test_no_repo_config_enables_chain_scope_flag() -> None:
    """``GOSSIP_AUTH_REQUIRE_CHAIN_SCOPE`` flips gossip auth to chain-bound
    scopes — a consensus-adjacent semantic change gated as Phase-B. Repo
    config must not enable it; the flip is an explicit ops action."""
    offenders: list[str] = []
    for path in _ENV_FILES + _SERVICE_FILES:
        for name, value in _env_assignments(path):
            if name == "GOSSIP_AUTH_REQUIRE_CHAIN_SCOPE" and re.match(_TRUTHY, value):
                offenders.append(f"{path.relative_to(REPO_ROOT)}: GOSSIP_AUTH_REQUIRE_CHAIN_SCOPE={value}")
    assert not offenders, "repo config enables the Phase-B gossip flag:\n" + "\n".join(offenders)


# ── systemd unit: api-gateway trusted-proxy args (#1189 / R9-4) ────────


@pytest.fixture(scope="module")
def gateway_unit() -> str:
    unit = REPO_ROOT / "apps" / "api-gateway" / "aitbc-api-gateway.service"
    assert unit.exists(), f"missing unit: {unit}"
    return unit.read_text()


def test_gateway_unit_trusts_only_loopback_proxy(gateway_unit: str) -> None:
    """The unit must keep ``--proxy-headers --forwarded-allow-ips 127.0.0.1``:
    without them uvicorn ignores XFF, the rate limiter collapses to a single
    127.0.0.1 bucket (R9-4), and client identity is lost. Widening
    ``--forwarded-allow-ips`` beyond loopback re-opens the spoofable-identity
    class (#1177/#1189)."""
    assert "--proxy-headers" in gateway_unit, "--proxy-headers missing from gateway unit"
    assert re.search(r"--forwarded-allow-ips\s+127\.0\.0\.1(?![\d.])", gateway_unit), (
        "--forwarded-allow-ips is not pinned to 127.0.0.1 — forwarded identity would be trusted from non-loopback peers"
    )


def test_gateway_unit_keeps_sandbox_directives(gateway_unit: str) -> None:
    for directive in ("NoNewPrivileges=yes", "ProtectSystem=", "PrivateTmp=yes"):
        assert directive in gateway_unit, f"{directive} missing from gateway unit"


# ── env examples must not carry live-looking secrets ───────────────────

_SECRET_VALUE = re.compile(
    r"(?i)(private[_-]?key|secret|passwd|password|api[_-]?key|token|seed[_-]?phrase)"
    r"[\"']?\s*[:=]\s*[\"']?"
    r"(?!\s*$|\s*#|<|\.\.\.|example|placeholder|your[-_]|change[-_]|xxx|REDACTED)"
    r"[^\s\"'#]{16,}"
)
_PRIVKEY_BLOCK = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")


def test_env_examples_carry_no_secret_material() -> None:
    """Env examples/templates must use placeholders, not values that look
    like real credentials (long high-entropy strings on secret-named vars,
    or PEM private-key blocks)."""
    offenders: list[str] = []
    for path in _ENV_FILES:
        text = path.read_text(errors="replace")
        rel = path.relative_to(REPO_ROOT)
        for i, line in enumerate(text.splitlines(), 1):
            if _PRIVKEY_BLOCK.search(line):
                offenders.append(f"{rel}:{i}: PEM private key block")
            elif _SECRET_VALUE.search(line):
                offenders.append(f"{rel}:{i}: secret-named var with non-placeholder value")
    assert not offenders, "env examples carry secret-looking material:\n" + "\n".join(offenders)
