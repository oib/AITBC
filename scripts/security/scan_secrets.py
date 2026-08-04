#!/usr/bin/env python3
"""Scan source code for hardcoded secrets and API keys.

Intended for CI/local verification of production source. Exits 0 when no
suspicious values are found in the scanned paths, exits 1 and prints findings
otherwise.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path


DEFAULT_EXCLUDE = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".mypy_cache",
    ".ruff_cache",
    ".pytest_cache",
    ".tox",
    "dist",
    "build",
    ".eggs",
    "*.egg-info",
    "package-lock.json",
    "yarn.lock",
    "poetry.lock",
    "Pipfile.lock",
    "*.pyc",
    "*.pyo",
    ".DS_Store",
    # Non-production paths are skipped by default.
    "docs",
    "packages",
    "dev",
    "tests",
    "test",
    "examples",
    "example",
    "README.md",
    "artifacts",
    "out",
    "work",
}


# Capture the quoted value in group 2.
ASSIGNMENT_PATTERNS = [
    re.compile(
        r"(?i)(?:api[_-]?key|auth[_-]?token|access[_-]?token|secret[_-]?key|private[_-]?key|password)"
        r"\s*[:=]\s*([\"'])([^\"'\$\{<>]{8,})\1"
    ),
]

HIGH_ENTROPY_PATTERNS = [
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),  # AWS access key id
    re.compile(r"\bsk-[a-zA-Z0-9]{48,}\b"),  # OpenAI-style key
    re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY-----"),
    # Private key assigned as a 64-char hex string.
    re.compile(r"(?i)(?:private[_-]?key|secret)\s*[:=]\s*([\"'])0x[a-f0-9]{64}\1"),
]


ALLOWLIST_SUBSTRINGS = {
    "example",
    "placeholder",
    "change_me",
    "your_",
    "your-",
    "mock",
    "dummy",
    "fake",
    "demo_",
    "demo-",
    "test_",
    "test-",
    "testkey",
    "invalid",
    "encrypted",
    "mock_fallback",
    "fallback",
    "[encrypted",
    "]",
}


def _should_exclude(path: Path, exclude: set[str]) -> bool:
    """Return True if a path should be skipped."""
    for part in path.parts:
        if part in exclude:
            return True
        if any(part.endswith(suffix) for suffix in (".pyc", ".pyo", ".lock")):
            return True
    return False


def _looks_like_secret(value: str) -> bool:
    """Filter out obvious non-secrets and env-var references."""
    stripped = value.strip().strip("\"'").lower()
    if not stripped:
        return False
    if "${" in value or "$" in value:
        return False
    if stripped.startswith(("<", "[")) and stripped.endswith((">", "]")):
        return False
    if any(sub in stripped for sub in ALLOWLIST_SUBSTRINGS):
        return False
    # Skip short/repeated placeholders like xxxxx, 00000, etc.
    if len(set(stripped)) <= 3:
        return False
    return True


def scan_file(path: Path) -> list[tuple[int, str, str]]:
    """Return list of (line_number, category, matched_text) for a file."""
    findings: list[tuple[int, str, str]] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except (OSError, UnicodeDecodeError):
        return findings

    for lineno, line in enumerate(text.splitlines(), start=1):
        for pattern in ASSIGNMENT_PATTERNS:
            for match in pattern.finditer(line):
                value = match.group(2)
                if _looks_like_secret(value):
                    findings.append((lineno, "suspicious-assignment", match.group(0).strip()))
        for pattern in HIGH_ENTROPY_PATTERNS:
            for match in pattern.finditer(line):
                if match.group(0).strip().startswith("-----"):
                    findings.append((lineno, "private-key-block", match.group(0).strip()))
                else:
                    findings.append((lineno, "high-entropy-token", match.group(0).strip()))
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description="Scan source code for hardcoded secrets/API keys")
    parser.add_argument("--root", default=os.environ.get("REPO_ROOT", "/opt/aitbc"))
    parser.add_argument("--exclude", action="append", default=[], help="Additional path components to exclude")
    parser.add_argument("--extensions", default="py,js,ts,sh,yml,yaml,toml,cfg,ini,json,txt,env")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    exclude = DEFAULT_EXCLUDE | set(args.exclude)
    extensions = set(args.extensions.split(","))

    findings: list[tuple[Path, int, str, str]] = []

    for path in root.rglob("*"):
        if path.is_dir():
            continue
        if _should_exclude(path, exclude):
            continue
        if path.suffix.lstrip(".") not in extensions and path.name not in {"Dockerfile", ".env"}:
            continue
        for lineno, category, match in scan_file(path):
            findings.append((path, lineno, category, match))

    if not findings:
        print("No hardcoded secrets/API keys detected in scanned source paths.")
        return 0

    print("Potential hardcoded secrets/API keys detected:")
    for path, lineno, category, match in findings:
        rel = path.relative_to(root)
        print(f"  {rel}:{lineno} [{category}] {match}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
