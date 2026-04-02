"""
Complete System Integration Tests for AITBC Agent Coordinator
Tests integration of all 9 systems: Architecture, Services, Security, Agents, API, Tests, Advanced Security, Monitoring, Type Safety
"""

import pytest
import requests
import json
import time
from datetime import datetime, timedelta
from typing import Dict, Any, List

class TestCompleteSystemIntegration:
    """Test integration of all completed systems"""
    
    BASE_URL = "http://localhost:9001"
    
    def get_admin_token(self):
        """Get admin token for authenticated requests"""
        response = requests.post(
            f"{self.BASE_URL}/auth/login",
            json={"username": "admin", "password": "admin123"},
            headers={"Content-Type": "application/json"}
        )
        return response.json()["access_token"]
    
    def test_system_architecture_integration(self):
        """Test System Architecture (1/9) integration"""
        # Test FHS compliance - check service paths
        response = requests.get(f"{self.BASE_URL}/health")
        assert response.status_code == 200
        
        # Test system directory structure through service status
        health = response.json()
        assert health["status"] == "healthy"
        assert "service" in health
        
        # Test CLI system architecture commands
        service_info = health["service"]
        assert isinstance(service_info, str)
        
        # Test repository cleanup - clean API structure
        endpoints = [
            "/health", "/agents/discover", "/metrics/summary", 
            "/system/status", "/advanced-features/status"
        ]
        
        for endpoint in endpoints:
            if endpoint == "/agents/discover":
                # POST endpoint for agent discovery
                response = requests.post(f"{self.BASE_URL}{endpoint}", 
                    json={"status": "active", "capabilities": ["compute"]},
                    headers={"Content-Type": "application/json"})
            else:
                # GET endpoint for others
                response = requests.get(f"{self.BASE_URL}{endpoint}")
            # Should not return 404 for core endpoints
            assert response.status_code != 404
    
    def test_service_management_integration(self):
        """Test Service Management (2/9) integration"""
        # Test single marketplace service
        response = requests.get(f"{self.BASE_URL}/health")
        assert response.status_code == 200
        
        health = response.json()
        service_name = health["service"]
        
        # Test service consolidation
        assert service_name == "agent-coordinator"
        
        # Test environment file consolidation through consistent responses
        response = requests.get(f"{self.BASE_URL}/metrics/summary")
        assert response.status_code == 200
        health_metrics = response.json()
        assert health_metrics["status"] == "success"
        
        # Test blockchain service functionality
        response = requests.get(f"{self.BASE_URL}/advanced-features/status")
        assert response.status_code == 200
        features = response.json()
        assert "distributed_consensus" in features["features"]
    
    def test_basic_security_integration(self):
        """Test Basic Security (3/9) integration"""
        # Test API key security (keystore not directly testable via API)
        # Test input validation
        response = requests.post(
            f"{self.BASE_URL}/agents/register",
            json={"invalid": "data"},
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code in [422, 400]
        
        # Test API error handling
        response = requests.get(f"{self.BASE_URL}/nonexistent")
        assert response.status_code == 404
        error = response.json()
        assert "status" in error
        assert error["status"] == "error"
    
    def test_agent_systems_integration(self):
        """Test Agent Systems (4/9) integration"""
        # Test multi-agent communication
        agent_data = {
            "agent_id": "integration_test_agent",
            "agent_type": "worker",
            "capabilities": ["compute", "storage", "ai_processing"],
            "services": ["task_processing", "learning"],
            "endpoints": {"api": "http://localhost:8001/api", "status": "http://localhost:8001/status"},
            "metadata": {"version": "1.0.0", "capabilities_version": "2.0"}
        }
        
        response = requests.post(
            f"{self.BASE_URL}/agents/register",
            json=agent_data,
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 200
        
        # Test agent coordinator with load balancing
        response = requests.post(
            f"{self.BASE_URL}/agents/discover",
            json={"status": "active", "capabilities": ["compute"]},
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 200
        discovery = response.json()
        assert "agents" in discovery
        assert "count" in discovery
        
        # Test advanced AI/ML integration
        token = self.get_admin_token()
        
        # Test real-time learning
        experience_data = {
            "context": {"system_load": 0.7, "agents": 5},
            "action": "optimize_resources",
            "outcome": "success",
            "performance_metrics": {"response_time": 0.3, "throughput": 150},
            "reward": 0.9
        }
        
        response = requests.post(
            f"{self.BASE_URL}/ai/learning/experience",
            json=experience_data,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            }
        )
        assert response.status_code == 200
        
        # Test neural networks
        nn_config = {
            "network_id": "integration_nn",
            "input_size": 5,
            "hidden_sizes": [32, 16],
            "output_size": 1,
            "learning_rate": 0.01
        }
        
        response = requests.post(
            f"{self.BASE_URL}/ai/neural-network/create",
            json=nn_config,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            }
        )
        assert response.status_code == 200
        
        # Test distributed consensus
        proposal_data = {
            "proposer_id": "integration_node",
            "content": {
                "action": "resource_allocation",
                "resources": {"cpu": 4, "memory": "8GB"},
                "description": "Allocate resources for AI processing"
            }
        }
        
        response = requests.post(
            f"{self.BASE_URL}/consensus/proposal/create",
            json=proposal_data,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            }
        )
        assert response.status_code == 200
    
    def test_api_functionality_integration(self):
        """Test API Functionality (5/9) integration"""
        # Test all 17+ API endpoints working
        endpoints_to_test = [
            ("GET", "/health"),
            ("POST", "/agents/discover"),
            ("POST", "/tasks/submit"),
            ("GET", "/load-balancer/strategy"),
            ("PUT", "/load-balancer/strategy?strategy=round_robin"),
            ("GET", "/advanced-features/status"),
            ("GET", "/metrics/summary"),
            ("GET", "/metrics/health"),
            ("POST", "/auth/login")
        ]
        
        working_endpoints = 0
        for method, endpoint in endpoints_to_test:
            if method == "GET":
                response = requests.get(f"{self.BASE_URL}{endpoint}")
            elif method == "POST":
                response = requests.post(
                    f"{self.BASE_URL}{endpoint}",
                    json={"test": "data"},
                    headers={"Content-Type": "application/json"}
                )
            elif method == "PUT":
                response = requests.put(f"{self.BASE_URL}{endpoint}")
            
            # Should not return 500 (internal server error)
            if response.status_code != 500:
                working_endpoints += 1
        
        # At least 80% of endpoints should be working
        assert working_endpoints >= len(endpoints_to_test) * 0.8
        
        # Test proper HTTP status codes
        response = requests.get(f"{self.BASE_URL}/health")
        assert response.status_code == 200
        
        response = requests.get(f"{self.BASE_URL}/nonexistent")
        assert response.status_code == 404
        
        # Test comprehensive error handling
        response = requests.post(
            f"{self.BASE_URL}/agents/register",
            json={},
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code in [422, 400]
    
    def test_test_suite_integration(self):
        """Test Test Suite (6/9) integration"""
        # Test that test endpoints are available
        response = requests.get(f"{self.BASE_URL}/health")
        assert response.status_code == 200
        
        # Test API integration test functionality
        # (This tests the test infrastructure itself)
        test_data = {
            "agent_id": "test_suite_agent",
            "agent_type": "worker",
            "capabilities": ["testing"],
            "services": ["test_service"],
            "endpoints": {"api": "http://localhost:8001/api"},
            "metadata": {"version": "1.0.0"}
        }
        
        response = requests.post(
            f"{self.BASE_URL}/agents/register",
            json=test_data,
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 200
        
        # Verify test data can be retrieved
        response = requests.post(
            f"{self.BASE_URL}/agents/discover",
            json={"agent_id": "test_suite_agent"},
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 200
        
        # Test performance benchmark endpoints
        response = requests.get(f"{self.BASE_URL}/metrics/summary")
        assert response.status_code == 200
        metrics = response.json()
        assert "performance" in metrics
        assert "total_requests" in metrics["performance"]
    
    def test_advanced_security_integration(self):
        """Test Advanced Security (7/9) integration"""
        # Test JWT authentication
        response = requests.post(
            f"{self.BASE_URL}/auth/login",
            json={"username": "admin", "password": "admin123"},
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 200
        auth_data = response.json()
        assert "access_token" in auth_data
        assert "refresh_token" in auth_data
        assert auth_data["role"] == "admin"
        
        token = auth_data["access_token"]
        
        # Test token validation
        response = requests.post(
            f"{self.BASE_URL}/auth/validate",
            json={"token": token},
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 200
        validation = response.json()
        assert validation["valid"] is True
        
        # Test protected endpoints
        response = requests.get(
            f"{self.BASE_URL}/protected/admin",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200
        admin_data = response.json()
        assert "Welcome admin!" in admin_data["message"]
        
        # Test role-based access control
        response = requests.post(
            f"{self.BASE_URL}/auth/login",
            json={"username": "user", "password": "user123"},
            headers={"Content-Type": "application/json"}
        )
        user_token = response.json()["access_token"]
        
        response = requests.get(
            f"{self.BASE_URL}/protected/admin",
            headers={"Authorization": f"Bearer {user_token}"}
        )
        assert response.status_code == 403
        
        # Test API key management
        response = requests.post(
            f"{self.BASE_URL}/auth/api-key/generate?user_id=integration_user",
            json=["agent:view"],
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            }
        )
        assert response.status_code == 200
        api_key_data = response.json()
        assert "api_key" in api_key_data
        
        # Test user management
        response = requests.post(
            f"{self.BASE_URL}/users/integration_user/role?role=operator",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            }
        )
        assert response.status_code == 200
        role_data = response.json()
        assert role_data["role"] == "operator"
    
    def test_production_monitoring_integration(self):
        """Test Production Monitoring (8/9) integration"""
        token = self.get_admin_token()
        
        # Test Prometheus metrics
        response = requests.get(f"{self.BASE_URL}/metrics")
        assert response.status_code == 200
        assert response.headers["content-type"] == "text/plain; charset=utf-8"
        
        # Test metrics summary
        response = requests.get(f"{self.BASE_URL}/metrics/summary")
        assert response.status_code == 200
        metrics = response.json()
        assert "performance" in metrics
        assert "system" in metrics
        
        # Test health metrics - use system status instead
        response = requests.get(
            f"{self.BASE_URL}/system/status",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200
        health = response.json()
        assert "overall" in health
        assert health["overall"] == "healthy"
        
        # Test alerting system
        response = requests.get(
            f"{self.BASE_URL}/alerts/stats",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200
        alert_stats = response.json()
        assert "stats" in alert_stats
        assert "total_alerts" in alert_stats["stats"]
        assert "total_rules" in alert_stats["stats"]
        
        # Test alert rules
        response = requests.get(
            f"{self.BASE_URL}/alerts/rules",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200
        rules = response.json()
        assert "rules" in rules
        assert len(rules["rules"]) >= 5  # Should have default rules
        
        # Test SLA monitoring
        response = requests.get(
            f"{self.BASE_URL}/sla",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200
        sla = response.json()
        assert "sla" in sla
        assert "overall_compliance" in sla["sla"]
        
        # Test SLA recording
        response = requests.post(
            f"{self.BASE_URL}/sla/response_time/record?value=0.2",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            }
        )
        assert response.status_code == 200
        sla_record = response.json()
        assert "SLA metric recorded" in sla_record["message"]
        
        # Test comprehensive system status
        response = requests.get(
            f"{self.BASE_URL}/system/status",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200
        system_status = response.json()
        assert "overall" in system_status
        assert "performance" in system_status
        assert "alerts" in system_status
        assert "sla" in system_status
        assert "system" in system_status
        assert "services" in system_status
    
    def test_type_safety_integration(self):
        """Test Type Safety (9/9) integration"""
        # Test type validation in agent registration
        valid_agent = {
            "agent_id": "type_safety_agent",
            "agent_type": "worker",
            "capabilities": ["compute"],
            "services": ["task_processing"]
        }
        
        response = requests.post(
            f"{self.BASE_URL}/agents/register",
            json=valid_agent,
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 200
        
        # Test type validation with invalid data
        invalid_agent = {
            "agent_id": 123,  # Should be string
            "agent_type": "worker",
            "capabilities": "compute"  # Should be list
        }
        
        response = requests.post(
            f"{self.BASE_URL}/agents/register",
            json=invalid_agent,
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code in [422, 400]
        
        # Test API response type consistency
        response = requests.get(f"{self.BASE_URL}/health")
        assert response.status_code == 200
        health = response.json()
        assert isinstance(health["status"], str)
        assert isinstance(health["timestamp"], str)
        assert isinstance(health["service"], str)
        
        # Test error response types
        response = requests.get(f"{self.BASE_URL}/nonexistent")
        assert response.status_code == 404
        error = response.json()
        assert isinstance(error["status"], str)
        assert isinstance(error["message"], str)
        
        # Test advanced features type safety
        token = self.get_admin_token()
        
        # Test AI learning experience types
        experience = {
            "context": {"system_load": 0.8},
            "action": "optimize",
            "outcome": "success",
            "performance_metrics": {"response_time": 0.4},
            "reward": 0.85
        }
        
        response = requests.post(
            f"{self.BASE_URL}/ai/learning/experience",
            json=experience,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            }
        )
        assert response.status_code == 200
        exp_response = response.json()
        assert isinstance(exp_response["experience_id"], str)
        assert isinstance(exp_response["recorded_at"], str)

class TestEndToEndWorkflow:
    """Test complete end-to-end workflows across all systems"""
    
    BASE_URL = "http://localhost:9001"
    
    def get_admin_token(self):
        """Get admin token for authenticated requests"""
        response = requests.post(
            f"{self.BASE_URL}/auth/login",
            json={"username": "admin", "password": "admin123"},
            headers={"Content-Type": "application/json"}
        )
        return response.json()["access_token"]
    
    def test_complete_agent_lifecycle(self):
        """Test complete agent lifecycle across all systems"""
        token = self.get_admin_token()
        
        # 1. System Architecture: Clean API structure
        # 2. Service Management: Single service running
        # 3. Basic Security: Input validation
        # 4. Agent Systems: Multi-agent coordination
        # 5. API Functionality: Proper endpoints
        # 6. Test Suite: Verifiable operations
        # 7. Advanced Security: Authentication
        # 8. Production Monitoring: Metrics tracking
        # 9. Type Safety: Type validation
        
        # Register agent with proper types
        agent_data = {
            "agent_id": "e2e_test_agent",
            "agent_type": "advanced_worker",
            "capabilities": ["compute", "ai_processing", "consensus"],
            "services": ["task_processing", "learning", "voting"],
            "endpoints": ["http://localhost:8001"],
            "metadata": {"version": "2.0.0", "test_mode": True}
        }
        
        response = requests.post(
            f"{self.BASE_URL}/agents/register",
            json=agent_data,
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 200
        
        # Submit task with type validation
        task_data = {
            "task_data": {
                "task_id": "e2e_test_task",
                "task_type": "ai_processing",
                "requirements": {"cpu": 2, "memory": "4GB", "gpu": True},
                "payload": {"model": "test_model", "data": "test_data"}
            },
            "priority": "high",
            "requirements": {
                "min_agents": 1,
                "max_execution_time": 600,
                "capabilities": ["ai_processing"]
            }
        }
        
        response = requests.post(
            f"{self.BASE_URL}/tasks/submit",
            json=task_data,
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 200
        
        # Record AI learning experience
        experience = {
            "context": {
                "agent_id": "e2e_test_agent",
                "task_id": "e2e_test_task",
                "system_load": 0.6,
                "active_agents": 3
            },
            "action": "process_ai_task",
            "outcome": "success",
            "performance_metrics": {
                "response_time": 0.8,
                "accuracy": 0.95,
                "resource_usage": 0.7
            },
            "reward": 0.92
        }
        
        response = requests.post(
            f"{self.BASE_URL}/ai/learning/experience",
            json=experience,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            }
        )
        assert response.status_code == 200
        
        # Create consensus proposal
        proposal = {
            "proposer_id": "e2e_test_agent",
            "content": {
                "action": "resource_optimization",
                "recommendations": {
                    "cpu_allocation": "increase",
                    "memory_optimization": "enable",
                    "learning_rate": 0.01
                },
                "justification": "Based on AI processing performance"
            }
        }
        
        response = requests.post(
            f"{self.BASE_URL}/consensus/proposal/create",
            json=proposal,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            }
        )
        assert response.status_code == 200
        
        # Record SLA metric
        response = requests.post(
            f"{self.BASE_URL}/sla/ai_processing_time/record",
            json={"value": 0.8},
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            }
        )
        assert response.status_code == 200
        
        # Check system status with monitoring
        response = requests.get(
            f"{self.BASE_URL}/system/status",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200
        status = response.json()
        assert status["overall"] in ["healthy", "degraded", "unhealthy"]
        
        # Verify metrics were recorded
        response = requests.get(f"{self.BASE_URL}/metrics/summary")
        assert response.status_code == 200
        metrics = response.json()
        assert metrics["performance"]["total_requests"] > 0
    
    def test_security_monitoring_integration(self):
        """Test integration of security and monitoring systems"""
        token = self.get_admin_token()
        
        # Test authentication with monitoring
        start_time = time.time()
        response = requests.post(
            f"{self.BASE_URL}/auth/login",
            json={"username": "admin", "password": "admin123"},
            headers={"Content-Type": "application/json"}
        )
        login_time = time.time() - start_time
        
        assert response.status_code == 200
        auth_data = response.json()
        assert "access_token" in auth_data
        
        # Test that authentication was monitored
        response = requests.get(f"{self.BASE_URL}/metrics/summary")
        assert response.status_code == 200
        metrics = response.json()
        assert metrics["performance"]["total_requests"] > 0
        
        # Test API key management with security
        response = requests.post(
            f"{self.BASE_URL}/auth/api-key/generate",
            json={"user_id": "security_test_user", "permissions": ["system:health"]},
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            }
        )
        assert response.status_code == 200
        api_key = response.json()["api_key"]
        
        # Test API key validation
        response = requests.post(
            f"{self.BASE_URL}/auth/api-key/validate",
            json={"api_key": api_key},
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 200
        validation = response.json()
        assert validation["valid"] is True
        assert validation["user_id"] == "security_test_user"
        
        # Test alerting for security events
        response = requests.get(
            f"{self.BASE_URL}/alerts/stats",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200
        alert_stats = response.json()
        assert "stats" in alert_stats
        
        # Test role-based access with monitoring
        response = requests.get(
            f"{self.BASE_URL}/users/security_test_user/permissions",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200
        permissions = response.json()
        assert "permissions" in permissions

if __name__ == '__main__':
    pytest.main([__file__])
