"""The rerun policy: no global retries, named flakes only (TEST-1).

``pyproject.toml`` addopts used to carry ``--reruns 2 --reruns-delay 1`` for
every suite on every host, so any transient failure was retried twice before
anyone saw it. That is what hid the 15-test ``cli/tests`` burst on node2 on
13 Oct — subprocess tests reading the operator's own ``~/.aitbc.yaml`` failed
against a transient remote endpoint and passed on rerun, invisibly.

Retries now exist only as ``@pytest.mark.flaky(reruns=N)`` on tests with a
named environmental cause. These tests keep both halves of the arrangement
enforceable: the marker must be registered (``--strict-markers`` is on, and
pytest-rerunfailures only self-registers it when the plugin is installed), and
addopts must not grow a global ``--reruns`` back.
"""

import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def _pytest_ini() -> dict:
    return tomllib.loads((REPO / "pyproject.toml").read_text())["tool"]["pytest"]["ini_options"]


def test_flaky_marker_is_registered():
    """``pytest.mark.flaky`` must resolve on hosts without the plugin too."""
    markers = _pytest_ini()["markers"]
    names = {m.split(":", 1)[0].split("(", 1)[0].strip() for m in markers}
    assert "flaky" in names, (
        "pytest.mark.flaky is rerunfailures' per-test API; without an ini "
        "entry --strict-markers rejects it wherever the plugin is absent"
    )


def test_addopts_do_not_request_reruns_globally():
    """A blanket retry hides failure bursts (the 13-Oct ``cli/tests`` incident).

    Retries belong on individually marked tests, so addopts must stay free of
    ``--reruns``/``--reruns-delay``; the root conftest still accepts them as
    no-ops for hosts that invoke pytest with them explicitly.
    """
    addopts = _pytest_ini()["addopts"]
    assert "--reruns" not in addopts and "--reruns-delay" not in addopts, (
        "global --reruns in addopts retried every suite twice by default and "
        "hid the flaky CLI burst; use pytest.mark.flaky on the named tests instead"
    )
