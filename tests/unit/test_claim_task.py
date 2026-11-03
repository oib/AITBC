"""#945: claim-task.py claims with a unique sha, not origin/main.

Two agents pushing ``claim/<n>`` at the same ``origin/main`` sha used to
both succeed — an identical ref update is a no-op — so both held the
"lock". The claim must push a commit that exists only once; a second
agent's push is then a non-fast-forward update the remote rejects.
"""

import importlib.util
import os
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "utils" / "claim-task.py"

GIT_ENV = {
    "GIT_AUTHOR_NAME": "test",
    "GIT_AUTHOR_EMAIL": "t@t",
    "GIT_COMMITTER_NAME": "test",
    "GIT_COMMITTER_EMAIL": "t@t",
}


def _load():
    spec = importlib.util.spec_from_file_location("claim_task", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _git(args, cwd):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, env={**os.environ, **GIT_ENV})


def _work_clone(tmp_path: Path, name: str) -> Path:
    work = tmp_path / name
    _git(["clone", str(tmp_path / "remote.git"), str(work)], tmp_path)
    return work


def test_second_agent_claim_on_same_issue_fails(tmp_path, monkeypatch):
    remote = tmp_path / "remote.git"
    _git(["init", "--bare", str(remote)], tmp_path)
    seed = _work_clone(tmp_path, "seed")
    (seed / "f").write_text("x")
    _git(["add", "f"], seed)
    _git(["commit", "-m", "init"], seed)
    _git(["push", "origin", "HEAD:main"], seed)

    mod = _load()

    agent_a = _work_clone(tmp_path, "a")
    monkeypatch.setattr(mod, "REPO_DIR", str(agent_a))
    assert mod.claim_issue(7) is True

    agent_b = _work_clone(tmp_path, "b")
    monkeypatch.setattr(mod, "REPO_DIR", str(agent_b))
    assert mod.claim_issue(7) is False, "second claim on #7 must collide, not no-op"


def test_claimed_at_is_stored():
    src = SCRIPT.read_text()
    assert '"claimed_at"' in src
