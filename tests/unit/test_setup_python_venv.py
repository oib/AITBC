"""Unit tests for scripts/ci/setup-python-venv.sh venv repair + shebang check.

--mode copy historically copied the cached venv verbatim: every bin/* script
kept a `#!$CACHE_ROOT/<key>/bin/python*` shebang, activate kept
VIRTUAL_ENV=<cache>, and pyvenv.cfg kept the cache `command =` line. Sourcing
that activate then prepends the *cache* bin dir to PATH, so `pip`/`python`
resolve to the cache interpreter and installs land in the wrong tree (the
hub/hub1 venv drift).

The script defines its logic as functions and returns early when sourced, so
these tests drive `repair_copied_venv` / `assert_venv_shebangs` on fake venv
trees under tmp_path via `bash -c` harnesses — no real pip ever runs (bin/pip
stubs are /bin/sh scripts; only fake console scripts carry the shebangs under
test). The end-to-end case runs the script itself with --skip-requirements and
a pre-seeded cache venv so the pip-install path is never reached.
"""

import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "ci" / "setup-python-venv.sh"

pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="bash required")


def _sourced(body: str, **env) -> subprocess.CompletedProcess:
    """Run `body` in bash with the script sourced.

    Sourcing defines the functions and returns at the source guard — the
    executable body (arg parsing, cache build, pip) never runs. $0 is the
    harness name so the guard sees a sourced context; function parameters come
    in through env vars.
    """
    e = {**os.environ, **{k: str(v) for k, v in env.items()}}
    return subprocess.run(
        ["bash", "-c", f'source "{SCRIPT}"\n{body}', "venv-test-harness"],
        env=e,
        capture_output=True,
        text=True,
        timeout=30,
    )


def _script(bindir: Path, name: str, shebang: str, body: str = "exit 0\n") -> Path:
    """Write an executable script with a literal first-line shebang."""
    p = bindir / name
    p.write_text(f"#!{shebang}\n{body}")
    p.chmod(0o755)
    return p


def _venv_tree(venv: Path) -> Path:
    """Minimal venv-shaped tree: bin/python* symlinks + a real pyvenv.cfg."""
    bindir = venv / "bin"
    bindir.mkdir(parents=True)
    os.symlink(sys.executable, bindir / "python3")
    os.symlink("python3", bindir / "python")
    (venv / "pyvenv.cfg").write_text(
        "home = /usr/bin\n"
        "include-system-site-packages = false\n"
        "version = 3.13.5\n"
        "executable = /usr/bin/python3.13\n"
        f"command = {sys.executable} -m venv {venv}\n"
    )
    return bindir


def _write_activates(venv: Path, venv_path: Path) -> None:
    """activate/activate.csh/activate.fish embedding `venv_path` literally,
    mimicking the CPython 3.13 layout (cygwin branch + export line, prompt
    strings carrying the venv basename)."""
    bindir = venv / "bin"
    base = venv_path.name
    (bindir / "activate").write_text(
        '# This file must be used with "source bin/activate" *from bash*\n'
        f'case "$(uname)" in\n'
        "    CYGWIN*|MSYS*|MINGW*)\n"
        f"        VIRTUAL_ENV=$(cygpath {venv_path})\n"
        "        export VIRTUAL_ENV\n"
        "        ;;\n"
        "    *)\n"
        f"        export VIRTUAL_ENV={venv_path}\n"
        "        ;;\n"
        "esac\n"
        'PATH="$VIRTUAL_ENV/"bin":$PATH"\n'
        "export PATH\n"
        f"VIRTUAL_ENV_PROMPT={base}\n"
        "export VIRTUAL_ENV_PROMPT\n"
        f'PS1="("{base}") ${{PS1:-}}"\n'
        "export PS1\n"
    )
    (bindir / "activate.csh").write_text(f"setenv VIRTUAL_ENV {venv_path}\nsetenv VIRTUAL_ENV_PROMPT {base}\n")
    (bindir / "activate.fish").write_text(f"set -gx VIRTUAL_ENV {venv_path}\nset -gx VIRTUAL_ENV_PROMPT {base}\n")


def _fake_cache_venv(cache_venv: Path) -> None:
    """A 'built' cache venv for --mode copy tests: python* symlinks, a /bin/sh
    pip stub (so `cached_environment_is_valid`'s `pip --version` never runs a
    real pip), one console script shebanged at the cache path, and activate*
    files embedding the cache path."""
    bindir = _venv_tree(cache_venv)
    _script(bindir, "pip", "/bin/sh", 'echo "pip 99.0 (test stub)"\n')
    _script(bindir, "aitbc", f"{cache_venv}/bin/python3", "import sys\n")
    _write_activates(cache_venv, cache_venv)


class TestAssertVenvShebangs:
    def test_clean_venv_passes(self, tmp_path):
        venv = tmp_path / "venv"
        bindir = _venv_tree(venv)
        _script(bindir, "pip", f"{venv}/bin/python3")
        _script(bindir, "aitbc", f"{venv}/bin/python")
        r = _sourced('assert_venv_shebangs "$V"', V=venv)
        assert r.returncode == 0, r.stderr

    def test_foreign_venv_shebang_fails(self, tmp_path):
        """The cache-copy trap: a script shebanged at another venv's path."""
        venv = tmp_path / "venv"
        foreign = tmp_path / "cache" / "py3.13.5-reqabc-extra000"
        bindir = _venv_tree(venv)
        _script(bindir, "pip", f"{venv}/bin/python3")
        _script(bindir, "aitbc", f"{foreign}/bin/python3")
        r = _sourced('assert_venv_shebangs "$V"', V=venv)
        assert r.returncode != 0
        assert "aitbc" in r.stderr

    def test_symlinked_venv_resolves_to_cache_ok(self, tmp_path):
        """--mode symlink: VENV_DIR is a symlink at the cache venv, so
        cache-path shebangs are correct — the assert must be a no-op."""
        cache_venv = tmp_path / "cache-venv"
        bindir = _venv_tree(cache_venv)
        _script(bindir, "pip", f"{cache_venv}/bin/python3")
        link = tmp_path / "venv"
        link.symlink_to(cache_venv)
        r = _sourced('assert_venv_shebangs "$V"', V=link)
        assert r.returncode == 0, r.stderr

    def test_launcher_and_base_interpreter_shebangs_allowed(self, tmp_path):
        """Generic launchers (/usr/bin/env, /bin/sh) and the base interpreter
        recorded in pyvenv.cfg are legitimate non-venv shebangs."""
        venv = tmp_path / "venv"
        bindir = _venv_tree(venv)
        _script(bindir, "pip", f"{venv}/bin/python3")
        _script(bindir, "envtool", "/usr/bin/env python3")
        _script(bindir, "shim", "/bin/sh")
        _script(bindir, "basetool", "/usr/bin/python3")  # == pyvenv.cfg home dir
        r = _sourced('assert_venv_shebangs "$V"', V=venv)
        assert r.returncode == 0, r.stderr


class TestRepairCopiedVenv:
    def test_repair_rewrites_shebangs_activates_and_cfg(self, tmp_path):
        cache_venv = tmp_path / "cache" / "py3.13.5-reqabc-extra000"
        _fake_cache_venv(cache_venv)
        dest = tmp_path / "dest" / "venv"
        dest.parent.mkdir(parents=True)
        shutil.copytree(cache_venv, dest, symlinks=True)

        r = _sourced(
            'repair_copied_venv && assert_venv_shebangs "$VENV_DIR"',
            CACHE_VENV_DIR=cache_venv,
            VENV_DIR=dest,
            PYTHON_BIN=sys.executable,
        )
        assert r.returncode == 0, r.stderr

        # Shebang repointed to the dest interpreter, mode preserved.
        pip_like = dest / "bin" / "aitbc"
        assert pip_like.read_text().splitlines()[0] == f"#!{dest}/bin/python3"
        assert pip_like.stat().st_mode & 0o777 == 0o755

        # activate: both VIRTUAL_ENV assignments and the prompt basename.
        activate = (dest / "bin" / "activate").read_text()
        assert str(cache_venv) not in activate
        assert f"export VIRTUAL_ENV={dest}" in activate
        assert f"cygpath {dest}" in activate
        assert f"VIRTUAL_ENV_PROMPT={dest.name}" in activate
        assert cache_venv.name not in activate

        # Same repointing in the csh/fish variants.
        assert f"setenv VIRTUAL_ENV {dest}" in (dest / "bin" / "activate.csh").read_text()
        assert f"set -gx VIRTUAL_ENV {dest}" in (dest / "bin" / "activate.fish").read_text()

        # pyvenv.cfg: only `command =` rewritten; the rest untouched.
        cfg = dict(line.split(" = ", 1) for line in (dest / "pyvenv.cfg").read_text().splitlines())
        assert cfg["command"] == f"{sys.executable} -m venv {dest}"
        assert cfg["home"] == "/usr/bin"
        assert cfg["version"] == "3.13.5"
        assert cfg["executable"] == "/usr/bin/python3.13"

    def test_repair_leaves_clean_scripts_alone(self, tmp_path):
        """A script already shebanged at the destination must not be touched."""
        cache_venv = tmp_path / "cache" / "py3.13.5-reqabc-extra000"
        _fake_cache_venv(cache_venv)
        dest = tmp_path / "dest" / "venv"
        dest.parent.mkdir(parents=True)
        shutil.copytree(cache_venv, dest, symlinks=True)
        # A console script that is already correct for the destination.
        ok = _script(dest / "bin", "already-ok", f"{dest}/bin/python3")

        r = _sourced(
            "repair_copied_venv",
            CACHE_VENV_DIR=cache_venv,
            VENV_DIR=dest,
            PYTHON_BIN=sys.executable,
        )
        assert r.returncode == 0, r.stderr
        assert ok.read_text().splitlines()[0] == f"#!{dest}/bin/python3"


class TestModeCopyEndToEnd:
    """Full script run with --skip-requirements and a pre-seeded cache venv:
    exercises the copy branch → repair_copied_venv → assert_venv_shebangs →
    activate pipeline. bin/pip is a /bin/sh stub so no real pip ever runs."""

    def test_mode_copy_repairs_and_validates(self, tmp_path):
        pyver = ".".join(map(str, sys.version_info[:3]))
        cache_key = f"py{pyver}-reqno-req-extra{hashlib.sha256(b'').hexdigest()[:16]}"
        cache_root = tmp_path / "cache"
        cache_venv = cache_root / cache_key
        _fake_cache_venv(cache_venv)

        repo = tmp_path / "repo"
        repo.mkdir()
        dest = tmp_path / "venv"

        r = subprocess.run(
            [
                "bash",
                str(SCRIPT),
                "--repo-dir",
                str(repo),
                "--venv-dir",
                str(dest),
                "--cache-root",
                str(cache_root),
                "--skip-requirements",
                "--mode",
                "copy",
                "--python-bin",
                sys.executable,
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert r.returncode == 0, f"stdout:\n{r.stdout}\nstderr:\n{r.stderr}"
        assert "Reusing cached Python environment" in r.stdout
        assert "Python environment ready" in r.stdout

        # The copied console script's shebang was repointed from cache to dest.
        assert (dest / "bin" / "aitbc").read_text().splitlines()[0] == f"#!{dest}/bin/python3"
        activate = (dest / "bin" / "activate").read_text()
        assert str(cache_venv) not in activate
        assert f"export VIRTUAL_ENV={dest}" in activate

        cfg = dict(line.split(" = ", 1) for line in (dest / "pyvenv.cfg").read_text().splitlines())
        assert cfg["command"] == f"{sys.executable} -m venv {dest}"

    def test_mode_symlink_is_untouched(self, tmp_path):
        """Symlink mode keeps cache-path shebangs — legitimately pointing at
        the resolved venv — so the assert stays a no-op."""
        pyver = ".".join(map(str, sys.version_info[:3]))
        cache_key = f"py{pyver}-reqno-req-extra{hashlib.sha256(b'').hexdigest()[:16]}"
        cache_root = tmp_path / "cache"
        cache_venv = cache_root / cache_key
        _fake_cache_venv(cache_venv)

        repo = tmp_path / "repo"
        repo.mkdir()
        dest = tmp_path / "venv"

        r = subprocess.run(
            [
                "bash",
                str(SCRIPT),
                "--repo-dir",
                str(repo),
                "--venv-dir",
                str(dest),
                "--cache-root",
                str(cache_root),
                "--skip-requirements",
                "--mode",
                "symlink",
                "--python-bin",
                sys.executable,
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert r.returncode == 0, f"stdout:\n{r.stdout}\nstderr:\n{r.stderr}"
        assert dest.is_symlink()
        # Shebang still names the cache path — correct for a symlinked venv.
        assert (dest / "bin" / "aitbc").read_text().splitlines()[0] == f"#!{cache_venv}/bin/python3"
