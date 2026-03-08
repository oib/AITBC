"""
Integration Tests for AITBC Multi-Chain Components
Tests end-to-end functionality across all implemented services
"""

import pytest
import asyncio
import json
import time
from datetime import datetime
from pathlib import Path
import subprocess
import requests
from typing import Dict, Any, List

class TestMultiChainIntegration:
    """Test suite for multi-chain integration"""
    
    @pytest.fixture(scope="class")
    def test_config(self):
        """Test configuration for integration tests"""
        return {
            "base_url": "http://localhost",
            "ports": {
                "coordinator": 8001,
                "blockchain": 8007,
                "consensus": 8002,
                "network": 8008,
                "explorer": 8016,
                "wallet_daemon": 8003,
                "exchange": 8010,
                "oracle": 8011,
                "trading": 8012,
                "compliance": 8015,
                "plugin_registry": 8013,
                "plugin_marketplace": 8014,
                "plugin_analytics": 8016,
                "global_infrastructure": 8017,
                "ai_agents": 8018,
                "load_balancer": 8019
            },
            "test_chains": ["ait-devnet", "ait-testnet"],
            "test_wallets": ["test_wallet_1", "test_wallet_2"],
            "timeout": 30
        }
    
    @pytest.fixture(scope="class")
    def services_health(self, test_config):
        """Check if all services are healthy before running tests"""
        healthy_services = {}
        
        for service_name, port in test_config["ports"].items():
            try:
                response = requests.get(f"{test_config['base_url']}:{port}/health", timeout=5)
                if response.status_code == 200:
                    healthy_services[service_name] = True
                    print(f"✅ {service_name} service is healthy")
                else:
                    healthy_services[service_name] = False
                    print(f"❌ {service_name} service returned status {response.status_code}")
            except Exception as e:
                healthy_services[service_name] = False
                print(f"❌ {service_name} service is unreachable: {str(e)}")
        
        return healthy_services
    
    def test_coordinator_health(self, test_config, services_health):
        """Test coordinator service health"""
        assert services_health.get("coordinator", False), "Coordinator service is not healthy"
        
        response = requests.get(f"{test_config['base_url']}:{test_config['ports']['coordinator']}/health")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert data["status"] == "ok"
    
    def test_blockchain_integration(self, test_config, services_health):
        """Test blockchain service integration"""
        assert services_health.get("blockchain", False), "Blockchain service is not healthy"
        
        # Test blockchain health
        response = requests.get(f"{test_config['base_url']}:{test_config['ports']['blockchain']}/health")
        assert response.status_code == 200
        
        # Test chain listing
        response = requests.get(f"{test_config['base_url']}:{test_config['ports']['blockchain']}/rpc/chains")
        assert response.status_code == 200
        chains = response.json()
        assert isinstance(chains, list)
        
        # Test block head
        response = requests.get(f"{test_config['base_url']}:{test_config['ports']['blockchain']}/rpc/head")
        assert response.status_code == 200
        head = response.json()
        assert "height" in head
        assert isinstance(head["height"], int)
    
    def test_consensus_integration(self, test_config, services_health):
        """Test consensus service integration"""
        assert services_health.get("consensus", False), "Consensus service is not healthy"
        
        # Test consensus status
        response = requests.get(f"{test_config['base_url']}:{test_config['ports']['consensus']}/rpc/consensusStatus")
        assert response.status_code == 200
        status = response.json()
        assert "status" in status
        assert status["status"] == "healthy"
        
        # Test validators
        response = requests.get(f"{test_config['base_url']}:{test_config['ports']['consensus']}/rpc/validators")
        assert response.status_code == 200
        validators = response.json()
        assert isinstance(validators, list)
    
    def test_network_integration(self, test_config, services_health):
        """Test network service integration"""
        assert services_health.get("network", False), "Network service is not healthy"
        
        # Test network status
        response = requests.get(f"{test_config['base_url']}:{test_config['ports']['network']}/network/status")
        assert response.status_code == 200
        status = response.json()
        assert "status" in status
        assert status["status"] == "healthy"
        
        # Test peer management
        response = requests.get(f"{test_config['base_url']}:{test_config['ports']['network']}/network/peers")
        assert response.status_code == 200
        peers = response.json()
        assert isinstance(peers, list)
    
    def test_explorer_integration(self, test_config, services_health):
        """Test explorer service integration"""
        assert services_health.get("explorer", False), "Explorer service is not healthy"
        
        # Test explorer health
        response = requests.get(f"{test_config['base_url']}:{test_config['ports']['explorer']}/health")
        assert response.status_code == 200
        
        # Test chains API
        response = requests.get(f"{test_config['base_url']}:{test_config['ports']['explorer']}/api/v1/chains")
        assert response.status_code == 200
        chains = response.json()
        assert "chains" in chains
        assert isinstance(chains["chains"], list)
    
    def test_wallet_daemon_integration(self, test_config, services_health):
        """Test wallet daemon integration"""
        assert services_health.get("wallet_daemon", False), "Wallet daemon service is not healthy"
        
        # Test wallet daemon health
        response = requests.get(f"{test_config['base_url']}:{test_config['ports']['wallet_daemon']}/health")
        assert response.status_code == 200
        
        # Test chain listing
        response = requests.get(f"{test_config['base_url']}:{test_config['ports']['wallet_daemon']}/v1/chains")
        assert response.status_code == 200
        chains = response.json()
        assert isinstance(chains, list)
    
    def test_exchange_integration(self, test_config, services_health):
        """Test exchange service integration"""
        assert services_health.get("exchange", False), "Exchange service is not healthy"
        
        # Test exchange health
        response = requests.get(f"{test_config['base_url']}:{test_config['ports']['exchange']}/health")
        assert response.status_code == 200
        
        # Test trading pairs
        response = requests.get(f"{test_config['base_url']}:{test_config['ports']['exchange']}/api/v1/pairs")
        assert response.status_code == 200
        pairs = response.json()
        assert "pairs" in pairs
        assert isinstance(pairs["pairs"], list)
    
    def test_oracle_integration(self, test_config, services_health):
        """Test oracle service integration"""
        assert services_health.get("oracle", False), "Oracle service is not healthy"
        
        # Test oracle health
        response = requests.get(f"{test_config['base_url']}:{test_config['ports']['oracle']}/health")
        assert response.status_code == 200
        
        # Test price feed
        response = requests.get(f"{test_config['base_url']}:{test_config['ports']['oracle']}/api/v1/price-feed")
        assert response.status_code == 200
        prices = response.json()
        assert isinstance(prices, list)
    
    def test_trading_engine_integration(self, test_config, services_health):
        """Test trading engine integration"""
        assert services_health.get("trading", False), "Trading engine service is not healthy"
        
        # Test trading engine health
        response = requests.get(f"{test_config['base_url']}:{test_config['ports']['trading']}/health")
        assert response.status_code == 200
        
        # Test order book
        response = requests.get(f"{test_config['base_url']}:{test_config['ports']['trading']}/api/v1/orderbook/AITBC-BTC")
        assert response.status_code in [200, 404]  # 404 is acceptable if pair doesn't exist
    
    def test_compliance_integration(self, test_config, services_health):
        """Test compliance service integration"""
        assert services_health.get("compliance", False), "Compliance service is not healthy"
        
        # Test compliance health
        response = requests.get(f"{test_config['base_url']}:{test_config['ports']['compliance']}/health")
        assert response.status_code == 200
        
        # Test dashboard
        response = requests.get(f"{test_config['base_url']}:{test_config['ports']['compliance']}/api/v1/dashboard")
        assert response.status_code == 200
        dashboard = response.json()
        assert "dashboard" in dashboard
    
    def test_plugin_ecosystem_integration(self, test_config, services_health):
        """Test plugin ecosystem integration"""
        # Test plugin registry
        if services_health.get("plugin_registry", False):
            response = requests.get(f"{test_config['base_url']}:{test_config['ports']['plugin_registry']}/health")
            assert response.status_code == 200
            
            response = requests.get(f"{test_config['base_url']}:{test_config['ports']['plugin_registry']}/api/v1/plugins")
            assert response.status_code == 200
            plugins = response.json()
            assert "plugins" in plugins
        
        # Test plugin marketplace
        if services_health.get("plugin_marketplace", False):
            response = requests.get(f"{test_config['base_url']}:{test_config['ports']['plugin_marketplace']}/health")
            assert response.status_code == 200
            
            response = requests.get(f"{test_config['base_url']}:{test_config['ports']['plugin_marketplace']}/api/v1/marketplace/featured")
            assert response.status_code == 200
            featured = response.json()
            assert "featured_plugins" in featured
        
        # Test plugin analytics
        if services_health.get("plugin_analytics", False):
            response = requests.get(f"{test_config['base_url']}:{test_config['ports']['plugin_analytics']}/health")
            assert response.status_code == 200
            
            response = requests.get(f"{test_config['base_url']}:{test_config['ports']['plugin_analytics']}/api/v1/analytics/dashboard")
            assert response.status_code == 200
            analytics = response.json()
            assert "dashboard" in analytics
    
    def test_global_services_integration(self, test_config, services_health):
        """Test global services integration"""
        # Test global infrastructure
        if services_health.get("global_infrastructure", False):
            response = requests.get(f"{test_config['base_url']}:{test_config['ports']['global_infrastructure']}/health")
            assert response.status_code == 200
            
            response = requests.get(f"{test_config['base_url']}:{test_config['ports']['global_infrastructure']}/api/v1/global/dashboard")
            assert response.status_code == 200
            dashboard = response.json()
            assert "dashboard" in dashboard
        
        # Test AI agents
        if services_health.get("ai_agents", False):
            response = requests.get(f"{test_config['base_url']}:{test_config['ports']['ai_agents']}/health")
            assert response.status_code == 200
            
            response = requests.get(f"{test_config['base_url']}:{test_config['ports']['ai_agents']}/api/v1/network/dashboard")
            assert response.status_code == 200
            network = response.json()
            assert "dashboard" in network
        
        # Test load balancer
        if services_health.get("load_balancer", False):
            response = requests.get(f"{test_config['base_url']}:{test_config['ports']['load_balancer']}/health")
            assert response.status_code == 200
            
            response = requests.get(f"{test_config['base_url']}:{test_config['ports']['load_balancer']}/api/v1/dashboard")
            assert response.status_code == 200
            dashboard = response.json()
            assert "dashboard" in dashboard
    
    def test_end_to_end_transaction_flow(self, test_config, services_health):
        """Test complete end-to-end transaction flow"""
        # Skip test if critical services are not healthy
        if not all([
            services_health.get("blockchain", False),
            services_health.get("consensus", False),
            services_health.get("network", False)
        ]):
            pytest.skip("Critical services not healthy for end-to-end test")
        
        # Submit a transaction to blockchain
        transaction_data = {
            "from": "ait1testsender000000000000000000000000000",
            "to": "ait1testreceiver000000000000000000000000",
            "amount": "1000",
            "chain_id": "ait-devnet"
        }
        
        response = requests.post(
            f"{test_config['base_url']}:{test_config['ports']['blockchain']}/rpc/submitTransaction",
            json=transaction_data
        )
        
        # Accept 200 or 400 (invalid transaction is acceptable for integration test)
        assert response.status_code in [200, 400]
        
        if response.status_code == 200:
            result = response.json()
            assert "transaction_id" in result or "error" in result
    
    def test_cli_integration(self, test_config):
        """Test CLI integration with services"""
        # Test CLI help command
        result = subprocess.run(
            ["python", "-m", "aitbc_cli.main", "--help"],
            capture_output=True,
            text=True,
            cwd="/home/oib/windsurf/aitbc/cli"
        )
        
        assert result.returncode == 0
        assert "Usage:" in result.stdout
        
        # Test specific CLI commands
        cli_commands = [
            ["wallet", "--help"],
            ["blockchain", "--help"],
            ["multisig", "--help"],
            ["genesis-protection", "--help"],
            ["transfer-control", "--help"],
            ["compliance", "--help"]
        ]
        
        for command in cli_commands:
            result = subprocess.run(
                ["python", "-m", "aitbc_cli.main"] + command,
                capture_output=True,
                text=True,
                cwd="/home/oib/windsurf/aitbc/cli"
            )
            
            assert result.returncode == 0, f"CLI command {' '.join(command)} failed"
    
    def test_service_discovery(self, test_config, services_health):
        """Test service discovery and inter-service communication"""
        # Test that services can discover each other
        healthy_services = [name for name, healthy in services_health.items() if healthy]
        
        assert len(healthy_services) > 0, "No healthy services found"
        
        # Test that explorer can discover blockchain data
        if services_health.get("explorer") and services_health.get("blockchain"):
            response = requests.get(f"{test_config['base_url']}:{test_config['ports']['explorer']}/api/v1/blocks")
            assert response.status_code == 200
            blocks = response.json()
            assert "blocks" in blocks
            assert isinstance(blocks["blocks"], list)
    
    def test_error_handling(self, test_config, services_health):
        """Test error handling across services"""
        # Test 404 errors
        if services_health.get("blockchain", False):
            response = requests.get(f"{test_config['base_url']}:{test_config['ports']['blockchain']}/rpc/nonexistent")
            assert response.status_code == 404
        
        # Test invalid requests
        if services_health.get("exchange", False):
            response = requests.post(
                f"{test_config['base_url']}:{test_config['ports']['exchange']}/api/v1/orders",
                json={"invalid": "data"}
            )
            assert response.status_code in [400, 422]
    
    def test_performance_metrics(self, test_config, services_health):
        """Test performance metrics collection"""
        # Test that services provide performance metrics
        metric_endpoints = [
            ("blockchain", "/rpc/status"),
            ("consensus", "/rpc/consensusStatus"),
            ("network", "/network/status"),
            ("trading", "/api/v1/engine/stats")
        ]
        
        for service_name, endpoint in metric_endpoints:
            if services_health.get(service_name, False):
                response = requests.get(f"{test_config['base_url']}:{test_config['ports'][service_name]}{endpoint}")
                assert response.status_code == 200
                
                data = response.json()
                # Check for common performance fields
                performance_fields = ["status", "timestamp", "uptime", "performance"]
                found_fields = [field for field in performance_fields if field in data]
                assert len(found_fields) > 0, f"No performance fields found in {service_name} response"

class TestCrossChainIntegration:
    """Test cross-chain functionality"""
    
    @pytest.fixture(scope="class")
    def cross_chain_config(self):
        """Cross-chain test configuration"""
        return {
            "source_chain": "ait-devnet",
            "target_chain": "ait-testnet",
            "test_amount": 1000,
            "test_address": "ait1testcrosschain00000000000000000000"
        }
    
    def test_cross_chain_isolation(self, cross_chain_config):
        """Test that chains are properly isolated"""
        # This test would verify that tokens from one chain cannot be used on another
        # Implementation depends on the specific cross-chain isolation mechanisms
        pass
    
    def test_chain_specific_operations(self, cross_chain_config):
        """Test chain-specific operations"""
        # Test that operations are chain-specific
        pass

class TestSecurityIntegration:
    """Test security integration across services"""
    
    def test_authentication_flow(self):
        """Test authentication across services"""
        # Test that authentication works consistently
        pass
    
    def test_authorization_controls(self):
        """Test authorization controls"""
        # Test that authorization is properly enforced
        pass
    
    def test_encryption_handling(self):
        """Test encryption across services"""
        # Test that sensitive data is properly encrypted
        pass

# Performance and load testing
class TestPerformanceIntegration:
    """Test performance under load"""
    
    def test_concurrent_requests(self, test_config):
        """Test handling of concurrent requests"""
        import concurrent.futures
        import threading
        
        def make_request(service_name, endpoint):
            try:
                response = requests.get(f"{test_config['base_url']}:{test_config['ports'][service_name]}{endpoint}", timeout=5)
                return response.status_code
            except:
                return None
        
        # Test concurrent requests to multiple services
        services_to_test = ["blockchain", "consensus", "network"]
        endpoints = ["/health", "/rpc/status", "/network/status"]
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = []
            for service in services_to_test:
                for endpoint in endpoints:
                    for _ in range(5):  # 5 concurrent requests per service/endpoint
                        future = executor.submit(make_request, service, endpoint)
                        futures.append(future)
            
            results = [future.result() for future in concurrent.futures.as_completed(futures)]
            
            # Check that most requests succeeded
            success_count = len([r for r in results if r in [200, 404]])  # 404 is acceptable for some endpoints
            success_rate = success_count / len(results)
            
            assert success_rate > 0.8, f"Low success rate: {success_rate:.2%}"
    
    def test_response_times(self, test_config, services_health):
        """Test response times are within acceptable limits"""
        acceptable_response_times = {
            "health": 1.0,  # 1 second for health checks
            "rpc": 2.0,    # 2 seconds for RPC calls
            "api": 1.5     # 1.5 seconds for API calls
        }
        
        # Test response times for healthy services
        for service_name, healthy in services_health.items():
            if not healthy:
                continue
            
            # Test health endpoint
            start_time = time.time()
            response = requests.get(f"{test_config['base_url']}:{test_config['ports'][service_name]}/health", timeout=5)
            response_time = time.time() - start_time
            
            assert response_time < acceptable_response_times["health"], \
                f"{service_name} health endpoint too slow: {response_time:.2f}s"

if __name__ == "__main__":
    # Run integration tests
    pytest.main([__file__, "-v", "--tb=short"])
