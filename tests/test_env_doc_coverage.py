"""Env-var documentation coverage — aitbc_chain and fleet-config-check.

Every environment variable the blockchain node reads, and every variable
`fleet-config-check.sh` watches for drift, must appear in
`docs/blockchain/ENVIRONMENT_CONFIGURATION.md` (the canonical env doc).
The doc uses lowercase names for some entries (`supported_chains`), so
matching is case-insensitive. Docs drift fails at commit time — same
pattern as the bridge_monitor TestDocsCoverage suite.

ALLOWLIST is for names the process technically reads but that are not
operator knobs: interpreter/build internals and test harnesses.
"""

import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHAIN_SRC = ROOT / "apps" / "blockchain-node" / "src" / "aitbc_chain"
FLEET_CHECK = ROOT / "scripts" / "monitoring" / "fleet-config-check.sh"
ENV_DOC = ROOT / "docs" / "blockchain" / "ENVIRONMENT_CONFIGURATION.md"

# read by the interpreter/build or test scaffolding, not operator knobs
ALLOWLIST = {
    "AITBC_VERSION",  # stamped by the build, read-only introspection
    "AITBC_HOSTNAME",  # container/runtime identity, not a config knob
    "DEV_MODE",  # test harness switch
}

_ENV_PATTERNS = (
    re.compile(r"""os\.getenv\(["']([A-Z0-9_]+)["']"""),
    re.compile(r"""os\.environ\.get\(["']([A-Z0-9_]+)["']"""),
    re.compile(r"""os\.environ\[["']([A-Z0-9_]+)["']\]"""),
    re.compile(r"""_env_value\(([^)]*)\)"""),
)


def _chain_env_names() -> set[str]:
    names: set[str] = set()
    for dirpath, _dirs, files in os.walk(CHAIN_SRC):
        for fname in files:
            if not fname.endswith(".py"):
                continue
            text = Path(dirpath, fname).read_text(errors="replace")
            for pat in _ENV_PATTERNS:
                for m in pat.finditer(text):
                    if pat.pattern.startswith("_env_value"):
                        names.update(re.findall(r'"([A-Z0-9_]+)"', m.group(1)))
                    else:
                        names.add(m.group(1))
    return names - ALLOWLIST


def _fleet_check_names() -> set[str]:
    """VARS/EFF_VARS assignments in fleet-config-check.sh."""
    text = FLEET_CHECK.read_text()
    names: set[str] = set()
    for m in re.finditer(r'^(?:VARS|EFF_VARS)="([^"]*)"', text, re.M):
        names.update(m.group(1).split())
    # EFF_VARS references $VARS; both are captured by the regex above
    names = {n for n in names if re.fullmatch(r"[A-Z0-9_]+", n)}
    return names - {"$VARS"}


def _doc_text() -> str:
    return ENV_DOC.read_text().upper()


class TestChainEnvDocCoverage:
    def test_every_chain_env_var_is_documented(self):
        doc = _doc_text()
        missing = sorted(n for n in _chain_env_names() if n.upper() not in doc)
        assert not missing, (
            "env vars read by aitbc_chain but absent from docs/blockchain/ENVIRONMENT_CONFIGURATION.md: " + ", ".join(missing)
        )


class TestFleetCheckVarsDocCoverage:
    def test_fleet_check_watched_vars_are_documented(self):
        doc = _doc_text()
        missing = sorted(n for n in _fleet_check_names() if n.upper() not in doc)
        assert not missing, (
            "drift-watched vars in fleet-config-check.sh absent from "
            "docs/blockchain/ENVIRONMENT_CONFIGURATION.md: " + ", ".join(missing)
        )
