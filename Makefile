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
	@echo "make test-governance the governance suite, which needs its own process"
	@echo "make openapi       regenerate docs/api/*-openapi.json from the running apps"
	@echo "make openapi-check fail if the committed specs differ from what the apps produce"

lint:
	$(PYTHON) -m ruff check .

typecheck:
	$(PYTHON) -m mypy --show-error-codes aitbc/

test:
	$(PYTHON) -m pytest tests/unit -q

# Separate process, not a preference. apps/governance and apps/coordinator-api both map
# governance_profiles, proposals, votes, dao_treasury and transparency_reports onto
# SQLModel's process-global metadata, with different columns on each side -- coordinator-api
# stores voting_power as float, governance as Numeric(20, 8). Importing both raises
# InvalidRequestError, so governance stays out of `testpaths` and runs here instead. Fold it
# back into the main run once the two model sets stop sharing a registry.
test-governance:
	$(PYTHON) -m pytest apps/governance/tests -q

# docs/api/ is generated, not written. Regenerate rather than editing a spec by hand.
openapi:
	$(PYTHON) scripts/extract_openapi_specs.py

# The drift guard. docs/api/ and docs/openapi/ used to hold two sets of specs for the same
# services with nothing saying which was current -- the coordinator ones had diverged to
# the point of sharing a single path out of 354. Regenerating and diffing means a spec
# cannot silently fall behind the app again.
openapi-check: openapi
	@git diff --exit-code --stat -- docs/api/ \
		|| (echo ""; \
		    echo "docs/api/ is out of date with the applications."; \
		    echo "Run 'make openapi' and commit the result."; \
		    exit 1)
