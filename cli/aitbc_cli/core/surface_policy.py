"""Live-validated CLI surface allowlist (G8).

Command groups are shown by default unless they are in the deprecated set.
The deprecated groups are the legacy on-chain surfaces that the design cycle
has replaced with top-level commands (`market` for GPU/software offers,
`governance` for service-backed proposals, etc.). Everything else is exposed
so that the default `aitbc --help` matches the documented CLI catalog.

Use `aitbc --show-deprecated <command>` to invoke the legacy groups.
"""

from __future__ import annotations

# Legacy / duplicated command groups kept for compatibility but hidden from the
# default help surface.
DEPRECATED_COMMANDS: set[str] = {
    "marketplace",
    "operations",
}
