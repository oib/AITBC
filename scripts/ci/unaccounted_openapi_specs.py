#!/usr/bin/env python3
"""Report OpenAPI documents under a docs directory that no application generates.

The drift check compares the committed specs against freshly generated ones and learns which
files those are from the generator. That is the right way round -- a list written out by hand
is one more thing that falls out of step with the apps -- but it leaves a gap the generator
cannot close by itself: a spec it does *not* produce is never compared against anything, so it
can say whatever it likes for as long as it likes, and no amount of regenerating will disturb
it.

That is not hypothetical. ``docs/api/blockchain/openapi.json`` published three paths for an API
that has 328 of them, at a version the node had left behind months earlier, and two of the
three did not exist at all. It survived three months of a green drift check because the
discovery step looked one directory deep for files named ``*-openapi.json`` and it was neither.
Nothing else looked at it either: it was valid JSON, it was linked from a README, and no test
named it.

So the rule here is the complement of the diff: every OpenAPI document under the docs directory
has to be one the generator wrote. Hand-written JSON is legitimate in that tree -- ``examples/``
is full of request bodies -- so a file is judged by its own ``openapi``/``swagger`` key rather
than by its name or its depth. Naming and depth are precisely what the stub got wrong, and a
rule that trusts either reproduces the hole it is closing.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# A spec in YAML would be exactly as invisible, and switching extension should not be enough to
# defeat the check. Matched as text rather than parsed: pyyaml is a test dependency here, not a
# runtime one, and this script runs from a pre-commit hook where an import error would read as
# a drift failure. The only question being asked is whether the document declares itself at the
# top level, which in YAML means column zero.
_YAML_DECLARES_A_SPEC = re.compile(r"^(openapi|swagger)\s*:", re.MULTILINE)

_CANDIDATE_SUFFIXES = (".json", ".yaml", ".yml")


def is_openapi_document(path: Path) -> bool:
    """Whether this file announces itself as an OpenAPI (or Swagger) document."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False  # unreadable is not this check's business to report
    if path.suffix == ".json":
        try:
            document = json.loads(text)
        except ValueError:
            # Malformed JSON is a real problem but it is not drift, and reporting it here
            # would send the reader to `make openapi` for a syntax error.
            return False
        return isinstance(document, dict) and ("openapi" in document or "swagger" in document)
    return bool(_YAML_DECLARES_A_SPEC.search(text))


def main() -> int:
    parser = argparse.ArgumentParser(description="List published specs no application generates.")
    parser.add_argument("--docs-dir", type=Path, required=True, help="the published spec directory")
    parser.add_argument("generated", nargs="*", help="paths the generator wrote, relative to --docs-dir")
    args = parser.parse_args()

    if not args.docs_dir.is_dir():
        print(f"{args.docs_dir} is not a directory", file=sys.stderr)
        return 2

    generated = {Path(name) for name in args.generated}
    for path in sorted(args.docs_dir.rglob("*")):
        if not path.is_file() or path.suffix not in _CANDIDATE_SUFFIXES:
            continue
        if path.relative_to(args.docs_dir) in generated:
            continue
        if is_openapi_document(path):
            print(path.as_posix())
    return 0


if __name__ == "__main__":
    sys.exit(main())
