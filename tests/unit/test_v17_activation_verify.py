"""#1005: the revived-surface probe accepts only armed-gate rejections."""

from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/ops/v17-activation-verify.sh"


def _case_block(src: str) -> str:
    start = src.index('case "$code" in')
    # the inner `case "$sdet"` ends first; the outer esac is column-8
    return src[start : src.index("\n        esac", start)]


def test_no_catchall_pass():
    blk = _case_block(SCRIPT.read_text())
    # the old catch-all printed ok for any code — it must now fail
    assert "unexpected answer" in blk


def test_route_miss_404_fails_but_business_404_passes():
    blk = _case_block(SCRIPT.read_text())
    assert "404 route-miss" in blk
    # armed gate's 404 (account-not-found) still passes
    assert "HTTP 404 on :%s" in blk


def test_unexpected_statuses_fail():
    blk = _case_block(SCRIPT.read_text())
    for arm in ("410", "403"):
        assert arm in blk
    tail = blk.rsplit("*)", 1)[-1]
    assert "FAIL" in tail and "revive_bad=1" in tail
