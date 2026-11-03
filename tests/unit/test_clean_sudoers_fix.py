"""UTILS-CLEAN-SUDOERS-ROOT-EQUIVALENT-GRANT-1 — no root-equivalent wildcards.

clean-sudoers-fix.sh was presented as a minimal sudoers but granted NOPASSWD
root for `chown -R *`, `chmod -R *`, `git *`, `pip3 install *`, `incus exec
*`, `kill -HUP *` — each a root shell in a trenchcoat. The script now writes
the candidate to a temp file, visudo -c's it, and only then installs.
"""

from pathlib import Path

SCRIPT = (Path(__file__).resolve().parents[2] / "scripts" / "utils" / "clean-sudoers-fix.sh").read_text()


def test_no_root_equivalent_wildcard_grants():
    for needle in (
        "chown -R *",
        "chmod -R *",
        "git *",
        "pip3 install *",
        "incus exec",
        "incus shell",
        "kill -HUP *",
        "rm -rf",
        "make *",
        "gcc *",
        "NOPASSWD: ALL",
    ):
        assert needle not in SCRIPT, needle


def test_candidate_is_validated_before_install():
    assert "mktemp" in SCRIPT
    assert "visudo -c" in SCRIPT
    # install happens after the visudo check, not before
    assert SCRIPT.index('visudo -c -f "$tmp_sudoers"') < SCRIPT.index("install -m 0440")
