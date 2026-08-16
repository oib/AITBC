# AITBC developer tasks.
#
# These wrap the commands in CONTRIBUTING.md so there is one place to look
# and one spelling to keep working.

# Prefer the repo's own venv; fall back to whatever python is on PATH so the targets still
# work from a git worktree, which has no venv/ of its own. Override with `make PYTHON=...`.
PYTHON ?= $(shell test -x ./venv/bin/python && echo ./venv/bin/python || command -v python3)

.PHONY: help lint typecheck test test-governance openapi openapi-check

help:
	@echo "make lint            ruff over the repo"
	@echo "make typecheck       mypy over aitbc/ (the mypy-clean scope)"
	@echo "make test            unit tests"
	@echo "make test-governance just the governance suite (a bare pytest also covers it)"
	@echo "make openapi       regenerate docs/api/*-openapi.json from the running apps"
	@echo "make openapi-check fail if the committed specs differ from what the apps produce"

lint:
	$(PYTHON) -m ruff check .

typecheck:
	$(PYTHON) -m mypy --show-error-codes aitbc/

test:
	$(PYTHON) -m pytest tests/unit -q

# A convenience for running one suite, not a workaround any more. This used to be the only
# way governance ran: it and apps/coordinator-api mapped governance_profiles, proposals,
# votes, dao_treasury and transparency_reports onto SQLModel's process-global metadata with
# different columns on each side, importing both raised InvalidRequestError, and the suite
# stayed out of `testpaths` because of it. Fixed in V23-72 and V23-73; `apps/governance/tests`
# has been in `testpaths` since, so a bare `pytest` covers it. (`make test` does not -- that
# target runs tests/unit only.)
test-governance:
	$(PYTHON) -m pytest apps/governance/tests -q

# docs/api/ is generated, not written. Regenerate rather than editing a spec by hand.
openapi:
	$(PYTHON) scripts/extract_openapi_specs.py

# The drift guard. docs/api/ and docs/openapi/ used to hold two sets of specs for the same
# services with nothing saying which was current -- the coordinator ones had diverged to
# the point of sharing a single path out of 354. Regenerating and diffing means a spec
# cannot silently fall behind the app again.
#
# The check lives in a script rather than here because a pre-commit hook now runs it too
# (V23-82), and because it no longer works by regenerating in place and asking git what
# changed -- that made asking the question rewrite the answer.
openapi-check:
	@PYTHON="$(PYTHON)" bash scripts/ci/check-openapi-drift.sh
