"""
Plugin Registry CLI Commands for AITBC
Commands for managing plugin registration, versioning, and discovery
"""

import click
import json
import requests
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

@click.group()
def plugin_registry():
    """Plugin registry management commands"""
    pass

@plugin_registry.command()
@click.option('--plugin-id', help='Plugin ID to register')
@click.option('--name', required=True, help='Plugin name')
@click.option('--version', required=True, help='Plugin version')
@click.option('--description', required=True, help='Plugin description')
@click.option('--author', required=True, help='Plugin author')
@click.option('--category', required=True, help='Plugin category')
@click.option('--tags', help='Plugin tags (comma-separated)')
@click.option('--repository', help='Source repository URL')
@click.option('--homepage', help='Plugin homepage URL')
@click.option('--license', help='Plugin license')
@click.option('--test-mode', is_flag=True, help='Run in test mode')
def register(plugin_id, name, version, description, author, category, tags, repository, homepage, license, test_mode):
    """Register a new plugin in the registry"""
    try:
        if not plugin_id:
            plugin_id = name.lower().replace(' ', '-').replace('_', '-')
        
        # Create plugin registration data
        plugin_data = {
            "plugin_id": plugin_id,
            "name": name,
            "version": version,
            "description": description,
            "author": author,
            "category": category,
            "tags": tags.split(',') if tags else [],
            "repository": repository,
            "homepage": homepage,
            "license": license,
            "status": "active",
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
            "downloads": 0,
            "rating": 0.0,
            "reviews_count": 0
        }
        
        if test_mode:
            # Mock registration for testing
            plugin_data["registration_id"] = f"reg_{int(datetime.utcnow().timestamp())}"
            plugin_data["status"] = "registered"
            click.echo(f"✅ Plugin registered successfully (test mode)")
            click.echo(f"📋 Plugin ID: {plugin_data['plugin_id']}")
            click.echo(f"📦 Version: {plugin_data['version']}")
            click.echo(f"📝 Description: {plugin_data['description']}")
            return
        
        # Send to registry service
        config = get_config()
        response = requests.post(
            f"{config.coordinator_url}/api/v1/plugins/register",
            json=plugin_data,
            headers={"Authorization": f"Bearer {config.api_key}"},
            timeout=30
        )
        
        if response.status_code == 201:
            result = response.json()
            click.echo(f"✅ Plugin registered successfully")
            click.echo(f"📋 Plugin ID: {result['plugin_id']}")
            click.echo(f"📦 Version: {result['version']}")
            click.echo(f"📝 Description: {result['description']}")
        else:
            click.echo(f"❌ Registration failed: {response.text}", err=True)
            
    except Exception as e:
        click.echo(f"❌ Error registering plugin: {str(e)}", err=True)

@plugin_registry.command()
@click.option('--plugin-id', help='Specific plugin ID (optional)')
@click.option('--category', help='Filter by category')
@click.option('--author', help='Filter by author')
@click.option('--status', help='Filter by status')
@click.option('--limit', type=int, default=20, help='Number of results to return')
@click.option('--test-mode', is_flag=True, help='Run in test mode')
def list(plugin_id, category, author, status, limit, test_mode):
    """List registered plugins"""
    try:
        if test_mode:
            # Mock data for testing
            mock_plugins = [
                {
                    "plugin_id": "trading-bot",
                    "name": "Advanced Trading Bot",
                    "version": "1.0.0",
                    "description": "Automated trading bot with advanced algorithms",
                    "author": "AITBC Team",
                    "category": "trading",
                    "tags": ["trading", "automation", "bot"],
                    "status": "active",
                    "downloads": 1250,
                    "rating": 4.5,
                    "reviews_count": 42
                },
                {
                    "plugin_id": "oracle-feed",
                    "name": "Oracle Price Feed",
                    "version": "2.1.0",
                    "description": "Real-time price oracle integration",
                    "author": "Oracle Developer",
                    "category": "oracle",
                    "tags": ["oracle", "price", "feed"],
                    "status": "active",
                    "downloads": 890,
                    "rating": 4.8,
                    "reviews_count": 28
                }
            ]
            
            click.echo("📋 Registered Plugins:")
            click.echo("=" * 60)
            
            for plugin in mock_plugins[:limit]:
                click.echo(f"📦 {plugin['name']} (v{plugin['version']})")
                click.echo(f"   🆔 ID: {plugin['plugin_id']}")
                click.echo(f"   👤 Author: {plugin['author']}")
                click.echo(f"   📂 Category: {plugin['category']}")
                click.echo(f"   ⭐ Rating: {plugin['rating']}/5.0 ({plugin['reviews_count']} reviews)")
                click.echo(f"   📥 Downloads: {plugin['downloads']}")
                click.echo(f"   📝 {plugin['description'][:60]}...")
                click.echo("")
            
            return
        
        # Fetch from registry service
        config = get_config()
        params = {
            "limit": limit
        }
        
        if plugin_id:
            params["plugin_id"] = plugin_id
        if category:
            params["category"] = category
        if author:
            params["author"] = author
        if status:
            params["status"] = status
        
        response = requests.get(
            f"{config.coordinator_url}/api/v1/plugins",
            params=params,
            headers={"Authorization": f"Bearer {config.api_key}"},
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            plugins = result.get("plugins", [])
            
            click.echo("📋 Registered Plugins:")
            click.echo("=" * 60)
            
            for plugin in plugins:
                click.echo(f"📦 {plugin['name']} (v{plugin['version']})")
                click.echo(f"   🆔 ID: {plugin['plugin_id']}")
                click.echo(f"   👤 Author: {plugin['author']}")
                click.echo(f"   📂 Category: {plugin['category']}")
                click.echo(f"   ⭐ Rating: {plugin.get('rating', 0)}/5.0 ({plugin.get('reviews_count', 0)} reviews)")
                click.echo(f"   📥 Downloads: {plugin.get('downloads', 0)}")
                click.echo(f"   📝 {plugin['description'][:60]}...")
                click.echo("")
        else:
            click.echo(f"❌ Failed to list plugins: {response.text}", err=True)
            
    except Exception as e:
        click.echo(f"❌ Error listing plugins: {str(e)}", err=True)

@plugin_registry.command()
@click.argument('plugin_id')
@click.option('--test-mode', is_flag=True, help='Run in test mode')
def info(plugin_id, test_mode):
    """Get detailed information about a specific plugin"""
    try:
        if test_mode:
            # Mock data for testing
            mock_plugin = {
                "plugin_id": plugin_id,
                "name": "Advanced Trading Bot",
                "version": "1.0.0",
                "description": "Automated trading bot with advanced algorithms and machine learning capabilities",
                "author": "AITBC Team",
                "category": "trading",
                "tags": ["trading", "automation", "bot", "ml"],
                "repository": "https://github.com/aitbc/trading-bot",
                "homepage": "https://aitbc.dev/plugins/trading-bot",
                "license": "MIT",
                "status": "active",
                "created_at": "2024-01-15T10:30:00Z",
                "updated_at": "2024-03-01T14:20:00Z",
                "downloads": 1250,
                "rating": 4.5,
                "reviews_count": 42,
                "dependencies": ["exchange-integration", "oracle-feed"],
                "security_scan": {
                    "status": "passed",
                    "scan_date": "2024-03-01T14:20:00Z",
                    "vulnerabilities": 0
                },
                "performance_metrics": {
                    "cpu_usage": 2.5,
                    "memory_usage": 512,
                    "response_time_ms": 45
                }
            }
            
            click.echo(f"📦 Plugin Information: {mock_plugin['name']}")
            click.echo("=" * 60)
            click.echo(f"🆔 Plugin ID: {mock_plugin['plugin_id']}")
            click.echo(f"📦 Version: {mock_plugin['version']}")
            click.echo(f"👤 Author: {mock_plugin['author']}")
            click.echo(f"📂 Category: {mock_plugin['category']}")
            click.echo(f"🏷️  Tags: {', '.join(mock_plugin['tags'])}")
            click.echo(f"📄 License: {mock_plugin['license']}")
            click.echo(f"📊 Status: {mock_plugin['status']}")
            click.echo(f"⭐ Rating: {mock_plugin['rating']}/5.0 ({mock_plugin['reviews_count']} reviews)")
            click.echo(f"📥 Downloads: {mock_plugin['downloads']}")
            click.echo(f"📅 Created: {mock_plugin['created_at']}")
            click.echo(f"🔄 Updated: {mock_plugin['updated_at']}")
            click.echo("")
            click.echo("📝 Description:")
            click.echo(f"   {mock_plugin['description']}")
            click.echo("")
            click.echo("🔗 Links:")
            click.echo(f"   📦 Repository: {mock_plugin['repository']}")
            click.echo(f"   🌐 Homepage: {mock_plugin['homepage']}")
            click.echo("")
            click.echo("🔒 Security Scan:")
            click.echo(f"   Status: {mock_plugin['security_scan']['status']}")
            click.echo(f"   Scan Date: {mock_plugin['security_scan']['scan_date']}")
            click.echo(f"   Vulnerabilities: {mock_plugin['security_scan']['vulnerabilities']}")
            click.echo("")
            click.echo("⚡ Performance Metrics:")
            click.echo(f"   CPU Usage: {mock_plugin['performance_metrics']['cpu_usage']}%")
            click.echo(f"   Memory Usage: {mock_plugin['performance_metrics']['memory_usage']}MB")
            click.echo(f"   Response Time: {mock_plugin['performance_metrics']['response_time_ms']}ms")
            return
        
        # Fetch from registry service
        config = get_config()
        response = requests.get(
            f"{config.coordinator_url}/api/v1/plugins/{plugin_id}",
            headers={"Authorization": f"Bearer {config.api_key}"},
            timeout=30
        )
        
        if response.status_code == 200:
            plugin = response.json()
            
            click.echo(f"📦 Plugin Information: {plugin['name']}")
            click.echo("=" * 60)
            click.echo(f"🆔 Plugin ID: {plugin['plugin_id']}")
            click.echo(f"📦 Version: {plugin['version']}")
            click.echo(f"👤 Author: {plugin['author']}")
            click.echo(f"📂 Category: {plugin['category']}")
            click.echo(f"🏷️  Tags: {', '.join(plugin.get('tags', []))}")
            click.echo(f"📄 License: {plugin.get('license', 'N/A')}")
            click.echo(f"📊 Status: {plugin['status']}")
            click.echo(f"⭐ Rating: {plugin.get('rating', 0)}/5.0 ({plugin.get('reviews_count', 0)} reviews)")
            click.echo(f"📥 Downloads: {plugin.get('downloads', 0)}")
            click.echo(f"📅 Created: {plugin['created_at']}")
            click.echo(f"🔄 Updated: {plugin['updated_at']}")
            click.echo("")
            click.echo("📝 Description:")
            click.echo(f"   {plugin['description']}")
            click.echo("")
            if plugin.get('repository'):
                click.echo("🔗 Links:")
                click.echo(f"   📦 Repository: {plugin['repository']}")
            if plugin.get('homepage'):
                click.echo(f"   🌐 Homepage: {plugin['homepage']}")
        else:
            click.echo(f"❌ Plugin not found: {response.text}", err=True)
            
    except Exception as e:
        click.echo(f"❌ Error getting plugin info: {str(e)}", err=True)

@plugin_registry.command()
@click.argument('plugin_id')
@click.option('--version', required=True, help='New version number')
@click.option('--changelog', required=True, help='Version changelog')
@click.option('--test-mode', is_flag=True, help='Run in test mode')
def update_version(plugin_id, version, changelog, test_mode):
    """Update plugin version"""
    try:
        update_data = {
            "version": version,
            "changelog": changelog,
            "updated_at": datetime.utcnow().isoformat()
        }
        
        if test_mode:
            click.echo(f"✅ Plugin version updated (test mode)")
            click.echo(f"📦 Plugin ID: {plugin_id}")
            click.echo(f"📦 New Version: {version}")
            click.echo(f"📝 Changelog: {changelog}")
            return
        
        # Send to registry service
        config = get_config()
        response = requests.put(
            f"{config.coordinator_url}/api/v1/plugins/{plugin_id}/version",
            json=update_data,
            headers={"Authorization": f"Bearer {config.api_key}"},
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            click.echo(f"✅ Plugin version updated successfully")
            click.echo(f"📦 Plugin ID: {result['plugin_id']}")
            click.echo(f"📦 New Version: {result['version']}")
            click.echo(f"📝 Changelog: {changelog}")
        else:
            click.echo(f"❌ Version update failed: {response.text}", err=True)
            
    except Exception as e:
        click.echo(f"❌ Error updating plugin version: {str(e)}", err=True)

@plugin_registry.command()
@click.option('--query', help='Search query')
@click.option('--category', help='Filter by category')
@click.option('--tags', help='Filter by tags (comma-separated)')
@click.option('--limit', type=int, default=10, help='Number of results')
@click.option('--test-mode', is_flag=True, help='Run in test mode')
def search(query, category, tags, limit, test_mode):
    """Search for plugins"""
    try:
        search_params = {
            "limit": limit
        }
        
        if query:
            search_params["query"] = query
        if category:
            search_params["category"] = category
        if tags:
            search_params["tags"] = tags.split(',')
        
        if test_mode:
            # Mock search results
            mock_results = [
                {
                    "plugin_id": "trading-bot",
                    "name": "Advanced Trading Bot",
                    "version": "1.0.0",
                    "description": "Automated trading bot with advanced algorithms",
                    "relevance_score": 0.95
                },
                {
                    "plugin_id": "oracle-feed",
                    "name": "Oracle Price Feed",
                    "version": "2.1.0",
                    "description": "Real-time price oracle integration",
                    "relevance_score": 0.87
                }
            ]
            
            click.echo(f"🔍 Search Results for '{query or 'all'}':")
            click.echo("=" * 60)
            
            for result in mock_results:
                click.echo(f"📦 {result['name']} (v{result['version']})")
                click.echo(f"   🆔 ID: {result['plugin_id']}")
                click.echo(f"   📝 {result['description'][:60]}...")
                click.echo(f"   📊 Relevance: {result['relevance_score']:.2f}")
                click.echo("")
            
            return
        
        # Search in registry service
        config = get_config()
        response = requests.get(
            f"{config.coordinator_url}/api/v1/plugins/search",
            params=search_params,
            headers={"Authorization": f"Bearer {config.api_key}"},
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            plugins = result.get("plugins", [])
            
            click.echo(f"🔍 Search Results for '{query or 'all'}':")
            click.echo("=" * 60)
            
            for plugin in plugins:
                click.echo(f"📦 {plugin['name']} (v{plugin['version']})")
                click.echo(f"   🆔 ID: {plugin['plugin_id']}")
                click.echo(f"   📝 {plugin['description'][:60]}...")
                click.echo(f"   📊 Relevance: {plugin.get('relevance_score', 0):.2f}")
                click.echo("")
        else:
            click.echo(f"❌ Search failed: {response.text}", err=True)
            
    except Exception as e:
        click.echo(f"❌ Error searching plugins: {str(e)}", err=True)

@plugin_registry.command()
@click.option('--test-mode', is_flag=True, help='Run in test mode')
def status(test_mode):
    """Get plugin registry status"""
    try:
        if test_mode:
            # Mock status data
            status_data = {
                "total_plugins": 156,
                "active_plugins": 142,
                "pending_plugins": 8,
                "inactive_plugins": 6,
                "total_downloads": 45678,
                "categories": {
                    "trading": 45,
                    "oracle": 32,
                    "security": 28,
                    "analytics": 25,
                    "utility": 26
                },
                "recent_registrations": 12,
                "security_scans": {
                    "passed": 148,
                    "failed": 3,
                    "pending": 5
                }
            }
            
            click.echo("📊 Plugin Registry Status:")
            click.echo("=" * 40)
            click.echo(f"📦 Total Plugins: {status_data['total_plugins']}")
            click.echo(f"✅ Active Plugins: {status_data['active_plugins']}")
            click.echo(f"⏳ Pending Plugins: {status_data['pending_plugins']}")
            click.echo(f"❌ Inactive Plugins: {status_data['inactive_plugins']}")
            click.echo(f"📥 Total Downloads: {status_data['total_downloads']}")
            click.echo("")
            click.echo("📂 Categories:")
            for category, count in status_data['categories'].items():
                click.echo(f"   {category}: {count}")
            click.echo("")
            click.echo("🔒 Security Scans:")
            click.echo(f"   ✅ Passed: {status_data['security_scans']['passed']}")
            click.echo(f"   ❌ Failed: {status_data['security_scans']['failed']}")
            click.echo(f"   ⏳ Pending: {status_data['security_scans']['pending']}")
            return
        
        # Get status from registry service
        config = get_config()
        response = requests.get(
            f"{config.coordinator_url}/api/v1/plugins/status",
            headers={"Authorization": f"Bearer {config.api_key}"},
            timeout=30
        )
        
        if response.status_code == 200:
            status = response.json()
            
            click.echo("📊 Plugin Registry Status:")
            click.echo("=" * 40)
            click.echo(f"📦 Total Plugins: {status.get('total_plugins', 0)}")
            click.echo(f"✅ Active Plugins: {status.get('active_plugins', 0)}")
            click.echo(f"⏳ Pending Plugins: {status.get('pending_plugins', 0)}")
            click.echo(f"❌ Inactive Plugins: {status.get('inactive_plugins', 0)}")
            click.echo(f"📥 Total Downloads: {status.get('total_downloads', 0)}")
            click.echo(f"📈 Recent Registrations: {status.get('recent_registrations', 0)}")
        else:
            click.echo(f"❌ Failed to get status: {response.text}", err=True)
            
    except Exception as e:
        click.echo(f"❌ Error getting status: {str(e)}", err=True)

# Helper function to get config
def get_config():
    """Get CLI configuration"""
    try:
        from .config import get_config
        return get_config()
    except ImportError:
        # Fallback for testing
        from types import SimpleNamespace
        return SimpleNamespace(
            coordinator_url="http://localhost:8013",
            api_key="test-api-key"
        )

if __name__ == "__main__":
    plugin_registry()
