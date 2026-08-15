"""Pytest configuration for exchange service tests.

The exchange service runs via ``apps.exchange.simple_exchange.server``.
Tests import from ``apps.exchange.simple_exchange.*`` modules.
"""

# The repo root is on `pythonpath` in pyproject.toml, which is what makes
# `apps.exchange.simple_exchange.*` importable. Nothing is inserted here on purpose.
#
# This file used to do `sys.path.insert(0, parents[2])`, and `parents[2]` is `apps/`, not the
# repo root. Putting `apps/` on sys.path changes how pytest derives module names for every
# other suite: `apps.agent-coordinator.tests.conftest` becomes `agent-coordinator.tests
# .conftest`. A conftest already imported under the first name is then imported *again* under
# the second, so two module objects exist for one file — and a fixture that patches a class
# attribute in one copy is invisible to a test reading it from the other. That is what made
# the agent-coordinator faucet tests fail in a full run while passing alone (V23-69).
