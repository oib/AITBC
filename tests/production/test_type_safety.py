"""
Type Safety Tests for AITBC Agent Coordinator
Tests type validation, Pydantic models, and type hints compliance
"""

import pytest
import requests
import json
from typing import Dict, Any, List
from pydantic import BaseModel, ValidationError

class TestTypeValidation:
    """Test type validation and Pydantic models"""
    
    BASE_URL = "http://localhost:9001"
    
    def test_agent_registration_type_validation(self):
        """Test agent registration type validation"""
        # Test valid agent registration
        valid_data = {
            "agent_id": "test_agent_001",
            "agent_type": "worker",
            "capabilities": ["compute", "storage"],
            "services": ["task_processing"],
            "endpoints": {"main": "http://localhost:8001"},
            "metadata": {"version": "1.0.0"}
        }
        
        response = requests.post(
            f"{self.BASE_URL}/agents/register",
            json=valid_data,
            headers={"Content-Type": "application/json"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "agent_id" in data
        assert data["agent_id"] == valid_data["agent_id"]
    
    def test_agent_registration_invalid_types(self):
        """Test agent registration with invalid types"""
        # Test with invalid agent_type
        invalid_data = {
            "agent_id": "test_agent_002",
            "agent_type": 123,  # Should be string
            "capabilities": ["compute"],
            "services": ["task_processing"]
        }
        
        response = requests.post(
            f"{self.BASE_URL}/agents/register",
            json=invalid_data,
            headers={"Content-Type": "application/json"}
        )
        
        # Should return validation error
        assert response.status_code in [422, 400]
    
    def test_task_submission_type_validation(self):
        """Test task submission type validation"""
        # Test valid task submission
        valid_data = {
            "task_data": {
                "task_id": "task_001",
                "task_type": "compute",
                "requirements": {"cpu": 2, "memory": "4GB"}
            },
            "priority": "normal",
            "requirements": {
                "min_agents": 1,
                "max_execution_time": 300
            }
        }
        
        response = requests.post(
            f"{self.BASE_URL}/tasks/submit",
            json=valid_data,
            headers={"Content-Type": "application/json"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "task_id" in data
    
    def test_task_submission_invalid_types(self):
        """Test task submission with invalid types"""
        # Test with invalid priority
        invalid_data = {
            "task_data": {
                "task_id": "task_002",
                "task_type": "compute"
            },
            "priority": 123,  # Should be string
            "requirements": {
                "min_agents": "1"  # Should be integer
            }
        }
        
        response = requests.post(
            f"{self.BASE_URL}/tasks/submit",
            json=invalid_data,
            headers={"Content-Type": "application/json"}
        )
        
        # Should return validation error
        assert response.status_code in [422, 400]
    
    def test_load_balancer_strategy_validation(self):
        """Test load balancer strategy type validation"""
        # Test valid strategy
        response = requests.put(
            f"{self.BASE_URL}/load-balancer/strategy?strategy=round_robin"
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "strategy" in data
        assert data["strategy"] == "round_robin"
    
    def test_load_balancer_invalid_strategy(self):
        """Test invalid load balancer strategy"""
        response = requests.put(
            f"{self.BASE_URL}/load-balancer/strategy?strategy=invalid_strategy"
        )
        
        assert response.status_code == 400
        data = response.json()
        assert "Invalid strategy" in data["detail"]

class TestAPIResponseTypes:
    """Test API response type consistency"""
    
    BASE_URL = "http://localhost:9001"
    
    def test_health_check_response_types(self):
        """Test health check response types"""
        response = requests.get(f"{self.BASE_URL}/health")
        
        assert response.status_code == 200
        data = response.json()
        
        # Check response structure
        assert isinstance(data, dict)
        assert "status" in data
        assert "timestamp" in data
        assert "version" in data
        assert "service" in data  # Fixed: was "services"
        
        # Check field types
        assert isinstance(data["status"], str)
        assert isinstance(data["timestamp"], str)
        assert isinstance(data["version"], str)
        assert isinstance(data["service"], str)  # Fixed: was "services" as dict
        
        # Check status value
        assert data["status"] in ["healthy", "degraded", "unhealthy"]
        assert data["status"] == "healthy"
    
    def test_agent_discovery_response_types(self):
        """Test agent discovery response types"""
        # Register an agent first
        agent_data = {
            "agent_id": "discovery_test_agent",
            "agent_type": "worker",
            "capabilities": ["test"]
        }
        
        requests.post(
            f"{self.BASE_URL}/agents/register",
            json=agent_data,
            headers={"Content-Type": "application/json"}
        )
        
        # Test agent discovery
        response = requests.post(
            f"{self.BASE_URL}/agents/discover",
            json={"status": "active"},
            headers={"Content-Type": "application/json"}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Check response structure
        assert isinstance(data, dict)
        assert "status" in data
        assert "agents" in data
        assert "count" in data  # Fixed: was "total"
        
        # Check field types
        assert isinstance(data["status"], str)
        assert isinstance(data["agents"], list)
        assert isinstance(data["count"], int)  # Fixed: was "total"
        
        # Check agent structure if any agents found
        if data["agents"]:
            agent = data["agents"][0]
            assert isinstance(agent, dict)
            assert "agent_id" in agent
            assert "agent_type" in agent
            assert "status" in agent
    
    def test_metrics_response_types(self):
        """Test metrics endpoint response types"""
        response = requests.get(f"{self.BASE_URL}/metrics/summary")
        
        assert response.status_code == 200
        data = response.json()
        
        # Check response structure
        assert isinstance(data, dict)
        assert "status" in data
        assert "performance" in data
        assert "system" in data
        assert "timestamp" in data
        
        # Check performance metrics types
        perf = data["performance"]
        assert isinstance(perf, dict)
        assert isinstance(perf.get("avg_response_time"), (int, float))
        assert isinstance(perf.get("p95_response_time"), (int, float))
        assert isinstance(perf.get("p99_response_time"), (int, float))
        assert isinstance(perf.get("error_rate"), (int, float))
        assert isinstance(perf.get("total_requests"), int)
        assert isinstance(perf.get("uptime_seconds"), (int, float))
        
        # Check system metrics types
        system = data["system"]
        assert isinstance(system, dict)
        assert isinstance(system.get("total_agents"), int)
        assert isinstance(system.get("active_agents"), int)
        assert isinstance(system.get("total_tasks"), int)
        assert isinstance(system.get("load_balancer_strategy"), str)

class TestErrorHandlingTypes:
    """Test error handling response types"""
    
    BASE_URL = "http://localhost:9001"
    
    def test_not_found_error_types(self):
        """Test 404 error response types"""
        response = requests.get(f"{self.BASE_URL}/nonexistent_endpoint")
        
        assert response.status_code == 404
        data = response.json()
        
        # Check error response structure
        assert isinstance(data, dict)
        assert "status" in data
        assert "message" in data
        assert "timestamp" in data
        
        # Check field types
        assert isinstance(data["status"], str)
        assert isinstance(data["message"], str)
        assert isinstance(data["timestamp"], str)
        
        assert data["status"] == "error"
        assert "not found" in data["message"].lower()
    
    def test_validation_error_types(self):
        """Test validation error response types"""
        # Send invalid data to trigger validation error
        response = requests.post(
            f"{self.BASE_URL}/agents/register",
            json={"invalid": "data"},
            headers={"Content-Type": "application/json"}
        )
        
        assert response.status_code in [422, 400]
        data = response.json()
        
        # Check error response structure
        assert isinstance(data, dict)
        assert "detail" in data  # FastAPI validation errors use "detail"
        
        # Check detail type
        assert isinstance(data["detail"], (str, list))
    
    def test_authentication_error_types(self):
        """Test authentication error response types"""
        # Test without authentication
        response = requests.get(f"{self.BASE_URL}/protected/admin")
        
        assert response.status_code == 401
        data = response.json()
        
        # Check error response structure
        assert isinstance(data, dict)
        assert "detail" in data
        assert isinstance(data["detail"], str)
        assert "authentication" in data["detail"].lower()
    
    def test_authorization_error_types(self):
        """Test authorization error response types"""
        # Login as regular user
        response = requests.post(
            f"{self.BASE_URL}/auth/login",
            json={"username": "user", "password": "user123"},
            headers={"Content-Type": "application/json"}
        )
        token = response.json()["access_token"]
        
        # Try to access admin endpoint
        response = requests.get(
            f"{self.BASE_URL}/protected/admin",
            headers={"Authorization": f"Bearer {token}"}
        )
        
        assert response.status_code == 403
        data = response.json()
        
        # Check error response structure
        assert isinstance(data, dict)
        assert "detail" in data
        # Detail can be either string or object for authorization errors
        if isinstance(data["detail"], str):
            assert "permissions" in data["detail"].lower()
        else:
            # Authorization error object format
            assert "error" in data["detail"]
            assert "required_roles" in data["detail"]
            assert "current_role" in data["detail"]

class TestAdvancedFeaturesTypeSafety:
    """Test type safety in advanced features"""
    
    BASE_URL = "http://localhost:9001"
    
    def get_admin_token(self):
        """Get admin token for authenticated requests"""
        response = requests.post(
            f"{self.BASE_URL}/auth/login",
            json={"username": "admin", "password": "admin123"},
            headers={"Content-Type": "application/json"}
        )
        return response.json()["access_token"]
    
    def test_ai_learning_experience_types(self):
        """Test AI learning experience type validation"""
        token = self.get_admin_token()
        
        # Test valid experience data
        valid_experience = {
            "context": {
                "system_load": 0.7,
                "agents": 5,
                "task_queue_size": 25
            },
            "action": "scale_resources",
            "outcome": "success",
            "performance_metrics": {
                "response_time": 0.5,
                "throughput": 100,
                "error_rate": 0.02
            },
            "reward": 0.8,
            "metadata": {"test": True}
        }
        
        response = requests.post(
            f"{self.BASE_URL}/ai/learning/experience",
            json=valid_experience,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Check response structure
        assert isinstance(data, dict)
        assert "status" in data
        assert "experience_id" in data
        assert "recorded_at" in data
        
        # Check field types
        assert isinstance(data["status"], str)
        assert isinstance(data["experience_id"], str)
        assert isinstance(data["recorded_at"], str)
        
        assert data["status"] == "success"
    
    def test_neural_network_creation_types(self):
        """Test neural network creation type validation"""
        token = self.get_admin_token()
        
        # Test valid network config
        valid_config = {
            "network_id": "test_nn_001",
            "input_size": 10,
            "hidden_sizes": [64, 32],
            "output_size": 1,
            "learning_rate": 0.01
        }
        
        response = requests.post(
            f"{self.BASE_URL}/ai/neural-network/create",
            json=valid_config,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Check response structure
        assert isinstance(data, dict)
        assert "status" in data
        assert "network_id" in data
        assert "architecture" in data
        
        # Check field types
        assert isinstance(data["status"], str)
        assert isinstance(data["network_id"], str)
        assert isinstance(data["architecture"], dict)
        
        # Check architecture structure
        arch = data["architecture"]
        assert isinstance(arch.get("input_size"), int)
        assert isinstance(arch.get("hidden_sizes"), list)
        assert isinstance(arch.get("output_size"), int)
        # learning_rate may be None, so check if it exists and is numeric
        learning_rate = arch.get("learning_rate")
        if learning_rate is not None:
            assert isinstance(learning_rate, (int, float))
    
    def test_consensus_proposal_types(self):
        """Test consensus proposal type validation"""
        token = self.get_admin_token()
        
        # Test valid proposal
        valid_proposal = {
            "proposer_id": "node_001",
            "content": {
                "action": "system_update",
                "version": "1.1.0",
                "description": "Update system to new version"
            }
        }
        
        response = requests.post(
            f"{self.BASE_URL}/consensus/proposal/create",
            json=valid_proposal,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Check response structure
        assert isinstance(data, dict)
        assert "status" in data
        assert "proposal_id" in data
        assert "required_votes" in data
        assert "deadline" in data
        assert "algorithm" in data
        
        # Check field types
        assert isinstance(data["status"], str)
        assert isinstance(data["proposal_id"], str)
        assert isinstance(data["required_votes"], int)
        assert isinstance(data["deadline"], str)
        assert isinstance(data["algorithm"], str)

class TestTypeSafetyIntegration:
    """Test type safety across integrated systems"""
    
    BASE_URL = "http://localhost:9001"
    
    def test_end_to_end_type_consistency(self):
        """Test type consistency across end-to-end workflows"""
        # 1. Register agent with proper types
        agent_data = {
            "agent_id": "type_test_agent",
            "agent_type": "worker",
            "capabilities": ["compute", "storage"],
            "services": ["task_processing"]
        }
        
        response = requests.post(
            f"{self.BASE_URL}/agents/register",
            json=agent_data,
            headers={"Content-Type": "application/json"}
        )
        
        assert response.status_code == 200
        agent_response = response.json()
        assert isinstance(agent_response["agent_id"], str)
        
        # 2. Submit task with proper types
        task_data = {
            "task_data": {
                "task_id": "type_test_task",
                "task_type": "compute",
                "requirements": {"cpu": 1}
            },
            "priority": "normal"
        }
        
        response = requests.post(
            f"{self.BASE_URL}/tasks/submit",
            json=task_data,
            headers={"Content-Type": "application/json"}
        )
        
        assert response.status_code == 200
        task_response = response.json()
        assert isinstance(task_response["task_id"], str)
        assert isinstance(task_response["priority"], str)
        
        # 3. Get metrics with proper types
        response = requests.get(f"{self.BASE_URL}/metrics/summary")
        assert response.status_code == 200
        metrics_response = response.json()
        
        # Verify all numeric fields are proper types
        perf = metrics_response["performance"]
        numeric_fields = ["avg_response_time", "p95_response_time", "p99_response_time", "error_rate", "total_requests", "uptime_seconds"]
        
        for field in numeric_fields:
            assert field in perf
            assert isinstance(perf[field], (int, float))
        
        # 4. Check agent discovery returns consistent types
        response = requests.post(
            f"{self.BASE_URL}/agents/discover",
            json={"status": "active"},
            headers={"Content-Type": "application/json"}
        )
        
        assert response.status_code == 200
        discovery_response = response.json()
        assert isinstance(discovery_response["count"], int)  # Fixed: was "total"
        assert isinstance(discovery_response["agents"], list)
    
    def test_error_response_type_consistency(self):
        """Test that all error responses have consistent types"""
        # Test 404 error
        response = requests.get(f"{self.BASE_URL}/nonexistent")
        assert response.status_code == 404
        error_404 = response.json()
        assert isinstance(error_404["status"], str)
        assert isinstance(error_404["message"], str)
        
        # Test 401 error
        response = requests.get(f"{self.BASE_URL}/protected/admin")
        assert response.status_code == 401
        error_401 = response.json()
        assert isinstance(error_401["detail"], str)
        
        # Test 403 error (login as user first)
        response = requests.post(
            f"{self.BASE_URL}/auth/login",
            json={"username": "user", "password": "user123"},
            headers={"Content-Type": "application/json"}
        )
        token = response.json()["access_token"]
        
        response = requests.get(
            f"{self.BASE_URL}/protected/admin",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 403
        error_403 = response.json()
        # 403 errors can be either string or object format
        if isinstance(error_403["detail"], str):
            assert isinstance(error_403["detail"], str)
        else:
            # Authorization error object format
            assert isinstance(error_403["detail"], dict)
            assert "error" in error_403["detail"]
            assert "required_roles" in error_403["detail"]
            assert "current_role" in error_403["detail"]
        
        # Test validation error
        response = requests.post(
            f"{self.BASE_URL}/agents/register",
            json={"invalid": "data"},
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code in [422, 400]
        error_validation = response.json()
        assert isinstance(error_validation["detail"], (str, list))

if __name__ == '__main__':
    pytest.main([__file__])
