"""Live-validated CLI surface allowlist (G8).

A command group is only shown by default if it maps to a scenario that has been
end-to-end validated on a live node. Everything else is hidden and can only be
invoked with `aitbc --show-deprecated <command>`.
"""

from __future__ import annotations

# Top-level command groups that participate in the validated economic loop.
VALIDATED_COMMANDS: set[str] = {
    "account",
    "ai",
    "auth",
    "bond",
    "bridge",
    "config",
    "list",
    "market",
    "node",
    "start",
    "stop",
    "restart",
    "transactions",
    "version",
    "wallet",
}
