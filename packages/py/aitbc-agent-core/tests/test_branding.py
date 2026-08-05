"""Tests for aitbc_agent_core.branding."""

from aitbc_agent_core.branding import BrandSettings


def test_default_brand_settings():
    brand = BrandSettings.default()
    assert brand.name == "AITBC"
    assert brand.token_symbol == "AITBC"
    assert brand.network_name == "AITBC Network"


def test_from_env_overrides(monkeypatch):
    monkeypatch.setenv("AITBC_BRAND_NAME", "CustomNet")
    monkeypatch.setenv("AITBC_BRAND_TOKEN_SYMBOL", "CNET")
    brand = BrandSettings.from_env()
    assert brand.name == "CustomNet"
    assert brand.token_symbol == "CNET"
    assert brand.network_name == "AITBC Network"  # unchanged


def test_from_env_overrides_argument():
    brand = BrandSettings.from_env(
        overrides={
            "AITBC_BRAND_NAME": "Override",
            "AITBC_BRAND_TOKEN_SYMBOL": "OVR",
        }
    )
    assert brand.name == "Override"
    assert brand.token_symbol == "OVR"
