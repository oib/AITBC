"""Edge case and error handling tests for plugin registry service"""

import pytest
import sys
import sys
from pathlib import Path
from fastapi.testclient import TestClient
from datetime import datetime


from main import app, PluginRegistration, PluginVersion, SecurityScan, plugins, plugin_versions, security_scans, analytics, downloads


@pytest.fixture(autouse=True)
def reset_state():
    """Reset global state before each test"""
    plugins.clear()
    plugin_versions.clear()
    security_scans.clear()
    analytics.clear()
    downloads.clear()
    yield
    plugins.clear()
    plugin_versions.clear()
    security_scans.clear()
    analytics.clear()
    downloads.clear()


@pytest.mark.unit
def test_plugin_registration_empty_name():
    """Test PluginRegistration with empty name"""
    plugin = PluginRegistration(
        name="",
        version="1.0.0",
        description="A test plugin",
        author="Test Author",
        category="testing",
        tags=[],
        repository_url="https://github.com/test/plugin",
        license="MIT",
        dependencies=[],
        aitbc_version="1.0.0",
        plugin_type="cli"
    )
    assert plugin.name == ""


@pytest.mark.unit
def test_plugin_registration_empty_tags():
    """Test PluginRegistration with empty tags"""
    plugin = PluginRegistration(
        name="Test Plugin",
        version="1.0.0",
        description="A test plugin",
        author="Test Author",
        category="testing",
        tags=[],
        repository_url="https://github.com/test/plugin",
        license="MIT",
        dependencies=[],
        aitbc_version="1.0.0",
        plugin_type="cli"
    )
    assert plugin.tags == []


@pytest.mark.unit
def test_plugin_version_empty_changelog():
    """Test PluginVersion with empty changelog"""
    version = PluginVersion(
        version="1.0.0",
        changelog="",
        download_url="https://github.com/test/plugin/archive/v1.0.0.tar.gz",
        checksum="abc123",
        aitbc_compatibility=["1.0.0"],
        release_date=datetime.utcnow()
    )
    assert version.changelog == ""


@pytest.mark.unit
def test_security_scan_empty_vulnerabilities():
    """Test SecurityScan with empty vulnerabilities"""
    scan = SecurityScan(
        scan_id="scan_123",
        plugin_id="test_plugin",
        version="1.0.0",
        scan_date=datetime.utcnow(),
        vulnerabilities=[],
        risk_score="low",
        passed=True
    )
    assert scan.vulnerabilities == []


@pytest.mark.integration
def test_add_version_nonexistent_plugin():
    """Test adding version to nonexistent plugin"""
    client = TestClient(app)
    version = PluginVersion(
        version="1.0.0",
        changelog="Initial release",
        download_url="https://github.com/test/plugin/archive/v1.0.0.tar.gz",
        checksum="abc123",
        aitbc_compatibility=["1.0.0"],
        release_date=datetime.utcnow()
    )
    response = client.post("/api/v1/plugins/nonexistent/versions", json=version.model_dump(mode='json'))
    assert response.status_code == 404


@pytest.mark.integration
def test_download_nonexistent_plugin():
    """Test downloading nonexistent plugin"""
    client = TestClient(app)
    response = client.get("/api/v1/plugins/nonexistent/download/1.0.0")
    assert response.status_code == 404


@pytest.mark.integration
def test_download_nonexistent_version():
    """Test downloading nonexistent version"""
    client = TestClient(app)
    
    # Register plugin first
    plugin = PluginRegistration(
        name="Test Plugin",
        version="1.0.0",
        description="A test plugin",
        author="Test Author",
        category="testing",
        tags=[],
        repository_url="https://github.com/test/plugin",
        license="MIT",
        dependencies=[],
        aitbc_version="1.0.0",
        plugin_type="cli"
    )
    client.post("/api/v1/plugins/register", json=plugin.model_dump())
    
    # Try to download nonexistent version
    response = client.get("/api/v1/plugins/test_plugin/download/2.0.0")
    assert response.status_code == 404


@pytest.mark.integration
def test_security_scan_nonexistent_plugin():
    """Test creating security scan for nonexistent plugin"""
    client = TestClient(app)
    scan = SecurityScan(
        scan_id="scan_123",
        plugin_id="nonexistent",
        version="1.0.0",
        scan_date=datetime.utcnow(),
        vulnerabilities=[],
        risk_score="low",
        passed=True
    )
    response = client.post("/api/v1/plugins/nonexistent/security-scan", json=scan.model_dump(mode='json'))
    assert response.status_code == 404


@pytest.mark.integration
def test_security_scan_nonexistent_version():
    """Test creating security scan for nonexistent version"""
    client = TestClient(app)
    
    # Register plugin first
    plugin = PluginRegistration(
        name="Test Plugin",
        version="1.0.0",
        description="A test plugin",
        author="Test Author",
        category="testing",
        tags=[],
        repository_url="https://github.com/test/plugin",
        license="MIT",
        dependencies=[],
        aitbc_version="1.0.0",
        plugin_type="cli"
    )
    client.post("/api/v1/plugins/register", json=plugin.model_dump())
    
    # Create security scan for nonexistent version
    scan = SecurityScan(
        scan_id="scan_123",
        plugin_id="test_plugin",
        version="2.0.0",
        scan_date=datetime.utcnow(),
        vulnerabilities=[],
        risk_score="low",
        passed=True
    )
    response = client.post("/api/v1/plugins/test_plugin/security-scan", json=scan.model_dump(mode='json'))
    assert response.status_code == 404


@pytest.mark.integration
def test_list_plugins_with_filters():
    """Test listing plugins with filters"""
    client = TestClient(app)
    
    # Register multiple plugins
    plugin1 = PluginRegistration(
        name="Test Plugin 1",
        version="1.0.0",
        description="A test plugin",
        author="Test Author",
        category="testing",
        tags=["test"],
        repository_url="https://github.com/test/plugin1",
        license="MIT",
        dependencies=[],
        aitbc_version="1.0.0",
        plugin_type="cli"
    )
    client.post("/api/v1/plugins/register", json=plugin1.model_dump())
    
    plugin2 = PluginRegistration(
        name="Production Plugin",
        version="1.0.0",
        description="A production plugin",
        author="Test Author",
        category="production",
        tags=["prod"],
        repository_url="https://github.com/test/plugin2",
        license="MIT",
        dependencies=[],
        aitbc_version="1.0.0",
        plugin_type="web"
    )
    client.post("/api/v1/plugins/register", json=plugin2.model_dump())
    
    # Filter by category
    response = client.get("/api/v1/plugins?category=testing")
    assert response.status_code == 200
    data = response.json()
    assert data["total_plugins"] == 1
    assert data["plugins"][0]["category"] == "testing"


@pytest.mark.integration
def test_list_plugins_with_search():
    """Test listing plugins with search"""
    client = TestClient(app)
    
    # Register plugin
    plugin = PluginRegistration(
        name="Test Plugin",
        version="1.0.0",
        description="A test plugin for testing",
        author="Test Author",
        category="testing",
        tags=["test"],
        repository_url="https://github.com/test/plugin",
        license="MIT",
        dependencies=[],
        aitbc_version="1.0.0",
        plugin_type="cli"
    )
    client.post("/api/v1/plugins/register", json=plugin.model_dump())
    
    # Search for plugin
    response = client.get("/api/v1/plugins?search=test")
    assert response.status_code == 200
    data = response.json()
    assert data["total_plugins"] == 1


@pytest.mark.integration
def test_security_scan_failed():
    """Test security scan that failed"""
    client = TestClient(app)
    
    # Register plugin first
    plugin = PluginRegistration(
        name="Test Plugin",
        version="1.0.0",
        description="A test plugin",
        author="Test Author",
        category="testing",
        tags=[],
        repository_url="https://github.com/test/plugin",
        license="MIT",
        dependencies=[],
        aitbc_version="1.0.0",
        plugin_type="cli"
    )
    client.post("/api/v1/plugins/register", json=plugin.model_dump())
    
    # Add version first
    version = PluginVersion(
        version="1.0.0",
        changelog="Initial release",
        download_url="https://github.com/test/plugin/archive/v1.0.0.tar.gz",
        checksum="abc123",
        aitbc_compatibility=["1.0.0"],
        release_date=datetime.utcnow()
    )
    client.post("/api/v1/plugins/test_plugin/versions", json=version.model_dump(mode='json'))
    
    # Create failed security scan
    scan = SecurityScan(
        scan_id="scan_123",
        plugin_id="test_plugin",
        version="1.0.0",
        scan_date=datetime.utcnow(),
        vulnerabilities=[{"severity": "high", "description": "Critical issue"}],
        risk_score="high",
        passed=False
    )
    response = client.post("/api/v1/plugins/test_plugin/security-scan", json=scan.model_dump(mode='json'))
    assert response.status_code == 200
    data = response.json()
    assert data["passed"] is False
    assert data["risk_score"] == "high"
