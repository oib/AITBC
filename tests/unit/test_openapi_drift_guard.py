"""The OpenAPI drift guard, and the `files:` pattern that decides when it runs.

`make openapi-check` existed for a release before anything invoked it, and was red on main
that whole time. It is now a pre-commit hook (V23-82). A hook that runs on every commit would
cost ~6s each time, so it is scoped with `files:` -- which means the scoping is now load
bearing: a spec-affecting file outside the pattern is a commit the guard sleeps through, and
that is the same failure as not having the guard.

The pattern is not a guess. Generating the specs imports 593 repo-local modules and the
pattern is the set of prefixes they live under. The second test below re-derives that set --
generating the specs in a fresh interpreter and reading its `sys.modules` -- so the pattern
cannot quietly stop covering the code it was measured against.

The obvious pattern -- `apps/*/src/` -- is the one this catches: 127 of those modules live in
`aitbc/` and `packages/py/`, and they are where the shared models are, including the money
fields whose Decimal conversion was one of the three drifts that had gone unnoticed.

The last two tests are about a different property the hook needs and did not have: that the
generated spec is a function of the code and not of the environment it was generated in.
"""

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
CONFIG = REPO / ".pre-commit-config.yaml"
EXTRACTOR = REPO / "scripts" / "extract_openapi_specs.py"

# Generates the specs and reports which of the repo's own files that took, as JSON.
#
# In a subprocess deliberately. The first version of this ran the extractor in-process and
# diffed `sys.modules` before and after -- which meant that once anything else in the session
# had imported the apps, the difference was empty and the assertion passed over nothing at
# all. It was caught by narrowing the pattern on purpose and watching the test still pass.
# A fresh interpreter has no ambient imports to hide behind.
_COLLECT_IMPORTS = """
import io, json, runpy, sys
from contextlib import redirect_stdout
from pathlib import Path

repo, out_dir = Path(sys.argv[1]), sys.argv[2]
sys.argv = ["extract_openapi_specs.py", "--output-dir", out_dir]
try:
    with redirect_stdout(io.StringIO()):
        runpy.run_path(str(repo / "scripts" / "extract_openapi_specs.py"), run_name="__main__")
except SystemExit as exit_:
    if exit_.code:
        raise SystemExit(f"the extractor could not import one of the apps (exit {exit_.code})")

found = set()
for module in list(sys.modules.values()):
    file = getattr(module, "__file__", None)
    if not file:
        continue
    try:
        rel = Path(file).resolve().relative_to(repo)
    except ValueError:
        continue
    if "venv" in rel.parts or "site-packages" in rel.parts:
        continue
    found.add(str(rel))
print(json.dumps(sorted(found)))
"""


def _files_imported_generating_the_specs(out_dir: Path) -> list[str]:
    result = subprocess.run(
        [sys.executable, "-c", _COLLECT_IMPORTS, str(REPO), str(out_dir)],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr[-2000:]
    return json.loads(result.stdout.strip().splitlines()[-1])


def _files_in(out_dir: Path, env: dict[str, str]) -> dict[str, str]:
    """Generate the specs under `env` on top of a clean environment, keyed by filename."""
    out_dir.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [sys.executable, str(EXTRACTOR), "--output-dir", str(out_dir)],
        cwd=REPO,
        capture_output=True,
        text=True,
        env={"PATH": "/usr/bin:/bin", "HOME": str(out_dir), **env},
    )
    assert result.returncode == 0, result.stderr[-2000:]
    return {p.name: p.read_text() for p in sorted(out_dir.glob("*-openapi.json"))}


def _hook_config() -> dict:
    """The openapi-drift hook's own block, read out of the pre-commit config.

    Parsed with yaml rather than by hand so a reformat of the file does not break this.
    """
    yaml = pytest.importorskip("yaml")
    config = yaml.safe_load(CONFIG.read_text())
    for repo in config["repos"]:
        for hook in repo.get("hooks", []):
            if hook.get("id") == "openapi-drift":
                return hook
    raise AssertionError("no openapi-drift hook in .pre-commit-config.yaml")


def test_the_drift_hook_is_registered_for_a_stage_that_actually_runs():
    """`stages: [pre-push]` would be a hook that never runs in this repo.

    `.git/hooks/pre-push` belongs to git-lfs -- `pre-commit install` was only ever run for
    the pre-commit and commit-msg hook types -- so the bandit entry further down the config
    has never executed on any push. Putting the drift guard there would have reproduced
    exactly the bug it exists to fix. Filed separately; asserted here so that moving this
    hook to pre-push is a deliberate act rather than a plausible-looking edit.
    """
    hook = _hook_config()
    assert hook["stages"] == ["pre-commit"]
    assert hook["pass_filenames"] is False
    assert not hook.get("always_run"), "always_run would override files: and run on every commit"


def test_the_files_pattern_covers_everything_the_specs_are_built_from(tmp_path):
    """Generate the specs, then check the pattern matches every repo file that was imported.

    This is the assertion that keeps the scoping honest as the apps grow. A new shared model
    in a directory the pattern does not name would otherwise change published schemas on a
    commit the hook declines to run for.
    """
    pattern = re.compile(_hook_config()["files"])
    imported = _files_imported_generating_the_specs(tmp_path)

    # Guard against the assertion below passing because nothing was collected -- the failure
    # mode this test had in its first draft. Five apps cannot be imported from a dozen files.
    assert len(imported) > 400, f"only {len(imported)} repo files collected; the probe is broken"

    uncovered = sorted(f for f in imported if not pattern.match(f))
    assert not uncovered, (
        "these files are imported when the specs are generated but are outside the hook's "
        f"files: pattern, so changing them would not run the drift check: {uncovered}"
    )


def test_the_extractor_fails_when_an_app_cannot_be_imported(tmp_path):
    """The hole that made the guard unfalsifiable.

    A failed extraction used to print "✗ Failed" and exit 0. The app's stale spec stayed on
    disk, the diff compared it against itself, and the check reported no drift for a service
    it had not managed to look at. Provoked here the way it happens in practice: the
    placeholder environment the extractor sets stops satisfying an app's own validation.
    """
    result = subprocess.run(
        [sys.executable, str(EXTRACTOR), "--output-dir", str(tmp_path)],
        cwd=REPO,
        capture_output=True,
        text=True,
        env={"PATH": "/usr/bin:/bin", "JWT_SECRET": "too-short", "SECRET_KEY": "too-short"},
    )
    assert result.returncode != 0, "an app that will not import must fail the run"
    assert "agent-coordinator" in result.stdout + result.stderr


def test_the_drift_script_passes_against_the_committed_specs():
    """End to end, and the reason `make openapi-check` is worth having wired up at all.

    Also pins that the script leaves the working tree alone: it generates into a temporary
    directory, so running the check cannot itself be what makes the specs current.
    """
    tracked = subprocess.run(
        ["git", "status", "--porcelain", "--", "docs/api"],
        cwd=REPO,
        capture_output=True,
        text=True,
    ).stdout

    result = subprocess.run(["bash", "scripts/ci/check-openapi-drift.sh"], cwd=REPO, capture_output=True, text=True)
    assert result.returncode == 0, f"docs/api is out of date:\n{result.stdout}"

    after = subprocess.run(
        ["git", "status", "--porcelain", "--", "docs/api"],
        cwd=REPO,
        capture_output=True,
        text=True,
    ).stdout
    assert after == tracked, "the check wrote into docs/api/ instead of a temporary directory"


def test_the_specs_do_not_depend_on_the_environment_they_are_generated_in(tmp_path):
    """A hook whose verdict depends on the developer's shell is worse than no hook.

    `DEBUG` decides what coordinator-api publishes: 38 routes -- the agent, swarm and
    dashboard mocks, in-memory and unauthenticated, documented in their own source as never
    for production -- mount only when it is set, along with `/docs` and `/redoc`. The
    extractor used to inherit it, so `make openapi` produced a different spec depending on who
    ran it, and regenerating with `DEBUG=true` exported would have published mock endpoints as
    the API.

    Found by this suite failing: `tests/integration/conftest.py` sets `DEBUG=true` for the
    session, so the end-to-end check above reported 2,032 lines of drift when run inside the
    full suite and none when run alone.
    """
    baseline = _files_in(tmp_path / "clean", env={})
    hostile = _files_in(tmp_path / "hostile", env={"DEBUG": "true", "TEST_MODE": "true"})
    differing = sorted(name for name in baseline if baseline[name] != hostile.get(name))
    assert not differing, f"these specs change with the ambient environment: {differing}"


# The 38 routes coordinator-api mounts only when `settings.debug` is set, by the module that
# gates them. Written out rather than derived by generating with DEBUG on and diffing: that
# difference is empty precisely when someone has removed a gate, which is the regression this
# is here to catch, so it would pass at the moment it mattered.
_DEBUG_ONLY_ROUTES = {
    # contexts/agent_coordination/routers/agent_messaging.py -- "Only enable mock endpoints
    # if debug mode is set"; in production the module exports an empty router.
    "prefixes": ("/v1/agent/", "/v1/swarm/", "/_debug"),
    # contexts/infrastructure/routers/monitor.py -- the whole router body is under the gate.
    "exact": ("/v1/dashboard", "/v1/dashboard/history", "/v1/miners", "/v1/swarm"),
}


def test_no_debug_only_route_is_published():
    """The consequence, asserted against the committed spec rather than a fresh one.

    Narrower than the test above and it fails differently: that one catches the generator
    losing control of its environment, this one catches a route moving out from behind the
    `settings.debug` gate and into the published production contract. These are in-memory and
    unauthenticated, and their own comments say "Do NOT use in production" -- publishing them
    in the spec is how a client comes to depend on one.
    """
    spec = json.loads((REPO / "docs" / "api" / "coordinator-api-openapi.json").read_text())
    published = [
        path
        for path in spec["paths"]
        if path.startswith(_DEBUG_ONLY_ROUTES["prefixes"]) or path in _DEBUG_ONLY_ROUTES["exact"]
    ]
    assert not published, f"debug-gated routes in the published spec: {sorted(published)}"
