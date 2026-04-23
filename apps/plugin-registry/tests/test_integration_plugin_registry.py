"""Integration tests for plugin registry service"""

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


@pytest.mark.integration
def test_root_endpoint():
    """Test root endpoint"""
    client = TestClient(app)
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "AITBC Plugin Registry"
    assert data["status"] == "running"


@pytest.mark.integration
def test_health_check_endpoint():
    """Test health check endpoint"""
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "total_plugins" in data
    assert "total_versions" in data


@pytest.mark.integration
def test_register_plugin():
    """Test plugin registration"""
    client = TestClient(app)
    plugin = PluginRegistration(
        name="Test Plugin",
        version="1.0.0",
        description="A test plugin",
        author="Test Author",
        category="testing",
        tags=["test", "demo"],
        repository_url="https://github.com/test/plugin",
        license="MIT",
        dependencies=[],
        aitbc_version="1.0.0",
        plugin_type="cli"
    )
    response = client.post("/api/v1/plugins/register", json=plugin.model_dump())
    assert response.status_code == 200
    data = response.json()
    assert data["plugin_id"] == "test_plugin"
    assert data["status"] == "registered"
    assert data["name"] == "Test Plugin"


@pytest.mark.integration
def test_register_duplicate_plugin():
    """Test registering duplicate plugin"""
    client = TestClient(app)
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
    
    # First registration
    client.post("/api/v1/plugins/register", json=plugin.model_dump())
    
    # Second registration should fail
    response = client.post("/api/v1/plugins/register", json=plugin.model_dump())
    assert response.status_code == 400


@pytest.mark.integration
def test_add_plugin_version():
    """Test adding plugin version"""
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
    
    # Add version
    version = PluginVersion(
        version="1.1.0",
        changelog="Bug fixes",
        download_url="https://github.com/test/plugin/archive/v1.1.0.tar.gz",
        checksum="def456",
        aitbc_compatibility=["1.0.0"],
        release_date=datetime.utcnow()
    )
    response = client.post("/api/v1/plugins/test_plugin/versions", json=version.model_dump(mode='json'))
    assert response.status_code == 200
    data = response.json()
    assert data["version"] == "1.1.0"
    assert data["status"] == "added"


@pytest.mark.integration
def test_add_duplicate_version():
    """Test adding duplicate version"""
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
    
    # Add version
    version = PluginVersion(
        version="1.1.0",
        changelog="Bug fixes",
        download_url="https://github.com/test/plugin/archive/v1.1.0.tar.gz",
        checksum="def456",
        aitbc_compatibility=["1.0.0"],
        release_date=datetime.utcnow()
    )
    client.post("/api/v1/plugins/test_plugin/versions", json=version.model_dump(mode='json'))
    
    # Add same version again should fail
    response = client.post("/api/v1/plugins/test_plugin/versions", json=version.model_dump(mode='json'))
    assert response.status_code == 400


@pytest.mark.integration
def test_list_plugins():
    """Test listing plugins"""
    client = TestClient(app)
    response = client.get("/api/v1/plugins")
    assert response.status_code == 200
    data = response.json()
    assert "plugins" in data
    assert "total_plugins" in data


@pytest.mark.integration
def test_get_plugin():
    """Test getting specific plugin"""
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
    
    # Get plugin
    response = client.get("/api/v1/plugins/test_plugin")
    assert response.status_code == 200
    data = response.json()
    assert data["plugin_id"] == "test_plugin"
    assert data["name"] == "Test Plugin"


@pytest.mark.integration
def test_get_plugin_not_found():
    """Test getting nonexistent plugin"""
    client = TestClient(app)
    response = client.get("/api/v1/plugins/nonexistent")
    assert response.status_code == 404


@pytest.mark.integration
def test_get_plugin_versions():
    """Test getting plugin versions"""
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
    
    # Get versions
    response = client.get("/api/v1/plugins/test_plugin/versions")
    assert response.status_code == 200
    data = response.json()
    assert data["plugin_id"] == "test_plugin"
    assert "versions" in data


@pytest.mark.integration
def test_download_plugin():
    """Test downloading plugin"""
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
    
    # Download plugin
    response = client.get("/api/v1/plugins/test_plugin/download/1.0.0")
    assert response.status_code == 200
    data = response.json()
    assert data["plugin_id"] == "test_plugin"
    assert data["version"] == "1.0.0"


@pytest.mark.integration
def test_create_security_scan():
    """Test creating security scan"""
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
    
    # Create security scan
    scan = SecurityScan(
        scan_id="scan_123",
        plugin_id="test_plugin",
        version="1.0.0",
        scan_date=datetime.utcnow(),
        vulnerabilities=[],
        risk_score="low",
        passed=True
    )
    response = client.post("/api/v1/plugins/test_plugin/security-scan", json=scan.model_dump(mode='json'))
    assert response.status_code == 200
    data = response.json()
    assert data["scan_id"] == "scan_123"
    assert data["passed"] is True


@pytest.mark.integration
def test_get_plugin_security():
    """Test getting plugin security info"""
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
    
    # Get security info
    response = client.get("/api/v1/plugins/test_plugin/security")
    assert response.status_code == 200
    data = response.json()
    assert data["plugin_id"] == "test_plugin"
    assert "security_scans" in data


@pytest.mark.integration
def test_get_categories():
    """Test getting categories"""
    client = TestClient(app)
    response = client.get("/api/v1/categories")
    assert response.status_code == 200
    data = response.json()
    assert "categories" in data
    assert "total_categories" in data


@pytest.mark.integration
def test_get_tags():
    """Test getting tags"""
    client = TestClient(app)
    response = client.get("/api/v1/tags")
    assert response.status_code == 200
    data = response.json()
    assert "tags" in data
    assert "total_tags" in data


@pytest.mark.integration
def test_get_popular_plugins():
    """Test getting popular plugins"""
    client = TestClient(app)
    response = client.get("/api/v1/analytics/popular")
    assert response.status_code == 200
    data = response.json()
    assert "popular_plugins" in data


@pytest.mark.integration
def test_get_recent_plugins():
    """Test getting recent plugins"""
    client = TestClient(app)
    response = client.get("/api/v1/analytics/recent")
    assert response.status_code == 200
    data = response.json()
    assert "recent_plugins" in data


@pytest.mark.integration
def test_get_analytics_dashboard():
    """Test getting analytics dashboard"""
    client = TestClient(app)
    response = client.get("/api/v1/analytics/dashboard")
    assert response.status_code == 200
    data = response.json()
    assert "dashboard" in data
