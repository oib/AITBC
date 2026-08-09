"""V23-32: a flag manifest must have a reader, or it must not exist.

``feature_flags.json`` sat at the repo root describing six flags. Nothing had read it since
``aitbc/feature_flags.py`` was deleted in v0.10.9, and by v0.23 four of the six entries were
false — including two security controls it reported as enabled at 100% rollout that were not
implemented at all.

An inert manifest is worse than no manifest. Deleting it is only half a fix, because the
next person to want a flag will recreate it and it will be inert again on the same day. So
this guards the invariant rather than the deletion: *if* a flag manifest exists, code must
read it.
"""

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parents[2]

# Names a flag manifest would plausibly be given. The point is the shape of the mistake, not
# one filename -- feature_flags.json reappearing as flags.json would be the same mistake.
MANIFEST_NAMES = ("feature_flags.json", "feature-flags.json", "flags.json")

SEARCH_ROOTS = ("aitbc", "apps", "cli", "packages", "scripts")

SKIP_DIRS = {".claude", "harness", "node_modules", "graphify-out", "tmp", "__pycache__", ".venv", "venv"}


def _iter_python_files() -> list[Path]:
    """Every tracked-ish .py file under the search roots, minus vendored//nested trees."""
    files: list[Path] = []
    for root in SEARCH_ROOTS:
        base = REPO_ROOT / root
        if not base.is_dir():
            continue
        for path in base.rglob("*.py"):
            if SKIP_DIRS.intersection(path.parts):
                continue
            files.append(path)
    return files


def _reads_manifest(path: Path, manifest: str) -> bool:
    """True if the file mentions ``manifest`` outside of a comment or docstring.

    A comment saying "feature_flags.json is not read" is not a reader, and this test exists
    precisely because such comments are what remained. Parsing to AST and looking only at
    string constants keeps the guard from being satisfied by prose about itself.
    """
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return False

    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            doc = ast.get_docstring(node, clean=False)
            if doc is not None:
                docstrings.add(doc)

    return any(
        isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and manifest in node.value
        and node.value not in docstrings
        for node in ast.walk(tree)
    )


@pytest.mark.parametrize("manifest", MANIFEST_NAMES)
def test_flag_manifest_has_a_reader_or_does_not_exist(manifest: str) -> None:
    """A flag manifest at the repo root must be loaded by code, or not be there."""
    path = REPO_ROOT / manifest
    if not path.exists():
        return

    readers = [p for p in _iter_python_files() if _reads_manifest(p, manifest)]

    assert readers, (
        f"{manifest} exists but no code reads it. A flag manifest nobody loads does not "
        f"gate anything -- it is documentation that looks like configuration, and it drifts "
        f"silently because no test can fail when an entry stops being true. Either wire up "
        f"a loader, or delete the file and gate the behaviour on an environment variable "
        f"read at import time (see the Feature Flags section of CLAUDE.md)."
    )


def test_claude_md_does_not_advertise_a_flag_manifest_as_authoritative() -> None:
    """CLAUDE.md must not tell readers to consult a manifest to learn what is live.

    The old text was "Check it before assuming a capability is actually live". Pointing at an
    oracle that answers wrong is worse than pointing at nothing, and both humans and agents
    follow that file.
    """
    text = (REPO_ROOT / "CLAUDE.md").read_text(encoding="utf-8")

    if "feature_flags.json" not in text:
        return

    assert "There is no feature-flag system" in text, (
        "CLAUDE.md mentions feature_flags.json without stating that no feature-flag system "
        "exists. If a loader has since been written, update this test along with it -- but "
        "do not let the file describe a manifest as the way to check what is live unless "
        "something actually reads it."
    )
