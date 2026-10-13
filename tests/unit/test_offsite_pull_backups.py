"""Tests for scripts/ops/offsite-pull-backups.sh.

The script pulls backup generations over ssh, verifies a host-side sha256
manifest, encrypts every file with age, and prunes to KEEP generations per
host. Tests run it for real with ``ssh`` and ``rsync`` stubbed to operate on
a local fake ``REMOTE_BASE`` (the same convention as
``test_aitbc_backup.py``), plus a throwaway age identity -- never an
operator key.
"""

import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "ops" / "offsite-pull-backups.sh"

pytestmark = pytest.mark.skipif(
    shutil.which("bash") is None or shutil.which("age") is None or shutil.which("rsync") is None,
    reason="needs bash, age and rsync",
)

GEN = "20261013_010357"


def _fake_host(remote: Path, gen: str = GEN, files: dict[str, bytes] | None = None, age_min: int = 60):
    d = remote / gen
    d.mkdir(parents=True)
    for name, content in (files or {"chain_a.db.gz": b"chain", "keystore.tar.gz": b"keys"}).items():
        (d / name).write_bytes(content)
    # generation must look STABLE_MIN old: older than the 10-minute default
    old = time.time() - age_min * 60
    for f in d.iterdir():
        os.utime(f, (old, old))
    os.utime(d, (old, old))
    return d


def _run(tmp_path: Path, remote: Path, stub_bin: Path, *extra_args: str, **env_over):
    dest = tmp_path / "dest"
    env = {
        "PATH": f"{stub_bin}:{os.environ['PATH']}",
        "DEST": str(dest),
        "HOSTS": "fake1",
        "REMOTE_BASE": str(remote),
        "AGE_RECIPIENT": env_over.pop("AGE_RECIPIENT", os.environ.get("_TEST_AGE_RECIPIENT", "")),
        "MIN_FREE_GB": env_over.pop("MIN_FREE_GB", "0"),
        "STUB_LOG": str(tmp_path / "stub.log"),
        **{k: str(v) for k, v in env_over.items()},
    }
    return subprocess.run(
        ["bash", str(SCRIPT), *extra_args],
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    ), dest


@pytest.fixture()
def env(tmp_path: Path):
    remote = tmp_path / "remote"
    remote.mkdir()
    stub_bin = tmp_path / "bin"
    stub_bin.mkdir()
    # ssh <host> "<remote script>": drop host, eval the script so REMOTE_BASE
    # (embedded expanded by the caller) points at the fake dir.
    (stub_bin / "ssh").write_text('#!/bin/bash\nlog="${STUB_LOG:-/dev/null}"\necho "ssh $1" >> "$log"\nshift\neval "$1"\n')
    # rsync <opts> host:src/ dst/ -> cp -a
    (stub_bin / "rsync").write_text(
        '#!/bin/bash\nargs=("$@")\ndst="${args[-1]}"\nsrc="${args[-2]}"\nsrc="${src#*:}"\ncp -a "$src". "$dst"\n'
    )
    for s in ("ssh", "rsync"):
        (stub_bin / s).chmod(0o755)
    # throwaway recipient for tests only; identity file never leaves tmp
    key = subprocess.run(["age-keygen"], capture_output=True, text=True, check=True)
    recipient = next(line.split()[-1] for line in key.stderr.splitlines() if line.startswith("Public key"))
    os.environ["_TEST_AGE_RECIPIENT"] = recipient
    yield remote, stub_bin


def test_pull_verifies_and_encrypts(env, tmp_path):
    remote, stub_bin = env
    _fake_host(remote)
    r, dest = _run(tmp_path, remote, stub_bin)
    assert r.returncode == 0, r.stderr + r.stdout
    gen_dir = dest / "fake1" / GEN
    assert (gen_dir / "chain_a.db.gz.age").exists()
    assert (gen_dir / "SHA256SUMS.age").exists()
    assert not (dest / "fake1" / f"{GEN}.partial").exists()
    assert oct(gen_dir.stat().st_mode)[-3:] == "700"
    assert "verified + encrypted" in r.stdout


def test_idempotent_skip(env, tmp_path):
    remote, stub_bin = env
    _fake_host(remote)
    r1, dest = _run(tmp_path, remote, stub_bin)
    assert r1.returncode == 0
    r2, _ = _run(tmp_path, remote, stub_bin)
    assert r2.returncode == 0
    assert "already verified -- skipped" in r2.stdout


def test_checksum_mismatch_rejected(env, tmp_path):
    remote, stub_bin = env
    _fake_host(remote)
    # corrupt between manifest and copy: rsync stub delivers tampered bytes
    (stub_bin / "rsync").write_text(
        '#!/bin/bash\nargs=("$@")\ndst="${args[-1]}"\nsrc="${args[-2]}"\nsrc="${src#*:}"\n'
        'cp -a "$src". "$dst"\necho tampered >> "$dst/chain_a.db.gz"\n'
    )
    (stub_bin / "rsync").chmod(0o755)
    r, dest = _run(tmp_path, remote, stub_bin)
    assert r.returncode != 0
    assert "CHECKSUM MISMATCH" in r.stderr
    assert not (dest / "fake1" / GEN).exists()


def test_retention_keeps_newest_and_foreign_dirs(env, tmp_path):
    remote, stub_bin = env
    _fake_host(remote)
    host_dir = tmp_path / "dest" / "fake1"
    # pre-seed older generations + a foreign dir
    for g in ("20261010_010100", "20261011_010100", "20261012_010100"):
        (host_dir / g).mkdir(parents=True)
        (host_dir / g / "SHA256SUMS.age").write_text("x")
    (host_dir / "keep-me-not-a-generation").mkdir()
    r, dest = _run(tmp_path, remote, stub_bin, KEEP="2")
    assert r.returncode == 0, r.stderr
    names = sorted(p.name for p in host_dir.iterdir())
    # newest two generations kept (12th + new 13th), oldest two pruned, foreign dir intact
    assert "20261010_010100" not in names and "20261011_010100" not in names
    assert "20261012_010100" in names and GEN in names
    assert "keep-me-not-a-generation" in names


def test_disk_guard_refuses(env, tmp_path):
    remote, stub_bin = env
    _fake_host(remote)
    r, _ = _run(tmp_path, remote, stub_bin, MIN_FREE_GB="999999")
    assert r.returncode == 2
    assert "free" in r.stderr


def test_refuses_plaintext_without_recipient(env, tmp_path):
    remote, stub_bin = env
    _fake_host(remote)
    r, _ = _run(tmp_path, remote, stub_bin, AGE_RECIPIENT="")
    assert r.returncode == 2
    assert "AGE_RECIPIENT" in r.stderr


def test_dry_run_pulls_nothing(env, tmp_path):
    remote, stub_bin = env
    _fake_host(remote)
    r, dest = _run(tmp_path, remote, stub_bin, "--dry-run")
    assert r.returncode == 0
    assert "would pull" in r.stdout and GEN in r.stdout
    assert not (dest / "fake1" / GEN).exists()


def test_marker_written_on_full_success_and_status(env, tmp_path):
    remote, stub_bin = env
    _fake_host(remote)
    r, dest = _run(tmp_path, remote, stub_bin)
    assert r.returncode == 0, r.stderr
    marker = dest / "last-success.txt"
    assert marker.exists()
    text = marker.read_text()
    assert "timestamp_epoch=" in text and GEN in text and "fake1" in text
    assert oct(marker.stat().st_mode)[-3:] == "600"
    r2, _ = _run(tmp_path, remote, stub_bin, "--status")
    assert r2.returncode == 0
    assert "last success" in r2.stdout


def test_marker_survives_failed_run(env, tmp_path):
    remote, stub_bin = env
    _fake_host(remote)
    r1, dest = _run(tmp_path, remote, stub_bin)
    assert r1.returncode == 0
    marker = dest / "last-success.txt"
    assert marker.exists()
    # now make the host unreachable and re-run: failure must leave the marker
    (stub_bin / "ssh").write_text("#!/bin/bash\nexit 5\n")
    (stub_bin / "ssh").chmod(0o755)
    r2, _ = _run(tmp_path, remote, stub_bin, HOSTS="gone")
    assert r2.returncode != 0
    assert marker.exists()


def test_status_stale_and_missing(env, tmp_path):
    remote, stub_bin = env
    _fake_host(remote)
    dest = tmp_path / "dest"
    # no marker at all -> rc 1
    r1, _ = _run(tmp_path, remote, stub_bin, "--status")
    assert r1.returncode == 1
    # stale marker -> rc 1
    (dest).mkdir(parents=True)
    (dest / "last-success.txt").write_text("timestamp_epoch=1\n")
    r2, _ = _run(tmp_path, remote, stub_bin, "--status")
    assert r2.returncode == 1
    assert "STALE" in r2.stdout


def test_pull_log_rotation(env, tmp_path):
    remote, stub_bin = env
    _fake_host(remote)
    dest = tmp_path / "dest"
    dest.mkdir(parents=True)
    big = dest / "pull.log"
    big.write_bytes(b"x" * (2 * 1024 * 1024))
    for n in (".1", ".2", ".3"):
        (dest / f"pull.log{n}").write_text(f"old{n}")
    r, _ = _run(tmp_path, remote, stub_bin, PULL_LOG=str(big))
    assert r.returncode == 0
    # the script does not write pull.log itself (the unit appends output), so
    # rotation leaves it absent or small -- the content moved to pull.log.1
    assert not big.exists() or big.stat().st_size < 2 * 1024 * 1024
    assert (dest / "pull.log.1").stat().st_size == 2 * 1024 * 1024
    assert (dest / "pull.log.2").read_text() == "old.1"
    assert (dest / "pull.log.3").read_text() == "old.2"
    assert not (dest / "pull.log.4").exists()


def test_metric_write_to_metric_host_is_failure_tolerant(env, tmp_path):
    remote, stub_bin = env
    _fake_host(remote)
    # ssh stub: first arg is host; metric write goes to METRIC_HOST which the
    # stub maps into a local dir via METRIC_TEXTFILE_DIR (env-expanded already)
    metric_dir = tmp_path / "textfile"
    metric_dir.mkdir()
    r, dest = _run(tmp_path, remote, stub_bin, METRIC_HOST="fake1", METRIC_TEXTFILE_DIR=str(metric_dir))
    assert r.returncode == 0, r.stderr + r.stdout
    prom = metric_dir / "aitbc_offsite_pull.prom"
    assert prom.exists()
    assert "aitbc_offsite_pull_last_success_timestamp_seconds" in prom.read_text()
    # metric write failing must NOT fail the pull
    (stub_bin / "ssh").write_text('#!/bin/bash\nshift\ncase "$1" in *prom*) exit 9;; *) eval "$1";; esac\n')
    (stub_bin / "ssh").chmod(0o755)
    (remote / GEN).rename(remote / "20261014_010000")
    import os as _os

    for f in (remote / "20261014_010000").iterdir():
        _os.utime(f, (time.time() - 3600,) * 2)
    _os.utime(remote / "20261014_010000", (time.time() - 3600,) * 2)
    r2, _ = _run(tmp_path, remote, stub_bin, METRIC_HOST="fake1", METRIC_TEXTFILE_DIR=str(metric_dir))
    assert r2.returncode == 0, r2.stderr
    assert "pull-metric write" in r2.stderr
