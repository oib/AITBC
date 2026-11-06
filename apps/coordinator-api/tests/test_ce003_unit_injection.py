"""CE-003 regression: agent deployment unit-file injection must be rejected.

instance_id is composed from user-controlled deployment_name and
target_environment, then interpolated into a systemd unit path and unit
contents. A newline payload must never reach the filesystem or systemctl.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from coordinator_api.contexts.agent_coordination.services.integration import (
    AgentDeploymentManager,
    _validate_unit_component,
)


@pytest.mark.parametrize(
    "bad",
    [
        "name\nExecStart=/bin/sh -c id",
        "name\n[Service]\nExecStart=/bin/id",
        "../../etc/cron.d/evil",
        "name with space",
        "name;reboot",
        "name$(id)",
        "",
        "-leading-dash",
        "a" * 64,
    ],
)
def test_validate_unit_component_rejects(bad: str) -> None:
    with pytest.raises(ValueError):
        _validate_unit_component(bad, "instance_id")


@pytest.mark.parametrize("good", ["deploy-prod-0", "agent.v2_us-1", "a" * 63])
def test_validate_unit_component_accepts(good: str) -> None:
    assert _validate_unit_component(good, "instance_id") == good


def test_deploy_agent_systemd_rejects_poisoned_instance_id() -> None:
    """A pre-existing poisoned row must fail before any file write."""
    manager = AgentDeploymentManager(session=None)  # type: ignore[arg-type]
    instance = SimpleNamespace(instance_id="evil\nExecStart=/bin/touch /tmp/pwned", port=8000)

    with (
        patch("builtins.open", side_effect=AssertionError("unit file must not be opened")),
        patch(
            "coordinator_api.contexts.agent_coordination.services.integration.asyncio.create_subprocess_exec",
            new=AsyncMock(side_effect=AssertionError("systemctl must not run")),
        ),
        pytest.raises(ValueError),
    ):
        asyncio.run(manager._deploy_agent_systemd(instance, SimpleNamespace()))  # type: ignore[arg-type]


class _FakeProc:
    def __init__(self, cmd: tuple[str, ...]) -> None:
        self._cmd = cmd
        self.returncode = 0

    async def communicate(self) -> tuple[bytes, bytes]:
        if "is-active" in self._cmd:
            return b"active\n", b""
        return b"", b""


async def _fake_create_subprocess(*cmd: str, **_kwargs: object) -> _FakeProc:
    return _FakeProc(cmd)


def test_deploy_agent_systemd_unit_runs_unprivileged() -> None:
    """The generated unit must not run the agent as root (CE-003)."""
    manager = AgentDeploymentManager(session=None)  # type: ignore[arg-type]
    captured: dict[str, str] = {}

    class _FakeFile:
        def __init__(self, path: str, _mode: str) -> None:
            captured["path"] = path

        def __enter__(self) -> _FakeFile:
            return self

        def __exit__(self, *exc: object) -> None:
            return None

        def write(self, content: str) -> None:
            captured["content"] = content

    instance = SimpleNamespace(instance_id="deploy-prod-0", port=8000)

    with (
        patch("builtins.open", side_effect=lambda p, m: _FakeFile(p, m)),
        patch("coordinator_api.contexts.agent_coordination.services.integration.os.chmod"),
        patch(
            "coordinator_api.contexts.agent_coordination.services.integration.asyncio.create_subprocess_exec",
            new=_fake_create_subprocess,
        ),
    ):
        asyncio.run(manager._deploy_agent_systemd(instance, SimpleNamespace()))  # type: ignore[arg-type]

    content = captured["content"]
    assert "User=aitbc" in content
    assert "User=root" not in content
    assert "Group=root" not in content
    assert captured["path"].endswith("aitbc-agent-deploy-prod-0.service")
