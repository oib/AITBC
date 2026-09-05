"""The test tier must stay a strict, pinned subset of the dev tier.

requirements-test.txt lists names only; versions come from requirements-dev.txt
used as a pip constraints file. That only holds if every name in the test tier
actually appears in the dev export -- otherwise pip silently resolves an
unpinned version from PyPI and the two tiers drift apart without anyone
noticing. These tests make that impossible.

Background: pyproject's addopts pass --reruns unconditionally, so a host without
pytest-rerunfailures cannot collect the suite at all. node0, node2 and hub2 were
in exactly that state because the profile installer exports `--only main`.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TEST_REQ = REPO / "requirements-test.txt"
DEV_REQ = REPO / "requirements-dev.txt"


def _canon(name: str) -> str:
    """PEP 503 name normalisation, minus any extras marker."""
    return re.sub(r"[-_.]+", "-", name.split("[")[0]).lower()


def _test_tier_names() -> set[str]:
    names = set()
    for line in TEST_REQ.read_text().splitlines():
        line = line.split("#")[0].strip()
        if line:
            names.add(_canon(line))
    return names


def _dev_tier_pins() -> dict[str, str]:
    pins = {}
    for line in DEV_REQ.read_text().splitlines():
        match = re.match(r"^([A-Za-z0-9._\[\]-]+)==([^\s;]+)", line.split("#")[0].strip())
        if match:
            pins[_canon(match.group(1))] = match.group(2)
    return pins


def test_test_tier_is_a_subset_of_the_dev_tier():
    missing = sorted(_test_tier_names() - set(_dev_tier_pins()))
    assert not missing, (
        f"{missing} are in requirements-test.txt but absent from requirements-dev.txt. "
        "Using the dev export as a constraints file would leave them unpinned, so pip "
        "would resolve whatever PyPI offers. Add them to the poetry dev group and "
        "re-run scripts/ci/export-requirements.sh."
    )


def test_addopts_plugins_are_in_the_test_tier():
    """Whatever the shared addopts require must ship in the tier every node gets."""
    pyproject = (REPO / "pyproject.toml").read_text()
    addopts = re.search(r'^addopts\s*=\s*"([^"]*)"', pyproject, re.MULTILINE)
    assert addopts, "could not find addopts in pyproject.toml"

    # flag -> distribution that provides it
    provided_by = {
        "--reruns": "pytest-rerunfailures",
        "--timeout": "pytest-timeout",
        "--cov": "pytest-cov",
    }
    tier = _test_tier_names()
    for flag, dist in provided_by.items():
        if flag in addopts.group(1):
            assert _canon(dist) in tier, (
                f"addopts passes {flag}, provided by {dist}, but {dist} is not in "
                "requirements-test.txt. Every node runs with these addopts, so pytest "
                "would abort during collection with 'unrecognized arguments'."
            )
