"""CI-KNOWNRED-TOLERATES-WHOLE-RATCHETS-1 — the manual gate's tolerance
list must key on the failing file, not the check name, and a tolerance
that never fires must fail the run instead of silently masking debt.

The verdict logic lives in an embedded python heredoc inside
run-suite-manual.sh; these tests extract and execute it verbatim.
"""

import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "ci" / "run-suite-manual.sh"
KNOWN_RED = REPO_ROOT / "scripts" / "ci" / "manual-ci-known-red.txt"


def _verdict_src() -> str:
    body = SCRIPT.read_text()
    m = re.search(r"python3 - \"\$OUT_DIR\" \"\$KNOWN_RED\" <<'PY'\n(.*?)\nPY\n", body, re.S)
    assert m, "verdict heredoc not found in run-suite-manual.sh"
    return m.group(1)


def _write_junit(out_dir: Path, suite: str, failing_name: str | None) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "results.tsv").write_text(f"{suite}\t{1 if failing_name else 0}\t3\n")
    if failing_name:
        case = f'<testcase classname="check" name="{failing_name}" time="0"><failure>see log</failure></testcase>'
        xml = (
            f'<?xml version="1.0"?><testsuite name="{suite}" tests="1" failures="1" skipped="0" errors="0">{case}</testsuite>'
        )
    else:
        xml = f'<?xml version="1.0"?><testsuite name="{suite}" tests="1" failures="0" skipped="0" errors="0"><testcase classname="check" name="{suite}" time="0"/></testsuite>'
    (out_dir / f"{suite}.xml").write_text(xml)


def _run(out_dir: Path, known: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-", str(out_dir), str(known)],
        input=_verdict_src(),
        capture_output=True,
        text=True,
    )


def test_unlisted_check_failure_fails(tmp_path):
    out = tmp_path / "out"
    known = tmp_path / "known.txt"
    known.write_text("# empty\n")
    _write_junit(out, "except-ratchet", "except-ratchet::aitbc/new_file.py")
    r = _run(out, known)
    assert r.returncode == 1
    assert "NEW-RED" in r.stdout


def test_listed_per_file_failure_is_tolerated(tmp_path):
    out = tmp_path / "out"
    known = tmp_path / "known.txt"
    known.write_text("check::except-ratchet::aitbc/new_file.py\ttolerated\n")
    _write_junit(out, "except-ratchet", "except-ratchet::aitbc/new_file.py")
    r = _run(out, known)
    assert r.returncode == 0
    assert "TOLER" in r.stdout


def test_whole_check_entry_no_longer_covers_new_files(tmp_path):
    out = tmp_path / "out"
    known = tmp_path / "known.txt"
    known.write_text("check::except-ratchet::aitbc/old_file.py\ttolerated\n")
    _write_junit(out, "except-ratchet", "except-ratchet::aitbc/new_file.py")
    r = _run(out, known)
    assert r.returncode == 1
    assert "aitbc/new_file.py" in r.stdout


def test_stale_tolerance_fails_the_run(tmp_path):
    out = tmp_path / "out"
    known = tmp_path / "known.txt"
    known.write_text("check::except-ratchet::aitbc/old_file.py\tfixed\n")
    _write_junit(out, "except-ratchet", None)
    r = _run(out, known)
    assert r.returncode == 1
    assert "STALE-TOLERANCE" in r.stdout


def test_known_red_has_no_whole_check_ratchet_entries():
    for line in KNOWN_RED.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        ident = line.split("\t", 1)[0].strip()
        # per-file entries carry a third segment; a bare check::name entry
        # tolerates the whole check and must not appear.
        for check in ("check::c901-ratchet", "check::except-ratchet", "check::version-check"):
            assert ident != check, f"whole-check tolerance for {check} still listed"


def test_remote_driver_ssh_failure_reaches_exit_2():
    body = SCRIPT.read_text()
    assert "<<'REMOTE' || rc_remote=$?" in body
    assert "exit 2" in body.split("REMOTE\n", 1)[1]
