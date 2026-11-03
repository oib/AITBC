"""Gone-pins for retired one-shot deployment probe scripts."""

from pathlib import Path

UTILS = Path(__file__).resolve().parents[2] / "scripts" / "utils"


def test_verify_production_advanced_is_retired():
    """#953: it probed all service metrics on one wrong port and checked
    removed components — the real units' health endpoints cover this."""
    assert not (UTILS / "verify-production-advanced.sh").exists()


def test_dead_doc_check_scripts_are_retired():
    """#954: the doc-check tools pointed at a retired plan-doc path that no
    longer exists — they always reported 'not found'."""
    assert not (UTILS / "check-documentation-requirements.sh").exists()
    assert not (UTILS / "run_documentation_conversion.sh").exists()
