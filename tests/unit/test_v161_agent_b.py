"""Unit tests for v0.16.1 Agent B tasks."""

from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path
from types import ModuleType

from sqlmodel import Session, SQLModel, create_engine

REPO_ROOT = Path(__file__).resolve().parents[2]


def _coordinator_module(module_path: str) -> ModuleType:
    """Import a coordinator-api module by adding its source directory to path."""
    src = str(REPO_ROOT / "apps" / "coordinator-api" / "src")
    if src not in sys.path:
        sys.path.insert(0, src)
    return __import__(module_path, fromlist=["__name__"])


def test_cli_config_check_reports_missing_keys() -> None:
    from click.testing import CliRunner
    from cli.aitbc_cli.core.main import cli

    runner = CliRunner()
    result = runner.invoke(cli, ["config", "check"])
    assert result.exit_code == 0
    assert "AITBC_API_KEY" in result.output or "missing" in result.output.lower()


def test_cli_config_set_and_unset() -> None:
    from click.testing import CliRunner
    from cli.aitbc_cli.core.main import cli

    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(cli, ["config", "set", "timeout", "60"])
        assert result.exit_code == 0
        config_path = Path(".aitbc.yaml")
        assert config_path.exists()

        result = runner.invoke(cli, ["config", "unset", "timeout"])
        assert result.exit_code == 0
        text = config_path.read_text(encoding="utf-8")
        assert "timeout" not in text


def test_bootstrap_env_generates_dot_env() -> None:
    import tempfile

    from click.testing import CliRunner
    from cli.aitbc_cli.core.main import cli

    runner = CliRunner()
    with tempfile.TemporaryDirectory() as tmpdir:
        env_path = Path(tmpdir) / ".env"
        result = runner.invoke(cli, ["bootstrap", "bootstrap-env", "--output", str(env_path), "--overwrite"])
        assert result.exit_code == 0
        assert env_path.exists()
        text = env_path.read_text(encoding="utf-8")
        assert "AITBC_API_KEY=" in text


def test_env_validator_detects_missing_keys() -> None:
    from cli.aitbc_cli.services.env_validator import validate_env

    result = validate_env({})
    assert result.valid is False
    assert "AITBC_API_KEY" in result.missing


def test_developer_service_registers_and_lists() -> None:
    service_mod = _coordinator_module("coordinator_api.contexts.developer.services.developer_service")
    schemas = _coordinator_module("coordinator_api.contexts.developer.schemas.developer")

    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        service = service_mod.DeveloperService(session)
        request = schemas.DeveloperCreate(wallet_address="0xabc", name="Builder")
        import asyncio

        developer = asyncio.run(service.register(request))
        assert developer.wallet_address == "0xabc"
        found = asyncio.run(service.get_by_wallet("0xabc"))
        assert found is not None


def test_grant_service_creates_and_lists() -> None:
    import asyncio

    service_mod = _coordinator_module("coordinator_api.contexts.governance.services.grant_service")
    dev_mod = _coordinator_module("coordinator_api.contexts.developer.domain.developer")

    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        # Register a developer first because grant uses foreign key.
        developer = dev_mod.Developer(wallet_address="0xabc")
        session.add(developer)
        session.commit()

        service = service_mod.GrantService(session)
        grant = asyncio.run(
            service.create_grant(
                developer_id=developer.id,
                title="Test Grant",
                description="test",
                requested_amount=Decimal("100"),
                voting_days=7,
            )
        )
        assert grant.title == "Test Grant"
        assert grant.status.value == "submitted"


def test_hello_agent_example() -> None:
    import importlib.util

    main_path = REPO_ROOT / "examples" / "builder" / "hello-agent" / "main.py"
    spec = importlib.util.spec_from_file_location("hello_agent_main", str(main_path))
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    result = module.run_agent()
    assert result["status"] == "ok"
    assert "AITBC" in result["message"]
