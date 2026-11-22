"""AUDIT-GPU-UPDATE-PRICING-1 (#2564): ``gpu update --pricing`` let
non-numeric values escape as an ``InvalidOperation`` traceback and sent
negative, NaN, Infinity and key-less JSON prices to the GPU service.

Now ``_price_per_hour`` validates everything before the PUT: finite,
non-negative Decimal; dicts must carry ``price_per_hour``.
"""

from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from aitbc_cli.commands.gpu_market import gpu


def _invoke(pricing: str):
    config = MagicMock()
    config.gpu_service_url = "http://gpu.local"
    config.gpu_api_key = "k"
    client = MagicMock()
    with (
        patch("aitbc_cli.commands.gpu_market.get_config", return_value=config),
        patch("aitbc_cli.commands.gpu_market.AITBCHTTPClient", return_value=client),
    ):
        result = CliRunner().invoke(gpu, ["update", "--gpu-id", "gpu-1", "--pricing", pricing], obj={"output_format": "table"})
    return result, client


@pytest.mark.parametrize(
    "pricing,expected",
    [
        ('{"price_per_hour":10}', "10"),
        ('{"price_per_hour":10.5}', "10.5"),
        ("10", "10"),
        ("7.25", "7.25"),
        ("0", "0"),
    ],
)
def test_valid_prices_reach_service(pricing, expected):
    result, client = _invoke(pricing)
    assert result.exit_code == 0, result.output
    body = client.put.call_args.kwargs["json"]
    assert body == {"price_per_hour": expected}


@pytest.mark.parametrize(
    "pricing",
    [
        "abc",  # bare non-numeric → InvalidOperation used to escape
        '"abc"',  # JSON string
        '{"price_per_hour":"abc"}',
        '{"price_per_hour":null}',
        '{"other_key":10}',  # key-less dict → None used to be sent
        "-5",
        '{"price_per_hour":-1}',
        "nan",
        "NaN",
        "Infinity",
        "-Infinity",
        '{"price_per_hour":1e999}',  # finite? no — overflow to Infinity
    ],
)
def test_invalid_prices_never_reach_service(pricing):
    result, client = _invoke(pricing)
    assert result.exit_code != 0
    assert "Traceback" not in result.output
    client.put.assert_not_called()


def test_status_only_still_works():
    config = MagicMock()
    config.gpu_service_url = "http://gpu.local"
    config.gpu_api_key = "k"
    client = MagicMock()
    with (
        patch("aitbc_cli.commands.gpu_market.get_config", return_value=config),
        patch("aitbc_cli.commands.gpu_market.AITBCHTTPClient", return_value=client),
    ):
        result = CliRunner().invoke(gpu, ["update", "--gpu-id", "gpu-1", "--status", "active"], obj={"output_format": "table"})
    assert result.exit_code == 0, result.output
    assert client.put.call_args.kwargs["json"] == {"status": "active"}
