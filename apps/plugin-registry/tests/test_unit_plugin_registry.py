"""Unit tests for plugin registry service"""

import pytest
import sys
import sys
from pathlib import Path
from datetime import datetime, UTC


from main import app, PluginRegistration, PluginVersion, SecurityScan


@pytest.mark.unit
def test_app_initialization():
    """Test that the FastAPI app initializes correctly"""
    assert app is not None
    assert app.title == "AITBC Plugin Registry"
    assert app.version == "1.0.0"


@pytest.mark.unit
def test_plugin_registration_model():
    """Test PluginRegistration model"""
    plugin = PluginRegistration(
        name="Test Plugin",
        version="1.0.0",
        description="A test plugin",
        author="Test Author",
        category="testing",
        tags=["test", "demo"],
        repository_url="https://github.com/test/plugin",
        homepage_url="https://test.com",
        license="MIT",
        dependencies=["dependency1"],
        aitbc_version="1.0.0",
        plugin_type="cli"
    )
    assert plugin.name == "Test Plugin"
    assert plugin.version == "1.0.0"
    assert plugin.author == "Test Author"
    assert plugin.category == "testing"
    assert plugin.tags == ["test", "demo"]
    assert plugin.license == "MIT"
    assert plugin.plugin_type == "cli"


@pytest.mark.unit
def test_plugin_registration_defaults():
    """Test PluginRegistration default values"""
    plugin = PluginRegistration(
        name="Test Plugin",
        version="1.0.0",
        description="A test plugin",
        author="Test Author",
        category="testing",
        tags=[],
        repository_url="https://github.com/test/plugin",
        license="MIT",
        aitbc_version="1.0.0",
        plugin_type="cli"
    )
    assert plugin.homepage_url is None
    assert plugin.dependencies == []


@pytest.mark.unit
def test_plugin_version_model():
    """Test PluginVersion model"""
    version = PluginVersion(
        version="1.0.0",
        changelog="Initial release",
        download_url="https://github.com/test/plugin/archive/v1.0.0.tar.gz",
        checksum="abc123",
        aitbc_compatibility=["1.0.0", "1.1.0"],
        release_date=datetime.now(datetime.UTC)
    )
    assert version.version == "1.0.0"
    assert version.changelog == "Initial release"
    assert version.download_url == "https://github.com/test/plugin/archive/v1.0.0.tar.gz"
    assert version.checksum == "abc123"
    assert version.aitbc_compatibility == ["1.0.0", "1.1.0"]


@pytest.mark.unit
def test_security_scan_model():
    """Test SecurityScan model"""
    scan = SecurityScan(
        scan_id="scan_123",
        plugin_id="test_plugin",
        version="1.0.0",
        scan_date=datetime.now(datetime.UTC),
        vulnerabilities=[{"severity": "low", "description": "Test"}],
        risk_score="low",
        passed=True
    )
    assert scan.scan_id == "scan_123"
    assert scan.plugin_id == "test_plugin"
    assert scan.version == "1.0.0"
    assert scan.risk_score == "low"
    assert scan.passed is True
    assert len(scan.vulnerabilities) == 1
