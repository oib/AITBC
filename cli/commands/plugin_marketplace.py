"""
Plugin Marketplace CLI Commands for AITBC
Commands for browsing, purchasing, and managing plugins from the marketplace
"""

import click
import json
import requests
from datetime import datetime
from typing import Dict, Any, List, Optional

@click.group()
def plugin_marketplace():
    """Plugin marketplace commands"""
    pass

@plugin_marketplace.command()
@click.option('--category', help='Filter by category')
@click.option('--price-min', type=float, help='Minimum price filter')
@click.option('--price-max', type=float, help='Maximum price filter')
@click.option('--rating-min', type=float, help='Minimum rating filter')
@click.option('--sort', default='popularity', help='Sort by (popularity, rating, price, newest)')
@click.option('--limit', type=int, default=20, help='Number of results')
@click.option('--test-mode', is_flag=True, help='Run in test mode')
def browse(category, price_min, price_max, rating_min, sort, limit, test_mode):
    """Browse plugins in the marketplace"""
    try:
        params = {
            "limit": limit,
            "sort": sort
        }
        
        if category:
            params["category"] = category
        if price_min is not None:
            params["price_min"] = price_min
        if price_max is not None:
            params["price_max"] = price_max
        if rating_min is not None:
            params["rating_min"] = rating_min
        
        if test_mode:
            # Mock marketplace data
            mock_plugins = [
                {
                    "plugin_id": "trading-bot",
                    "name": "Advanced Trading Bot",
                    "version": "1.0.0",
                    "description": "Automated trading bot with advanced algorithms",
                    "author": "AITBC Team",
                    "category": "trading",
                    "price": 99.99,
                    "rating": 4.5,
                    "reviews_count": 42,
                    "downloads": 1250,
                    "featured": True,
                    "tags": ["trading", "automation", "bot"],
                    "preview_image": "https://marketplace.aitbc.dev/plugins/trading-bot/preview.png"
                },
                {
                    "plugin_id": "oracle-feed",
                    "name": "Oracle Price Feed",
                    "version": "2.1.0",
                    "description": "Real-time price oracle integration",
                    "author": "Oracle Developer",
                    "category": "oracle",
                    "price": 49.99,
                    "rating": 4.8,
                    "reviews_count": 28,
                    "downloads": 890,
                    "featured": True,
                    "tags": ["oracle", "price", "feed"],
                    "preview_image": "https://marketplace.aitbc.dev/plugins/oracle-feed/preview.png"
                },
                {
                    "plugin_id": "security-scanner",
                    "name": "Security Scanner Pro",
                    "version": "3.0.0",
                    "description": "Advanced security scanning and vulnerability detection",
                    "author": "Security Labs",
                    "category": "security",
                    "price": 199.99,
                    "rating": 4.7,
                    "reviews_count": 15,
                    "downloads": 567,
                    "featured": False,
                    "tags": ["security", "scanning", "vulnerability"],
                    "preview_image": "https://marketplace.aitbc.dev/plugins/security-scanner/preview.png"
                }
            ]
            
            click.echo("🛒 Plugin Marketplace:")
            click.echo("=" * 60)
            
            for plugin in mock_plugins[:limit]:
                featured_badge = "⭐" if plugin.get('featured') else ""
                click.echo(f"{featured_badge} {plugin['name']} (v{plugin['version']})")
                click.echo(f"   💰 Price: ${plugin['price']}")
                click.echo(f"   ⭐ Rating: {plugin['rating']}/5.0 ({plugin['reviews_count']} reviews)")
                click.echo(f"   📥 Downloads: {plugin['downloads']}")
                click.echo(f"   📂 Category: {plugin['category']}")
                click.echo(f"   👤 Author: {plugin['author']}")
                click.echo(f"   📝 {plugin['description'][:60]}...")
                click.echo("")
            
            return
        
        # Fetch from marketplace service
        config = get_config()
        response = requests.get(
            f"{config.coordinator_url}/api/v1/marketplace/browse",
            params=params,
            headers={"Authorization": f"Bearer {config.api_key}"},
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            plugins = result.get("plugins", [])
            
            click.echo("🛒 Plugin Marketplace:")
            click.echo("=" * 60)
            
            for plugin in plugins:
                featured_badge = "⭐" if plugin.get('featured') else ""
                click.echo(f"{featured_badge} {plugin['name']} (v{plugin['version']})")
                click.echo(f"   💰 Price: ${plugin.get('price', 0.0)}")
                click.echo(f"   ⭐ Rating: {plugin.get('rating', 0)}/5.0 ({plugin.get('reviews_count', 0)} reviews)")
                click.echo(f"   📥 Downloads: {plugin.get('downloads', 0)}")
                click.echo(f"   📂 Category: {plugin.get('category', 'N/A')}")
                click.echo(f"   👤 Author: {plugin.get('author', 'N/A')}")
                click.echo(f"   📝 {plugin['description'][:60]}...")
                click.echo("")
        else:
            click.echo(f"❌ Failed to browse marketplace: {response.text}", err=True)
            
    except Exception as e:
        click.echo(f"❌ Error browsing marketplace: {str(e)}", err=True)

@plugin_marketplace.command()
@click.argument('plugin_id')
@click.option('--test-mode', is_flag=True, help='Run in test mode')
def details(plugin_id, test_mode):
    """Get detailed information about a marketplace plugin"""
    try:
        if test_mode:
            # Mock plugin details
            mock_plugin = {
                "plugin_id": plugin_id,
                "name": "Advanced Trading Bot",
                "version": "1.0.0",
                "description": "Automated trading bot with advanced algorithms and machine learning capabilities. Features include real-time market analysis, automated trading strategies, risk management, and portfolio optimization.",
                "author": "AITBC Team",
                "category": "trading",
                "price": 99.99,
                "rating": 4.5,
                "reviews_count": 42,
                "downloads": 1250,
                "featured": True,
                "tags": ["trading", "automation", "bot", "ml", "risk-management"],
                "repository": "https://github.com/aitbc/trading-bot",
                "homepage": "https://aitbc.dev/plugins/trading-bot",
                "license": "MIT",
                "created_at": "2024-01-15T10:30:00Z",
                "updated_at": "2024-03-01T14:20:00Z",
                "preview_image": "https://marketplace.aitbc.dev/plugins/trading-bot/preview.png",
                "screenshots": [
                    "https://marketplace.aitbc.dev/plugins/trading-bot/screenshot1.png",
                    "https://marketplace.aitbc.dev/plugins/trading-bot/screenshot2.png"
                ],
                "documentation": "https://docs.aitbc.dev/plugins/trading-bot",
                "support": "support@aitbc.dev",
                "compatibility": {
                    "aitbc_version": ">=1.0.0",
                    "python_version": ">=3.8",
                    "dependencies": ["exchange-integration", "oracle-feed"]
                },
                "pricing": {
                    "type": "one-time",
                    "amount": 99.99,
                    "currency": "USD",
                    "includes_support": True,
                    "includes_updates": True
                },
                "reviews": [
                    {
                        "id": 1,
                        "user": "trader123",
                        "rating": 5,
                        "title": "Excellent trading bot!",
                        "comment": "This bot has significantly improved my trading performance. Highly recommended!",
                        "date": "2024-02-15T10:30:00Z"
                    },
                    {
                        "id": 2,
                        "user": "alice_trader",
                        "rating": 4,
                        "title": "Good but needs improvements",
                        "comment": "Great features but the UI could be more intuitive.",
                        "date": "2024-02-10T14:20:00Z"
                    }
                ]
            }
            
            click.echo(f"🛒 Plugin Details: {mock_plugin['name']}")
            click.echo("=" * 60)
            click.echo(f"📦 Version: {mock_plugin['version']}")
            click.echo(f"👤 Author: {mock_plugin['author']}")
            click.echo(f"📂 Category: {mock_plugin['category']}")
            click.echo(f"💰 Price: ${mock_plugin['price']} {mock_plugin['pricing']['currency']}")
            click.echo(f"⭐ Rating: {mock_plugin['rating']}/5.0 ({mock_plugin['reviews_count']} reviews)")
            click.echo(f"📥 Downloads: {mock_plugin['downloads']}")
            click.echo(f"🏷️  Tags: {', '.join(mock_plugin['tags'])}")
            click.echo(f"📄 License: {mock_plugin['license']}")
            click.echo(f"📅 Created: {mock_plugin['created_at']}")
            click.echo(f"🔄 Updated: {mock_plugin['updated_at']}")
            click.echo("")
            click.echo("📝 Description:")
            click.echo(f"   {mock_plugin['description']}")
            click.echo("")
            click.echo("💰 Pricing:")
            click.echo(f"   Type: {mock_plugin['pricing']['type']}")
            click.echo(f"   Amount: ${mock_plugin['pricing']['amount']} {mock_plugin['pricing']['currency']}")
            click.echo(f"   Includes Support: {'Yes' if mock_plugin['pricing']['includes_support'] else 'No'}")
            click.echo(f"   Includes Updates: {'Yes' if mock_plugin['pricing']['includes_updates'] else 'No'}")
            click.echo("")
            click.echo("🔗 Links:")
            click.echo(f"   📦 Repository: {mock_plugin['repository']}")
            click.echo(f"   🌐 Homepage: {mock_plugin['homepage']}")
            click.echo(f"   📚 Documentation: {mock_plugin['documentation']}")
            click.echo(f"   📧 Support: {mock_plugin['support']}")
            click.echo("")
            click.echo("🔧 Compatibility:")
            click.echo(f"   AITBC Version: {mock_plugin['compatibility']['aitbc_version']}")
            click.echo(f"   Python Version: {mock_plugin['compatibility']['python_version']}")
            click.echo(f"   Dependencies: {', '.join(mock_plugin['compatibility']['dependencies'])}")
            click.echo("")
            click.echo("⭐ Recent Reviews:")
            for review in mock_plugin['reviews'][:3]:
                stars = "⭐" * review['rating']
                click.echo(f"   {stars} {review['title']}")
                click.echo(f"   👤 {review['user']} - {review['date']}")
                click.echo(f"   📝 {review['comment']}")
                click.echo("")
            return
        
        # Fetch from marketplace service
        config = get_config()
        response = requests.get(
            f"{config.coordinator_url}/api/v1/marketplace/plugins/{plugin_id}",
            headers={"Authorization": f"Bearer {config.api_key}"},
            timeout=30
        )
        
        if response.status_code == 200:
            plugin = response.json()
            
            click.echo(f"🛒 Plugin Details: {plugin['name']}")
            click.echo("=" * 60)
            click.echo(f"📦 Version: {plugin['version']}")
            click.echo(f"👤 Author: {plugin['author']}")
            click.echo(f"📂 Category: {plugin['category']}")
            click.echo(f"💰 Price: ${plugin.get('price', 0.0)}")
            click.echo(f"⭐ Rating: {plugin.get('rating', 0)}/5.0 ({plugin.get('reviews_count', 0)} reviews)")
            click.echo(f"📥 Downloads: {plugin.get('downloads', 0)}")
            click.echo(f"🏷️  Tags: {', '.join(plugin.get('tags', []))}")
            click.echo(f"📄 License: {plugin.get('license', 'N/A')}")
            click.echo(f"📅 Created: {plugin['created_at']}")
            click.echo(f"🔄 Updated: {plugin['updated_at']}")
            click.echo("")
            click.echo("📝 Description:")
            click.echo(f"   {plugin['description']}")
        else:
            click.echo(f"❌ Plugin not found: {response.text}", err=True)
            
    except Exception as e:
        click.echo(f"❌ Error getting plugin details: {str(e)}", err=True)

@plugin_marketplace.command()
@click.argument('plugin_id')
@click.option('--test-mode', is_flag=True, help='Run in test mode')
def purchase(plugin_id, test_mode):
    """Purchase a plugin from the marketplace"""
    try:
        if test_mode:
            click.echo(f"💰 Purchase initiated (test mode)")
            click.echo(f"📦 Plugin ID: {plugin_id}")
            click.echo(f"💳 Payment method: Test Card")
            click.echo(f"💰 Amount: $99.99")
            click.echo(f"✅ Purchase completed successfully")
            click.echo(f"📧 License key: TEST-KEY-{plugin_id.upper()}")
            click.echo(f"📥 Download link: https://marketplace.aitbc.dev/download/{plugin_id}")
            return
        
        # Get plugin details first
        config = get_config()
        response = requests.get(
            f"{config.coordinator_url}/api/v1/marketplace/plugins/{plugin_id}",
            headers={"Authorization": f"Bearer {config.api_key}"},
            timeout=30
        )
        
        if response.status_code != 200:
            click.echo(f"❌ Plugin not found: {response.text}", err=True)
            return
        
        plugin = response.json()
        
        # Create purchase order
        purchase_data = {
            "plugin_id": plugin_id,
            "price": plugin.get('price', 0.0),
            "currency": plugin.get('pricing', {}).get('currency', 'USD'),
            "payment_method": "credit_card",
            "purchased_at": datetime.utcnow().isoformat()
        }
        
        response = requests.post(
            f"{config.coordinator_url}/api/v1/marketplace/purchase",
            json=purchase_data,
            headers={"Authorization": f"Bearer {config.api_key}"},
            timeout=30
        )
        
        if response.status_code == 201:
            result = response.json()
            click.echo(f"💰 Purchase completed successfully!")
            click.echo(f"📦 Plugin: {result['plugin_name']}")
            click.echo(f"💳 Amount: ${result['amount']} {result['currency']}")
            click.echo(f"📧 License Key: {result['license_key']}")
            click.echo(f"📥 Download: {result['download_url']}")
            click.echo(f"📧 Support: {result['support_email']}")
        else:
            click.echo(f"❌ Purchase failed: {response.text}", err=True)
            
    except Exception as e:
        click.echo(f"❌ Error purchasing plugin: {str(e)}", err=True)

@plugin_marketplace.command()
@click.option('--category', help='Filter by category')
@click.option('--price-min', type=float, help='Minimum price filter')
@click.option('--price-max', type=float, help='Maximum price filter')
@click.option('--rating-min', type=float, help='Minimum rating filter')
@click.option('--limit', type=int, default=10, help='Number of results')
@click.option('--test-mode', is_flag=True, help='Run in test mode')
def featured(category, price_min, price_max, rating_min, limit, test_mode):
    """Browse featured plugins"""
    try:
        params = {
            "featured": True,
            "limit": limit
        }
        
        if category:
            params["category"] = category
        if price_min is not None:
            params["price_min"] = price_min
        if price_max is not None:
            params["price_max"] = price_max
        if rating_min is not None:
            params["rating_min"] = rating_min
        
        if test_mode:
            # Mock featured plugins
            mock_featured = [
                {
                    "plugin_id": "trading-bot",
                    "name": "Advanced Trading Bot",
                    "version": "1.0.0",
                    "description": "Automated trading bot with advanced algorithms",
                    "author": "AITBC Team",
                    "category": "trading",
                    "price": 99.99,
                    "rating": 4.5,
                    "downloads": 1250,
                    "featured": True,
                    "featured_reason": "Top-rated trading automation tool"
                },
                {
                    "plugin_id": "oracle-feed",
                    "name": "Oracle Price Feed",
                    "version": "2.1.0",
                    "description": "Real-time price oracle integration",
                    "author": "Oracle Developer",
                    "category": "oracle",
                    "price": 49.99,
                    "rating": 4.8,
                    "downloads": 890,
                    "featured": True,
                    "featured_reason": "Most reliable oracle integration"
                }
            ]
            
            click.echo("⭐ Featured Plugins:")
            click.echo("=" * 60)
            
            for plugin in mock_featured[:limit]:
                click.echo(f"⭐ {plugin['name']} (v{plugin['version']})")
                click.echo(f"   💰 Price: ${plugin['price']}")
                click.echo(f"   ⭐ Rating: {plugin['rating']}/5.0")
                click.echo(f"   📥 Downloads: {plugin['downloads']}")
                click.echo(f"   📂 Category: {plugin['category']}")
                click.echo(f"   👤 Author: {plugin['author']}")
                click.echo(f"   🏆 {plugin['featured_reason']}")
                click.echo("")
            
            return
        
        # Fetch from marketplace service
        config = get_config()
        response = requests.get(
            f"{config.coordinator_url}/api/v1/marketplace/featured",
            params=params,
            headers={"Authorization": f"Bearer {config.api_key}"},
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            plugins = result.get("plugins", [])
            
            click.echo("⭐ Featured Plugins:")
            click.echo("=" * 60)
            
            for plugin in plugins:
                click.echo(f"⭐ {plugin['name']} (v{plugin['version']})")
                click.echo(f"   💰 Price: ${plugin.get('price', 0.0)}")
                click.echo(f"   ⭐ Rating: {plugin.get('rating', 0)}/5.0")
                click.echo(f"   📥 Downloads: {plugin.get('downloads', 0)}")
                click.echo(f"   📂 Category: {plugin.get('category', 'N/A')}")
                click.echo(f"   👤 Author: {plugin.get('author', 'N/A')}")
                click.echo(f"   🏆 {plugin.get('featured_reason', 'Featured plugin')}")
                click.echo("")
        else:
            click.echo(f"❌ Failed to get featured plugins: {response.text}", err=True)
            
    except Exception as e:
        click.echo(f"❌ Error getting featured plugins: {str(e)}", err=True)

@plugin_marketplace.command()
@click.option('--test-mode', is_flag=True, help='Run in test mode')
def my_purchases(test_mode):
    """View your purchased plugins"""
    try:
        if test_mode:
            # Mock purchase history
            mock_purchases = [
                {
                    "plugin_id": "trading-bot",
                    "name": "Advanced Trading Bot",
                    "version": "1.0.0",
                    "purchase_date": "2024-02-15T10:30:00Z",
                    "price": 99.99,
                    "license_key": "TEST-KEY-TRADING-BOT",
                    "status": "active",
                    "download_count": 5
                },
                {
                    "plugin_id": "oracle-feed",
                    "name": "Oracle Price Feed",
                    "version": "2.1.0",
                    "purchase_date": "2024-02-10T14:20:00Z",
                    "price": 49.99,
                    "license_key": "TEST-KEY-ORACLE-FEED",
                    "status": "active",
                    "download_count": 3
                }
            ]
            
            click.echo("📋 Your Purchased Plugins:")
            click.echo("=" * 60)
            
            for purchase in mock_purchases:
                status_icon = "✅" if purchase['status'] == 'active' else "⏳"
                click.echo(f"{status_icon} {purchase['name']} (v{purchase['version']})")
                click.echo(f"   📅 Purchased: {purchase['purchase_date']}")
                click.echo(f"   💰 Price: ${purchase['price']}")
                click.echo(f"   📧 License Key: {purchase['license_key']}")
                click.echo(f"   📥 Downloads: {purchase['download_count']}")
                click.echo("")
            
            return
        
        # Get user's purchases
        config = get_config()
        response = requests.get(
            f"{config.coordinator_url}/api/v1/marketplace/purchases",
            headers={"Authorization": f"Bearer {config.api_key}"},
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            purchases = result.get("purchases", [])
            
            click.echo("📋 Your Purchased Plugins:")
            click.echo("=" * 60)
            
            for purchase in purchases:
                status_icon = "✅" if purchase['status'] == 'active' else "⏳"
                click.echo(f"{status_icon} {purchase['plugin_name']} (v{purchase['version']})")
                click.echo(f"   📅 Purchased: {purchase['purchase_date']}")
                click.echo(f"   💰 Price: ${purchase['price']} {purchase['currency']}")
                click.echo(f"   📧 License Key: {purchase['license_key']}")
                click.echo(f"   📥 Downloads: {purchase.get('download_count', 0)}")
                click.echo("")
        else:
            click.echo(f"❌ Failed to get purchases: {response.text}", err=True)
            
    except Exception as e:
        click.echo(f"❌ Error getting purchases: {str(e)}", err=True)

@plugin_marketplace.command()
@click.argument('plugin_id')
@click.option('--license-key', help='License key for the plugin')
@click.option('--test-mode', is_flag=True, help='Run in test mode')
def download(plugin_id, license_key, test_mode):
    """Download a purchased plugin"""
    try:
        if test_mode:
            click.echo(f"📥 Download started (test mode)")
            click.echo(f"📦 Plugin ID: {plugin_id}")
            click.echo(f"📧 License Key: {license_key or 'TEST-KEY'}")
            click.echo(f"✅ Download completed successfully")
            click.echo(f"📁 Download location: /tmp/{plugin_id}.zip")
            return
        
        # Validate license key
        config = get_config()
        response = requests.post(
            f"{config.coordinator_url}/api/v1/marketplace/download/{plugin_id}",
            json={"license_key": license_key},
            headers={"Authorization": f"Bearer {config.api_key}"},
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            click.echo(f"📥 Download started!")
            click.echo(f"📦 Plugin: {result['plugin_name']}")
            click.echo(f"📁 Download URL: {result['download_url']}")
            click.echo(f"📦 File Size: {result['file_size_mb']} MB")
            click.echo(f"🔑 Checksum: {result['checksum']}")
            
            # Download the file
            download_response = requests.get(result['download_url'], timeout=60)
            
            if download_response.status_code == 200:
                filename = f"{plugin_id}.zip"
                with open(filename, 'wb') as f:
                    f.write(download_response.content)
                
                click.echo(f"✅ Download completed!")
                click.echo(f"📁 Saved as: {filename}")
                click.echo(f"📁 Size: {len(download_response.content) / 1024 / 1024:.1f} MB")
            else:
                click.echo(f"❌ Download failed: {download_response.text}", err=True)
        else:
            click.echo(f"❌ Download failed: {response.text}", err=True)
            
    except Exception as e:
        click.echo(f"❌ Error downloading plugin: {str(e)}", err=True)

# Helper function to get config
def get_config():
    """Get CLI configuration"""
    try:
        from config import get_config
        return get_config()
    except ImportError:
        # Fallback for testing
        from types import SimpleNamespace
        return SimpleNamespace(
            coordinator_url="http://localhost:8014",
            api_key="test-api-key"
        )

if __name__ == "__main__":
    plugin_marketplace()
