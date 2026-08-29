"""Tests for the additional typed AITBC CLI tools in the MCP server."""

from __future__ import annotations

import json
import sys
from pathlib import Path

MCP_SERVER_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(MCP_SERVER_DIR))

import aitbc_mcp_server as mcp_server

# Replace remote SSH execution with a recorder so tests run offline.
CAPTURED: list[dict[str, object]] = []


def _fake_run_remote(host: str, command: str, timeout: int = 60) -> dict[str, object]:
    CAPTURED.append({"host": host, "command": command, "timeout": timeout})
    return {"host": host, "command": command, "returncode": 0, "stdout": "{}", "stderr": ""}


mcp_server._run_remote = _fake_run_remote

import aitbc_mcp_cli_tools  # noqa: E402


def _last_command() -> str:
    assert CAPTURED
    return str(CAPTURED[-1]["command"])


def _clear() -> None:
    CAPTURED.clear()


def test_buy_ait_exchange():
    _clear()
    result = json.loads(
        aitbc_mcp_cli_tools.buy_ait_exchange(
            amount="1.0",
            max_price="0.00076",
            wallet="genesis",
            dry_run=False,
            confirm=True,
            role="hub",
        )
    )
    assert result["returncode"] == 0
    cmd = _last_command()
    assert "aitbc" in cmd
    assert "exchange-island" in cmd
    assert "buy" in cmd
    assert "--ait-amount=1.0" in cmd
    assert "--quote-currency=ETH" in cmd
    assert "--max-price=0.00076" in cmd
    assert "--wallet=genesis" in cmd


def test_sell_ait_exchange():
    _clear()
    result = json.loads(
        aitbc_mcp_cli_tools.sell_ait_exchange(
            amount="2.0",
            min_price="0.00075",
            wallet="hub2-shop",
            dry_run=False,
            confirm=True,
            role="hub",
        )
    )
    assert result["returncode"] == 0
    cmd = _last_command()
    assert "exchange-island sell" in cmd
    assert "--ait-amount=2.0" in cmd
    assert "--quote-currency=ETH" in cmd
    assert "--min-price=0.00075" in cmd
    assert "--wallet=hub2-shop" in cmd


def test_get_exchange_orderbook():
    _clear()
    result = json.loads(aitbc_mcp_cli_tools.get_exchange_orderbook(pair="AIT/ETH", limit=5, role="hub"))
    assert result["returncode"] == 0
    cmd = _last_command()
    assert "exchange-island orderbook" in cmd
    assert "AIT/ETH" in cmd
    assert "--limit=5" in cmd


def test_create_island():
    _clear()
    result = json.loads(
        aitbc_mcp_cli_tools.create_island(
            island_id="ait-test-island",
            island_name="test",
            chain_id="ait-test",
            dry_run=False,
            confirm=True,
            role="hub",
        )
    )
    assert result["returncode"] == 0
    cmd = _last_command()
    assert "node island create" in cmd
    assert "--island-id=ait-test-island" in cmd
    assert "--island-name=test" in cmd
    assert "--chain-id=ait-test" in cmd


def test_join_island():
    _clear()
    result = json.loads(
        aitbc_mcp_cli_tools.join_island(
            island_id="ait-test-island",
            island_name="test",
            chain_id="ait-test",
            hub="hub.aitbc.bubuit.net",
            is_hub=False,
            rpc_url="https://hub.aitbc.bubuit.net/rpc",
            dry_run=False,
            confirm=True,
            role="shop",
        )
    )
    assert result["returncode"] == 0
    cmd = _last_command()
    assert "node island join" in cmd
    assert "--island-id=ait-test-island" in cmd
    assert "--island-name=test" in cmd
    assert "--chain-id=ait-test" in cmd
    assert "--hub=hub.aitbc.bubuit.net" in cmd
    assert "--rpc-url=https://hub.aitbc.bubuit.net/rpc" in cmd
    assert "--is-hub" not in cmd


def test_join_island_as_hub():
    _clear()
    result = json.loads(
        aitbc_mcp_cli_tools.join_island(
            island_id="ait-test-island",
            island_name="test",
            chain_id="ait-test",
            is_hub=True,
            dry_run=False,
            confirm=True,
            role="hub",
        )
    )
    assert result["returncode"] == 0
    cmd = _last_command()
    assert "node island join" in cmd
    assert "--is-hub" in cmd


def test_create_market_offer():
    _clear()
    result = json.loads(
        aitbc_mcp_cli_tools.create_market_offer(
            service_type="ipfs",
            model="ipfs-host",
            price="1",
            unit="per_day",
            description="Host files for 1 AIT per day",
            wallet="hub2-shop",
            dry_run=False,
            confirm=True,
            role="shop",
        )
    )
    assert result["returncode"] == 0
    cmd = _last_command()
    assert cmd.startswith("AITBC_WALLET_DIR=/var/lib/aitbc/wallets")
    assert "market" in cmd
    assert "--wallet=hub2-shop" in cmd
    assert "offer" in cmd
    assert "ipfs" in cmd
    assert "ipfs-host" in cmd
    assert "--unit=per_day" in cmd
    assert "--description='Host files for 1 AIT per day'" in cmd


def test_upload_ipfs():
    _clear()
    result = json.loads(
        aitbc_mcp_cli_tools.upload_ipfs(
            file="/tmp/test.txt",
            name="test upload",
            pin=True,
            dry_run=False,
            confirm=True,
            role="shop",
        )
    )
    assert result["returncode"] == 0
    cmd = _last_command()
    assert "ipfs upload" in cmd
    assert "--file=/tmp/test.txt" in cmd
    assert "--name='test upload'" in cmd
    assert "--pin" in cmd


def test_download_ipfs():
    _clear()
    result = json.loads(
        aitbc_mcp_cli_tools.download_ipfs(
            cid="QmTest",
            output="/tmp/out",
            wait=True,
            role="hub",
        )
    )
    assert result["returncode"] == 0
    cmd = _last_command()
    assert "ipfs download" in cmd
    assert "QmTest" in cmd
    assert "--output=/tmp/out" in cmd
    assert "--wait" in cmd


def test_create_wallet():
    _clear()
    result = json.loads(
        aitbc_mcp_cli_tools.create_wallet(
            name="test-wallet",
            wallet_type="simple",
            encrypt=False,
            dry_run=False,
            confirm=True,
            role="hub",
        )
    )
    assert result["returncode"] == 0
    cmd = _last_command()
    assert "wallet create" in cmd
    assert "test-wallet" in cmd
    assert "--type=simple" in cmd
    assert "--no-encrypt" in cmd


def test_fund_wallet():
    _clear()
    result = json.loads(
        aitbc_mcp_cli_tools.fund_wallet(
            address="0x5e2D7C7A4F8E9B1C3d5A2e8F4c6b8a0D2e4f6A8C",
            amount_ait="5.0",
            dry_run=False,
            confirm=True,
            role="hub",
        )
    )
    assert result["returncode"] == 0
    cmd = _last_command()
    assert "wallet fund" in cmd
    assert "0x5e2D7C7A4F8E9B1C3d5A2e8F4c6b8a0D2e4f6A8C" in cmd
    assert "--amount-ait=5.0" in cmd


def test_dry_run_gating():
    _clear()
    result = json.loads(
        aitbc_mcp_cli_tools.buy_ait_exchange(
            amount="1.0",
            max_price="0.00076",
            dry_run=True,
            confirm=False,
            role="hub",
        )
    )
    assert result.get("dry_run") is True
    assert "command" in result
    assert not CAPTURED


def test_run_market_offer():
    _clear()
    result = json.loads(
        aitbc_mcp_cli_tools.run_market_offer(
            offer_id_or_plugin_id="sw_offer_1234",
            prompt="transcribe this",
            wallet="test-wallet-3",
            language="en",
            stream=True,
            dry_run=False,
            confirm=True,
            role="customer",
        )
    )
    assert result["returncode"] == 0
    cmd = _last_command()
    assert cmd.startswith("AITBC_WALLET_DIR=/var/lib/aitbc/wallets")
    assert "market --wallet=test-wallet-3 run" in cmd
    assert "sw_offer_1234" in cmd
    assert "'transcribe this'" in cmd
    assert "--language=en" in cmd
    assert "--stream" in cmd


def test_send_aitbc_from_wallet():
    _clear()
    result = json.loads(
        aitbc_mcp_cli_tools.send_aitbc_from_wallet(
            to_address="0xC10F0E4fC10f0e4FC10f0e4fC10F0E4FC10F0e4f",
            amount="1.5",
            wallet_name="test-wallet-3",
            fee="0.001",
            dry_run=False,
            confirm=True,
            role="hub",
        )
    )
    assert result["returncode"] == 0
    cmd = _last_command()
    assert cmd.startswith("AITBC_WALLET_DIR=/var/lib/aitbc/wallets")
    assert "wallet --wallet-name=test-wallet-3 send" in cmd
    assert "0xC10F0E4fC10f0e4FC10f0e4fC10F0E4FC10F0e4f" in cmd
    assert "1.5" in cmd
    assert "--fee=0.001" in cmd


def test_nested_market_escrow_create():
    _clear()
    result = json.loads(
        aitbc_mcp_cli_tools.create_market_escrow(
            job_id="job-1234",
            buyer="0xABCDabcdABcDabcDaBCDAbcdABcdAbCdABcDABCd",
            provider="0xDb5247d03cA2e40f3995A583b2C097Ab703efD4d",
            amount="1.0",
            wallet="test-wallet-3",
            dry_run=False,
            confirm=True,
            role="hub",
        )
    )
    assert result["returncode"] == 0
    cmd = _last_command()
    assert "market --wallet=test-wallet-3 escrow create" in cmd
    assert "job-1234" in cmd
    assert "0xABCDabcdABcDabcDaBCDAbcdABcdAbCdABcDABCd" in cmd
    assert "0xDb5247d03cA2e40f3995A583b2C097Ab703efD4d" in cmd
    assert "1.0" in cmd


def test_set_aitbc_config():
    _clear()
    result = json.loads(
        aitbc_mcp_cli_tools.set_aitbc_config(
            key="coordinator.url",
            value="https://hub.aitbc.bubuit.net",
            global_config=True,
            dry_run=False,
            confirm=True,
            role="hub",
        )
    )
    assert result["returncode"] == 0
    cmd = _last_command()
    assert "config set" in cmd
    assert "coordinator.url" in cmd
    assert "https://hub.aitbc.bubuit.net" in cmd
    assert "--global" in cmd


def test_login_aitbc():
    _clear()
    result = json.loads(
        aitbc_mcp_cli_tools.login_aitbc(
            wallet="test-wallet-3",
            dry_run=False,
            confirm=True,
            role="hub",
        )
    )
    assert result["returncode"] == 0
    cmd = _last_command()
    assert cmd.startswith("AITBC_WALLET_DIR=/var/lib/aitbc/wallets")
    assert "auth login --wallet=test-wallet-3" in cmd


if __name__ == "__main__":
    test_buy_ait_exchange()
    test_sell_ait_exchange()
    test_get_exchange_orderbook()
    test_create_island()
    test_join_island()
    test_join_island_as_hub()
    test_create_market_offer()
    test_upload_ipfs()
    test_download_ipfs()
    test_create_wallet()
    test_fund_wallet()
    test_dry_run_gating()
    test_run_market_offer()
    test_send_aitbc_from_wallet()
    test_nested_market_escrow_create()
    test_set_aitbc_config()
    test_login_aitbc()
    print("All aitbc_mcp_cli_tools tests passed")
